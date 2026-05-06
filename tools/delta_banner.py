"""Shared rendering helpers for the Auto Delta banner (Phase B).

This module is the single source of truth for converting a `delta_payload`
dict (produced by `.claude/skills/data-manager/scripts/delta-comparator.py`)
into HTML or Markdown surfaces consumed by the four output renderers
(Mode A briefing, Mode B comparison, Mode C dashboard, Mode D memo).

Schema of `delta_payload` (see roadmap §"Phase B"):

    {
        "prev_date": "2026-04-15",
        "curr_date": "2026-05-06",
        "rr_score":  {"prev": 1.42, "curr": 1.69, "delta": "+0.27", "delta_pct": "+19.0%"},
        "verdict":   {"prev": "관찰", "curr": "관찰", "changed": false},
        "base_target": {"prev": 385.0, "curr": 418.0, "delta_pct": "+8.6%", "currency": "USD"},
        "weighted_fair_value": {"prev": 320.0, "curr": 346.84, "delta_pct": "+8.4%", "currency": "USD"},
        "new_risks": ["AI Capex 회수 지연"],
        "removed_risks": [],
        "new_catalysts": [{"date": "2026-12-01", "event": "DC Circuit ..."}],
        "removed_catalysts": [],
    }

Renderers should call `render_html_banner(payload, korean=True)` or
`render_markdown_banner(payload, korean=True)`. When `payload` is None or
empty (no prior snapshot, `--no-delta` set, or sanitization failure), the
helpers return an empty string so the caller can simply concatenate without
branching.
"""

from __future__ import annotations

import html as _html
from typing import Any


def _esc(value: Any) -> str:
    return _html.escape("" if value is None else str(value))


def _currency_symbol(currency: str | None) -> str:
    if not currency:
        return ""
    mapping = {"USD": "$", "KRW": "₩", "EUR": "€", "JPY": "¥"}
    return mapping.get(currency.upper(), "")


def _fmt_value(value: Any, currency: str | None = None, digits: int = 2) -> str:
    if value is None:
        return "—"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        sym = _currency_symbol(currency)
        if currency and currency.upper() == "KRW":
            return f"{sym}{value:,.0f}"
        return f"{sym}{value:,.{digits}f}"
    return str(value)


def _delta_color_class(delta_str: str | None) -> str:
    if not delta_str:
        return "text-slate-500"
    cleaned = str(delta_str).replace("%", "").replace("+", "").strip()
    try:
        val = float(cleaned)
    except ValueError:
        return "text-slate-500"
    if val > 0:
        return "text-emerald-600"
    if val < 0:
        return "text-rose-600"
    return "text-slate-500"


