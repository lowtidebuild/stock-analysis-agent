from __future__ import annotations

import copy
import json
import math
import re
import zipfile
from pathlib import Path
from typing import Any

from tools.analysis_contract import extract_numeric_value, utc_now_iso
from tools.artifact_validation import (
    validate_analysis_semantics,
    validate_artifact_data,
    validate_cross_artifact_consistency,
    validate_formula_metrics,
    validate_verdict_alignment,
)

QUALITY_ITEM_STATUSES = {"PASS", "PASS_WITH_FLAGS", "CRITICAL_FLAG", "FAIL", "SKIP"}
CRITIC_OVERALL_STATUSES = {"PASS", "PASS_WITH_FLAGS", "FAIL"}
DELIVERY_IMPACTS = {"none", "historical_flag_only", "non_blocking_flag", "delivery_blocking_flag"}
STATUS_SEVERITY = {
    "PASS": 0,
    "SKIP": 0,
    "PASS_WITH_FLAGS": 1,
    "CRITICAL_FLAG": 2,
    "FAIL": 3,
}
CRITIC_ITEM_SEVERITY = {
    "PASS": 0,
    "SKIP": 0,
    "PASS_WITH_FLAGS": 1,
    "FAIL": 2,
}
CORE_GENERATED_ITEMS = (
    "contract_validation",
    "semantic_consistency",
    "verdict_policy",
    "cross_artifact_consistency",
)
BASELINE_GENERATED_ITEMS = (
    "financial_consistency",
    "price_and_date",
    "blank_over_wrong",
)
FINANCIAL_SAMPLE_PRIORITY = (
    "price_at_analysis",
    "market_cap",
    "pe_ratio",
    "fcf_yield",
    "operating_margin",
    "revenue_growth_yoy",
)
SOURCE_TAG_PATTERN = re.compile(r"\[(?:Filing|Portal|KR-Portal|Calc|Est|Macro|User)\]")
NUMBER_PATTERN = re.compile(r"(?<![A-Za-z0-9_])(?:[$₩€£]?\s*)?\d+(?:,\d{3})*(?:\.\d+)?\s*(?:%|x|bp|B|M|T|조|억|만)?")
MODE_REQUIRED_RENDERED_TERMS = {
    "C": (
        ("DCF valuation", ("dcf",)),
        ("analyst coverage", ("analyst coverage", "analyst target", "analyst rating")),
        ("chart data", ("new chart", "chart.js", "pricelabels", "pricedata")),
    ),
    "D": (
        ("executive summary", ("executive summary", "요약")),
        ("valuation", ("valuation", "밸류에이션", "가치평가")),
        ("risk", ("risk", "리스크")),
    ),
}


