"""Tests for the benchmark price cache (Task 4.1).

Covers Task 4.1 of the backtest harness plan
(``docs/superpowers/plans/2026-05-08-backtest-harness.md``).

Two layers:

- :mod:`tools.backtest.benchmark_cache` — pure helpers that load a JSONL
  cache file and resolve a (benchmark, target_date) pair to a close
  price, with weekend/holiday forward-search.
- ``evals/backtest/scripts/cache-benchmarks.py`` — CLI fixture builder
  that writes the cache. Real yfinance calls are gated behind
  ``INTEGRATION_TESTS=1``.

Run via: ``python -m pytest tests/backtest/test_benchmark_cache.py -v``
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.backtest.benchmark_cache import (  # noqa: E402
    BenchmarkCacheError,
    get_benchmark_close,
    load_benchmark_cache,
    select_benchmark,
)

FIXTURE_PATH = ROOT / "evals" / "backtest" / "data" / "benchmark-prices-fixture.jsonl"
SCRIPT_PATH = ROOT / "evals" / "backtest" / "scripts" / "cache-benchmarks.py"

EXPECTED_BENCHMARKS = {"SPY", "QQQ", "KOSPI"}


# ---------------------------------------------------------------------------
# load_benchmark_cache
# ---------------------------------------------------------------------------


def test_load_benchmark_cache_reads_fixture() -> None:
    cache = load_benchmark_cache(FIXTURE_PATH)
    assert set(cache.keys()) == EXPECTED_BENCHMARKS
    for name in EXPECTED_BENCHMARKS:
        assert cache[name], f"{name} should have at least one date entry"


def test_load_benchmark_cache_rejects_missing_file(tmp_path: pathlib.Path) -> None:
    missing = tmp_path / "does-not-exist.jsonl"
    with pytest.raises(BenchmarkCacheError) as excinfo:
        load_benchmark_cache(missing)
    assert "not exist" in str(excinfo.value).lower() or "missing" in str(excinfo.value).lower()


def test_load_benchmark_cache_rejects_malformed_jsonl(tmp_path: pathlib.Path) -> None:
    bad = tmp_path / "bad.jsonl"
    bad.write_text(
        '{"date": "2025-03-03", "benchmark": "SPY", "close": 580.0}\n'
        "this is not json\n",
        encoding="utf-8",
    )
    with pytest.raises(BenchmarkCacheError) as excinfo:
        load_benchmark_cache(bad)
    assert "json" in str(excinfo.value).lower() or "parse" in str(excinfo.value).lower()


def test_load_benchmark_cache_rejects_missing_benchmark_coverage(
    tmp_path: pathlib.Path,
) -> None:
    incomplete = tmp_path / "incomplete.jsonl"
    incomplete.write_text(
        '{"date": "2025-03-03", "benchmark": "SPY", "close": 580.0}\n'
        '{"date": "2025-03-03", "benchmark": "QQQ", "close": 490.0}\n',
        encoding="utf-8",
    )
    with pytest.raises(BenchmarkCacheError) as excinfo:
        load_benchmark_cache(incomplete)
    assert "kospi" in str(excinfo.value).lower()


def test_load_benchmark_cache_groups_by_benchmark() -> None:
    cache = load_benchmark_cache(FIXTURE_PATH)
    # Same date should appear under each benchmark.
    sample_date = _dt.date(2025, 3, 3)
    for name in EXPECTED_BENCHMARKS:
        assert sample_date in cache[name], (
            f"{name} cache missing sample date {sample_date}"
        )
        assert isinstance(cache[name][sample_date], float)


def test_load_benchmark_cache_rejects_bad_record_schema(tmp_path: pathlib.Path) -> None:
    bad = tmp_path / "bad-schema.jsonl"
    bad.write_text(
        '{"date": "2025-03-03", "benchmark": "SPY"}\n',  # missing 'close'
        encoding="utf-8",
    )
    with pytest.raises(BenchmarkCacheError) as excinfo:
        load_benchmark_cache(bad)
    assert "close" in str(excinfo.value).lower() or "field" in str(excinfo.value).lower()


# ---------------------------------------------------------------------------
# get_benchmark_close
# ---------------------------------------------------------------------------


def test_get_benchmark_close_exact_date_hit() -> None:
    cache = load_benchmark_cache(FIXTURE_PATH)
    target = _dt.date(2025, 3, 3)  # forward-filled date present in fixture
    price = get_benchmark_close(cache, "SPY", target)
    assert price is not None
    assert isinstance(price, float)
    assert price > 0


def test_get_benchmark_close_forward_fills_weekend() -> None:
    # Build a tiny in-memory cache where Saturday is missing so the
    # forward search must walk to Monday.
    cache = {
        "SPY": {
            _dt.date(2025, 3, 7): 575.0,   # Friday
            _dt.date(2025, 3, 10): 580.0,  # Monday
        },
    }
    saturday = _dt.date(2025, 3, 8)
    price = get_benchmark_close(cache, "SPY", saturday)
    assert price == 580.0


def test_get_benchmark_close_returns_none_when_beyond_window() -> None:
    cache = {"SPY": {_dt.date(2025, 3, 7): 575.0}}
    far_future = _dt.date(2025, 3, 20)
    price = get_benchmark_close(cache, "SPY", far_future, max_lookahead_days=5)
    assert price is None


def test_get_benchmark_close_unknown_benchmark_raises() -> None:
    cache = {"SPY": {_dt.date(2025, 3, 7): 575.0}}
    with pytest.raises(BenchmarkCacheError):
        get_benchmark_close(cache, "DAX", _dt.date(2025, 3, 7))


def test_get_benchmark_close_respects_max_lookahead_days() -> None:
    cache = {
        "SPY": {
            _dt.date(2025, 3, 14): 575.0,
        },
    }
    target = _dt.date(2025, 3, 10)
    # 4 days lookahead reaches Friday the 14th.
    assert get_benchmark_close(cache, "SPY", target, max_lookahead_days=4) == 575.0
    # 3 days lookahead does not reach the 14th.
    assert get_benchmark_close(cache, "SPY", target, max_lookahead_days=3) is None


# ---------------------------------------------------------------------------
# select_benchmark
# ---------------------------------------------------------------------------


def test_select_benchmark_kr_returns_kospi() -> None:
    assert select_benchmark("KR") == "KOSPI"
    assert select_benchmark("KR", ticker="005930") == "KOSPI"


def test_select_benchmark_us_default_spy() -> None:
    assert select_benchmark("US") == "SPY"
    assert select_benchmark("US", ticker="AAPL") == "SPY"


def test_select_benchmark_us_prefer_qqq() -> None:
    assert select_benchmark("US", prefer_qqq=True) == "QQQ"
    assert select_benchmark("US", ticker="NVDA", prefer_qqq=True) == "QQQ"


def test_select_benchmark_kr_ignores_prefer_qqq() -> None:
    # KR market should always return KOSPI regardless of prefer_qqq flag.
    assert select_benchmark("KR", prefer_qqq=True) == "KOSPI"


# ---------------------------------------------------------------------------
# CLI script tests
# ---------------------------------------------------------------------------


def test_cache_script_dry_run_help() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--help"],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert completed.returncode == 0, completed.stderr
    assert "--start" in completed.stdout
    assert "--end" in completed.stdout
    assert "--output" in completed.stdout


def test_cache_script_rejects_invalid_date_format(tmp_path: pathlib.Path) -> None:
    out = tmp_path / "out.jsonl"
    completed = subprocess.run(
        [
            sys.executable, str(SCRIPT_PATH),
            "--start", "2025/03/01",  # wrong separator
            "--end", "2025-04-30",
            "--output", str(out),
        ],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert completed.returncode == 2, (
        f"expected exit 2 for argparse error, got {completed.returncode}: "
        f"stdout={completed.stdout!r} stderr={completed.stderr!r}"
    )


def test_cache_script_rejects_future_end(tmp_path: pathlib.Path) -> None:
    out = tmp_path / "out.jsonl"
    completed = subprocess.run(
        [
            sys.executable, str(SCRIPT_PATH),
            "--start", "2025-03-01",
            "--end", "2099-01-01",
            "--output", str(out),
        ],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert completed.returncode != 0, (
        f"expected non-zero exit for future --end, got {completed.returncode}"
    )


def test_cache_script_rejects_end_before_start(tmp_path: pathlib.Path) -> None:
    out = tmp_path / "out.jsonl"
    completed = subprocess.run(
        [
            sys.executable, str(SCRIPT_PATH),
            "--start", "2025-04-30",
            "--end", "2025-03-01",
            "--output", str(out),
        ],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert completed.returncode != 0


# ---------------------------------------------------------------------------
# Optional integration test (gated)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    os.environ.get("INTEGRATION_TESTS") != "1",
    reason="hits real yfinance — set INTEGRATION_TESTS=1 to run",
)
def test_cache_script_real_yfinance(tmp_path: pathlib.Path) -> None:
    out = tmp_path / "real.jsonl"
    completed = subprocess.run(
        [
            sys.executable, str(SCRIPT_PATH),
            "--start", "2024-01-02",
            "--end", "2024-01-15",
            "--output", str(out),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stderr
    assert out.is_file()
    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines() if line.strip()]
    benchmarks = {row["benchmark"] for row in rows}
    assert benchmarks == EXPECTED_BENCHMARKS
    # Spot-check that all dates are within the requested window.
    for row in rows:
        d = _dt.date.fromisoformat(row["date"])
        assert _dt.date(2024, 1, 2) <= d <= _dt.date(2024, 1, 15)
        assert isinstance(row["close"], float)


# ---------------------------------------------------------------------------
# Regression tests for code-quality NIT fixes
# ---------------------------------------------------------------------------


def test_load_rejects_duplicate_benchmark_date_pair(tmp_path: pathlib.Path) -> None:
    """Two rows with the same (benchmark, date) must raise — silent
    last-write-wins violates the project's blank-over-wrong principle.
    A hand-edited fixture or a cache from a different builder could
    carry duplicates and the loader must surface them."""
    cache_path = tmp_path / "dup.jsonl"
    cache_path.write_text(
        "\n".join(
            [
                json.dumps({"benchmark": "SPY", "date": "2025-03-03", "close": 100.0}),
                json.dumps({"benchmark": "QQQ", "date": "2025-03-03", "close": 200.0}),
                json.dumps({"benchmark": "KOSPI", "date": "2025-03-03", "close": 2500.0}),
                # Duplicate of the SPY row above with a different close.
                json.dumps({"benchmark": "SPY", "date": "2025-03-03", "close": 999.0}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(BenchmarkCacheError, match="duplicate"):
        load_benchmark_cache(cache_path)


def test_get_benchmark_close_default_lookahead_covers_kr_chuseok() -> None:
    """Default max_lookahead_days must be wide enough to cross KR
    multi-day closures. Mirrors BACKTEST_PRICE_LOOKBACK_DAYS=10 in
    the yfinance collector — Chuseok can stack 8+ calendar days."""
    # Synthetic cache where KOSPI has a 9-day gap (Sep 30 -> Oct 9),
    # close to Chuseok 2017's actual schedule.
    cache: dict[str, dict[_dt.date, float]] = {
        "SPY": {_dt.date(2017, 9, 29): 100.0, _dt.date(2017, 10, 9): 105.0},
        "QQQ": {_dt.date(2017, 9, 29): 200.0, _dt.date(2017, 10, 9): 210.0},
        "KOSPI": {_dt.date(2017, 9, 29): 2400.0, _dt.date(2017, 10, 9): 2450.0},
    }
    # 5-day lookback (the prior default) would have failed: Sep 30 ->
    # forward search Sep 30 .. Oct 5 finds nothing. 10-day default
    # walks Sep 30 .. Oct 10 and finds Oct 9.
    close = get_benchmark_close(cache, "KOSPI", _dt.date(2017, 9, 30))
    assert close == 2450.0, (
        "Default max_lookahead_days must cover ~9-day KR holiday stacks "
        "(Chuseok). The Task 2.1 collector uses BACKTEST_PRICE_LOOKBACK_"
        "DAYS=10 — keep this in sync."
    )
