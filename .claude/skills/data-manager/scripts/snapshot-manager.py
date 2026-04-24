#!/usr/bin/env python3
"""
snapshot-manager.py — Manages versioned analysis snapshots.

Usage:
    python snapshot-manager.py save --ticker AAPL --data-file output/runs/<run_id>/AAPL/analysis-result.json
    python snapshot-manager.py list --ticker AAPL
    python snapshot-manager.py get --ticker AAPL --date latest
    python snapshot-manager.py get --ticker AAPL --date 2026-03-12
    python snapshot-manager.py get --ticker AAPL --date 30d   (30 days ago)

Snapshot storage:
    output/data/{ticker}/snapshots/{snapshot_id}/analysis-result.json — immutable archive
    output/data/{ticker}/latest.json                                  — pointer to most recent
    Custom roots are supported via --data-root for fixture and CI usage.
"""

import sys
import json
import argparse
from datetime import timedelta, date
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

THIS_FILE = Path(__file__).resolve()
BASE_DIR = THIS_FILE.parents[4]
sys.path.insert(0, str(BASE_DIR))

from tools.analysis_contract import find_repo_root  # noqa: E402
from tools.artifact_validation import validate_artifact_file  # noqa: E402
from tools.paths import data_dir, runtime_path  # noqa: E402
from tools.snapshot_store import (  # noqa: E402
    atomic_write_json,
    build_latest_pointer,
    build_snapshot_id,
    display_path,
    ensure_snapshot_metadata,
    iter_snapshot_entries,
    load_snapshot_document,
    promote_snapshot_artifacts,
    read_json,
)

BASE_DIR = find_repo_root(__file__)
DEFAULT_OUTPUT_DIR = data_dir() / "data"


def resolve_data_root(data_root: str | None = None) -> Path:
    if not data_root:
        return DEFAULT_OUTPUT_DIR
    return runtime_path(data_root)


def get_ticker_dir(ticker: str, data_root: str | None = None) -> Path:
    d = resolve_data_root(data_root) / ticker.upper()
    d.mkdir(parents=True, exist_ok=True)
    return d


def cmd_save(ticker: str, data_file: str, skip_validation: bool = False, data_root: str | None = None):
    """Save snapshot from analysis-result.json."""
    data_path = runtime_path(data_file)
    if not data_path.exists():
        print(json.dumps({"status": "error", "message": f"Data file not found: {data_file}"}))
        sys.exit(1)

    validation_result = None
    if not skip_validation:
        validation_result = validate_artifact_file(data_path, "analysis-result", base_dir=BASE_DIR)
        if not validation_result["valid"]:
            print(json.dumps({
                "status": "error",
                "message": "Input analysis-result.json failed schema validation",
                "validation_errors": validation_result["errors"],
            }, ensure_ascii=False, indent=2))
            sys.exit(1)

    data = read_json(data_path)

    # Inject metadata if not already present
    data = ensure_snapshot_metadata(data, ticker)
    if "snapshot_source_artifact" not in data:
        try:
            data["snapshot_source_artifact"] = str(data_path.resolve().relative_to(BASE_DIR))
        except ValueError:
            data["snapshot_source_artifact"] = str(data_path.resolve())

    ticker_upper = ticker.upper()
    ticker_dir = get_ticker_dir(ticker_upper, data_root=data_root)
    snapshot_id = build_snapshot_id(data)
    snapshot_root = ticker_dir / "snapshots" / snapshot_id
    latest_path = ticker_dir / "latest.json"

    refs = promote_snapshot_artifacts(
        source_analysis_path=data_path,
        snapshot_root=snapshot_root,
        snapshot=data,
        base_dir=BASE_DIR,
    )
    latest_pointer = build_latest_pointer(
        ticker=ticker_upper,
        snapshot=data,
        snapshot_id=snapshot_id,
        refs=refs,
    )
    atomic_write_json(latest_path, latest_pointer)

    print(json.dumps({
        "status": "ok",
        "snapshot_id": snapshot_id,
        "snapshot_root": display_path(snapshot_root, BASE_DIR),
        "snapshot_path": refs["analysis_result"],
        "latest_path": display_path(latest_path, BASE_DIR),
        "latest_format": "pointer",
        "promoted_refs": refs,
        "analysis_date": data["analysis_date"],
        "ticker": ticker_upper,
        "validation_performed": not skip_validation,
        "validation_errors": [] if not validation_result else validation_result["errors"],
    }, ensure_ascii=False, indent=2))


