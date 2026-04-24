#!/usr/bin/env python3
"""
contract_checks.py — Local/CI entrypoint for schema and eval validation.

Usage:
    python tools/contract_checks.py
    python tools/contract_checks.py --manifest evals/cases/default.json
    python tools/contract_checks.py --verbose
"""

from __future__ import annotations

import argparse
import compileall
import json
import shutil
import sys
from pathlib import Path

THIS_FILE = Path(__file__).resolve()
REPO_ROOT = THIS_FILE.parents[1]
sys.path.insert(0, str(REPO_ROOT))

from tools.eval_harness import run_manifest  # noqa: E402
from tools.paths import data_path  # noqa: E402


COMPILE_DIRS = [
    REPO_ROOT / "tools",
    REPO_ROOT / ".claude" / "agents" / "analyst" / "scripts",
    REPO_ROOT / ".claude" / "agents" / "critic" / "scripts",
    REPO_ROOT / ".claude" / "skills" / "data-manager" / "scripts",
    REPO_ROOT / ".claude" / "skills" / "data-validator" / "scripts",
    REPO_ROOT / ".claude" / "skills" / "briefing-generator" / "scripts",
    REPO_ROOT / ".claude" / "skills" / "dashboard-generator" / "scripts",
    REPO_ROOT / ".claude" / "skills" / "quality-checker" / "scripts",
    REPO_ROOT / ".claude" / "skills" / "output-generator" / "scripts",
]
RUNTIME_OUTPUT_FIXTURE_ROOT = REPO_ROOT / "evals" / "fixtures" / "runtime_output"


def ensure_runtime_output_fixtures() -> list[str]:
    copied: list[str] = []
    if not RUNTIME_OUTPUT_FIXTURE_ROOT.exists():
        return copied

    destination_root = data_path()
    for fixture_path in sorted(RUNTIME_OUTPUT_FIXTURE_ROOT.rglob("*")):
        if fixture_path.is_dir():
            continue
        relative_path = fixture_path.relative_to(RUNTIME_OUTPUT_FIXTURE_ROOT)
        destination = destination_root / relative_path
        if destination.exists():
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(fixture_path, destination)
        try:
            copied.append(str(destination.resolve().relative_to(REPO_ROOT)))
        except ValueError:
            copied.append(str(destination.resolve()))
    return copied


def run_compile_checks() -> list[str]:
    failures: list[str] = []
    for directory in COMPILE_DIRS:
        if directory.exists() and not compileall.compile_dir(directory, quiet=1):
            failures.append(str(directory))
    return failures


def resolve_manifests(explicit_manifests: list[str] | None, manifest_glob: str) -> list[Path]:
    if explicit_manifests:
        return [REPO_ROOT / manifest for manifest in explicit_manifests]
    return sorted(REPO_ROOT.glob(manifest_glob))


def build_compact_summary(
    fixture_copies: list[str],
    compile_failures: list[str],
    summaries: list[dict[str, object]],
) -> dict[str, object]:
    manifest_rows = []
    failed_cases = []
    total_cases = 0

    for summary in summaries:
        case_count = int(summary.get("case_count", 0))
        passed = int(summary.get("passed", 0))
        failed = int(summary.get("failed", 0))
        total_cases += case_count
        manifest_rows.append(
            {
                "manifest": str(summary.get("manifest")),
                "case_count": case_count,
                "passed": passed,
                "failed": failed,
            }
        )

        for case in summary.get("cases", []):
            if not case.get("matches_expectation", False):
                failed_cases.append(
                    {
                        "manifest": str(summary.get("manifest")),
                        "id": case.get("id"),
                        "kind": case.get("kind"),
                        "path": case.get("path"),
                        "expect_valid": case.get("expect_valid"),
                        "actual_valid": case.get("actual_valid"),
                        "missing_expected_substrings": case.get("missing_expected_substrings", []),
                        "assertion_errors": case.get("assertion_errors", []),
                    }
                )

    return {
        "fixture_copies": fixture_copies,
        "compile_failures": compile_failures,
        "manifest_count": len(summaries),
        "case_count": total_cases,
        "manifests": manifest_rows,
        "failed_cases": failed_cases,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run local contract checks")
    parser.add_argument("--manifest", action="append", help="Specific eval manifest to run. Can be repeated.")
    parser.add_argument("--manifest-glob", default="evals/cases/*.json")
    parser.add_argument("--verbose", action="store_true", help="Print full per-case eval payloads.")
    args = parser.parse_args()

    fixture_copies = ensure_runtime_output_fixtures()
    compile_failures = run_compile_checks()
    manifests = resolve_manifests(args.manifest, args.manifest_glob)
    summaries = [run_manifest(manifest) for manifest in manifests]
    all_evals_passed = all(summary["all_matched_expectation"] for summary in summaries)

    payload = (
        {
            "fixture_copies": fixture_copies,
            "compile_failures": compile_failures,
            "manifest_count": len(summaries),
            "eval_summaries": summaries,
        }
        if args.verbose
        else build_compact_summary(fixture_copies, compile_failures, summaries)
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    if compile_failures or not all_evals_passed:
        sys.exit(1)


if __name__ == "__main__":
    main()
