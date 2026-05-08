#!/usr/bin/env python3
"""Benchmark price cache builder for the backtest harness (Task 4.1).

Fetches daily close prices for the three reference benchmarks used by
the backtest harness — ``SPY`` (US broad market), ``QQQ`` (US tech),
and ``KOSPI`` (Korean broad market, yfinance ticker ``^KS11``) — over
the requested date window, forward-fills missing calendar days so that
weekend/holiday gaps don't break a JOIN against ticker-level outcomes,
and writes the result as JSONL.

The output is consumed by :mod:`tools.backtest.benchmark_cache` and
ultimately by ``OutcomeComputer`` (Task 4.2) when it computes excess
returns.

Output schema
-------------

One JSON object per line, with three fields::

    {"date": "YYYY-MM-DD", "benchmark": "SPY", "close": 580.12}

``benchmark`` is the friendly alias (``SPY`` / ``QQQ`` / ``KOSPI``)
rather than the yfinance ticker. The file is sorted by
``(benchmark, date)`` so a manual ``head`` / ``tail`` is meaningful.

Usage
-----

::

    python evals/backtest/scripts/cache-benchmarks.py \\
        --start 2024-01-01 \\
        --end 2024-12-31 \\
        --output evals/backtest/data/benchmark-prices.jsonl

Exit codes
----------
- ``0`` — success (file written atomically).
- ``1`` — yfinance / network error during fetch.
- ``2`` — argparse or input validation error (bad date format, end in
  the future, end < start).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import pathlib
import sys
from collections.abc import Sequence

# Friendly alias → yfinance ticker mapping. KOSPI is ^KS11 on yfinance.
_BENCHMARKS: tuple[tuple[str, str], ...] = (
    ("SPY", "SPY"),
    ("QQQ", "QQQ"),
    ("KOSPI", "^KS11"),
)


def _parse_iso_date(value: str) -> _dt.date:
    """Parse a strict ``YYYY-MM-DD`` date.

    Raises ``argparse.ArgumentTypeError`` so argparse exits 2 on
    deviation (wrong separator, wrong field widths, invalid calendar
    date).
    """
    try:
        parsed = _dt.datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"date must be YYYY-MM-DD (got {value!r}): {exc}"
        ) from exc
    return parsed


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cache-benchmarks",
        description=(
            "Fetch daily close prices for SPY, QQQ, and KOSPI (^KS11) "
            "from yfinance, forward-fill missing dates, and write the "
            "result as JSONL for the backtest harness."
        ),
    )
    parser.add_argument(
        "--start",
        required=True,
        type=_parse_iso_date,
        help="Earliest date to fetch (YYYY-MM-DD, inclusive).",
    )
    parser.add_argument(
        "--end",
        required=True,
        type=_parse_iso_date,
        help="Latest date to fetch (YYYY-MM-DD, inclusive).",
    )
    parser.add_argument(
        "--output",
        required=True,
        type=pathlib.Path,
        help=(
            "Output JSONL path. Suggested location: "
            "evals/backtest/data/benchmark-prices.jsonl"
        ),
    )
    return parser


def _validate_window(start: _dt.date, end: _dt.date) -> None:
    """Reject non-sensical windows — end < start or end in the future."""
    today = _dt.date.today()
    if end > today:
        raise SystemExit(
            f"--end {end.isoformat()} is in the future "
            f"(today is {today.isoformat()}); historical data only.",
        )
    if end < start:
        raise SystemExit(
            f"--end {end.isoformat()} must be >= --start {start.isoformat()}",
        )


def _fetch_benchmark_series(
    yf_ticker: str,
    start: _dt.date,
    end: _dt.date,
):
    """Fetch the daily close column for a single yfinance ticker.

    ``yfinance.Ticker(symbol).history`` treats ``end`` as exclusive, so
    we add one day to make our CLI semantics inclusive.
    """
    import yfinance as yf  # local import keeps argparse-only paths fast

    history = yf.Ticker(yf_ticker).history(
        start=start.isoformat(),
        end=(end + _dt.timedelta(days=1)).isoformat(),
        interval="1d",
        auto_adjust=False,
    )
    if history is None or history.empty:
        raise RuntimeError(
            f"yfinance returned empty history for {yf_ticker} "
            f"({start.isoformat()} to {end.isoformat()})"
        )
    if "Close" not in history.columns:
        raise RuntimeError(
            f"yfinance history for {yf_ticker} missing 'Close' column"
        )
    return history["Close"]


def _build_calendar(start: _dt.date, end: _dt.date) -> list[_dt.date]:
    """All calendar dates in [start, end] inclusive."""
    span = (end - start).days + 1
    return [start + _dt.timedelta(days=i) for i in range(span)]


def _forward_fill(
    closes_by_date: dict[_dt.date, float],
    calendar: Sequence[_dt.date],
) -> dict[_dt.date, float]:
    """Forward-fill missing days using the most recent prior close.

    Days before the first observed close stay absent — there is no
    prior value to carry forward.
    """
    filled: dict[_dt.date, float] = {}
    last_close: float | None = None
    for day in calendar:
        if day in closes_by_date:
            last_close = closes_by_date[day]
            filled[day] = last_close
        elif last_close is not None:
            filled[day] = last_close
    return filled


def _atomic_write_jsonl(
    path: pathlib.Path,
    rows: Sequence[dict[str, object]],
) -> None:
    """Write ``rows`` to ``path`` atomically via a sibling .tmp file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True))
            fh.write("\n")
    os.replace(tmp, path)


def _collect_rows(
    start: _dt.date,
    end: _dt.date,
) -> list[dict[str, object]]:
    """Fetch every benchmark and return the assembled JSONL row list."""
    calendar = _build_calendar(start, end)
    rows: list[dict[str, object]] = []

    for alias, yf_ticker in _BENCHMARKS:
        series = _fetch_benchmark_series(yf_ticker, start, end)
        closes_by_date: dict[_dt.date, float] = {}
        for ts, value in series.items():
            # ``ts`` is a pandas Timestamp; convert to plain date.
            day = ts.date() if hasattr(ts, "date") else ts
            try:
                closes_by_date[day] = float(value)
            except (TypeError, ValueError):
                # NaN or unparseable value — skip; forward-fill will
                # cover it.
                continue

        filled = _forward_fill(closes_by_date, calendar)
        for day in calendar:
            if day not in filled:
                # No observation has happened yet — skip leading gap.
                continue
            rows.append(
                {
                    "date": day.isoformat(),
                    "benchmark": alias,
                    "close": round(filled[day], 4),
                }
            )

    rows.sort(key=lambda row: (row["benchmark"], row["date"]))
    return rows


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        _validate_window(args.start, args.end)
    except SystemExit as exc:
        print(str(exc), file=sys.stderr)
        return 2

    try:
        rows = _collect_rows(args.start, args.end)
    except Exception as exc:  # noqa: BLE001 — surface yfinance failure
        print(
            f"benchmark fetch failed: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 1

    try:
        _atomic_write_jsonl(args.output, rows)
    except OSError as exc:
        print(f"failed to write {args.output}: {exc}", file=sys.stderr)
        return 1

    print(
        f"wrote {len(rows)} rows to {args.output} "
        f"(window={args.start.isoformat()}..{args.end.isoformat()})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
