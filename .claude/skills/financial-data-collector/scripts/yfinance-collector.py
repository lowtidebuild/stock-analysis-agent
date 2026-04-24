#!/usr/bin/env python3
"""
yfinance Collector
Collects fallback market data and quarterly statements from Yahoo Finance.

Usage:
  python .claude/skills/financial-data-collector/scripts/yfinance-collector.py \
    --ticker AAPL \
    --market US \
    --output output/data/AAPL/yfinance-raw.json \
    [--bundle minimum|standard] \
    [--timeout 15]

Exit codes:
  0 - success (JSON written, current_price available)
  1 - partial success (JSON written, current_price available but non-critical calls failed)
  2 - failure (no JSON written; current_price unavailable or dependency error)
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
from tools.prompt_injection_filter import SANITIZER_VERSION, sanitize_record  # noqa: E402

try:
    import yfinance as yf
except ImportError:
    yf = None


DEFAULT_HISTORY_PERIOD = "1y"
DEFAULT_HISTORY_INTERVAL = "1d"

INCOME_STMT_ALIASES = {
    "revenue": ["Total Revenue", "Revenue"],
    "gross_profit": ["Gross Profit"],
    "operating_income": ["Operating Income", "Operating Revenue"],
    "net_income": [
        "Net Income",
        "Net Income Common Stockholders",
        "Net Income From Continuing Operations",
    ],
    "eps_diluted": ["Diluted EPS"],
    "diluted_shares": ["Diluted Average Shares"],
}

BALANCE_SHEET_ALIASES = {
    "total_assets": ["Total Assets"],
    "total_equity": [
        "Total Equity Gross Minority Interest",
        "Stockholders Equity",
        "Total Stockholder Equity",
        "Common Stock Equity",
    ],
    "total_debt": ["Total Debt"],
    "cash_and_equivalents": [
        "Cash And Cash Equivalents",
        "Cash Cash Equivalents And Short Term Investments",
        "Cash And Short Term Investments",
    ],
    "short_term_debt": [
        "Current Debt And Capital Lease Obligation",
        "Current Debt",
        "Short Long Term Debt",
        "Short Term Debt",
    ],
    "long_term_debt": [
        "Long Term Debt And Capital Lease Obligation",
        "Long Term Debt",
        "Long Term Capital Lease Obligation",
    ],
}

CASHFLOW_ALIASES = {
    "operating_cashflow": [
        "Operating Cash Flow",
        "Cash Flow From Continuing Operating Activities",
        "Net Cash Provided By Operating Activities",
    ],
    "capital_expenditure": [
        "Capital Expenditure",
        "Capital Expenditure Reported",
        "Purchase Of PPE",
    ],
    "free_cash_flow": ["Free Cash Flow"],
}

INFO_FIELD_ALIASES = {
    "market_cap": ["marketCap"],
    "enterprise_value": ["enterpriseValue"],
    "shares_outstanding": ["sharesOutstanding"],
    "float_shares": ["floatShares"],
    "pe_trailing": ["trailingPE"],
    "pe_forward": ["forwardPE"],
    "pb_ratio": ["priceToBook"],
    "ev_ebitda": ["enterpriseToEbitda"],
    "dividend_yield": ["dividendYield"],
    "beta": ["beta"],
    "fifty_two_week_high": ["fiftyTwoWeekHigh"],
    "fifty_two_week_low": ["fiftyTwoWeekLow"],
    "sector": ["sector", "sectorDisp"],
    "industry": ["industry", "industryDisp"],
    "country": ["country"],
    "website": ["website"],
}

PRICE_KEYS = ["regularMarketPrice", "currentPrice"]
CHANGE_KEYS = ["regularMarketChange"]
CHANGE_PCT_KEYS = ["regularMarketChangePercent"]
CURRENCY_KEYS = ["currency"]

ANALYST_TARGET_KEYS = {
    "mean_target": ["targetMeanPrice"],
    "median_target": ["targetMedianPrice"],
    "high_target": ["targetHighPrice"],
    "low_target": ["targetLowPrice"],
    "analyst_count": ["numberOfAnalystOpinions"],
    "recommendation_mean": ["recommendationMean"],
    "recommendation_key": ["recommendationKey"],
}


class FatalCollectionError(RuntimeError):
    """Raised when the collector should stop and return exit code 2."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def isoformat_utc(dt: datetime | None = None) -> str:
    return (dt or utc_now()).strftime("%Y-%m-%dT%H:%M:%SZ")


def dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def as_number(value: Any) -> int | float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if hasattr(value, "item") and not isinstance(value, (bytes, bytearray)):
        try:
            value = value.item()
        except Exception:  # noqa: BLE001
            pass
    if isinstance(value, (int, float)):
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return None
        if isinstance(value, float) and value.is_integer():
            return int(value)
        return value
    try:
        if value != value:
            return None
    except Exception:
        pass
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped or stripped in {"-", "nan", "NaN", "None"}:
            return None
        try:
            parsed = float(stripped.replace(",", ""))
        except ValueError:
            return None
        if parsed.is_integer():
            return int(parsed)
        return parsed
    return None


def normalize_date(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "to_pydatetime"):
        value = value.to_pydatetime()
    if isinstance(value, datetime):
        return value.date().isoformat()
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()[:10]
        except Exception:
            return str(value)
    return str(value)[:10]


def is_rate_limited_error(error: BaseException) -> bool:
    message = str(error).lower()
    return "429" in message or "too many requests" in message or "rate limit" in message


def run_with_timeout(func: Any, timeout: int) -> Any:
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(func)
        try:
            return future.result(timeout=timeout)
        except FuturesTimeoutError as exc:
            future.cancel()
            raise TimeoutError(f"timed out after {timeout}s") from exc


def call_with_retry(
    label: str,
    timeout: int,
    func: Any,
    calls_succeeded: list[str],
    calls_failed: list[str],
    critical: bool = False,
) -> Any:
    last_error: BaseException | None = None
    for attempt in range(2):
        try:
            result = run_with_timeout(func, timeout)
            calls_succeeded.append(label)
            time.sleep(0.3)
            return result
        except BaseException as exc:  # noqa: BLE001
            last_error = exc
            if is_rate_limited_error(exc):
                raise FatalCollectionError(f"{label} rate limited: {exc}") from exc
            if attempt == 0:
                time.sleep(2)
                continue
    message = f"{label}:{type(last_error).__name__}:{last_error}"
    calls_failed.append(message)
    if critical:
        raise FatalCollectionError(message)
    time.sleep(0.3)
    return None


def build_info_lookup(frame: Any) -> dict[str, Any]:
    lookup: dict[str, Any] = {}
    if frame is None or getattr(frame, "empty", True):
        return lookup
    for index_label in frame.index:
        key = str(index_label).strip().casefold()
        lookup[key] = index_label
    return lookup


def get_statement_value(frame: Any, lookup: dict[str, Any], aliases: list[str], column: Any) -> Any:
    for alias in aliases:
        matched = lookup.get(alias.casefold())
        if matched is not None:
            try:
                return frame.at[matched, column]
            except Exception:  # noqa: BLE001
                return None
    return None


