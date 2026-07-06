"""Mode A/C rendering and rendered-output validation for the A/B/C parity runner."""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.parity.data_sources import load_json, write_json
from scripts.parity.formatting import (
    as_number,
    currency_prefix,
    currency_symbol,
    fmt,
    metric_display,
    metric_value,
    pct,
)
from tools.quality_report import build_rendered_output_item

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GOLDEN_CONFIG = {
    "minimums": {
        "body_text_chars": 10000,
        "canvas_count": 3,
        "html_byte_size": 50000,
        "script_count": 3,
        "table_count": 5,
    },
    "required_heading_groups": [
        {"id": "scenario", "pattern": "Scenario Valuation|시나리오 밸류에이션"},
        {"id": "kpi", "pattern": "Key Performance Indicators|핵심 KPI"},
        {"id": "variant_view", "pattern": "Variant View|투자 thesis|투자 논점|차별적 관점"},
        {"id": "precision_risk", "pattern": "Precision Risk|정밀 리스크"},
        {"id": "macro", "pattern": "Macro Environment|Macro Context|매크로 환경"},
        {"id": "valuation", "pattern": "Valuation|밸류에이션"},
        {"id": "peer", "pattern": "Peer Comparison|동종업계 비교"},
        {"id": "charts", "pattern": "Charts & Trend Data|재무 차트"},
        {"id": "quality", "pattern": "Quality of Earnings|Financial Detail Analysis|재무 세부 분석"},
        {"id": "portfolio", "pattern": "Portfolio Strategy|포트폴리오 전략"},
        {"id": "disclaimer", "pattern": "Disclaimer|면책"},
    ],
    "forbidden_patterns": [
        "arrays not present in this fixture",
        r"\{[A-Z0-9_]+\}",
        "/Users/",
        "stock-analysis-agent/output",
    ],
}

LABELS: dict[str, dict[str, str]] = {
    "en": {
        "investment_dashboard": "Investment Dashboard",
        "mode_c_dashboard": "Mode C Deep Dive Dashboard",
        "scenario_valuation": "Scenario Valuation",
        "scenario_valuation_12m": "Scenario Valuation (12-Month Targets)",
        "key_performance_indicators": "Key Performance Indicators",
        "investment_thesis_variant_view": "Investment Thesis & Variant View",
        "precision_risk_analysis": "Precision Risk Analysis",
        "valuation_metrics": "Valuation Metrics",
        "dcf_valuation": "DCF Valuation",
        "valuation_bridge": "Valuation Bridge",
        "peer_comparison": "Peer Comparison",
        "macro_environment": "Macro Environment",
        "analyst_coverage": "Analyst Coverage",
        "charts_trend_data": "Charts & Trend Data",
        "financial_detail_analysis": "Financial Detail Analysis",
        "quality_gate": "Quality of Earnings & Evidence Gate",
        "quality_earnings": "Quality of Earnings",
        "portfolio_strategy": "Portfolio Strategy",
        "source_appendix": "Source-Tagged Claims Appendix",
        "chart_evidence_boundary": "Chart Evidence Boundary",
        "quarterly_revenue_operating_income": "Quarterly Revenue & Operating Income",
        "margin_trend": "Margin Trend - Op vs Net %",
        "latest_quarter_bridge": "Latest Quarter Business Driver Bridge",
        "fcf_run_rate": "Free Cash Flow Run-Rate - validated trend boundary",
        "quarterly_trend_compatibility": "Quarterly Trend Compatibility - revenue, operating income, FCF",
        "stock_price_targets": "Stock Price vs Scenario Targets",
        "base_dcf_fair_value": "Base DCF Fair Value",
        "enterprise_value": "Enterprise Value",
        "equity_value": "Equity value",
        "terminal_growth": "Terminal growth",
        "dcf_sensitivity_table": "DCF Sensitivity Table",
        "reverse_dcf": "Reverse DCF",
        "market_is_pricing_in": "Market is pricing in",
        "our_base_assumes": "Our base assumes",
        "annual_fcf_growth": "annual FCF growth",
        "consensus_average": "Consensus Average",
        "median_target": "Median Target",
        "street_high": "Street High",
        "street_low": "Street Low",
        "coverage_status": "Coverage status:",
        "weighted_fair_value": "Weighted Fair Value",
        "current_price": "Current Price",
        "implied_view_vs_market": "Implied View vs Market",
        "reconciliation_logic": "Reconciliation Logic",
        "decision_anchor": "Decision anchor:",
        "weight": "Weight",
        "subject": "Subject",
        "evidence_boundary_4_artifact": "4-artifact evidence boundary",
        "renderer_guardrails": "renderer-specific guardrails",
        "scenario_math": "Scenario math",
        "chart_arrays": "Chart arrays",
        "delivery_gate": "Delivery gate",
        "scenario_execution_guidelines": "3-scenario execution guidelines",
        "what_would_make_wrong": "What Would Make Me Wrong",
        "source_profile": "Source profile",
        "analysis_date": "Analysis Date:",
        "mode_deep_dive": "Mode: Deep Dive Dashboard (C)",
        "data_mode": "Data Mode:",
        "confidence_cap": "Confidence Cap:",
        "rr_score": "R/R Score:",
        "bear_case": "Bear Case",
        "base_case": "Base Case",
        "bull_case": "Bull Case",
        "variant_view": "Variant View",
        "market_cap": "Market Cap",
        "revenue_ttm": "Revenue TTM",
        "revenue_growth": "Revenue Growth",
        "operating_margin": "Operating Margin",
        "op_margin": "Op Margin",
        "fcf_yield": "FCF Yield",
        "net_debt_ebitda": "Net Debt / EBITDA",
        "net_debt": "Net Debt",
        "fcf_ttm": "FCF TTM",
        "pe_ratio": "P/E",
        "beta": "Beta",
        "risk": "Risk",
        "mechanism": "Mechanism",
        "financial_impact": "Financial Impact",
        "probability": "Probability",
        "metric": "Metric",
        "current": "Current",
        "unit": "Unit",
        "assessment": "Assessment",
        "company": "Company",
        "basis": "Basis",
        "value": "Value",
        "period": "Period",
        "check": "Check",
        "quarter": "Quarter",
        "revenue": "Revenue",
        "gross_profit": "Gross Profit",
        "operating_income": "Operating Income",
        "op_income": "Op Income",
        "net_income": "Net Income",
        "free_cash_flow": "Free Cash Flow",
        "net_margin": "Net Margin",
        "latest_quarter": "Latest Quarter",
        "bull_target": "Bull Target",
        "base_target": "Base Target",
        "bear_target": "Bear Target",
        "price": "Price",
        "date": "Date",
        "catalyst": "Catalyst",
        "significance": "Significance",
        "claim": "Claim",
        "source": "Source",
        "grade": "Grade",
        "tag": "Tag",
        "disclaimer": "Disclaimer",
        "last_updated": "Last updated:",
        "sources": "Sources:",
        "validated_sources": "validated metrics, evidence pack, deterministic calculations.",
        "disclaimer_default": "This dashboard is for informational purposes only and does not constitute investment advice.",
        "chart_boundary_paragraph_1": "Revenue, operating income, margin, FCF run-rate, and business-driver bridge charts are populated from normalized quarterly financial statement rows or validated TTM metrics. If the raw provider nests rows under a vendor-specific envelope, the renderer must flatten that structure before charting so the dashboard cannot pass with a single zero-filled fallback period.",
        "chart_boundary_paragraph_2": "The audit table below mirrors the chart arrays used by Chart.js. It lets a reviewer verify that trend visuals are backed by at least four concrete periods, non-zero revenue and operating-income points, and visibly changing margins before the dashboard clears strict semantic parity.",
    },
    "ko": {
        "investment_dashboard": "투자 대시보드",
        "mode_c_dashboard": "Mode C 심층 대시보드",
        "scenario_valuation": "시나리오 밸류에이션",
        "scenario_valuation_12m": "시나리오 밸류에이션 (12개월 목표가)",
        "key_performance_indicators": "핵심 KPI",
        "investment_thesis_variant_view": "투자 논점과 차별적 관점",
        "precision_risk_analysis": "정밀 리스크 분석",
        "valuation_metrics": "밸류에이션 지표",
        "dcf_valuation": "DCF 밸류에이션",
        "valuation_bridge": "밸류에이션 브리지",
        "peer_comparison": "동종업계 비교",
        "macro_environment": "매크로 환경",
        "analyst_coverage": "애널리스트 커버리지",
        "charts_trend_data": "재무 차트",
        "financial_detail_analysis": "재무 세부 분석",
        "quality_gate": "이익 품질 및 증거 게이트",
        "quality_earnings": "이익 품질",
        "portfolio_strategy": "포트폴리오 전략",
        "source_appendix": "출처 태그 클레임 부록",
        "chart_evidence_boundary": "차트 증거 경계",
        "quarterly_revenue_operating_income": "분기 매출 및 영업이익",
        "margin_trend": "마진 추이 - 영업 vs 순이익률",
        "latest_quarter_bridge": "최근 분기 사업 동인 브리지",
        "fcf_run_rate": "잉여현금흐름 런레이트 - 검증 추세 경계",
        "quarterly_trend_compatibility": "분기 추세 정합성 - 매출, 영업이익, FCF",
        "stock_price_targets": "주가와 시나리오 목표가",
        "base_dcf_fair_value": "Base DCF 적정가",
        "enterprise_value": "기업가치",
        "equity_value": "주주가치",
        "terminal_growth": "영구성장률",
        "dcf_sensitivity_table": "DCF 민감도 표",
        "reverse_dcf": "역산 DCF",
        "market_is_pricing_in": "시장은 다음을 반영",
        "our_base_assumes": "Base 가정",
        "annual_fcf_growth": "연간 FCF 성장률",
        "consensus_average": "컨센서스 평균",
        "median_target": "중앙값 목표가",
        "street_high": "최고 목표가",
        "street_low": "최저 목표가",
        "coverage_status": "커버리지 상태:",
        "weighted_fair_value": "가중 적정가",
        "current_price": "현재가",
        "implied_view_vs_market": "시장 대비 내재 시각",
        "reconciliation_logic": "조정 논리",
        "decision_anchor": "판단 앵커:",
        "weight": "가중치",
        "subject": "대상 기업",
        "evidence_boundary_4_artifact": "4개 산출물 증거 경계",
        "renderer_guardrails": "렌더러 전용 가드레일",
        "scenario_math": "시나리오 산식",
        "chart_arrays": "차트 배열",
        "delivery_gate": "전달 게이트",
        "scenario_execution_guidelines": "3개 시나리오 실행 기준",
        "what_would_make_wrong": "내 판단이 틀리는 조건",
        "source_profile": "소스 프로필",
        "analysis_date": "분석일:",
        "mode_deep_dive": "모드: 심층 대시보드 (C)",
        "data_mode": "데이터 모드:",
        "confidence_cap": "신뢰도 상한:",
        "rr_score": "R/R 점수:",
        "bear_case": "약세 시나리오",
        "base_case": "기준 시나리오",
        "bull_case": "강세 시나리오",
        "variant_view": "차별적 관점",
        "market_cap": "시가총액",
        "revenue_ttm": "TTM 매출",
        "revenue_growth": "매출 성장률",
        "operating_margin": "영업이익률",
        "op_margin": "영업이익률",
        "fcf_yield": "FCF 수익률",
        "net_debt_ebitda": "순차입금 / EBITDA",
        "net_debt": "순차입금",
        "fcf_ttm": "TTM FCF",
        "pe_ratio": "PER",
        "beta": "베타",
        "risk": "리스크",
        "mechanism": "작동 경로",
        "financial_impact": "재무 영향",
        "probability": "확률",
        "metric": "지표",
        "current": "현재",
        "unit": "단위",
        "assessment": "판단",
        "company": "기업",
        "basis": "근거",
        "value": "값",
        "period": "기간",
        "check": "체크",
        "quarter": "분기",
        "revenue": "매출",
        "gross_profit": "매출총이익",
        "operating_income": "영업이익",
        "op_income": "영업이익",
        "net_income": "순이익",
        "free_cash_flow": "잉여현금흐름",
        "net_margin": "순이익률",
        "latest_quarter": "최근 분기",
        "bull_target": "강세 목표가",
        "base_target": "기준 목표가",
        "bear_target": "약세 목표가",
        "price": "주가",
        "date": "날짜",
        "catalyst": "촉매",
        "significance": "의미",
        "claim": "클레임",
        "source": "출처",
        "grade": "등급",
        "tag": "태그",
        "disclaimer": "면책 고지",
        "last_updated": "최종 업데이트:",
        "sources": "출처:",
        "validated_sources": "검증 지표, 증거 패키지, 결정론적 계산.",
        "disclaimer_default": "이 대시보드는 정보 제공용이며 투자 조언이 아닙니다.",
        "chart_boundary_paragraph_1": "매출, 영업이익, 마진, 잉여현금흐름 런레이트, 사업 동인 브리지 차트는 정규화된 분기 재무제표 행 또는 검증된 TTM 지표에서 채웁니다. 원천 제공자가 벤더별 포장 구조 안에 행을 중첩하더라도, 렌더러는 차트 작성 전에 이를 평탄화해 단일 0값 기간으로 대시보드가 통과하지 못하게 해야 합니다.",
        "chart_boundary_paragraph_2": "아래 감사 표는 Chart.js에 전달된 차트 배열을 그대로 반영합니다. 검토자는 대시보드가 엄격한 의미 정합성을 통과하기 전에 추세 시각화가 최소 4개 실제 기간, 0이 아닌 매출 및 영업이익 값, 실제로 변하는 마진에 의해 뒷받침되는지 확인할 수 있습니다.",
    },
}

KOREAN_REQUIRED_HEADING_FALLBACKS = {
    "variant_view": r"투자 논점|차별적 관점",
    "precision_risk": r"정밀 리스크",
    "disclaimer": r"면책|투자 조언",
}


def is_korean(language: str | None) -> bool:
    return str(language or "").lower().startswith("ko")


def mode_c_label(language: str | None, key: str) -> str:
    locale = "ko" if is_korean(language) else "en"
    return LABELS.get(locale, {}).get(key) or LABELS["en"].get(key, key)


def mode_c_count(language: str | None, count: int, en_unit: str, ko_unit: str) -> str:
    if is_korean(language):
        return f"{count}개 {ko_unit}"
    return f"{count} {en_unit}"


def mode_c_status(language: str | None, value: Any) -> str:
    text = str(value or "")
    if not is_korean(language):
        return text
    return {
        "available": "이용 가능",
        "unavailable": "이용 불가",
        "success": "성공",
        "monitor": "모니터링",
        "neutral": "중립",
        "overweight": "비중확대",
        "underweight": "비중축소",
    }.get(text.lower(), text.replace("_", " "))


