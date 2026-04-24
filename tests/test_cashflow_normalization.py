"""Tests for yfinance cash-flow sign normalization."""

from __future__ import annotations

import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
YFINANCE_COLLECTOR = ROOT / ".claude" / "skills" / "financial-data-collector" / "scripts" / "yfinance-collector.py"


def _load_yfinance_collector():
    spec = importlib.util.spec_from_file_location("test_yfinance_collector", YFINANCE_COLLECTOR)
    if spec is None or spec.loader is None:
        raise AssertionError("failed to load yfinance collector")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FrameAt:
    def __init__(self, data):
        self._data = data

    def __getitem__(self, key):
        row, column = key
        return self._data[row][column]


class _StatementFrame:
    empty = False

    def __init__(self, data, columns):
        self._data = data
        self.index = list(data.keys())
        self.columns = columns
        self.at = _FrameAt(data)


class CashflowNormalizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.collector = _load_yfinance_collector()

    def _normalize_cashflow(self, capex, free_cash_flow=None):
        data = {
            "Operating Cash Flow": {"2025-12-31": 100},
            "Capital Expenditure": {"2025-12-31": capex},
            "Free Cash Flow": {"2025-12-31": free_cash_flow},
        }
        frame = _StatementFrame(data, ["2025-12-31"])
        warnings = []
        rows = self.collector.normalize_statement(
            frame,
            self.collector.CASHFLOW_ALIASES,
            "quarterly",
            warnings,
        )
        return rows[0]

    def test_negative_capex_is_normalized_to_positive_outflow(self):
        row = self._normalize_cashflow(capex=-20)

        self.assertEqual(row["capex_raw"], -20)
        self.assertEqual(row["capex_outflow_abs"], 20)
        self.assertEqual(row["capital_expenditure"], 20)
        self.assertEqual(row["capex_sign_convention"], "negative_outflow")
        self.assertEqual(row["free_cash_flow"], 80)
        self.assertEqual(row["free_cash_flow_calculated"], 80)

    def test_positive_capex_uses_same_outflow_convention(self):
        row = self._normalize_cashflow(capex=20)

        self.assertEqual(row["capex_raw"], 20)
        self.assertEqual(row["capex_outflow_abs"], 20)
        self.assertEqual(row["capital_expenditure"], 20)
        self.assertEqual(row["capex_sign_convention"], "positive_outflow")
        self.assertEqual(row["free_cash_flow"], 80)

    def test_source_fcf_conflict_is_recorded(self):
        row = self._normalize_cashflow(capex=-20, free_cash_flow=95)

        self.assertEqual(row["free_cash_flow"], 95)
        self.assertEqual(row["free_cash_flow_calculated"], 80)
        self.assertEqual(row["free_cash_flow_conflict"]["source_value"], 95)
        self.assertEqual(row["free_cash_flow_conflict"]["calculated_value"], 80)


if __name__ == "__main__":
    unittest.main()