def normalize_statement(
    frame: Any,
    aliases_map: dict[str, list[str]],
    period_type: str,
    warnings: list[str],
) -> list[dict[str, Any]]:
    if frame is None or getattr(frame, "empty", True):
        return []

    lookup = build_info_lookup(frame)
    matched_aliases: dict[str, list[str]] = {}
    for field_name, aliases in aliases_map.items():
        matched_aliases[field_name] = aliases
        if not any(alias.casefold() in lookup for alias in aliases):
            warnings.append(f"{period_type}:{field_name}:missing")

    columns = list(frame.columns)
    try:
        columns = sorted(columns, reverse=True)
    except TypeError:
        pass

    rows: list[dict[str, Any]] = []
    for column in columns:
        row: dict[str, Any] = {
            "period_end": normalize_date(column),
            "period_type": period_type,
        }
        for field_name, aliases in matched_aliases.items():
            row[field_name] = as_number(get_statement_value(frame, lookup, aliases, column))

        if "capital_expenditure" in row and row.get("capital_expenditure") is not None:
            capex_raw = row["capital_expenditure"]
            capex_outflow_abs = as_number(abs(capex_raw))
            row["capex_raw"] = capex_raw
            row["capex_outflow_abs"] = capex_outflow_abs
            if capex_raw < 0:
                row["capex_sign_convention"] = "negative_outflow"
            elif capex_raw > 0:
                row["capex_sign_convention"] = "positive_outflow"
            else:
                row["capex_sign_convention"] = "zero"
            row["capital_expenditure"] = capex_outflow_abs

        if "operating_cashflow" in row and "capex_outflow_abs" in row:
            op_cf = row.get("operating_cashflow")
            capex_outflow_abs = row.get("capex_outflow_abs")
            if op_cf is not None and capex_outflow_abs is not None:
                calculated_fcf = as_number(op_cf - capex_outflow_abs)
                row["free_cash_flow_calculated"] = calculated_fcf
                source_fcf = row.get("free_cash_flow")
                if source_fcf is None:
                    row["free_cash_flow"] = calculated_fcf
                elif calculated_fcf is not None:
                    threshold = max(abs(calculated_fcf) * 0.02, 1)
                    difference = as_number(source_fcf - calculated_fcf)
                    if difference is not None and abs(difference) > threshold:
                        row["free_cash_flow_conflict"] = {
                            "source_value": source_fcf,
                            "calculated_value": calculated_fcf,
                            "difference": difference,
                        }

        if "short_term_debt" in row and "long_term_debt" in row and row.get("total_debt") is None:
            short_debt = row.get("short_term_debt")
            long_debt = row.get("long_term_debt")
            if short_debt is not None or long_debt is not None:
                row["total_debt"] = as_number((short_debt or 0) + (long_debt or 0))

        has_payload = any(
            value is not None
            for key, value in row.items()
            if key not in {"period_end", "period_type"}
        )
        if has_payload:
            rows.append(row)

    return rows


def normalize_history(frame: Any) -> list[dict[str, Any]]:
    if frame is None or getattr(frame, "empty", True):
        return []

    try:
        sorted_frame = frame.sort_index()
    except Exception:  # noqa: BLE001
        sorted_frame = frame

    rows: list[dict[str, Any]] = []
    for index_label, history_row in sorted_frame.iterrows():
        date_value = normalize_date(index_label)
        row = {
            "date": date_value,
            "open": as_number(history_row.get("Open")),
            "high": as_number(history_row.get("High")),
            "low": as_number(history_row.get("Low")),
            "close": as_number(history_row.get("Close")),
            "volume": as_number(history_row.get("Volume")),
        }
        if any(row[key] is not None for key in ("open", "high", "low", "close", "volume")):
            rows.append(row)
    return rows


def latest_history_price(history_rows: list[dict[str, Any]]) -> int | float | None:
    for row in reversed(history_rows):
        if row.get("close") is not None:
            return row["close"]
    return None


def read_info_field(
    info: dict[str, Any],
    field_name: str,
    aliases: list[str],
    calls_failed: list[str],
) -> tuple[Any, str | None]:
    expected_key = aliases[0]
    if expected_key not in info:
        calls_failed.append(f"info:missing:{expected_key}")
    for alias in aliases:
        if alias in info:
            value = info.get(alias)
            if value not in ("", None):
                return value, alias
    return None, None


