#!/usr/bin/env python3
"""
Peer Mini-Fetch — Phase D

Lightweight yfinance fetcher used by the orchestrator in Mode C/D to populate
the Mode C peer comparison table with real numbers instead of `[Est] peer
reference` placeholders.

Usage (CLI):
  python .claude/skills/financial-data-collector/scripts/peer-fetch.py \
    --tickers MSFT META AMZN AAPL \
    --output-dir output/runs/{run_id}/peers/ \
    --cache-dir  output/data/peers-cache/ \
    --cache-ttl-hours 24 \
    --timeout 30

Per-ticker JSON output (written to BOTH ``--output-dir`` and ``--cache-dir``)::

    {
      "ticker": "MSFT",
      "company_name": "Microsoft Corporation",
      "currency": "USD",
      "collection_timestamp": "2026-05-07T00:00:00Z",
      "data_source": "yfinance (peer mini-fetch)",
      "tag": "[Portal]",
      "confidence_grade": "B",
      "metrics": {
        "current_price": 425.30,
        "market_cap": 3158000000000,
        "pe_forward": 31.5,
        "ev_ebitda": 22.5,
        "revenue_growth_yoy": 16.0,
        "operating_margin": 44.5,
        "fcf_yield": 2.22,
        "beta": 0.91
      },
      "_sanitization": {
        "tool":  "tools/prompt_injection_filter.py",
        "version": "1",
        "redactions": 0,
        "findings": []
      },
      "cache_expires_at": "2026-05-08T00:00:00Z"   # cache copy only
    }

Design rules (CLAUDE.md §12 + §9):

* Single ``yfinance.Ticker(t).info`` call per peer (fast path, ~5-10s).
* 30s per-ticker timeout via ``concurrent.futures.ThreadPoolExecutor``.
* Each ticker is independent — one failure does NOT abort the run; the
  failed peer gets a ``status="error"`` record with the canonical schema
  shape preserved (so downstream consumers do not need special-cases).
* Cache miss / expired (cache_expires_at < now) → fresh fetch + cache write.
* Cache hit → no yfinance call.
* All fetched strings pass through ``tools.prompt_injection_filter`` before
  being written to disk.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime, timedelta, timezone
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


PEER_TAG = "[Portal]"
PEER_GRADE = "B"
DATA_SOURCE = "yfinance (peer mini-fetch)"

# Canonical metric column set displayed by the Mode C peer table.
PEER_METRIC_KEYS: tuple[str, ...] = (
    "current_price",
    "market_cap",
    "pe_forward",
    "ev_ebitda",
    "revenue_growth_yoy",
    "operating_margin",
    "fcf_yield",
    "beta",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _isoformat(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _as_float(value: Any) -> float | int | None:
    """Coerce yfinance values to a JSON-friendly number, or None."""
    if value is None:
        return None
    if isinstance(value, bool):  # bool is subclass of int — exclude
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
        rounded = round(float(value), places)
    except (TypeError, ValueError):
        return None
    if rounded == int(rounded):
        return int(rounded) if places == 0 else rounded
    return rounded


def _percent_from_fraction(value: Any) -> float | None:
    """``revenueGrowth=0.16`` → ``16.0``.  Pass-through if already in %.

    Heuristic: yfinance ``revenueGrowth`` and ``operatingMargins`` are *fractions*
    in the [-1, 1] range. If the source already returned percent (>1.5 or <-1.5
    in absolute terms), trust it.
    """
    coerced = _as_float(value)
    if coerced is None:
        return None
    if abs(coerced) <= 1.5:
        return _round(coerced * 100, 2)
    return _round(coerced, 2)


def _fcf_yield(free_cashflow: Any, market_cap: Any) -> float | None:
    fcf = _as_float(free_cashflow)
    mc = _as_float(market_cap)
    if fcf is None or mc in (None, 0):
        return None
    try:
        return _round((fcf / mc) * 100, 2)
    except ZeroDivisionError:
        return None


def _company_name(info: dict) -> str | None:
    for key in ("longName", "shortName", "displayName"):
        value = info.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _currency(info: dict) -> str | None:
    value = info.get("currency")
    if isinstance(value, str) and value.strip():
        return value.strip().upper()
    return None


def _empty_metrics() -> dict[str, Any]:
    return {key: None for key in PEER_METRIC_KEYS}


def _build_metrics(info: dict) -> dict[str, Any]:
    metrics = _empty_metrics()
    metrics["current_price"] = _round(
        _as_float(info.get("regularMarketPrice"))
        or _as_float(info.get("currentPrice")),
        4,
    )
    metrics["market_cap"] = _as_float(info.get("marketCap"))
    metrics["pe_forward"] = _round(_as_float(info.get("forwardPE")), 2)
    metrics["ev_ebitda"] = _round(_as_float(info.get("enterpriseToEbitda")), 2)
    metrics["revenue_growth_yoy"] = _percent_from_fraction(info.get("revenueGrowth"))
    metrics["operating_margin"] = _percent_from_fraction(info.get("operatingMargins"))
    metrics["fcf_yield"] = _fcf_yield(info.get("freeCashflow"), info.get("marketCap"))
    metrics["beta"] = _round(_as_float(info.get("beta")), 4)
    return metrics


def _wrap_with_sanitization(payload: dict[str, Any]) -> dict[str, Any]:
    """Sanitize the payload's strings and stamp the canonical block."""
    san_block = payload.pop("_sanitization", None)
    cleaned, findings = sanitize_record(payload)
    cleaned["_sanitization"] = {
        "tool": "tools/prompt_injection_filter.py",
        "version": SANITIZER_VERSION,
        "timestamp": _isoformat(_utc_now()),
        "redactions": len(findings),
        "findings": findings,
    }
    # Preserve cache_expires_at if it was set before sanitization (it is a
    # plain ISO timestamp and harmless to re-stamp).
    return cleaned


