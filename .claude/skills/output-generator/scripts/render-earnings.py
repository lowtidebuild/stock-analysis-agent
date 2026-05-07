#!/usr/bin/env python3
"""render-earnings.py — Mode E (Earnings Preview / Review) HTML renderer.

Phase F.4 of `docs/superpowers/plans/2026-05-07-mode-e-earnings-detail.md`.

Window-aware Mode E renderer:
- Preview: 6 sections (consensus_snapshot, beat_miss_history, key_questions,
  options_snapshot, pre_mortem, pre_print_position).
- Review: 6 sections (actual_vs_consensus, guidance_delta,
  key_questions_answered, thesis_impact, light_verdict_update,
  post_print_action).

Auto-dispatches based on `earnings_sub_mode` field. OD-F2 enforced
(options unavailable → Section 4 stub). OD-F3 enforced (outdated verdict
badge + Mode C rerun banner).

Templates (read-only, reference only):
- `.claude/skills/output-generator/references/mode-e-template-preview.md`
- `.claude/skills/output-generator/references/mode-e-template-review.md`

The renderer builds HTML inline (mirroring `render-comparison.py`) rather
than parsing the markdown template, because the templates carry conditional
substitution comments that require renderer-side logic anyway. The HTML
skeleton produced here is a 1:1 implementation of the template's HTML
fenced code block.

Usage:
    python render-earnings.py --input output/runs/<run_id>/<ticker>/analysis-result.json
    python render-earnings.py --input <path> --output output/reports/GOOGL_E_preview_ko_2026-04-26.html
"""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any, Optional

THIS_FILE = Path(__file__).resolve()
REPO_ROOT = THIS_FILE.parents[4]

import sys

sys.path.insert(0, str(REPO_ROOT))

from tools.paths import data_path, runtime_path  # noqa: E402


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------


