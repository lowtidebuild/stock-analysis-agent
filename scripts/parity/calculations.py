"""Deterministic calculators for the A/B/C parity runner."""

from __future__ import annotations

import importlib.util
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tools.artifact_validation import validate_artifact_data
from tools.context_budget import build_context_budget

from scripts.parity.data_sources import load_json, write_json

REPO_ROOT = Path(__file__).resolve().parents[2]
DCF_CALCULATOR_PATH = REPO_ROOT / ".claude" / "agents" / "analyst" / "scripts" / "dcf-calculator.py"


@dataclass(frozen=True)
class CalculationResult:
    ticker: str
    artifact_root: Path
    calculations_path: Path
    context_budget_path: Path
    status: str
    scenario_status: str
    dcf_status: str


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_calculation_handoff(
    *,
    language: str,
    market: str,
    mode: str,
    run_id: str,
    ticker: str,
) -> CalculationResult:
    ticker_dir = REPO_ROOT / "output" / "runs" / run_id / ticker
    run_dir = ticker_dir.parent
    validated_path = ticker_dir / "validated-data.json"
    evidence_path = ticker_dir / "evidence-pack.json"
    validated = load_json(validated_path)
    if not validated:
        raise ValueError(f"validated-data.json is required before deterministic calculations: {validated_path}")

    calculations = build_deterministic_calculations(
        evidence=load_json(evidence_path),
        language=language,
        market=market,
        mode=mode,
        run_id=run_id,
        ticker=ticker,
        validated=validated,
    )
    calculation_errors = validate_artifact_data("deterministic-calculations", calculations)
    if calculation_errors:
        raise ValueError(
            "deterministic-calculations failed contract checks: "
            + "; ".join(calculation_errors[:5])
        )
    calculations_path = ticker_dir / "deterministic-calculations.json"
    write_json(calculations_path, calculations)

    context_budget = build_context_budget(run_dir, ticker=ticker)
    context_budget_path = ticker_dir / "context-budget.json"
    write_json(context_budget_path, context_budget)
    context_errors = validate_artifact_data("context-budget", context_budget)
    if context_errors:
        raise ValueError(
            "context-budget failed after deterministic calculations: "
            + "; ".join(context_errors[:5])
        )

    return CalculationResult(
        ticker=ticker,
        artifact_root=ticker_dir,
        calculations_path=calculations_path,
        context_budget_path=context_budget_path,
        status=calculations["status"],
        scenario_status=calculations["scenario_analysis"]["status"],
        dcf_status=calculations["dcf_analysis"]["status"],
    )


def build_deterministic_calculations(
    *,
    evidence: dict[str, Any],
    language: str,
    market: str,
    mode: str,
    run_id: str,
    ticker: str,
    validated: dict[str, Any],
) -> dict[str, Any]:
    metrics = validated.get("validated_metrics") if isinstance(validated.get("validated_metrics"), dict) else {}
    macro = validated.get("macro_context") if isinstance(validated.get("macro_context"), dict) else {}
    ratios = build_ratio_recomputation(metrics)
    scenarios = build_scenario_analysis(metrics, language=language)
    dcf = build_dcf_analysis(metrics, macro=macro)
    valuation_bridge = build_valuation_bridge(
        dcf=dcf,
        language=language,
        metrics=metrics,
        scenarios=scenarios,
    )
    macro_deltas = build_macro_deltas(macro)
    blockers = []
    if scenarios["status"] != "available":
        blockers.append("scenario_analysis_unavailable")
    if dcf["status"] != "available":
        blockers.append("dcf_analysis_unavailable")

    return {
        "schema_version": "abc-parity-deterministic-calculations-v1",
        "artifact_type": "deterministic-calculations",
        "ticker": ticker,
        "market": market,
        "mode": mode,
        "language": language,
        "generated_at": utc_now(),
        "run_context": {
            "run_id": run_id,
            "artifact_root": display_path(REPO_ROOT / "output" / "runs" / run_id / ticker),
            "ticker": ticker,
        },
        "status": "available" if not blockers else "partial",
        "blockers": blockers,
        "source_profile": validated.get("source_profile"),
        "overall_grade": validated.get("overall_grade"),
        "ratio_recomputation": ratios,
        "scenario_analysis": scenarios,
        "dcf_analysis": dcf,
        "reverse_dcf": dcf.get("reverse_dcf"),
        "valuation_bridge": valuation_bridge,
        "macro_deltas": macro_deltas,
        "analyst_handoff": {
            "use_scenarios_exactly": scenarios["status"] == "available",
            "use_rr_score_exactly": scenarios.get("rr_score") is not None,
            "use_dcf_outputs_exactly": dcf["status"] == "available",
            "raw_artifacts_default_load": "deny",
            "evidence_fact_count": len(evidence.get("facts") or []),
        },
    }


