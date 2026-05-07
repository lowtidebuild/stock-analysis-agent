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
import re
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Iterable, Mapping, Optional

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

CATEGORY_KEYWORDS = {
    "Earnings": ["earnings", "quarterly", "annual", "10-q", "10-k", "실적", "분기", "결산"],
    "Corporate": [
        "product launch", "fda", "approval", "lockup", "m&a", "acquisition",
        "merger", "spin-off", "buyback", "dividend", "guidance",
        "신제품", "승인", "인수", "합병", "배당", "자사주", "가이던스",
    ],
    "Industry": ["conference", "trade show", "expo", "industry data", "컨퍼런스", "전시회", "산업 통계"],
    "Macro": ["fomc", "fed", "cpi", "gdp", "jobs", "ecb", "boj", "bok", "금통위", "한은", "물가지수", "고용지표"],
}
IMPACT_KEYWORDS = {
    "H": ["earnings", "fda", "guidance", "m&a", "fomc", "실적", "승인", "가이던스"],
    "M": ["product launch", "conference", "신제품", "컨퍼런스"],
    "L": ["industry data", "expo", "산업 통계", "전시회"],
}

# Phase E — Mode C Catalyst Timeline.
#
# The Mode C dashboard renders upcoming_catalysts as a Gantt-style timeline
# grouped by category. The category vocabulary is intentionally smaller than
# the watchlist-style CATEGORY_KEYWORDS above (which has Earnings/Corporate/
# Industry/Macro labels). The timeline groups are: earnings, regulatory,
# product, macro, other — matching the visual buckets in
# `references/analysis-framework-dashboard.md` (Phase E spec).

TIMELINE_CATEGORIES = ("earnings", "regulatory", "product", "macro", "other")

TIMELINE_CATEGORY_KEYWORDS = {
    "earnings": ["earnings", "quarterly", "annual", "10-q", "10-k", "실적", "분기", "결산", "results"],
    "regulatory": [
        "regulatory", "antitrust", "doj", "ftc", "fda", "approval", "ruling",
        "court", "appeal", "lawsuit", "settlement", "sec ", "subpoena",
        "규제", "공정위", "독점", "소송", "판결", "항소", "승인",
    ],
    "product": [
        "product launch", "launch", "release", "rollout", "ga release",
        "general availability", "신제품", "출시", "런칭", "공개",
    ],
    "macro": [
        "fomc", "fed", "cpi", "gdp", "jobs", "ecb", "boj", "bok",
        "금통위", "한은", "물가지수", "고용지표", "rate decision",
    ],
}

# event_type → timeline category. Used when no keyword in the description
# matches but the analyst tagged the catalyst with an event_type.
EVENT_TYPE_TO_CATEGORY = {
    "earnings": "earnings",
    "regulatory": "regulatory",
    "antitrust": "regulatory",
    "court": "regulatory",
    "product": "product",
    "launch": "product",
    "release": "product",
    "macro": "macro",
    "fomc": "macro",
    "rate": "macro",
}

ISO_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")


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


def classify_category(event_text: str) -> str:
    lowered = (event_text or "").lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword.lower() in lowered for keyword in keywords):
            return category
    return "Corporate"


def classify_impact(event_text: str) -> str:
    lowered = (event_text or "").lower()
    for impact, keywords in IMPACT_KEYWORDS.items():
        if any(keyword.lower() in lowered for keyword in keywords):
            return impact
    return "M"


def build_catalyst_record(raw: dict) -> dict:
    event_text = str(raw.get("event") or raw.get("description") or raw.get("event_type") or "")
    return {
        **raw,
        "category": raw.get("category") or classify_category(event_text),
        "impact": raw.get("impact") or classify_impact(event_text),
        "pre_announce_risk": bool(raw.get("pre_announce_risk", False)),
    }


# ---------------------------------------------------------------------------
# Phase E — Mode C catalyst timeline helpers
# ---------------------------------------------------------------------------


