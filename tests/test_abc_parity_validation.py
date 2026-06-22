from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

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


def test_run_abc_parity_validate_only_skip_network_writes_contract_artifacts() -> None:
    run_id = "pytest_abc_parity_validate_skip_AAPL_A"
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
        "--validate-only",
        "--skip-network",
    )

    assert result.returncode == 0, result.stderr
    ticker_root = REPO_ROOT / "output" / "runs" / run_id / "AAPL"
    validated_path = ticker_root / "validated-data.json"
    evidence_path = ticker_root / "evidence-pack.json"
    context_path = ticker_root / "context-budget.json"
    summary_path = ticker_root / "validation-summary.json"

    for path in (validated_path, evidence_path, context_path, summary_path):
        assert path.exists(), path

    validated = json.loads(validated_path.read_text(encoding="utf-8"))
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert validated["source_profile"] == "web_only"
    assert validated["overall_grade"] == "D"
    assert evidence["raw_access_policy"]["default_load"] == "deny"
    assert validate_artifact_file(validated_path, "validated-data", base_dir=REPO_ROOT)["valid"]
    assert validate_artifact_file(evidence_path, "evidence-pack", base_dir=REPO_ROOT)["valid"]
    assert validate_artifact_file(context_path, "context-budget", base_dir=REPO_ROOT)["valid"]


def test_run_abc_parity_validate_only_with_mock_yfinance_promotes_fallback() -> None:
    run_id = "pytest_abc_parity_validate_mock_yf_AAPL_A"
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
                    "pe_trailing": 30.0,
                    "pe_forward": 26.0,
                    "pb_ratio": 12.0,
                    "ev_ebitda": 22.0,
                    "enterprise_value": 3_100_000_000_000,
                    "beta": 1.1,
                    "fifty_two_week_high": 220.0,
                    "fifty_two_week_low": 150.0,
                },
                "income_statements": [
                    {"period_end": "2026-03-31", "revenue": 100, "operating_income": 30, "net_income": 25},
                    {"period_end": "2025-12-31", "revenue": 90, "operating_income": 27, "net_income": 20},
                    {"period_end": "2025-09-30", "revenue": 80, "operating_income": 24, "net_income": 18},
                    {"period_end": "2025-06-30", "revenue": 70, "operating_income": 21, "net_income": 16},
                    {"period_end": "2025-03-31", "revenue": 75, "operating_income": 20, "net_income": 15},
                ],
                "cash_flow_statements": [
                    {"period_end": "2026-03-31", "operating_cashflow": 30, "capital_expenditure": 10, "free_cash_flow": 20},
                    {"period_end": "2025-12-31", "operating_cashflow": 28, "capital_expenditure": 9, "free_cash_flow": 19},
                    {"period_end": "2025-09-30", "operating_cashflow": 25, "capital_expenditure": 8, "free_cash_flow": 17},
                    {"period_end": "2025-06-30", "operating_cashflow": 22, "capital_expenditure": 7, "free_cash_flow": 15},
                ],
                "balance_sheets": [
                    {
                        "period_end": "2026-03-31",
                        "total_debt": 100_000_000_000,
                        "cash_and_equivalents": 60_000_000_000,
                    }
                ],
                "derived_ttm": {
                    "revenue_ttm": 340_000_000_000,
                    "operating_income_ttm": 102_000_000_000,
                    "net_income_ttm": 79_000_000_000,
                    "fcf_ttm": 71_000_000_000,
                },
                "analyst_targets": {"mean_target": 225.0, "median_target": 220.0},
            }
        ),
        encoding="utf-8",
    )

    build_validation_handoff(
        language="en",
        market="US",
        mode="A",
        run_id=run_id,
        ticker="AAPL",
    )
    validated_path = ticker_root / "validated-data.json"
    evidence_path = ticker_root / "evidence-pack.json"
    validated = json.loads(validated_path.read_text(encoding="utf-8"))
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))

    assert validated["source_profile"] == "yfinance_fallback"
    assert validated["effective_mode"] == "standard"
    assert validated["confidence_cap"] == "C"
    assert validated["validated_metrics"]["price_at_analysis"]["value"] == 200
    assert evidence["facts"]
    assert validate_artifact_file(validated_path, "validated-data", base_dir=REPO_ROOT)["valid"]
    assert validate_artifact_file(evidence_path, "evidence-pack", base_dir=REPO_ROOT)["valid"]


