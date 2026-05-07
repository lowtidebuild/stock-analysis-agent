#!/usr/bin/env python3
"""
Options Fetcher — Phase F.2 (Mode E Preview)

ATM 스트래들 가격과 implied 1-day move %를 yfinance ``option_chain``에서
산출하는 lightweight fetcher. Mode E Preview에서 hero 헤더에 표시되는
implied move 숫자의 단일 소스이다.

Usage (CLI):
  python .claude/skills/financial-data-collector/scripts/options-fetcher.py \
    --tickers GOOGL AAPL \
    --output-dir output/runs/{run_id}/options/ \
    --today-date 2026-05-07 \
    --timeout 30

Per-ticker JSON output (written to ``--output-dir``)::

    {
      "ticker": "GOOGL",
      "as_of": "2026-05-07T12:00:00Z",
      "spot_price": 388.43,
      "nearest_expiry": "2026-05-09",
      "atm_strike": 388,
      "atm_call_price": 4.20,
      "atm_put_price": 4.05,
      "atm_straddle_price": 8.25,
      "implied_move_pct": 2.12,
      "iv_percentile": null,
      "expiry_offset_days": 2,
      "_sanitization": {
        "tool":  "tools/prompt_injection_filter.py",
        "version": "1",
        "redactions": 0,
        "findings": []
      }
    }

설계 규칙 (CLAUDE.md §12 + §9, OD-F2):

* yfinance options-chain 실패는 **hard fail이 아니다** (OD-F2):
  ``status="unavailable"`` + null 필드 + ``error`` 메시지로 graceful 반환.
* 30s per-ticker timeout via ``concurrent.futures.ThreadPoolExecutor``.
* Per-ticker error isolation — 한 티커 실패가 다른 티커를 abort 하지 않음.
* 모든 fetched string은 ``tools.prompt_injection_filter`` 통과 후 disk 작성.
* Stateless (orchestrator가 재진입 캐싱 책임).
"""

from __future__ import annotations