def _classify_timeline_category(event_text: str, event_type: Optional[str]) -> str:
    """Map free-text + event_type to one of TIMELINE_CATEGORIES."""
    lowered = (event_text or "").lower()
    for category, keywords in TIMELINE_CATEGORY_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            return category
    if event_type:
        et = event_type.lower().strip()
        if et in EVENT_TYPE_TO_CATEGORY:
            return EVENT_TYPE_TO_CATEGORY[et]
        # Heuristic: any event_type containing a known category word
        for key, mapped in EVENT_TYPE_TO_CATEGORY.items():
            if key in et:
                return mapped
    return "other"


def _coerce_iso_date(value) -> Optional[str]:
    """Return YYYY-MM-DD if `value` starts with a parseable ISO date, else None."""
    if not value or not isinstance(value, str):
        return None
    m = ISO_DATE_RE.match(value.strip())
    if not m:
        return None
    candidate = m.group(1)
    try:
        datetime.strptime(candidate, "%Y-%m-%d")
    except ValueError:
        return None
    return candidate


def normalize_catalyst_for_timeline(
    raw: Mapping,
    *,
    subject_ticker: str,
) -> Optional[dict]:
    """Normalize one catalyst record for the Mode C timeline view.

    Backward-compat rules:
    - Legacy single ``date`` field maps to ``start_date == end_date``.
    - Missing ``category`` is inferred from description + event_type, falling
      back to ``"other"`` when nothing matches.
    - Missing ``ticker`` defaults to ``subject_ticker`` (passed by caller).
    - Missing ``significance`` defaults to ``"medium"``.

    Returns ``None`` when no parseable date is available — invalid items are
    silently dropped so the timeline doesn't break on TBD / freeform values.
    """
    if not isinstance(raw, Mapping):
        return None

    start_raw = raw.get("start_date") or raw.get("date")
    end_raw = raw.get("end_date") or raw.get("date") or start_raw

    start_date = _coerce_iso_date(start_raw)
    end_date = _coerce_iso_date(end_raw) or start_date
    if start_date is None:
        return None
    if end_date is None:
        end_date = start_date

    is_range = start_date != end_date

    # Category — explicit > inferred from text > inferred from event_type > other.
    explicit_category = raw.get("category")
    if explicit_category and explicit_category in TIMELINE_CATEGORIES:
        category = explicit_category
    else:
        text_for_classify = " ".join(
            str(x)
            for x in (raw.get("description"), raw.get("event"), raw.get("event_type"))
            if x
        )
        category = _classify_timeline_category(text_for_classify, raw.get("event_type"))

    significance = raw.get("significance") or "medium"
    if significance not in ("high", "medium", "low"):
        significance = "medium"

    ticker = raw.get("ticker") or subject_ticker

    return {
        # Preserve the legacy `date` field for downstream consumers that
        # haven't migrated yet.
        "date": start_raw if isinstance(start_raw, str) else start_date,
        "start_date": start_date,
        "end_date": end_date,
        "is_range": is_range,
        "category": category,
        "ticker": ticker,
        "event_type": raw.get("event_type"),
        "description": raw.get("description") or raw.get("event") or "",
        "significance": significance,
        "expected_impact": raw.get("expected_impact"),
    }


