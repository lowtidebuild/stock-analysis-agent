"""Tests for BatchRunner consecutive-failure abort (Task 3.3).

Covers the abort behavior added on top of Task 3.2's per-ticker error
isolation:

- After ``consecutive_failure_threshold`` (default 3) tickers complete
  with FAILED status in a row, the runner must abort the cohort by
  setting an internal abort event so subsequent worker invocations
  short-circuit, then raising :class:`BatchRunnerError` once the
  executor block exits.
- The counter resets on any non-FAILED result (DONE / SKIPPED), so
  intermittent failures interleaved with successes never trip the
  abort.
- The constructor rejects non-positive thresholds.

Run via:
``python -m pytest tests/backtest/test_batch_runner_abort.py -v``
"""

from __future__ import annotations

import datetime as _dt
import json
import pathlib
import sys
import threading
import time
from typing import Any

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.backtest.batch_runner import (  # noqa: E402
    BatchRunner,
    BatchRunnerError,
    TickerRunStatus,
)
from tools.backtest.cohort_manifest import (  # noqa: E402
    CohortManifest,
    TickerEntry,
)
from tools.backtest.historical_adapters import (  # noqa: E402
    HistoricalFetchError,
)


# ---------------------------------------------------------------------------
# Stub adapters
# ---------------------------------------------------------------------------


class _FailingYFinanceAdapter:
    """Stub yfinance adapter that always raises HistoricalFetchError."""

    def __init__(self) -> None:
        self.calls: list[str] = []
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
        with self._lock:
            self.calls.append(ticker)
        raise HistoricalFetchError(
            f"forced failure for {ticker}",
            returncode=1,
            stderr="forced",
            ticker=ticker,
            as_of=as_of,
        )


class _PatternedYFinanceAdapter:
    """Stub adapter where each ticker can independently succeed or fail.

    The behavior per ticker is driven by ``fail_for`` — a set of tickers
    that should raise ``HistoricalFetchError``. Any ticker outside the
    set writes a minimal payload and returns success.
    """

    def __init__(self, *, fail_for: set[str]) -> None:
        self.fail_for = set(fail_for)
        self.calls: list[str] = []
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
        with self._lock:
            self.calls.append(ticker)
        if ticker in self.fail_for:
            raise HistoricalFetchError(
                f"forced failure for {ticker}",
                returncode=1,
                stderr="forced",
                ticker=ticker,
                as_of=as_of,
            )
        output_path = pathlib.Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"ticker": ticker, "current_price": {"price": 1.0}}
        output_path.write_text(json.dumps(payload), encoding="utf-8")
        return payload


class _StubFredAdapter:
    def __init__(self) -> None:
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
                {"as_of": as_of, "output_path": pathlib.Path(output_path)}
            )
        output_path = pathlib.Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"series": {"DGS10": 4.0}}
        output_path.write_text(json.dumps(payload), encoding="utf-8")
        return payload