def build_ratio_recomputation(metrics: dict[str, Any]) -> dict[str, Any]:
    price = metric_number(metrics, "price_at_analysis")
    market_cap_b = metric_number(metrics, "market_cap")
    revenue_b = metric_number(metrics, "revenue_ttm")
    fcf_b = metric_number(metrics, "fcf_ttm")
    net_debt_b = metric_number(metrics, "net_debt")
    diluted_shares_m = metric_number(metrics, "diluted_shares")
    if diluted_shares_m is None and price and market_cap_b:
        diluted_shares_m = round((market_cap_b * 1000) / price, 4)

    computed = {
        "diluted_shares": metric_entry(
            diluted_shares_m,
            unit="millions",
            formula="market_cap / price when source shares are unavailable",
        ),
        "fcf_yield": metric_entry(
            safe_pct(fcf_b, market_cap_b),
            unit="percent",
            formula="fcf_ttm / market_cap",
        ),
        "price_to_sales": metric_entry(
            safe_div(market_cap_b, revenue_b),
            unit="x",
            formula="market_cap / revenue_ttm",
        ),
        "net_debt_to_market_cap": metric_entry(
            safe_pct(net_debt_b, market_cap_b),
            unit="percent",
            formula="net_debt / market_cap",
        ),
    }
    return {
        "status": "available" if any(item["value"] is not None for item in computed.values()) else "unavailable",
        "inputs": {
            "price_at_analysis": price,
            "market_cap_billions": market_cap_b,
            "revenue_ttm_billions": revenue_b,
            "fcf_ttm_billions": fcf_b,
            "net_debt_billions": net_debt_b,
        },
        "computed_metrics": computed,
    }


def build_scenario_analysis(metrics: dict[str, Any], *, language: str) -> dict[str, Any]:
    price = metric_number(metrics, "price_at_analysis")
    if price is None or price <= 0:
        return unavailable("missing_price_at_analysis")

    analyst_mean = metric_number(metrics, "analyst_target_mean")
    analyst_median = metric_number(metrics, "analyst_target_median")
    analyst_high = metric_number(metrics, "analyst_target_high")
    analyst_low = metric_number(metrics, "analyst_target_low")
    high_52w = metric_number(metrics, "fifty_two_week_high")
    low_52w = metric_number(metrics, "fifty_two_week_low")
    growth = metric_number(metrics, "revenue_growth_yoy")
    fcf_yield = metric_number(metrics, "fcf_yield")

    base_target = analyst_median or analyst_mean or price * base_multiplier(growth, fcf_yield)
    bull_target = analyst_high or max(base_target * 1.15, high_52w or base_target * 1.1)
    bear_floor = price * 0.70
    bear_target = analyst_low if analyst_low and analyst_low < price else low_52w if low_52w and low_52w < price else bear_floor
    bear_target = max(min(bear_target, price * 0.85), price * 0.45)
    probabilities = {"bull": 0.25, "base": 0.50, "bear": 0.25}
    assumptions = scenario_assumptions(language=language, has_targets=bool(analyst_mean or analyst_median))
    scenarios = {
        "bull": scenario_item(bull_target, price, probabilities["bull"], assumptions["bull"]),
        "base": scenario_item(base_target, price, probabilities["base"], assumptions["base"]),
        "bear": scenario_item(bear_target, price, probabilities["bear"], assumptions["bear"]),
    }
    rr_score = calculate_rr_score(scenarios)
    expected_return = sum(
        item["return_pct"] * item["probability"]
        for item in scenarios.values()
        if item.get("return_pct") is not None and item.get("probability") is not None
    )
    return {
        "status": "available",
        "method": "deterministic target anchor with consensus/high-low fallback",
        "current_price": price,
        "scenarios": scenarios,
        "probability_sum": round(sum(item["probability"] for item in scenarios.values()), 4),
        "expected_return_pct": round(expected_return, 4),
        "rr_score": rr_score,
        "checks": {
            "target_ordering": scenarios["bull"]["target"] >= scenarios["base"]["target"] >= scenarios["bear"]["target"],
            "probability_sum_is_one": abs(sum(item["probability"] for item in scenarios.values()) - 1.0) < 0.001,
            "all_returns_numeric": all(isinstance(item.get("return_pct"), (int, float)) for item in scenarios.values()),
        },
    }


