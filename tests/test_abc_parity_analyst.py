from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from scripts.parity.analyst import (
    build_analyst_handoff,
    build_codex_native_analysis,
    enforce_deterministic_contract,
    ensure_mode_c_sections,
)
from scripts.parity.calculations import build_calculation_handoff
from scripts.parity.validation import build_validation_handoff
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


def test_fixture_analyst_writes_schema_valid_analysis_result(monkeypatch) -> None:
    run_id = "pytest_abc_parity_analyst_fixture_AAPL_A"
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
    build_calculation_handoff(language="en", market="US", mode="A", run_id=run_id, ticker="AAPL")
    monkeypatch.setenv("ANALYST_BACKEND", "fixture")

    result = build_analyst_handoff(language="en", market="US", mode="A", run_id=run_id, ticker="AAPL")

    analysis_path = ticker_root / "analysis-result.json"
    input_path = ticker_root / "analyst-input.json"
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    analyst_input = json.loads(input_path.read_text(encoding="utf-8"))
    analyst_message = json.loads(analyst_input["messages"][0]["content"])
    calculations = json.loads((ticker_root / "deterministic-calculations.json").read_text(encoding="utf-8"))

    assert result.provider == "fixture"
    assert analyst_input["input_profile"] == "compact"
    assert (ticker_root / "analyst-input.compact.json").exists()
    assert analyst_input["compaction"]["byte_reduction_ratio"] >= 0.25
    assert analyst_input["compaction"]["compact_user_payload_bytes"] < (
        analyst_input["compaction"]["full_user_payload_bytes"]
    )
    assert not analyst_input["compaction"]["warnings"]
    assert analyst_message["schema_version"] == "abc-parity-compact-analyst-input-v1"
    assert analysis["scenarios"] == calculations["scenario_analysis"]["scenarios"]
    assert analysis["rr_score"] == calculations["scenario_analysis"]["rr_score"]
    assert analysis["key_metrics"]["price_at_analysis"]["value"] == 200
    assert analyst_input["excluded_raw_artifacts_default"] == "deny"
    assert analyst_message["mode_contract"]["required_sections"]["precision_risks"]["min_items"] == 2
    assert analyst_message["mode_contract"]["required_sections"]["precision_risks"]["empty_array_policy"] == "not_allowed"
    assert "historical_prices" not in json.dumps(analyst_input["messages"], ensure_ascii=False)
    assert validate_artifact_file(analysis_path, "analysis-result", base_dir=REPO_ROOT)["valid"]


def test_codex_native_analyst_writes_production_local_analysis_result(monkeypatch) -> None:
    run_id = "pytest_abc_parity_analyst_codex_native_AAPL_C"
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
    build_validation_handoff(language="ko", market="US", mode="C", run_id=run_id, ticker="AAPL")
    build_calculation_handoff(language="ko", market="US", mode="C", run_id=run_id, ticker="AAPL")
    monkeypatch.setenv("ANALYST_BACKEND", "codex_native")

    result = build_analyst_handoff(language="ko", market="US", mode="C", run_id=run_id, ticker="AAPL")

    analysis_path = ticker_root / "analysis-result.json"
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    analysis_text = json.dumps(analysis, ensure_ascii=False).lower()

    assert result.provider == "codex_native"
    assert result.model == "local-deterministic-analyst"
    assert analysis["run_context"]["backend"]["provider"] == "codex_native"
    assert analysis["run_context"]["backend"]["usage"]["api_calls"] == 0
    assert analysis["sections"]["precision_risks"]
    assert "fixture" not in analysis_text
    assert "프리미엄 디바이스" in analysis["thesis"]
    assert validate_artifact_file(analysis_path, "analysis-result", base_dir=REPO_ROOT)["valid"]