def _is_meaningful(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    return bool(payload.get("prev_date") or payload.get("curr_date") or payload.get("rr_score"))


def render_html_banner(payload: dict | None, korean: bool = True) -> str:
    """Render a self-contained <section class="delta-banner"> block.

    Returns "" when payload is missing / empty. Designed to be prepended above
    the first content section of any HTML mode (A/B/C).
    """
    if not _is_meaningful(payload):
        return ""

    title = "지난 분석 대비 변화" if korean else "Changes vs Last Analysis"
    rr_label = "R/R Score"
    verdict_label = "투자의견" if korean else "Verdict"
    target_label = "Base Case 목표가" if korean else "Base Target"
    fv_label = "가중 적정가치" if korean else "Weighted Fair Value"
    new_risk_label = "신규 리스크" if korean else "New risks"
    removed_risk_label = "해제된 리스크" if korean else "Resolved risks"
    new_cat_label = "신규 카탈리스트" if korean else "New catalysts"
    removed_cat_label = "제거된 카탈리스트" if korean else "Removed catalysts"
    none_label = "없음" if korean else "None"

    rr = payload.get("rr_score") or {}
    verdict = payload.get("verdict") or {}
    base = payload.get("base_target") or {}
    fv = payload.get("weighted_fair_value") or {}
    currency = base.get("currency") or fv.get("currency")

    rr_delta = rr.get("delta")
    rr_delta_pct = rr.get("delta_pct")
    rr_color = _delta_color_class(rr_delta_pct or rr_delta)
    base_color = _delta_color_class(base.get("delta_pct"))
    fv_color = _delta_color_class(fv.get("delta_pct"))

    def _join(items: Any, key: str = "event") -> str:
        if not items:
            return _esc(none_label)
        rendered: list[str] = []
        for item in items:
            if isinstance(item, dict):
                date_part = item.get("date")
                text = item.get(key) or item.get("event") or item.get("title") or ""
                if date_part:
                    rendered.append(f"{_esc(text)} ({_esc(date_part)})")
                else:
                    rendered.append(_esc(text))
            else:
                rendered.append(_esc(item))
        return ", ".join(rendered)

    new_risks_html = _join(payload.get("new_risks") or [])
    removed_risks_html = _join(payload.get("removed_risks") or [])
    new_cats_html = _join(payload.get("new_catalysts") or [])
    removed_cats_html = _join(payload.get("removed_catalysts") or [])

    rr_value_html = (
        f"{_esc(rr.get('prev'))} → {_esc(rr.get('curr'))} "
        f"<span class=\"{rr_color}\">({_esc(rr_delta or rr_delta_pct or '—')})</span>"
    )
    verdict_value_html = (
        f"{_esc(verdict.get('prev') or '—')} → {_esc(verdict.get('curr') or '—')}"
    )
    base_value_html = (
        f"{_esc(_fmt_value(base.get('prev'), currency))} → "
        f"{_esc(_fmt_value(base.get('curr'), currency))} "
        f"<span class=\"{base_color}\">({_esc(base.get('delta_pct') or '—')})</span>"
    )
    fv_value_html = (
        f"{_esc(_fmt_value(fv.get('prev'), currency))} → "
        f"{_esc(_fmt_value(fv.get('curr'), currency))} "
        f"<span class=\"{fv_color}\">({_esc(fv.get('delta_pct') or '—')})</span>"
    )

    return (
        '<section class="delta-banner card p-5 border-l-4 border-amber-500 bg-amber-50/50 mb-6">\n'
        '  <div class="flex items-start gap-3">\n'
        '    <span class="text-amber-600 text-xl" aria-hidden="true">⟳</span>\n'
        '    <div class="flex-1">\n'
        f'      <h2 class="font-bold text-slate-900 mb-1">{_esc(title)} '
        f'({_esc(payload.get("prev_date") or "—")} → {_esc(payload.get("curr_date") or "—")})</h2>\n'
        '      <div class="grid grid-cols-2 md:grid-cols-4 gap-3 mt-3 text-sm">\n'
        f'        <div><p class="text-slate-500 text-[11px] uppercase tracking-wide">{_esc(rr_label)}</p>'
        f'<p class="font-semibold">{rr_value_html}</p></div>\n'
        f'        <div><p class="text-slate-500 text-[11px] uppercase tracking-wide">{_esc(verdict_label)}</p>'
        f'<p class="font-semibold">{verdict_value_html}</p></div>\n'
        f'        <div><p class="text-slate-500 text-[11px] uppercase tracking-wide">{_esc(target_label)}</p>'
        f'<p class="font-semibold">{base_value_html}</p></div>\n'
        f'        <div><p class="text-slate-500 text-[11px] uppercase tracking-wide">{_esc(fv_label)}</p>'
        f'<p class="font-semibold">{fv_value_html}</p></div>\n'
        '      </div>\n'
        '      <div class="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3 text-xs text-slate-700">\n'
        f'        <div><strong class="text-rose-600">{_esc(new_risk_label)}:</strong> {new_risks_html}</div>\n'
        f'        <div><strong class="text-emerald-600">{_esc(removed_risk_label)}:</strong> {removed_risks_html}</div>\n'
        f'        <div><strong class="text-amber-700">{_esc(new_cat_label)}:</strong> {new_cats_html}</div>\n'
        f'        <div><strong class="text-slate-600">{_esc(removed_cat_label)}:</strong> {removed_cats_html}</div>\n'
        '      </div>\n'
        '    </div>\n'
        '  </div>\n'
        '</section>'
    )


def render_markdown_banner(payload: dict | None, korean: bool = True) -> str:
    """Render a quote-block banner suitable for Mode D / chat surfaces.

    Returns "" when payload is missing / empty.
    """
    if not _is_meaningful(payload):
        return ""

    title = "지난 분석 대비 변화" if korean else "Changes vs Last Analysis"
    rr = payload.get("rr_score") or {}
    verdict = payload.get("verdict") or {}
    base = payload.get("base_target") or {}
    fv = payload.get("weighted_fair_value") or {}
    currency = base.get("currency") or fv.get("currency")

    new_risk_label = "신규 리스크" if korean else "New risks"
    removed_risk_label = "해제된 리스크" if korean else "Resolved risks"
    new_cat_label = "신규 카탈리스트" if korean else "New catalysts"
    none_label = "없음" if korean else "None"

    def _items(items: Any) -> str:
        if not items:
            return none_label
        rendered: list[str] = []
        for item in items:
            if isinstance(item, dict):
                text = item.get("event") or item.get("title") or ""
                d = item.get("date")
                rendered.append(f"{text} ({d})" if d else str(text))
            else:
                rendered.append(str(item))
        return ", ".join(rendered)

    rr_pct = rr.get("delta_pct") or rr.get("delta") or "—"
    base_pct = base.get("delta_pct") or "—"
    fv_pct = fv.get("delta_pct") or "—"

    lines = [
        f"> **{title}** ({payload.get('prev_date') or '—'} → {payload.get('curr_date') or '—'})",
        f"> - R/R Score: {rr.get('prev')} → {rr.get('curr')} ({rr_pct})",
        f"> - Verdict: {verdict.get('prev') or '—'} → {verdict.get('curr') or '—'}",
        f"> - Base Target: {_fmt_value(base.get('prev'), currency)} → {_fmt_value(base.get('curr'), currency)} ({base_pct})",
        f"> - Weighted Fair Value: {_fmt_value(fv.get('prev'), currency)} → {_fmt_value(fv.get('curr'), currency)} ({fv_pct})",
        f"> - {new_risk_label}: {_items(payload.get('new_risks') or [])}",
        f"> - {removed_risk_label}: {_items(payload.get('removed_risks') or [])}",
        f"> - {new_cat_label}: {_items(payload.get('new_catalysts') or [])}",
    ]
    return "\n".join(lines)


def render_docx_lines(payload: dict | None, korean: bool = True) -> list[tuple[str, str]]:
    """Return [(label, value), ...] tuples for python-docx Mode D rendering.

    Empty list when payload is missing.
    """
    if not _is_meaningful(payload):
        return []

    rr = payload.get("rr_score") or {}
    verdict = payload.get("verdict") or {}
    base = payload.get("base_target") or {}
    fv = payload.get("weighted_fair_value") or {}
    currency = base.get("currency") or fv.get("currency")

    new_risk_label = "신규 리스크" if korean else "New risks"
    removed_risk_label = "해제된 리스크" if korean else "Resolved risks"
    new_cat_label = "신규 카탈리스트" if korean else "New catalysts"
    none_label = "없음" if korean else "None"

    def _items(items: Any) -> str:
        if not items:
            return none_label
        rendered: list[str] = []
        for item in items:
            if isinstance(item, dict):
                text = item.get("event") or item.get("title") or ""
                d = item.get("date")
                rendered.append(f"{text} ({d})" if d else str(text))
            else:
                rendered.append(str(item))
        return ", ".join(rendered)

    rr_pct = rr.get("delta_pct") or rr.get("delta") or "—"
    base_pct = base.get("delta_pct") or "—"
    fv_pct = fv.get("delta_pct") or "—"

    return [
        ("Period", f"{payload.get('prev_date') or '—'} → {payload.get('curr_date') or '—'}"),
        ("R/R Score", f"{rr.get('prev')} → {rr.get('curr')} ({rr_pct})"),
        ("Verdict", f"{verdict.get('prev') or '—'} → {verdict.get('curr') or '—'}"),
        ("Base Target", f"{_fmt_value(base.get('prev'), currency)} → {_fmt_value(base.get('curr'), currency)} ({base_pct})"),
        ("Weighted Fair Value", f"{_fmt_value(fv.get('prev'), currency)} → {_fmt_value(fv.get('curr'), currency)} ({fv_pct})"),
        (new_risk_label, _items(payload.get("new_risks") or [])),
        (removed_risk_label, _items(payload.get("removed_risks") or [])),
        (new_cat_label, _items(payload.get("new_catalysts") or [])),
    ]


def extract_payload(analysis: dict | None) -> dict | None:
    """Pull the delta_payload out of an analysis-result.json dict.

    Recognized locations (in priority order):
      - analysis["delta_payload"]
      - analysis["auto_delta_payload"]   (set by orchestrator pipeline state)
      - analysis["sections"]["delta_payload"]
    """
    if not isinstance(analysis, dict):
        return None
    for key in ("delta_payload", "auto_delta_payload"):
        candidate = analysis.get(key)
        if isinstance(candidate, dict) and _is_meaningful(candidate):
            return candidate
    sections = analysis.get("sections")
    if isinstance(sections, dict):
        candidate = sections.get("delta_payload")
        if isinstance(candidate, dict) and _is_meaningful(candidate):
            return candidate
    return None
