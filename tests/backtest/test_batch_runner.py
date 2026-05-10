"""Tests for tools.backtest.batch_runner.

Covers Task 3.2 of the backtest harness plan
(``docs/superpowers/plans/2026-05-08-backtest-harness.md``):

- ``BatchRunner`` processes a cohort manifest end-to-end for the
  data-collection phase (yfinance + FRED + DART).
- Resumable on restart: ``state.json`` is rebuilt or loaded; tickers
  marked DONE are skipped on the next pass.
- FRED is fetched once per cohort, not per ticker.
- DART is invoked only for KR tickers.
- Concurrency is bounded by ``max_workers``.
- Leakage findings flip a ticker's status to FAILED.

Run via: ``python -m pytest tests/backtest/test_batch_runner.py -v``
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import pathlib
import subprocess
import sys
import threading
import time
import unittest
from typing import Any

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.backtest.batch_runner import (  # noqa: E402
    BatchRunner,
    BatchRunnerError,
    CohortState,
    TickerRunRecord,
    TickerRunStatus,
)
from tools.backtest.cohort_manifest import (  # noqa: E402
    CohortManifest,
    TickerEntry,
)
from tools.backtest.leakage_detector import (  # noqa: E402
    LeakageError,
    LeakageFinding,
)


# ---------------------------------------------------------------------------
# Stub adapters
# ---------------------------------------------------------------------------


class _StubYFinanceAdapter:
    """Stub yfinance adapter that writes a minimal payload to output_path."""

    def __init__(
        self,
        *,
        payload: dict[str, Any] | None = None,
        delay_seconds: float = 0.0,
        concurrency_tracker: "_ConcurrencyTracker | None" = None,
    ) -> None:
        self.payload = payload or {"ticker": "STUB", "current_price": {"price": 1.0}}
        self.delay_seconds = delay_seconds
        self.concurrency_tracker = concurrency_tracker
        self.calls: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def fetch(
        self,
        *,
        ticker: str,
        market: str,
        as_of: _dt.date,
        output_path: pathlib.Path,
        bundle: str = "standard",
    ) -> dict[str, Any]:
        if self.concurrency_tracker is not None:
            self.concurrency_tracker.enter()
        try:
            with self._lock:
                self.calls.append(
                    {
                        "ticker": ticker,
                        "market": market,
                        "as_of": as_of,
                        "output_path": pathlib.Path(output_path),
                        "bundle": bundle,
                    }
                )
            if self.delay_seconds:
                time.sleep(self.delay_seconds)
            payload = dict(self.payload)
            payload["ticker"] = ticker
            output_path = pathlib.Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(payload), encoding="utf-8")
            return payload
        finally:
            if self.concurrency_tracker is not None:
                self.concurrency_tracker.exit()


class _StubFredAdapter:
    def __init__(self, *, payload: dict[str, Any] | None = None) -> None:
        self.payload = payload or {"series": {"DGS10": 4.0}}
        self.calls: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def fetch(
        self,
        *,
        as_of: _dt.date,
        output_path: pathlib.Path,
        include_kr: bool = False,
    ) -> dict[str, Any]:
        with self._lock:
            self.calls.append(
                {
                    "as_of": as_of,
                    "output_path": pathlib.Path(output_path),
                    "include_kr": include_kr,
                }
            )
        output_path = pathlib.Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(self.payload), encoding="utf-8")
        return self.payload


class _StubDartAdapter:
    def __init__(self, *, payload: dict[str, Any] | None = None) -> None:
        self.payload = payload or {"corp_code": "00126380"}
        self.calls: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def fetch(
        self,
        *,
        ticker: str,
        as_of: _dt.date,
        output_path: pathlib.Path,
    ) -> dict[str, Any]:
        with self._lock:
            self.calls.append(
                {
                    "ticker": ticker,
                    "as_of": as_of,
                    "output_path": pathlib.Path(output_path),
                }
            )
        output_path = pathlib.Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = dict(self.payload)
        payload["ticker"] = ticker
        output_path.write_text(json.dumps(payload), encoding="utf-8")
        return payload


class _ConcurrencyTracker:
    """Records the maximum simultaneous-call count across stub fetches."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active = 0
        self.peak = 0

    def enter(self) -> None:
        with self._lock:
            self._active += 1
            if self._active > self.peak:
                self.peak = self._active

    def exit(self) -> None:
        with self._lock:
            self._active -= 1


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> pathlib.Path:
    """Redirect $STOCK_ANALYSIS_DATA_DIR so backtest_path() points into tmp."""
    data_dir = tmp_path / "data"
    monkeypatch.setenv("STOCK_ANALYSIS_DATA_DIR", str(data_dir))
    return data_dir


