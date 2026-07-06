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


def prepare_collected_fixture_run(run_id: str, *, language: str = "en") -> Path:
    collect = run_parity(
        "--ticker",
        "AAPL",
        "--mode",
        "C",
        "--lang",
        language,
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
    return ticker_root


def test_mode_c_entrypoint_offline_produces_passing_dashboard_when_fixture_allowed(monkeypatch, capsys):
    run_id = "pytest_run_mode_c_entrypoint_AAPL_C"
    ticker_root = prepare_collected_fixture_run(run_id)
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
            "--allow-fixture-delivery",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    report_path = Path(payload["report_path"])
    quality_path = ticker_root / "quality-report.json"
    tier2_path = ticker_root / "tier2-raw.json"
    quality = json.loads(quality_path.read_text(encoding="utf-8"))

    assert rc == 0
    assert payload["run_id"] == run_id
    assert payload["run_profile"] == "smoke"
    assert report_path.exists()
    assert report_path.stat().st_size > 40_000
    assert quality["delivery_gate"]["result"] == "PASS"
    assert quality["delivery_gate"]["ready_for_delivery"] is True
    assert quality["items"]["numeric_sanity"]["status"] == "PASS"
    assert quality["items"]["fixture_delivery_guard"]["status"] == "PASS_WITH_FLAGS"
    assert "fixture_delivery_guard" in quality["delivery_gate"]["non_blocking_items"]
    assert validate_artifact_file(tier2_path, "tier2-raw", base_dir=REPO_ROOT)["valid"]
    assert validate_artifact_file(quality_path, "quality-report", base_dir=REPO_ROOT)["valid"]


def test_mode_c_entrypoint_ko_smoke_publishes_localized_dashboard(monkeypatch, capsys):
    run_id = "pytest_run_mode_c_entrypoint_AAPL_C_ko"
    ticker_root = prepare_collected_fixture_run(run_id, language="ko")
    monkeypatch.setenv("ANALYST_BACKEND", "fixture")

    rc = run_main(
        [
            "--ticker",
            "AAPL",
            "--mode",
            "C",
            "--lang",
            "ko",
            "--market",
            "US",
            "--run-id",
            run_id,
            "--skip-network",
            "--reuse-collected",
            "--allow-fixture-delivery",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    report_path = Path(payload["report_path"])
    quality_path = Path(payload["quality_report_path"])
    render_path = ticker_root / "mode-c-dashboard.html"
    quality = json.loads(quality_path.read_text(encoding="utf-8"))
    html = report_path.read_text(encoding="utf-8")
    run_local_html = render_path.read_text(encoding="utf-8")

    assert rc == 0
    assert payload["run_id"] == run_id
    assert payload["run_profile"] == "smoke"
    assert payload["delivery_gate"] == "PASS"
    assert report_path.exists()
    assert render_path.exists()
    assert html == run_local_html
    assert quality_path == ticker_root / "quality-report.json"
    assert quality["delivery_gate"]["result"] == "PASS"
    assert quality["delivery_gate"]["ready_for_delivery"] is True
    assert quality["items"]["numeric_sanity"]["status"] == "PASS"
    assert quality["items"]["fixture_delivery_guard"]["status"] == "PASS_WITH_FLAGS"
    assert "fixture_delivery_guard" in quality["delivery_gate"]["non_blocking_items"]

    for expected in (
        "Mode C 심층 대시보드",
        "시나리오 밸류에이션",
        "투자 논점과 차별적 관점",
        "정밀 리스크 분석",
        "밸류에이션 지표",
        "DCF 밸류에이션",
        "애널리스트 커버리지",
        "재무 차트",
        "이익 품질 및 증거 게이트",
        "포트폴리오 전략",
        "출처 태그 클레임 부록",
        "면책 고지",
        "label: '매출'",
        "label: '영업이익'",
        "label: '잉여현금흐름'",
        "label: '강세 목표가'",
        "label: '기준 목표가'",
        "label: '약세 목표가'",
    ):
        assert expected in html

    for forbidden in (
        "Mode C Deep Dive Dashboard",
        "Investment Thesis & Variant View",
        "Precision Risk Analysis",
        "Charts & Trend Data",
        "Financial Detail Analysis",
        "Quality of Earnings & Evidence Gate",
        "Portfolio Strategy",
        "Source-Tagged Claims Appendix",
        ">Disclaimer<",
        "tracked metrics",
        "debate points",
        "deterministic rows",
        "target anchors",
        "scenario paths",
        "points max",
        "anchor points",
        "FRED series",
        "label: 'Revenue'",
        "label: 'Operating Income'",
        "label: 'Free Cash Flow'",
        "Bull Target",
        "Base Target",
        "Bear Target",
        "const개 분기",
        "/Users/",
    ):
        assert forbidden not in html

    assert validate_artifact_file(quality_path, "quality-report", base_dir=REPO_ROOT)["valid"]


def test_mode_c_entrypoint_codex_native_runs_without_fixture_allowance(monkeypatch, capsys):
    run_id = "pytest_run_mode_c_entrypoint_codex_native_AAPL_C_ko"
    ticker_root = prepare_collected_fixture_run(run_id, language="ko")
    monkeypatch.delenv("ANALYST_BACKEND", raising=False)

    rc = run_main(
        [
            "--ticker",
            "AAPL",
            "--mode",
            "C",
            "--lang",
            "ko",
            "--market",
            "US",
            "--run-id",
            run_id,
            "--skip-network",
            "--reuse-collected",
            "--analyst-backend",
            "codex_native",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    report_path = Path(payload["report_path"])
    quality_path = ticker_root / "quality-report.json"
    analysis_path = ticker_root / "analysis-result.json"
    quality = json.loads(quality_path.read_text(encoding="utf-8"))
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    html = report_path.read_text(encoding="utf-8")

    assert rc == 0
    assert payload["run_profile"] == "production"
    assert payload["delivery_gate"] == "PASS"
    assert report_path.exists()
    assert quality["delivery_gate"]["ready_for_delivery"] is True
    assert quality["items"]["fixture_delivery_guard"]["status"] == "PASS"
    assert quality["items"]["fixture_delivery_guard"]["backend_provider"] == "codex_native"
    assert "fixture_delivery_guard" not in quality["delivery_gate"]["blocking_items"]
    assert analysis["run_context"]["backend"]["provider"] == "codex_native"
    assert analysis["run_context"]["backend"]["usage"]["api_calls"] == 0
    assert analysis["run_context"]["fixture_backend"] is False
    assert "이익 품질 및 증거 게이트" in html
    assert "포트폴리오 전략" in html
    assert "출처 태그 클레임 부록" in html
    assert validate_artifact_file(analysis_path, "analysis-result", base_dir=REPO_ROOT)["valid"]
    assert validate_artifact_file(quality_path, "quality-report", base_dir=REPO_ROOT)["valid"]


def test_mode_c_entrypoint_blocks_fixture_without_explicit_allow(monkeypatch, capsys):
    run_id = "pytest_run_mode_c_entrypoint_blocks_fixture_AAPL_C"
    ticker_root = prepare_collected_fixture_run(run_id)
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
    quality_path = ticker_root / "quality-report.json"
    quality = json.loads(quality_path.read_text(encoding="utf-8"))

    assert rc == 1
    assert "quality gate" in payload["error"].lower()
    assert quality["items"]["fixture_delivery_guard"]["status"] == "FAIL"
    assert quality["delivery_gate"]["result"] == "BLOCKED"
    assert quality["delivery_gate"]["ready_for_delivery"] is False
    assert "fixture_delivery_guard" in quality["delivery_gate"]["blocking_items"]
    assert "fixture_delivery_guard" in quality["delivery_gate"]["terminal_blocking_items"]
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
