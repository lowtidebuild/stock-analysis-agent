#!/usr/bin/env python3
"""
render-comparison.py — Scriptable Mode B peer comparison renderer.

Usage:
    python render-comparison.py --input output/runs/<run_id>/<ticker>/analysis-result.json
    python render-comparison.py --input output/runs/<run_id>/<ticker>/analysis-result.json --output output/reports/AAPL_MSFT_GOOGL_B_EN_2026-03-28.html
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


def load_json(path: str | Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def resolve_path(path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else REPO_ROOT / candidate


def display_path(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)) if path.is_absolute() and path.is_relative_to(REPO_ROOT) else str(path)


def escape(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def is_korean(language: str | None) -> bool:
    return (language or "").lower().startswith("ko")


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
    return "—"


def format_currency_value(value: Any, currency: str | None) -> str:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return escape(value) or "—"
    digits = 0 if (currency or "").upper() == "KRW" else 2
    return f"{currency_symbol(currency)}{value:,.{digits}f}"


def format_unit_value(value: Any, unit: str | None, currency: str | None = None) -> str:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return escape(value) or "—"
    normalized_unit = (unit or "").lower()
    if normalized_unit in {"percent", "%"}:
        return format_percent(value)
    if normalized_unit in {"x", "multiple"}:
        return f"{value:.2f}x"
    if normalized_unit == "조원":
        return f"{value:,.1f}조원" if abs(value) < 100 else f"{value:,.0f}조원"
    if normalized_unit == "억원":
        return f"{value:,.0f}억원"
    if normalized_unit == "million_usd":
        return f"${value:,.1f}M"
    if normalized_unit == "billions_usd":
        return f"${value:,.2f}B"
    if normalized_unit in {"usd", "krw", "eur", "jpy"}:
        return format_currency_value(value, unit.upper())
    if normalized_unit:
        return f"{format_number(value)} {escape(unit)}"
    if currency:
        return format_currency_value(value, currency)
    return format_number(value)


def tag_badge(tag: str | None) -> str:
    if not tag:
        return ""
    klass = {
        "[Filing]": "bg-blue-50 text-blue-700 border-blue-200",
        "[Company]": "bg-indigo-50 text-indigo-700 border-indigo-200",
        "[Portal]": "bg-gray-100 text-gray-700 border-gray-200",
        "[KR-Portal]": "bg-sky-50 text-sky-700 border-sky-200",
        "[Calc]": "bg-emerald-50 text-emerald-700 border-emerald-200",
        "[Est]": "bg-amber-50 text-amber-700 border-amber-200",
        "[Macro]": "bg-violet-50 text-violet-700 border-violet-200",
    }.get(tag, "bg-gray-100 text-gray-600 border-gray-200")
    return f'<code class="{klass} border text-[10px] px-1.5 py-0.5 rounded-full">{escape(tag)}</code>'


def rr_badge(rr_score: Any) -> str:
    if isinstance(rr_score, (int, float)) and not isinstance(rr_score, bool):
        if rr_score > 3:
            klass = "bg-green-50 text-green-700 border-green-200"
        elif rr_score >= 1:
            klass = "bg-slate-100 text-slate-700 border-slate-200"
        else:
            klass = "bg-red-50 text-red-700 border-red-200"
        label = f"{rr_score:.2f}"
    else:
        klass = "bg-gray-100 text-gray-500 border-gray-200"
        label = "N/A"
    return f'<span class="{klass} border text-sm px-3 py-1 rounded-full font-bold">{escape(label)}</span>'


def verdict_badge(verdict: str | None) -> str:
    normalized = (verdict or "").lower()
    if verdict == "비중확대" or normalized == "overweight":
        klass = "bg-green-50 text-green-700 border-green-200"
    elif verdict == "비중축소" or normalized == "underweight":
        klass = "bg-red-50 text-red-700 border-red-200"
    elif verdict == "관찰" or normalized == "watch":
        klass = "bg-blue-50 text-blue-700 border-blue-200"
    else:
        klass = "bg-slate-100 text-slate-700 border-slate-200"
    return f'<span class="{klass} border text-xs px-3 py-1 rounded-full font-bold">{escape(verdict or "Neutral")}</span>'


def data_mode_badge(peer: dict[str, Any], korean: bool) -> str:
    market = (peer.get("analysis") or {}).get("market")
    data_mode = (peer.get("analysis") or {}).get("data_mode")
    ticker = peer.get("ticker")
    if market == "KR":
        label = f"{ticker} · 한국주식" if korean else f"{ticker} · Korean Stock"
        klass = "bg-sky-500/20 text-sky-100"
    elif data_mode == "enhanced":
        label = f"{ticker} · 강화 모드" if korean else f"{ticker} · Enhanced"
        klass = "bg-green-500/20 text-green-100"
    else:
        label = f"{ticker} · 표준 모드" if korean else f"{ticker} · Standard"
        klass = "bg-amber-500/20 text-amber-100"
    return f'<span class="{klass} text-xs px-3 py-1 rounded-full">{escape(label)}</span>'


def parse_risk_label(item: Any) -> str | None:
    if isinstance(item, str) and item:
        return item
    if isinstance(item, dict):
        for key in ("risk", "title", "description", "name"):
            value = item.get(key)
            if isinstance(value, str) and value:
                return value
    return None


def parse_catalyst_label(item: Any) -> str | None:
    if isinstance(item, str) and item:
        return item
    if isinstance(item, dict):
        for key in ("description", "event", "event_type", "name"):
            value = item.get(key)
            if isinstance(value, str) and value:
                return value
    return None


def collect_unique_tickers(main_analysis: dict[str, Any]) -> list[str]:
    ordered: list[str] = []
    for candidate in [main_analysis.get("ticker"), *(main_analysis.get("peer_tickers") or [])]:
        if not isinstance(candidate, str):
            continue
        cleaned = candidate.upper()
        if cleaned and cleaned not in ordered:
            ordered.append(cleaned)
    return ordered


def score_candidate(path: Path, *, analysis_date: str | None, output_mode: str | None) -> tuple[int, str]:
    try:
        payload = load_json(path)
    except Exception:
        return (99, str(path))
    penalty = 0
    if payload.get("analysis_date") != analysis_date:
        penalty += 10
    if payload.get("output_mode") != output_mode:
        penalty += 5
    return (penalty, str(path))


def find_analysis_path_for_ticker(
    ticker: str,
    main_analysis: dict[str, Any],
) -> Path | None:
    run_context = main_analysis.get("run_context") if isinstance(main_analysis.get("run_context"), dict) else {}
    artifact_root = run_context.get("artifact_root")
    if isinstance(artifact_root, str):
        same_run = REPO_ROOT / Path(artifact_root).parent.parent / ticker / "analysis-result.json"
        if same_run.exists():
            return same_run

    runs_root = REPO_ROOT / "output" / "runs"
    candidates = list(runs_root.glob(f"*/{ticker}/analysis-result.json"))
    if not candidates:
        return None
    analysis_date = main_analysis.get("analysis_date")
    output_mode = main_analysis.get("output_mode")
    return min(candidates, key=lambda path: score_candidate(path, analysis_date=analysis_date, output_mode=output_mode))


def find_validated_path_for_ticker(ticker: str, analysis_path: Path | None) -> Path | None:
    if analysis_path is not None:
        sibling = analysis_path.with_name("validated-data.json")
        if sibling.exists():
            return sibling
    run_candidates = sorted((REPO_ROOT / "output" / "runs").glob(f"*/{ticker}/validated-data.json"))
    if run_candidates:
        return run_candidates[-1]
    legacy = REPO_ROOT / "output" / "data" / ticker / "validated-data.json"
    return legacy if legacy.exists() else None


def fallback_metric_from_analysis(analysis: dict[str, Any], key: str) -> dict[str, Any] | None:
    mapping = {
        "price": {"value": analysis.get("price_at_analysis"), "currency": analysis.get("currency"), "display_tag": "[Portal]"},
        "market_cap": {"value": analysis.get("market_cap_조원"), "unit": "조원", "display_tag": "[Portal]"},
        "per": {"value": analysis.get("per"), "unit": "x", "display_tag": "[Portal]"},
        "ev_ebitda": {"value": analysis.get("ev_ebitda"), "unit": "x", "display_tag": "[Portal]"},
        "pbr": {"value": analysis.get("pbr"), "unit": "x", "display_tag": "[Portal]"},
        "roe": {"value": analysis.get("roe"), "unit": "percent", "display_tag": "[Portal]"},
        "operating_margin": {"value": analysis.get("operating_margin"), "unit": "percent", "display_tag": "[Portal]"},
        "revenue_ttm": {"value": analysis.get("revenue_ttm_조원"), "unit": "조원", "display_tag": "[Portal]"},
        "rr_score": {"value": analysis.get("rr_score"), "display_tag": "[Calc]"},
        "verdict": {"value": analysis.get("verdict")},
    }
    entry = mapping.get(key)
    if not isinstance(entry, dict):
        return None
    return entry if entry.get("value") is not None else None


def metric_entry(peer: dict[str, Any], key: str) -> dict[str, Any] | None:
    if key == "rr_score":
        return {"value": (peer.get("analysis") or {}).get("rr_score"), "display_tag": "[Calc]"}
    if key == "verdict":
        return {"value": (peer.get("analysis") or {}).get("verdict")}

    validated = peer.get("validated_metrics") if isinstance(peer.get("validated_metrics"), dict) else {}
    if isinstance(validated.get(key), dict):
        return validated[key]

    analysis_metrics = (peer.get("analysis") or {}).get("key_metrics")
    if isinstance(analysis_metrics, dict) and isinstance(analysis_metrics.get(key), dict):
        return analysis_metrics[key]

    return fallback_metric_from_analysis(peer.get("analysis") or {}, key)


def metric_numeric_value(peer: dict[str, Any], key: str) -> float | None:
    entry = metric_entry(peer, key)
    if not isinstance(entry, dict):
        return None
    value = entry.get("value")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def metric_display(peer: dict[str, Any], key: str) -> str:
    entry = metric_entry(peer, key)
    if not isinstance(entry, dict):
        return '<span class="text-gray-400">—</span>'
    if entry.get("grade") == "D" or entry.get("value") is None:
        return '<span class="text-gray-400">—</span>'

    value = entry.get("value")
    currency = entry.get("currency") or (peer.get("analysis") or {}).get("currency")
    unit = entry.get("unit")
    if key == "price":
        return format_currency_value(value, currency)
    if key in {"per", "ev_ebitda", "pbr"} and isinstance(value, (int, float)):
        return f"{value:.2f}x"
    if key == "verdict":
        return verdict_badge(str(value))
    if key == "rr_score":
        return rr_badge(value)
    return format_unit_value(value, unit, currency=currency)


def metric_tags(peers: list[dict[str, Any]], key: str) -> list[str]:
    tags: list[str] = []
    for peer in peers:
        entry = metric_entry(peer, key)
        if not isinstance(entry, dict):
            continue
        tag = entry.get("display_tag") or entry.get("tag")
        if isinstance(tag, str) and tag and tag not in tags:
            tags.append(tag)
    return tags


def winner_for_metric(peers: list[dict[str, Any]], key: str, mode: str) -> str | None:
    values: list[tuple[str, float]] = []
    for peer in peers:
        numeric = metric_numeric_value(peer, key)
        if numeric is None:
            continue
        values.append((peer["ticker"], numeric))
    if not values:
        return None
    if mode == "high":
        return max(values, key=lambda item: item[1])[0]
    if mode == "low":
        return min(values, key=lambda item: item[1])[0]
    return None


def base_case(peer: dict[str, Any]) -> dict[str, Any]:
    scenarios = (peer.get("analysis") or {}).get("scenarios")
    return scenarios.get("base", {}) if isinstance(scenarios, dict) else {}


def base_return(peer: dict[str, Any]) -> float | None:
    base = base_case(peer)
    value = base.get("return_pct")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    target = base.get("target")
    price = (peer.get("analysis") or {}).get("price_at_analysis")
    if isinstance(target, (int, float)) and isinstance(price, (int, float)) and price:
        return ((target / price) - 1) * 100
    return None


def primary_catalyst(peer: dict[str, Any]) -> str | None:
    catalysts = (peer.get("analysis") or {}).get("upcoming_catalysts")
    if isinstance(catalysts, list):
        for item in catalysts:
            label = parse_catalyst_label(item)
            if label:
                return label
    return None


def primary_risk(peer: dict[str, Any]) -> str | None:
    risks = (peer.get("analysis") or {}).get("top_risks")
    if isinstance(risks, list):
        for item in risks:
            label = parse_risk_label(item)
            if label:
                return label
    return None


def peer_label(peer: dict[str, Any]) -> str:
    analysis = peer.get("analysis") or {}
    company = analysis.get("company_name")
    return f"{peer['ticker']} ({company})" if company else peer["ticker"]


def collect_peer_payloads(main_analysis: dict[str, Any]) -> list[dict[str, Any]]:
    peers: list[dict[str, Any]] = []
    seen: set[str] = set()
    for ticker in collect_unique_tickers(main_analysis):
        if ticker in seen:
            continue
        seen.add(ticker)
        analysis_path = find_analysis_path_for_ticker(ticker, main_analysis)
        if ticker == (main_analysis.get("ticker") or "").upper():
            analysis = main_analysis
        elif analysis_path is not None:
            analysis = load_json(analysis_path)
        else:
            analysis = {"ticker": ticker, "peer_tickers": [], "output_mode": "B"}

        validated_path = find_validated_path_for_ticker(ticker, analysis_path)
        validated = load_json(validated_path) if validated_path is not None else {}
        peers.append(
            {
                "ticker": ticker,
                "analysis": analysis,
                "validated_metrics": validated.get("validated_metrics") if isinstance(validated, dict) else {},
            }
        )
    return peers


METRIC_ROWS = [
    ("Price & Size", "price", "Current Price", "none"),
    ("Price & Size", "market_cap", "Market Cap", "none"),
    ("Valuation", "per", "P/E (TTM)", "low"),
    ("Valuation", "ev_ebitda", "EV/EBITDA", "low"),
    ("Valuation", "pbr", "P/B", "low"),
    ("Growth & Profitability", "revenue_growth_yoy", "Revenue Growth", "high"),
    ("Growth & Profitability", "operating_margin", "Operating Margin", "high"),
    ("Growth & Profitability", "roe", "ROE", "high"),
    ("Cash & Balance Sheet", "fcf_yield", "FCF Yield", "high"),
    ("Cash & Balance Sheet", "net_debt_ebitda", "Net Debt / EBITDA", "low"),
    ("Decision", "rr_score", "R/R Score", "high"),
    ("Decision", "verdict", "Verdict", "none"),
]


def render_comparison_table(peers: list[dict[str, Any]]) -> str:
    rows: list[str] = []
    active_section = None
    colspan = len(peers) + 2
    for section, key, label, winner_mode in METRIC_ROWS:
        if section != active_section:
            active_section = section
            rows.append(
                f'<tr class="bg-slate-50"><td class="p-3 text-xs uppercase tracking-[0.25em] text-slate-400 font-semibold" colspan="{colspan}">{escape(section)}</td></tr>'
            )
        winner = winner_for_metric(peers, key, winner_mode)
        tags = "".join(tag_badge(tag) for tag in metric_tags(peers, key))
        metric_label = f'<div class="flex items-center gap-1.5">{escape(label)} {tags}</div>' if tags else escape(label)
        cells: list[str] = []
        for peer in peers:
            highlight = "text-green-700 font-semibold" if winner and peer["ticker"] == winner and key != "verdict" else "text-slate-900"
            cells.append(f'<td class="p-3 text-right {highlight}">{metric_display(peer, key)}</td>')
        winner_display = escape(winner) if winner else "—"
        rows.append(
            f'<tr class="border-t border-slate-100 hover:bg-slate-50"><td class="p-3 text-slate-600">{metric_label}</td>{"".join(cells)}<td class="p-3 text-right text-green-700 font-semibold">{winner_display}</td></tr>'
        )
    headers = "".join(f'<th class="p-4 text-right font-semibold text-slate-900">{escape(peer["ticker"])}</th>' for peer in peers)
    return f"""
    <section>
      <h2 class="text-xl font-bold text-slate-900 mb-4">Comparison Matrix</h2>
      <div class="card overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="bg-slate-50 text-slate-500 text-xs uppercase">
              <th class="text-left p-4 font-semibold">Metric</th>
              {headers}
              <th class="text-right p-4 font-semibold">Winner</th>
            </tr>
          </thead>
          <tbody>
            {"".join(rows)}
          </tbody>
        </table>
      </div>
    </section>
    """


def render_scenario_cards(peers: list[dict[str, Any]], korean: bool) -> str:
    cards: list[str] = []
    for peer in peers:
        analysis = peer.get("analysis") or {}
        scenarios = analysis.get("scenarios") if isinstance(analysis.get("scenarios"), dict) else {}
        currency = analysis.get("currency")
        base = scenarios.get("base", {})
        bull = scenarios.get("bull", {})
        bear = scenarios.get("bear", {})
        assumption = base.get("key_assumption") or primary_catalyst(peer) or primary_risk(peer) or (
            "세부 시나리오 설명은 레거시 샘플에 남지 않았습니다." if korean else "Legacy sample did not preserve a richer scenario narrative."
        )
        cards.append(
            f"""
            <div class="card p-5">
              <div class="flex items-center justify-between mb-3">
                <h3 class="font-bold text-slate-900 text-lg">{escape(peer_label(peer))}</h3>
                {rr_badge(analysis.get("rr_score"))}
              </div>
              <div class="space-y-2 text-sm">
                <div class="flex justify-between p-2 bg-green-50 rounded-xl">
                  <span class="text-green-700 font-medium">Bull ({format_probability(bull.get("probability"))})</span>
                  <span class="text-slate-900 font-semibold">{format_currency_value(bull.get("target"), currency)} ({format_percent(bull.get("return_pct"), 1)})</span>
                </div>
                <div class="flex justify-between p-2 bg-blue-50 rounded-xl">
                  <span class="text-blue-700 font-medium">Base ({format_probability(base.get("probability"))})</span>
                  <span class="text-slate-900 font-semibold">{format_currency_value(base.get("target"), currency)} ({format_percent(base.get("return_pct"), 1)})</span>
                </div>
                <div class="flex justify-between p-2 bg-red-50 rounded-xl">
                  <span class="text-red-700 font-medium">Bear ({format_probability(bear.get("probability"))})</span>
                  <span class="text-slate-900 font-semibold">{format_currency_value(bear.get("target"), currency)} ({format_percent(bear.get("return_pct"), 1)})</span>
                </div>
              </div>
              <div class="mt-3 pt-3 border-t border-slate-100">
                <p class="text-slate-500 text-xs">{escape(assumption)}</p>
              </div>
            </div>
            """
        )
    return f"""
    <section>
      <h2 class="text-xl font-bold text-slate-900 mb-4">{"시나리오 비교" if korean else "Scenario Comparison"}</h2>
      <div class="grid grid-cols-1 md:grid-cols-{max(1, min(len(peers), 3))} gap-4">
        {"".join(cards)}
      </div>
    </section>
    """


def ranking_rationale(peer: dict[str, Any], korean: bool) -> str:
    analysis = peer.get("analysis") or {}
    rr_score = analysis.get("rr_score")
    return_pct = base_return(peer)
    operating_margin = metric_numeric_value(peer, "operating_margin")
    per_ratio = metric_numeric_value(peer, "per")
    per_text = f"{format_number(per_ratio, 2)}x" if per_ratio is not None else ("미집계" if korean else "not available")
    if korean:
        return (
            f"기준 시나리오 기대수익률 {format_percent(return_pct, 1)}와 영업이익률 {format_percent(operating_margin, 1)} 조합이 돋보입니다. "
            f"현재 P/E는 {per_text}, R/R은 {format_number(rr_score, 2)}입니다."
        )
    return (
        f"Base-case upside of {format_percent(return_pct, 1)} pairs with {format_percent(operating_margin, 1)} operating margin. "
        f"The stock trades at {per_text} on P/E with an R/R score of {format_number(rr_score, 2)}."
    )


def render_ranking(peers: list[dict[str, Any]], korean: bool) -> str:
    ranked = sorted(
        peers,
        key=lambda peer: metric_numeric_value(peer, "rr_score") if metric_numeric_value(peer, "rr_score") is not None else -999,
        reverse=True,
    )
    rows: list[str] = []
    accent_classes = [("green", "border-green-500 text-green-600"), ("blue", "border-blue-500 text-blue-600")]
    for index, peer in enumerate(ranked, start=1):
        accent = accent_classes[index - 1][1] if index <= len(accent_classes) else "border-slate-300 text-slate-500"
        rows.append(
            f"""
            <div class="card p-4 flex items-center gap-4 border-l-4 {accent}">
              <span class="text-2xl font-bold">{escape(f'#{index}')}</span>
              <div class="flex-1">
                <div class="flex items-center gap-2">
                  <span class="font-bold text-slate-900 text-lg">{escape(peer_label(peer))}</span>
                  {rr_badge((peer.get("analysis") or {}).get("rr_score"))}
                </div>
                <p class="text-slate-500 text-sm mt-1">{escape(ranking_rationale(peer, korean))}</p>
              </div>
            </div>
            """
        )
    return f"""
    <section>
      <h2 class="text-xl font-bold text-slate-900 mb-4">{"R/R 점수 순위" if korean else "R/R Score Ranking"}</h2>
      <div class="space-y-3">{"".join(rows)}</div>
    </section>
    """


def build_best_pick_copy(best_peer: dict[str, Any] | None, peers: list[dict[str, Any]], korean: bool, analysis_date: str | None) -> str:
    if best_peer is None or (metric_numeric_value(best_peer, "rr_score") or 0) < 1:
        return (
            "모든 종목의 기대보상비가 매력적이지 않아 뚜렷한 최선호를 제시하기 어렵습니다." if korean
            else "No clear best pick emerges because every peer screens as unattractive on current risk/reward."
        )

    analysis = best_peer.get("analysis") or {}
    base_target = base_case(best_peer).get("target") or analysis.get("analyst_target")
    return_pct = base_return(best_peer)
    per_ratio = metric_numeric_value(best_peer, "per")
    margin = metric_numeric_value(best_peer, "operating_margin")
    catalyst = primary_catalyst(best_peer) or ("다음 실적/제품 이벤트" if korean else "the next earnings or product catalyst")
    risk = primary_risk(best_peer) or ("리스크 공시는 레거시 샘플에서 제한적입니다." if korean else "risk disclosure remains thin in the legacy sample.")
    leader = peer_label(best_peer)
    peers_text = ", ".join(peer["ticker"] for peer in peers if peer["ticker"] != best_peer["ticker"])
    if korean:
        return (
            f"이 문단은 의견입니다. {leader}를 {analysis_date or '현재'} 기준 최선호로 봅니다. "
            f"기준 시나리오 목표가는 {format_currency_value(base_target, analysis.get('currency'))}, 기대수익률은 {format_percent(return_pct, 1)}이며, "
            f"P/E {format_number(per_ratio, 2)}x와 영업이익률 {format_percent(margin, 1)} 조합이 {peers_text} 대비 상대 강점입니다. "
            f"핵심 촉매는 {catalyst}이고, 가장 중요한 리스크는 {risk}"
        )
    return (
        f"This is an opinion. {leader} is the best pick as of {analysis_date or 'today'} because its base-case target of "
        f"{format_currency_value(base_target, analysis.get('currency'))} implies {format_percent(return_pct, 1)} upside, while "
        f"{format_number(per_ratio, 2)}x P/E and {format_percent(margin, 1)} operating margin compare well versus {peers_text}. "
        f"The next catalyst is {catalyst}, and the key risk is {risk}"
    )


def render_best_pick(peers: list[dict[str, Any]], korean: bool, analysis_date: str | None) -> str:
    ranked = sorted(
        peers,
        key=lambda peer: metric_numeric_value(peer, "rr_score") if metric_numeric_value(peer, "rr_score") is not None else -999,
        reverse=True,
    )
    best_peer = ranked[0] if ranked else None
    verdict = (best_peer.get("analysis") or {}).get("verdict") if best_peer else None
    ticker = best_peer["ticker"] if best_peer else ("없음" if korean else "None")
    copy_text = build_best_pick_copy(best_peer, peers, korean, analysis_date)
    header = "최선호 종목" if korean else "Best Pick"
    date_label = analysis_date or "—"
    return f"""
    <section>
      <div class="card p-6 bg-green-50 border border-green-200">
        <div class="flex items-start gap-3">
          <div class="w-12 h-12 rounded-2xl bg-green-600 text-white flex items-center justify-center text-xl font-bold">#1</div>
          <div>
            <h2 class="text-xl font-semibold text-green-800 mb-2">{escape(header)} ({escape(date_label)})</h2>
            <p class="text-slate-900 font-bold text-lg mb-2">{escape(ticker)} {verdict_badge(verdict)}</p>
            <p class="text-slate-700 text-sm mb-3">{escape(copy_text)}</p>
            <p class="text-slate-500 text-xs italic">{escape("정보 해석에 기반한 의견이며 투자 조언이 아닙니다." if korean else "This reflects the analyst view based on available data and is not investment advice.")}</p>
          </div>
        </div>
      </div>
    </section>
    """


def build_differentiators(peers: list[dict[str, Any]], korean: bool) -> list[tuple[str, str]]:
    differentiators: list[tuple[str, str]] = []
    main_peer = peers[0] if peers else None
    per_values = [(peer, metric_numeric_value(peer, "per")) for peer in peers]
    per_values = [(peer, value) for peer, value in per_values if value is not None]
    if len(per_values) >= 2:
        cheapest = min(per_values, key=lambda item: item[1])
        richest = max(per_values, key=lambda item: item[1])
        if korean:
            differentiators.append(
                (
                    "밸류에이션 스프레드",
                    f"{cheapest[0]['ticker']}는 P/E {format_number(cheapest[1], 2)}x로 가장 낮고, {richest[0]['ticker']}는 {format_number(richest[1], 2)}x로 가장 높습니다. 같은 메모리/반도체 체인 안에서도 밸류에이션 허들이 뚜렷하게 다릅니다.",
                )
            )
        else:
            differentiators.append(
                (
                    "Valuation spread",
                    f"{cheapest[0]['ticker']} screens cheapest at {format_number(cheapest[1], 2)}x P/E, while {richest[0]['ticker']} sits at {format_number(richest[1], 2)}x. The peer set is not being priced on a uniform multiple.",
                )
            )

    margin_values = [(peer, metric_numeric_value(peer, "operating_margin")) for peer in peers]
    margin_values = [(peer, value) for peer, value in margin_values if value is not None]
    if len(margin_values) >= 2:
        best = max(margin_values, key=lambda item: item[1])
        weakest = min(margin_values, key=lambda item: item[1])
        if korean:
            differentiators.append(
                (
                    "수익성 격차",
                    f"{best[0]['ticker']}의 영업이익률은 {format_percent(best[1], 1)}로 가장 높고, {weakest[0]['ticker']}는 {format_percent(weakest[1], 1)}입니다. 수익성 차이가 동일 멀티플 적용을 어렵게 만듭니다.",
                )
            )
        else:
            differentiators.append(
                (
                    "Profitability gap",
                    f"{best[0]['ticker']} leads on operating margin at {format_percent(best[1], 1)}, versus {format_percent(weakest[1], 1)} for {weakest[0]['ticker']}. Margin durability is one reason multiples should not converge mechanically.",
                )
            )

    if main_peer is not None:
        main_per = metric_numeric_value(main_peer, "per")
        main_return = base_return(main_peer)
        main_catalyst = primary_catalyst(main_peer)
        main_risk = primary_risk(main_peer)
        comparison_pool = [(peer, metric_numeric_value(peer, "per")) for peer in peers[1:]]
        comparison_pool = [(peer, value) for peer, value in comparison_pool if value is not None]
        if (main_catalyst or main_risk) and main_per is not None and comparison_pool:
            nearest_peer, nearest_per = min(comparison_pool, key=lambda item: abs(item[1] - main_per))
            if korean:
                sentence = (
                    f"{main_peer['ticker']}는 P/E {format_number(main_per, 2)}x로 {nearest_peer['ticker']}의 {format_number(nearest_per, 2)}x와 비교되는 위치에 있습니다. "
                    f"재평가 조건은 {main_catalyst or '다음 실적/제품 이벤트'}이고, 먼저 점검할 리스크는 {main_risk or '세부 리스크 공시 보강'}입니다."
                )
                if main_return is not None:
                    sentence += f" 기준 기대수익률은 {format_percent(main_return, 1)}입니다."
                differentiators.append((f"{main_peer['ticker']} 재평가 조건", sentence))
            else:
                sentence = (
                    f"{main_peer['ticker']} trades on {format_number(main_per, 2)}x P/E versus {format_number(nearest_per, 2)}x for {nearest_peer['ticker']}. "
                    f"The re-rating trigger is {main_catalyst or 'the next earnings or product catalyst'}, while the first risk to watch is {main_risk or 'the need for fuller risk disclosure'}."
                )
                if main_return is not None:
                    sentence += f" Base-case upside is {format_percent(main_return, 1)}."
                differentiators.append((f"{main_peer['ticker']} re-rating setup", sentence))

    rr_values = [(peer, base_return(peer), metric_numeric_value(peer, "rr_score")) for peer in peers]
    rr_values = [(peer, ret, rr) for peer, ret, rr in rr_values if ret is not None and rr is not None]
    if len(rr_values) >= 2:
        leader = max(rr_values, key=lambda item: item[2])
        laggard = min(rr_values, key=lambda item: item[2])
        catalyst = primary_catalyst(leader[0])
        risk = primary_risk(leader[0])
        if korean:
            sentence = (
                f"{leader[0]['ticker']}의 기준 기대수익률은 {format_percent(leader[1], 1)}, R/R은 {format_number(leader[2], 2)}로 가장 높습니다. "
                f"반면 {laggard[0]['ticker']}는 기준 기대수익률 {format_percent(laggard[1], 1)}, R/R {format_number(laggard[2], 2)}에 머뭅니다."
            )
            if catalyst:
                sentence += f" 차별화 촉매는 {catalyst}입니다."
            if risk:
                sentence += f" 반대로 가장 먼저 확인할 리스크는 {risk}입니다."
            differentiators.append(("리스크/촉매 비대칭", sentence))
        else:
            sentence = (
                f"{leader[0]['ticker']} combines {format_percent(leader[1], 1)} base-case upside with an R/R score of {format_number(leader[2], 2)}, "
                f"while {laggard[0]['ticker']} is only at {format_percent(laggard[1], 1)} and {format_number(laggard[2], 2)}."
            )
            if catalyst:
                sentence += f" The visible catalyst is {catalyst}."
            if risk:
                sentence += f" The first risk to monitor is {risk}."
            differentiators.append(("Risk/catalyst asymmetry", sentence))

    return differentiators[:3]


def render_differentiators(peers: list[dict[str, Any]], korean: bool) -> str:
    cards = []
    for title, body in build_differentiators(peers, korean):
        cards.append(
            f"""
            <div class="card p-4 flex gap-3">
              <div class="w-10 h-10 rounded-xl bg-blue-50 text-blue-600 flex items-center justify-center font-bold">≠</div>
              <div>
                <p class="text-slate-900 font-semibold">{escape(title)}</p>
                <p class="text-slate-600 text-sm">{escape(body)}</p>
              </div>
            </div>
            """
        )
    return f"""
    <section>
      <h2 class="text-xl font-bold text-slate-900 mb-4">{"차별화 포인트" if korean else "Key Differentiators"}</h2>
      <div class="space-y-3">{"".join(cards)}</div>
    </section>
    """


def collect_source_list(peers: list[dict[str, Any]]) -> str:
    sources: list[str] = []
    for metric_key in ("price", "market_cap", "per", "ev_ebitda", "operating_margin", "fcf_yield"):
        for peer in peers:
            entry = metric_entry(peer, metric_key)
            if not isinstance(entry, dict):
                continue
            for source in entry.get("sources", []) if isinstance(entry.get("sources"), list) else []:
                if isinstance(source, str) and source and source not in sources:
                    sources.append(source)
    if not sources:
        sources = ["run-local validated-data.json"]
    return " · ".join(sources[:6])


def disclaimer_text(korean: bool) -> str:
    if korean:
        return (
            "이 보고서는 정보 제공 목적으로만 AI 리서치 어시스턴트가 생성한 것입니다. 투자 조언, 증권 매수/매도 권유, 또는 투자 수익 보장이 아닙니다. "
            "모든 데이터는 공개 정보에서 수집되었으며 최신 시장 상황을 반영하지 않을 수 있습니다. 투자 결정 전 반드시 자체 실사를 수행하시기 바랍니다."
        )
    return (
        "This report is generated by an AI research assistant for informational purposes only. It does not constitute investment advice, a solicitation to buy or sell securities, or a guarantee of returns. "
        "All data is sourced from public information and may not reflect the most current market conditions. Always conduct your own due diligence before making investment decisions."
    )


def render_html(peers: list[dict[str, Any]], main_analysis: dict[str, Any]) -> str:
    language = main_analysis.get("output_language")
    korean = is_korean(language)
    analysis_date = main_analysis.get("analysis_date") or "—"
    title = "피어 비교" if korean else "Peer Comparison"
    subtitle = " vs ".join(peer["ticker"] for peer in peers)
    badges = "".join(data_mode_badge(peer, korean) for peer in peers)
    source_list = collect_source_list(peers)
    return f"""<!DOCTYPE html>
