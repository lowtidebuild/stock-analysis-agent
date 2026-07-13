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
from scripts.parity.formatting import (
    as_number,
    format_plain_number,
    metric_display_from_metrics as metric_display,
    metric_value,
    money_text,
    percent_text,
)
from tools.artifact_validation import (
    validate_artifact_data,
    validate_cross_artifact_consistency,
)
from tools.backend_providers import FIXTURE_BACKEND_PROVIDERS

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
FIXTURE_BACKEND_NAMES = FIXTURE_BACKEND_PROVIDERS
CODEX_NATIVE_BACKEND_NAMES = {"codex_native", "codex", "local_codex"}


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
    backend_key = backend_name.lower()
    if backend_key in FIXTURE_BACKEND_NAMES:
        analyst_json = build_fixture_analysis(
            calculations=calculations,
            evidence=evidence,
            language=language,
            mode=mode,
            peer_records=peer_records,
            validated=validated,
        )
        backend_meta = {"provider": "fixture", "model": "deterministic-fixture", "usage": {}}
    elif backend_key in CODEX_NATIVE_BACKEND_NAMES:
        analyst_json = build_codex_native_analysis(
            calculations=calculations,
            evidence=evidence,
            language=language,
            mode=mode,
            peer_records=peer_records,
            validated=validated,
        )
        backend_meta = {
            "provider": "codex_native",
            "model": "local-deterministic-analyst",
            "usage": {"api_calls": 0},
        }
    else:
        schema = load_analysis_schema()
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
        thesis = f"{company}({ticker})는 검증된 숫자와 결정론적 시나리오 기준으로 판단해야 하며, 핵심 논점은 성장 지속성, FCF 전환, 밸류에이션 부담의 균형이다."
        risk_prefix = "검증된 지표가 약화되면"
        catalyst_prefix = "다음 확인 지점은"
        variant_view_q1 = f"{thesis} 첫 번째 차별적 질문은 현재 성장률이 현금 전환 악화 없이 복리로 이어질 수 있는지다."
        variant_view_q2 = f"{company}는 밸류에이션 지지가 단순한 멀티플 확장이 아니라 지속 가능한 이익 체력에서 나오는지 입증해야 한다."
        variant_view_q3 = "하방 논점은 출처가 검증된 FCF와 마진 증거가 투자심리 리셋을 흡수할 수 있는지다."
        precision_risks = [
            {
                "risk": f"{risk_prefix} 성장 프리미엄이 낮아질 수 있다.",
                "mechanism": "성장 기대가 실망으로 바뀌면 선행 추정치가 내려가고, 밸류에이션 멀티플이 압축되며, 약세 시나리오 목표가 쪽으로 재평가될 수 있다.",
                "financial_impact": "매출 성장률과 FCF 전환율이 낮아지면 기준 시나리오 적정가가 하락한다.",
            },
            {
                "risk": f"{risk_prefix} FCF 품질이 보고 이익을 따라가지 못할 수 있다.",
                "mechanism": "재투자 부담이나 운전자본 부담이 커지면 FCF 수익률이 낮아지고 DCF 지지력이 약해진다.",
                "financial_impact": "DCF 적정가와 밸류에이션 브리지의 가중 적정가가 낮아진다.",
            },
            {
                "risk": f"{risk_prefix} 컨센서스 목표가가 뒤처질 수 있다.",
                "mechanism": "추정치 변경은 후행 재무제표보다 애널리스트 목표가 앵커를 더 빠르게 움직일 수 있다.",
                "financial_impact": "시나리오 기준값과 애널리스트 목표가 앵커를 다시 설정해야 한다.",
            },
        ]
        qoe_narrative = "이익 품질은 검증된 지표로만 판단하며, Grade D 필드는 추정으로 채우지 않고 제외한다."
        portfolio_strategy = "포지션 크기는 일반적인 매수/매도 문구보다 결정론적 R/R 점수, 밸류에이션 브리지의 할인 또는 프리미엄, 다음 증거 확인 지점을 기준으로 정해야 한다."
        wrong_checks = [
            "새 증거 반영 후 시나리오 확률과 기준 시나리오가 서로 맞지 않는다.",
            "FCF 전환율이 검증 데이터 추세에서 크게 벗어난다.",
            "새 공시나 회사 발표가 현재 출처 태그 지표와 충돌한다.",
        ]
        disclaimer = "투자 조언이 아니며, 결과는 실행 시점의 검증된 산출물에 따라 달라집니다."
        rr_score_interpretation = "결정론적 시나리오가 R/R 점수를 정의하고, 애널리스트 문장은 증거와의 정합성을 설명한다."
        catalyst_event = f"{catalyst_prefix} 출처 태그가 붙은 최신 재무 증거다."
        catalyst_significance = "새 검증 데이터로 밸류에이션과 시나리오 앵커를 갱신한다."
        catalyst_narrative = "애널리스트 논지가 바뀌기 전에 새 검증 지표가 결정론적 계산을 먼저 갱신해야 한다."
    else:
        thesis = f"{company} ({ticker}) should be judged on verified metrics and deterministic scenarios; the core debate is growth durability, FCF conversion, and valuation risk."
        risk_prefix = "If verified metrics weaken"
        catalyst_prefix = "The next checkpoint is"
        variant_view_q1 = f"{thesis} The first variant question is whether current growth can compound without degrading cash conversion."
        variant_view_q2 = f"{company} must prove that valuation support is driven by durable earnings power rather than multiple expansion alone."
        variant_view_q3 = "The downside debate is whether source-verified FCF and margin evidence can absorb a sentiment reset."
        precision_risks = [
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
        ]
        qoe_narrative = "Quality of earnings is judged from validated metrics only; Grade D fields are excluded rather than filled with guesses."
        portfolio_strategy = "Position sizing should follow the deterministic R/R score, valuation bridge discount or premium, and upcoming evidence checkpoints rather than a generic buy/sell label."
        wrong_checks = [
            "Scenario probabilities stop summing to the deterministic base case after new evidence.",
            "FCF conversion diverges materially from the validated-data trend.",
            "A new filing or company release contradicts the current source-tagged metrics.",
        ]
        disclaimer = "This is not investment advice; outputs depend on the verified artifacts available at run time."
        rr_score_interpretation = "Deterministic scenarios define the R/R score; analyst text explains the evidence fit."
        catalyst_event = f"{catalyst_prefix} updated source-tagged financial evidence."
        catalyst_significance = "Refresh valuation and scenario anchors with new verified data."
        catalyst_narrative = "New validated metrics should update the deterministic calculations before the analyst thesis changes."

    sections: dict[str, Any] = {
        "one_line_thesis": thesis,
        "action_signal": fixture_action_signal(language),
        "variant_view_q1": variant_view_q1,
        "variant_view_q2": variant_view_q2,
        "variant_view_q3": variant_view_q3,
        "precision_risks": precision_risks,
        "valuation_metrics": list((calculations.get("ratio_recomputation") or {}).get("computed_metrics", {}).values()),
        "dcf_analysis": dcf_section(calculations),
        "macro_context": macro_section(validated),
        "peer_comparison": peer_comparison_from_records(peer_records, language=language)
        or peer_unavailable_disclosure(),
        "analyst_coverage": analyst_coverage(validated),
        "qoe_summary": {
            "narrative": qoe_narrative,
            "fact_basis": fact_text,
        },
        "portfolio_strategy": portfolio_strategy,
        "what_would_make_me_wrong": wrong_checks,
        "source_tagged_claims": source_tagged_claims(evidence),
        "disclaimer": disclaimer,
    }
    if mode == "A":
        sections["briefing_summary"] = thesis
    if mode == "B":
        sections["relative_view"] = "Mode B comparison ranking is deferred to the comparison pass; this per-ticker analyst result supplies comparable inputs."
    return {
        "verdict": "neutral",
        "rr_score_interpretation": rr_score_interpretation,
        "thesis": thesis,
        "variant_view": [sections["variant_view_q1"], sections["variant_view_q2"], sections["variant_view_q3"]],
        "top_risks": sections["precision_risks"],
        "upcoming_catalysts": [
            {
                "date": validated.get("analysis_date"),
                "event": catalyst_event,
                "significance": catalyst_significance,
                "narrative": catalyst_narrative,
            }
        ],
        "sections": sections,
    }


