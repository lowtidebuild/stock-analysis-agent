from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from tools.analysis_contract import (
    CANONICAL_DISPLAY_TAGS,
    CANONICAL_SOURCE_TYPES,
    extract_numeric_value,
    find_repo_root,
    metric_display_tag,
    normalize_metric_entry,
)
from tools.analysis_patch import load_json as load_json_file
from tools.analysis_patch import validate_against_patch_plan

SCHEMA_DIR = Path(".claude") / "schemas"
MILLION_SHARE_UNITS = {"million", "millions"}
MILLION_CURRENCY_UNITS = {
    "million",
    "millions",
    "million_usd",
    "millions_usd",
    "million_krw",
    "millions_krw",
    "m_usd",
}
UNIT_MULTIPLIERS = {
    "million": 1_000_000,
    "millions": 1_000_000,
    "million_usd": 1_000_000,
    "millions_usd": 1_000_000,
    "million_krw": 1_000_000,
    "millions_krw": 1_000_000,
    "m_usd": 1_000_000,
    "백만원": 1_000_000,
    "억원": 100_000_000,
    "조원": 1_000_000_000_000,
    "percent": 1,
    "%": 1,
}
QUALITY_REPORT_CORE_ITEMS = {
    "financial_consistency",
    "price_and_date",
    "blank_over_wrong",
    "contract_validation",
    "semantic_consistency",
    "verdict_policy",
    "cross_artifact_consistency",
}
QUALITY_STATUS_SEVERITY = {
    "PASS": 0,
    "SKIP": 0,
    "PASS_WITH_FLAGS": 1,
    "CRITICAL_FLAG": 2,
    "FAIL": 3,
}
CRITIC_REVIEW_ALLOWED_OVERALL = {"PASS", "PASS_WITH_FLAGS", "FAIL"}
CRITIC_REVIEW_ALLOWED_ITEM_STATUSES = {"PASS", "PASS_WITH_FLAGS", "FAIL", "SKIP"}
QUALITY_ITEM_DELIVERY_IMPACTS = {"none", "historical_flag_only", "non_blocking_flag", "delivery_blocking_flag"}
QUALITY_ITEM_SEVERITIES = {"NONE", "MINOR", "MAJOR", "BLOCKER"}
QUALITY_ITEM_SEVERITY_RANK = {
    "NONE": 0,
    "MINOR": 1,
    "MAJOR": 2,
    "BLOCKER": 3,
}
VERDICT_ALIASES = {
    "overweight": "overweight",
    "비중확대": "overweight",
    "neutral": "neutral",
    "중립": "neutral",
    "underweight": "underweight",
    "비중축소": "underweight",
    "watch": "watch",
    "관찰": "watch",
}
MODE_ALLOWED_VERDICT_CATEGORIES = {
    "A": {"overweight", "neutral", "underweight"},
    "B": {"overweight", "neutral", "underweight", "watch"},
    "C": {"overweight", "neutral", "underweight", "watch"},
    "D": {"overweight", "neutral", "underweight", "watch"},
}
SCHEMA_ARTIFACT_TYPES = {
    "run-manifest",
    "research-plan",
    "validated-data",
    "analysis-result",
    "quality-report",
    "snapshot",
    "patch-plan",
    "analysis-patch",
    "patch-loop-result",
}
FETCHED_ARTIFACT_TYPES = {
    "tier1-raw",
    "tier2-raw",
    "dart-api-raw",
    "yfinance-raw",
    "fred-snapshot",
}
FETCHED_ARTIFACT_FILENAMES = {f"{artifact_type}.json" for artifact_type in FETCHED_ARTIFACT_TYPES}
UNSANITIZED_FETCHED_CONTENT_FLAG = "unsanitized fetched content (sanitizer block missing)"
EMPTY_VALUES = (None, "", [], {})
MODE_C_REQUIRED_SECTIONS = (
    "variant_view_q1",
    "variant_view_q2",
    "variant_view_q3",
    "precision_risks",
    "valuation_metrics",
    "dcf_analysis",
    "macro_context",
    "peer_comparison",
    "analyst_coverage",
    "qoe_summary",
    "portfolio_strategy",
    "what_would_make_me_wrong",
)
MODE_D_REQUIRED_SECTIONS = (
    "executive_summary",
    "business_overview",
    "financial_performance",
    "valuation_analysis",
    "variant_view_q1",
    "variant_view_q2",
    "variant_view_q3",
    "variant_view_q4",
    "variant_view_q5",
    "precision_risks",
    "investment_scenarios",
    "peer_comparison",
    "management_governance",
    "quality_of_earnings",
    "what_would_make_me_wrong",
    "appendix_data_sources",
)