def build_info_payload(info: dict[str, Any], calls_failed: list[str]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for field_name, aliases in INFO_FIELD_ALIASES.items():
        value, _ = read_info_field(info, field_name, aliases, calls_failed)
        payload[field_name] = as_number(value) if field_name not in {"sector", "industry", "country", "website"} else value

    payload["raw_info_keys_present"] = sorted(str(key) for key in info.keys())
    return payload


def build_analyst_targets(
    info: dict[str, Any],
    analyst_price_targets: Any,
    recommendations: Any,
    calls_failed: list[str],
) -> dict[str, Any]:
    if analyst_price_targets is None:
        analyst_price_targets = {}
    if not isinstance(analyst_price_targets, dict):
        try:
            analyst_price_targets = dict(analyst_price_targets)
        except Exception:  # noqa: BLE001
            analyst_price_targets = {}

    payload: dict[str, Any] = {
        "mean_target": None,
        "median_target": None,
        "high_target": None,
        "low_target": None,
        "analyst_count": None,
        "recommendation_mean": None,
        "recommendation_key": None,
    }

    analyst_target_fallbacks = {
        "mean_target": ["mean", "meanPrice"],
        "median_target": ["median", "medianPrice"],
        "high_target": ["high", "highPrice"],
        "low_target": ["low", "lowPrice"],
        "analyst_count": ["numberOfAnalysts", "analystCount"],
    }

    for field_name, aliases in ANALYST_TARGET_KEYS.items():
        value, _ = read_info_field(info, field_name, aliases, calls_failed)
        if value is None:
            for fallback_key in analyst_target_fallbacks.get(field_name, []):
                if fallback_key in analyst_price_targets:
                    value = analyst_price_targets.get(fallback_key)
                    break
        if field_name == "recommendation_mean" and value is None and recommendations is not None:
            if hasattr(recommendations, "empty") and not recommendations.empty and "rating" in recommendations.columns:
                try:
                    value = recommendations["rating"].dropna().astype(float).mean()
                except Exception:  # noqa: BLE001
                    value = None
        payload[field_name] = as_number(value) if field_name != "recommendation_key" else value

    return payload


def resolve_current_price(
    info: dict[str, Any],
    history_rows: list[dict[str, Any]],
    market: str,
    timestamp: str,
    calls_failed: list[str],
    warnings: list[str],
) -> dict[str, Any]:
    price, source_field = read_info_field(info, "current_price", PRICE_KEYS, calls_failed)
    change, _ = read_info_field(info, "change", CHANGE_KEYS, calls_failed)
    change_pct, _ = read_info_field(info, "change_pct", CHANGE_PCT_KEYS, calls_failed)
    currency, _ = read_info_field(info, "currency", CURRENCY_KEYS, calls_failed)

    numeric_price = as_number(price)
    if numeric_price is None:
        history_price = latest_history_price(history_rows)
        if history_price is not None:
            numeric_price = history_price
            source_field = "history.close"
            warnings.append("current_price:fallback_to_history_close")

    if currency in (None, ""):
        currency = "KRW" if market == "KR" else "USD"

    return {
        "price": numeric_price,
        "currency": currency,
        "change": as_number(change),
        "change_pct": as_number(change_pct),
        "as_of": timestamp,
        "source_field": source_field,
    }


def compute_ttm(income_rows: list[dict[str, Any]], cashflow_rows: list[dict[str, Any]]) -> dict[str, Any]:
    income_quarters = income_rows[:4]
    cashflow_quarters = cashflow_rows[:4]

    def sum_field(rows: list[dict[str, Any]], field_name: str) -> int | float | None:
        values = [row.get(field_name) for row in rows if row.get(field_name) is not None]
        if not values:
            return None
        return as_number(sum(values))

    diluted_shares = None
    if income_quarters:
        diluted_shares = income_quarters[0].get("diluted_shares")

    eps_ttm = sum_field(income_quarters, "eps_diluted")
    if eps_ttm is None:
        net_income_ttm = sum_field(income_quarters, "net_income")
        if net_income_ttm is not None and diluted_shares not in (None, 0):
            eps_ttm = as_number(net_income_ttm / diluted_shares)

    return {
        "revenue_ttm": sum_field(income_quarters, "revenue"),
        "net_income_ttm": sum_field(income_quarters, "net_income"),
        "operating_income_ttm": sum_field(income_quarters, "operating_income"),
        "eps_ttm": eps_ttm,
        "fcf_ttm": sum_field(cashflow_quarters, "free_cash_flow"),
        "quarters_used": min(4, len(income_quarters)),
    }


def build_data_quality(
    current_price: dict[str, Any],
    income_rows: list[dict[str, Any]],
    balance_rows: list[dict[str, Any]],
    cashflow_rows: list[dict[str, Any]],
    warnings: list[str],
) -> dict[str, Any]:
    quarters_available = len(income_rows)
    statements_complete = (
        len(income_rows) >= 4
        and len(balance_rows) >= 4
        and len(cashflow_rows) >= 4
    )
    return {
        "price_available": current_price.get("price") is not None,
        "quarters_available": quarters_available,
        "statements_complete": statements_complete,
        "warnings": dedupe_preserve_order(warnings),
    }


def choose_candidates(ticker: str, market: str) -> list[str]:
    normalized = ticker.strip().upper()
    if market == "US":
        return [normalized]
    base = ticker.strip()
    return [f"{base}.KS", f"{base}.KQ"]


def classify_kr_candidate(info: dict[str, Any], history_rows: list[dict[str, Any]]) -> dict[str, Any]:
    quote_type = str(info.get("quoteType") or "").upper()
    short_name = str(info.get("shortName") or "")
    long_name = str(info.get("longName") or "")
    full_exchange_name = str(info.get("fullExchangeName") or "")
    has_price = resolve_current_price(
        info=info,
        history_rows=history_rows,
        market="KR",
        timestamp=isoformat_utc(),
        calls_failed=[],
        warnings=[],
    ).get("price") is not None

    return {
        "quote_type": quote_type,
        "short_name": short_name,
        "long_name": long_name,
        "full_exchange_name": full_exchange_name,
        "has_price": has_price,
        "is_equity": quote_type == "EQUITY",
    }


def collect_quote_data(
    symbol: str,
    timeout: int,
    calls_succeeded: list[str],
    calls_failed: list[str],
) -> tuple[Any, dict[str, Any], list[dict[str, Any]]]:
    ticker_obj = yf.Ticker(symbol)
    info = call_with_retry("info", timeout, lambda: ticker_obj.info, calls_succeeded, calls_failed)
    info = info if isinstance(info, dict) else {}
    history_frame = call_with_retry(
        "history",
        timeout,
        lambda: ticker_obj.history(period="5d", interval=DEFAULT_HISTORY_INTERVAL, auto_adjust=False),
        calls_succeeded,
        calls_failed,
    )
    history_rows = normalize_history(history_frame)
    return ticker_obj, info, history_rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect fallback stock data from yfinance")
    parser.add_argument("--ticker", required=True, help="Ticker symbol (KR expects a 6-digit stock code)")
    parser.add_argument("--market", required=True, choices=["US", "KR"], help="Market: US or KR")
    parser.add_argument("--output", required=True, help="Output JSON file path")
    parser.add_argument("--bundle", default="standard", choices=["minimum", "standard"], help="Collection bundle")
    parser.add_argument("--timeout", type=int, default=15, help="Per-call timeout in seconds")
    args = parser.parse_args()

    if yf is None:
        print("yfinance is not installed. Install yfinance>=0.2.40 first.", file=sys.stderr)
        return 2

    output_path = Path(args.output).expanduser()
    if not output_path.is_absolute():
        output_path = Path.cwd() / output_path

    timestamp = isoformat_utc()
    calls_succeeded: list[str] = []
    calls_failed: list[str] = []
    warnings: list[str] = []

    try:
        yfinance_version = metadata.version("yfinance")
    except metadata.PackageNotFoundError:
        yfinance_version = getattr(yf, "__version__", "unknown")

    resolved_symbol: str | None = None
    resolved_ticker_obj: Any = None
    resolved_info: dict[str, Any] = {}
    initial_history_rows: list[dict[str, Any]] = []
    kr_candidates: list[dict[str, Any]] = []

    try:
        for candidate in choose_candidates(args.ticker, args.market):
            ticker_obj, info, history_rows = collect_quote_data(candidate, args.timeout, calls_succeeded, calls_failed)

            price_payload = resolve_current_price(
                info=info,
                history_rows=history_rows,
                market=args.market,
                timestamp=timestamp,
                calls_failed=calls_failed,
                warnings=warnings,
            )
            if args.market == "KR":
                kr_meta = classify_kr_candidate(info, history_rows)
                kr_candidates.append(
                    {
                        "symbol": candidate,
                        "ticker_obj": ticker_obj,
                        "info": info,
                        "history_rows": history_rows,
                        "price_payload": price_payload,
                        "meta": kr_meta,
                    }
                )
                if price_payload.get("price") is None:
                    warnings.append(f"suffix_probe:{candidate}:no_price")
                continue

            if price_payload.get("price") is not None:
                resolved_symbol = candidate
                resolved_ticker_obj = ticker_obj
                resolved_info = info
                initial_history_rows = history_rows
                break

        if args.market == "KR":
            preferred_candidate = next(
                (
                    item
                    for item in kr_candidates
                    if item["price_payload"].get("price") is not None and item["meta"].get("is_equity")
                ),
                None,
            )
            fallback_candidate = next(
                (item for item in kr_candidates if item["price_payload"].get("price") is not None),
                None,
            )
            chosen_candidate = preferred_candidate or fallback_candidate
            if chosen_candidate is not None:
                resolved_symbol = chosen_candidate["symbol"]
                resolved_ticker_obj = chosen_candidate["ticker_obj"]
                resolved_info = chosen_candidate["info"]
                initial_history_rows = chosen_candidate["history_rows"]
                for item in kr_candidates:
                    if (
                        item is not chosen_candidate
                        and item["price_payload"].get("price") is not None
                        and not item["meta"].get("is_equity")
                    ):
                        warnings.append(
                            f"suffix_probe:{item['symbol']}:ignored_non_equity:{item['meta'].get('quote_type') or 'UNKNOWN'}"
                        )
            else:
                for item in kr_candidates:
                    warnings.append(f"suffix_probe:{item['symbol']}:no_usable_quote")

        if resolved_symbol is None or resolved_ticker_obj is None:
            raise FatalCollectionError(f"Could not resolve current price for {args.ticker}")

        full_history_rows = initial_history_rows
        history_frame = call_with_retry(
            "history_full",
            args.timeout,
            lambda: resolved_ticker_obj.history(
                period=DEFAULT_HISTORY_PERIOD,
                interval=DEFAULT_HISTORY_INTERVAL,
                auto_adjust=False,
            ),
            calls_succeeded,
            calls_failed,
        )
        if history_frame is not None and not getattr(history_frame, "empty", True):
            full_history_rows = normalize_history(history_frame)

        income_rows: list[dict[str, Any]] = []
        balance_rows: list[dict[str, Any]] = []
        cashflow_rows: list[dict[str, Any]] = []
        analyst_targets_raw: Any = None
        recommendations_raw: Any = None

        if args.bundle == "standard":
            income_frame = call_with_retry(
                "income_stmt",
                args.timeout,
                lambda: resolved_ticker_obj.quarterly_income_stmt,
                calls_succeeded,
                calls_failed,
            )
            balance_frame = call_with_retry(
                "balance_sheet",
                args.timeout,
                lambda: resolved_ticker_obj.quarterly_balance_sheet,
                calls_succeeded,
                calls_failed,
            )
            cashflow_frame = call_with_retry(
                "cashflow",
                args.timeout,
                lambda: resolved_ticker_obj.quarterly_cashflow,
                calls_succeeded,
                calls_failed,
            )
            analyst_targets_raw = call_with_retry(
                "analyst_targets",
                args.timeout,
                lambda: resolved_ticker_obj.analyst_price_targets,
                calls_succeeded,
                calls_failed,
            )
            recommendations_raw = call_with_retry(
                "recommendations",
                args.timeout,
                lambda: resolved_ticker_obj.recommendations,
                calls_succeeded,
                calls_failed,
            )

            income_rows = normalize_statement(income_frame, INCOME_STMT_ALIASES, "quarterly", warnings)
            balance_rows = normalize_statement(balance_frame, BALANCE_SHEET_ALIASES, "quarterly", warnings)
            cashflow_rows = normalize_statement(cashflow_frame, CASHFLOW_ALIASES, "quarterly", warnings)

        current_price = resolve_current_price(
            info=resolved_info,
            history_rows=full_history_rows,
            market=args.market,
            timestamp=timestamp,
            calls_failed=calls_failed,
            warnings=warnings,
        )
        if current_price.get("price") is None:
            raise FatalCollectionError(f"Current price unavailable for {resolved_symbol}")

        payload = {
            "ticker": args.ticker,
            "market": args.market,
            "yahoo_symbol": resolved_symbol,
            "collection_timestamp": timestamp,
            "data_source": "yfinance",
            "yfinance_version": yfinance_version,
            "bundle": args.bundle,
            "calls_succeeded": dedupe_preserve_order(calls_succeeded),
            "calls_failed": dedupe_preserve_order(calls_failed),
            "current_price": current_price,
            "info": build_info_payload(resolved_info, calls_failed),
            "income_statements": income_rows,
            "balance_sheets": balance_rows,
            "cash_flow_statements": cashflow_rows,
            "historical_prices": {
                "range": DEFAULT_HISTORY_PERIOD,
                "interval": DEFAULT_HISTORY_INTERVAL,
                "rows": full_history_rows,
            },
            "analyst_targets": build_analyst_targets(
                resolved_info,
                analyst_targets_raw,
                recommendations_raw,
                calls_failed,
            ),
            "derived_ttm": compute_ttm(income_rows, cashflow_rows),
            "data_quality": build_data_quality(
                current_price=current_price,
                income_rows=income_rows,
                balance_rows=balance_rows,
                cashflow_rows=cashflow_rows,
                warnings=warnings,
            ),
        }

        payload["calls_failed"] = dedupe_preserve_order(calls_failed)
        payload["data_quality"]["warnings"] = dedupe_preserve_order(payload["data_quality"]["warnings"])

        payload, sanitization_findings = sanitize_record(payload)
        payload["_sanitization"] = {
            "tool": "tools/prompt_injection_filter.py",
            "version": SANITIZER_VERSION,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "redactions": len(sanitization_findings),
            "findings": sanitization_findings,
        }

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        major_call_failures = [
            item
            for item in payload["calls_failed"]
            if not item.startswith("info:missing:")
            and any(
                item.startswith(prefix)
                for prefix in (
                    "history_full:",
                    "income_stmt:",
                    "balance_sheet:",
                    "cashflow:",
                    "analyst_targets:",
                    "recommendations:",
                )
            )
        ]
        exit_code = 1 if major_call_failures else 0

        summary = {
            "status": "success" if exit_code == 0 else "partial",
            "ticker": args.ticker,
            "market": args.market,
            "yahoo_symbol": resolved_symbol,
            "output_path": str(output_path),
            "current_price": current_price.get("price"),
            "calls_succeeded": len(payload["calls_succeeded"]),
            "calls_failed": len(payload["calls_failed"]),
        }
        print(json.dumps(summary, ensure_ascii=False))
        return exit_code

    except FatalCollectionError as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
