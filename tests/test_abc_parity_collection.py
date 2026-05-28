from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_run_abc_parity_collect_only_skip_network(tmp_path: Path) -> None:
    run_id = f"pytest_{tmp_path.name}_AAPL_A"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_abc_parity.py",
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
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    run_root = REPO_ROOT / "output" / "runs" / run_id
    assert (run_root / "request.json").exists()
    assert (run_root / "run-metadata.json").exists()
    assert (run_root / "macro" / "fred-raw.json").exists()
    assert (run_root / "AAPL" / "research-plan.json").exists()
    assert (run_root / "AAPL" / "financial-datasets-raw.json").exists()
    assert (run_root / "AAPL" / "dart-api-raw.json").exists()
    assert (run_root / "AAPL" / "yfinance-raw.json").exists()

    metadata = json.loads((run_root / "run-metadata.json").read_text())
    assert metadata["schema_version"] == "abc-parity-collection-summary-v1"
    assert metadata["ticker_results"][0]["schema_version"] == (
        "abc-parity-source-collection-summary-v1"
    )
    assert metadata["performance"]["schema_version"] == "abc-parity-performance-v1"
    assert metadata["performance"]["total_duration_seconds"] >= 0
    assert any(
        stage["stage"] == "ticker_collect"
        for stage in metadata["performance"]["stage_timings"]
    )
    assert metadata["macro"]["duration_seconds"] >= 0
    assert metadata["ticker_results"][0]["duration_seconds"] >= 0
    assert metadata["ticker_results"][0]["performance"]["artifact_measurements"][
        "research_plan"
    ]["estimated_tokens"] > 0

    collection_summary = json.loads(
        (run_root / "AAPL" / "source-collection-summary.json").read_text()
    )
    assert collection_summary["duration_seconds"] >= 0


def test_financial_datasets_missing_key_writes_unavailable(monkeypatch, tmp_path: Path) -> None:
    from scripts.parity.data_sources import collect_financial_datasets

    monkeypatch.setenv("SAA_COLLECTOR_CACHE", "0")
    old_key = os.environ.pop("FINANCIAL_DATASETS_API_KEY", None)
    try:
        output_path = tmp_path / "financial-datasets-raw.json"
        result = collect_financial_datasets(
            output_path=output_path,
            ticker="AAPL",
            market="US",
        )
    finally:
        if old_key is not None:
            os.environ["FINANCIAL_DATASETS_API_KEY"] = old_key

    assert result.status == "unavailable"
    payload = json.loads(output_path.read_text())
    assert payload["reason"] == "missing_financial_datasets_api_key"


def test_financial_datasets_parallel_endpoint_collection_preserves_contract(
    monkeypatch,
    tmp_path: Path,
) -> None:
    import scripts.parity.data_sources as data_sources

    monkeypatch.setenv("FINANCIAL_DATASETS_API_KEY", "test-key")
    monkeypatch.setenv("SAA_COLLECTOR_CACHE_DIR", str(tmp_path / "source-cache"))
    monkeypatch.setenv("SAA_FINANCIAL_DATASETS_MAX_WORKERS", "4")

    def fake_get(
        *,
        api_key: str,
        base_url: str,
        endpoint: str,
        params: dict[str, str],
        timeout: int,
    ) -> dict[str, object]:
        if endpoint == "/filings":
            raise RuntimeError("rate limited")
        return {
            "api_key_seen": bool(api_key),
            "base_url": base_url,
            "endpoint": endpoint,
            "params": params,
            "timeout": timeout,
        }

    monkeypatch.setattr(data_sources, "financial_datasets_get", fake_get)

    output_path = tmp_path / "financial-datasets-raw.json"
    result = data_sources.collect_financial_datasets(
        output_path=output_path,
        ticker="AAPL",
        market="US",
        timeout=7,
    )

    assert result.status == "partial"
    assert result.summary == {"calls_succeeded": 5, "calls_failed": 1}
    payload = json.loads(output_path.read_text())
    assert list(payload["calls"]) == [
        "financials_quarterly",
        "financials_ttm",
        "prices_recent",
        "filings",
        "insider_trades",
        "analyst_estimates",
    ]
    assert payload["calls"]["filings"] is None
    assert payload["errors"] == [
        {"endpoint": "/filings", "label": "filings", "message": "rate limited"}
    ]


