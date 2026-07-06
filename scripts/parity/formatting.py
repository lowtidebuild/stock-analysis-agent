"""Shared metric formatting rules for analyst prose and HTML rendering.

Canonical public-display rules:

| Metric class | Rule |
| --- | --- |
| `market_cap`, `revenue_ttm`, `fcf_ttm`, `net_debt` | Values are normalized billions; render as currency + `B`. |
| Percent, margin, yield, growth | Render as one-decimal percent, with a positive sign outside probability fields. |
| Valuation multiples | Render as one-decimal `x`. |
| Price/target money values | Render USD with two decimals and KRW with no decimals. |
| Other plain numbers | Render with fixed decimals for dashboard values or trimmed decimals for prose helpers. |
"""

from __future__ import annotations

from typing import Any

BILLION_METRICS = {"market_cap", "revenue_ttm", "fcf_ttm", "net_debt"}
MULTIPLE_METRICS = {"pe_ratio", "pe_forward", "ev_ebitda", "pb_ratio", "net_debt_ebitda"}


def currency_symbol(currency: str) -> str:
    return {"USD": "$", "KRW": "KRW ", "EUR": "EUR ", "JPY": "JPY "}.get(
        currency.upper(), f"{currency} " if currency else ""
    )


def currency_prefix(currency: str) -> str:
    return {"USD": "$", "KRW": "KRW ", "EUR": "EUR ", "JPY": "JPY "}.get(currency.upper(), "")


def fmt(value: Any, digits: int = 1) -> str:
    number = as_number(value)
    if number is None:
        return "-"
    return f"{number:,.{digits}f}"


def pct(value: Any, *, probability: bool = False) -> str:
    number = as_number(value)
    if number is None:
        return "-"
    if probability and abs(number) <= 1:
        number *= 100
    return f"{number:+.1f}%" if not probability and number > 0 else f"{number:.1f}%"


def as_number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace("%", "").replace(",", "").strip())
        except ValueError:
            return None
    return None


def metric_value(metrics: dict[str, Any], key: str) -> float | None:
    entry = metrics.get(key)
    if not isinstance(entry, dict):
        return None
    return as_number(entry.get("value"))


def metric_display(entry: Any, metric_name: str, currency: str) -> str:
    if not isinstance(entry, dict):
        return "-"
    value = entry.get("value")
    unit = str(entry.get("unit") or "").lower()
    number = as_number(value)
    if number is None:
        return "-"
    if metric_name in BILLION_METRICS:
        return f"{currency_symbol(currency)}{fmt(number, 1)}B"
    if unit in {"percent", "%"} or metric_name.endswith("yield") or "margin" in metric_name or "growth" in metric_name:
        return pct(number)
    if unit == "x" or metric_name in MULTIPLE_METRICS:
        return f"{fmt(number, 1)}x"
    return fmt(number, 2)


def metric_display_from_metrics(metrics: dict[str, Any], key: str, *, currency: str) -> str:
    return metric_display(metrics.get(key), key, currency)


def money_text(value: Any, currency: str) -> str:
    number = as_number(value)
    if number is None:
        return "-"
    if currency.upper() == "KRW":
        return f"KRW {number:,.0f}"
    symbol = "$" if currency.upper() == "USD" else f"{currency} "
    return f"{symbol}{number:,.2f}"


def percent_text(value: Any, *, probability: bool = False) -> str:
    return pct(value, probability=probability)


def format_plain_number(value: Any) -> str:
    number = as_number(value)
    if number is None:
        return "-"
    return f"{number:,.2f}".rstrip("0").rstrip(".")
