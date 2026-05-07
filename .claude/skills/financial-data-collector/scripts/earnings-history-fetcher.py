#!/usr/bin/env python3
"""
Earnings History Fetcher — Phase F.2 (Mode E Preview + Review)

최근 N분기(기본 8) 실적 actual / consensus / surprise + 발표 다음 거래일
주가 반응(%) 데이터를 yfinance ``earnings_history``에서 수집.

* Mode E Preview — 과거 hit-rate가 ER playbook의 base rate.
* Mode E Review  — 이번 분기 surprise를 어제까지의 8분기 분포와 비교.

Usage (CLI):
  python .claude/skills/financial-data-collector/scripts/earnings-history-fetcher.py \
    --tickers GOOGL AAPL \
    --output-dir output/runs/{run_id}/earnings-history/ \
    --quarters 8 \
    --timeout 30

Per-ticker JSON output (written to ``--output-dir``)::

    {
      "ticker": "GOOGL",
      "collection_timestamp": "2026-05-07T12:00:00Z",
      "quarters": [
        {
          "quarter": "Q1 2026",
          "report_date": "2026-04-29",
          "actual_eps": 5.11,
          "consensus_eps": 2.63,
          "surprise_pct": 94.3,
          "beat": true,
          "stock_reaction_1d_pct": 6.5
        },
        ...
      ],
      "summary": {
        "quarters_count": 8,
        "hit_rate": 0.875,
        "avg_surprise_pct": 12.4,
        "avg_reaction_1d_pct": 3.2
      },
      "_sanitization": {
        "tool":  "tools/prompt_injection_filter.py",
        "version": "1",
        "redactions": 0,
        "findings": []
      }
    }

설계 규칙 (CLAUDE.md §12 + §9):

* 30s per-ticker timeout via ``concurrent.futures.ThreadPoolExecutor``.
* Per-ticker error isolation — 한 티커 실패가 다른 티커를 abort 하지 않음.
* 실적 row 단위로 missing field가 있어도 stripping이 아니라 ``None`` 보존,
  summary 계산에서만 제외 → 빈칸 > 틀린 숫자 (CLAUDE.md §1).
* 모든 fetched string은 ``tools.prompt_injection_filter`` 통과.
* Stateless.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import date, datetime, timedelta, timezone
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
except ImportError:  # pragma: no cover
    _yf_default = None


DEFAULT_QUARTERS = 8


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _isoformat(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if hasattr(value, "item") and not isinstance(value, (bytes, bytearray, str)):
        try:
            value = value.item()
        except Exception:  # noqa: BLE001
            pass
    if isinstance(value, (int, float)):
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return None
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped or stripped.lower() in {"nan", "none", "-"}:
            return None
        try:
            return float(stripped.replace(",", ""))
        except ValueError:
            return None
    return None


def _round(value: float | int | None, places: int = 2) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), places)
    except (TypeError, ValueError):
        return None


def _coerce_to_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
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


def _quarter_label(d: date) -> str:
    """Approximate calendar-quarter label from a report date.

    Note: yfinance reports the *fiscal* quarter; we use the reporting date's
    calendar quarter as a stable label. Downstream Mode E template renderer
    can re-label using fiscal mapping if needed.
    """
    q = (d.month - 1) // 3 + 1
    return f"Q{q} {d.year}"


def _row_get(row: Any, key: str) -> Any:
    if row is None:
        return None
    if isinstance(row, dict):
        return row.get(key)
    try:
        if key in row:
            return row[key]
    except Exception:  # noqa: BLE001
        pass
    return getattr(row, key, None)


def _wrap_with_sanitization(payload: dict[str, Any]) -> dict[str, Any]:
    payload.pop("_sanitization", None)
    cleaned, findings = sanitize_record(payload)
    cleaned["_sanitization"] = {
        "tool": "tools/prompt_injection_filter.py",
        "version": SANITIZER_VERSION,
        "timestamp": _isoformat(_utc_now()),
        "redactions": len(findings),
        "findings": findings,
    }
    return cleaned


# ---------------------------------------------------------------------------
# Iteration over earnings-history rows (DataFrame OR list[dict])
# ---------------------------------------------------------------------------


def _iter_history_rows(df: Any) -> list[tuple[date | None, Any]]:
    """Return [(report_date, row), ...] from yfinance ``earnings_history``.

    Supports:
    * pandas DataFrame with DatetimeIndex (real yfinance object).
    * Test stubs exposing ``iterrows()`` yielding (date, row).
    * Plain list[dict] with a ``report_date`` key.
    """
    if df is None:
        return []
    # Empty short-circuit
    if getattr(df, "empty", False):
        return []
    rows: list[tuple[date | None, Any]] = []
    iterrows = getattr(df, "iterrows", None)
    if callable(iterrows):
        try:
            for idx, row in iterrows():
                rows.append((_coerce_to_date(idx), row))
        except Exception:  # noqa: BLE001
            return []
        return rows
    if isinstance(df, list):
        for row in df:
            rows.append((_coerce_to_date(_row_get(row, "report_date")), row))
        return rows
    # Best-effort fallback
    try:
        for row in list(df):
            rows.append((_coerce_to_date(_row_get(row, "report_date")), row))
    except TypeError:
        return []
    return rows


# ---------------------------------------------------------------------------
# 1-day stock reaction
# ---------------------------------------------------------------------------


def _get_close_on_or_before(price_history: Any, target: date) -> float | None:
    """Best-effort price lookup for ``target`` (or earlier trading day)."""
    if price_history is None:
        return None
    # Test-stub helpers
    helper = getattr(price_history, "get_close_on_or_before", None)
    if callable(helper):
        try:
            return _as_float(helper(target))
        except Exception:  # noqa: BLE001
            pass
    # pandas-style .loc + .index
    index = getattr(price_history, "index", None)
    if index is None:
        return None
    closes = getattr(price_history, "_closes", None)
    if closes is None:
        # Try real-pandas fallback: iterate index + ['Close']
        try:
            for raw in reversed(list(index)):
                d = _coerce_to_date(raw)
                if d is not None and d <= target:
                    try:
                        v = price_history.loc[raw, "Close"]
                    except Exception:  # noqa: BLE001
                        v = None
                    f = _as_float(v)
                    if f is not None:
                        return f
            return None
        except Exception:  # noqa: BLE001
            return None
    # Test-stub dict fallback
    sorted_dates = sorted(closes.keys())
    for d in reversed(sorted_dates):
        if d <= target:
            return _as_float(closes[d])
    return None


def _get_close_on_or_after(price_history: Any, target: date) -> float | None:
    if price_history is None:
        return None
    helper = getattr(price_history, "get_close_on_or_after", None)
    if callable(helper):
        try:
            return _as_float(helper(target))
        except Exception:  # noqa: BLE001
            pass
    index = getattr(price_history, "index", None)
    if index is None:
        return None
    closes = getattr(price_history, "_closes", None)
    if closes is None:
        try:
            for raw in list(index):
                d = _coerce_to_date(raw)
                if d is not None and d >= target:
                    try:
                        v = price_history.loc[raw, "Close"]
                    except Exception:  # noqa: BLE001
                        v = None
                    f = _as_float(v)
                    if f is not None:
                        return f
            return None
        except Exception:  # noqa: BLE001
            return None
    sorted_dates = sorted(closes.keys())
    for d in sorted_dates:
        if d >= target:
            return _as_float(closes[d])
    return None


def _stock_reaction_1d_pct(
    price_history: Any, report_date: date | None
) -> float | None:
    """1-day reaction = (close[D+1] - close[D]) / close[D] * 100.

    Falls back to closest available trading days.
    """
    if report_date is None:
        return None
    base = _get_close_on_or_before(price_history, report_date)
    next_day = _get_close_on_or_after(price_history, report_date + timedelta(days=1))
    if base is None or next_day is None or base == 0:
        return None
    return _round((next_day - base) / base * 100, 2)


# ---------------------------------------------------------------------------
# Per-quarter normalization
# ---------------------------------------------------------------------------


def _normalize_quarter(
    report_date: date | None,
    raw_row: Any,
    price_history: Any,
) -> dict[str, Any]:
    actual = _as_float(_row_get(raw_row, "epsActual"))
    estimate = _as_float(_row_get(raw_row, "epsEstimate"))

    if actual is None or estimate is None:
        surprise_pct: float | None = None
        beat: bool | None = None
    else:
        if estimate == 0:
            # Edge: zero estimate — surprise undefined.
            surprise_pct = None
            beat = actual > 0
        else:
            diff = actual - estimate
            surprise_pct = _round(diff / abs(estimate) * 100, 2)
            beat = actual > estimate

    reaction = _stock_reaction_1d_pct(price_history, report_date)

    return {
        "quarter": _quarter_label(report_date) if report_date else None,
        "report_date": report_date.isoformat() if report_date else None,
        "actual_eps": _round(actual, 4) if actual is not None else None,
        "consensus_eps": _round(estimate, 4) if estimate is not None else None,
        "surprise_pct": surprise_pct,
        "beat": beat,
        "stock_reaction_1d_pct": reaction,
    }


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


def _summarize(quarters: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(quarters)
    if total == 0:
        return {
            "quarters_count": 0,
            "hit_rate": None,
            "avg_surprise_pct": None,
            "avg_reaction_1d_pct": None,
        }

    surprise_vals = [
        q["surprise_pct"] for q in quarters if q.get("surprise_pct") is not None
    ]
    reaction_vals = [
        q["stock_reaction_1d_pct"]
        for q in quarters
        if q.get("stock_reaction_1d_pct") is not None
    ]
    beat_vals = [q["beat"] for q in quarters if q.get("beat") is not None]

    hit_rate = (
        round(sum(1 for b in beat_vals if b) / len(beat_vals), 4)
        if beat_vals
        else None
    )
    avg_surprise = (
        round(sum(surprise_vals) / len(surprise_vals), 2)
        if surprise_vals
        else None
    )
    avg_reaction = (
        round(sum(reaction_vals) / len(reaction_vals), 2)
        if reaction_vals
        else None
    )

    return {
        "quarters_count": total,
        "hit_rate": hit_rate,
        "avg_surprise_pct": avg_surprise,
        "avg_reaction_1d_pct": avg_reaction,
    }


# ---------------------------------------------------------------------------
# Per-ticker fetch
# ---------------------------------------------------------------------------


def _empty_payload(ticker: str) -> dict[str, Any]:
    return {
        "ticker": ticker,
        "collection_timestamp": _isoformat(_utc_now()),
        "quarters": [],
        "summary": _summarize([]),
    }


def _fetch_history_inner(
    yf_module: Any, ticker: str, quarters: int
) -> dict[str, Any]:
    ticker_obj = yf_module.Ticker(ticker)

    # 1) Earnings history
    try:
        eh = ticker_obj.earnings_history
    except BaseException as exc:  # noqa: BLE001
        payload = _empty_payload(ticker)
        payload["error"] = (
            f"earnings_history failed: {type(exc).__name__}: {exc}"
        )
        return payload

    raw_rows = _iter_history_rows(eh)
    if not raw_rows:
        return _empty_payload(ticker)

    # Sort newest-first by report_date (None at the end).
    raw_rows.sort(
        key=lambda x: x[0] if x[0] is not None else date.min, reverse=True
    )

    # Limit to N most-recent quarters.
    raw_rows = raw_rows[: max(int(quarters), 0)]
    if not raw_rows:
        return _empty_payload(ticker)

    # 2) Stock-price history covering the report-date span (+1d).
    earliest = min(d for d, _ in raw_rows if d is not None)
    latest = max(d for d, _ in raw_rows if d is not None)
    start = earliest - timedelta(days=5)
    end = latest + timedelta(days=10)

    try:
        price_history = ticker_obj.history(
            start=start.isoformat(), end=end.isoformat()
        )
    except BaseException:  # noqa: BLE001
        price_history = None

    # 3) Normalize each quarter.
    quarters_out: list[dict[str, Any]] = []
    for report_date, raw_row in raw_rows:
        quarters_out.append(
            _normalize_quarter(report_date, raw_row, price_history)
        )

    payload: dict[str, Any] = {
        "ticker": ticker,
        "collection_timestamp": _isoformat(_utc_now()),
        "quarters": quarters_out,
        "summary": _summarize(quarters_out),
    }
    return payload


def fetch_earnings_history(
    ticker: str,
    yf_module: Any | None = None,
    timeout: int = 30,
    quarters: int = DEFAULT_QUARTERS,
) -> dict[str, Any]:
    """Fetch earnings history for one ticker (graceful failure on yfinance error)."""
    ticker_upper = (ticker or "").strip().upper()
    yf_to_use = yf_module if yf_module is not None else _yf_default

    if yf_to_use is None:
        payload = _empty_payload(ticker_upper)
        payload["error"] = "yfinance is not installed"
        return _wrap_with_sanitization(payload)

    def _call() -> dict[str, Any]:
        return _fetch_history_inner(yf_to_use, ticker_upper, quarters)

    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_call)
            try:
                payload = future.result(timeout=timeout)
            except FuturesTimeoutError as exc:
                future.cancel()
                payload = _empty_payload(ticker_upper)
                payload["error"] = f"timeout after {timeout}s: {exc}"
    except BaseException as exc:  # noqa: BLE001 — defensive belt-and-suspenders
        payload = _empty_payload(ticker_upper)
        payload["error"] = f"unexpected: {type(exc).__name__}: {exc}"

    return _wrap_with_sanitization(payload)


# ---------------------------------------------------------------------------
# Multi-ticker / disk I/O
# ---------------------------------------------------------------------------


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    tmp.replace(path)


def fetch_earnings_history_many(
    tickers: Iterable[str],
    output_dir: Path | str,
    yf_module: Any | None = None,
    timeout: int = 30,
    quarters: int = DEFAULT_QUARTERS,
) -> list[dict[str, Any]]:
    """Fetch earnings history for many tickers.

    Writes ``{TICKER}.json`` per ticker into ``output_dir`` (atomic write).
    Per-ticker failures are isolated.
    """
    output_dir_path = Path(output_dir)
    output_dir_path.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    for raw in tickers:
        ticker = (raw or "").strip()
        if not ticker:
            continue
        try:
            record = fetch_earnings_history(
                ticker=ticker,
                yf_module=yf_module,
                timeout=timeout,
                quarters=quarters,
            )
        except BaseException as exc:  # noqa: BLE001 — defensive
            payload = _empty_payload(ticker.upper())
            payload["error"] = f"defensive: {type(exc).__name__}: {exc}"
            record = _wrap_with_sanitization(payload)
        try:
            _write_json(output_dir_path / f"{record['ticker']}.json", record)
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
            "Mode E earnings-history fetcher (last N quarters actual / "
            "consensus / surprise + 1-day stock reaction)."
        )
    )
    parser.add_argument(
        "--tickers",
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
        "--quarters",
        type=int,
        default=DEFAULT_QUARTERS,
        help=f"Number of most-recent quarters to keep (default: {DEFAULT_QUARTERS})",
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

    results = fetch_earnings_history_many(
        tickers=args.tickers,
        output_dir=output_dir,
        timeout=args.timeout,
        quarters=args.quarters,
    )

    summary = {
        "tickers_requested": list(args.tickers),
        "quarters_requested": args.quarters,
        "by_ticker": {
            r["ticker"]: {
                "quarters_count": r["summary"]["quarters_count"],
                "hit_rate": r["summary"]["hit_rate"],
                "avg_surprise_pct": r["summary"]["avg_surprise_pct"],
                "avg_reaction_1d_pct": r["summary"]["avg_reaction_1d_pct"],
                "error": r.get("error"),
            }
            for r in results
        },
        "output_dir": str(output_dir),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    return 0 if results else 1


if __name__ == "__main__":
    raise SystemExit(main())
