from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from tools.paths import data_dir

CANONICAL_DISPLAY_TAGS = [
    "[Filing]",
    "[Company]",
    "[Portal]",
    "[KR-Portal]",
    "[Calc]",
    "[Est]",
    "[Macro]",
]

CANONICAL_SOURCE_TYPES = [
    "filing",
    "company_release",
    "portal_global",
    "portal_kr",
    "calculated",
    "estimate",
    "macro",
    "internal",
]

SOURCE_TYPE_TO_DISPLAY_TAG = {
    "filing": "[Filing]",
    "company_release": "[Company]",
    "portal_global": "[Portal]",
    "portal_kr": "[KR-Portal]",
    "calculated": "[Calc]",
    "estimate": "[Est]",
    "macro": "[Macro]",
    "internal": None,
}

SOURCE_TYPE_TO_AUTHORITY = {
    "filing": "regulatory",
    "company_release": "issuer",
    "portal_global": "market_portal",
    "portal_kr": "market_portal",
    "calculated": "derived",
    "estimate": "sell_side",
    "macro": "government",
    "internal": "internal",
}

LEGACY_TAG_ALIASES = {
    "[DART-API]": "filing",
    "[KR-Web]": "portal_kr",
    "[Calculated]": "calculated",
    "[Web]": "portal_global",
    "[1S]": None,
    "[Unverified]": None,
    "[Approx]": None,
    "[≈]": None,
    "[Filing]": "filing",
    "[Company]": "company_release",
    "[Portal]": "portal_global",
    "[KR-Portal]": "portal_kr",
    "[Calc]": "calculated",
    "[Est]": "estimate",
    "[Macro]": "macro",
}

ESTIMATE_SOURCE_MARKERS = (
    "marketbeat",
    "tipranks",
    "consensus",
    "price target",
    "grades summary",
    "historical grades",
    "analyst",
    "fmp",
)

PORTAL_KR_MARKERS = (
    "fnguide",
    "naver",
    "kind",
    "krx",
    "sedaily",
    "hankyung",
    "investing.com korea",
)

PORTAL_GLOBAL_MARKERS = (
    "yahoo",
    "marketwatch",
    "stockanalysis",
    "macrotrends",
    "companiesmarketcap",
    "gurufocus",
    "valueinvesting.io",
    "capital.com",
    "tradingview",
    "finviz",
    "google finance",
    "investing.com",
)

COMPANY_MARKERS = (
    "newsroom",
    "investor relations",
    "earnings call",
    "shareholder letter",
    "press release",
    "ir website",
)

FILING_MARKERS = (
    "sec",
    "10-k",
    "10-q",
    "8-k",
    "edgar",
    "dart",
    "financial datasets",
    "opendart",
)

MACRO_MARKERS = (
    "fred",
    "federal reserve",
    "st. louis fed",
    "bank of korea",
    "ecosis",
)

NUMERIC_SUFFIX_MULTIPLIERS = {
    "K": 1_000,
    "M": 1_000_000,
    "B": 1_000_000_000,
    "T": 1_000_000_000_000,
}


