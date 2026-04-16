"""Tests for fetched-artifact sanitization enforcement in the validator."""

from __future__ import annotations

import json
import pathlib
import tempfile
import unittest

from tools.artifact_validation import validate_artifact_file


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
            self.assertEqual(result["overall_grade"], "D")
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
            self.assertNotEqual(result["overall_grade"], "D")
            self.assertFalse(any("unsanitized" in str(flag).lower() for flag in result.get("flags", [])))


if __name__ == "__main__":
    unittest.main()