import argparse
import json
import math
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
# Helpers
# ---------------------------------------------------------------------------


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _isoformat(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_today(today_date: str | None) -> date:
    """Parse YYYY-MM-DD or default to UTC today."""
    if today_date is None or today_date == "":
        return _utc_now().date()
    if isinstance(today_date, date) and not isinstance(today_date, datetime):
        return today_date
    return datetime.strptime(today_date, "%Y-%m-%d").date()


def _as_float(value: Any) -> float | int | None:
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
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped or stripped.lower() in {"nan", "none", "-"}:
            return None
        try:
            return float(stripped.replace(",", ""))
        except ValueError:
            return None
    return None


def _round(value: float | int | None, places: int = 2) -> float | int | None:
    if value is None:
        return None
    try:
        return round(float(value), places)
    except (TypeError, ValueError):
        return None


def _row_get(row: Any, key: str) -> Any:
    """Read a column from a dict-like row OR a pandas Series."""
    if row is None:
        return None
    if isinstance(row, dict):
        return row.get(key)
    # pandas Series style
    try:
        if key in row:
            return row[key]
    except Exception:  # noqa: BLE001
        pass
    return getattr(row, key, None)


def _iter_rows(table: Any) -> Iterable[Any]:
    """Iterate option-chain rows, accepting list[dict] and pandas DataFrame."""
    if table is None:
        return []
    # pandas DataFrame: prefer iterrows()
    iterrows = getattr(table, "iterrows", None)
    if callable(iterrows):
        try:
            return [row for _, row in iterrows()]
        except Exception:  # noqa: BLE001
            return []
    if isinstance(table, list):
        return table
    # Best-effort fallback: iterate if iterable.
    try:
        return list(table)
    except TypeError:
        return []


def _option_price(row: Any) -> float | None:
    """Return last_price, falling back to mid (bid+ask)/2 when sensible."""
    last = _as_float(_row_get(row, "lastPrice"))
    if last is not None and last > 0:
        return last
    bid = _as_float(_row_get(row, "bid"))
    ask = _as_float(_row_get(row, "ask"))
    if bid is not None and ask is not None and bid > 0 and ask > 0:
        return (bid + ask) / 2
    if last is not None:
        return last  # could be 0.0 — surface it rather than null
    return None


def _pick_atm_row(rows: list[Any], spot: float) -> Any | None:
    """Return the row whose strike is closest to ``spot``."""
    best = None
    best_dist: float | None = None
    for row in rows:
        strike = _as_float(_row_get(row, "strike"))
        if strike is None:
            continue
        dist = abs(strike - spot)
        if best_dist is None or dist < best_dist:
            best_dist = dist
            best = row
    return best


def _strike_of(row: Any) -> float | int | None:
    val = _as_float(_row_get(row, "strike"))
    if val is None:
        return None
    if isinstance(val, float) and val.is_integer():
        return int(val)
    return val


def _spot_from_ticker(ticker_obj: Any) -> float | None:
    """Try fast_info first, then info regularMarketPrice / currentPrice."""
    fast_info = getattr(ticker_obj, "fast_info", None)
    if fast_info is not None:
        # Could be a dict-like or an attribute holder.
        if hasattr(fast_info, "get"):
            try:
                v = fast_info.get("last_price")
            except Exception:  # noqa: BLE001
                v = None
            if v is not None:
                f = _as_float(v)
                if f is not None:
                    return f
        attr = getattr(fast_info, "last_price", None)
        if attr is not None:
            f = _as_float(attr)
            if f is not None:
                return f
    info = getattr(ticker_obj, "info", None)
    if isinstance(info, dict):
        for key in ("regularMarketPrice", "currentPrice", "previousClose"):
            f = _as_float(info.get(key))
            if f is not None:
                return f
    return None


def _parse_iso_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue
    return None


def _pick_nearest_expiry(
    expiries: Iterable[Any], today: date
) -> tuple[str | None, int | None]:
    """Pick the nearest expiry on or after ``today``.

    Returns (expiry_str, days_offset) or (None, None) if no future expiry.
    """
    best_str: str | None = None
    best_offset: int | None = None
    for raw in expiries:
        if isinstance(raw, str):
            d = _parse_iso_date(raw)
            s = raw
        else:
            d = _parse_iso_date(raw)
            s = d.isoformat() if d is not None else None
        if d is None or s is None:
            continue
        offset = (d - today).days
        if offset < 0:
            continue
        if best_offset is None or offset < best_offset:
            best_offset = offset
            best_str = s
    return best_str, best_offset


def _wrap_with_sanitization(payload: dict[str, Any]) -> dict[str, Any]:
    """Sanitize the payload's strings and stamp the canonical block."""
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
# Payload construction
# ---------------------------------------------------------------------------


def _empty_payload(ticker: str, today: date) -> dict[str, Any]:
    return {
        "ticker": ticker,
        "as_of": _isoformat(_utc_now()),
        "today_date": today.isoformat(),
        "spot_price": None,
        "nearest_expiry": None,
        "atm_strike": None,
        "atm_call_price": None,
        "atm_put_price": None,
        "atm_straddle_price": None,
        "implied_move_pct": None,
        "iv_percentile": None,
        "expiry_offset_days": None,
    }


def _unavailable_payload(
    ticker: str, today: date, error: str
) -> dict[str, Any]:
    payload = _empty_payload(ticker, today)
    payload["status"] = "unavailable"
    payload["error"] = error
    return payload


# ---------------------------------------------------------------------------
# Per-ticker fetch
# ---------------------------------------------------------------------------


def _fetch_options_inner(
    yf_module: Any, ticker: str, today: date
) -> dict[str, Any]:
    """Synchronous fetch (called inside a thread-pool for timeout)."""
    ticker_obj = yf_module.Ticker(ticker)

    # 1) Get the available expiries
    try:
        raw_expiries = ticker_obj.options
    except BaseException as exc:  # noqa: BLE001
        return _unavailable_payload(
            ticker, today, f"options listing failed: {type(exc).__name__}: {exc}"
        )

    expiries = list(raw_expiries) if raw_expiries is not None else []
    if not expiries:
        return _unavailable_payload(
            ticker, today, "no option expiries available"
        )

    nearest_expiry, expiry_offset = _pick_nearest_expiry(expiries, today)
    if nearest_expiry is None:
        return _unavailable_payload(
            ticker, today, "no future-dated option expiry"
        )

    # 2) Fetch the chain for the nearest expiry
    try:
        chain = ticker_obj.option_chain(nearest_expiry)
    except BaseException as exc:  # noqa: BLE001
        return _unavailable_payload(
            ticker, today, f"option_chain failed: {type(exc).__name__}: {exc}"
        )

    calls = list(_iter_rows(getattr(chain, "calls", None)))
    puts = list(_iter_rows(getattr(chain, "puts", None)))
    if not calls or not puts:
        return _unavailable_payload(
            ticker, today, "option chain returned empty calls/puts"
        )

    # 3) Spot price
    spot = _spot_from_ticker(ticker_obj)
    if spot is None or spot <= 0:
        return _unavailable_payload(ticker, today, "spot price unavailable")

    # 4) ATM picking (closest strike to spot, on the call side)
    atm_call = _pick_atm_row(calls, spot)
    if atm_call is None:
        return _unavailable_payload(ticker, today, "no ATM call row")
    atm_strike_call = _as_float(_row_get(atm_call, "strike"))
    if atm_strike_call is None:
        return _unavailable_payload(ticker, today, "ATM call missing strike")

    # Match the same strike on the put side; if not present, pick closest put.
    atm_put = None
    for p in puts:
        if _as_float(_row_get(p, "strike")) == atm_strike_call:
            atm_put = p
            break
    if atm_put is None:
        atm_put = _pick_atm_row(puts, spot)
    if atm_put is None:
        return _unavailable_payload(ticker, today, "no ATM put row")

    call_price = _option_price(atm_call)
    put_price = _option_price(atm_put)
    if call_price is None or put_price is None:
        return _unavailable_payload(
            ticker, today, "ATM call or put price missing"
        )

    straddle = call_price + put_price
    implied_move_pct = (straddle / spot) * 100 if spot else None

    payload = _empty_payload(ticker, today)
    payload["spot_price"] = _round(spot, 4)
    payload["nearest_expiry"] = nearest_expiry
    payload["atm_strike"] = _strike_of(atm_call)
    payload["atm_call_price"] = _round(call_price, 4)
    payload["atm_put_price"] = _round(put_price, 4)
    payload["atm_straddle_price"] = _round(straddle, 4)
    payload["implied_move_pct"] = _round(implied_move_pct, 2)
    payload["expiry_offset_days"] = expiry_offset
    return payload


def fetch_options(
    ticker: str,
    yf_module: Any | None = None,
    timeout: int = 30,
    today_date: str | None = None,
) -> dict[str, Any]:
    """Fetch options data for one ticker.

    Per OD-F2 (graceful failure):

    * yfinance option chain failure NEVER raises. The record falls back to
      ``status="unavailable"`` + null fields + ``error`` message.
    * 30s timeout via thread-pool; timeout also degrades to unavailable.
    """
    ticker_upper = (ticker or "").strip().upper()
    today = _parse_today(today_date)
    yf_to_use = yf_module if yf_module is not None else _yf_default

    if yf_to_use is None:
        payload = _unavailable_payload(
            ticker_upper, today, "yfinance is not installed"
        )
        return _wrap_with_sanitization(payload)

    def _call() -> dict[str, Any]:
        return _fetch_options_inner(yf_to_use, ticker_upper, today)

    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_call)
            try:
                payload = future.result(timeout=timeout)
            except FuturesTimeoutError as exc:
                future.cancel()
                payload = _unavailable_payload(
                    ticker_upper, today, f"timeout after {timeout}s: {exc}"
                )
    except BaseException as exc:  # noqa: BLE001 — defensive belt-and-suspenders
        payload = _unavailable_payload(
            ticker_upper, today, f"unexpected: {type(exc).__name__}: {exc}"
        )

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


