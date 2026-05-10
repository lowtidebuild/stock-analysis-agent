"""Tests for tools/backtest_runner.py CLI argparse behavior.

Run via: python -m unittest tests.backtest.test_cli
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
CLI = ROOT / "tools" / "backtest_runner.py"


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )


class BacktestRunnerCliTests(unittest.TestCase):
    def test_as_of_flag_parsed_correctly(self):
        result = _run_cli("--cohort", "smoke", "--as-of", "2025-03-31", "--dry-run")
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["cohort"], "smoke")
        self.assertEqual(payload["as_of"], "2025-03-31")

    def test_as_of_invalid_format_rejected(self):
        result = _run_cli("--cohort", "smoke", "--as-of", "2025/03/31")
        self.assertEqual(result.returncode, 2, msg=result.stdout + result.stderr)

    def test_as_of_future_date_rejected(self):
        result = _run_cli("--cohort", "smoke", "--as-of", "2099-01-01", "--dry-run")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("future", result.stderr.lower())

    def test_no_as_of_is_ok(self):
        result = _run_cli("--cohort", "smoke", "--dry-run")
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["cohort"], "smoke")
        self.assertIsNone(payload["as_of"])

    def test_missing_cohort_rejected(self):
        result = _run_cli("--dry-run")
        self.assertEqual(result.returncode, 2, msg=result.stdout + result.stderr)

    def test_unknown_cohort_returns_exit_2(self):
        # Task 3.2: the CLI now resolves the manifest and rejects
        # unknown cohort ids with exit code 2 (manifest load failure).
        # The Chunk-3-stub "not yet implemented" path was removed when
        # the runner was wired to BatchRunner.
        result = _run_cli("--cohort", "this_cohort_does_not_exist")
        self.assertEqual(result.returncode, 2, msg=result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
