"""Tests for mode-specific analysis-result completeness checks."""

from __future__ import annotations

import unittest

from tools.artifact_validation import validate_analysis_completeness


def _mode_c_payload():
    return {
        "output_mode": "C",
        "sections": {
            "variant_view_q1": "Variant view one includes specific evidence and a clear investor dispute.",
            "variant_view_q2": "Variant view two names the catalyst and explains why it matters.",
            "variant_view_q3": "Variant view three defines the downside pressure and evidence threshold.",
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
            "portfolio_strategy": "Position sizing follows valuation spread, catalyst timing, and downside risk.",
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

    def test_mode_c_rejects_short_required_text_section(self):
        payload = _mode_c_payload()
        payload["sections"]["variant_view_q1"] = "Too short"

        errors = validate_analysis_completeness(payload)

        self.assertTrue(any("at least 8 words" in error for error in errors))

    def test_mode_d_requires_q4_q5_and_qoe(self):
        payload = {
            "output_mode": "D",
            "sections": {
                "executive_summary": "Summary explains the verdict, source confidence, and main risk.",
                "business_overview": "Business overview describes segments, demand drivers, and competitive position.",
                "financial_performance": "Financial performance covers revenue, margin, cash flow, and balance sheet.",
                "valuation_analysis": "Valuation analysis links multiples, cash flow, and scenario targets.",
                "variant_view_q1": "Variant question one describes a specific investor disagreement clearly.",
                "variant_view_q2": "Variant question two identifies the catalyst and evidence threshold.",
                "variant_view_q3": "Variant question three explains the downside mechanism and trigger.",
                "precision_risks": [{"risk": "a"}, {"risk": "b"}, {"risk": "c"}],
                "investment_scenarios": "Investment scenarios separate bull, base, and bear drivers clearly.",
                "peer_comparison": "Peer comparison explains relative valuation, growth, and margin context.",
                "management_governance": "Management governance reviews incentives, capital allocation, and execution risk.",
                "what_would_make_me_wrong": ["condition"],
                "appendix_data_sources": "Appendix lists data sources, grades, dates, and exclusions clearly.",
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
                "executive_summary": "Summary explains the verdict, source confidence, and main risk.",
                "business_overview": "Business overview describes segments, demand drivers, and competitive position.",
                "financial_performance": "Financial performance covers revenue, margin, cash flow, and balance sheet.",
                "valuation_analysis": "Valuation analysis links multiples, cash flow, and scenario targets.",
                "variant_view_q1": "Variant question one describes a specific investor disagreement clearly.",
                "variant_view_q2": "Variant question two identifies the catalyst and evidence threshold.",
                "variant_view_q3": "Variant question three explains the downside mechanism and trigger.",
                "variant_view_q4": "Variant question four tests a consensus assumption with evidence.",
                "variant_view_q5": "Variant question five states what would change the thesis.",
                "precision_risks": [{"risk": "a"}, {"risk": "b"}, {"risk": "c"}],
                "investment_scenarios": "Investment scenarios separate bull, base, and bear drivers clearly.",
                "peer_comparison": "Peer comparison explains relative valuation, growth, and margin context.",
                "management_governance": "Management governance reviews incentives, capital allocation, and execution risk.",
                "quality_of_earnings": "QoE summary only",
                "what_would_make_me_wrong": ["condition"],
                "appendix_data_sources": "Appendix lists data sources, grades, dates, and exclusions clearly.",
            },
        }

        errors = validate_analysis_completeness(payload)

        self.assertTrue(any("requires QoE object" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