def load_json(path: str | Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def resolve_path(path: str | Path) -> Path:
    return runtime_path(path)


def display_path(path: Path) -> str:
    if path.is_absolute() and path.is_relative_to(REPO_ROOT):
        return str(path.relative_to(REPO_ROOT))
    return str(path)


def escape(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def is_korean(language: str | None) -> bool:
    return (language or "").lower().startswith("ko")


def currency_symbol(currency: str | None) -> str:
    mapping = {"USD": "$", "KRW": "₩", "EUR": "€", "JPY": "¥"}
    return mapping.get((currency or "").upper(), f"{currency} " if currency else "")


def format_number(value: Any, digits: int = 2) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{value:,.{digits}f}"
    return "—"


def format_percent(value: Any, digits: int = 1, signed: bool = False) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if signed:
            return f"{value:+.{digits}f}%"
        return f"{value:.{digits}f}%"
    return "—"


def format_signed_percent_or_dash(value: Any, digits: int = 1) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        sign = "+" if value > 0 else ""
        return f"{sign}{value:.{digits}f}%"
    return "—"


def format_revenue(value: Any, unit: str | None) -> str:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return "—"
    normalized_unit = (unit or "").lower()
    if normalized_unit in {"millions_usd", "million_usd"}:
        if abs(value) >= 1000:
            return f"${value / 1000:,.1f}B"
        return f"${value:,.0f}M"
    if normalized_unit == "billions_usd":
        return f"${value:,.2f}B"
    if normalized_unit in {"억원"}:
        return f"{value:,.0f}억원"
    if normalized_unit in {"조원"}:
        return f"{value:,.1f}조원"
    return f"{value:,.0f}"


def korean_font_link(language: str | None) -> str:
    if is_korean(language):
        return (
            '<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:'
            'wght@300;400;500;700&display=swap" rel="stylesheet">'
        )
    return ""


def collect_source_tags(*tag_lists: Any) -> list[str]:
    """Collect unique source tags appearing in the analysis output."""
    seen: list[str] = []
    for item in tag_lists:
        if isinstance(item, str) and item.startswith("[") and item.endswith("]"):
            if item not in seen:
                seen.append(item)
    return seen


def _safe_json_for_script(obj: Any) -> str:
    """Serialize JSON for embedding inside a <script> tag.

    Replaces ``</`` with ``<\\/`` so that an attacker-controlled string
    such as ``"Q1 </script><script>alert(1)</script>"`` cannot prematurely
    close the surrounding <script> tag (or a ``type="application/json"``
    island, which the HTML parser also closes on ``</script>``).

    Per CLAUDE.md §12, all fetched strings are untrusted; this helper
    sanitizes them at the renderer boundary before they cross into the
    HTML document.
    """
    return json.dumps(obj, ensure_ascii=False).replace("</", "<\\/")


def days_until_label(days_until: Any, korean: bool) -> str:
    if not isinstance(days_until, (int, float)) or isinstance(days_until, bool):
        return ""
    n = abs(int(days_until))
    if korean:
        return f"{n}일 후" if days_until < 0 else f"{n}일 경과"
    return f"in {n} days" if days_until < 0 else f"{n} days ago"


def quarter_from_date(date_iso: str | None) -> str:
    if not isinstance(date_iso, str) or len(date_iso) < 7:
        return "—"
    try:
        year = int(date_iso[:4])
        month = int(date_iso[5:7])
    except ValueError:
        return "—"
    quarter = (month - 1) // 3 + 1
    return f"Q{quarter} {year}"


# ---------------------------------------------------------------------------
# Preview renderer
# ---------------------------------------------------------------------------


def _preview_hero(analysis: dict[str, Any]) -> str:
    ticker = escape(analysis.get("ticker") or "—")
    company = escape(analysis.get("company_name") or analysis.get("ticker") or "—")
    window = analysis.get("earnings_window") or {}
    window_label = escape(window.get("window_label") or "D-?")
    next_date = window.get("next_earnings_date")
    quarter_label = quarter_from_date(next_date)
    confirmed = bool(window.get("next_earnings_confirmed", True))
    days_until = window.get("days_until")
    korean = is_korean(analysis.get("output_language"))

    consensus_snapshot = analysis.get("consensus_snapshot") or {}
    eps_block = consensus_snapshot.get("eps") or {}
    rev_block = consensus_snapshot.get("revenue") or {}
    consensus_eps = format_number(eps_block.get("mean"), 2)
    consensus_rev = format_revenue(rev_block.get("mean"), rev_block.get("unit"))

    options_snapshot = analysis.get("options_snapshot") or {}
    if options_snapshot.get("status") == "available":
        implied_move_html = (
            f'±{format_number(options_snapshot.get("implied_move_pct"), 1)}% '
            f'<span class="source-tag tag-options">[Options]</span>'
        )
    else:
        implied_move_html = "—"

    currency = analysis.get("currency") or "USD"
    sym = currency_symbol(currency)
    price_at_analysis = format_number(analysis.get("price_at_analysis"), 2)
    analysis_date = escape(analysis.get("analysis_date") or "—")
    data_mode = escape(analysis.get("data_mode") or "standard")
    days_label = escape(days_until_label(days_until, korean))
    earnings_dt_text = escape(next_date or "—")

    if not confirmed:
        warning_banner = (
            '<p class="mt-2 text-xs bg-yellow-300/30 text-yellow-100 inline-block px-2 py-1 rounded">'
            '<i class="fa-solid fa-triangle-exclamation mr-1"></i>'
            '실적 일정 미확정 — IR 페이지에서 재확인 필요'
            "</p>"
        )
    else:
        warning_banner = ""

    return f"""
<header style="background: linear-gradient(135deg, #7c2d12 0%, #c2410c 30%, #ea580c 60%, #fb923c 100%);">
  <div class="max-w-7xl mx-auto px-4 sm:px-6 py-8">
    <div class="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
      <div>
        <div class="flex items-center gap-3 mb-2">
          <span class="badge-d px-3 py-1.5 rounded-lg text-sm font-extrabold tracking-wide">
            {window_label}
          </span>
          <h1 class="text-3xl font-bold text-white tracking-tight">
            {company} <span class="text-orange-100/80 text-xl font-mono">{ticker}</span>
          </h1>
        </div>
        <p class="text-orange-100 text-sm font-semibold mt-1">
          {escape(quarter_label)} EARNINGS PREVIEW
        </p>
        <p class="text-orange-100/80 text-xs mt-2">
          <i class="fa-solid fa-calendar mr-1"></i>
          발표 예정: {earnings_dt_text} ({days_label})
        </p>
        {warning_banner}
      </div>
      <div class="flex flex-col gap-2 text-right">
        <div class="grid grid-cols-2 gap-x-6 gap-y-1 text-sm">
          <span class="text-orange-100/70">컨센서스 EPS</span>
          <span class="text-white font-semibold">{consensus_eps} <span class="source-tag tag-est">[Est]</span></span>
          <span class="text-orange-100/70">컨센서스 매출</span>
          <span class="text-white font-semibold">{consensus_rev}</span>
          <span class="text-orange-100/70">현재가</span>
          <span class="text-white font-semibold">{sym}{price_at_analysis}</span>
          <span class="text-orange-100/70">옵션 implied move</span>
          <span class="text-white font-semibold">{implied_move_html}</span>
        </div>
      </div>
    </div>
    <div class="mt-4 pt-4 border-t border-white/10 flex flex-wrap gap-4 text-xs text-orange-100/60">
      <span>분석일: {analysis_date}</span>
      <span>·</span>
      <span>모드: Earnings Preview (E)</span>
      <span>·</span>
      <span>데이터: {data_mode}</span>
    </div>
  </div>
</header>
"""


def _preview_section_consensus(analysis: dict[str, Any]) -> str:
    consensus = analysis.get("consensus_snapshot") or {}
    eps = consensus.get("eps") or {}
    rev = consensus.get("revenue") or {}
    segments = consensus.get("segment_consensus") or []

    def disp(value: Any, digits: int = 2) -> str:
        return format_number(value, digits) if isinstance(value, (int, float)) else "—"

    eps_mean = disp(eps.get("mean"), 2)
    eps_high = disp(eps.get("high"), 2)
    eps_low = disp(eps.get("low"), 2)
    rev_mean = disp(rev.get("mean"), 0)
    rev_high = disp(rev.get("high"), 0)
    rev_low = disp(rev.get("low"), 0)

    def dispersion_pct(block: dict[str, Any]) -> str:
        h, low, m = block.get("high"), block.get("low"), block.get("mean")
        if all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in (h, low, m)) and m:
            return f"{(h - low) / m * 100:.1f}"
        return "—"

    eps_disp = dispersion_pct(eps)
    rev_disp = dispersion_pct(rev)

    rev_unit = (rev.get("unit") or "").lower()
    currency_unit = "M USD" if rev_unit in {"millions_usd", "million_usd"} else (
        "B USD" if rev_unit == "billions_usd" else escape(rev.get("unit") or "—")
    )

    segment_rows: list[str] = []
    for seg in segments:
        if not isinstance(seg, dict):
            continue
        segment_rows.append(
            "<tr class=\"border-b\">"
            f"<td class=\"py-2 font-semibold\">{escape(seg.get('segment') or '—')}</td>"
            f"<td class=\"py-2 text-gray-500 text-xs\">{escape(seg.get('metric') or '—')}</td>"
            f"<td class=\"text-right py-2\">{disp(seg.get('mean'), 1)}</td>"
            f"<td class=\"text-right py-2 text-xs text-gray-500\">"
            f"{disp(seg.get('low'), 1)}–{disp(seg.get('high'), 1)}</td>"
            "</tr>"
        )
    segment_html = (
        "".join(segment_rows)
        if segment_rows
        else '<tr><td colspan="4" class="py-3 text-xs text-gray-400 italic">No segment consensus data</td></tr>'
    )

    return f"""
<section id="section-consensus">
  <h2 class="text-xl font-bold text-gray-900 mb-4">
    <i class="fa-solid fa-bullseye mr-2 text-orange-500"></i>
    1. 컨센서스 스냅샷
  </h2>
  <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
    <div class="card p-6">
      <h3 class="text-sm font-bold text-gray-700 mb-3">Top-line</h3>
      <table class="w-full text-sm">
        <thead>
          <tr class="text-xs uppercase text-gray-500 border-b">
            <th class="text-left py-2">항목</th>
            <th class="text-right py-2">Mean</th>
            <th class="text-right py-2">High</th>
            <th class="text-right py-2">Low</th>
            <th class="text-right py-2">출처</th>
          </tr>
        </thead>
        <tbody>
          <tr class="border-b">
            <td class="py-2 font-semibold">EPS</td>
            <td class="text-right py-2">{eps_mean}</td>
            <td class="text-right py-2 text-green-600">{eps_high}</td>
            <td class="text-right py-2 text-red-600">{eps_low}</td>
            <td class="text-right py-2"><span class="source-tag tag-est">[Est]</span></td>
          </tr>
          <tr class="border-b">
            <td class="py-2 font-semibold">매출 ({currency_unit})</td>
            <td class="text-right py-2">{rev_mean}</td>
            <td class="text-right py-2 text-green-600">{rev_high}</td>
            <td class="text-right py-2 text-red-600">{rev_low}</td>
            <td class="text-right py-2"><span class="source-tag tag-est">[Est]</span></td>
          </tr>
        </tbody>
      </table>
      <p class="text-xs text-gray-400 mt-3 italic">
        Dispersion (high − low / mean): EPS {eps_disp}% · 매출 {rev_disp}%
      </p>
    </div>
    <div class="card p-6">
      <h3 class="text-sm font-bold text-gray-700 mb-3">부문별 컨센서스</h3>
      <table class="w-full text-sm">
        <thead>
          <tr class="text-xs uppercase text-gray-500 border-b">
            <th class="text-left py-2">부문</th>
            <th class="text-left py-2">지표</th>
            <th class="text-right py-2">Mean</th>
            <th class="text-right py-2">레인지</th>
          </tr>
        </thead>
        <tbody>
          {segment_html}
        </tbody>
      </table>
    </div>
  </div>
</section>
"""


def _preview_section_history(analysis: dict[str, Any]) -> str:
    history = analysis.get("beat_miss_history") or {}
    quarters = history.get("quarters") or []
    summary = history.get("summary") or {}

    if not quarters:
        return """
<section id="section-history">
  <h2 class="text-xl font-bold text-gray-900 mb-4">
    <i class="fa-solid fa-chart-column mr-2 text-orange-500"></i>
    2. Beat/Miss 히스토리
  </h2>
  <div class="text-gray-400 italic text-sm p-4 border border-gray-200 rounded-lg bg-gray-50">
    [Data unavailable — earnings history not collected]
  </div>
</section>
"""

    n_q = len(quarters)
    insufficient_banner = ""
    if n_q < 4:
        insufficient_banner = (
            '<p class="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded p-2 mt-2">'
            '<i class="fa-solid fa-triangle-exclamation mr-1"></i>'
            f"[Quality flag: insufficient history ({n_q} quarters)]"
            "</p>"
        )

    hit_rate_pct = format_number(summary.get("hit_rate", 0) * 100 if isinstance(summary.get("hit_rate"), (int, float)) else None, 1)
    avg_surprise = format_number(summary.get("avg_surprise_pct"), 1)
    avg_reaction = format_number(summary.get("avg_reaction_1d_pct"), 1)

    rows: list[str] = []
    chart_labels: list[str] = []
    chart_data: list[float] = []
    for q in quarters:
        if not isinstance(q, dict):
            continue
        beat = bool(q.get("beat"))
        beat_color = "text-green-600" if beat else "text-red-600"
        reaction_value = q.get("stock_reaction_1d_pct")
        reaction_color = (
            "text-green-600" if isinstance(reaction_value, (int, float)) and reaction_value >= 0
            else "text-red-600"
        )
        actual_eps = format_number(q.get("actual_eps"), 2)
        consensus_eps_q = format_number(q.get("consensus_eps"), 2)
        surprise_str = format_number(q.get("surprise_pct"), 1)
        reaction_str = format_number(reaction_value, 1)
        rows.append(
            "<tr class=\"border-b\">"
            f"<td class=\"p-3 font-semibold\">{escape(q.get('quarter') or '—')}</td>"
            f"<td class=\"p-3 text-gray-500 text-xs font-mono\">{escape(q.get('report_date') or '—')}</td>"
            f"<td class=\"text-right p-3\">{actual_eps}</td>"
            f"<td class=\"text-right p-3\">{consensus_eps_q}</td>"
            f"<td class=\"text-right p-3 {beat_color}\">{surprise_str}%</td>"
            f"<td class=\"text-right p-3 {reaction_color}\">{reaction_str}%</td>"
            "<td class=\"text-right p-3\"><span class=\"source-tag tag-history\">[History]</span></td>"
            "</tr>"
        )
        chart_labels.append(q.get("quarter") or "")
        if isinstance(q.get("surprise_pct"), (int, float)):
            chart_data.append(float(q["surprise_pct"]))
        else:
            chart_data.append(0.0)

    chart_labels_js = _safe_json_for_script(chart_labels)
    chart_data_js = _safe_json_for_script(chart_data)

    return f"""
<section id="section-history">
  <h2 class="text-xl font-bold text-gray-900 mb-4">
    <i class="fa-solid fa-chart-column mr-2 text-orange-500"></i>
    2. Beat/Miss 히스토리 (최근 {n_q}분기)
  </h2>
  <p class="text-sm text-gray-500 mb-4">
    Hit rate {hit_rate_pct}% · 평균 surprise {avg_surprise}% ·
    평균 1일 주가 반응 {avg_reaction}%
    <span class="source-tag tag-calc">[Calc]</span>
  </p>
  <div class="card p-5">
    <canvas id="beatMissChart" height="160"></canvas>
  </div>
  {insufficient_banner}
  <div class="card overflow-x-auto mt-4">
    <table class="w-full text-sm">
      <thead>
        <tr class="bg-gray-50 text-gray-600 text-xs uppercase">
          <th class="text-left p-3 font-semibold">분기</th>
          <th class="text-left p-3 font-semibold">발표일</th>
          <th class="text-right p-3 font-semibold">Actual EPS</th>
          <th class="text-right p-3 font-semibold">Consensus</th>
          <th class="text-right p-3 font-semibold">Surprise %</th>
          <th class="text-right p-3 font-semibold">1일 반응</th>
          <th class="text-right p-3 font-semibold">출처</th>
        </tr>
      </thead>
      <tbody>
        {''.join(rows)}
      </tbody>
    </table>
  </div>
  <script id="beat-miss-chart-data" type="application/json">{{"labels": {chart_labels_js}, "data": {chart_data_js}}}</script>
</section>
"""


def _preview_section_key_questions(analysis: dict[str, Any]) -> str:
    questions = analysis.get("key_questions") or []
    if not questions:
        return """
<section id="section-key-questions">
  <h2 class="text-xl font-bold text-gray-900 mb-4">
    <i class="fa-solid fa-circle-question mr-2 text-orange-500"></i>
    3. 핵심 질문
  </h2>
  <p class="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded p-3">
    [Quality flag: no key questions — Mode E Preview requires ≥4]
  </p>
</section>
"""

    cards: list[str] = []
    for idx, q in enumerate(questions, start=1):
        if not isinstance(q, dict):
            continue
        cards.append(f"""
<div class="card p-5 border-l-4 border-orange-500">
  <p class="text-sm font-bold text-gray-800 mb-2">
    Q{idx}. {escape(q.get('question') or '—')}
  </p>
  <p class="text-xs text-gray-500 mb-3">
    예상 답변: <span class="font-semibold text-gray-700">{escape(q.get('expected_answer') or '—')}</span>
  </p>
  <div class="grid grid-cols-2 gap-2 text-xs">
    <div class="bg-green-50 rounded p-2">
      <p class="text-green-700 font-semibold">If YES</p>
      <p class="text-green-800">{escape(q.get('stock_impact_if_yes') or '—')}</p>
    </div>
    <div class="bg-red-50 rounded p-2">
      <p class="text-red-700 font-semibold">If NO</p>
      <p class="text-red-800">{escape(q.get('stock_impact_if_no') or '—')}</p>
    </div>
  </div>
  <p class="text-xs text-gray-600 mt-3 italic">
    <strong>근거:</strong> {escape(q.get('rationale') or '—')}
  </p>
  <p class="text-xs text-gray-500 mt-2">
    <strong>메커니즘:</strong> {escape(q.get('mechanism') or '—')}
  </p>
</div>
""")
    return f"""
<section id="section-key-questions">
  <h2 class="text-xl font-bold text-gray-900 mb-4">
    <i class="fa-solid fa-circle-question mr-2 text-orange-500"></i>
    3. 핵심 질문 ({len(questions)}개)
  </h2>
  <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
    {''.join(cards)}
  </div>
</section>
"""


def _preview_section_options(analysis: dict[str, Any]) -> str:
    options = analysis.get("options_snapshot") or {}
    status = options.get("status")
    currency = analysis.get("currency") or "USD"
    sym = currency_symbol(currency)

    if status != "available":
        reason = options.get("_unavailable_reason") or "yfinance option chain not available for this ticker"
        return f"""
<section id="section-options" class="opacity-80">
  <h2 class="text-xl font-bold text-gray-900 mb-4">
    <i class="fa-solid fa-chart-line mr-2 text-orange-500"></i>
    4. 옵션 & 센티먼트
  </h2>
  <div class="card p-6 bg-gray-50 border border-gray-200 text-center">
    <p class="text-sm text-gray-500">
      <i class="fa-solid fa-circle-exclamation mr-1 text-amber-500"></i>
      <strong>데이터 미수집</strong> — options chain unavailable
    </p>
    <p class="text-xs text-gray-400 mt-2">
      {escape(reason)}
    </p>
    <p class="text-xs text-gray-400 mt-1">
      Implied move 데이터 없이 분석 진행. Section 5 Pre-Mortem과 Section 6
      포지션 권고는 컨센서스 + 히스토리 기반.
    </p>
  </div>
</section>
"""

    spot = format_number(options.get("spot_price"), 2)
    atm_strike = format_number(options.get("atm_strike"), 0)
    atm_call = format_number(options.get("atm_call_price"), 2)
    atm_put = format_number(options.get("atm_put_price"), 2)
    atm_straddle = format_number(options.get("atm_straddle_price"), 2)
    implied_move = format_number(options.get("implied_move_pct"), 1)
    expiry = escape(options.get("nearest_expiry") or "—")
    iv_pct_raw = options.get("iv_percentile")
    if isinstance(iv_pct_raw, (int, float)) and not isinstance(iv_pct_raw, bool):
        iv_pct_html = f"{iv_pct_raw:.0f}%"
    else:
        iv_pct_html = "—"

    return f"""
<section id="section-options">
  <h2 class="text-xl font-bold text-gray-900 mb-4">
    <i class="fa-solid fa-chart-line mr-2 text-orange-500"></i>
    4. 옵션 & 센티먼트
  </h2>
  <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
    <div class="card p-5 stat-card" style="border-left: 4px solid #7c3aed">
      <p class="text-xs text-gray-500 mb-1">Spot Price</p>
      <p class="text-2xl font-bold text-gray-900">{sym}{spot}</p>
      <p class="text-[10px] text-gray-400 mt-1"><span class="source-tag tag-options">[Options]</span></p>
    </div>
    <div class="card p-5 stat-card" style="border-left: 4px solid #7c3aed">
      <p class="text-xs text-gray-500 mb-1">ATM Strike</p>
      <p class="text-2xl font-bold text-gray-900">{sym}{atm_strike}</p>
      <p class="text-[10px] text-gray-400 mt-1">Expiry {expiry}</p>
    </div>
    <div class="card p-5 stat-card" style="border-left: 4px solid #7c3aed">
      <p class="text-xs text-gray-500 mb-1">ATM Straddle</p>
      <p class="text-2xl font-bold text-gray-900">{sym}{atm_straddle}</p>
      <p class="text-[10px] text-gray-400 mt-1">Call {atm_call} / Put {atm_put}</p>
    </div>
    <div class="card p-5 stat-card" style="border-left: 4px solid #7c3aed">
      <p class="text-xs text-gray-500 mb-1">Implied 1-day Move</p>
      <p class="text-2xl font-bold text-purple-700">±{implied_move}%</p>
      <p class="text-[10px] text-gray-400 mt-1">IV %ile {iv_pct_html}</p>
    </div>
  </div>
  <p class="text-xs text-gray-500 mt-4 italic">
    Implied move ≈ (ATM call + ATM put) / spot × 100. Options-derived move
    represents the market's price for a 1-σ event around earnings — not
    directional bias.
  </p>
</section>
"""


def _preview_section_pre_mortem(analysis: dict[str, Any]) -> str:
    rows_data = analysis.get("pre_mortem") or []
    if not rows_data:
        return """
<section id="section-pre-mortem">
  <h2 class="text-xl font-bold text-gray-900 mb-4">
    <i class="fa-solid fa-skull mr-2 text-orange-500"></i>
    5. Pre-Mortem 시나리오
  </h2>
  <p class="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded p-3">
    [Quality flag: no pre-mortem scenarios — Mode E Preview requires ≥3]
  </p>
</section>
"""

    rendered_rows: list[str] = []
    prob_sum = 0.0
    for r in rows_data:
        if not isinstance(r, dict):
            continue
        impact = str(r.get("stock_impact") or "")
        if impact.startswith("+"):
            color = "text-green-600"
        elif impact.startswith("-"):
            color = "text-red-600"
        else:
            color = "text-gray-600"
        prob = r.get("probability")
        prob_pct = "—"
        if isinstance(prob, (int, float)) and not isinstance(prob, bool):
            prob_sum += float(prob)
            prob_pct = f"{prob * 100:.0f}"
        rendered_rows.append(
            "<tr class=\"border-b\">"
            f"<td class=\"p-3 font-semibold\">{escape(r.get('scenario') or '—')}</td>"
            f"<td class=\"p-3 text-xs text-gray-600\">{escape(r.get('trigger') or '—')}</td>"
            f"<td class=\"text-center p-3 {color} font-semibold\">{escape(impact or '—')}</td>"
            f"<td class=\"text-center p-3 font-mono\">{prob_pct}%</td>"
            f"<td class=\"p-3 text-xs text-gray-500\">{escape(r.get('mechanism') or '—')}</td>"
            "</tr>"
        )

    prob_total_pct = f"{prob_sum * 100:.1f}"
    quality_flag = ""
    if not (99.0 <= prob_sum * 100 <= 101.0):
        quality_flag = (
            '<p class="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded p-2 mt-2">'
            '<i class="fa-solid fa-triangle-exclamation mr-1"></i>'
            f"[Quality flag: pre-mortem probability total is {prob_total_pct}%, expected 100%]"
            "</p>"
        )

    return f"""
<section id="section-pre-mortem">
  <h2 class="text-xl font-bold text-gray-900 mb-4">
    <i class="fa-solid fa-skull mr-2 text-orange-500"></i>
    5. Pre-Mortem 시나리오
  </h2>
  <p class="text-sm text-gray-500 mb-4">
    "If stock drops/jumps post-print, what would have triggered it?" 각 시나리오의 확률 합계는 100%.
  </p>
  {quality_flag}
  <div class="card overflow-x-auto">
    <table class="w-full text-sm">
      <thead>
        <tr class="bg-gray-50 text-gray-600 text-xs uppercase">
          <th class="text-left p-3 font-semibold">시나리오</th>
          <th class="text-left p-3 font-semibold">트리거 (구체적 임계치)</th>
          <th class="text-center p-3 font-semibold">주가 영향</th>
          <th class="text-center p-3 font-semibold">확률</th>
          <th class="text-left p-3 font-semibold">메커니즘</th>
        </tr>
      </thead>
      <tbody>
        {''.join(rendered_rows)}
      </tbody>
      <tfoot>
        <tr class="bg-gray-100 font-semibold">
          <td colspan="3" class="p-3 text-right text-gray-700">확률 합계</td>
          <td class="text-center p-3 font-mono">{prob_total_pct}%</td>
          <td class="p-3"></td>
        </tr>
      </tfoot>
    </table>
  </div>
</section>
"""


def _preview_section_pre_print(analysis: dict[str, Any]) -> str:
    pos = analysis.get("pre_print_position") or {}
    rec = pos.get("recommendation") or "Hold"
    badge_class = {
        "Add": "bg-green-100 text-green-800",
        "Hold": "bg-blue-100 text-blue-800",
        "Trim": "bg-amber-100 text-amber-800",
        "Hedge": "bg-purple-100 text-purple-800",
    }.get(rec, "bg-gray-100 text-gray-800")
    label_map = {
        "Hold": "보유 / Hold",
        "Trim": "일부 매도 / Trim",
        "Hedge": "헤지 / Hedge",
        "Add": "추가 매수 / Add",
    }
    label = label_map.get(rec, rec)
    rationale = escape(pos.get("rationale") or "—")

    options_status = (analysis.get("options_snapshot") or {}).get("status")
    options_strategy = pos.get("options_strategy")
    options_block = ""
    if options_strategy and options_status == "available":
        options_block = f"""
<div class="card p-4 bg-purple-50 border border-purple-200 mt-3">
  <p class="text-sm font-bold text-purple-700 mb-1">
    <i class="fa-solid fa-arrows-spin mr-2"></i>
    옵션 전략 (catalyst-driven traders)
  </p>
  <p class="text-sm text-gray-700">{escape(options_strategy)}</p>
</div>
"""

    return f"""
<section id="section-pre-print">
  <h2 class="text-xl font-bold text-gray-900 mb-4">
    <i class="fa-solid fa-flag mr-2 text-orange-500"></i>
    6. Pre-Print 포지션 권고
  </h2>
  <div class="card p-6">
    <div class="flex items-center gap-3 mb-4">
      <span class="px-4 py-2 rounded-lg text-sm font-extrabold {badge_class}">
        {escape(label)}
      </span>
      <span class="text-xs text-gray-500">
        Hold / Trim / Hedge / Add 중 1개
      </span>
    </div>
    <p class="text-sm text-gray-700 leading-relaxed mb-4">
      {rationale}
    </p>
    {options_block}
  </div>
</section>
"""


def _preview_footer(analysis: dict[str, Any], data_sources: list[str]) -> str:
    ticker = escape(analysis.get("ticker") or "—")
    currency = analysis.get("currency") or "USD"
    sym = currency_symbol(currency)
    price = format_number(analysis.get("price_at_analysis"), 2)
    analysis_date = escape(analysis.get("analysis_date") or "—")
    window = analysis.get("earnings_window") or {}
    window_label = escape(window.get("window_label") or "—")
    sources_csv = ", ".join(data_sources) if data_sources else "—"

    return f"""
<footer class="bg-gray-900 text-gray-400 mt-12">
  <div class="max-w-7xl mx-auto px-4 sm:px-6 py-8">
    <div class="flex flex-col md:flex-row justify-between items-start gap-4">
      <div>
        <p class="text-xs mb-2">
          <strong class="text-gray-300">Disclaimer:</strong>
          본 리포트는 정보 제공 목적으로만 작성되었으며, 투자 권유나 매수/매도 추천이
          아닙니다. 실적 발표는 변동성이 큰 이벤트로, 본 분석의 시나리오는 발생 가능한
          경로 중 일부에 불과합니다. 모든 투자 의사결정은 본인의 리서치와 리스크 허용
          범위에 따라 수행하시기 바랍니다. This is not investment advice. For
          informational purposes only.
        </p>
        <p class="text-xs">
          Last Updated: {analysis_date} · Price: {sym}{price} ({ticker})
        </p>
      </div>
      <div class="text-xs text-right">
        <p>Sources: {escape(sources_csv)}</p>
        <p class="mt-1 text-gray-500">
          Mode E Preview · Window {window_label} · Generated {analysis_date}
        </p>
      </div>
    </div>
  </div>
</footer>
"""


def _preview_chart_script(analysis: dict[str, Any]) -> str:
    history = analysis.get("beat_miss_history") or {}
    quarters = history.get("quarters") or []
    if not quarters:
        return ""
    labels = [q.get("quarter") or "" for q in quarters if isinstance(q, dict)]
    values = []
    for q in quarters:
        if not isinstance(q, dict):
            continue
        v = q.get("surprise_pct")
        values.append(float(v) if isinstance(v, (int, float)) else 0.0)
    labels_js = _safe_json_for_script(labels)
    data_js = _safe_json_for_script(values)
    return f"""
<script>
(function() {{
  if (typeof Chart === 'undefined') return;
  const canvas = document.getElementById('beatMissChart');
  if (!canvas) return;
  const labels = {labels_js};
  const data = {data_js};
  const green = 'rgba(34,197,94,';
  const red = 'rgba(239,68,68,';
  new Chart(canvas.getContext('2d'), {{
    type: 'bar',
    data: {{
      labels: labels,
      datasets: [{{
        label: 'EPS Surprise %',
        data: data,
        backgroundColor: data.map(v => v >= 0 ? green + '0.7)' : red + '0.7)'),
        borderColor: data.map(v => v >= 0 ? green + '1)' : red + '1)'),
        borderWidth: 1,
        borderRadius: 6
      }}]
    }},
    options: {{
      responsive: true,
      plugins: {{
        legend: {{ display: false }},
        tooltip: {{ callbacks: {{ label: ctx => 'Surprise: ' + ctx.parsed.y.toFixed(1) + '%' }} }}
      }},
      scales: {{
        y: {{ grid: {{ color: 'rgba(0,0,0,0.05)' }}, ticks: {{ font: {{ size: 10 }}, callback: v => v + '%' }} }},
        x: {{ grid: {{ display: false }}, ticks: {{ font: {{ size: 10 }} }} }}
      }}
    }}
  }});
}})();
</script>
"""


def build_preview_html(analysis: dict[str, Any]) -> str:
    language = analysis.get("output_language") or "ko"
    ticker = escape(analysis.get("ticker") or "—")
    company = escape(analysis.get("company_name") or analysis.get("ticker") or "—")
    window = analysis.get("earnings_window") or {}
    quarter_label = quarter_from_date(window.get("next_earnings_date"))
    window_label = escape(window.get("window_label") or "—")

    # Collect tags from inputs for footer
    consensus = analysis.get("consensus_snapshot") or {}
    history = analysis.get("beat_miss_history") or {}
    options = analysis.get("options_snapshot") or {}
    summary = history.get("summary") or {}

    tag_candidates: list[str] = []
    eps_block = consensus.get("eps") or {}
    rev_block = consensus.get("revenue") or {}
    tag_candidates.append(eps_block.get("tag"))
    tag_candidates.append(rev_block.get("tag"))
    for seg in (consensus.get("segment_consensus") or []):
        if isinstance(seg, dict):
            tag_candidates.append(seg.get("tag"))
    tag_candidates.append(summary.get("tag"))
    for q in (history.get("quarters") or []):
        if isinstance(q, dict):
            tag_candidates.append(q.get("tag"))
    if options.get("status") == "available":
        tag_candidates.append(options.get("tag") or "[Options]")

    data_sources = collect_source_tags(*tag_candidates)

    parts = [
        f"""<!DOCTYPE html>
<html lang="{escape(language)}">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{company} ({ticker}) — {escape(quarter_label)} Earnings Preview ({window_label})</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/css/all.min.css">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
  {korean_font_link(language)}
  <style>
    * {{ font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Noto Sans KR', sans-serif; }}
    .card {{ background: #fff; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.06); transition: transform 0.2s, box-shadow 0.2s; }}
    .card:hover {{ transform: translateY(-2px); box-shadow: 0 4px 14px rgba(0,0,0,0.1); }}
    .source-tag {{ font-family: monospace; font-size: 0.7rem; padding: 1px 5px; border-radius: 3px; background: #f3f4f6; }}
    .tag-est {{ color: #b45309; }}
    .tag-options {{ color: #7c3aed; }}
    .tag-history {{ color: #0e7490; }}
    .tag-calc {{ color: #059669; }}
    .tag-company {{ color: #2563eb; }}
    .tag-filing {{ color: #1e3f80; }}
    .badge-d {{ background: #fb923c; color: #fff; }}
    ::-webkit-scrollbar {{ width: 6px; }}
    ::-webkit-scrollbar-thumb {{ background: #cbd5e1; border-radius: 3px; }}
  </style>
</head>
<body class="bg-gray-50 text-gray-800">
""",
        _preview_hero(analysis),
        '<main class="max-w-7xl mx-auto px-4 sm:px-6 py-8 space-y-8">',
        _preview_section_consensus(analysis),
        _preview_section_history(analysis),
        _preview_section_key_questions(analysis),
        _preview_section_options(analysis),
        _preview_section_pre_mortem(analysis),
        _preview_section_pre_print(analysis),
        "</main>",
        _preview_footer(analysis, data_sources),
        _preview_chart_script(analysis),
        "</body></html>",
    ]
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Review renderer
# ---------------------------------------------------------------------------


def _review_hero(analysis: dict[str, Any]) -> str:
    ticker = escape(analysis.get("ticker") or "—")
    company = escape(analysis.get("company_name") or analysis.get("ticker") or "—")
    window = analysis.get("earnings_window") or {}
    window_label = escape(window.get("window_label") or "D+?")
    actual_date = window.get("actual_earnings_date")
    quarter_label = quarter_from_date(actual_date)

    actual_vs = analysis.get("actual_vs_consensus") or {}
    eps_block = actual_vs.get("eps") or {}
    beat = bool(eps_block.get("beat"))
    eps_surprise = format_number(eps_block.get("surprise_pct"), 1)

    if beat:
        gradient = "linear-gradient(135deg, #064e3b 0%, #047857 30%, #059669 60%, #10b981 100%)"
        badge_class = "badge-d-plus"
        flag_class = "bg-green-500/20 text-green-100"
        beat_icon = "circle-check"
        beat_label = "BEAT"
    else:
        gradient = "linear-gradient(135deg, #7f1d1d 0%, #b91c1c 30%, #dc2626 60%, #f97316 100%)"
        badge_class = "badge-d-plus-miss"
        flag_class = "bg-red-500/20 text-red-100"
        beat_icon = "circle-xmark"
        beat_label = "MISS"

    stock_reaction = analysis.get("stock_reaction") or {}
    post_market = stock_reaction.get("post_market_pct")
    next_day = stock_reaction.get("next_day_pct")
    post_market_html = format_signed_percent_or_dash(post_market, 1)
    next_day_html = format_signed_percent_or_dash(next_day, 1)

    light_verdict = analysis.get("light_verdict_update") or {}
    prior_verdict = escape(light_verdict.get("prior_verdict") or "—")
    updated_verdict = escape(light_verdict.get("updated_verdict") or "—")

    currency = analysis.get("currency") or "USD"
    sym = currency_symbol(currency)
    price = format_number(analysis.get("price_at_analysis"), 2)
    analysis_date = escape(analysis.get("analysis_date") or "—")
    data_mode = escape(analysis.get("data_mode") or "standard")
    actual_date_html = escape(actual_date or "—")

    return f"""
<header style="background: {gradient};">
  <div class="max-w-7xl mx-auto px-4 sm:px-6 py-8">
    <div class="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
      <div>
        <div class="flex items-center gap-3 mb-2">
          <span class="{badge_class} px-3 py-1.5 rounded-lg text-sm font-extrabold tracking-wide">
            {window_label}
          </span>
          <h1 class="text-3xl font-bold text-white tracking-tight">
            {company} <span class="text-white/80 text-xl font-mono">{ticker}</span>
          </h1>
        </div>
        <p class="text-white/90 text-sm font-semibold mt-1">
          {escape(quarter_label)} EARNINGS REVIEW
        </p>
        <div class="flex items-center gap-3 mt-3">
          <span class="px-3 py-1 rounded-full text-sm font-bold {flag_class}">
            <i class="fa-solid fa-{beat_icon} mr-1"></i>
            {beat_label}
          </span>
          <span class="text-white/80 text-sm">
            EPS surprise <span class="font-semibold">{eps_surprise}%</span>
          </span>
        </div>
      </div>
      <div class="flex flex-col gap-2 text-right">
        <div class="grid grid-cols-2 gap-x-6 gap-y-1 text-sm">
          <span class="text-white/70">Post-market</span>
          <span class="text-white font-semibold">{post_market_html}</span>
          <span class="text-white/70">Next-day</span>
          <span class="text-white font-semibold">{next_day_html}</span>
          <span class="text-white/70">Verdict</span>
          <span class="text-white font-semibold">{prior_verdict} → {updated_verdict}</span>
          <span class="text-white/70">현재가</span>
          <span class="text-white font-semibold">{sym}{price}</span>
        </div>
      </div>
    </div>
    <div class="mt-4 pt-4 border-t border-white/10 flex flex-wrap gap-4 text-xs text-white/60">
      <span>분석일: {analysis_date}</span>
      <span>·</span>
      <span>모드: Earnings Review (E)</span>
      <span>·</span>
      <span>발표일: {actual_date_html}</span>
      <span>·</span>
      <span>데이터: {data_mode}</span>
    </div>
  </div>
</header>
"""


def _review_section_print_snapshot(analysis: dict[str, Any]) -> str:
    av = analysis.get("actual_vs_consensus") or {}
    eps = av.get("eps") or {}
    rev = av.get("revenue") or {}
    segments = av.get("segments") or []
    om = av.get("operating_margin")

    def beat_bits(beat: Any) -> tuple[str, str, str]:
        is_beat = bool(beat)
        color = "text-green-600" if is_beat else "text-red-600"
        badge = "bg-green-100 text-green-800" if is_beat else "bg-red-100 text-red-800"
        label = "Beat" if is_beat else "Miss"
        return color, badge, label

    eps_color, eps_badge, eps_label = beat_bits(eps.get("beat"))
    rev_color, rev_badge, rev_label = beat_bits(rev.get("beat"))

    rev_unit = (rev.get("unit") or "").lower()
    currency_unit = "M USD" if rev_unit in {"millions_usd", "million_usd"} else (
        "B USD" if rev_unit == "billions_usd" else escape(rev.get("unit") or "—")
    )

    seg_rows: list[str] = []
    for seg in segments:
        if not isinstance(seg, dict):
            continue
        s_color, s_badge, s_label = beat_bits(seg.get("beat"))
        actual = seg.get("actual")
        consensus = seg.get("consensus")
        actual_str = format_number(actual, 1)
        consensus_str = format_number(consensus, 1)
        if (isinstance(actual, (int, float)) and isinstance(consensus, (int, float))
                and not isinstance(actual, bool) and not isinstance(consensus, bool)
                and consensus):
            surprise_pct = (actual - consensus) / abs(consensus) * 100
            surprise_str = f"{surprise_pct:+.1f}%"
        else:
            surprise_str = "—"
        seg_rows.append(
            "<tr class=\"border-b\">"
            f"<td class=\"p-3 text-gray-700\">{escape(seg.get('segment') or '—')} ({escape(seg.get('metric') or '')})</td>"
            f"<td class=\"text-right p-3\">{actual_str}</td>"
            f"<td class=\"text-right p-3 text-gray-500\">{consensus_str}</td>"
            f"<td class=\"text-right p-3 {s_color}\">{surprise_str}</td>"
            f"<td class=\"text-center p-3\"><span class=\"inline-block px-2 py-0.5 rounded text-xs font-bold {s_badge}\">{s_label}</span></td>"
            "<td class=\"text-right p-3\"><span class=\"source-tag tag-company\">[Company]</span></td>"
            "</tr>"
        )

    om_row = ""
    if isinstance(om, dict) and om.get("actual") is not None:
        o_color, o_badge, o_label = beat_bits(om.get("beat"))
        om_actual_pct = format_number((om.get("actual") or 0) * 100, 1)
        om_consensus_pct = format_number((om.get("consensus") or 0) * 100, 1)
        delta_pp = om.get("delta_pp")
        delta_str = f"{delta_pp:+.1f}pp" if isinstance(delta_pp, (int, float)) else "—"
        om_row = f"""
<tr class="border-b">
  <td class="p-3 text-gray-700">영업이익률</td>
  <td class="text-right p-3">{om_actual_pct}%</td>
  <td class="text-right p-3 text-gray-500">{om_consensus_pct}%</td>
  <td class="text-right p-3 {o_color}">{delta_str}</td>
  <td class="text-center p-3"><span class="inline-block px-2 py-0.5 rounded text-xs font-bold {o_badge}">{o_label}</span></td>
  <td class="text-right p-3"><span class="source-tag tag-filing">[Filing]</span></td>
</tr>
"""

    eps_actual = format_number(eps.get("actual"), 2)
    eps_consensus = format_number(eps.get("consensus"), 2)
    eps_surprise = format_number(eps.get("surprise_pct"), 1)
    rev_actual = format_revenue(rev.get("actual"), rev.get("unit"))
    rev_consensus = format_revenue(rev.get("consensus"), rev.get("unit"))
    rev_surprise = format_number(rev.get("surprise_pct"), 1)

    return f"""
<section id="section-print-snapshot">
  <h2 class="text-xl font-bold text-gray-900 mb-4">
    <i class="fa-solid fa-table-cells mr-2 text-emerald-600"></i>
    1. Print Snapshot
  </h2>
  <div class="card overflow-x-auto">
    <table class="w-full text-sm">
      <thead>
        <tr class="bg-gray-50 text-gray-600 text-xs uppercase">
          <th class="text-left p-3 font-semibold">항목</th>
          <th class="text-right p-3 font-semibold">Actual</th>
          <th class="text-right p-3 font-semibold">Consensus</th>
          <th class="text-right p-3 font-semibold">Surprise %</th>
          <th class="text-center p-3 font-semibold">Beat?</th>
          <th class="text-right p-3 font-semibold">출처</th>
        </tr>
      </thead>
      <tbody>
        <tr class="border-b font-semibold">
          <td class="p-3">EPS</td>
          <td class="text-right p-3">{eps_actual}</td>
          <td class="text-right p-3 text-gray-500">{eps_consensus}</td>
          <td class="text-right p-3 {eps_color}">{eps_surprise}%</td>
          <td class="text-center p-3"><span class="inline-block px-2 py-0.5 rounded text-xs font-bold {eps_badge}">{eps_label}</span></td>
          <td class="text-right p-3"><span class="source-tag tag-company">[Company]</span></td>
        </tr>
        <tr class="border-b font-semibold">
          <td class="p-3">매출 ({currency_unit})</td>
          <td class="text-right p-3">{rev_actual}</td>
          <td class="text-right p-3 text-gray-500">{rev_consensus}</td>
          <td class="text-right p-3 {rev_color}">{rev_surprise}%</td>
          <td class="text-center p-3"><span class="inline-block px-2 py-0.5 rounded text-xs font-bold {rev_badge}">{rev_label}</span></td>
          <td class="text-right p-3"><span class="source-tag tag-company">[Company]</span></td>
        </tr>
        {''.join(seg_rows)}
        {om_row}
      </tbody>
    </table>
  </div>
  <p class="text-xs text-gray-400 mt-3 italic">
    Surprise % = (actual − consensus) / |consensus| × 100. Beat 정의: top-line은 surprise &gt; 0, cost 항목은 surprise &lt; 0.
  </p>
</section>
"""


def _review_section_guidance(analysis: dict[str, Any]) -> str:
    g = analysis.get("guidance_delta") or {}
    if not g:
        return """
<section id="section-guidance">
  <h2 class="text-xl font-bold text-gray-900 mb-4">
    <i class="fa-solid fa-arrow-trend-up mr-2 text-emerald-600"></i>
    2. 가이던스 업데이트
  </h2>
  <p class="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded p-3">
    [Quality flag: missing guidance delta]
  </p>
</section>
"""

    currency = analysis.get("currency") or "USD"
    sym = currency_symbol(currency)
    fy_pre = format_number(g.get("fy_eps_consensus_pre"), 2)
    fy_post = format_number(g.get("fy_eps_consensus_post"), 2)
    delta_pct_value = g.get("delta_pct")
    if isinstance(delta_pct_value, (int, float)) and not isinstance(delta_pct_value, bool):
        delta_str = f"{delta_pct_value:+.1f}"
        if delta_pct_value > 0:
            delta_color = "text-green-600"
        elif delta_pct_value < 0:
            delta_color = "text-red-600"
        else:
            delta_color = "text-gray-600"
    else:
        delta_str = "—"
        delta_color = "text-gray-600"

    tone = (g.get("tone") or "").lower()
    tone_label = {"raised": "상향", "maintained": "유지", "lowered": "하향"}.get(tone, escape(g.get("tone") or "—"))
    tone_color = {"raised": "text-green-600", "lowered": "text-red-600"}.get(tone, "text-gray-600")
    company_change = escape(g.get("company_guidance_change") or "—")

    return f"""
<section id="section-guidance">
  <h2 class="text-xl font-bold text-gray-900 mb-4">
    <i class="fa-solid fa-arrow-trend-up mr-2 text-emerald-600"></i>
    2. 가이던스 업데이트
  </h2>
  <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
    <div class="card p-5 text-center">
      <p class="text-xs text-gray-500 mb-1">FY EPS 컨센서스 (Pre)</p>
      <p class="text-3xl font-bold text-gray-700">{sym}{fy_pre}</p>
      <p class="text-[10px] text-gray-400 mt-1"><span class="source-tag tag-est">[Est]</span></p>
    </div>
    <div class="card p-5 text-center">
      <p class="text-xs text-gray-500 mb-1">FY EPS 컨센서스 (Post)</p>
      <p class="text-3xl font-bold text-emerald-600">{sym}{fy_post}</p>
      <p class="text-[10px] text-gray-400 mt-1"><span class="source-tag tag-est">[Est]</span></p>
    </div>
    <div class="card p-5 text-center">
      <p class="text-xs text-gray-500 mb-1">변화</p>
      <p class="text-3xl font-bold {delta_color}">
        {delta_str}%
      </p>
      <p class="text-xs text-gray-400 mt-1">
        Tone: <strong class="{tone_color}">{tone_label}</strong>
      </p>
    </div>
  </div>
  <div class="card p-5 mt-4 bg-blue-50 border border-blue-200">
    <p class="text-sm font-bold text-blue-800 mb-2">
      <i class="fa-solid fa-bullhorn mr-2"></i>
      회사 가이던스 변화
    </p>
    <p class="text-sm text-gray-700">{company_change}</p>
  </div>
</section>
"""


def _review_section_questions_answered(analysis: dict[str, Any]) -> str:
    questions = analysis.get("key_questions_answered") or []
    if not questions:
        return """
<section id="section-questions-answered">
  <h2 class="text-xl font-bold text-gray-900 mb-4">
    <i class="fa-solid fa-circle-check mr-2 text-emerald-600"></i>
    3. 핵심 질문 답변 (vs Preview)
  </h2>
  <div class="card p-5 bg-gray-50 border border-gray-200 text-center">
    <p class="text-sm text-gray-500 italic">이전 Preview가 없어 핵심 질문 추적 불가</p>
  </div>
</section>
"""

    cards: list[str] = []
    for idx, q in enumerate(questions, start=1):
        if not isinstance(q, dict):
            continue
        status = (q.get("answer_status") or "").lower()
        border_class = {
            "yes": "border-green-500",
            "no": "border-red-500",
            "partial": "border-amber-500",
        }.get(status, "border-gray-300")
        badge_class = {
            "yes": "bg-green-100 text-green-800",
            "no": "bg-red-100 text-red-800",
            "partial": "bg-amber-100 text-amber-800",
        }.get(status, "bg-gray-100 text-gray-700")
        status_label = {
            "yes": "✓ YES",
            "no": "✗ NO",
            "partial": "± 부분",
        }.get(status, escape(q.get("answer_status") or "—"))
        cards.append(f"""
<div class="card p-5 border-l-4 {border_class}">
  <p class="text-sm font-bold text-gray-800 mb-2">
    Q{idx}. {escape(q.get('question') or '—')}
  </p>
  <div class="flex items-center gap-2 mb-3">
    <span class="px-2 py-0.5 rounded text-xs font-bold {badge_class}">
      {status_label}
    </span>
    <span class="text-xs text-gray-500">실제 데이터</span>
  </div>
  <p class="text-sm text-gray-700 mb-3"><strong>실제:</strong> {escape(q.get('actual_data') or '—')}</p>
  <p class="text-xs text-gray-600 italic">
    <strong>Thesis 영향:</strong> {escape(q.get('thesis_impact') or '—')}
  </p>
</div>
""")

    return f"""
<section id="section-questions-answered">
  <h2 class="text-xl font-bold text-gray-900 mb-4">
    <i class="fa-solid fa-circle-check mr-2 text-emerald-600"></i>
    3. 핵심 질문 답변 (vs Preview)
  </h2>
  <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
    {''.join(cards)}
  </div>
</section>
"""


_STATUS_BADGE = {
    "Strengthened": "bg-emerald-100 text-emerald-800",
    "On track": "bg-blue-100 text-blue-800",
    "Watching": "bg-gray-100 text-gray-700",
    "Weakened": "bg-amber-100 text-amber-800",
    "Broken": "bg-red-100 text-red-800",
    "Confirmed": "bg-emerald-100 text-emerald-800",
}
_TREND_COLOR = {
    "Positive": "text-green-600",
    "Stable": "text-gray-500",
    "Negative": "text-red-600",
}
_TREND_ARROW = {
    "Positive": "↑",
    "Stable": "→",
    "Negative": "↓",
}


def _pillar_rows(pillars: Any) -> str:
    if not isinstance(pillars, list) or not pillars:
        return '<p class="text-xs text-gray-400 italic">No pillars tracked.</p>'
    rendered: list[str] = []
    for p in pillars:
        if not isinstance(p, dict):
            continue
        prior = p.get("prior_status") or "—"
        current = p.get("current_status") or "—"
        prior_badge = _STATUS_BADGE.get(prior, "bg-gray-100 text-gray-700")
        current_badge = _STATUS_BADGE.get(current, "bg-gray-100 text-gray-700")
        trend = p.get("trend") or "Stable"
        trend_color = _TREND_COLOR.get(trend, "text-gray-500")
        trend_label = f"{_TREND_ARROW.get(trend, '→')} {trend}"
        rendered.append(f"""
<div class="border-b last:border-b-0 pb-3 last:pb-0">
  <p class="font-semibold text-gray-800 text-sm mb-1">{escape(p.get('pillar') or '—')}</p>
  <p class="text-xs text-gray-500 mb-2">
    <span class="inline-block px-2 py-0.5 rounded {prior_badge}">{escape(prior)}</span>
    <i class="fa-solid fa-arrow-right text-gray-400 mx-1"></i>
    <span class="inline-block px-2 py-0.5 rounded {current_badge}">{escape(current)}</span>
    <span class="ml-2 text-xs {trend_color}">{escape(trend_label)}</span>
  </p>
  <p class="text-xs text-gray-700">{escape(p.get('evidence') or '—')}</p>
</div>
""")
    return "".join(rendered)


def _review_section_thesis_impact(analysis: dict[str, Any]) -> str:
    thesis = analysis.get("thesis_impact") or {}
    prior_date = thesis.get("prior_mode_c_date")
    if not prior_date:
        return """
<section id="section-thesis-impact" class="opacity-90">
  <h2 class="text-xl font-bold text-gray-900 mb-4">
    <i class="fa-solid fa-scale-balanced mr-2 text-emerald-600"></i>
    4. Thesis Impact
  </h2>
  <div class="card p-6 bg-amber-50 border border-amber-200">
    <p class="text-sm text-amber-800">
      <i class="fa-solid fa-circle-info mr-1"></i>
      <strong>No prior Mode C baseline</strong> — first-look review
    </p>
    <p class="text-xs text-amber-700 mt-2">
      이 종목은 이전 Mode C 분석 snapshot이 없어 thesis pillar 변화를 추적할 수 없습니다.
    </p>
    <p class="text-xs text-amber-700 mt-2">
      Mode C 분석을 먼저 실행하면 다음 실적 발표 시 thesis 변화를 자동으로 추적할 수 있습니다.
    </p>
  </div>
</section>
"""

    long_pillars = _pillar_rows(thesis.get("long_pillars"))
    short_pillars = _pillar_rows(thesis.get("short_pillars"))

    return f"""
<section id="section-thesis-impact">
  <h2 class="text-xl font-bold text-gray-900 mb-4">
    <i class="fa-solid fa-scale-balanced mr-2 text-emerald-600"></i>
    4. Thesis Impact (vs prior Mode C, {escape(prior_date)})
  </h2>
  <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
    <div class="card p-6 border-l-4 border-green-500">
      <h3 class="text-lg font-bold text-green-700 mb-3">
        <i class="fa-solid fa-arrow-trend-up mr-2"></i>Long Pillars
      </h3>
      <div class="space-y-3">
        {long_pillars}
      </div>
    </div>
    <div class="card p-6 border-l-4 border-red-500">
      <h3 class="text-lg font-bold text-red-700 mb-3">
        <i class="fa-solid fa-arrow-trend-down mr-2"></i>Short Pillars
      </h3>
      <div class="space-y-3">
        {short_pillars}
      </div>
    </div>
  </div>
</section>
"""


def _verdict_change_label(prior: str | None, updated: str | None) -> str:
    if prior is None or updated is None:
        return "—"
    if prior == updated:
        return "유지"
    if prior == "관찰" and updated == "비중확대":
        return "상향 ↑"
    if prior == "비중확대" and updated == "관찰":
        return "하향 ↓"
    if prior == "관찰" and updated == "비중축소":
        return "하향 ↓"
    if prior == "비중축소" and updated == "관찰":
        return "상향 ↑"
    return f"{prior} → {updated}"


def _review_section_light_verdict(analysis: dict[str, Any]) -> str:
    light = analysis.get("light_verdict_update") or {}
    prior_rr = light.get("prior_rr_score")

    if prior_rr is None:
        reason = escape(light.get("reason") or "이전 Mode C 분석이 없어 R/R Score 비교가 불가능합니다.")
        return f"""
<section id="section-light-verdict" class="opacity-90">
  <h2 class="text-xl font-bold text-gray-900 mb-4">
    <i class="fa-solid fa-flag-checkered mr-2 text-emerald-600"></i>
    5. Light Verdict Update
  </h2>
  <div class="card p-6 bg-amber-50 border border-amber-200">
    <p class="text-sm text-amber-800">
      <i class="fa-solid fa-circle-info mr-1"></i>
      <strong>Mode C 재실행으로 R/R 산출 권고</strong>
    </p>
    <p class="text-xs text-amber-700 mt-2">
      {reason}
    </p>
  </div>
</section>
"""

    prior_rr_str = format_number(prior_rr, 2)
    thesis = analysis.get("thesis_impact") or {}
    prior_mode_c_date = escape(thesis.get("prior_mode_c_date") or "—")
    prior_verdict = escape(light.get("prior_verdict") or "—")
    updated_verdict = escape(light.get("updated_verdict") or "—")
    change_label = escape(_verdict_change_label(light.get("prior_verdict"), light.get("updated_verdict")))
    reason = escape(light.get("reason") or "—")

    outdated_flag = bool(light.get("outdated_flag"))
    if outdated_flag:
        updated_card = """
<div class="text-center p-4 bg-amber-50 rounded-lg badge-outdated">
  <p class="text-xs text-amber-800 mb-1">Updated R/R Score</p>
  <p class="text-3xl font-bold text-amber-700">—</p>
  <p class="text-xs text-amber-700 mt-1">
    <i class="fa-solid fa-triangle-exclamation mr-1"></i>
    Outdated · DCF 미재실행
  </p>
</div>
"""
    else:
        updated_rr = light.get("updated_rr_score")
        updated_rr_str = format_number(updated_rr, 2) if isinstance(updated_rr, (int, float)) else "—"
        updated_card = f"""
<div class="text-center p-4 bg-emerald-50 rounded-lg">
  <p class="text-xs text-emerald-800 mb-1">Updated R/R Score</p>
  <p class="text-3xl font-bold text-emerald-700">{updated_rr_str}</p>
  <p class="text-xs text-emerald-700 mt-1">Light recompute</p>
</div>
"""

    return f"""
<section id="section-light-verdict">
  <h2 class="text-xl font-bold text-gray-900 mb-4">
    <i class="fa-solid fa-flag-checkered mr-2 text-emerald-600"></i>
    5. Light Verdict Update
  </h2>
  <div class="card p-6">
    <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
      <div class="text-center p-4 bg-gray-50 rounded-lg">
        <p class="text-xs text-gray-500 mb-1">Prior R/R Score</p>
        <p class="text-3xl font-bold text-gray-700">{prior_rr_str}</p>
        <p class="text-xs text-gray-400 mt-1">Mode C, {prior_mode_c_date}</p>
      </div>
      {updated_card}
      <div class="text-center p-4 bg-blue-50 rounded-lg">
        <p class="text-xs text-blue-700 mb-1">Verdict</p>
        <p class="text-2xl font-bold text-blue-700">{prior_verdict} → {updated_verdict}</p>
        <p class="text-xs text-blue-600 mt-1">{change_label}</p>
      </div>
    </div>
    <div class="card p-4 bg-gray-50 border border-gray-200 mt-3">
      <p class="text-sm font-bold text-gray-700 mb-2">
        <i class="fa-solid fa-info-circle mr-1"></i>
        업데이트 사유
      </p>
      <p class="text-sm text-gray-700 leading-relaxed">{reason}</p>
    </div>
  </div>
</section>
"""


def _review_section_post_print(analysis: dict[str, Any]) -> str:
    action = analysis.get("post_print_action") or {}
    rec = action.get("recommendation") or "Hold"
    badge_class = {
        "Add": "bg-green-100 text-green-800",
        "Hold": "bg-blue-100 text-blue-800",
        "Trim": "bg-amber-100 text-amber-800",
        "Reverse": "bg-red-100 text-red-800",
    }.get(rec, "bg-gray-100 text-gray-800")

    label_map = {
        "Hold": "보유 / Hold",
        "Trim": "일부 매도 / Trim",
        "Add": "추가 매수 / Add",
        "Reverse": "포지션 전환 / Reverse",
    }
    label = label_map.get(rec, rec)
    rationale = escape(action.get("rationale") or "—")

    currency = analysis.get("currency") or "USD"
    sym = currency_symbol(currency)

    def render_levels(rows: Any, kind: str) -> str:
        if not isinstance(rows, list) or not rows:
            if rec == "Hold":
                return '<li class="text-gray-400 italic">(해당 없음 — 현재 권고 = Hold 또는 Trim)</li>'
            return ('<li class="text-amber-700 italic">'
                    '[Quality flag: missing actionable level]</li>')
        rendered: list[str] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            price_text = format_number(row.get("price"), 2)
            trigger = escape(row.get("trigger") or "—")
            if kind == "entry":
                color = "text-green-700"
                detail = f"Size: {escape(row.get('size') or '—')}"
            else:
                color = "text-rose-700"
                detail = f"Action: {escape(row.get('action') or '—')}"
            rendered.append(f"""
<li class="flex items-start gap-2 border-b last:border-b-0 pb-2 last:pb-0">
  <span class="font-mono font-bold {color} w-20 flex-shrink-0">
    {sym}{price_text}
  </span>
  <span class="flex-1">
    {trigger}
    <span class="block text-gray-400 text-[10px] mt-0.5">{detail}</span>
  </span>
</li>
""")
        return "".join(rendered)

    entry_html = render_levels(action.get("entry_levels"), "entry")
    exit_html = render_levels(action.get("exit_levels"), "exit")

    return f"""
<section id="section-post-print">
  <h2 class="text-xl font-bold text-gray-900 mb-4">
    <i class="fa-solid fa-bullseye mr-2 text-emerald-600"></i>
    6. Post-Print 액션 권고
  </h2>
  <div class="card p-6">
    <div class="flex items-center gap-3 mb-4">
      <span class="px-4 py-2 rounded-lg text-sm font-extrabold {badge_class}">
        {escape(label)}
      </span>
      <span class="text-xs text-gray-500">
        Add / Trim / Hold / Reverse 중 1개
      </span>
    </div>
    <p class="text-sm text-gray-700 leading-relaxed mb-5">
      {rationale}
    </p>
    <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
      <div class="card p-4 bg-green-50 border border-green-200">
        <p class="text-sm font-bold text-green-800 mb-2">
          <i class="fa-solid fa-arrow-down-to-line mr-1"></i>
          Entry Levels
        </p>
        <ul class="text-xs text-gray-700 space-y-2">
          {entry_html}
        </ul>
      </div>
      <div class="card p-4 bg-rose-50 border border-rose-200">
        <p class="text-sm font-bold text-rose-800 mb-2">
          <i class="fa-solid fa-arrow-up-from-line mr-1"></i>
          Exit Levels
        </p>
        <ul class="text-xs text-gray-700 space-y-2">
          {exit_html}
        </ul>
      </div>
    </div>
  </div>
</section>
"""


def _mode_c_rerun_banner(analysis: dict[str, Any]) -> str:
    light = analysis.get("light_verdict_update") or {}
    if not light.get("mode_c_rerun_recommended"):
        return ""
    rerun_window = escape(light.get("rerun_window") or "D+2 ~ D+5")
    thesis = analysis.get("thesis_impact") or {}
    prior_mode_c_date = escape(thesis.get("prior_mode_c_date") or "—")
    ticker = escape(analysis.get("ticker") or "")
    return f"""
<div class="max-w-7xl mx-auto px-4 sm:px-6 mb-8">
  <div class="card p-5 bg-gradient-to-r from-blue-50 to-indigo-50 border-2 border-blue-300">
    <div class="flex items-start gap-3">
      <div class="w-10 h-10 bg-blue-500 rounded-full flex items-center justify-center flex-shrink-0">
        <i class="fa-solid fa-arrows-rotate text-white"></i>
      </div>
      <div class="flex-1">
        <p class="text-sm font-bold text-blue-900 mb-1">
          Mode C 재실행 권고 (다음 윈도우: {rerun_window})
        </p>
        <p class="text-xs text-gray-700 mb-2">
          이번 Review는 forward EPS 컨센서스만 light recompute한 결과입니다.
          DCF / Bull-Base-Bear target / R/R Score는 prior Mode C 시점 ({prior_mode_c_date}) 그대로 유지되며 outdated로 표시됩니다.
          가격 발견 메커니즘이 안정화되는 D+2 ~ D+5 사이에 Mode C를 재실행하면 새로운 실적 데이터를
          반영한 valuation을 얻을 수 있습니다.
        </p>
        <p class="text-xs text-blue-600 font-mono">
          명령 예시: "{ticker} 다시 분석해줘" 또는 "{ticker} Mode C"
        </p>
      </div>
    </div>
  </div>
</div>
"""


def _review_footer(analysis: dict[str, Any], data_sources: list[str]) -> str:
    ticker = escape(analysis.get("ticker") or "—")
    currency = analysis.get("currency") or "USD"
    sym = currency_symbol(currency)
    price = format_number(analysis.get("price_at_analysis"), 2)
    analysis_date = escape(analysis.get("analysis_date") or "—")
    window = analysis.get("earnings_window") or {}
    window_label = escape(window.get("window_label") or "—")
    sources_csv = ", ".join(data_sources) if data_sources else "—"

    return f"""
<footer class="bg-gray-900 text-gray-400 mt-8">
  <div class="max-w-7xl mx-auto px-4 sm:px-6 py-8">
    <div class="flex flex-col md:flex-row justify-between items-start gap-4">
      <div>
        <p class="text-xs mb-2">
          <strong class="text-gray-300">Disclaimer:</strong>
          본 리포트는 정보 제공 목적으로만 작성되었으며, 투자 권유나 매수/매도 추천이 아닙니다.
          실적 발표 직후의 주가 반응은 단기 가격 발견 과정으로, 본 분석의 권고 레벨은 발생
          가능한 경로 중 일부에 불과합니다. 모든 투자 의사결정은 본인의 리서치와 리스크 허용
          범위에 따라 수행하시기 바랍니다. This is not investment advice. For
          informational purposes only.
        </p>
        <p class="text-xs">
          Last Updated: {analysis_date} · Price: {sym}{price} ({ticker})
        </p>
      </div>
      <div class="text-xs text-right">
        <p>Sources: {escape(sources_csv)}</p>
        <p class="mt-1 text-gray-500">
          Mode E Review · Window {window_label} · Generated {analysis_date}
        </p>
      </div>
    </div>
  </div>
</footer>
"""


def build_review_html(analysis: dict[str, Any]) -> str:
    language = analysis.get("output_language") or "ko"
    ticker = escape(analysis.get("ticker") or "—")
    company = escape(analysis.get("company_name") or analysis.get("ticker") or "—")
    window = analysis.get("earnings_window") or {}
    quarter_label = quarter_from_date(window.get("actual_earnings_date"))
    window_label = escape(window.get("window_label") or "—")

    # Collect tags
    av = analysis.get("actual_vs_consensus") or {}
    eps_block = av.get("eps") or {}
    rev_block = av.get("revenue") or {}
    om_block = av.get("operating_margin") or {}
    stock_reaction = analysis.get("stock_reaction") or {}
    guidance = analysis.get("guidance_delta") or {}

    tag_candidates = [
        eps_block.get("tag"),
        rev_block.get("tag"),
        om_block.get("tag"),
        stock_reaction.get("tag"),
        guidance.get("tag"),
    ]
    for seg in (av.get("segments") or []):
        if isinstance(seg, dict):
            tag_candidates.append(seg.get("tag"))
    # Sweep tags from key_questions_answered (Section 3) and thesis_impact
    # pillars (Section 4) so the Review footer Sources line is symmetric
    # with the Preview side (which sweeps segment_consensus[*].tag).
    for q in (analysis.get("key_questions_answered") or []):
        if isinstance(q, dict):
            tag_candidates.append(q.get("tag"))
    thesis = analysis.get("thesis_impact") or {}
    for pillar_key in ("long_pillars", "short_pillars"):
        for pillar in (thesis.get(pillar_key) or []):
            if isinstance(pillar, dict):
                tag_candidates.append(pillar.get("tag"))
    data_sources = collect_source_tags(*tag_candidates)

    parts = [
        f"""<!DOCTYPE html>
<html lang="{escape(language)}">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{company} ({ticker}) — {escape(quarter_label)} Earnings Review ({window_label})</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/css/all.min.css">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
  {korean_font_link(language)}
  <style>
    * {{ font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Noto Sans KR', sans-serif; }}
    .card {{ background: #fff; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.06); transition: transform 0.2s, box-shadow 0.2s; }}
    .card:hover {{ transform: translateY(-2px); box-shadow: 0 4px 14px rgba(0,0,0,0.1); }}
    .source-tag {{ font-family: monospace; font-size: 0.7rem; padding: 1px 5px; border-radius: 3px; background: #f3f4f6; }}
    .tag-est {{ color: #b45309; }}
    .tag-history {{ color: #0e7490; }}
    .tag-calc {{ color: #059669; }}
    .tag-company {{ color: #2563eb; }}
    .tag-filing {{ color: #1e3f80; }}
    .tag-portal {{ color: #4b5563; }}
    .badge-d-plus {{ background: #10b981; color: #fff; }}
    .badge-d-plus-miss {{ background: #ef4444; color: #fff; }}
    .badge-outdated {{
      background: repeating-linear-gradient(45deg, #fef3c7, #fef3c7 6px, #fde68a 6px, #fde68a 12px);
      color: #92400e;
      border: 1px dashed #d97706;
      font-style: italic;
    }}
    ::-webkit-scrollbar {{ width: 6px; }}
    ::-webkit-scrollbar-thumb {{ background: #cbd5e1; border-radius: 3px; }}
  </style>
</head>
<body class="bg-gray-50 text-gray-800">
""",
        _review_hero(analysis),
        '<main class="max-w-7xl mx-auto px-4 sm:px-6 py-8 space-y-8">',
        _review_section_print_snapshot(analysis),
        _review_section_guidance(analysis),
        _review_section_questions_answered(analysis),
        _review_section_thesis_impact(analysis),
        _review_section_light_verdict(analysis),
        _review_section_post_print(analysis),
        "</main>",
        _mode_c_rerun_banner(analysis),
        _review_footer(analysis, data_sources),
        "</body></html>",
    ]
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Dispatch + atomic write
# ---------------------------------------------------------------------------


def _default_report_path(analysis: dict[str, Any]) -> Path:
    """Compute default `output/reports/{ticker}_E_{sub}_{lang}_{date}.html`."""
    ticker = (analysis.get("ticker") or "UNKNOWN").upper()
    sub_mode = (analysis.get("earnings_sub_mode") or "preview").lower()
    lang = (analysis.get("output_language") or "ko").upper()
    date = analysis.get("analysis_date")
    if not date:
        from datetime import datetime, timezone
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    fname = f"{ticker}_E_{sub_mode}_{lang}_{date}.html"
    return data_path("reports", fname)


def _atomic_write(target: Path, content: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(target)


def render_earnings(analysis: dict[str, Any], output_path: Optional[str] = None) -> str:
    """Dispatch on `earnings_sub_mode`. Returns the absolute output path written."""
    sub_mode = (analysis.get("earnings_sub_mode") or "").lower()
    if sub_mode == "preview":
        html_text = build_preview_html(analysis)
    elif sub_mode == "review":
        html_text = build_review_html(analysis)
    else:
        raise ValueError(
            f"Mode E requires earnings_sub_mode preview|review, got {analysis.get('earnings_sub_mode')!r}"
        )

    if output_path is None:
        report_path = analysis.get("report_path")
        if isinstance(report_path, str) and report_path:
            target = resolve_path(report_path)
        else:
            target = _default_report_path(analysis)
    else:
        target = Path(output_path)
        if not target.is_absolute():
            target = resolve_path(target)

    _atomic_write(target, html_text)
    return str(target)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a Mode E earnings preview/review HTML file from analysis-result.json")
    parser.add_argument("--input", required=True, help="Path to analysis-result.json")
    parser.add_argument("--output", help="Optional output HTML path")
    args = parser.parse_args()

    input_path = resolve_path(args.input)
    analysis = load_json(input_path)
    written = render_earnings(analysis, output_path=args.output)
    print(json.dumps({
        "input_path": display_path(input_path),
        "output_path": display_path(Path(written)),
        "earnings_sub_mode": analysis.get("earnings_sub_mode"),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
