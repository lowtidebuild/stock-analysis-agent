"""Tests for :class:`OutcomeComputer` (Task 4.2).

Covers Task 4.2 of the backtest harness plan
(``docs/superpowers/plans/2026-05-08-backtest-harness.md``):

- :func:`add_months` — pure month-arithmetic helper with end-of-month
  rollover semantics.
- :class:`OutcomeComputer` — computes 1M / 3M / 6M / 12M forward returns
  and benchmark-adjusted excess returns for a (ticker, as_of) pair.
- ``write_outcome`` atomic persistence.

Real yfinance calls are gated behind ``INTEGRATION_TESTS=1``. Unit tests
inject a mock ``price_fetcher`` callable.

Run via: ``python -m pytest tests/backtest/test_outcome_computer.py -v``
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.backtest.outcome_computer import (  # noqa: E402
    ForwardPriceUnavailable,
    OutcomeComputer,
    OutcomeComputerError,
    add_months,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_benchmark_cache(
    benchmarks: dict[str, list[tuple[_dt.date, float]]],
) -> dict[str, dict[_dt.date, float]]:
    """Build a benchmark cache dict from {name: [(date, close), ...]}."""
    return {
        name: {date: close for date, close in entries}
        for name, entries in benchmarks.items()
    }


def _series(start: _dt.date, prices: list[float]) -> dict[_dt.date, float]:
    """Build a daily-spaced ``{date: close}`` series."""
    return {
        start + _dt.timedelta(days=offset): price
        for offset, price in enumerate(prices)
    }


# ---------------------------------------------------------------------------
# add_months
# ---------------------------------------------------------------------------


def test_add_months_simple() -> None:
    assert add_months(_dt.date(2025, 1, 15), 3) == _dt.date(2025, 4, 15)


def test_add_months_end_of_month_rollover_non_leap() -> None:
    # Jan 31 + 1m → Feb 28 in 2025 (non-leap)
    assert add_months(_dt.date(2025, 1, 31), 1) == _dt.date(2025, 2, 28)


def test_add_months_end_of_month_rollover_leap() -> None:
    # Jan 31 + 1m → Feb 29 in 2024 (leap year)
    assert add_months(_dt.date(2024, 1, 31), 1) == _dt.date(2024, 2, 29)


def test_add_months_year_rollover() -> None:
    assert add_months(_dt.date(2025, 12, 15), 3) == _dt.date(2026, 3, 15)
    # Dec + 1m = next year Jan
    assert add_months(_dt.date(2025, 12, 31), 1) == _dt.date(2026, 1, 31)


def test_add_months_twelve_months_is_anniversary() -> None:
    assert add_months(_dt.date(2025, 3, 31), 12) == _dt.date(2026, 3, 31)
    # Feb 29 + 12m → Feb 28 (anniversary year is non-leap)
    assert add_months(_dt.date(2024, 2, 29), 12) == _dt.date(2025, 2, 28)


def test_add_months_zero_returns_same_date() -> None:
    assert add_months(_dt.date(2025, 5, 15), 0) == _dt.date(2025, 5, 15)


def test_add_months_negative_raises() -> None:
    with pytest.raises(ValueError):
        add_months(_dt.date(2025, 5, 15), -1)


def test_add_months_requires_date() -> None:
    with pytest.raises(TypeError):
        add_months("2025-05-15", 3)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# OutcomeComputer.compute — benchmark selection
# ---------------------------------------------------------------------------


def _us_benchmark_cache_for_2025() -> dict[str, dict[_dt.date, float]]:
    """SPY/QQQ/KOSPI cache spanning 2025-03-26 .. 2026-04-15.

    Daily linear ramp so the math is easy to reason about.
    """
    start = _dt.date(2025, 3, 26)
    end = _dt.date(2026, 4, 15)
    days = (end - start).days + 1
    return {
        "SPY": {
            start + _dt.timedelta(days=i): 500.0 + i * 1.0
            for i in range(days)
        },
        "QQQ": {
            start + _dt.timedelta(days=i): 400.0 + i * 0.5
            for i in range(days)
        },
        "KOSPI": {
            start + _dt.timedelta(days=i): 2500.0 + i * 2.0
            for i in range(days)
        },
    }


def _make_fetcher(
    series: dict[_dt.date, float],
) -> "object":
    """Build a mock ``price_fetcher`` callable returning the supplied series."""

    def fetcher(
        ticker: str,
        start_date: _dt.date,
        end_date: _dt.date,
    ) -> dict[_dt.date, float]:
        del ticker
        return {
            d: c
            for d, c in series.items()
            if start_date <= d <= end_date
        }

    return fetcher


def test_compute_us_uses_spy_default() -> None:
    cache = _us_benchmark_cache_for_2025()
    as_of = _dt.date(2025, 3, 31)
    # Daily +1 ramp on the ticker too.
    ticker_series = {
        as_of + _dt.timedelta(days=i): 100.0 + i for i in range(380)
    }
    computer = OutcomeComputer(
        benchmark_cache=cache,
        price_fetcher=_make_fetcher(ticker_series),
    )
    outcome = computer.compute(ticker="AAPL", market="US", as_of=as_of)
    assert outcome["benchmark"] == "SPY"


def test_compute_kr_uses_kospi() -> None:
    cache = _us_benchmark_cache_for_2025()
    as_of = _dt.date(2025, 3, 31)
    ticker_series = {
        as_of + _dt.timedelta(days=i): 70000.0 + i * 100 for i in range(380)
    }
    computer = OutcomeComputer(
        benchmark_cache=cache,
        price_fetcher=_make_fetcher(ticker_series),
    )
    outcome = computer.compute(ticker="005930", market="KR", as_of=as_of)
    assert outcome["benchmark"] == "KOSPI"


def test_compute_prefer_qqq_overrides_to_qqq() -> None:
    cache = _us_benchmark_cache_for_2025()
    as_of = _dt.date(2025, 3, 31)
    ticker_series = {
        as_of + _dt.timedelta(days=i): 100.0 + i for i in range(380)
    }
    computer = OutcomeComputer(
        benchmark_cache=cache,
        price_fetcher=_make_fetcher(ticker_series),
    )
    outcome = computer.compute(
        ticker="NVDA", market="US", as_of=as_of, prefer_qqq=True
    )
    assert outcome["benchmark"] == "QQQ"


# ---------------------------------------------------------------------------
# OutcomeComputer.compute — return math
# ---------------------------------------------------------------------------


def test_compute_horizon_returns_correct() -> None:
    """Known prices: as_of close = 100, +1m = 110, +3m = 121, +6m = 130, +12m = 150.

    Returns: 1m=10%, 3m=21%, 6m=30%, 12m=50%.
    """
    cache = _us_benchmark_cache_for_2025()
    as_of = _dt.date(2025, 3, 31)
    horizons_dates = {
        "1m": add_months(as_of, 1),
        "3m": add_months(as_of, 3),
        "6m": add_months(as_of, 6),
        "12m": add_months(as_of, 12),
    }
    ticker_series: dict[_dt.date, float] = {as_of: 100.0}
    ticker_series[horizons_dates["1m"]] = 110.0
    ticker_series[horizons_dates["3m"]] = 121.0
    ticker_series[horizons_dates["6m"]] = 130.0
    ticker_series[horizons_dates["12m"]] = 150.0

    computer = OutcomeComputer(
        benchmark_cache=cache,
        price_fetcher=_make_fetcher(ticker_series),
    )
    outcome = computer.compute(ticker="AAPL", market="US", as_of=as_of)
    assert outcome["ticker_close_at_as_of"] == 100.0
    assert outcome["horizons"]["1m"]["ticker_return"] == pytest.approx(0.10)
    assert outcome["horizons"]["3m"]["ticker_return"] == pytest.approx(0.21)
    assert outcome["horizons"]["6m"]["ticker_return"] == pytest.approx(0.30)
    assert outcome["horizons"]["12m"]["ticker_return"] == pytest.approx(0.50)


def test_compute_excess_return_subtraction() -> None:
    """Ticker +5% over a horizon, benchmark +2% → excess = 3%."""
    as_of = _dt.date(2025, 3, 31)
    target_1m = add_months(as_of, 1)
    # Tight 2-point cache spanning every relevant horizon date.
    cache = {
        "SPY": {as_of: 100.0, target_1m: 102.0},
        "QQQ": {as_of: 100.0, target_1m: 102.0},
        "KOSPI": {as_of: 1000.0, target_1m: 1020.0},
    }
    # Add far-future entries so 3m/6m/12m don't blow up the test.
    for name in cache:
        cache[name][add_months(as_of, 3)] = cache[name][as_of] * 1.0
        cache[name][add_months(as_of, 6)] = cache[name][as_of] * 1.0
        cache[name][add_months(as_of, 12)] = cache[name][as_of] * 1.0

    ticker_series = {as_of: 50.0, target_1m: 52.5}
    for h in (3, 6, 12):
        ticker_series[add_months(as_of, h)] = 50.0  # no change → not asserted

    computer = OutcomeComputer(
        benchmark_cache=cache,
        price_fetcher=_make_fetcher(ticker_series),
    )
    outcome = computer.compute(ticker="AAPL", market="US", as_of=as_of)
    h1m = outcome["horizons"]["1m"]
    assert h1m["ticker_return"] == pytest.approx(0.05)
    assert h1m["benchmark_return"] == pytest.approx(0.02)
    assert h1m["excess_return"] == pytest.approx(0.03)


def test_compute_forward_search_handles_weekend_as_of() -> None:
    """as_of=Saturday 2025-03-29 → uses Monday 2025-03-31 close."""
    saturday = _dt.date(2025, 3, 29)  # Saturday
    monday = _dt.date(2025, 3, 31)
    cache = _us_benchmark_cache_for_2025()
    # Ticker only has data starting Monday.
    ticker_series: dict[_dt.date, float] = {monday: 100.0}
    for h in (1, 3, 6, 12):
        ticker_series[add_months(monday, h)] = 100.0

    computer = OutcomeComputer(
        benchmark_cache=cache,
        price_fetcher=_make_fetcher(ticker_series),
    )
    outcome = computer.compute(ticker="AAPL", market="US", as_of=saturday)
    assert outcome["ticker_close_at_as_of"] == 100.0
    # `as_of` round-trips the input.
    assert outcome["as_of"] == saturday.isoformat()
    # `actual_as_of_date` records the trading day that actually supplied
    # the close — this is the load-bearing forward-search assertion.
    assert outcome["actual_as_of_date"] == monday.isoformat()


def test_compute_records_data_unavailable_when_horizon_missing() -> None:
    """as_of=2025-03-31; mock fetcher returns only ~6 months of data → 12m
    horizon is recorded as null + ``_status="data_unavailable"``."""
    as_of = _dt.date(2025, 3, 31)
    cache = _us_benchmark_cache_for_2025()
    ticker_series: dict[_dt.date, float] = {
        as_of: 100.0,
        add_months(as_of, 1): 105.0,
        add_months(as_of, 3): 110.0,
        add_months(as_of, 6): 115.0,
        # Nothing for 12m.
    }

    computer = OutcomeComputer(
        benchmark_cache=cache,
        price_fetcher=_make_fetcher(ticker_series),
    )
    outcome = computer.compute(ticker="AAPL", market="US", as_of=as_of)
    h12 = outcome["horizons"]["12m"]
    assert h12["ticker_close"] is None
    assert h12["ticker_return"] is None
    assert h12["excess_return"] is None
    assert h12.get("_status") == "data_unavailable"


def test_compute_raises_when_as_of_close_unavailable() -> None:
    """Fetcher returns no data near as_of → ForwardPriceUnavailable."""
    as_of = _dt.date(2025, 3, 31)
    cache = _us_benchmark_cache_for_2025()
    # Ticker series is far in the past; nothing within forward-search range.
    ticker_series = {_dt.date(2024, 1, 1): 50.0}

    computer = OutcomeComputer(
        benchmark_cache=cache,
        price_fetcher=_make_fetcher(ticker_series),
    )
    with pytest.raises(ForwardPriceUnavailable):
        computer.compute(ticker="AAPL", market="US", as_of=as_of)


def test_compute_uses_default_max_lookahead_10() -> None:
    """Default kwarg verified by reading the attribute."""
    cache = _us_benchmark_cache_for_2025()
    computer = OutcomeComputer(benchmark_cache=cache)
    assert computer.max_lookahead_days == 10


def test_compute_outcome_meta_block() -> None:
    """``_backtest_meta`` block carries computed_at, fetch window, lookahead."""
    cache = _us_benchmark_cache_for_2025()
    as_of = _dt.date(2025, 3, 31)
    ticker_series = {as_of + _dt.timedelta(days=i): 100.0 + i for i in range(380)}
    computer = OutcomeComputer(
        benchmark_cache=cache,
        price_fetcher=_make_fetcher(ticker_series),
    )
    outcome = computer.compute(ticker="AAPL", market="US", as_of=as_of)
    meta = outcome["_backtest_meta"]
    assert "computed_at" in meta
    assert meta["fetch_window_start"] == (as_of - _dt.timedelta(days=5)).isoformat()
    assert meta["fetch_window_end"] == (as_of + _dt.timedelta(days=380)).isoformat()
    assert meta["max_lookahead_days"] == 10


def test_compute_horizon_dates_anchored_to_as_of() -> None:
    """target_date for each horizon is add_months(as_of, N), NOT actual_date."""
    cache = _us_benchmark_cache_for_2025()
    as_of = _dt.date(2025, 3, 31)
    ticker_series: dict[_dt.date, float] = {as_of: 100.0}
    for h in (1, 3, 6, 12):
        ticker_series[add_months(as_of, h)] = 100.0

    computer = OutcomeComputer(
        benchmark_cache=cache,
        price_fetcher=_make_fetcher(ticker_series),
    )
    outcome = computer.compute(ticker="AAPL", market="US", as_of=as_of)
    assert outcome["horizons"]["1m"]["target_date"] == add_months(as_of, 1).isoformat()
    assert outcome["horizons"]["3m"]["target_date"] == add_months(as_of, 3).isoformat()
    assert outcome["horizons"]["6m"]["target_date"] == add_months(as_of, 6).isoformat()
    assert outcome["horizons"]["12m"]["target_date"] == add_months(as_of, 12).isoformat()


# ---------------------------------------------------------------------------
# Persistence (write_outcome)
# ---------------------------------------------------------------------------


def test_write_outcome_creates_file_atomically(tmp_path: pathlib.Path) -> None:
    cache = _us_benchmark_cache_for_2025()
    as_of = _dt.date(2025, 3, 31)
    ticker_series = {as_of + _dt.timedelta(days=i): 100.0 + i for i in range(380)}
    computer = OutcomeComputer(
        benchmark_cache=cache,
        price_fetcher=_make_fetcher(ticker_series),
    )
    outcome = computer.compute(ticker="AAPL", market="US", as_of=as_of)

    ticker_dir = tmp_path / "AAPL"
    ticker_dir.mkdir()
    written = computer.write_outcome(ticker_run_dir=ticker_dir, outcome=outcome)

    assert written.is_file()
    assert written.name == "_outcome.json"
    payload = json.loads(written.read_text(encoding="utf-8"))
    assert payload["ticker"] == "AAPL"
    assert payload["benchmark"] == "SPY"
    # No leftover .tmp file.
    assert not (ticker_dir / "_outcome.json.tmp").exists()


def test_write_outcome_overwrites_existing(tmp_path: pathlib.Path) -> None:
    cache = _us_benchmark_cache_for_2025()
    as_of = _dt.date(2025, 3, 31)
    ticker_series = {as_of + _dt.timedelta(days=i): 100.0 + i for i in range(380)}
    computer = OutcomeComputer(
        benchmark_cache=cache,
        price_fetcher=_make_fetcher(ticker_series),
    )
    outcome = computer.compute(ticker="AAPL", market="US", as_of=as_of)

    ticker_dir = tmp_path / "AAPL"
    ticker_dir.mkdir()
    # Pre-existing file with stale data.
    (ticker_dir / "_outcome.json").write_text(
        '{"ticker": "STALE"}', encoding="utf-8"
    )

    written = computer.write_outcome(ticker_run_dir=ticker_dir, outcome=outcome)
    payload = json.loads(written.read_text(encoding="utf-8"))
    assert payload["ticker"] == "AAPL"


def test_write_outcome_creates_parent_dir(tmp_path: pathlib.Path) -> None:
    """write_outcome should create the ticker_run_dir if it doesn't exist."""
    cache = _us_benchmark_cache_for_2025()
    as_of = _dt.date(2025, 3, 31)
    ticker_series = {as_of + _dt.timedelta(days=i): 100.0 + i for i in range(380)}
    computer = OutcomeComputer(
        benchmark_cache=cache,
        price_fetcher=_make_fetcher(ticker_series),
    )
    outcome = computer.compute(ticker="AAPL", market="US", as_of=as_of)

    nonexistent = tmp_path / "deep" / "nested" / "AAPL"
    written = computer.write_outcome(ticker_run_dir=nonexistent, outcome=outcome)
    assert written.is_file()


