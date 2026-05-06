"""Phase B — Auto Delta Mode: tests for delta-comparator extensions.

Verifies:
1. Two snapshots → JSON output includes a `delta_payload` block matching the
   structured schema (rr_score, verdict, base_target, weighted_fair_value,
   risk/catalyst additions/removals, prev/current dates).
2. HTML format flag produces a banner with all required field markers.
3. Markdown format flag produces a quote-block banner.
4. `--no-delta` flag suppresses output (returns empty/skip).
5. Single snapshot (no prior) → graceful skip status, exit 0.
6. `--ticker T --old-date latest --new-date latest` auto-discovers prev/curr
   from the snapshots directory (most recent two snapshots).
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SNAPSHOT_MANAGER = ROOT / ".claude" / "skills" / "data-manager" / "scripts" / "snapshot-manager.py"
DELTA_COMPARATOR = ROOT / ".claude" / "skills" / "data-manager" / "scripts" / "delta-comparator.py"


def sample_analysis(
    ticker: str,
    run_id: str,
    analysis_date: str,
    price: float,
    rr_score: float,
    verdict: str = "관찰",
    base_target: float = 110.0,
    weighted_fair_value: float | None = None,
    top_risks: list | None = None,
    upcoming_catalysts: list | None = None,
) -> dict:
    return {
        "ticker": ticker,
        "market": "US",
        "data_mode": "standard",
        "output_mode": "C",
        "output_language": "ko",
        "analysis_date": analysis_date,
        "price_at_analysis": price,
        "currency": "USD",
        "run_context": {
            "run_id": run_id,
            "artifact_root": f"output/runs/{run_id}/{ticker}",
            "ticker": ticker,
        },
        "key_metrics": {
            "pe_ratio": {"value": 20.0, "grade": "B", "sources": ["test"]}
        },
        "scenarios": {
            "bull": {"target": price * 1.3, "return_pct": 30, "probability": 0.25, "key_assumption": "Upside"},
            "base": {"target": base_target, "return_pct": 10, "probability": 0.50, "key_assumption": "Base"},
            "bear": {"target": price * 0.8, "return_pct": -20, "probability": 0.25, "key_assumption": "Downside"},
        },
        "valuation_bridge": (
            {"weighted_fair_value": weighted_fair_value, "currency": "USD"}
            if weighted_fair_value is not None
            else {}
        ),
        "rr_score": rr_score,
        "verdict": verdict,
        "top_risks": top_risks or ["기존 리스크"],
        "upcoming_catalysts": upcoming_catalysts or [
            {"date": "2099-01-01", "event": "기존 카탈리스트"}
        ],
    }


def run_subprocess(command: list[str], env: dict[str, str] | None = None, check: bool = True) -> subprocess.CompletedProcess:
    run_env = None if env is None else {**os.environ, **env}
    return subprocess.run(command, cwd=ROOT, env=run_env, text=True, capture_output=True, check=check)


def run_json(command: list[str], env: dict[str, str] | None = None) -> dict:
    result = run_subprocess(command, env=env, check=True)
    return json.loads(result.stdout)


def save_snapshot(data_root: pathlib.Path, tmp_path: pathlib.Path, ticker: str, run_id: str, analysis: dict) -> dict:
    run_dir = tmp_path / "runs" / run_id / ticker
    run_dir.mkdir(parents=True, exist_ok=True)
    analysis_path = run_dir / "analysis-result.json"
    analysis_path.write_text(json.dumps(analysis), encoding="utf-8")
    (run_dir / "quality-report.json").write_text(json.dumps({"status": "PASS"}), encoding="utf-8")
    return run_json([
        sys.executable,
        str(SNAPSHOT_MANAGER),
        "save",
        "--ticker",
        ticker,
        "--data-file",
        str(analysis_path),
        "--data-root",
        str(data_root),
        "--skip-validation",
    ])


class DeltaAutoModeTests(unittest.TestCase):
    def test_json_format_includes_structured_delta_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            data_root = tmp_path / "data"

            old_analysis = sample_analysis(
                "AAPL", "run-old", "2026-04-15", 100.0, 1.42,
                verdict="관찰", base_target=385.0, weighted_fair_value=320.0,
                top_risks=["기존 리스크"],
                upcoming_catalysts=[{"date": "2026-08-01", "event": "Q3 실적"}],
            )
            new_analysis = sample_analysis(
                "AAPL", "run-new", "2026-05-06", 110.0, 1.69,
                verdict="관찰", base_target=418.0, weighted_fair_value=346.84,
                top_risks=["기존 리스크", "AI Capex 회수 지연"],
                upcoming_catalysts=[
                    {"date": "2026-08-01", "event": "Q3 실적"},
                    {"date": "2026-12-01", "event": "DC Circuit 항소심 결정"},
                ],
            )
            save_snapshot(data_root, tmp_path, "AAPL", "run-old", old_analysis)
            save_snapshot(data_root, tmp_path, "AAPL", "run-new", new_analysis)

            payload = run_json([
                sys.executable,
                str(DELTA_COMPARATOR),
                "compare",
                "--ticker",
                "AAPL",
                "--old-date",
                "2026-04-15",
                "--new-date",
                "latest",
                "--data-root",
                str(data_root),
                "--format",
                "json",
            ])

            self.assertIn("delta_payload", payload)
            dp = payload["delta_payload"]
            self.assertEqual(dp["prev_date"], "2026-04-15")
            self.assertEqual(dp["curr_date"], "2026-05-06")
            self.assertEqual(dp["rr_score"]["prev"], 1.42)
            self.assertEqual(dp["rr_score"]["curr"], 1.69)
            self.assertIn("delta", dp["rr_score"])
            self.assertIn("delta_pct", dp["rr_score"])
            self.assertEqual(dp["verdict"]["prev"], "관찰")
            self.assertEqual(dp["verdict"]["curr"], "관찰")
            self.assertFalse(dp["verdict"]["changed"])
            self.assertEqual(dp["base_target"]["prev"], 385.0)
            self.assertEqual(dp["base_target"]["curr"], 418.0)
            self.assertEqual(dp["base_target"]["currency"], "USD")
            self.assertEqual(dp["weighted_fair_value"]["prev"], 320.0)
            self.assertEqual(dp["weighted_fair_value"]["curr"], 346.84)
            self.assertIn("AI Capex 회수 지연", dp["new_risks"])
            self.assertEqual(dp["removed_risks"], [])
            new_event_titles = " ".join(
                c["event"] if isinstance(c, dict) else str(c)
                for c in dp["new_catalysts"]
            )
            self.assertIn("DC Circuit", new_event_titles)
            self.assertEqual(dp["removed_catalysts"], [])

    def test_html_format_renders_banner_with_required_markers(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            data_root = tmp_path / "data"
            save_snapshot(
                data_root, tmp_path, "AAPL", "run-old",
                sample_analysis(
                    "AAPL", "run-old", "2026-04-15", 100.0, 1.42,
                    base_target=385.0, weighted_fair_value=320.0,
                ),
            )
            save_snapshot(
                data_root, tmp_path, "AAPL", "run-new",
                sample_analysis(
                    "AAPL", "run-new", "2026-05-06", 110.0, 1.69,
                    base_target=418.0, weighted_fair_value=346.84,
                    top_risks=["기존 리스크", "AI Capex 회수 지연"],
                ),
            )

            result = run_subprocess([
                sys.executable,
                str(DELTA_COMPARATOR),
                "compare",
                "--ticker",
                "AAPL",
                "--old-date",
                "2026-04-15",
                "--new-date",
                "latest",
                "--data-root",
                str(data_root),
                "--format",
                "html",
            ])

            html_text = result.stdout
            self.assertIn("delta-banner", html_text)
            self.assertIn("R/R Score", html_text)
            self.assertIn("1.42", html_text)
            self.assertIn("1.69", html_text)
            self.assertIn("2026-04-15", html_text)
            self.assertIn("2026-05-06", html_text)
            # Risk additions surfaced
            self.assertIn("AI Capex", html_text)
            # Banner should be a <section> with the delta-banner class so the
            # renderers can drop it in directly above their first section.
            self.assertIn("<section", html_text)

    def test_markdown_format_renders_quote_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            data_root = tmp_path / "data"
            save_snapshot(
                data_root, tmp_path, "AAPL", "run-old",
                sample_analysis("AAPL", "run-old", "2026-04-15", 100.0, 1.42, base_target=385.0),
            )
            save_snapshot(
                data_root, tmp_path, "AAPL", "run-new",
                sample_analysis("AAPL", "run-new", "2026-05-06", 110.0, 1.69, base_target=418.0),
            )

            result = run_subprocess([
                sys.executable,
                str(DELTA_COMPARATOR),
                "compare",
                "--ticker",
                "AAPL",
                "--old-date",
                "2026-04-15",
                "--new-date",
                "latest",
                "--data-root",
                str(data_root),
                "--format",
                "markdown",
            ])
            md_text = result.stdout
            # Markdown uses a quote-block banner
            self.assertIn("> ", md_text)
            self.assertIn("R/R Score", md_text)
            self.assertIn("2026-04-15", md_text)
            self.assertIn("2026-05-06", md_text)

    def test_no_delta_flag_suppresses_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            data_root = tmp_path / "data"
            save_snapshot(
                data_root, tmp_path, "AAPL", "run-old",
                sample_analysis("AAPL", "run-old", "2026-04-15", 100.0, 1.42),
            )
            save_snapshot(
                data_root, tmp_path, "AAPL", "run-new",
                sample_analysis("AAPL", "run-new", "2026-05-06", 110.0, 1.69),
            )

            result = run_subprocess([
                sys.executable,
                str(DELTA_COMPARATOR),
                "compare",
                "--ticker",
                "AAPL",
                "--old-date",
                "latest",
                "--new-date",
                "latest",
                "--data-root",
                str(data_root),
                "--format",
                "json",
                "--no-delta",
            ])
            self.assertEqual(result.returncode, 0)
            payload = json.loads(result.stdout)
            self.assertEqual(payload.get("status"), "skipped")
            self.assertEqual(payload.get("reason"), "no_delta_flag")

    def test_single_snapshot_graceful_skip(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            data_root = tmp_path / "data"
            save_snapshot(
                data_root, tmp_path, "AAPL", "run-only",
                sample_analysis("AAPL", "run-only", "2026-05-06", 110.0, 1.69),
            )

            result = run_subprocess([
                sys.executable,
                str(DELTA_COMPARATOR),
                "compare",
                "--ticker",
                "AAPL",
                "--old-date",
                "latest",
                "--new-date",
                "latest",
                "--data-root",
                str(data_root),
                "--format",
                "json",
            ], check=False)
            self.assertEqual(result.returncode, 0)
            payload = json.loads(result.stdout)
            self.assertEqual(payload.get("status"), "skipped")
            self.assertIn("reason", payload)
            self.assertIn("no_prior_snapshot", payload.get("reason", ""))

    def test_auto_discovery_resolves_prev_and_curr_when_both_latest(self):
        """When both --old-date and --new-date are 'latest', auto-discover the
        two most recent distinct snapshots."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            data_root = tmp_path / "data"
            save_snapshot(
                data_root, tmp_path, "AAPL", "run-1",
                sample_analysis("AAPL", "run-1", "2026-04-15", 100.0, 1.42, base_target=385.0),
            )
            save_snapshot(
                data_root, tmp_path, "AAPL", "run-2",
                sample_analysis("AAPL", "run-2", "2026-05-06", 110.0, 1.69, base_target=418.0),
            )

            payload = run_json([
                sys.executable,
                str(DELTA_COMPARATOR),
                "compare",
                "--ticker",
                "AAPL",
                "--old-date",
                "latest",
                "--new-date",
                "latest",
                "--data-root",
                str(data_root),
                "--format",
                "json",
            ])
            dp = payload["delta_payload"]
            self.assertEqual(dp["prev_date"], "2026-04-15")
            self.assertEqual(dp["curr_date"], "2026-05-06")


if __name__ == "__main__":
    unittest.main()
