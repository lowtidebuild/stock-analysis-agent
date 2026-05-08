"""Tests for the ``--as-of`` flag on yfinance-collector.py.

Covers Task 2.1 of the backtest harness plan
(``docs/superpowers/plans/2026-05-08-backtest-harness.md``):

The ``--as-of YYYY-MM-DD`` flag enables historical data collection mode
on the existing yfinance-collector.py. These tests cover the CLI surface
without making real network calls:

- ``--as-of`` is registered (visible in ``--help``).
- Bad date format is rejected with exit code 2 (argparse error).
- Future date is rejected with exit code 2 (argparse error).
- Default behavior (no ``--as-of``) is unchanged — covered by existing
  collector tests, but we add a basic ``--help`` regression here too.

The actual historical fetch behavior (which requires yfinance + network)
is exercised via an opt-in integration test gated by the
``INTEGRATION_TESTS=1`` env var.

Run via: ``python -m pytest tests/financial_data_collector/test_yfinance_as_of_flag.py -v``
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
COLLECTOR_PATH = (
    REPO_ROOT
    / ".claude"
    / "skills"
    / "financial-data-collector"
    / "scripts"
    / "yfinance-collector.py"
)


def _run_collector(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(COLLECTOR_PATH), *args],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )


class YFinanceAsOfFlagTests(unittest.TestCase):
    def test_collector_path_exists(self):
        self.assertTrue(
            COLLECTOR_PATH.is_file(),
            f"yfinance-collector.py should exist at {COLLECTOR_PATH}",
        )

    def test_help_includes_as_of_flag(self):
        result = _run_collector("--help")
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("--as-of", result.stdout)

    def test_help_includes_existing_flags(self):
        # Regression: the existing flags must remain in the CLI.
        result = _run_collector("--help")
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        for flag in ("--ticker", "--market", "--output", "--bundle", "--timeout"):
            self.assertIn(flag, result.stdout, msg=f"missing flag: {flag}")

    def test_as_of_invalid_format_rejected(self):
        # Use slashes instead of hyphens — should fail argparse validation.
        result = _run_collector(
            "--ticker", "AAPL",
            "--market", "US",
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
            "--ticker", "AAPL",
            "--market", "US",
            "--output", "/tmp/should-not-write.json",
            "--as-of", "not-a-date",
        )
        self.assertEqual(
            result.returncode, 2,
            msg=f"expected exit 2, got {result.returncode}",
        )

    def test_as_of_future_date_rejected(self):
        result = _run_collector(
            "--ticker", "AAPL",
            "--market", "US",
            "--output", "/tmp/should-not-write.json",
            "--as-of", "2099-01-01",
        )
        self.assertEqual(
            result.returncode, 2,
            msg=f"expected exit 2 for future date, got {result.returncode}",
        )
        self.assertIn("future", result.stderr.lower())


@unittest.skipUnless(
    os.environ.get("INTEGRATION_TESTS") == "1",
    "Integration test — requires network. Set INTEGRATION_TESTS=1 to enable.",
)
class YFinanceAsOfIntegrationTests(unittest.TestCase):
    """Live-network integration test. Skipped by default."""

    def test_as_of_historical_fetch_aapl(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / "aapl.json"
            result = _run_collector(
                "--ticker", "AAPL",
                "--market", "US",
                "--output", str(out),
                "--bundle", "standard",
                "--as-of", "2025-01-15",
                "--timeout", "30",
            )
            self.assertIn(
                result.returncode, (0, 1),
                msg=f"collector should exit 0 or 1, got {result.returncode}\n"
                    f"stdout={result.stdout}\nstderr={result.stderr}",
            )
            self.assertTrue(out.exists())
            payload = json.loads(out.read_text(encoding="utf-8"))
            self.assertIn("_backtest_meta", payload)
            self.assertEqual(payload["_backtest_meta"]["as_of"], "2025-01-15")
            self.assertEqual(payload["_backtest_meta"]["freeze_strategy"], "hybrid")
            self.assertIn("_backtest_caveats", payload)
            self.assertIn(
                "info_fields_use_current_state", payload["_backtest_caveats"]
            )
            self.assertIsNone(
                payload["analyst_targets"],
                msg="analyst targets must be skipped in as-of mode",
            )


if __name__ == "__main__":
    unittest.main()
