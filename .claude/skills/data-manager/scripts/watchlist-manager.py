#!/usr/bin/env python3
"""
watchlist-manager.py — Manages output/watchlist.json.

Usage:
    python watchlist-manager.py add --ticker AAPL --market US
    python watchlist-manager.py add --ticker 005930 --market KR
    python watchlist-manager.py remove --ticker AAPL
    python watchlist-manager.py list
    python watchlist-manager.py update-snapshot --ticker AAPL --snapshot-path output/data/AAPL/snapshots/2026-03-12_run_20260312T000000Z_AAPL/analysis-result.json
    python watchlist-manager.py update-fields --ticker AAPL --rr-score 7.8 --verdict Overweight --price 175.50
"""

import sys
import json
import argparse
from datetime import datetime, date
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

THIS_FILE = Path(__file__).resolve()
BASE_DIR = THIS_FILE.parents[4]
sys.path.insert(0, str(BASE_DIR))

from tools.analysis_contract import find_repo_root  # noqa: E402
from tools.paths import data_path, runtime_path  # noqa: E402
from tools.snapshot_store import (  # noqa: E402
    display_path,
    is_latest_pointer,
    load_snapshot_document,
    read_json,
    resolve_pointer_snapshot_path,
)

BASE_DIR = find_repo_root(__file__)
WATCHLIST_PATH = data_path("watchlist.json")


def atomic_write(path: Path, data: dict):
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def load_watchlist() -> dict:
    if WATCHLIST_PATH.exists():
        with open(WATCHLIST_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"version": "1.0", "last_updated": None, "tickers": []}


def save_watchlist(wl: dict):
    wl["last_updated"] = datetime.utcnow().isoformat() + "Z"
    atomic_write(WATCHLIST_PATH, wl)


def normalize_ticker(ticker: str, market: str) -> str:
    if market == "KR":
        return ticker.zfill(6)
    return ticker.upper()


def find_ticker(tickers: list, ticker: str) -> int:
    """Return index of ticker in tickers list, or -1 if not found."""
    t_upper = ticker.upper()
    for i, entry in enumerate(tickers):
        if entry["ticker"].upper() == t_upper:
            return i
    return -1


def cmd_add(ticker: str, market: str):
    market = market.upper()
    if market not in ("US", "KR"):
        print(json.dumps({"status": "error", "message": f"Invalid market: {market}. Must be US or KR."}))
        sys.exit(1)

    wl = load_watchlist()
    norm_ticker = normalize_ticker(ticker, market)

    idx = find_ticker(wl["tickers"], norm_ticker)
    if idx >= 0:
        print(json.dumps({
            "status": "already_exists",
            "message": f"{norm_ticker} is already in the watchlist.",
            "entry": wl["tickers"][idx],
        }, ensure_ascii=False))
        return

    new_entry = {
        "ticker": norm_ticker,
        "market": market,
        "added_date": date.today().isoformat(),
        "last_snapshot_path": None,
        "last_analysis_date": None,
        "last_rr_score": None,
        "last_price": None,
        "last_verdict": None,
        "alert_flags": [],
    }
    wl["tickers"].append(new_entry)
    save_watchlist(wl)

    print(json.dumps({
        "status": "ok",
        "message": f"Added {norm_ticker} ({market}) to watchlist.",
        "entry": new_entry,
        "total_tickers": len(wl["tickers"]),
    }, ensure_ascii=False, indent=2))

    if len(wl["tickers"]) > 30:
        print(json.dumps({
            "warning": f"Watchlist has {len(wl['tickers'])} tickers. Scan performance degrades above 30 tickers."
        }, ensure_ascii=False))


def cmd_remove(ticker: str):
    wl = load_watchlist()
    idx = find_ticker(wl["tickers"], ticker)

    if idx < 0:
        print(json.dumps({"status": "not_found", "message": f"{ticker.upper()} not found in watchlist."}))
        sys.exit(1)

    removed = wl["tickers"].pop(idx)
    save_watchlist(wl)

    print(json.dumps({
        "status": "ok",
        "message": f"Removed {removed['ticker']} from watchlist.",
        "removed_entry": removed,
        "total_tickers": len(wl["tickers"]),
    }, ensure_ascii=False, indent=2))


