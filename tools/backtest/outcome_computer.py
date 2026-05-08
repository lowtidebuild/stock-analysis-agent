"""Forward-return outcome computer for the backtest harness.

Task 4.2 of the backtest plan
(``docs/superpowers/plans/2026-05-08-backtest-harness.md``).

Given a ``(ticker, as_of)`` pair, :class:`OutcomeComputer` computes
forward returns at 1M / 3M / 6M / 12M horizons plus benchmark-adjusted
excess returns, and persists the result to ``_outcome.json`` next to
the ticker's run artifacts. Cohort aggregation (Task 4.3) consumes
those files.

How horizons are anchored
-------------------------

A horizon ``Nm`` resolves to a *target date* via :func:`add_months`,
which uses calendar-month arithmetic with end-of-month rollover (e.g.
2025-01-31 + 1m → 2025-02-28; 2024-01-31 + 1m → 2024-02-29). The actual
*trading-day close* used for the return is then found by forward search
up to ``max_lookahead_days`` calendar days — long enough to skip a
weekend, a US holiday, or a stacked KR closure (Chuseok / Lunar New
Year). This mirrors the lookahead used by
:func:`tools.backtest.benchmark_cache.get_benchmark_close`.

Returns are computed as ``(close_at_target / close_at_as_of) - 1`` (a
plain decimal — 0.0289 = 2.89%).

Why in-process Python (not a subprocess)
----------------------------------------

:class:`tools.backtest.historical_adapters.YFinanceHistorical` and
friends call the production collector scripts via ``subprocess`` for
production parity (the live pipeline shells out to those scripts too).
Outcome computation, by contrast, has no production analog — the
production pipeline never asks "what happened 12 months *after* the
analysis date?" — so there is no parity argument and an in-process
implementation keeps cohort runs faster (no fork-per-ticker) and
testable with a simple injected ``price_fetcher`` callable.

Output schema
-------------

::

    {
      "ticker": "AAPL",
      "market": "US",
      "as_of": "2025-03-31",
      "benchmark": "QQQ",
      "ticker_close_at_as_of": 207.42,
      "horizons": {
        "1m": {
          "target_date": "2025-04-30",
          "actual_date": "2025-04-30",
          "ticker_close": 213.41,
          "ticker_return": 0.0289,
          "benchmark_close": 480.5,
          "benchmark_return": 0.0142,
          "excess_return": 0.0147
        },
        "3m": { ... },
        "6m": { ... },
        "12m": {
          "target_date": "2026-03-31",
          "actual_date": null,
          "ticker_close": null,
          "ticker_return": null,
          "benchmark_close": null,
          "benchmark_return": null,
          "excess_return": null,
          "_status": "data_unavailable"
        }
      },
      "_backtest_meta": {
        "computed_at": "2026-05-09T12:34:56+00:00",
        "fetch_window_start": "2025-03-26",
        "fetch_window_end": "2026-04-15",
        "max_lookahead_days": 10
      }
    }
"""

from __future__ import annotations

import calendar
import datetime as _dt
import json
import os
import pathlib
from typing import Any, Callable, Literal

from tools.backtest.benchmark_cache import (
    get_benchmark_close,
    select_benchmark,
)


_DEFAULT_HORIZONS: tuple[tuple[str, int], ...] = (
    ("1m", 1),
    ("3m", 3),
    ("6m", 6),
    ("12m", 12),
)
# Mirrors the benchmark cache default. KR multi-day closures (Chuseok)
# can stack 8+ calendar days; 10 covers them with a safety margin.
_DEFAULT_MAX_LOOKAHEAD_DAYS = 10
# 5 days back lets a Saturday/Sunday as_of fall through to the next
# trading day; the 380-day forward window covers the 12m horizon plus
# the lookahead buffer.
_FETCH_BACKWARD_DAYS = 5
_FETCH_FORWARD_DAYS = 380

# Korean ticker suffixes for yfinance. KOSPI uses ``.KS``; KOSDAQ uses
# ``.KQ``. The 6-digit ticker alone is ambiguous, so the default fetcher
# tries ``.KS`` first then falls back to ``.KQ``.
_KR_SUFFIX_KOSPI = ".KS"
_KR_SUFFIX_KOSDAQ = ".KQ"


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class OutcomeComputerError(RuntimeError):
    """Base exception for outcome-computer failures."""


class ForwardPriceUnavailable(OutcomeComputerError):
    """Raised when the ticker has no close price near ``as_of``.

    Distinct from a horizon-level data gap (which is recorded in the
    output dict as ``_status="data_unavailable"``) — if we cannot anchor
    the *as-of* close, every horizon return would be ill-defined and
    the row should be excluded from cohort statistics entirely.
    """


