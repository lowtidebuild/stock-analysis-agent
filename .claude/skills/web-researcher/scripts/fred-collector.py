#!/usr/bin/env python3
"""
FRED API Collector
Fetches macroeconomic indicators from FRED (Federal Reserve Economic Data).

Usage:
  python fred-collector.py --output output/data/macro/fred-snapshot.json
  python fred-collector.py --market KR --output output/data/macro/fred-snapshot.json
  python fred-collector.py --output output/data/macro/fred-snapshot.json --force

Cache: 24-hour TTL. If cache is valid, returns cached data (zero API calls).
       If cache is stale but refresh fails, returns stale data with warning.

API Key priority:
  1. --api-key argument
  2. FRED_API_KEY environment variable
  3. FRED_API_KEY in <repo-root>/.env (auto-loaded if python-dotenv installed)

FRED API docs: https://fred.stlouisfed.org/docs/api/fred/
"""

import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Auto-load <repo>/.env if present so FRED_API_KEY in .env works without
# manually exporting it before each call.
try:
    from dotenv import load_dotenv  # type: ignore
    _env_file = _REPO_ROOT / ".env"
    if _env_file.exists():
        load_dotenv(_env_file, override=False)
except ImportError:
    pass

from tools.prompt_injection_filter import SANITIZER_VERSION, sanitize_record  # noqa: E402

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"

CACHE_TTL_HOURS = 24

# All FRED series to collect — common + all sectors + KR overlay
SERIES_CONFIG = {
    # Common (always relevant)
    "DGS10":            {"name": "10-Year Treasury Yield",             "unit": "percent",             "category": "common"},
    "DGS2":             {"name": "2-Year Treasury Yield",              "unit": "percent",             "category": "common"},
    "DFF":              {"name": "Federal Funds Effective Rate",       "unit": "percent",             "category": "common"},
    "CPIAUCSL":         {"name": "CPI All Urban Consumers",           "unit": "index",               "category": "common",  "transform": "yoy"},
    "A191RL1Q225SBEA":  {"name": "Real GDP Growth Rate (Quarterly)",  "unit": "percent",             "category": "common"},
    "UNRATE":           {"name": "Unemployment Rate",                  "unit": "percent",             "category": "common"},
    # Financial sector
    "BAA10Y":           {"name": "Moody's BAA Corporate Bond Spread", "unit": "percent",             "category": "financial"},
    "DPRIME":           {"name": "Bank Prime Loan Rate",              "unit": "percent",             "category": "financial"},
    # Energy sector
    "DCOILWTICO":       {"name": "WTI Crude Oil Price",               "unit": "dollars_per_barrel",  "category": "energy"},
    # Consumer sector
    "RSAFS":            {"name": "Advance Retail Sales",              "unit": "millions_of_dollars", "category": "consumer"},
    "UMCSENT":          {"name": "Consumer Sentiment (UMich)",        "unit": "index_1966Q1_100",    "category": "consumer"},
    # Industrial sector
    "INDPRO":           {"name": "Industrial Production Index",       "unit": "index_2017_100",      "category": "industrial"},
    # Korean overlay
    "DEXKOUS":          {"name": "USD/KRW Exchange Rate",             "unit": "krw_per_usd",         "category": "kr_overlay"},
}

MACRO_FIELD_MAP = {
    "risk_free_rate": ("common", "DGS10"),
    "fed_funds_rate": ("common", "DFF"),
    "yield_curve_spread": ("common", "yield_curve_spread"),
    "cpi_yoy": ("common", "CPIAUCSL"),
    "gdp_growth": ("common", "A191RL1Q225SBEA"),
    "unemployment": ("common", "UNRATE"),
}

KR_OVERLAY_FIELD_MAP = {
    "usd_krw": "DEXKOUS",
}

SECTOR_FIELD_MAP = {
    "financial": {"baa_spread": "BAA10Y", "prime_rate": "DPRIME"},
    "energy": {"wti_crude": "DCOILWTICO"},
    "consumer": {"retail_sales": "RSAFS", "consumer_sentiment": "UMCSENT"},
    "industrial": {"industrial_production": "INDPRO"},
}


def fred_request(series_id, api_key, limit=5):
    """Fetch latest observations for a FRED series. Returns list of observations or None."""
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "sort_order": "desc",
        "limit": str(limit),
    }
    url = FRED_BASE + "?" + urllib.parse.urlencode(params)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "StockAnalysisAgent/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data.get("observations", [])
    except Exception as e:
        return None


