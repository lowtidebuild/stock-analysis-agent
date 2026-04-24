#!/usr/bin/env python3
"""
quality-report-builder.py — Rebuilds run-local quality-report.json from canonical artifacts.

Usage:
    python quality-report-builder.py --run-dir output/runs/20260328T000000Z_AAPL_C
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

THIS_FILE = Path(__file__).resolve()
REPO_ROOT = THIS_FILE.parents[4]
sys.path.insert(0, str(REPO_ROOT))

from tools.artifact_validation import validate_artifact_data, validate_artifact_file  # noqa: E402
from tools.quality_report import build_quality_report_from_run_dir  # noqa: E402


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build run-local quality-report.json from canonical artifacts")
    parser.add_argument("--run-dir", required=True, help="Run directory like output/runs/{run_id}")
    parser.add_argument("--report-path", default=None, help="Rendered HTML/DOCX report path to validate")
    parser.add_argument("--print-only", action="store_true", help="Print JSON without writing quality-report.json")
    args = parser.parse_args()

    run_dir = REPO_ROOT / args.run_dir
    report_path = None
    if args.report_path:
        candidate = Path(args.report_path)
        report_path = candidate if candidate.is_absolute() else REPO_ROOT / candidate
    report = build_quality_report_from_run_dir(run_dir, report_path=report_path)

    ticker_dirs = [child for child in run_dir.iterdir() if child.is_dir()]
    if len(ticker_dirs) != 1:
        raise SystemExit(f"Expected exactly one ticker directory under {run_dir}")
    quality_report_path = ticker_dirs[0] / "quality-report.json"

    if not args.print_only:
        with open(quality_report_path, "w", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2)

    if args.print_only:
        validation_errors = validate_artifact_data("quality-report", report, base_dir=REPO_ROOT)
        validation = {
            "artifact_type": "quality-report",
            "path": display_path(quality_report_path),
            "valid": not validation_errors,
            "schema_valid": not validation_errors,
            "ingestion_allowed": not validation_errors,
            "errors": validation_errors,
        }
    else:
        validation = validate_artifact_file(quality_report_path, "quality-report", base_dir=REPO_ROOT)
    print(
        json.dumps(
            {
                "quality_report_path": display_path(quality_report_path),
                "written": not args.print_only,
                "overall_result": report.get("overall_result"),
                "delivery_gate_result": (report.get("delivery_gate") or {}).get("result"),
                "ready_for_delivery": (report.get("delivery_gate") or {}).get("ready_for_delivery"),
                "max_severity": (report.get("delivery_gate") or {}).get("max_severity"),
                "item_keys": sorted(report.get("items", {}).keys()),
                "validation": validation,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
