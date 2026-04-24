"""Guardrails for run-local raw artifact path guidance."""

from __future__ import annotations

import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

OPERATIONAL_DOC_GLOBS = (
    "CLAUDE.md",
    ".claude/agents/**/*.md",
    ".claude/skills/**/*.md",
    ".claude/skills/**/*.py",
    "docs/yfinance-integration-spec.md",
    "docs/adr/0002-run-local-snapshot-promotion.ko.md",
    "docs/agent-audit-remediation-guide.ko.md",
    "tools/sanitize_artifact.py",
)

FORBIDDEN_SHARED_ARTIFACT_PATH = re.compile(
    r"output/data/(?:\{ticker\}|\{TICKER\}|[A-Z0-9]{1,12})/"
    r"(?:tier[12]-raw|dart-api-raw|yfinance-raw|validated-data|research-plan)\.json"
)


class RunLocalArtifactDocsTests(unittest.TestCase):
    def test_operational_docs_do_not_point_raw_artifacts_at_shared_data_dir(self):
        offenders: list[str] = []
        for pattern in OPERATIONAL_DOC_GLOBS:
            for path in ROOT.glob(pattern):
                if path.is_dir():
                    continue
                text = path.read_text(encoding="utf-8")
                for match in FORBIDDEN_SHARED_ARTIFACT_PATH.finditer(text):
                    relpath = path.relative_to(ROOT)
                    offenders.append(f"{relpath}: {match.group(0)}")

        self.assertEqual([], offenders)

    def test_claude_handoff_documents_run_local_raw_artifacts(self):
        claude = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn("output/runs/{run_id}/{ticker}/tier1-raw.json", claude)
        self.assertIn("output/runs/{run_id}/{ticker}/tier2-raw.json", claude)
        self.assertIn("output/runs/{run_id}/{ticker}/evidence-pack.json", claude)
        self.assertIn("output/runs/{run_id}/{ticker}/context-budget.json", claude)
        self.assertIn("output/data/{ticker}/latest.json", claude)


if __name__ == "__main__":
    unittest.main()
