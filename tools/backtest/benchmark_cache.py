"""Benchmark price cache loader for the backtest harness.

Task 4.1 of the backtest plan
(``docs/superpowers/plans/2026-05-08-backtest-harness.md``) splits the
problem of "what's the benchmark close on date X?" into two pieces:

1. A CLI fixture builder
   (``evals/backtest/scripts/cache-benchmarks.py``) fetches daily closes
   for SPY, QQQ, and KOSPI (yfinance ticker ``^KS11``) over the cohort
   window, forward-fills weekends/holidays, and writes a JSONL file.
2. This module loads that JSONL into an in-memory lookup and exposes a
   small surface to downstream consumers — first :class:`OutcomeComputer`
   in Task 4.2, later cohort aggregation.

Design choices:

- **Pure-stdlib JSONL.** Cohort runs are small (≤ 5 years × 3 benchmarks
  ≈ 5,500 rows). Using JSONL keeps the cache human-inspectable and
  removes a pyarrow dependency. Pandas is only used by the *script*
  (because yfinance returns a DataFrame); the loader stays pure
  stdlib.
- **Forward-fill at the lookup boundary.** The cache file is already
  forward-filled (every calendar day in the requested window has a
  close), but :func:`get_benchmark_close` still walks forward up to
  ``max_lookahead_days`` to handle queries that fall after the last
  cached date or for benchmarks that legitimately have a gap.
- **Fail fast on missing benchmark coverage.** If the JSONL file is
  missing one of the expected benchmarks
  (``SPY``/``QQQ``/``KOSPI``) we raise rather than return a partial
  cache — :class:`OutcomeComputer` is going to ask for all three and a
  silent ``KeyError`` later in the run is worse than a loud failure
  here.

The module mirrors the pure-functions style of
:mod:`tools.backtest.sec_historical`.
"""

from __future__ import annotations

import datetime as _dt
import json
import pathlib
from typing import Literal

_REQUIRED_BENCHMARKS: tuple[str, ...] = ("SPY", "QQQ", "KOSPI")
_REQUIRED_FIELDS: tuple[str, ...] = ("date", "benchmark", "close")
# Mirrors BACKTEST_PRICE_LOOKBACK_DAYS in
# .claude/skills/financial-data-collector/scripts/yfinance-collector.py.
# 10 days covers KR Chuseok (up to ~8 calendar days) and Lunar New Year
# clusters (~5 days + adjacent weekend). 5 days was insufficient.
_DEFAULT_MAX_LOOKAHEAD_DAYS = 10


class BenchmarkCacheError(RuntimeError):
    """Raised for any malformed input encountered while loading or querying.

    Covers four failure modes:

    - Missing JSONL file.
    - JSONL line that fails ``json.loads``.
    - JSONL record missing one of the required fields or carrying a
      non-ISO ``date``.
    - Loaded cache missing one of the required benchmarks.
    - :func:`get_benchmark_close` called with an unknown benchmark name.
    """


