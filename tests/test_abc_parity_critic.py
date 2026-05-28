from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from scripts.parity.critic import build_critic_handoff
from tests.test_abc_parity_calculations import write_mock_yfinance
from tools.artifact_validation import validate_artifact_file

REPO_ROOT = Path(__file__).resolve().parents[1]


def run_parity(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    return subprocess.run(
        [sys.executable, "scripts/run_abc_parity.py", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=merged_env,
    )


def ensure_critic_fixture_run(run_id: str) -> Path:
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
    result = run_parity(
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
        "--critic-only",
        "--reuse-collected",
        "--skip-network",
        env={"ANALYST_BACKEND": "fixture"},
    )
    assert result.returncode == 0, result.stderr
    return ticker_root


def ensure_mode_a_critic_fixture_run(run_id: str) -> Path:
    collect = run_parity(
        "--ticker",
        "AAPL",
        "--mode",
        "A",
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
    result = run_parity(
        "--ticker",
        "AAPL",
        "--mode",
        "A",
        "--lang",
        "en",
        "--market",
        "US",
        "--run-id",
        run_id,
        "--critic-only",
        "--reuse-collected",
        "--skip-network",
        env={"ANALYST_BACKEND": "fixture"},
    )
    assert result.returncode == 0, result.stderr
    return ticker_root


def test_runner_critic_only_writes_delivery_ready_quality_report_and_summary() -> None:
    run_id = "pytest_abc_parity_critic_fixture_AAPL_C"
    ensure_critic_fixture_run(run_id)
    run_metadata = json.loads((REPO_ROOT / "output" / "runs" / run_id / "run-metadata.json").read_text(encoding="utf-8"))
    critic = run_metadata["critic_results"][0]
    quality_path = REPO_ROOT / critic["quality_report_path"]
    summary_path = REPO_ROOT / run_metadata["abc_parity_summary_path"]
    quality = json.loads(quality_path.read_text(encoding="utf-8"))
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    assert critic["status"] == "PASS"
    assert critic["delivery_ready"] is True
    assert critic["patch_status"] == "not_needed"
    assert quality["delivery_gate"]["ready_for_delivery"] is True
    assert validate_artifact_file(quality_path, "quality-report", base_dir=REPO_ROOT)["valid"]
    assert summary["overall_status"] == "PASS"


def test_runner_critic_only_mode_a_uses_render_gate() -> None:
    run_id = "pytest_abc_parity_critic_fixture_AAPL_A"
    ensure_mode_a_critic_fixture_run(run_id)
    run_metadata = json.loads((REPO_ROOT / "output" / "runs" / run_id / "run-metadata.json").read_text(encoding="utf-8"))
    critic = run_metadata["critic_results"][0]
    render = run_metadata["render_results"][0]
    quality_path = REPO_ROOT / critic["quality_report_path"]
    quality = json.loads(quality_path.read_text(encoding="utf-8"))

    assert render["status"] == "PASS"
    assert critic["status"] == "PASS"
    assert critic["delivery_ready"] is True
    assert quality["delivery_gate"]["ready_for_delivery"] is True
    assert quality["critic_review"]["overall"] == "PASS"
    assert (REPO_ROOT / render["render_report_path"]).exists()


def test_runner_reuse_stages_hits_stage_cache() -> None:
    run_id = "pytest_abc_parity_reuse_stages_AAPL_A"
    ticker_root = ensure_mode_a_critic_fixture_run(run_id)

    result = run_parity(
        "--ticker",
        "AAPL",
        "--mode",
        "A",
        "--lang",
        "en",
        "--market",
        "US",
        "--run-id",
        run_id,
        "--critic-only",
        "--reuse-collected",
        "--reuse-stages",
        "--skip-network",
        env={"ANALYST_BACKEND": "fixture"},
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    cache_hit_stages = {
        item["stage"]
        for item in payload["performance"]["stage_timings"]
        if item.get("cache_hit") is True
    }
    assert {"validation", "calculation", "analyst", "render", "critic"} <= cache_hit_stages
    assert payload["analyst_results"][0]["performance"]["cache"]["hit"] is True
    assert payload["critic_results"][0]["performance"]["cache"]["hit"] is True
    assert (ticker_root / "stage-cache.json").exists()


def test_peer_mini_fetch_all_fail_is_deliverable_with_flags() -> None:
    run_id = "pytest_abc_parity_peer_all_fail_AAPL_C"
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
    render = run_parity(
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
        "--render-only",
        "--reuse-collected",
        "--skip-network",
        env={"ANALYST_BACKEND": "fixture"},
    )
    assert render.returncode == 0, render.stderr
    (ticker_root / "peer-fetch-summary.json").write_text(
        json.dumps(
            {
                "schema_version": "abc-parity-peer-mini-fetch-summary-v1",
                "source": "peer_mini_fetch",
                "status": "failed",
                "tickers_requested": ["MSFT", "GOOGL", "META"],
                "tickers_collected": [],
                "tickers_failed": ["MSFT", "GOOGL", "META"],
                "exit_code": 1,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    result = build_critic_handoff(
        language="en",
        market="US",
        mode="C",
        run_id=run_id,
        ticker="AAPL",
    )
    quality = json.loads((ticker_root / "quality-report.json").read_text(encoding="utf-8"))
    peer_item = quality["items"]["peer_mini_fetch"]

    assert result.delivery_ready is True
    assert quality["overall_result"] == "PASS_WITH_FLAGS"
    assert quality["delivery_gate"]["ready_for_delivery"] is True
    assert quality["delivery_gate"]["result"] == "PASS"
    assert "peer_mini_fetch" in quality["delivery_gate"]["non_blocking_items"]
    assert peer_item["status"] == "PASS_WITH_FLAGS"
    assert peer_item["delivery_impact"] == "non_blocking_flag"
    assert validate_artifact_file(ticker_root / "quality-report.json", "quality-report", base_dir=REPO_ROOT)["valid"]


def test_critic_applies_one_patch_for_generic_thesis_and_rechecks() -> None:
    run_id = "pytest_abc_parity_critic_patch_AAPL_C"
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
    render = run_parity(
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
        "--render-only",
        "--reuse-collected",
        "--skip-network",
        env={"ANALYST_BACKEND": "fixture"},
    )
    assert render.returncode == 0, render.stderr

    analysis_path = ticker_root / "analysis-result.json"
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    analysis["thesis"] = "The company is attractive."
    analysis["sections"]["one_line_thesis"] = "The company is attractive."
    analysis["sections"]["variant_view_q1"] = "The company is attractive."
    analysis_path.write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")

    result = build_critic_handoff(
        language="en",
        market="US",
        mode="C",
        run_id=run_id,
        ticker="AAPL",
    )
    patched = json.loads(analysis_path.read_text(encoding="utf-8"))
    quality = json.loads((ticker_root / "quality-report.json").read_text(encoding="utf-8"))

    assert result.patch_status == "applied"
    assert result.delivery_ready is True
    assert "AAPL" in patched["thesis"]
    assert (ticker_root / "analysis-result.precritic.json").exists()
    assert quality["critic_review"]["recheck_count"] == 1
    assert quality["critic_review"]["overall"] == "PASS"


def test_eval_abc_parity_summarizes_critic_run() -> None:
    run_id = "pytest_abc_parity_critic_fixture_AAPL_C"
    ensure_critic_fixture_run(run_id)
    result = subprocess.run(
        [
            sys.executable,
            "scripts/eval_abc_parity.py",
            "--run-id",
            run_id,
            "--output-dir",
            "output/evals/pytest_abc_parity_critic_fixture_AAPL_C",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["overall_status"] == "PASS"
    assert payload["pass_count"] >= 1
    assert (REPO_ROOT / payload["summary_path"]).exists()