def _make_manifest(
    *,
    cohort_id: str = "test",
    as_of: _dt.date | None = None,
    tickers: tuple[TickerEntry, ...] | None = None,
) -> CohortManifest:
    return CohortManifest(
        cohort_id=cohort_id,
        as_of=as_of or _dt.date(2025, 3, 31),
        tickers=tickers or (TickerEntry(ticker="AAPL", market="US"),),
        benchmark="SPY",
        mode="C",
        run_count=1,
        cost_cap_usd=5.0,
        notes="",
    )


# ---------------------------------------------------------------------------
# CohortState
# ---------------------------------------------------------------------------


def test_cohort_state_to_json_roundtrip() -> None:
    started = _dt.datetime(2026, 5, 8, 12, 0, 0, tzinfo=_dt.UTC)
    state = CohortState(
        cohort_id="smoke",
        as_of=_dt.date(2025, 3, 31),
        started_at=started,
        last_updated_at=started,
        runs={
            "AAPL": TickerRunRecord(
                ticker="AAPL",
                status=TickerRunStatus.DONE,
                started_at=started,
                finished_at=started,
                duration_seconds=1.5,
                bytes_written=1234,
            ),
        },
        total_bytes_written=1234,
        notes=["fetched fred"],
    )
    text = state.to_json()
    rebuilt = CohortState.from_json(text)
    assert rebuilt.cohort_id == "smoke"
    assert rebuilt.as_of == _dt.date(2025, 3, 31)
    assert rebuilt.started_at == started
    assert rebuilt.runs["AAPL"].status is TickerRunStatus.DONE
    assert rebuilt.runs["AAPL"].duration_seconds == 1.5
    assert rebuilt.runs["AAPL"].bytes_written == 1234
    assert rebuilt.total_bytes_written == 1234
    assert rebuilt.notes == ["fetched fred"]


def test_cohort_state_save_is_atomic(tmp_path: pathlib.Path) -> None:
    started = _dt.datetime(2026, 5, 8, 12, 0, 0, tzinfo=_dt.UTC)
    state = CohortState(
        cohort_id="t",
        as_of=_dt.date(2025, 3, 31),
        started_at=started,
        last_updated_at=started,
        runs={},
    )
    target = tmp_path / "state.json"
    state.save(target)
    assert target.exists()
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["cohort_id"] == "t"
    # Atomic save uses a temp file + rename — confirm no leftover .tmp file.
    leftovers = [p for p in tmp_path.iterdir() if p.suffix == ".tmp"]
    assert leftovers == []


def test_state_load_or_init_initializes_when_missing(tmp_path: pathlib.Path) -> None:
    manifest = _make_manifest(
        tickers=(
            TickerEntry(ticker="AAPL", market="US"),
            TickerEntry(ticker="MSFT", market="US"),
        )
    )
    target = tmp_path / "state.json"
    state = CohortState.load_or_init(target, manifest)
    assert state.cohort_id == manifest.cohort_id
    assert state.as_of == manifest.as_of
    assert set(state.runs) == {"AAPL", "MSFT"}
    for record in state.runs.values():
        assert record.status is TickerRunStatus.PENDING


def test_state_load_or_init_loads_existing(tmp_path: pathlib.Path) -> None:
    manifest = _make_manifest(
        tickers=(
            TickerEntry(ticker="AAPL", market="US"),
            TickerEntry(ticker="MSFT", market="US"),
        )
    )
    started = _dt.datetime(2026, 5, 8, 12, 0, 0, tzinfo=_dt.UTC)
    seed = CohortState(
        cohort_id=manifest.cohort_id,
        as_of=manifest.as_of,
        started_at=started,
        last_updated_at=started,
        runs={
            "AAPL": TickerRunRecord(
                ticker="AAPL",
                status=TickerRunStatus.DONE,
                bytes_written=42,
            ),
            "MSFT": TickerRunRecord(ticker="MSFT", status=TickerRunStatus.PENDING),
        },
        total_bytes_written=42,
    )
    target = tmp_path / "state.json"
    seed.save(target)
    state = CohortState.load_or_init(target, manifest)
    assert state.runs["AAPL"].status is TickerRunStatus.DONE
    assert state.runs["MSFT"].status is TickerRunStatus.PENDING
    assert state.total_bytes_written == 42


