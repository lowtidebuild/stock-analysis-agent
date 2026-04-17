#!/usr/bin/env python3
"""
apply-critic-recheck.py — Applies a partial critic recheck to an existing run-local quality report.

Usage:
    python apply-critic-recheck.py \
      --quality-report output/runs/20260328T000000Z_AAPL_C/AAPL/quality-report.json \
      --recheck-json evals/fixtures/critic-recheck-pass.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

THIS_FILE = Path(__file__).resolve()
REPO_ROOT = THIS_FILE.parents[4]
sys.path.insert(0, str(REPO_ROOT))

from tools.artifact_validation import validate_artifact_data  # noqa: E402
from tools.quality_report import apply_critic_recheck, load_json  # noqa: E402


def load_recheck_payload(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]] | None]:
    payload = load_json(path)
    if "recheck_review" in payload:
        recheck_review = payload.get("recheck_review")
        feedback = payload.get("feedback_for_analyst")
    else:
        recheck_review = payload
        feedback = payload.get("feedback_for_analyst") if isinstance(payload, dict) else None

    if not isinstance(recheck_review, dict):
        raise ValueError("recheck payload must be an object or contain a recheck_review object")
    if feedback is not None and not isinstance(feedback, list):
        raise ValueError("feedback_for_analyst must be an array when present")
    return recheck_review, feedback


def _display_path(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)) if path.is_relative_to(REPO_ROOT) else str(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply partial critic recheck to a run-local quality report")
    parser.add_argument("--quality-report", required=True, help="Path to run-local quality-report.json")
    parser.add_argument("--recheck-json", required=True, help="Path to recheck payload JSON")
    parser.add_argument("--output", help="Optional output path; defaults to in-place update")
    args = parser.parse_args()

    quality_report_path = REPO_ROOT / args.quality_report
    recheck_json_path = REPO_ROOT / args.recheck_json if not Path(args.recheck_json).is_absolute() else Path(args.recheck_json)
    output_path = (
        REPO_ROOT / args.output
        if args.output and not Path(args.output).is_absolute()
        else Path(args.output) if args.output
        else quality_report_path
    )

    quality_report = load_json(quality_report_path)
    recheck_review, feedback = load_recheck_payload(recheck_json_path)
    updated_report = apply_critic_recheck(quality_report, recheck_review, feedback)
    validation_errors = validate_artifact_data("quality-report", updated_report, base_dir=REPO_ROOT)
    if validation_errors:
        raise SystemExit(json.dumps({"valid": False, "errors": validation_errors}, ensure_ascii=False, indent=2))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(updated_report, handle, ensure_ascii=False, indent=2)

    print(
        json.dumps(
            {
                "quality_report_path": _display_path(output_path),
                "overall_result": updated_report.get("overall_result"),
                "core_overall_result": updated_report.get("core_overall_result"),
                "critic_overall": updated_report.get("critic_review", {}).get("overall"),
                "recheck_count": updated_report.get("critic_review", {}).get("recheck_count"),
                "remaining_feedback_count": len(updated_report.get("feedback_for_analyst", [])),
                "valid": True,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
