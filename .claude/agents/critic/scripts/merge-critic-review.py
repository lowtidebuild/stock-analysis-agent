#!/usr/bin/env python3
"""
merge-critic-review.py — Safely attaches critic findings to a run-local quality report.

Usage:
    python merge-critic-review.py \
      --quality-report output/runs/20260328T000000Z_AAPL_C/AAPL/quality-report.json \
      --critic-json /tmp/critic-review.json
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
from tools.quality_report import load_json, merge_critic_review  # noqa: E402


def load_critic_payload(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]] | None]:
    payload = load_json(path)
    if "critic_review" in payload:
        critic_review = payload.get("critic_review")
        feedback = payload.get("feedback_for_analyst")
    else:
        critic_review = payload
        feedback = None

    if not isinstance(critic_review, dict):
        raise ValueError("critic payload must be an object or contain a critic_review object")
    if feedback is not None and not isinstance(feedback, list):
        raise ValueError("feedback_for_analyst must be an array when present")
    return critic_review, feedback


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge critic review into a run-local quality report")
    parser.add_argument("--quality-report", required=True, help="Path to run-local quality-report.json")
    parser.add_argument("--critic-json", required=True, help="Path to critic review JSON payload")
    parser.add_argument("--output", help="Optional output path; defaults to in-place update")
    args = parser.parse_args()

    quality_report_path = REPO_ROOT / args.quality_report
    critic_json_path = REPO_ROOT / args.critic_json if not Path(args.critic_json).is_absolute() else Path(args.critic_json)
    output_path = REPO_ROOT / args.output if args.output else quality_report_path

    quality_report = load_json(quality_report_path)
    critic_review, feedback = load_critic_payload(critic_json_path)
    merged_report = merge_critic_review(quality_report, critic_review, feedback)
    validation_errors = validate_artifact_data("quality-report", merged_report, base_dir=REPO_ROOT)
    if validation_errors:
        raise SystemExit(json.dumps({"valid": False, "errors": validation_errors}, ensure_ascii=False, indent=2))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(merged_report, handle, ensure_ascii=False, indent=2)

    print(
        json.dumps(
            {
                "quality_report_path": (
                    str(output_path.relative_to(REPO_ROOT))
                    if output_path.is_relative_to(REPO_ROOT)
                    else str(output_path)
                ),
                "overall_result": merged_report.get("overall_result"),
                "core_overall_result": merged_report.get("core_overall_result"),
                "critic_overall": merged_report.get("critic_review", {}).get("overall"),
                "feedback_count": len(merged_report.get("feedback_for_analyst", [])),
                "valid": True,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