def test_state_load_or_init_rejects_mismatched_cohort_id(tmp_path: pathlib.Path) -> None:
    manifest = _make_manifest(cohort_id="cohortA")
    started = _dt.datetime(2026, 5, 8, 12, 0, 0, tzinfo=_dt.UTC)
    seed = CohortState(
        cohort_id="cohortB",
        as_of=manifest.as_of,
        started_at=started,
        last_updated_at=started,
        runs={},
    )
    target = tmp_path / "state.json"
    seed.save(target)
    with pytest.raises(BatchRunnerError):
        CohortState.load_or_init(target, manifest)


def test_state_load_or_init_rejects_mismatched_as_of(tmp_path: pathlib.Path) -> None:
    manifest = _make_manifest(as_of=_dt.date(2025, 3, 31))
    started = _dt.datetime(2026, 5, 8, 12, 0, 0, tzinfo=_dt.UTC)
    seed = CohortState(
        cohort_id=manifest.cohort_id,
        as_of=_dt.date(2025, 6, 30),  # different
        started_at=started,
        last_updated_at=started,
        runs={},
    )
    target = tmp_path / "state.json"
    seed.save(target)
    with pytest.raises(BatchRunnerError):
        CohortState.load_or_init(target, manifest)


# ---------------------------------------------------------------------------
# BatchRunner — core flow
# ---------------------------------------------------------------------------


def test_runner_processes_smoke_cohort(_isolated_data_dir: pathlib.Path) -> None:
    manifest = _make_manifest(
        cohort_id="smoke",
        tickers=(TickerEntry(ticker="AAPL", market="US"),),
    )
    yf = _StubYFinanceAdapter()
    fred = _StubFredAdapter()
    dart = _StubDartAdapter()
    runner = BatchRunner(
        manifest=manifest,
        max_workers=1,
        yfinance_adapter=yf,
        fred_adapter=fred,
        dart_adapter=dart,
    )
    state = runner.run()

    assert state.runs["AAPL"].status is TickerRunStatus.DONE
    assert state.runs["AAPL"].error is None

    cohort_root = _isolated_data_dir / "backtest" / "cohorts" / "smoke"
    state_path = cohort_root / "state.json"
    assert state_path.exists()
    fred_path = cohort_root / "fred-raw.json"
    assert fred_path.exists()

    yf_path = cohort_root / "runs" / "AAPL" / "yfinance-raw.json"
    assert yf_path.exists()
    meta_path = cohort_root / "runs" / "AAPL" / "_backtest-meta.json"
    assert meta_path.exists()


def test_runner_creates_per_ticker_artifacts(_isolated_data_dir: pathlib.Path) -> None:
    manifest = _make_manifest(
        cohort_id="multi",
        tickers=(
            TickerEntry(ticker="AAPL", market="US"),
            TickerEntry(ticker="MSFT", market="US"),
        ),
    )
    runner = BatchRunner(
        manifest=manifest,
        max_workers=2,
        yfinance_adapter=_StubYFinanceAdapter(),
        fred_adapter=_StubFredAdapter(),
        dart_adapter=_StubDartAdapter(),
    )
    runner.run()

    cohort_root = _isolated_data_dir / "backtest" / "cohorts" / "multi"
    for ticker in ("AAPL", "MSFT"):
        assert (cohort_root / "runs" / ticker / "_backtest-meta.json").exists()
        assert (cohort_root / "runs" / ticker / "yfinance-raw.json").exists()


