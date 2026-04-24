"""Tests for rendered report quality checks."""

from __future__ import annotations

import json
import importlib.util
import pathlib
import subprocess
import sys
import tempfile
import unittest

from tools.quality_report import build_rendered_output_item

ROOT = pathlib.Path(__file__).resolve().parents[1]
QUALITY_REPORT_BUILDER = ROOT / ".claude" / "skills" / "quality-checker" / "scripts" / "quality-report-builder.py"
BRIEFING_RENDERER = ROOT / ".claude" / "skills" / "briefing-generator" / "scripts" / "render-briefing.py"


def _load_briefing_renderer():
    spec = importlib.util.spec_from_file_location("render_briefing", BRIEFING_RENDERER)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _mode_c_html(body: str) -> str:
    return f"""<!doctype html>
<html>
  <body>
    <h1>Example Report</h1>
    <section>DCF Valuation</section>
    <section>Analyst Coverage</section>
    <section>Peer Comparison</section>
    <p>Revenue 10 [Filing] and margin 20% [Calc].</p>
    <script>
      const priceLabels = ["2026-01-01"];
      const priceData = [10];
      new Chart(document.createElement("canvas"), {{ data: {{ labels: priceLabels }} }});
    </script>
    <footer>Disclaimer: informational only, not investment advice.</footer>
    {body}
  </body>
</html>"""


def _mode_a_analysis() -> dict:
    return {
        "ticker": "XYZ",
        "company_name": "Example Co",
        "output_mode": "A",
        "output_language": "en",
        "analysis_date": "2026-04-24",
        "price_at_analysis": 100.0,
        "currency": "USD",
        "rr_score": 2.0,
        "verdict": "neutral",
        "key_metrics": {
            "market_cap": {"value": 100_000_000, "grade": "B", "display_tag": "[Portal]"},
            "pe_ratio": {"value": 20.5, "grade": "B", "display_tag": "[Calc]"},
            "revenue_ttm": {"value": 50_000_000, "grade": "A", "display_tag": "[Filing]"},
        },
        "scenarios": {
            "bull": {"target": 120, "return_pct": 20, "probability": 0.3, "key_assumption": "Upside"},
            "base": {"target": 105, "return_pct": 5, "probability": 0.5, "key_assumption": "Base"},
            "bear": {"target": 80, "return_pct": -20, "probability": 0.2, "key_assumption": "Downside"},
        },
        "sections": {"one_line_thesis": "A concise thesis with enough company-specific context."},
        "top_risks": ["A specific risk chain could pressure margins."],
        "upcoming_catalysts": [{"description": "Next report", "date": "2026-05-01"}],
    }


def _mode_a_html(body: str) -> str:
    return f"""<!doctype html>
<html>
  <body>
    <h1>Example Co</h1>
    <p>As of 2026-04-24</p>
    <section>
      <div>Market Cap $100,000,000 [Portal] Grade B</div>
      <div>Pe Ratio 20.5x [Calc] Grade B</div>
      <div>Revenue Ttm $50,000,000 [Filing] Grade A</div>
    </section>
    <footer>Disclaimer: informational only, not investment advice.</footer>
    {body}
  </body>
</html>"""


