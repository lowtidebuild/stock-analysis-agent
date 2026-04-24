"""Tests for keeping critic review scoped to narrative judgment."""

from __future__ import annotations

import unittest

from tools.artifact_validation import validate_artifact_data


CORE_ITEMS = {
    "financial_consistency": {"status": "PASS"},
    "price_and_date": {"status": "PASS"},
    "blank_over_wrong": {"status": "PASS"},
    "contract_validation": {"status": "PASS"},
    "semantic_consistency": {"status": "PASS"},
    "verdict_policy": {"status": "PASS"},
    "cross_artifact_consistency": {"status": "PASS"},
}


def _quality_report(critic_item: str) -> dict:
    return {
        "ticker": "AAPL",
        "output_mode": "D",
        "check_timestamp": "2026-04-24T00:00:00Z",
        "overall_result": "PASS",
        "core_overall_result": "PASS",
        "run_context": {
            "run_id": "run-1",
            "artifact_root": "output/runs/run-1/AAPL",
            "ticker": "AAPL",
        },
        "items": CORE_ITEMS,
        "delivery_gate": {
            "result": "PASS",
            "ready_for_delivery": True,
            "blocking_items": [],
            "non_blocking_items": [],
            "historical_only_items": [],
            "critic_overall": "PASS",
            "critic_delivery_impact": "none",
        },
        "critic_review": {
            "reviewer": "critic-agent",
            "review_timestamp": "2026-04-24T00:01:00Z",
            "overall": "PASS",
            "items": [
                {
                    "item": critic_item,
                    "status": "PASS",
                    "section": "Section 4",
                    "notes": "Narrative judgment passed.",
                }
            ],
        },
    }


class CriticReviewContractTests(unittest.TestCase):
    def test_allows_narrative_critic_item(self):
        self.assertEqual(validate_artifact_data("quality-report", _quality_report("generic_test")), [])

    def test_rejects_deterministic_critic_item(self):
        errors = validate_artifact_data("quality-report", _quality_report("scenario_consistency"))

        self.assertTrue(any("deterministic" in error for error in errors))
        self.assertTrue(any("critic_review" in error for error in errors))

    def test_rejects_unknown_critic_item(self):
        errors = validate_artifact_data("quality-report", _quality_report("spreadsheet_spellcheck"))

        self.assertTrue(any("not an allowed narrative critic item" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