def test_collect_ticker_sources_parallelizes_worker_sources_with_stable_order(
    monkeypatch,
    tmp_path: Path,
) -> None:
    import scripts.run_abc_parity as runner

    monkeypatch.setenv("SAA_SOURCE_MAX_WORKERS", "2")
    run_id = f"pytest_{tmp_path.name}_parallel_AAPL_A"

    def fake_financial_datasets(
        *,
        output_path: Path,
        ticker: str,
        market: str,
        timeout: int,
    ) -> runner.SourceResult:
        runner.write_json(output_path, {"source": "financial_datasets", "status": "success"})
        return runner.SourceResult(
            source="financial_datasets",
            status="success",
            output_path=output_path,
            summary={"ticker": ticker, "market": market, "timeout": timeout},
        )

    def fake_yfinance(
        *,
        output_path: Path,
        ticker: str,
        market: str,
        timeout: int,
    ) -> runner.SourceResult:
        runner.write_json(output_path, {"source": "yfinance", "status": "success"})
        return runner.SourceResult(
            source="yfinance",
            status="success",
            output_path=output_path,
            summary={"ticker": ticker, "market": market, "timeout": timeout},
        )

    monkeypatch.setattr(runner, "collect_financial_datasets", fake_financial_datasets)
    monkeypatch.setattr(runner, "collect_yfinance", fake_yfinance)

    summary = runner.collect_ticker_sources(
        run_id=run_id,
        ticker="AAPL",
        market="US",
        mode="A",
        language="en",
        peer_tickers=[],
        skip_network=False,
        timeout=9,
    )

    assert [source["source"] for source in summary["sources"]] == [
        "financial_datasets",
        "dart",
        "yfinance",
    ]
    assert summary["collection_strategy"]["source_max_workers"] == 2
    assert summary["collection_strategy"]["parallel_sources"] == [
        "financial_datasets",
        "yfinance",
    ]
    assert summary["collection_strategy"]["immediate_sources"] == ["dart"]


def test_yfinance_collector_cache_reuses_fresh_artifact(
    monkeypatch,
    tmp_path: Path,
) -> None:
    import scripts.parity.data_sources as data_sources

    monkeypatch.setenv("SAA_COLLECTOR_CACHE_DIR", str(tmp_path / "source-cache"))
    monkeypatch.setenv("SAA_YFINANCE_CACHE_TTL_SECONDS", "3600")
    calls = {"count": 0}

    def fake_run_existing_collector(
        *,
        command: list[str],
        output_path: Path,
        source: str,
        ticker: str | None,
    ) -> data_sources.SourceResult:
        calls["count"] += 1
        data_sources.write_json(
            output_path,
            {
                "schema_version": "abc-parity-yfinance-raw-v1",
                "source": source,
                "status": "success",
                "ticker": ticker,
                "collection_timestamp": "2026-05-28T00:00:00Z",
                "current_price": {"price": 123.45},
            },
        )
        return data_sources.SourceResult(
            source=source,
            status="success",
            output_path=output_path,
            summary={"collector_called": calls["count"]},
        )

    monkeypatch.setattr(data_sources, "run_existing_collector", fake_run_existing_collector)

    first = data_sources.collect_yfinance(
        output_path=tmp_path / "first" / "yfinance-raw.json",
        ticker="AAPL",
        market="US",
    )
    second_path = tmp_path / "second" / "yfinance-raw.json"
    second = data_sources.collect_yfinance(
        output_path=second_path,
        ticker="AAPL",
        market="US",
    )

    assert first.status == "success"
    assert second.status == "cached"
    assert calls["count"] == 1
    cached_payload = json.loads(second_path.read_text())
    assert cached_payload["current_price"]["price"] == 123.45
    assert cached_payload["source_cache"]["status"] == "hit"
    assert (tmp_path / "source-cache" / "yfinance").exists()


def test_parse_stdout_json_accepts_multiline_json() -> None:
    from scripts.parity.data_sources import parse_stdout_json

    payload = parse_stdout_json(
        '{\n'
        '  "tickers_requested": ["SNOW"],\n'
        '  "tickers_collected": ["SNOW"],\n'
        '  "tickers_failed": []\n'
        '}'
    )

    assert payload["tickers_collected"] == ["SNOW"]