def cmd_list():
    wl = load_watchlist()
    tickers = wl.get("tickers", [])

    output = {
        "total": len(tickers),
        "last_updated": wl.get("last_updated"),
        "tickers": tickers,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


def cmd_update_snapshot(ticker: str, snapshot_path: str):
    """Update the last_snapshot_path and related fields from the snapshot file."""
    wl = load_watchlist()
    idx = find_ticker(wl["tickers"], ticker)

    if idx < 0:
        print(json.dumps({"status": "not_found", "message": f"{ticker.upper()} not found in watchlist. Add it first."}))
        sys.exit(1)

    snap_file = runtime_path(snapshot_path)
    if not snap_file.exists():
        print(json.dumps({"status": "error", "message": f"Snapshot file not found: {snapshot_path}"}))
        sys.exit(1)

    try:
        raw_snapshot_ref = read_json(snap_file)
        snap = load_snapshot_document(snap_file, BASE_DIR)
    except Exception as e:
        print(json.dumps({"status": "error", "message": f"Snapshot file could not be read: {e}"}))
        sys.exit(1)

    stored_snapshot_path = display_path(snap_file, BASE_DIR)
    if is_latest_pointer(raw_snapshot_ref):
        resolved_snapshot = resolve_pointer_snapshot_path(raw_snapshot_ref, snap_file, BASE_DIR)
        stored_snapshot_path = display_path(resolved_snapshot, BASE_DIR)

    entry = wl["tickers"][idx]
    entry["last_snapshot_path"] = stored_snapshot_path
    entry["last_analysis_date"] = snap.get("analysis_date")
    entry["last_rr_score"] = snap.get("rr_score")
    entry["last_price"] = snap.get("price_at_analysis")
    entry["last_verdict"] = snap.get("verdict")
    # Clear stale flags
    entry["alert_flags"] = [f for f in entry.get("alert_flags", []) if not f.startswith("STALE_")]

    save_watchlist(wl)

    print(json.dumps({
        "status": "ok",
        "message": f"Updated snapshot reference for {entry['ticker']}.",
        "entry": entry,
    }, ensure_ascii=False, indent=2))


def cmd_update_fields(ticker: str, rr_score=None, verdict=None, price=None, alert_flags=None):
    """Update individual fields without a snapshot file."""
    wl = load_watchlist()
    idx = find_ticker(wl["tickers"], ticker)

    if idx < 0:
        print(json.dumps({"status": "not_found", "message": f"{ticker.upper()} not found in watchlist."}))
        sys.exit(1)

    entry = wl["tickers"][idx]
    if rr_score is not None:
        entry["last_rr_score"] = float(rr_score)
    if verdict is not None:
        entry["last_verdict"] = verdict
    if price is not None:
        entry["last_price"] = float(price)
    if alert_flags is not None:
        entry["alert_flags"] = alert_flags

    save_watchlist(wl)

    print(json.dumps({
        "status": "ok",
        "message": f"Updated fields for {entry['ticker']}.",
        "entry": entry,
    }, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description="Watchlist manager")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # add
    add_p = subparsers.add_parser("add")
    add_p.add_argument("--ticker", required=True)
    add_p.add_argument("--market", required=True, choices=["US", "KR", "us", "kr"])

    # remove
    rm_p = subparsers.add_parser("remove")
    rm_p.add_argument("--ticker", required=True)

    # list
    subparsers.add_parser("list")

    # update-snapshot
    us_p = subparsers.add_parser("update-snapshot")
    us_p.add_argument("--ticker", required=True)
    us_p.add_argument("--snapshot-path", required=True)

    # update-fields
    uf_p = subparsers.add_parser("update-fields")
    uf_p.add_argument("--ticker", required=True)
    uf_p.add_argument("--rr-score", type=float)
    uf_p.add_argument("--verdict")
    uf_p.add_argument("--price", type=float)
    uf_p.add_argument("--add-flag", dest="add_flag")

    args = parser.parse_args()

    if args.command == "add":
        cmd_add(args.ticker, args.market)
    elif args.command == "remove":
        cmd_remove(args.ticker)
    elif args.command == "list":
        cmd_list()
    elif args.command == "update-snapshot":
        cmd_update_snapshot(args.ticker, args.snapshot_path)
    elif args.command == "update-fields":
        flags = None
        if hasattr(args, "add_flag") and args.add_flag:
            wl = load_watchlist()
            idx = find_ticker(wl["tickers"], args.ticker)
            if idx >= 0:
                flags = wl["tickers"][idx].get("alert_flags", [])
                if args.add_flag not in flags:
                    flags = flags + [args.add_flag]
        cmd_update_fields(
            args.ticker,
            rr_score=args.rr_score,
            verdict=args.verdict,
            price=args.price,
            alert_flags=flags,
        )


if __name__ == "__main__":
    main()
