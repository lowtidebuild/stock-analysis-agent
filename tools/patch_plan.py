from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from tools.analysis_contract import build_default_report_path


MAX_FEEDBACK_LOOPS = 1


def load_json(path: str | Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def normalize_label(text: str | None) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"[^a-z0-9가-힣]+", " ", text.lower()).strip()
    return re.sub(r"\s+", " ", cleaned)


def infer_analysis_targets(output_mode: str, section: str | None, source_item: str | None) -> list[str]:
    mode = (output_mode or "").upper()
    label = normalize_label(section)
    item = normalize_label(source_item)

    def targets(*values: str) -> list[str]:
        return list(values)

    if mode == "A":
        if "thesis" in label:
            return targets("sections.one_line_thesis")
        if "timeline" in label:
            if "past" in label:
                return targets("sections.timeline_past")
            if "future" in label:
                return targets("sections.timeline_future")
            return targets("sections.timeline_past", "sections.timeline_future")
        if "catalyst" in label or "action signal" in label:
            return targets("upcoming_catalysts", "sections.action_signal")
        if "risk" in label or "risk" in item:
            return targets("top_risks")

    if mode == "B":
        if "comparison" in label or "matrix" in label or "table" in label:
            return targets("price_at_analysis", "key_metrics")
        if "scenario" in label:
            return targets("scenarios")
        if "ranking" in label or "rr score" in label or "r r score" in label:
            return targets("rr_score", "verdict", "scenarios")
        if "best pick" in label:
            return targets("rr_score", "verdict", "top_risks", "upcoming_catalysts", "key_metrics")
        if "differentiator" in label or "differentiat" in label:
            return targets("top_risks", "upcoming_catalysts", "key_metrics", "scenarios")

    if "precision risk" in label or "risk" in item:
        return targets("sections.precision_risks")
    if "quality of earnings" in label or "qoe" in label:
        return targets("sections.quality_of_earnings" if mode == "D" else "sections.qoe_summary")
    if "executive summary" in label:
        return targets("sections.executive_summary")
    if "business overview" in label or "competitive position" in label:
        return targets("sections.business_overview")
    if "financial performance" in label:
        return targets("sections.financial_performance")
    if "valuation" in label:
        return targets("sections.valuation_analysis", "sections.dcf_analysis")
    if "investment scenarios" in label or "scenarios" in label:
        return (
            targets("scenarios", "sections.investment_scenarios")
            if mode == "D"
            else targets("scenarios")
        )
    if "peer comparison" in label or "peers" in label:
        return targets("sections.peer_comparison", "sections.peer_comparison_narrative")
    if "management" in label or "governance" in label:
        return targets("sections.management_governance")
    if "what would make me wrong" in label or "pre mortem" in label or "premortem" in label:
        return targets("sections.what_would_make_me_wrong", "sections.pre_mortem")
    if "portfolio strategy" in label:
        return targets("sections.portfolio_strategy", "sections.what_would_make_me_wrong")
    if "analyst coverage" in label:
        return targets("sections.analyst_coverage")
    if "charts" in label:
        return targets("sections.charts")
    if "quarterly" in label:
        return targets("sections.qoe_summary", "sections.quarterly_financials")
    if "variant view" in label or "generic test" in item:
        if "q1" in label:
            return targets("sections.variant_view_q1")
        if "q2" in label:
            return targets("sections.variant_view_q2")
        if "q3" in label:
            return targets("sections.variant_view_q3")
        if "q4" in label:
            return targets("sections.variant_view_q4")
        if "q5" in label:
            return targets("sections.variant_view_q5")
        if mode == "D":
            return targets(
                "sections.variant_view_q1",
                "sections.variant_view_q2",
                "sections.variant_view_q3",
                "sections.variant_view_q4",
                "sections.variant_view_q5",
            )
        return targets("sections.variant_view_q1", "sections.variant_view_q2", "sections.variant_view_q3")
    if "header" in label:
        return targets("price_at_analysis", "key_metrics", "data_quality_used")
    if "kpi" in label:
        return targets("key_metrics")
    if "data backing" in item or "math consistency" in item:
        return targets("key_metrics", "scenarios")
    return []