def test_codex_native_falls_back_to_pe_ratio_when_forward_pe_missing() -> None:
    metric = lambda value, unit: {"value": value, "unit": unit, "grade": "B", "display_tag": "[Portal]"}
    validated = {
        "ticker": "AAPL",
        "company_name": "Apple Inc.",
        "market": "US",
        "currency": "USD",
        "analysis_date": "2026-07-06",
        "validated_metrics": {
            "price_at_analysis": metric(200.0, "USD"),
            "revenue_ttm": metric(340.0, "billions"),
            "revenue_growth_yoy": metric(5.0, "%"),
            "operating_margin": metric(30.0, "%"),
            "fcf_yield": metric(2.4, "%"),
            "ev_ebitda": metric(22.0, "x"),
            "pe_ratio": metric(30.0, "x"),
            "beta": metric(1.1, "x"),
        },
        "exclusions": [],
    }
    calculations = {
        "scenario_analysis": {
            "rr_score": 2.5,
            "scenarios": {
                "bull": {"target": 260.0, "probability": 0.3, "key_assumption": "Upside"},
                "base": {"target": 225.0, "probability": 0.5, "key_assumption": "Base"},
                "bear": {"target": 160.0, "probability": 0.2, "key_assumption": "Downside"},
            },
        },
        "dcf_analysis": {"result": {"fair_value_per_share": 220.0}},
        "reverse_dcf": {"implied_fcf_growth": 0.04, "analyst_growth_assumption": 0.05, "growth_gap_bp": 100},
        "valuation_bridge": {"weighted_fair_value": 225.0},
        "ratio_recomputation": {"computed_metrics": {}},
    }
    evidence = {"facts": [{"claim": "Revenue", "grade": "B", "sources": ["fixture"]}]}

    analysis = build_codex_native_analysis(
        calculations=calculations,
        evidence=evidence,
        language="en",
        mode="C",
        peer_records=[],
        validated=validated,
    )

    text = analysis["sections"]["variant_view_q3"]
    assert "verified TTM revenue of $340.0B" in analysis["thesis"]
    assert "forward P/E 30.0x" in text
    assert "forward P/E -" not in text


def test_mode_a_enforces_precision_risks_when_backend_returns_empty(monkeypatch) -> None:
    run_id = "pytest_abc_parity_analyst_empty_risks_AAPL_A"
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
    build_calculation_handoff(language="en", market="US", mode="A", run_id=run_id, ticker="AAPL")
    validated = json.loads((ticker_root / "validated-data.json").read_text(encoding="utf-8"))
    evidence = json.loads((ticker_root / "evidence-pack.json").read_text(encoding="utf-8"))
    calculations = json.loads((ticker_root / "deterministic-calculations.json").read_text(encoding="utf-8"))

    analysis = enforce_deterministic_contract(
        {
            "sections": {"precision_risks": []},
            "top_risks": [],
            "upcoming_catalysts": [],
        },
        backend_meta={"provider": "test", "model": "empty-risk-fixture", "usage": {}},
        calculations=calculations,
        evidence=evidence,
        language="en",
        mode="A",
        peer_records=[],
        run_id=run_id,
        ticker="AAPL",
        validated=validated,
    )

    risks = analysis["sections"]["precision_risks"]
    assert len(risks) >= 2
    assert analysis["top_risks"] == risks
    assert all(risk["mechanism"] and risk["financial_impact"] for risk in risks[:2])
    assert "AAPL" in risks[0]["risk"]


def test_runner_analysis_only_uses_fixture_backend() -> None:
    run_id = "pytest_abc_parity_analysis_only_fixture_AAPL_A"
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
    payload = json.loads(result.stdout)
    assert payload["analyst_results"][0]["provider"] == "fixture"
    assert (ticker_root / "analysis-result.json").exists()


def test_mode_c_sections_replace_peer_placeholder_with_explicit_disclosure() -> None:
    sections = ensure_mode_c_sections(
        {
            "peer_comparison": [
                {
                    "ticker": "peer_set_pending",
                    "summary": "Peer calculation will be expanded in the Mode B/comps session.",
                }
            ]
        },
        calculations={},
        evidence={},
        language="en",
        validated={"ticker": "GOOGL", "company_name": "Alphabet Inc."},
    )

    peer = sections["peer_comparison"][0]
    assert peer["ticker"] == "peer_data_unavailable"
    assert "explicitly excluded" in peer["summary"]
    assert "placeholder" not in peer["summary"].lower()


def test_mode_c_sections_use_peer_mini_fetch_when_available() -> None:
    sections = ensure_mode_c_sections(
        {
            "peer_comparison": [
                {
                    "ticker": "peer_set_pending",
                    "summary": "Peer calculation will be expanded in the Mode B/comps session.",
                }
            ]
        },
        calculations={},
        evidence={},
        language="en",
        peer_records=[
            {
                "ticker": "MSFT",
                "company_name": "Microsoft Corporation",
                "data_source": "yfinance (peer mini-fetch)",
                "tag": "[Portal]",
                "confidence_grade": "B",
                "metrics": {
                    "pe_forward": 31.5,
                    "ev_ebitda": 22.5,
                    "revenue_growth_yoy": 16.0,
                    "operating_margin": 44.5,
                    "fcf_yield": 2.2,
                },
            }
        ],
        validated={"ticker": "GOOGL", "company_name": "Alphabet Inc."},
    )

    peer = sections["peer_comparison"][0]
    assert peer["ticker"] == "MSFT"
    assert "Forward P/E 31.5x" in peer["value"]
    assert peer["tag"] == "[Portal]"