def build_timeline_payload(
    *,
    subject_ticker: str,
    subject_catalysts: Iterable[Mapping],
    peer_catalysts: Optional[Mapping[str, Iterable[Mapping]]] = None,
) -> dict:
    """Produce the run-local payload consumed by the Mode C timeline renderer.

    Output shape:
        {
          "subject_ticker": "GOOGL",
          "peer_count": 2,
          "categories": ["earnings", "regulatory", "product", "macro", "other"],
          "events": [ <normalized catalyst>, ... ],   # sorted by start_date
        }

    Subject events are flagged with ``is_subject=True``; peer events are
    flagged ``is_subject=False`` so the renderer can emphasize the subject
    ticker visually. Items with unparseable dates are dropped.
    """
    events: list[dict] = []

    for raw in subject_catalysts or []:
        normalized = normalize_catalyst_for_timeline(raw, subject_ticker=subject_ticker)
        if normalized is None:
            continue
        # Force subject ticker on subject-side records even if the input
        # carried a stale `ticker` field.
        normalized["ticker"] = subject_ticker
        normalized["is_subject"] = True
        events.append(normalized)

    peer_count = 0
    for peer_ticker, raws in (peer_catalysts or {}).items():
        peer_added = False
        for raw in raws or []:
            normalized = normalize_catalyst_for_timeline(
                raw, subject_ticker=peer_ticker
            )
            if normalized is None:
                continue
            normalized["ticker"] = peer_ticker
            normalized["is_subject"] = False
            events.append(normalized)
            peer_added = True
        if peer_added:
            peer_count += 1

    events.sort(key=lambda e: (e["start_date"], 0 if e.get("is_subject") else 1))

    return {
        "subject_ticker": subject_ticker,
        "peer_count": peer_count,
        "categories": list(TIMELINE_CATEGORIES),
        "events": events,
    }


def _load_peer_catalysts_from_run(run_dir: Path) -> dict[str, list[dict]]:
    """Read Phase D `output/runs/{run_id}/peers/*.json` for next_earnings_date.

    Each peer JSON may carry a `next_earnings_date` field (ISO or
    "YYYY-MM-DD (estimated)" format) and/or an `upcoming_catalysts[]` list.
    Only entries with a parseable ISO date are surfaced.
    """
    peers_dir = run_dir / "peers"
    if not peers_dir.exists() or not peers_dir.is_dir():
        return {}

    out: dict[str, list[dict]] = {}
    for peer_file in sorted(peers_dir.glob("*.json")):
        try:
            with open(peer_file, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue

        # CLAUDE.md §12 trust boundary: skip peer files that lack a
        # _sanitization block. The aggregator never trusts unsanitized fetched
        # content.
        if "_sanitization" not in payload:
            continue

        peer_ticker = payload.get("ticker") or peer_file.stem.upper()
        items: list[dict] = []

        ner = payload.get("next_earnings_date")
        if ner:
            items.append(
                {
                    "date": ner,
                    "event_type": "earnings",
                    "category": "earnings",
                    "description": f"{peer_ticker} 다음 실적 발표",
                    "significance": "high",
                }
            )

        for cat in payload.get("upcoming_catalysts", []) or []:
            if isinstance(cat, dict):
                items.append(cat)

        if items:
            out[peer_ticker] = items

    return out


def cmd_timeline(
    *,
    subject_ticker: str,
    snapshot_path: Optional[Path],
    run_dir: Optional[Path],
    include_peers: bool,
    output_path: Optional[Path],
):
    """Build a Mode C timeline JSON for a single subject ticker.

    Reads `analysis-result.json` for subject catalysts, optionally merges peer
    earnings dates from the run-local `peers/` directory, and writes the
    timeline payload to `output_path` (or stdout when omitted).
    """
    subject_catalysts: list[dict] = []
    if snapshot_path and snapshot_path.exists():
        try:
            with open(snapshot_path, "r", encoding="utf-8") as f:
                snap = json.load(f)
            raw_list = snap.get("upcoming_catalysts", [])
            if isinstance(raw_list, list):
                subject_catalysts = [c for c in raw_list if isinstance(c, dict)]
        except (OSError, json.JSONDecodeError) as exc:
            print(
                json.dumps(
                    {"status": "error", "reason": f"failed to read snapshot: {exc}"},
                    ensure_ascii=False,
                ),
                file=sys.stderr,
            )
            sys.exit(2)

    peer_catalysts: Optional[dict[str, list[dict]]] = None
    if include_peers and run_dir is not None:
        peer_catalysts = _load_peer_catalysts_from_run(run_dir)

    payload = build_timeline_payload(
        subject_ticker=subject_ticker,
        subject_catalysts=subject_catalysts,
        peer_catalysts=peer_catalysts,
    )

    if output_path:
        atomic_write(output_path, payload)
        print(
            json.dumps(
                {
                    "status": "ok",
                    "subject_ticker": subject_ticker,
                    "events": len(payload["events"]),
                    "peer_count": payload["peer_count"],
                    "output": str(output_path),
                },
                ensure_ascii=False,
            )
        )
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))


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
                events.append(build_catalyst_record({
                    "date": event_date,
                    "ticker": ticker,
                    "market": market,
                    "event_type": cat.get("event_type", cat.get("event", "unknown")),
                    "event": cat.get("event", cat.get("description", cat.get("event_type", ""))),
                    "description": cat.get("description", cat.get("event", "")),
                    "significance": cat.get("significance", "medium"),
                    "source": cat.get("source", snap_path_str),
                    "source_snapshot": snap_path_str,
                }))

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
    print(f"{'Date':<12} {'Ticker':<10} {'Market':<7} {'Impact':<8} {'Category':<10} {'Event'}")
    print(sep)

    for e in filtered:
        impact = e.get("impact") or {"high": "H", "medium": "M", "low": "L"}.get(str(e.get("significance", "medium")).lower(), "M")
        category = e.get("category", "Corporate")
        desc = e.get("description") or e.get("event_type", "")
        if len(desc) > 45:
            desc = desc[:42] + "..."
        print(f"{e['date']:<12} {e['ticker']:<10} {e['market']:<7} {impact:<8} {category:<10} {desc}")

    print(sep)
    print(f"Total: {len(filtered)} events | Calendar built: {calendar.get('build_date', 'unknown')}")