class RenderedOutputValidationTests(unittest.TestCase):
    def test_mode_a_briefing_renderer_satisfies_minimum_output_gate(self):
        renderer = _load_briefing_renderer()
        analysis = _mode_a_analysis()
        with tempfile.TemporaryDirectory() as tmp:
            report_path = pathlib.Path(tmp) / "briefing.html"
            report_path.write_text(renderer.build_briefing_html(analysis), encoding="utf-8")

            item = build_rendered_output_item(report_path, analysis, {"exclusions": []})

            self.assertEqual(item["status"], "PASS")
            self.assertEqual(item["mode_a_minimum_checks"]["status"], "PASS")

    def test_mode_a_html_missing_disclaimer_fails(self):
        analysis = _mode_a_analysis()
        with tempfile.TemporaryDirectory() as tmp:
            report_path = pathlib.Path(tmp) / "briefing.html"
            report_path.write_text(
                _mode_a_html("").replace("Disclaimer: informational only, not investment advice.", ""),
                encoding="utf-8",
            )

            item = build_rendered_output_item(report_path, analysis, {"exclusions": []})

            self.assertEqual(item["status"], "FAIL")
            self.assertTrue(any("disclaimer" in error.lower() for error in item["errors"]))

    def test_mode_a_html_missing_kpi_attribution_fails(self):
        analysis = _mode_a_analysis()
        with tempfile.TemporaryDirectory() as tmp:
            report_path = pathlib.Path(tmp) / "briefing.html"
            report_path.write_text(
                _mode_a_html("")
                .replace("[Portal] Grade B", "")
                .replace("[Calc] Grade B", "")
                .replace("[Filing] Grade A", ""),
                encoding="utf-8",
            )

            item = build_rendered_output_item(report_path, analysis, {"exclusions": []})

            self.assertEqual(item["status"], "FAIL")
            self.assertTrue(any("kpi attribution" in error.lower() for error in item["errors"]))

    def test_mode_a_html_missing_as_of_date_fails(self):
        analysis = _mode_a_analysis()
        with tempfile.TemporaryDirectory() as tmp:
            report_path = pathlib.Path(tmp) / "briefing.html"
            report_path.write_text(_mode_a_html("").replace("2026-04-24", ""), encoding="utf-8")

            item = build_rendered_output_item(report_path, analysis, {"exclusions": []})

            self.assertEqual(item["status"], "FAIL")
            self.assertTrue(any("as-of date" in error.lower() for error in item["errors"]))

    def test_mode_c_html_with_required_sections_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            report_path = pathlib.Path(tmp) / "report.html"
            report_path.write_text(_mode_c_html(""), encoding="utf-8")

            item = build_rendered_output_item(
                report_path,
                {"output_mode": "C", "key_metrics": {}},
                {"exclusions": []},
            )

            self.assertEqual(item["status"], "PASS")

    def test_mode_c_html_missing_disclaimer_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            report_path = pathlib.Path(tmp) / "report.html"
            report_path.write_text(
                _mode_c_html("").replace("Disclaimer: informational only, not investment advice.", ""),
                encoding="utf-8",
            )

            item = build_rendered_output_item(
                report_path,
                {"output_mode": "C", "key_metrics": {}},
                {"exclusions": []},
            )

            self.assertEqual(item["status"], "FAIL")
            self.assertTrue(any("disclaimer" in error.lower() for error in item["errors"]))

    def test_mode_c_fixture_chart_placeholder_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            report_path = pathlib.Path(tmp) / "report.html"
            report_path.write_text(
                """<html><body>
                <section>DCF Valuation</section>
                <section>Analyst Coverage</section>
                <p>Charts & Trend Data: arrays are not present in this fixture.</p>
                <footer>Disclaimer: not investment advice.</footer>
                </body></html>""",
                encoding="utf-8",
            )

            item = build_rendered_output_item(
                report_path,
                {"output_mode": "C", "key_metrics": {}},
                {"exclusions": []},
            )

            self.assertEqual(item["status"], "FAIL")
            self.assertTrue(any("fixture" in error.lower() for error in item["errors"]))

    def test_grade_d_rendered_value_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            report_path = pathlib.Path(tmp) / "report.html"
            report_path.write_text(_mode_c_html("<p>EV/EBITDA 12.3x</p>"), encoding="utf-8")

            item = build_rendered_output_item(
                report_path,
                {"output_mode": "C", "key_metrics": {"ev_ebitda": {"value": 12.3}}},
                {"exclusions": [{"metric": "ev_ebitda"}]},
            )

            self.assertEqual(item["status"], "FAIL")
            self.assertTrue(any("excluded" in error.lower() or "grade d" in error.lower() for error in item["errors"]))

    def test_builder_accepts_report_path_in_print_only_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            run_dir = root / "runs" / "run1"
            ticker_dir = run_dir / "XYZ"
            ticker_dir.mkdir(parents=True)
            report_path = root / "reports" / "XYZ_C_EN_2026-04-24.html"
            report_path.parent.mkdir()
            report_path.write_text(_mode_c_html(""), encoding="utf-8")

            run_context = {"run_id": "run1", "ticker": "XYZ"}
            (ticker_dir / "research-plan.json").write_text(
                json.dumps({"ticker": "XYZ", "market": "US", "output_mode": "C", "run_context": run_context}),
                encoding="utf-8",
            )
            (ticker_dir / "validated-data.json").write_text(
                json.dumps({"ticker": "XYZ", "market": "US", "run_context": run_context, "validated_metrics": {}, "exclusions": []}),
                encoding="utf-8",
            )
            (ticker_dir / "analysis-result.json").write_text(
                json.dumps(
                    {
                        "ticker": "XYZ",
                        "market": "US",
                        "data_mode": "standard",
                        "output_mode": "C",
                        "analysis_date": "2026-04-24",
                        "run_context": run_context,
                        "key_metrics": {},
                        "scenarios": {
                            "bull": {"target": 12, "probability": 0.3},
                            "base": {"target": 10, "probability": 0.5},
                            "bear": {"target": 8, "probability": 0.2},
                        },
                        "rr_score": 5,
                        "verdict": "neutral",
                        "sections": {
                            "variant_view_q1": "x",
                            "variant_view_q2": "x",
                            "variant_view_q3": "x",
                            "precision_risks": [{"risk": "x"}, {"risk": "y"}, {"risk": "z"}],
                            "valuation_metrics": [{"metric": "P/E"}],
                            "peer_comparison": [{"ticker": "ABC"}],
                            "portfolio_strategy": "x",
                            "what_would_make_me_wrong": ["x"],
                        },
                    }
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(QUALITY_REPORT_BUILDER),
                    "--run-dir",
                    str(run_dir),
                    "--report-path",
                    str(report_path),
                    "--print-only",
                ],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertIn("rendered_output", payload["item_keys"])


if __name__ == "__main__":
    unittest.main()
