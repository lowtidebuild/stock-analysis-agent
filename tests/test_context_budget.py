"""Tests for Analyst context-budget measurement and routing policy."""

from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

from tools.artifact_validation import validate_artifact_data, validate_artifact_file
from tools.context_budget import build_context_budget, main as context_budget_main

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _run_context() -> dict:
    return {
        "run_id": "run-budget",
        "artifact_root": "output/runs/run-budget/TEST",
        "ticker": "TEST",
    }


def _write_json(path: pathlib.Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _make_run_tree(root: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path]:
    run_dir = root / "output" / "runs" / "run-budget"
    ticker_dir = run_dir / "TEST"
    ticker_dir.mkdir(parents=True)
    framework_path = ticker_dir / "framework.md"
    framework_path.write_text("# Framework\n\nUse validated facts only.\n", encoding="utf-8")

    _write_json(
        ticker_dir / "validated-data.json",
        {
            "ticker": "TEST",
            "market": "US",
            "run_context": _run_context(),
            "validated_metrics": {
                "price_at_analysis": {
                    "value": 12.34,
                    "grade": "C",
                    "sources": ["Portal quote page"],
                }
            },
        },
    )
    _write_json(
        ticker_dir / "evidence-pack.json",
        {
            "ticker": "TEST",
            "market": "US",
            "run_context": _run_context(),
            "facts": [{"metric": "price_at_analysis", "value": 12.34, "grade": "C"}],
        },
    )
    _write_json(
        ticker_dir / "research-plan.json",
        {
            "ticker": "TEST",
            "market": "US",
            "run_context": _run_context(),
            "analysis_framework_path": "framework.md",
        },
    )
    _write_json(ticker_dir / "tier2-raw.json", {"_sanitization": {"status": "pass"}, "body": "x" * 400})
    return run_dir, ticker_dir


class ContextBudgetTests(unittest.TestCase):
    def test_build_context_budget_counts_default_inputs_and_excludes_raw_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, _ticker_dir = _make_run_tree(pathlib.Path(tmp))

            budget = build_context_budget(run_dir)

            included_roles = {item["role"] for item in budget["included_files"]}
            excluded_roles = {item["role"] for item in budget["excluded_raw_artifacts"]}
            self.assertIn("validated_metrics", included_roles)
            self.assertIn("compact_evidence", included_roles)
            self.assertIn("routing_plan", included_roles)
            self.assertIn("analysis_framework", included_roles)
            self.assertEqual({"raw_artifact_excluded_by_default"}, excluded_roles)
            self.assertGreater(budget["totals"]["estimated_tokens_avoided_by_default_raw_exclusion"], 0)
            self.assertTrue(budget["totals"]["within_soft_limit"])
            self.assertEqual(validate_artifact_data("context-budget", budget), [])

    def test_cli_writes_valid_context_budget_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, ticker_dir = _make_run_tree(pathlib.Path(tmp))
            output_path = ticker_dir / "context-budget.json"

            exit_code = context_budget_main(
                [
                    "--run-dir",
                    str(run_dir),
                    "--ticker",
                    "TEST",
                    "--output",
                    str(output_path),
                ]
            )

            self.assertEqual(exit_code, 0)
            result = validate_artifact_file(output_path, "context-budget", base_dir=ROOT)
            self.assertTrue(result["valid"])
            self.assertTrue(result["ingestion_allowed"])

    def test_routing_policy_documents_model_boundaries(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, _ticker_dir = _make_run_tree(pathlib.Path(tmp))

            budget = build_context_budget(run_dir, ticker="TEST")

            self.assertIn("final_investment_reasoning", budget["routing_policy"]["strong_model"])
            self.assertIn("first_pass_narrative_comments", budget["routing_policy"]["cheap_model_or_deterministic_preprocess"])
            self.assertIn("renderer_execution", budget["routing_policy"]["no_llm"])

    def test_operational_docs_include_context_budget_handoff(self):
        claude = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
        analyst = (ROOT / ".claude" / "agents" / "analyst" / "AGENT.md").read_text(encoding="utf-8")
        inputs_section = analyst.split("## Inputs (Load in This Order)", 1)[1].split("---", 1)[0]

        self.assertIn("output/runs/{run_id}/{ticker}/context-budget.json", claude)
        self.assertIn("Model Routing Cost Policy", claude)
        self.assertIn("No LLM", claude)
        self.assertIn("Cheap model", claude)
        self.assertIn("Strong model", claude)
        self.assertIn("Run-local `context-budget.json`", inputs_section)
        self.assertIn("within_soft_limit", inputs_section)


if __name__ == "__main__":
    unittest.main()
