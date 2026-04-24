#!/usr/bin/env python3
"""
render-dashboard.py — Eval-only Mode C dashboard renderer.

This script is not the canonical user-facing Mode C renderer. Final delivery
must populate references/html-template.md as described in
docs/adr/0001-mode-c-rendering-strategy.ko.md.

Usage:
    python render-dashboard.py --input output/runs/<run_id>/<ticker>/analysis-result.json
    python render-dashboard.py --input output/runs/<run_id>/<ticker>/analysis-result.json --output output/reports/AAPL_C_EN_2026-03-28.html
"""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any

THIS_FILE = Path(__file__).resolve()
REPO_ROOT = THIS_FILE.parents[4]

import sys

sys.path.insert(0, str(REPO_ROOT))

from tools.analysis_contract import build_default_report_path  # noqa: E402
from tools.paths import data_path, runtime_path  # noqa: E402


def load_json(path: str | Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def resolve_path(path: str | Path) -> Path:
    return runtime_path(path)


def display_path(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)) if path.is_absolute() and path.is_relative_to(REPO_ROOT) else str(path)


def escape(value: Any) -> str:
    if value is None:
        return ""
    return html.escape(str(value))


def safe_join(items: list[str], fallback: str = "[Data unavailable]") -> str:
    filtered = [item for item in items if item]
    return "".join(filtered) if filtered else f'<div class="text-sm text-gray-500 italic">{escape(fallback)}</div>'


def currency_symbol(currency: str | None) -> str:
    mapping = {
        "USD": "$",
        "KRW": "₩",
        "EUR": "€",
        "JPY": "¥",
    }
    return mapping.get((currency or "").upper(), f"{currency} " if currency else "")


def format_decimal(value: Any, digits: int = 1) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{value:,.{digits}f}"
    return escape(value) or "—"


def format_percent(value: Any, digits: int = 1) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{value:.{digits}f}%"
    return escape(value) or "—"


def format_probability(value: Any) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{value * 100:.0f}%"
    return escape(value) or "—"


def format_abbrev_number(value: Any) -> str:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return escape(value) or "—"
    magnitude = abs(value)
    if magnitude >= 1_000_000_000_000:
        return f"{value / 1_000_000_000_000:.2f}T"
    if magnitude >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f}B"
    if magnitude >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    if magnitude >= 1_000:
        return f"{value / 1_000:.1f}K"
    return f"{value:,.0f}"


def format_metric_value(entry: Any, metric_name: str, currency: str | None) -> str:
    if not isinstance(entry, dict):
        return escape(entry) or "—"
    value = entry.get("value")
    unit = entry.get("unit")
    if value is None:
        return "—"
    if metric_name == "market_cap":
        return f"{currency_symbol(currency)}{format_abbrev_number(float(value) * 1_000_000 if unit == 'millions_usd' else value)}"
    if unit in {"percent", "%"}:
        return format_percent(value)
    if metric_name in {"pe_ratio", "ev_ebitda"} and isinstance(value, (int, float)):
        return f"{value:.1f}x"
    if isinstance(value, (int, float)):
        return format_decimal(value)
    return escape(value)


def tag_badge(display_tag: str | None) -> str:
    if not display_tag:
        return ""
    color = {
        "[Filing]": "text-blue-600",
        "[Company]": "text-indigo-600",
        "[Portal]": "text-gray-600",
        "[KR-Portal]": "text-purple-600",
        "[Calc]": "text-green-600",
        "[Est]": "text-amber-600",
    }.get(display_tag, "text-gray-500")
    return f'<code class="bg-gray-100 {color} text-xs px-1.5 py-0.5 rounded">{escape(display_tag)}</code>'


