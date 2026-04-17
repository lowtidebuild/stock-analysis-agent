from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
from typing import Any

from tools.analysis_contract import build_default_report_path, find_repo_root, utc_now_iso
from tools.analysis_patch import apply_analysis_patch, load_json as load_json_file, normalize_analysis_patch
from tools.patch_plan import build_patch_plan
from tools.quality_report import apply_critic_recheck, build_quality_report


def display_path(path: str | Path, repo_root: str | Path | None = None) -> str:
    resolved = Path(path)
    root = Path(repo_root) if repo_root is not None else find_repo_root(resolved if resolved.exists() else Path.cwd())
    return str(resolved.relative_to(root)) if resolved.is_absolute() and resolved.is_relative_to(root) else str(resolved)


def load_docx_generator(repo_root: str | Path) -> Any:
    module_path = Path(repo_root) / ".claude" / "skills" / "output-generator" / "scripts" / "docx-generator.py"
    spec = importlib.util.spec_from_file_location("docx_generator_script", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load docx generator from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_dashboard_generator(repo_root: str | Path) -> Any:
    module_path = Path(repo_root) / ".claude" / "skills" / "dashboard-generator" / "scripts" / "render-dashboard.py"
    spec = importlib.util.spec_from_file_location("dashboard_generator_script", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load dashboard generator from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_comparison_generator(repo_root: str | Path) -> Any:
    module_path = Path(repo_root) / ".claude" / "skills" / "output-generator" / "scripts" / "render-comparison.py"
    spec = importlib.util.spec_from_file_location("comparison_generator_script", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load comparison generator from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_briefing_generator(repo_root: str | Path) -> Any:
    module_path = Path(repo_root) / ".claude" / "skills" / "briefing-generator" / "scripts" / "render-briefing.py"
    spec = importlib.util.spec_from_file_location("briefing_generator_script", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load briefing generator from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def resolve_report_output_path(
    analysis_result: dict[str, Any],
    output_analysis_result_path: str | Path,
    repo_root: str | Path,
    override: str | Path | None = None,
) -> Path | None:
    if override is not None:
        return Path(override)

    report_path = analysis_result.get("report_path")
    if not isinstance(report_path, str) or not report_path:
        return None

    report_candidate = Path(report_path)
    if report_candidate.is_absolute():
        return report_candidate
    return Path(repo_root) / report_candidate


def derive_default_report_output_path(analysis_result: dict[str, Any], repo_root: str | Path) -> Path | None:
    ticker = analysis_result.get("ticker")
    output_mode = analysis_result.get("output_mode")
    output_language = analysis_result.get("output_language")
    analysis_date = analysis_result.get("analysis_date")
    default_path = build_default_report_path(
        ticker=ticker,
        output_mode=output_mode,
        output_language=output_language,
        analysis_date=analysis_date,
        peer_tickers=analysis_result.get("peer_tickers"),
    )
    if default_path is None:
        return None
    return Path(repo_root) / default_path


def build_render_result(
    output_mode: str,
    analysis_result: dict[str, Any],
    output_analysis_result_path: str | Path,
    repo_root: str | Path,
    *,
    report_output_override: str | Path | None = None,
) -> dict[str, Any]:
    report_output_path = resolve_report_output_path(
        analysis_result,
        output_analysis_result_path,
        repo_root,
        override=report_output_override,
    )
    if report_output_path is None:
        report_output_path = derive_default_report_output_path(analysis_result, repo_root)
    if report_output_path is None:
        return {
            "required": False,
            "status": "not_requested",
            "engine": None,
            "report_output_path": None,
            "notes": ["No report_path was present on analysis-result.json, so no rerender was attempted."],
        }

    if output_mode == "A":
        try:
            module = load_briefing_generator(repo_root)
            output_value = module.generate_briefing(analysis_result, str(report_output_path))
            return {
                "required": True,
                "status": "rendered",
                "engine": "briefing-generator",
                "report_output_path": display_path(output_value, repo_root=repo_root),
                "rendered_at": utc_now_iso(),
                "notes": ["Mode A briefing rerender completed successfully."],
            }
        except Exception as exc:
            return {
                "required": True,
                "status": "render_failed",
                "engine": "briefing-generator",
                "report_output_path": display_path(report_output_path, repo_root=repo_root),
                "notes": [str(exc)],
            }

    if output_mode == "C":
        try:
            module = load_dashboard_generator(repo_root)
            output_value = module.generate_dashboard(analysis_result, str(report_output_path))
            return {
                "required": True,
                "status": "rendered",
                "engine": "dashboard-generator",
                "report_output_path": display_path(output_value, repo_root=repo_root),
                "rendered_at": utc_now_iso(),
                "notes": ["Mode C dashboard rerender completed successfully."],
            }
        except Exception as exc:
            return {
                "required": True,
                "status": "render_failed",
                "engine": "dashboard-generator",
                "report_output_path": display_path(report_output_path, repo_root=repo_root),
                "notes": [str(exc)],
            }

    if output_mode == "B":
        try:
            module = load_comparison_generator(repo_root)
            output_value = module.generate_comparison_report(analysis_result, str(report_output_path))
            return {
                "required": True,
                "status": "rendered",
                "engine": "comparison-generator",
                "report_output_path": display_path(output_value, repo_root=repo_root),
                "rendered_at": utc_now_iso(),
                "notes": ["Mode B peer comparison rerender completed successfully."],
            }
        except Exception as exc:
            return {
                "required": True,
                "status": "render_failed",
                "engine": "comparison-generator",
                "report_output_path": display_path(report_output_path, repo_root=repo_root),
                "notes": [str(exc)],
            }

    if output_mode == "D":
        try:
            module = load_docx_generator(repo_root)
            output_value = module.generate_docx(analysis_result, str(report_output_path))
            return {
                "required": True,
                "status": "rendered",
                "engine": "docx-generator",
                "report_output_path": display_path(output_value, repo_root=repo_root),
                "rendered_at": utc_now_iso(),
                "notes": ["Mode D DOCX rerender completed successfully."],
            }
        except Exception as exc:
            return {
                "required": True,
                "status": "render_failed",
                "engine": "docx-generator",
                "report_output_path": display_path(report_output_path, repo_root=repo_root),
                "notes": [str(exc)],
            }

    return {
        "required": True,
        "status": "manual_render_required",
        "engine": None,
        "report_output_path": display_path(report_output_path, repo_root=repo_root),
        "notes": [
            f"Mode {output_mode} render automation is not yet available in script form; rerender must be handled by the existing generator workflow.",
        ],
    }


def build_recheck_result(
    original_report: dict[str, Any],
    final_report: dict[str, Any],
    *,
    recheck_payload_path: str | None = None,
    recheck_applied: bool = False,
) -> dict[str, Any]:
    original_critic = original_report.get("critic_review") if isinstance(original_report.get("critic_review"), dict) else {}
    final_critic = final_report.get("critic_review") if isinstance(final_report.get("critic_review"), dict) else {}
    remaining_fail_items = [
        item.get("item")
        for item in final_critic.get("items", [])
        if isinstance(item, dict) and item.get("status") == "FAIL" and isinstance(item.get("item"), str)
    ]
    result = {
        "status": "applied" if recheck_applied else "not_run",
        "critic_overall_before": original_critic.get("overall"),
        "critic_overall_after": final_critic.get("overall"),
        "remaining_fail_count": len(remaining_fail_items),
        "quality_report_updated": recheck_applied,
    }
    if recheck_payload_path is not None:
        result["recheck_payload_path"] = recheck_payload_path
    if recheck_applied:
        result["remaining_fail_items"] = remaining_fail_items
    return result


def build_patch_loop_result(
    *,
    patch_plan: dict[str, Any],
    analysis_patch: dict[str, Any],
    final_quality_report: dict[str, Any],
    next_patch_plan: dict[str, Any],
    render: dict[str, Any],
    recheck: dict[str, Any],
    patch_plan_path: str,
    analysis_patch_path: str,
    analysis_result_path: str,
    quality_report_path: str,
    next_patch_plan_path: str,
) -> dict[str, Any]:
    delivery_gate = final_quality_report.get("delivery_gate") if isinstance(final_quality_report.get("delivery_gate"), dict) else {}
    delivery_ready = (
        delivery_gate.get("ready_for_delivery") is True
        and next_patch_plan.get("ready_for_redelivery") is True
        and render.get("status") in {"not_requested", "rendered"}
    )
    critic_review = final_quality_report.get("critic_review") if isinstance(final_quality_report.get("critic_review"), dict) else {}
    return {
        "ticker": patch_plan.get("ticker"),
        "output_mode": patch_plan.get("output_mode"),
        "run_context": patch_plan.get("run_context") or {},
        "source_patch_plan_path": patch_plan_path,
        "analysis_patch_path": analysis_patch_path,
        "analysis_result_path": analysis_result_path,
        "quality_report_path": quality_report_path,
        "render": render,
        "recheck": recheck,
        "next_patch_plan": {
            "path": next_patch_plan_path,
            "pending_fix_count": next_patch_plan.get("pending_fix_count"),
            "ready_for_redelivery": next_patch_plan.get("ready_for_redelivery"),
            "loop_state": next_patch_plan.get("loop_state"),
        },
        "quality_gate": {
            "overall_result": final_quality_report.get("overall_result"),
            "delivery_gate_result": delivery_gate.get("result"),
            "critic_overall": critic_review.get("overall"),
            "blocking_items": delivery_gate.get("blocking_items", []),
            "non_blocking_items": delivery_gate.get("non_blocking_items", []),
            "historical_only_items": delivery_gate.get("historical_only_items", []),
            "delivery_ready": delivery_ready,
        },
        "completed_by": "patch-loop-orchestrator",
        "completed_at": utc_now_iso(),
    }


def run_patch_loop(
    *,
    repo_root: str | Path,
    patch_plan_path: str | Path,
    raw_patch_path: str | Path,
    source_quality_report_path: str | Path,
    output_analysis_result_path: str | Path,
    output_analysis_patch_path: str | Path,
    output_quality_report_path: str | Path,
    output_patch_plan_path: str | Path,
    output_loop_result_path: str | Path | None = None,
    recheck_payload_path: str | Path | None = None,
    report_output_override: str | Path | None = None,
) -> dict[str, Any]:
    repo_root_path = Path(repo_root)
    patch_plan = load_json_file(patch_plan_path)
    raw_patch = load_json_file(raw_patch_path)
    run_context = patch_plan.get("run_context") if isinstance(patch_plan.get("run_context"), dict) else {}
    artifact_root = run_context.get("artifact_root")
    if not isinstance(artifact_root, str) or not artifact_root:
        raise ValueError("patch-plan.json is missing run_context.artifact_root")

    source_analysis_result_path = repo_root_path / patch_plan["analysis_result_path"]
    research_plan = load_json_file(repo_root_path / artifact_root / "research-plan.json")
    validated_data = load_json_file(repo_root_path / artifact_root / "validated-data.json")
    source_analysis_result = load_json_file(source_analysis_result_path)
    source_quality_report = load_json_file(source_quality_report_path)

    normalized_patch = normalize_analysis_patch(
        raw_patch,
        patch_plan,
        patch_plan_path=display_path(patch_plan_path, repo_root=repo_root_path),
        source_analysis_result_path=display_path(source_analysis_result_path, repo_root=repo_root_path),
        target_analysis_result_path=display_path(output_analysis_result_path, repo_root=repo_root_path),
    )
    updated_analysis_result = apply_analysis_patch(source_analysis_result, normalized_patch, patch_plan)
    default_report_output_path = derive_default_report_output_path(updated_analysis_result, repo_root_path)
    if updated_analysis_result.get("report_path") is None and default_report_output_path is not None:
        updated_analysis_result["report_path"] = display_path(default_report_output_path, repo_root=repo_root_path)

    rebuilt_quality_report = build_quality_report(
        research_plan,
        validated_data,
        updated_analysis_result,
        existing_report=source_quality_report,
    )

    final_quality_report = copy.deepcopy(rebuilt_quality_report)
    if recheck_payload_path is not None:
        recheck_review = load_json_file(recheck_payload_path)
        final_quality_report = apply_critic_recheck(rebuilt_quality_report, recheck_review)

    render = build_render_result(
        patch_plan.get("output_mode"),
        updated_analysis_result,
        output_analysis_result_path,
        repo_root=repo_root_path,
        report_output_override=report_output_override,
    )

    next_patch_plan = build_patch_plan(
        final_quality_report,
        analysis_result=updated_analysis_result,
        quality_report_path=display_path(output_quality_report_path, repo_root=repo_root_path),
        analysis_result_path=display_path(output_analysis_result_path, repo_root=repo_root_path),
    )

    recheck = build_recheck_result(
        source_quality_report,
        final_quality_report,
        recheck_payload_path=display_path(recheck_payload_path, repo_root=repo_root_path) if recheck_payload_path is not None else None,
        recheck_applied=recheck_payload_path is not None,
    )

    loop_result = build_patch_loop_result(
        patch_plan=patch_plan,
        analysis_patch=normalized_patch,
        final_quality_report=final_quality_report,
        next_patch_plan=next_patch_plan,
        render=render,
        recheck=recheck,
        patch_plan_path=display_path(patch_plan_path, repo_root=repo_root_path),
        analysis_patch_path=display_path(output_analysis_patch_path, repo_root=repo_root_path),
        analysis_result_path=display_path(output_analysis_result_path, repo_root=repo_root_path),
        quality_report_path=display_path(output_quality_report_path, repo_root=repo_root_path),
        next_patch_plan_path=display_path(output_patch_plan_path, repo_root=repo_root_path),
    )

    paths_to_write = [
        (Path(output_analysis_result_path), updated_analysis_result),
        (Path(output_analysis_patch_path), normalized_patch),
        (Path(output_quality_report_path), final_quality_report),
        (Path(output_patch_plan_path), next_patch_plan),
    ]
    if output_loop_result_path is not None:
        paths_to_write.append((Path(output_loop_result_path), loop_result))

    for path, payload in paths_to_write:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)

    return loop_result