def fetch_options_many(
    tickers: Iterable[str],
    output_dir: Path | str,
    yf_module: Any | None = None,
    timeout: int = 30,
    today_date: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch options for many tickers.

    Writes ``{TICKER}.json`` per ticker into ``output_dir`` (atomic write).
    Per-ticker failures are isolated — one bad ticker does not abort siblings.
    """
    output_dir_path = Path(output_dir)
    output_dir_path.mkdir(parents=True, exist_ok=True)

    today = _parse_today(today_date)

    results: list[dict[str, Any]] = []
    for raw in tickers:
        ticker = (raw or "").strip()
        if not ticker:
            continue
        try:
            record = fetch_options(
                ticker=ticker,
                yf_module=yf_module,
                timeout=timeout,
                today_date=today_date,
            )
        except BaseException as exc:  # noqa: BLE001 — defensive belt-and-suspenders
            record = _wrap_with_sanitization(
                _unavailable_payload(
                    ticker.upper(),
                    today,
                    f"defensive: {type(exc).__name__}: {exc}",
                )
            )
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
            "Mode E options fetcher (ATM straddle + implied 1-day move). "
            "Graceful unavailable on yfinance failure (OD-F2)."
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

    results = fetch_options_many(
        tickers=args.tickers,
        output_dir=output_dir,
        timeout=args.timeout,
        today_date=args.today_date,
    )

    summary = {
        "tickers_requested": list(args.tickers),
        "by_ticker": {
            r["ticker"]: {
                "status": r.get("status", "ok"),
                "nearest_expiry": r.get("nearest_expiry"),
                "atm_strike": r.get("atm_strike"),
                "implied_move_pct": r.get("implied_move_pct"),
                "expiry_offset_days": r.get("expiry_offset_days"),
            }
            for r in results
        },
        "output_dir": str(output_dir),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    return 0 if results else 1


if __name__ == "__main__":
    raise SystemExit(main())