# ---------------------------------------------------------------------------
# Pure date helper
# ---------------------------------------------------------------------------


def add_months(d: _dt.date, months: int) -> _dt.date:
    """Add ``months`` calendar months to ``d`` with end-of-month rollover.

    Examples
    --------
    >>> add_months(datetime.date(2025, 1, 15), 3)
    datetime.date(2025, 4, 15)
    >>> add_months(datetime.date(2025, 1, 31), 1)
    datetime.date(2025, 2, 28)
    >>> add_months(datetime.date(2024, 1, 31), 1)
    datetime.date(2024, 2, 29)
    >>> add_months(datetime.date(2025, 12, 15), 3)
    datetime.date(2026, 3, 15)

    Parameters
    ----------
    d:
        Base date. Must be :class:`datetime.date` (not
        :class:`datetime.datetime`).
    months:
        Number of calendar months to add. Must be ``>= 0``. Negative
        offsets are not supported — outcome computation only ever walks
        forward.

    Returns
    -------
    datetime.date
        The shifted date, clamped to the last day of the target month
        when the source day overflows.

    Raises
    ------
    TypeError
        ``d`` is not a :class:`datetime.date`.
    ValueError
        ``months`` is negative.
    """
    if not isinstance(d, _dt.date) or isinstance(d, _dt.datetime):
        raise TypeError(
            f"d must be datetime.date (not {type(d).__name__})"
        )
    if months < 0:
        raise ValueError(
            f"months must be >= 0, got {months}; outcome computation "
            "is forward-only"
        )

    total = d.month - 1 + months
    new_year = d.year + total // 12
    new_month = total % 12 + 1
    last_day = calendar.monthrange(new_year, new_month)[1]
    new_day = min(d.day, last_day)
    return _dt.date(new_year, new_month, new_day)


# ---------------------------------------------------------------------------
# Default price fetcher
# ---------------------------------------------------------------------------


def _to_yfinance_symbol(ticker: str, market: str) -> tuple[str, str | None]:
    """Map a ticker to a yfinance symbol, with optional fallback.

    Returns a ``(primary, fallback)`` tuple. ``fallback`` is ``None`` for
    US tickers; KR 6-digit codes try ``.KS`` first then ``.KQ``.
    """
    if market == "KR" and ticker.isdigit() and len(ticker) == 6:
        return f"{ticker}{_KR_SUFFIX_KOSPI}", f"{ticker}{_KR_SUFFIX_KOSDAQ}"
    # If the caller passed a fully-qualified KR symbol, leave it alone.
    return ticker, None


def _yfinance_forward_prices(
    ticker: str,
    start_date: _dt.date,
    end_date: _dt.date,
) -> dict[_dt.date, float]:
    """Default ``price_fetcher`` — fetches daily closes via yfinance.

    Tries the supplied ``ticker`` symbol directly. If the caller has
    encoded the market into the symbol (``005930.KS``), only the literal
    symbol is queried; otherwise the helper assumes US for the default
    path. KR fallback (``.KS`` → ``.KQ``) is handled by
    :class:`OutcomeComputer` before calling this fetcher.

    Imported lazily so unit tests that inject a mock fetcher never
    require yfinance.
    """
    import yfinance  # type: ignore[import-untyped]

    # yfinance ``end`` is exclusive. Add one day to include ``end_date``.
    yf_end = end_date + _dt.timedelta(days=1)
    history = yfinance.Ticker(ticker).history(
        start=start_date.isoformat(),
        end=yf_end.isoformat(),
        interval="1d",
        auto_adjust=False,
    )
    if history is None or history.empty:
        return {}

    closes: dict[_dt.date, float] = {}
    for idx, row in history.iterrows():
        # idx is a pandas Timestamp; convert to date.
        try:
            d = idx.date()
        except AttributeError:
            d = _dt.date.fromisoformat(str(idx)[:10])
        close = row.get("Close")
        if close is None:
            continue
        try:
            closes[d] = float(close)
        except (TypeError, ValueError):
            continue
    return closes


# ---------------------------------------------------------------------------
# OutcomeComputer
# ---------------------------------------------------------------------------