def parse_latest_value(observations):
    """Extract the most recent non-'.' value from FRED observations."""
    if not observations:
        return None, None
    for obs in observations:
        val = obs.get("value", ".")
        if val != ".":
            try:
                return float(val), obs.get("date")
            except (ValueError, TypeError):
                continue
    return None, None


def compute_yoy_change(observations):
    """Compute YoY % change from FRED observations (for CPI-like index series).

    Fetches 15 monthly observations (desc order) so index 0 = latest, index 12 = ~12 months ago.
    """
    if not observations or len(observations) < 2:
        return None
    # Build list of (date, value) pairs, skipping missing '.' values
    values = []
    for obs in observations:
        val = obs.get("value", ".")
        if val != ".":
            try:
                values.append((obs.get("date", ""), float(val)))
            except (ValueError, TypeError):
                continue
    if len(values) < 2:
        return None

    current_val = values[0][1]
    # Find observation closest to 12 months ago
    # With 15 monthly observations sorted desc, index ~12 is approximately 1 year ago
    prior_val = values[-1][1] if len(values) >= 12 else values[-1][1]
    # Prefer the 12th observation if available (more accurate YoY)
    if len(values) >= 13:
        prior_val = values[12][1]

    if prior_val and prior_val != 0:
        return round((current_val - prior_val) / prior_val * 100, 2)
    return None


def macro_grade(api_status, errors=None, cache_status=None):
    """Return the display grade for the structured FRED macro payload."""
    if cache_status == "cache_very_stale":
        return "C"
    if cache_status == "cache_stale" or api_status == "failed_using_stale":
        return "B"
    if api_status == "success" and not errors:
        return "A"
    if api_status == "partial":
        return "B"
    return "D"


def macro_entry_value(entry):
    if not isinstance(entry, dict):
        return None
    if entry.get("yoy_pct") is not None:
        return entry.get("yoy_pct")
    return entry.get("value")


def macro_series_item(series_id, entry, grade):
    if not isinstance(entry, dict):
        return None
    value = macro_entry_value(entry)
    if value is None:
        return None
    return {
        "id": series_id,
        "label": entry.get("series_name") or series_id,
        "value": value,
        "as_of_date": entry.get("date"),
        "unit": entry.get("unit"),
        "grade": grade,
        "source": "FRED",
    }


def _macro_group(snapshot, group_name):
    group = snapshot.get(group_name)
    return group if isinstance(group, dict) else {}


def build_macro_context_structured(snapshot, reason=None, cache_status=None):
    """Build the canonical macro_context.structured contract from a FRED snapshot."""
    retrieved_at = snapshot.get("collection_timestamp") or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    errors = snapshot.get("errors") if isinstance(snapshot.get("errors"), list) else []
    api_status = snapshot.get("api_status") or ("failed" if reason else "success")
    grade = macro_grade(api_status, errors=errors, cache_status=cache_status)

    common = _macro_group(snapshot, "common")
    sector = _macro_group(snapshot, "sector")
    kr_overlay = _macro_group(snapshot, "kr_overlay")

    if reason:
        return {
            "source": "FRED",
            "status": "unavailable",
            "grade": "D",
            "reason": reason,
            "retrieved_at": retrieved_at,
            "series": [],
        }

    series = []
    for series_id, entry in common.items():
        item = macro_series_item(series_id, entry, grade)
        if item:
            series.append(item)
    for sector_entries in sector.values():
        if not isinstance(sector_entries, dict):
            continue
        for series_id, entry in sector_entries.items():
            item = macro_series_item(series_id, entry, grade)
            if item:
                series.append(item)
    for series_id, entry in kr_overlay.items():
        item = macro_series_item(series_id, entry, grade)
        if item:
            series.append(item)

    if not series:
        return {
            "source": "FRED",
            "status": "unavailable",
            "grade": "D",
            "reason": "no_series_available",
            "retrieved_at": retrieved_at,
            "series": [],
        }

    structured = {
        "source": "FRED",
        "status": "available",
        "tag": "[Macro]",
        "grade": grade,
        "retrieved_at": retrieved_at,
        "series": series,
        "sector_specific": {},
        "kr_overlay": {},
    }

    for field_name, (group_name, series_id) in MACRO_FIELD_MAP.items():
        group = common if group_name == "common" else {}
        entry = group.get(series_id)
        value = macro_entry_value(entry)
        if value is not None:
            structured[field_name] = value

    spread = structured.get("yield_curve_spread")
    if spread is not None:
        structured["yield_curve_inverted"] = spread < 0

    for sector_name, fields in SECTOR_FIELD_MAP.items():
        sector_entries = sector.get(sector_name) if isinstance(sector.get(sector_name), dict) else {}
        sector_payload = {}
        for field_name, series_id in fields.items():
            value = macro_entry_value(sector_entries.get(series_id))
            if value is not None:
                sector_payload[field_name] = value
        if sector_payload:
            structured["sector_specific"][sector_name] = sector_payload

    for field_name, series_id in KR_OVERLAY_FIELD_MAP.items():
        value = macro_entry_value(kr_overlay.get(series_id))
        if value is not None:
            structured["kr_overlay"][field_name] = value

    if errors:
        structured["warnings"] = errors
    return structured


