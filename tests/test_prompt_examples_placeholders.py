"""Guardrails for prompt examples that should not seed real facts."""

from __future__ import annotations

import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PROMPT_FILES = [
    ROOT / ".claude" / "agents" / "analyst" / "AGENT.md",
    ROOT / ".claude" / "agents" / "critic" / "AGENT.md",
]


class PromptExamplePlaceholderTests(unittest.TestCase):
    def test_agent_examples_do_not_embed_real_company_seed_values(self):
        banned_patterns = [
            r"\bAAPL\b",
            r"\bApple\b",
            r"\bNASDAQ\b",
            r"\bWWDC\b",
            r"\bDOJ\b",
            r"\bApp Store\b",
            r"\b2026-\d{2}-\d{2}\b",
            r"\b2025\b",
            r"\$[0-9]",
        ]

        for path in PROMPT_FILES:
            text = path.read_text(encoding="utf-8")
            for pattern in banned_patterns:
                with self.subTest(path=str(path.relative_to(ROOT)), pattern=pattern):
                    self.assertIsNone(re.search(pattern, text))


if __name__ == "__main__":
    unittest.main()
