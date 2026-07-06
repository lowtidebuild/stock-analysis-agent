from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

from tools.security_audit import audit_paths, forbidden_staged_findings

ROOT = pathlib.Path(__file__).resolve().parents[1]
CLI = ROOT / "tools" / "security_audit.py"


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )


class SecurityAuditTests(unittest.TestCase):
    def test_cli_blocks_high_confidence_secret_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "config.py"
            key_name = "OPENAI_" + "API_KEY"
            secret_value = "sk-proj-" + "abcdefghijklmnopqrstuvwx1234567890"
            path.write_text(
                f'{key_name} = "{secret_value}"\n',
                encoding="utf-8",
            )

            result = _run_cli("--paths", str(path), "--format", "json")
            self.assertEqual(result.returncode, 1, result.stdout)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["errors"], 2)
            self.assertIn("openai_secret_key", {item["rule"] for item in payload["findings"]})
            self.assertIn("sensitive_assignment", {item["rule"] for item in payload["findings"]})

    def test_env_variable_names_in_docs_are_not_secret_findings(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "RUNBOOK.md"
            path.write_text(
                "Set OPENAI_API_KEY and TAVILY_API_KEY outside the agent session.\n",
                encoding="utf-8",
            )

            result = _run_cli("--paths", str(path), "--format", "json")
            self.assertEqual(result.returncode, 0, result.stdout)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["errors"], 0)

    def test_forbidden_staged_paths_block_generated_and_secret_surfaces(self):
        findings = forbidden_staged_findings(
            [
                "output/reports/AAPL_C_ko_2026-06-23.html",
                ".understand-anything/knowledge-graph.json",
                ".env.local",
            ]
        )

        self.assertEqual(len(findings), 3)
        self.assertEqual({finding.rule for finding in findings}, {"forbidden_staged_path"})

    def test_staged_env_variants_are_forbidden(self):
        for name in [".env.production", ".env.staging", ".env.dev", "config/.env.production"]:
            with self.subTest(name=name):
                findings = forbidden_staged_findings([name])
                self.assertTrue(any(item.rule == "forbidden_staged_path" for item in findings))
                self.assertTrue(any(item.severity == "ERROR" for item in findings))

    def test_staged_env_example_is_allowed(self):
        findings = forbidden_staged_findings([".env.example", "config/.env.example"])

        self.assertEqual(findings, [])

    def test_fixture_marker_in_published_report_is_blocking(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "output" / "reports" / "AAPL_A_ko_2026-06-23.html"
            path.parent.mkdir(parents=True)
            path.write_text('<html>{"provider": "fixture", "run_profile": "smoke"}</html>', encoding="utf-8")

            findings = audit_paths([path])

        self.assertTrue(any(item.rule == "fixture_delivery_marker" for item in findings))
        self.assertTrue(any(item.severity == "ERROR" for item in findings))

    def test_http_script_in_html_is_blocking_and_https_script_is_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "report.html"
            path.write_text(
                '<script src="http://cdn.example.test/bad.js"></script>\n'
                '<script src="https://cdn.example.test/ok.js"></script>\n',
                encoding="utf-8",
            )

            findings = audit_paths([path])

        by_rule = {item.rule: item for item in findings}
        self.assertEqual(by_rule["insecure_external_script"].severity, "ERROR")
        self.assertEqual(by_rule["external_script_dependency"].severity, "WARN")


if __name__ == "__main__":
    unittest.main()