def test_validation_consumes_sanitized_tier2_metric_candidates() -> None:
    run_id = "pytest_abc_parity_validate_tier2_candidates_AAPL_C"
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
    (ticker_root / "tier2-raw.json").write_text(
        json.dumps(
            {
                "ticker": "AAPL",
                "collection_timestamp": "2026-05-21T00:00:00Z",
                "market": "US",
                "status": "ok",
                "provider": "fixture",
                "raw_search_results": [
                    {
                        "query_id": "q_target_1",
                        "query": "AAPL analyst target",
                        "rank": 1,
                        "title": "Analyst target fixture",
                        "url": "https://example.com/aapl-target",
                        "published_date": None,
                        "retrieved_at": "2026-05-21T00:00:00Z",
                        "snippet": "Consensus target fixture.",
                        "source_domain": "example.com",
                    }
                ],
                "extracted_metric_candidates": [
                    {
                        "candidate_id": "c_target_1",
                        "metric": "analyst_target_mean",
                        "raw_value": "$225",
                        "normalized_value": 225.0,
                        "unit": "USD",
                        "currency": "USD",
                        "as_of_date": "2026-05-21",
                        "source_url": "https://example.com/aapl-target",
                        "source_query_id": "q_target_1",
                        "source_result_rank": 1,
                        "source_domain": "example.com",
                        "extraction_method": "search_snippet",
                        "confidence_candidate": "C",
                        "notes": "Fixture candidate",
                    }
                ],
                "metric_conflicts": [],
                "_sanitization": {"status": "pass", "findings": [], "redactions": 0},
            }
        ),
        encoding="utf-8",
    )

    build_validation_handoff(
        language="en",
        market="US",
        mode="C",
        run_id=run_id,
        ticker="AAPL",
    )

    validated_path = ticker_root / "validated-data.json"
    evidence_path = ticker_root / "evidence-pack.json"
    validated = json.loads(validated_path.read_text(encoding="utf-8"))
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    target = validated["validated_metrics"]["analyst_target_mean"]

    assert target["value"] == 225.0
    assert target["grade"] == "C"
    assert target["source_type"] == "estimate"
    assert target["candidate_trace"]["selected_candidate_id"] == "c_target_1"
    assert validated["source_registry"]["tier2"]["status"] == "ok"
    assert any(ref.endswith("/tier2-raw.json") for ref in evidence["raw_artifact_refs"])
    assert any(fact["metric"] == "analyst_target_mean" for fact in evidence["facts"])
    assert validate_artifact_file(validated_path, "validated-data", base_dir=REPO_ROOT)["valid"]
    assert validate_artifact_file(evidence_path, "evidence-pack", base_dir=REPO_ROOT)["valid"]


def test_dart_raw_without_status_is_primary_for_kr_validation() -> None:
    run_id = "pytest_abc_parity_validate_mock_dart_005930_C"
    collect = run_parity(
        "--ticker",
        "005930",
        "--mode",
        "C",
        "--lang",
        "ko",
        "--market",
        "KR",
        "--run-id",
        run_id,
        "--collect-only",
        "--skip-network",
    )
    assert collect.returncode == 0, collect.stderr
    ticker_root = REPO_ROOT / "output" / "runs" / run_id / "005930"
    (ticker_root / "dart-api-raw.json").write_text(
        json.dumps(
            {
                "stock_code": "005930",
                "corp_name": "삼성전자(주)",
                "stock_name": "삼성전자",
                "collection_timestamp": "2026-05-21T00:00:00Z",
                "data_source": "DART OpenAPI",
                "confidence_grade": "A",
                "ttm_income_statement": {
                    "currency": "KRW",
                    "revenue": 333_000_000_000_000,
                    "operating_income": 43_000_000_000_000,
                    "net_income": 45_000_000_000_000,
                },
                "balance_sheet_latest": {
                    "cash": 58_000_000_000_000,
                    "short_term_debt": 18_000_000_000_000,
                    "current_portion_lt_debt": 1_000_000_000_000,
                    "long_term_debt": 6_000_000_000_000,
                    "bonds_payable": 1_000_000_000_000,
                },
                "periods_detail": {
                    "Annual": {
                        "year": 2025,
                        "metrics": {
                            "revenue": {"value": 333_000_000_000_000, "prior": 300_000_000_000_000},
                            "operating_cash_flow": {"value": 85_000_000_000_000},
                            "capex": {"value": 47_000_000_000_000},
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    build_validation_handoff(
        language="ko",
        market="KR",
        mode="C",
        run_id=run_id,
        ticker="005930",
    )

    validated_path = ticker_root / "validated-data.json"
    validated = json.loads(validated_path.read_text(encoding="utf-8"))

    assert validated["source_profile"] == "sec_or_dart_primary"
    assert validated["source_tier"] == "filing_primary"
    assert validated["validated_metrics"]["revenue_ttm"]["grade"] == "A"
    assert validate_artifact_file(validated_path, "validated-data", base_dir=REPO_ROOT)["valid"]