def verdict_badge(verdict: str) -> str:
    normalized = (verdict or "").lower()
    if verdict in {"비중확대"} or normalized == "overweight":
        klass = "bg-green-50 text-green-700 border-green-200"
    elif verdict in {"비중축소"} or normalized == "underweight":
        klass = "bg-red-50 text-red-700 border-red-200"
    elif verdict in {"관찰"} or normalized == "watch":
        klass = "bg-blue-50 text-blue-700 border-blue-200"
    else:
        klass = "bg-gray-100 text-gray-700 border-gray-200"
    return f'<span class="{klass} border px-4 py-1.5 rounded-lg font-bold">{escape(verdict or "Neutral")}</span>'


def rr_badge(rr_score: Any) -> str:
    if isinstance(rr_score, (int, float)) and not isinstance(rr_score, bool):
        if rr_score > 3:
            klass = "bg-green-600 text-white"
            label = "Attractive"
        elif rr_score >= 1:
            klass = "bg-gray-600 text-white"
            label = "Balanced"
        else:
            klass = "bg-red-600 text-white"
            label = "Unfavorable"
        value = f"{rr_score:.2f}"
    else:
        klass = "bg-gray-400 text-white"
        label = "Unavailable"
        value = "—"
    return (
        f'<div class="{klass} inline-flex flex-col rounded-xl px-5 py-3">'
        f'<span class="text-2xl font-bold">R/R {value}</span>'
        f'<span class="text-sm opacity-90">{label}</span>'
        "</div>"
    )


def data_confidence_badge(key_metrics: dict[str, Any]) -> str:
    counts = {"A": 0, "B": 0, "C": 0, "D": 0}
    for entry in key_metrics.values():
        if isinstance(entry, dict):
            grade = entry.get("grade")
            if grade in counts:
                counts[grade] += 1
    if counts["D"] > 0:
        klass = "bg-red-50 text-red-700 border-red-200"
        label = "Data Confidence D"
    elif counts["C"] > 0:
        klass = "bg-amber-50 text-amber-700 border-amber-200"
        label = "Data Confidence C"
    elif counts["B"] > 0:
        klass = "bg-blue-50 text-blue-700 border-blue-200"
        label = "Data Confidence B"
    else:
        klass = "bg-green-50 text-green-700 border-green-200"
        label = "Data Confidence A"
    summary = f"A:{counts['A']} B:{counts['B']} C:{counts['C']} D:{counts['D']}"
    return f'<span class="{klass} inline-flex items-center gap-2 border px-3 py-1.5 rounded-lg text-sm font-semibold">{label}<span class="text-xs opacity-80">{summary}</span></span>'


def render_kpi_tiles(key_metrics: dict[str, Any], currency: str | None) -> str:
    labels = {
        "market_cap": "Market Cap",
        "pe_ratio": "P/E",
        "ev_ebitda": "EV/EBITDA",
        "fcf_yield": "FCF Yield",
        "revenue_growth_yoy": "Revenue Growth",
        "operating_margin": "Operating Margin",
    }
    tiles = []
    for metric_name, label in labels.items():
        entry = key_metrics.get(metric_name)
        if not isinstance(entry, dict):
            continue
        tiles.append(
            "<div class=\"card p-5 border-l-4 border-blue-500\">"
            f"<p class=\"text-xs text-gray-500 mb-1\">{escape(label)}</p>"
            f"<p class=\"text-2xl font-bold text-gray-900\">{format_metric_value(entry, metric_name, currency)}</p>"
            f"<div class=\"mt-2\">{tag_badge(entry.get('display_tag') or entry.get('tag'))}</div>"
            "</div>"
        )
    return safe_join(tiles)


