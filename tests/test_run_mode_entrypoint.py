from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.run_analysis import emit_legacy_web_runner_warning, main as legacy_run_main
from scripts.run_mode import main as run_main
from tests.test_abc_parity_comparison import prepare_mode_b_fixture_run, write_peer_yfinance
from tests.test_abc_parity_calculations import write_mock_yfinance
from tests.test_run_mode_c_entrypoint import prepare_collected_fixture_run, run_parity
from tools.artifact_validation import validate_artifact_file

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_run_analysis_legacy_warning_points_to_native_entrypoint(capsys):
    emit_legacy_web_runner_warning()

    captured = capsys.readouterr()

    assert captured.out == ""
    assert "deprecated" in captured.err.lower()
    assert "--native" in captured.err
    assert "scripts/run_mode.py" in captured.err


def prepare_collected_mode_a_run(
    run_id: str,
    *,
    language: str = "en",
    market: str = "US",
    ticker: str = "AAPL",
    yfinance_writer: Any | None = None,
) -> Path:
    collect = run_parity(
        "--ticker",
        ticker,
        "--mode",
        "A",
        "--lang",
        language,
        "--market",
        market,
        "--run-id",
        run_id,
        "--collect-only",
        "--skip-network",
    )
    assert collect.returncode == 0, collect.stderr
    ticker_root = REPO_ROOT / "output" / "runs" / run_id / ticker
    if yfinance_writer is None:
        write_mock_yfinance(ticker_root)
    else:
        yfinance_writer(ticker_root)
    return ticker_root


def write_kr_yfinance_fixture(
    ticker_root: Path,
    *,
    fcf_b: float,
    market_cap_b: float,
    operating_margin_pct: float,
    price: float,
    revenue_b: float,
    revenue_growth_pct: float,
    target_mean: float,
    target_median: float,
    ticker: str,
) -> None:
    write_peer_yfinance(
        ticker_root,
        currency="KRW",
        market="KR",
        ticker=ticker,
        price=price,
        market_cap_b=market_cap_b,
        pe=18.0,
        ev_ebitda=8.5,
        revenue_b=revenue_b,
        revenue_growth_pct=revenue_growth_pct,
        operating_margin_pct=operating_margin_pct,
        fcf_b=fcf_b,
        target_mean=target_mean,
        target_median=target_median,
        target_high=target_median * 1.22,
        target_low=target_median * 0.72,
    )


def prepare_mixed_mode_b_fixture_run(run_id: str) -> Path:
    tickers = "AAPL,005930,000660"
    collect = run_parity(
        "--ticker",
        "AAPL",
        "--tickers",
        tickers,
        "--mode",
        "B",
        "--lang",
        "ko",
        "--market",
        "mixed",
        "--run-id",
        run_id,
        "--collect-only",
        "--skip-network",
    )
    assert collect.returncode == 0, collect.stderr
    run_root = REPO_ROOT / "output" / "runs" / run_id
    write_peer_yfinance(
        run_root / "AAPL",
        ticker="AAPL",
        price=200,
        market_cap_b=3000,
        pe=30,
        ev_ebitda=22,
        revenue_b=390,
        revenue_growth_pct=5,
        operating_margin_pct=30,
        fcf_b=72,
        target_mean=225,
        target_median=220,
        target_high=260,
        target_low=155,
    )
    write_kr_yfinance_fixture(
        run_root / "005930",
        ticker="005930",
        price=72_000,
        market_cap_b=430_000,
        revenue_b=300_000,
        revenue_growth_pct=14,
        operating_margin_pct=18,
        fcf_b=34_000,
        target_mean=88_000,
        target_median=86_000,
    )
    write_kr_yfinance_fixture(
        run_root / "000660",
        ticker="000660",
        price=225_000,
        market_cap_b=165_000,
        revenue_b=66_000,
        revenue_growth_pct=28,
        operating_margin_pct=24,
        fcf_b=9_500,
        target_mean=270_000,
        target_median=265_000,
    )
    return run_root