def build_dcf_analysis(metrics: dict[str, Any], *, macro: dict[str, Any]) -> dict[str, Any]:
    price = metric_number(metrics, "price_at_analysis")
    market_cap_b = metric_number(metrics, "market_cap")
    fcf_b = metric_number(metrics, "fcf_ttm")
    revenue_growth = metric_number(metrics, "revenue_growth_yoy")
    net_debt_b = metric_number(metrics, "net_debt") or 0.0
    diluted_shares_m = metric_number(metrics, "diluted_shares")
    if diluted_shares_m is None and price and market_cap_b:
        diluted_shares_m = round((market_cap_b * 1000) / price, 4)
    if price is None or fcf_b is None or diluted_shares_m is None:
        missing = [
            name
            for name, value in (
                ("price_at_analysis", price),
                ("fcf_ttm", fcf_b),
                ("diluted_shares", diluted_shares_m),
            )
            if value is None
        ]
        return {**unavailable("missing_dcf_inputs"), "missing_inputs": missing}

    dcf_module = load_dcf_module()
    risk_free_rate = decimal_rate(macro_number(macro, "risk_free_rate")) or 0.04
    beta = metric_number(metrics, "beta") or 1.0
    fcf_growth_rate = clamp(decimal_rate(revenue_growth) or 0.05, 0.01, 0.18)
    inputs = {
        "scenario_name": "base",
        "current_price": price,
        "current_price_for_reverse": price,
        "diluted_shares": diluted_shares_m,
        "fcf_ttm": fcf_b * 1000,
        "fcf_growth_rate": fcf_growth_rate,
        "risk_free_rate": risk_free_rate,
        "beta": beta,
        "erp": 0.055,
        "terminal_growth_rate": 0.025 if risk_free_rate <= 0.05 else 0.03,
        "forecast_years": 10,
        "net_debt": net_debt_b * 1000,
        "mid_year_convention": True,
    }
    result = dcf_module.calculate_dcf(inputs)
    return {
        "status": "available" if result.get("fair_value_per_share") is not None else "unavailable",
        "method": "existing dcf-calculator.py",
        "inputs": inputs,
        "result": result,
        "reverse_dcf": result.get("reverse_dcf"),
        "sensitivity_table": result.get("sensitivity_table"),
        "warnings": result.get("errors") or [],
    }