def load_json(path: str | Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _numeric_close(actual: float, expected: float, tolerance_pct: float = 0.01, absolute_floor: float = 0.1) -> bool:
    return abs(actual - expected) <= max(abs(expected) * tolerance_pct, absolute_floor)


def _build_status(errors: list[str], pass_with_flags: bool = False) -> str:
    if errors:
        return "FAIL"
    if pass_with_flags:
        return "PASS_WITH_FLAGS"
    return "PASS"


def _metric_entry_value(entry: Any) -> float | None:
    if isinstance(entry, dict):
        return extract_numeric_value(entry.get("value"))
    return extract_numeric_value(entry)


def _read_rendered_text(report_path: str | Path) -> tuple[str | None, str | None]:
    path = Path(report_path)
    suffix = path.suffix.lower()
    try:
        if suffix == ".docx":
            with zipfile.ZipFile(path) as archive:
                document_xml = archive.read("word/document.xml").decode("utf-8", errors="replace")
            return re.sub(r"<[^>]+>", " ", document_xml), None
        return path.read_text(encoding="utf-8", errors="replace"), None
    except Exception as exc:  # noqa: BLE001
        return None, f"Unable to read rendered output: {type(exc).__name__}: {exc}"


def _html_body_text(rendered_text: str) -> str:
    text = re.sub(r"<script\b[^>]*>.*?</script>", " ", rendered_text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<style\b[^>]*>.*?</style>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _stringify_metric_value(value: float) -> list[str]:
    candidates = {str(value)}
    if float(value).is_integer():
        int_value = int(value)
        candidates.add(str(int_value))
        candidates.add(f"{int_value:,}")
    else:
        candidates.add(f"{value:,.2f}")
        candidates.add(f"{value:.2f}")
    return sorted(candidates, key=len, reverse=True)


def _source_tag_coverage(rendered_text: str) -> dict[str, Any]:
    visible_text = _html_body_text(rendered_text)
    numbers = NUMBER_PATTERN.findall(visible_text)
    tags = SOURCE_TAG_PATTERN.findall(visible_text)
    if not numbers:
        return {"status": "PASS", "numeric_claim_count": 0, "source_tag_count": len(tags), "coverage_pct": 100.0}

    # One source tag often covers a table row with several numbers. This is a
    # coarse output-facing guardrail, not a citation parser.
    expected_tags = max(1, math.ceil(len(numbers) / 5))
    coverage_pct = min(100.0, round(len(tags) / expected_tags * 100, 1))
    status = "PASS" if len(tags) >= expected_tags else "FAIL"
    return {
        "status": status,
        "numeric_claim_count": len(numbers),
        "source_tag_count": len(tags),
        "expected_source_tags": expected_tags,
        "coverage_pct": coverage_pct,
    }


def build_rendered_output_item(
    report_path: str | Path,
    analysis: dict[str, Any],
    validated: dict[str, Any],
) -> dict[str, Any]:
    path = Path(report_path)
    errors: list[str] = []
    warnings: list[str] = []

    if not path.exists():
        return {
            "status": "FAIL",
            "report_path": str(path),
            "errors": [f"Rendered output file is missing: {path}"],
        }

    rendered_text, read_error = _read_rendered_text(path)
    if rendered_text is None:
        return {
            "status": "FAIL",
            "report_path": str(path),
            "errors": [read_error or "Rendered output could not be read"],
        }

    lower_text = rendered_text.lower()
    visible_text = _html_body_text(rendered_text)
    lower_visible_text = visible_text.lower()

    if path.suffix.lower() in {".html", ".htm"} and not re.search(r"<html\b", rendered_text, re.IGNORECASE):
        errors.append("HTML report is missing <html> root element")

    if "disclaimer" not in lower_text and "investment advice" not in lower_text and "투자 조언" not in lower_text:
        errors.append("Rendered output is missing disclaimer text")

    output_mode = str(analysis.get("output_mode") or "").upper()
    for label, candidates in MODE_REQUIRED_RENDERED_TERMS.get(output_mode, ()):
        if not any(candidate in lower_visible_text or candidate in lower_text for candidate in candidates):
            errors.append(f"Rendered output is missing required Mode {output_mode} section: {label}")

    if output_mode == "C" and path.suffix.lower() in {".html", ".htm"}:
        if "arrays are not present" in lower_text or "fixture" in lower_visible_text:
            errors.append("Mode C dashboard rendered fixture-only chart placeholder text")
        if not any(token in lower_text for token in ("new chart", "pricelabels", "pricedata", "const quarters")):
            errors.append("Mode C dashboard is missing Chart.js data initialization")

    exclusions = validated.get("exclusions") or []
    key_metrics = analysis.get("key_metrics") if isinstance(analysis.get("key_metrics"), dict) else {}
    blank_violations: list[dict[str, Any]] = []
    for exclusion in exclusions:
        metric_name = exclusion.get("metric") if isinstance(exclusion, dict) else exclusion
        if not metric_name:
            continue
        metric_entry = key_metrics.get(str(metric_name))
        metric_value = _metric_entry_value(metric_entry)
        if metric_value is None:
            continue
        if any(candidate and candidate in visible_text for candidate in _stringify_metric_value(metric_value)):
            blank_violations.append({"metric": str(metric_name), "value_found": metric_value})
    if blank_violations:
        errors.append("Rendered output displays values for metrics marked as excluded/Grade D")

    source_coverage = _source_tag_coverage(rendered_text)
    if source_coverage["status"] == "FAIL":
        warnings.append(
            "Rendered output source-tag coverage is below threshold "
            f"({source_coverage['source_tag_count']}/{source_coverage['expected_source_tags']})"
        )

    item: dict[str, Any] = {
        "status": "FAIL" if errors else ("PASS_WITH_FLAGS" if warnings else "PASS"),
        "report_path": str(path),
        "file_exists": True,
        "source_tag_coverage": source_coverage,
    }
    if blank_violations:
        item["blank_over_wrong_violations"] = blank_violations
    if errors:
        item["errors"] = errors
    if warnings:
        item["warnings"] = warnings
    return item


def _analysis_metric_value(analysis: dict[str, Any], metric_name: str) -> float | None:
    if metric_name == "price_at_analysis":
        return extract_numeric_value(analysis.get("price_at_analysis"))
    key_metrics = analysis.get("key_metrics")
    if not isinstance(key_metrics, dict):
        return None
    return _metric_entry_value(key_metrics.get(metric_name))


def _validated_metric_value(validated: dict[str, Any], metric_name: str) -> float | None:
    validated_metrics = validated.get("validated_metrics")
    if not isinstance(validated_metrics, dict):
        return None
    if metric_name == "price_at_analysis":
        return _metric_entry_value(validated_metrics.get("price_at_analysis") or validated_metrics.get("price"))
    return _metric_entry_value(validated_metrics.get(metric_name))


def build_financial_consistency_item(validated: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
    sampled_values: list[dict[str, Any]] = []
    errors: list[str] = []

    for metric_name in FINANCIAL_SAMPLE_PRIORITY:
        output_value = _analysis_metric_value(analysis, metric_name)
        source_value = _validated_metric_value(validated, metric_name)
        if output_value is None or source_value is None:
            continue

        match = _numeric_close(output_value, source_value, tolerance_pct=0.01, absolute_floor=0.1)
        sampled_values.append(
            {
                "metric": metric_name,
                "output_value": output_value,
                "source_value": source_value,
                "match": match,
            }
        )
        if not match:
            errors.append(
                f"{metric_name}: analysis-result {output_value} differs from validated-data {source_value}"
            )
        if len(sampled_values) == 3:
            break

    if not sampled_values:
        return {
            "status": "PASS_WITH_FLAGS",
            "sampled_values": [],
            "notes": ["No overlapping metrics were available for deterministic financial consistency sampling."],
        }

    item: dict[str, Any] = {
        "status": _build_status(errors),
        "sampled_values": sampled_values,
    }
    if errors:
        item["errors"] = errors
    return item


def build_price_and_date_item(validated: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    price_found = extract_numeric_value(analysis.get("price_at_analysis"))
    date_found = analysis.get("analysis_date")
    source_price = _validated_metric_value(validated, "price_at_analysis")

    if price_found is None:
        errors.append("Current price missing from analysis-result")
    elif source_price is not None and not _numeric_close(price_found, source_price, tolerance_pct=0.001, absolute_floor=0.05):
        errors.append(f"Analysis price {price_found} does not match validated price {source_price}")

    if not isinstance(date_found, str) or not date_found:
        errors.append("Analysis date missing from analysis-result")

    status = "CRITICAL_FLAG" if any("price" in error.lower() for error in errors) else _build_status(errors)
    item: dict[str, Any] = {
        "status": status,
        "price_found": price_found,
        "date_found": date_found,
    }
    if errors:
        item["errors"] = errors
    return item


def build_blank_over_wrong_item(validated: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
    exclusions = validated.get("exclusions") or []
    key_metrics = analysis.get("key_metrics") if isinstance(analysis.get("key_metrics"), dict) else {}
    checked_metrics: list[str] = []
    violations: list[dict[str, Any]] = []

    for exclusion in exclusions:
        if isinstance(exclusion, dict):
            metric_name = exclusion.get("metric")
        else:
            metric_name = exclusion
        if not metric_name:
            continue
        metric_name = str(metric_name)
        checked_metrics.append(metric_name)
        entry = key_metrics.get(metric_name)
        value = _metric_entry_value(entry)
        if value is not None:
            violations.append({"metric": metric_name, "value_found": value})

    item: dict[str, Any] = {
        "status": "FAIL" if violations else "PASS",
        "excluded_metrics_checked": checked_metrics,
        "violations_found": len(violations),
    }
    if violations:
        item["violations"] = violations
        item["errors"] = [
            f"{violation['metric']} appears with value {violation['value_found']} despite exclusion"
            for violation in violations
        ]
    return item


def build_contract_validation_item(
    research_plan: dict[str, Any],
    validated: dict[str, Any],
    analysis: dict[str, Any],
) -> dict[str, Any]:
    artifact_payloads = {
        "research-plan": research_plan,
        "validated-data": validated,
        "analysis-result": analysis,
    }
    artifact_results = {}
    all_errors: list[str] = []
    for artifact_type, payload in artifact_payloads.items():
        errors = validate_artifact_data(artifact_type, payload)
        artifact_results[artifact_type] = {
            "status": "PASS" if not errors else "FAIL",
            "error_count": len(errors),
            "errors": errors,
        }
        all_errors.extend(f"{artifact_type}: {error}" for error in errors)

    item: dict[str, Any] = {
        "status": _build_status(all_errors),
        "artifacts": artifact_results,
    }
    if all_errors:
        item["errors"] = all_errors
    return item


def build_semantic_consistency_item(analysis: dict[str, Any]) -> dict[str, Any]:
    errors = validate_analysis_semantics(analysis)
    errors.extend(
        validate_formula_metrics(
            analysis.get("key_metrics", {}),
            path="$.key_metrics",
            price_override=analysis.get("price_at_analysis"),
        )
    )
    item: dict[str, Any] = {
        "status": _build_status(errors),
        "error_count": len(errors),
    }
    if errors:
        item["errors"] = errors
    return item


def build_verdict_policy_item(analysis: dict[str, Any]) -> dict[str, Any]:
    errors = validate_verdict_alignment(analysis)
    item: dict[str, Any] = {
        "status": _build_status(errors),
    }
    if errors:
        item["errors"] = errors
    return item


def build_cross_artifact_item(
    research_plan: dict[str, Any],
    validated: dict[str, Any],
    analysis: dict[str, Any],
) -> dict[str, Any]:
    errors = validate_cross_artifact_consistency(research_plan, validated, analysis)
    item: dict[str, Any] = {
        "status": _build_status(errors),
        "error_count": len(errors),
    }
    if errors:
        item["errors"] = errors
    return item


def infer_delivery_impact(item_name: str, item_payload: dict[str, Any]) -> str:
    explicit = item_payload.get("delivery_impact")
    if explicit in DELIVERY_IMPACTS:
        return explicit

    status = item_payload.get("status")
    if status in {"PASS", "SKIP", None}:
        return "none"
    if item_name == "legacy_migration":
        return "historical_flag_only"
    if status == "PASS_WITH_FLAGS":
        return "non_blocking_flag"
    return "delivery_blocking_flag"


def annotate_delivery_impacts(items: dict[str, Any]) -> dict[str, Any]:
    annotated: dict[str, Any] = copy.deepcopy(items)
    for item_name, payload in annotated.items():
        if isinstance(payload, dict):
            payload["delivery_impact"] = infer_delivery_impact(item_name, payload)
    return annotated


def critic_delivery_impact(critic_review: dict[str, Any] | None) -> str:
    if not isinstance(critic_review, dict):
        return "none"
    overall = critic_review.get("overall")
    if overall == "FAIL":
        return "delivery_blocking_flag"
    if overall == "PASS_WITH_FLAGS":
        return "non_blocking_flag"
    return "none"


def build_delivery_gate(items: dict[str, Any], critic_review: dict[str, Any] | None = None) -> dict[str, Any]:
    blocking_items: list[str] = []
    non_blocking_items: list[str] = []
    historical_only_items: list[str] = []

    for item_name, payload in items.items():
        if not isinstance(payload, dict):
            continue
        status = payload.get("status")
        if status in {None, "PASS", "SKIP"}:
            continue
        impact = infer_delivery_impact(item_name, payload)
        if impact == "delivery_blocking_flag":
            blocking_items.append(item_name)
        elif impact == "historical_flag_only":
            historical_only_items.append(item_name)
        elif impact == "non_blocking_flag":
            non_blocking_items.append(item_name)

    critic_impact = critic_delivery_impact(critic_review)
    critic_overall = critic_review.get("overall") if isinstance(critic_review, dict) else None
    if critic_impact == "delivery_blocking_flag":
        blocking_items.append("critic_review")
    elif critic_impact == "non_blocking_flag":
        non_blocking_items.append("critic_review")

    result = "BLOCKED" if blocking_items else "PASS"
    return {
        "result": result,
        "ready_for_delivery": result == "PASS",
        "blocking_items": blocking_items,
        "non_blocking_items": non_blocking_items,
        "historical_only_items": historical_only_items,
        "critic_overall": critic_overall,
        "critic_delivery_impact": critic_impact,
    }


def combine_overall_result(items: dict[str, Any]) -> str:
    statuses = [
        value.get("status")
        for value in items.values()
        if isinstance(value, dict) and value.get("status") in QUALITY_ITEM_STATUSES
    ]
    return combine_statuses(statuses)


def combine_statuses(statuses: list[str | None]) -> str:
    normalized = [status for status in statuses if status in STATUS_SEVERITY]
    if not normalized:
        return "PASS"
    return max(normalized, key=lambda item: STATUS_SEVERITY[item])  # type: ignore[arg-type]


def combine_report_overall_result(core_overall_result: str, critic_review: dict[str, Any] | None = None) -> str:
    critic_overall = None
    if isinstance(critic_review, dict):
        critic_overall = critic_review.get("overall")
        if critic_overall not in CRITIC_OVERALL_STATUSES:
            critic_overall = None
    return combine_statuses([core_overall_result, critic_overall])


def combine_critic_overall(items: list[dict[str, Any]]) -> str:
    statuses = [item.get("status") for item in items if isinstance(item, dict)]
    normalized = [status for status in statuses if status in CRITIC_ITEM_SEVERITY]
    if not normalized:
        return "PASS"
    return max(normalized, key=lambda item: CRITIC_ITEM_SEVERITY[item])  # type: ignore[arg-type]


def build_feedback_for_analyst(critic_review: dict[str, Any]) -> list[dict[str, Any]]:
    feedback: list[dict[str, Any]] = []
    for item in critic_review.get("items", []):
        if not isinstance(item, dict) or item.get("status") != "FAIL":
            continue
        section = item.get("section")
        problem = item.get("problem")
        fix = item.get("fix")
        if isinstance(section, str) and isinstance(problem, str) and isinstance(fix, str):
            feedback.append(
                {
                    "section": section,
                    "problem": problem,
                    "fix": fix,
                }
            )
    return feedback


def merge_items(existing_items: dict[str, Any] | None, generated_items: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(existing_items) if isinstance(existing_items, dict) else {}

    for key in BASELINE_GENERATED_ITEMS:
        if key in generated_items and key not in merged:
            merged[key] = generated_items[key]

    for key in CORE_GENERATED_ITEMS:
        if key in generated_items:
            merged[key] = generated_items[key]

    for key, value in generated_items.items():
        if key not in BASELINE_GENERATED_ITEMS and key not in CORE_GENERATED_ITEMS:
            merged[key] = value

    return merged


def merge_critic_review(
    report: dict[str, Any],
    critic_review: dict[str, Any],
    feedback_for_analyst: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    merged = copy.deepcopy(report)
    merged["critic_review"] = copy.deepcopy(critic_review)
    if feedback_for_analyst is not None:
        merged["feedback_for_analyst"] = copy.deepcopy(feedback_for_analyst)

    core_overall_result = merged.get("core_overall_result") or combine_overall_result(merged.get("items", {}))
    merged["core_overall_result"] = core_overall_result
    merged["overall_result"] = combine_report_overall_result(core_overall_result, merged["critic_review"])
    merged["delivery_gate"] = build_delivery_gate(merged.get("items", {}), merged["critic_review"])
    return merged


def apply_critic_recheck(
    report: dict[str, Any],
    recheck_review: dict[str, Any],
    feedback_for_analyst: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    merged = copy.deepcopy(report)
    current_review = merged.get("critic_review")
    if not isinstance(current_review, dict):
        raise ValueError("quality report does not contain an existing critic_review")

    current_items = current_review.get("items")
    if not isinstance(current_items, list) or not current_items:
        raise ValueError("critic_review.items must be a non-empty array before recheck")

    failing_item_names = {
        item.get("item")
        for item in current_items
        if isinstance(item, dict) and item.get("status") == "FAIL" and isinstance(item.get("item"), str)
    }
    if not failing_item_names:
        raise ValueError("critic_review has no failing items to recheck")

    incoming_items = recheck_review.get("items")
    if not isinstance(incoming_items, list) or not incoming_items:
        raise ValueError("recheck payload must contain a non-empty items array")

    incoming_by_name: dict[str, dict[str, Any]] = {}
    for item in incoming_items:
        if not isinstance(item, dict) or not isinstance(item.get("item"), str):
            raise ValueError("each recheck item must be an object with an item field")
        item_name = item["item"]
        if item_name in incoming_by_name:
            raise ValueError(f"duplicate recheck item {item_name!r}")
        if item_name not in failing_item_names:
            raise ValueError(
                f"recheck item {item_name!r} is not currently failing and cannot be rechecked"
            )
        incoming_by_name[item_name] = copy.deepcopy(item)

    updated_items: list[dict[str, Any]] = []
    for item in current_items:
        if not isinstance(item, dict):
            updated_items.append(item)
            continue
        item_name = item.get("item")
        if isinstance(item_name, str) and item_name in incoming_by_name:
            replacement = incoming_by_name[item_name]
            if "section" not in replacement and "section" in item:
                replacement["section"] = item["section"]
            updated_items.append(replacement)
        else:
            updated_items.append(copy.deepcopy(item))

    updated_review = copy.deepcopy(current_review)
    updated_review["reviewer"] = recheck_review.get("reviewer", current_review.get("reviewer"))
    updated_review["review_timestamp"] = recheck_review.get(
        "review_timestamp",
        current_review.get("review_timestamp"),
    )
    updated_review["items"] = updated_items
    updated_review["overall"] = combine_critic_overall(updated_items)

    history = copy.deepcopy(current_review.get("recheck_history", []))
    history.append(
        {
            "review_timestamp": updated_review["review_timestamp"],
            "updated_items": sorted(incoming_by_name),
            "remaining_fail_items": sorted(
                item.get("item")
                for item in updated_items
                if isinstance(item, dict) and item.get("status") == "FAIL" and isinstance(item.get("item"), str)
            ),
        }
    )
    updated_review["recheck_history"] = history
    updated_review["recheck_count"] = len(history)

    merged["critic_review"] = updated_review
    merged["core_overall_result"] = merged.get("core_overall_result") or combine_overall_result(merged.get("items", {}))
    if feedback_for_analyst is not None:
        merged["feedback_for_analyst"] = copy.deepcopy(feedback_for_analyst)
    else:
        rebuilt_feedback = build_feedback_for_analyst(updated_review)
        if rebuilt_feedback:
            merged["feedback_for_analyst"] = rebuilt_feedback
        else:
            merged.pop("feedback_for_analyst", None)

    merged["overall_result"] = combine_report_overall_result(merged["core_overall_result"], updated_review)
    merged["delivery_gate"] = build_delivery_gate(merged.get("items", {}), updated_review)
    return merged


def build_quality_report(
    research_plan: dict[str, Any],
    validated: dict[str, Any],
    analysis: dict[str, Any],
    *,
    existing_report: dict[str, Any] | None = None,
    report_path: str | Path | None = None,
) -> dict[str, Any]:
    existing_report = copy.deepcopy(existing_report) if existing_report else {}
    generated_items = {
        "financial_consistency": build_financial_consistency_item(validated, analysis),
        "price_and_date": build_price_and_date_item(validated, analysis),
        "blank_over_wrong": build_blank_over_wrong_item(validated, analysis),
        "contract_validation": build_contract_validation_item(research_plan, validated, analysis),
        "semantic_consistency": build_semantic_consistency_item(analysis),
        "verdict_policy": build_verdict_policy_item(analysis),
        "cross_artifact_consistency": build_cross_artifact_item(research_plan, validated, analysis),
    }
    if report_path is not None:
        generated_items["rendered_output"] = build_rendered_output_item(report_path, analysis, validated)
    merged_items = annotate_delivery_impacts(merge_items(existing_report.get("items"), generated_items))
    critic_review = existing_report.get("critic_review") if isinstance(existing_report.get("critic_review"), dict) else None
    core_overall_result = combine_overall_result(merged_items)
    delivery_gate = build_delivery_gate(merged_items, critic_review)

    run_context = (
        analysis.get("run_context")
        or validated.get("run_context")
        or research_plan.get("run_context")
        or existing_report.get("run_context")
    )
    report = {
        "ticker": analysis.get("ticker") or validated.get("ticker") or research_plan.get("ticker"),
        "output_mode": analysis.get("output_mode") or research_plan.get("output_mode") or existing_report.get("output_mode"),
        "check_timestamp": utc_now_iso(),
        "overall_result": combine_report_overall_result(core_overall_result, critic_review),
        "run_context": run_context,
        "items": merged_items,
        "delivery_gate": delivery_gate,
        "auto_fixes_applied": existing_report.get("auto_fixes_applied", []),
        "inline_flags_added": existing_report.get("inline_flags_added", []),
        "generated_by": "quality-report-builder",
    }
    if report_path is not None:
        report["report_path"] = str(report_path)
    if critic_review:
        report["critic_review"] = critic_review
        report["core_overall_result"] = core_overall_result

    for key in ("mode_a_simplified", "migration", "reviewer", "review_timestamp", "feedback_for_analyst"):
        if key in existing_report:
            report[key] = existing_report[key]

    return report


def build_quality_report_from_run_dir(run_dir: str | Path, report_path: str | Path | None = None) -> dict[str, Any]:
    path = Path(run_dir)
    ticker_dirs = [child for child in path.iterdir() if child.is_dir()]
    if len(ticker_dirs) != 1:
        raise ValueError(f"Expected exactly one ticker directory under {path}, found {len(ticker_dirs)}")

    ticker_dir = ticker_dirs[0]
    research_plan = load_json(ticker_dir / "research-plan.json")
    validated = load_json(ticker_dir / "validated-data.json")
    analysis = load_json(ticker_dir / "analysis-result.json")
    quality_report_path = ticker_dir / "quality-report.json"
    existing_report = load_json(quality_report_path) if quality_report_path.exists() else None
    return build_quality_report(research_plan, validated, analysis, existing_report=existing_report, report_path=report_path)


def write_quality_report(run_dir: str | Path, report_path: str | Path | None = None) -> Path:
    path = Path(run_dir)
    report = build_quality_report_from_run_dir(path, report_path=report_path)
    ticker_dirs = [child for child in path.iterdir() if child.is_dir()]
    ticker_dir = ticker_dirs[0]
    quality_report_path = ticker_dir / "quality-report.json"
    with open(quality_report_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
    return quality_report_path