def attach_macro_context(snapshot, reason=None, cache_status=None):
    snapshot["macro_context"] = {
        "structured": build_macro_context_structured(snapshot, reason=reason, cache_status=cache_status)
    }
    return snapshot


def build_failure_snapshot(reason, errors=None, include_kr=False):
    snapshot = {
        "collection_timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "cache_ttl_hours": CACHE_TTL_HOURS,
        "api_status": "failed",
        "source": "FRED",
        "tag": "[Macro]",
        "confidence_grade": "D",
        "common": {},
        "sector": {"technology": {}, "financial": {}, "energy": {}, "consumer": {}, "industrial": {}},
        "kr_overlay": {} if include_kr else {},
        "errors": errors or [reason],
    }
    return attach_macro_context(snapshot, reason=reason)


def write_snapshot(output_path, snapshot):
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)


def check_cache(output_path, force=False):
    """Check if cached snapshot is valid. Returns (data, status) or (None, status)."""
    if force:
        return None, "force_refresh"
    if not os.path.exists(output_path):
        return None, "no_cache"
    try:
        with open(output_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        ts = data.get("collection_timestamp")
        if not ts:
            return None, "invalid_cache"
        collection_time = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        age_hours = (datetime.now(timezone.utc) - collection_time).total_seconds() / 3600
        if age_hours < CACHE_TTL_HOURS:
            return data, "cache_valid"
        elif age_hours < 24 * 7:
            return data, "cache_stale"
        else:
            return data, "cache_very_stale"
    except (json.JSONDecodeError, ValueError, KeyError):
        return None, "invalid_cache"


def collect_all_series(api_key, include_kr=False):
    """Fetch all FRED series. Returns (series_data, errors)."""
    series_data = {}
    errors = []

    for series_id, config in SERIES_CONFIG.items():
        # Skip KR overlay if not requested
        if config["category"] == "kr_overlay" and not include_kr:
            continue

        # Fetch more observations for YoY transform series
        limit = 15 if config.get("transform") == "yoy" else 5
        observations = fred_request(series_id, api_key, limit=limit)

        if observations is None:
            errors.append(f"Failed to fetch {series_id} ({config['name']})")
            series_data[series_id] = None
            continue

        value, date = parse_latest_value(observations)
        entry = {
            "value": value,
            "date": date,
            "unit": config["unit"],
            "series_name": config["name"],
            "category": config["category"],
        }

        # Compute YoY for CPI-like series
        if config.get("transform") == "yoy":
            yoy = compute_yoy_change(observations)
            entry["yoy_pct"] = yoy
            entry["unit"] = "percent_yoy"

        series_data[series_id] = entry

        # Small delay to stay well within FRED rate limits (120 req/min)
        time.sleep(0.3)

    return series_data, errors


def build_snapshot(series_data, errors, include_kr=False):
    """Structure the collected data into the snapshot format."""
    common = {}
    sector = {"technology": {}, "financial": {}, "energy": {}, "consumer": {}, "industrial": {}}
    kr_overlay = {}

    for series_id, entry in series_data.items():
        if entry is None:
            continue
        cat = entry["category"]
        if cat == "common":
            common[series_id] = entry
        elif cat == "kr_overlay":
            kr_overlay[series_id] = entry
        elif cat in sector:
            sector[cat][series_id] = entry

    # Derived: yield curve spread
    dgs10 = (common.get("DGS10") or {}).get("value")
    dgs2 = (common.get("DGS2") or {}).get("value")
    if dgs10 is not None and dgs2 is not None:
        common["yield_curve_spread"] = {
            "value": round(dgs10 - dgs2, 3),
            "derived": True,
            "formula": "DGS10 - DGS2",
            "interpretation": "positive = normal, negative = inverted",
        }

    api_status = "success" if not errors else ("partial" if any(v is not None for v in series_data.values()) else "failed")
    snapshot = {
        "collection_timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "cache_ttl_hours": CACHE_TTL_HOURS,
        "api_status": api_status,
        "source": "FRED",
        "tag": "[Macro]",
        "confidence_grade": macro_grade(api_status, errors=errors),
        "common": common,
        "sector": sector,
        "kr_overlay": kr_overlay if include_kr else {},
        "errors": errors,
    }
    return attach_macro_context(snapshot)


def attach_sanitization_metadata(record):
    cleaned, sanitization_findings = sanitize_record(record)
    cleaned["_sanitization"] = {
        "tool": "tools/prompt_injection_filter.py",
        "version": SANITIZER_VERSION,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "redactions": len(sanitization_findings),
        "findings": sanitization_findings,
    }
    return cleaned


def main():
    parser = argparse.ArgumentParser(description="FRED API macroeconomic data collector")
    parser.add_argument("--output", required=True, help="Output JSON file path")
    parser.add_argument("--market", default="US", choices=["US", "KR"], help="Market (US or KR — KR adds KRW/USD)")
    parser.add_argument("--force", action="store_true", help="Ignore cache, force API refresh")
    parser.add_argument("--api-key", default="", help="FRED API key (overrides env var)")
    args = parser.parse_args()

    api_key = args.api_key or os.environ.get("FRED_API_KEY", "")
    include_kr = args.market == "KR"

    # Check cache first
    cached_data, cache_status = check_cache(args.output, force=args.force)

    if cache_status == "cache_valid":
        if not isinstance(cached_data.get("macro_context"), dict):
            cached_data = attach_sanitization_metadata(attach_macro_context(cached_data, cache_status=cache_status))
            write_snapshot(args.output, cached_data)
        # Cache is fresh — return immediately
        summary = {
            "status": "cached",
            "cache_age_note": "Cache valid (< 24h), no API calls made",
            "output_path": args.output,
            "series_count": sum(1 for v in {**cached_data.get("common", {}), **cached_data.get("kr_overlay", {})}.values() if isinstance(v, dict) and v.get("value") is not None),
        }
        print(json.dumps(summary, ensure_ascii=False))
        return

    # Cache expired or missing — try to refresh
    if not api_key:
        if cached_data:
            # No API key but have stale cache — return it with warning
            cached_data["api_status"] = "failed_using_stale"
            cached_data["confidence_grade"] = macro_grade("failed_using_stale", cache_status=cache_status)
            cached_data = attach_sanitization_metadata(attach_macro_context(cached_data, cache_status=cache_status))
            write_snapshot(args.output, cached_data)
            summary = {
                "status": "stale_cache",
                "warning": "FRED_API_KEY not set. Using stale cached data.",
                "output_path": args.output,
            }
            print(json.dumps(summary, ensure_ascii=False))
            return
        else:
            error = "FRED API key not provided. Set FRED_API_KEY env var or use --api-key."
            failure_snapshot = attach_sanitization_metadata(
                build_failure_snapshot("missing_api_key", errors=[error], include_kr=include_kr)
            )
            write_snapshot(args.output, failure_snapshot)
            result = {"status": "fail", "error": error, "output_path": args.output}
            print(json.dumps(result, ensure_ascii=False))
            sys.exit(1)

    # Fetch from FRED API
    series_data, errors = collect_all_series(api_key, include_kr=include_kr)

    if not any(v is not None for v in series_data.values()):
        # Total failure — return stale cache if available
        if cached_data:
            cached_data["api_status"] = "failed_using_stale"
            cached_data["confidence_grade"] = macro_grade("failed_using_stale", cache_status=cache_status)
            cached_data["errors"] = errors
            cached_data = attach_sanitization_metadata(attach_macro_context(cached_data, cache_status=cache_status))
            write_snapshot(args.output, cached_data)
            summary = {
                "status": "stale_cache",
                "warning": "All FRED API calls failed. Using stale cached data.",
                "errors": errors,
                "output_path": args.output,
            }
            print(json.dumps(summary, ensure_ascii=False))
            return
        else:
            failure_snapshot = attach_sanitization_metadata(
                build_failure_snapshot("collector_failed", errors=errors, include_kr=include_kr)
            )
            write_snapshot(args.output, failure_snapshot)
            result = {
                "status": "fail",
                "error": "All FRED API calls failed and no cache available.",
                "errors": errors,
                "output_path": args.output,
            }
            print(json.dumps(result, ensure_ascii=False))
            sys.exit(1)

    # Build and write snapshot
    snapshot = attach_sanitization_metadata(
        build_snapshot(series_data, errors, include_kr=include_kr)
    )
    write_snapshot(args.output, snapshot)

    # Summary to stdout
    non_null = sum(1 for v in series_data.values() if v is not None)
    summary = {
        "status": "success" if not errors else "partial",
        "series_collected": non_null,
        "series_failed": len(errors),
        "include_kr": include_kr,
        "output_path": args.output,
    }
    if errors:
        summary["errors"] = errors
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
