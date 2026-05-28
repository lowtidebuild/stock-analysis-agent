"""Mode B comparison artifacts, renderer, and delivery gate."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from typing import Any

from scripts.parity.data_sources import load_json, write_json
from scripts.parity.rendering import (
    as_number,
    currency_symbol,
    esc,
    fmt,
    grade_badge,
    metric_display,
    pct,
    rendered_metrics,
    source_tag,
    visible_text,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
MISSING_DISPLAY = "—"

COMPARISON_METRICS = [
    {"key": "price_at_analysis", "label": "Price", "direction": "context"},
    {"key": "market_cap", "label": "Market Cap", "direction": "context"},
    {"key": "revenue_growth_yoy", "label": "Revenue Growth", "direction": "higher"},
    {"key": "operating_margin", "label": "Operating Margin", "direction": "higher"},
    {"key": "fcf_yield", "label": "FCF Yield", "direction": "higher"},
    {"key": "pe_ratio", "label": "P/E", "direction": "lower"},
    {"key": "ev_ebitda", "label": "EV/EBITDA", "direction": "lower"},
    {"key": "net_debt_ebitda", "label": "Net Debt / EBITDA", "direction": "lower"},
    {"key": "rr_score", "label": "R/R Score", "direction": "higher"},
    {"key": "base_return_pct", "label": "Base Return", "direction": "higher"},
]


@dataclass(frozen=True)
class ComparisonResult:
    artifact_root: Path
    comparison_input_path: Path
    analysis_result_path: Path
    html_path: Path
    render_report_path: Path
    quality_report_path: Path
    status: str
    delivery_ready: bool
    metrics: dict[str, Any]
    best_pick: str | None


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_mode_b_comparison_handoff(
    *,
    language: str,
    market: str,
    run_id: str,
    tickers: list[str],
) -> ComparisonResult:
    if not 2 <= len(tickers) <= 5:
        raise ValueError("Mode B comparison requires 2-5 tickers")

    comparison_dir = REPO_ROOT / "output" / "runs" / run_id / "comparison"
    comparison_dir.mkdir(parents=True, exist_ok=True)
    loaded = [load_ticker_bundle(run_id=run_id, ticker=ticker) for ticker in tickers]
    comparison_input = build_comparison_input(
        language=language,
        loaded=loaded,
        market=market,
        run_id=run_id,
        tickers=tickers,
    )
    comparison_input_path = comparison_dir / "comparison-input.json"
    write_json(comparison_input_path, comparison_input)

    analysis_result = build_comparison_analysis(comparison_input)
    analysis_result_path = comparison_dir / "comparison-analysis-result.json"
    write_json(analysis_result_path, analysis_result)

    html_text = build_mode_b_comparison_html(analysis_result)
    html_path = comparison_dir / "mode-b-comparison.html"
    html_path.write_text(html_text, encoding="utf-8")

    render_validation = validate_mode_b_comparison_html(
        html_text,
        analysis_result=analysis_result,
        html_path=html_path,
    )
    render_report = {
        "schema_version": "abc-parity-mode-b-render-report-v1",
        "mode": "B",
        "language": language,
        "market": market,
        "tickers": tickers,
        "status": render_validation["status"],
        "html_path": display_path(html_path),
        "comparison_analysis_result_path": display_path(analysis_result_path),
        "validation": render_validation,
        "created_at": utc_now(),
    }
    render_report_path = comparison_dir / "mode-b-render-report.json"
    write_json(render_report_path, render_report)

    quality_report = build_comparison_quality_report(
        analysis_result=analysis_result,
        render_report=render_report,
    )
    quality_report_path = comparison_dir / "comparison-quality-report.json"
    write_json(quality_report_path, quality_report)
    if quality_report["overall_result"] != "PASS":
        errors = quality_report["delivery_gate"].get("blocking_items") or []
        raise ValueError("Mode B comparison failed delivery gate: " + "; ".join(errors[:8]))

    return ComparisonResult(
        artifact_root=comparison_dir,
        comparison_input_path=comparison_input_path,
        analysis_result_path=analysis_result_path,
        html_path=html_path,
        render_report_path=render_report_path,
        quality_report_path=quality_report_path,
        status=quality_report["overall_result"],
        delivery_ready=quality_report["delivery_gate"]["ready_for_delivery"],
        metrics=render_validation["metrics"],
        best_pick=(analysis_result.get("best_pick") or {}).get("ticker"),
    )


def load_ticker_bundle(*, run_id: str, ticker: str) -> dict[str, Any]:
    ticker_dir = REPO_ROOT / "output" / "runs" / run_id / ticker
    return {
        "ticker": ticker,
        "artifact_root": display_path(ticker_dir),
        "validated": load_json(ticker_dir / "validated-data.json"),
        "calculations": load_json(ticker_dir / "deterministic-calculations.json"),
        "analysis": load_json(ticker_dir / "analysis-result.json"),
        "evidence": load_json(ticker_dir / "evidence-pack.json"),
    }


def build_comparison_input(
    *,
    language: str,
    loaded: list[dict[str, Any]],
    market: str,
    run_id: str,
    tickers: list[str],
) -> dict[str, Any]:
    return {
        "schema_version": "abc-parity-mode-b-comparison-input-v1",
        "mode": "B",
        "language": language,
        "market": market,
        "run_context": {
            "run_id": run_id,
            "artifact_root": display_path(REPO_ROOT / "output" / "runs" / run_id / "comparison"),
            "tickers": tickers,
        },
        "metric_columns": COMPARISON_METRICS,
        "ticker_artifacts": [
            {
                "ticker": item["ticker"],
                "artifact_root": item["artifact_root"],
                "validated_data_path": f"{item['artifact_root']}/validated-data.json",
                "analysis_result_path": f"{item['artifact_root']}/analysis-result.json",
                "deterministic_calculations_path": f"{item['artifact_root']}/deterministic-calculations.json",
                "company_name": item["validated"].get("company_name") or item["ticker"],
                "source_profile": item["validated"].get("source_profile"),
                "overall_grade": item["validated"].get("overall_grade"),
            }
            for item in loaded
        ],
        "loaded": loaded,
        "created_at": utc_now(),
    }


def build_comparison_analysis(comparison_input: dict[str, Any]) -> dict[str, Any]:
    loaded = comparison_input["loaded"]
    metric_columns = comparison_input["metric_columns"]
    rows = [build_metric_matrix_row(item, metric_columns) for item in loaded]
    peer_medians = build_peer_medians(rows, metric_columns)
    relative_valuation = build_relative_valuation(rows, peer_medians)
    ranking = build_ranking(rows, relative_valuation)
    best_pick = ranking[0] if ranking else None
    avoid_or_hold = ranking[-1] if ranking else None
    missing = build_missing_data_disclosure(rows, metric_columns)
    macro_lens = build_macro_lens(loaded)
    catalysts_risks = build_catalyst_risk_comparison(loaded)
    variants = build_variant_views(loaded)
    language = str(comparison_input.get("language") or "en")
    best_pick_reasoning = build_best_pick_reasoning(
        best_pick=best_pick,
        avoid_or_hold=avoid_or_hold,
        language=language,
        missing=missing,
        relative_valuation=relative_valuation,
        rows=rows,
    )

    ticker_list = [row["ticker"] for row in rows]
    thesis = comparison_thesis(best_pick, avoid_or_hold, rows, language=language)
    return {
        "schema_version": "abc-parity-mode-b-comparison-analysis-v1",
        "artifact_type": "comparison-analysis-result",
        "mode": "B",
        "language": comparison_input["language"],
        "market": comparison_input["market"],
        "compared_tickers": ticker_list,
        "comparison_thesis": thesis,
        "metric_columns": metric_columns,
        "metric_matrix": rows,
        "peer_medians": peer_medians,
        "relative_valuation": relative_valuation,
        "ranking": ranking,
        "best_pick": best_pick,
        "best_pick_reasoning": best_pick_reasoning,
        "avoid_or_hold": avoid_or_hold,
        "per_ticker_variant_views": variants,
        "macro_lens": macro_lens,
        "catalyst_risk_comparison": catalysts_risks,
        "missing_data_disclosure": missing,
        "disclaimer": "This comparison is for informational purposes only and does not constitute investment advice.",
        "created_at": utc_now(),
    }


def build_metric_matrix_row(item: dict[str, Any], metric_columns: list[dict[str, Any]]) -> dict[str, Any]:
    validated = item["validated"]
    analysis = item["analysis"]
    metrics = analysis.get("key_metrics") if isinstance(analysis.get("key_metrics"), dict) else {}
    scenarios = analysis.get("scenarios") if isinstance(analysis.get("scenarios"), dict) else {}
    currency = analysis.get("currency") or validated.get("currency") or "USD"
    values = {}
    for column in metric_columns:
        key = column["key"]
        if key == "rr_score":
            values[key] = comparison_value(
                analysis.get("rr_score"),
                display=fmt(analysis.get("rr_score"), 2),
                grade="C",
                source_tag="[Calc]",
                reason="deterministic_scenario_rr",
            )
        elif key == "base_return_pct":
            base = scenarios.get("base") if isinstance(scenarios.get("base"), dict) else {}
            values[key] = comparison_value(
                base.get("return_pct"),
                display=pct(base.get("return_pct")),
                grade="C",
                source_tag="[Calc]",
                reason="deterministic_base_case_return",
            )
        else:
            entry = metrics.get(key)
            missing = not isinstance(entry, dict) or entry.get("value") in (None, "")
            values[key] = {
                "value": as_number(entry.get("value")) if isinstance(entry, dict) else None,
                "display": MISSING_DISPLAY if missing else metric_display(entry, key, currency),
                "source_tag": (entry.get("display_tag") or entry.get("tag") or "[User]") if isinstance(entry, dict) else "[User]",
                "grade": entry.get("grade") if isinstance(entry, dict) else "D",
                "missing": missing,
                "reason": missing_reason(entry),
            }
    return {
        "ticker": item["ticker"],
        "company_name": validated.get("company_name") or item["ticker"],
        "currency": currency,
        "source_profile": validated.get("source_profile"),
        "overall_grade": validated.get("overall_grade"),
        "values": values,
    }


def comparison_value(
    value: Any,
    *,
    display: str,
    grade: str,
    source_tag: str,
    reason: str,
) -> dict[str, Any]:
    number = as_number(value)
    missing = number is None
    return {
        "value": number,
        "display": MISSING_DISPLAY if missing else display,
        "source_tag": source_tag,
        "grade": grade if not missing else "D",
        "missing": missing,
        "reason": reason if not missing else "metric_unavailable",
    }


def missing_reason(entry: Any) -> str:
    if isinstance(entry, dict):
        return str(entry.get("exclusion_reason") or "metric_unavailable")
    return "metric_unavailable"


def build_peer_medians(rows: list[dict[str, Any]], metric_columns: list[dict[str, Any]]) -> dict[str, Any]:
    medians = {}
    for column in metric_columns:
        key = column["key"]
        values = [
            row["values"][key]["value"]
            for row in rows
            if row["values"].get(key) and row["values"][key]["value"] is not None
        ]
        medians[key] = round(float(median(values)), 4) if values else None
    return medians


def build_relative_valuation(rows: list[dict[str, Any]], peer_medians: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    for row in rows:
        values = row["values"]
        pe_premium = premium_discount(values["pe_ratio"]["value"], peer_medians.get("pe_ratio"))
        ev_premium = premium_discount(values["ev_ebitda"]["value"], peer_medians.get("ev_ebitda"))
        fcf_spread = premium_discount(values["fcf_yield"]["value"], peer_medians.get("fcf_yield"))
        result.append(
            {
                "ticker": row["ticker"],
                "pe_premium_discount_pct": pe_premium,
                "ev_ebitda_premium_discount_pct": ev_premium,
                "fcf_yield_spread_pct": fcf_spread,
                "note": relative_note(row["ticker"], pe_premium, ev_premium, fcf_spread),
            }
        )
    return result


def premium_discount(value: float | None, median_value: float | None) -> float | None:
    if value is None or median_value in (None, 0):
        return None
    return round((value - median_value) / median_value * 100, 2)


def relative_note(ticker: str, pe_premium: float | None, ev_premium: float | None, fcf_spread: float | None) -> str:
    if pe_premium is None and ev_premium is None:
        return f"{ticker} lacks enough valuation metrics for peer median comparison."
    parts = []
    if pe_premium is not None:
        parts.append(f"P/E {pe_premium:+.1f}% vs peer median")
    if ev_premium is not None:
        parts.append(f"EV/EBITDA {ev_premium:+.1f}% vs peer median")
    if fcf_spread is not None:
        parts.append(f"FCF yield {fcf_spread:+.1f}% vs peer median")
    return "; ".join(parts)


def build_ranking(rows: list[dict[str, Any]], relative_valuation: list[dict[str, Any]]) -> list[dict[str, Any]]:
    relative_by_ticker = {item["ticker"]: item for item in relative_valuation}
    ranking = []
    for row in rows:
        values = row["values"]
        relative = relative_by_ticker.get(row["ticker"], {})
        rr = values["rr_score"]["value"] or 0
        base_return = values["base_return_pct"]["value"] or 0
        growth = values["revenue_growth_yoy"]["value"] or 0
        margin = values["operating_margin"]["value"] or 0
        fcf_yield = values["fcf_yield"]["value"] or 0
        pe_premium = relative.get("pe_premium_discount_pct")
        ev_premium = relative.get("ev_ebitda_premium_discount_pct")
        valuation_penalty = sum(max(item or 0, 0) for item in (pe_premium, ev_premium)) * 0.08
        valuation_bonus = sum(abs(min(item or 0, 0)) for item in (pe_premium, ev_premium)) * 0.03
        score = rr * 20 + base_return * 0.35 + growth * 0.4 + margin * 0.2 + fcf_yield * 0.9 + valuation_bonus - valuation_penalty
        ranking.append(
            {
                "ticker": row["ticker"],
                "score": round(score, 2),
                "numeric_basis": {
                    "rr_score": rr,
                    "base_return_pct": base_return,
                    "revenue_growth_yoy": growth,
                    "operating_margin": margin,
                    "fcf_yield": fcf_yield,
                    "pe_premium_discount_pct": pe_premium,
                    "ev_ebitda_premium_discount_pct": ev_premium,
                },
                "rationale": (
                    f"{row['ticker']} score uses R/R {rr:.2f}, base return {base_return:.1f}%, "
                    f"growth {growth:.1f}%, operating margin {margin:.1f}%, FCF yield {fcf_yield:.1f}%, "
                    f"and peer median valuation premium/discount."
                ),
            }
        )
    ranking.sort(key=lambda item: item["score"], reverse=True)
    for index, item in enumerate(ranking, start=1):
        item["rank"] = index
    return ranking


def build_missing_data_disclosure(rows: list[dict[str, Any]], metric_columns: list[dict[str, Any]]) -> list[dict[str, str]]:
    missing = []
    labels = {column["key"]: column["label"] for column in metric_columns}
    for row in rows:
        for key, value in row["values"].items():
            if value.get("missing"):
                missing.append(
                    {
                        "ticker": row["ticker"],
                        "metric": key,
                        "label": labels.get(key, key),
                        "display": MISSING_DISPLAY,
                        "reason": value.get("reason") or "metric_unavailable",
                    }
                )
    return missing


def build_best_pick_reasoning(
    *,
    best_pick: dict[str, Any] | None,
    avoid_or_hold: dict[str, Any] | None,
    language: str,
    missing: list[dict[str, str]],
    relative_valuation: list[dict[str, Any]],
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    is_ko = language == "ko"
    if not best_pick:
        return {
            "ticker": None,
            "decision": "최선호 선택 없음" if is_ko else "No best pick",
            "why_it_wins": (
                "공통 비교 지표가 부족해 이 비교 세트에서는 최선호 종목을 강제로 정하지 않는다."
                if is_ko
                else "The comparison set cannot produce a best pick because ranking evidence is unavailable."
            ),
            "numeric_drivers": [],
            "tradeoff": "공통 metric 없이 상대 결론을 만들지 않는다." if is_ko else "Do not force a relative call without common metrics.",
            "missing_data_boundary": (
                "결측 필드는 반드시 —와 사유로 남긴다."
                if is_ko
                else "Missing fields must remain disclosed as — with a reason."
            ),
            "source_tag": "[Calc]",
        }

    ticker = str(best_pick.get("ticker") or "")
    row = next((item for item in rows if item.get("ticker") == ticker), {})
    relative = next((item for item in relative_valuation if item.get("ticker") == ticker), {})
    values = row.get("values") if isinstance(row.get("values"), dict) else {}
    basis = best_pick.get("numeric_basis") if isinstance(best_pick.get("numeric_basis"), dict) else {}
    drivers = best_pick_numeric_drivers(values, basis, relative, language=language)
    avoid_text = (
        (
            f"{avoid_or_hold.get('ticker')}이 최하위라서 이 선택의 기회비용을 보여준다."
            if is_ko
            else f"{avoid_or_hold.get('ticker')} ranks last, which frames the opportunity cost."
        )
        if isinstance(avoid_or_hold, dict) and avoid_or_hold.get("ticker") and avoid_or_hold.get("ticker") != ticker
        else ("별도의 회피/보유 후보는 없다." if is_ko else "No separate avoid/hold ticker is available.")
    )
    missing_count = len(missing)
    missing_boundary = (
        (
            f"결측 비교 필드 {missing_count}개는 {MISSING_DISPLAY}와 사유로 표시되며, 최선호 판단은 없는 데이터를 보간하지 않는다."
            if is_ko
            else f"{missing_count} missing comparison field(s) are displayed as {MISSING_DISPLAY} with reasons, so the best-pick call does not interpolate unavailable evidence."
        )
        if missing_count
        else ("공통 metric matrix에 결측 비교 필드는 없다." if is_ko else "No missing comparison fields are present in the common metric matrix.")
    )
    return {
        "ticker": ticker,
        "decision": f"{ticker}는 이 Mode B 세트의 상대 최선호 종목이다." if is_ko else f"{ticker} is the relative best pick in this Mode B set.",
        "why_it_wins": (
            f"{ticker}는 동일한 column set에서 R/R, base return, 영업 품질, 현금흐름 수익률, peer median valuation 증거를 함께 반영한 deterministic score가 가장 높다."
            if is_ko
            else f"{ticker} ranks #1 because its deterministic score combines R/R, base return, operating quality, cash-flow yield, "
            "and peer-median valuation evidence on the same column set."
        ),
        "numeric_drivers": drivers,
        "tradeoff": (
            f"{avoid_text} 이 결론은 상대 비교이지 단독 매수 추천이 아니다."
            if is_ko
            else f"{avoid_text} The decision remains relative, not a stand-alone buy recommendation."
        ),
        "missing_data_boundary": missing_boundary,
        "source_tag": "[Calc]",
    }


def best_pick_numeric_drivers(
    values: dict[str, Any],
    basis: dict[str, Any],
    relative: dict[str, Any],
    *,
    language: str,
) -> list[dict[str, Any]]:
    is_ko = language == "ko"
    driver_specs = [
        ("rr_score", "R/R Score", fmt(basis.get("rr_score"), 2)),
        ("base_return_pct", "Base Return", pct(basis.get("base_return_pct"))),
        ("revenue_growth_yoy", "Revenue Growth", pct(basis.get("revenue_growth_yoy"))),
        ("operating_margin", "Operating Margin", pct(basis.get("operating_margin"))),
        ("fcf_yield", "FCF Yield", pct(basis.get("fcf_yield"))),
    ]
    drivers = []
    for key, label, display in driver_specs:
        value = values.get(key) if isinstance(values.get(key), dict) else {}
        if value.get("missing"):
            continue
        drivers.append(
            {
                "metric": key,
                "label": label,
                "display": display,
                "interpretation": (
                    f"{label} 지표는 deterministic ranking score에 직접 반영된다."
                    if is_ko
                    else f"{label} contributes to the deterministic ranking score."
                ),
            }
        )
    valuation_note = relative.get("note")
    if valuation_note:
        drivers.append(
            {
                "metric": "relative_valuation",
                "label": "Relative Valuation",
                "display": str(valuation_note),
                "interpretation": (
                    "Peer median premium/discount를 valuation check로 반영한다."
                    if is_ko
                    else "Peer-median premium/discount is included as a valuation check."
                ),
            }
        )
    return drivers[:6]


def build_macro_lens(loaded: list[dict[str, Any]]) -> dict[str, Any]:
    series = []
    for item in loaded:
        macro = item["validated"].get("macro_context") if isinstance(item["validated"].get("macro_context"), dict) else {}
        structured = macro.get("structured") if isinstance(macro.get("structured"), dict) else {}
        if structured.get("status") == "available":
            series.extend(entry for entry in structured.get("series", []) if isinstance(entry, dict))
    if not series:
        return {
            "status": "unavailable",
            "summary": "Macro data unavailable; no FRED rates, inflation, GDP, or unemployment values are inferred.",
            "series": [],
        }
    return {
        "status": "available",
        "summary": f"Macro light lens uses {len(series)} source-tagged FRED series and applies them equally across the comparison set.",
        "series": series[:8],
    }


def build_catalyst_risk_comparison(loaded: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for item in loaded:
        analysis = item["analysis"]
        sections = analysis.get("sections") if isinstance(analysis.get("sections"), dict) else {}
        catalysts = analysis.get("upcoming_catalysts") if isinstance(analysis.get("upcoming_catalysts"), list) else []
        risks = sections.get("precision_risks") if isinstance(sections.get("precision_risks"), list) else analysis.get("top_risks")
        if not isinstance(risks, list):
            risks = []
        rows.append(
            {
                "ticker": item["ticker"],
                "catalysts": catalysts[:2],
                "risks": risks[:2],
            }
        )
    return rows


def build_variant_views(loaded: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows = []
    for item in loaded:
        analysis = item["analysis"]
        sections = analysis.get("sections") if isinstance(analysis.get("sections"), dict) else {}
        view = sections.get("relative_view") or sections.get("variant_view_q1") or analysis.get("thesis")
        rows.append({"ticker": item["ticker"], "view": str(view or "Variant view unavailable.")})
    return rows


def comparison_thesis(
    best_pick: dict[str, Any] | None,
    avoid_or_hold: dict[str, Any] | None,
    rows: list[dict[str, Any]],
    *,
    language: str,
) -> str:
    tickers = "/".join(row["ticker"] for row in rows)
    is_ko = language == "ko"
    if not best_pick:
        return (
            f"{tickers} 비교는 필수 numeric evidence가 부족해 순위를 확정할 수 없다."
            if is_ko
            else f"{tickers} comparison cannot rank the set because required numeric evidence is unavailable."
        )
    avoid_text = (
        f", 반면 {avoid_or_hold['ticker']}은 risk/reward가 가장 약하다"
        if is_ko and avoid_or_hold
        else f" while {avoid_or_hold['ticker']} is the weakest risk/reward setup"
        if avoid_or_hold
        else ""
    )
    if is_ko:
        return (
            f"{tickers} 중 {best_pick['ticker']}가 deterministic R/R, base return, cash-flow yield, "
            f"영업 품질, peer median valuation check에서 상대 1위로 나온다{avoid_text.replace(',', ';')}. "
            "이 결론은 절대 매수 의견이 아니라 비교 세트 내부의 상대 판단이며, 각 종목은 별도 catalyst와 risk mechanism 점검이 필요하다."
        )
    return (
        f"Within {tickers}, {best_pick['ticker']} ranks first on deterministic R/R, base return, cash-flow yield, "
        f"operating quality, and peer median valuation checks{avoid_text}. The call is relative, not absolute; "
        "each ticker still needs its own catalyst and risk mechanism follow-up."
    )


def build_mode_b_comparison_html(analysis: dict[str, Any]) -> str:
    tickers = analysis["compared_tickers"]
    best = analysis.get("best_pick") or {}
    avoid = analysis.get("avoid_or_hold") or {}
    return f"""<!DOCTYPE html>
