"""Tests for severity-driven delivery gate policy."""

from __future__ import annotations

import copy
import unittest

from tools.artifact_validation import validate_artifact_data
from tools.quality_report import annotate_delivery_impacts, build_delivery_gate


CORE_ITEMS = {
    "financial_consistency": {"status": "PASS"},
    "price_and_date": {"status": "PASS"},
    "blank_over_wrong": {"status": "PASS"},
    "contract_validation": {"status": "PASS"},
    "semantic_consistency": {"status": "PASS"},
    "verdict_policy": {"status": "PASS"},
    "cross_artifact_consistency": {"status": "PASS"},
}


def _quality_report(items):
    return {
        "ticker": "AAPL",
        "output_mode": "C",
        "check_timestamp": "2026-04-24T00:00:00Z",
        "overall_result": "FAIL" if any(item.get("status") == "FAIL" for item in items.values()) else "PASS",
        "run_context": {
            "run_id": "20260424T000000Z_AAPL_C",
            "artifact_root": "output/runs/20260424T000000Z_AAPL_C/AAPL",
            "ticker": "AAPL",
        },
        "items": items,
        "delivery_gate": build_delivery_gate(items),
        "auto_fixes_applied": [],
        "inline_flags_added": [],
        "generated_by": "quality-report-builder",
    }


class DeliverySeverityTests(unittest.TestCase):
    def test_legacy_flag_stays_historical_and_deliverable(self):
        items = annotate_delivery_impacts({"legacy_migration": {"status": "PASS_WITH_FLAGS"}})

        gate = build_delivery_gate(items)

        self.assertEqual(items["legacy_migration"]["severity"], "MINOR")
        self.assertEqual(items["legacy_migration"]["delivery_impact"], "historical_flag_only")
        self.assertEqual(gate["result"], "PASS")
        self.assertEqual(gate["max_severity"], "MINOR")

    def test_major_failure_is_non_blocking_when_declared(self):
        items = annotate_delivery_impacts(
            {
                "contract_validation": {
                    "status": "FAIL",
                    "severity": "MAJOR",
                    "errors": ["Non-blocking report polish issue"],
                }
            }
        )

        gate = build_delivery_gate(items)

        self.assertEqual(items["contract_validation"]["delivery_impact"], "non_blocking_flag")
        self.assertEqual(gate["result"], "PASS")
        self.assertTrue(gate["ready_for_delivery"])
        self.assertEqual(gate["max_severity"], "MAJOR")
        self.assertIn("contract_validation", gate["non_blocking_items"])

    def test_blocker_blocks_even_when_status_is_flagged(self):
        items = annotate_delivery_impacts(
            {
                "rendered_output": {
                    "status": "PASS_WITH_FLAGS",
                    "severity": "BLOCKER",
                    "errors": ["Rendered report exposes excluded Grade D value"],
                }
            }
        )

        gate = build_delivery_gate(items)

        self.assertEqual(items["rendered_output"]["delivery_impact"], "delivery_blocking_flag")
        self.assertEqual(gate["result"], "BLOCKED")
        self.assertFalse(gate["ready_for_delivery"])

    def test_critic_major_failure_is_deliverable_with_flags(self):
        critic_review = {
            "overall": "FAIL",
            "items": [
                {
                    "item": "completeness",
                    "status": "FAIL",
                    "severity": "MAJOR",
                    "problem": "QoE section needs more detail",
                    "fix": "Add FCF conversion commentary",
                }
            ],
        }

        gate = build_delivery_gate(CORE_ITEMS, critic_review)

        self.assertEqual(gate["result"], "PASS")
        self.assertEqual(gate["critic_severity"], "MAJOR")
        self.assertEqual(gate["critic_delivery_impact"], "non_blocking_flag")
        self.assertIn("critic_review", gate["non_blocking_items"])

    def test_validator_rejects_gate_that_ignores_major_severity(self):
        items = copy.deepcopy(CORE_ITEMS)
        items["contract_validation"] = {
            "status": "FAIL",
            "severity": "MAJOR",
            "delivery_impact": "non_blocking_flag",
            "errors": ["Fixture major issue"],
        }
        report = _quality_report(items)
        self.assertEqual(validate_artifact_data("quality-report", report), [])

        report["delivery_gate"]["result"] = "BLOCKED"
        report["delivery_gate"]["ready_for_delivery"] = False

        errors = validate_artifact_data("quality-report", report)

        self.assertTrue(any("$.delivery_gate.result" in error for error in errors))
        self.assertTrue(any("$.delivery_gate.ready_for_delivery" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