def find_repo_root(start: str | Path) -> Path:
    path = Path(start).resolve()
    candidates = [path] if path.is_dir() else [path.parent]
    candidates.extend(list(candidates[0].parents))
    for candidate in candidates:
        if (candidate / "CLAUDE.md").exists() and (candidate / "README.md").exists():
            return candidate
    raise RuntimeError(f"Could not locate repository root from {start}")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_run_id(tickers: Iterable[str], timestamp: datetime | None = None) -> str:
    stamp = (timestamp or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    cleaned = [re.sub(r"[^A-Za-z0-9]", "", ticker.upper()) for ticker in tickers if ticker]
    suffix = "_".join(cleaned[:3]) if cleaned else "SESSION"
    return f"{stamp}_{suffix}"


def default_report_extension(output_mode: str) -> str | None:
    mode = (output_mode or "").upper()
    if mode in {"A", "B", "C"}:
        return "html"
    if mode == "D":
        return "docx"
    return None


def build_default_report_path(
    *,
    ticker: str | None,
    output_mode: str | None,
    output_language: str | None,
    analysis_date: str | None,
    report_key: str | None = None,
    peer_tickers: Iterable[str] | None = None,
) -> str | None:
    mode = (output_mode or "").upper()
    extension = default_report_extension(mode)
    if extension is None:
        return None

    key = report_key
    if key is None and mode == "B":
        ordered_tickers: list[str] = []
        for candidate in [ticker, *(peer_tickers or [])]:
            if not isinstance(candidate, str):
                continue
            cleaned = re.sub(r"[^A-Za-z0-9]", "", candidate.upper())
            if cleaned and cleaned not in ordered_tickers:
                ordered_tickers.append(cleaned)
        key = "_".join(ordered_tickers) if ordered_tickers else None
    if key is None:
        key = ticker
    if not isinstance(key, str) or not key:
        return None

    lang = (output_language or "en").upper()
    date_value = analysis_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"output/reports/{key}_{mode}_{lang}_{date_value}.{extension}"


def build_run_paths(
    base_dir: str | Path,
    run_id: str,
    ticker: str,
    data_root: str | Path | None = None,
) -> dict[str, Path]:
    base = Path(base_dir).resolve()
    ticker_upper = ticker.upper()
    output_dir = Path(data_root).expanduser() if data_root is not None else data_dir()
    if not output_dir.is_absolute():
        output_dir = base / output_dir
    output_dir = output_dir.resolve()
    run_root = output_dir / "runs" / run_id
    ticker_root = run_root / ticker_upper
    return {
        "run_root": run_root,
        "run_manifest": run_root / "run-manifest.json",
        "artifact_root": ticker_root,
        "ticker_root": ticker_root,
        "research_plan": ticker_root / "research-plan.json",
        "tier1_raw": ticker_root / "tier1-raw.json",
        "dart_api_raw": ticker_root / "dart-api-raw.json",
        "tier2_raw": ticker_root / "tier2-raw.json",
        "validated_data": ticker_root / "validated-data.json",
        "analysis_result": ticker_root / "analysis-result.json",
        "quality_report": ticker_root / "quality-report.json",
        "reports_dir": output_dir / "reports",
        "snapshot_dir": output_dir / "data" / ticker_upper,
    }


def build_snapshot_paths(
    base_dir: str | Path,
    ticker: str,
    snapshot_id: str,
    data_root: str | Path | None = None,
) -> dict[str, Path]:
    base = Path(base_dir).resolve()
    ticker_upper = ticker.upper()
    output_dir = Path(data_root).expanduser() if data_root is not None else data_dir()
    if not output_dir.is_absolute():
        output_dir = base / output_dir
    output_dir = output_dir.resolve()
    ticker_cache_root = output_dir / "data" / ticker_upper
    snapshot_root = ticker_cache_root / "snapshots" / snapshot_id
    return {
        "ticker_cache_root": ticker_cache_root,
        "latest_pointer": ticker_cache_root / "latest.json",
        "snapshot_root": snapshot_root,
        "tier1_raw": snapshot_root / "tier1-raw.json",
        "dart_api_raw": snapshot_root / "dart-api-raw.json",
        "tier2_raw": snapshot_root / "tier2-raw.json",
        "validated_data": snapshot_root / "validated-data.json",
        "analysis_result": snapshot_root / "analysis-result.json",
        "quality_report": snapshot_root / "quality-report.json",
        "evidence_pack": snapshot_root / "evidence-pack.json",
    }


def relativize_paths(base_dir: str | Path, paths: dict[str, Path]) -> dict[str, str]:
    base = Path(base_dir).resolve()
    relpaths: dict[str, str] = {}
    for key, value in paths.items():
        try:
            relpaths[key] = str(value.resolve().relative_to(base))
        except ValueError:
            relpaths[key] = str(value.resolve())
    return relpaths


def _lower_sources(sources: Iterable[str]) -> list[str]:
    return [str(source).strip().lower() for source in sources if str(source).strip()]


def infer_source_type(
    tag: str | None,
    sources: Iterable[str] | None,
    market: str | None = None,
) -> str | None:
    if tag == "[Unverified]":
        return None
    normalized_market = (market or "").upper()
    if tag in LEGACY_TAG_ALIASES and LEGACY_TAG_ALIASES[tag]:
        return LEGACY_TAG_ALIASES[tag]

    source_text = " | ".join(_lower_sources(sources or []))

    if any(marker in source_text for marker in MACRO_MARKERS):
        return "macro"
    if any(marker in source_text for marker in FILING_MARKERS):
        return "filing"
    if any(marker in source_text for marker in COMPANY_MARKERS):
        return "company_release"
    if any(marker in source_text for marker in ESTIMATE_SOURCE_MARKERS):
        return "estimate"
    if any(marker in source_text for marker in PORTAL_KR_MARKERS):
        return "portal_kr"
    if any(marker in source_text for marker in PORTAL_GLOBAL_MARKERS):
        return "portal_global"
    if normalized_market == "KR":
        return "portal_kr"
    if normalized_market == "US":
        return "portal_global"
    return None


def normalize_metric_entry(metric_name: str, entry: Any, market: str | None = None) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []

    if isinstance(entry, dict):
        normalized = dict(entry)
    else:
        normalized = {"value": entry}
        warnings.append(f"{metric_name}: wrapped non-dict metric entry into canonical object")

    grade = normalized.get("grade")
    if isinstance(grade, str):
        normalized["grade"] = grade.upper()

    sources = normalized.get("sources")
    if not isinstance(sources, list):
        sources = [] if sources in (None, "") else [str(sources)]
        normalized["sources"] = sources

    notes = normalized.get("notes")
    if notes is None and normalized.get("note") is not None:
        normalized["notes"] = normalized.get("note")
        normalized.pop("note", None)

    original_tag = normalized.get("display_tag", normalized.get("tag"))
    approximate = bool(normalized.get("approximate", False))
    if original_tag in ("[≈]", "[Approx]"):
        approximate = True
        warnings.append(f"{metric_name}: converted legacy approximation tag {original_tag}")

    source_type = normalized.get("source_type")
    if normalized.get("grade") != "D" and source_type not in CANONICAL_SOURCE_TYPES:
        inferred = infer_source_type(original_tag, sources, market=market)
        source_type = inferred
        if inferred:
            warnings.append(f"{metric_name}: inferred source_type={inferred}")

    if original_tag == "[Filing]" and source_type == "company_release":
        warnings.append(
            f"{metric_name}: downgraded display tag from [Filing] to [Company] because sources look like issuer releases"
        )

    display_tag = SOURCE_TYPE_TO_DISPLAY_TAG.get(source_type)
    if normalized.get("grade") == "D":
        display_tag = None
        source_type = None

    normalized["source_type"] = source_type
    normalized["source_authority"] = (
        SOURCE_TYPE_TO_AUTHORITY.get(source_type) if source_type else normalized.get("source_authority")
    )
    normalized["display_tag"] = display_tag
    normalized["tag"] = display_tag
    normalized["approximate"] = approximate

    if normalized.get("grade") == "D":
        normalized.setdefault("value", None)
        if normalized.get("value") is not None:
            warnings.append(f"{metric_name}: Grade D metric must have value=null")
        if not normalized.get("exclusion_reason"):
            normalized["exclusion_reason"] = normalized.get("notes") or "Legacy migration marked this metric unverifiable"
            warnings.append(f"{metric_name}: Grade D metric should include exclusion_reason")

    return normalized, warnings


def normalize_metric_mapping(metrics: dict[str, Any], market: str | None = None) -> tuple[dict[str, Any], list[str]]:
    normalized: dict[str, Any] = {}
    warnings: list[str] = []
    for metric_name, entry in metrics.items():
        normalized_entry, entry_warnings = normalize_metric_entry(metric_name, entry, market=market)
        normalized[metric_name] = normalized_entry
        warnings.extend(entry_warnings)
    return normalized, warnings


def extract_numeric_value(value: Any) -> float | None:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):
        for key in ("value", "raw", "amount", "market_cap_raw"):
            if key in value:
                extracted = extract_numeric_value(value.get(key))
                if extracted is not None:
                    return extracted
        return None
    if value is None:
        return None

    text = str(value).strip()
    if not text or text in {"-", "—", "N/A", "n/a", "null", "None"}:
        return None

    cleaned = text.replace(",", "").replace("$", "").replace("KRW", "").replace("USD", "")
    cleaned = cleaned.replace("x", "").replace("X", "").replace("%", "").strip()

    match = re.fullmatch(r"([-+]?\d+(?:\.\d+)?)([KMBT])?", cleaned, flags=re.IGNORECASE)
    if match:
        number = float(match.group(1))
        suffix = (match.group(2) or "").upper()
        if suffix:
            number *= NUMERIC_SUFFIX_MULTIPLIERS[suffix]
        return number

    try:
        return float(cleaned)
    except ValueError:
        return None


def metric_display_tag(entry: Any) -> str | None:
    if isinstance(entry, dict):
        return entry.get("display_tag") or entry.get("tag")
    return None
