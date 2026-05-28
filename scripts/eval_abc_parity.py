#!/usr/bin/env python3
"""Summarize A/B/C parity run quality into output/evals."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.parity.data_sources import load_json, write_json  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    run_roots = resolve_run_roots(args)
    samples: list[dict[str, Any]] = []
    for run_root in run_roots:
        samples.extend(summarize_run(run_root))

    blocked = [sample for sample in samples if not sample["delivery_ready"]]
    summary = {
        "schema_version": "abc-parity-eval-summary-v1",
        "golden_set": args.golden_set,
        "run_roots": [display_path(path) for path in run_roots],
        "sample_count": len(samples),
        "pass_count": len(samples) - len(blocked),
        "blocked_count": len(blocked),
        "overall_status": "PASS" if samples and not blocked else "FAIL",
        "samples": samples,
        "created_at": utc_now(),
    }
    output_dir = Path(args.output_dir) if args.output_dir else REPO_ROOT / "output" / "evals" / utc_slug()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "abc-parity-summary.json"
    write_json(output_path, summary)
    print(json.dumps({"summary_path": display_path(output_path), **summary}, ensure_ascii=False))
    return 0 if summary["overall_status"] == "PASS" else 2


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate existing A/B/C parity run artifacts")
    parser.add_argument("--run-id", action="append", default=[])
    parser.add_argument("--run-root", action="append", default=[])
    parser.add_argument("--golden-set", default=None)
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args(argv)
    if not args.run_id and not args.run_root:
        parser.error("Provide at least one --run-id or --run-root")
    return args


def resolve_run_roots(args: argparse.Namespace) -> list[Path]:
    roots: list[Path] = []
    for run_id in args.run_id:
        roots.append(REPO_ROOT / "output" / "runs" / run_id)
    for raw in args.run_root:
        path = Path(raw)
        roots.append(path if path.is_absolute() else REPO_ROOT / path)
    missing = [str(path) for path in roots if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing run roots: " + ", ".join(missing))
    return roots


def summarize_run(run_root: Path) -> list[dict[str, Any]]:
    samples = []
    for ticker_dir in sorted(child for child in run_root.iterdir() if child.is_dir() and child.name != "macro"):
        if ticker_dir.name == "comparison":
            continue
        quality = load_json(ticker_dir / "quality-report.json")
        loop = load_json(ticker_dir / "critic-loop-result.json") if (ticker_dir / "critic-loop-result.json").exists() else {}
        mode = str(quality.get("output_mode") or loop.get("mode") or "")
        render = load_json(render_report_path(ticker_dir, mode)) if render_report_path(ticker_dir, mode).exists() else {}
        delivery_gate = quality.get("delivery_gate") if isinstance(quality.get("delivery_gate"), dict) else {}
        samples.append(
            {
                "run_id": run_root.name,
                "ticker": ticker_dir.name,
                "mode": mode,
                "quality_result": quality.get("overall_result"),
                "critic_overall": (quality.get("critic_review") or {}).get("overall") if isinstance(quality.get("critic_review"), dict) else None,
                "delivery_ready": delivery_gate.get("ready_for_delivery") is True,
                "blocking_items": delivery_gate.get("blocking_items", []),
                "patch_status": loop.get("patch_status"),
                "render_status": render.get("status"),
                "render_metrics": (render.get("validation") or {}).get("metrics") if isinstance(render.get("validation"), dict) else None,
                "quality_report_path": display_path(ticker_dir / "quality-report.json"),
                "critic_loop_path": display_path(ticker_dir / "critic-loop-result.json") if (ticker_dir / "critic-loop-result.json").exists() else None,
            }
        )
    comparison = summarize_comparison(run_root)
    if comparison:
        samples.append(comparison)
    return samples


def summarize_comparison(run_root: Path) -> dict[str, Any] | None:
    comparison_dir = run_root / "comparison"
    quality_path = comparison_dir / "comparison-quality-report.json"
    render_path = comparison_dir / "mode-b-render-report.json"
    analysis_path = comparison_dir / "comparison-analysis-result.json"
    if not quality_path.exists():
        return None
    quality = load_json(quality_path)
    render = load_json(render_path) if render_path.exists() else {}
    analysis = load_json(analysis_path) if analysis_path.exists() else {}
    delivery_gate = quality.get("delivery_gate") if isinstance(quality.get("delivery_gate"), dict) else {}
    return {
        "run_id": run_root.name,
        "ticker": "comparison",
        "mode": "B",
        "tickers": analysis.get("compared_tickers") or quality.get("compared_tickers"),
        "quality_result": quality.get("overall_result"),
        "critic_overall": None,
        "delivery_ready": delivery_gate.get("ready_for_delivery") is True,
        "blocking_items": delivery_gate.get("blocking_items", []),
        "patch_status": None,
        "render_status": render.get("status"),
        "render_metrics": (render.get("validation") or {}).get("metrics") if isinstance(render.get("validation"), dict) else None,
        "quality_report_path": display_path(quality_path),
        "critic_loop_path": None,
        "best_pick": (analysis.get("best_pick") or {}).get("ticker") if isinstance(analysis.get("best_pick"), dict) else None,
    }


def render_report_path(ticker_dir: Path, mode: str) -> Path:
    if mode == "A":
        return ticker_dir / "mode-a-render-report.json"
    return ticker_dir / "mode-c-render-report.json"


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_slug() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return str(path.resolve())


if __name__ == "__main__":
    raise SystemExit(main())
