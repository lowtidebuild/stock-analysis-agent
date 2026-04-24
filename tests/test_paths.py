"""Tests for tools.paths env-var path resolution."""

from __future__ import annotations

import os
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class DataDirTests(unittest.TestCase):
    def setUp(self):
        # Snapshot relevant env vars and clear them.
        self._snapshot = {
            k: os.environ.get(k)
            for k in ("STOCK_ANALYSIS_DATA_DIR", "STOCK_ANALYSIS_PRIVATE_DOCS_DIR")
        }
        for k in self._snapshot:
            os.environ.pop(k, None)
        # Force-reimport so module-level constants re-evaluate.
        sys.modules.pop("tools.paths", None)

    def tearDown(self):
        for k, v in self._snapshot.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        sys.modules.pop("tools.paths", None)

    def test_data_dir_defaults_to_in_repo_output(self):
        from tools.paths import data_dir, REPO_ROOT

        self.assertEqual(data_dir(), REPO_ROOT / "output")

    def test_data_dir_respects_env_var(self):
        os.environ["STOCK_ANALYSIS_DATA_DIR"] = "/tmp/some-other-place"
        from tools.paths import data_dir

        self.assertEqual(data_dir(), pathlib.Path("/tmp/some-other-place"))

    def test_data_dir_expands_user(self):
        os.environ["STOCK_ANALYSIS_DATA_DIR"] = "~/scratch/sa"
        from tools.paths import data_dir

        self.assertEqual(data_dir(), pathlib.Path.home() / "scratch" / "sa")

    def test_data_dir_resolves_relative_env_under_repo(self):
        os.environ["STOCK_ANALYSIS_DATA_DIR"] = "tmp-runtime"
        from tools.paths import data_dir, REPO_ROOT

        self.assertEqual(data_dir(), REPO_ROOT / "tmp-runtime")

    def test_private_docs_dir_defaults_to_in_repo(self):
        from tools.paths import private_docs_dir, REPO_ROOT

        self.assertEqual(private_docs_dir(), REPO_ROOT / "docs" / "superpowers")

    def test_private_docs_dir_respects_env_var(self):
        os.environ["STOCK_ANALYSIS_PRIVATE_DOCS_DIR"] = "/tmp/private"
        from tools.paths import private_docs_dir

        self.assertEqual(private_docs_dir(), pathlib.Path("/tmp/private"))

    def test_data_subpath_helper(self):
        from tools.paths import data_path

        result = data_path("reports", "x.html")
        self.assertTrue(str(result).endswith("output/reports/x.html"))

    def test_runtime_path_maps_output_prefix_to_data_dir(self):
        os.environ["STOCK_ANALYSIS_DATA_DIR"] = "/tmp/stock-agent-runtime"
        from tools.paths import runtime_path

        self.assertEqual(
            runtime_path("output/runs/run-a/AAPL/analysis-result.json"),
            pathlib.Path("/tmp/stock-agent-runtime/runs/run-a/AAPL/analysis-result.json"),
        )

    def test_default_report_path_honors_data_dir_env(self):
        os.environ["STOCK_ANALYSIS_DATA_DIR"] = "/tmp/stock-agent-runtime"
        from tools.analysis_contract import build_default_report_path

        self.assertEqual(
            build_default_report_path(
                ticker="AAPL",
                output_mode="C",
                output_language="en",
                analysis_date="2026-04-24",
            ),
            str(pathlib.Path("/tmp/stock-agent-runtime/reports/AAPL_C_EN_2026-04-24.html").resolve()),
        )

    def test_build_run_paths_honors_data_dir_env(self):
        os.environ["STOCK_ANALYSIS_DATA_DIR"] = "/tmp/stock-agent-runtime"
        from tools.analysis_contract import build_run_paths

        paths = build_run_paths(ROOT, "20260424T000000Z_AAPL", "AAPL")

        self.assertEqual(
            paths["tier1_raw"],
            pathlib.Path("/tmp/stock-agent-runtime/runs/20260424T000000Z_AAPL/AAPL/tier1-raw.json").resolve(),
        )
        self.assertEqual(paths["snapshot_dir"], pathlib.Path("/tmp/stock-agent-runtime/data/AAPL").resolve())

    def test_build_snapshot_paths_use_immutable_snapshot_namespace(self):
        os.environ["STOCK_ANALYSIS_DATA_DIR"] = "/tmp/stock-agent-runtime"
        from tools.analysis_contract import build_snapshot_paths

        paths = build_snapshot_paths(ROOT, "aapl", "2026-04-24_run_abc123")

        self.assertEqual(paths["latest_pointer"], pathlib.Path("/tmp/stock-agent-runtime/data/AAPL/latest.json").resolve())
        self.assertEqual(
            paths["validated_data"],
            pathlib.Path("/tmp/stock-agent-runtime/data/AAPL/snapshots/2026-04-24_run_abc123/validated-data.json").resolve(),
        )


if __name__ == "__main__":
    unittest.main()
