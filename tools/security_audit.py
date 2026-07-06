#!/usr/bin/env python3
"""Audit commit/output surfaces for leaked secrets and unsafe delivery artifacts.

This is a lightweight pre-delivery check for the stock analysis pipeline. It is
deliberately local and dependency-free so it can run before commits, before
publishing reports, or inside CI.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.backend_providers import DETERMINISTIC_BACKEND_PROVIDERS, FIXTURE_BACKEND_PROVIDERS  # noqa: E402

SEVERITIES = {"ERROR", "WARN"}
TEXT_SUFFIXES = {
    ".css",
    ".csv",
    ".html",
    ".htm",
    ".json",
    ".jsonl",
    ".md",
    ".py",
    ".sh",
    ".txt",
    ".toml",
    ".ts",
    ".tsx",
    ".yaml",
    ".yml",
}
SKIP_DIRS = {
    ".git",
    ".pytest_cache",
    "__pycache__",
    "node_modules",
}
NEVER_READ_PATTERNS = (
    ".env",
    ".env.*",
)
FORBIDDEN_STAGED_PATTERNS = (
    ".env",
    ".env.*",
    "*/.env",
    "*/.env.*",
    "*.key",
    "*.pem",
    "secrets.json",
    "output/*",
    ".understand-anything/*",
)
ALLOWED_ENV_BASENAMES = {".env.example"}
PLACEHOLDER_VALUES = {
    "",
    "none",
    "null",
    "placeholder",
    "redacted",
    "changeme",
    "your_api_key",
    "your-api-key",
    "example",
    "test",
    "dummy",
}
SECRET_VALUE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("openai_secret_key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b")),
    ("anthropic_secret_key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b")),
    ("aws_access_key_id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{30,}\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b")),
    ("private_key_block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("bearer_token", re.compile(r"\bAuthorization\s*[:=]\s*Bearer\s+[A-Za-z0-9._~+/=-]{20,}", re.I)),
    ("jwt_token", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
)
SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"""(?ix)
    \b(?:[A-Za-z0-9_]+[_-])?(api[_-]?key|secret|token|password|passwd|credential|private[_-]?key)\b
    ["']?\s*[:=]\s*
    ["']?([^"',\s#}]+)
    """
)
NEXT_PUBLIC_SECRET_RE = re.compile(r"\bNEXT_PUBLIC_[A-Z0-9_]*(?:SECRET|TOKEN|PASSWORD|PRIVATE_KEY)[A-Z0-9_]*\b")
SCRIPT_SRC_RE = re.compile(r"<script\b[^>]*\bsrc=[\"']([^\"']+)[\"']", re.I)
FIXTURE_PROVIDER_MARKERS = tuple(
    marker
    for provider in sorted(FIXTURE_BACKEND_PROVIDERS)
    for key in ("provider", "backend_provider")
    for marker in (f'"{key}": "{provider}"', f'"{key}":"{provider}"')
)
FIXTURE_MARKERS = (
    *FIXTURE_PROVIDER_MARKERS,
    '"run_profile": "smoke"',
    '"run_profile":"smoke"',
    '"run_profile": "fixture"',
    '"run_profile":"fixture"',
    "ANALYST_BACKEND=fixture",
    "allow-fixture-delivery",
)


@dataclass(frozen=True)
class Finding:
    severity: str
    rule: str
    path: str
    line: int | None
    detail: str

    def __post_init__(self) -> None:
        if self.severity not in SEVERITIES:
            raise ValueError(f"invalid severity: {self.severity}")


def rel_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def is_never_read_path(path: Path) -> bool:
    name = path.name
    return any(fnmatch.fnmatch(name, pattern) for pattern in NEVER_READ_PATTERNS)


def is_text_candidate(path: Path) -> bool:
    if path.suffix.lower() in TEXT_SUFFIXES:
        return True
    return path.name in {"Dockerfile", "Makefile"}


def should_skip_path(path: Path) -> bool:
    parts = set(path.parts)
    return bool(parts & SKIP_DIRS) or is_never_read_path(path)


def iter_path_inputs(paths: Iterable[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_dir():
            for root, dirnames, filenames in os.walk(path):
                dirnames[:] = sorted(dirname for dirname in dirnames if dirname not in SKIP_DIRS)
                for filename in sorted(filenames):
                    child = Path(root) / filename
                    if is_never_read_path(child):
                        continue
                    if child.is_file():
                        files.append(child)
        elif path.exists():
            files.append(path)
    return files


def git_paths(args: list[str]) -> list[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git command failed")
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def staged_paths() -> list[Path]:
    names = git_paths(["diff", "--cached", "--name-only", "--diff-filter=ACMRT"])
    return [REPO_ROOT / name for name in names]


def tracked_workspace_paths() -> list[Path]:
    names = git_paths(["ls-files"])
    return [REPO_ROOT / name for name in names]


def forbidden_staged_findings(path_names: Iterable[str]) -> list[Finding]:
    findings: list[Finding] = []
    for name in path_names:
        normalized = name.replace("\\", "/")
        if normalized.rsplit("/", 1)[-1] in ALLOWED_ENV_BASENAMES:
            continue
        for pattern in FORBIDDEN_STAGED_PATTERNS:
            if fnmatch.fnmatch(normalized, pattern):
                findings.append(
                    Finding(
                        "ERROR",
                        "forbidden_staged_path",
                        normalized,
                        None,
                        f"Do not commit generated/cache/secret-like path matching {pattern!r}.",
                    )
                )
                break
    return findings


def looks_like_placeholder(value: str) -> bool:
    normalized = value.strip().strip("'\"").lower()
    if normalized in PLACEHOLDER_VALUES:
        return True
    if normalized.startswith("${") or normalized.startswith("$"):
        return True
    if normalized.startswith("<") and normalized.endswith(">"):
        return True
    if re.fullmatch(r"[A-Z0-9_]{8,}", value):
        return True
    return False


def scan_text_for_secrets(path: Path, text: str) -> list[Finding]:
    findings: list[Finding] = []
    lines = text.splitlines()
    for line_no, line in enumerate(lines, start=1):
        if NEXT_PUBLIC_SECRET_RE.search(line) and "NEXT_PUBLIC_SECRET_RE" not in line:
            findings.append(
                Finding(
                    "ERROR",
                    "public_secret_variable",
                    rel_path(path),
                    line_no,
                    "Public env-style variable name contains a secret/token/password marker.",
                )
            )
        for rule, pattern in SECRET_VALUE_PATTERNS:
            if pattern.search(line):
                findings.append(
                    Finding(
                        "ERROR",
                        rule,
                        rel_path(path),
                        line_no,
                        "High-confidence secret/token pattern found.",
                    )
                )
        for match in SENSITIVE_ASSIGNMENT_RE.finditer(line):
            value = match.group(2).strip().strip("'\"")
            if len(value) < 12 or looks_like_placeholder(value):
                continue
            findings.append(
                Finding(
                    "ERROR",
                    "sensitive_assignment",
                    rel_path(path),
                    line_no,
                    "Sensitive-looking assignment has a concrete value.",
                )
            )
    return findings


def is_delivery_report_path(path: Path) -> bool:
    normalized_parts = path.as_posix().split("/")
    for index in range(len(normalized_parts) - 1):
        if normalized_parts[index] == "output" and normalized_parts[index + 1] == "reports":
            return True
    return False


def output_root_for_report(path: Path) -> Path | None:
    resolved = path.resolve()
    for parent in (resolved.parent, *resolved.parents):
        if parent.name == "reports" and parent.parent.name == "output":
            return parent.parent
    return None


def parse_report_identity(path: Path) -> dict[str, Any] | None:
    parts = path.stem.split("_")
    if len(parts) < 4:
        return None
    mode_index: int | None = None
    for index in range(len(parts) - 3, -1, -1):
        if parts[index].upper() in {"A", "B", "C", "D", "E"}:
            mode_index = index
            break
    if mode_index is None or mode_index == 0:
        return None
    tickers = tuple(part.upper() for part in parts[:mode_index] if part)
    if not tickers:
        return None
    return {
        "tickers": tickers,
        "mode": parts[mode_index].upper(),
        "analysis_date": parts[-1],
    }


def iter_report_analysis_paths(path: Path) -> list[Path]:
    output_root = output_root_for_report(path)
    identity = parse_report_identity(path)
    if output_root is None or identity is None:
        return []
    tickers = set(identity["tickers"])
    paths: list[Path] = []
    seen: set[Path] = set()

    runs_root = output_root / "runs"
    if runs_root.exists():
        for candidate in sorted(runs_root.glob("*/*/analysis-result.json")):
            if candidate.parent.name.upper() not in tickers:
                continue
            resolved = candidate.resolve()
            if resolved not in seen:
                paths.append(candidate)
                seen.add(resolved)

    data_root = output_root / "data"
    for ticker in sorted(tickers):
        snapshot_root = data_root / ticker / "snapshots"
        if snapshot_root.exists():
            for candidate in sorted(snapshot_root.glob("*/analysis-result.json"), reverse=True):
                resolved = candidate.resolve()
                if resolved not in seen:
                    paths.append(candidate)
                    seen.add(resolved)
        ticker_root = data_root / ticker
        if ticker_root.exists():
            for candidate in sorted(ticker_root.glob(f"{ticker}_*_snapshot.json"), reverse=True):
                resolved = candidate.resolve()
                if resolved not in seen:
                    paths.append(candidate)
                    seen.add(resolved)
    return paths


def read_json_object(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def matching_report_analysis_documents(path: Path) -> list[tuple[Path, dict[str, Any]]]:
    identity = parse_report_identity(path)
    if identity is None:
        return []
    report_date = str(identity.get("analysis_date") or "")
    documents: list[tuple[Path, dict[str, Any]]] = []
    for candidate in iter_report_analysis_paths(path):
        data = read_json_object(candidate)
        if data is None:
            continue
        candidate_date = str(data.get("analysis_date") or "")
        if report_date and candidate_date and candidate_date != report_date:
            continue
        documents.append((candidate, data))
    return documents


def report_provenance_findings(path: Path) -> list[Finding]:
    if not is_delivery_report_path(path):
        return []
    documents = matching_report_analysis_documents(path)
    if not documents:
        return [
            Finding(
                "WARN",
                "fixture_provenance_unverifiable",
                rel_path(path),
                None,
                "Published report path has no matching analysis-result artifact for fixture/deterministic provenance verification.",
            )
        ]

    findings: list[Finding] = []
    for analysis_path, analysis in documents:
        run_context = analysis.get("run_context") if isinstance(analysis.get("run_context"), dict) else {}
        backend = run_context.get("backend") if isinstance(run_context.get("backend"), dict) else {}
        provider = str(backend.get("provider") or "").strip().lower()
        run_profile = str(run_context.get("run_profile") or "").strip().lower()
        fixture_backend = provider in FIXTURE_BACKEND_PROVIDERS or run_context.get("fixture_backend") is True
        deterministic_backend = (
            provider in DETERMINISTIC_BACKEND_PROVIDERS
            or run_context.get("deterministic_backend") is True
            or run_profile == "deterministic"
        )
        non_production_profile = run_profile in {"smoke", "fixture"}
        allow_deterministic_delivery = run_context.get("allow_deterministic_delivery") is True

        if fixture_backend or non_production_profile:
            reason = "fixture/smoke"
        elif deterministic_backend and not allow_deterministic_delivery:
            reason = "deterministic_without_opt_in"
        else:
            continue

        findings.append(
            Finding(
                "ERROR",
                "fixture_delivery_provenance",
                rel_path(path),
                None,
                (
                    f"Published report maps to {rel_path(analysis_path)} with provider "
                    f"{provider or 'unknown'} and run_profile {run_profile or 'unknown'} ({reason})."
                ),
            )
        )
    return findings


def scan_delivery_markers(path: Path, text: str) -> list[Finding]:
    if not is_delivery_report_path(path):
        return []
    lower = text.lower()
    findings: list[Finding] = []
    if any(marker.lower() in lower for marker in FIXTURE_MARKERS):
        findings.append(
            Finding(
                "ERROR",
                "fixture_delivery_marker",
                rel_path(path),
                None,
                "Published report path contains fixture/smoke delivery marker.",
            )
        )
    findings.extend(report_provenance_findings(path))
    return findings


def scan_html_dependencies(path: Path, text: str) -> list[Finding]:
    if path.suffix.lower() not in {".html", ".htm"}:
        return []
    findings: list[Finding] = []
    for match in SCRIPT_SRC_RE.finditer(text):
        src = match.group(1).strip()
        line_no = text.count("\n", 0, match.start()) + 1
        if src.lower().startswith("http://"):
            findings.append(
                Finding(
                    "ERROR",
                    "insecure_external_script",
                    rel_path(path),
                    line_no,
                    f"Script uses insecure http URL: {src}",
                )
            )
        elif src.lower().startswith("https://"):
            findings.append(
                Finding(
                    "WARN",
                    "external_script_dependency",
                    rel_path(path),
                    line_no,
                    f"External script dependency should be intentional: {src}",
                )
            )
    return findings


def scan_file(path: Path) -> list[Finding]:
    if should_skip_path(path):
        return [
            Finding(
                "WARN",
                "skipped_sensitive_path",
                rel_path(path),
                None,
                "Path was not read by security audit.",
            )
        ]
    if not is_text_candidate(path):
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return [Finding("WARN", "unreadable_file", rel_path(path), None, str(exc))]
    findings: list[Finding] = []
    findings.extend(scan_text_for_secrets(path, text))
    findings.extend(scan_delivery_markers(path, text))
    findings.extend(scan_html_dependencies(path, text))
    return findings


def audit_paths(paths: Iterable[Path]) -> list[Finding]:
    findings: list[Finding] = []
    for path in iter_path_inputs(paths):
        findings.extend(scan_file(path))
    return findings


def render_text(findings: list[Finding]) -> str:
    if not findings:
        return "security audit passed: no findings"
    lines = ["security audit findings:"]
    for finding in sorted(findings, key=lambda item: (item.severity != "ERROR", item.path, item.line or 0, item.rule)):
        location = finding.path
        if finding.line is not None:
            location = f"{location}:{finding.line}"
        lines.append(f"- {finding.severity} {finding.rule} {location} - {finding.detail}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit staged files or selected paths for secret leakage and unsafe report delivery.",
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--staged", action="store_true", help="Audit staged files (default).")
    source.add_argument("--workspace", action="store_true", help="Audit tracked workspace files.")
    source.add_argument("--paths", nargs="+", help="Audit explicit files/directories.")
    parser.add_argument("--format", choices=("text", "json"), default="text", help="Output format.")
    parser.add_argument("--fail-on-warn", action="store_true", help="Return non-zero when warnings are present.")
    args = parser.parse_args(argv)

    try:
        if args.paths:
            paths = [Path(item) for item in args.paths]
            staged_names: list[str] = []
        elif args.workspace:
            paths = tracked_workspace_paths()
            staged_names = []
        else:
            paths = staged_paths()
            staged_names = [rel_path(path) for path in paths]
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    findings = forbidden_staged_findings(staged_names)
    findings.extend(audit_paths(paths))

    if args.format == "json":
        payload = {
            "status": "FAIL" if any(f.severity == "ERROR" for f in findings) else "PASS",
            "errors": sum(1 for finding in findings if finding.severity == "ERROR"),
            "warnings": sum(1 for finding in findings if finding.severity == "WARN"),
            "findings": [asdict(finding) for finding in findings],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_text(findings))

    has_error = any(finding.severity == "ERROR" for finding in findings)
    has_warn = any(finding.severity == "WARN" for finding in findings)
    if has_error or (args.fail_on_warn and has_warn):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
