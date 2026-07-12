#!/usr/bin/env python3
"""
Earnings Window Classifier — Phase F.1

Classify whether a ticker is currently in a Mode E earnings window:

* ``preview`` — D-7 ~ D-1 (7 days before report through day-before)
* ``review``  — D ~ D+3   (report day through 3 days after)
* ``none``    — outside the window

Usage (CLI):
  python .claude/skills/earnings-window-detector/scripts/window-classifier.py \
    --ticker GOOGL AAPL \
    --output-dir output/runs/{run_id}/earnings-window/ \
    --today-date 2026-05-07 \
    --timeout 30

Per-ticker JSON output (written to ``--output-dir``)::

    {
      "ticker": "GOOGL",
      "today_date": "2026-05-07",
      "next_earnings_date": "2026-07-29",
      "next_earnings_confirmed": true,
      "days_until": 83,
      "window": "none",
      "override_mode": null,
      "lookup_source": "yfinance.Ticker.calendar",
      "fallback_used": false,
      "_sanitization": {
        "tool":  "tools/prompt_injection_filter.py",
        "version": "1",
        "redactions": 0,
        "findings": []
      }
    }

Window enum:
  * ``preview`` — ``-7 <= days_until <= -1`` (NOTE: days_until = earnings - today)
                    so equivalently ``1 <= days_until_calendar <= 7``
  * ``review``  — ``-3 <= days_until <= 0``
  * ``none``    — outside the union

We compute ``days_until = (earnings_date - today_date).days``:
  * ``+3``  → 3 days from now → preview
  * ``0``   → today → review
  * ``-1``  → 1 day ago  → review
  * ``-3``  → 3 days ago  → review
  * ``-4``  → 4 days ago  → none
  * ``+30`` → 30 days out → none

Design rules (CLAUDE.md §12 + §9):

* Stateless: no cache. Orchestrator (Chunk 5) decides reuse via Mode E entry policy.
* 30s per-ticker timeout via ``concurrent.futures.ThreadPoolExecutor``.
* Each ticker is independent — one failure does NOT abort siblings.
* ``yfinance.Ticker.calendar`` is the primary lookup; ``earnings_dates``
  DataFrame is the fallback. If both fail, returns window="none" with
  ``next_earnings_confirmed=False`` and ``fallback_used=True``.
* All output passes through ``tools.prompt_injection_filter`` before disk write.
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

# Make repo-root imports available when invoked as a CLI script.
_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.prompt_injection_filter import (  # noqa: E402
    SANITIZER_VERSION,
    sanitize_record,
)

try:  # yfinance is optional at import time so unit tests can inject a fake.
    import yfinance as _yf_default
except ImportError:  # pragma: no cover - exercised only in environments w/o yfinance
    _yf_default = None


# ---------------------------------------------------------------------------
# Window classification rules
# ---------------------------------------------------------------------------
#
# days_until = (earnings_date - today_date).days
#   * earnings is in the future → days_until > 0
#   * earnings is today          → days_until == 0
#   * earnings is in the past    → days_until < 0
#
# Preview window  (D-7 ~ D-1):  1 <= days_until <= 7
# Review  window  (D   ~ D+3): -3 <= days_until <= 0
# Anything else                 → "none"
PREVIEW_MIN_DAYS_AHEAD = 1
PREVIEW_MAX_DAYS_AHEAD = 7
REVIEW_MIN_DAYS_AHEAD = -3
REVIEW_MAX_DAYS_AHEAD = 0


def _classify(days_until: int) -> str:
    if PREVIEW_MIN_DAYS_AHEAD <= days_until <= PREVIEW_MAX_DAYS_AHEAD:
        return "preview"
    if REVIEW_MIN_DAYS_AHEAD <= days_until <= REVIEW_MAX_DAYS_AHEAD:
        return "review"
    return "none"


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------


def _parse_today(today_date: str | None) -> date:
    """Parse YYYY-MM-DD or default to UTC today."""
    if today_date is None or today_date == "":
        return datetime.now(timezone.utc).date()
    if isinstance(today_date, date) and not isinstance(today_date, datetime):
        return today_date
    return datetime.strptime(today_date, "%Y-%m-%d").date()


def _coerce_to_date(value: Any) -> date | None:
    """Best-effort coercion of yfinance date-ish values into a date."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    # pandas Timestamp / numpy datetime64 expose .to_pydatetime() or .date()
    for attr in ("date", "to_pydatetime"):
        method = getattr(value, attr, None)
        if callable(method):
            try:
                got = method()
            except Exception:  # noqa: BLE001
                continue
            if isinstance(got, datetime):
                return got.date()
            if isinstance(got, date):
                return got
    if isinstance(value, str):
        # Try ISO date or full ISO datetime.
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue
        try:
            return datetime.fromisoformat(value).date()
        except ValueError:
            return None
    return None


# ---------------------------------------------------------------------------
# yfinance lookups
# ---------------------------------------------------------------------------