def render_scenarios(scenarios: dict[str, Any], currency: str | None) -> str:
    config = [
        ("bear", "Bear Case", "text-red-300 border-red-400/30", "text-red-300"),
        ("base", "Base Case", "text-blue-200 border-blue-300/50 scale-105 bg-white/15", "text-green-300"),
        ("bull", "Bull Case", "text-green-300 border-green-400/30", "text-green-300"),
    ]
    cards = []
    symbol = currency_symbol(currency)
    for key, label, border_class, return_class in config:
        payload = scenarios.get(key) if isinstance(scenarios, dict) else {}
        if not isinstance(payload, dict):
            payload = {}
        cards.append(
            f'<div class="bg-white/10 backdrop-blur-sm rounded-xl p-5 text-center border {border_class}">'
            f'<p class="text-sm font-semibold mb-1">{escape(label)}</p>'
            f'<p class="text-3xl font-extrabold text-white">{symbol}{format_decimal(payload.get("target"), 1)}</p>'
            f'<p class="{return_class} text-sm mt-1">{format_percent(payload.get("return_pct"), 1)} · {format_probability(payload.get("probability"))}</p>'
            f'<p class="text-blue-200/60 text-xs mt-2">{escape(payload.get("key_assumption") or "—")}</p>'
            "</div>"
        )
    return "".join(cards)


def render_variant_cards(sections: dict[str, Any]) -> str:
    cards = [
        ("Variant View Q1", sections.get("variant_view_q1"), "border-green-500", "bg-green-50", "text-green-700"),
        ("Variant View Q2", sections.get("variant_view_q2"), "border-blue-500", "bg-blue-50", "text-blue-700"),
        ("Variant View Q3", sections.get("variant_view_q3"), "border-amber-500", "bg-amber-50", "text-amber-700"),
    ]
    rendered = []
    for title, content, border, background, title_color in cards:
        rendered.append(
            f'<div class="card p-6 border-l-4 {border}">'
            f'<h3 class="text-lg font-bold mb-3 {title_color}">{escape(title)}</h3>'
            f'<div class="{background} rounded-lg p-4 text-sm text-gray-700 leading-6">{escape(content or "[Data unavailable]")}</div>'
            "</div>"
        )
    return "".join(rendered)


def render_precision_risks(sections: dict[str, Any]) -> str:
    risks = sections.get("precision_risks")
    if not isinstance(risks, list) or not risks:
        return '<div class="card p-5 text-sm text-gray-500 italic">[Data unavailable]</div>'
    rows = []
    for risk in risks:
        if not isinstance(risk, dict):
            continue
        rows.append(
            "<tr class=\"border-b border-gray-100 align-top\">"
            f"<td class=\"p-4 font-semibold text-gray-900\">{escape(risk.get('risk') or '—')}</td>"
            f"<td class=\"p-4 text-gray-700\">{escape(risk.get('mechanism') or '—')}</td>"
            f"<td class=\"p-4 text-gray-700\">{escape(risk.get('ebitda_impact') or '—')}</td>"
            f"<td class=\"p-4 text-gray-700\">{escape(risk.get('probability') or '—')}</td>"
            f"<td class=\"p-4 text-gray-700\">{escape(risk.get('mitigation') or '—')}</td>"
            "</tr>"
        )
    return (
        '<div class="card overflow-x-auto"><table class="w-full text-sm">'
        '<thead><tr class="bg-gray-50 text-gray-600 text-xs uppercase">'
        '<th class="text-left p-4">Risk</th><th class="text-left p-4">Mechanism</th><th class="text-left p-4">Financial Impact</th><th class="text-left p-4">Probability</th><th class="text-left p-4">Mitigation</th>'
        "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></div>"
    )


def render_valuation_tiles(sections: dict[str, Any]) -> str:
    metrics = sections.get("valuation_metrics")
    if not isinstance(metrics, list) or not metrics:
        return '<div class="card p-5 text-sm text-gray-500 italic">[Data unavailable]</div>'
    tiles = []
    for item in metrics:
        if not isinstance(item, dict):
            continue
        context = []
        if item.get("sector_avg"):
            context.append(f"Sector avg: {item['sector_avg']}")
        if item.get("assessment"):
            context.append(f"Assessment: {item['assessment']}")
        tiles.append(
            '<div class="card p-4 border-l-4 border-blue-500">'
            f'<p class="text-xs text-gray-500">{escape(item.get("metric") or "Metric")}</p>'
            f'<p class="text-xl font-bold">{escape(item.get("current") or "—")}</p>'
            f'<p class="text-xs text-gray-400 mt-1">{escape(" | ".join(context) or "Context unavailable")}</p>'
            "</div>"
        )
    return f'<div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">{safe_join(tiles)}</div>'