# ---------------------------------------------------------------------------
# Schema sanity
# ---------------------------------------------------------------------------


def test_compute_full_schema_keys_present() -> None:
    cache = _us_benchmark_cache_for_2025()
    as_of = _dt.date(2025, 3, 31)
    ticker_series = {as_of + _dt.timedelta(days=i): 100.0 + i for i in range(380)}
    computer = OutcomeComputer(
        benchmark_cache=cache,
        price_fetcher=_make_fetcher(ticker_series),
    )
    outcome = computer.compute(ticker="AAPL", market="US", as_of=as_of)

    expected_top = {
        "ticker", "market", "as_of", "benchmark",
        "ticker_close_at_as_of", "horizons", "_backtest_meta",
    }
    assert expected_top.issubset(outcome.keys())
    assert set(outcome["horizons"].keys()) == {"1m", "3m", "6m", "12m"}
    expected_horizon = {
        "target_date", "actual_date", "ticker_close", "ticker_return",
        "benchmark_close", "benchmark_return", "excess_return",
    }
    for hkey, hvals in outcome["horizons"].items():
        assert expected_horizon.issubset(hvals.keys()), (
            f"horizon {hkey} missing keys: "
            f"{expected_horizon - set(hvals.keys())}"
        )


# ---------------------------------------------------------------------------
# Optional integration test
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    os.environ.get("INTEGRATION_TESTS") != "1",
    reason="hits real yfinance — set INTEGRATION_TESTS=1 to run",
)
def test_compute_real_yfinance_aapl_2025q1() -> None:
    """Real yfinance fetch for AAPL with as_of=2025-03-31."""
    fixture_path = ROOT / "evals" / "backtest" / "data" / "benchmark-prices-fixture.jsonl"
    from tools.backtest.benchmark_cache import load_benchmark_cache

    cache = load_benchmark_cache(fixture_path)
    computer = OutcomeComputer(benchmark_cache=cache)
    as_of = _dt.date(2025, 3, 31)
    outcome = computer.compute(ticker="AAPL", market="US", as_of=as_of)
    assert outcome["ticker"] == "AAPL"
    assert outcome["benchmark"] == "SPY"
    assert outcome["ticker_close_at_as_of"] is not None
    # 1m and 3m horizons should land within the fixture window
    # (2025-03-03 .. 2025-04-30 covers up to ~1m).
    h1m = outcome["horizons"]["1m"]
    assert h1m["ticker_close"] is not None