def infer_report_targets(output_mode: str, section: str | None) -> list[str]:
    mode = (output_mode or "").upper()
    label = section or ""
    normalized = normalize_label(section)

    if normalized:
        return [label]

    if mode == "D":
        return ["Executive Summary", "Target Section in DOCX rerender"]
    if mode == "C":
        return ["Target Section in HTML dashboard rerender"]
    if mode == "B":
        return ["Target row/section in peer comparison HTML"]
    return ["Target section in Mode A briefing HTML"]


def infer_source_item(feedback_item: dict[str, Any], critic_review: dict[str, Any] | None) -> str | None:
    if not isinstance(critic_review, dict):
        return None
    review_items = critic_review.get("items")
    if not isinstance(review_items, list):
        return None

    section = feedback_item.get("section")
    problem = feedback_item.get("problem")
    for item in review_items:
        if not isinstance(item, dict):
            continue
        if item.get("section") == section and item.get("problem") == problem:
            return item.get("item")
    for item in review_items:
        if not isinstance(item, dict):
            continue
        if item.get("section") == section:
            return item.get("item")
    return None


def build_patch_plan(
    quality_report: dict[str, Any],
    analysis_result: dict[str, Any] | None = None,
    quality_report_path: str | None = None,
    analysis_result_path: str | None = None,
) -> dict[str, Any]:
    run_context = quality_report.get("run_context") or {}
    output_mode = quality_report.get("output_mode")
    critic_review = quality_report.get("critic_review") if isinstance(quality_report.get("critic_review"), dict) else None
    feedback = quality_report.get("feedback_for_analyst") if isinstance(quality_report.get("feedback_for_analyst"), list) else []
    report_output_path = None
    if isinstance(analysis_result, dict):
        report_output_path = analysis_result.get("report_path")
        if report_output_path is None:
            report_output_path = build_default_report_path(
                ticker=analysis_result.get("ticker") or quality_report.get("ticker"),
                output_mode=analysis_result.get("output_mode") or output_mode,
                output_language=analysis_result.get("output_language"),
                analysis_date=analysis_result.get("analysis_date"),
                peer_tickers=analysis_result.get("peer_tickers"),
            )

    artifact_root = run_context.get("artifact_root")
    if analysis_result_path is None and isinstance(artifact_root, str):
        analysis_result_path = f"{artifact_root}/analysis-result.json"

    tasks = []
    for index, feedback_item in enumerate(feedback, start=1):
        if not isinstance(feedback_item, dict):
            continue
        section = feedback_item.get("section")
        problem = feedback_item.get("problem")
        requested_fix = feedback_item.get("fix")
        source_item = infer_source_item(feedback_item, critic_review)
        analysis_targets = infer_analysis_targets(output_mode, section, source_item)
        report_targets = infer_report_targets(output_mode, section)
        task_id_base = normalize_label(source_item or section or f"task {index}").replace(" ", "_") or f"task_{index}"
        edit_scope = "analysis_json_and_render" if analysis_targets else "report_render_only"
        tasks.append(
            {
                "task_id": f"{index:02d}_{task_id_base}",
                "priority": index,
                "source_item": source_item,
                "section": section,
                "problem": problem,
                "requested_fix": requested_fix,
                "analysis_targets": analysis_targets,
                "report_targets": report_targets,
                "edit_scope": edit_scope,
                "render_step_required": bool(report_output_path),
                "notes": [
                    "Patch only the failing section; preserve all previously passing critic items.",
                ],
            }
        )

    current_recheck_count = 0
    if critic_review and isinstance(critic_review.get("recheck_count"), int):
        current_recheck_count = critic_review["recheck_count"]
    remaining_recheck_budget = max(0, MAX_FEEDBACK_LOOPS - current_recheck_count)

    if tasks:
        loop_state = "patch_and_recheck" if remaining_recheck_budget > 0 else "patch_or_deliver_with_flags"
    else:
        loop_state = "ready_for_delivery"

    return {
        "ticker": quality_report.get("ticker"),
        "output_mode": output_mode,
        "run_context": run_context,
        "quality_report_path": quality_report_path,
        "analysis_result_path": analysis_result_path,
        "report_output_path": report_output_path,
        "critic_overall": critic_review.get("overall") if critic_review else None,
        "current_recheck_count": current_recheck_count,
        "remaining_recheck_budget": remaining_recheck_budget,
        "pending_fix_count": len(tasks),
        "ready_for_redelivery": len(tasks) == 0,
        "loop_state": loop_state,
        "tasks": tasks,
    }
