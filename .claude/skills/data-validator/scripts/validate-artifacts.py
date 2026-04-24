#!/usr/bin/env python3
"""
validate-artifacts.py — Validates run-local artifacts and snapshots against repository schemas.

Usage:
    python validate-artifacts.py --artifact-type validated-data --input output/runs/<run_id>/AAPL/validated-data.json
    python validate-artifacts.py --run-dir output/runs/<run_id>
"""

import argparse
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

THIS_FILE = Path(__file__).resolve()
REPO_ROOT = THIS_FILE.parents[4]
sys.path.insert(0, str(REPO_ROOT))

from tools.artifact_validation import validate_artifact_file, validate_run_directory  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate artifact files or run directories")
    parser.add_argument("--artifact-type", choices=[
        "run-manifest",
        "research-plan",
        "validated-data",
        "evidence-pack",
        "context-budget",
        "analysis-result",
        "quality-report",
        "tier1-raw",
        "tier2-raw",
        "dart-api-raw",
        "yfinance-raw",
        "fred-snapshot",
        "patch-plan",
        "analysis-patch",
        "patch-loop-result",
        "snapshot",
    ])
    parser.add_argument("--input", default=None, help="Path to the artifact file to validate")
    parser.add_argument("--run-dir", default=None, help="Path to output/runs/<run_id>")
    args = parser.parse_args()

    if args.run_dir:
        result = validate_run_directory(Path(args.run_dir), base_dir=REPO_ROOT)
    else:
        if not args.artifact_type or not args.input:
            parser.error("--artifact-type and --input are required unless --run-dir is provided")
        result = validate_artifact_file(Path(args.input), args.artifact_type, base_dir=REPO_ROOT)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result.get("valid", False) or not result.get("ingestion_allowed", True):
        sys.exit(1)


if __name__ == "__main__":
    main()