def build_codex_native_analysis(
    *,
    calculations: dict[str, Any],
    evidence: dict[str, Any],
    language: str,
    mode: str,
    peer_records: list[dict[str, Any]] | None = None,
    validated: dict[str, Any],
) -> dict[str, Any]:
    """Build an analyst-result draft from local verified artifacts only.

    This is the Codex-native path for runs where the operator wants the full
    Mode C pipeline without an external analyst LLM call.
    """

    metrics = validated.get("validated_metrics") if isinstance(validated.get("validated_metrics"), dict) else {}
    company = str(validated.get("company_name") or validated.get("ticker") or "the company")
    ticker = str(validated.get("ticker") or company)
    currency = str(validated.get("currency") or "USD")
    scenarios = (calculations.get("scenario_analysis") or {}).get("scenarios")
    scenarios = scenarios if isinstance(scenarios, dict) else {}
    scenario_analysis = calculations.get("scenario_analysis") if isinstance(calculations.get("scenario_analysis"), dict) else {}
    rr_score = scenario_analysis.get("rr_score")
    verdict = verdict_from_rr(rr_score)
    price = metric_value(metrics, "price_at_analysis")
    base_target = scenario_target(scenarios, "base")
    bull_target = scenario_target(scenarios, "bull")
    bear_target = scenario_target(scenarios, "bear")
    dcf_result = (calculations.get("dcf_analysis") or {}).get("result")
    dcf_result = dcf_result if isinstance(dcf_result, dict) else {}
    dcf_value = dcf_result.get("fair_value_per_share")
    reverse = calculations.get("reverse_dcf") if isinstance(calculations.get("reverse_dcf"), dict) else {}
    bridge = calculations.get("valuation_bridge") if isinstance(calculations.get("valuation_bridge"), dict) else {}
    weighted_fair_value = bridge.get("weighted_fair_value")
    implied_growth = reverse.get("implied_fcf_growth")
    analyst_growth = reverse.get("analyst_growth_assumption")
    gap_bp = reverse.get("growth_gap_bp")
    profile = company_domain_profile(company=company, ticker=ticker, language=language)

    revenue_text = metric_display(metrics, "revenue_ttm", currency=currency)
    growth_text = metric_display(metrics, "revenue_growth_yoy", currency=currency)
    margin_text = metric_display(metrics, "operating_margin", currency=currency)
    fcf_yield_text = metric_display(metrics, "fcf_yield", currency=currency)
    ev_ebitda_text = metric_display(metrics, "ev_ebitda", currency=currency)
    forward_pe_text = metric_display(metrics, "pe_forward", currency=currency)
    if forward_pe_text == "-":
        forward_pe_text = metric_display(metrics, "pe_ratio", currency=currency)
    beta_text = metric_display(metrics, "beta", currency=currency)
    price_text = money_text(price, currency)
    base_text = money_text(base_target, currency)
    bull_text = money_text(bull_target, currency)
    bear_text = money_text(bear_target, currency)
    dcf_text = money_text(dcf_value, currency)
    bridge_text = money_text(weighted_fair_value, currency)
    implied_growth_text = percent_text(implied_growth, probability=True)
    analyst_growth_text = percent_text(analyst_growth, probability=True)

    if language == "ko":
        thesis = (
            f"{company}({ticker})는 {profile} 노출이 핵심인 기업으로, 검증 지표상 TTM 매출 {revenue_text}, "
            f"YoY 매출 성장률 {growth_text}, 영업이익률 {margin_text}를 기록했다. "
            f"12개월 시나리오 기준 현재가 {price_text} 대비 기준 목표가 {base_text}와 강세 목표가 {bull_text}가 "
            f"남아 있어 R/R {format_plain_number(rr_score)}는 {korean_verdict(verdict)} 구조다. "
            f"다만 DCF 적정가 {dcf_text}와 가중 적정가 {bridge_text}가 현재가와 얼마나 벌어지는지가 "
            "투자 판단의 핵심이며, 성장의 방향성보다 그 성장에 이미 지불한 멀티플이 FCF로 정당화되는지가 더 중요하다."
        )
        variant_q1 = (
            f"성장 지속성: {ticker}의 {growth_text} 매출 성장은 {profile} 투자 사이클을 반영한다. "
            f"기준 목표가 {base_text}가 유지되려면 신규 수요와 매출 전환이 동시에 확인되어야 하며, "
            f"둔화가 보이면 약세 목표가 {bear_text}가 먼저 리스크 기준점이 된다."
        )
        variant_q2 = (
            f"현금흐름 전환: FCF 수익률은 {fcf_yield_text}이고 DCF 적정가는 {dcf_text}다. "
            f"역산 DCF는 시장이 {implied_growth_text} FCF 성장을 요구한다고 읽히며, "
            f"base 가정 {analyst_growth_text}와의 차이가 안전마진을 좌우한다."
        )
        variant_q3 = (
            f"밸류에이션: EV/EBITDA {ev_ebitda_text}, forward PER {forward_pe_text}, beta {beta_text}는 "
            f"주가가 성장 기대와 할인율에 민감하다는 뜻이다. 시나리오 R/R은 {format_plain_number(rr_score)}지만, "
            "장기 DCF 앵커와 12개월 목표가 앵커가 서로 다른 메시지를 내는지 계속 분리해 봐야 한다."
        )
        action_signal = (
            f"{korean_verdict(verdict)}로 보되, 노출 조정은 현재가 {price_text}, 기준 목표가 {base_text}, "
            f"가중 적정가 {bridge_text}, FCF 수익률 {fcf_yield_text}를 함께 확인한 뒤 단계적으로 판단한다."
        )
        qoe_narrative = (
            f"이익 품질은 성장률 {growth_text}, 영업이익률 {margin_text}, FCF 수익률 {fcf_yield_text}의 조합으로 본다. "
            "매출과 마진이 좋아도 현금흐름 전환이 뒤처지면 DCF 지지력은 약해진다."
        )
        portfolio_strategy = (
            f"신규 진입은 기준 목표가 {base_text}까지의 여력과 가중 적정가 {bridge_text} 대비 프리미엄을 나눠 보고, "
            "기존 보유는 다음 실적에서 매출 성장과 FCF 전환이 동시에 유지되는지 확인하면서 조절한다."
        )
        wrong_checks = [
            f"다음 검증 데이터에서 매출 성장률과 FCF 수익률이 동시에 개선되어 {implied_growth_text} 내재 성장 요구가 현실적인 범위로 내려온다.",
            f"DCF 적정가 {dcf_text}와 가중 적정가 {bridge_text}가 현재가 {price_text}에 가까워질 만큼 할인율 또는 FCF 추정이 개선된다.",
            f"동종 peer 멀티플이 {ticker} 쪽으로 재평가되어 EV/EBITDA {ev_ebitda_text} 프리미엄이 구조적으로 정당화된다.",
        ]
        rr_score_interpretation = (
            f"R/R {format_plain_number(rr_score)}는 결정론적 약세 {bear_text}, 기준 {base_text}, 강세 {bull_text} "
            "시나리오에서 계산되며, Codex-native 분석은 이 산출물을 재계산하지 않고 설명만 붙인다."
        )
        disclaimer = "투자 조언이 아니며, 모든 판단은 실행 시점의 검증 산출물과 이후 회사 공시 및 시장 데이터 업데이트에 따라 달라질 수 있다."
    else:
        thesis = (
            f"{company} ({ticker}) is a {profile} story with verified TTM revenue of {revenue_text}, "
            f"YoY revenue growth of {growth_text}, and operating margin of {margin_text}. "
            f"On the 12-month scenario frame, current price {price_text} compares with base target {base_text} "
            f"and bull target {bull_text}, leaving deterministic R/R of {format_plain_number(rr_score)}. "
            f"The key debate is whether FCF can compound enough to justify the multiple already embedded in price, "
            f"given DCF fair value {dcf_text} and weighted fair value {bridge_text}."
        )
        variant_q1 = (
            f"Growth durability: {ticker}'s {growth_text} revenue growth reflects the {profile} cycle. "
            f"Base target {base_text} requires demand and conversion to keep confirming; if growth rolls over, "
            f"bear target {bear_text} becomes the risk reference."
        )
        variant_q2 = (
            f"Cash conversion: FCF yield is {fcf_yield_text} and DCF fair value is {dcf_text}. "
            f"Reverse DCF reads market-implied FCF growth near {implied_growth_text} versus the base assumption of {analyst_growth_text}, "
            "so the margin of safety depends on converting growth into cash."
        )
        variant_q3 = (
            f"Valuation: EV/EBITDA {ev_ebitda_text}, forward P/E {forward_pe_text}, and beta {beta_text} show sensitivity "
            f"to both growth expectations and discount rates. Scenario R/R is {format_plain_number(rr_score)}, "
            "but the long-term DCF anchor and 12-month target anchor should be kept separate."
        )
        action_signal = (
            f"Treat the signal as {verdict}; change exposure only after reconciling current price {price_text}, "
            f"base target {base_text}, weighted fair value {bridge_text}, and FCF yield {fcf_yield_text}."
        )
        qoe_narrative = (
            f"Quality of earnings is judged from growth {growth_text}, operating margin {margin_text}, and FCF yield {fcf_yield_text}. "
            "Revenue and margin strength matter less if cash conversion fails to support the DCF anchor."
        )
        portfolio_strategy = (
            f"For new exposure, compare upside to base target {base_text} with the premium or discount to weighted fair value {bridge_text}. "
            "For existing exposure, scale around the next evidence update on revenue growth and FCF conversion."
        )
        wrong_checks = [
            f"Revenue growth and FCF yield both improve enough for the {implied_growth_text} implied growth requirement to look realistic.",
            f"DCF fair value {dcf_text} and weighted fair value {bridge_text} move materially closer to current price {price_text}.",
            f"Peer multiples re-rate toward {ticker}, structurally supporting the EV/EBITDA {ev_ebitda_text} premium.",
        ]
        rr_score_interpretation = (
            f"R/R {format_plain_number(rr_score)} is calculated from deterministic bear {bear_text}, base {base_text}, "
            f"and bull {bull_text} scenarios; the Codex-native pass explains those artifacts without recalculating them."
        )
        disclaimer = "This is not investment advice; judgments depend on the verified run artifacts and later company or market updates."

    precision_risks = codex_precision_risks(
        analyst_growth_text=analyst_growth_text,
        base_target=base_text,
        bear_target=bear_text,
        bridge_text=bridge_text,
        company=company,
        dcf_text=dcf_text,
        ev_ebitda_text=ev_ebitda_text,
        fcf_yield_text=fcf_yield_text,
        growth_text=growth_text,
        implied_growth_text=implied_growth_text,
        language=language,
        margin_text=margin_text,
        peer_records=peer_records,
        price_text=price_text,
        rr_score=rr_score,
        ticker=ticker,
    )
    sections: dict[str, Any] = {
        "one_line_thesis": thesis,
        "action_signal": action_signal,
        "variant_view_q1": variant_q1,
        "variant_view_q2": variant_q2,
        "variant_view_q3": variant_q3,
        "precision_risks": precision_risks,
        "valuation_metrics": list((calculations.get("ratio_recomputation") or {}).get("computed_metrics", {}).values())
        or [{"metric": "unavailable"}],
        "dcf_analysis": dcf_section(calculations),
        "macro_context": macro_section(validated),
        "peer_comparison": peer_comparison_from_records(peer_records, language=language)
        or peer_unavailable_disclosure(),
        "analyst_coverage": analyst_coverage(validated),
        "qoe_summary": {
            "narrative": qoe_narrative,
            "fact_basis": first_fact_basis(evidence),
            "grade_boundary": validated.get("overall_grade"),
        },
        "portfolio_strategy": portfolio_strategy,
        "what_would_make_me_wrong": wrong_checks,
        "source_tagged_claims": source_tagged_claims(evidence),
        "disclaimer": disclaimer,
    }
    if mode == "A":
        sections["briefing_summary"] = thesis
    if mode == "B":
        sections["relative_view"] = (
            "Mode B comparison ranking is deferred to the comparison pass; this local Codex result supplies comparable inputs."
        )
    return {
        "verdict": verdict,
        "rr_score_interpretation": rr_score_interpretation,
        "thesis": thesis,
        "variant_view": [variant_q1, variant_q2, variant_q3],
        "top_risks": precision_risks,
        "upcoming_catalysts": codex_catalysts(
            analysis_date=validated.get("analysis_date"),
            language=language,
            ticker=ticker,
        ),
        "sections": sections,
        "disclaimer": disclaimer,
        "codex_native_notes": {
            "external_analyst_api_calls": 0,
            "growth_gap_bp": gap_bp,
        },
    }