def test_runner_fetches_fred_once_per_cohort(_isolated_data_dir: pathlib.Path) -> None:
    manifest = _make_manifest(
        cohort_id="multifred",
        tickers=(
            TickerEntry(ticker="AAPL", market="US"),
            TickerEntry(ticker="MSFT", market="US"),
            TickerEntry(ticker="NVDA", market="US"),
        ),
    )
    fred = _StubFredAdapter()
    runner = BatchRunner(
        manifest=manifest,
        max_workers=2,
        yfinance_adapter=_StubYFinanceAdapter(),
        fred_adapter=fred,
        dart_adapter=_StubDartAdapter(),
    )
    runner.run()
    assert len(fred.calls) == 1


def test_runner_skips_fred_when_already_present(_isolated_data_dir: pathlib.Path) -> None:
    manifest = _make_manifest(
        cohort_id="fredskip",
        tickers=(TickerEntry(ticker="AAPL", market="US"),),
    )
    fred = _StubFredAdapter()
    # Pre-populate the cohort fred-raw.json so the runner sees existing data.
    cohort_root = _isolated_data_dir / "backtest" / "cohorts" / "fredskip"
    cohort_root.mkdir(parents=True, exist_ok=True)
    (cohort_root / "fred-raw.json").write_text(
        json.dumps({"series": {"DGS10": 3.5}}), encoding="utf-8"
    )
    runner = BatchRunner(
        manifest=manifest,
        max_workers=1,
        yfinance_adapter=_StubYFinanceAdapter(),
        fred_adapter=fred,
        dart_adapter=_StubDartAdapter(),
    )
    runner.run()
    assert fred.calls == []  # idempotent


def test_runner_calls_dart_only_for_kr_tickers(_isolated_data_dir: pathlib.Path) -> None:
    manifest = _make_manifest(
        cohort_id="mixed",
        tickers=(
            TickerEntry(ticker="AAPL", market="US"),
            TickerEntry(ticker="005930", market="KR"),
            TickerEntry(ticker="MSFT", market="US"),
            TickerEntry(ticker="000660", market="KR"),
        ),
    )
    dart = _StubDartAdapter()
    runner = BatchRunner(
        manifest=manifest,
        max_workers=2,
        yfinance_adapter=_StubYFinanceAdapter(),
        fred_adapter=_StubFredAdapter(),
        dart_adapter=dart,
    )
    runner.run()
    dart_tickers = sorted(call["ticker"] for call in dart.calls)
    assert dart_tickers == ["000660", "005930"]

    cohort_root = _isolated_data_dir / "backtest" / "cohorts" / "mixed"
    assert (cohort_root / "runs" / "005930" / "dart-raw.json").exists()
    assert not (cohort_root / "runs" / "AAPL" / "dart-raw.json").exists()


def test_runner_resumes_skipping_done_tickers(_isolated_data_dir: pathlib.Path) -> None:
    manifest = _make_manifest(
        cohort_id="resume",
        tickers=(
            TickerEntry(ticker="AAPL", market="US"),
            TickerEntry(ticker="MSFT", market="US"),
            TickerEntry(ticker="NVDA", market="US"),
        ),
    )
    cohort_root = _isolated_data_dir / "backtest" / "cohorts" / "resume"
    cohort_root.mkdir(parents=True, exist_ok=True)

    started = _dt.datetime(2026, 5, 8, 12, 0, 0, tzinfo=_dt.UTC)
    seed = CohortState(
        cohort_id=manifest.cohort_id,
        as_of=manifest.as_of,
        started_at=started,
        last_updated_at=started,
        runs={
            "AAPL": TickerRunRecord(ticker="AAPL", status=TickerRunStatus.DONE),
            "MSFT": TickerRunRecord(ticker="MSFT", status=TickerRunStatus.PENDING),
            "NVDA": TickerRunRecord(ticker="NVDA", status=TickerRunStatus.PENDING),
        },
    )
    seed.save(cohort_root / "state.json")

    yf = _StubYFinanceAdapter()
    runner = BatchRunner(
        manifest=manifest,
        max_workers=2,
        yfinance_adapter=yf,
        fred_adapter=_StubFredAdapter(),
        dart_adapter=_StubDartAdapter(),
    )
    state = runner.run()

    yf_tickers = sorted(call["ticker"] for call in yf.calls)
    assert yf_tickers == ["MSFT", "NVDA"]
    assert state.runs["AAPL"].status is TickerRunStatus.DONE
    assert state.runs["MSFT"].status is TickerRunStatus.DONE
    assert state.runs["NVDA"].status is TickerRunStatus.DONE