def _extract_calendar_date(calendar: Any) -> date | None:
    """yfinance.Ticker.calendar can be either:

    * dict-like with key "Earnings Date" → list[date|datetime] (newer yfinance)
    * pandas DataFrame with index "Earnings Date" (older yfinance)
    * None / empty
    """
    if calendar is None:
        return None
    # dict-like
    if hasattr(calendar, "get"):
        raw = calendar.get("Earnings Date")
        if raw is None:
            return None
        # Could be list/tuple of dates, or single date.
        if isinstance(raw, (list, tuple)):
            for item in raw:
                d = _coerce_to_date(item)
                if d is not None:
                    return d
            return None
        return _coerce_to_date(raw)
    # DataFrame fallback (older yfinance)
    try:
        loc = calendar.loc["Earnings Date"]
    except Exception:  # noqa: BLE001
        return None
    # loc might be a Series of values
    if hasattr(loc, "iloc"):
        try:
            return _coerce_to_date(loc.iloc[0])
        except Exception:  # noqa: BLE001
            return None
    return _coerce_to_date(loc)


def _next_future_date(dates: Iterable[Any], today: date) -> date | None:
    """Return the soonest date >= today, or None if none qualify."""
    candidates: list[date] = []
    for raw in dates:
        d = _coerce_to_date(raw)
        if d is None:
            continue
        if d >= today:
            candidates.append(d)
    if not candidates:
        return None
    return min(candidates)


def _extract_earnings_dates_df_date(df: Any, today: date) -> date | None:
    """Pull the next future date from the earnings_dates DataFrame.

    The real object is a pandas DataFrame whose ``.index`` is a
    ``DatetimeIndex`` of report dates. We only iterate the index, so this
    works with our test stub too.
    """
    if df is None:
        return None
    if getattr(df, "empty", False):
        return None
    index = getattr(df, "index", None)
    if index is None:
        return None
    return _next_future_date(index, today)


def _lookup_calendar(yf_module: Any, ticker: str) -> tuple[date | None, str | None]:
    """Try ``Ticker.calendar`` first; return (date, error_msg)."""
    try:
        ticker_obj = yf_module.Ticker(ticker)
        calendar = ticker_obj.calendar
    except BaseException as exc:  # noqa: BLE001
        return None, f"calendar: {type(exc).__name__}: {exc}"
    d = _extract_calendar_date(calendar)
    return d, None


def _lookup_earnings_dates(
    yf_module: Any, ticker: str, today: date
) -> tuple[date | None, str | None]:
    """Try ``Ticker.earnings_dates`` DataFrame; return (date, error_msg)."""
    try:
        ticker_obj = yf_module.Ticker(ticker)
        df = ticker_obj.earnings_dates
    except BaseException as exc:  # noqa: BLE001
        return None, f"earnings_dates: {type(exc).__name__}: {exc}"
    d = _extract_earnings_dates_df_date(df, today)
    return d, None


def _lookup_next_earnings(
    yf_module: Any, ticker: str, today: date, timeout: int
) -> tuple[date | None, str, list[str]]:
    """Run both lookups under a single thread-pool timeout.

    Returns ``(earnings_date_or_none, lookup_source, error_messages)``.
    ``lookup_source`` is one of:
      * "yfinance.Ticker.calendar"
      * "yfinance.Ticker.earnings_dates"
      * "none" (both failed or both empty)
    """
    errors: list[str] = []

    def _do_lookup() -> tuple[date | None, str]:
        d, err = _lookup_calendar(yf_module, ticker)
        if err:
            errors.append(err)
        if d is not None:
            return d, "yfinance.Ticker.calendar"
        d, err = _lookup_earnings_dates(yf_module, ticker, today)
        if err:
            errors.append(err)
        if d is not None:
            return d, "yfinance.Ticker.earnings_dates"
        return None, "none"

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(_do_lookup)
        try:
            return (*future.result(timeout=timeout), errors)
        except FuturesTimeoutError as exc:
            future.cancel()
            errors.append(f"timeout after {timeout}s: {exc}")
            return None, "none", errors


# ---------------------------------------------------------------------------
# Payload construction
# ---------------------------------------------------------------------------


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _isoformat_dt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _wrap_with_sanitization(payload: dict[str, Any]) -> dict[str, Any]:
    """Sanitize the payload's strings and stamp the canonical block."""
    payload.pop("_sanitization", None)
    cleaned, findings = sanitize_record(payload)
    cleaned["_sanitization"] = {
        "tool": "tools/prompt_injection_filter.py",
        "version": SANITIZER_VERSION,
        "timestamp": _isoformat_dt(_utc_now()),
        "redactions": len(findings),
        "findings": findings,
    }
    return cleaned


