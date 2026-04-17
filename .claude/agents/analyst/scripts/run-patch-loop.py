#!/usr/bin/env python3
"""
run-patch-loop.py — Applies an analysis patch, refreshes quality-report, optionally rerenders, and optionally applies critic recheck.

Usage:
    python run-patch-loop.py \
      --patch-plan output/runs/<run_id>/<ticker>/patch-plan.json \
      --patch-json path/to/analysis-patch-input.json \
      --quality-report /tmp/quality-report-with-critic.json \
      --critic-recheck-json evals/fixtures/critic-recheck-pass.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

THIS_FILE = Path(__file__).resolve()
REPO_ROOT = THIS_FILE.parents[4]
sys.path.insert(0, str(REPO_ROOT))

from tools.artifact_validation import validate_artifact_data  # noqa: E402
from tools.patch_loop import run_patch_loop  # noqa: E402


def resolve_path(raw_path: str | None) -> Path | None:
    if raw_path is None:
        return None
    path = Path(raw_path)
    return path if path.is_absolute() else REPO_ROOT / path


def display_path(path: Path | None) -> str | None:
    if path is None:
        return None
    return str(path.relative_to(REPO_ROOT)) if path.is_absolute() and path.is_relative_to(REPO_ROOT) else str(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the analyst patch loop")
    parser.add_argument("--patch-plan", required=True, help="Path to patch-plan.json")
    parser.add_argument("--patch-json", required=True, help="Path to raw analysis patch input")
    parser.add_argument("--quality-report", help="Path to critic-merged quality-report.json (defaults to patch-plan source)")
    parser.add_argument("--critic-recheck-json", help="Optional critic partial recheck payload")
    parser.add_argument("--output-analysis-result", help="Optional output analysis-result.json path")
    parser.add_argument("--output-analysis-patch", help="Optional output analysis-patch.json path")
    parser.add_argument("--output-quality-report", help="Optional output quality-report.json path")
    parser.add_argument("--output-next-patch-plan", help="Optional output next patch-plan.json path")
    parser.add_argument("--output-loop-result", help="Optional output patch-loop-result.json path")
    parser.add_argument("--report-output", help="Optional override for final HTML/DOCX output path")
    args = parser.parse_args()

    patch_plan_path = resolve_path(args.patch_plan)
    patch_plan = json.loads(patch_plan_path.read_text(encoding="utf-8"))
    run_context = patch_plan.get("run_context") if isinstance(patch_plan.get("run_context"), dict) else {}
    artifact_root = run_context.get("artifact_root")
    if not isinstance(artifact_root, str) or not artifact_root:
        raise SystemExit("patch-plan.json is missing run_context.artifact_root")

    quality_report_path = resolve_path(args.quality_report or patch_plan.get("quality_report_path") or f"{artifact_root}/quality-report.json")
    output_analysis_result_path = resolve_path(args.output_analysis_result or f"{artifact_root}/analysis-result.json")
    output_analysis_patch_path = resolve_path(args.output_analysis_patch or f"{artifact_root}/analysis-patch.json")
    output_quality_report_path = resolve_path(args.output_quality_report or f"{artifact_root}/quality-report.json")
    output_next_patch_plan_path = resolve_path(args.output_next_patch_plan or f"{artifact_root}/patch-plan.json")
    output_loop_result_path = resolve_path(args.output_loop_result or f"{artifact_root}/patch-loop-result.json")

    loop_result = run_patch_loop(
        repo_root=REPO_ROOT,
        patch_plan_path=patch_plan_path,
        raw_patch_path=resolve_path(args.patch_json),
        source_quality_report_path=quality_report_path,
        output_analysis_result_path=output_analysis_result_path,
        output_analysis_patch_path=output_analysis_patch_path,
        output_quality_report_path=output_quality_report_path,
        output_patch_plan_path=output_next_patch_plan_path,
        output_loop_result_path=output_loop_result_path,
        recheck_payload_path=resolve_path(args.critic_recheck_json) if args.critic_recheck_json else None,
        report_output_override=resolve_path(args.report_output) if args.report_output else None,
    )

    validations = {
        "analysis-result": json.loads(output_analysis_result_path.read_text(encoding="utf-8")),
        "analysis-patch": json.loads(output_analysis_patch_path.read_text(encoding="utf-8")),
        "quality-report": json.loads(output_quality_report_path.read_text(encoding="utf-8")),
        "patch-plan": json.loads(output_next_patch_plan_path.read_text(encoding="utf-8")),
        "patch-loop-result": json.loads(output_loop_result_path.read_text(encoding="utf-8")),
    }
    validation_errors = {
        artifact_type: validate_artifact_data(artifact_type, payload, base_dir=REPO_ROOT)
        for artifact_type, payload in validations.items()
    }
    failed_validations = {artifact_type: errors for artifact_type, errors in validation_errors.items() if errors}
    if failed_validations:
        print(
            json.dumps(
                {
                    "valid": False,
                    "validation_errors": failed_validations,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        sys.exit(1)

    print(
        json.dumps(
            {
                "valid": True,
                "analysis_result_path": display_path(output_analysis_result_path),
                "analysis_patch_path": display_path(output_analysis_patch_path),
                "quality_report_path": display_path(output_quality_report_path),
                "next_patch_plan_path": display_path(output_next_patch_plan_path),
                "loop_result_path": display_path(output_loop_result_path),
                "render_status": loop_result.get("render", {}).get("status"),
                "recheck_status": loop_result.get("recheck", {}).get("status"),
                "overall_result": loop_result.get("quality_gate", {}).get("overall_result"),
                "delivery_ready": loop_result.get("quality_gate", {}).get("delivery_ready"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