def cmd_list(ticker: str, data_root: str | None = None):
    """List all snapshots for a ticker in reverse chronological order."""
    ticker_dir = get_ticker_dir(ticker, data_root=data_root)
    entries = []
    for entry in iter_snapshot_entries(ticker_dir, ticker, BASE_DIR):
        if "error" in entry:
            entries.append({
                "snapshot_id": entry.get("snapshot_id"),
                "path": entry.get("path_display"),
                "storage": entry.get("storage"),
                "error": entry["error"],
            })
            continue

        snap = entry["data"]
        entries.append({
            "snapshot_id": entry.get("snapshot_id"),
            "date": snap.get("analysis_date", "unknown"),
            "rr_score": snap.get("rr_score"),
            "verdict": snap.get("verdict"),
            "data_mode": snap.get("data_mode"),
            "output_mode": snap.get("output_mode"),
            "storage": entry.get("storage"),
            "path": entry.get("path_display"),
        })

    print(json.dumps({"ticker": ticker.upper(), "snapshots": entries}, ensure_ascii=False, indent=2))


def cmd_get(ticker: str, date_arg: str, data_root: str | None = None):
    """Retrieve a snapshot by date specifier."""
    ticker_dir = get_ticker_dir(ticker, data_root=data_root)

    if date_arg == "latest":
        target_path = ticker_dir / "latest.json"
        if not target_path.exists():
            print(json.dumps({"status": "error", "message": f"No latest.json found for {ticker}"}))
            sys.exit(1)
        data = load_snapshot_document(target_path, BASE_DIR)
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return

    # Handle Nd format (e.g., "30d" = 30 days ago)
    if date_arg.endswith("d") and date_arg[:-1].isdigit():
        days_ago = int(date_arg[:-1])
        target_date = (date.today() - timedelta(days=days_ago)).isoformat()
    else:
        target_date = date_arg

    best = None
    entries = iter_snapshot_entries(ticker_dir, ticker, BASE_DIR)
    for entry in entries:
        if "data" not in entry:
            continue
        snap_date = str(entry.get("analysis_date") or "")
        if snap_date <= target_date:
            best = entry
            break

    if best is None:
        print(json.dumps({
            "status": "error",
            "message": f"No snapshot found for {ticker} on or before {target_date}",
            "available": [entry.get("snapshot_id") for entry in entries],
        }))
        sys.exit(1)

    print(json.dumps(best["data"], ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description="Snapshot manager")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # save
    save_p = subparsers.add_parser("save")
    save_p.add_argument("--ticker", required=True)
    save_p.add_argument("--data-file", required=True)
    save_p.add_argument("--skip-validation", action="store_true")
    save_p.add_argument("--data-root", default=None)

    # list
    list_p = subparsers.add_parser("list")
    list_p.add_argument("--ticker", required=True)
    list_p.add_argument("--data-root", default=None)

    # get
    get_p = subparsers.add_parser("get")
    get_p.add_argument("--ticker", required=True)
    get_p.add_argument("--date", required=True, help="latest | YYYY-MM-DD | Nd (e.g. 30d)")
    get_p.add_argument("--data-root", default=None)

    args = parser.parse_args()

    if args.command == "save":
        cmd_save(args.ticker, args.data_file, skip_validation=args.skip_validation, data_root=args.data_root)
    elif args.command == "list":
        cmd_list(args.ticker, data_root=args.data_root)
    elif args.command == "get":
        cmd_get(args.ticker, args.date, data_root=args.data_root)


if __name__ == "__main__":
    main()
