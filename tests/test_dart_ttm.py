"""Tests for DART TTM reconstruction."""

from __future__ import annotations

import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
DART_COLLECTOR = ROOT / ".claude" / "skills" / "web-researcher" / "scripts" / "dart-collector.py"


def _load_dart_collector():
    spec = importlib.util.spec_from_file_location("test_dart_collector", DART_COLLECTOR)
    if spec is None or spec.loader is None:
        raise AssertionError("failed to load DART collector")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _is_field(value):
    return {"statement_type": "IS", "value": value}


class DartTtmTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.collector = _load_dart_collector()

    def test_q3_prior_annual_and_prior_q3_compute_true_ttm(self):
        periods = {
            "Q3": {"parsed": {"revenue": _is_field(90), "operating_income": _is_field(9)}},
            "Annual": {"parsed": {"revenue": _is_field(120), "operating_income": _is_field(12)}},
            "Q3_prior": {"parsed": {"revenue": _is_field(80), "operating_income": _is_field(8)}},
        }

        ttm, note, precision = self.collector.estimate_ttm(periods)

        self.assertEqual(ttm["revenue"], 130)
        self.assertEqual(ttm["operating_income"], 13)
        self.assertIn("current Q3 YTD + prior annual - prior Q3 YTD", note)
        self.assertEqual(precision, "high")

    def test_q3_without_prior_period_is_labeled_ytd_proxy(self):
        periods = {
            "Q3": {"parsed": {"revenue": _is_field(90)}},
        }

        ttm, note, precision = self.collector.estimate_ttm(periods)

        self.assertEqual(ttm["revenue"], 90)
        self.assertIn("YTD proxy", note)
        self.assertEqual(precision, "low")

    def test_annual_only_is_not_labeled_current_ttm(self):
        periods = {
            "Annual": {"parsed": {"revenue": _is_field(120)}},
        }

        ttm, note, precision = self.collector.estimate_ttm(periods)

        self.assertEqual(ttm["revenue"], 120)
        self.assertIn("Latest annual 12M period", note)
        self.assertEqual(precision, "medium")


if __name__ == "__main__":
    unittest.main()