def load_schema(schema_name: str, base_dir: str | Path | None = None) -> dict[str, Any]:
    root = find_repo_root(base_dir or Path.cwd())
    schema_path = root / SCHEMA_DIR / f"{schema_name}.schema.json"
    with open(schema_path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _type_matches(value: Any, expected_type: str) -> bool:
    if expected_type == "object":
        return isinstance(value, dict)
    if expected_type == "array":
        return isinstance(value, list)
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "null":
        return value is None
    return True


def _validate_instance(instance: Any, schema: dict[str, Any], path: str, errors: list[str]) -> None:
    expected_type = schema.get("type")
    if expected_type is not None:
        allowed_types = expected_type if isinstance(expected_type, list) else [expected_type]
        if not any(_type_matches(instance, item) for item in allowed_types):
            errors.append(f"{path}: expected type {allowed_types}, got {type(instance).__name__}")
            return

    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: {instance!r} is not one of {schema['enum']}")

    if "const" in schema and instance != schema["const"]:
        errors.append(f"{path}: expected constant {schema['const']!r}, got {instance!r}")

    if isinstance(instance, str) and "pattern" in schema:
        if not re.fullmatch(schema["pattern"], instance):
            errors.append(f"{path}: {instance!r} does not match pattern {schema['pattern']}")

    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append(f"{path}: {instance} is below minimum {schema['minimum']}")
        if "maximum" in schema and instance > schema["maximum"]:
            errors.append(f"{path}: {instance} is above maximum {schema['maximum']}")

    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errors.append(f"{path}: expected at least {schema['minItems']} items, got {len(instance)}")
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            errors.append(f"{path}: expected at most {schema['maxItems']} items, got {len(instance)}")
        item_schema = schema.get("items")
        if item_schema:
            for index, item in enumerate(instance):
                _validate_instance(item, item_schema, f"{path}[{index}]", errors)
        return

    if isinstance(instance, dict):
        required = schema.get("required", [])
        for key in required:
            if key not in instance:
                errors.append(f"{path}: missing required key {key!r}")

        properties = schema.get("properties", {})
        for key, prop_schema in properties.items():
            if key in instance:
                _validate_instance(instance[key], prop_schema, f"{path}.{key}", errors)

        additional_properties = schema.get("additionalProperties", True)
        if isinstance(additional_properties, dict):
            for key, value in instance.items():
                if key not in properties:
                    _validate_instance(value, additional_properties, f"{path}.{key}", errors)
        elif additional_properties is False:
            for key in instance:
                if key not in properties:
                    errors.append(f"{path}: unexpected key {key!r}")


def validate_schema(instance: Any, schema: dict[str, Any]) -> list[str]:
    try:
        import jsonschema  # type: ignore
    except ImportError:
        errors: list[str] = []
        _validate_instance(instance, schema, "$", errors)
        return errors

    validator = jsonschema.Draft7Validator(schema)
    return [f"{'/'.join(map(str, error.absolute_path)) or '$'}: {error.message}" for error in validator.iter_errors(instance)]


def validate_metric_mapping(mapping: dict[str, Any], market: str | None = None, path: str = "$.validated_metrics") -> list[str]:
    errors: list[str] = []
    for metric_name, entry in mapping.items():
        original_entry = entry if isinstance(entry, dict) else {"value": entry}
        original_tag = original_entry.get("display_tag") or original_entry.get("tag")
        normalized, warnings = normalize_metric_entry(metric_name, entry, market=market)
        if warnings:
            for warning in warnings:
                if "Grade D metric must have value=null" in warning or "should include exclusion_reason" in warning:
                    errors.append(f"{path}.{metric_name}: {warning}")

        display_tag = metric_display_tag(normalized)
        source_type = normalized.get("source_type")
        grade = normalized.get("grade")

        if original_tag and original_tag != display_tag:
            errors.append(
                f"{path}.{metric_name}: non-canonical display_tag {original_tag} should be normalized to {display_tag}"
            )
        if grade in {"A", "B", "C"}:
            for required_key in ("source_type", "source_authority", "display_tag"):
                if required_key not in original_entry:
                    errors.append(f"{path}.{metric_name}: missing explicit {required_key}")

        if display_tag and display_tag not in CANONICAL_DISPLAY_TAGS:
            errors.append(f"{path}.{metric_name}: non-canonical display_tag {display_tag}")
        if source_type and source_type not in CANONICAL_SOURCE_TYPES:
            errors.append(f"{path}.{metric_name}: non-canonical source_type {source_type}")
        if source_type == "company_release" and display_tag == "[Filing]":
            errors.append(f"{path}.{metric_name}: issuer release cannot use [Filing]")
        if grade == "D":
            if normalized.get("value") is not None:
                errors.append(f"{path}.{metric_name}: Grade D metric must have null value")
            if not normalized.get("exclusion_reason"):
                errors.append(f"{path}.{metric_name}: Grade D metric missing exclusion_reason")
        elif grade in {"A", "B", "C"}:
            if not display_tag:
                errors.append(f"{path}.{metric_name}: verified metric missing display_tag")
            if not normalized.get("sources"):
                errors.append(f"{path}.{metric_name}: verified metric missing sources")
    return errors


def _metric_value(entry: Any) -> float | None:
    if isinstance(entry, dict):
        return extract_numeric_value(entry.get("value"))
    return extract_numeric_value(entry)


def _metric_unit(entry: Any) -> str | None:
    if not isinstance(entry, dict):
        return None
    unit = entry.get("unit")
    if unit in (None, ""):
        return None
    normalized = re.sub(r"[^0-9A-Za-z가-힣%]+", "_", str(unit).strip().lower()).strip("_")
    return normalized or None


def _is_close(actual: float, expected: float, *, abs_tol: float, rel_tol: float = 0.01) -> bool:
    return abs(actual - expected) <= max(abs_tol, abs(expected) * rel_tol)


def _convert_unit_value(value: float | None, unit: str | None) -> float | None:
    if value is None:
        return None
    if unit is None:
        return value
    multiplier = UNIT_MULTIPLIERS.get(unit)
    if multiplier is None:
        return None
    return value * multiplier


def _ratio_from_entries(numerator: Any, denominator: Any) -> float | None:
    numerator_value = _metric_value(numerator)
    denominator_value = _metric_value(denominator)
    if numerator_value is None or denominator_value in (None, 0):
        return None

    numerator_unit = _metric_unit(numerator)
    denominator_unit = _metric_unit(denominator)
    if numerator_unit and denominator_unit and numerator_unit == denominator_unit:
        return numerator_value / denominator_value

    numerator_converted = _convert_unit_value(numerator_value, numerator_unit)
    denominator_converted = _convert_unit_value(denominator_value, denominator_unit)
    if numerator_converted is None or denominator_converted in (None, 0):
        return None
    return numerator_converted / denominator_converted


def validate_formula_metrics(
    metrics: dict[str, Any],
    *,
    path: str,
    price_override: Any = None,
) -> list[str]:
    errors: list[str] = []
    price_entry = metrics.get("price_at_analysis") or metrics.get("price")
    price = extract_numeric_value(price_override if price_override is not None else price_entry)

    shares_entry = metrics.get("diluted_shares")
    shares_value = _metric_value(shares_entry)
    shares_unit = _metric_unit(shares_entry)

    market_cap_entry = metrics.get("market_cap")
    market_cap_value = _metric_value(market_cap_entry)
    market_cap_unit = _metric_unit(market_cap_entry)

    if (
        price is not None
        and shares_value is not None
        and market_cap_value is not None
        and shares_unit in MILLION_SHARE_UNITS
        and market_cap_unit in MILLION_CURRENCY_UNITS
    ):
        expected_market_cap = price * shares_value
        if not _is_close(market_cap_value, expected_market_cap, abs_tol=1.0, rel_tol=0.005):
            errors.append(
                f"{path}.market_cap.value: expected {expected_market_cap:.2f} from price × diluted_shares, got {market_cap_value}"
            )

    eps_entry = metrics.get("eps_ttm")
    eps = _metric_value(eps_entry)
    if eps is None and shares_value not in (None, 0):
        net_income_value = _metric_value(metrics.get("net_income_ttm"))
        if net_income_value is not None:
            eps = net_income_value / shares_value

    pe_value = _metric_value(metrics.get("pe_ratio"))
    if price is not None and eps not in (None, 0) and pe_value is not None:
        expected_pe = price / eps
        if not _is_close(pe_value, expected_pe, abs_tol=0.1, rel_tol=0.01):
            errors.append(
                f"{path}.pe_ratio.value: expected {expected_pe:.2f} from price ÷ EPS, got {pe_value}"
            )

    fcf_yield_value = _metric_value(metrics.get("fcf_yield"))
    if fcf_yield_value is not None and market_cap_entry is not None:
        fcf_to_market_cap = _ratio_from_entries(metrics.get("fcf_ttm"), market_cap_entry)
        if fcf_to_market_cap is not None:
            expected_fcf_yield = fcf_to_market_cap * 100
            if not _is_close(fcf_yield_value, expected_fcf_yield, abs_tol=0.1, rel_tol=0.02):
                errors.append(
                    f"{path}.fcf_yield.value: expected {expected_fcf_yield:.2f}% from fcf_ttm ÷ market_cap, got {fcf_yield_value}"
                )

    return errors


def validate_run_context(data: dict[str, Any], path: str = "$.run_context") -> list[str]:
    errors: list[str] = []
    run_context = data.get("run_context")
    if not isinstance(run_context, dict):
        return [f"{path}: missing or invalid run_context object"]

    required = ["run_id", "artifact_root", "ticker"]
    for key in required:
        if not run_context.get(key):
            errors.append(f"{path}.{key}: missing required run context field")

    artifact_root = run_context.get("artifact_root")
    normalized_root = artifact_root.replace("\\", "/") if isinstance(artifact_root, str) else ""
    if artifact_root and "output/runs/" not in normalized_root:
        errors.append(f"{path}.artifact_root: expected run-local artifact path, got {artifact_root}")

    return errors


def validate_scenarios(data: dict[str, Any], path: str = "$.scenarios") -> list[str]:
    errors: list[str] = []
    scenarios = data.get("scenarios")
    if not isinstance(scenarios, dict):
        return errors

    probabilities = {}
    for case in ("bull", "base", "bear"):
        case_data = scenarios.get(case)
        if not isinstance(case_data, dict):
            errors.append(f"{path}.{case}: missing scenario object")
            continue
        probability = extract_numeric_value(case_data.get("probability"))
        probabilities[case] = probability

    if all(prob is not None for prob in probabilities.values()):
        total = sum(probabilities.values())  # type: ignore[arg-type]
        if abs(total - 1.0) > 0.01:
            errors.append(f"{path}: scenario probabilities must sum to 1.0 (+/- 0.01), got {total:.4f}")
        base = probabilities.get("base")
        bull = probabilities.get("bull")
        bear = probabilities.get("bear")
        if base is not None and bull is not None and bear is not None:
            if not (base >= bull and base >= bear):
                errors.append(f"{path}: base probability should be the highest or tied highest")

    return errors


def validate_analysis_semantics(data: dict[str, Any], path: str = "$") -> list[str]:
    errors: list[str] = []
    scenarios = data.get("scenarios")
    if not isinstance(scenarios, dict):
        return errors

    price = extract_numeric_value(data.get("price_at_analysis"))
    targets: dict[str, float | None] = {}
    returns: dict[str, float | None] = {}
    probabilities: dict[str, float | None] = {}

    for case in ("bull", "base", "bear"):
        case_data = scenarios.get(case)
        if not isinstance(case_data, dict):
            continue
        target = extract_numeric_value(case_data.get("target"))
        ret = extract_numeric_value(case_data.get("return_pct"))
        prob = extract_numeric_value(case_data.get("probability"))
        targets[case] = target
        returns[case] = ret
        probabilities[case] = prob

        if price not in (None, 0) and target is not None and ret is not None:
            expected_return = ((target - price) / price) * 100
            if not _is_close(ret, expected_return, abs_tol=0.15, rel_tol=0.01):
                errors.append(
                    f"{path}.scenarios.{case}.return_pct: expected {expected_return:.2f} from target/price, got {ret}"
                )

    if all(targets.get(case) is not None for case in ("bull", "base", "bear")):
        if not (
            targets["bull"] >= targets["base"] >= targets["bear"]  # type: ignore[operator]
        ):
            errors.append(f"{path}.scenarios: expected bull.target >= base.target >= bear.target")

    bull_return = returns.get("bull")
    base_return = returns.get("base")
    bear_return = returns.get("bear")
    bull_prob = probabilities.get("bull")
    base_prob = probabilities.get("base")
    bear_prob = probabilities.get("bear")
    rr_score = extract_numeric_value(data.get("rr_score"))

    if (
        bull_return is not None
        and base_return is not None
        and bear_return not in (None, 0)
        and bull_prob is not None
        and base_prob is not None
        and bear_prob not in (None, 0)
        and rr_score is not None
    ):
        expected_rr_score = ((bull_return * bull_prob) + (base_return * base_prob)) / abs(bear_return * bear_prob)
        if not _is_close(rr_score, expected_rr_score, abs_tol=0.05, rel_tol=0.01):
            errors.append(
                f"{path}.rr_score: expected {expected_rr_score:.2f} from scenario formula, got {rr_score}"
            )

    return errors


def validate_analysis_completeness(data: dict[str, Any], path: str = "$") -> list[str]:
    output_mode = str(data.get("output_mode") or "").upper()
    sections = data.get("sections")
    errors: list[str] = []

    if output_mode not in {"C", "D"}:
        return errors
    if not isinstance(sections, dict):
        return [f"{path}.sections: Mode {output_mode} completeness requires sections object"]

    required_sections = MODE_C_REQUIRED_SECTIONS if output_mode == "C" else MODE_D_REQUIRED_SECTIONS
    for key in required_sections:
        if sections.get(key) in EMPTY_VALUES:
            errors.append(f"{path}.sections.{key}: Mode {output_mode} completeness missing required section")

    risks = sections.get("precision_risks")
    if not isinstance(risks, list) or len(risks) < 3:
        errors.append(f"{path}.sections.precision_risks: Mode {output_mode} completeness requires at least 3 risks")

    if output_mode == "C":
        dcf = sections.get("dcf_analysis")
        if dcf not in EMPTY_VALUES and not isinstance(dcf, dict):
            errors.append(f"{path}.sections.dcf_analysis: Mode C completeness requires DCF object")
        elif isinstance(dcf, dict):
            for key in ("base", "bull", "bear", "methodology"):
                if dcf.get(key) in EMPTY_VALUES:
                    errors.append(f"{path}.sections.dcf_analysis.{key}: Mode C completeness missing DCF field")
        analyst_coverage = sections.get("analyst_coverage")
        if analyst_coverage not in EMPTY_VALUES and not isinstance(analyst_coverage, dict):
            errors.append(f"{path}.sections.analyst_coverage: Mode C completeness requires coverage object")
        elif isinstance(analyst_coverage, dict):
            if analyst_coverage.get("consensus") in EMPTY_VALUES and analyst_coverage.get("price_target") in EMPTY_VALUES:
                errors.append(
                    f"{path}.sections.analyst_coverage: Mode C completeness requires consensus or price_target"
                )

    if output_mode == "D":
        qoe = sections.get("quality_of_earnings")
        if qoe not in EMPTY_VALUES and not isinstance(qoe, dict):
            errors.append(f"{path}.sections.quality_of_earnings: Mode D completeness requires QoE object")
        elif isinstance(qoe, dict) and qoe.get("narrative") in EMPTY_VALUES:
            errors.append(f"{path}.sections.quality_of_earnings.narrative: Mode D completeness missing QoE narrative")

    return errors


def normalize_verdict(verdict: Any) -> str | None:
    if verdict is None:
        return None
    return VERDICT_ALIASES.get(str(verdict).strip().lower())


def validate_verdict_alignment(data: dict[str, Any], path: str = "$") -> list[str]:
    errors: list[str] = []
    rr_score = extract_numeric_value(data.get("rr_score"))
    verdict = data.get("verdict")
    output_mode = str(data.get("output_mode") or "").upper()

    if verdict in (None, "") or rr_score is None:
        return errors

    normalized_verdict = normalize_verdict(verdict)
    if normalized_verdict is None:
        errors.append(f"{path}.verdict: unsupported verdict value {verdict!r}")
        return errors

    allowed_for_mode = MODE_ALLOWED_VERDICT_CATEGORIES.get(output_mode)
    if allowed_for_mode and normalized_verdict not in allowed_for_mode:
        errors.append(
            f"{path}.verdict: {verdict!r} is not allowed for output_mode {output_mode}"
        )
        return errors

    if output_mode in {"A", "C", "D"}:
        if rr_score > 3.0 and normalized_verdict != "overweight":
            errors.append(
                f"{path}.verdict: R/R {rr_score:.2f} requires Overweight/비중확대 for mode {output_mode}, got {verdict!r}"
            )
        elif 1.0 <= rr_score <= 3.0 and normalized_verdict not in {"neutral", "watch"}:
            errors.append(
                f"{path}.verdict: R/R {rr_score:.2f} requires Neutral/Watch (중립/관찰) for mode {output_mode}, got {verdict!r}"
            )
        elif rr_score < 1.0 and normalized_verdict != "underweight":
            errors.append(
                f"{path}.verdict: R/R {rr_score:.2f} requires Underweight/비중축소 for mode {output_mode}, got {verdict!r}"
            )
        return errors

    if output_mode == "B":
        if rr_score > 3.0 and normalized_verdict == "underweight":
            errors.append(
                f"{path}.verdict: R/R {rr_score:.2f} is incompatible with Underweight/비중축소 in mode B"
            )
        elif rr_score < 1.0 and normalized_verdict == "overweight":
            errors.append(
                f"{path}.verdict: R/R {rr_score:.2f} is incompatible with Overweight/비중확대 in mode B"
            )

    return errors


def validate_cross_artifact_consistency(
    research_plan: dict[str, Any] | None,
    validated_data: dict[str, Any] | None,
    analysis_result: dict[str, Any] | None,
) -> list[str]:
    errors: list[str] = []
    payloads = [("research-plan", research_plan), ("validated-data", validated_data), ("analysis-result", analysis_result)]
    present_payloads = [(label, payload) for label, payload in payloads if isinstance(payload, dict)]

    for field in ("ticker", "market", "data_mode", "output_mode", "analysis_date"):
        values = {}
        for label, payload in present_payloads:
            value = payload.get(field)
            if value is not None:
                values[label] = value
        if len(set(values.values())) > 1:
            errors.append(f"cross-artifact.{field}: inconsistent values {values}")

    run_context_fields = ("run_id", "artifact_root", "ticker")
    run_context_values: dict[str, dict[str, Any]] = {}
    for label, payload in present_payloads:
        run_context = payload.get("run_context")
        if isinstance(run_context, dict):
            run_context_values[label] = {field: run_context.get(field) for field in run_context_fields}
    for field in run_context_fields:
        values = {
            label: context.get(field)
            for label, context in run_context_values.items()
            if context.get(field) is not None
        }
        if len(set(values.values())) > 1:
            errors.append(f"cross-artifact.run_context.{field}: inconsistent values {values}")

    if not isinstance(validated_data, dict) or not isinstance(analysis_result, dict):
        return errors

    validated_metrics = validated_data.get("validated_metrics")
    analysis_metrics = analysis_result.get("key_metrics")
    if not isinstance(validated_metrics, dict) or not isinstance(analysis_metrics, dict):
        return errors

    validated_price_entry = validated_metrics.get("price_at_analysis") or validated_metrics.get("price")
    validated_price = _metric_value(validated_price_entry)
    analysis_price = extract_numeric_value(analysis_result.get("price_at_analysis"))
    if validated_price is not None and analysis_price is not None:
        if not _is_close(analysis_price, validated_price, abs_tol=0.05, rel_tol=0.001):
            errors.append(
                f"cross-artifact.price_at_analysis: analysis-result {analysis_price} does not match validated-data {validated_price}"
            )

    for metric_name, analysis_entry in analysis_metrics.items():
        validated_entry = validated_metrics.get(metric_name)
        if not isinstance(validated_entry, dict) or not isinstance(analysis_entry, dict):
            continue

        analysis_value = _metric_value(analysis_entry)
        validated_value = _metric_value(validated_entry)
        if analysis_value is not None and validated_value is not None:
            if not _is_close(analysis_value, validated_value, abs_tol=0.1, rel_tol=0.01):
                errors.append(
                    f"cross-artifact.{metric_name}.value: analysis-result {analysis_value} does not match validated-data {validated_value}"
                )

        for key in ("grade", "source_type", "display_tag"):
            analysis_meta = analysis_entry.get(key)
            validated_meta = validated_entry.get(key)
            if analysis_meta is not None and validated_meta is not None and analysis_meta != validated_meta:
                errors.append(
                    f"cross-artifact.{metric_name}.{key}: analysis-result {analysis_meta!r} does not match validated-data {validated_meta!r}"
                )

    return errors


def validate_quality_report(data: dict[str, Any], path: str = "$.items") -> list[str]:
    items = data.get("items")
    if not isinstance(items, dict):
        return [f"{path}: missing or invalid items object"]

    errors: list[str] = []
    expected_core = _combine_quality_statuses([
        item_payload.get("status")
        for item_payload in items.values()
        if isinstance(item_payload, dict)
    ])
    missing = sorted(QUALITY_REPORT_CORE_ITEMS - set(items))
    for item_name in missing:
        errors.append(f"{path}: missing core quality item {item_name!r}")

    for item_name, item_payload in items.items():
        if not isinstance(item_payload, dict):
            errors.append(f"{path}.{item_name}: expected object payload")
            continue
        status = item_payload.get("status")
        if not isinstance(status, str):
            errors.append(f"{path}.{item_name}.status: missing item status")
        severity = item_payload.get("severity")
        if severity is not None and severity not in QUALITY_ITEM_SEVERITIES:
            errors.append(
                f"{path}.{item_name}.severity: {severity!r} is not one of {sorted(QUALITY_ITEM_SEVERITIES)}"
            )
        delivery_impact = item_payload.get("delivery_impact")
        if delivery_impact is not None and delivery_impact not in QUALITY_ITEM_DELIVERY_IMPACTS:
            errors.append(
                f"{path}.{item_name}.delivery_impact: {delivery_impact!r} is not one of {sorted(QUALITY_ITEM_DELIVERY_IMPACTS)}"
            )

    expected_delivery_gate = _build_expected_delivery_gate(items, data.get("critic_review") if isinstance(data.get("critic_review"), dict) else None)
    delivery_gate = data.get("delivery_gate")
    if not isinstance(delivery_gate, dict):
        errors.append("$.delivery_gate: expected object payload")
    else:
        for key in (
            "result",
            "ready_for_delivery",
            "blocking_items",
            "non_blocking_items",
            "historical_only_items",
            "critic_overall",
            "critic_delivery_impact",
        ):
            if key not in delivery_gate:
                errors.append(f"$.delivery_gate.{key}: missing required field")

        if delivery_gate.get("result") != expected_delivery_gate["result"]:
            errors.append(
                f"$.delivery_gate.result: expected {expected_delivery_gate['result']!r}, got {delivery_gate.get('result')!r}"
            )
        if delivery_gate.get("ready_for_delivery") != expected_delivery_gate["ready_for_delivery"]:
            errors.append(
                f"$.delivery_gate.ready_for_delivery: expected {expected_delivery_gate['ready_for_delivery']!r}, got {delivery_gate.get('ready_for_delivery')!r}"
            )
        for list_key in ("blocking_items", "non_blocking_items", "historical_only_items"):
            actual = delivery_gate.get(list_key)
            if not isinstance(actual, list):
                errors.append(f"$.delivery_gate.{list_key}: expected array")
            elif sorted(actual) != sorted(expected_delivery_gate[list_key]):
                errors.append(
                    f"$.delivery_gate.{list_key}: expected {expected_delivery_gate[list_key]!r}, got {actual!r}"
                )
        if delivery_gate.get("critic_overall") != expected_delivery_gate["critic_overall"]:
            errors.append(
                f"$.delivery_gate.critic_overall: expected {expected_delivery_gate['critic_overall']!r}, got {delivery_gate.get('critic_overall')!r}"
            )
        if delivery_gate.get("critic_delivery_impact") != expected_delivery_gate["critic_delivery_impact"]:
            errors.append(
                f"$.delivery_gate.critic_delivery_impact: expected {expected_delivery_gate['critic_delivery_impact']!r}, got {delivery_gate.get('critic_delivery_impact')!r}"
            )
        for optional_key in ("max_severity", "critic_severity"):
            if optional_key in delivery_gate and delivery_gate.get(optional_key) != expected_delivery_gate[optional_key]:
                errors.append(
                    f"$.delivery_gate.{optional_key}: expected {expected_delivery_gate[optional_key]!r}, got {delivery_gate.get(optional_key)!r}"
                )
        if "item_severities" in delivery_gate:
            actual_severities = delivery_gate.get("item_severities")
            if not isinstance(actual_severities, dict):
                errors.append("$.delivery_gate.item_severities: expected object")
            elif actual_severities != expected_delivery_gate["item_severities"]:
                errors.append(
                    f"$.delivery_gate.item_severities: expected {expected_delivery_gate['item_severities']!r}, got {actual_severities!r}"
                )

    critic_review = data.get("critic_review")
    feedback = data.get("feedback_for_analyst")
    if critic_review is not None:
        if not isinstance(critic_review, dict):
            errors.append("$.critic_review: expected object payload")
        else:
            reviewer = critic_review.get("reviewer")
            review_timestamp = critic_review.get("review_timestamp")
            overall = critic_review.get("overall")
            review_items = critic_review.get("items")
            if not isinstance(reviewer, str) or not reviewer:
                errors.append("$.critic_review.reviewer: missing reviewer")
            if not isinstance(review_timestamp, str) or not review_timestamp:
                errors.append("$.critic_review.review_timestamp: missing review timestamp")
            if overall not in CRITIC_REVIEW_ALLOWED_OVERALL:
                errors.append(
                    f"$.critic_review.overall: {overall!r} is not one of {sorted(CRITIC_REVIEW_ALLOWED_OVERALL)}"
                )
            critic_severity = critic_review.get("severity")
            if critic_severity is not None and critic_severity not in QUALITY_ITEM_SEVERITIES:
                errors.append(
                    f"$.critic_review.severity: {critic_severity!r} is not one of {sorted(QUALITY_ITEM_SEVERITIES)}"
                )
            if not isinstance(review_items, list) or not review_items:
                errors.append("$.critic_review.items: expected non-empty array")
            else:
                for index, review_item in enumerate(review_items):
                    if not isinstance(review_item, dict):
                        errors.append(f"$.critic_review.items[{index}]: expected object payload")
                        continue
                    item_name = review_item.get("item")
                    item_status = review_item.get("status")
                    if not isinstance(item_name, str) or not item_name:
                        errors.append(f"$.critic_review.items[{index}].item: missing item name")
                    if item_status not in CRITIC_REVIEW_ALLOWED_ITEM_STATUSES:
                        errors.append(
                            f"$.critic_review.items[{index}].status: {item_status!r} is not one of {sorted(CRITIC_REVIEW_ALLOWED_ITEM_STATUSES)}"
                        )
                    item_severity = review_item.get("severity")
                    if item_severity is not None and item_severity not in QUALITY_ITEM_SEVERITIES:
                        errors.append(
                            f"$.critic_review.items[{index}].severity: {item_severity!r} is not one of {sorted(QUALITY_ITEM_SEVERITIES)}"
                        )
                    if item_status == "FAIL":
                        if not review_item.get("problem"):
                            errors.append(f"$.critic_review.items[{index}].problem: required when status=FAIL")
                        if not review_item.get("fix"):
                            errors.append(f"$.critic_review.items[{index}].fix: required when status=FAIL")

            expected_critic_overall = _combine_critic_statuses(review_items if isinstance(review_items, list) else [])
            if overall in CRITIC_REVIEW_ALLOWED_OVERALL and overall != expected_critic_overall:
                errors.append(
                    f"$.critic_review.overall: expected {expected_critic_overall!r} from critic items, got {overall!r}"
                )

            recheck_history = critic_review.get("recheck_history")
            recheck_count = critic_review.get("recheck_count")
            if recheck_history is not None:
                if not isinstance(recheck_history, list):
                    errors.append("$.critic_review.recheck_history: expected array")
                else:
                    for index, history_item in enumerate(recheck_history):
                        if not isinstance(history_item, dict):
                            errors.append(f"$.critic_review.recheck_history[{index}]: expected object payload")
                            continue
                        review_timestamp_value = history_item.get("review_timestamp")
                        updated_items_value = history_item.get("updated_items")
                        remaining_fail_items_value = history_item.get("remaining_fail_items")
                        if not isinstance(review_timestamp_value, str) or not review_timestamp_value:
                            errors.append(
                                f"$.critic_review.recheck_history[{index}].review_timestamp: missing value"
                            )
                        if not isinstance(updated_items_value, list):
                            errors.append(f"$.critic_review.recheck_history[{index}].updated_items: expected array")
                        if not isinstance(remaining_fail_items_value, list):
                            errors.append(
                                f"$.critic_review.recheck_history[{index}].remaining_fail_items: expected array"
                            )
                    if recheck_count is not None and recheck_count != len(recheck_history):
                        errors.append(
                            f"$.critic_review.recheck_count: expected {len(recheck_history)} to match recheck_history length, got {recheck_count!r}"
                        )
            elif recheck_count not in (None, 0):
                errors.append("$.critic_review.recheck_count: must be null/0 when recheck_history is absent")

            if feedback is not None:
                if not isinstance(feedback, list):
                    errors.append("$.feedback_for_analyst: expected array")
                else:
                    for index, feedback_item in enumerate(feedback):
                        if not isinstance(feedback_item, dict):
                            errors.append(f"$.feedback_for_analyst[{index}]: expected object payload")
                            continue
                        for field in ("section", "problem", "fix"):
                            value = feedback_item.get(field)
                            if not isinstance(value, str) or not value:
                                errors.append(f"$.feedback_for_analyst[{index}].{field}: missing required field")
            elif critic_review.get("overall") == "FAIL":
                errors.append("$.feedback_for_analyst: required when critic_review.overall=FAIL")

            core_overall_result = data.get("core_overall_result")
            if core_overall_result is not None and core_overall_result != expected_core:
                errors.append(
                    f"$.core_overall_result: expected {expected_core!r} from core items, got {core_overall_result!r}"
                )

            expected_overall = _combine_quality_statuses([expected_core, critic_review.get("overall")])
            if data.get("overall_result") != expected_overall:
                errors.append(
                    f"$.overall_result: expected {expected_overall!r} after critic merge, got {data.get('overall_result')!r}"
                )
    elif feedback is not None:
        errors.append("$.feedback_for_analyst: critic_review must be present when feedback_for_analyst is provided")
    else:
        if data.get("core_overall_result") is not None and data.get("core_overall_result") != expected_core:
            errors.append(
                f"$.core_overall_result: expected {expected_core!r} from core items, got {data.get('core_overall_result')!r}"
            )
        if data.get("overall_result") != expected_core:
            errors.append(
                f"$.overall_result: expected {expected_core!r} from core items, got {data.get('overall_result')!r}"
            )

    return errors


def validate_patch_plan(data: dict[str, Any], path: str = "$") -> list[str]:
    errors: list[str] = []
    ticker = data.get("ticker")
    run_context = data.get("run_context")
    if isinstance(run_context, dict):
        context_ticker = run_context.get("ticker")
        if ticker and context_ticker and ticker != context_ticker:
            errors.append(f"{path}.run_context.ticker: expected {ticker!r} to match top-level ticker")

    output_mode = data.get("output_mode")
    pending_fix_count = data.get("pending_fix_count")
    ready_for_redelivery = data.get("ready_for_redelivery")
    current_recheck_count = data.get("current_recheck_count")
    remaining_recheck_budget = data.get("remaining_recheck_budget")
    loop_state = data.get("loop_state")
    critic_overall = data.get("critic_overall")
    tasks = data.get("tasks")
    report_output_path = data.get("report_output_path")
    quality_report_path = data.get("quality_report_path")
    analysis_result_path = data.get("analysis_result_path")

    if quality_report_path is not None and quality_report_path:
        quality_report_path_str = str(quality_report_path)
        if "quality-report" not in quality_report_path_str or not quality_report_path_str.endswith(".json"):
            errors.append(
                f"{path}.quality_report_path: expected a quality-report JSON path, got {quality_report_path!r}"
            )
    if analysis_result_path is not None and analysis_result_path:
        analysis_result_path_str = str(analysis_result_path)
        if "analysis-result" not in analysis_result_path_str or not analysis_result_path_str.endswith(".json"):
            errors.append(
                f"{path}.analysis_result_path: expected an analysis-result JSON path, got {analysis_result_path!r}"
            )

    if not isinstance(tasks, list):
        return errors

    if pending_fix_count != len(tasks):
        errors.append(f"{path}.pending_fix_count: expected {len(tasks)} to match tasks length, got {pending_fix_count!r}")
    expected_ready = len(tasks) == 0
    if ready_for_redelivery != expected_ready:
        errors.append(
            f"{path}.ready_for_redelivery: expected {expected_ready!r} when tasks length is {len(tasks)}, got {ready_for_redelivery!r}"
        )

    if isinstance(current_recheck_count, int) and isinstance(remaining_recheck_budget, int):
        if current_recheck_count < 0:
            errors.append(f"{path}.current_recheck_count: must be >= 0, got {current_recheck_count}")
        if remaining_recheck_budget < 0:
            errors.append(f"{path}.remaining_recheck_budget: must be >= 0, got {remaining_recheck_budget}")

    expected_loop_state = "ready_for_delivery"
    if tasks:
        expected_loop_state = "patch_and_recheck" if remaining_recheck_budget and remaining_recheck_budget > 0 else "patch_or_deliver_with_flags"
    if loop_state != expected_loop_state:
        errors.append(f"{path}.loop_state: expected {expected_loop_state!r}, got {loop_state!r}")

    if critic_overall == "FAIL" and not tasks:
        errors.append(f"{path}.tasks: critic_overall=FAIL requires at least one patch task")

    priorities: list[int] = []
    expected_render_step = bool(report_output_path)
    for index, task in enumerate(tasks):
        if not isinstance(task, dict):
            errors.append(f"{path}.tasks[{index}]: expected object payload")
            continue

        task_id = task.get("task_id")
        priority = task.get("priority")
        analysis_targets = task.get("analysis_targets")
        report_targets = task.get("report_targets")
        edit_scope = task.get("edit_scope")
        render_step_required = task.get("render_step_required")
        section = task.get("section")

        if isinstance(priority, int):
            priorities.append(priority)
        if not isinstance(task_id, str) or not task_id:
            errors.append(f"{path}.tasks[{index}].task_id: missing task identifier")
        if not isinstance(report_targets, list) or not report_targets:
            errors.append(f"{path}.tasks[{index}].report_targets: expected non-empty array")
        if not isinstance(analysis_targets, list):
            errors.append(f"{path}.tasks[{index}].analysis_targets: expected array")
            analysis_targets = []
        if not isinstance(section, str) or not section:
            errors.append(f"{path}.tasks[{index}].section: missing section label")

        if edit_scope == "analysis_json_and_render" and not analysis_targets:
            errors.append(
                f"{path}.tasks[{index}].edit_scope: analysis_json_and_render requires at least one analysis target"
            )
        if edit_scope == "report_render_only" and analysis_targets:
            errors.append(
                f"{path}.tasks[{index}].edit_scope: report_render_only cannot declare analysis targets"
            )
        if render_step_required != expected_render_step:
            errors.append(
                f"{path}.tasks[{index}].render_step_required: expected {expected_render_step!r} from report_output_path, got {render_step_required!r}"
            )

        if output_mode == "D" and isinstance(analysis_targets, list):
            normalized_targets = set(analysis_targets)
            if "Section 9" in str(section) and "sections.quality_of_earnings" not in normalized_targets:
                errors.append(
                    f"{path}.tasks[{index}].analysis_targets: Section 9 fixes should target sections.quality_of_earnings in Mode D"
                )
            if "Section 5" in str(section) and "sections.precision_risks" not in normalized_targets:
                errors.append(
                    f"{path}.tasks[{index}].analysis_targets: Section 5 fixes should target sections.precision_risks in Mode D"
                )

    if priorities and sorted(priorities) != list(range(1, len(priorities) + 1)):
        errors.append(f"{path}.tasks: priorities must be consecutive starting at 1, got {priorities!r}")

    return errors


def validate_analysis_patch(data: dict[str, Any], path: str = "$") -> list[str]:
    errors: list[str] = []
    patch_plan_path = data.get("patch_plan_path")
    source_analysis_result_path = data.get("source_analysis_result_path")
    target_analysis_result_path = data.get("target_analysis_result_path")
    applied_by = data.get("applied_by")
    applied_at = data.get("applied_at")

    if not isinstance(patch_plan_path, str) or "patch-plan" not in patch_plan_path or not patch_plan_path.endswith(".json"):
        errors.append(f"{path}.patch_plan_path: expected a patch-plan JSON path, got {patch_plan_path!r}")
        patch_plan_path = None
    if not isinstance(source_analysis_result_path, str) or "analysis-result" not in source_analysis_result_path or not source_analysis_result_path.endswith(".json"):
        errors.append(
            f"{path}.source_analysis_result_path: expected an analysis-result JSON path, got {source_analysis_result_path!r}"
        )
    if not isinstance(target_analysis_result_path, str) or "analysis-result" not in target_analysis_result_path or not target_analysis_result_path.endswith(".json"):
        errors.append(
            f"{path}.target_analysis_result_path: expected an analysis-result JSON path, got {target_analysis_result_path!r}"
        )
    if not isinstance(applied_by, str) or not applied_by:
        errors.append(f"{path}.applied_by: missing executor identifier")
    if not isinstance(applied_at, str) or not applied_at:
        errors.append(f"{path}.applied_at: missing applied timestamp")

    if patch_plan_path:
        patch_plan_file = Path(patch_plan_path)
        if not patch_plan_file.is_absolute():
            patch_plan_file = find_repo_root(Path.cwd()) / patch_plan_file
        if not patch_plan_file.exists():
            errors.append(f"{path}.patch_plan_path: referenced patch-plan file does not exist at {patch_plan_path!r}")
        else:
            patch_plan = load_json_file(patch_plan_file)
            errors.extend(validate_against_patch_plan(data, patch_plan, path=path))

    return errors


def validate_patch_loop_result(data: dict[str, Any], path: str = "$") -> list[str]:
    errors: list[str] = []
    render = data.get("render") if isinstance(data.get("render"), dict) else {}
    recheck = data.get("recheck") if isinstance(data.get("recheck"), dict) else {}
    next_patch_plan = data.get("next_patch_plan") if isinstance(data.get("next_patch_plan"), dict) else {}
    quality_gate = data.get("quality_gate") if isinstance(data.get("quality_gate"), dict) else {}

    render_required = render.get("required")
    render_status = render.get("status")
    report_output_path = render.get("report_output_path")
    if render_required is False and render_status != "not_requested":
        errors.append(f"{path}.render.status: expected 'not_requested' when render.required is false")
    if render_required is True and render_status == "not_requested":
        errors.append(f"{path}.render.status: render.required=true cannot use not_requested status")
    if render_status == "rendered" and not report_output_path:
        errors.append(f"{path}.render.report_output_path: required when render.status=rendered")
    if render_status == "manual_render_required" and not report_output_path:
        errors.append(f"{path}.render.report_output_path: required when render.status=manual_render_required")

    recheck_status = recheck.get("status")
    remaining_fail_count = recheck.get("remaining_fail_count")
    critic_overall_after = recheck.get("critic_overall_after")
    if recheck_status == "not_run" and recheck.get("quality_report_updated") is not False:
        errors.append(f"{path}.recheck.quality_report_updated: expected false when recheck.status=not_run")
    if recheck_status == "applied" and recheck.get("quality_report_updated") is not True:
        errors.append(f"{path}.recheck.quality_report_updated: expected true when recheck.status=applied")
    if critic_overall_after == "FAIL" and remaining_fail_count == 0:
        errors.append(f"{path}.recheck.remaining_fail_count: expected > 0 when critic_overall_after=FAIL")
    if critic_overall_after in {"PASS", "PASS_WITH_FLAGS"} and remaining_fail_count not in (0, None):
        errors.append(f"{path}.recheck.remaining_fail_count: expected 0 when critic_overall_after={critic_overall_after}")

    next_pending = next_patch_plan.get("pending_fix_count")
    next_ready = next_patch_plan.get("ready_for_redelivery")
    next_loop_state = next_patch_plan.get("loop_state")
    if next_ready is True and next_pending not in (0, None):
        errors.append(f"{path}.next_patch_plan.pending_fix_count: expected 0 when ready_for_redelivery=true")
    if next_ready is False and next_pending == 0:
        errors.append(f"{path}.next_patch_plan.ready_for_redelivery: expected true when pending_fix_count=0")
    if next_ready is True and next_loop_state != "ready_for_delivery":
        errors.append(f"{path}.next_patch_plan.loop_state: expected ready_for_delivery when next patch plan is ready")

    overall_result = quality_gate.get("overall_result")
    delivery_gate_result = quality_gate.get("delivery_gate_result")
    delivery_ready = quality_gate.get("delivery_ready")
    if delivery_ready:
        if delivery_gate_result != "PASS":
            errors.append(f"{path}.quality_gate.delivery_ready: requires delivery_gate_result=PASS")
        if next_ready is not True:
            errors.append(f"{path}.quality_gate.delivery_ready: requires next_patch_plan.ready_for_redelivery=true")
        if render_status not in {"not_requested", "rendered"}:
            errors.append(f"{path}.quality_gate.delivery_ready: incompatible with render.status={render_status!r}")
    if delivery_gate_result == "BLOCKED" and delivery_ready:
        errors.append(f"{path}.quality_gate.delivery_ready: must be false when delivery_gate_result=BLOCKED")
    if delivery_gate_result == "PASS" and overall_result not in {"PASS", "PASS_WITH_FLAGS"}:
        errors.append(f"{path}.quality_gate.delivery_gate_result: PASS is inconsistent with overall_result={overall_result!r}")

    return errors


def _combine_quality_statuses(statuses: list[Any]) -> str:
    normalized = [status for status in statuses if status in QUALITY_STATUS_SEVERITY]
    if not normalized:
        return "PASS"
    return max(normalized, key=lambda item: QUALITY_STATUS_SEVERITY[item])


def _combine_critic_statuses(items: list[Any]) -> str:
    severities = {
        "PASS": 0,
        "SKIP": 0,
        "PASS_WITH_FLAGS": 1,
        "FAIL": 2,
    }
    normalized = [
        item.get("status")
        for item in items
        if isinstance(item, dict) and item.get("status") in severities
    ]
    if not normalized:
        return "PASS"
    return max(normalized, key=lambda item: severities[item])


def _infer_delivery_impact(item_name: str, item_payload: dict[str, Any]) -> str:
    severity = _infer_delivery_severity(item_name, item_payload)
    if severity == "NONE":
        return "none"
    if item_name == "legacy_migration":
        return "historical_flag_only"
    if severity == "BLOCKER":
        return "delivery_blocking_flag"

    explicit = item_payload.get("delivery_impact")
    if explicit in {"historical_flag_only", "non_blocking_flag"}:
        return explicit
    return "non_blocking_flag"


def _infer_delivery_severity(item_name: str, item_payload: dict[str, Any]) -> str:
    explicit = item_payload.get("severity")
    if explicit in QUALITY_ITEM_SEVERITIES:
        return explicit

    explicit_impact = item_payload.get("delivery_impact")
    status = item_payload.get("status")
    if explicit_impact == "delivery_blocking_flag":
        return "BLOCKER"
    if explicit_impact in {"historical_flag_only", "non_blocking_flag"}:
        return "MAJOR" if status in {"FAIL", "CRITICAL_FLAG"} else "MINOR"

    if item_name == "legacy_migration" and status not in {"PASS", "SKIP", None}:
        return "MINOR"
    if status in {"PASS", "SKIP", None}:
        return "NONE"
    if status == "PASS_WITH_FLAGS":
        return "MINOR"
    return "BLOCKER"


def _critic_delivery_severity(critic_review: dict[str, Any] | None) -> str:
    if not isinstance(critic_review, dict):
        return "NONE"
    explicit = critic_review.get("severity")
    if explicit in QUALITY_ITEM_SEVERITIES:
        return explicit

    item_severities: list[str] = []
    items = critic_review.get("items")
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            item_severities.append(_infer_delivery_severity(str(item.get("item") or "critic_item"), item))
    if item_severities:
        return max(item_severities, key=lambda value: QUALITY_ITEM_SEVERITY_RANK[value])

    overall = critic_review.get("overall")
    if overall == "FAIL":
        return "BLOCKER"
    if overall == "PASS_WITH_FLAGS":
        return "MINOR"
    return "NONE"


def _delivery_impact_from_severity(severity: str, *, historical: bool = False) -> str:
    if severity == "BLOCKER":
        return "delivery_blocking_flag"
    if severity in {"MAJOR", "MINOR"}:
        return "historical_flag_only" if historical else "non_blocking_flag"
    return "none"


def _critic_delivery_impact(critic_review: dict[str, Any] | None) -> str:
    return _delivery_impact_from_severity(_critic_delivery_severity(critic_review))


def _build_expected_delivery_gate(items: dict[str, Any], critic_review: dict[str, Any] | None = None) -> dict[str, Any]:
    blocking_items: list[str] = []
    non_blocking_items: list[str] = []
    historical_only_items: list[str] = []
    item_severities: dict[str, str] = {}

    for item_name, item_payload in items.items():
        if not isinstance(item_payload, dict):
            continue
        severity = _infer_delivery_severity(item_name, item_payload)
        if severity == "NONE":
            continue
        item_severities[item_name] = severity
        impact = _infer_delivery_impact(item_name, item_payload)
        if impact == "delivery_blocking_flag":
            blocking_items.append(item_name)
        elif impact == "non_blocking_flag":
            non_blocking_items.append(item_name)
        elif impact == "historical_flag_only":
            historical_only_items.append(item_name)

    critic_severity = _critic_delivery_severity(critic_review)
    critic_impact = _critic_delivery_impact(critic_review)
    critic_overall = critic_review.get("overall") if isinstance(critic_review, dict) else None
    if critic_impact == "delivery_blocking_flag":
        blocking_items.append("critic_review")
    elif critic_impact == "non_blocking_flag":
        non_blocking_items.append("critic_review")

    all_severities = list(item_severities.values())
    if critic_severity != "NONE":
        all_severities.append(critic_severity)
    max_severity = max(all_severities, key=lambda value: QUALITY_ITEM_SEVERITY_RANK[value]) if all_severities else "NONE"

    result = "BLOCKED" if blocking_items else "PASS"
    return {
        "result": result,
        "ready_for_delivery": result == "PASS",
        "blocking_items": blocking_items,
        "non_blocking_items": non_blocking_items,
        "historical_only_items": historical_only_items,
        "max_severity": max_severity,
        "item_severities": item_severities,
        "critic_overall": critic_overall,
        "critic_severity": critic_severity,
        "critic_delivery_impact": critic_impact,
    }


def validate_artifact_data(
    artifact_type: str,
    data: dict[str, Any],
    base_dir: str | Path | None = None,
) -> list[str]:
    if artifact_type in FETCHED_ARTIFACT_TYPES:
        return []
    if artifact_type not in SCHEMA_ARTIFACT_TYPES:
        raise ValueError(f"unsupported artifact_type: {artifact_type}")

    schema = load_schema(artifact_type, base_dir=base_dir)
    errors = validate_schema(data, schema)

    if artifact_type in {"research-plan", "validated-data", "analysis-result", "quality-report", "snapshot", "patch-plan", "analysis-patch", "patch-loop-result"}:
        errors.extend(validate_run_context(data))

    market = data.get("market")
    if artifact_type == "validated-data":
        errors.extend(validate_metric_mapping(data.get("validated_metrics", {}), market=market))
        errors.extend(validate_formula_metrics(data.get("validated_metrics", {}), path="$.validated_metrics"))
    if artifact_type in {"analysis-result", "snapshot"}:
        errors.extend(validate_metric_mapping(data.get("key_metrics", {}), market=market, path="$.key_metrics"))
        errors.extend(validate_scenarios(data))
        errors.extend(validate_analysis_semantics(data))
        errors.extend(validate_verdict_alignment(data))
        errors.extend(
            validate_formula_metrics(
                data.get("key_metrics", {}),
                path="$.key_metrics",
                price_override=data.get("price_at_analysis"),
            )
        )
    if artifact_type == "analysis-result":
        errors.extend(validate_analysis_completeness(data))

    if artifact_type == "run-manifest":
        tickers = data.get("tickers", [])
        for ticker in tickers:
            if not re.fullmatch(r"[A-Z0-9]{1,10}", ticker):
                errors.append(f"$.tickers: invalid ticker token {ticker!r}")
    if artifact_type == "quality-report":
        errors.extend(validate_quality_report(data))
    if artifact_type == "patch-plan":
        errors.extend(validate_patch_plan(data))
    if artifact_type == "analysis-patch":
        errors.extend(validate_analysis_patch(data))
    if artifact_type == "patch-loop-result":
        errors.extend(validate_patch_loop_result(data))

    return errors


def _requires_sanitization_check(artifact_type: str, path: Path) -> bool:
    return artifact_type in FETCHED_ARTIFACT_TYPES or path.name in FETCHED_ARTIFACT_FILENAMES


def _has_sanitization_block(data: Any) -> bool:
    return isinstance(data, dict) and isinstance(data.get("_sanitization"), dict)


def validate_artifact_file(
    artifact_path: str | Path,
    artifact_type: str,
    base_dir: str | Path | None = None,
) -> dict[str, Any]:
    path = Path(artifact_path)
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    errors = validate_artifact_data(artifact_type, data, base_dir=base_dir or path)
    flags: list[str] = []
    security_flags: list[str] = []
    warnings: list[dict[str, str]] = []
    sanitization_required = _requires_sanitization_check(artifact_type, path)
    sanitization_present = _has_sanitization_block(data)

    if sanitization_required and not sanitization_present:
        flags.append(UNSANITIZED_FETCHED_CONTENT_FLAG)
        security_flags.append("unsanitized_fetched_content")
        warnings.append(
            {
                "code": "unsanitized_fetched_content",
                "message": UNSANITIZED_FETCHED_CONTENT_FLAG,
                "path": str(path),
            }
        )

    schema_valid = not errors
    ingestion_allowed = schema_valid and not security_flags
    overall_grade = "D" if errors or flags else "A"
    return {
        "artifact_type": artifact_type,
        "path": str(path),
        "valid": schema_valid,
        "schema_valid": schema_valid,
        "ingestion_allowed": ingestion_allowed,
        "sanitization_required": sanitization_required,
        "sanitization_present": sanitization_present,
        "errors": errors,
        "overall_grade": overall_grade,
        "flags": flags,
        "security_flags": security_flags,
        "quality_flag": flags[0] if flags else None,
        "quality_flags": flags,
        "warnings": warnings,
    }


def validate_run_directory(run_dir: str | Path, base_dir: str | Path | None = None) -> dict[str, Any]:
    path = Path(run_dir)
    base = find_repo_root(base_dir or path)
    manifest_path = path / "run-manifest.json"
    results: list[dict[str, Any]] = []
    if manifest_path.exists():
        results.append(validate_artifact_file(manifest_path, "run-manifest", base_dir=base))
        with open(manifest_path, "r", encoding="utf-8") as handle:
            manifest = json.load(handle)
        tickers = manifest.get("tickers", [])
    else:
        tickers = [child.name for child in path.iterdir() if child.is_dir()]
        results.append(
            {
                "artifact_type": "run-manifest",
                "path": str(manifest_path),
                "valid": False,
                "schema_valid": False,
                "ingestion_allowed": False,
                "errors": ["run-manifest.json is missing"],
            }
        )

    for ticker in tickers:
        ticker_dir = path / ticker
        ticker_payloads: dict[str, dict[str, Any]] = {}
        artifact_specs = {
            "research-plan": ticker_dir / "research-plan.json",
            "validated-data": ticker_dir / "validated-data.json",
            "analysis-result": ticker_dir / "analysis-result.json",
            "quality-report": ticker_dir / "quality-report.json",
        }
        optional_artifact_specs = {
            "patch-plan": ticker_dir / "patch-plan.json",
            "analysis-patch": ticker_dir / "analysis-patch.json",
            "patch-loop-result": ticker_dir / "patch-loop-result.json",
        }
        for artifact_type, artifact_path in artifact_specs.items():
            if artifact_path.exists():
                results.append(validate_artifact_file(artifact_path, artifact_type, base_dir=base))
                with open(artifact_path, "r", encoding="utf-8") as handle:
                    ticker_payloads[artifact_type] = json.load(handle)
            else:
                results.append(
                    {
                        "artifact_type": artifact_type,
                        "path": str(artifact_path),
                        "valid": False,
                        "schema_valid": False,
                        "ingestion_allowed": False,
                        "errors": ["artifact is missing"],
                    }
                )

        for artifact_type, artifact_path in optional_artifact_specs.items():
            if artifact_path.exists():
                results.append(validate_artifact_file(artifact_path, artifact_type, base_dir=base))
                with open(artifact_path, "r", encoding="utf-8") as handle:
                    ticker_payloads[artifact_type] = json.load(handle)

        cross_artifact_errors = validate_cross_artifact_consistency(
            ticker_payloads.get("research-plan"),
            ticker_payloads.get("validated-data"),
            ticker_payloads.get("analysis-result"),
        )
        if cross_artifact_errors:
            results.append(
                {
                    "artifact_type": "cross-artifact-consistency",
                    "path": str(ticker_dir),
                    "valid": False,
                    "errors": cross_artifact_errors,
                }
            )

    return {
        "run_dir": str(path),
        "valid": all(result["valid"] for result in results),
        "ingestion_allowed": all(result.get("ingestion_allowed", result["valid"]) for result in results),
        "results": results,
    }