def render_peer_comparison(sections: dict[str, Any]) -> str:
    peers = sections.get("peer_comparison")
    if not isinstance(peers, list) or not peers:
        return '<div class="card p-5 text-sm text-gray-500 italic">[Data unavailable]</div>'
    rows = []
    for item in peers:
        if not isinstance(item, dict):
            continue
        rows.append(
            "<tr class=\"border-b border-gray-100\">"
            f"<td class=\"p-4 font-semibold\">{escape(item.get('ticker') or '—')}</td>"
            f"<td class=\"p-4\">{escape(item.get('metric') or '—')}</td>"
            f"<td class=\"p-4\">{escape(item.get('value') or item.get('current') or '—')}</td>"
            "</tr>"
        )
    return (
        '<div class="card overflow-x-auto"><table class="w-full text-sm">'
        '<thead><tr class="bg-gray-50 text-gray-600 text-xs uppercase"><th class="text-left p-4">Peer</th><th class="text-left p-4">Metric</th><th class="text-left p-4">Value</th></tr></thead>'
        "<tbody>" + "".join(rows) + "</tbody></table></div>"
    )


def render_macro_context(sections: dict[str, Any]) -> str:
    macro = sections.get("macro_context")
    if not isinstance(macro, dict):
        return '<div class="card p-5 text-sm text-gray-500 italic">[Data unavailable]</div>'
    factors = macro.get("factors")
    factor_cards = []
    if isinstance(factors, list):
        for factor in factors:
            if not isinstance(factor, dict):
                continue
            factor_cards.append(
                '<div class="rounded-xl border border-gray-200 bg-white p-4">'
                f'<p class="font-semibold text-gray-900">{escape(factor.get("factor") or "Factor")}</p>'
                f'<p class="text-sm text-gray-600 mt-2">{escape(factor.get("impact") or "—")}</p>'
                f'<p class="text-xs text-gray-400 mt-2">Probability: {escape(factor.get("probability") or "—")}</p>'
                "</div>"
            )
    return (
        '<div class="card p-6">'
        f'<p class="text-sm text-gray-700 leading-6">{escape(macro.get("narrative") or "[Data unavailable]")}</p>'
        f'<div class="grid grid-cols-1 md:grid-cols-2 gap-3 mt-4">{safe_join(factor_cards, fallback="No factor cards available.")}</div>'
        "</div>"
    )


def render_portfolio_and_watchouts(sections: dict[str, Any], catalysts: list[Any] | None) -> str:
    wrong_items = sections.get("what_would_make_me_wrong")
    wrong_list = []
    if isinstance(wrong_items, list):
        for item in wrong_items:
            wrong_list.append(f"<li>{escape(item)}</li>")
    catalyst_rows = []
    if isinstance(catalysts, list):
        for item in catalysts:
            if not isinstance(item, dict):
                continue
            catalyst_rows.append(
                "<tr class=\"border-b border-gray-100\">"
                f"<td class=\"p-3\">{escape(item.get('date') or '—')}</td>"
                f"<td class=\"p-3\">{escape(item.get('description') or '—')}</td>"
                f"<td class=\"p-3\">{escape(item.get('significance') or '—')}</td>"
                "</tr>"
            )
    return (
        '<div class="grid grid-cols-1 lg:grid-cols-2 gap-4">'
        '<div class="card p-6">'
        '<h3 class="text-lg font-bold text-gray-900 mb-3">Portfolio Strategy</h3>'
        f'<p class="text-sm text-gray-700 leading-6">{escape(sections.get("portfolio_strategy") or "[Data unavailable]")}</p>'
        '</div>'
        '<div class="card p-6">'
        '<h3 class="text-lg font-bold text-gray-900 mb-3">What Would Make Me Wrong</h3>'
        f'<ul class="list-disc pl-5 space-y-2 text-sm text-gray-700">{safe_join(wrong_list, fallback="[Data unavailable]")}</ul>'
        "</div>"
        '<div class="card p-6 lg:col-span-2">'
        '<h3 class="text-lg font-bold text-gray-900 mb-3">Upcoming Catalysts</h3>'
        '<div class="overflow-x-auto"><table class="w-full text-sm">'
        '<thead><tr class="bg-gray-50 text-gray-600 text-xs uppercase"><th class="text-left p-3">Date</th><th class="text-left p-3">Event</th><th class="text-left p-3">Significance</th></tr></thead>'
        f'<tbody>{safe_join(catalyst_rows, fallback="<tr><td class=\"p-3 text-gray-500 italic\" colspan=\"3\">[Data unavailable]</td></tr>")}</tbody>'
        '</table></div></div></div>'
    )


