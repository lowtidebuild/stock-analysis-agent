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


if __name__ == "__main__":
    unittest.main()