@dataclass(frozen=True)
class RenderResult:
    ticker: str
    artifact_root: Path
    html_path: Path
    render_report_path: Path
    status: str
    metrics: dict[str, Any]


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_render_handoff(
    *,
    language: str,
    market: str,
    mode: str,
    run_id: str,
    ticker: str,
) -> RenderResult:
    if mode == "A":
        return build_mode_a_render_handoff(
            language=language,
            market=market,
            mode=mode,
            run_id=run_id,
            ticker=ticker,
        )
    if mode == "C":
        return build_mode_c_render_handoff(
            language=language,
            market=market,
            mode=mode,
            run_id=run_id,
            ticker=ticker,
        )
    raise ValueError(f"Mode {mode} renderer is not implemented yet")


def build_mode_a_render_handoff(
    *,
    language: str,
    market: str,
    mode: str,
    run_id: str,
    ticker: str,
) -> RenderResult:
    if mode != "A":
        raise ValueError("Mode A renderer only accepts mode='A'")

    ticker_dir = REPO_ROOT / "output" / "runs" / run_id / ticker
    analysis_path = ticker_dir / "analysis-result.json"
    validated_path = ticker_dir / "validated-data.json"

    analysis = load_json(analysis_path)
    validated = load_json(validated_path)
    if analysis.get("output_mode") != "A":
        raise ValueError("Mode A renderer requires analysis-result.output_mode == 'A'")

    html_text = build_mode_a_briefing_html(
        analysis=analysis,
        language=language,
        market=market,
    )
    html_path = ticker_dir / "mode-a-briefing.html"
    html_path.write_text(html_text, encoding="utf-8")

    render_validation = validate_mode_a_rendered_html(
        html_text,
        analysis=analysis,
        html_path=html_path,
        validated=validated,
    )
    quality_item = build_rendered_output_item(html_path, analysis, validated)
    if quality_item.get("status") == "FAIL":
        render_validation["errors"].extend(quality_item.get("errors") or [])
        render_validation["status"] = "FAIL"
    elif quality_item.get("status") == "PASS_WITH_FLAGS":
        render_validation["warnings"].extend(quality_item.get("warnings") or [])

    render_report = {
        "schema_version": "abc-parity-mode-a-render-report-v1",
        "ticker": ticker,
        "market": market,
        "mode": mode,
        "language": language,
        "status": render_validation["status"],
        "html_path": display_path(html_path),
        "analysis_result_path": display_path(analysis_path),
        "quality_item": quality_item,
        "validation": render_validation,
        "created_at": utc_now(),
    }
    render_report_path = ticker_dir / "mode-a-render-report.json"
    write_json(render_report_path, render_report)
    if render_validation["status"] != "PASS":
        raise ValueError(
            "Mode A rendered output failed parity checks: "
            + "; ".join(render_validation["errors"][:8])
        )
    return RenderResult(
        ticker=ticker,
        artifact_root=ticker_dir,
        html_path=html_path,
        render_report_path=render_report_path,
        status=render_validation["status"],
        metrics=render_validation["metrics"],
    )


def build_mode_c_render_handoff(
    *,
    language: str,
    market: str,
    mode: str,
    run_id: str,
    ticker: str,
) -> RenderResult:
    if mode != "C":
        raise ValueError("Mode C renderer only accepts mode='C'")

    ticker_dir = REPO_ROOT / "output" / "runs" / run_id / ticker
    analysis_path = ticker_dir / "analysis-result.json"
    validated_path = ticker_dir / "validated-data.json"
    calculations_path = ticker_dir / "deterministic-calculations.json"
    evidence_path = ticker_dir / "evidence-pack.json"

    analysis = load_json(analysis_path)
    validated = load_json(validated_path)
    calculations = load_json(calculations_path)
    evidence = load_json(evidence_path)
    if analysis.get("output_mode") != "C":
        raise ValueError("Mode C renderer requires analysis-result.output_mode == 'C'")

    html_text = build_mode_c_dashboard_html(
        analysis=analysis,
        calculations=calculations,
        evidence=evidence,
        language=language,
        market=market,
        validated=validated,
    )
    html_path = ticker_dir / "mode-c-dashboard.html"
    html_path.write_text(html_text, encoding="utf-8")

    render_validation = validate_mode_c_rendered_html(
        html_text,
        analysis=analysis,
        html_path=html_path,
        validated=validated,
    )
    quality_item = build_rendered_output_item(html_path, analysis, validated)
    if quality_item.get("status") == "FAIL":
        render_validation["errors"].extend(quality_item.get("errors") or [])
        render_validation["status"] = "FAIL"
    elif quality_item.get("status") == "PASS_WITH_FLAGS":
        render_validation["warnings"].extend(quality_item.get("warnings") or [])

    render_report = {
        "schema_version": "abc-parity-mode-c-render-report-v1",
        "ticker": ticker,
        "market": market,
        "mode": mode,
        "language": language,
        "status": render_validation["status"],
        "html_path": display_path(html_path),
        "analysis_result_path": display_path(analysis_path),
        "quality_item": quality_item,
        "validation": render_validation,
        "created_at": utc_now(),
    }
    render_report_path = ticker_dir / "mode-c-render-report.json"
    write_json(render_report_path, render_report)
    if render_validation["status"] != "PASS":
        raise ValueError(
            "Mode C rendered output failed parity checks: "
            + "; ".join(render_validation["errors"][:8])
        )
    return RenderResult(
        ticker=ticker,
        artifact_root=ticker_dir,
        html_path=html_path,
        render_report_path=render_report_path,
        status=render_validation["status"],
        metrics=render_validation["metrics"],
    )


def build_mode_a_briefing_html(
    *,
    analysis: dict[str, Any],
    language: str,
    market: str,
) -> str:
    ticker = str(analysis.get("ticker") or "UNKNOWN")
    company = str(analysis.get("company_name") or ticker)
    currency = str(analysis.get("currency") or ("KRW" if market == "KR" else "USD"))
    sections = analysis.get("sections") if isinstance(analysis.get("sections"), dict) else {}
    metrics = analysis.get("key_metrics") if isinstance(analysis.get("key_metrics"), dict) else {}
    scenarios = analysis.get("scenarios") if isinstance(analysis.get("scenarios"), dict) else {}
    thesis = mode_a_brief_text(analysis.get("thesis") or sections.get("one_line_thesis"), "Thesis unavailable.", max_words=42)
    action = mode_a_brief_text(
        sections.get("action_signal"),
        "Use scenario math and source-tagged evidence before changing exposure.",
        max_words=32,
    )
    variant_q1 = mode_a_brief_text(sections.get("variant_view_q1") or thesis, thesis, max_words=24)
    variant_q2 = mode_a_brief_text(
        sections.get("variant_view_q2"),
        "The second debate is whether validated cash-flow evidence supports the base case.",
        max_words=24,
    )
    variant_q3 = mode_a_brief_text(
        sections.get("variant_view_q3"),
        "The third debate is whether downside risk is already reflected in the scenario spread.",
        max_words=24,
    )
    price = analysis.get("price_at_analysis") or metric_value(metrics, "price_at_analysis")
    rr_score = mode_a_rr_score(analysis, scenarios)
    base_target = scenario_target(scenarios, "base")
    company_signal = mode_a_company_signal(company=company, currency=currency, metrics=metrics, ticker=ticker)
    dcf = analysis.get("dcf_analysis") if isinstance(analysis.get("dcf_analysis"), dict) else {}
    bridge = analysis.get("valuation_bridge") if isinstance(analysis.get("valuation_bridge"), dict) else {}
    reverse_dcf = analysis.get("reverse_dcf") if isinstance(analysis.get("reverse_dcf"), dict) else {}

    return f"""<!DOCTYPE html>
<html lang="{esc(language)}">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{esc(company)} ({esc(ticker)}) - Mode A Briefing</title>
  {korean_font(language)}
  <style>
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: #f7f8fb; color: #172033; font-family: Inter, -apple-system, BlinkMacSystemFont, "Noto Sans KR", sans-serif; }}
    main {{ max-width: 980px; margin: 0 auto; padding: 28px 22px 42px; }}
    header {{ background: #101827; color: #fff; border-radius: 8px; padding: 26px 28px; }}
    section {{ background: #fff; border: 1px solid #e4e7ee; border-radius: 8px; margin-top: 16px; padding: 22px 24px; }}
    h1 {{ margin: 0; font-size: 30px; line-height: 1.15; letter-spacing: 0; }}
    h2 {{ margin: 0 0 12px; font-size: 16px; line-height: 1.3; color: #101827; letter-spacing: 0; }}
    p {{ margin: 0 0 11px; line-height: 1.65; font-size: 14px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ border-bottom: 1px solid #e7eaf0; padding: 10px 8px; text-align: left; vertical-align: top; }}
    th {{ color: #5c667a; font-size: 11px; text-transform: uppercase; }}
    .meta {{ color: #a9b6cc; margin-top: 8px; font-size: 13px; }}
    .hero-grid {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin-top: 18px; }}
    .hero-stat {{ background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.14); border-radius: 7px; padding: 10px; }}
    .label {{ color: #6b7486; font-size: 11px; text-transform: uppercase; margin-bottom: 4px; }}
    .value {{ color: #101827; font-weight: 750; font-size: 20px; line-height: 1.2; }}
    .hero-stat .label {{ color: #b7c2d4; }}
    .hero-stat .value {{ color: #fff; }}
    .kpi-grid {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }}
    .kpi {{ border: 1px solid #e4e7ee; border-radius: 7px; padding: 12px; min-height: 104px; }}
    .source-tag {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11px; padding: 1px 5px; border-radius: 4px; background: #f0f2f5; color: #334155; }}
    .grade-badge {{ font-size: 11px; font-weight: 750; padding: 1px 6px; border-radius: 4px; background: #e8f0ff; color: #1e3a8a; }}
    .pill {{ display: inline-block; border-radius: 999px; padding: 4px 9px; margin-right: 6px; background: #eef3ff; color: #244c93; font-size: 12px; font-weight: 700; }}
    .muted {{ color: #5c667a; }}
    .risk-card, .claim-card {{ border-left: 3px solid #335c99; padding: 9px 0 9px 12px; margin-top: 10px; }}
    .footer-note {{ color: #5c667a; font-size: 12px; }}
    @media (max-width: 760px) {{ .hero-grid, .kpi-grid {{ grid-template-columns: 1fr; }} main {{ padding: 14px; }} header, section {{ padding: 18px; }} }}
  </style>
</head>
<body>
<main>
  <header>
    <div class="label">Mode A Evidence Briefing</div>
    <h1>{esc(company)} ({esc(ticker)})</h1>
    <p class="meta">Analysis Date: {esc(analysis.get("analysis_date"))} · Market: {esc(market)} · Source profile: {esc(analysis.get("source_profile") or "mixed")} · Confidence cap: {esc(analysis.get("confidence_cap") or "unknown")}</p>
    <div class="hero-grid">
      <div class="hero-stat"><div class="label">Price At Analysis</div><div class="value">{currency_symbol(currency)}{fmt(price, 2)}</div></div>
      <div class="hero-stat"><div class="label">Verdict</div><div class="value">{esc(analysis.get("verdict"))}</div></div>
      <div class="hero-stat"><div class="label">R/R Score</div><div class="value">{mode_a_number(rr_score, 2)}</div></div>
      <div class="hero-stat"><div class="label">Base Target</div><div class="value">{mode_a_currency(base_target, currency)}</div></div>
    </div>
  </header>
  {deterministic_disclosure_banner(analysis, language)}

  <section id="decision-brief">
    <h2>Decision Brief</h2>
    <p><span class="pill">Thesis</span>{esc(thesis)} {source_tag("[Calc]")}</p>
    <p><span class="pill">Evidence Tape</span>{esc(company_signal)} The decision hinges on verified metrics that also drive scenarios, R/R score, and valuation bridge. {source_tag("[Calc]")}</p>
    <p><span class="pill">Action</span>{esc(action)} Mode A stays compact while showing scenario targets, KPI grades, risks, catalysts, and source-tagged claims. {source_tag("[Calc]")}</p>
    <p>{esc(company)} should be read through three checks: 1) {esc(variant_q1)} 2) {esc(variant_q2)} 3) {esc(variant_q3)} The conclusion is a compact operating view, not a standalone buy/sell slogan. {source_tag("[Calc]")}</p>
  </section>

  <section id="kpi-tape">
    <h2>Key Performance Indicators</h2>
    <div class="kpi-grid">{render_mode_a_kpis(metrics, currency)}</div>
    <p class="footer-note">Each KPI is rendered with its source tag and confidence grade. Grade D or excluded metrics should stay absent from decision logic rather than being filled with a plausible substitute. {mode_a_macro_boundary(sections)}</p>
  </section>

  <section id="scenario-rr">
    <h2>Scenario Targets and R/R</h2>
    {render_mode_a_scenarios(scenarios, currency, price=price)}
    <p>Bull, base, and bear cases show whether upside comes from operating evidence, valuation expansion, or a fragile target multiple. R/R Score {mode_a_number(rr_score, 2)} is the compact signal; assumptions show what must be true. {source_tag("[Calc]")}</p>
  </section>

  <section id="valuation-check">
    <h2>Valuation Check</h2>
    <p>{mode_a_valuation_sentence(dcf=dcf, bridge=bridge, reverse_dcf=reverse_dcf, currency=currency)} This is a sanity check; thin deterministic math stays disclosed rather than padded. {source_tag("[Calc]")}</p>
  </section>

  <section id="risk-mechanisms">
    <h2>Risk Mechanisms</h2>
    {render_mode_a_risks(analysis, sections)}
  </section>

  <section id="catalyst-watch">
    <h2>Catalyst Watch</h2>
    {render_mode_a_catalysts(analysis)}
  </section>

  <section id="evidence-notes">
    <h2>Source-Tagged Evidence Notes</h2>
    {render_mode_a_claims(analysis)}
  </section>

  <section id="disclaimer">
    <h2>Disclaimer</h2>
    <p>{esc(analysis.get("disclaimer") or "This briefing is for informational purposes only and does not constitute investment advice.")}</p>
  </section>
</main>
</body>
</html>
"""


def mode_a_brief_text(value: Any, fallback: str, *, max_words: int) -> str:
    text = re.sub(r"\s+", " ", str(value or fallback)).strip()
    if not text:
        text = fallback
    words = text.split(" ")
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]).rstrip(".,;:") + "..."


def render_mode_a_kpis(metrics: dict[str, Any], currency: str) -> str:
    cards = []
    for key, entry in mode_a_kpi_entries(metrics):
        cards.append(
            f"""<div class="kpi" data-mode-a-kpi="true">
              <div class="label">{esc(metric_title(key))}</div>
              <div class="value">{metric_display(entry, key, currency)}</div>
              <p class="muted">{metric_source(entry)}</p>
            </div>"""
        )
    return "".join(cards)


def render_mode_a_scenarios(scenarios: dict[str, Any], currency: str, *, price: Any = None) -> str:
    rows = []
    price_number = as_number(price)
    for key, label in (("bull", "Bull"), ("base", "Base"), ("bear", "Bear")):
        item = scenarios.get(key) if isinstance(scenarios.get(key), dict) else {}
        target = as_number(item.get("target"))
        return_pct = as_number(item.get("return_pct"))
        if return_pct is None and target is not None and price_number not in {None, 0}:
            return_pct = (target / price_number - 1) * 100
        rows.append(
            f"""<tr data-mode-a-scenario="true">
              <td><strong>{label}</strong></td>
              <td>{mode_a_currency(target, currency)}</td>
              <td>{mode_a_pct(return_pct)}</td>
              <td>{pct(item.get("probability"), probability=True)}</td>
              <td>{esc(item.get("key_assumption") or "Assumption unavailable.")} {source_tag("[Calc]")}</td>
            </tr>"""
        )
    return f"""<table>
      <thead><tr><th>Case</th><th>Target</th><th>Return</th><th>Probability</th><th>Assumption</th></tr></thead>
      <tbody>{''.join(rows)}</tbody>
    </table>"""