def build_valuation_bridge(
    *,
    dcf: dict[str, Any],
    language: str,
    metrics: dict[str, Any],
    scenarios: dict[str, Any],
) -> dict[str, Any]:
    price = metric_number(metrics, "price_at_analysis")
    anchors = []
    dcf_value = (dcf.get("result") or {}).get("fair_value_per_share") if isinstance(dcf.get("result"), dict) else None
    if dcf_value is not None:
        anchors.append(anchor("DCF (Base)", dcf_value, 0.35, "10Y FCF + terminal value", "[Calc]"))

    analyst_target = metric_number(metrics, "analyst_target_median") or metric_number(metrics, "analyst_target_mean")
    if analyst_target is not None:
        anchors.append(anchor("Analyst Target", analyst_target, 0.25, "Consensus target", "[Est]"))

    base_scenario = (scenarios.get("scenarios") or {}).get("base") if isinstance(scenarios.get("scenarios"), dict) else {}
    if isinstance(base_scenario, dict) and base_scenario.get("target") is not None:
        label = "우리 Base Scenario" if language == "ko" else "Our Base Scenario"
        anchors.append(anchor(label, base_scenario["target"], 0.40, "Deterministic base scenario", "[Calc]"))

    if not anchors:
        return unavailable("no_valuation_anchors")

    anchors = normalize_anchor_weights(anchors)
    weighted = round(sum(item["value_per_share"] * item["weight"] for item in anchors), 4)
    implied = round(((weighted - price) / price) * 100, 4) if price else None
    return {
        "status": "available",
        "anchors": anchors,
        "current_price": price,
        "weighted_fair_value": weighted,
        "implied_view_vs_market": f"{implied:+.1f}%" if implied is not None else None,
        "decision_anchor": "scenarios.base" if base_scenario else "weighted_fair_value",
        "reconciliation_logic": bridge_logic(language=language, anchor_count=len(anchors)),
    }


def build_macro_deltas(macro: dict[str, Any]) -> dict[str, Any]:
    structured = macro.get("structured") if isinstance(macro.get("structured"), dict) else {}
    if structured.get("status") != "available":
        return unavailable(structured.get("reason") or "macro_unavailable")
    return {
        "status": "available",
        "risk_free_rate": structured.get("risk_free_rate"),
        "fed_funds_rate": structured.get("fed_funds_rate"),
        "yield_curve_spread": structured.get("yield_curve_spread"),
        "yield_curve_inverted": structured.get("yield_curve_inverted"),
        "cpi_yoy": structured.get("cpi_yoy"),
        "gdp_growth": structured.get("gdp_growth"),
        "unemployment": structured.get("unemployment"),
    }