def codex_precision_risks(
    *,
    analyst_growth_text: str,
    base_target: str,
    bear_target: str,
    bridge_text: str,
    company: str,
    dcf_text: str,
    ev_ebitda_text: str,
    fcf_yield_text: str,
    growth_text: str,
    implied_growth_text: str,
    language: str,
    margin_text: str,
    peer_records: list[dict[str, Any]] | None,
    price_text: str,
    rr_score: Any,
    ticker: str,
) -> list[dict[str, Any]]:
    has_peers = bool(peer_records)
    if language == "ko":
        risks = [
            {
                "risk": f"{company}({ticker})의 성장 프리미엄이 신규 수요 둔화로 압축될 수 있다.",
                "mechanism": f"매출 성장률 {growth_text}가 둔화되면 기준 목표가 {base_target}의 전제가 약해지고, 투자자는 약세 목표가 {bear_target} 쪽 확률을 높인다.",
                "financial_impact": f"R/R {format_plain_number(rr_score)}가 낮아지고, 현재가 {price_text} 대비 하방 기준이 더 중요해진다.",
            },
            {
                "risk": "높은 성장 기대가 실제 FCF 전환보다 앞서갈 수 있다.",
                "mechanism": f"FCF 수익률 {fcf_yield_text}와 영업이익률 {margin_text}가 함께 개선되지 않으면 DCF {dcf_text}와 가중 적정가 {bridge_text}가 주가를 지지하기 어렵다.",
                "financial_impact": f"시장이 요구하는 {implied_growth_text} FCF 성장과 base 가정 {analyst_growth_text}의 차이가 멀티플 정상화 하방으로 작동한다.",
            },
            {
                "risk": "할인율 또는 밸류에이션 멀티플 변화에 민감하다.",
                "mechanism": f"EV/EBITDA {ev_ebitda_text} 수준에서는 금리, 리스크 프리미엄, 성장률 가정이 조금만 바뀌어도 장기 현금흐름 현재가치가 크게 변한다.",
                "financial_impact": f"DCF {dcf_text}와 현재가 {price_text} 사이의 괴리가 커지면 가중 적정가 {bridge_text}가 더 엄격한 리스크 기준이 된다.",
            },
        ]
        if has_peers:
            risks.append(
                {
                    "risk": "동종업계 대비 프리미엄이 과도하다고 판단될 수 있다.",
                    "mechanism": "peer mini-fetch가 낮은 상대 멀티플을 보여주면 투자자는 성장 프리미엄의 지속성을 더 빠르게 재검증한다.",
                    "financial_impact": f"상대가치 프리미엄 축소는 기준 목표가 {base_target}보다 가중 적정가 {bridge_text}를 먼저 보게 만든다.",
                }
            )
        return risks
    risks = [
        {
            "risk": f"{company} ({ticker}) growth premium could compress if new demand slows.",
            "mechanism": f"If revenue growth {growth_text} decelerates, the premise behind base target {base_target} weakens and investors assign more weight to bear target {bear_target}.",
            "financial_impact": f"R/R {format_plain_number(rr_score)} would fall and downside versus current price {price_text} becomes the tighter risk reference.",
        },
        {
            "risk": "Growth expectations could outrun actual FCF conversion.",
            "mechanism": f"If FCF yield {fcf_yield_text} and operating margin {margin_text} fail to improve together, DCF {dcf_text} and weighted fair value {bridge_text} provide less support.",
            "financial_impact": f"The gap between market-implied {implied_growth_text} FCF growth and base assumption {analyst_growth_text} becomes multiple-normalization downside.",
        },
        {
            "risk": "The stock is sensitive to discount-rate and valuation multiple changes.",
            "mechanism": f"At EV/EBITDA {ev_ebitda_text}, small changes in rates, risk premium, or growth assumptions can materially change long-term cash-flow present value.",
            "financial_impact": f"If the gap between DCF {dcf_text} and current price {price_text} widens, weighted fair value {bridge_text} becomes the stricter risk anchor.",
        },
    ]
    if has_peers:
        risks.append(
            {
                "risk": "The relative valuation premium may be challenged versus peers.",
                "mechanism": "If the peer mini-fetch shows lower relative multiples, investors will re-test whether the growth premium is durable.",
                "financial_impact": f"Premium compression would move the debate from base target {base_target} toward weighted fair value {bridge_text}.",
            }
        )
    return risks


