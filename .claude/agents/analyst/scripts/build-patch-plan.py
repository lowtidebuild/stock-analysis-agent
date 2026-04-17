#!/usr/bin/env python3
"""
build-patch-plan.py — Builds an analyst patch plan from a run-local quality report.

Usage:
    python build-patch-plan.py \
      --quality-report /tmp/aapl-quality-report-with-critic.json \
      --output /tmp/aapl-patch-plan.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

THIS_FILE = Path(__file__).resolve()
REPO_ROOT = THIS_FILE.parents[4]
sys.path.insert(0, str(REPO_ROOT))

from tools.patch_plan import build_patch_plan, load_json  # noqa: E402


def display_path(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)) if path.is_relative_to(REPO_ROOT) else str(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build analyst patch plan from a quality report")
    parser.add_argument("--quality-report", required=True, help="Path to quality-report.json")
    parser.add_argument("--output", help="Optional output path for patch plan JSON")
    args = parser.parse_args()

    quality_report_path = (
        REPO_ROOT / args.quality_report
        if not Path(args.quality_report).is_absolute()
        else Path(args.quality_report)
    )
    output_path = (
        REPO_ROOT / args.output
        if args.output and not Path(args.output).is_absolute()
        else Path(args.output) if args.output
        else None
    )

    quality_report = load_json(quality_report_path)
    analysis_result_path = None
    analysis_result = None
    run_context = quality_report.get("run_context") if isinstance(quality_report.get("run_context"), dict) else {}
    artifact_root = run_context.get("artifact_root")
    if output_path is None and isinstance(artifact_root, str):
        output_path = (
            REPO_ROOT / f"{artifact_root}/patch-plan.json"
            if not Path(f"{artifact_root}/patch-plan.json").is_absolute()
            else Path(f"{artifact_root}/patch-plan.json")
        )
    if isinstance(artifact_root, str):
        candidate = (
            REPO_ROOT / f"{artifact_root}/analysis-result.json"
            if not Path(f"{artifact_root}/analysis-result.json").is_absolute()
            else Path(f"{artifact_root}/analysis-result.json")
        )
        analysis_result_path = display_path(candidate)
        if candidate.exists():
            analysis_result = load_json(candidate)

    patch_plan = build_patch_plan(
        quality_report,
        analysis_result=analysis_result,
        quality_report_path=display_path(quality_report_path),
        analysis_result_path=analysis_result_path,
    )

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as handle:
            json.dump(patch_plan, handle, ensure_ascii=False, indent=2)

    print(
        json.dumps(
            {
                "quality_report_path": display_path(quality_report_path),
                "output_path": display_path(output_path) if output_path else None,
                "pending_fix_count": patch_plan.get("pending_fix_count"),
                "ready_for_redelivery": patch_plan.get("ready_for_redelivery"),
                "loop_state": patch_plan.get("loop_state"),
                "task_ids": [task.get("task_id") for task in patch_plan.get("tasks", [])],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