<html lang="{escape('ko' if korean else 'en')}">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{escape(title)}: {escape(subtitle)} | {escape(analysis_date)}</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Noto+Sans+KR:wght@400;500;700;800&display=swap" rel="stylesheet">
  <style>
    * {{ font-family: 'Inter', 'Noto Sans KR', sans-serif; }}
    body {{ background: #f8fafc; }}
    .card {{ background: #fff; border-radius: 18px; box-shadow: 0 16px 40px rgba(15, 23, 42, 0.08); }}
  </style>
</head>
<body class="text-slate-800 min-h-screen">
  <header class="bg-[linear-gradient(135deg,#071632_0%,#0f2d5f_45%,#1758ba_100%)]">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 py-10">
      <h1 class="text-3xl font-bold text-white tracking-tight mb-1">{escape(title)}</h1>
      <p class="text-blue-100 text-sm">{escape(subtitle)} · {escape(analysis_date)}</p>
      <div class="flex flex-wrap gap-2 mt-4">{badges}</div>
    </div>
  </header>

  <main class="max-w-7xl mx-auto px-4 sm:px-6 py-8 space-y-8">
    {render_comparison_table(peers)}
    {render_scenario_cards(peers, korean)}
    {render_ranking(peers, korean)}
    {render_best_pick(peers, korean, analysis_date)}
    {render_differentiators(peers, korean)}
  </main>

  <footer class="bg-slate-950 text-slate-300 mt-12">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 py-8">
      <p class="text-xs mb-2"><strong class="text-slate-100">{escape('면책 조항' if korean else 'Disclaimer')}:</strong> {escape(disclaimer_text(korean))}</p>
      <p class="text-xs">{escape(('데이터 소스' if korean else 'Data sources'))}: {escape(source_list)} · Generated: {escape(analysis_date)}</p>
    </div>
  </footer>
</body>
</html>
"""


def generate_comparison_report(analysis_result_or_path: dict[str, Any] | str | Path, output_path: str | Path | None = None) -> str:
    if isinstance(analysis_result_or_path, dict):
        analysis = analysis_result_or_path
    else:
        analysis = load_json(resolve_path(analysis_result_or_path))

    resolved_output = resolve_path(
        output_path
        or analysis.get("report_path")
        or build_default_report_path(
            ticker=analysis.get("ticker"),
            output_mode=analysis.get("output_mode"),
            output_language=analysis.get("output_language"),
            analysis_date=analysis.get("analysis_date"),
            peer_tickers=analysis.get("peer_tickers"),
        )
    )
    resolved_output.parent.mkdir(parents=True, exist_ok=True)
    html_body = render_html(collect_peer_payloads(analysis), analysis)
    resolved_output.write_text(html_body, encoding="utf-8")
    return str(resolved_output)


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a Mode B peer comparison report")
    parser.add_argument("--input", required=True, help="Path to analysis-result.json")
    parser.add_argument("--output", help="Optional output HTML path")
    args = parser.parse_args()

    output = generate_comparison_report(args.input, args.output)
    payload = {
        "input_path": display_path(resolve_path(args.input)),
        "output_path": display_path(resolve_path(output)),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
