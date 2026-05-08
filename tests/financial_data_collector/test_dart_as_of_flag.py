"""Tests for the ``--as-of`` flag on dart-collector.py.

Covers Task 2.4 of the backtest harness plan
(``docs/superpowers/plans/2026-05-08-backtest-harness.md``):

The ``--as-of YYYY-MM-DD`` flag enables historical Korean disclosure
collection on the existing dart-collector.py. These tests cover the CLI
surface without making real network calls:

- ``--as-of`` is registered (visible in ``--help``).
- Bad date format is rejected with exit code 2 (argparse error).
- Future date is rejected with exit code 2 (argparse error).
- Existing flags (``--stock-code``, ``--output``, ``--api-key``) remain
  intact (zero regression).

The actual historical fetch behavior (which requires a DART API key +
network) is not exercised here. Snapshot semantics are covered by the
adapter tests under ``tests/backtest/test_dart_historical.py`` which use
``subprocess.run`` monkeypatching.

Note: dart-collector.py lives under ``.claude/skills/web-researcher/``,
not financial-data-collector. We test it from this directory because it
shares the as-of CLI contract with the other collectors (mirrors
``test_fred_as_of_flag.py``).

Run via: ``python -m pytest tests/financial_data_collector/test_dart_as_of_flag.py -v``
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
COLLECTOR_PATH = (
    REPO_ROOT
    / ".claude"
    / "skills"
    / "web-researcher"
    / "scripts"
    / "dart-collector.py"
)


def _run_collector(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(COLLECTOR_PATH), *args],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )


class DartAsOfFlagTests(unittest.TestCase):
    def test_collector_path_exists(self):
        self.assertTrue(
            COLLECTOR_PATH.is_file(),
            f"dart-collector.py should exist at {COLLECTOR_PATH}",
        )

    def test_help_includes_as_of_flag(self):
        result = _run_collector("--help")
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("--as-of", result.stdout)

    def test_help_includes_existing_flags(self):
        # Regression: the existing flags must remain in the CLI surface.
        result = _run_collector("--help")
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        for flag in ("--stock-code", "--output", "--api-key"):
            self.assertIn(flag, result.stdout, msg=f"missing flag: {flag}")

    def test_as_of_invalid_format_rejected(self):
        # Use slashes instead of hyphens — should fail argparse validation.
        result = _run_collector(
            "--stock-code", "005930",
            "--output", "/tmp/should-not-write.json",
            "--as-of", "2025/03/31",
        )
        self.assertEqual(
            result.returncode, 2,
            msg=f"expected exit 2 for bad date, got {result.returncode}\n"
                f"stdout={result.stdout}\nstderr={result.stderr}",
        )

    def test_as_of_garbage_string_rejected(self):
        result = _run_collector(
            "--stock-code", "005930",
            "--output", "/tmp/should-not-write.json",
            "--as-of", "not-a-date",
        )
        self.assertEqual(
            result.returncode, 2,
            msg=f"expected exit 2, got {result.returncode}",
        )

    def test_as_of_future_date_rejected(self):
        result = _run_collector(
            "--stock-code", "005930",
            "--output", "/tmp/should-not-write.json",
            "--as-of", "2099-01-01",
        )
        self.assertEqual(
            result.returncode, 2,
            msg=f"expected exit 2 for future date, got {result.returncode}",
        )
        self.assertIn("future", result.stderr.lower())


if __name__ == "__main__":
    unittest.main()