def load_dcf_module() -> Any:
    spec = importlib.util.spec_from_file_location("parity_dcf_calculator", DCF_CALCULATOR_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load DCF calculator: {DCF_CALCULATOR_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def metric_number(metrics: dict[str, Any], name: str) -> float | None:
    entry = metrics.get(name)
    if not isinstance(entry, dict):
        return None
    return as_number(entry.get("value"))


def macro_number(macro: dict[str, Any], name: str) -> float | None:
    structured = macro.get("structured") if isinstance(macro.get("structured"), dict) else {}
    return as_number(structured.get(name))


def as_number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return None
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(",", "").replace("%", "").strip())
        except ValueError:
            return None
    return None


def metric_entry(value: float | None, *, formula: str, unit: str) -> dict[str, Any]:
    return {
        "value": round(value, 4) if value is not None else None,
        "unit": unit,
        "formula": formula,
        "status": "available" if value is not None else "unavailable",
    }


def scenario_item(target: float, current_price: float, probability: float, assumption: str) -> dict[str, Any]:
    return {
        "target": round(target, 4),
        "return_pct": round((target / current_price - 1) * 100, 4),
        "probability": probability,
        "key_assumption": assumption,
    }


def calculate_rr_score(scenarios: dict[str, dict[str, Any]]) -> float | None:
    bull = scenarios.get("bull", {})
    base = scenarios.get("base", {})
    bear = scenarios.get("bear", {})
    upside = (
        (as_number(bull.get("return_pct")) or 0) * (as_number(bull.get("probability")) or 0)
        + (as_number(base.get("return_pct")) or 0) * (as_number(base.get("probability")) or 0)
    )
    downside = abs((as_number(bear.get("return_pct")) or 0) * (as_number(bear.get("probability")) or 0))
    if downside == 0:
        return None
    return round(upside / downside, 4)


def safe_div(numerator: Any, denominator: Any) -> float | None:
    left = as_number(numerator)
    right = as_number(denominator)
    if left is None or right in (None, 0):
        return None
    return left / right


def safe_pct(numerator: Any, denominator: Any) -> float | None:
    value = safe_div(numerator, denominator)
    return value * 100 if value is not None else None


def decimal_rate(value: float | None) -> float | None:
    if value is None:
        return None
    return value / 100 if abs(value) > 1 else value


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def base_multiplier(growth: float | None, fcf_yield: float | None) -> float:
    multiplier = 1.0
    if growth is not None:
        multiplier += clamp(growth / 100, -0.1, 0.2) * 0.5
    if fcf_yield is not None and fcf_yield < 2:
        multiplier -= 0.05
    return clamp(multiplier, 0.80, 1.20)


def scenario_assumptions(*, language: str, has_targets: bool) -> dict[str, str]:
    if language == "ko":
        if has_targets:
            return {
                "bull": "컨센서스 상단 또는 52주 고점 회복이 가능한 고성장/마진 개선 케이스.",
                "base": "컨센서스 중앙값 또는 평균 목표가가 실현되고 주요 추정치 하향이 없는 케이스.",
                "bear": "하단 목표가 또는 최근 저점 재테스트를 반영한 디레이팅 케이스.",
            }
        return {
            "bull": "매출 성장과 현금흐름 지표가 동시에 개선되는 케이스.",
            "base": "검증된 현재 데이터에서 완만한 정상화만 반영한 케이스.",
            "bear": "검증 데이터 부족과 밸류에이션 압축을 반영한 보수 케이스.",
        }
    if has_targets:
        return {
            "bull": "Consensus high-case or 52-week high is reached on growth and margin delivery.",
            "base": "Consensus median/mean target is realized with no major estimate reset.",
            "bear": "Downside target or recent-low retest captures valuation compression.",
        }
    return {
        "bull": "Revenue growth and cash-flow conversion improve together.",
        "base": "Only modest normalization is credited from the verified current data.",
        "bear": "Thin verified data and valuation compression drive the downside case.",
    }


def anchor(label: str, value: float, weight: float, method: str, tag: str) -> dict[str, Any]:
    return {
        "label": label,
        "value_per_share": round(value, 4),
        "weight": weight,
        "method": method,
        "tag": tag,
    }


def normalize_anchor_weights(anchors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    total = sum(as_number(item.get("weight")) or 0 for item in anchors)
    if total <= 0:
        equal = 1 / len(anchors)
        return [{**item, "weight": round(equal, 4)} for item in anchors]
    return [{**item, "weight": round((as_number(item.get("weight")) or 0) / total, 4)} for item in anchors]


def bridge_logic(*, anchor_count: int, language: str) -> str:
    if language == "ko":
        return (
            f"Deterministic bridge는 현재 이용 가능한 {anchor_count}개 앵커를 같은 주당가치 단위로 정렬한다. "
            "DCF는 장기 FCF와 할인율에 민감하고, 애널리스트/시나리오 앵커는 12개월 기대치를 더 많이 반영한다. "
            "따라서 analyst pass는 이 가중평균을 결론으로 그대로 복사하지 말고, 어떤 앵커가 투자판단을 지배하는지 설명해야 한다. "
            "또한 현재가 대비 괴리가 데이터 품질, 추정치 신뢰도, 현금흐름 지속성 중 어디에서 발생했는지 분리해 해석해야 한다."
        )
    return (
        f"The deterministic bridge aligns {anchor_count} available anchors on a per-share basis. "
        "DCF is most sensitive to long-term FCF and discount-rate assumptions, while analyst and scenario anchors "
        "carry more 12-month expectation weight. The analyst pass should explain which anchor drives the decision, "
        "whether the gap versus market price comes from data quality, estimate confidence, or cash-flow durability, "
        "and what fresh evidence would move the decision anchor."
    )


def unavailable(reason: Any) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "reason": str(reason),
    }


def display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return str(path.resolve())