# ---------------------------------------------------------------------------
# Cache I/O
# ---------------------------------------------------------------------------


def _cache_path(cache_dir: Path, ticker: str) -> Path:
    return Path(cache_dir) / f"{ticker.upper()}.json"


def _load_cache(cache_dir: Path | None, ticker: str) -> dict[str, Any] | None:
    if cache_dir is None:
        return None
    path = _cache_path(cache_dir, ticker)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _cache_is_fresh(cache_payload: dict[str, Any], now: datetime) -> bool:
    expires = cache_payload.get("cache_expires_at")
    if not isinstance(expires, str):
        return False
    try:
        # tolerate both "...Z" and "...+00:00"
        if expires.endswith("Z"):
            expires_dt = datetime.strptime(expires, "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=timezone.utc
            )
        else:
            expires_dt = datetime.fromisoformat(expires)
            if expires_dt.tzinfo is None:
                expires_dt = expires_dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return False
    return expires_dt > now


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


# ---------------------------------------------------------------------------
# Per-ticker fetch
# ---------------------------------------------------------------------------


def _fetch_info_with_timeout(yf_module: Any, ticker: str, timeout: int) -> dict:
    """Return ``yfinance.Ticker(ticker).info`` or raise."""

    def _call() -> dict:
        ticker_obj = yf_module.Ticker(ticker)
        info = getattr(ticker_obj, "info", None)
        if info is None:
            return {}
        return info if isinstance(info, dict) else dict(info)

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(_call)
        try:
            return future.result(timeout=timeout)
        except FuturesTimeoutError as exc:
            future.cancel()
            raise TimeoutError(f"yfinance.info timed out after {timeout}s") from exc


def _build_payload(
    ticker: str,
    info: dict,
    timestamp: str,
) -> dict[str, Any]:
    return {
        "ticker": ticker,
        "company_name": _company_name(info),
        "currency": _currency(info),
        "collection_timestamp": timestamp,
        "data_source": DATA_SOURCE,
        "tag": PEER_TAG,
        "confidence_grade": PEER_GRADE,
        "metrics": _build_metrics(info),
    }


def _build_error_payload(ticker: str, error: BaseException, timestamp: str) -> dict[str, Any]:
    return {
        "ticker": ticker,
        "company_name": None,
        "currency": None,
        "collection_timestamp": timestamp,
        "data_source": DATA_SOURCE,
        "tag": PEER_TAG,
        "confidence_grade": "D",
        "status": "error",
        "error": f"{type(error).__name__}: {error}",
        "metrics": _empty_metrics(),
    }


