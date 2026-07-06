from __future__ import annotations

from tools.artifact_validation import validate_artifact_data
from tools.quality_report import build_numeric_sanity_item, build_quality_report


def _run_context() -> dict:
    return {
        "run_id": "run-1",
        "artifact_root": "output/runs/run-1/AAPL",
        "ticker": "AAPL",
    }


def _analysis() -> dict:
    return {
        "ticker": "AAPL",
        "market": "US",
        "data_mode": "standard",
        "output_mode": "C",
        "analysis_date": "2026-06-22",
        "price_at_analysis": 100,
        "run_context": _run_context(),
        "key_metrics": {},
        "scenarios": {
            "bull": {"target": 130, "probability": 0.25, "key_assumption": "Upside"},
            "base": {"target": 110, "probability": 0.5, "key_assumption": "Base"},
            "bear": {"target": 80, "probability": 0.25, "key_assumption": "Downside"},
        },
        "rr_score": 5,
        "verdict": "overweight",
        "sections": {
            "variant_view_q1": "specific",
            "variant_view_q2": "specific",
            "variant_view_q3": "specific",
            "precision_risks": [{"risk": "x"}, {"risk": "y"}, {"risk": "z"}],
            "valuation_metrics": [{"metric": "P/E"}],
            "peer_comparison": [{"ticker": "MSFT"}],
            "portfolio_strategy": "strategy",
            "what_would_make_me_wrong": ["condition"],
            "dcf_analysis": {"base": {}, "bull": {}, "bear": {}, "methodology": "dcf"},
            "analyst_coverage": {"consensus": "buy"},
            "qoe_summary": "quality",
        },
    }


def test_numeric_sanity_item_delivers_major_validated_data_flags_with_flag() -> None:
    validated = {
        "ticker": "AAPL",
        "market": "US",
        "validated_metrics": {},
        "exclusions": [],
        "_validation": {
            "sanity_flags": [
                {
                    "rule": "margin_invariant",
                    "severity": "MAJOR",
                    "detail": "gross_margin_pct=30 is below ebitda_margin_pct=35",
                }
            ]
        },
    }

    item = build_numeric_sanity_item(validated)

    assert item["status"] == "PASS_WITH_FLAGS"
    assert item["severity"] == "MAJOR"
    assert item["delivery_impact"] == "non_blocking_flag"
    assert item["blocker_action"] == "none"
    assert item["flag_count"] == 1


def test_numeric_sanity_item_still_blocks_blocker_validated_data_flags() -> None:
    validated = {
        "ticker": "AAPL",
        "market": "US",
        "validated_metrics": {},
        "exclusions": [],
        "_validation": {
            "sanity_flags": [
                {
                    "rule": "impossible_value",
                    "severity": "BLOCKER",
                    "detail": "negative market cap",
                }
            ]
        },
    }

    item = build_numeric_sanity_item(validated)

    assert item["status"] == "FAIL"
    assert item["severity"] == "BLOCKER"
    assert item["delivery_impact"] == "delivery_blocking_flag"
    assert item["blocker_action"] == "terminal"


def test_numeric_sanity_item_warns_on_minor_validated_data_flags() -> None:
    validated = {
        "ticker": "AAPL",
        "market": "US",
        "validated_metrics": {},
        "exclusions": [],
        "_validation": {
            "sanity_flags": [
                {
                    "rule": "multiple_range",
                    "severity": "MINOR",
                    "detail": "ev_revenue=45x outside hard range",
                }
            ]
        },
    }

    item = build_numeric_sanity_item(validated)

    assert item["status"] == "PASS_WITH_FLAGS"
    assert item["severity"] == "MINOR"
    assert item["delivery_impact"] == "non_blocking_flag"


def test_quality_report_delivers_with_flag_on_major_numeric_sanity_flag() -> None:
    validated = {
        "ticker": "AAPL",
        "market": "US",
        "validated_metrics": {},
        "exclusions": [],
        "run_context": _run_context(),
        "_validation": {
            "sanity_flags": [
                {
                    "rule": "margin_invariant",
                    "severity": "MAJOR",
                    "detail": "gross_margin_pct=30 is below ebitda_margin_pct=35",
                }
            ]
        },
    }

    report = build_quality_report(
        {"ticker": "AAPL", "market": "US", "output_mode": "C", "run_context": _run_context()},
        validated,
        _analysis(),
    )

    assert report["items"]["numeric_sanity"]["status"] == "PASS_WITH_FLAGS"
    assert report["items"]["numeric_sanity"]["severity"] == "MAJOR"
    assert "numeric_sanity" in report["delivery_gate"]["non_blocking_items"]
    assert "numeric_sanity" not in report["delivery_gate"]["blocking_items"]
    assert "numeric_sanity" not in report["delivery_gate"]["terminal_blocking_items"]
    assert validate_artifact_data("quality-report", report) == []
