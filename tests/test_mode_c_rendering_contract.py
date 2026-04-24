"""Tests for the Mode C canonical rendering path."""

from __future__ import annotations

import unittest
from pathlib import Path

from tools.patch_loop import build_patch_loop_result, build_render_result


class ModeCRenderingContractTests(unittest.TestCase):
    def test_mode_c_patch_loop_requires_manual_template_render(self):
        render = build_render_result(
            "C",
            {"ticker": "AAPL", "output_mode": "C", "report_path": "output/reports/AAPL_C_EN_2026-04-24.html"},
            "output/runs/20260424T000000Z_AAPL_C/AAPL/analysis-result.json",
            repo_root=Path.cwd(),
        )

        self.assertTrue(render["required"])
        self.assertEqual(render["status"], "manual_render_required")
        self.assertEqual(render["engine"], "html-template-manual")
        self.assertIn("render-dashboard.py is eval-only", " ".join(render["notes"]))

    def test_manual_mode_c_render_blocks_patch_loop_delivery_ready(self):
        loop_result = build_patch_loop_result(
            patch_plan={
                "ticker": "AAPL",
                "output_mode": "C",
                "run_context": {
                    "run_id": "20260424T000000Z_AAPL_C",
                    "artifact_root": "output/runs/20260424T000000Z_AAPL_C/AAPL",
                    "ticker": "AAPL",
                },
            },
            analysis_patch={},
            final_quality_report={
                "overall_result": "PASS",
                "delivery_gate": {
                    "result": "PASS",
                    "ready_for_delivery": True,
                    "blocking_items": [],
                    "non_blocking_items": [],
                    "historical_only_items": [],
                },
            },
            next_patch_plan={
                "pending_fix_count": 0,
                "ready_for_redelivery": True,
                "loop_state": "ready_for_delivery",
            },
            render={
                "required": True,
                "status": "manual_render_required",
                "engine": "html-template-manual",
                "report_output_path": "output/reports/AAPL_C_EN_2026-04-24.html",
            },
            recheck={"status": "not_run"},
            patch_plan_path="output/runs/20260424T000000Z_AAPL_C/AAPL/patch-plan.json",
            analysis_patch_path="output/runs/20260424T000000Z_AAPL_C/AAPL/analysis-patch.json",
            analysis_result_path="output/runs/20260424T000000Z_AAPL_C/AAPL/analysis-result.json",
            quality_report_path="output/runs/20260424T000000Z_AAPL_C/AAPL/quality-report.json",
            next_patch_plan_path="output/runs/20260424T000000Z_AAPL_C/AAPL/patch-plan.json",
        )

        self.assertFalse(loop_result["quality_gate"]["delivery_ready"])


if __name__ == "__main__":
    unittest.main()
