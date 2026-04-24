"""Tests for structured FRED macro availability contracts."""

from __future__ import annotations

import importlib.util
import pathlib
import tempfile
import unittest

from tools.artifact_validation import validate_macro_context_contract
from tools.quality_report import build_rendered_output_item

ROOT = pathlib.Path(__file__).resolve().parents[1]
FRED_COLLECTOR = ROOT / ".claude" / "skills" / "web-researcher" / "scripts" / "fred-collector.py"


def _load_fred_collector():
    spec = importlib.util.spec_from_file_location("test_fred_collector", FRED_COLLECTOR)
    if spec is None or spec.loader is None:
        raise AssertionError("failed to load FRED collector")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _macro_report(body: str) -> str:
    return f"""<!doctype html>
<html>
  <body>
    <section>DCF Valuation</section>
    <section>Analyst Coverage</section>
    <section>Peer Comparison</section>
    <script>
      const priceLabels = ["2026-01-01"];
      const priceData = [10];
      new Chart(document.createElement("canvas"), {{ data: {{ labels: priceLabels }} }});
    </script>
    <footer>Disclaimer: informational only, not investment advice.</footer>
    {body}
  </body>
</html>"""


class FredMacroContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.collector = _load_fred_collector()

    def test_successful_snapshot_exposes_available_structured_context(self):
        series_data = {
            "DGS10": {
                "value": 4.52,
                "date": "2026-04-23",
                "unit": "percent",
                "series_name": "10-Year Treasury Yield",
                "category": "common",
            },
            "DFF": {
                "value": 4.33,
                "date": "2026-04-23",
                "unit": "percent",
                "series_name": "Federal Funds Effective Rate",
                "category": "common",
            },
            "CPIAUCSL": {
                "value": 320.0,
                "yoy_pct": 2.8,
                "date": "2026-03-31",
                "unit": "percent_yoy",
                "series_name": "CPI All Urban Consumers",
                "category": "common",
            },
            "DEXKOUS": {
                "value": 1375.5,
                "date": "2026-04-23",
                "unit": "krw_per_usd",
                "series_name": "USD/KRW Exchange Rate",
                "category": "kr_overlay",
            },
        }

        snapshot = self.collector.build_snapshot(series_data, [], include_kr=True)
        structured = snapshot["macro_context"]["structured"]

        self.assertEqual(structured["status"], "available")
        self.assertEqual(structured["grade"], "A")
        self.assertEqual(structured["risk_free_rate"], 4.52)
        self.assertEqual(structured["cpi_yoy"], 2.8)
        self.assertEqual(structured["kr_overlay"]["usd_krw"], 1375.5)
        self.assertTrue(any(item["id"] == "DGS10" and item["grade"] == "A" for item in structured["series"]))
        self.assertEqual(validate_macro_context_contract(snapshot["macro_context"]), [])

    def test_failure_snapshot_exposes_unavailable_grade_d_context(self):
        snapshot = self.collector.build_failure_snapshot("collector_timeout", errors=["timeout"], include_kr=False)
        structured = snapshot["macro_context"]["structured"]

        self.assertEqual(structured["status"], "unavailable")
        self.assertEqual(structured["grade"], "D")
        self.assertEqual(structured["reason"], "collector_timeout")
        self.assertEqual(structured["series"], [])
        self.assertEqual(validate_macro_context_contract(snapshot["macro_context"]), [])

    def test_unavailable_macro_context_rejects_numeric_fred_claims(self):
        analysis = {
            "output_mode": "C",
            "sections": {
                "macro_context": {
                    "structured": {
                        "source": "FRED",
                        "status": "unavailable",
                        "grade": "D",
                        "reason": "collector_timeout",
                        "series": [],
                    }
                }
            },
        }

        with tempfile.TemporaryDirectory() as tmp:
            report_path = pathlib.Path(tmp) / "report.html"
            report_path.write_text(_macro_report("<p>FRED 10Y Treasury yield is 4.52% [Macro].</p>"), encoding="utf-8")

            item = build_rendered_output_item(report_path, analysis, {"exclusions": []})

        self.assertEqual(item["status"], "FAIL")
        self.assertTrue(any("FRED structured data is unavailable" in error for error in item["errors"]))

    def test_unavailable_macro_context_allows_explicit_unavailable_marker(self):
        analysis = {
            "output_mode": "C",
            "sections": {
                "macro_context": {
                    "structured": {
                        "source": "FRED",
                        "status": "unavailable",
                        "grade": "D",
                        "reason": "collector_timeout",
                        "series": [],
                    }
                }
            },
        }

        with tempfile.TemporaryDirectory() as tmp:
            report_path = pathlib.Path(tmp) / "report.html"
            report_path.write_text(_macro_report("<p>Macro data unavailable from FRED.</p>"), encoding="utf-8")

            item = build_rendered_output_item(report_path, analysis, {"exclusions": []})

        self.assertNotEqual(item["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
