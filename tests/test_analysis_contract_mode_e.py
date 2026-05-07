"""Tests for Mode E (Earnings Preview/Review) filename generation in tools/analysis_contract.py."""

from __future__ import annotations

import os
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class ModeEFilenameTests(unittest.TestCase):
    """Verify Mode E paths follow the canonical `{ticker}_E_{sub}_{lang}_{date}.html` pattern."""

    def setUp(self) -> None:
        os.environ["STOCK_ANALYSIS_DATA_DIR"] = "/tmp/stock-agent-runtime-mode-e"

    def tearDown(self) -> None:
        os.environ.pop("STOCK_ANALYSIS_DATA_DIR", None)

    def test_default_extension_for_mode_e_is_html(self):
        from tools.analysis_contract import default_report_extension

        self.assertEqual(default_report_extension("E"), "html")
        self.assertEqual(default_report_extension("e"), "html")

    def test_preview_filename_korean(self):
        from tools.analysis_contract import build_default_report_path

        result = build_default_report_path(
            ticker="GOOGL",
            output_mode="E",
            output_language="ko",
            analysis_date="2026-04-26",
            sub_mode="preview",
        )
        self.assertEqual(
            result,
            str(pathlib.Path("/tmp/stock-agent-runtime-mode-e/reports/GOOGL_E_preview_KO_2026-04-26.html").resolve()),
        )

    def test_review_filename_korean(self):
        from tools.analysis_contract import build_default_report_path

        result = build_default_report_path(
            ticker="GOOGL",
            output_mode="E",
            output_language="ko",
            analysis_date="2026-04-30",
            sub_mode="review",
        )
        self.assertEqual(
            result,
            str(pathlib.Path("/tmp/stock-agent-runtime-mode-e/reports/GOOGL_E_review_KO_2026-04-30.html").resolve()),
        )

    def test_missing_sub_mode_raises_value_error(self):
        from tools.analysis_contract import build_default_report_path

        with self.assertRaises(ValueError):
            build_default_report_path(
                ticker="GOOGL",
                output_mode="E",
                output_language="ko",
                analysis_date="2026-04-26",
                sub_mode=None,
            )

    def test_invalid_sub_mode_raises_value_error(self):
        from tools.analysis_contract import build_default_report_path

        with self.assertRaises(ValueError):
            build_default_report_path(
                ticker="AAPL",
                output_mode="E",
                output_language="en",
                analysis_date="2026-05-01",
                sub_mode="bogus",
            )

    def test_sub_mode_normalized_lowercase(self):
        from tools.analysis_contract import build_default_report_path

        result = build_default_report_path(
            ticker="aapl",
            output_mode="E",
            output_language="en",
            analysis_date="2026-05-01",
            sub_mode="PREVIEW",
        )
        self.assertEqual(
            result,
            str(pathlib.Path("/tmp/stock-agent-runtime-mode-e/reports/AAPL_E_preview_EN_2026-05-01.html").resolve()),
        )

    def test_mode_a_backward_compat(self):
        from tools.analysis_contract import build_default_report_path

        result = build_default_report_path(
            ticker="AAPL",
            output_mode="A",
            output_language="ko",
            analysis_date="2026-05-01",
        )
        self.assertEqual(
            result,
            str(pathlib.Path("/tmp/stock-agent-runtime-mode-e/reports/AAPL_A_KO_2026-05-01.html").resolve()),
        )

    def test_mode_b_backward_compat(self):
        from tools.analysis_contract import build_default_report_path

        result = build_default_report_path(
            ticker="AAPL",
            output_mode="B",
            output_language="en",
            analysis_date="2026-05-01",
            peer_tickers=["MSFT", "GOOGL"],
        )
        self.assertEqual(
            result,
            str(pathlib.Path("/tmp/stock-agent-runtime-mode-e/reports/AAPL_MSFT_GOOGL_B_EN_2026-05-01.html").resolve()),
        )

    def test_mode_c_backward_compat(self):
        from tools.analysis_contract import build_default_report_path

        result = build_default_report_path(
            ticker="AAPL",
            output_mode="C",
            output_language="ko",
            analysis_date="2026-05-01",
        )
        self.assertEqual(
            result,
            str(pathlib.Path("/tmp/stock-agent-runtime-mode-e/reports/AAPL_C_KO_2026-05-01.html").resolve()),
        )

    def test_mode_d_backward_compat_docx(self):
        from tools.analysis_contract import build_default_report_path

        result = build_default_report_path(
            ticker="AAPL",
            output_mode="D",
            output_language="ko",
            analysis_date="2026-05-01",
        )
        self.assertEqual(
            result,
            str(pathlib.Path("/tmp/stock-agent-runtime-mode-e/reports/AAPL_D_KO_2026-05-01.docx").resolve()),
        )

    def test_sub_mode_ignored_for_non_e_modes(self):
        """Passing sub_mode for Mode A/B/C/D should not affect the filename (graceful, no error)."""
        from tools.analysis_contract import build_default_report_path

        result = build_default_report_path(
            ticker="AAPL",
            output_mode="C",
            output_language="ko",
            analysis_date="2026-05-01",
            sub_mode="preview",  # ignored
        )
        self.assertEqual(
            result,
            str(pathlib.Path("/tmp/stock-agent-runtime-mode-e/reports/AAPL_C_KO_2026-05-01.html").resolve()),
        )


if __name__ == "__main__":
    unittest.main()