class _StubDartAdapter:
    def __init__(self) -> None:
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
                {"ticker": ticker, "as_of": as_of, "output_path": pathlib.Path(output_path)}
            )
        output_path = pathlib.Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"ticker": ticker, "corp_code": "00126380"}
        output_path.write_text(json.dumps(payload), encoding="utf-8")
        return payload


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolated_data_dir(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> pathlib.Path:
    data_dir = tmp_path / "data"
    monkeypatch.setenv("STOCK_ANALYSIS_DATA_DIR", str(data_dir))
    return data_dir


def _make_manifest(
    *,
    cohort_id: str = "abort-test",
    tickers: tuple[TickerEntry, ...],
) -> CohortManifest:
    return CohortManifest(
        cohort_id=cohort_id,
        as_of=_dt.date(2025, 3, 31),
        tickers=tickers,
        benchmark="SPY",
        mode="C",
        run_count=1,
        cost_cap_usd=5.0,
        notes="",
    )


# ---------------------------------------------------------------------------
# Threshold validation
# ---------------------------------------------------------------------------


def test_threshold_must_be_positive() -> None:
    """consecutive_failure_threshold <= 0 must raise BatchRunnerError."""
    manifest = _make_manifest(
        tickers=(TickerEntry(ticker="AAPL", market="US"),),
    )
    with pytest.raises(BatchRunnerError, match="consecutive_failure_threshold"):
        BatchRunner(
            manifest=manifest,
            yfinance_adapter=_FailingYFinanceAdapter(),
            fred_adapter=_StubFredAdapter(),
            dart_adapter=_StubDartAdapter(),
            consecutive_failure_threshold=0,
        )

    with pytest.raises(BatchRunnerError, match="consecutive_failure_threshold"):
        BatchRunner(
            manifest=manifest,
            yfinance_adapter=_FailingYFinanceAdapter(),
            fred_adapter=_StubFredAdapter(),
            dart_adapter=_StubDartAdapter(),
            consecutive_failure_threshold=-1,
        )


def test_threshold_must_be_int_not_float_or_nan() -> None:
    """The trip site uses == against an int counter, so a float
    threshold (NaN, Inf, 2.5) would silently disable the safety net.
    Must reject non-int types at __init__."""
    import math

    manifest = _make_manifest(
        tickers=(TickerEntry(ticker="AAPL", market="US"),),
    )
    for bad_threshold in (2.5, math.nan, math.inf, "3", True, None):
        with pytest.raises(BatchRunnerError, match="must be an int"):
            BatchRunner(
                manifest=manifest,
                yfinance_adapter=_FailingYFinanceAdapter(),
                fred_adapter=_StubFredAdapter(),
                dart_adapter=_StubDartAdapter(),
                consecutive_failure_threshold=bad_threshold,  # type: ignore[arg-type]
            )


# ---------------------------------------------------------------------------
# Abort behavior
# ---------------------------------------------------------------------------


def test_abort_after_three_consecutive_failures(
    _isolated_data_dir: pathlib.Path,
) -> None:
    """5 tickers, all fail. Runner aborts after the 3rd consecutive
    failure, raises BatchRunnerError, and records the abort note."""
    manifest = _make_manifest(
        cohort_id="abort-3",
        tickers=(
            TickerEntry(ticker="AAA", market="US"),
            TickerEntry(ticker="BBB", market="US"),
            TickerEntry(ticker="CCC", market="US"),
            TickerEntry(ticker="DDD", market="US"),
            TickerEntry(ticker="EEE", market="US"),
        ),
    )
    yf = _FailingYFinanceAdapter()
    runner = BatchRunner(
        manifest=manifest,
        max_workers=1,  # serialize so consecutive ordering is deterministic
        yfinance_adapter=yf,
        fred_adapter=_StubFredAdapter(),
        dart_adapter=_StubDartAdapter(),
        consecutive_failure_threshold=3,
    )

    with pytest.raises(BatchRunnerError) as exc_info:
        runner.run()

    # Reload the on-disk state to confirm persistence.
    cohort_root = _isolated_data_dir / "backtest" / "cohorts" / "abort-3"
    state_path = cohort_root / "state.json"
    assert state_path.exists()
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    notes = payload["notes"]
    assert any("aborted" in note and "3" in note for note in notes), (
        f"expected abort note in state.notes, got {notes!r}"
    )

    # At least 3 tickers must be FAILED. Remaining tickers may be
    # SKIPPED (worker short-circuited) or PENDING (never picked up).
    failed_tickers = [
        t for t, rec in payload["runs"].items() if rec["status"] == "failed"
    ]
    assert len(failed_tickers) >= 3, (
        f"expected >=3 FAILED tickers, got {failed_tickers!r}"
    )

    # The error message should mention the threshold.
    assert "3" in str(exc_info.value)


def test_abort_threshold_configurable(
    _isolated_data_dir: pathlib.Path,
) -> None:
    """Threshold=2 trips after just 2 consecutive failures."""
    manifest = _make_manifest(
        cohort_id="abort-2",
        tickers=(
            TickerEntry(ticker="AAA", market="US"),
            TickerEntry(ticker="BBB", market="US"),
            TickerEntry(ticker="CCC", market="US"),
            TickerEntry(ticker="DDD", market="US"),
        ),
    )
    yf = _FailingYFinanceAdapter()
    runner = BatchRunner(
        manifest=manifest,
        max_workers=1,
        yfinance_adapter=yf,
        fred_adapter=_StubFredAdapter(),
        dart_adapter=_StubDartAdapter(),
        consecutive_failure_threshold=2,
    )

    with pytest.raises(BatchRunnerError):
        runner.run()

    cohort_root = _isolated_data_dir / "backtest" / "cohorts" / "abort-2"
    payload = json.loads((cohort_root / "state.json").read_text(encoding="utf-8"))
    notes = payload["notes"]
    assert any("aborted" in note and "2" in note for note in notes), (
        f"expected abort note for threshold=2, got {notes!r}"
    )


def test_no_abort_when_failures_not_consecutive(
    _isolated_data_dir: pathlib.Path,
) -> None:
    """Pattern: FAIL DONE FAIL DONE FAIL — DONE in between resets the
    counter, so total of 3 failures across 5 tickers should NOT abort."""
    manifest = _make_manifest(
        cohort_id="non-consecutive",
        tickers=(
            TickerEntry(ticker="A1", market="US"),
            TickerEntry(ticker="B2", market="US"),
            TickerEntry(ticker="C3", market="US"),
            TickerEntry(ticker="D4", market="US"),
            TickerEntry(ticker="E5", market="US"),
        ),
    )
    # A1, C3, E5 fail; B2, D4 succeed.
    yf = _PatternedYFinanceAdapter(fail_for={"A1", "C3", "E5"})
    runner = BatchRunner(
        manifest=manifest,
        max_workers=1,  # serial so order is deterministic
        yfinance_adapter=yf,
        fred_adapter=_StubFredAdapter(),
        dart_adapter=_StubDartAdapter(),
        consecutive_failure_threshold=3,
    )
    # Should NOT raise.
    state = runner.run()

    statuses = {t: rec.status for t, rec in state.runs.items()}
    assert statuses["A1"] is TickerRunStatus.FAILED
    assert statuses["B2"] is TickerRunStatus.DONE
    assert statuses["C3"] is TickerRunStatus.FAILED
    assert statuses["D4"] is TickerRunStatus.DONE
    assert statuses["E5"] is TickerRunStatus.FAILED
    # No abort note.
    assert not any("aborted" in note for note in state.notes), (
        f"expected no abort note, got {state.notes!r}"
    )


def test_consecutive_failures_reset_after_done(
    _isolated_data_dir: pathlib.Path,
) -> None:
    """Pattern: 2x FAIL, 1x DONE, 2x FAIL.

    Total 4 failures, but never 3 consecutive — must NOT abort."""
    manifest = _make_manifest(
        cohort_id="reset",
        tickers=(
            TickerEntry(ticker="A1", market="US"),
            TickerEntry(ticker="B2", market="US"),
            TickerEntry(ticker="C3", market="US"),
            TickerEntry(ticker="D4", market="US"),
            TickerEntry(ticker="E5", market="US"),
        ),
    )
    # A1, B2 fail; C3 ok; D4, E5 fail.
    yf = _PatternedYFinanceAdapter(fail_for={"A1", "B2", "D4", "E5"})
    runner = BatchRunner(
        manifest=manifest,
        max_workers=1,
        yfinance_adapter=yf,
        fred_adapter=_StubFredAdapter(),
        dart_adapter=_StubDartAdapter(),
        consecutive_failure_threshold=3,
    )
    state = runner.run()  # must NOT raise

    failed = [t for t, rec in state.runs.items() if rec.status is TickerRunStatus.FAILED]
    done = [t for t, rec in state.runs.items() if rec.status is TickerRunStatus.DONE]
    assert sorted(failed) == ["A1", "B2", "D4", "E5"]
    assert sorted(done) == ["C3"]
    assert not any("aborted" in note for note in state.notes)


def test_abort_event_short_circuits_remaining_tickers(
    _isolated_data_dir: pathlib.Path,
) -> None:
    """Once the abort event is set, subsequent _run_ticker invocations
    must SKIP without invoking the adapter.

    There is an unavoidable race window: a worker may have already
    started a slow fetch when the main thread observes the Nth failure
    and sets the abort event. The spec accepts up to ``max_workers``
    extra in-flight tickers (one per worker that was already mid-call).
    Beyond that, the abort_event short-circuit must hold — at minimum
    one ticker on a 5-ticker / threshold=3 / max_workers=1 cohort must
    be SKIPPED via the short-circuit, not via a real adapter call.
    """
    manifest = _make_manifest(
        cohort_id="short-circuit",
        tickers=(
            TickerEntry(ticker="A1", market="US"),
            TickerEntry(ticker="B2", market="US"),
            TickerEntry(ticker="C3", market="US"),
            TickerEntry(ticker="D4", market="US"),
            TickerEntry(ticker="E5", market="US"),
        ),
    )
    yf = _FailingYFinanceAdapter()
    runner = BatchRunner(
        manifest=manifest,
        max_workers=1,
        yfinance_adapter=yf,
        fred_adapter=_StubFredAdapter(),
        dart_adapter=_StubDartAdapter(),
        consecutive_failure_threshold=3,
    )

    with pytest.raises(BatchRunnerError):
        runner.run()

    # Adapter must NOT be invoked for every ticker — at least one of the
    # tail tickers must short-circuit via the abort event. The race-window
    # bound is threshold + max_workers (one ticker may already be in
    # _run_ticker past the abort_event check by the time the main thread
    # sets it).
    threshold = 3
    max_workers = 1
    assert len(yf.calls) < len(manifest.tickers), (
        f"expected at least one ticker to short-circuit before adapter, "
        f"but adapter saw all of them: {yf.calls!r}"
    )
    assert len(yf.calls) <= threshold + max_workers, (
        f"expected at most threshold+max_workers={threshold + max_workers} "
        f"adapter calls, got {len(yf.calls)}: {yf.calls!r}"
    )

    # And at least one ticker must be marked SKIPPED via the abort
    # short-circuit (not FAILED or DONE).
    cohort_root = _isolated_data_dir / "backtest" / "cohorts" / "short-circuit"
    payload = json.loads((cohort_root / "state.json").read_text(encoding="utf-8"))
    skipped = [t for t, rec in payload["runs"].items() if rec["status"] == "skipped"]
    assert len(skipped) >= 1, (
        f"expected >=1 SKIPPED ticker (abort short-circuit), got {skipped!r} "
        f"from runs={payload['runs']!r}"
    )
    # The skipped tickers should carry the abort error message.
    for ticker in skipped:
        assert "aborted" in (payload["runs"][ticker]["error"] or "").lower(), (
            f"SKIPPED ticker {ticker} missing abort error annotation: "
            f"{payload['runs'][ticker]!r}"
        )
