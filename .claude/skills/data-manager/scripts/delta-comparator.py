#!/usr/bin/env python3
"""
delta-comparator.py — Compares two analysis snapshots for a ticker.

Usage:
    python delta-comparator.py compare --ticker AAPL --old-date 2026-02-01 --new-date latest
    python delta-comparator.py compare --ticker AAPL --old-date 30d --new-date latest
    python delta-comparator.py compare --ticker AAPL --old-date latest --new-date latest --format html
    python delta-comparator.py compare --ticker AAPL --old-date latest --new-date latest --no-delta

Output formats (--format):
    - json (default): legacy structured delta report with `delta_payload` block
      attached for renderer consumption.
    - html: standalone <section class="delta-banner"> block ready to drop into
      Mode A / B / C output above the first content section.
    - markdown: quote-block banner suitable for Mode D / chat summaries.

Auto-discovery:
    When both --old-date and --new-date are 'latest' the comparator picks the
    two most recent distinct snapshots for the ticker. With a single snapshot
    available, it emits {"status": "skipped", "reason": "no_prior_snapshot"}
    and exits 0.

Toggle:
    --no-delta short-circuits with {"status": "skipped", "reason":
    "no_delta_flag"} so callers can centrally suppress banner emission without
    branching logic at every call site.
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

from tools.analysis_contract import extract_numeric_value, find_repo_root  # noqa: E402
from tools.delta_banner import (  # noqa: E402
    render_html_banner,
    render_markdown_banner,
)
from tools.paths import data_dir, runtime_path  # noqa: E402
from tools.snapshot_store import iter_snapshot_entries, load_snapshot_document  # noqa: E402

BASE_DIR = find_repo_root(__file__)
DEFAULT_OUTPUT_DIR = data_dir() / "data"

KEY_METRICS = [
    "market_cap", "pe_ratio", "ev_ebitda", "fcf_yield",
    "revenue_growth_yoy", "operating_margin", "gross_margin",
    "net_margin", "net_debt_ebitda", "revenue_ttm",
    "ebitda_ttm", "eps_ttm", "fcf_ttm", "roe", "dividend_yield",
]

SIGNIFICANT_CHANGE_THRESHOLD = 0.10  # 10% change = significant


def resolve_data_root(data_root: str | None = None) -> Path:
    if not data_root:
        return DEFAULT_OUTPUT_DIR
    return runtime_path(data_root)


def load_snapshot(ticker: str, date_arg: str, data_root: str | None = None) -> dict:
    """Load snapshot using snapshot-manager logic."""
    ticker_upper = ticker.upper()
    ticker_dir = resolve_data_root(data_root) / ticker_upper

    if date_arg == "latest":
        p = ticker_dir / "latest.json"
        if not p.exists():
            raise FileNotFoundError(f"No latest.json for {ticker_upper}")
        return load_snapshot_document(p, BASE_DIR)

    # Handle Nd format
    if date_arg.endswith("d") and date_arg[:-1].isdigit():
        days_ago = int(date_arg[:-1])
        target_date = (date.today() - timedelta(days=days_ago)).isoformat()
    else:
        target_date = date_arg

    entries = iter_snapshot_entries(ticker_dir, ticker_upper, BASE_DIR)
    for entry in entries:
        if "data" not in entry:
            continue
        snap_date = str(entry.get("analysis_date") or "")
        if snap_date <= target_date:
            return entry["data"]

    raise FileNotFoundError(f"No snapshot for {ticker_upper} on or before {target_date}")


def auto_discover_pair(ticker: str, data_root: str | None = None) -> tuple[dict, dict] | None:
    """Pick the two most recent distinct snapshots for a ticker.

    Returns (old_snapshot, new_snapshot) when at least two are available with
    different analysis_date values, otherwise None.
    """
    ticker_upper = ticker.upper()
    ticker_dir = resolve_data_root(data_root) / ticker_upper
    if not ticker_dir.exists():
        return None
    entries = iter_snapshot_entries(ticker_dir, ticker_upper, BASE_DIR)
    valid = [e for e in entries if "data" in e]
    if len(valid) < 2:
        return None
    new_entry = valid[0]
    new_date = str(new_entry.get("analysis_date") or "")
    old_entry = None
    for entry in valid[1:]:
        snap_date = str(entry.get("analysis_date") or "")
        if snap_date and snap_date != new_date:
            old_entry = entry
            break
    if old_entry is None:
        old_entry = valid[1]
    return old_entry["data"], new_entry["data"]


def pct_change(old_val, new_val):
    """Compute % change from old to new. Returns None if not computable."""
    old_num = extract_numeric_value(old_val)
    new_num = extract_numeric_value(new_val)
    if old_num is None or new_num is None:
        return None
    if old_num == 0:
        return None
    return (new_num - old_num) / abs(old_num) * 100


def direction(pct):
    if pct is None:
        return "unchanged"
    if pct > 0:
        return "up"
    if pct < 0:
        return "down"
    return "unchanged"


def get_nested(snap: dict, key: str):
    """Get value from key_metrics or top-level."""
    km = snap.get("key_metrics", {})
    if key in km:
        metric = km[key]
        if isinstance(metric, dict) and "value" in metric:
            return metric.get("value")
        return metric
    return snap.get(key)


def compare_metrics(old_snap: dict, new_snap: dict) -> dict:
    changes = {}
    for metric in KEY_METRICS:
        old_val = get_nested(old_snap, metric)
        new_val = get_nested(new_snap, metric)
        pct = pct_change(old_val, new_val)
        changes[metric] = {
            "old": old_val,
            "new": new_val,
            "pct_change": round(pct, 2) if pct is not None else None,
            "direction": direction(pct),
            "significant": abs(pct) >= SIGNIFICANT_CHANGE_THRESHOLD * 100 if pct is not None else False,
        }
    return changes


def compare_scenarios(old_snap: dict, new_snap: dict) -> dict:
    changes = {}
    for case in ("bull", "base", "bear"):
        old_s = old_snap.get("scenarios", {}).get(case, {})
        new_s = new_snap.get("scenarios", {}).get(case, {})
        changes[case] = {
            "old_target": old_s.get("target"),
            "new_target": new_s.get("target"),
            "old_return_pct": old_s.get("return_pct"),
            "new_return_pct": new_s.get("return_pct"),
            "old_probability": old_s.get("probability"),
            "new_probability": new_s.get("probability"),
            "assumption_changed": old_s.get("key_assumption") != new_s.get("key_assumption"),
        }
    return changes


def compare_risks(old_snap: dict, new_snap: dict):
    old_risks = {r if isinstance(r, str) else r.get("title", str(r))
                 for r in old_snap.get("top_risks", [])}
    new_risks = {r if isinstance(r, str) else r.get("title", str(r))
                 for r in new_snap.get("top_risks", [])}
    return {
        "new_risks": sorted(new_risks - old_risks),
        "resolved_risks": sorted(old_risks - new_risks),
        "unchanged_risks": sorted(old_risks & new_risks),
    }


def compare_catalysts(old_snap: dict, new_snap: dict):
    def catalyst_key(c):
        if isinstance(c, dict):
            return f"{c.get('date', '')}:{c.get('event', c.get('description', ''))}"
        return str(c)

    old_keys = {catalyst_key(c) for c in old_snap.get("upcoming_catalysts", [])}
    new_cats = new_snap.get("upcoming_catalysts", [])
    new_keys = {catalyst_key(c) for c in new_cats}

    added = [c for c in new_cats if catalyst_key(c) not in old_keys]
    removed_keys = old_keys - new_keys

    return {
        "new_catalysts": added,
        "removed_catalysts": sorted(removed_keys),
    }


def compare_thesis_pillars(old_snap: dict, new_snap: dict) -> list[dict]:
    def pillar_key(item):
        if not isinstance(item, dict):
            return str(item).strip().lower()
        return str(item.get("pillar") or item.get("title") or item).strip().lower()

    old_map = {pillar_key(item): item for item in old_snap.get("thesis_pillars", []) if pillar_key(item)}
    new_map = {pillar_key(item): item for item in new_snap.get("thesis_pillars", []) if pillar_key(item)}
    rows = []
    for key in sorted(set(old_map) | set(new_map)):
        old_item = old_map.get(key)
        new_item = new_map.get(key)
        if old_item is None:
            change = "New"
        elif new_item is None:
            change = "Dropped"
        elif old_item.get("current_status") != new_item.get("current_status") or old_item.get("trend") != new_item.get("trend"):
            change = "Changed"
        else:
            change = "Unchanged"
        rows.append({
            "pillar": (new_item or old_item or {}).get("pillar") if isinstance(new_item or old_item, dict) else key,
            "prior_status": old_item.get("current_status") if isinstance(old_item, dict) else None,
            "current_status": new_item.get("current_status") if isinstance(new_item, dict) else None,
            "trend": new_item.get("trend") if isinstance(new_item, dict) else None,
            "new_evidence": new_item.get("last_evidence") if isinstance(new_item, dict) else None,
            "change": change,
        })
    return rows


def build_summary(delta: dict) -> list:
    """Generate human-readable summary of significant changes."""
    summary = []

    # Price change
    pc = delta["price_change"]
    if pc["pct"] is not None and abs(pc["pct"]) >= 5:
        summary.append(
            f"Price {'up' if pc['pct'] > 0 else 'down'} {abs(pc['pct']):.1f}% "
            f"({pc['old']} → {pc['new']}) over {delta['elapsed_days']} days"
        )

    # R/R Score change
    rr = delta["rr_score_change"]
    if rr["old"] is not None and rr["new"] is not None:
        rr_delta = (rr["new"] or 0) - (rr["old"] or 0)
        if abs(rr_delta) >= 0.5:
            summary.append(f"R/R Score changed significantly: {rr['old']} → {rr['new']} ({rr_delta:+.2f})")

    # Verdict change
    vc = delta["verdict_change"]
    if vc["changed"]:
        summary.append(f"Verdict changed: {vc['old']} → {vc['new']}")

    # Significant metric changes
    for metric, mc in delta["metric_changes"].items():
        if mc["significant"] and mc["pct_change"] is not None:
            summary.append(
                f"{metric}: {mc['old']} → {mc['new']} ({mc['pct_change']:+.1f}%)"
            )

    # New risks
    if delta["risk_changes"]["new_risks"]:
        summary.append(f"New risks emerged: {', '.join(delta['risk_changes']['new_risks'])}")

    # New catalysts
    if delta["catalyst_changes"]["new_catalysts"]:
        cats = delta["catalyst_changes"]["new_catalysts"]
        summary.append(f"{len(cats)} new catalyst(s) identified")

    pillar_changes = [row for row in delta.get("thesis_pillar_changes", []) if row.get("change") in {"New", "Dropped", "Changed"}]
    if pillar_changes:
        summary.append(f"{len(pillar_changes)} thesis pillar change(s) identified")

    return summary if summary else ["No significant changes detected"]


def _risk_titles(snap: dict) -> list[str]:
    titles = []
    for risk in snap.get("top_risks", []) or []:
        if isinstance(risk, str):
            titles.append(risk)
        elif isinstance(risk, dict):
            title = risk.get("title") or risk.get("risk") or risk.get("name")
            if title:
                titles.append(str(title))
    return titles


def _catalyst_records(snap: dict) -> list[dict]:
    records = []
    for cat in snap.get("upcoming_catalysts", []) or []:
        if isinstance(cat, dict):
            records.append({
                "date": cat.get("date"),
                "event": cat.get("event") or cat.get("description") or "",
            })
        else:
            records.append({"date": None, "event": str(cat)})
    return records


def _catalyst_key(record: dict) -> str:
    return f"{record.get('date') or ''}::{(record.get('event') or '').strip().lower()}"


def _delta_pct_str(prev_val, curr_val) -> str | None:
    pct = pct_change(prev_val, curr_val)
    if pct is None:
        return None
    return f"{pct:+.1f}%"


def _signed(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{value:+.2f}"
    return str(value)


def build_delta_payload(old_snap: dict, new_snap: dict) -> dict:
    """Compact payload tailored for renderer banners (Mode A/B/C/D)."""
    prev_rr = old_snap.get("rr_score")
    curr_rr = new_snap.get("rr_score")
    rr_delta = None
    if isinstance(prev_rr, (int, float)) and isinstance(curr_rr, (int, float)):
        rr_delta = round(curr_rr - prev_rr, 2)
    rr_delta_pct = _delta_pct_str(prev_rr, curr_rr)

    base_prev = (old_snap.get("scenarios") or {}).get("base", {}).get("target")
    base_curr = (new_snap.get("scenarios") or {}).get("base", {}).get("target")
    currency = new_snap.get("currency") or old_snap.get("currency")

    wfv_prev = (old_snap.get("valuation_bridge") or {}).get("weighted_fair_value")
    wfv_curr = (new_snap.get("valuation_bridge") or {}).get("weighted_fair_value")

    old_risks = _risk_titles(old_snap)
    new_risks = _risk_titles(new_snap)
    old_risk_set = set(old_risks)
    new_risk_set = set(new_risks)

    old_cats = _catalyst_records(old_snap)
    new_cats = _catalyst_records(new_snap)
    old_keys = {_catalyst_key(c) for c in old_cats}
    new_keys = {_catalyst_key(c) for c in new_cats}

    return {
        "prev_date": old_snap.get("analysis_date"),
        "curr_date": new_snap.get("analysis_date"),
        "rr_score": {
            "prev": prev_rr,
            "curr": curr_rr,
            "delta": _signed(rr_delta),
            "delta_pct": rr_delta_pct,
        },
        "verdict": {
            "prev": old_snap.get("verdict"),
            "curr": new_snap.get("verdict"),
            "changed": old_snap.get("verdict") != new_snap.get("verdict"),
        },
        "base_target": {
            "prev": base_prev,
            "curr": base_curr,
            "delta_pct": _delta_pct_str(base_prev, base_curr),
            "currency": currency,
        },
        "weighted_fair_value": {
            "prev": wfv_prev,
            "curr": wfv_curr,
            "delta_pct": _delta_pct_str(wfv_prev, wfv_curr),
            "currency": currency,
        },
        "new_risks": [r for r in new_risks if r not in old_risk_set],
        "removed_risks": [r for r in old_risks if r not in new_risk_set],
        "new_catalysts": [c for c in new_cats if _catalyst_key(c) not in old_keys],
        "removed_catalysts": [c for c in old_cats if _catalyst_key(c) not in new_keys],
    }


def build_delta_report(ticker: str, old_date: str, new_date: str, data_root: str | None = None) -> dict:
    old_snap = load_snapshot(ticker, old_date, data_root=data_root)
    new_snap = load_snapshot(ticker, new_date, data_root=data_root)
    resolved_root = resolve_data_root(data_root)
    try:
        data_root_display = str(resolved_root.relative_to(BASE_DIR))
    except ValueError:
        data_root_display = str(resolved_root)

    # Elapsed days
    try:
        old_dt = datetime.fromisoformat(old_snap.get("analysis_date", ""))
        new_dt = datetime.fromisoformat(new_snap.get("analysis_date", ""))
        elapsed = (new_dt - old_dt).days
    except Exception:
        elapsed = None

    # Price change
    old_price = old_snap.get("price_at_analysis")
    new_price = new_snap.get("price_at_analysis")
    price_pct = pct_change(old_price, new_price)
    old_price_num = extract_numeric_value(old_price)
    new_price_num = extract_numeric_value(new_price)

    delta = {
        "ticker": ticker.upper(),
        "old_date": old_snap.get("analysis_date"),
        "new_date": new_snap.get("analysis_date"),
        "data_root": data_root_display,
        "elapsed_days": elapsed,
        "price_change": {
            "old": old_price,
            "new": new_price,
            "absolute": round(new_price_num - old_price_num, 4) if (old_price_num is not None and new_price_num is not None) else None,
            "pct": round(price_pct, 2) if price_pct is not None else None,
        },
        "rr_score_change": {
            "old": old_snap.get("rr_score"),
            "new": new_snap.get("rr_score"),
        },
        "verdict_change": {
            "old": old_snap.get("verdict"),
            "new": new_snap.get("verdict"),
            "changed": old_snap.get("verdict") != new_snap.get("verdict"),
        },
        "data_mode_change": {
            "old": old_snap.get("data_mode"),
            "new": new_snap.get("data_mode"),
        },
        "metric_changes": compare_metrics(old_snap, new_snap),
        "scenario_changes": compare_scenarios(old_snap, new_snap),
        "risk_changes": compare_risks(old_snap, new_snap),
        "catalyst_changes": compare_catalysts(old_snap, new_snap),
        "thesis_pillar_changes": compare_thesis_pillars(old_snap, new_snap),
    }

    delta["summary"] = build_summary(delta)
    delta["delta_payload"] = build_delta_payload(old_snap, new_snap)
    return delta


def _is_korean(snap: dict | None) -> bool:
    if not isinstance(snap, dict):
        return True  # default Korean for repo's primary audience
    lang = (snap.get("output_language") or "").lower()
    return lang.startswith("ko") if lang else True


def cmd_compare(
    ticker: str,
    old_date: str,
    new_date: str,
    data_root: str | None = None,
    fmt: str = "json",
    no_delta: bool = False,
):
    if no_delta:
        print(json.dumps({"status": "skipped", "reason": "no_delta_flag"}, ensure_ascii=False))
        return

    auto_pair: tuple[dict, dict] | None = None
    if old_date == "latest" and new_date == "latest":
        auto_pair = auto_discover_pair(ticker, data_root=data_root)
        if auto_pair is None:
            print(json.dumps(
                {"status": "skipped", "reason": "no_prior_snapshot"},
                ensure_ascii=False,
            ))
            return

    try:
        if auto_pair is not None:
            old_snap, new_snap = auto_pair
            resolved_root = resolve_data_root(data_root)
            try:
                data_root_display = str(resolved_root.relative_to(BASE_DIR))
            except ValueError:
                data_root_display = str(resolved_root)
            try:
                old_dt = datetime.fromisoformat(old_snap.get("analysis_date", ""))
                new_dt = datetime.fromisoformat(new_snap.get("analysis_date", ""))
                elapsed = (new_dt - old_dt).days
            except Exception:
                elapsed = None
            old_price = old_snap.get("price_at_analysis")
            new_price = new_snap.get("price_at_analysis")
            price_pct = pct_change(old_price, new_price)
            old_price_num = extract_numeric_value(old_price)
            new_price_num = extract_numeric_value(new_price)
            delta = {
                "ticker": ticker.upper(),
                "old_date": old_snap.get("analysis_date"),
                "new_date": new_snap.get("analysis_date"),
                "data_root": data_root_display,
                "elapsed_days": elapsed,
                "price_change": {
                    "old": old_price,
                    "new": new_price,
                    "absolute": round(new_price_num - old_price_num, 4) if (old_price_num is not None and new_price_num is not None) else None,
                    "pct": round(price_pct, 2) if price_pct is not None else None,
                },
                "rr_score_change": {
                    "old": old_snap.get("rr_score"),
                    "new": new_snap.get("rr_score"),
                },
                "verdict_change": {
                    "old": old_snap.get("verdict"),
                    "new": new_snap.get("verdict"),
                    "changed": old_snap.get("verdict") != new_snap.get("verdict"),
                },
                "data_mode_change": {
                    "old": old_snap.get("data_mode"),
                    "new": new_snap.get("data_mode"),
                },
                "metric_changes": compare_metrics(old_snap, new_snap),
                "scenario_changes": compare_scenarios(old_snap, new_snap),
                "risk_changes": compare_risks(old_snap, new_snap),
                "catalyst_changes": compare_catalysts(old_snap, new_snap),
                "thesis_pillar_changes": compare_thesis_pillars(old_snap, new_snap),
            }
            delta["summary"] = build_summary(delta)
            delta["delta_payload"] = build_delta_payload(old_snap, new_snap)
        else:
            delta = build_delta_report(ticker, old_date, new_date, data_root=data_root)
            new_snap = load_snapshot(ticker, new_date, data_root=data_root)
    except FileNotFoundError as e:
        if fmt in {"html", "markdown"}:
            # Renderers expect empty string fallback so they can drop the banner silently.
            print("")
            return
        print(json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False))
        sys.exit(1)

    payload = delta.get("delta_payload", {})
    korean = _is_korean(new_snap if not auto_pair else auto_pair[1])

    if fmt == "html":
        print(render_html_banner(payload, korean=korean))
    elif fmt == "markdown":
        print(render_markdown_banner(payload, korean=korean))
    else:
        print(json.dumps(delta, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description="Delta comparator for analysis snapshots")
    subparsers = parser.add_subparsers(dest="command", required=True)

    cmp_p = subparsers.add_parser("compare")
    cmp_p.add_argument("--ticker", required=True)
    cmp_p.add_argument("--old-date", required=True, help="YYYY-MM-DD | Nd | latest")
    cmp_p.add_argument("--new-date", required=True, help="YYYY-MM-DD | Nd | latest")
    cmp_p.add_argument("--data-root", default=None, help="Optional alternate snapshot root")
    cmp_p.add_argument(
        "--format",
        choices=["json", "html", "markdown"],
        default="json",
        help="Output format. JSON keeps the legacy delta report (now with a delta_payload block); html/markdown emit ready-to-prepend banners.",
    )
    cmp_p.add_argument(
        "--no-delta",
        action="store_true",
        help="Suppress emission. Returns {status: skipped, reason: no_delta_flag} on stdout.",
    )

    args = parser.parse_args()

    if args.command == "compare":
        cmd_compare(
            args.ticker,
            args.old_date,
            args.new_date,
            data_root=args.data_root,
            fmt=args.format,
            no_delta=args.no_delta,
        )


if __name__ == "__main__":
    main()