class OutcomeComputer:
    """Compute forward returns + benchmark-adjusted excess returns.

    Parameters
    ----------
    benchmark_cache:
        Output of
        :func:`tools.backtest.benchmark_cache.load_benchmark_cache`.
        Outer key: benchmark name. Inner: ``{date: close}``.
    price_fetcher:
        Callable ``(ticker, start_date, end_date) -> {date: close}``. The
        default uses yfinance; tests inject a deterministic mock.
    max_lookahead_days:
        Forward-search window for non-trading days, applied to both
        the ticker series and the benchmark cache. Defaults to 10 to
        match :func:`get_benchmark_close`.
    horizons:
        Tuple of ``(label, months)`` pairs to compute. The default is
        ``(("1m", 1), ("3m", 3), ("6m", 6), ("12m", 12))``.
    """

    def __init__(
        self,
        *,
        benchmark_cache: dict[str, dict[_dt.date, float]],
        price_fetcher: (
            Callable[[str, _dt.date, _dt.date], dict[_dt.date, float]] | None
        ) = None,
        max_lookahead_days: int = _DEFAULT_MAX_LOOKAHEAD_DAYS,
        horizons: tuple[tuple[str, int], ...] = _DEFAULT_HORIZONS,
    ) -> None:
        if max_lookahead_days < 0:
            raise OutcomeComputerError(
                f"max_lookahead_days must be >= 0, got {max_lookahead_days}"
            )
        if not horizons:
            raise OutcomeComputerError("horizons must be non-empty")

        self.benchmark_cache = benchmark_cache
        self.price_fetcher = price_fetcher or _yfinance_forward_prices
        self.max_lookahead_days = max_lookahead_days
        self.horizons = horizons

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def compute(
        self,
        *,
        ticker: str,
        market: Literal["US", "KR"],
        as_of: _dt.date,
        prefer_qqq: bool = False,
    ) -> dict[str, Any]:
        """Compute the outcome dict for ``(ticker, as_of)``.

        See module docstring for the full output schema.

        Raises
        ------
        ForwardPriceUnavailable
            No close price found within the forward-search window of
            ``as_of``. The cohort runner should drop this row.
        """
        if not isinstance(as_of, _dt.date) or isinstance(as_of, _dt.datetime):
            raise TypeError(
                f"as_of must be datetime.date (not {type(as_of).__name__})"
            )

        benchmark = select_benchmark(market, ticker=ticker, prefer_qqq=prefer_qqq)
        fetch_start = as_of - _dt.timedelta(days=_FETCH_BACKWARD_DAYS)
        fetch_end = as_of + _dt.timedelta(days=_FETCH_FORWARD_DAYS)

        ticker_prices = self._fetch_ticker_prices(
            ticker=ticker,
            market=market,
            start=fetch_start,
            end=fetch_end,
        )

        as_of_lookup = self._forward_search(ticker_prices, as_of)
        if as_of_lookup is None:
            raise ForwardPriceUnavailable(
                f"no close price found for {ticker!r} within "
                f"{self.max_lookahead_days} days of as_of={as_of.isoformat()}"
            )
        actual_as_of_date, ticker_close_at_as_of = as_of_lookup

        bench_as_of_lookup = self._forward_search_benchmark(benchmark, as_of)
        # Benchmark cache is forward-filled, but defensively allow a None
        # here too — if the as-of falls past the cache window the horizon
        # rows will record data_unavailable.
        benchmark_close_at_as_of = (
            bench_as_of_lookup[1] if bench_as_of_lookup is not None else None
        )

        horizons_out: dict[str, dict[str, Any]] = {}
        for label, months in self.horizons:
            target_date = add_months(as_of, months)
            horizons_out[label] = self._compute_horizon(
                target_date=target_date,
                ticker_prices=ticker_prices,
                benchmark=benchmark,
                ticker_close_at_as_of=ticker_close_at_as_of,
                benchmark_close_at_as_of=benchmark_close_at_as_of,
            )

        return {
            "ticker": ticker,
            "market": market,
            "as_of": as_of.isoformat(),
            "benchmark": benchmark,
            "ticker_close_at_as_of": ticker_close_at_as_of,
            "actual_as_of_date": actual_as_of_date.isoformat(),
            "horizons": horizons_out,
            "_backtest_meta": {
                "computed_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
                "fetch_window_start": fetch_start.isoformat(),
                "fetch_window_end": fetch_end.isoformat(),
                "max_lookahead_days": self.max_lookahead_days,
            },
        }

    def write_outcome(
        self,
        *,
        ticker_run_dir: pathlib.Path,
        outcome: dict[str, Any],
    ) -> pathlib.Path:
        """Atomically write ``_outcome.json`` to ``ticker_run_dir``.

        Uses a sibling ``.tmp`` file + :func:`os.replace` so a crash
        mid-write never leaves a partial JSON document. Idempotent —
        re-calling overwrites the prior file.

        Parameters
        ----------
        ticker_run_dir:
            Directory that holds the ticker's run artifacts. Created if
            missing (including parents).
        outcome:
            Dict returned by :meth:`compute` (or a structurally
            equivalent payload).

        Returns
        -------
        pathlib.Path
            The path to the written ``_outcome.json``.
        """
        ticker_run_dir = pathlib.Path(ticker_run_dir)
        ticker_run_dir.mkdir(parents=True, exist_ok=True)
        path = ticker_run_dir / "_outcome.json"
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(
            json.dumps(outcome, indent=2, sort_keys=False) + "\n",
            encoding="utf-8",
        )
        os.replace(tmp_path, path)
        return path

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fetch_ticker_prices(
        self,
        *,
        ticker: str,
        market: str,
        start: _dt.date,
        end: _dt.date,
    ) -> dict[_dt.date, float]:
        """Fetch ticker prices, handling KR ``.KS``/``.KQ`` fallback."""
        primary, fallback = _to_yfinance_symbol(ticker, market)
        prices = self.price_fetcher(primary, start, end)
        if not prices and fallback is not None:
            prices = self.price_fetcher(fallback, start, end)
        return prices

    def _forward_search(
        self,
        prices: dict[_dt.date, float],
        target: _dt.date,
    ) -> tuple[_dt.date, float] | None:
        """Return ``(actual_date, close)`` at or after ``target``.

        Walks one day at a time up to ``self.max_lookahead_days``.
        Returns ``None`` when nothing is found in the window.
        """
        for offset in range(self.max_lookahead_days + 1):
            candidate = target + _dt.timedelta(days=offset)
            if candidate in prices:
                return candidate, prices[candidate]
        return None

    def _forward_search_benchmark(
        self,
        benchmark: str,
        target: _dt.date,
    ) -> tuple[_dt.date, float] | None:
        """Forward-search the benchmark cache, returning ``(date, close)``.

        Wraps :func:`get_benchmark_close` so we also know which date
        actually supplied the close (for ``actual_date`` in the
        horizon dict).
        """
        # Walk manually so we can record which date hit; benchmark_cache's
        # public API only returns the close.
        series = self.benchmark_cache.get(benchmark, {})
        for offset in range(self.max_lookahead_days + 1):
            candidate = target + _dt.timedelta(days=offset)
            if candidate in series:
                return candidate, series[candidate]
        # Defensive consistency check: ensure get_benchmark_close agrees.
        # Both paths walk the same range with the same lookahead, so a
        # mismatch would point at a contract bug.
        sentinel = get_benchmark_close(
            self.benchmark_cache,
            benchmark,
            target,
            max_lookahead_days=self.max_lookahead_days,
        )
        assert sentinel is None, (
            "benchmark forward-search inconsistency: "
            f"benchmark={benchmark!r} target={target.isoformat()}"
        )
        return None

    def _compute_horizon(
        self,
        *,
        target_date: _dt.date,
        ticker_prices: dict[_dt.date, float],
        benchmark: str,
        ticker_close_at_as_of: float,
        benchmark_close_at_as_of: float | None,
    ) -> dict[str, Any]:
        """Compute one horizon's payload."""
        ticker_lookup = self._forward_search(ticker_prices, target_date)
        bench_lookup = self._forward_search_benchmark(benchmark, target_date)

        if (
            ticker_lookup is None
            or bench_lookup is None
            or benchmark_close_at_as_of is None
        ):
            return {
                "target_date": target_date.isoformat(),
                "actual_date": None,
                "ticker_close": None,
                "ticker_return": None,
                "benchmark_close": None,
                "benchmark_return": None,
                "excess_return": None,
                "_status": "data_unavailable",
            }

        actual_date, ticker_close = ticker_lookup
        _bench_actual_date, benchmark_close = bench_lookup

        ticker_return = (ticker_close / ticker_close_at_as_of) - 1.0
        benchmark_return = (benchmark_close / benchmark_close_at_as_of) - 1.0
        excess_return = ticker_return - benchmark_return

        return {
            "target_date": target_date.isoformat(),
            "actual_date": actual_date.isoformat(),
            "ticker_close": ticker_close,
            "ticker_return": ticker_return,
            "benchmark_close": benchmark_close,
            "benchmark_return": benchmark_return,
            "excess_return": excess_return,
        }


__all__ = [
    "ForwardPriceUnavailable",
    "OutcomeComputer",
    "OutcomeComputerError",
    "add_months",
]
