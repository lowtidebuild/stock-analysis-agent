#!/usr/bin/env python3
"""
eval_harness.py — Runs repository-level validation cases against artifacts and run directories.

Usage:
    python tools/eval_harness.py --manifest evals/cases/default.json
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

THIS_FILE = Path(__file__).resolve()
REPO_ROOT = THIS_FILE.parents[1]
sys.path.insert(0, str(REPO_ROOT))

from tools.analysis_contract import extract_numeric_value  # noqa: E402
from tools.artifact_validation import validate_artifact_file, validate_run_directory  # noqa: E402

EMPTY_VALUES = (None, "", [], {})


def load_json(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def parse_path(path: str) -> list[str | int]:
    normalized = path.strip()
    if normalized in {"", "$"}:
        return []
    if normalized.startswith("$."):
        normalized = normalized[2:]
    elif normalized.startswith("$"):
        normalized = normalized[1:]

    tokens: list[str | int] = []
    buffer = ""
    index = 0
    while index < len(normalized):
        char = normalized[index]
        if char == ".":
            if buffer:
                tokens.append(buffer)
                buffer = ""
            index += 1
            continue
        if char == "[":
            if buffer:
                tokens.append(buffer)
                buffer = ""
            closing = normalized.find("]", index)
            if closing == -1:
                raise ValueError(f"Unclosed index in path: {path}")
            raw_index = normalized[index + 1:closing]
            if not raw_index.isdigit():
                raise ValueError(f"Non-numeric index {raw_index!r} in path: {path}")
            tokens.append(int(raw_index))
            index = closing + 1
            continue
        buffer += char
        index += 1
    if buffer:
        tokens.append(buffer)
    return tokens


def resolve_path(payload: Any, path: str) -> tuple[bool, Any, str | None]:
    current = payload
    for token in parse_path(path):
        if isinstance(token, int):
            if not isinstance(current, list):
                return False, None, f"{path}: expected list before index [{token}]"
            if token >= len(current):
                return False, None, f"{path}: missing list index [{token}]"
            current = current[token]
            continue

        if not isinstance(current, dict):
            return False, None, f"{path}: expected object before key {token}"
        if token not in current:
            return False, None, f"{path}: missing key {token}"
        current = current[token]

    return True, current, None


def collect_payload_assertion_errors(payload: Any, assertions: dict[str, Any] | None, label: str) -> list[str]:
    if not assertions:
        return []

    errors: list[str] = []

    for path in assertions.get("required_paths", []):
        found, value, reason = resolve_path(payload, path)
        if not found:
            errors.append(f"{label}: missing required path {path} ({reason})")
        elif value in EMPTY_VALUES:
            errors.append(f"{label}: required path {path} is empty")

    for path, expected in assertions.get("equals", {}).items():
        found, value, reason = resolve_path(payload, path)
        if not found:
            errors.append(f"{label}: missing expected-equals path {path} ({reason})")
        elif value != expected:
            errors.append(f"{label}: expected {path} == {expected!r}, got {value!r}")

    for item in assertions.get("contains", []):
        path = item["path"]
        expected = item["value"]
        found, value, reason = resolve_path(payload, path)
        if not found:
            errors.append(f"{label}: missing contains path {path} ({reason})")
            continue

        if isinstance(value, list):
            matched = expected in value
        elif isinstance(value, str):
            matched = str(expected) in value
        elif isinstance(value, dict):
            matched = expected in value or expected in value.values()
        else:
            matched = False

        if not matched:
            errors.append(f"{label}: expected {path} to contain {expected!r}, got {value!r}")

    for item in assertions.get("numeric_ranges", []):
        path = item["path"]
        minimum = item.get("min")
        maximum = item.get("max")
        found, value, reason = resolve_path(payload, path)
        if not found:
            errors.append(f"{label}: missing numeric range path {path} ({reason})")
            continue

        numeric_value = extract_numeric_value(value)
        if numeric_value is None:
            errors.append(f"{label}: path {path} is not numeric ({value!r})")
            continue
        if minimum is not None and numeric_value < minimum:
            errors.append(f"{label}: expected {path} >= {minimum}, got {numeric_value}")
        if maximum is not None and numeric_value > maximum:
            errors.append(f"{label}: expected {path} <= {maximum}, got {numeric_value}")

    for item in assertions.get("list_lengths", []):
        path = item["path"]
        found, value, reason = resolve_path(payload, path)
        if not found:
            errors.append(f"{label}: missing list length path {path} ({reason})")
            continue
        if not isinstance(value, (list, dict, str)):
            errors.append(f"{label}: path {path} does not support len() ({value!r})")
            continue
        length = len(value)
        if "equals" in item and length != item["equals"]:
            errors.append(f"{label}: expected len({path}) == {item['equals']}, got {length}")
        if "min" in item and length < item["min"]:
            errors.append(f"{label}: expected len({path}) >= {item['min']}, got {length}")
        if "max" in item and length > item["max"]:
            errors.append(f"{label}: expected len({path}) <= {item['max']}, got {length}")

    return errors


def load_run_payloads(result: dict[str, Any]) -> dict[str, Any]:
    payloads: dict[str, Any] = {}
    for subresult in result.get("results", []):
        artifact_type = subresult.get("artifact_type")
        artifact_path = subresult.get("path")
        if not artifact_type or not artifact_path:
            continue
        path = Path(artifact_path)
        if path.exists() and path.is_file():
            payloads[artifact_type] = load_json(path)
    return payloads


def collect_case_assertion_errors(
    case: dict[str, Any],
    kind: str,
    payloads: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    if kind == "artifact":
        artifact_type = case["artifact_type"]
        payload = payloads.get(artifact_type)
        if payload is None:
            return [f"artifact:{artifact_type}: payload unavailable for assertions"]
        return collect_payload_assertion_errors(payload, case.get("assertions"), f"artifact:{artifact_type}")

    artifact_assertions = case.get("artifact_assertions", {})
    for artifact_type, assertions in artifact_assertions.items():
        payload = payloads.get(artifact_type)
        if payload is None:
            errors.append(f"run_dir:{artifact_type}: payload unavailable for assertions")
            continue
        errors.extend(collect_payload_assertion_errors(payload, assertions, f"run_dir:{artifact_type}"))
    return errors


def collect_comparison_assertion_errors(
    left_payload: Any,
    right_payload: Any,
    assertions: dict[str, Any] | None,
    label: str,
) -> list[str]:
    if not assertions:
        return []

    errors: list[str] = []
    errors.extend(collect_payload_assertion_errors(left_payload, {
        "required_paths": assertions.get("left_required_paths", []),
    }, f"{label}:left"))
    errors.extend(collect_payload_assertion_errors(right_payload, {
        "required_paths": assertions.get("right_required_paths", []),
    }, f"{label}:right"))

    for item in assertions.get("path_pairs_equal", []):
        left_path = item["left"]
        right_path = item["right"]
        left_found, left_value, left_reason = resolve_path(left_payload, left_path)
        right_found, right_value, right_reason = resolve_path(right_payload, right_path)
        if not left_found:
            errors.append(f"{label}: missing left path {left_path} ({left_reason})")
            continue
        if not right_found:
            errors.append(f"{label}: missing right path {right_path} ({right_reason})")
            continue
        if left_value != right_value:
            errors.append(f"{label}: expected {left_path} == {right_path}, got {left_value!r} vs {right_value!r}")

    for item in assertions.get("numeric_pairs_close", []):
        left_path = item["left"]
        right_path = item["right"]
        tolerance = item.get("tolerance", 0.0)
        left_found, left_value, left_reason = resolve_path(left_payload, left_path)
        right_found, right_value, right_reason = resolve_path(right_payload, right_path)
        if not left_found:
            errors.append(f"{label}: missing left numeric path {left_path} ({left_reason})")
            continue
        if not right_found:
            errors.append(f"{label}: missing right numeric path {right_path} ({right_reason})")
            continue
        left_numeric = extract_numeric_value(left_value)
        right_numeric = extract_numeric_value(right_value)
        if left_numeric is None or right_numeric is None:
            errors.append(f"{label}: non-numeric comparison {left_path}={left_value!r}, {right_path}={right_value!r}")
            continue
        if abs(left_numeric - right_numeric) > tolerance:
            errors.append(
                f"{label}: expected {left_path} ~= {right_path} within {tolerance}, got {left_numeric} vs {right_numeric}"
            )

    return errors


def load_delta_module():
    module_path = REPO_ROOT / ".claude" / "skills" / "data-manager" / "scripts" / "delta-comparator.py"
    spec = importlib.util.spec_from_file_location("delta_comparator_script", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load delta comparator module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def completeness_checks(artifact_type: str, artifact_path: Path) -> list[str]:
    # Completeness now lives in tools.artifact_validation so normal artifact
    # validation and run-dir validation share the same contract.
    return []


def evaluate_case(case: dict[str, Any]) -> dict[str, Any]:
    kind = case["kind"]
    path = REPO_ROOT / case["path"] if "path" in case else None
    expect_valid = case.get("expect_valid", True)
    required_substrings = case.get("required_error_substrings", [])
    payloads: dict[str, Any] = {}

    if kind == "artifact":
        result = validate_artifact_file(path, case["artifact_type"], base_dir=REPO_ROOT)
        completeness_issues = completeness_checks(case["artifact_type"], path)
        if completeness_issues:
            result["valid"] = False
            result["errors"].extend(completeness_issues)
        if path.exists():
            payloads[case["artifact_type"]] = load_json(path)
    elif kind == "run_dir":
        result = validate_run_directory(path, base_dir=REPO_ROOT)
        completeness_issues = []
        for subresult in result["results"]:
            if subresult["artifact_type"] == "analysis-result" and Path(subresult["path"]).exists():
                completeness_issues.extend(completeness_checks("analysis-result", Path(subresult["path"])))
        if completeness_issues:
            result["valid"] = False
            result.setdefault("results", []).append({
                "artifact_type": "analysis-result-completeness",
                "path": str(path),
                "valid": False,
                "errors": completeness_issues,
            })
        payloads = load_run_payloads(result)
    elif kind == "comparison":
        left_path = REPO_ROOT / case["left"]["path"]
        right_path = REPO_ROOT / case["right"]["path"]
        left_payload = load_json(left_path)
        right_payload = load_json(right_path)
        payloads = {
            "left": left_payload,
            "right": right_payload,
        }
        assertion_errors = collect_comparison_assertion_errors(
            left_payload,
            right_payload,
            case.get("assertions"),
            "comparison",
        )
        result = {
            "left_path": str(left_path),
            "right_path": str(right_path),
            "valid": not assertion_errors,
            "errors": assertion_errors,
        }
    elif kind == "delta":
        module = load_delta_module()
        data_root = case.get("data_root")
        try:
            delta_payload = module.build_delta_report(
                case["ticker"],
                case["old_date"],
                case["new_date"],
                data_root=data_root,
            )
            payloads = {"delta": delta_payload}
            assertion_errors = collect_payload_assertion_errors(
                delta_payload,
                case.get("assertions"),
                "delta",
            )
            result = {
                "delta": delta_payload,
                "valid": not assertion_errors,
                "errors": assertion_errors,
            }
        except Exception as exc:
            result = {
                "delta": None,
                "valid": False,
                "errors": [str(exc)],
            }
    else:
        raise ValueError(f"Unsupported case kind: {kind}")

    all_errors = []
    if kind in {"artifact", "comparison", "delta"}:
        all_errors.extend(result.get("errors", []))
    else:
        for subresult in result.get("results", []):
            all_errors.extend(subresult.get("errors", []))

    matches_expectation = result.get("valid", False) == expect_valid
    missing_expected_substrings = [
        needle for needle in required_substrings
        if not any(needle in error for error in all_errors)
    ]
    assertion_errors = [] if kind in {"comparison", "delta"} else collect_case_assertion_errors(case, kind, payloads)
    if missing_expected_substrings or assertion_errors:
        matches_expectation = False

    return {
        "id": case["id"],
        "kind": kind,
        "path": (
            str(path)
            if path is not None
            else (
                f"{case['left']['path']} -> {case['right']['path']}"
                if kind == "comparison"
                else f"{case['ticker']}:{case['old_date']}->{case['new_date']}"
            )
        ),
        "expect_valid": expect_valid,
        "actual_valid": result.get("valid", False),
        "matches_expectation": matches_expectation,
        "missing_expected_substrings": missing_expected_substrings,
        "assertion_errors": assertion_errors,
        "result": result,
    }


def run_manifest(manifest_path: Path) -> dict[str, Any]:
    manifest = load_json(manifest_path)
    cases = manifest.get("cases", [])
    evaluated = [evaluate_case(case) for case in cases]
    passed = sum(1 for item in evaluated if item["matches_expectation"])
    return {
        "manifest": str(manifest_path),
        "case_count": len(evaluated),
        "passed": passed,
        "failed": len(evaluated) - passed,
        "all_matched_expectation": passed == len(evaluated),
        "cases": evaluated,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run artifact evaluation cases")
    parser.add_argument("--manifest", required=True)
    args = parser.parse_args()

    summary = run_manifest(REPO_ROOT / args.manifest)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if not summary["all_matched_expectation"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
