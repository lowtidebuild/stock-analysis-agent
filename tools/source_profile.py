"""Source profile contract helpers.

These fields separate the user's requested collection mode from the source
tier actually achieved by the run. That prevents a yfinance-only fallback from
being displayed as if it had full enhanced/filing-grade coverage.
"""

from __future__ import annotations

from typing import Any

DATA_MODES = {"enhanced", "standard"}
SOURCE_PROFILES = {
    "financial_datasets",
    "sec_or_dart_primary",
    "yfinance_fallback",
    "web_only",
    "mixed",
}
SOURCE_TIERS = {
    "filing_primary",
    "api_structured",
    "portal_structured",
    "search_snippet",
    "user_supplied",
}
CONFIDENCE_CAPS = {"A", "B", "C", "D"}
GRADE_RANK = {"A": 4, "B": 3, "C": 2, "D": 1}

SOURCE_PROFILE_LABELS = {
    "financial_datasets": "Financial Datasets",
    "sec_or_dart_primary": "SEC/DART primary",
    "yfinance_fallback": "yfinance fallback",
    "web_only": "web only",
    "mixed": "mixed sources",
}
SOURCE_TIER_LABELS = {
    "filing_primary": "filing primary",
    "api_structured": "structured API",
    "portal_structured": "portal structured",
    "search_snippet": "search snippet",
    "user_supplied": "user supplied",
}


def source_profile_label(payload: dict[str, Any]) -> str:
    profile = payload.get("source_profile")
    if isinstance(profile, str) and profile in SOURCE_PROFILE_LABELS:
        return SOURCE_PROFILE_LABELS[profile]
    data_source = payload.get("data_source")
    if isinstance(data_source, str) and data_source:
        return data_source.replace("_", " ")
    data_mode = payload.get("effective_mode") or payload.get("data_mode")
    if data_mode == "enhanced":
        return "enhanced source"
    if data_mode == "standard":
        return "standard source"
    return "source profile unavailable"


def effective_mode_label(payload: dict[str, Any]) -> str:
    effective_mode = payload.get("effective_mode") or payload.get("data_mode")
    if effective_mode == "enhanced":
        return "enhanced"
    if effective_mode == "standard":
        return "standard"
    return "unknown"


def source_confidence_label(payload: dict[str, Any], *, overall_grade: Any = None) -> str:
    parts = [source_profile_label(payload)]
    effective_mode = effective_mode_label(payload)
    if effective_mode != "unknown":
        parts.append(f"effective {effective_mode}")

    grade = overall_grade or payload.get("overall_grade") or payload.get("quality_grade")
    if isinstance(grade, str) and grade in CONFIDENCE_CAPS:
        parts.append(f"grade {grade}")

    cap = payload.get("confidence_cap")
    if isinstance(cap, str) and cap in CONFIDENCE_CAPS:
        parts.append(f"cap {cap}")

    return " | ".join(parts)