def codex_catalysts(*, analysis_date: Any, language: str, ticker: str) -> list[dict[str, Any]]:
    if language == "ko":
        return [
            {
                "date": analysis_date,
                "event": "다음 실적과 신규 수요/수주 업데이트",
                "significance": "매출 성장과 FCF 전환이 동시에 유지되는지 확인한다.",
                "narrative": "검증 데이터가 바뀌면 시나리오 목표가, R/R, DCF 앵커를 먼저 갱신한다.",
            },
            {
                "date": "date_unknown",
                "event": f"{ticker} peer 멀티플 및 컨센서스 목표가 재점검",
                "significance": "성장 프리미엄과 애널리스트 목표가 앵커가 현재 가격을 지지하는지 확인한다.",
                "narrative": "날짜가 확인되지 않은 이벤트는 정량 산출물에 직접 반영하지 않는다.",
            },
        ]
    return [
        {
            "date": analysis_date,
            "event": "Next earnings and demand/order update",
            "significance": "Check whether revenue growth and FCF conversion persist together.",
            "narrative": "When verified data changes, refresh scenario targets, R/R, and DCF anchors first.",
        },
        {
            "date": "date_unknown",
            "event": f"{ticker} peer multiple and consensus target reset",
            "significance": "Check whether the growth premium and analyst target anchor still support price.",
            "narrative": "Undated events are not directly reflected in deterministic calculations.",
        },
    ]


