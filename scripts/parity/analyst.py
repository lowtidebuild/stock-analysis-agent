"""Analyst pass orchestration for the A/B/C parity runner."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.analyst_backends import get_backend
from scripts.parity.data_sources import load_json, write_json
from tools.artifact_validation import (
    validate_artifact_data,
    validate_cross_artifact_consistency,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
ANALYSIS_SCHEMA_PATH = REPO_ROOT / ".claude" / "schemas" / "analysis-result.schema.json"
COMPACT_ANALYST_INPUT_SCHEMA_VERSION = "abc-parity-compact-analyst-input-v1"
PEER_PLACEHOLDER_TERMS = (
    "peer_set_pending",
    "comparable data pending",
    "not yet wired",
    "will be expanded",
    "placeholder",
)


@dataclass(frozen=True)
class AnalystResult:
    ticker: str
    artifact_root: Path
    analyst_input_path: Path
    analysis_result_path: Path
    provider: str
    model: str
    status: str


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_analyst_handoff(
    *,
    language: str,
    market: str,
    mode: str,
    run_id: str,
    ticker: str,
) -> AnalystResult:
    ticker_dir = REPO_ROOT / "output" / "runs" / run_id / ticker
    research_plan = load_json(ticker_dir / "research-plan.json")
    validated = load_json(ticker_dir / "validated-data.json")
    evidence = load_json(ticker_dir / "evidence-pack.json")
    context_budget = load_json(ticker_dir / "context-budget.json")
    calculations = load_json(ticker_dir / "deterministic-calculations.json")
    peer_records = load_peer_records(ticker_dir)
    if not validated or not evidence or not calculations:
        raise ValueError("validated-data, evidence-pack, and deterministic-calculations are required before analyst pass")
    ensure_calculations_ready(calculations)

    system = build_system_prompt(language=language, mode=mode)
    full_user_payload = build_full_analyst_input_payload(
        calculations=calculations,
        context_budget=context_budget,
        evidence=evidence,
        language=language,
        mode=mode,
        peer_records=peer_records,
        research_plan=research_plan,
        validated=validated,
    )
    compact_user_payload = build_compact_analyst_input(
        calculations=calculations,
        context_budget=context_budget,
        evidence=evidence,
        language=language,
        market=market,
        mode=mode,
        peer_records=peer_records,
        research_plan=research_plan,
        ticker=ticker,
        validated=validated,
    )
    full_user_json = json.dumps(full_user_payload, ensure_ascii=False)
    compact_user_json = json.dumps(compact_user_payload, ensure_ascii=False)
    compaction = build_compaction_report(
        compact_user_json=compact_user_json,
        context_budget=context_budget,
        full_user_json=full_user_json,
    )
    messages = [
        {
            "role": "user",
            "content": compact_user_json,
        }
    ]
    compact_input_path = ticker_dir / "analyst-input.compact.json"
    write_json(compact_input_path, compact_user_payload)
    input_pack = {
        "schema_version": "abc-parity-analyst-input-v1",
        "ticker": ticker,
        "market": market,
        "mode": mode,
        "language": language,
        "generated_at": utc_now(),
        "input_profile": "compact",
        "system": system,
        "messages": messages,
        "compact_input_path": display_path(compact_input_path),
        "compaction": compaction,
        "included_artifacts": [
            "research-plan.json",
            "validated-data.json",
            "evidence-pack.json",
            "context-budget.json",
            "deterministic-calculations.json",
        ],
        "excluded_raw_artifacts_default": "deny",
    }
    if peer_records:
        input_pack["included_artifacts"].append("peers/*.json")
    analyst_input_path = ticker_dir / "analyst-input.json"
    write_json(analyst_input_path, input_pack)

    backend_name = os.environ.get("ANALYST_BACKEND", "").strip()
    schema = load_analysis_schema()
    if backend_name in {"fixture", "deterministic_fixture", "local_fixture"}:
        analyst_json = build_fixture_analysis(
            calculations=calculations,
            evidence=evidence,
            language=language,
            mode=mode,
            peer_records=peer_records,
            validated=validated,
        )
        backend_meta = {"provider": "fixture", "model": "deterministic-fixture", "usage": {}}
    else:
        backend = get_backend(backend_name or None, logical_tier="analyst_main")
        backend_result = backend.complete(
            system=system,
            messages=messages,
            json_schema=schema,
            max_tokens=6500 if mode in {"B", "C"} else 4200,
        )
        if not backend_result.json:
            raise ValueError("analyst backend did not return structured JSON")
        analyst_json = backend_result.json
        backend_meta = {
            "provider": backend_result.provider,
            "model": backend_result.model,
            "usage": backend_result.usage,
        }

    analysis = enforce_deterministic_contract(
        analyst_json,
        backend_meta=backend_meta,
        calculations=calculations,
        evidence=evidence,
        language=language,
        mode=mode,
        peer_records=peer_records,
        run_id=run_id,
        ticker=ticker,
        validated=validated,
    )
    errors = validate_artifact_data("analysis-result", analysis)
    errors.extend(validate_cross_artifact_consistency(research_plan, validated, analysis))
    if errors:
        write_json(ticker_dir / "analysis-result.rejected.json", analysis)
        raise ValueError("analysis-result failed contract checks: " + "; ".join(errors[:8]))

    analysis_path = ticker_dir / "analysis-result.json"
    write_json(analysis_path, analysis)
    write_json(
        ticker_dir / "analyst-summary.json",
        {
            "schema_version": "abc-parity-analyst-summary-v1",
            "ticker": ticker,
            "mode": mode,
            "provider": backend_meta["provider"],
            "model": backend_meta["model"],
            "input_profile": "compact",
            "compaction": compaction,
            "analysis_result": display_path(analysis_path),
            "created_at": utc_now(),
        },
    )
    return AnalystResult(
        ticker=ticker,
        artifact_root=ticker_dir,
        analyst_input_path=analyst_input_path,
        analysis_result_path=analysis_path,
        provider=backend_meta["provider"],
        model=backend_meta["model"],
        status="success",
    )


def build_full_analyst_input_payload(
    *,
    calculations: dict[str, Any],
    context_budget: dict[str, Any],
    evidence: dict[str, Any],
    language: str,
    mode: str,
    peer_records: list[dict[str, Any]],
    research_plan: dict[str, Any],
    validated: dict[str, Any],
) -> dict[str, Any]:
    return {
        "task": "Produce schema-constrained analysis-result JSON from compact verified artifacts.",
        "mode": mode,
        "language": language,
        "mode_contract": mode_specific_contract(mode=mode, language=language),
        "research_plan": research_plan,
        "validated_data": validated,
        "evidence_pack": evidence,
        "context_budget": context_budget,
        "deterministic_calculations": calculations,
        "peer_mini_fetch": peer_records,
        "rules": ANALYST_RULES,
    }


def build_compact_analyst_input(
    *,
    calculations: dict[str, Any],
    context_budget: dict[str, Any],
    evidence: dict[str, Any],
    language: str,
    market: str,
    mode: str,
    peer_records: list[dict[str, Any]],
    research_plan: dict[str, Any],
    ticker: str,
    validated: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": COMPACT_ANALYST_INPUT_SCHEMA_VERSION,
        "task": "Produce schema-constrained analysis-result JSON from compact verified artifacts.",
        "mode": mode,
        "language": language,
        "mode_contract": mode_specific_contract(mode=mode, language=language),
        "research_plan": compact_research_plan(research_plan, fallback_market=market, ticker=ticker),
        "validated_data": compact_validated_data(validated),
        "evidence_pack": compact_evidence_pack(evidence),
        "context_budget": compact_context_budget(context_budget),
        "deterministic_calculations": compact_calculations(calculations),
        "peer_mini_fetch": compact_peer_records(peer_records),
        "rules": ANALYST_RULES,
    }


def compact_research_plan(
    research_plan: dict[str, Any],
    *,
    fallback_market: str,
    ticker: str,
) -> dict[str, Any]:
    return remove_empty(
        {
            "schema_version": research_plan.get("schema_version"),
            "ticker": research_plan.get("ticker") or ticker,
            "market": research_plan.get("market") or fallback_market,
            "output_mode": research_plan.get("output_mode"),
            "output_language": research_plan.get("output_language"),
            "analysis_date": research_plan.get("analysis_date"),
            "analysis_framework_path": research_plan.get("analysis_framework_path"),
            "data_profile": research_plan.get("data_profile"),
            "required_sources": research_plan.get("required_sources"),
            "peer_tickers": research_plan.get("peer_tickers"),
            "macro_factors": research_plan.get("macro_factors"),
        }
    )


def compact_validated_data(validated: dict[str, Any]) -> dict[str, Any]:
    metrics = validated.get("validated_metrics") if isinstance(validated.get("validated_metrics"), dict) else {}
    compact_metrics = {
        key: compact_metric_entry(value)
        for key, value in metrics.items()
        if should_include_metric(value)
    }
    return remove_empty(
        {
            "schema_version": validated.get("schema_version"),
            "ticker": validated.get("ticker"),
            "company_name": validated.get("company_name"),
            "market": validated.get("market"),
            "analysis_date": validated.get("analysis_date"),
            "currency": validated.get("currency"),
            "data_mode": validated.get("data_mode"),
            "requested_mode": validated.get("requested_mode"),
            "effective_mode": validated.get("effective_mode"),
            "source_profile": validated.get("source_profile"),
            "source_tier": validated.get("source_tier"),
            "confidence_cap": validated.get("confidence_cap"),
            "overall_grade": validated.get("overall_grade"),
            "grade_summary": validated.get("grade_summary"),
            "validated_metrics": compact_metrics,
            "valuation_inputs": compact_mapping(validated.get("valuation_inputs")),
            "macro_context": compact_macro_context(validated.get("macro_context")),
            "staleness": compact_mapping(validated.get("staleness")),
            "exclusions": [
                compact_exclusion(item)
                for item in as_dict_list(validated.get("exclusions"))[:32]
            ],
            "conflicts": as_dict_list(validated.get("metric_conflicts"))[:16],
        }
    )


def should_include_metric(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    grade = str(value.get("grade") or value.get("confidence_grade") or "").upper()
    return value.get("value") is not None and grade != "D"


def compact_metric_entry(entry: Any) -> dict[str, Any]:
    if not isinstance(entry, dict):
        return {}
    return remove_empty(
        {
            "value": entry.get("value"),
            "unit": entry.get("unit"),
            "period": entry.get("period"),
            "as_of": entry.get("as_of"),
            "grade": entry.get("grade") or entry.get("confidence_grade"),
            "source": entry.get("source") or entry.get("data_source"),
            "source_field": entry.get("source_field"),
            "tag": entry.get("tag"),
            "reason": entry.get("reason"),
        }
    )


def compact_evidence_pack(evidence: dict[str, Any]) -> dict[str, Any]:
    return remove_empty(
        {
            "schema_version": evidence.get("schema_version"),
            "ticker": evidence.get("ticker"),
            "as_of": evidence.get("as_of"),
            "raw_access_policy": evidence.get("raw_access_policy"),
            "facts": [compact_fact(fact) for fact in as_dict_list(evidence.get("facts"))[:48]],
            "exclusions": [
                compact_exclusion(item)
                for item in as_dict_list(evidence.get("exclusions"))[:32]
            ],
            "conflicts": as_dict_list(evidence.get("conflicts"))[:16],
            "macro_context": compact_macro_context(evidence.get("macro_context")),
        }
    )


def compact_fact(fact: dict[str, Any]) -> dict[str, Any]:
    return remove_empty(
        {
            "metric": fact.get("metric"),
            "claim": fact.get("claim"),
            "value": fact.get("value"),
            "unit": fact.get("unit"),
            "period": fact.get("period"),
            "as_of": fact.get("as_of"),
            "grade": fact.get("grade"),
            "sources": fact.get("sources"),
            "source_refs": fact.get("source_refs"),
            "tag": fact.get("tag"),
        }
    )


def compact_exclusion(item: dict[str, Any]) -> dict[str, Any]:
    return remove_empty(
        {
            "metric": item.get("metric"),
            "reason": item.get("reason"),
            "grade": item.get("grade"),
            "source": item.get("source"),
        }
    )


def compact_context_budget(context_budget: dict[str, Any]) -> dict[str, Any]:
    routing = context_budget.get("routing_policy") if isinstance(context_budget.get("routing_policy"), dict) else {}
    included_files = [
        {
            "role": item.get("role"),
            "estimated_tokens": item.get("estimated_tokens"),
        }
        for item in as_dict_list(context_budget.get("included_files"))
    ]
    return remove_empty(
        {
            "schema_version": context_budget.get("schema_version"),
            "token_estimator": context_budget.get("token_estimator"),
            "totals": context_budget.get("totals"),
            "included_file_summary": included_files,
            "routing_policy": {
                "strong_model": routing.get("strong_model"),
                "no_llm": routing.get("no_llm"),
            },
        }
    )


def compact_calculations(calculations: dict[str, Any]) -> dict[str, Any]:
    dcf = calculations.get("dcf_analysis") if isinstance(calculations.get("dcf_analysis"), dict) else {}
    return remove_empty(
        {
            "schema_version": calculations.get("schema_version"),
            "ticker": calculations.get("ticker"),
            "market": calculations.get("market"),
            "mode": calculations.get("mode"),
            "language": calculations.get("language"),
            "status": calculations.get("status"),
            "blockers": calculations.get("blockers"),
            "source_profile": calculations.get("source_profile"),
            "overall_grade": calculations.get("overall_grade"),
            "ratio_recomputation": compact_ratio_recomputation(calculations.get("ratio_recomputation")),
            "scenario_analysis": calculations.get("scenario_analysis"),
            "dcf_analysis": remove_empty(
                {
                    "status": dcf.get("status"),
                    "result": dcf.get("result"),
                    "reverse_dcf": dcf.get("reverse_dcf"),
                }
            ),
            "reverse_dcf": calculations.get("reverse_dcf"),
            "valuation_bridge": calculations.get("valuation_bridge"),
            "macro_deltas": calculations.get("macro_deltas"),
            "analyst_handoff": calculations.get("analyst_handoff"),
        }
    )


def compact_ratio_recomputation(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return remove_empty(
        {
            "status": value.get("status"),
            "computed_metrics": value.get("computed_metrics"),
        }
    )


def compact_peer_records(peer_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compacted = []
    for record in peer_records[:5]:
        metrics = record.get("metrics") if isinstance(record.get("metrics"), dict) else {}
        compacted.append(
            remove_empty(
                {
                    "ticker": record.get("ticker"),
                    "company_name": record.get("company_name"),
                    "data_source": record.get("data_source"),
                    "tag": record.get("tag"),
                    "confidence_grade": record.get("confidence_grade"),
                    "metrics": {
                        key: metrics.get(key)
                        for key in (
                            "current_price",
                            "market_cap",
                            "pe_forward",
                            "ev_ebitda",
                            "revenue_growth_yoy",
                            "operating_margin",
                            "fcf_yield",
                            "beta",
                        )
                        if metrics.get(key) is not None
                    },
                }
            )
        )
    return compacted


def compact_macro_context(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    structured = value.get("structured") if isinstance(value.get("structured"), dict) else {}
    series = structured.get("series") if isinstance(structured.get("series"), list) else []
    return remove_empty(
        {
            "status": value.get("status") or structured.get("status"),
            "grade": value.get("grade") or structured.get("grade"),
            "reason": value.get("reason") or structured.get("reason"),
            "source": value.get("source") or structured.get("source"),
            "series": series[:12],
        }
    )


def compact_mapping(value: Any) -> dict[str, Any] | None:
    return value if isinstance(value, dict) else None


def as_dict_list(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def remove_empty(value: dict[str, Any]) -> dict[str, Any]:
    return {
        key: item
        for key, item in value.items()
        if item is not None and item != {} and item != []
    }


def build_compaction_report(
    *,
    compact_user_json: str,
    context_budget: dict[str, Any],
    full_user_json: str,
) -> dict[str, Any]:
    full_bytes = len(full_user_json.encode("utf-8"))
    compact_bytes = len(compact_user_json.encode("utf-8"))
    reduction = 0.0 if full_bytes == 0 else round((full_bytes - compact_bytes) / full_bytes, 4)
    compact_tokens = estimate_tokens(compact_user_json)
    soft_limit = (
        (context_budget.get("totals") or {}).get("strong_model_soft_limit_tokens")
        if isinstance(context_budget.get("totals"), dict)
        else None
    ) or 50_000
    warnings = []
    if reduction < 0.25:
        warnings.append("compact_input_reduction_below_25_percent")
    if compact_tokens > soft_limit:
        warnings.append("compact_input_exceeds_strong_model_soft_limit")
    return {
        "schema_version": "abc-parity-analyst-compaction-v1",
        "full_user_payload_bytes": full_bytes,
        "compact_user_payload_bytes": compact_bytes,
        "byte_reduction_ratio": reduction,
        "compact_estimated_tokens": compact_tokens,
        "token_estimator": "chars_div_4_ceil",
        "strong_model_soft_limit_tokens": soft_limit,
        "warnings": warnings,
    }


def estimate_tokens(text: str) -> int:
    return (len(text) + 3) // 4


ANALYST_RULES = [
    "Do not load raw artifacts by default.",
    "Do not invent numbers. Use deterministic_calculations for scenarios, R/R, DCF, reverse DCF, and valuation bridge.",
    "Grade D metrics must stay null or be excluded.",
    "Every important numeric claim must be source-tagged via key_metrics, scenarios, or deterministic_calculations.",
    "Analyst text should explain mechanism, variant view, risks, and what would change the thesis.",
    "For Mode A, sections.precision_risks and top_risks must contain at least two risk objects with risk, mechanism, and financial_impact fields.",
]


def ensure_calculations_ready(calculations: dict[str, Any]) -> None:
    scenario_status = (calculations.get("scenario_analysis") or {}).get("status")
    if scenario_status != "available":
        raise ValueError("analyst pass requires available deterministic scenario_analysis")
    if calculations.get("status") not in {"available", "partial"}:
        raise ValueError("deterministic calculations are not ready")


def build_system_prompt(*, language: str, mode: str) -> str:
    lang = "Korean" if language == "ko" else "English"
    mode_detail = ""
    if mode == "A":
        mode_detail = (
            " For Mode A, always populate sections.precision_risks and top_risks "
            "with at least two concrete risk mechanisms. Each risk must connect "
            "cause -> verified metric impact -> valuation or scenario impact."
        )
    return (
        "You are an institutional-grade equity analyst. Return only JSON matching "
        "analysis-result.schema.json. You interpret verified evidence; you do not "
        "recalculate valuation math. Use deterministic_calculations exactly for "
        "scenario targets, return_pct, rr_score, DCF, reverse DCF, and valuation_bridge. "
        "Blank is better than wrong. Make the output company-specific, source-grounded, "
        f"and suitable for Mode {mode}.{mode_detail} Human-readable prose must be in {lang}."
    )


def mode_specific_contract(*, mode: str, language: str) -> dict[str, Any]:
    contract: dict[str, Any] = {
        "mode": mode,
        "language": language,
        "source_boundary": "Use only validated_data, evidence_pack, and deterministic_calculations.",
    }
    if mode == "A":
        contract["required_sections"] = {
            "precision_risks": {
                "min_items": 2,
                "required_fields": ["risk", "mechanism", "financial_impact"],
                "mechanism_shape": "cause -> verified metric impact -> valuation/scenario impact",
                "empty_array_policy": "not_allowed",
            },
            "top_risks": {
                "min_items": 2,
                "mirror": "sections.precision_risks",
            },
        }
        contract["quality_bar"] = [
            "Do not return generic risks that could fit any company.",
            "Tie each risk to at least one validated metric, scenario target, R/R score, DCF, reverse DCF, or valuation bridge.",
            "If a source-tagged risk is unavailable, use deterministic fallback language from verified metrics instead of an empty array.",
        ]
    return contract


def load_analysis_schema() -> dict[str, Any]:
    return json.loads(ANALYSIS_SCHEMA_PATH.read_text(encoding="utf-8"))


def build_fixture_analysis(
    *,
    calculations: dict[str, Any],
    evidence: dict[str, Any],
    language: str,
    mode: str,
    peer_records: list[dict[str, Any]] | None = None,
    validated: dict[str, Any],
) -> dict[str, Any]:
    company = validated.get("company_name") or validated.get("ticker")
    ticker = validated.get("ticker")
    facts = evidence.get("facts") if isinstance(evidence.get("facts"), list) else []
    fact_text = "; ".join(str(fact.get("claim") or fact.get("metric")) for fact in facts[:4] if isinstance(fact, dict))
    if not fact_text:
        fact_text = "verified evidence remains thin; deterministic calculations define the usable boundaries"
    if language == "ko":
        thesis = f"{company}({ticker})는 검증된 숫자와 deterministic scenario 기준으로 판단해야 하며, 핵심 논점은 성장 지속성, FCF 전환, 밸류에이션 부담의 균형이다."
        risk_prefix = "검증된 지표가 약화되면"
        catalyst_prefix = "다음 확인 지점은"
    else:
        thesis = f"{company} ({ticker}) should be judged on verified metrics and deterministic scenarios; the core debate is growth durability, FCF conversion, and valuation risk."
        risk_prefix = "If verified metrics weaken"
        catalyst_prefix = "The next checkpoint is"

    sections: dict[str, Any] = {
        "one_line_thesis": thesis,
        "action_signal": fixture_action_signal(language),
        "variant_view_q1": f"{thesis} The first variant question is whether current growth can compound without degrading cash conversion.",
        "variant_view_q2": f"{company} must prove that valuation support is driven by durable earnings power rather than multiple expansion alone.",
        "variant_view_q3": f"The downside debate is whether source-verified FCF and margin evidence can absorb a sentiment reset.",
        "precision_risks": [
            {
                "risk": f"{risk_prefix} growth could be repriced lower.",
                "mechanism": "Growth disappointment reduces forward estimates, compresses valuation multiples, and pushes the bear scenario toward its deterministic target.",
                "financial_impact": "Lower revenue growth and lower FCF conversion reduce the base-case fair value.",
            },
            {
                "risk": f"{risk_prefix} FCF quality could lag reported earnings.",
                "mechanism": "Higher reinvestment or working-capital drag would lower FCF yield and weaken DCF support.",
                "financial_impact": "DCF fair value and valuation_bridge weighted fair value would fall.",
            },
            {
                "risk": f"{risk_prefix} consensus targets may be stale.",
                "mechanism": "Estimate revisions can move analyst target anchors faster than trailing financials.",
                "financial_impact": "Scenario base and analyst-target valuation anchors would need to reset.",
            },
        ],
        "valuation_metrics": list((calculations.get("ratio_recomputation") or {}).get("computed_metrics", {}).values()),
        "dcf_analysis": dcf_section(calculations),
        "macro_context": macro_section(validated),
        "peer_comparison": peer_comparison_from_records(peer_records, language=language)
        or peer_unavailable_disclosure(),
        "analyst_coverage": analyst_coverage(validated),
        "qoe_summary": {
            "narrative": "Quality of earnings is judged from validated metrics only; Grade D fields are excluded rather than filled with guesses.",
            "fact_basis": fact_text,
        },
        "portfolio_strategy": "Position sizing should follow the deterministic R/R score, valuation bridge discount or premium, and upcoming evidence checkpoints rather than a generic buy/sell label.",
        "what_would_make_me_wrong": [
            "Scenario probabilities stop summing to the deterministic base case after new evidence.",
            "FCF conversion diverges materially from the validated-data trend.",
            "A new filing or company release contradicts the current source-tagged metrics.",
        ],
        "source_tagged_claims": source_tagged_claims(evidence),
        "disclaimer": "This is not investment advice; outputs depend on the verified artifacts available at run time.",
    }
    if mode == "A":
        sections["briefing_summary"] = thesis
    if mode == "B":
        sections["relative_view"] = "Mode B comparison ranking is deferred to the comparison pass; this per-ticker analyst result supplies comparable inputs."
    return {
        "verdict": "neutral",
        "rr_score_interpretation": "Deterministic scenarios define the R/R score; analyst text explains the evidence fit.",
        "thesis": thesis,
        "variant_view": [sections["variant_view_q1"], sections["variant_view_q2"], sections["variant_view_q3"]],
        "top_risks": sections["precision_risks"],
        "upcoming_catalysts": [
            {
                "date": validated.get("analysis_date"),
                "event": f"{catalyst_prefix} updated source-tagged financial evidence.",
                "significance": "Refresh valuation and scenario anchors with new verified data.",
                "narrative": "New validated metrics should update the deterministic calculations before the analyst thesis changes.",
            }
        ],
        "sections": sections,
    }


def enforce_deterministic_contract(
    analyst_json: dict[str, Any],
    *,
    backend_meta: dict[str, Any],
    calculations: dict[str, Any],
    evidence: dict[str, Any],
    language: str,
    mode: str,
    peer_records: list[dict[str, Any]] | None = None,
    run_id: str,
    ticker: str,
    validated: dict[str, Any],
) -> dict[str, Any]:
    metrics = validated.get("validated_metrics") if isinstance(validated.get("validated_metrics"), dict) else {}
    scenario_analysis = calculations.get("scenario_analysis") if isinstance(calculations.get("scenario_analysis"), dict) else {}
    scenarios = scenario_analysis.get("scenarios") if isinstance(scenario_analysis.get("scenarios"), dict) else {}
    rr_score = scenario_analysis.get("rr_score")
    analysis = dict(analyst_json)
    sections = analysis.get("sections") if isinstance(analysis.get("sections"), dict) else {}
    sections = {**sections}
    if mode == "C":
        sections = ensure_mode_c_sections(
            sections,
            calculations=calculations,
            evidence=evidence,
            validated=validated,
            language=language,
            peer_records=peer_records,
        )
    if mode == "A":
        sections = ensure_mode_a_sections(
            sections,
            calculations=calculations,
            evidence=evidence,
            language=language,
            validated=validated,
        )
    top_risks = analysis.get("top_risks")
    if mode == "A" and not has_usable_precision_risks(top_risks, min_count=2):
        top_risks = sections.get("precision_risks")

    analysis.update(
        {
            "ticker": ticker,
            "company_name": validated.get("company_name") or ticker,
            "market": validated["market"],
            "data_mode": validated["data_mode"],
            "requested_mode": validated.get("requested_mode"),
            "effective_mode": validated.get("effective_mode"),
            "source_profile": validated.get("source_profile"),
            "source_tier": validated.get("source_tier"),
            "confidence_cap": validated.get("confidence_cap"),
            "output_mode": mode,
            "output_language": language,
            "analysis_date": validated["analysis_date"],
            "price_at_analysis": metric_value(metrics, "price_at_analysis"),
            "currency": validated.get("currency"),
            "run_context": {
                "run_id": run_id,
                "artifact_root": f"output/runs/{run_id}/{ticker}",
                "ticker": ticker,
                "backend": backend_meta,
                "generated_by": "scripts/parity/analyst.py",
            },
            "key_metrics": select_key_metrics(metrics),
            "scenarios": scenarios,
            "rr_score": rr_score,
            "verdict": verdict_from_rr(rr_score),
            "top_risks": top_risks,
            "upcoming_catalysts": ensure_minimum_catalysts(
                analysis.get("upcoming_catalysts"),
                language=language,
                ticker=ticker,
                validated=validated,
            ),
            "sections": sections,
            "dcf_analysis": (calculations.get("dcf_analysis") or {}).get("result"),
            "reverse_dcf": calculations.get("reverse_dcf"),
            "valuation_bridge": analysis_valuation_bridge(calculations),
            "confidence_summary": {
                "overall_grade": validated.get("overall_grade"),
                "source_profile": validated.get("source_profile"),
                "evidence_fact_count": len(evidence.get("facts") or []),
            },
            "disclaimer": analysis.get("disclaimer")
            or "This is not investment advice; verify source artifacts before acting.",
        }
    )
    return analysis


def ensure_mode_a_sections(
    sections: dict[str, Any],
    *,
    calculations: dict[str, Any],
    evidence: dict[str, Any],
    language: str,
    validated: dict[str, Any],
) -> dict[str, Any]:
    company = validated.get("company_name") or validated.get("ticker")
    ticker = validated.get("ticker") or company
    thesis = (
        f"{company}({ticker})는 검증된 metric, deterministic scenario, valuation bridge가 서로 맞는지로 판단해야 한다."
        if language == "ko"
        else f"{company} ({ticker}) should be judged by whether verified metrics, deterministic scenarios, and the valuation bridge agree."
    )
    sections.setdefault("one_line_thesis", thesis)
    sections.setdefault(
        "action_signal",
        "검증 지표와 R/R score가 함께 개선될 때만 노출을 늘린다."
        if language == "ko"
        else "Increase exposure only when verified metrics and the R/R score improve together.",
    )
    risks = normalize_precision_risks(
        sections.get("precision_risks"),
        fallback=build_precision_risk_fallbacks(
            calculations=calculations,
            evidence=evidence,
            language=language,
            validated=validated,
        ),
        min_count=2,
    )
    sections["precision_risks"] = risks
    sections.setdefault(
        "what_would_make_me_wrong",
        [
            f"{ticker}의 새 filing이나 업데이트가 현재 revenue, margin, FCF 증거와 충돌한다."
            if language == "ko"
            else f"A new {ticker} filing or update contradicts the current revenue, margin, or FCF evidence.",
            "시나리오 확률과 목표가가 최신 가격과 deterministic R/R에 더 이상 맞지 않는다."
            if language == "ko"
            else "Scenario probabilities and targets no longer reconcile to the latest price and deterministic R/R.",
        ],
    )
    return sections


def normalize_precision_risks(
    risks: Any,
    *,
    fallback: list[dict[str, Any]],
    min_count: int,
) -> list[dict[str, Any]]:
    normalized = [
        dict(item)
        for item in risks
        if is_usable_precision_risk(item)
    ] if isinstance(risks, list) else []
    for risk in fallback:
        if len(normalized) >= min_count:
            break
        normalized.append(risk)
    return normalized


def has_usable_precision_risks(risks: Any, *, min_count: int) -> bool:
    if not isinstance(risks, list):
        return False
    return len([item for item in risks if is_usable_precision_risk(item)]) >= min_count


def is_usable_precision_risk(risk: Any) -> bool:
    if not isinstance(risk, dict):
        return False
    title = str(risk.get("risk") or risk.get("title") or "").strip()
    mechanism = str(risk.get("mechanism") or "").strip()
    impact = str(risk.get("financial_impact") or risk.get("ebitda_impact") or "").strip()
    return bool(title) and word_count(mechanism) >= 8 and word_count(impact) >= 4


def build_precision_risk_fallbacks(
    *,
    calculations: dict[str, Any],
    evidence: dict[str, Any],
    language: str,
    validated: dict[str, Any],
) -> list[dict[str, Any]]:
    ticker = str(validated.get("ticker") or "the company")
    company = str(validated.get("company_name") or ticker)
    metrics = validated.get("validated_metrics") if isinstance(validated.get("validated_metrics"), dict) else {}
    scenarios = (calculations.get("scenario_analysis") or {}).get("scenarios") if isinstance(calculations.get("scenario_analysis"), dict) else {}
    base = scenarios.get("base") if isinstance(scenarios, dict) and isinstance(scenarios.get("base"), dict) else {}
    bear = scenarios.get("bear") if isinstance(scenarios, dict) and isinstance(scenarios.get("bear"), dict) else {}
    rr_score = (calculations.get("scenario_analysis") or {}).get("rr_score") if isinstance(calculations.get("scenario_analysis"), dict) else None
    base_target = base.get("target") if isinstance(base, dict) else None
    bear_target = bear.get("target") if isinstance(bear, dict) else None
    growth_signal = metric_signal(metrics, "revenue_growth_yoy") or "validated revenue growth"
    margin_signal = metric_signal(metrics, "operating_margin") or "validated operating margin"
    fcf_signal = metric_signal(metrics, "fcf_yield") or "validated FCF yield"
    evidence_basis = first_fact_basis(evidence)
    if language == "ko":
        return [
            {
                "risk": f"{company}({ticker})의 성장 지속성이 검증된 tape보다 약해지는 위험",
                "mechanism": f"{growth_signal}가 둔화되면 매출 추정과 영업 레버리지가 동시에 낮아져 base scenario의 전제가 약해진다.",
                "financial_impact": f"base target {base_target}와 R/R score {rr_score}를 낮춰야 하고, bear target {bear_target} 쪽 확률을 높인다.",
                "source_basis": evidence_basis,
            },
            {
                "risk": f"{company}({ticker})의 현금흐름 품질이 이익을 따라가지 못하는 위험",
                "mechanism": f"{fcf_signal}와 {margin_signal}가 함께 약해지면 DCF와 valuation bridge의 현금흐름 앵커가 먼저 훼손된다.",
                "financial_impact": "DCF fair value, reverse DCF implied growth gap, weighted fair value를 모두 다시 낮춰 검증해야 한다.",
                "source_basis": evidence_basis,
            },
        ]
    return [
        {
            "risk": f"{company} ({ticker}) growth durability weakens versus the verified tape.",
            "mechanism": f"If {growth_signal} decelerates, revenue estimates and operating leverage both weaken, undermining the base scenario assumption.",
            "financial_impact": f"Base target {base_target} and R/R score {rr_score} should be reduced while bear target {bear_target} receives more weight.",
            "source_basis": evidence_basis,
        },
        {
            "risk": f"{company} ({ticker}) cash-flow quality fails to confirm reported earnings.",
            "mechanism": f"If {fcf_signal} and {margin_signal} weaken together, the DCF and valuation bridge lose their cash-flow anchor before the multiple resets.",
            "financial_impact": "DCF fair value, reverse DCF implied growth gap, and weighted fair value all need to be marked lower.",
            "source_basis": evidence_basis,
        },
    ]


def metric_signal(metrics: dict[str, Any], key: str) -> str | None:
    entry = metrics.get(key)
    if not isinstance(entry, dict):
        return None
    value = entry.get("value")
    if value is None:
        return None
    unit = entry.get("unit")
    suffix = "%"
    if unit in {"x", "turns"}:
        suffix = "x"
    elif unit not in {"percent", "%"}:
        suffix = f" {unit}" if unit else ""
    return f"{key} {value}{suffix}"


def first_fact_basis(evidence: dict[str, Any]) -> str:
    facts = evidence.get("facts") if isinstance(evidence.get("facts"), list) else []
    for fact in facts:
        if isinstance(fact, dict):
            claim = fact.get("claim") or fact.get("metric")
            if claim:
                return str(claim)
    return "validated evidence pack"


def word_count(value: str) -> int:
    return len([part for part in re.split(r"\s+", value.strip()) if part])


def ensure_mode_c_sections(
    sections: dict[str, Any],
    *,
    calculations: dict[str, Any],
    evidence: dict[str, Any],
    language: str,
    peer_records: list[dict[str, Any]] | None = None,
    validated: dict[str, Any],
) -> dict[str, Any]:
    company = validated.get("company_name") or validated.get("ticker")
    base_sentence = (
        f"{company} requires a source-tagged debate around growth durability, margin quality, valuation support, and downside triggers."
    )
    sections.setdefault("variant_view_q1", base_sentence + " The first question is whether revenue growth can sustain the deterministic base scenario.")
    sections.setdefault("variant_view_q2", base_sentence + " The second question is whether FCF conversion supports the DCF anchor.")
    sections.setdefault("variant_view_q3", base_sentence + " The third question is whether valuation can absorb weaker consensus revisions.")
    sections.setdefault("precision_risks", build_fixture_analysis(calculations=calculations, evidence=evidence, language=language, mode="C", validated=validated)["sections"]["precision_risks"])
    sections.setdefault("valuation_metrics", list((calculations.get("ratio_recomputation") or {}).get("computed_metrics", {}).values()) or [{"metric": "unavailable"}])
    sections.setdefault("dcf_analysis", dcf_section(calculations))
    sections.setdefault("macro_context", macro_section(validated))
    peer_comparison = sections.get("peer_comparison")
    if not isinstance(peer_comparison, list) or has_peer_placeholder(peer_comparison):
        sections["peer_comparison"] = (
            peer_comparison_from_records(peer_records, language=language)
            or peer_unavailable_disclosure()
        )
    sections.setdefault("analyst_coverage", analyst_coverage(validated))
    sections.setdefault("qoe_summary", {"narrative": "Validated metrics are used as the quality-of-earnings boundary; missing fields remain blank."})
    sections.setdefault("portfolio_strategy", "Portfolio action should depend on valuation bridge discount, deterministic R/R, catalyst timing, and source confidence rather than a generic headline view.")
    sections.setdefault("what_would_make_me_wrong", ["A fresh filing contradicts the validated metrics.", "FCF conversion fails to support the DCF anchor."])
    return sections


def peer_unavailable_disclosure() -> list[dict[str, str]]:
    return [
        {
            "ticker": "peer_data_unavailable",
            "summary": "Mode C peer data is unavailable in this run, so peer-relative valuation is explicitly excluded. Use the subject company's validated metrics, deterministic scenarios, DCF, analyst targets, and valuation bridge until a peer mini-fetch is attached.",
        }
    ]


def load_peer_records(ticker_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    peers_dir = ticker_dir / "peers"
    if not peers_dir.exists():
        return records
    for path in sorted(peers_dir.glob("*.json")):
        payload = load_json(path)
        if is_usable_peer_record(payload):
            records.append(payload)
    return records[:5]


def is_usable_peer_record(record: dict[str, Any]) -> bool:
    if record.get("status") == "error":
        return False
    metrics = record.get("metrics")
    if not isinstance(metrics, dict):
        return False
    return any(value is not None for value in metrics.values())


def peer_comparison_from_records(
    records: list[dict[str, Any]] | None,
    *,
    language: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in records or []:
        if not is_usable_peer_record(record):
            continue
        metrics = record.get("metrics") if isinstance(record.get("metrics"), dict) else {}
        ticker = str(record.get("ticker") or "").upper()
        if not ticker:
            continue
        value = peer_value(metrics)
        if language == "ko":
            summary = f"{record.get('company_name') or ticker} peer mini-fetch: 성장, 마진, 현금흐름, 밸류에이션을 같은 yfinance 스냅샷 기준으로 비교한다."
        else:
            summary = f"{record.get('company_name') or ticker} peer mini-fetch compares growth, margin, cash conversion, and valuation on the same yfinance snapshot."
        rows.append(
            {
                "ticker": ticker,
                "summary": summary,
                "value": value,
                "tag": record.get("tag") or "[Portal]",
                "source": record.get("data_source") or "yfinance (peer mini-fetch)",
                "confidence_grade": record.get("confidence_grade") or "B",
                "metrics": metrics,
            }
        )
    return rows


def peer_value(metrics: dict[str, Any]) -> str:
    parts = []
    pe = as_number(metrics.get("pe_forward"))
    ev_ebitda = as_number(metrics.get("ev_ebitda"))
    growth = as_number(metrics.get("revenue_growth_yoy"))
    margin = as_number(metrics.get("operating_margin"))
    fcf_yield = as_number(metrics.get("fcf_yield"))
    if pe is not None:
        parts.append(f"Forward P/E {pe:.1f}x")
    if ev_ebitda is not None:
        parts.append(f"EV/EBITDA {ev_ebitda:.1f}x")
    if growth is not None:
        parts.append(f"Revenue growth {growth:.1f}%")
    if margin is not None:
        parts.append(f"Op margin {margin:.1f}%")
    if fcf_yield is not None:
        parts.append(f"FCF yield {fcf_yield:.1f}%")
    return "; ".join(parts) if parts else "Peer metrics unavailable"


def has_peer_placeholder(peers: list[Any]) -> bool:
    for peer in peers:
        if not isinstance(peer, dict):
            continue
        haystack = f"{peer.get('ticker') or ''} {peer.get('summary') or ''} {peer.get('value') or ''}".lower()
        if any(term in haystack for term in PEER_PLACEHOLDER_TERMS):
            return True
    return False


def dcf_section(calculations: dict[str, Any]) -> dict[str, Any]:
    dcf = calculations.get("dcf_analysis") if isinstance(calculations.get("dcf_analysis"), dict) else {}
    result = dcf.get("result") if isinstance(dcf.get("result"), dict) else {}
    fair_value = result.get("fair_value_per_share")
    return {
        "base": {"fair_value": fair_value, "details": result},
        "bull": {"fair_value": fair_value, "method": "base DCF plus scenario interpretation pending"},
        "bear": {"fair_value": fair_value, "method": "base DCF minus scenario interpretation pending"},
        "methodology": "Deterministic DCF from scripts/parity/calculations.py wrapping analyst dcf-calculator.py.",
        "reverse": dcf.get("reverse_dcf") or result.get("reverse_dcf"),
    }


def macro_section(validated: dict[str, Any]) -> dict[str, Any]:
    macro = validated.get("macro_context") if isinstance(validated.get("macro_context"), dict) else {}
    structured = macro.get("structured") if isinstance(macro.get("structured"), dict) else {}
    return {
        "structured": structured
        or {
            "source": "FRED",
            "status": "unavailable",
            "grade": "D",
            "reason": "macro_context_unavailable",
            "series": [],
        },
        "narrative": "Macro inputs are included only when FRED structured data is available; otherwise the analyst must not invent rates.",
    }


def analyst_coverage(validated: dict[str, Any]) -> dict[str, Any]:
    metrics = validated.get("validated_metrics") if isinstance(validated.get("validated_metrics"), dict) else {}
    return {
        "consensus": "available" if metric_value(metrics, "analyst_target_mean") is not None else "unavailable",
        "price_target": metric_value(metrics, "analyst_target_mean"),
        "source": "validated_metrics.analyst_target_mean",
    }


def analysis_valuation_bridge(calculations: dict[str, Any]) -> dict[str, Any] | None:
    bridge = calculations.get("valuation_bridge")
    if not isinstance(bridge, dict) or bridge.get("status") != "available":
        return None
    result = dict(bridge)
    result.pop("status", None)
    return result


def select_key_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    selected = {}
    for key, value in metrics.items():
        if isinstance(value, dict):
            selected[key] = value
    return selected


def source_tagged_claims(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    claims = []
    for fact in evidence.get("facts") or []:
        if not isinstance(fact, dict):
            continue
        claims.append(
            {
                "claim": fact.get("claim"),
                "sources": fact.get("sources") or [],
                "grade": fact.get("grade"),
            }
        )
    return claims


def ensure_minimum_catalysts(
    catalysts: Any,
    *,
    language: str,
    ticker: str,
    validated: dict[str, Any],
) -> list[dict[str, Any]]:
    rows = [dict(item) for item in catalysts if isinstance(item, dict)] if isinstance(catalysts, list) else []
    if not rows:
        rows.append(
            {
                "date": validated.get("analysis_date") or "date_unknown",
                "event": (
                    f"{ticker} source-tagged financial evidence refresh"
                    if language != "ko"
                    else f"{ticker} source-tagged 재무 증거 갱신"
                ),
                "significance": (
                    "Refresh deterministic scenarios, valuation bridge, and risk mechanisms with verified data."
                    if language != "ko"
                    else "검증 데이터로 deterministic scenario, valuation bridge, risk mechanism을 갱신한다."
                ),
                "narrative": "New verified data should update calculations before analyst prose changes.",
            }
        )
    while len(rows) < 2:
        rows.append(
            {
                "date": "date_unknown",
                "event": (
                    f"{ticker} scenario and R/R recalculation checkpoint"
                    if language != "ko"
                    else f"{ticker} scenario 및 R/R 재계산 체크포인트"
                ),
                "significance": (
                    "Reconcile current price, scenario targets, R/R score, and FCF evidence before changing exposure."
                    if language != "ko"
                    else "현재가, 시나리오 타깃, R/R score, FCF 증거를 함께 재점검한 뒤 노출을 바꾼다."
                ),
                "narrative": "date_unknown is used until a source-tagged event date is available.",
            }
        )
    return rows


def fixture_action_signal(language: str) -> str:
    if language == "ko":
        return "새 포지션은 deterministic R/R과 valuation bridge가 동시에 개선될 때까지 단계적으로만 접근한다."
    return "Add exposure only when deterministic R/R and the valuation bridge improve together."


def verdict_from_rr(rr_score: Any) -> str:
    value = as_number(rr_score)
    if value is None:
        return "neutral"
    if value > 3:
        return "overweight"
    if value >= 1:
        return "neutral"
    return "underweight"


def metric_value(metrics: dict[str, Any], key: str) -> float | None:
    entry = metrics.get(key)
    if not isinstance(entry, dict):
        return None
    return as_number(entry.get("value"))


def as_number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace("%", "").replace(",", "").strip())
        except ValueError:
            return None
    return None


def display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return str(path.resolve())
