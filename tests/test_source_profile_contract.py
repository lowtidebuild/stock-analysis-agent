"""Tests for requested/effective source profile contracts."""

from __future__ import annotations

import unittest

from tools.artifact_validation import validate_artifact_data, validate_cross_artifact_consistency
from tools.source_profile import source_confidence_label


def _run_context() -> dict:
    return {
        "run_id": "run-1",
        "artifact_root": "output/runs/run-1/AAPL",
        "ticker": "AAPL",
    }


def _validated(**overrides) -> dict:
    payload = {
        "ticker": "AAPL",
        "market": "US",
        "data_mode": "enhanced",
        "requested_mode": "enhanced",
        "effective_mode": "standard",
        "source_profile": "yfinance_fallback",
        "source_tier": "portal_structured",
        "confidence_cap": "C",
        "validation_timestamp": "2026-04-24T00:00:00Z",
        "overall_grade": "C",
        "run_context": _run_context(),
        "validated_metrics": {},
        "grade_summary": {"A": 0, "B": 0, "C": 1, "D": 0},
        "exclusions": [],
    }
    payload.update(overrides)
    return payload


def _analysis(**overrides) -> dict:
    payload = {
        "ticker": "AAPL",
        "market": "US",
        "data_mode": "enhanced",
        "requested_mode": "enhanced",
        "effective_mode": "standard",
        "source_profile": "yfinance_fallback",
        "source_tier": "portal_structured",
        "confidence_cap": "C",
        "output_mode": "A",
        "analysis_date": "2026-04-24",
        "run_context": _run_context(),
        "key_metrics": {},
        "scenarios": {
            "bull": {"target": 130, "probability": 0.25, "key_assumption": "Upside"},
            "base": {"target": 110, "probability": 0.5, "key_assumption": "Base"},
            "bear": {"target": 80, "probability": 0.25, "key_assumption": "Downside"},
        },
        "rr_score": 5,
        "verdict": "overweight",
    }
    payload.update(overrides)
    return payload


class SourceProfileContractTests(unittest.TestCase):
    def test_yfinance_fallback_source_profile_is_valid(self):
        errors = validate_artifact_data("validated-data", _validated())

        self.assertEqual(errors, [])

    def test_yfinance_fallback_requires_standard_effective_mode(self):
        errors = validate_artifact_data("validated-data", _validated(effective_mode="enhanced"))

        self.assertTrue(any("effective_mode" in error and "yfinance_fallback" in error for error in errors))

    def test_confidence_cap_limits_overall_grade(self):
        errors = validate_artifact_data("validated-data", _validated(overall_grade="B", confidence_cap="C"))

        self.assertTrue(any("confidence_cap" in error for error in errors))

    def test_source_profile_must_match_between_validated_and_analysis(self):
        errors = validate_cross_artifact_consistency(
            {"ticker": "AAPL", "market": "US", "data_mode": "enhanced", "output_mode": "A", "analysis_date": "2026-04-24"},
            _validated(),
            _analysis(source_profile="financial_datasets"),
        )

        self.assertTrue(any("source_profile" in error for error in errors))

    def test_source_confidence_label_includes_profile_and_cap(self):
        label = source_confidence_label(_analysis())

        self.assertIn("yfinance fallback", label)
        self.assertIn("effective standard", label)
        self.assertIn("cap C", label)


if __name__ == "__main__":
    unittest.main()
