from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.parity.calculations import build_calculation_handoff
from scripts.parity.validation import build_validation_handoff
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


def write_mock_yfinance(ticker_root: Path) -> None:
    (ticker_root / "yfinance-raw.json").write_text(
        json.dumps(
            {
                "ticker": "AAPL",
                "market": "US",
                "status": "success",
                "collection_timestamp": "2026-05-21T00:00:00Z",
                "current_price": {
                    "price": 200.0,
                    "currency": "USD",
                    "as_of": "2026-05-20T20:00:00Z",
                    "source_field": "regularMarketPrice",
                },
                "info": {
                    "market_cap": 3_000_000_000_000,
                    "shares_outstanding": 15_000_000_000,
                    "pe_trailing": 30.0,
                    "pe_forward": 26.0,
                    "pb_ratio": 12.0,
                    "ev_ebitda": 22.0,
                    "enterprise_value": 3_100_000_000_000,
                    "total_debt": 120_000_000_000,
                    "total_cash": 70_000_000_000,
                    "beta": 1.1,
                    "fifty_two_week_high": 240.0,
                    "fifty_two_week_low": 150.0,
                },
                "income_statements": [
                    {"period_end": "2026-03-31", "revenue": 100_000_000_000, "operating_income": 30_000_000_000, "net_income": 25_000_000_000},
                    {"period_end": "2025-12-31", "revenue": 90_000_000_000, "operating_income": 27_000_000_000, "net_income": 20_000_000_000},
                    {"period_end": "2025-09-30", "revenue": 80_000_000_000, "operating_income": 24_000_000_000, "net_income": 18_000_000_000},
                    {"period_end": "2025-06-30", "revenue": 70_000_000_000, "operating_income": 21_000_000_000, "net_income": 16_000_000_000},
                    {"period_end": "2025-03-31", "revenue": 75_000_000_000, "operating_income": 20_000_000_000, "net_income": 15_000_000_000},
                ],
                "cash_flow_statements": [
                    {"period_end": "2026-03-31", "operating_cashflow": 30_000_000_000, "capital_expenditure": 10_000_000_000, "free_cash_flow": 20_000_000_000},
                    {"period_end": "2025-12-31", "operating_cashflow": 28_000_000_000, "capital_expenditure": 9_000_000_000, "free_cash_flow": 19_000_000_000},
                    {"period_end": "2025-09-30", "operating_cashflow": 25_000_000_000, "capital_expenditure": 8_000_000_000, "free_cash_flow": 17_000_000_000},
                    {"period_end": "2025-06-30", "operating_cashflow": 22_000_000_000, "capital_expenditure": 7_000_000_000, "free_cash_flow": 15_000_000_000},
                ],
                "balance_sheets": [
                    {
                        "period_end": "2026-03-31",
                        "total_debt": 120_000_000_000,
                        "cash_and_equivalents": 70_000_000_000,
                    }
                ],
                "derived_ttm": {
                    "revenue_ttm": 340_000_000_000,
                    "operating_income_ttm": 102_000_000_000,
                    "net_income_ttm": 79_000_000_000,
                    "fcf_ttm": 71_000_000_000,
                },
                "analyst_targets": {
                    "mean_target": 225.0,
                    "median_target": 220.0,
                    "high_target": 260.0,
                    "low_target": 160.0,
                },
            }
        ),
        encoding="utf-8",
    )


def test_calculation_handoff_builds_scenarios_dcf_and_updates_context_budget() -> None:
    run_id = "pytest_abc_parity_calculations_mock_yf_AAPL_A"
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
    build_validation_handoff(language="en", market="US", mode="A", run_id=run_id, ticker="AAPL")
    result = build_calculation_handoff(language="en", market="US", mode="A", run_id=run_id, ticker="AAPL")

    calculations_path = ticker_root / "deterministic-calculations.json"
    context_path = ticker_root / "context-budget.json"
    calculations = json.loads(calculations_path.read_text(encoding="utf-8"))
    context = json.loads(context_path.read_text(encoding="utf-8"))

    assert result.scenario_status == "available"
    assert result.dcf_status == "available"
    assert calculations["scenario_analysis"]["rr_score"] is not None
    assert calculations["dcf_analysis"]["result"]["fair_value_per_share"] is not None
    assert calculations["reverse_dcf"] is not None
    assert calculations["valuation_bridge"]["status"] == "available"
    assert any(item["role"] == "deterministic_calculations" for item in context["included_files"])
    assert validate_artifact_file(calculations_path, "deterministic-calculations", base_dir=REPO_ROOT)["valid"]
    assert validate_artifact_file(context_path, "context-budget", base_dir=REPO_ROOT)["valid"]


def test_runner_calculate_only_stays_fail_closed_before_analyst() -> None:
    run_id = "pytest_abc_parity_calculate_only_empty_AAPL_A"
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
        "--calculate-only",
        "--skip-network",
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["calculation_results"][0]["status"] == "partial"
    assert (REPO_ROOT / "output" / "runs" / run_id / "AAPL" / "deterministic-calculations.json").exists()
