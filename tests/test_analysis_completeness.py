"""Tests for mode-specific analysis-result completeness checks."""

from __future__ import annotations

import unittest

from tools.artifact_validation import validate_analysis_completeness


def _mode_c_payload():
    return {
        "output_mode": "C",
        "sections": {
            "variant_view_q1": "q1",
            "variant_view_q2": "q2",
            "variant_view_q3": "q3",
            "precision_risks": [{"risk": "a"}, {"risk": "b"}, {"risk": "c"}],
            "valuation_metrics": [{"metric": "P/E"}],
            "dcf_analysis": {
                "base": {"fair_value": 100},
                "bull": {"fair_value": 120},
                "bear": {"fair_value": 80},
                "methodology": "DCF methodology",
            },
            "macro_context": {"narrative": "macro"},
            "peer_comparison": [{"ticker": "ABC"}],
            "analyst_coverage": {"consensus": "Neutral"},
            "qoe_summary": {"narrative": "quality"},
            "portfolio_strategy": "strategy",
            "what_would_make_me_wrong": ["condition"],
        },
    }


class AnalysisCompletenessTests(unittest.TestCase):
    def test_mode_c_complete_payload_passes(self):
        self.assertEqual(validate_analysis_completeness(_mode_c_payload()), [])

    def test_mode_c_missing_dcf_is_rejected(self):
        payload = _mode_c_payload()
        payload["sections"].pop("dcf_analysis")

        errors = validate_analysis_completeness(payload)

        self.assertTrue(any("dcf_analysis" in error for error in errors))

    def test_mode_c_rejects_non_structured_dcf(self):
        payload = _mode_c_payload()
        payload["sections"]["dcf_analysis"] = "DCF summary only"

        errors = validate_analysis_completeness(payload)

        self.assertTrue(any("requires DCF object" in error for error in errors))

    def test_mode_c_requires_three_precision_risks(self):
        payload = _mode_c_payload()
        payload["sections"]["precision_risks"] = [{"risk": "a"}]

        errors = validate_analysis_completeness(payload)

        self.assertTrue(any("at least 3 risks" in error for error in errors))

    def test_mode_d_requires_q4_q5_and_qoe(self):
        payload = {
            "output_mode": "D",
            "sections": {
                "executive_summary": "summary",
                "business_overview": "business",
                "financial_performance": "financial",
                "valuation_analysis": "valuation",
                "variant_view_q1": "q1",
                "variant_view_q2": "q2",
                "variant_view_q3": "q3",
                "precision_risks": [{"risk": "a"}, {"risk": "b"}, {"risk": "c"}],
                "investment_scenarios": "scenarios",
                "peer_comparison": "peers",
                "management_governance": "governance",
                "what_would_make_me_wrong": ["condition"],
                "appendix_data_sources": "sources",
            },
        }

        errors = validate_analysis_completeness(payload)

        self.assertTrue(any("variant_view_q4" in error for error in errors))
        self.assertTrue(any("variant_view_q5" in error for error in errors))
        self.assertTrue(any("quality_of_earnings" in error for error in errors))

    def test_mode_d_rejects_unstructured_qoe(self):
        payload = {
            "output_mode": "D",
            "sections": {
                "executive_summary": "summary",
                "business_overview": "business",
                "financial_performance": "financial",
                "valuation_analysis": "valuation",
                "variant_view_q1": "q1",
                "variant_view_q2": "q2",
                "variant_view_q3": "q3",
                "variant_view_q4": "q4",
                "variant_view_q5": "q5",
                "precision_risks": [{"risk": "a"}, {"risk": "b"}, {"risk": "c"}],
                "investment_scenarios": "scenarios",
                "peer_comparison": "peers",
                "management_governance": "governance",
                "quality_of_earnings": "QoE summary only",
                "what_would_make_me_wrong": ["condition"],
                "appendix_data_sources": "sources",
            },
        }

        errors = validate_analysis_completeness(payload)

        self.assertTrue(any("requires QoE object" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
