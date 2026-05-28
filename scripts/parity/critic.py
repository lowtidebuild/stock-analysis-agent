"""Critic, one-pass patch, and parity summary helpers for A/B/C parity runs."""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.parity.data_sources import load_json, write_json
from scripts.parity.rendering import build_render_handoff
from tools.artifact_validation import validate_artifact_data, validate_cross_artifact_consistency
from tools.quality_report import (
    apply_critic_recheck,
    build_feedback_for_analyst,
    build_quality_report,
    combine_critic_overall,
    merge_critic_review,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class CriticResult:
    ticker: str
    artifact_root: Path
    quality_report_path: Path
    critic_review_path: Path
    loop_result_path: Path
    status: str
    patch_status: str
    delivery_ready: bool
    failing_items: list[str]


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_critic_handoff(
    *,
    language: str,
    market: str,
    mode: str,
    patch_once: bool = True,
    run_id: str,
    ticker: str,
) -> CriticResult:
    ticker_dir = REPO_ROOT / "output" / "runs" / run_id / ticker
    research_path = ticker_dir / "research-plan.json"
    validated_path = ticker_dir / "validated-data.json"
    evidence_path = ticker_dir / "evidence-pack.json"
    context_path = ticker_dir / "context-budget.json"
    analysis_path = ticker_dir / "analysis-result.json"

    research = load_json(research_path)
    validated = load_json(validated_path)
    evidence = load_json(evidence_path)
    context = load_json(context_path)
    analysis = load_json(analysis_path)
    report_path = rendered_report_path(ticker_dir, mode)

    base_quality = build_quality_report(
        research,
        validated,
        analysis,
        evidence_pack=evidence,
        context_budget=context,
        report_path=report_path,
    )
    critic_review = build_critic_review(
        analysis=analysis,
        evidence=evidence,
        mode=mode,
        rendered_report=rendered_report(ticker_dir, mode),
        validated=validated,
    )
    quality = merge_critic_review(base_quality, critic_review, build_feedback_for_analyst(critic_review))
    quality_report_path = ticker_dir / "quality-report.json"
    critic_review_path = ticker_dir / "critic-review.json"
    loop_result_path = ticker_dir / "critic-loop-result.json"
    write_json(critic_review_path, critic_review)
    write_json(quality_report_path, quality)

    patch_status = "not_needed"
    patch_payload: dict[str, Any] | None = None
    final_quality = quality
    final_critic = critic_review
    if patch_once and critic_review.get("overall") == "FAIL":
        patched_analysis, patch_payload = build_auto_patch(
            analysis=analysis,
            critic_review=critic_review,
            evidence=evidence,
            validated=validated,
        )
        if patch_payload["updates"]:
            patch_status = "applied"
            write_json(ticker_dir / "analysis-result.precritic.json", analysis)
            write_json(ticker_dir / "analysis-patch.json", patch_payload)
            validate_patched_analysis(research, validated, patched_analysis)
            write_json(analysis_path, patched_analysis)
            if mode in {"A", "C"} and report_path is not None:
                build_render_handoff(
                    language=language,
                    market=market,
                    mode=mode,
                    run_id=run_id,
                    ticker=ticker,
                )
                report_path = rendered_report_path(ticker_dir, mode)

            after_quality_core = build_quality_report(
                research,
                validated,
                patched_analysis,
                evidence_pack=evidence,
                context_budget=context,
                report_path=report_path,
            )
            recheck_review = build_recheck_review(
                original_review=critic_review,
                patched_analysis=patched_analysis,
                evidence=evidence,
                mode=mode,
                rendered_report=rendered_report(ticker_dir, mode),
                validated=validated,
            )
            quality_with_original_critic = merge_critic_review(
                after_quality_core,
                critic_review,
                build_feedback_for_analyst(critic_review),
            )
            final_quality = apply_critic_recheck(quality_with_original_critic, recheck_review)
            final_critic = final_quality["critic_review"]
            if final_critic.get("overall") == "PASS":
                # apply_critic_recheck preserves the prior explicit BLOCKER severity;
                # remove it so severity is recomputed from the rechecked PASS items.
                final_critic = copy.deepcopy(final_critic)
                final_critic.pop("severity", None)
                final_critic.pop("blocker_action", None)
                feedback = build_feedback_for_analyst(final_critic)
                final_quality = merge_critic_review(
                    after_quality_core,
                    final_critic,
                    feedback if feedback else None,
                )
                final_critic = final_quality["critic_review"]
            write_json(critic_review_path, final_critic)
            write_json(quality_report_path, final_quality)
        else:
            patch_status = "not_patchable"

    failing_items = failing_critic_items(final_critic)
    loop_result = {
        "schema_version": "abc-parity-critic-loop-v1",
        "ticker": ticker,
        "mode": mode,
        "run_context": {
            "run_id": run_id,
            "artifact_root": display_path(ticker_dir),
            "ticker": ticker,
        },
        "quality_report_path": display_path(quality_report_path),
        "critic_review_path": display_path(critic_review_path),
        "analysis_patch_path": display_path(ticker_dir / "analysis-patch.json") if patch_payload else None,
        "patch_status": patch_status,
        "critic_overall": final_critic.get("overall"),
        "delivery_gate": final_quality.get("delivery_gate"),
        "failing_items": failing_items,
        "completed_at": utc_now(),
    }
    write_json(loop_result_path, loop_result)
    return CriticResult(
        ticker=ticker,
        artifact_root=ticker_dir,
        quality_report_path=quality_report_path,
        critic_review_path=critic_review_path,
        loop_result_path=loop_result_path,
        status=str(final_critic.get("overall")),
        patch_status=patch_status,
        delivery_ready=bool((final_quality.get("delivery_gate") or {}).get("ready_for_delivery")),
        failing_items=failing_items,
    )


def build_critic_review(
    *,
    analysis: dict[str, Any],
    evidence: dict[str, Any],
    mode: str,
    rendered_report: dict[str, Any] | None,
    validated: dict[str, Any],
) -> dict[str, Any]:
    items = [
        generic_test(analysis),
        mechanism_test(analysis),
        scenario_assumption_distinctness(analysis),
        conclusion_evidence_fit(analysis, evidence, rendered_report),
        what_would_make_me_wrong_test(analysis),
        differentiator_specificity_test(analysis, validated),
        quality_report_contract_gap(analysis, mode, rendered_report),
    ]
    return {
        "reviewer": "abc-parity-deterministic-critic",
        "review_timestamp": utc_now(),
        "overall": combine_critic_overall(items),
        "items": items,
    }


def build_recheck_review(
    *,
    original_review: dict[str, Any],
    patched_analysis: dict[str, Any],
    evidence: dict[str, Any],
    mode: str,
    rendered_report: dict[str, Any] | None,
    validated: dict[str, Any],
) -> dict[str, Any]:
    full = build_critic_review(
        analysis=patched_analysis,
        evidence=evidence,
        mode=mode,
        rendered_report=rendered_report,
        validated=validated,
    )
    failing = {
        item.get("item")
        for item in original_review.get("items", [])
        if isinstance(item, dict) and item.get("status") == "FAIL"
    }
    full["items"] = [item for item in full["items"] if item.get("item") in failing]
    full["overall"] = combine_critic_overall(full["items"])
    return full


def generic_test(analysis: dict[str, Any]) -> dict[str, Any]:
    ticker = str(analysis.get("ticker") or "")
    company = str(analysis.get("company_name") or ticker)
    text = joined_text(
        analysis.get("thesis"),
        (analysis.get("sections") or {}).get("one_line_thesis") if isinstance(analysis.get("sections"), dict) else None,
        *((analysis.get("variant_view") or []) if isinstance(analysis.get("variant_view"), list) else []),
    )
    words = word_count(text)
    contains_identity = bool(ticker and ticker.lower() in text.lower()) or bool(company and company.lower() in text.lower())
    generic_markers = ("company is attractive", "strong fundamentals", "good growth", "solid business")
    if not contains_identity or words < 12 or any(marker in text.lower() for marker in generic_markers):
        return fail_item(
            "generic_test",
            "Investment Thesis & Variant View",
            "The thesis is too generic or does not identify the company-specific debate.",
            "Rewrite thesis and variant view around ticker-specific evidence, scenario math, and source-tagged metrics.",
        )
    return pass_item("generic_test", "Investment Thesis & Variant View", f"Thesis references {ticker or company} with {words} words.")


def mechanism_test(analysis: dict[str, Any]) -> dict[str, Any]:
    sections = analysis.get("sections") if isinstance(analysis.get("sections"), dict) else {}
    risks = sections.get("precision_risks") if isinstance(sections.get("precision_risks"), list) else analysis.get("top_risks")
    if not isinstance(risks, list) or len(risks) < 2:
        return fail_item(
            "mechanism_test",
            "Precision Risk",
            "Fewer than two risk rows include mechanism chains.",
            "Add at least two risks with mechanism and financial impact fields.",
        )
    weak = []
    for index, risk in enumerate(risks[:5], start=1):
        if not isinstance(risk, dict):
            weak.append(index)
            continue
        mechanism = str(risk.get("mechanism") or "")
        impact = str(risk.get("financial_impact") or risk.get("ebitda_impact") or "")
        if word_count(mechanism) < 8 or word_count(impact) < 4:
            weak.append(index)
    if weak:
        return fail_item(
            "mechanism_test",
            "Precision Risk",
            f"Risk rows {weak} lack mechanism depth or financial impact.",
            "Patch each weak risk with cause -> metric impact -> valuation impact.",
        )
    return pass_item("mechanism_test", "Precision Risk", f"{len(risks)} risk rows include mechanisms.")


def scenario_assumption_distinctness(analysis: dict[str, Any]) -> dict[str, Any]:
    scenarios = analysis.get("scenarios") if isinstance(analysis.get("scenarios"), dict) else {}
    assumptions = []
    targets = []
    for key in ("bull", "base", "bear"):
        item = scenarios.get(key)
        if not isinstance(item, dict):
            return fail_item(
                "scenario_assumption_distinctness",
                "Scenario Valuation",
                f"{key} scenario is missing.",
                "Restore bull/base/bear scenarios from deterministic-calculations.",
            )
        assumptions.append(str(item.get("key_assumption") or "").strip().lower())
        targets.append(item.get("target"))
    if len(set(assumptions)) < 3 or len([value for value in targets if value is not None]) < 3:
        return fail_item(
            "scenario_assumption_distinctness",
            "Scenario Valuation",
            "Scenario assumptions or targets are not distinct enough.",
            "Use deterministic scenario assumptions and targets exactly.",
        )
    return pass_item("scenario_assumption_distinctness", "Scenario Valuation", "Bull/base/bear assumptions are distinct.")


def conclusion_evidence_fit(
    analysis: dict[str, Any],
    evidence: dict[str, Any],
    rendered_report: dict[str, Any] | None,
) -> dict[str, Any]:
    claims = analysis.get("source_tagged_claims")
    if not isinstance(claims, list):
        sections = analysis.get("sections") if isinstance(analysis.get("sections"), dict) else {}
        claims = sections.get("source_tagged_claims")
    claim_count = len(claims) if isinstance(claims, list) else 0
    evidence_count = len(evidence.get("facts") or []) if isinstance(evidence, dict) else 0
    render_status = ((rendered_report or {}).get("validation") or {}).get("status")
    if claim_count < min(5, max(1, evidence_count)) or (rendered_report and render_status != "PASS"):
        return fail_item(
            "conclusion_evidence_fit",
            "Source-Tagged Claims",
            "The conclusion is not sufficiently tied to source-tagged claims or rendered validation failed.",
            "Restore source_tagged_claims from the evidence pack and rerun rendered validation.",
        )
    return pass_item("conclusion_evidence_fit", "Source-Tagged Claims", f"{claim_count} source-tagged claims support the output.")


def what_would_make_me_wrong_test(analysis: dict[str, Any]) -> dict[str, Any]:
    sections = analysis.get("sections") if isinstance(analysis.get("sections"), dict) else {}
    items = sections.get("what_would_make_me_wrong")
    if not isinstance(items, list) or len(items) < 2 or any(word_count(item) < 5 for item in items[:2]):
        return fail_item(
            "what_would_make_me_wrong_test",
            "What Would Make Me Wrong",
            "The report lacks concrete falsification checks.",
            "Add at least two company-specific falsification triggers tied to metrics, filings, or catalysts.",
        )
    return pass_item("what_would_make_me_wrong_test", "What Would Make Me Wrong", f"{len(items)} falsification checks present.")


def differentiator_specificity_test(analysis: dict[str, Any], validated: dict[str, Any]) -> dict[str, Any]:
    metrics = analysis.get("key_metrics") if isinstance(analysis.get("key_metrics"), dict) else {}
    source_profile = analysis.get("source_profile") or validated.get("source_profile")
    if len(metrics) < 3:
        return fail_item(
            "differentiator_specificity_test",
            "Differentiator Specificity",
            "The report has too few validated metrics to support a company-specific view.",
            "Use at least three validated metrics in thesis, KPI, and valuation sections.",
        )
    detail = f"{len(metrics)} validated metrics and source profile {source_profile} are available."
    return pass_item("differentiator_specificity_test", "Differentiator Specificity", detail)


def quality_report_contract_gap(
    analysis: dict[str, Any],
    mode: str,
    rendered_report: dict[str, Any] | None,
) -> dict[str, Any]:
    if mode in {"A", "C"}:
        contract_label = f"Mode {mode} Render Contract"
        report_name = "mode-a-render-report" if mode == "A" else "mode-c-render-report"
        if not rendered_report:
            return fail_item(
                "quality_report_contract_gap",
                contract_label,
                f"Mode {mode} critic did not receive rendered draft validation.",
                f"Render Mode {mode} output and include {report_name} before delivery.",
            )
        if ((rendered_report.get("validation") or {}).get("status")) != "PASS":
            return fail_item(
                "quality_report_contract_gap",
                contract_label,
                f"Rendered Mode {mode} output did not pass parity validator.",
                f"Patch analysis/rendering inputs and rerun Mode {mode} rendered validator.",
            )
    if mode == "C" and not analysis.get("valuation_bridge"):
        return fail_item(
            "quality_report_contract_gap",
            "Mode C Render Contract",
            "Mode C analysis is missing valuation_bridge.",
            "Restore valuation_bridge from deterministic-calculations.",
        )
    section = f"Mode {mode} Render Contract" if mode in {"A", "C"} else "Mode Render Contract"
    return pass_item("quality_report_contract_gap", section, "Mode-specific rendered contract is present.")


def build_auto_patch(
    *,
    analysis: dict[str, Any],
    critic_review: dict[str, Any],
    evidence: dict[str, Any],
    validated: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    patched = copy.deepcopy(analysis)
    updates: list[dict[str, Any]] = []
    ticker = str(patched.get("ticker") or validated.get("ticker") or "the company")
    company = str(patched.get("company_name") or validated.get("company_name") or ticker)
    metrics = patched.get("key_metrics") if isinstance(patched.get("key_metrics"), dict) else {}
    facts = evidence.get("facts") if isinstance(evidence.get("facts"), list) else []
    fact_text = "; ".join(str(fact.get("claim") or fact.get("metric")) for fact in facts[:4] if isinstance(fact, dict))
    if not fact_text:
        fact_text = "validated metrics and deterministic scenarios define the current evidence boundary"

    failing = failing_critic_items(critic_review)
    if "generic_test" in failing:
        thesis = (
            f"{company} ({ticker}) should be judged through its verified metric base, deterministic scenario targets, "
            f"and valuation bridge rather than a generic growth label. Current evidence includes {fact_text}; "
            "the investment question is whether those verified figures can support the base scenario while risk "
            "mechanisms remain contained."
        )
        set_path(patched, "thesis", thesis)
        set_path(patched, "sections.one_line_thesis", thesis)
        set_path(patched, "sections.variant_view_q1", thesis)
        updates.append(update("generic_test", "$.thesis", thesis, "Replace generic thesis with ticker-specific evidence framing."))
        updates.append(update("generic_test", "$.sections.one_line_thesis", thesis, "Keep rendered thesis aligned."))
        updates.append(update("generic_test", "$.sections.variant_view_q1", thesis, "Ensure variant view carries company-specific debate."))

    if "mechanism_test" in failing:
        price = metric_value(metrics, "price_at_analysis")
        base = scenario_target(patched, "base")
        risks = [
            {
                "risk": f"{ticker} revenue growth or demand durability weakens versus the validated trend.",
                "mechanism": "A growth miss would reduce forward estimates, lower the base scenario target, and pressure the valuation bridge because revenue and cash-flow anchors would both move lower.",
                "financial_impact": f"Base scenario target {base} and current price {price} would need to be reconciled with lower FCF conversion.",
            },
            {
                "risk": f"{ticker} free cash flow quality fails to match reported earnings.",
                "mechanism": "Higher reinvestment, working-capital drag, or margin compression would reduce FCF yield and weaken the DCF fair value before the market multiple adjusts.",
                "financial_impact": "DCF fair value, reverse DCF alignment, and weighted fair value would all move lower.",
            },
            {
                "risk": f"{ticker} consensus targets prove stale after new filings or company updates.",
                "mechanism": "If sell-side targets lag new evidence, analyst target anchors can overstate the base case and make the R/R score look better than the validated facts justify.",
                "financial_impact": "Analyst target and base scenario anchors would be reset before delivery.",
            },
        ]
        set_path(patched, "sections.precision_risks", risks)
        set_path(patched, "top_risks", risks)
        updates.append(update("mechanism_test", "$.sections.precision_risks", risks, "Add risk mechanism chains and financial impact."))
        updates.append(update("mechanism_test", "$.top_risks", risks, "Keep top risks aligned with precision risks."))

    if "what_would_make_me_wrong_test" in failing:
        wrong = [
            f"A new source filing contradicts the current {ticker} revenue, FCF, or margin evidence.",
            "Scenario probabilities no longer reconcile to the deterministic R/R after updated market price or targets.",
            "DCF and reverse DCF assumptions diverge from validated cash-flow conversion after the next reporting cycle.",
        ]
        set_path(patched, "sections.what_would_make_me_wrong", wrong)
        updates.append(update("what_would_make_me_wrong_test", "$.sections.what_would_make_me_wrong", wrong, "Add concrete falsification checks."))

    if "conclusion_evidence_fit" in failing:
        claims = [
            {
                "claim": str(fact.get("claim") or fact.get("metric") or "validated evidence"),
                "sources": fact.get("sources") if isinstance(fact, dict) else [],
                "grade": fact.get("grade") if isinstance(fact, dict) else "C",
            }
            for fact in facts[:24]
            if isinstance(fact, dict)
        ]
        set_path(patched, "source_tagged_claims", claims)
        set_path(patched, "sections.source_tagged_claims", claims)
        updates.append(update("conclusion_evidence_fit", "$.source_tagged_claims", claims, "Restore evidence-backed source claims."))

    patch_payload = {
        "schema_version": "abc-parity-analysis-patch-v1",
        "ticker": patched.get("ticker"),
        "output_mode": patched.get("output_mode"),
        "run_context": patched.get("run_context") or {},
        "task_ids": sorted(set(item["task_id"] for item in updates)),
        "updated_paths": [item["path"] for item in updates],
        "updates": updates,
        "render_required": bool(updates and patched.get("output_mode") in {"A", "C"}),
        "preserve_untouched_sections": True,
        "applied_by": "abc-parity-deterministic-critic",
        "applied_at": utc_now(),
    }
    return patched, patch_payload


def validate_patched_analysis(research: dict[str, Any], validated: dict[str, Any], analysis: dict[str, Any]) -> None:
    errors = validate_artifact_data("analysis-result", analysis)
    errors.extend(validate_cross_artifact_consistency(research, validated, analysis))
    if errors:
        raise ValueError("patched analysis-result failed validation: " + "; ".join(errors[:6]))


def rendered_report_path(ticker_dir: Path, mode: str) -> Path | None:
    if mode == "A" and (ticker_dir / "mode-a-briefing.html").exists():
        return ticker_dir / "mode-a-briefing.html"
    if mode == "C" and (ticker_dir / "mode-c-dashboard.html").exists():
        return ticker_dir / "mode-c-dashboard.html"
    return None


def rendered_report(ticker_dir: Path, mode: str) -> dict[str, Any] | None:
    if mode == "A":
        return load_json_if_exists(ticker_dir / "mode-a-render-report.json")
    if mode == "C":
        return load_json_if_exists(ticker_dir / "mode-c-render-report.json")
    return None


def load_json_if_exists(path: Path) -> dict[str, Any] | None:
    return load_json(path) if path.exists() else None


def failing_critic_items(critic_review: dict[str, Any]) -> list[str]:
    return [
        item["item"]
        for item in critic_review.get("items", [])
        if isinstance(item, dict) and item.get("status") == "FAIL" and isinstance(item.get("item"), str)
    ]


def pass_item(item: str, section: str, detail: str) -> dict[str, Any]:
    return {
        "item": item,
        "section": section,
        "status": "PASS",
        "detail": detail,
    }


def fail_item(item: str, section: str, problem: str, fix: str) -> dict[str, Any]:
    return {
        "item": item,
        "section": section,
        "status": "FAIL",
        "problem": problem,
        "fix": fix,
        "severity": "BLOCKER",
        "blocker_action": "patchable",
    }


def update(task_id: str, path: str, value: Any, rationale: str) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "path": path,
        "value": value,
        "rationale": rationale,
    }


def set_path(payload: dict[str, Any], dotted_path: str, value: Any) -> None:
    current = payload
    parts = dotted_path.split(".")
    for part in parts[:-1]:
        if not isinstance(current.get(part), dict):
            current[part] = {}
        current = current[part]
    current[parts[-1]] = value


def joined_text(*values: Any) -> str:
    chunks = []
    for value in values:
        if value is None:
            continue
        chunks.append(str(value))
    return " ".join(chunks)


def word_count(value: Any) -> int:
    return len(re.findall(r"[A-Za-z0-9가-힣']+", str(value or "")))


def metric_value(metrics: dict[str, Any], key: str) -> float | None:
    entry = metrics.get(key)
    if not isinstance(entry, dict):
        return None
    return as_number(entry.get("value"))


def scenario_target(analysis: dict[str, Any], key: str) -> float | None:
    scenarios = analysis.get("scenarios") if isinstance(analysis.get("scenarios"), dict) else {}
    item = scenarios.get(key)
    if isinstance(item, dict):
        return as_number(item.get("target"))
    return None


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


def write_run_parity_summary(*, run_id: str, tickers: list[str]) -> Path:
    run_root = REPO_ROOT / "output" / "runs" / run_id
    samples = []
    for ticker in tickers:
        ticker_dir = run_root / ticker
        quality = load_json_if_exists(ticker_dir / "quality-report.json") or {}
        loop = load_json_if_exists(ticker_dir / "critic-loop-result.json") or {}
        mode = str(quality.get("output_mode") or loop.get("mode") or "")
        render = rendered_report(ticker_dir, mode) or {}
        delivery_gate = quality.get("delivery_gate") if isinstance(quality.get("delivery_gate"), dict) else {}
        samples.append(
            {
                "ticker": ticker,
                "mode": mode,
                "quality_result": quality.get("overall_result"),
                "critic_overall": (quality.get("critic_review") or {}).get("overall") if isinstance(quality.get("critic_review"), dict) else None,
                "delivery_ready": delivery_gate.get("ready_for_delivery") is True,
                "blocking_items": delivery_gate.get("blocking_items", []),
                "patch_status": loop.get("patch_status"),
                "render_status": render.get("status"),
                "render_metrics": (render.get("validation") or {}).get("metrics") if isinstance(render.get("validation"), dict) else None,
            }
        )
    comparison = comparison_summary_sample(run_root)
    comparison_blocked = comparison is not None and not comparison["delivery_ready"]
    blocked = [sample for sample in samples if not sample["delivery_ready"]]
    summary = {
        "schema_version": "abc-parity-summary-v1",
        "run_id": run_id,
        "sample_count": len(samples),
        "pass_count": len(samples) - len(blocked),
        "blocked_count": len(blocked),
        "overall_status": "PASS" if not blocked and not comparison_blocked else "FAIL",
        "samples": samples,
        "comparison": comparison,
        "created_at": utc_now(),
    }
    path = run_root / "abc-parity-summary.json"
    write_json(path, summary)
    return path


def comparison_summary_sample(run_root: Path) -> dict[str, Any] | None:
    comparison_dir = run_root / "comparison"
    quality_path = comparison_dir / "comparison-quality-report.json"
    render_path = comparison_dir / "mode-b-render-report.json"
    analysis_path = comparison_dir / "comparison-analysis-result.json"
    if not quality_path.exists():
        return None
    quality = load_json_if_exists(quality_path) or {}
    render = load_json_if_exists(render_path) or {}
    analysis = load_json_if_exists(analysis_path) or {}
    delivery_gate = quality.get("delivery_gate") if isinstance(quality.get("delivery_gate"), dict) else {}
    return {
        "mode": "B",
        "tickers": analysis.get("compared_tickers") or quality.get("compared_tickers"),
        "quality_result": quality.get("overall_result"),
        "delivery_ready": delivery_gate.get("ready_for_delivery") is True,
        "blocking_items": delivery_gate.get("blocking_items", []),
        "render_status": render.get("status"),
        "render_metrics": (render.get("validation") or {}).get("metrics") if isinstance(render.get("validation"), dict) else None,
        "best_pick": (analysis.get("best_pick") or {}).get("ticker") if isinstance(analysis.get("best_pick"), dict) else None,
        "quality_report_path": display_path(quality_path),
    }


def display_path(path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return str(path.resolve())
