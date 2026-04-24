"""Tests for pointer-only latest.json snapshot persistence."""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SNAPSHOT_MANAGER = ROOT / ".claude" / "skills" / "data-manager" / "scripts" / "snapshot-manager.py"
DELTA_COMPARATOR = ROOT / ".claude" / "skills" / "data-manager" / "scripts" / "delta-comparator.py"


def sample_analysis(ticker: str, run_id: str, analysis_date: str, price: float, rr_score: float) -> dict:
    return {
        "ticker": ticker,
        "market": "US",
        "data_mode": "standard",
        "output_mode": "A",
        "analysis_date": analysis_date,
        "price_at_analysis": price,
        "currency": "USD",
        "run_context": {
            "run_id": run_id,
            "artifact_root": f"output/runs/{run_id}/{ticker}",
            "ticker": ticker,
        },
        "key_metrics": {
            "pe_ratio": {
                "value": 20.0,
                "grade": "B",
                "sources": ["test"],
            }
        },
        "scenarios": {
            "bull": {"target": price * 1.3, "return_pct": 30, "probability": 0.25, "key_assumption": "Upside case"},
            "base": {"target": price * 1.1, "return_pct": 10, "probability": 0.50, "key_assumption": "Base case"},
            "bear": {"target": price * 0.8, "return_pct": -20, "probability": 0.25, "key_assumption": "Downside case"},
        },
        "rr_score": rr_score,
        "verdict": "neutral",
        "top_risks": ["test risk"],
        "upcoming_catalysts": [{"date": "2099-01-01", "event": "test catalyst"}],
    }


def run_json(command: list[str]) -> dict:
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=True)
    return json.loads(result.stdout)


class SnapshotPointerTests(unittest.TestCase):
    def test_save_writes_pointer_latest_and_get_resolves_full_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            run_dir = tmp_path / "runs" / "run-a" / "AAPL"
            run_dir.mkdir(parents=True)
            analysis_path = run_dir / "analysis-result.json"
            analysis_path.write_text(
                json.dumps(sample_analysis("AAPL", "run-a", "2026-04-24", 100.0, 6.5)),
                encoding="utf-8",
            )
            (run_dir / "quality-report.json").write_text(json.dumps({"status": "PASS"}), encoding="utf-8")

            save_result = run_json([
                sys.executable,
                str(SNAPSHOT_MANAGER),
                "save",
                "--ticker",
                "AAPL",
                "--data-file",
                str(analysis_path),
                "--data-root",
                str(tmp_path / "data"),
                "--skip-validation",
            ])

            latest_path = tmp_path / "data" / "AAPL" / "latest.json"
            latest = json.loads(latest_path.read_text(encoding="utf-8"))
            self.assertEqual(latest["kind"], "stock-analysis.latest-snapshot-pointer")
            self.assertEqual(latest["latest_snapshot_id"], save_result["snapshot_id"])
            self.assertIn("analysis_result", latest["refs"])
            self.assertIn("quality_report", latest["refs"])
            self.assertNotIn("scenarios", latest)

            snapshot_path = pathlib.Path(save_result["snapshot_path"])
            self.assertTrue(snapshot_path.exists())
            self.assertEqual(snapshot_path.parent.name, save_result["snapshot_id"])

            loaded = run_json([
                sys.executable,
                str(SNAPSHOT_MANAGER),
                "get",
                "--ticker",
                "AAPL",
                "--date",
                "latest",
                "--data-root",
                str(tmp_path / "data"),
            ])
            self.assertEqual(loaded["ticker"], "AAPL")
            self.assertIn("scenarios", loaded)
            self.assertEqual(loaded["rr_score"], 6.5)

            listed = run_json([
                sys.executable,
                str(SNAPSHOT_MANAGER),
                "list",
                "--ticker",
                "AAPL",
                "--data-root",
                str(tmp_path / "data"),
            ])
            self.assertEqual(listed["snapshots"][0]["snapshot_id"], save_result["snapshot_id"])
            self.assertEqual(listed["snapshots"][0]["storage"], "snapshot_dir")

    def test_get_latest_keeps_legacy_full_snapshot_compatibility(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_root = pathlib.Path(tmp) / "data"
            ticker_dir = data_root / "MSFT"
            ticker_dir.mkdir(parents=True)
            legacy = sample_analysis("MSFT", "legacy-run", "2026-04-20", 200.0, 7.1)
            (ticker_dir / "latest.json").write_text(json.dumps(legacy), encoding="utf-8")

            loaded = run_json([
                sys.executable,
                str(SNAPSHOT_MANAGER),
                "get",
                "--ticker",
                "MSFT",
                "--date",
                "latest",
                "--data-root",
                str(data_root),
            ])
            self.assertEqual(loaded["ticker"], "MSFT")
            self.assertEqual(loaded["analysis_date"], "2026-04-20")
            self.assertIn("scenarios", loaded)

    def test_delta_comparator_resolves_pointer_latest_and_snapshot_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            data_root = tmp_path / "data"

            for run_id, analysis_date, price, rr_score in (
                ("run-old", "2026-04-01", 100.0, 5.0),
                ("run-new", "2026-04-24", 112.0, 6.0),
            ):
                run_dir = tmp_path / "runs" / run_id / "AAPL"
                run_dir.mkdir(parents=True)
                analysis_path = run_dir / "analysis-result.json"
                analysis_path.write_text(
                    json.dumps(sample_analysis("AAPL", run_id, analysis_date, price, rr_score)),
                    encoding="utf-8",
                )
                run_json([
                    sys.executable,
                    str(SNAPSHOT_MANAGER),
                    "save",
                    "--ticker",
                    "AAPL",
                    "--data-file",
                    str(analysis_path),
                    "--data-root",
                    str(data_root),
                    "--skip-validation",
                ])

            delta = run_json([
                sys.executable,
                str(DELTA_COMPARATOR),
                "compare",
                "--ticker",
                "AAPL",
                "--old-date",
                "2026-04-01",
                "--new-date",
                "latest",
                "--data-root",
                str(data_root),
            ])
            self.assertEqual(delta["old_date"], "2026-04-01")
            self.assertEqual(delta["new_date"], "2026-04-24")
            self.assertEqual(delta["price_change"]["pct"], 12.0)


if __name__ == "__main__":
    unittest.main()
