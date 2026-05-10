"""Tests for tools.paths.backtest_path helper.

Run via: python -m unittest tests.test_paths_backtest
"""

from __future__ import annotations

import os
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class BacktestPathTests(unittest.TestCase):
    def setUp(self):
        self._snapshot = {
            k: os.environ.get(k)
            for k in ("STOCK_ANALYSIS_DATA_DIR",)
        }
        for k in self._snapshot:
            os.environ.pop(k, None)
        sys.modules.pop("tools.paths", None)

    def tearDown(self):
        for k, v in self._snapshot.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        sys.modules.pop("tools.paths", None)

    def test_backtest_path_defaults_under_repo_output(self):
        from tools.paths import backtest_path, REPO_ROOT

        self.assertEqual(
            backtest_path("cohorts", "2025Q1"),
            REPO_ROOT / "output" / "backtest" / "cohorts" / "2025Q1",
        )

    def test_backtest_path_no_parts_returns_root(self):
        from tools.paths import backtest_path, REPO_ROOT

        self.assertEqual(
            backtest_path(),
            REPO_ROOT / "output" / "backtest",
        )

    def test_backtest_path_honors_data_dir_env(self):
        os.environ["STOCK_ANALYSIS_DATA_DIR"] = "/tmp/stock-agent-runtime"
        from tools.paths import backtest_path

        self.assertEqual(
            backtest_path("cohorts", "2025Q1"),
            pathlib.Path("/tmp/stock-agent-runtime/backtest/cohorts/2025Q1"),
        )

    def test_backtest_path_in_public_api(self):
        from tools import paths

        self.assertIn("backtest_path", paths.__all__)


if __name__ == "__main__":
    unittest.main()
