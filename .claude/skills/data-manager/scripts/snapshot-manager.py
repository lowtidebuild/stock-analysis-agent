#!/usr/bin/env python3
"""
snapshot-manager.py — Manages versioned analysis snapshots.

Usage:
    python snapshot-manager.py save --ticker AAPL --data-file output/analysis-result.json
    python snapshot-manager.py list --ticker AAPL
    python snapshot-manager.py get --ticker AAPL --date latest
    python snapshot-manager.py get --ticker AAPL --date 2026-03-12
    python snapshot-manager.py get --ticker AAPL --date 30d   (30 days ago)

Snapshot storage:
    output/data/{ticker}/{ticker}_{YYYY-MM-DD}_snapshot.json   — versioned archive
    output/data/{ticker}/latest.json                           — always points to most recent
"""

import sys
import os
import json
import argparse
import shutil
from datetime import datetime, timedelta, date
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = Path(__file__).resolve().parents[5]  # project root
OUTPUT_DIR = BASE_DIR / "output" / "data"


def get_ticker_dir(ticker: str) -> Path:
    d = OUTPUT_DIR / ticker.upper()
    d.mkdir(parents=True, exist_ok=True)
    return d


def atomic_write(path: Path, data: dict):
    """Write JSON atomically via temp file + replace."""
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def cmd_save(ticker: str, data_file: str):
    """Save snapshot from analysis-result.json."""
    data_path = Path(data_file)
    if not data_path.exists():
        print(json.dumps({"status": "error", "message": f"Data file not found: {data_file}"}))
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
        data["snapshot_saved_at"] = datetime.utcnow().isoformat() + "Z"

    ticker_dir = get_ticker_dir(ticker)
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
    }, ensure_ascii=False, indent=2))


def cmd_list(ticker: str):
    """List all snapshots for a ticker in reverse chronological order."""
    ticker_dir = get_ticker_dir(ticker)
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


def cmd_get(ticker: str, date_arg: str):
    """Retrieve a snapshot by date specifier."""
    ticker_dir = get_ticker_dir(ticker)

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

    # list
    list_p = subparsers.add_parser("list")
    list_p.add_argument("--ticker", required=True)

    # get
    get_p = subparsers.add_parser("get")
    get_p.add_argument("--ticker", required=True)
    get_p.add_argument("--date", required=True, help="latest | YYYY-MM-DD | Nd (e.g. 30d)")

    args = parser.parse_args()

    if args.command == "save":
        cmd_save(args.ticker, args.data_file)
    elif args.command == "list":
        cmd_list(args.ticker)
    elif args.command == "get":
        cmd_get(args.ticker, args.date)


if __name__ == "__main__":
    main()
