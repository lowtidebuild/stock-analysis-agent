"""Phase A — Mode C Valuation Bridge widget contract tests.

These tests verify the contract pieces (spec, template, agent instructions,
fixture, and arithmetic) that together make the new ``valuation_bridge``
field renderable on the Mode C dashboard. Per ADR 0001 the user-facing
HTML for Mode C is populated manually from
``.claude/skills/dashboard-generator/references/html-template.md``; the
template is therefore the canonical contract surface.

Scope:

1. Framework spec mentions ``valuation_bridge``.
2. HTML template includes the ``{VALUATION_BRIDGE_SECTION}`` placeholder.
3. Analyst AGENT.md instructs Mode C to produce the field.
4. The fixture parses and carries the full 4-anchor schema.
5. Weighted average is arithmetically consistent with the anchors.
6. ``implied_view_vs_market`` matches the formula
   ``(weighted_fair_value - current_price) / current_price * 100``.
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = REPO_ROOT / "tests" / "fixtures" / "googl_with_valuation_bridge.json"
FRAMEWORK_PATH = REPO_ROOT / "references" / "analysis-framework-dashboard.md"
TEMPLATE_PATH = (
    REPO_ROOT
    / ".claude"
    / "skills"
    / "dashboard-generator"
    / "references"
    / "html-template.md"
)
ANALYST_AGENT_PATH = REPO_ROOT / ".claude" / "agents" / "analyst" / "AGENT.md"


class ValuationBridgeContractTests(unittest.TestCase):
    """Contract surface: spec docs + template placeholder + agent instructions."""

    def test_framework_documents_valuation_bridge(self) -> None:
        text = FRAMEWORK_PATH.read_text(encoding="utf-8")
        self.assertTrue(
            "valuation_bridge" in text or "Valuation Bridge" in text,
            "analysis-framework-dashboard.md must document the valuation_bridge "
            "section so analysts know to produce it.",
        )

    def test_template_has_valuation_bridge_placeholder(self) -> None:
        text = TEMPLATE_PATH.read_text(encoding="utf-8")
        self.assertIn(
            "{VALUATION_BRIDGE_SECTION}",
            text,
            "html-template.md must expose a {VALUATION_BRIDGE_SECTION} "
            "placeholder so the manual-population renderer can inject the "
            "bridge HTML between DCF/Reverse DCF and Peer Comparison.",
        )

    def test_template_marks_weighted_fair_value_as_model_output(self) -> None:
        text = TEMPLATE_PATH.read_text(encoding="utf-8")
        self.assertIn('class="badge-model"', text)
        self.assertIn("모델 산출값", text)

    def test_template_places_bridge_between_valuation_and_peers(self) -> None:
        text = TEMPLATE_PATH.read_text(encoding="utf-8")
        bridge_idx = text.find("{VALUATION_BRIDGE_SECTION}")
        peers_idx = text.find("section-peers")
        self.assertGreater(bridge_idx, 0, "bridge placeholder missing")
        self.assertGreater(peers_idx, 0, "peers section missing in template")
        self.assertLess(
            bridge_idx,
            peers_idx,
            "{VALUATION_BRIDGE_SECTION} must appear before the peer "
            "comparison section so the bridge renders right after DCF.",
        )

    def test_analyst_agent_documents_valuation_bridge_output(self) -> None:
        text = ANALYST_AGENT_PATH.read_text(encoding="utf-8")
        self.assertIn(
            "valuation_bridge",
            text,
            "analyst/AGENT.md must instruct Mode C analysis to write the "
            "valuation_bridge field into analysis-result.json.",
        )


class ValuationBridgeFixtureTests(unittest.TestCase):
    """Fixture-side contract: shape + arithmetic invariants."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    def test_fixture_has_top_level_valuation_bridge(self) -> None:
        self.assertIn("valuation_bridge", self.fixture)

    def test_fixture_has_four_anchors_with_required_fields(self) -> None:
        bridge = self.fixture["valuation_bridge"]
        anchors = bridge["anchors"]
        self.assertEqual(len(anchors), 4, "must have exactly 4 anchors")

        labels = {a["label"] for a in anchors}
        self.assertIn("DCF (Base)", labels)
        self.assertIn("Comp Multiples", labels)
        self.assertIn("Analyst Median Target", labels)
        # Korean label for "our base scenario"
        self.assertTrue(
            any("Base Scenario" in a["label"] for a in anchors),
            f"expected an anchor labeled like '... Base Scenario', got {labels}",
        )

        required = {"label", "value_per_share", "weight", "method", "tag"}
        for anchor in anchors:
            missing = required - set(anchor.keys())
            self.assertFalse(
                missing,
                f"anchor {anchor.get('label')!r} missing fields: {missing}",
            )

    def test_fixture_top_level_required_keys(self) -> None:
        bridge = self.fixture["valuation_bridge"]
        for key in (
            "current_price",
            "weighted_fair_value",
            "implied_view_vs_market",
            "reconciliation_logic",
            "decision_anchor",
        ):
            self.assertIn(key, bridge, f"valuation_bridge missing {key}")

    def test_anchor_weights_sum_to_one(self) -> None:
        anchors = self.fixture["valuation_bridge"]["anchors"]
        total_weight = sum(a["weight"] for a in anchors)
        self.assertAlmostEqual(total_weight, 1.0, places=4)

    def test_weighted_fair_value_matches_anchor_arithmetic(self) -> None:
        bridge = self.fixture["valuation_bridge"]
        computed = sum(a["value_per_share"] * a["weight"] for a in bridge["anchors"])
        self.assertAlmostEqual(
            computed,
            bridge["weighted_fair_value"],
            delta=0.1,
            msg=(
                "weighted_fair_value must equal sum(value_per_share * weight) "
                "across anchors within 0.1; computed={computed} vs declared="
                f"{bridge['weighted_fair_value']}"
            ).format(computed=computed),
        )

    def test_implied_view_matches_formula(self) -> None:
        bridge = self.fixture["valuation_bridge"]
        expected = (
            (bridge["weighted_fair_value"] - bridge["current_price"])
            / bridge["current_price"]
            * 100.0
        )
        declared = bridge["implied_view_vs_market"]
        match = re.match(r"^([+-]?\d+(?:\.\d+)?)%$", declared.strip())
        self.assertIsNotNone(
            match,
            f"implied_view_vs_market must be a signed percentage string (e.g. "
            f"'-10.7%'); got {declared!r}",
        )
        declared_value = float(match.group(1))
        # Sign agreement
        self.assertEqual(
            (declared_value > 0) - (declared_value < 0),
            (expected > 0) - (expected < 0),
            f"sign mismatch: declared {declared_value} vs computed {expected}",
        )
        # Magnitude within 0.2 pp tolerance to allow for rounding presentation
        self.assertAlmostEqual(declared_value, expected, delta=0.2)

    def test_reconciliation_logic_is_substantive_korean_paragraph(self) -> None:
        text = self.fixture["valuation_bridge"]["reconciliation_logic"]
        self.assertIsInstance(text, str)
        # Korean Mode C output style — require Hangul presence.
        has_hangul = any("가" <= ch <= "힣" for ch in text)
        self.assertTrue(
            has_hangul,
            "reconciliation_logic should be a Korean paragraph for ko Mode C output.",
        )
        # Word count >= 50 (Korean is space-separated for our purposes; we count
        # whitespace-delimited tokens which approximates the framework rule).
        word_count = len(text.split())
        self.assertGreaterEqual(
            word_count,
            50,
            f"reconciliation_logic must be >=50 words/tokens; got {word_count}",
        )

    def test_decision_anchor_points_to_known_target(self) -> None:
        anchor = self.fixture["valuation_bridge"]["decision_anchor"]
        self.assertIn(
            anchor,
            {
                "scenarios.base",
                "scenarios.bull",
                "scenarios.bear",
                "weighted_fair_value",
            },
            f"unexpected decision_anchor value: {anchor!r}",
        )


if __name__ == "__main__":
    unittest.main()