def _build_payload(
    ticker: str,
    today: date,
    earnings_date: date | None,
    lookup_source: str,
    fallback_used: bool,
    errors: list[str],
) -> dict[str, Any]:
    if earnings_date is None:
        days_until: int | None = None
        window = "none"
        confirmed = False
        next_earnings_iso: str | None = None
    else:
        days_until = (earnings_date - today).days
        window = _classify(days_until)
        confirmed = True
        next_earnings_iso = earnings_date.isoformat()
    date_precision = (
        "estimated"
        if earnings_date is not None
        and lookup_source in {
            "yfinance.Ticker.calendar",
            "yfinance.Ticker.earnings_dates",
        }
        else None
    )

    payload: dict[str, Any] = {
        "ticker": ticker,
        "today_date": today.isoformat(),
        "next_earnings_date": next_earnings_iso,
        "next_earnings_confirmed": confirmed,
        "date_precision": date_precision,
        "days_until": days_until,
        "window": window,
        "override_mode": None,
        "lookup_source": lookup_source,
        "fallback_used": fallback_used,
    }
    if errors:
        payload["lookup_errors"] = list(errors)
    return payload


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def classify_window(
    ticker: str,
    today_date: str | None = None,
    yf_module: Any | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    """Classify the earnings window for one ticker.

    Per-ticker errors never raise: yfinance failures degrade to
    ``window="none"`` + ``next_earnings_confirmed=False`` + ``fallback_used=True``.
    """
    ticker_upper = (ticker or "").strip().upper()
    today = _parse_today(today_date)
    yf_to_use = yf_module if yf_module is not None else _yf_default

    if yf_to_use is None:
        payload = _build_payload(
            ticker=ticker_upper,
            today=today,
            earnings_date=None,
            lookup_source="none",
            fallback_used=True,
            errors=["yfinance is not installed"],
        )
        return _wrap_with_sanitization(payload)

    try:
        earnings_date, lookup_source, errors = _lookup_next_earnings(
            yf_to_use, ticker_upper, today, timeout
        )
    except BaseException as exc:  # noqa: BLE001 — defensive belt-and-suspenders
        earnings_date = None
        lookup_source = "none"
        errors = [f"unexpected: {type(exc).__name__}: {exc}"]

    fallback_used = earnings_date is None
    payload = _build_payload(
        ticker=ticker_upper,
        today=today,
        earnings_date=earnings_date,
        lookup_source=lookup_source,
        fallback_used=fallback_used,
        errors=errors,
    )
    return _wrap_with_sanitization(payload)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    tmp.replace(path)


def classify_windows(
    tickers: Iterable[str],
    output_dir: Path | str,
    today_date: str | None = None,
    yf_module: Any | None = None,
    timeout: int = 30,
) -> list[dict[str, Any]]:
    """Classify multiple tickers; one bad ticker does not abort siblings.

    Writes ``{TICKER}.json`` per ticker into ``output_dir`` (atomic).
    Returns a list of result dicts in input order.
    """
    output_dir_path = Path(output_dir)
    output_dir_path.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    for raw in tickers:
        ticker = (raw or "").strip()
        if not ticker:
            continue
        try:
            record = classify_window(
                ticker=ticker,
                today_date=today_date,
                yf_module=yf_module,
                timeout=timeout,
            )
        except BaseException as exc:  # noqa: BLE001
            record = _wrap_with_sanitization(
                _build_payload(
                    ticker=ticker.upper(),
                    today=_parse_today(today_date),
                    earnings_date=None,
                    lookup_source="none",
                    fallback_used=True,
                    errors=[f"defensive: {type(exc).__name__}: {exc}"],
                )
            )
        try:
            _write_json(
                output_dir_path / f"{record['ticker']}.json", record
            )
        except OSError:
            pass
        results.append(record)
    return results


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Earnings window classifier (Mode E auto-detect). "
            "Classifies preview (D-7..D-1), review (D..D+3), or none."
        )
    )
    parser.add_argument(
        "--ticker",
        nargs="+",
        required=True,
        help="One or more ticker symbols (e.g. GOOGL AAPL MSFT)",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Output directory for per-ticker JSON files",
    )
    parser.add_argument(
        "--today-date",
        default=None,
        help="Anchor date YYYY-MM-DD (default: UTC today)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Per-ticker timeout in seconds (default: 30)",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir).expanduser()
    if not output_dir.is_absolute():
        output_dir = Path.cwd() / output_dir

    results = classify_windows(
        tickers=args.ticker,
        output_dir=output_dir,
        today_date=args.today_date,
        timeout=args.timeout,
    )

    summary = {
        "tickers_requested": list(args.ticker),
        "today_date": (args.today_date or _parse_today(None).isoformat()),
        "by_ticker": {
            r["ticker"]: {
                "window": r["window"],
                "days_until": r["days_until"],
                "next_earnings_date": r["next_earnings_date"],
                "next_earnings_confirmed": r["next_earnings_confirmed"],
                "lookup_source": r["lookup_source"],
                "fallback_used": r["fallback_used"],
            }
            for r in results
        },
        "output_dir": str(output_dir),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    # Exit 0 if at least one ticker was classified (success or graceful none),
    # 1 if input was empty.
    return 0 if results else 1


if __name__ == "__main__":
    raise SystemExit(main())