def test_run_mode_dispatches_mode_a_codex_native(monkeypatch, capsys):
    run_id = "pytest_run_mode_entrypoint_codex_native_AAPL_A"
    ticker_root = prepare_collected_mode_a_run(run_id)
    monkeypatch.delenv("ANALYST_BACKEND", raising=False)

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
            run_id,
            "--skip-network",
            "--reuse-collected",
            "--analyst-backend",
            "codex_native",
            "--allow-deterministic-delivery",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    quality = json.loads((ticker_root / "quality-report.json").read_text(encoding="utf-8"))
    analysis = json.loads((ticker_root / "analysis-result.json").read_text(encoding="utf-8"))
    report_path = Path(payload["report_path"])
    html = report_path.read_text(encoding="utf-8")

    assert rc == 0
    assert payload["schema_version"] == "run-mode-entry-result-v1"
    assert payload["mode"] == "A"
    assert payload["ticker"] == "AAPL"
    assert payload["backend_provider"] == "codex_native"
    assert payload["run_profile"] == "deterministic"
    assert payload["delivery_gate"] == "PASS"
    assert report_path.exists()
    assert report_path.name.startswith("AAPL_A_en_")
    assert (ticker_root / "mode-a-briefing.html").exists()
    assert quality["delivery_gate"]["ready_for_delivery"] is True
    assert quality["items"]["fixture_delivery_guard"]["status"] == "PASS_WITH_FLAGS"
    assert "fixture_delivery_guard" in quality["delivery_gate"]["non_blocking_items"]
    assert analysis["run_context"]["backend"]["provider"] == "codex_native"
    assert analysis["run_context"]["backend"]["usage"]["api_calls"] == 0
    assert analysis["run_context"]["run_profile"] == "deterministic"
    assert analysis["run_context"]["verdict_provenance"] == "deterministic_rule"
    assert "deterministic template without LLM analysis" in html
    assert validate_artifact_file(ticker_root / "quality-report.json", "quality-report", base_dir=REPO_ROOT)["valid"]


