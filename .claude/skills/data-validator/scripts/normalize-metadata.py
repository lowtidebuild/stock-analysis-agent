#!/usr/bin/env python3
"""
normalize-metadata.py — Rewrites metric metadata to the canonical source contract.

Usage:
    python normalize-metadata.py --artifact-type validated-data --input output/data/005930/validated-data.json
    python normalize-metadata.py --artifact-type analysis-result --input output/runs/<run_id>/AAPL/analysis-result.json --in-place
"""

import argparse
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

THIS_FILE = Path(__file__).resolve()
REPO_ROOT = THIS_FILE.parents[4]
sys.path.insert(0, str(REPO_ROOT))

from tools.analysis_contract import normalize_metric_mapping  # noqa: E402


def normalize_payload(artifact_type: str, payload: dict) -> tuple[dict, list[str]]:
    market = payload.get("market")
    warnings: list[str] = []

    if artifact_type == "validated-data":
        normalized_metrics, metric_warnings = normalize_metric_mapping(payload.get("validated_metrics", {}), market=market)
        payload["validated_metrics"] = normalized_metrics
        warnings.extend(metric_warnings)
    elif artifact_type in {"analysis-result", "snapshot"}:
        normalized_metrics, metric_warnings = normalize_metric_mapping(payload.get("key_metrics", {}), market=market)
        payload["key_metrics"] = normalized_metrics
        warnings.extend(metric_warnings)
    else:
        warnings.append(f"Artifact type {artifact_type} does not currently have metric normalization rules")

    return payload, warnings


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize metric metadata to canonical source tags")
    parser.add_argument("--artifact-type", required=True, choices=["validated-data", "analysis-result", "snapshot"])
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", default=None)
    parser.add_argument("--in-place", action="store_true")
    args = parser.parse_args()

    input_path = Path(args.input)
    with open(input_path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)

    normalized_payload, warnings = normalize_payload(args.artifact_type, payload)

    if args.in_place:
        output_path = input_path
    elif args.output:
        output_path = Path(args.output)
    else:
        output_path = input_path.with_name(f"{input_path.stem}.normalized{input_path.suffix}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(normalized_payload, handle, ensure_ascii=False, indent=2)

    result = {
        "status": "ok",
        "artifact_type": args.artifact_type,
        "input": str(input_path),
        "output": str(output_path),
        "warnings": warnings,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