def main():
    parser = argparse.ArgumentParser(description="Catalyst aggregator")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("build")

    show_p = subparsers.add_parser("show")
    show_p.add_argument("--days", type=int, default=30)
    show_p.add_argument("--ticker", default=None)

    timeline_p = subparsers.add_parser(
        "timeline",
        help=(
            "Build a Mode C catalyst timeline JSON for a single subject "
            "ticker. Optionally merges peer earnings dates from "
            "output/runs/{run_id}/peers/ when --include-peers is set."
        ),
    )
    timeline_p.add_argument(
        "--ticker",
        required=True,
        help="Subject ticker (e.g. GOOGL). Used as the default ticker label "
             "for catalysts that don't carry one and as the focal point of "
             "the rendered timeline.",
    )
    timeline_p.add_argument(
        "--snapshot",
        required=True,
        help="Path to the subject's analysis-result.json (the source of "
             "upcoming_catalysts[]).",
    )
    timeline_p.add_argument(
        "--run-dir",
        default=None,
        help="Path to the run-local directory (output/runs/{run_id}/{ticker}). "
             "Required when --include-peers is set so peer JSONs in "
             "../peers/ can be discovered.",
    )
    timeline_p.add_argument(
        "--include-peers",
        action="store_true",
        help="Phase D — merge peer earnings dates from output/runs/{run_id}/peers/*.json. "
             "Each peer JSON must carry a _sanitization block (CLAUDE.md §12).",
    )
    timeline_p.add_argument(
        "--output",
        default=None,
        help="Output path for the timeline JSON. When omitted the payload is "
             "printed to stdout.",
    )

    args = parser.parse_args()

    if args.command == "build":
        cmd_build()
    elif args.command == "show":
        cmd_show(args.days, args.ticker)
    elif args.command == "timeline":
        run_dir = Path(args.run_dir) if args.run_dir else None
        if args.include_peers and run_dir is None:
            parser.error("--include-peers requires --run-dir")
        cmd_timeline(
            subject_ticker=args.ticker.upper(),
            snapshot_path=Path(args.snapshot) if args.snapshot else None,
            run_dir=run_dir,
            include_peers=bool(args.include_peers),
            output_path=Path(args.output) if args.output else None,
        )


if __name__ == "__main__":
    main()