def fetch_peer(
    ticker: str,
    cache_dir: Path | str | None,
    cache_ttl_hours: int = 24,
    timeout: int = 30,
    yf_module: Any | None = None,
    output_dir: Path | str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Fetch one peer ticker and return the canonical record dict.

    * If a fresh cache file exists at ``cache_dir/{TICKER}.json`` (per
      ``cache_ttl_hours`` / ``cache_expires_at``), the cached payload is
      returned and ``yf_module`` is NOT called.
    * Otherwise the function calls ``yf_module.Ticker(ticker).info``,
      sanitizes the result, writes it to the cache (and to ``output_dir``
      when provided), and returns the new record.
    * Per-ticker errors (network, invalid ticker, malformed payload) are
      caught and returned as a ``status="error"`` record. This function
      never raises for a single-peer failure.
    """
    ticker_upper = ticker.upper()
    cache_dir_path = Path(cache_dir) if cache_dir is not None else None
    output_dir_path = Path(output_dir) if output_dir is not None else None
    now_dt = now or _utc_now()

    # 1) Cache hit?
    cached = _load_cache(cache_dir_path, ticker_upper)
    if cached is not None and _cache_is_fresh(cached, now_dt):
        # Mirror cache to run-local output if requested (cheap copy).
        if output_dir_path is not None:
            try:
                _write_json(output_dir_path / f"{ticker_upper}.json", cached)
            except OSError:
                pass
        return cached

    # 2) Fresh fetch (with per-ticker error containment).
    timestamp = _isoformat(now_dt)
    yf_to_use = yf_module if yf_module is not None else _yf_default
    if yf_to_use is None:
        payload = _build_error_payload(
            ticker_upper,
            RuntimeError("yfinance is not installed"),
            timestamp,
        )
    else:
        try:
            info = _fetch_info_with_timeout(yf_to_use, ticker_upper, timeout)
            if not isinstance(info, dict):
                info = {}
            payload = _build_payload(ticker_upper, info, timestamp)
        except BaseException as exc:  # noqa: BLE001
            payload = _build_error_payload(ticker_upper, exc, timestamp)

    # 3) Sanitize.
    payload = _wrap_with_sanitization(payload)

    # 4) Write to cache + output_dir.
    if cache_dir_path is not None:
        cache_payload = dict(payload)
        cache_payload["cache_expires_at"] = _isoformat(
            now_dt + timedelta(hours=cache_ttl_hours)
        )
        try:
            _write_json(_cache_path(cache_dir_path, ticker_upper), cache_payload)
        except OSError:
            pass
        # Return value mirrors the cache_expires_at so callers see consistent shape.
        payload = cache_payload

    if output_dir_path is not None:
        try:
            _write_json(output_dir_path / f"{ticker_upper}.json", payload)
        except OSError:
            pass

    return payload


def fetch_peers(
    tickers: Iterable[str],
    output_dir: Path | str,
    cache_dir: Path | str,
    cache_ttl_hours: int = 24,
    timeout: int = 30,
    yf_module: Any | None = None,
) -> list[dict[str, Any]]:
    """Fetch multiple peer tickers; one bad ticker does not abort others."""
    output_dir_path = Path(output_dir)
    cache_dir_path = Path(cache_dir)
    output_dir_path.mkdir(parents=True, exist_ok=True)
    cache_dir_path.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    for raw_ticker in tickers:
        ticker = (raw_ticker or "").strip()
        if not ticker:
            continue
        try:
            record = fetch_peer(
                ticker=ticker,
                cache_dir=cache_dir_path,
                cache_ttl_hours=cache_ttl_hours,
                timeout=timeout,
                yf_module=yf_module,
                output_dir=output_dir_path,
            )
        except BaseException as exc:  # noqa: BLE001 — defensive belt-and-suspenders
            record = _wrap_with_sanitization(
                _build_error_payload(ticker.upper(), exc, _isoformat(_utc_now()))
            )
            try:
                _write_json(output_dir_path / f"{ticker.upper()}.json", record)
            except OSError:
                pass
        results.append(record)
    return results


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Peer mini-fetch (Mode C/D peer comparison populator)"
    )
    parser.add_argument(
        "--tickers",
        nargs="+",
        required=True,
        help="One or more peer ticker symbols (e.g. MSFT META AMZN AAPL)",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Run-local directory: output/runs/{run_id}/peers/",
    )
    parser.add_argument(
        "--cache-dir",
        default="output/data/peers-cache",
        help="Run-shared 24h cache directory (default: output/data/peers-cache/)",
    )
    parser.add_argument(
        "--cache-ttl-hours",
        type=int,
        default=24,
        help="Cache freshness window in hours (default: 24)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Per-ticker timeout in seconds (default: 30)",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir).expanduser()
    cache_dir = Path(args.cache_dir).expanduser()
    if not output_dir.is_absolute():
        output_dir = Path.cwd() / output_dir
    if not cache_dir.is_absolute():
        cache_dir = Path.cwd() / cache_dir

    results = fetch_peers(
        tickers=args.tickers,
        output_dir=output_dir,
        cache_dir=cache_dir,
        cache_ttl_hours=args.cache_ttl_hours,
        timeout=args.timeout,
    )

    summary = {
        "tickers_requested": list(args.tickers),
        "tickers_collected": [r["ticker"] for r in results if r.get("status") != "error"],
        "tickers_failed": [r["ticker"] for r in results if r.get("status") == "error"],
        "output_dir": str(output_dir),
        "cache_dir": str(cache_dir),
        "cache_ttl_hours": args.cache_ttl_hours,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    # Exit 0 if at least one peer succeeded, 1 if all failed (matches
    # yfinance-collector pattern of "partial success is still success").
    if summary["tickers_collected"]:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