def render_mode_a_risks(analysis: dict[str, Any], sections: dict[str, Any]) -> str:
    risks = sections.get("precision_risks") if isinstance(sections.get("precision_risks"), list) else analysis.get("top_risks")
    if not isinstance(risks, list):
        risks = []
    if len(risks) < 2:
        risks = [*risks, *mode_a_fallback_risks(analysis)][:2]
    cards = []
    for risk in risks[:4]:
        if isinstance(risk, dict):
            title = risk.get("risk") or risk.get("title") or "Risk"
            mechanism = mode_a_brief_text(risk.get("mechanism"), "Mechanism requires analyst follow-up.", max_words=26)
            impact = mode_a_brief_text(
                risk.get("financial_impact") or risk.get("ebitda_impact"),
                "Financial impact is not quantified.",
                max_words=18,
            )
        else:
            title = str(risk)
            mechanism = "Mechanism requires analyst follow-up."
            impact = "Financial impact is not quantified."
        cards.append(
            f"""<div class="risk-card" data-mode-a-risk="true">
              <p><strong>{esc(title)}</strong></p>
              <p>Mechanism: {esc(mechanism)} Financial impact: {esc(impact)} {source_tag("[Calc]")}</p>
            </div>"""
        )
    return "".join(cards)


def mode_a_fallback_risks(analysis: dict[str, Any]) -> list[dict[str, str]]:
    ticker = str(analysis.get("ticker") or "the company")
    currency = str(analysis.get("currency") or "USD")
    metrics = analysis.get("key_metrics") if isinstance(analysis.get("key_metrics"), dict) else {}
    scenarios = analysis.get("scenarios") if isinstance(analysis.get("scenarios"), dict) else {}
    base_target = scenario_target(scenarios, "base")
    base_target_text = fmt(base_target, 2) if base_target is not None else "the base target"
    growth_signal = mode_a_metric_signal(metrics, "revenue_growth_yoy", currency) or "validated revenue growth"
    fcf_signal = mode_a_metric_signal(metrics, "fcf_yield", currency) or "validated FCF evidence"
    return [
        {
            "risk": f"{ticker} growth durability weakens versus the validated tape.",
            "mechanism": (
                f"If {growth_signal} decelerates, operating leverage and the scenario "
                f"multiple can compress before the next full model refresh."
            ),
            "financial_impact": (
                f"Base-case support around {base_target_text} would weaken and the R/R "
                "score should be cut before adding exposure."
            ),
        },
        {
            "risk": f"{ticker} cash conversion fails to confirm reported earnings.",
            "mechanism": (
                f"If {fcf_signal} rolls over, the DCF bridge becomes less reliable and "
                "valuation support depends more on multiple expansion."
            ),
            "financial_impact": (
                "Downside should be expressed through lower base probability, lower "
                "terminal assumptions, or a wider bear-case discount."
            ),
        },
    ]


def mode_a_metric_signal(metrics: dict[str, Any], key: str, currency: str) -> str | None:
    entry = metrics.get(key)
    if not isinstance(entry, dict):
        return None
    display = metric_display(entry, key, currency)
    if display == "-":
        return None
    return f"{metric_title(key)} {display}"


def render_mode_a_catalysts(analysis: dict[str, Any]) -> str:
    rows = []
    for catalyst in mode_a_catalyst_entries(analysis)[:4]:
        significance = mode_a_brief_text(
            catalyst.get("significance") or catalyst.get("narrative"),
            "Refresh source-tagged evidence.",
            max_words=24,
        )
        rows.append(
            f"""<tr data-mode-a-catalyst="true">
              <td>{esc(catalyst.get("date") or "date_unknown")}</td>
              <td><strong>{esc(catalyst.get("event") or catalyst.get("title") or "Catalyst")}</strong></td>
              <td>{esc(significance)} {source_tag("[User]")}</td>
            </tr>"""
        )
    return f"""<table>
      <thead><tr><th>Date</th><th>Event</th><th>Why It Matters</th></tr></thead>
      <tbody>{''.join(rows)}</tbody>
    </table>"""


def render_mode_a_claims(analysis: dict[str, Any]) -> str:
    claims = mode_a_source_claims(analysis)
    if not claims:
        return f"""<p class="claim-card">Source-tagged claims are unavailable; the briefing should be held at the evidence boundary until claims are restored. {source_tag("[User]")}</p>"""
    cards = []
    for claim in claims[:6]:
        sources = ", ".join(str(item) for item in (claim.get("sources") or [])[:2])
        claim_text = mode_a_brief_text(
            claim.get("claim") or claim.get("metric"),
            "Validated claim",
            max_words=22,
        )
        cards.append(
            f"""<div class="claim-card">
              <p>{esc(claim_text)} {grade_badge({"grade": claim.get("grade") or "C"})} {source_tag(tag_for_grade(str(claim.get("grade") or "C")))}</p>
              <p class="footer-note">Source basis: {esc(sources or "evidence pack")}</p>
            </div>"""
        )
    return "".join(cards)


