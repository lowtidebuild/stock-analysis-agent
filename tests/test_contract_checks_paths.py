"""Tests for contract-check runtime fixture path isolation."""

from __future__ import annotations

import os
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class ContractChecksPathTests(unittest.TestCase):
    def setUp(self):
        self._data_dir = os.environ.get("STOCK_ANALYSIS_DATA_DIR")

    def tearDown(self):
        if self._data_dir is None:
            os.environ.pop("STOCK_ANALYSIS_DATA_DIR", None)
        else:
            os.environ["STOCK_ANALYSIS_DATA_DIR"] = self._data_dir

    def test_runtime_fixtures_copy_to_configured_data_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["STOCK_ANALYSIS_DATA_DIR"] = tmp
            from tools.contract_checks import ensure_runtime_output_fixtures

            copied = ensure_runtime_output_fixtures()
            resolved_tmp = str(pathlib.Path(tmp).resolve())
            self.assertTrue(copied)
            self.assertTrue((pathlib.Path(tmp) / "runs" / "20260328T000000Z_AAPL_C").exists())
            self.assertTrue(all(str(path).startswith(resolved_tmp) for path in copied))

    def test_eval_harness_resolves_output_paths_to_configured_data_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["STOCK_ANALYSIS_DATA_DIR"] = tmp
            from tools.eval_harness import resolve_case_path

            self.assertEqual(
                resolve_case_path("output/runs/run-a/AAPL/analysis-result.json"),
                pathlib.Path(tmp) / "runs" / "run-a" / "AAPL" / "analysis-result.json",
            )
            self.assertEqual(
                resolve_case_path("evals/fixtures/quality-report-critic-valid.json"),
                ROOT / "evals" / "fixtures" / "quality-report-critic-valid.json",
            )

    def test_analysis_patch_validation_resolves_embedded_output_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["STOCK_ANALYSIS_DATA_DIR"] = tmp
            from tools.artifact_validation import validate_artifact_file
            from tools.contract_checks import ensure_runtime_output_fixtures

            ensure_runtime_output_fixtures()
            result = validate_artifact_file(
                ROOT / "evals" / "fixtures" / "analysis-patch-aapl-valid.json",
                "analysis-patch",
                base_dir=ROOT,
            )

            self.assertTrue(result["valid"], result["errors"])


if __name__ == "__main__":
    unittest.main()