def load_benchmark_cache(
    path: pathlib.Path,
) -> dict[str, dict[_dt.date, float]]:
    """Load a benchmark price JSONL file into a lookup table.

    Parameters
    ----------
    path:
        Path to the JSONL file produced by
        ``evals/backtest/scripts/cache-benchmarks.py``. Each line must
        be a JSON object with ``date`` (ISO ``YYYY-MM-DD``),
        ``benchmark`` (one of ``"SPY"``, ``"QQQ"``, ``"KOSPI"``), and
        ``close`` (float).

    Returns
    -------
    dict[str, dict[datetime.date, float]]
        Outer key: benchmark name (``SPY`` / ``QQQ`` / ``KOSPI``).
        Inner key: trading date. Inner value: close price.

    Raises
    ------
    BenchmarkCacheError
        File missing, malformed JSON, missing/typed-wrong fields, or
        any of the three required benchmarks absent from the file.
    """
    resolved = pathlib.Path(path)
    if not resolved.is_file():
        raise BenchmarkCacheError(
            f"benchmark cache file does not exist: {resolved}"
        )

    cache: dict[str, dict[_dt.date, float]] = {}

    with resolved.open("r", encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise BenchmarkCacheError(
                    f"failed to parse JSON on line {lineno} of {resolved}: "
                    f"{exc}"
                ) from exc

            if not isinstance(record, dict):
                raise BenchmarkCacheError(
                    f"line {lineno} of {resolved} is not a JSON object"
                )

            for field in _REQUIRED_FIELDS:
                if field not in record:
                    raise BenchmarkCacheError(
                        f"line {lineno} of {resolved} missing required "
                        f"field {field!r}"
                    )

            benchmark = record["benchmark"]
            if not isinstance(benchmark, str):
                raise BenchmarkCacheError(
                    f"line {lineno} of {resolved} has non-string "
                    f"benchmark={benchmark!r}"
                )

            try:
                parsed_date = _dt.date.fromisoformat(record["date"])
            except (TypeError, ValueError) as exc:
                raise BenchmarkCacheError(
                    f"line {lineno} of {resolved} has invalid date="
                    f"{record['date']!r}: {exc}"
                ) from exc

            close_raw = record["close"]
            try:
                close = float(close_raw)
            except (TypeError, ValueError) as exc:
                raise BenchmarkCacheError(
                    f"line {lineno} of {resolved} has non-numeric "
                    f"close={close_raw!r}: {exc}"
                ) from exc

            inner = cache.setdefault(benchmark, {})
            if parsed_date in inner:
                # Fail-fast on duplicate (benchmark, date) pairs. Silent
                # last-write-wins would violate the project's blank-over-
                # wrong principle (CLAUDE.md §1).
                raise BenchmarkCacheError(
                    f"line {lineno} of {resolved} duplicates "
                    f"(benchmark={benchmark!r}, date={parsed_date.isoformat()}); "
                    f"prior close={inner[parsed_date]} new close={close}"
                )
            inner[parsed_date] = close

    missing = [name for name in _REQUIRED_BENCHMARKS if name not in cache]
    if missing:
        raise BenchmarkCacheError(
            f"benchmark cache {resolved} is missing required benchmark(s): "
            f"{', '.join(missing)}"
        )

    return cache


def get_benchmark_close(
    cache: dict[str, dict[_dt.date, float]],
    benchmark: str,
    target_date: _dt.date,
    *,
    max_lookahead_days: int = _DEFAULT_MAX_LOOKAHEAD_DAYS,
) -> float | None:
    """Look up the close price for ``(benchmark, target_date)``.

    Parameters
    ----------
    cache:
        Lookup table returned by :func:`load_benchmark_cache`.
    benchmark:
        One of the cached benchmark names (typically
        ``"SPY"``/``"QQQ"``/``"KOSPI"``). Unknown names raise
        :class:`BenchmarkCacheError` rather than returning ``None`` —
        a missing benchmark is a programming error, not data absence.
    target_date:
        The date to look up. If the date is missing from the cache
        (weekend / holiday / past last cached day), the function walks
        forward one day at a time up to ``max_lookahead_days`` looking
        for the next available close.
    max_lookahead_days:
        Inclusive upper bound on the forward walk in days. Defaults to
        5 — long enough to cover a Friday → Tuesday Memorial-Day-style
        gap, short enough that a query well past the cached window
        returns ``None`` rather than silently scanning forever.

    Returns
    -------
    float | None
        The close price as a float, or ``None`` if no close was found
        within the lookahead window.

    Raises
    ------
    BenchmarkCacheError
        ``benchmark`` is not present in ``cache``.
    """
    if benchmark not in cache:
        raise BenchmarkCacheError(
            f"unknown benchmark {benchmark!r}; "
            f"cache contains: {sorted(cache.keys())}"
        )
    if max_lookahead_days < 0:
        raise BenchmarkCacheError(
            f"max_lookahead_days must be >= 0, got {max_lookahead_days}"
        )

    series = cache[benchmark]
    for offset in range(max_lookahead_days + 1):
        candidate = target_date + _dt.timedelta(days=offset)
        if candidate in series:
            return series[candidate]
    return None


def select_benchmark(
    market: Literal["US", "KR"],
    ticker: str | None = None,
    *,
    prefer_qqq: bool = False,
) -> str:
    """Pick the appropriate benchmark name for a market/ticker pair.

    Parameters
    ----------
    market:
        ``"US"`` or ``"KR"``.
    ticker:
        Reserved for a future heuristic (e.g. routing tech-heavy US
        tickers to QQQ automatically). Currently ignored.
    prefer_qqq:
        Only consulted for ``market == "US"``. When ``True``, returns
        ``"QQQ"`` instead of the default ``"SPY"``.

    Returns
    -------
    str
        ``"KOSPI"`` for KR, ``"QQQ"`` for US with ``prefer_qqq=True``,
        otherwise ``"SPY"``.
    """
    del ticker  # reserved for future heuristic — currently unused
    if market == "KR":
        return "KOSPI"
    if market == "US":
        return "QQQ" if prefer_qqq else "SPY"
    raise BenchmarkCacheError(
        f"unsupported market {market!r}; expected 'US' or 'KR'"
    )


__all__ = [
    "BenchmarkCacheError",
    "get_benchmark_close",
    "load_benchmark_cache",
    "select_benchmark",
]
