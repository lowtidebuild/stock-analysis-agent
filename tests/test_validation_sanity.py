from __future__ import annotations

import json

from tools.artifact_validation import (
    build_validated_data_sanity_flags,
    check_growth_multiple_correlation,
    check_margin_invariant,
    check_multiple_ranges,
    validate_artifact_file,
)


def _run_context() -> dict:
    return {
        "run_id": "run-1",
        "artifact_root": "output/runs/run-1/AAPL",
        "ticker": "AAPL",
    }


def test_margin_invariant_flags_gross_below_ebitda():
    """Gross margin must be >= EBITDA margin >= Net margin."""
    metrics = {"gross_margin_pct": 30, "ebitda_margin_pct": 35, "net_margin_pct": 10}

    flags = check_margin_invariant(metrics)

    assert any(flag["rule"] == "margin_invariant" and flag["severity"] == "MAJOR" for flag in flags)


def test_margin_invariant_passes_normal_case():
    metrics = {"gross_margin_pct": 60, "ebitda_margin_pct": 25, "net_margin_pct": 15}

    flags = check_margin_invariant(metrics)

    assert flags == []


def test_multiple_range_flags_outside_hard_range():
    metrics = {"ev_revenue": 45, "ev_ebitda": 12, "p_e": 25}

    flags = check_multiple_ranges(metrics)

    assert any(flag["rule"] == "multiple_range" and "ev_revenue" in flag["detail"] for flag in flags)


def test_growth_multiple_correlation_flags_high_pe_low_growth():
    metrics = {"p_e": 95, "revenue_growth_pct": 4}

    flags = check_growth_multiple_correlation(metrics)

    assert any(flag["rule"] == "growth_multiple_mismatch" for flag in flags)


def test_validated_data_sanity_flags_use_metric_aliases():
    data = {
        "validated_metrics": {
            "gross_margin": {"value": 30},
            "ebitda_margin": {"value": 35},
            "net_margin": {"value": 10},
            "pe_ratio": {"value": 95},
            "revenue_growth_yoy": {"value": 4},
        }
    }

    flags = build_validated_data_sanity_flags(data)
    rules = {flag["rule"] for flag in flags}

    assert "margin_invariant" in rules
    assert "growth_multiple_mismatch" in rules


def test_validate_artifact_file_surfaces_sanity_flags(tmp_path):
    payload = {
        "ticker": "AAPL",
        "market": "US",
        "data_mode": "enhanced",
        "requested_mode": "enhanced",
        "effective_mode": "standard",
        "source_profile": "yfinance_fallback",
        "source_tier": "portal_structured",
        "confidence_cap": "C",
        "validation_timestamp": "2026-05-06T00:00:00Z",
        "overall_grade": "C",
        "run_context": _run_context(),
        "validated_metrics": {
            "gross_margin": {"value": 30, "grade": "C", "sources": ["Yahoo Finance"]},
            "ebitda_margin": {"value": 35, "grade": "C", "sources": ["Yahoo Finance"]},
            "net_margin": {"value": 10, "grade": "C", "sources": ["Yahoo Finance"]},
        },
        "grade_summary": {"A": 0, "B": 0, "C": 3, "D": 0},
        "exclusions": [],
    }
    artifact = tmp_path / "validated-data.json"
    artifact.write_text(json.dumps(payload), encoding="utf-8")

    result = validate_artifact_file(artifact, "validated-data")

    assert any(flag["rule"] == "margin_invariant" for flag in result["sanity_flags"])
