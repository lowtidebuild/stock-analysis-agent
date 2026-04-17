#!/usr/bin/env python3
"""
apply-analysis-patch.py — Applies a guarded analysis patch to analysis-result.json.

Usage:
    python apply-analysis-patch.py \
      --patch-plan output/runs/<run_id>/<ticker>/patch-plan.json \
      --patch-json path/to/analysis-patch-input.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

THIS_FILE = Path(__file__).resolve()
REPO_ROOT = THIS_FILE.parents[4]
sys.path.insert(0, str(REPO_ROOT))

from tools.analysis_patch import apply_analysis_patch, load_json, normalize_analysis_patch  # noqa: E402
from tools.artifact_validation import validate_artifact_data, validate_cross_artifact_consistency  # noqa: E402


def resolve_path(raw_path: str | None) -> Path | None:
    if raw_path is None:
        return None
    path = Path(raw_path)
    return path if path.is_absolute() else REPO_ROOT / path


def display_path(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)) if path.is_relative_to(REPO_ROOT) else str(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply an analyst patch constrained by patch-plan.json")
    parser.add_argument("--patch-plan", required=True, help="Path to patch-plan.json")
    parser.add_argument("--patch-json", required=True, help="Path to raw patch input JSON")
    parser.add_argument("--output-analysis-result", help="Optional output path for patched analysis-result.json")
    parser.add_argument("--output-patch-record", help="Optional output path for normalized analysis-patch.json")
    args = parser.parse_args()

    patch_plan_path = resolve_path(args.patch_plan)
    patch_json_path = resolve_path(args.patch_json)
    output_analysis_result_path = resolve_path(args.output_analysis_result)
    output_patch_record_path = resolve_path(args.output_patch_record)

    patch_plan = load_json(patch_plan_path)
    analysis_result_hint = patch_plan.get("analysis_result_path")
    if not isinstance(analysis_result_hint, str) or not analysis_result_hint:
        raise SystemExit("patch-plan.json does not declare analysis_result_path")

    source_analysis_result_path = resolve_path(analysis_result_hint)
    if source_analysis_result_path is None or not source_analysis_result_path.exists():
        raise SystemExit(f"Source analysis-result.json not found: {analysis_result_hint}")

    run_context = patch_plan.get("run_context") if isinstance(patch_plan.get("run_context"), dict) else {}
    artifact_root = run_context.get("artifact_root")
    if output_analysis_result_path is None:
        output_analysis_result_path = source_analysis_result_path
    if output_patch_record_path is None:
        if isinstance(artifact_root, str) and artifact_root:
            output_patch_record_path = resolve_path(f"{artifact_root}/analysis-patch.json")
        else:
            output_patch_record_path = output_analysis_result_path.parent / "analysis-patch.json"

    raw_patch = load_json(patch_json_path)
    normalized_patch = normalize_analysis_patch(
        raw_patch,
        patch_plan,
        patch_plan_path=display_path(patch_plan_path),
        source_analysis_result_path=display_path(source_analysis_result_path),
        target_analysis_result_path=display_path(output_analysis_result_path),
    )

    patch_errors = validate_artifact_data("analysis-patch", normalized_patch, base_dir=REPO_ROOT)
    if patch_errors:
        print(
            json.dumps(
                {
                    "valid": False,
                    "stage": "analysis-patch",
                    "errors": patch_errors,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        sys.exit(1)

    source_analysis_result = load_json(source_analysis_result_path)
    updated_analysis_result = apply_analysis_patch(source_analysis_result, normalized_patch, patch_plan)

    analysis_errors = validate_artifact_data("analysis-result", updated_analysis_result, base_dir=REPO_ROOT)
    if isinstance(artifact_root, str) and artifact_root:
        research_plan_path = resolve_path(f"{artifact_root}/research-plan.json")
        validated_data_path = resolve_path(f"{artifact_root}/validated-data.json")
        if research_plan_path and research_plan_path.exists() and validated_data_path and validated_data_path.exists():
            research_plan = load_json(research_plan_path)
            validated_data = load_json(validated_data_path)
            analysis_errors.extend(
                validate_cross_artifact_consistency(
                    research_plan,
                    validated_data,
                    updated_analysis_result,
                )
            )

    if analysis_errors:
        print(
            json.dumps(
                {
                    "valid": False,
                    "stage": "analysis-result",
                    "errors": analysis_errors,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        sys.exit(1)

    output_analysis_result_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_analysis_result_path, "w", encoding="utf-8") as handle:
        json.dump(updated_analysis_result, handle, ensure_ascii=False, indent=2)

    output_patch_record_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_patch_record_path, "w", encoding="utf-8") as handle:
        json.dump(normalized_patch, handle, ensure_ascii=False, indent=2)

    print(
        json.dumps(
            {
                "valid": True,
                "patch_plan_path": display_path(patch_plan_path),
                "patch_record_path": display_path(output_patch_record_path),
                "output_analysis_result_path": display_path(output_analysis_result_path),
                "task_ids": normalized_patch.get("task_ids"),
                "updated_paths": normalized_patch.get("updated_paths"),
                "render_required": normalized_patch.get("render_required"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
