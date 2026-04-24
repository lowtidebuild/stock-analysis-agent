#!/usr/bin/env python3
"""
render-briefing.py — Scriptable Mode A briefing renderer.

Usage:
    python render-briefing.py --input output/runs/<run_id>/<ticker>/analysis-result.json
    python render-briefing.py --input output/runs/<run_id>/<ticker>/analysis-result.json --output output/reports/NVDA_A_en_2026-03-13.html
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
from tools.source_profile import source_confidence_label  # noqa: E402


def load_json(path: str | Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def resolve_path(path: str | Path) -> Path:
    return runtime_path(path)


def display_path(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)) if path.is_absolute() and path.is_relative_to(REPO_ROOT) else str(path)


def escape(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def currency_symbol(currency: str | None) -> str:
    mapping = {"USD": "$", "KRW": "₩", "EUR": "€", "JPY": "¥"}
    return mapping.get((currency or "").upper(), f"{currency} " if currency else "")


def format_number(value: Any, digits: int = 1) -> str:
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


def tag_badge(metric: dict[str, Any]) -> str:
    display_tag = metric.get("display_tag") or metric.get("tag")
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


def rr_badge(rr_score: Any) -> str:
    if isinstance(rr_score, (int, float)) and not isinstance(rr_score, bool):
        if rr_score > 3:
            klass = "bg-green-600 text-white"
            label = "Attractive"
        elif rr_score >= 1:
            klass = "bg-yellow-500 text-white"
            label = "Balanced"
        else:
            klass = "bg-red-600 text-white"
            label = "Unfavorable"
        value = f"{rr_score:.2f}"
    else:
        klass = "bg-gray-500 text-white"
        label = "Unavailable"
        value = "—"
    return f'<div class="{klass} rounded-xl px-5 py-3"><div class="text-2xl font-bold">R/R {value}</div><div class="text-sm opacity-90">{label}</div></div>'


def verdict_badge(verdict: str | None) -> str:
    normalized = (verdict or "").lower()
    if verdict == "비중확대" or normalized == "overweight":
        klass = "bg-green-50 text-green-700 border-green-200"
    elif verdict == "비중축소" or normalized == "underweight":
        klass = "bg-red-50 text-red-700 border-red-200"
    else:
        klass = "bg-gray-100 text-gray-700 border-gray-200"
    return f'<span class="{klass} border font-bold px-4 py-1.5 rounded-lg">{escape(verdict or "Neutral")}</span>'


def fallback_action_signal(verdict: str | None, rr_score: Any) -> str:
    if isinstance(rr_score, (int, float)) and rr_score > 3:
        return "Add on confirmation of the next catalyst while protecting against event volatility."
    if isinstance(rr_score, (int, float)) and rr_score < 1:
        return "Wait for a materially better entry or a cleaner catalyst setup."
    if verdict and (verdict.lower() == "overweight" or verdict == "비중확대"):
        return "Build exposure gradually and reassess after the next reported catalyst."
    return "Stay selective until the next catalyst clarifies the setup."


def render_kpis(key_metrics: dict[str, Any], currency: str | None) -> str:
    if not isinstance(key_metrics, dict) or not key_metrics:
        return '<div class="text-sm text-gray-500 italic">KPI data unavailable.</div>'
    tiles = []
    for name, metric in list(key_metrics.items())[:3]:
        if not isinstance(metric, dict):
            continue
        value = metric.get("value")
        if name in {"pe_forward", "pe_ratio", "ev_ebitda"} and isinstance(value, (int, float)):
            value_text = f"{value:.1f}x"
        elif name in {"market_cap"} and isinstance(value, (int, float)):
            value_text = f"{currency_symbol(currency)}{value:,.0f}"
        elif isinstance(value, (int, float)):
            value_text = f"{value:,.2f}"
        else:
            value_text = escape(value) or "—"
        label = name.replace("_", " ").title()
        tiles.append(
            '<div class="bg-gray-900/70 rounded-xl p-4 border border-white/10">'
            f'<div class="text-xs uppercase tracking-[0.2em] text-blue-200/70">{escape(label)}</div>'
            f'<div class="text-2xl font-bold text-white mt-2">{value_text}</div>'
            f'<div class="mt-3 flex items-center gap-2">{tag_badge(metric)}<span class="text-xs text-blue-200/70">Grade {escape(metric.get("grade") or "—")}</span></div>'
            '</div>'
        )
    return "".join(tiles)


def render_scenarios(scenarios: dict[str, Any], currency: str | None) -> str:
    if not isinstance(scenarios, dict):
        return '<p class="text-sm text-gray-500 italic">Scenario data unavailable.</p>'
    order = [("bull", "🐂 Bull"), ("base", "📊 Base"), ("bear", "🐻 Bear")]
    lines = []
    symbol = currency_symbol(currency)
    for key, label in order:
        scenario = scenarios.get(key)
        if not isinstance(scenario, dict):
            continue
        lines.append(
            f'<div class="text-sm text-gray-100 leading-6"><span class="font-semibold">{escape(label)}:</span> '
            f'{symbol}{format_number(scenario.get("target"), 1)} '
            f'({format_percent(scenario.get("return_pct"), 1)}) '
            f'· Prob {format_probability(scenario.get("probability"))} '
            f'· {escape(scenario.get("key_assumption") or "—")}</div>'
        )
    return "".join(lines) or '<p class="text-sm text-gray-500 italic">Scenario data unavailable.</p>'


def render_timeline(events: Any, empty_text: str) -> str:
    if not isinstance(events, list) or not events:
        return f'<div class="rounded-xl border border-dashed border-gray-300 p-4 text-sm text-gray-500 italic">{escape(empty_text)}</div>'
    rows = []
    for event in events:
        if not isinstance(event, dict):
            continue
        rows.append(
            '<div class="relative pl-6 pb-5">'
            '<div class="absolute left-0 top-1 h-3 w-3 rounded-full bg-blue-500"></div>'
            '<div class="text-xs uppercase tracking-[0.2em] text-gray-400">'
            f'{escape(event.get("date") or "Date TBD")} · {escape(event.get("significance") or "event")}'
            '</div>'
            f'<div class="font-semibold text-gray-900 mt-1">{escape(event.get("event") or event.get("description") or "Event")}</div>'
            f'<div class="text-sm text-gray-600 mt-1">{escape(event.get("narrative") or event.get("description") or "Narrative unavailable.")}</div>'
            '</div>'
        )
    return "".join(rows)


def build_briefing_html(data: dict[str, Any]) -> str:
    sections = data.get("sections") if isinstance(data.get("sections"), dict) else {}
    key_metrics = data.get("key_metrics") if isinstance(data.get("key_metrics"), dict) else {}
    scenarios = data.get("scenarios") if isinstance(data.get("scenarios"), dict) else {}
    ticker = data.get("ticker") or "UNKNOWN"
    company_name = data.get("company_name") or ticker
    currency = data.get("currency") or "USD"
    thesis = sections.get("one_line_thesis")
    if not isinstance(thesis, str) or not thesis:
        thesis = "Legacy sample migration preserved the verdict and scenario math, but no explicit one-line thesis was available."
    action_signal = sections.get("action_signal")
    if not isinstance(action_signal, str) or not action_signal:
        action_signal = fallback_action_signal(data.get("verdict"), data.get("rr_score"))
    top_risk = None
    if isinstance(data.get("top_risks"), list) and data["top_risks"]:
        top_risk = data["top_risks"][0]
    if not top_risk:
        top_risk = "Top risk detail unavailable in the promoted sample."
    catalysts = data.get("upcoming_catalysts") if isinstance(data.get("upcoming_catalysts"), list) else []
    next_catalyst = catalysts[0] if catalysts else None
    timeline_past = sections.get("timeline_past")
    timeline_future = sections.get("timeline_future")
    pattern_detection = sections.get("pattern_detection")
    migration_notes = ((data.get("migration") or {}).get("notes") if isinstance(data.get("migration"), dict) else []) or []
    next_catalyst_payload = next_catalyst if isinstance(next_catalyst, dict) else {}

    korean_font = (
        '<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700&display=swap" rel="stylesheet">'
        if data.get("output_language") == "ko"
        else ""
    )
    return f"""<!DOCTYPE html>
