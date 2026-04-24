"""Tests for fetched-artifact sanitization enforcement in the validator."""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

from tools.artifact_validation import validate_artifact_file

ROOT = pathlib.Path(__file__).resolve().parents[1]
VALIDATE_ARTIFACTS = ROOT / ".claude" / "skills" / "data-validator" / "scripts" / "validate-artifacts.py"


class ValidatorUnsanitizedTests(unittest.TestCase):
    def test_validator_flags_missing_sanitization_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact = pathlib.Path(tmp) / "tier2-raw.json"
            artifact.write_text(
                json.dumps({"ticker": "AAPL", "snippet": "ok"}),
                encoding="utf-8",
            )

            result = validate_artifact_file(str(artifact), artifact_type="tier2-raw")

            self.assertTrue(result["valid"])
            self.assertTrue(result["schema_valid"])
            self.assertFalse(result["ingestion_allowed"])
            self.assertTrue(result["sanitization_required"])
            self.assertFalse(result["sanitization_present"])
            self.assertEqual(result["overall_grade"], "D")
            self.assertIn("unsanitized_fetched_content", result["security_flags"])
            self.assertTrue(any("unsanitized" in str(flag).lower() for flag in result.get("flags", [])))

    def test_validator_accepts_sanitized_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact = pathlib.Path(tmp) / "tier2-raw.json"
            artifact.write_text(
                json.dumps(
                    {
                        "ticker": "AAPL",
                        "snippet": "ok",
                        "_sanitization": {
                            "tool": "tools/prompt_injection_filter.py",
                            "version": "1",
                            "redactions": 0,
                            "findings": [],
                        },
                    }
                ),
                encoding="utf-8",
            )

            result = validate_artifact_file(str(artifact), artifact_type="tier2-raw")

            self.assertTrue(result["valid"])
            self.assertTrue(result["schema_valid"])
            self.assertTrue(result["ingestion_allowed"])
            self.assertTrue(result["sanitization_required"])
            self.assertTrue(result["sanitization_present"])
            self.assertNotEqual(result["overall_grade"], "D")
            self.assertEqual(result["security_flags"], [])
            self.assertFalse(any("unsanitized" in str(flag).lower() for flag in result.get("flags", [])))

    def test_cli_exits_nonzero_when_ingestion_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact = pathlib.Path(tmp) / "tier2-raw.json"
            artifact.write_text(
                json.dumps({"ticker": "AAPL", "snippet": "ok"}),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(VALIDATE_ARTIFACTS),
                    "--artifact-type",
                    "tier2-raw",
                    "--input",
                    str(artifact),
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn('"ingestion_allowed": false', result.stdout)


if __name__ == "__main__":
    unittest.main()