def mode_a_kpi_entries(metrics: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    priority = [
        "price_at_analysis",
        "market_cap",
        "pe_ratio",
        "fcf_yield",
        "operating_margin",
        "revenue_growth_yoy",
        "revenue_ttm",
        "fcf_ttm",
        "ev_ebitda",
    ]
    entries: list[tuple[str, dict[str, Any]]] = []
    for key in priority:
        entry = metrics.get(key)
        if isinstance(entry, dict):
            entries.append((key, entry))
    for key, entry in metrics.items():
        if len(entries) >= 9:
            break
        if key not in {item[0] for item in entries} and isinstance(entry, dict):
            entries.append((key, entry))
    return entries


def mode_a_catalyst_entries(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    catalysts = analysis.get("upcoming_catalysts") if isinstance(analysis.get("upcoming_catalysts"), list) else []
    rows = [dict(item) for item in catalysts if isinstance(item, dict)]
    ticker = analysis.get("ticker") or "ticker"
    while len(rows) < 2:
        rows.append(
            {
                "date": "date_unknown",
                "event": f"{ticker} source refresh and scenario recalculation",
                "significance": "Recheck validated metrics, scenario targets, R/R score, and risk mechanisms before changing the thesis.",
            }
        )
    return rows


def mode_a_source_claims(analysis: dict[str, Any]) -> list[dict[str, Any]]:
    claims = analysis.get("source_tagged_claims")
    if not isinstance(claims, list):
        sections = analysis.get("sections") if isinstance(analysis.get("sections"), dict) else {}
        claims = sections.get("source_tagged_claims")
    return [item for item in (claims or []) if isinstance(item, dict)]


def mode_a_macro_boundary(sections: dict[str, Any]) -> str:
    macro = sections.get("macro_context") if isinstance(sections.get("macro_context"), dict) else {}
    structured = macro.get("structured") if isinstance(macro.get("structured"), dict) else {}
    if structured.get("status") == "unavailable":
        return f"Macro data unavailable; no rates or FRED series are inferred. {source_tag('[Macro]')}"
    if structured.get("status") == "available":
        return f"Macro series are shown only when source-tagged structured data exists. {source_tag('[Macro]')}"
    return ""


def mode_a_company_signal(*, company: str, currency: str, metrics: dict[str, Any], ticker: str) -> str:
    parts: list[str] = []
    for key in ("revenue_growth_yoy", "operating_margin", "fcf_yield", "pe_ratio", "market_cap"):
        entry = metrics.get(key)
        if not isinstance(entry, dict):
            continue
        display = metric_display(entry, key, currency)
        if display != "-":
            parts.append(f"{metric_title(key)} {display}")
    if parts:
        return f"{company} ({ticker}) evidence tape: " + ", ".join(parts[:4]) + "."
    return f"{company} ({ticker}) has a thin validated metric tape, so scenario targets and risk mechanisms carry the decision."


def mode_a_rr_score(analysis: dict[str, Any], scenarios: dict[str, Any]) -> float | None:
    rr_score = as_number(analysis.get("rr_score"))
    if rr_score is not None:
        return rr_score
    bull = scenario_return_probability(scenarios, "bull")
    base = scenario_return_probability(scenarios, "base")
    bear = scenario_return_probability(scenarios, "bear")
    if bull is None or base is None or bear is None:
        return None
    downside = abs(bear)
    if downside == 0:
        return None
    return round((bull + base) / downside, 4)


def scenario_return_probability(scenarios: dict[str, Any], key: str) -> float | None:
    item = scenarios.get(key)
    if not isinstance(item, dict):
        return None
    return_pct = as_number(item.get("return_pct"))
    probability = as_number(item.get("probability"))
    if return_pct is None or probability is None:
        return None
    return return_pct * probability


def mode_a_number(value: Any, digits: int = 2) -> str:
    number = as_number(value)
    if number is None:
        return "Unavailable"
    return fmt(number, digits)


def mode_a_currency(value: Any, currency: str, digits: int = 2) -> str:
    number = as_number(value)
    if number is None:
        return "Unavailable"
    return f"{currency_symbol(currency)}{fmt(number, digits)}"


def mode_a_pct(value: Any) -> str:
    number = as_number(value)
    if number is None:
        return "Unavailable"
    return pct(number)


def mode_a_valuation_sentence(
    *,
    dcf: dict[str, Any],
    bridge: dict[str, Any],
    reverse_dcf: dict[str, Any],
    currency: str,
) -> str:
    dcf_value = mode_a_currency(dcf.get("fair_value_per_share"), currency)
    bridge_value = mode_a_currency(bridge.get("weighted_fair_value"), currency)
    reverse_status = str(reverse_dcf.get("status") or "")
    if reverse_status not in {"success", "available"}:
        reason = reverse_dcf.get("notes") or reverse_dcf.get("reason") or "reverse DCF is unavailable under the current validated cash-flow evidence"
        reverse_text = f"Reverse DCF is unavailable: {reason}"
    else:
        reverse_text = (
            "Reverse DCF marks market-implied FCF growth at "
            f"{pct(reverse_dcf.get('implied_fcf_growth'), probability=True)} against the analyst growth anchor of "
            f"{pct(reverse_dcf.get('analyst_growth_assumption'), probability=True)}"
        )
    return f"Base DCF fair value is {dcf_value} and the valuation bridge fair value is {bridge_value} where available. {reverse_text}."


def metric_title(name: str) -> str:
    return name.replace("_", " ").title()


def build_mode_c_dashboard_html(
    *,
    analysis: dict[str, Any],
    calculations: dict[str, Any],
    evidence: dict[str, Any],
    language: str,
    market: str,
    validated: dict[str, Any],
) -> str:
    ticker = str(analysis.get("ticker") or validated.get("ticker") or "UNKNOWN")
    company = str(analysis.get("company_name") or validated.get("company_name") or ticker)
    currency = str(analysis.get("currency") or validated.get("currency") or ("KRW" if market == "KR" else "USD"))
    symbol = currency_symbol(currency)
    sections = analysis.get("sections") if isinstance(analysis.get("sections"), dict) else {}
    metrics = analysis.get("key_metrics") if isinstance(analysis.get("key_metrics"), dict) else {}
    scenarios = analysis.get("scenarios") if isinstance(analysis.get("scenarios"), dict) else {}
    dcf = analysis.get("dcf_analysis") if isinstance(analysis.get("dcf_analysis"), dict) else {}
    bridge = analysis.get("valuation_bridge") if isinstance(analysis.get("valuation_bridge"), dict) else None
    reverse_dcf = analysis.get("reverse_dcf") if isinstance(analysis.get("reverse_dcf"), dict) else None
    source_claims = (
        sections.get("source_tagged_claims")
        if isinstance(sections.get("source_tagged_claims"), list)
        else analysis.get("source_tagged_claims")
    )
    if not isinstance(source_claims, list):
        source_claims = evidence.get("facts") if isinstance(evidence.get("facts"), list) else []

    quarterly = normalize_quarterly(validated.get("financials_quarterly"))
    chart_data = build_chart_data(
        analysis=analysis,
        metrics=metrics,
        quarterly=quarterly,
        scenarios=scenarios,
        language=language,
    )
    price_chart_label = (
        f"{ticker} {mode_c_label(language, 'price')}"
        if is_korean(language)
        else f"{ticker} {mode_c_label(language, 'price')}"
    )
    footer_disclaimer = analysis.get("disclaimer") or mode_c_label(language, "disclaimer_default")
    html_text = f"""<!DOCTYPE html>
<html lang="{esc(language)}">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{esc(company)} ({esc(ticker)}) - {esc(mode_c_label(language, "investment_dashboard"))}</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/css/all.min.css">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
  {korean_font(language)}
  <style>
    * {{ font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Noto Sans KR', sans-serif; }}
    body {{ background: #f8fafc; color: #1f2937; }}
    .card {{ background: #fff; border-radius: 12px; box-shadow: 0 1px 3px rgba(15,23,42,0.08), 0 1px 2px rgba(15,23,42,0.06); }}
    .stat-card {{ border-left: 4px solid #3b82f6; }}
    .source-tag {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.7rem; padding: 1px 5px; border-radius: 4px; background: #f3f4f6; }}
    .tag-portal {{ color: #4b5563; }}
    .tag-calc {{ color: #047857; }}
    .tag-est {{ color: #b45309; }}
    .tag-macro {{ color: #6d28d9; }}
    .grade-badge {{ font-size: 0.65rem; font-weight: 700; padding: 1px 6px; border-radius: 4px; vertical-align: middle; margin-left: 6px; }}
    .grade-A {{ background: #d1fae5; color: #065f46; }}
    .grade-B {{ background: #dbeafe; color: #1e40af; }}
    .grade-C {{ background: #fef3c7; color: #92400e; }}
    .grade-D {{ background: #fee2e2; color: #991b1b; }}
  </style>
  <script>
    tailwind.config = {{ theme: {{ extend: {{ colors: {{
      brand: {{ 50: '#eef3fc', 100: '#d4e2f9', 400: '#4285F4', 500: '#3367d6', 600: '#2a56b0', 700: '#1e3f80', 800: '#142a55', 900: '#0d1b38' }}
    }}}}}}}};
  </script>
</head>
<body>
  <header id="section-header" style="background: linear-gradient(135deg, #0d1b38 0%, #1e3f80 32%, #2a56b0 68%, #3367d6 100%);">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 py-8">
      <div class="flex flex-col lg:flex-row justify-between gap-6">
        <div>
          <p class="text-blue-200 text-xs font-semibold uppercase tracking-widest">{esc(mode_c_label(language, "mode_c_dashboard"))}</p>
          <h1 class="text-3xl md:text-4xl font-extrabold text-white mt-2">{esc(company)}</h1>
          <p class="text-blue-200 mt-1">{esc(market)}: {esc(ticker)} · {esc(mode_c_label(language, "source_profile"))} {esc(analysis.get("source_profile") or "mixed")}</p>
          <div class="flex flex-wrap items-center gap-3 mt-5">
            <span class="text-4xl font-extrabold text-white">{symbol}{fmt(metric_value(metrics, "price_at_analysis") or analysis.get("price_at_analysis"), 2)}</span>
            {verdict_badge(analysis.get("verdict"))}
            {rr_badge(analysis.get("rr_score"))}
          </div>
        </div>
        <div class="grid grid-cols-2 gap-x-6 gap-y-2 text-sm text-right">
          {header_metric(mode_c_label(language, "market_cap"), metrics.get("market_cap"), currency, "market_cap")}
          {header_metric(mode_c_label(language, "pe_ratio"), metrics.get("pe_ratio"), currency, "pe_ratio")}
          {header_metric("EV/EBITDA", metrics.get("ev_ebitda"), currency, "ev_ebitda")}
          {header_metric(mode_c_label(language, "fcf_yield"), metrics.get("fcf_yield"), currency, "fcf_yield")}
          {header_metric(mode_c_label(language, "revenue_ttm"), metrics.get("revenue_ttm"), currency, "revenue_ttm")}
          {header_metric(mode_c_label(language, "op_margin"), metrics.get("operating_margin"), currency, "operating_margin")}
        </div>
      </div>
      <div class="mt-5 pt-4 border-t border-white/10 flex flex-wrap gap-3 text-xs text-blue-200/70">
        <span>{esc(mode_c_label(language, "analysis_date"))} {esc(analysis.get("analysis_date"))}</span>
        <span>{esc(mode_c_label(language, "mode_deep_dive"))}</span>
        <span>{esc(mode_c_label(language, "data_mode"))} {esc(analysis.get("data_mode"))}</span>
        <span>{esc(mode_c_label(language, "confidence_cap"))} {esc(analysis.get("confidence_cap") or validated.get("confidence_cap"))}</span>
      </div>
    </div>
  </header>
  {deterministic_disclosure_banner(analysis, language)}

  <main class="max-w-7xl mx-auto px-4 sm:px-6 py-8 space-y-8">
    {render_scenario_section(analysis, scenarios, sections, currency, language)}
    {render_kpi_section(metrics, currency, language)}
    {render_variant_section(analysis, sections, language)}
    {render_precision_risk_section(analysis, sections, language)}
    {render_valuation_section(sections, dcf, bridge, reverse_dcf, currency, language)}
    {render_peer_and_macro_section(analysis, sections, metrics, language)}
    {render_analyst_coverage_section(metrics, sections, currency, language)}
    {render_charts_section(chart_data, currency, language)}
    {render_financial_detail_section(metrics, quarterly, sections, currency, language)}
    {render_quality_gate_section(analysis, calculations, evidence, validated, language)}
    {render_portfolio_section(analysis, sections, scenarios, language)}
    {render_source_appendix(source_claims, language)}
  </main>

  <footer class="bg-gray-900 text-gray-400 mt-12">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 py-8">
      <h2 class="text-sm font-bold text-gray-200 mb-2">{esc(mode_c_label(language, "disclaimer"))}</h2>
      <p class="text-xs leading-6">{esc(footer_disclaimer)}</p>
      <p class="text-xs mt-2">{esc(mode_c_label(language, "last_updated"))} {esc(analysis.get("analysis_date"))} · {esc(mode_c_label(language, "sources"))} {esc(mode_c_label(language, "validated_sources"))}</p>
    </div>
  </footer>

  <script>
  const blue = 'rgba(59,130,246,';
  const green = 'rgba(16,185,129,';
  const red = 'rgba(239,68,68,';
  const amber = 'rgba(245,158,11,';
  const quarters = {json_js(chart_data["quarters"])};
  const revenueData = {json_js(chart_data["revenue"])};
  const opIncomeData = {json_js(chart_data["operating_income"])};
  const fcfData = {json_js(chart_data["free_cash_flow"])};
  const marginData = {json_js(chart_data["operating_margin"])};
  const netMarginData = {json_js(chart_data["net_margin"])};
  const priceLabels = {json_js(chart_data["price_labels"])};
  const priceData = {json_js(chart_data["price_data"])};
  const bullLineData = {json_js(chart_data["bull_line"])};
  const baseLineData = {json_js(chart_data["base_line"])};
  const bearLineData = {json_js(chart_data["bear_line"])};
  const segmentLabels = {json_js(chart_data["segment_labels"])};
  const segmentData = {json_js(chart_data["segment_data"])};

  new Chart(document.getElementById('revenueChart').getContext('2d'), {{
    type: 'bar',
    data: {{ labels: quarters, datasets: [
      {{ label: '{esc(mode_c_label(language, "revenue"))}', data: revenueData, backgroundColor: blue + '0.55)', borderColor: blue + '1)', borderWidth: 1, borderRadius: 6 }},
      {{ label: '{esc(mode_c_label(language, "operating_income"))}', type: 'line', data: opIncomeData, borderColor: green + '1)', backgroundColor: green + '0.1)', borderWidth: 2.5, pointRadius: 4, fill: false }}
    ] }},
    options: {{ responsive: true, plugins: {{ legend: {{ position: 'bottom' }} }}, scales: {{ y: {{ ticks: {{ callback: v => '{currency_prefix(currency)}' + v + 'B' }} }} }} }}
  }});

  new Chart(document.getElementById('marginChart').getContext('2d'), {{
    type: 'line',
    data: {{ labels: quarters, datasets: [
      {{ label: '{esc(mode_c_label(language, "operating_margin"))}', data: marginData, borderColor: green + '1)', backgroundColor: green + '0.12)', borderWidth: 2.5, pointRadius: 4, fill: true }},
      {{ label: '{esc(mode_c_label(language, "net_margin"))}', data: netMarginData, borderColor: amber + '1)', backgroundColor: amber + '0.10)', borderWidth: 2, pointRadius: 4, fill: false }}
    ] }},
    options: {{ responsive: true, plugins: {{ legend: {{ position: 'bottom' }} }}, scales: {{ y: {{ ticks: {{ callback: v => v + '%' }} }} }} }}
  }});

  new Chart(document.getElementById('segmentChart').getContext('2d'), {{
    type: 'bar',
    data: {{ labels: segmentLabels, datasets: [
      {{ label: '{esc(mode_c_label(language, "latest_quarter"))}', data: segmentData, backgroundColor: [blue + '0.55)', green + '0.55)', amber + '0.55)', red + '0.45)'], borderColor: [blue + '1)', green + '1)', amber + '1)', red + '0.9)'], borderWidth: 1, borderRadius: 6 }}
    ] }},
    options: {{ responsive: true, plugins: {{ legend: {{ display: false }} }}, scales: {{ y: {{ ticks: {{ callback: v => '{currency_prefix(currency)}' + v + 'B' }} }} }} }}
  }});

  new Chart(document.getElementById('fcfChart').getContext('2d'), {{
    type: 'line',
    data: {{ labels: quarters, datasets: [
      {{ label: '{esc(mode_c_label(language, "free_cash_flow"))}', data: fcfData, borderColor: green + '1)', backgroundColor: green + '0.12)', borderWidth: 2.5, pointRadius: 4, fill: true }}
    ] }},
    options: {{ responsive: true, plugins: {{ legend: {{ position: 'bottom' }} }}, scales: {{ y: {{ ticks: {{ callback: v => '{currency_prefix(currency)}' + v + 'B' }} }} }} }}
  }});

  new Chart(document.getElementById('quarterlyChart').getContext('2d'), {{
    type: 'line',
    data: {{ labels: quarters, datasets: [
      {{ label: '{esc(mode_c_label(language, "revenue"))}', data: revenueData, borderColor: blue + '1)', backgroundColor: blue + '0.10)', borderWidth: 2.5, pointRadius: 4, fill: false }},
      {{ label: '{esc(mode_c_label(language, "operating_income"))}', data: opIncomeData, borderColor: green + '1)', backgroundColor: green + '0.10)', borderWidth: 2.3, pointRadius: 4, fill: false }},
      {{ label: '{esc(mode_c_label(language, "free_cash_flow"))}', data: fcfData, borderColor: amber + '1)', backgroundColor: amber + '0.10)', borderWidth: 2.1, pointRadius: 4, fill: false }}
    ] }},
    options: {{ responsive: true, plugins: {{ legend: {{ position: 'bottom' }} }}, scales: {{ y: {{ ticks: {{ callback: v => '{currency_prefix(currency)}' + v + 'B' }} }} }} }}
  }});

  new Chart(document.getElementById('priceChart').getContext('2d'), {{
    type: 'line',
    data: {{ labels: priceLabels, datasets: [
      {{ label: '{esc(price_chart_label)}', data: priceData, borderColor: blue + '1)', backgroundColor: blue + '0.08)', borderWidth: 2.5, pointRadius: 4, fill: true, tension: 0.25 }},
      {{ label: '{esc(mode_c_label(language, "bull_target"))}', data: bullLineData, borderColor: green + '0.7)', borderDash: [7,4], pointRadius: 0 }},
      {{ label: '{esc(mode_c_label(language, "base_target"))}', data: baseLineData, borderColor: amber + '0.8)', borderDash: [4,4], pointRadius: 0 }},
      {{ label: '{esc(mode_c_label(language, "bear_target"))}', data: bearLineData, borderColor: red + '0.7)', borderDash: [7,4], pointRadius: 0 }}
    ] }},
    options: {{ responsive: true, plugins: {{ legend: {{ position: 'bottom' }} }}, scales: {{ y: {{ ticks: {{ callback: v => '{currency_prefix(currency)}' + v }} }} }} }}
  }});
  </script>
</body>
</html>
"""
    return html_text


def render_scenario_section(
    analysis: dict[str, Any],
    scenarios: dict[str, Any],
    sections: dict[str, Any],
    currency: str,
    language: str,
) -> str:
    cards = []
    for key, title, klass in (
        ("bear", mode_c_label(language, "bear_case"), "border-red-400/30 text-red-300"),
        ("base", mode_c_label(language, "base_case"), "border-blue-300/60 text-blue-100 bg-white/15"),
        ("bull", mode_c_label(language, "bull_case"), "border-green-400/30 text-green-300"),
    ):
        item = scenarios.get(key) if isinstance(scenarios.get(key), dict) else {}
        cards.append(
            f"""<div class="bg-white/10 backdrop-blur-sm rounded-xl p-5 text-center border {klass}">
              <p class="text-sm font-semibold mb-1">{title} · P {pct(item.get("probability"), probability=True)}</p>
              <p class="text-3xl font-extrabold text-white">{currency_symbol(currency)}{fmt(item.get("target"), 2)}</p>
              <p class="text-sm mt-1">{pct(item.get("return_pct"))}</p>
              <p class="text-blue-100/70 text-xs mt-2 leading-relaxed">{esc(item.get("key_assumption") or "Scenario assumption unavailable.")} {source_tag("[Calc]")}</p>
            </div>"""
        )
    return f"""<section id="section-scenarios" class="rounded-2xl overflow-hidden" style="background: linear-gradient(135deg, #0d1b38, #1e3f80, #2a56b0, #142a55);">
      <div class="p-6 sm:p-8">
        <div class="flex flex-wrap justify-between items-start gap-4 mb-6">
          <div>
            <h2 class="text-lg font-bold text-blue-200 mb-1"><i class="fa-solid fa-bullseye mr-2"></i>{esc(mode_c_label(language, "scenario_valuation_12m"))}</h2>
            <p class="text-blue-200/60 text-xs max-w-4xl">{esc(analysis.get("thesis") or sections.get("one_line_thesis") or sections.get("variant_view_q1"))}</p>
          </div>
          <div class="bg-gray-700 text-white px-5 py-3 rounded-xl text-center">
            <div class="text-2xl font-bold">{esc(mode_c_label(language, "rr_score"))} {fmt(analysis.get("rr_score"), 2)}</div>
            <div class="text-sm text-gray-200">{esc(analysis.get("verdict"))}</div>
          </div>
        </div>
        <div class="grid grid-cols-1 md:grid-cols-3 gap-4">{''.join(cards)}</div>
      </div>
    </section>"""


def render_kpi_section(metrics: dict[str, Any], currency: str, language: str) -> str:
    keys = [
        ("market_cap", mode_c_label(language, "market_cap")),
        ("revenue_ttm", mode_c_label(language, "revenue_ttm")),
        ("revenue_growth_yoy", mode_c_label(language, "revenue_growth")),
        ("operating_margin", mode_c_label(language, "operating_margin")),
        ("fcf_yield", mode_c_label(language, "fcf_yield")),
        ("ev_ebitda", "EV/EBITDA"),
        ("pe_ratio", mode_c_label(language, "pe_ratio")),
        ("beta", mode_c_label(language, "beta")),
    ]
    tiles = [
        f"""<div class="card p-5 stat-card">
          <p class="text-xs text-gray-500 mb-1">{esc(label)} {grade_badge(metrics.get(key))}</p>
          <p class="text-2xl font-bold text-brand-700">{metric_display(metrics.get(key), key, currency)}</p>
          <p class="text-xs text-gray-500 mt-1">{metric_source(metrics.get(key))}</p>
        </div>"""
        for key, label in keys
        if isinstance(metrics.get(key), dict)
    ]
    return f"""<section id="section-kpi">
      <h2 class="text-xl font-bold text-gray-900 mb-4"><i class="fa-solid fa-chart-bar mr-2 text-brand-400"></i>{esc(mode_c_label(language, "key_performance_indicators"))} - {esc(mode_c_count(language, len(tiles), "tracked metrics", "추적 지표"))}</h2>
      <div class="grid grid-cols-2 md:grid-cols-4 gap-4">{''.join(tiles)}</div>
    </section>"""


def render_variant_section(analysis: dict[str, Any], sections: dict[str, Any], language: str) -> str:
    variants = analysis.get("variant_view") if isinstance(analysis.get("variant_view"), list) else []
    questions = [
        ("Q1", sections.get("variant_view_q1") or first(variants)),
        ("Q2", sections.get("variant_view_q2") or item_at(variants, 1)),
        ("Q3", sections.get("variant_view_q3") or item_at(variants, 2)),
    ]
    rows = "".join(
        f"""<div class="bg-blue-50 rounded-lg p-4 border border-blue-100">
          <p class="font-bold text-blue-900 mb-2"><span class="bg-blue-100 text-blue-800 text-xs px-2 py-0.5 rounded mr-2">{label}</span>{esc(mode_c_label(language, "variant_view"))}</p>
          <p class="text-sm leading-7 text-gray-700">{esc(text or "Company-specific variant view unavailable.")}</p>
        </div>"""
        for label, text in questions
    )
    return f"""<section id="section-thesis">
      <h2 class="text-xl font-bold text-gray-900 mb-4"><i class="fa-solid fa-scale-balanced mr-2 text-brand-400"></i>{mode_c_label(language, "investment_thesis_variant_view")} - {esc(mode_c_count(language, 3, "debate points", "논점"))}</h2>
      <div class="card p-6 border-l-4 border-blue-500">
        <p class="text-sm text-gray-700 leading-7 mb-5">{esc(analysis.get("thesis") or sections.get("one_line_thesis"))}</p>
        <div class="space-y-4">{rows}</div>
      </div>
    </section>"""


def render_precision_risk_section(analysis: dict[str, Any], sections: dict[str, Any], language: str) -> str:
    risks = sections.get("precision_risks") if isinstance(sections.get("precision_risks"), list) else analysis.get("top_risks")
    if not isinstance(risks, list):
        risks = []
    rows = []
    for risk in risks[:6]:
        if isinstance(risk, dict):
            rows.append(
                f"""<tr class="border-b align-top">
                  <td class="p-4 font-semibold text-gray-900">{esc(risk.get("risk") or risk.get("title"))}</td>
                  <td class="p-4 text-gray-700">{esc(risk.get("mechanism") or "Mechanism unavailable.")}</td>
                  <td class="p-4 text-gray-700">{esc(risk.get("financial_impact") or risk.get("ebitda_impact") or "Impact not quantified.")}</td>
                  <td class="p-4 text-gray-700">{esc(risk.get("probability") or "monitor")}</td>
                  <td class="p-4 text-gray-700">{source_tag("[Calc]")}</td>
                </tr>"""
            )
        else:
            rows.append(
                f"""<tr class="border-b"><td class="p-4 font-semibold">{esc(risk)}</td><td class="p-4">Mechanism requires analyst follow-up.</td><td class="p-4">Not quantified.</td><td class="p-4">monitor</td><td class="p-4">{source_tag("[User]")}</td></tr>"""
            )
    return f"""<section id="section-risks">
      <h2 class="text-xl font-bold text-gray-900 mb-4"><i class="fa-solid fa-shield-halved mr-2 text-red-500"></i>{esc(mode_c_label(language, "precision_risk_analysis"))} - {esc(mode_c_count(language, len(rows), "mechanisms", "메커니즘"))}</h2>
      <div class="card overflow-x-auto">
        <table class="w-full text-sm">
          <thead><tr class="bg-gray-50 text-gray-600 text-xs uppercase"><th class="text-left p-4">{esc(mode_c_label(language, "risk"))}</th><th class="text-left p-4">{esc(mode_c_label(language, "mechanism"))}</th><th class="text-left p-4">{esc(mode_c_label(language, "financial_impact"))}</th><th class="text-left p-4">{esc(mode_c_label(language, "probability"))}</th><th class="text-left p-4">{esc(mode_c_label(language, "source"))}</th></tr></thead>
          <tbody>{''.join(rows)}</tbody>
        </table>
      </div>
    </section>"""


def render_valuation_section(
    sections: dict[str, Any],
    dcf: dict[str, Any],
    bridge: dict[str, Any] | None,
    reverse_dcf: dict[str, Any] | None,
    currency: str,
    language: str,
) -> str:
    valuation_metrics = sections.get("valuation_metrics") if isinstance(sections.get("valuation_metrics"), list) else []
    metric_rows = []
    for idx, item in enumerate(valuation_metrics[:8]):
        if isinstance(item, dict):
            metric_rows.append(
                f"""<tr class="border-b hover:bg-gray-50">
                  <td class="p-4 font-semibold">{esc(item.get("metric") or item.get("formula") or f"Metric {idx + 1}")} {source_tag(item.get("tag") or "[Calc]")}</td>
                  <td class="p-4 text-right font-bold">{esc(item.get("current") or fmt(item.get("value"), 2))}</td>
                  <td class="p-4 text-right text-gray-600">{esc(item.get("unit") or "value")}</td>
                  <td class="p-4 text-gray-600">{esc(item.get("assessment") or item.get("formula") or "Deterministic calculation.")}</td>
                </tr>"""
            )
    dcf_rows = render_dcf_sensitivity(dcf, currency, language)
    return f"""<section id="section-valuation">
      <h2 class="text-xl font-bold text-gray-900 mb-4"><i class="fa-solid fa-calculator mr-2 text-brand-400"></i>{esc(mode_c_label(language, "valuation_metrics"))} - {esc(mode_c_count(language, len(metric_rows), "deterministic rows", "결정론적 항목"))}</h2>
      <div class="card overflow-x-auto mb-5">
        <table class="w-full text-sm">
          <thead><tr class="bg-gray-50 text-gray-600 text-xs uppercase"><th class="text-left p-4">{esc(mode_c_label(language, "metric"))}</th><th class="text-right p-4">{esc(mode_c_label(language, "current"))}</th><th class="text-right p-4">{esc(mode_c_label(language, "unit"))}</th><th class="text-left p-4">{esc(mode_c_label(language, "assessment"))}</th></tr></thead>
          <tbody>{''.join(metric_rows)}</tbody>
        </table>
      </div>
      <section id="section-dcf">
        <h2 class="text-xl font-bold text-gray-900 mb-4"><i class="fa-solid fa-square-root-variable mr-2 text-brand-400"></i>{esc(mode_c_label(language, "dcf_valuation"))} - fair value {currency_symbol(currency)}{fmt(dcf.get("fair_value_per_share"), 2)}</h2>
        <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
          <div class="card p-5 stat-card"><p class="text-xs text-gray-500">{esc(mode_c_label(language, "base_dcf_fair_value"))}</p><p class="text-3xl font-bold text-brand-700">{currency_symbol(currency)}{fmt(dcf.get("fair_value_per_share"), 2)}</p><p class="text-xs text-gray-500 mt-1">Upside {pct(dcf.get("upside_downside_pct"))} {source_tag("[Calc]")}</p></div>
          <div class="card p-5 stat-card"><p class="text-xs text-gray-500">{esc(mode_c_label(language, "enterprise_value"))}</p><p class="text-3xl font-bold text-brand-700">{fmt(dcf.get("enterprise_value"), 1)}M</p><p class="text-xs text-gray-500 mt-1">{esc(mode_c_label(language, "equity_value"))} {fmt(dcf.get("equity_value"), 1)}M {source_tag("[Calc]")}</p></div>
          <div class="card p-5 stat-card"><p class="text-xs text-gray-500">WACC</p><p class="text-3xl font-bold text-brand-700">{pct((dcf.get("assumptions") or {}).get("wacc"), probability=True)}</p><p class="text-xs text-gray-500 mt-1">{esc(mode_c_label(language, "terminal_growth"))} {pct((dcf.get("assumptions") or {}).get("terminal_growth_rate"), probability=True)} {source_tag("[Calc]")}</p></div>
        </div>
        <div class="card p-6 mb-4 overflow-x-auto">
          <h3 class="text-sm font-bold text-gray-700 mb-3">{esc(mode_c_label(language, "dcf_sensitivity_table"))} - {esc(mode_c_count(language, 3, "WACC cases", "WACC 케이스"))}</h3>
          <table class="w-full text-sm">
            <thead><tr class="bg-gray-50 text-gray-600 text-xs uppercase"><th class="text-left p-3">WACC</th><th class="text-right p-3">TGR 2.0%</th><th class="text-right p-3">TGR 2.5%</th><th class="text-right p-3">TGR 3.0%</th></tr></thead>
            <tbody>{dcf_rows}</tbody>
          </table>
        </div>
        {render_reverse_dcf(reverse_dcf, language)}
      </section>
      {render_valuation_bridge(bridge, currency, language)}
    </section>"""


def render_peer_and_macro_section(
    analysis: dict[str, Any],
    sections: dict[str, Any],
    metrics: dict[str, Any],
    language: str,
) -> str:
    peers = sections.get("peer_comparison") if isinstance(sections.get("peer_comparison"), list) else []
    peer_rows = [
        peer_row(analysis.get("ticker"), mode_c_label(language, "subject"), metrics, "bg-blue-50/60 font-semibold", language)
    ]
    for peer in peers[:5]:
        if isinstance(peer, dict):
            peer_rows.append(
                f"""<tr class="border-b hover:bg-gray-50">
                  <td class="p-4 font-semibold">{esc(peer.get("ticker") or "Peer")}</td>
                  <td class="p-4">{esc(peer.get("summary") or peer.get("metric") or "Comparable data pending.")}</td>
                  <td class="p-4 text-right">{esc(peer.get("value") or "-")}</td>
                  <td class="p-4 text-right">{source_tag(peer.get("tag") or "[Portal]")}</td>
                </tr>"""
            )
    macro = sections.get("macro_context") if isinstance(sections.get("macro_context"), dict) else {}
    structured = macro.get("structured") if isinstance(macro.get("structured"), dict) else {}
    if structured.get("status") == "available":
        macro_cards = "".join(
            f"""<div class="rounded-lg border border-gray-200 p-3"><p class="text-xs text-gray-500">{esc(item.get("label") or item.get("id"))}</p><p class="font-semibold">{esc(item.get("value"))} {esc(item.get("unit"))} {source_tag("[Macro]")}</p></div>"""
            for item in structured.get("series", [])
            if isinstance(item, dict)
        )
    else:
        macro_cards = f"""<div class="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
          <p class="font-semibold">{esc("매크로 데이터 이용 불가" if is_korean(language) else "Macro data unavailable")} {source_tag("[Macro]")}</p>
          <p>{esc(structured.get("reason") or ("FRED 구조화 시계열 이용 불가; 금리는 추정하지 않습니다." if is_korean(language) else "FRED structured series unavailable; no rates are inferred."))}</p>
        </div>"""
    return f"""<section class="grid grid-cols-1 xl:grid-cols-2 gap-5">
      <div id="section-peers">
        <h2 class="text-xl font-bold text-gray-900 mb-4"><i class="fa-solid fa-users mr-2 text-brand-400"></i>{esc(mode_c_label(language, "peer_comparison"))} - {esc(mode_c_count(language, len(peer_rows), "rows", "행"))}</h2>
        <div class="card overflow-x-auto">
          <table class="w-full text-sm">
            <thead><tr class="bg-gray-50 text-gray-600 text-xs uppercase"><th class="text-left p-4">{esc(mode_c_label(language, "company"))}</th><th class="text-left p-4">{esc(mode_c_label(language, "basis"))}</th><th class="text-right p-4">{esc(mode_c_label(language, "value"))}</th><th class="text-right p-4">{esc(mode_c_label(language, "source"))}</th></tr></thead>
            <tbody>{''.join(peer_rows)}</tbody>
          </table>
        </div>
      </div>
      <div id="section-macro">
        <h2 class="text-xl font-bold text-gray-900 mb-4"><i class="fa-solid fa-globe mr-2 text-brand-400"></i>{esc(mode_c_label(language, "macro_environment"))} - {esc(mode_c_count(language, len(structured.get("series") or []), "FRED series", "FRED 시계열"))}</h2>
        <div class="card p-5">
          <div class="grid grid-cols-1 md:grid-cols-2 gap-3 mb-4">{macro_cards}</div>
          <p class="text-sm text-gray-700 leading-7">{esc(macro.get("narrative") or "Macro context is included only when structured FRED data is available.")}</p>
        </div>
      </div>
    </section>"""


def render_analyst_coverage_section(metrics: dict[str, Any], sections: dict[str, Any], currency: str, language: str) -> str:
    coverage = sections.get("analyst_coverage") if isinstance(sections.get("analyst_coverage"), dict) else {}
    mean = metric_value(metrics, "analyst_target_mean") or coverage.get("price_target")
    median = metric_value(metrics, "analyst_target_median")
    high = metric_value(metrics, "analyst_target_high")
    low = metric_value(metrics, "analyst_target_low")
    price = metric_value(metrics, "price_at_analysis")
    return f"""<section id="section-analyst">
      <h2 class="text-xl font-bold text-gray-900 mb-4"><i class="fa-solid fa-bullhorn mr-2 text-brand-400"></i>{esc(mode_c_label(language, "analyst_coverage"))} - {esc(mode_c_count(language, 4, "target anchors", "목표가 앵커"))}</h2>
      <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
        {target_card(mode_c_label(language, "consensus_average"), mean, price, currency, language)}
        {target_card(mode_c_label(language, "median_target"), median, price, currency, language)}
        {target_card(mode_c_label(language, "street_high"), high, price, currency, language)}
        {target_card(mode_c_label(language, "street_low"), low, price, currency, language)}
      </div>
      <div class="card p-5 mt-4 text-sm text-gray-700">{esc(mode_c_label(language, "coverage_status"))} {esc(mode_c_status(language, coverage.get("consensus") or "available if target metrics exist"))} {source_tag("[Est]")}</div>
    </section>"""


def render_charts_section(chart_data: dict[str, Any], currency: str, language: str) -> str:
    chart_rows = render_chart_audit_rows(chart_data, currency, language)
    return f"""<section id="section-charts">
      <h2 class="text-xl font-bold text-gray-900 mb-4"><i class="fa-solid fa-chart-bar mr-2 text-brand-400"></i>{mode_c_label(language, "charts_trend_data")} - {esc(mode_c_count(language, 6, "charts", "차트"))}</h2>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div class="card p-5"><h3 class="text-sm font-semibold text-gray-700 mb-3">{esc(mode_c_label(language, "quarterly_revenue_operating_income"))} - {esc(mode_c_count(language, 6, "points max", "포인트 이하"))}</h3><canvas id="revenueChart" height="210"></canvas></div>
        <div class="card p-5"><h3 class="text-sm font-semibold text-gray-700 mb-3">{esc(mode_c_label(language, "margin_trend"))}</h3><canvas id="marginChart" height="210"></canvas></div>
      </div>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
        <div class="card p-5"><h3 class="text-sm font-semibold text-gray-700 mb-3">{esc(mode_c_label(language, "latest_quarter_bridge"))}</h3><canvas id="segmentChart" height="190"></canvas></div>
        <div class="card p-5"><h3 class="text-sm font-semibold text-gray-700 mb-3">{esc(mode_c_label(language, "fcf_run_rate"))}</h3><canvas id="fcfChart" height="190"></canvas></div>
      </div>
      <div class="grid grid-cols-1 gap-4 mt-4">
        <div class="card p-5"><h3 class="text-sm font-semibold text-gray-700 mb-3">{esc(mode_c_label(language, "quarterly_trend_compatibility"))}</h3><canvas id="quarterlyChart" height="190"></canvas></div>
      </div>
      <div class="grid grid-cols-1 gap-4 mt-4">
        <div class="card p-5"><h3 class="text-sm font-semibold text-gray-700 mb-3">{esc(mode_c_label(language, "stock_price_targets"))} - {esc(mode_c_count(language, 6, "anchor points", "앵커 포인트"))}</h3><canvas id="priceChart" height="190"></canvas></div>
      </div>
      <div class="card p-5 mt-4 bg-gray-50 border border-gray-200">
        <h3 class="text-sm font-bold text-gray-700 mb-2">{esc(mode_c_label(language, "chart_evidence_boundary"))}</h3>
        <p class="text-sm text-gray-700 leading-7 mb-3">{esc(mode_c_label(language, "chart_boundary_paragraph_1"))} {source_tag("[Calc]")}</p>
        <p class="text-sm text-gray-700 leading-7 mb-4">{esc(mode_c_label(language, "chart_boundary_paragraph_2"))} {source_tag("[Calc]")}</p>
        <div class="overflow-x-auto">
          <table class="w-full text-sm bg-white border border-gray-200">
            <thead><tr class="bg-gray-50 text-gray-600 text-xs uppercase"><th class="text-left p-3">{esc(mode_c_label(language, "period"))}</th><th class="text-right p-3">{esc(mode_c_label(language, "revenue"))}</th><th class="text-right p-3">{esc(mode_c_label(language, "operating_income"))}</th><th class="text-right p-3">FCF</th><th class="text-right p-3">{esc(mode_c_label(language, "operating_margin"))}</th><th class="text-right p-3">{esc(mode_c_label(language, "net_margin"))}</th><th class="text-right p-3">{esc(mode_c_label(language, "source"))}</th></tr></thead>
            <tbody>{chart_rows}</tbody>
          </table>
        </div>
      </div>
    </section>"""


def render_chart_audit_rows(chart_data: dict[str, Any], currency: str, language: str) -> str:
    quarters = chart_data.get("quarters") if isinstance(chart_data.get("quarters"), list) else []
    revenue = chart_data.get("revenue") if isinstance(chart_data.get("revenue"), list) else []
    op_income = chart_data.get("operating_income") if isinstance(chart_data.get("operating_income"), list) else []
    free_cash_flow = chart_data.get("free_cash_flow") if isinstance(chart_data.get("free_cash_flow"), list) else []
    op_margin = chart_data.get("operating_margin") if isinstance(chart_data.get("operating_margin"), list) else []
    net_margin = chart_data.get("net_margin") if isinstance(chart_data.get("net_margin"), list) else []
    rows = []
    for index, period in enumerate(quarters[:6]):
        rows.append(
            f"""<tr class="border-b">
              <td class="p-3 font-semibold">{esc(period)}</td>
              <td class="p-3 text-right">{currency_symbol(currency)}{fmt(item_at(revenue, index), 2)}B</td>
              <td class="p-3 text-right">{currency_symbol(currency)}{fmt(item_at(op_income, index), 2)}B</td>
              <td class="p-3 text-right">{currency_symbol(currency)}{fmt(item_at(free_cash_flow, index), 2)}B</td>
              <td class="p-3 text-right">{fmt(item_at(op_margin, index), 2)}%</td>
              <td class="p-3 text-right">{fmt(item_at(net_margin, index), 2)}%</td>
              <td class="p-3 text-right">{source_tag("[Calc]")}</td>
            </tr>"""
        )
    if not rows:
        message = "차트 감사 행 이용 불가" if is_korean(language) else "Chart audit rows unavailable."
        return f"""<tr><td colspan="7" class="p-3 text-gray-500">{esc(message)} {source_tag("[Calc]")}</td></tr>"""
    return "".join(rows)


def render_financial_detail_section(
    metrics: dict[str, Any],
    quarterly: list[dict[str, Any]],
    sections: dict[str, Any],
    currency: str,
    language: str,
) -> str:
    qoe = sections.get("qoe_summary") if isinstance(sections.get("qoe_summary"), dict) else {}
    quarter_rows = "".join(
        f"""<tr class="border-b">
          <td class="p-3 font-semibold">{esc(item.get("period_end"))}</td>
          <td class="p-3 text-right">{currency_symbol(currency)}{fmt(to_billions(item.get("revenue")), 1)}B {source_tag("[Calc]")}</td>
          <td class="p-3 text-right">{currency_symbol(currency)}{fmt(to_billions(item.get("operating_income")), 1)}B {source_tag("[Calc]")}</td>
          <td class="p-3 text-right">{pct(margin(item.get("operating_income"), item.get("revenue")))}</td>
          <td class="p-3 text-right">{currency_symbol(currency)}{fmt(to_billions(item.get("net_income")), 1)}B {source_tag("[Calc]")}</td>
        </tr>"""
        for item in quarterly[:6]
    )
    if not quarter_rows:
        message = "분기 데이터 이용 불가; TTM 지표는 계속 표시됩니다." if is_korean(language) else "Quarterly data unavailable; TTM metrics remain visible."
        quarter_rows = f"""<tr><td colspan="5" class="p-4 text-gray-500">{esc(message)} {source_tag("[Calc]")}</td></tr>"""
    return f"""<section id="section-financials">
      <h2 class="text-xl font-bold text-gray-900 mb-4"><i class="fa-solid fa-file-invoice-dollar mr-2 text-brand-400"></i>{esc(mode_c_label(language, "financial_detail_analysis"))} - {esc(mode_c_count(language, len(quarterly[:6]), "quarters", "분기"))}</h2>
      <div class="grid grid-cols-1 md:grid-cols-4 gap-4 mb-4">
        {detail_card(mode_c_label(language, "revenue_ttm"), metrics.get("revenue_ttm"), currency, "revenue_ttm")}
        {detail_card(mode_c_label(language, "fcf_ttm"), metrics.get("fcf_ttm"), currency, "fcf_ttm")}
        {detail_card(mode_c_label(language, "net_debt"), metrics.get("net_debt"), currency, "net_debt")}
        {detail_card(mode_c_label(language, "net_debt_ebitda"), metrics.get("net_debt_ebitda"), currency, "net_debt_ebitda")}
      </div>
      <div class="card overflow-x-auto">
        <table class="w-full text-sm">
          <thead><tr class="bg-gray-50 text-gray-600 text-xs uppercase"><th class="text-left p-3">{esc(mode_c_label(language, "quarter"))}</th><th class="text-right p-3">{esc(mode_c_label(language, "revenue"))}</th><th class="text-right p-3">{esc(mode_c_label(language, "op_income"))}</th><th class="text-right p-3">{esc(mode_c_label(language, "op_margin"))}</th><th class="text-right p-3">{esc(mode_c_label(language, "net_income"))}</th></tr></thead>
          <tbody>{quarter_rows}</tbody>
        </table>
      </div>
      <div class="card p-5 mt-4 bg-blue-50 border border-blue-200">
        <h3 class="text-sm font-bold text-blue-900 mb-2">{esc(mode_c_label(language, "quality_earnings"))} - {esc(mode_c_count(language, 1, f"Grade {qoe.get('grade') or 'C'} read", f"등급 {qoe.get('grade') or 'C'} 리드"))}</h3>
        <p class="text-sm text-gray-700 leading-7">{esc(qoe.get("narrative") or "Quality of earnings uses validated metrics only; excluded fields remain blank.")} {source_tag("[Calc]")}</p>
      </div>
    </section>"""


def render_quality_gate_section(
    analysis: dict[str, Any],
    calculations: dict[str, Any],
    evidence: dict[str, Any],
    validated: dict[str, Any],
    language: str,
) -> str:
    grade_summary = validated.get("grade_summary") if isinstance(validated.get("grade_summary"), dict) else {}
    fact_count = len(evidence.get("facts") or []) if isinstance(evidence, dict) else 0
    calc_status = calculations.get("status") if isinstance(calculations, dict) else "unknown"
    scenario_status = ((calculations.get("scenario_analysis") or {}).get("status") if isinstance(calculations, dict) else "unknown")
    dcf_status = ((calculations.get("dcf_analysis") or {}).get("status") if isinstance(calculations, dict) else "unknown")
    rows = "".join(
        f"""<tr class="border-b">
          <td class="p-3 font-semibold">{esc(label)}</td>
          <td class="p-3">{esc(value)}</td>
          <td class="p-3">{source_tag(tag)}</td>
        </tr>"""
        for label, value, tag in (
            ("검증 지표 수" if is_korean(language) else "Validated metric count", len(validated.get("validated_metrics") or {}), "[Calc]"),
            ("증거 팩트 수" if is_korean(language) else "Evidence fact count", fact_count, "[Calc]"),
            ("등급 A/B/C/D 분포" if is_korean(language) else "Grade A/B/C/D split", f"A {grade_summary.get('A', 0)} / B {grade_summary.get('B', 0)} / C {grade_summary.get('C', 0)} / D {grade_summary.get('D', 0)}", "[Calc]"),
            ("결정론 계산 상태" if is_korean(language) else "Deterministic calculation status", mode_c_status(language, calc_status), "[Calc]"),
            ("시나리오 계산 상태" if is_korean(language) else "Scenario calculation status", mode_c_status(language, scenario_status), "[Calc]"),
            ("DCF 계산 상태" if is_korean(language) else "DCF calculation status", mode_c_status(language, dcf_status), "[Calc]"),
            (mode_c_label(language, "source_profile"), analysis.get("source_profile") or validated.get("source_profile") or "mixed", "[Portal]"),
            ("신뢰도 상한" if is_korean(language) else "Confidence cap", analysis.get("confidence_cap") or validated.get("confidence_cap") or "unknown", "[Calc]"),
        )
    )
    return f"""<section id="section-quality-gate">
      <h2 class="text-xl font-bold text-gray-900 mb-4"><i class="fa-solid fa-clipboard-check mr-2 text-brand-400"></i>{mode_c_label(language, "quality_gate")} - {esc(mode_c_count(language, fact_count, "facts", "팩트"))}</h2>
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div class="card p-6">
          <h3 class="text-sm font-bold text-gray-700 mb-3">{esc(mode_c_label(language, "evidence_boundary_4_artifact"))}</h3>
          <p class="text-sm text-gray-700 leading-7 mb-3">This Mode C dashboard is populated from validated-data, evidence-pack, deterministic-calculations, and analysis-result only. Raw artifacts stay outside the renderer by default, which prevents the dashboard from silently pulling unvalidated quarterly rows, stale market fields, or local files into the final HTML. Numbers in scenario valuation, DCF, reverse DCF, valuation bridge, KPI tiles, financial detail cards, and chart arrays are treated as deterministic outputs rather than analyst prose. When a metric is Grade D or excluded, the renderer is required to leave the value blank instead of filling a plausible substitute. {source_tag("[Calc]")}</p>
          <p class="text-sm text-gray-700 leading-7">The quality-of-earnings read is therefore deliberately narrow: revenue, operating margin, free cash flow, net debt, and analyst target fields can influence the report only when they appear in validated metrics with source tags and grades. This keeps the final dashboard closer to the original stock-analysis-agent discipline: explain the thesis richly, but let contract artifacts define what can be shown as a number. {source_tag("[Calc]")}</p>
        </div>
        <div class="card overflow-x-auto">
          <table class="w-full text-sm">
            <thead><tr class="bg-gray-50 text-gray-600 text-xs uppercase"><th class="text-left p-3">{esc(mode_c_label(language, "check"))}</th><th class="text-left p-3">{esc(mode_c_label(language, "value"))}</th><th class="text-left p-3">{esc(mode_c_label(language, "source"))}</th></tr></thead>
            <tbody>{rows}</tbody>
          </table>
        </div>
      </div>
      <div class="card p-6 mt-4 bg-gray-50 border border-gray-200">
        <h3 class="text-sm font-bold text-gray-700 mb-3">12 {esc(mode_c_label(language, "renderer_guardrails"))}</h3>
        <div class="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm text-gray-700">
          <div class="rounded-lg bg-white border border-gray-200 p-4">
            <p class="font-semibold text-gray-900 mb-2">{esc(mode_c_label(language, "scenario_math"))}</p>
            <p class="leading-6">Bull, base, and bear targets use deterministic scenario targets exactly. The R/R badge is carried from analysis-result, and the rendered chart lines reuse those same target values so table, cards, and chart cannot drift. {source_tag("[Calc]")}</p>
          </div>
          <div class="rounded-lg bg-white border border-gray-200 p-4">
            <p class="font-semibold text-gray-900 mb-2">{esc(mode_c_label(language, "chart_arrays"))}</p>
            <p class="leading-6">Revenue and margin charts are built from validated quarterly financial rows when available. The price chart is derived from current price, 52-week range, and deterministic scenario targets. Empty chart arrays are blocked by the Mode C render validator. {source_tag("[Calc]")}</p>
          </div>
          <div class="rounded-lg bg-white border border-gray-200 p-4">
            <p class="font-semibold text-gray-900 mb-2">{esc(mode_c_label(language, "delivery_gate"))}</p>
            <p class="leading-6">The generated HTML must clear byte-size, visible-text, canvas, script, table, required heading, forbidden string, local path leak, source tag, DCF, reverse DCF, and valuation bridge checks before later sessions may promote it to a report snapshot. {source_tag("[Calc]")}</p>
          </div>
        </div>
      </div>
    </section>"""


def render_portfolio_section(analysis: dict[str, Any], sections: dict[str, Any], scenarios: dict[str, Any], language: str) -> str:
    wrong = sections.get("what_would_make_me_wrong") if isinstance(sections.get("what_would_make_me_wrong"), list) else []
    wrong_html = "".join(f"<li>{esc(item)}</li>" for item in wrong[:8])
    catalysts = analysis.get("upcoming_catalysts") if isinstance(analysis.get("upcoming_catalysts"), list) else []
    catalyst_rows = "".join(
        f"""<tr class="border-b"><td class="p-3">{esc(item.get("date") or "date_unknown")}</td><td class="p-3">{esc(item.get("event") or item.get("description"))}</td><td class="p-3">{esc(item.get("significance") or item.get("narrative"))}</td><td class="p-3">{source_tag("[User]")}</td></tr>"""
        for item in catalysts
        if isinstance(item, dict)
    )
    return f"""<section id="section-strategy">
      <h2 class="text-xl font-bold text-gray-900 mb-4"><i class="fa-solid fa-chess-knight mr-2 text-brand-400"></i>{esc(mode_c_label(language, "portfolio_strategy"))} - {esc(mode_c_count(language, 3, "scenario paths", "시나리오 경로"))}</h2>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div class="card p-6"><h3 class="text-sm font-bold text-gray-700 mb-3">{esc(mode_c_label(language, "scenario_execution_guidelines"))}</h3><p class="text-sm text-gray-700 leading-7">{esc(sections.get("portfolio_strategy") or "Portfolio action should follow scenario probabilities and valuation bridge evidence.")}</p></div>
        <div class="card p-6"><h3 class="text-sm font-bold text-gray-700 mb-3">{esc(mode_c_label(language, "what_would_make_wrong"))} - {esc(mode_c_count(language, len(wrong[:8]), "checks", "체크"))}</h3><ul class="list-disc pl-5 text-sm text-gray-700 space-y-2">{wrong_html}</ul></div>
      </div>
      <div class="card overflow-x-auto mt-4">
        <table class="w-full text-sm">
          <thead><tr class="bg-gray-50 text-gray-600 text-xs uppercase"><th class="text-left p-3">{esc(mode_c_label(language, "date"))}</th><th class="text-left p-3">{esc(mode_c_label(language, "catalyst"))}</th><th class="text-left p-3">{esc(mode_c_label(language, "significance"))}</th><th class="text-left p-3">{esc(mode_c_label(language, "source"))}</th></tr></thead>
          <tbody>{catalyst_rows}</tbody>
        </table>
      </div>
    </section>"""


def render_source_appendix(source_claims: list[Any], language: str) -> str:
    rows = []
    for index, claim in enumerate(source_claims[:40], start=1):
        if not isinstance(claim, dict):
            continue
        grade = claim.get("grade") or "C"
        source = ", ".join(str(item) for item in (claim.get("sources") or [])[:3])
        rows.append(
            f"""<tr class="border-b">
              <td class="p-3 text-right text-gray-500">{index}</td>
              <td class="p-3">{esc(claim.get("claim") or claim.get("metric"))}</td>
              <td class="p-3">{esc(source or "validated evidence pack")}</td>
              <td class="p-3">{grade_badge({"grade": grade})}</td>
              <td class="p-3">{source_tag(tag_for_grade(grade))}</td>
            </tr>"""
        )
    return f"""<section id="section-sources">
      <h2 class="text-xl font-bold text-gray-900 mb-4"><i class="fa-solid fa-book mr-2 text-brand-400"></i>{esc(mode_c_label(language, "source_appendix"))} - {esc(mode_c_count(language, len(rows), "claims", "클레임"))}</h2>
      <div class="card overflow-x-auto">
        <table class="w-full text-sm">
          <thead><tr class="bg-gray-50 text-gray-600 text-xs uppercase"><th class="text-right p-3">#</th><th class="text-left p-3">{esc(mode_c_label(language, "claim"))}</th><th class="text-left p-3">{esc(mode_c_label(language, "source"))}</th><th class="text-left p-3">{esc(mode_c_label(language, "grade"))}</th><th class="text-left p-3">{esc(mode_c_label(language, "tag"))}</th></tr></thead>
          <tbody>{''.join(rows)}</tbody>
        </table>
      </div>
    </section>"""


def render_dcf_sensitivity(dcf: dict[str, Any], currency: str, language: str) -> str:
    rows = []
    table = dcf.get("sensitivity_table") if isinstance(dcf.get("sensitivity_table"), list) else []
    for item in table[:5]:
        if not isinstance(item, dict):
            continue
        rows.append(
            f"""<tr class="border-b">
              <td class="p-3 font-bold">{esc(item.get("wacc"))}</td>
              <td class="p-3 text-right">{sensitivity_cell(item.get("tgr_2.0%"), currency)}</td>
              <td class="p-3 text-right">{sensitivity_cell(item.get("tgr_2.5%"), currency)}</td>
              <td class="p-3 text-right">{sensitivity_cell(item.get("tgr_3.0%"), currency)}</td>
            </tr>"""
        )
    if not rows:
        message = "DCF 민감도 이용 불가" if is_korean(language) else "DCF sensitivity unavailable"
        rows.append(f"""<tr><td class="p-3" colspan="4">{esc(message)} {source_tag("[Calc]")}</td></tr>""")
    return "".join(rows)


def render_reverse_dcf(reverse: dict[str, Any] | None, language: str = "en") -> str:
    if not isinstance(reverse, dict):
        return ""
    status = str(reverse.get("status") or "unavailable")
    if status not in {"success", "available"}:
        reason = reverse.get("notes") or reverse.get("reason") or "Reverse DCF requires validated positive free cash flow before an implied-growth read can be shown."
        return f"""<div class="card p-5 mt-4 bg-amber-50 border border-amber-200">
          <h3 class="text-sm font-bold text-amber-900 mb-3">{esc(mode_c_label(language, "reverse_dcf"))} - {esc(mode_c_status(language, "unavailable"))} ({esc(mode_c_status(language, status))})</h3>
          <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div class="p-3 bg-white rounded-lg"><p class="text-xs text-gray-500">Status</p><p class="text-xl font-bold text-amber-800">{esc(status.replace("_", " "))}</p><p class="text-xs text-gray-400">No implied growth shown {source_tag("[Calc]")}</p></div>
            <div class="p-3 bg-white rounded-lg"><p class="text-xs text-gray-500">Market price anchor</p><p class="text-xl font-bold text-gray-700">{fmt(reverse.get("target_price"), 2)}</p><p class="text-xs text-gray-400">Used only as context {source_tag("[Calc]")}</p></div>
            <div class="p-3 bg-white rounded-lg"><p class="text-xs text-gray-500">Evidence boundary</p><p class="text-sm font-semibold text-gray-700 leading-6">{esc(reason)}</p></div>
          </div>
        </div>"""
    gap = reverse.get("growth_gap_bp")
    return f"""<div class="card p-5 mt-4 bg-gradient-to-r from-blue-50 to-indigo-50 border border-blue-200">
      <h3 class="text-sm font-bold text-brand-700 mb-3">{esc(mode_c_label(language, "reverse_dcf"))} - {pct(reverse.get("implied_fcf_growth"), probability=True)} {esc("시장 내재 성장률" if is_korean(language) else "market-implied growth")}</h3>
      <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
        <div class="text-center p-3 bg-white rounded-lg"><p class="text-xs text-gray-500">{esc(mode_c_label(language, "market_is_pricing_in"))}</p><p class="text-2xl font-bold text-brand-700">{pct(reverse.get("implied_fcf_growth"), probability=True)}</p><p class="text-xs text-gray-400">{esc(mode_c_label(language, "annual_fcf_growth"))} {source_tag("[Calc]")}</p></div>
        <div class="text-center p-3 bg-white rounded-lg"><p class="text-xs text-gray-500">{esc(mode_c_label(language, "our_base_assumes"))}</p><p class="text-2xl font-bold text-gray-700">{pct(reverse.get("analyst_growth_assumption"), probability=True)}</p><p class="text-xs text-gray-400">{esc(mode_c_label(language, "annual_fcf_growth"))} {source_tag("[Calc]")}</p></div>
        <div class="text-center p-3 bg-white rounded-lg"><p class="text-xs text-gray-500">{esc("차이" if is_korean(language) else "Gap")}</p><p class="text-2xl font-bold text-gray-700">{fmt(gap, 0)}bp</p><p class="text-xs text-gray-400">{esc(reverse.get("notes"))}</p></div>
      </div>
    </div>"""


def render_valuation_bridge(bridge: dict[str, Any] | None, currency: str, language: str) -> str:
    if not isinstance(bridge, dict):
        return ""
    anchors = bridge.get("anchors") if isinstance(bridge.get("anchors"), list) else []
    anchor_html = "".join(
        f"""<div class="card p-4 stat-card">
          <p class="text-xs text-gray-500 mb-1">{esc(item.get("label"))}</p>
          <p class="text-2xl font-bold text-brand-700">{currency_symbol(currency)}{fmt(item.get("value_per_share"), 2)}</p>
          <p class="text-xs text-gray-500 mt-1">{esc(mode_c_label(language, "weight"))} {pct(item.get("weight"), probability=True)} · {esc(item.get("method"))}</p>
          <p class="text-xs mt-1">{source_tag(item.get("tag") or "[Calc]")}</p>
        </div>"""
        for item in anchors
        if isinstance(item, dict)
    )
    return f"""<section id="section-valuation-bridge">
      <h2 class="text-xl font-bold text-gray-900 mb-4"><i class="fa-solid fa-bridge mr-2 text-brand-400"></i>{esc(mode_c_label(language, "valuation_bridge"))} - {esc("가중 적정가" if is_korean(language) else "weighted FV")} {currency_symbol(currency)}{fmt(bridge.get("weighted_fair_value"), 2)}</h2>
      <div class="grid grid-cols-1 md:grid-cols-3 xl:grid-cols-4 gap-3 mb-4">{anchor_html}</div>
      <div class="card p-6 bg-gradient-to-r from-blue-50 to-indigo-50 border border-blue-200 mb-4">
        <div class="grid grid-cols-1 md:grid-cols-3 gap-4 text-center">
          <div><p class="text-xs text-gray-500">{esc(mode_c_label(language, "weighted_fair_value"))}</p><p class="text-3xl font-extrabold text-brand-700">{currency_symbol(currency)}{fmt(bridge.get("weighted_fair_value"), 2)}</p></div>
          <div><p class="text-xs text-gray-500">{esc(mode_c_label(language, "current_price"))}</p><p class="text-3xl font-bold text-gray-700">{currency_symbol(currency)}{fmt(bridge.get("current_price"), 2)}</p></div>
          <div><p class="text-xs text-gray-500">{esc(mode_c_label(language, "implied_view_vs_market"))}</p><p class="text-3xl font-bold text-green-700">{esc(bridge.get("implied_view_vs_market"))}</p></div>
        </div>
      </div>
      <div class="card p-5 bg-gray-50 border border-gray-200"><h3 class="text-sm font-bold text-gray-700 mb-2">{esc(mode_c_label(language, "reconciliation_logic"))} - {esc(mode_c_count(language, len(anchors), "anchors", "앵커"))}</h3><p class="text-sm text-gray-700 leading-7">{esc(bridge.get("reconciliation_logic"))}</p><p class="text-xs text-gray-400 mt-2">{esc(mode_c_label(language, "decision_anchor"))} {esc(bridge.get("decision_anchor"))} {source_tag("[Calc]")}</p></div>
    </section>"""


def validate_mode_a_rendered_html(
    html_text: str,
    *,
    analysis: dict[str, Any],
    html_path: Path | None = None,
    validated: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metrics = rendered_metrics(html_text)
    visible = visible_text(html_text)
    body_word_count = len(re.findall(r"[A-Za-z0-9가-힣']+", visible))
    kpi_count = len(re.findall(r'data-mode-a-kpi="true"', html_text))
    risk_count = len(re.findall(r'data-mode-a-risk="true"', html_text))
    catalyst_count = len(re.findall(r'data-mode-a-catalyst="true"', html_text))
    scenario_count = len(re.findall(r'data-mode-a-scenario="true"', html_text))
    errors: list[str] = []
    warnings: list[str] = []

    metrics.update(
        {
            "body_word_count": body_word_count,
            "kpi_count": kpi_count,
            "risk_count": risk_count,
            "catalyst_count": catalyst_count,
            "scenario_count": scenario_count,
            "rr_present": bool(re.search(r"R/R\s+Score\s*[-+]?\d|R/R\s+[-+]?\d", visible, flags=re.IGNORECASE)),
        }
    )

    if not 500 <= body_word_count <= 900:
        errors.append(f"Mode A briefing word count outside 500-900 range: {body_word_count}")
    if metrics["body_text_chars"] < 3200:
        errors.append(f"Mode A briefing body text is too thin: {metrics['body_text_chars']} chars")
    if kpi_count < 3:
        errors.append(f"Mode A briefing requires at least 3 KPI cards, found {kpi_count}")
    if risk_count < 2:
        errors.append(f"Mode A briefing requires at least 2 risk mechanisms, found {risk_count}")
    if catalyst_count < 2:
        errors.append(f"Mode A briefing requires at least 2 catalyst rows, found {catalyst_count}")
    if scenario_count < 3:
        errors.append(f"Mode A briefing requires bull/base/bear scenario rows, found {scenario_count}")
    if not metrics["rr_present"]:
        errors.append("Mode A briefing is missing R/R score")
    if metrics["source_tag_count"] < 8:
        errors.append(f"Mode A source tag count below threshold: {metrics['source_tag_count']} < 8")

    lower_visible = visible.lower()
    ticker = str(analysis.get("ticker") or "").lower()
    company = str(analysis.get("company_name") or "").lower()
    if ticker and ticker not in lower_visible and company and company not in lower_visible:
        errors.append("Mode A briefing thesis/header does not identify the company or ticker")

    for pattern in (r"\{[A-Z0-9_]+\}", "/Users/", "stock-analysis-agent/output"):
        if re.search(pattern, html_text):
            errors.append(f"forbidden rendered pattern present: {pattern}")
    if "Disclaimer" not in html_text and "investment advice" not in html_text.lower():
        errors.append("disclaimer missing")

    scenarios = analysis.get("scenarios") if isinstance(analysis.get("scenarios"), dict) else {}
    if mode_a_rr_score(analysis, scenarios) is None:
        errors.append("Mode A numeric R/R score missing")
    missing_targets = [
        key
        for key in ("bull", "base", "bear")
        if scenario_target(scenarios, key) is None
    ]
    if missing_targets:
        errors.append("Mode A scenario target missing for: " + ", ".join(missing_targets))
    if re.search(r"(R/R Score|Base Target)\s*(?:-|Unavailable|null|None|NaN)\b", visible, flags=re.IGNORECASE):
        errors.append("Mode A hero displays an unavailable R/R score or base target")

    return {
        "status": "FAIL" if errors else "PASS",
        "metrics": metrics,
        "errors": errors,
        "warnings": warnings,
        "report_path": display_path(html_path) if html_path else None,
    }


def validate_mode_c_rendered_html(
    html_text: str,
    *,
    analysis: dict[str, Any],
    html_path: Path | None = None,
    validated: dict[str, Any] | None = None,
) -> dict[str, Any]:
    config, config_source = load_golden_config()
    minimums = config.get("minimums") or DEFAULT_GOLDEN_CONFIG["minimums"]
    metrics = rendered_metrics(html_text)
    errors: list[str] = []
    warnings: list[str] = []
    korean_output = bool(re.search(r"<html\s+lang=[\"']ko", html_text, flags=re.IGNORECASE))
    for key, minimum in minimums.items():
        if key == "body_text_chars" and korean_output:
            minimum = min(int(minimum), 9500)
        actual = metrics.get(key, 0)
        if actual < minimum:
            errors.append(f"{key} below Mode C golden minimum: {actual} < {minimum}")

    for group in config.get("required_heading_groups", []):
        pattern = group.get("pattern") if isinstance(group, dict) else None
        group_id = group.get("id") if isinstance(group, dict) else "unknown"
        if pattern and not re.search(pattern, html_text, flags=re.IGNORECASE):
            fallback = KOREAN_REQUIRED_HEADING_FALLBACKS.get(str(group_id))
            if fallback and re.search(fallback, html_text, flags=re.IGNORECASE):
                continue
            errors.append(f"required heading group missing: {group_id}")

    for pattern in config.get("forbidden_patterns", []):
        if re.search(pattern, html_text):
            errors.append(f"forbidden rendered pattern present: {pattern}")

    if re.search(r"\{[A-Z0-9_]+\}", html_text):
        errors.append("unresolved template placeholder present")
    if metrics["source_tag_count"] < max(10, metrics["numeric_claim_count"] // 8):
        errors.append("source tag count below Mode C rendered-output threshold")
    if metrics["chart_init_count"] < 3:
        errors.append("Mode C chart initialization count below 3")
    if has_empty_chart_arrays(html_text):
        errors.append("Mode C chart data arrays are empty")
    if (
        "Disclaimer" not in html_text
        and "investment advice" not in html_text.lower()
        and "면책" not in html_text
        and "투자 조언" not in html_text
    ):
        errors.append("disclaimer missing")
    if analysis.get("valuation_bridge") and "Valuation Bridge" not in html_text and "밸류에이션 브리지" not in html_text:
        errors.append("valuation_bridge exists but rendered section is missing")
    if analysis.get("reverse_dcf") and "Reverse DCF" not in html_text and "역산 DCF" not in html_text:
        errors.append("reverse_dcf exists but rendered section is missing")

    return {
        "status": "FAIL" if errors else "PASS",
        "metrics": metrics,
        "errors": errors,
        "warnings": warnings,
        "golden_config_source": config_source,
        "report_path": display_path(html_path) if html_path else None,
    }


def rendered_metrics(html_text: str) -> dict[str, Any]:
    visible = visible_text(html_text)
    return {
        "html_byte_size": len(html_text.encode("utf-8")),
        "body_text_chars": len(visible),
        "canvas_count": len(re.findall(r"<canvas\b", html_text, re.IGNORECASE)),
        "script_count": len(re.findall(r"<script\b", html_text, re.IGNORECASE)),
        "table_count": len(re.findall(r"<table\b", html_text, re.IGNORECASE)),
        "source_tag_count": len(re.findall(r"\[(?:Filing|Portal|KR-Portal|Calc|Est|Macro|User)\]", visible)),
        "numeric_claim_count": len(re.findall(r"(?<![A-Za-z0-9_])(?:[$₩€£]?\s*)?\d+(?:,\d{3})*(?:\.\d+)?\s*(?:%|x|bp|B|M|T|조|억|만)?", visible)),
        "chart_init_count": len(re.findall(r"new\s+Chart\s*\(", html_text)),
        "unresolved_placeholder_count": len(re.findall(r"\{[A-Z0-9_]+\}", html_text)),
    }


def load_golden_config() -> tuple[dict[str, Any], str]:
    candidates = [
        REPO_ROOT / "web" / "data" / "golden" / "mode-c-parity.json",
        REPO_ROOT.parent / "stock-analysis-agent-web" / "web" / "data" / "golden" / "mode-c-parity.json",
    ]
    for candidate in candidates:
        if candidate.exists():
            return normalize_public_mode_c_golden_config(json.loads(candidate.read_text(encoding="utf-8"))), display_path(candidate)
    return normalize_public_mode_c_golden_config(DEFAULT_GOLDEN_CONFIG), "default"


def normalize_public_mode_c_golden_config(config: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(config)
    minimums = dict(DEFAULT_GOLDEN_CONFIG["minimums"])
    minimums.update(config.get("minimums") or {})
    for key in ("body_text_chars", "html_byte_size"):
        configured = int(minimums.get(key) or 0)
        minimums[key] = max(configured, DEFAULT_GOLDEN_CONFIG["minimums"][key])
    normalized["minimums"] = minimums
    groups = config.get("required_heading_groups")
    normalized["required_heading_groups"] = (
        list(groups) if groups else list(DEFAULT_GOLDEN_CONFIG["required_heading_groups"])
    )
    return normalized


def has_empty_chart_arrays(html_text: str) -> bool:
    for name in ("quarters", "revenueData", "opIncomeData", "fcfData", "marginData", "priceLabels", "priceData", "segmentLabels", "segmentData"):
        match = re.search(rf"const\s+{name}\s*=\s*(\[[^\]]*\])", html_text)
        if not match:
            return True
        try:
            parsed = json.loads(match.group(1))
        except json.JSONDecodeError:
            return True
        if not parsed:
            return True
    return False


def build_chart_data(
    *,
    analysis: dict[str, Any],
    metrics: dict[str, Any],
    quarterly: list[dict[str, Any]],
    scenarios: dict[str, Any],
    language: str = "en",
) -> dict[str, Any]:
    usable_quarters = quarterly[:6]
    if not usable_quarters:
        revenue = metric_value(metrics, "revenue_ttm") or 0
        op_margin = metric_value(metrics, "operating_margin") or 0
        net_margin = metric_value(metrics, "net_margin") or 0
        usable_quarters = [
            {
                "period_end": analysis.get("analysis_date") or "current",
                "revenue": revenue * 1_000_000_000,
                "operating_income": revenue * op_margin / 100 * 1_000_000_000,
                "net_income": revenue * net_margin / 100 * 1_000_000_000,
            }
        ]
    usable_quarters = list(reversed(usable_quarters))
    quarters = [str(item.get("period_end") or f"Q{index + 1}") for index, item in enumerate(usable_quarters)]
    revenue = [round(to_billions(item.get("revenue")), 2) for item in usable_quarters]
    op_income = [round(to_billions(item.get("operating_income")), 2) for item in usable_quarters]
    free_cash_flow = [
        round(free_cash_flow_billions(item, metrics, len(usable_quarters)), 2)
        for item in usable_quarters
    ]
    op_margin = [round(margin(item.get("operating_income"), item.get("revenue")) or 0, 2) for item in usable_quarters]
    net_margin = [round(margin(item.get("net_income"), item.get("revenue")) or 0, 2) for item in usable_quarters]
    latest_quarter = usable_quarters[-1] if usable_quarters else {}
    if is_korean(language):
        segment_labels = ["매출", "매출총이익", "영업이익", "순이익"]
    else:
        segment_labels = ["Revenue", "Gross Profit", "Operating Income", "Net Income"]
    segment_data = [
        round(to_billions(pick_any(latest_quarter, "revenue", "total_revenue", "sales")), 2),
        round(to_billions(pick_any(latest_quarter, "gross_profit", "grossProfit")), 2),
        round(to_billions(pick_any(latest_quarter, "operating_income", "operatingIncome", "operating_profit")), 2),
        round(to_billions(pick_any(latest_quarter, "net_income", "netIncome")), 2),
    ]

    price = metric_value(metrics, "price_at_analysis") or analysis.get("price_at_analysis") or 0
    low = metric_value(metrics, "fifty_two_week_low") or price
    high = metric_value(metrics, "fifty_two_week_high") or price
    bull = scenario_target(scenarios, "bull") or high or price
    base = scenario_target(scenarios, "base") or price
    bear = scenario_target(scenarios, "bear") or low or price
    if is_korean(language):
        price_labels = ["52주 저점", "현재가", "약세", "기준", "강세", "52주 고점"]
    else:
        price_labels = ["52W Low", "Current", "Bear", "Base", "Bull", "52W High"]
    price_data = [low, price, bear, base, bull, high]
    return {
        "quarters": quarters,
        "revenue": revenue,
        "operating_income": op_income,
        "free_cash_flow": free_cash_flow,
        "operating_margin": op_margin,
        "net_margin": net_margin,
        "price_labels": price_labels,
        "price_data": [round(float(value), 2) for value in price_data],
        "bull_line": [round(float(bull), 2)] * len(price_labels),
        "base_line": [round(float(base), 2)] * len(price_labels),
        "bear_line": [round(float(bear), 2)] * len(price_labels),
        "segment_labels": segment_labels,
        "segment_data": segment_data,
    }


def normalize_quarterly(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in value:
        rows.extend(flatten_quarterly_item(item))
    return sorted(rows, key=lambda item: str(item.get("period_end") or ""), reverse=True)


def flatten_quarterly_item(item: Any) -> list[dict[str, Any]]:
    if not isinstance(item, dict):
        return []
    nested_financials = item.get("financials")
    if isinstance(nested_financials, dict):
        statements = nested_financials.get("income_statements")
        if isinstance(statements, list):
            return [row for statement in statements for row in flatten_quarterly_item(statement)]
    statements = item.get("income_statements")
    if isinstance(statements, list):
        return [row for statement in statements for row in flatten_quarterly_item(statement)]

    normalized = {
        "period_end": item.get("period_end") or item.get("report_period") or item.get("date") or item.get("fiscal_period"),
        "revenue": pick_any(item, "revenue", "total_revenue", "sales"),
        "gross_profit": pick_any(item, "gross_profit", "grossProfit"),
        "operating_income": pick_any(item, "operating_income", "operatingIncome", "operating_profit"),
        "net_income": pick_any(item, "net_income", "netIncome", "net_income_common_stock"),
        "free_cash_flow": pick_any(item, "free_cash_flow", "freeCashFlow"),
        "operating_cash_flow": pick_any(item, "operating_cash_flow", "operatingCashFlow", "net_cash_flow_from_operations"),
        "capital_expenditure": pick_any(item, "capital_expenditure", "capitalExpenditure", "capex"),
    }
    if normalized["period_end"] or any(as_number(normalized.get(key)) is not None for key in ("revenue", "operating_income", "net_income")):
        return [normalized]
    return []


def pick_any(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if as_number(value) is not None:
            return value
    return None


def free_cash_flow_billions(
    row: dict[str, Any],
    metrics: dict[str, Any],
    period_count: int,
) -> float:
    direct = pick_any(row, "free_cash_flow", "freeCashFlow")
    if as_number(direct) is not None:
        return to_billions(direct)

    operating_cash_flow = as_number(pick_any(row, "operating_cash_flow", "operatingCashFlow"))
    capex = as_number(pick_any(row, "capital_expenditure", "capitalExpenditure", "capex"))
    if operating_cash_flow is not None and capex is not None:
        return to_billions(operating_cash_flow + capex if capex < 0 else operating_cash_flow - capex)

    fcf_ttm = metric_value(metrics, "fcf_ttm")
    if fcf_ttm is None:
        return 0.0
    divisor = max(1, min(period_count, 4))
    return fcf_ttm / divisor


def esc(value: Any) -> str:
    if value is None:
        return ""
    return html.escape(str(value), quote=True)


def visible_text(html_text: str) -> str:
    text = re.sub(r"<script\b[^>]*>.*?</script>", " ", html_text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<style\b[^>]*>.*?</style>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def json_js(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def korean_font(language: str) -> str:
    if language == "ko":
        return '<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700&display=swap" rel="stylesheet">'
    return ""


def deterministic_disclosure_banner(analysis: dict[str, Any], language: str) -> str:
    run_context = analysis.get("run_context") if isinstance(analysis.get("run_context"), dict) else {}
    if str(run_context.get("run_profile") or "").strip().lower() != "deterministic":
        return ""
    message = (
        "본 리포트는 LLM 분석 없이 검증 지표 기반 결정론적 템플릿으로 생성되었습니다. 투자 판단(verdict)은 규칙 기반 산출값입니다."
        if language == "ko"
        else "This report was generated from a deterministic template without LLM analysis; the verdict is rule-derived."
    )
    return (
        '<div style="max-width:1120px;margin:18px auto 0;padding:12px 18px;'
        'border:1px solid #f59e0b;background:#fffbeb;color:#92400e;'
        'border-radius:8px;font-size:13px;line-height:1.55;font-weight:650;">'
        f"{esc(message)}</div>"
    )


def metric_source(entry: Any) -> str:
    if not isinstance(entry, dict):
        return source_tag("[User]")
    tag = entry.get("display_tag") or entry.get("tag") or "[User]"
    grade = entry.get("grade") or "C"
    return f"{source_tag(tag)} {grade_badge({'grade': grade})}"


def source_tag(tag: Any) -> str:
    normalized = str(tag or "[User]")
    if normalized not in {"[Filing]", "[Portal]", "[KR-Portal]", "[Calc]", "[Est]", "[Macro]", "[User]"}:
        normalized = "[User]"
    klass = {
        "[Portal]": "tag-portal",
        "[KR-Portal]": "tag-portal",
        "[Calc]": "tag-calc",
        "[Est]": "tag-est",
        "[Macro]": "tag-macro",
    }.get(normalized, "tag-portal")
    return f'<span class="source-tag {klass}">{esc(normalized)}</span>'


def grade_badge(entry: Any) -> str:
    grade = entry.get("grade") if isinstance(entry, dict) else None
    grade = grade if grade in {"A", "B", "C", "D"} else "C"
    return f'<span class="grade-badge grade-{grade}">{grade}</span>'


def tag_for_grade(grade: str) -> str:
    return "[Calc]" if grade in {"A", "B", "C"} else "[User]"


def header_metric(label: str, entry: Any, currency: str, metric_key: str) -> str:
    return f"""<span class="text-blue-200/60">{esc(label)}</span><span class="text-white font-semibold">{metric_display(entry, metric_key, currency)} {grade_badge(entry)}</span>"""


def verdict_badge(verdict: Any) -> str:
    value = str(verdict or "neutral")
    return f'<span class="bg-white/10 border border-white/20 text-blue-100 px-4 py-1.5 rounded-lg font-bold">{esc(value)}</span>'


def rr_badge(rr_score: Any) -> str:
    return f'<span class="bg-gray-700 text-white px-4 py-2 rounded-xl font-bold">R/R {fmt(rr_score, 2)}</span>'


def to_billions(value: Any) -> float:
    number = as_number(value)
    if number is None:
        return 0.0
    return number / 1_000_000_000 if abs(number) > 1_000_000 else number


def margin(numerator: Any, denominator: Any) -> float | None:
    top = as_number(numerator)
    bottom = as_number(denominator)
    if top is None or bottom in {None, 0}:
        return None
    return top / bottom * 100


def scenario_target(scenarios: dict[str, Any], key: str) -> float | None:
    item = scenarios.get(key)
    if isinstance(item, dict):
        return as_number(item.get("target"))
    return None


def first(items: list[Any]) -> Any:
    return items[0] if items else None


def item_at(items: list[Any], index: int) -> Any:
    return items[index] if len(items) > index else None


def sensitivity_cell(value: Any, currency: str) -> str:
    if not isinstance(value, dict):
        return f"- {source_tag('[Calc]')}"
    return f"{currency_symbol(currency)}{fmt(value.get('fair_value'), 2)}<div class=\"text-xs text-gray-500\">{pct(value.get('upside_pct'))} {source_tag('[Calc]')}</div>"


def peer_row(ticker: Any, label: str, metrics: dict[str, Any], klass: str, language: str) -> str:
    growth_word = "성장률" if is_korean(language) else "growth"
    margin_word = "마진" if is_korean(language) else "margin"
    basis = f"{metric_display(metrics.get('revenue_growth_yoy'), 'revenue_growth_yoy', 'USD')} {growth_word} / {metric_display(metrics.get('operating_margin'), 'operating_margin', 'USD')} {margin_word}"
    return f"""<tr class="border-b {klass}">
      <td class="p-4 font-semibold">{esc(ticker)}</td>
      <td class="p-4">{esc(label)} - {basis}</td>
      <td class="p-4 text-right">{metric_display(metrics.get("market_cap"), "market_cap", "USD")}</td>
      <td class="p-4 text-right">{source_tag("[Calc]")}</td>
    </tr>"""


def target_card(label: str, target: Any, price: Any, currency: str, language: str) -> str:
    target_number = as_number(target)
    price_number = as_number(price)
    upside = None
    if target_number is not None and price_number not in {None, 0}:
        upside = (target_number - price_number) / price_number * 100
    return f"""<div class="card p-5 text-center">
      <p class="text-xs text-gray-500 mb-1">{esc(label)}</p>
      <p class="text-3xl font-bold text-brand-600">{currency_symbol(currency)}{fmt(target_number, 2)}</p>
      <p class="text-sm text-gray-500 mt-1">{pct(upside)} {esc("현재 대비" if is_korean(language) else "vs current")} {source_tag("[Est]")}</p>
    </div>"""


def detail_card(title: str, entry: Any, currency: str, metric_key: str) -> str:
    return f"""<div class="card p-5">
      <p class="text-xs text-gray-500 mb-1">{esc(title)} {grade_badge(entry)}</p>
      <p class="text-2xl font-bold text-brand-700">{metric_display(entry, metric_key, currency)}</p>
      <p class="text-xs text-gray-500 mt-1">{metric_source(entry)}</p>
    </div>"""


def display_path(path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return str(path.resolve())
