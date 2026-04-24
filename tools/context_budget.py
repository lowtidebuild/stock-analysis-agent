from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.paths import REPO_ROOT, runtime_path

ANALYST_INCLUDED_FILENAMES = (
    ("validated-data.json", "validated_metrics"),
    ("evidence-pack.json", "compact_evidence"),
    ("research-plan.json", "routing_plan"),
)
RAW_ARTIFACT_FILENAMES = (
    "tier1-raw.json",
    "tier2-raw.json",
    "dart-api-raw.json",
    "yfinance-raw.json",
    "fred-snapshot.json",
)
TOKEN_ESTIMATOR = "chars_div_4_ceil"
STRONG_MODEL_SOFT_LIMIT_TOKENS = 50_000


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def estimate_tokens(text: str) -> int:
    return int(math.ceil(len(text) / 4))


def read_json(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return data


def measure_file(path: Path, role: str) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    return {
        "path": str(path),
        "role": role,
        "bytes": path.stat().st_size,
        "chars": len(text),
        "estimated_tokens": estimate_tokens(text),
    }


def _display_path(path: Path, repo_root: Path = REPO_ROOT) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path.resolve())


def _resolve_ticker_dir(run_dir: str | Path, ticker: str | None = None) -> Path:
    path = runtime_path(run_dir)
    if (path / "validated-data.json").exists():
        return path

    if ticker:
        ticker_dir = path / ticker.upper()
        if ticker_dir.exists():
            return ticker_dir
        ticker_dir = path / ticker
        if ticker_dir.exists():
            return ticker_dir
        raise FileNotFoundError(f"Ticker directory not found under {path}: {ticker}")

    ticker_dirs = [child for child in path.iterdir() if child.is_dir()]
    if len(ticker_dirs) != 1:
        raise ValueError(f"Expected exactly one ticker directory under {path}, found {len(ticker_dirs)}")
    return ticker_dirs[0]


def _resolve_framework_path(research_plan: dict[str, Any], ticker_dir: Path) -> Path | None:
    framework = research_plan.get("analysis_framework_path") or research_plan.get("framework_path")
    if not framework:
        return None

    candidate = Path(str(framework)).expanduser()
    if candidate.is_absolute():
        return candidate if candidate.exists() else None

    for base in (REPO_ROOT, ticker_dir):
        resolved = (base / candidate).resolve()
        if resolved.exists():
            return resolved
    return None


def _run_context_from_payloads(ticker_dir: Path, payloads: list[dict[str, Any]]) -> dict[str, Any]:
    for payload in payloads:
        run_context = payload.get("run_context")
        if isinstance(run_context, dict):
            return run_context
    return {
        "run_id": ticker_dir.parent.name,
        "artifact_root": _display_path(ticker_dir),
        "ticker": ticker_dir.name,
    }


def build_context_budget(run_dir: str | Path, ticker: str | None = None) -> dict[str, Any]:
    ticker_dir = _resolve_ticker_dir(run_dir, ticker=ticker)

    included_files: list[dict[str, Any]] = []
    loaded_payloads: list[dict[str, Any]] = []
    research_plan: dict[str, Any] = {}
    for filename, role in ANALYST_INCLUDED_FILENAMES:
        path = ticker_dir / filename
        if not path.exists():
            continue
        included_files.append(measure_file(path, role))
        if filename.endswith(".json"):
            payload = read_json(path)
            loaded_payloads.append(payload)
            if filename == "research-plan.json":
                research_plan = payload

    framework_path = _resolve_framework_path(research_plan, ticker_dir) if research_plan else None
    if framework_path is not None:
        included_files.append(measure_file(framework_path, "analysis_framework"))

    excluded_raw_artifacts = []
    for filename in RAW_ARTIFACT_FILENAMES:
        path = ticker_dir / filename
        if path.exists():
            excluded_raw_artifacts.append(measure_file(path, "raw_artifact_excluded_by_default"))

    included_tokens = sum(item["estimated_tokens"] for item in included_files)
    excluded_tokens = sum(item["estimated_tokens"] for item in excluded_raw_artifacts)
    return {
        "schema_version": "1.0",
        "artifact_type": "context-budget",
        "target_agent": "analyst",
        "measurement_timestamp": utc_now_iso(),
        "token_estimator": TOKEN_ESTIMATOR,
        "run_context": _run_context_from_payloads(ticker_dir, loaded_payloads),
        "included_files": [
            {**item, "path": _display_path(Path(item["path"]))}
            for item in included_files
        ],
        "excluded_raw_artifacts": [
            {**item, "path": _display_path(Path(item["path"]))}
            for item in excluded_raw_artifacts
        ],
        "totals": {
            "included_estimated_tokens": included_tokens,
            "excluded_raw_estimated_tokens": excluded_tokens,
            "estimated_tokens_avoided_by_default_raw_exclusion": excluded_tokens,
            "strong_model_soft_limit_tokens": STRONG_MODEL_SOFT_LIMIT_TOKENS,
            "within_soft_limit": included_tokens <= STRONG_MODEL_SOFT_LIMIT_TOKENS,
        },
        "routing_policy": {
            "strong_model": [
                "final_investment_reasoning",
                "variant_view",
                "risk_mechanism_critique",
                "what_would_make_me_wrong",
            ],
            "cheap_model_or_deterministic_preprocess": [
                "analyst_coverage_summary",
                "news_catalyst_grouping",
                "first_pass_narrative_comments",
            ],
            "no_llm": [
                "schema_validation",
                "source_tag_count",
                "scenario_probability_sum",
                "word_count",
                "html_required_section_check",
                "docx_heading_table_check",
                "ratio_recomputation",
                "path_contract_validation",
                "renderer_execution",
                "context_budget_measurement",
            ],
        },
    }


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    resolved = runtime_path(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    tmp = resolved.with_suffix(f"{resolved.suffix}.tmp")
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    tmp.replace(resolved)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Measure Analyst handoff context size for a run")
    parser.add_argument("--run-dir", required=True, help="Path to output/runs/<run_id> or a ticker artifact directory")
    parser.add_argument("--ticker", default=None, help="Ticker directory to measure when run-dir contains multiple tickers")
    parser.add_argument("--output", default=None, help="Path to write context-budget.json")
    args = parser.parse_args(argv)

    budget = build_context_budget(args.run_dir, ticker=args.ticker)
    output = args.output
    if output is None:
        ticker_dir = _resolve_ticker_dir(args.run_dir, ticker=args.ticker)
        output = ticker_dir / "context-budget.json"
    write_json(output, budget)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
