from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from scripts.parity.rendering import (
    build_mode_a_briefing_html,
    build_chart_data,
    normalize_quarterly,
    render_reverse_dcf,
    validate_mode_a_rendered_html,
    validate_mode_c_rendered_html,
)
from tests.test_abc_parity_calculations import write_mock_yfinance

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


def write_peer_records(ticker_root: Path) -> None:
    peers_dir = ticker_root / "peers"
    peers_dir.mkdir(parents=True, exist_ok=True)
    records = [
        {
            "ticker": "MSFT",
            "company_name": "Microsoft Corporation",
            "collection_timestamp": "2026-05-24T00:00:00Z",
            "data_source": "yfinance (peer mini-fetch)",
            "tag": "[Portal]",
            "confidence_grade": "B",
            "metrics": {
                "current_price": 425.3,
                "market_cap": 3_158_000_000_000,
                "pe_forward": 31.5,
                "ev_ebitda": 22.5,
                "revenue_growth_yoy": 16.0,
                "operating_margin": 44.5,
                "fcf_yield": 2.2,
                "beta": 0.91,
            },
        },
        {
            "ticker": "META",
            "company_name": "Meta Platforms, Inc.",
            "collection_timestamp": "2026-05-24T00:00:00Z",
            "data_source": "yfinance (peer mini-fetch)",
            "tag": "[Portal]",
            "confidence_grade": "B",
            "metrics": {
                "current_price": 620.0,
                "market_cap": 1_540_000_000_000,
                "pe_forward": 24.2,
                "ev_ebitda": 17.8,
                "revenue_growth_yoy": 19.0,
                "operating_margin": 41.0,
                "fcf_yield": 3.0,
                "beta": 1.12,
            },
        },
    ]
    for record in records:
        (peers_dir / f"{record['ticker']}.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def test_mode_c_render_only_builds_golden_minimum_dashboard() -> None:
    run_id = "pytest_abc_parity_render_fixture_AAPL_C"
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
        "--render-only",
        "--reuse-collected",
        "--skip-network",
        env={"ANALYST_BACKEND": "fixture"},
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    render = payload["render_results"][0]
    html_path = REPO_ROOT / render["html_path"]
    report_path = REPO_ROOT / render["render_report_path"]
    report = json.loads(report_path.read_text(encoding="utf-8"))
    html = html_path.read_text(encoding="utf-8")

    assert render["status"] == "PASS"
    assert render["metrics"]["html_byte_size"] >= 40_000
    assert render["metrics"]["canvas_count"] >= 3
    assert render["metrics"]["table_count"] >= 5
    assert render["metrics"]["script_count"] >= 3
    assert report["status"] == "PASS"
    assert report["quality_item"]["status"] in {"PASS", "PASS_WITH_FLAGS"}
    assert 'id="segmentChart"' in html
    assert 'id="fcfChart"' in html
    assert 'id="quarterlyChart"' in html
    assert "Quality of Earnings & Evidence Gate" in html
    assert "Portfolio Strategy" in html
    assert "Source-Tagged Claims Appendix" in html
    assert "arrays are not present" not in html
    assert "{COMPANY_NAME}" not in html
    assert "/Users/" not in html


def test_mode_c_korean_render_localizes_dashboard_chrome() -> None:
    run_id = "pytest_abc_parity_render_fixture_AAPL_C_ko"
    collect = run_parity(
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
        "ko",
        "--market",
        "US",
        "--run-id",
        run_id,
        "--render-only",
        "--reuse-collected",
        "--skip-network",
        env={"ANALYST_BACKEND": "fixture"},
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    render = payload["render_results"][0]
    html_path = REPO_ROOT / render["html_path"]
    report_path = REPO_ROOT / render["render_report_path"]
    report = json.loads(report_path.read_text(encoding="utf-8"))
    html = html_path.read_text(encoding="utf-8")

    assert render["status"] == "PASS"
    assert report["status"] == "PASS"
    for expected in (
        "Mode C 심층 대시보드",
        "시나리오 밸류에이션",
        "핵심 KPI",
        "투자 논점과 차별적 관점",
        "정밀 리스크 분석",
        "밸류에이션 지표",
        "DCF 밸류에이션",
        "동종업계 비교",
        "매크로 환경",
        "애널리스트 커버리지",
        "재무 차트",
        "재무 세부 분석",
        "이익 품질 및 증거 게이트",
        "포트폴리오 전략",
        "출처 태그 클레임 부록",
        "면책 고지",
    ):
        assert expected in html

    for forbidden in (
        "Mode C Deep Dive Dashboard",
        "Scenario Valuation",
        "Key Performance Indicators",
        "Investment Thesis & Variant View",
        "Precision Risk Analysis",
        "Valuation Metrics",
        "DCF Valuation",
        "Peer Comparison",
        "Macro Environment",
        "Analyst Coverage",
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
    ):
        assert forbidden not in html


def test_mode_c_render_uses_peer_mini_fetch_rows() -> None:
    run_id = "pytest_abc_parity_render_peer_fixture_AAPL_C"
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
    write_peer_records(ticker_root)

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
        "--render-only",
        "--reuse-collected",
        "--skip-network",
        env={"ANALYST_BACKEND": "fixture"},
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    html_path = REPO_ROOT / payload["render_results"][0]["html_path"]
    analysis_path = ticker_root / "analysis-result.json"
    html = html_path.read_text(encoding="utf-8")
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    peers = analysis["sections"]["peer_comparison"]

    assert [peer["ticker"] for peer in peers] == ["META", "MSFT"]
    assert "peer_data_unavailable" not in html
    assert "Forward P/E 31.5x" in html
    assert "Meta Platforms" in html


def test_mode_c_reverse_dcf_renders_unavailable_boundary() -> None:
    html = render_reverse_dcf(
        {
            "status": "negative_fcf",
            "target_price": 41_750,
            "notes": "Reverse DCF requires positive FCF TTM.",
        }
    )

    assert "Reverse DCF" in html
    assert "negative fcf" in html
    assert "No implied growth shown" in html
    assert "Reverse DCF requires positive FCF TTM." in html


def test_mode_a_render_only_builds_dense_evidence_briefing() -> None:
    run_id = "pytest_abc_parity_render_fixture_AAPL_A"
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
        "--render-only",
        "--reuse-collected",
        "--skip-network",
        env={"ANALYST_BACKEND": "fixture"},
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    render = payload["render_results"][0]
    html_path = REPO_ROOT / render["html_path"]
    report_path = REPO_ROOT / render["render_report_path"]
    report = json.loads(report_path.read_text(encoding="utf-8"))
    html = html_path.read_text(encoding="utf-8")

    assert render["status"] == "PASS"
    assert report["status"] == "PASS"
    assert report["quality_item"]["status"] in {"PASS", "PASS_WITH_FLAGS"}
    assert 500 <= render["metrics"]["body_word_count"] <= 900
    assert render["metrics"]["kpi_count"] >= 3
    assert render["metrics"]["risk_count"] >= 2
    assert render["metrics"]["catalyst_count"] >= 2
    assert render["metrics"]["scenario_count"] == 3
    assert render["metrics"]["rr_present"] is True
    assert "AAPL" in html
    assert "Evidence Tape" in html
    assert "Revenue Growth Yoy" in html
    assert "/Users/" not in html


def test_mode_a_renderer_recomputes_missing_rr_from_scenarios() -> None:
    run_id = "pytest_abc_parity_render_rr_fallback_AAPL_A"
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
        "--analysis-only",
        "--reuse-collected",
        "--skip-network",
        env={"ANALYST_BACKEND": "fixture"},
    )
    assert result.returncode == 0, result.stderr
    analysis_path = REPO_ROOT / "output" / "runs" / run_id / "AAPL" / "analysis-result.json"
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    analysis["rr_score"] = None

    html = build_mode_a_briefing_html(analysis=analysis, language="en", market="US")
    report = validate_mode_a_rendered_html(html, analysis=analysis)

    assert report["status"] == "PASS"
    assert "R/R Score</div><div class=\"value\">Unavailable" not in html
    assert "Base Target</div><div class=\"value\">Unavailable" not in html
    assert "R/R Score</div><div class=\"value\">2.50" in html


def test_mode_c_render_validator_blocks_hollow_html() -> None:
    report = validate_mode_c_rendered_html(
        "<html><body><h2>Scenario Valuation</h2><footer>Disclaimer: not investment advice.</footer></body></html>",
        analysis={"output_mode": "C", "valuation_bridge": {"anchors": []}},
        validated={"exclusions": []},
    )

    assert report["status"] == "FAIL"
    assert any("html_byte_size" in error for error in report["errors"])
    assert any("required heading group" in error for error in report["errors"])


def test_mode_c_chart_data_flattens_financial_datasets_nested_quarters() -> None:
    quarterly = normalize_quarterly(
        [
            {
                "financials": {
                    "income_statements": [
                        {
                            "report_period": "2026-03-31",
                            "revenue": 109_896_000_000,
                            "gross_profit": 68_625_000_000,
                            "operating_income": 39_696_000_000,
                            "net_income": 62_578_000_000,
                        },
                        {
                            "report_period": "2025-12-31",
                            "revenue": 102_000_000_000,
                            "gross_profit": 60_000_000_000,
                            "operating_income": 31_000_000_000,
                            "net_income": 34_000_000_000,
                        },
                        {
                            "report_period": "2025-09-30",
                            "revenue": 96_000_000_000,
                            "gross_profit": 57_000_000_000,
                            "operating_income": 30_000_000_000,
                            "net_income": 28_000_000_000,
                        },
                        {
                            "report_period": "2025-06-30",
                            "revenue": 90_000_000_000,
                            "gross_profit": 53_000_000_000,
                            "operating_income": 28_000_000_000,
                            "net_income": 24_000_000_000,
                        },
                    ]
                }
            }
        ]
    )

    chart_data = build_chart_data(
        analysis={"analysis_date": "2026-05-24"},
        metrics={"price_at_analysis": {"value": 388.91}, "fcf_ttm": {"value": 12}},
        quarterly=quarterly,
        scenarios={"bull": {"target": 515}, "base": {"target": 430}, "bear": {"target": 330}},
    )

    assert len(chart_data["quarters"]) == 4
    assert chart_data["quarters"][-1] == "2026-03-31"
    assert chart_data["revenue"][-1] == 109.9
    assert chart_data["operating_income"][-1] == 39.7
    assert chart_data["segment_labels"] == ["Revenue", "Gross Profit", "Operating Income", "Net Income"]
    assert chart_data["segment_data"][0] == 109.9
    assert chart_data["segment_data"][2] == 39.7
    assert chart_data["free_cash_flow"] == [3, 3, 3, 3]


def test_mode_a_render_validator_blocks_thin_briefing() -> None:
    report = validate_mode_a_rendered_html(
        "<html><body><h2>Decision Brief</h2><p>AAPL thesis.</p><footer>Disclaimer: not investment advice.</footer></body></html>",
        analysis={
            "ticker": "AAPL",
            "company_name": "Apple Inc.",
            "output_mode": "A",
            "scenarios": {"bull": {"target": 10}, "base": {"target": 9}, "bear": {"target": 8}},
        },
        validated={"exclusions": []},
    )

    assert report["status"] == "FAIL"
    assert any("word count" in error for error in report["errors"])
    assert any("KPI" in error for error in report["errors"])