def build_dashboard_html(data: dict[str, Any]) -> str:
    ticker = data.get("ticker") or "UNKNOWN"
    company_name = data.get("company_name") or ticker
    currency = data.get("currency") or "USD"
    output_language = data.get("output_language") or "en"
    sections = data.get("sections") if isinstance(data.get("sections"), dict) else {}
    key_metrics = data.get("key_metrics") if isinstance(data.get("key_metrics"), dict) else {}
    scenarios = data.get("scenarios") if isinstance(data.get("scenarios"), dict) else {}

    price_text = f"{currency_symbol(currency)}{format_decimal(data.get('price_at_analysis'), 2)}"
    analysis_date = escape(data.get("analysis_date") or "—")
    company_type = escape(data.get("company_type") or "Deep Dive")
    title = f"{escape(company_name)} ({escape(ticker)}) — Investment Dashboard"
    font_link = (
        '<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700&display=swap" rel="stylesheet">'
        if output_language == "ko"
        else ""
    )
    return f"""<!DOCTYPE html>
<html lang="{escape(output_language)}">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/css/all.min.css">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
  {font_link}
  <style>
    * {{ font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Noto Sans KR', sans-serif; }}
    .card {{ background: #fff; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.06); }}
    .card:hover {{ box-shadow: 0 6px 18px rgba(0,0,0,0.08); }}
  </style>
</head>
<body class="bg-gray-50 text-gray-800">
  <header style="background: linear-gradient(135deg, #0d1b38 0%, #1e3f80 30%, #2a56b0 60%, #3367d6 100%);">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 py-8">
      <div class="flex flex-col md:flex-row justify-between gap-6">
        <div>
          <p class="text-blue-200 text-sm font-semibold uppercase tracking-[0.2em]">Mode C Dashboard</p>
          <h1 class="text-3xl md:text-4xl font-extrabold text-white mt-2">{escape(company_name)}</h1>
          <p class="text-blue-200 mt-2">{escape(ticker)} · {company_type}</p>
          <div class="flex flex-wrap items-center gap-3 mt-5">
            <span class="text-4xl font-extrabold text-white">{price_text}</span>
            {verdict_badge(data.get("verdict") or "Neutral")}
            {rr_badge(data.get("rr_score"))}
          </div>
        </div>
        <div class="flex flex-col items-start md:items-end gap-3">
          {data_confidence_badge(key_metrics)}
          <div class="text-sm text-blue-200/90 space-y-1">
            <p>Analysis Date: {analysis_date}</p>
            <p>Data Mode: {escape(data.get("data_mode") or "—")}</p>
            <p>Currency: {escape(currency)}</p>
          </div>
        </div>
      </div>
    </div>
  </header>

  <main class="max-w-7xl mx-auto px-4 sm:px-6 py-8 space-y-8">
    <section class="rounded-2xl overflow-hidden" style="background: linear-gradient(135deg, #0d1b38, #1e3f80, #2a56b0, #142a55);">
      <div class="p-6 sm:p-8">
        <h2 class="text-lg font-bold text-blue-200 mb-2"><i class="fa-solid fa-bullseye mr-2"></i>Scenario Valuation</h2>
        <p class="text-blue-200/60 text-sm mb-6">{escape(sections.get("variant_view_q1") or "Scenario framing unavailable.")}</p>
        <div class="grid grid-cols-1 md:grid-cols-3 gap-4">{render_scenarios(scenarios, currency)}</div>
      </div>
    </section>

    <section>
      <h2 class="text-xl font-bold text-gray-900 mb-4"><i class="fa-solid fa-chart-column mr-2 text-blue-500"></i>Key Metrics</h2>
      <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-5 gap-4">{render_kpi_tiles(key_metrics, currency)}</div>
    </section>

    <section>
      <h2 class="text-xl font-bold text-gray-900 mb-4"><i class="fa-solid fa-scale-balanced mr-2 text-blue-500"></i>Variant View</h2>
      <div class="grid grid-cols-1 lg:grid-cols-3 gap-4">{render_variant_cards(sections)}</div>
    </section>

    <section>
      <h2 class="text-xl font-bold text-gray-900 mb-4"><i class="fa-solid fa-triangle-exclamation mr-2 text-blue-500"></i>Precision Risks</h2>
      {render_precision_risks(sections)}
    </section>

    <section>
      <h2 class="text-xl font-bold text-gray-900 mb-4"><i class="fa-solid fa-calculator mr-2 text-blue-500"></i>Valuation</h2>
      {render_valuation_tiles(sections)}
    </section>

    <section class="grid grid-cols-1 xl:grid-cols-2 gap-4">
      <div>
        <h2 class="text-xl font-bold text-gray-900 mb-4"><i class="fa-solid fa-users mr-2 text-blue-500"></i>Peer Comparison</h2>
        {render_peer_comparison(sections)}
      </div>
      <div>
        <h2 class="text-xl font-bold text-gray-900 mb-4"><i class="fa-solid fa-globe mr-2 text-blue-500"></i>Macro Context</h2>
        {render_macro_context(sections)}
      </div>
    </section>

    <section>
      <h2 class="text-xl font-bold text-gray-900 mb-4"><i class="fa-solid fa-compass mr-2 text-blue-500"></i>Portfolio Strategy & Catalysts</h2>
      {render_portfolio_and_watchouts(sections, data.get("upcoming_catalysts"))}
    </section>

    <section>
      <h2 class="text-xl font-bold text-gray-900 mb-4"><i class="fa-solid fa-chart-line mr-2 text-blue-500"></i>Charts & Trend Data</h2>
      <div class="card p-6 text-sm text-gray-500 italic">Price history and quarterly chart arrays are not present in this fixture, so the dashboard shows structured narrative sections only.</div>
    </section>
  </main>

  <footer class="border-t border-gray-200 mt-10">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 py-6 text-xs text-gray-500 space-y-2">
      <p><strong>Disclaimer:</strong> This report is generated by an AI research assistant for informational purposes only. It does not constitute investment advice.</p>
      <p>Generated from run-local analysis-result.json on {analysis_date}.</p>
    </div>
  </footer>
</body>
</html>
"""


def generate_dashboard(data: dict[str, Any], output_path: str | Path) -> str:
    html_text = build_dashboard_html(data)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(html_text, encoding="utf-8")
    return str(destination)


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a Mode C dashboard HTML file from analysis-result.json")
    parser.add_argument("--input", required=True, help="Path to analysis-result.json")
    parser.add_argument("--output", help="Optional output HTML path")
    args = parser.parse_args()

    input_path = resolve_path(args.input)
    data = load_json(input_path)
    output_path = (
        resolve_path(args.output)
        if args.output
        else resolve_path(
            build_default_report_path(
                ticker=data.get("ticker"),
                output_mode="C",
                output_language=data.get("output_language"),
                analysis_date=data.get("analysis_date"),
            )
            or str(data_path("reports", "dashboard.html"))
        )
    )
    rendered_path = generate_dashboard(data, output_path)
    print(
        json.dumps(
            {
                "input_path": display_path(input_path),
                "output_path": display_path(Path(rendered_path)),
                "warning": "eval-only renderer; do not use for final Mode C delivery",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