def test_runner_marks_leakage_finding_as_failed(
    _isolated_data_dir: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = _make_manifest(
        cohort_id="leak",
        tickers=(
            TickerEntry(ticker="AAPL", market="US"),
            TickerEntry(ticker="MSFT", market="US"),
        ),
    )
    # Patch LeakageDetector.check to fail for AAPL only.
    from tools.backtest import batch_runner as br_mod

    real_check = br_mod.LeakageDetector.check

    def fake_check(self, payload, as_of, *, source_label="<root>"):
        ticker = payload.get("ticker") if isinstance(payload, dict) else None
        if ticker == "AAPL":
            finding = LeakageFinding(
                path=f"{source_label}.published_date",
                field_name="published_date",
                value="2030-01-01",
                kind="future_date",
            )
            raise LeakageError([finding])
        return real_check(self, payload, as_of, source_label=source_label)

    monkeypatch.setattr(br_mod.LeakageDetector, "check", fake_check)

    runner = BatchRunner(
        manifest=manifest,
        max_workers=1,  # serialize so output ordering is deterministic
        yfinance_adapter=_StubYFinanceAdapter(),
        fred_adapter=_StubFredAdapter(),
        dart_adapter=_StubDartAdapter(),
    )
    state = runner.run()

    assert state.runs["AAPL"].status is TickerRunStatus.FAILED
    assert state.runs["AAPL"].leakage_findings, "expected serialized leakage findings"
    assert state.runs["AAPL"].leakage_findings[0]["kind"] == "future_date"
    assert state.runs["MSFT"].status is TickerRunStatus.DONE


def test_runner_records_per_ticker_duration(_isolated_data_dir: pathlib.Path) -> None:
    manifest = _make_manifest(
        cohort_id="duration",
        tickers=(TickerEntry(ticker="AAPL", market="US"),),
    )
    yf = _StubYFinanceAdapter(delay_seconds=0.05)
    runner = BatchRunner(
        manifest=manifest,
        max_workers=1,
        yfinance_adapter=yf,
        fred_adapter=_StubFredAdapter(),
        dart_adapter=_StubDartAdapter(),
    )
    state = runner.run()
    record = state.runs["AAPL"]
    assert record.duration_seconds is not None
    assert record.duration_seconds >= 0.0
    assert record.started_at is not None
    assert record.finished_at is not None


def test_runner_records_bytes_written(_isolated_data_dir: pathlib.Path) -> None:
    manifest = _make_manifest(
        cohort_id="bytes",
        tickers=(TickerEntry(ticker="AAPL", market="US"),),
    )
    runner = BatchRunner(
        manifest=manifest,
        max_workers=1,
        yfinance_adapter=_StubYFinanceAdapter(),
        fred_adapter=_StubFredAdapter(),
        dart_adapter=_StubDartAdapter(),
    )
    state = runner.run()
    assert state.runs["AAPL"].bytes_written > 0
    assert state.total_bytes_written >= state.runs["AAPL"].bytes_written


def test_runner_concurrency_cap(_isolated_data_dir: pathlib.Path) -> None:
    manifest = _make_manifest(
        cohort_id="cap",
        tickers=(
            TickerEntry(ticker="AAPL", market="US"),
            TickerEntry(ticker="MSFT", market="US"),
            TickerEntry(ticker="NVDA", market="US"),
            TickerEntry(ticker="META", market="US"),
            TickerEntry(ticker="GOOGL", market="US"),
        ),
    )
    tracker = _ConcurrencyTracker()
    yf = _StubYFinanceAdapter(delay_seconds=0.05, concurrency_tracker=tracker)
    runner = BatchRunner(
        manifest=manifest,
        max_workers=2,
        yfinance_adapter=yf,
        fred_adapter=_StubFredAdapter(),
        dart_adapter=_StubDartAdapter(),
    )
    runner.run()
    assert tracker.peak <= 2, f"observed peak concurrency {tracker.peak}, expected <= 2"
    assert tracker.peak >= 1


def test_runner_state_saved_after_each_ticker(_isolated_data_dir: pathlib.Path) -> None:
    manifest = _make_manifest(
        cohort_id="save",
        tickers=(
            TickerEntry(ticker="AAPL", market="US"),
            TickerEntry(ticker="MSFT", market="US"),
        ),
    )
    runner = BatchRunner(
        manifest=manifest,
        max_workers=1,
        yfinance_adapter=_StubYFinanceAdapter(),
        fred_adapter=_StubFredAdapter(),
        dart_adapter=_StubDartAdapter(),
    )
    runner.run()
    state_path = _isolated_data_dir / "backtest" / "cohorts" / "save" / "state.json"
    assert state_path.exists()
    loaded = CohortState.from_json(state_path.read_text(encoding="utf-8"))
    assert all(rec.status is TickerRunStatus.DONE for rec in loaded.runs.values())


# ---------------------------------------------------------------------------
# CLI integration (minimal — full integration deferred to Chunk 6)
# ---------------------------------------------------------------------------


CLI = ROOT / "tools" / "backtest_runner.py"


def _run_cli(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env=full_env,
    )


def test_runner_cli_dry_run_unchanged() -> None:
    result = _run_cli("--cohort", "smoke", "--as-of", "2025-03-31", "--dry-run")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["cohort"] == "smoke"
    assert payload["as_of"] == "2025-03-31"


def test_runner_cli_rejects_unknown_cohort(tmp_path: pathlib.Path) -> None:
    """Without --dry-run, an unknown cohort id should exit 2 (manifest load failure)."""
    result = _run_cli(
        "--cohort", "this_cohort_does_not_exist",
        env={"STOCK_ANALYSIS_DATA_DIR": str(tmp_path)},
    )
    assert result.returncode == 2, result.stdout + result.stderr


def test_runner_cli_rejects_as_of_mismatch(tmp_path: pathlib.Path) -> None:
    """If --as-of differs from manifest.as_of, the runner must reject it."""
    # smoke.json's as_of is 2025-03-31; pass a different date
    result = _run_cli(
        "--cohort", "smoke",
        "--as-of", "2024-01-15",
        env={"STOCK_ANALYSIS_DATA_DIR": str(tmp_path)},
    )
    assert result.returncode == 2, result.stdout + result.stderr


# ---------------------------------------------------------------------------
# Regression tests for code-quality NIT fixes
# ---------------------------------------------------------------------------


def test_malformed_state_json_raises_batch_runner_error(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A truncated / hand-edited state.json should surface as a clean
    BatchRunnerError, not an uncaught traceback (JSONDecodeError /
    KeyError leaking out of from_json)."""
    monkeypatch.setenv("STOCK_ANALYSIS_DATA_DIR", str(tmp_path))

    manifest = CohortManifest(
        cohort_id="malformed",
        as_of=_dt.date(2025, 3, 31),
        tickers=(TickerEntry(ticker="AAPL", market="US"),),
    )

    cohort_root = tmp_path / "backtest" / "cohorts" / "malformed"
    cohort_root.mkdir(parents=True, exist_ok=True)
    (cohort_root / "state.json").write_text("{not valid json", encoding="utf-8")

    runner = BatchRunner(
        manifest=manifest,
        yfinance_adapter=_StubYFinanceAdapter(),
        fred_adapter=_StubFredAdapter(),
        dart_adapter=_StubDartAdapter(),
    )
    with pytest.raises(BatchRunnerError, match="malformed"):
        runner.run()


def test_total_bytes_does_not_double_count_on_retry(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When a FAILED ticker is retried and succeeds, total_bytes_written
    must reflect the new value alone, not old + new."""
    monkeypatch.setenv("STOCK_ANALYSIS_DATA_DIR", str(tmp_path))

    manifest = CohortManifest(
        cohort_id="retry-bytes",
        as_of=_dt.date(2025, 3, 31),
        tickers=(TickerEntry(ticker="AAPL", market="US"),),
    )

    cohort_root = tmp_path / "backtest" / "cohorts" / "retry-bytes"
    cohort_root.mkdir(parents=True, exist_ok=True)
    state_path = cohort_root / "state.json"

    # Seed state.json with a FAILED record claiming 100 bytes already
    # accumulated into the cohort total.
    seed_state = CohortState(
        cohort_id="retry-bytes",
        as_of=_dt.date(2025, 3, 31),
        started_at=_dt.datetime(2025, 3, 31, 0, 0, 0, tzinfo=_dt.UTC),
        last_updated_at=_dt.datetime(2025, 3, 31, 0, 0, 0, tzinfo=_dt.UTC),
        runs={
            "AAPL": TickerRunRecord(
                ticker="AAPL",
                status=TickerRunStatus.FAILED,
                bytes_written=100,
                error="prior transient error",
            ),
        },
        total_bytes_written=100,
    )
    seed_state.save(state_path)

    runner = BatchRunner(
        manifest=manifest,
        yfinance_adapter=_StubYFinanceAdapter(),
        fred_adapter=_StubFredAdapter(),
        dart_adapter=_StubDartAdapter(),
    )
    state = runner.run()

    assert state.runs["AAPL"].status == TickerRunStatus.DONE
    new_aapl_bytes = state.runs["AAPL"].bytes_written
    assert new_aapl_bytes > 0
    # FRED is fetched once per cohort and counted separately.
    fred_bytes = (cohort_root / "fred-raw.json").stat().st_size
    expected_total = new_aapl_bytes + fred_bytes
    assert state.total_bytes_written == expected_total, (
        f"total_bytes drifted: got {state.total_bytes_written}, "
        f"expected {expected_total} (=new_aapl {new_aapl_bytes} "
        f"+ fred {fred_bytes}); double-counting bug"
    )


def test_running_marked_inside_worker_not_in_dispatch_loop(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With max_workers=1 and 3 tickers, the queued tickers should
    appear PENDING (not RUNNING) until the worker picks them up.

    We verify by asserting that during the slow first ticker, the other
    two are PENDING in state.json — not pre-marked RUNNING by the
    dispatch loop."""
    monkeypatch.setenv("STOCK_ANALYSIS_DATA_DIR", str(tmp_path))

    manifest = CohortManifest(
        cohort_id="queue-vs-running",
        as_of=_dt.date(2025, 3, 31),
        tickers=(
            TickerEntry(ticker="AAPL", market="US"),
            TickerEntry(ticker="MSFT", market="US"),
            TickerEntry(ticker="GOOGL", market="US"),
        ),
    )

    cohort_root = tmp_path / "backtest" / "cohorts" / "queue-vs-running"
    state_path = cohort_root / "state.json"

    # Stub adapter pauses on AAPL so we can inspect mid-run state.
    inspect_event = threading.Event()
    release_event = threading.Event()

    class _PausingAdapter(_StubYFinanceAdapter):
        def fetch(self, *, ticker, market, as_of, output_path, bundle="standard"):
            if ticker == "AAPL":
                inspect_event.set()
                release_event.wait(timeout=5)
            return super().fetch(
                ticker=ticker, market=market, as_of=as_of,
                output_path=output_path, bundle=bundle,
            )

    runner = BatchRunner(
        manifest=manifest,
        max_workers=1,
        yfinance_adapter=_PausingAdapter(),
        fred_adapter=_StubFredAdapter(),
        dart_adapter=_StubDartAdapter(),
    )

    runner_thread = threading.Thread(target=runner.run, daemon=True)
    runner_thread.start()

    assert inspect_event.wait(timeout=5), "first worker never started"
    # Now AAPL is RUNNING inside the worker. Inspect state.json: AAPL
    # should be RUNNING; MSFT/GOOGL should still be PENDING (queued).
    mid_run_state = CohortState.from_json(state_path.read_text(encoding="utf-8"))
    assert mid_run_state.runs["AAPL"].status == TickerRunStatus.RUNNING
    assert mid_run_state.runs["MSFT"].status == TickerRunStatus.PENDING, (
        "MSFT should still be PENDING while AAPL is mid-fetch; "
        "got status={mid_run_state.runs['MSFT'].status}"
    )
    assert mid_run_state.runs["GOOGL"].status == TickerRunStatus.PENDING

    release_event.set()
    runner_thread.join(timeout=10)
    assert not runner_thread.is_alive(), "runner thread did not finish"


if __name__ == "__main__":
    unittest.main()