def test_run_mode_dispatches_mode_a_kr_auto_codex_native(monkeypatch, capsys):
    run_id = "pytest_run_mode_entrypoint_codex_native_005930_A_ko"
    ticker_root = prepare_collected_mode_a_run(
        run_id,
        language="ko",
        market="auto",
        ticker="005930",
        yfinance_writer=lambda root: write_kr_yfinance_fixture(
            root,
            ticker="005930",
            price=72_000,
            market_cap_b=430_000,
            revenue_b=300_000,
            revenue_growth_pct=14,
            operating_margin_pct=18,
            fcf_b=34_000,
            target_mean=88_000,
            target_median=86_000,
        ),
    )
    monkeypatch.delenv("ANALYST_BACKEND", raising=False)

    rc = run_main(
        [
            "--ticker",
            "005930",
            "--mode",
            "A",
            "--lang",
            "ko",
            "--market",
            "auto",
            "--run-id",
            run_id,
            "--skip-network",
            "--reuse-collected",
            "--analyst-backend",
            "codex_native",
            "--allow-deterministic-delivery",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    request = json.loads((REPO_ROOT / "output" / "runs" / run_id / "request.json").read_text(encoding="utf-8"))
    source_summary = json.loads((ticker_root / "source-collection-summary.json").read_text(encoding="utf-8"))
    validated = json.loads((ticker_root / "validated-data.json").read_text(encoding="utf-8"))
    analysis = json.loads((ticker_root / "analysis-result.json").read_text(encoding="utf-8"))

    assert rc == 0
    assert payload["schema_version"] == "run-mode-entry-result-v1"
    assert payload["mode"] == "A"
    assert payload["ticker"] == "005930"
    assert payload["backend_provider"] == "codex_native"
    assert payload["run_profile"] == "deterministic"
    assert payload["delivery_gate"] == "PASS"
    report_path = Path(payload["report_path"])
    html = report_path.read_text(encoding="utf-8")
    assert report_path.name.startswith("005930_A_ko_")
    assert request["market"] == "KR"
    assert source_summary["market"] == "KR"
    assert validated["market"] == "KR"
    assert validated["currency"] == "KRW"
    assert validated["source_profile"] == "yfinance_fallback"
    assert analysis["currency"] == "KRW"
    assert analysis["run_context"]["backend"]["usage"]["api_calls"] == 0
    assert analysis["run_context"]["run_profile"] == "deterministic"
    assert "LLM 분석 없이 검증 지표 기반 결정론적 템플릿" in html


def test_run_analysis_native_delegates_mode_a_to_unified_entrypoint(monkeypatch, capsys):
    run_id = "pytest_run_analysis_native_delegates_AAPL_A"
    ticker_root = prepare_collected_mode_a_run(run_id)
    monkeypatch.delenv("ANALYST_BACKEND", raising=False)

    rc = legacy_run_main(
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
            run_id,
            "--native",
            "--skip-network",
            "--reuse-collected",
            "--analyst-backend",
            "codex_native",
            "--allow-deterministic-delivery",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    quality = json.loads((ticker_root / "quality-report.json").read_text(encoding="utf-8"))
    analysis = json.loads((ticker_root / "analysis-result.json").read_text(encoding="utf-8"))

    assert rc == 0
    assert "deprecated" not in captured.err.lower()
    assert payload["schema_version"] == "run-mode-entry-result-v1"
    assert payload["mode"] == "A"
    assert payload["backend_provider"] == "codex_native"
    assert Path(payload["report_path"]).exists()
    assert payload["run_profile"] == "deterministic"
    assert quality["items"]["fixture_delivery_guard"]["status"] == "PASS_WITH_FLAGS"
    assert analysis["run_context"]["backend"]["provider"] == "codex_native"


def test_run_mode_dispatches_mode_c_codex_native(monkeypatch, capsys):
    run_id = "pytest_run_mode_entrypoint_codex_native_AAPL_C_ko"
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
            "--allow-deterministic-delivery",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    quality = json.loads((ticker_root / "quality-report.json").read_text(encoding="utf-8"))
    analysis = json.loads((ticker_root / "analysis-result.json").read_text(encoding="utf-8"))

    assert rc == 0
    assert payload["schema_version"] == "run-mode-entry-result-v1"
    assert payload["mode"] == "C"
    assert payload["ticker"] == "AAPL"
    assert payload["backend_provider"] == "codex_native"
    assert payload["run_profile"] == "deterministic"
    assert payload["delivery_gate"] == "PASS"
    report_path = Path(payload["report_path"])
    html = report_path.read_text(encoding="utf-8")
    assert report_path.exists()
    assert quality["delivery_gate"]["ready_for_delivery"] is True
    assert quality["items"]["fixture_delivery_guard"]["status"] == "PASS_WITH_FLAGS"
    assert "fixture_delivery_guard" in quality["delivery_gate"]["non_blocking_items"]
    assert analysis["run_context"]["backend"]["provider"] == "codex_native"
    assert analysis["run_context"]["backend"]["usage"]["api_calls"] == 0
    assert analysis["run_context"]["run_profile"] == "deterministic"
    assert "LLM 분석 없이 검증 지표 기반 결정론적 템플릿" in html


def test_run_mode_blocks_mode_a_fixture_without_explicit_allow(monkeypatch, capsys):
    run_id = "pytest_run_mode_entrypoint_blocks_fixture_AAPL_A"
    ticker_root = prepare_collected_mode_a_run(run_id)
    monkeypatch.delenv("ANALYST_BACKEND", raising=False)

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
            run_id,
            "--skip-network",
            "--reuse-collected",
            "--analyst-backend",
            "fixture",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    quality = json.loads((ticker_root / "quality-report.json").read_text(encoding="utf-8"))

    assert rc == 1
    assert payload["mode"] == "A"
    assert "quality gate" in payload["error"].lower()
    assert quality["items"]["fixture_delivery_guard"]["status"] == "FAIL"
    assert quality["delivery_gate"]["ready_for_delivery"] is False
    assert "fixture_delivery_guard" in quality["delivery_gate"]["blocking_items"]
    assert validate_artifact_file(ticker_root / "quality-report.json", "quality-report", base_dir=REPO_ROOT)["valid"]


def test_run_mode_b_requires_tickers(capsys):
    rc = run_main(
        [
            "--ticker",
            "AAPL",
            "--mode",
            "B",
            "--lang",
            "ko",
            "--market",
            "US",
            "--run-id",
            "pytest_run_mode_b_requires_tickers",
            "--skip-network",
            "--analyst-backend",
            "codex_native",
        ]
    )

    payload = json.loads(capsys.readouterr().out)

    assert rc == 2
    assert payload["mode"] == "B"
    assert "requires --tickers" in payload["error"]


def test_run_mode_dispatches_mode_b_codex_native(monkeypatch, capsys):
    run_id = "pytest_run_mode_entrypoint_codex_native_GOOGL_MSFT_AAPL_B"
    run_root = prepare_mode_b_fixture_run(run_id)
    monkeypatch.delenv("ANALYST_BACKEND", raising=False)

    rc = run_main(
        [
            "--ticker",
            "GOOGL",
            "--tickers",
            "GOOGL,MSFT,AAPL",
            "--mode",
            "B",
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
            "--allow-deterministic-delivery",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    comparison_dir = run_root / "comparison"
    comparison_quality = json.loads(
        (comparison_dir / "comparison-quality-report.json").read_text(encoding="utf-8")
    )

    assert rc == 0
    assert payload["schema_version"] == "run-mode-entry-result-v1"
    assert payload["mode"] == "B"
    assert payload["ticker"] == "GOOGL"
    assert payload["tickers"] == ["GOOGL", "MSFT", "AAPL"]
    assert payload["backend_provider"] == "codex_native"
    assert payload["run_profile"] == "deterministic"
    assert payload["delivery_gate"] == "PASS"
    assert payload["best_pick"] in {"GOOGL", "MSFT", "AAPL"}
    report_html = Path(payload["report_path"]).read_text(encoding="utf-8")
    comparison_html = Path(payload["comparison_report_path"]).read_text(encoding="utf-8")
    assert "LLM 분석 없이 검증 지표 기반 결정론적 템플릿" in comparison_html
    assert "LLM 분석 없이 검증 지표 기반 결정론적 템플릿" in report_html
    assert Path(payload["quality_report_path"]) == comparison_dir / "comparison-quality-report.json"
    assert comparison_quality["delivery_gate"]["ready_for_delivery"] is True
    for ticker in ["GOOGL", "MSFT", "AAPL"]:
        ticker_root = run_root / ticker
        quality = json.loads((ticker_root / "quality-report.json").read_text(encoding="utf-8"))
        analysis = json.loads((ticker_root / "analysis-result.json").read_text(encoding="utf-8"))
        assert quality["items"]["fixture_delivery_guard"]["status"] == "PASS_WITH_FLAGS"
        assert quality["delivery_gate"]["ready_for_delivery"] is True
        assert "fixture_delivery_guard" in quality["delivery_gate"]["non_blocking_items"]
        assert analysis["run_context"]["backend"]["provider"] == "codex_native"
        assert analysis["run_context"]["backend"]["usage"]["api_calls"] == 0
        assert analysis["run_context"]["run_profile"] == "deterministic"
        assert validate_artifact_file(ticker_root / "quality-report.json", "quality-report", base_dir=REPO_ROOT)[
            "valid"
        ]


def test_run_mode_dispatches_mode_b_mixed_market_codex_native(monkeypatch, capsys):
    run_id = "pytest_run_mode_entrypoint_codex_native_AAPL_005930_000660_B_mixed"
    run_root = prepare_mixed_mode_b_fixture_run(run_id)
    monkeypatch.delenv("ANALYST_BACKEND", raising=False)

    rc = run_main(
        [
            "--ticker",
            "AAPL",
            "--tickers",
            "AAPL,005930,000660",
            "--mode",
            "B",
            "--lang",
            "ko",
            "--market",
            "mixed",
            "--run-id",
            run_id,
            "--skip-network",
            "--reuse-collected",
            "--analyst-backend",
            "codex_native",
            "--allow-deterministic-delivery",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    metadata = json.loads((run_root / "run-metadata.json").read_text(encoding="utf-8"))
    comparison = json.loads((run_root / "comparison" / "comparison-analysis-result.json").read_text(encoding="utf-8"))

    assert rc == 0
    assert payload["schema_version"] == "run-mode-entry-result-v1"
    assert payload["mode"] == "B"
    assert payload["ticker"] == "AAPL"
    assert payload["tickers"] == ["AAPL", "005930", "000660"]
    assert payload["backend_provider"] == "codex_native"
    assert payload["run_profile"] == "deterministic"
    assert payload["delivery_gate"] == "PASS"
    assert metadata["market"] == "mixed"
    assert comparison["market"] == "mixed"
    assert comparison["compared_tickers"] == ["AAPL", "005930", "000660"]

    expected_markets = {"AAPL": "US", "005930": "KR", "000660": "KR"}
    expected_currencies = {"AAPL": "USD", "005930": "KRW", "000660": "KRW"}
    row_by_ticker = {row["ticker"]: row for row in comparison["metric_matrix"]}
    for ticker, expected_market in expected_markets.items():
        ticker_root = run_root / ticker
        source_summary = json.loads((ticker_root / "source-collection-summary.json").read_text(encoding="utf-8"))
        validated = json.loads((ticker_root / "validated-data.json").read_text(encoding="utf-8"))
        analysis = json.loads((ticker_root / "analysis-result.json").read_text(encoding="utf-8"))
        assert source_summary["market"] == expected_market
        assert validated["market"] == expected_market
        assert validated["currency"] == expected_currencies[ticker]
        assert analysis["currency"] == expected_currencies[ticker]
        assert analysis["run_context"]["backend"]["provider"] == "codex_native"
        assert analysis["run_context"]["backend"]["usage"]["api_calls"] == 0
        assert analysis["run_context"]["run_profile"] == "deterministic"
        assert row_by_ticker[ticker]["currency"] == expected_currencies[ticker]

    stage_markets = {
        (item.get("ticker"), item.get("market"))
        for item in metadata["performance"]["stage_timings"]
        if item.get("stage") == "ticker_collect"
    }
    assert stage_markets == {("AAPL", "US"), ("005930", "KR"), ("000660", "KR")}


def test_run_analysis_native_delegates_mode_b_to_unified_entrypoint(monkeypatch, capsys):
    run_id = "pytest_run_analysis_native_delegates_GOOGL_MSFT_AAPL_B"
    run_root = prepare_mode_b_fixture_run(run_id)
    monkeypatch.delenv("ANALYST_BACKEND", raising=False)

    rc = legacy_run_main(
        [
            "--ticker",
            "GOOGL",
            "--tickers",
            "GOOGL,MSFT,AAPL",
            "--mode",
            "B",
            "--lang",
            "ko",
            "--market",
            "US",
            "--run-id",
            run_id,
            "--native",
            "--skip-network",
            "--reuse-collected",
            "--analyst-backend",
            "codex_native",
            "--allow-deterministic-delivery",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    comparison_quality = json.loads(
        (run_root / "comparison" / "comparison-quality-report.json").read_text(encoding="utf-8")
    )

    assert rc == 0
    assert "deprecated" not in captured.err.lower()
    assert payload["schema_version"] == "run-mode-entry-result-v1"
    assert payload["mode"] == "B"
    assert payload["tickers"] == ["GOOGL", "MSFT", "AAPL"]
    assert payload["backend_provider"] == "codex_native"
    assert payload["run_profile"] == "deterministic"
    assert payload["delivery_gate"] == "PASS"
    assert Path(payload["comparison_report_path"]).exists()
    assert comparison_quality["delivery_gate"]["ready_for_delivery"] is True


def test_run_mode_blocks_mode_b_fixture_without_explicit_allow(monkeypatch, capsys):
    run_id = "pytest_run_mode_entrypoint_blocks_fixture_GOOGL_MSFT_AAPL_B"
    run_root = prepare_mode_b_fixture_run(run_id)
    monkeypatch.delenv("ANALYST_BACKEND", raising=False)

    rc = run_main(
        [
            "--ticker",
            "GOOGL",
            "--tickers",
            "GOOGL,MSFT,AAPL",
            "--mode",
            "B",
            "--lang",
            "ko",
            "--market",
            "US",
            "--run-id",
            run_id,
            "--skip-network",
            "--reuse-collected",
            "--analyst-backend",
            "fixture",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    quality = json.loads((run_root / "GOOGL" / "quality-report.json").read_text(encoding="utf-8"))

    assert rc == 1
    assert payload["mode"] == "B"
    assert "quality gate" in payload["error"].lower()
    assert quality["items"]["fixture_delivery_guard"]["status"] == "FAIL"
    assert quality["delivery_gate"]["ready_for_delivery"] is False
    assert "fixture_delivery_guard" in quality["delivery_gate"]["blocking_items"]
