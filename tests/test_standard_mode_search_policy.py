"""Guardrails for Standard Mode US collection order."""

from __future__ import annotations

import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

POLICY_FILES = [
    ROOT / ".claude" / "skills" / "web-researcher" / "SKILL.md",
    ROOT / ".claude" / "skills" / "market-router" / "SKILL.md",
    ROOT / ".claude" / "skills" / "web-researcher" / "references" / "us-data-sources.md",
    ROOT / ".claude" / "skills" / "financial-data-collector" / "SKILL.md",
    ROOT / "CLAUDE.md",
    ROOT / "docs" / "yfinance-integration-spec.md",
    ROOT / "docs" / "mcp-setup-guide.md",
    ROOT / "docs" / "mcp-setup-guide.ko.md",
]


class StandardModeSearchPolicyTests(unittest.TestCase):
    def test_fixed_eight_search_policy_is_not_reintroduced(self):
        forbidden_phrases = [
            "Execute ALL 8 searches",
            "8 searches still do not yield",
            "Execute these 8 searches in order",
            "Execute 8 US searches",
            "any of the 8 searches fail",
            "Standard: 8 minimum",
            "Standard Mode (web-only)",
            "Standard (Web-only)",
            "Web-only",
        ]

        for path in POLICY_FILES:
            text = path.read_text(encoding="utf-8")
            for phrase in forbidden_phrases:
                with self.subTest(path=str(path.relative_to(ROOT)), phrase=phrase):
                    self.assertNotIn(phrase, text)

    def test_yfinance_first_policy_is_explicit_in_orchestration_docs(self):
        expectations = {
            ".claude/skills/web-researcher/SKILL.md": [
                "Step 4.3 — Standard Mode US Protocol (Structured First)",
                "yfinance structured fetch",
                "Targeted searches only for missing structured fields",
                "price/market-cap/P/E searches skipped",
            ],
            ".claude/skills/market-router/SKILL.md": [
                "standard_us_order",
                "yfinance_structured_fetch_then_missing_field_search",
                "only_if_missing_after_yfinance",
            ],
            ".claude/skills/web-researcher/references/us-data-sources.md": [
                "Standard Mode — Adaptive Search Policy",
                "Start Standard Mode US collection with the yfinance structured fetch",
                "Run these targeted searches only when yfinance leaves",
            ],
            ".claude/skills/financial-data-collector/SKILL.md": [
                "Step 3.3.6 — Standard Mode yfinance Handoff",
                "Run this structured fetch before broad price",
            ],
            "CLAUDE.md": [
                "US Standard Mode: run yfinance structured fetch first",
                "targeted missing-field searches plus qualitative searches",
            ],
            "docs/yfinance-integration-spec.md": [
                "Replace the US Standard Mode Step 4.3 flow with yfinance-first structured",
                "Skip price, market-cap, P/E, and SEC",
            ],
        }

        for relative_path, required_phrases in expectations.items():
            text = (ROOT / relative_path).read_text(encoding="utf-8")
            for phrase in required_phrases:
                with self.subTest(path=relative_path, phrase=phrase):
                    self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()