<html lang="{escape(data.get('output_language') or 'en')}">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{escape(ticker)} Quick Briefing</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
  {korean_font}
  <style>
    * {{ font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Noto Sans KR', sans-serif; }}
    .glass {{ background: rgba(17, 24, 39, 0.72); backdrop-filter: blur(10px); }}
  </style>
</head>
<body class="bg-gray-950 text-gray-100 min-h-screen">
  <main class="max-w-6xl mx-auto px-4 sm:px-6 py-8 space-y-8">
    <section class="glass rounded-3xl border border-white/10 overflow-hidden">
      <div class="bg-gradient-to-br from-slate-900 via-blue-950 to-blue-700 p-6 sm:p-8">
        <div class="flex flex-col lg:flex-row justify-between gap-6">
          <div class="space-y-4">
            <div>
              <p class="text-blue-200 uppercase tracking-[0.3em] text-xs">Quick Briefing</p>
              <h1 class="text-3xl sm:text-4xl font-extrabold mt-2">{escape(company_name)}</h1>
              <p class="text-blue-200 mt-2">{escape(ticker)} · {escape(data.get("analysis_date") or "—")}</p>
            </div>
            <div class="flex flex-wrap items-center gap-3">
              <span class="text-4xl font-extrabold">{currency_symbol(currency)}{format_number(data.get("price_at_analysis"), 2)}</span>
              {verdict_badge(data.get("verdict"))}
              {rr_badge(data.get("rr_score"))}
            </div>
          </div>
          <div class="w-full lg:max-w-sm">
            <div class="rounded-2xl border border-white/10 bg-white/5 p-5">
              <p class="text-xs uppercase tracking-[0.3em] text-blue-200/80">One-line Thesis</p>
              <p class="mt-3 text-sm leading-6 text-gray-100">{escape(thesis)}</p>
            </div>
          </div>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mt-8">
          {render_kpis(key_metrics, currency)}
        </div>

        <div class="mt-8 rounded-2xl border border-white/10 bg-white/5 p-5">
          <h2 class="text-lg font-bold text-white">Scenario Summary</h2>
          <div class="mt-4 space-y-2">{render_scenarios(scenarios, currency)}</div>
        </div>

        <div class="grid grid-cols-1 lg:grid-cols-2 gap-4 mt-6">
          <div class="rounded-2xl border border-white/10 bg-white/5 p-5">
            <p class="text-xs uppercase tracking-[0.3em] text-rose-200/80">Top Risk</p>
            <p class="mt-3 text-sm leading-6">{escape(top_risk)}</p>
          </div>
          <div class="rounded-2xl border border-white/10 bg-white/5 p-5">
            <p class="text-xs uppercase tracking-[0.3em] text-emerald-200/80">Next Catalyst & Action</p>
            <p class="mt-3 text-sm leading-6">
              {escape(next_catalyst_payload.get("description") or "No dated catalyst captured in this run.")}
              {' · ' + escape(next_catalyst_payload.get("date")) if next_catalyst_payload.get("date") else ''}
            </p>
            <p class="mt-3 text-sm text-blue-100">{escape(action_signal)}</p>
          </div>
        </div>
      </div>
    </section>

    <section class="bg-white rounded-3xl shadow-sm border border-gray-200 overflow-hidden">
      <div class="px-6 sm:px-8 py-6 border-b border-gray-200">
        <h2 class="text-2xl font-bold text-gray-900">180-Day Event Timeline</h2>
        <p class="text-sm text-gray-500 mt-2">Past and upcoming events are shown when they exist in the run-local analysis artifact.</p>
      </div>
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-0">
        <div class="p-6 sm:p-8 border-b lg:border-b-0 lg:border-r border-gray-200">
          <h3 class="text-lg font-bold text-gray-900 mb-4">Past 90 Days</h3>
          {render_timeline(timeline_past, "Past-event timeline was not present in this promoted sample.")}
        </div>
        <div class="p-6 sm:p-8">
          <h3 class="text-lg font-bold text-gray-900 mb-4">Forward 90 Days</h3>
          {render_timeline(timeline_future or catalysts, "Forward-event timeline was not present; showing catalyst list when available.")}
        </div>
      </div>
      <div class="px-6 sm:px-8 py-5 bg-gray-50 border-t border-gray-200">
        <p class="text-xs uppercase tracking-[0.3em] text-gray-400">Pattern Detection</p>
        <p class="mt-2 text-sm text-gray-600">{escape(pattern_detection or "No statistically supported event pattern was stored in this run.")}</p>
      </div>
    </section>

    <section class="bg-white rounded-3xl shadow-sm border border-gray-200 p-6 sm:p-8">
      <h3 class="text-lg font-bold text-gray-900">Run Notes</h3>
      <ul class="mt-4 list-disc pl-5 space-y-2 text-sm text-gray-600">
        <li>Output mode: {escape(data.get("output_mode") or "A")} | Source confidence: {escape(source_confidence_label(data))}</li>
        <li>Report path: {escape(data.get("report_path") or "—")}</li>
        <li>{escape(migration_notes[0] if migration_notes else "No migration note recorded.")}</li>
      </ul>
    </section>
  </main>

  <footer class="max-w-6xl mx-auto px-4 sm:px-6 pb-8">
    <div class="text-xs text-gray-500 border-t border-white/10 pt-4">
      <p><strong>Disclaimer:</strong> This report is generated by an AI research assistant for informational purposes only. It does not constitute investment advice.</p>
      <p class="mt-2">Generated from run-local analysis-result.json on {escape(data.get("analysis_date") or "—")}.</p>
    </div>
  </footer>
</body>
</html>
"""


def generate_briefing(data: dict[str, Any], output_path: str | Path) -> str:
    html_text = build_briefing_html(data)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(html_text, encoding="utf-8")
    return str(destination)


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a Mode A briefing HTML file from analysis-result.json")
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
                output_mode="A",
                output_language=data.get("output_language"),
                analysis_date=data.get("analysis_date"),
            )
            or str(data_path("reports", "briefing.html"))
        )
    )
    rendered_path = generate_briefing(data, output_path)
    print(
        json.dumps(
            {
                "input_path": display_path(input_path),
                "output_path": display_path(Path(rendered_path)),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
