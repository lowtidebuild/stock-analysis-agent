"""Tests for deterministic scenario consistency checks in quality reports."""

from __future__ import annotations

import unittest

from tools.quality_report import build_quality_report, build_scenario_consistency_item


def _analysis() -> dict:
    return {
        "ticker": "AAPL",
        "market": "US",
        "data_mode": "standard",
        "output_mode": "C",
        "analysis_date": "2026-04-24",
        "price_at_analysis": 100,
        "run_context": {
            "run_id": "run-1",
            "artifact_root": "output/runs/run-1/AAPL",
            "ticker": "AAPL",
        },
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
            "quarterly_financials": [{"period": "Q1"}],
        },
    }


class ScenarioConsistencyQualityReportTests(unittest.TestCase):
    def test_scenario_consistency_passes_valid_probabilities_and_targets(self):
        item = build_scenario_consistency_item(_analysis())

        self.assertEqual(item["status"], "PASS")
        self.assertEqual(item["probability_sum"], 1.0)
        self.assertEqual(item["targets"]["bull"], 130)

    def test_scenario_consistency_fails_probability_sum_and_base_priority(self):
        analysis = _analysis()
        analysis["scenarios"]["bull"]["probability"] = 0.5
        analysis["scenarios"]["base"]["probability"] = 0.3
        analysis["scenarios"]["bear"]["probability"] = 0.3

        item = build_scenario_consistency_item(analysis)

        self.assertEqual(item["status"], "FAIL")
        self.assertTrue(any("probabilities must sum" in error for error in item["errors"]))
        self.assertTrue(any("base probability" in error for error in item["errors"]))

    def test_scenario_consistency_fails_target_ordering(self):
        analysis = _analysis()
        analysis["scenarios"]["bull"]["target"] = 90

        item = build_scenario_consistency_item(analysis)

        self.assertEqual(item["status"], "FAIL")
        self.assertTrue(any("bull.target" in error for error in item["errors"]))

    def test_quality_report_includes_scenario_consistency_item(self):
        report = build_quality_report(
            {"ticker": "AAPL", "market": "US", "output_mode": "C", "run_context": _analysis()["run_context"]},
            {"ticker": "AAPL", "market": "US", "validated_metrics": {}, "exclusions": []},
            _analysis(),
        )

        self.assertIn("scenario_consistency", report["items"])
        self.assertEqual(report["items"]["scenario_consistency"]["status"], "PASS")


if __name__ == "__main__":
    unittest.main()