<html lang="{esc(analysis.get("language"))}">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Mode B Comparison - {esc('/'.join(tickers))}</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: #f6f7fa; color: #172033; font-family: Inter, -apple-system, BlinkMacSystemFont, "Noto Sans KR", sans-serif; }}
    main {{ max-width: 1120px; margin: 0 auto; padding: 28px 22px 44px; }}
    header {{ background: #111827; color: #fff; border-radius: 8px; padding: 26px 28px; }}
    section {{ background: #fff; border: 1px solid #e4e7ee; border-radius: 8px; margin-top: 16px; padding: 22px 24px; }}
    h1 {{ margin: 0; font-size: 30px; line-height: 1.15; letter-spacing: 0; }}
    h2 {{ margin: 0 0 12px; font-size: 17px; line-height: 1.3; }}
    p {{ margin: 0 0 11px; line-height: 1.65; font-size: 14px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ border-bottom: 1px solid #e7eaf0; padding: 10px 8px; text-align: left; vertical-align: top; }}
    th {{ color: #5c667a; font-size: 11px; text-transform: uppercase; }}
    .hero-grid {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin-top: 18px; }}
    .hero-stat {{ background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.14); border-radius: 7px; padding: 12px; }}
    .label {{ color: #6b7486; font-size: 11px; text-transform: uppercase; margin-bottom: 4px; }}
    .hero-stat .label {{ color: #b7c2d4; }}
    .value {{ font-weight: 750; font-size: 22px; line-height: 1.2; }}
    .source-tag {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11px; padding: 1px 5px; border-radius: 4px; background: #f0f2f5; color: #334155; }}
    .grade-badge {{ font-size: 11px; font-weight: 750; padding: 1px 6px; border-radius: 4px; background: #e8f0ff; color: #1e3a8a; }}
    .pill {{ display: inline-block; border-radius: 999px; padding: 4px 9px; margin-right: 6px; background: #eef3ff; color: #244c93; font-size: 12px; font-weight: 700; }}
    .muted {{ color: #5c667a; }}
    .note {{ border-left: 3px solid #335c99; padding: 9px 0 9px 12px; margin-top: 10px; }}
    .missing {{ color: #8a3d00; font-weight: 700; }}
    @media (max-width: 820px) {{ .hero-grid {{ grid-template-columns: 1fr; }} main {{ padding: 14px; }} header, section {{ padding: 18px; }} table {{ font-size: 12px; }} }}
  </style>
</head>
<body>
<main>
  <header>
    <div class="label">Mode B Peer Comparison</div>
    <h1>{esc('/'.join(tickers))}</h1>
    <p class="muted">Ticker set: {esc(', '.join(tickers))} · Market: {esc(analysis.get("market"))} · Generated: {esc(analysis.get("created_at"))}</p>
    <div class="hero-grid">
      <div class="hero-stat"><div class="label">Best Pick</div><div class="value">{esc(best.get("ticker"))}</div><p>Score {fmt(best.get("score"), 2)} {source_tag("[Calc]")}</p></div>
      <div class="hero-stat"><div class="label">Avoid / Hold</div><div class="value">{esc(avoid.get("ticker"))}</div><p>Score {fmt(avoid.get("score"), 2)} {source_tag("[Calc]")}</p></div>
      <div class="hero-stat"><div class="label">Compared Tickers</div><div class="value">{len(tickers)}</div><p>2-5 ticker contract {source_tag("[Calc]")}</p></div>
    </div>
  </header>
  <section id="comparison-thesis">
    <h2>Ticker Set and Comparison Thesis</h2>
    <p>{esc(analysis.get("comparison_thesis"))} {source_tag("[Calc]")}</p>
  </section>
  <section id="best-pick-rationale">
    <h2>Best-Pick Decision Rationale</h2>
    {render_best_pick_reasoning(analysis)}
  </section>
  <section id="metric-matrix">
    <h2>Common Metric Matrix</h2>
    {render_metric_matrix(analysis)}
  </section>
  <section id="ranking">
    <h2>R/R Score Ranking and Best Pick</h2>
    {render_ranking(analysis)}
  </section>
  <section id="relative-valuation">
    <h2>Relative Valuation: Peer Median Premium/Discount</h2>
    {render_relative_valuation(analysis)}
  </section>
  <section id="growth-profitability-balance">
    <h2>Growth / Profitability / Balance Sheet Comparison</h2>
    <p>The matrix keeps identical columns for every ticker. Revenue growth, operating margin, FCF yield, valuation multiples, leverage, R/R score, and base return are shown side by side. Missing values stay as <span class="missing">{MISSING_DISPLAY}</span> with a reason rather than being interpolated. {source_tag("[Calc]")}</p>
  </section>
  <section id="variant-view">
    <h2>Per-Ticker Mini Variant View</h2>
    {render_variant_views(analysis)}
  </section>
  <section id="macro-lens">
    <h2>Macro Lens</h2>
    {render_macro_lens(analysis)}
  </section>
  <section id="catalyst-risk">
    <h2>Catalyst / Risk Comparison</h2>
    {render_catalyst_risk(analysis)}
  </section>
  <section id="missing-data">
    <h2>Missing-Data Disclosure</h2>
    {render_missing_data(analysis)}
  </section>
  <section id="disclaimer">
    <h2>Disclaimer</h2>
    <p>{esc(analysis.get("disclaimer"))}</p>
  </section>
</main>
</body>
</html>
"""


def render_metric_matrix(analysis: dict[str, Any]) -> str:
    columns = analysis["metric_columns"]
    header = "".join(f"<th>{esc(column['label'])}</th>" for column in columns)
    rows = []
    for row in analysis["metric_matrix"]:
        cells = []
        for column in columns:
            value = row["values"][column["key"]]
            cells.append(
                f"""<td>{esc(value.get("display"))} {source_tag(value.get("source_tag"))} {grade_badge({"grade": value.get("grade")})}</td>"""
            )
        rows.append(f"<tr><td><strong>{esc(row['ticker'])}</strong><br><span class=\"muted\">{esc(row['company_name'])}</span></td>{''.join(cells)}</tr>")
    return f"<table><thead><tr><th>Ticker</th>{header}</tr></thead><tbody>{''.join(rows)}</tbody></table>"


def render_best_pick_reasoning(analysis: dict[str, Any]) -> str:
    reasoning = analysis.get("best_pick_reasoning") if isinstance(analysis.get("best_pick_reasoning"), dict) else {}
    drivers = reasoning.get("numeric_drivers") if isinstance(reasoning.get("numeric_drivers"), list) else []
    driver_rows = "".join(
        f"""<tr><td>{esc(driver.get('label'))}</td><td>{esc(driver.get('display'))}</td><td>{esc(driver.get('interpretation'))} {source_tag("[Calc]")}</td></tr>"""
        for driver in drivers
        if isinstance(driver, dict)
    )
    if not driver_rows:
        driver_rows = f"""<tr><td colspan="3">Numeric best-pick drivers unavailable. {source_tag("[User]")}</td></tr>"""
    return f"""
    <p><span class="pill">{esc(reasoning.get("ticker") or "No pick")}</span>{esc(reasoning.get("why_it_wins") or "Best-pick reasoning unavailable.")} {source_tag(reasoning.get("source_tag") or "[Calc]")}</p>
    <table><thead><tr><th>Driver</th><th>Value</th><th>Interpretation</th></tr></thead><tbody>{driver_rows}</tbody></table>
    <div class="note"><p><strong>Tradeoff:</strong> {esc(reasoning.get("tradeoff") or "Tradeoff unavailable.")} {source_tag("[Calc]")}</p>
    <p><strong>Missing-data boundary:</strong> {esc(reasoning.get("missing_data_boundary") or "Missing data disclosure unavailable.")} {source_tag("[Calc]")}</p></div>
    """


def render_ranking(analysis: dict[str, Any]) -> str:
    rows = []
    for item in analysis["ranking"]:
        basis = item["numeric_basis"]
        rows.append(
            f"""<tr><td>{item['rank']}</td><td><strong>{esc(item['ticker'])}</strong></td><td>{fmt(item['score'], 2)}</td>
            <td>R/R {fmt(basis.get('rr_score'), 2)}, base return {pct(basis.get('base_return_pct'))}, growth {pct(basis.get('revenue_growth_yoy'))}, FCF yield {pct(basis.get('fcf_yield'))} {source_tag("[Calc]")}</td>
            <td>{esc(item['rationale'])}</td></tr>"""
        )
    return f"<table><thead><tr><th>Rank</th><th>Ticker</th><th>Score</th><th>Numeric Basis</th><th>Rationale</th></tr></thead><tbody>{''.join(rows)}</tbody></table>"


def render_relative_valuation(analysis: dict[str, Any]) -> str:
    rows = []
    for item in analysis["relative_valuation"]:
        rows.append(
            f"""<tr><td><strong>{esc(item['ticker'])}</strong></td>
            <td>{pct(item.get('pe_premium_discount_pct'))}</td>
            <td>{pct(item.get('ev_ebitda_premium_discount_pct'))}</td>
            <td>{pct(item.get('fcf_yield_spread_pct'))}</td>
            <td>{esc(item.get('note'))} {source_tag("[Calc]")}</td></tr>"""
        )
    return f"<table><thead><tr><th>Ticker</th><th>P/E Premium</th><th>EV/EBITDA Premium</th><th>FCF Yield Spread</th><th>Interpretation</th></tr></thead><tbody>{''.join(rows)}</tbody></table>"


def render_variant_views(analysis: dict[str, Any]) -> str:
    return "".join(
        f"""<div class="note"><p><span class="pill">{esc(item['ticker'])}</span>{esc(item['view'])} {source_tag("[Calc]")}</p></div>"""
        for item in analysis["per_ticker_variant_views"]
    )


def render_macro_lens(analysis: dict[str, Any]) -> str:
    macro = analysis["macro_lens"]
    if macro.get("status") == "available":
        rows = "".join(
            f"<tr><td>{esc(item.get('label') or item.get('id'))}</td><td>{esc(item.get('value'))}</td><td>{source_tag('[Macro]')}</td></tr>"
            for item in macro.get("series", [])
        )
        return f"<p>{esc(macro.get('summary'))} {source_tag('[Macro]')}</p><table><tbody>{rows}</tbody></table>"
    return f"<p>{esc(macro.get('summary'))} {source_tag('[Macro]')}</p>"


def render_catalyst_risk(analysis: dict[str, Any]) -> str:
    rows = []
    for item in analysis["catalyst_risk_comparison"]:
        catalysts = "; ".join(
            f"{catalyst.get('date') or 'date_unknown'}: {catalyst.get('event') or catalyst.get('description')}"
            for catalyst in item.get("catalysts", [])
            if isinstance(catalyst, dict)
        )
        risks = "; ".join(
            f"{risk.get('risk') or risk.get('title')}: {risk.get('mechanism')}"
            for risk in item.get("risks", [])
            if isinstance(risk, dict)
        )
        rows.append(f"<tr><td><strong>{esc(item['ticker'])}</strong></td><td>{esc(catalysts or 'date_unknown: catalyst unavailable')} {source_tag('[User]')}</td><td>{esc(risks or 'Risk mechanism unavailable')} {source_tag('[Calc]')}</td></tr>")
    return f"<table><thead><tr><th>Ticker</th><th>Catalysts</th><th>Risk Mechanisms</th></tr></thead><tbody>{''.join(rows)}</tbody></table>"


def render_missing_data(analysis: dict[str, Any]) -> str:
    missing = analysis.get("missing_data_disclosure") or []
    if not missing:
        return f"<p>No missing fields in the common metric matrix. {source_tag('[Calc]')}</p>"
    rows = "".join(
        f"""<tr><td>{esc(item['ticker'])}</td><td>{esc(item['label'])}</td><td class="missing">{esc(item['display'])}</td><td>{esc(item['reason'])}</td></tr>"""
        for item in missing
    )
    return f"<table><thead><tr><th>Ticker</th><th>Metric</th><th>Display</th><th>Reason</th></tr></thead><tbody>{rows}</tbody></table>"


def validate_mode_b_comparison_html(
    html_text: str,
    *,
    analysis_result: dict[str, Any],
    html_path: Path | None = None,
) -> dict[str, Any]:
    metrics = rendered_metrics(html_text)
    visible = visible_text(html_text)
    errors: list[str] = []
    warnings: list[str] = []
    tickers = analysis_result.get("compared_tickers") if isinstance(analysis_result.get("compared_tickers"), list) else []
    columns = analysis_result.get("metric_columns") if isinstance(analysis_result.get("metric_columns"), list) else []
    matrix = analysis_result.get("metric_matrix") if isinstance(analysis_result.get("metric_matrix"), list) else []

    metrics.update(
        {
            "comparison_ticker_count": len(tickers),
            "comparison_column_count": len(columns),
            "ranking_count": len(analysis_result.get("ranking") or []),
            "relative_valuation_count": len(analysis_result.get("relative_valuation") or []),
            "missing_disclosure_count": len(analysis_result.get("missing_data_disclosure") or []),
            "body_word_count": len(re.findall(r"[A-Za-z0-9가-힣']+", visible)),
        }
    )
    if not 2 <= len(tickers) <= 5:
        errors.append(f"Mode B requires 2-5 compared tickers, found {len(tickers)}")
    if len(columns) < 8:
        errors.append("Mode B metric matrix has too few common columns")
    column_keys = [column.get("key") for column in columns if isinstance(column, dict)]
    for row in matrix:
        values = row.get("values") if isinstance(row, dict) else {}
        if sorted(values.keys()) != sorted(column_keys):
            errors.append(f"metric matrix columns are not symmetric for {row.get('ticker') if isinstance(row, dict) else 'unknown'}")
    if len(analysis_result.get("ranking") or []) != len(tickers):
        errors.append("Mode B ranking does not include every ticker")
    best_pick = analysis_result.get("best_pick") if isinstance(analysis_result.get("best_pick"), dict) else {}
    if not best_pick.get("ticker"):
        errors.append("Mode B best_pick is missing")
    reasoning = analysis_result.get("best_pick_reasoning") if isinstance(analysis_result.get("best_pick_reasoning"), dict) else {}
    reasoning_drivers = reasoning.get("numeric_drivers") if isinstance(reasoning.get("numeric_drivers"), list) else []
    if reasoning.get("ticker") != best_pick.get("ticker") or len(reasoning_drivers) < 3:
        errors.append("Mode B best-pick reasoning must match best_pick and include at least 3 numeric drivers")
    if len(analysis_result.get("relative_valuation") or []) != len(tickers):
        errors.append("Mode B relative_valuation does not include every ticker")
    if not analysis_result.get("macro_lens"):
        errors.append("Mode B macro lens is missing")
    missing = analysis_result.get("missing_data_disclosure") or []
    missing_cell_count = count_missing_cells(matrix)
    if len(missing) != missing_cell_count:
        errors.append(f"Mode B missing-data disclosure count mismatch: {len(missing)} != {missing_cell_count}")
    if missing and not all(item.get("display") == MISSING_DISPLAY and item.get("reason") for item in missing if isinstance(item, dict)):
        errors.append("Mode B missing-data disclosure must display — with reason")
    if metrics["table_count"] < 4:
        errors.append(f"Mode B comparison requires at least 4 tables, found {metrics['table_count']}")
    if metrics["body_text_chars"] < 3500:
        errors.append(f"Mode B comparison body text is too thin: {metrics['body_text_chars']} chars")
    if metrics["source_tag_count"] < max(12, len(tickers) * 6):
        errors.append(f"Mode B source tag count below threshold: {metrics['source_tag_count']}")
    for heading in ("Common Metric Matrix", "Best-Pick Decision Rationale", "Relative Valuation", "Macro Lens", "Missing-Data Disclosure", "Disclaimer"):
        if heading.lower() not in visible.lower():
            errors.append(f"Mode B required heading missing: {heading}")
    for pattern in (r"\{[A-Z0-9_]+\}", "/Users/", "stock-analysis-agent/output"):
        if re.search(pattern, html_text):
            errors.append(f"forbidden rendered pattern present: {pattern}")
    if "investment advice" not in html_text.lower():
        errors.append("disclaimer missing")

    return {
        "status": "FAIL" if errors else "PASS",
        "metrics": metrics,
        "errors": errors,
        "warnings": warnings,
        "report_path": display_path(html_path) if html_path else None,
    }


def count_missing_cells(matrix: list[Any]) -> int:
    total = 0
    for row in matrix:
        values = row.get("values") if isinstance(row, dict) else {}
        if not isinstance(values, dict):
            continue
        total += sum(1 for value in values.values() if isinstance(value, dict) and value.get("missing"))
    return total


def build_comparison_quality_report(
    *,
    analysis_result: dict[str, Any],
    render_report: dict[str, Any],
) -> dict[str, Any]:
    items = comparison_quality_items(analysis_result, render_report)
    blocking = [
        item["detail"]
        for item in items
        if item["status"] == "FAIL" and item.get("delivery_impact") == "delivery_blocking_flag"
    ]
    return {
        "schema_version": "abc-parity-mode-b-comparison-quality-v1",
        "mode": "B",
        "output_mode": "B",
        "compared_tickers": analysis_result.get("compared_tickers"),
        "overall_result": "PASS" if not blocking else "FAIL",
        "items": items,
        "delivery_gate": {
            "result": "PASS" if not blocking else "FAIL",
            "ready_for_delivery": not blocking,
            "blocking_items": blocking,
            "patchable_blocking_items": blocking,
            "terminal_blocking_items": [],
            "max_severity": "NONE" if not blocking else "BLOCKER",
        },
        "render_report_path": render_report.get("html_path"),
        "created_at": utc_now(),
    }


def comparison_quality_items(analysis: dict[str, Any], render_report: dict[str, Any]) -> list[dict[str, Any]]:
    items = []
    items.append(quality_item("ticker_count", 2 <= len(analysis.get("compared_tickers") or []) <= 5, "2-5 ticker contract"))
    items.append(quality_item("metric_matrix", bool(analysis.get("metric_matrix")) and bool(analysis.get("metric_columns")), "symmetric metric matrix exists"))
    items.append(quality_item("ranking", len(analysis.get("ranking") or []) == len(analysis.get("compared_tickers") or []), "ranking includes all tickers"))
    items.append(quality_item("best_pick", bool((analysis.get("best_pick") or {}).get("ticker")), "best pick includes numeric basis"))
    items.append(quality_item("best_pick_reasoning", best_pick_reasoning_passes(analysis), "best-pick decision rationale includes at least 3 numeric drivers and tradeoff boundary"))
    items.append(quality_item("relative_valuation", len(analysis.get("relative_valuation") or []) == len(analysis.get("compared_tickers") or []), "peer median premium/discount exists"))
    items.append(quality_item("missing_data_disclosure", missing_data_disclosure_passes(analysis), "missing matrix cells are disclosed as — with reasons"))
    items.append(quality_item("macro_lens", bool(analysis.get("macro_lens")), "macro light lens exists"))
    items.append(quality_item("rendered_output", render_report.get("status") == "PASS", "rendered Mode B comparison passes validator"))
    return items


def best_pick_reasoning_passes(analysis: dict[str, Any]) -> bool:
    best = analysis.get("best_pick") if isinstance(analysis.get("best_pick"), dict) else {}
    reasoning = analysis.get("best_pick_reasoning") if isinstance(analysis.get("best_pick_reasoning"), dict) else {}
    drivers = reasoning.get("numeric_drivers") if isinstance(reasoning.get("numeric_drivers"), list) else []
    return bool(
        best.get("ticker")
        and reasoning.get("ticker") == best.get("ticker")
        and len(drivers) >= 3
        and reasoning.get("tradeoff")
        and reasoning.get("missing_data_boundary")
    )


def missing_data_disclosure_passes(analysis: dict[str, Any]) -> bool:
    matrix = analysis.get("metric_matrix") if isinstance(analysis.get("metric_matrix"), list) else []
    missing = analysis.get("missing_data_disclosure") if isinstance(analysis.get("missing_data_disclosure"), list) else []
    if len(missing) != count_missing_cells(matrix):
        return False
    return all(
        isinstance(item, dict) and item.get("display") == MISSING_DISPLAY and item.get("reason")
        for item in missing
    )


def quality_item(item: str, passed: bool, detail: str) -> dict[str, Any]:
    return {
        "item": item,
        "status": "PASS" if passed else "FAIL",
        "detail": detail,
        "severity": "NONE" if passed else "BLOCKER",
        "delivery_impact": "none" if passed else "delivery_blocking_flag",
        "blocker_action": "none" if passed else "patchable",
    }


def display_path(path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return str(path.resolve())