def company_domain_profile(*, company: str, ticker: str, language: str) -> str:
    haystack = f"{company} {ticker}".lower()
    if "vertiv" in haystack or ticker.upper() == "VRT":
        return "데이터센터 전력·냉각 인프라" if language == "ko" else "data-center power and cooling infrastructure"
    if "sk하이닉스" in haystack or "hynix" in haystack or ticker == "000660":
        return "AI 메모리/HBM과 반도체 사이클" if language == "ko" else "AI memory, HBM, and the semiconductor cycle"
    if "palantir" in haystack or ticker.upper() == "PLTR":
        return "AI 소프트웨어와 데이터 플랫폼" if language == "ko" else "AI software and data platforms"
    if "apple" in haystack or ticker.upper() == "AAPL":
        return "프리미엄 디바이스와 서비스 생태계" if language == "ko" else "premium devices and services ecosystem"
    return "검증된 성장, 마진, 현금흐름" if language == "ko" else "verified growth, margin, and cash-flow"


def scenario_target(scenarios: dict[str, Any], case: str) -> float | None:
    row = scenarios.get(case)
    if not isinstance(row, dict):
        return None
    return as_number(row.get("target") or row.get("target_price"))


def korean_verdict(verdict: str) -> str:
    return {
        "overweight": "비중확대",
        "neutral": "중립",
        "underweight": "비중축소",
    }.get(verdict, verdict)


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
        grade = str(record.get("confidence_grade") or "C").upper()
        if grade not in {"C", "D"}:
            # Peer mini-fetch is a single-source yfinance snapshot, so C is the
            # ceiling; legacy caches may still carry the pre-policy "B" during
            # their 24h TTL — clamp instead of passing the inflated grade on.
            grade = "C"
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
                "confidence_grade": grade,
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


def display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return str(path.resolve())
