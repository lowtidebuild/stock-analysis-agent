from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.run_mode_c import main as run_main
from tests.test_abc_parity_calculations import write_mock_yfinance
from tools.artifact_validation import validate_artifact_file

REPO_ROOT = Path(__file__).resolve().parents[1]


def run_parity(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "scripts/run_abc_parity.py", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_mode_c_entrypoint_offline_produces_passing_dashboard(monkeypatch, capsys):
    run_id = "pytest_run_mode_c_entrypoint_AAPL_C"
    collect = run_parity(
        "--ticker",
        "AAPL",
        "--mode",
        "C",
        "--lang",
        "en",
        "--market",
        "US",
        "--run-id",
        run_id,
        "--collect-only",
        "--skip-network",
    )
    assert collect.returncode == 0, collect.stderr
    ticker_root = REPO_ROOT / "output" / "runs" / run_id / "AAPL"
    write_mock_yfinance(ticker_root)
    monkeypatch.setenv("ANALYST_BACKEND", "fixture")

    rc = run_main(
        [
            "--ticker",
            "AAPL",
            "--mode",
            "C",
            "--lang",
            "en",
            "--market",
            "US",
            "--run-id",
            run_id,
            "--skip-network",
            "--reuse-collected",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    report_path = Path(payload["report_path"])
    quality_path = ticker_root / "quality-report.json"
    tier2_path = ticker_root / "tier2-raw.json"
    quality = json.loads(quality_path.read_text(encoding="utf-8"))

    assert rc == 0
    assert payload["run_id"] == run_id
    assert report_path.exists()
    assert report_path.stat().st_size > 40_000
    assert quality["delivery_gate"]["result"] == "PASS"
    assert quality["delivery_gate"]["ready_for_delivery"] is True
    assert validate_artifact_file(tier2_path, "tier2-raw", base_dir=REPO_ROOT)["valid"]
    assert validate_artifact_file(quality_path, "quality-report", base_dir=REPO_ROOT)["valid"]


def test_mode_c_entrypoint_rejects_other_modes():
    rc = run_main(
        [
            "--ticker",
            "AAPL",
            "--mode",
            "A",
            "--lang",
            "en",
            "--market",
            "US",
            "--run-id",
            "pytest_run_mode_c_rejects_mode_a",
            "--skip-network",
        ]
    )

    assert rc == 2
