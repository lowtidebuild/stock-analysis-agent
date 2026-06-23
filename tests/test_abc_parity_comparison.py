from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

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


def write_peer_yfinance(
    ticker_root: Path,
    *,
    currency: str = "USD",
    market: str = "US",
    ticker: str,
    price: float,
    market_cap_b: float,
    pe: float,
    ev_ebitda: float | None,
    revenue_b: float,
    revenue_growth_pct: float,
    operating_margin_pct: float,
    fcf_b: float,
    target_mean: float,
    target_median: float,
    target_high: float,
    target_low: float,
) -> None:
    write_mock_yfinance(ticker_root)
    path = ticker_root / "yfinance-raw.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["ticker"] = ticker
    data["market"] = market
    data["current_price"]["price"] = price
    data["current_price"]["currency"] = currency
    data["info"]["market_cap"] = market_cap_b * 1_000_000_000
    data["info"]["shares_outstanding"] = data["info"]["market_cap"] / price
    data["info"]["pe_trailing"] = pe
    data["info"]["pe_forward"] = pe * 0.88
    data["info"]["enterprise_value"] = data["info"]["market_cap"] * 1.03
    if ev_ebitda is None:
        data["info"].pop("ev_ebitda", None)
    else:
        data["info"]["ev_ebitda"] = ev_ebitda
    data["info"]["total_debt"] = market_cap_b * 0.04 * 1_000_000_000
    data["info"]["total_cash"] = market_cap_b * 0.03 * 1_000_000_000
    data["info"]["fifty_two_week_high"] = price * 1.22
    data["info"]["fifty_two_week_low"] = price * 0.72

    latest_q_revenue = revenue_b / 4
    prior_q_revenue = latest_q_revenue / (1 + revenue_growth_pct / 100)
    operating_income_b = revenue_b * operating_margin_pct / 100
    net_income_b = operating_income_b * 0.78
    data["derived_ttm"] = {
        "revenue_ttm": revenue_b * 1_000_000_000,
        "operating_income_ttm": operating_income_b * 1_000_000_000,
        "net_income_ttm": net_income_b * 1_000_000_000,
        "fcf_ttm": fcf_b * 1_000_000_000,
    }
    data["income_statements"] = [
        {
            "period_end": "2026-03-31",
            "revenue": latest_q_revenue * 1_000_000_000,
            "operating_income": latest_q_revenue * operating_margin_pct / 100 * 1_000_000_000,
            "net_income": latest_q_revenue * operating_margin_pct / 100 * 0.78 * 1_000_000_000,
        },
        {
            "period_end": "2025-12-31",
            "revenue": revenue_b * 0.25 * 1_000_000_000,
            "operating_income": revenue_b * 0.25 * operating_margin_pct / 100 * 1_000_000_000,
            "net_income": revenue_b * 0.25 * operating_margin_pct / 100 * 0.78 * 1_000_000_000,
        },
        {
            "period_end": "2025-09-30",
            "revenue": revenue_b * 0.24 * 1_000_000_000,
            "operating_income": revenue_b * 0.24 * operating_margin_pct / 100 * 1_000_000_000,
            "net_income": revenue_b * 0.24 * operating_margin_pct / 100 * 0.78 * 1_000_000_000,
        },
        {
            "period_end": "2025-06-30",
            "revenue": revenue_b * 0.23 * 1_000_000_000,
            "operating_income": revenue_b * 0.23 * operating_margin_pct / 100 * 1_000_000_000,
            "net_income": revenue_b * 0.23 * operating_margin_pct / 100 * 0.78 * 1_000_000_000,
        },
        {
            "period_end": "2025-03-31",
            "revenue": prior_q_revenue * 1_000_000_000,
            "operating_income": prior_q_revenue * operating_margin_pct / 100 * 1_000_000_000,
            "net_income": prior_q_revenue * operating_margin_pct / 100 * 0.78 * 1_000_000_000,
        },
    ]
    quarterly_fcf = fcf_b / 4
    data["cash_flow_statements"] = [
        {
            "period_end": period,
            "operating_cashflow": quarterly_fcf * 1.28 * 1_000_000_000,
            "capital_expenditure": quarterly_fcf * 0.28 * 1_000_000_000,
            "free_cash_flow": quarterly_fcf * 1_000_000_000,
        }
        for period in ("2026-03-31", "2025-12-31", "2025-09-30", "2025-06-30")
    ]
    data["balance_sheets"] = [
        {
            "period_end": "2026-03-31",
            "total_debt": data["info"]["total_debt"],
            "cash_and_equivalents": data["info"]["total_cash"],
        }
    ]
    data["analyst_targets"] = {
        "mean_target": target_mean,
        "median_target": target_median,
        "high_target": target_high,
        "low_target": target_low,
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def prepare_mode_b_fixture_run(run_id: str) -> Path:
    tickers = "GOOGL,MSFT,AAPL"
    collect = run_parity(
        "--ticker",
        "GOOGL",
        "--tickers",
        tickers,
        "--mode",
        "B",
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
    run_root = REPO_ROOT / "output" / "runs" / run_id
    write_peer_yfinance(
        run_root / "GOOGL",
        ticker="GOOGL",
        price=180,
        market_cap_b=2200,
        pe=24,
        ev_ebitda=17,
        revenue_b=360,
        revenue_growth_pct=12,
        operating_margin_pct=31,
        fcf_b=82,
        target_mean=215,
        target_median=210,
        target_high=245,
        target_low=145,
    )
    write_peer_yfinance(
        run_root / "MSFT",
        ticker="MSFT",
        price=430,
        market_cap_b=3200,
        pe=34,
        ev_ebitda=23,
        revenue_b=260,
        revenue_growth_pct=16,
        operating_margin_pct=43,
        fcf_b=76,
        target_mean=500,
        target_median=495,
        target_high=560,
        target_low=360,
    )
    write_peer_yfinance(
        run_root / "AAPL",
        ticker="AAPL",
        price=200,
        market_cap_b=3000,
        pe=30,
        ev_ebitda=None,
        revenue_b=390,
        revenue_growth_pct=5,
        operating_margin_pct=30,
        fcf_b=72,
        target_mean=225,
        target_median=220,
        target_high=260,
        target_low=155,
    )
    return run_root


def test_mode_b_render_only_builds_comparison_contract() -> None:
    run_id = "pytest_abc_parity_comparison_GOOGL_MSFT_AAPL_B"
    run_root = prepare_mode_b_fixture_run(run_id)
    result = run_parity(
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
        "--render-only",
        "--reuse-collected",
        "--skip-network",
        env={
            "ANALYST_BACKEND": "fixture",
            "SAA_ANALYST_MAX_WORKERS": "2",
            "SAA_TICKER_MAX_WORKERS": "3",
        },
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    comparison = payload["comparison_results"][0]
    comparison_dir = run_root / "comparison"
    analysis = json.loads((comparison_dir / "comparison-analysis-result.json").read_text(encoding="utf-8"))
    quality = json.loads((comparison_dir / "comparison-quality-report.json").read_text(encoding="utf-8"))
    html = (comparison_dir / "mode-b-comparison.html").read_text(encoding="utf-8")

    assert comparison["status"] == "PASS"
    assert comparison["delivery_ready"] is True
    assert [item["ticker"] for item in payload["validation_results"]] == ["GOOGL", "MSFT", "AAPL"]
    assert [item["ticker"] for item in payload["calculation_results"]] == ["GOOGL", "MSFT", "AAPL"]
    assert [item["ticker"] for item in payload["analyst_results"]] == ["GOOGL", "MSFT", "AAPL"]
    stage_tickers = {
        item["ticker"]
        for item in payload["performance"]["stage_timings"]
        if item["stage"] == "analyst"
    }
    assert stage_tickers == {"GOOGL", "MSFT", "AAPL"}
    assert comparison["best_pick"] in {"GOOGL", "MSFT", "AAPL"}
    assert analysis["compared_tickers"] == ["GOOGL", "MSFT", "AAPL"]
    assert len(analysis["metric_matrix"]) == 3
    assert len({tuple(row["values"].keys()) for row in analysis["metric_matrix"]}) == 1
    assert len(analysis["ranking"]) == 3
    assert len(analysis["relative_valuation"]) == 3
    assert analysis["best_pick_reasoning"]["ticker"] == analysis["best_pick"]["ticker"]
    assert len(analysis["best_pick_reasoning"]["numeric_drivers"]) >= 3
    boundary = analysis["best_pick_reasoning"]["missing_data_boundary"].lower()
    assert "missing" in boundary or "결측" in boundary
    assert quality["delivery_gate"]["ready_for_delivery"] is True
    assert any(item["item"] == "best_pick_reasoning" and item["status"] == "PASS" for item in quality["items"])
    assert any(item["item"] == "missing_data_disclosure" and item["status"] == "PASS" for item in quality["items"])
    assert any(item["display"] == "—" and item["reason"] for item in analysis["missing_data_disclosure"])
    assert "Best-Pick Decision Rationale" in html
    assert "Peer Median Premium/Discount" in html
    assert "Macro data unavailable" in html


def test_mode_b_critic_only_writes_comparison_summary() -> None:
    run_id = "pytest_abc_parity_comparison_critic_GOOGL_MSFT_AAPL_B"
    run_root = prepare_mode_b_fixture_run(run_id)
    result = run_parity(
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
        "--critic-only",
        "--reuse-collected",
        "--skip-network",
        env={"ANALYST_BACKEND": "fixture"},
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert len(payload["critic_results"]) == 3
    assert all(item["delivery_ready"] for item in payload["critic_results"])
    assert payload["comparison_results"][0]["delivery_ready"] is True

    summary = json.loads((run_root / "abc-parity-summary.json").read_text(encoding="utf-8"))
    assert summary["overall_status"] == "PASS"
    assert summary["comparison"]["delivery_ready"] is True
    assert summary["comparison"]["best_pick"] in {"GOOGL", "MSFT", "AAPL"}
