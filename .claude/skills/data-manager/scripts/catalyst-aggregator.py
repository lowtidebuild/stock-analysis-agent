#!/usr/bin/env python3
"""
catalyst-aggregator.py — Aggregates upcoming catalysts from all watchlist snapshots.

Usage:
    python catalyst-aggregator.py build
    python catalyst-aggregator.py show --days 30
    python catalyst-aggregator.py show --days 90 --ticker AAPL

Output:
    build: updates output/catalyst-calendar.json
    show:  prints a text table of upcoming events
"""

import sys
import json
import argparse
from datetime import datetime, date, timedelta
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

THIS_FILE = Path(__file__).resolve()
BASE_DIR = THIS_FILE.parents[4]
sys.path.insert(0, str(BASE_DIR))

from tools.analysis_contract import find_repo_root  # noqa: E402
from tools.paths import data_path, runtime_path  # noqa: E402
from tools.snapshot_store import display_path, load_snapshot_document  # noqa: E402

BASE_DIR = find_repo_root(__file__)
WATCHLIST_PATH = data_path("watchlist.json")
CALENDAR_PATH = data_path("catalyst-calendar.json")


def atomic_write(path: Path, data: dict):
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def load_json(path: Path) -> dict:
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def cmd_build():
    """Read all watchlist snapshots and aggregate upcoming_catalysts."""
    wl = load_json(WATCHLIST_PATH)
    tickers = wl.get("tickers", [])

    events = []
    skipped = []
    today = date.today().isoformat()

    for entry in tickers:
        ticker = entry.get("ticker")
        market = entry.get("market", "US")
        snap_path_str = entry.get("last_snapshot_path")

        if not snap_path_str:
            skipped.append({"ticker": ticker, "reason": "no snapshot path"})
            continue

        snap_path = runtime_path(snap_path_str)
        if not snap_path.exists():
            skipped.append({"ticker": ticker, "reason": f"snapshot file not found: {snap_path_str}"})
            continue

        try:
            snap = load_snapshot_document(snap_path, BASE_DIR)
        except Exception as e:
            skipped.append({"ticker": ticker, "reason": f"JSON parse error: {e}"})
            continue

        catalysts = snap.get("upcoming_catalysts", [])
        if not isinstance(catalysts, list):
            skipped.append({"ticker": ticker, "reason": "upcoming_catalysts not a list"})
            continue

        for cat in catalysts:
            if not isinstance(cat, dict):
                continue
            event_date = cat.get("date", "")
            # Only include future events (date >= today)
            if event_date and event_date >= today:
                events.append({
                    "date": event_date,
                    "ticker": ticker,
                    "market": market,
                    "event_type": cat.get("event_type", cat.get("event", "unknown")),
                    "description": cat.get("description", cat.get("event", "")),
                    "significance": cat.get("significance", "medium"),
                    "source_snapshot": snap_path_str,
                })

    # Sort by date
    events.sort(key=lambda x: x["date"])

    calendar = {
        "version": "1.0",
        "last_updated": datetime.utcnow().isoformat() + "Z",
        "build_date": today,
        "events": events,
        "skipped_tickers": skipped,
        "total_events": len(events),
        "tickers_processed": len(tickers) - len(skipped),
    }

    atomic_write(CALENDAR_PATH, calendar)

    print(json.dumps({
        "status": "ok",
        "total_events": len(events),
        "tickers_processed": len(tickers) - len(skipped),
        "tickers_skipped": len(skipped),
        "calendar_path": display_path(CALENDAR_PATH, BASE_DIR),
        "skipped_details": skipped if skipped else [],
    }, ensure_ascii=False, indent=2))


def cmd_show(days: int, ticker_filter: str = None):
    """Print upcoming events as a formatted text table."""
    calendar = load_json(CALENDAR_PATH)
    events = calendar.get("events", [])

    today = date.today()
    cutoff = (today + timedelta(days=days)).isoformat()
    today_str = today.isoformat()

    filtered = [
        e for e in events
        if e["date"] >= today_str and e["date"] <= cutoff
    ]

    if ticker_filter:
        filtered = [e for e in filtered if e["ticker"].upper() == ticker_filter.upper()]

    if not filtered:
        print(f"No upcoming catalysts in the next {days} days"
              + (f" for {ticker_filter.upper()}" if ticker_filter else "") + ".")
        return

    # Sort by date
    filtered.sort(key=lambda x: x["date"])

    # Header
    sep = "-" * 80
    print(sep)
    print(f"{'Upcoming Catalysts':^80}")
    print(f"{'Next ' + str(days) + ' days — as of ' + today_str:^80}")
    print(sep)
    print(f"{'Date':<12} {'Ticker':<10} {'Market':<7} {'Significance':<13} {'Event'}")
    print(sep)

    for e in filtered:
        sig = e.get("significance", "medium").upper()
        sig_marker = "!!!" if sig == "HIGH" else ("!!" if sig == "MEDIUM" else "!")
        desc = e.get("description") or e.get("event_type", "")
        if len(desc) > 45:
            desc = desc[:42] + "..."
        print(f"{e['date']:<12} {e['ticker']:<10} {e['market']:<7} {sig_marker + ' ' + sig:<13} {desc}")

    print(sep)
    print(f"Total: {len(filtered)} events | Calendar built: {calendar.get('build_date', 'unknown')}")


def main():
    parser = argparse.ArgumentParser(description="Catalyst aggregator")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("build")

    show_p = subparsers.add_parser("show")
    show_p.add_argument("--days", type=int, default=30)
    show_p.add_argument("--ticker", default=None)

    args = parser.parse_args()

    if args.command == "build":
        cmd_build()
    elif args.command == "show":
        cmd_show(args.days, args.ticker)


if __name__ == "__main__":
    main()
