#!/usr/bin/env python3
"""
artifact-manager.py — Initializes and inspects run-local artifact layouts.

Usage:
    python artifact-manager.py init --tickers AAPL
    python artifact-manager.py init --tickers AAPL MSFT --run-id 20260328T010203Z_AAPL_MSFT
    python artifact-manager.py show --run-id 20260328T010203Z_AAPL
"""

import argparse
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

THIS_FILE = Path(__file__).resolve()
REPO_ROOT = THIS_FILE.parents[4]
sys.path.insert(0, str(REPO_ROOT))

from tools.analysis_contract import (  # noqa: E402
    build_run_id,
    build_run_paths,
    relativize_paths,
    utc_now_iso,
)
from tools.paths import data_dir  # noqa: E402


def ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def atomic_write(path: Path, data: dict) -> None:
    ensure_directory(path.parent)
    temp_path = path.with_suffix(".tmp")
    with open(temp_path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
    temp_path.replace(path)


def init_run(tickers: list[str], run_id: str | None = None) -> dict:
    normalized_tickers = [ticker.upper() for ticker in tickers]
    resolved_run_id = run_id or build_run_id(normalized_tickers)

    artifacts: dict[str, dict] = {}
    manifest_path = None

    for ticker in normalized_tickers:
        paths = build_run_paths(REPO_ROOT, resolved_run_id, ticker)
        ensure_directory(paths["ticker_root"])
        ensure_directory(paths["reports_dir"])
        manifest_path = paths["run_manifest"]
        relpaths = relativize_paths(REPO_ROOT, paths)
        relpaths.pop("ticker_root", None)
        artifacts[ticker] = relpaths

    manifest = {
        "run_id": resolved_run_id,
        "created_at": utc_now_iso(),
        "tickers": normalized_tickers,
        "artifact_layout": "output/runs/{run_id}/{ticker}/",
        "artifacts": artifacts,
    }

    if manifest_path is None:
        raise RuntimeError("No manifest path resolved for run initialization")

    atomic_write(manifest_path, manifest)
    return manifest


def show_run(run_id: str) -> dict:
    manifest_path = data_dir() / "runs" / run_id / "run-manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Run manifest not found: {manifest_path}")
    with open(manifest_path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run-local artifact layout manager")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init")
    init_parser.add_argument("--tickers", nargs="+", required=True)
    init_parser.add_argument("--run-id", default=None)

    show_parser = subparsers.add_parser("show")
    show_parser.add_argument("--run-id", required=True)

    args = parser.parse_args()

    if args.command == "init":
        print(json.dumps(init_run(args.tickers, run_id=args.run_id), ensure_ascii=False, indent=2))
    elif args.command == "show":
        print(json.dumps(show_run(args.run_id), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
