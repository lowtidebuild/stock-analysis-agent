"""Critic-side deterministic check for valuation_bridge arithmetic invariants.

The framework (`references/analysis-framework-dashboard.md` §5b) lists five
invariants the analyst must self-check and the Critic must verify:

1. ``sum(anchor.weight) == 1.0`` (within 0.01 / 0.001).
2. ``weighted_fair_value ≈ Σ(value × weight)`` within 0.1.
3. ``implied_view_vs_market`` matches
   ``(weighted_fair_value − current_price) / current_price × 100`` (signed
   percentage with one decimal).
4. ``reconciliation_logic`` ≥ 50 whitespace-delimited tokens.
5. ``decision_anchor`` ∈ {scenarios.base, scenarios.bull, scenarios.bear,
   weighted_fair_value}.

Severity (Critic spec):

* arithmetic violation (1, 2, 3) → ``BLOCKER`` (patchable)
* word-count violation (4) → ``MAJOR``
* ``decision_anchor`` enum violation (5) → ``MAJOR``

When ``valuation_bridge`` is absent (older snapshots / Mode A/B/D), the check
returns ``status="SKIP"`` so backward compatibility is preserved.
"""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from tools.quality_report import build_valuation_bridge_consistency_item


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = REPO_ROOT / "tests" / "fixtures" / "googl_with_valuation_bridge.json"


def _load_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


class ValuationBridgeConsistencyCheckTests(unittest.TestCase):
    """The Critic check enforces the 5 framework invariants."""

    def test_pass_case_valid_fixture(self) -> None:
        analysis = _load_fixture()

        item = build_valuation_bridge_consistency_item(analysis)

        self.assertEqual(item["status"], "PASS", item)
        # Severity must be NONE for a passing item; quality_report annotator
        # promotes that to delivery_impact = "none".
        self.assertEqual(item.get("severity", "NONE"), "NONE")
        self.assertNotIn("errors", item)

    def test_fail_blocker_when_weighted_fair_value_arithmetic_off(self) -> None:
        analysis = _load_fixture()
        # Original fixture: weighted_fair_value = 346.84.
        # Push it 5.0 off so invariant #2 (weighted FV = Σ value*weight)
        # fails outside the 0.1 tolerance and invariant #3 (implied view
        # formula) likely also fails.
        analysis["valuation_bridge"]["weighted_fair_value"] = 351.84

        item = build_valuation_bridge_consistency_item(analysis)

        self.assertEqual(item["status"], "FAIL")
        self.assertEqual(item["severity"], "BLOCKER")
        self.assertEqual(item["blocker_action"], "patchable")
        # The error message should call out the weighted FV mismatch.
        self.assertTrue(
            any("weighted_fair_value" in err for err in item["errors"]),
            f"expected weighted_fair_value error, got {item['errors']!r}",
        )

    def test_fail_blocker_when_weights_do_not_sum_to_one(self) -> None:
        analysis = _load_fixture()
        # Push one weight off so the sum != 1.0 outside tolerance.
        analysis["valuation_bridge"]["anchors"][0]["weight"] = 0.40

        item = build_valuation_bridge_consistency_item(analysis)

        self.assertEqual(item["status"], "FAIL")
        self.assertEqual(item["severity"], "BLOCKER")
        self.assertTrue(
            any("weight" in err for err in item["errors"]),
            f"expected weight-sum error, got {item['errors']!r}",
        )

    def test_fail_major_when_reconciliation_logic_too_short(self) -> None:
        analysis = _load_fixture()
        analysis["valuation_bridge"]["reconciliation_logic"] = (
            "DCF는 보수적이고 Comp/Analyst는 강세이며 가중평균은 시장 대비 -10.7%다."
        )  # ~12 tokens, well under 50

        item = build_valuation_bridge_consistency_item(analysis)

        self.assertEqual(item["status"], "FAIL")
        # No arithmetic error → severity is MAJOR, not BLOCKER.
        self.assertEqual(item["severity"], "MAJOR")
        self.assertTrue(
            any("reconciliation_logic" in err for err in item["errors"]),
            f"expected reconciliation_logic length error, got {item['errors']!r}",
        )

    def test_fail_major_when_decision_anchor_unknown_enum(self) -> None:
        analysis = _load_fixture()
        analysis["valuation_bridge"]["decision_anchor"] = "scenarios.moonshot"

        item = build_valuation_bridge_consistency_item(analysis)

        self.assertEqual(item["status"], "FAIL")
        self.assertEqual(item["severity"], "MAJOR")
        self.assertTrue(
            any("decision_anchor" in err for err in item["errors"]),
            f"expected decision_anchor enum error, got {item['errors']!r}",
        )

    def test_blocker_takes_priority_over_major_severity(self) -> None:
        """When both arithmetic and narrative invariants fail, BLOCKER wins."""
        analysis = _load_fixture()
        analysis["valuation_bridge"]["weighted_fair_value"] = 351.84  # arithmetic
        analysis["valuation_bridge"]["decision_anchor"] = "scenarios.moonshot"  # major

        item = build_valuation_bridge_consistency_item(analysis)

        self.assertEqual(item["status"], "FAIL")
        self.assertEqual(item["severity"], "BLOCKER")

    def test_skip_when_valuation_bridge_absent(self) -> None:
        """Older snapshots / Mode A/B/D: the field is optional; graceful skip."""
        analysis = _load_fixture()
        del analysis["valuation_bridge"]

        item = build_valuation_bridge_consistency_item(analysis)

        self.assertEqual(item["status"], "SKIP")
        self.assertNotIn("errors", item)
        # SKIP must not raise severity — keeps delivery_gate clean.
        self.assertEqual(item.get("severity", "NONE"), "NONE")

    def test_implied_view_sign_mismatch_is_blocker(self) -> None:
        """If implied_view_vs_market sign disagrees with formula, BLOCKER."""
        analysis = _load_fixture()
        # Original implied_view_vs_market is "-10.7%" (correct).
        # Flip the sign to "+10.7%" — sign disagrees with formula.
        analysis["valuation_bridge"]["implied_view_vs_market"] = "+10.7%"

        item = build_valuation_bridge_consistency_item(analysis)

        self.assertEqual(item["status"], "FAIL")
        self.assertEqual(item["severity"], "BLOCKER")
        self.assertTrue(
            any("implied_view" in err for err in item["errors"]),
            f"expected implied_view error, got {item['errors']!r}",
        )


class ValuationBridgeIntegrationTests(unittest.TestCase):
    """The check must be wired into the canonical quality-report contract."""

    def test_quality_report_includes_valuation_bridge_consistency_item(self) -> None:
        from tools.quality_report import build_quality_report

        analysis = _load_fixture()
        # Minimal supporting artifacts so build_quality_report succeeds.
        run_context = {
            "run_id": "run-vb-1",
            "artifact_root": "output/runs/run-vb-1/GOOGL",
            "ticker": "GOOGL",
        }
        analysis = copy.deepcopy(analysis)
        analysis["run_context"] = run_context

        report = build_quality_report(
            {"ticker": "GOOGL", "market": "US", "output_mode": "C", "run_context": run_context},
            {
                "ticker": "GOOGL",
                "market": "US",
                "validated_metrics": {},
                "exclusions": [],
                "run_context": run_context,
            },
            analysis,
        )

        self.assertIn("valuation_bridge_consistency", report["items"])
        # Valid fixture → PASS at the item level.
        self.assertEqual(report["items"]["valuation_bridge_consistency"]["status"], "PASS")


if __name__ == "__main__":
    unittest.main()
