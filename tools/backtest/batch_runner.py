"""Resumable batch runner for the backtest harness (Task 3.2).

The :class:`BatchRunner` walks a :class:`CohortManifest` and orchestrates
the **data-collection phase** of the backtest pipeline for each ticker:

1. Build a :class:`BacktestContext` per ticker and persist
   ``_backtest-meta.json`` next to the artifacts.
2. Fetch yfinance OHLC + statements as of ``manifest.as_of`` via
   :class:`YFinanceHistorical` → ``yfinance-raw.json``.
3. For Korean tickers, also fetch DART disclosures via
   :class:`DartHistorical` → ``dart-raw.json``.
4. Walk every fetched payload through
   :class:`LeakageDetector` (strict mode by default) so any leakage
   finding flips the ticker run to ``FAILED`` instead of silently
   carrying poisoned data forward.

FRED macro data is fetched **once per cohort** (not per ticker) since
the same macro snapshot is shared across all tickers in the cohort.
The cohort-level fred-raw.json is written under
``backtest/cohorts/{cohort_id}/fred-raw.json`` and is **idempotent** —
the runner skips the fetch if the file already exists.

Resumability is provided by ``state.json`` next to the cohort root.
The runner saves state after every status transition so an interrupted
run can be resumed without re-fetching tickers that already finished.

Hard scope limits (Phase 1 / Task 3.2)
--------------------------------------

- The runner only **collects data**. It does **not** invoke the analyst
  (Mode C) or critic — that is Chunk 6's smoke-test concern.
- The runner does **not** fetch SEC filings. SEC data is delivered to
  the analyst pipeline through MCP, and any post-filtering for as-of
  correctness happens via ``tools.backtest.sec_historical`` against
  the MCP response — not as a subprocess fetch from this runner.
- The runner aborts the cohort once
  ``consecutive_failure_threshold`` (default 3) tickers complete with
  FAILED status in a row. The rationale: a streak of failures usually
  reflects a network outage or rate-limit, and continuing to spend
  per-ticker work on a systemic problem wastes both clock time and
  fetch budget. Abort raises :class:`BatchRunnerError` after the
  in-flight workers drain. Per-ticker errors that are interleaved with
  successes are still isolated as in Task 3.2 — see
  :meth:`BatchRunner._run_ticker`.
- Cost tracking is currently **bytes-of-fetched-JSON only**. A real
  Claude-token cost cap is added in Chunk 6 when the analyst runs.
  See the TODO inside :meth:`BatchRunner.run` for the bridge.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import pathlib
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from tools.backtest.cohort_manifest import CohortManifest
from tools.backtest.historical_adapters import (
    DartHistorical,
    FredHistorical,
    HistoricalFetchError,
    YFinanceHistorical,
)
from tools.backtest.leakage_detector import (
    LeakageDetector,
    LeakageError,
    LeakageFinding,
)
from tools.backtest.pipeline_context import BacktestContext
from tools.paths import backtest_path

__all__ = [
    "BatchRunner",
    "BatchRunnerError",
    "CohortState",
    "TickerRunRecord",
    "TickerRunStatus",
]


# ---------------------------------------------------------------------------
# Status / record types
# ---------------------------------------------------------------------------


class TickerRunStatus(str, Enum):
    """Lifecycle states for a per-ticker run inside a cohort.

    Stored as the string value (``status.value``) in ``state.json`` so
    the on-disk format stays human-readable.
    """

    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


_TERMINAL_STATUSES: frozenset[TickerRunStatus] = frozenset(
    {TickerRunStatus.DONE, TickerRunStatus.SKIPPED}
)


def _utcnow() -> _dt.datetime:
    return _dt.datetime.now(tz=_dt.UTC)


def _serialize_dt(value: _dt.datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _parse_dt(value: str | None) -> _dt.datetime | None:
    if value is None:
        return None
    return _dt.datetime.fromisoformat(value)


def _serialize_finding(finding: LeakageFinding) -> dict[str, Any]:
    return {
        "path": finding.path,
        "field_name": finding.field_name,
        "value": finding.value,
        "kind": finding.kind,
    }


@dataclass
class TickerRunRecord:
    """Per-ticker status record stored in ``state.json``.

    Parameters
    ----------
    ticker:
        The cohort ticker symbol (e.g. ``"AAPL"``, ``"005930"``).
    status:
        Current lifecycle state — see :class:`TickerRunStatus`.
    started_at:
        UTC timestamp when the ticker fetch began. ``None`` until the
        runner picks the ticker up.
    finished_at:
        UTC timestamp when the ticker reached a terminal state.
    duration_seconds:
        Wall-clock seconds between ``started_at`` and ``finished_at``.
    error:
        Stringified exception message when ``status == FAILED``.
    leakage_findings:
        Serialized list of :class:`LeakageFinding` records (one dict per
        finding) when leakage triggered the failure.
    bytes_written:
        Sum of byte sizes of artifacts the runner wrote for this ticker
        (yfinance-raw + dart-raw + meta).
    """

    ticker: str
    status: TickerRunStatus = TickerRunStatus.PENDING
    started_at: _dt.datetime | None = None
    finished_at: _dt.datetime | None = None
    duration_seconds: float | None = None
    error: str | None = None
    leakage_findings: list[dict[str, Any]] = field(default_factory=list)
    bytes_written: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "status": self.status.value,
            "started_at": _serialize_dt(self.started_at),
            "finished_at": _serialize_dt(self.finished_at),
            "duration_seconds": self.duration_seconds,
            "error": self.error,
            "leakage_findings": list(self.leakage_findings),
            "bytes_written": self.bytes_written,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TickerRunRecord":
        return cls(
            ticker=payload["ticker"],
            status=TickerRunStatus(payload.get("status", "pending")),
            started_at=_parse_dt(payload.get("started_at")),
            finished_at=_parse_dt(payload.get("finished_at")),
            duration_seconds=payload.get("duration_seconds"),
            error=payload.get("error"),
            leakage_findings=list(payload.get("leakage_findings") or []),
            bytes_written=int(payload.get("bytes_written", 0)),
        )


# ---------------------------------------------------------------------------
# Cohort state (state.json)
# ---------------------------------------------------------------------------


class BatchRunnerError(RuntimeError):
    """Raised on fatal cohort-level errors.

    Examples include cost cap violations (when implemented in Chunk 6)
    and ``state.json`` mismatch with the manifest (cohort_id / as_of
    drift, indicating either accidental reuse of a stale state file or
    a manually edited manifest).
    """


@dataclass
class CohortState:
    """Persistent state for a cohort run, serialized to ``state.json``.

    Saved atomically via temp file + ``os.replace``. The runner saves
    state after every per-ticker status transition so a crash mid-run
    leaves a well-formed ``state.json`` that can be loaded on the next
    invocation.
    """

    cohort_id: str
    as_of: _dt.date
    started_at: _dt.datetime
    last_updated_at: _dt.datetime
    runs: dict[str, TickerRunRecord]
    total_bytes_written: int = 0
    notes: list[str] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_json(self) -> str:
        payload: dict[str, Any] = {
            "cohort_id": self.cohort_id,
            "as_of": self.as_of.isoformat(),
            "started_at": _serialize_dt(self.started_at),
            "last_updated_at": _serialize_dt(self.last_updated_at),
            "runs": {
                ticker: record.to_dict()
                for ticker, record in sorted(self.runs.items())
            },
            "total_bytes_written": self.total_bytes_written,
            "notes": list(self.notes),
        }
        return json.dumps(payload, indent=2, sort_keys=True) + "\n"

    @classmethod
    def from_json(cls, text: str) -> "CohortState":
        try:
            payload = json.loads(text)
            runs_payload = payload.get("runs", {}) or {}
            runs = {
                ticker: TickerRunRecord.from_dict(record)
                for ticker, record in runs_payload.items()
            }
            return cls(
                cohort_id=payload["cohort_id"],
                as_of=_dt.date.fromisoformat(payload["as_of"]),
                started_at=_parse_dt(payload["started_at"]) or _utcnow(),
                last_updated_at=_parse_dt(payload["last_updated_at"]) or _utcnow(),
                runs=runs,
                total_bytes_written=int(payload.get("total_bytes_written", 0)),
                notes=list(payload.get("notes") or []),
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            # Refuse to silently lose progress on malformed state — the
            # operator should see a clean error, not a Python traceback.
            raise BatchRunnerError(
                f"state.json is malformed: {exc.__class__.__name__}: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: pathlib.Path) -> None:
        """Atomically write ``state.json``.

        Uses a sibling ``.tmp`` file + :func:`os.replace` so a crash
        mid-write never leaves a partial ``state.json``.
        """
        path = pathlib.Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(self.to_json(), encoding="utf-8")
        os.replace(tmp_path, path)

    @classmethod
    def load_or_init(
        cls, path: pathlib.Path, manifest: CohortManifest
    ) -> "CohortState":
        """Load ``state.json`` or initialize a fresh state.

        If ``path`` exists and matches ``(cohort_id, as_of)`` from
        ``manifest``, the saved state is returned (resumability).
        Mismatch raises :class:`BatchRunnerError` so a stray state file
        cannot silently corrupt a different cohort.
        """
        path = pathlib.Path(path)
        if path.exists():
            state = cls.from_json(path.read_text(encoding="utf-8"))
            if state.cohort_id != manifest.cohort_id:
                raise BatchRunnerError(
                    f"state.json cohort_id={state.cohort_id!r} does not "
                    f"match manifest.cohort_id={manifest.cohort_id!r} "
                    f"(state path: {path})"
                )
            if state.as_of != manifest.as_of:
                raise BatchRunnerError(
                    f"state.json as_of={state.as_of.isoformat()} does not "
                    f"match manifest.as_of={manifest.as_of.isoformat()} "
                    f"(state path: {path})"
                )
            # Backfill runs for any ticker added to the manifest after
            # the state was first written. New tickers start as PENDING.
            for entry in manifest.tickers:
                if entry.ticker not in state.runs:
                    state.runs[entry.ticker] = TickerRunRecord(ticker=entry.ticker)
            return state

        now = _utcnow()
        return cls(
            cohort_id=manifest.cohort_id,
            as_of=manifest.as_of,
            started_at=now,
            last_updated_at=now,
            runs={
                entry.ticker: TickerRunRecord(ticker=entry.ticker)
                for entry in manifest.tickers
            },
        )


# ---------------------------------------------------------------------------
# BatchRunner
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _TickerJobResult:
    """Internal result returned by :meth:`BatchRunner._run_ticker`."""

    ticker: str
    status: TickerRunStatus
    started_at: _dt.datetime
    finished_at: _dt.datetime
    duration_seconds: float
    bytes_written: int
    error: str | None
    leakage_findings: list[dict[str, Any]]


class BatchRunner:
    """Process a cohort manifest end-to-end (data-collection phase).

    Parameters
    ----------
    manifest:
        Validated :class:`CohortManifest` describing the cohort.
    max_workers:
        Maximum number of tickers fetched in parallel. Bounded by a
        :class:`concurrent.futures.ThreadPoolExecutor`. Defaults to 5.
    yfinance_adapter / fred_adapter / dart_adapter:
        Optional injected adapters. Default is a fresh production
        instance. Tests inject stubs that write fixture JSON.
    leakage_strict:
        Pass-through to :class:`LeakageDetector`. ``True`` (default) so
        the first finding flips the run to ``FAILED``.
    consecutive_failure_threshold:
        Number of consecutive FAILED tickers that triggers a cohort
        abort. The counter resets on any non-FAILED result (DONE or
        SKIPPED), so intermittent failures interleaved with successes
        never trip the abort. Must be ``>= 1``; non-positive values
        raise :class:`BatchRunnerError` from ``__init__``. Defaults to
        ``3``.
    """

    def __init__(
        self,
        *,
        manifest: CohortManifest,
        max_workers: int = 5,
        yfinance_adapter: YFinanceHistorical | None = None,
        fred_adapter: FredHistorical | None = None,
        dart_adapter: DartHistorical | None = None,
        leakage_strict: bool = True,
        consecutive_failure_threshold: int = 3,
    ) -> None:
        if max_workers < 1:
            raise ValueError(
                f"max_workers must be >= 1; got {max_workers}"
            )
        if consecutive_failure_threshold < 1:
            raise BatchRunnerError(
                f"consecutive_failure_threshold must be >= 1; "
                f"got {consecutive_failure_threshold}"
            )
        self.manifest: CohortManifest = manifest
        self.max_workers: int = max_workers
        self.yfinance_adapter: YFinanceHistorical = (
            yfinance_adapter if yfinance_adapter is not None else YFinanceHistorical()
        )
        self.fred_adapter: FredHistorical = (
            fred_adapter if fred_adapter is not None else FredHistorical()
        )
        self.dart_adapter: DartHistorical = (
            dart_adapter if dart_adapter is not None else DartHistorical()
        )
        self.leakage_strict: bool = leakage_strict
        self.consecutive_failure_threshold: int = consecutive_failure_threshold

        # Guard concurrent state.json writes from worker threads.
        self._state_lock = threading.Lock()
        # Set when consecutive failures hit the abort threshold; workers
        # check this at entry to short-circuit any not-yet-started fetch.
        self._abort_event = threading.Event()

    # ------------------------------------------------------------------
    # Public entrypoint
    # ------------------------------------------------------------------

    def run(self) -> CohortState:
        """Execute the cohort end-to-end and return the final state.

        Resume policy:

        - DONE / SKIPPED tickers are skipped on resume.
        - PENDING / RUNNING / FAILED tickers are re-run. RUNNING handles
          the "crashed mid-run" case; FAILED retries any prior failure
          (e.g. transient network error). Operators who want to keep
          a FAILED ticker terminal must remove it from the manifest
          or edit ``state.json`` (no `--retry-failed` flag yet — that's
          a Chunk 6 follow-up).

        Consecutive-failure abort (Task 3.3):

        - As ticker results arrive in ``as_completed`` order, the runner
          maintains a consecutive-failure counter. A FAILED result
          increments it; any other terminal status (DONE / SKIPPED)
          resets it to ``0``.
        - Once the counter reaches
          ``self.consecutive_failure_threshold``, ``self._abort_event``
          is set. Any in-flight worker that has not yet started its
          adapter call short-circuits and returns SKIPPED. Already-
          running workers complete normally so ``state.json`` stays
          consistent. Once the executor block exits, the runner raises
          :class:`BatchRunnerError` with the threshold and the list of
          tickers that failed in the trip-streak.
        - On abort the cohort note ``"aborted after N consecutive
          failures"`` is appended to ``state.notes`` so observers can
          distinguish a real abort from a clean termination.

        TODO(chunk-6): The current cost guard is ``total_bytes_written``
        only — meaningful as a fetch-volume sanity check, not as a
        Claude-token cost cap. The token-based cap lands when the
        analyst is wired in (Chunk 6).
        """
        cohort_root = backtest_path("cohorts", self.manifest.cohort_id)
        cohort_root.mkdir(parents=True, exist_ok=True)
        state_path = cohort_root / "state.json"

        state = CohortState.load_or_init(state_path, self.manifest)
        # Persist the initial (or backfilled) state so partial-run
        # observers see it even before any ticker completes.
        state.last_updated_at = _utcnow()
        state.save(state_path)

        # Step 1 — FRED is per-cohort, fetched once and shared by every
        # ticker. Idempotent: skip when the file is already present.
        self._fetch_fred_once(cohort_root, state, state_path)

        # Step 2 — Per-ticker data collection. Tickers already in a
        # terminal state (DONE / SKIPPED) are skipped (resumability).
        pending_entries = [
            entry for entry in self.manifest.tickers
            if state.runs[entry.ticker].status not in _TERMINAL_STATUSES
        ]

        if not pending_entries:
            return state

        # Reset abort state for a fresh ``run()`` invocation. Resuming a
        # cohort by calling ``run()`` again should not be poisoned by an
        # abort signal raised on a prior call.
        self._abort_event.clear()
        consecutive_failures: int = 0
        failure_streak_tickers: list[str] = []

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_ticker = {}
            for entry in pending_entries:
                ctx = BacktestContext(
                    cohort_id=self.manifest.cohort_id,
                    ticker=entry.ticker,
                    as_of=self.manifest.as_of,
                )
                future = executor.submit(
                    self._run_ticker,
                    entry.ticker,
                    entry.market,
                    ctx,
                    state,
                    state_path,
                )
                future_to_ticker[future] = entry.ticker

            for future in as_completed(future_to_ticker):
                ticker = future_to_ticker[future]
                try:
                    job_result = future.result()
                except Exception as exc:  # pragma: no cover — defensive
                    # _run_ticker is supposed to swallow its own
                    # exceptions and return a FAILED record. If it
                    # raises anyway, capture that here so the cohort
                    # run continues for other tickers.
                    job_result = _TickerJobResult(
                        ticker=ticker,
                        status=TickerRunStatus.FAILED,
                        started_at=_utcnow(),
                        finished_at=_utcnow(),
                        duration_seconds=0.0,
                        bytes_written=0,
                        error=f"unhandled exception: {exc!r}",
                        leakage_findings=[],
                    )

                with self._state_lock:
                    record = state.runs[ticker]
                    # Subtract any previously-counted bytes for this
                    # ticker before adding the new value so retries
                    # (FAILED -> DONE) don't double-count toward the
                    # cohort total.
                    state.total_bytes_written += (
                        job_result.bytes_written - record.bytes_written
                    )
                    record.status = job_result.status
                    record.started_at = job_result.started_at
                    record.finished_at = job_result.finished_at
                    record.duration_seconds = job_result.duration_seconds
                    record.bytes_written = job_result.bytes_written
                    record.error = job_result.error
                    record.leakage_findings = list(job_result.leakage_findings)
                    state.last_updated_at = _utcnow()

                    # Update consecutive-failure counter. SKIPPED can
                    # arise from the abort short-circuit itself, so we
                    # treat it (like DONE) as a counter reset rather
                    # than letting it pile additional FAILED weight onto
                    # the streak. Once the abort event is set, no new
                    # FAILED results should arrive — but if they do
                    # (e.g. a worker that was already mid-fetch), they
                    # are still recorded normally without re-triggering
                    # the abort path below.
                    if (
                        job_result.status is TickerRunStatus.FAILED
                        and not self._abort_event.is_set()
                    ):
                        consecutive_failures += 1
                        failure_streak_tickers.append(ticker)
                    elif job_result.status is not TickerRunStatus.FAILED:
                        consecutive_failures = 0
                        failure_streak_tickers = []

                    just_hit_threshold = (
                        consecutive_failures
                        == self.consecutive_failure_threshold
                        and not self._abort_event.is_set()
                    )
                    if just_hit_threshold:
                        self._abort_event.set()
                        state.notes.append(
                            f"aborted after {self.consecutive_failure_threshold} "
                            f"consecutive failures: "
                            f"{', '.join(failure_streak_tickers)}"
                        )

                    state.save(state_path)

        if self._abort_event.is_set():
            raise BatchRunnerError(
                f"cohort {self.manifest.cohort_id!r} aborted after "
                f"{self.consecutive_failure_threshold} consecutive ticker "
                f"failures: {', '.join(failure_streak_tickers)}"
            )

        return state

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fetch_fred_once(
        self,
        cohort_root: pathlib.Path,
        state: CohortState,
        state_path: pathlib.Path,
    ) -> None:
        fred_path = cohort_root / "fred-raw.json"
        if fred_path.exists():
            return

        # Include KR overlay if any ticker in the cohort is Korean —
        # the cohort-level snapshot must cover both markets so per-ticker
        # analysts don't need to re-fetch.
        include_kr = any(entry.market == "KR" for entry in self.manifest.tickers)

        try:
            self.fred_adapter.fetch(
                as_of=self.manifest.as_of,
                output_path=fred_path,
                include_kr=include_kr,
            )
        except HistoricalFetchError as exc:
            # FRED failure is non-fatal — record a cohort-level note
            # and proceed. Per-ticker records are unaffected.
            with self._state_lock:
                state.notes.append(
                    f"fred-fetch-failed: {exc} (returncode={exc.returncode})"
                )
                state.last_updated_at = _utcnow()
                state.save(state_path)
            return

        size = fred_path.stat().st_size if fred_path.exists() else 0
        with self._state_lock:
            state.total_bytes_written += size
            state.notes.append(f"fred-fetched: {size} bytes")
            state.last_updated_at = _utcnow()
            state.save(state_path)

    def _run_ticker(
        self,
        ticker: str,
        market: str,
        ctx: BacktestContext,
        state: CohortState,
        state_path: pathlib.Path,
    ) -> _TickerJobResult:
        # Short-circuit if the cohort has already been aborted. This
        # check runs before we mark RUNNING / touch the meta artifact /
        # invoke the adapter, so an aborted cohort wastes only the
        # thread-pool dispatch overhead per remaining ticker — never a
        # network call.
        if self._abort_event.is_set():
            now = _utcnow()
            return _TickerJobResult(
                ticker=ticker,
                status=TickerRunStatus.SKIPPED,
                started_at=now,
                finished_at=now,
                duration_seconds=0.0,
                bytes_written=0,
                error="skipped: cohort aborted after consecutive failures",
                leakage_findings=[],
            )

        # Mark RUNNING and persist as the first thing the worker does.
        # Doing this here (instead of in the dispatch loop) means a
        # ticker queued behind the concurrency cap stays PENDING in
        # state.json, which is more accurate for observers and resume.
        with self._state_lock:
            state.runs[ticker].status = TickerRunStatus.RUNNING
            state.last_updated_at = _utcnow()
            state.save(state_path)

        started_at = _utcnow()
        start_clock = time.monotonic()
        bytes_written = 0
        error: str | None = None
        leakage_findings: list[dict[str, Any]] = []
        status = TickerRunStatus.DONE

        try:
            ctx.write_meta()
            artifact_root = ctx.artifact_root()
            try:
                bytes_written += ctx.meta_path().stat().st_size
            except OSError:  # pragma: no cover — defensive
                pass

            # ---- yfinance ------------------------------------------------
            yf_path = artifact_root / "yfinance-raw.json"
            yf_payload = self.yfinance_adapter.fetch(
                ticker=ticker,
                market=market,
                as_of=ctx.as_of,
                output_path=yf_path,
            )
            if yf_path.exists():
                bytes_written += yf_path.stat().st_size
            self._check_leakage(yf_payload, ctx.as_of, source_label="yfinance-raw.json")

            # ---- DART (KR only) -----------------------------------------
            if market == "KR":
                dart_path = artifact_root / "dart-raw.json"
                dart_payload = self.dart_adapter.fetch(
                    ticker=ticker,
                    as_of=ctx.as_of,
                    output_path=dart_path,
                )
                if dart_path.exists():
                    bytes_written += dart_path.stat().st_size
                self._check_leakage(
                    dart_payload, ctx.as_of, source_label="dart-raw.json"
                )

        except LeakageError as exc:
            status = TickerRunStatus.FAILED
            error = str(exc)
            leakage_findings = [_serialize_finding(f) for f in exc.findings]
        except HistoricalFetchError as exc:
            status = TickerRunStatus.FAILED
            error = (
                f"{type(exc).__name__}: {exc} "
                f"(returncode={exc.returncode})"
            )
        except Exception as exc:  # noqa: BLE001 — runner must isolate ticker errors
            status = TickerRunStatus.FAILED
            error = f"{type(exc).__name__}: {exc}"

        finished_at = _utcnow()
        duration = time.monotonic() - start_clock

        return _TickerJobResult(
            ticker=ticker,
            status=status,
            started_at=started_at,
            finished_at=finished_at,
            duration_seconds=duration,
            bytes_written=bytes_written,
            error=error,
            leakage_findings=leakage_findings,
        )

    def _check_leakage(
        self,
        payload: object,
        as_of: _dt.date,
        *,
        source_label: str,
    ) -> None:
        # Each call constructs a fresh detector — they are stateless and
        # cheap, but using a fresh instance per artifact keeps the
        # findings list scoped correctly.
        detector = LeakageDetector(strict=self.leakage_strict)
        detector.check(payload, as_of, source_label=source_label)
