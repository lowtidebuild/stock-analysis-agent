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
    output/data/{ticker}/{ticker}_{YYYY-MM-DD}_snapshot.json   — versioned archive
    output/data/{ticker}/latest.json                           — always points to most recent
    Custom roots are supported via --data-root for fixture and CI usage.
"""

import sys
import os
import json
import argparse
import shutil
from datetime import datetime, timedelta, date, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

THIS_FILE = Path(__file__).resolve()
BASE_DIR = THIS_FILE.parents[4]
sys.path.insert(0, str(BASE_DIR))

from tools.analysis_contract import find_repo_root  # noqa: E402
from tools.artifact_validation import validate_artifact_file  # noqa: E402

BASE_DIR = find_repo_root(__file__)
DEFAULT_OUTPUT_DIR = BASE_DIR / "output" / "data"


def resolve_data_root(data_root: str | None = None) -> Path:
    if not data_root:
        return DEFAULT_OUTPUT_DIR
    root = Path(data_root)
    return root if root.is_absolute() else (BASE_DIR / root)


def get_ticker_dir(ticker: str, data_root: str | None = None) -> Path:
    d = resolve_data_root(data_root) / ticker.upper()
    d.mkdir(parents=True, exist_ok=True)
    return d


def atomic_write(path: Path, data: dict):
    """Write JSON atomically via temp file + replace."""
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def cmd_save(ticker: str, data_file: str, skip_validation: bool = False, data_root: str | None = None):
    """Save snapshot from analysis-result.json."""
    data_path = Path(data_file)
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

    with open(data_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Inject metadata if not already present
    today = date.today().isoformat()
    if "ticker" not in data:
        data["ticker"] = ticker.upper()
    if "analysis_date" not in data:
        data["analysis_date"] = today
    if "snapshot_saved_at" not in data:
        data["snapshot_saved_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    if "snapshot_source_artifact" not in data:
        try:
            data["snapshot_source_artifact"] = str(data_path.resolve().relative_to(BASE_DIR))
        except ValueError:
            data["snapshot_source_artifact"] = str(data_path.resolve())

    ticker_dir = get_ticker_dir(ticker, data_root=data_root)
    snapshot_name = f"{ticker.upper()}_{data['analysis_date']}_snapshot.json"
    snapshot_path = ticker_dir / snapshot_name
    latest_path = ticker_dir / "latest.json"

    atomic_write(snapshot_path, data)
    atomic_write(latest_path, data)

    print(json.dumps({
        "status": "ok",
        "snapshot_path": str(snapshot_path.relative_to(BASE_DIR)),
        "latest_path": str(latest_path.relative_to(BASE_DIR)),
        "analysis_date": data["analysis_date"],
        "ticker": ticker.upper(),
        "validation_performed": not skip_validation,
        "validation_errors": [] if not validation_result else validation_result["errors"],
    }, ensure_ascii=False, indent=2))


def cmd_list(ticker: str, data_root: str | None = None):
    """List all snapshots for a ticker in reverse chronological order."""
    ticker_dir = get_ticker_dir(ticker, data_root=data_root)
    pattern = f"{ticker.upper()}_*_snapshot.json"
    snapshots = sorted(ticker_dir.glob(pattern), reverse=True)

    entries = []
    for p in snapshots:
        try:
            with open(p, "r", encoding="utf-8") as f:
                snap = json.load(f)
            entries.append({
                "date": snap.get("analysis_date", "unknown"),
                "rr_score": snap.get("rr_score"),
                "verdict": snap.get("verdict"),
                "data_mode": snap.get("data_mode"),
                "output_mode": snap.get("output_mode"),
                "path": str(p.relative_to(BASE_DIR)),
            })
        except Exception as e:
            entries.append({"path": str(p), "error": str(e)})

    print(json.dumps({"ticker": ticker.upper(), "snapshots": entries}, ensure_ascii=False, indent=2))


def cmd_get(ticker: str, date_arg: str, data_root: str | None = None):
    """Retrieve a snapshot by date specifier."""
    ticker_dir = get_ticker_dir(ticker, data_root=data_root)

    if date_arg == "latest":
        target_path = ticker_dir / "latest.json"
        if not target_path.exists():
            print(json.dumps({"status": "error", "message": f"No latest.json found for {ticker}"}))
            sys.exit(1)
        with open(target_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return

    # Handle Nd format (e.g., "30d" = 30 days ago)
    if date_arg.endswith("d") and date_arg[:-1].isdigit():
        days_ago = int(date_arg[:-1])
        target_date = (date.today() - timedelta(days=days_ago)).isoformat()
    else:
        target_date = date_arg

    # Find closest snapshot on or before target_date
    pattern = f"{ticker.upper()}_*_snapshot.json"
    snapshots = sorted(ticker_dir.glob(pattern), reverse=True)

    best = None
    for p in snapshots:
        snap_date = p.stem.replace(f"{ticker.upper()}_", "").replace("_snapshot", "")
        if snap_date <= target_date:
            best = p
            break

    if best is None:
        print(json.dumps({
            "status": "error",
            "message": f"No snapshot found for {ticker} on or before {target_date}",
            "available": [p.stem for p in snapshots],
        }))
        sys.exit(1)

    with open(best, "r", encoding="utf-8") as f:
        data = json.load(f)
    print(json.dumps(data, ensure_ascii=False, indent=2))


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
