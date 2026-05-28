#!/usr/bin/env python3
"""A/B/C production parity runner scaffold."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import BoundedSemaphore, Lock
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.parity.data_sources import (  # noqa: E402
    SourceResult,
    collect_dart,
    collect_financial_datasets,
    collect_fred,
    collect_peer_mini_fetch,
    collect_yfinance,
    load_json,
    skipped_artifact,
    utc_now,
    write_json,
)
from scripts.parity.analyst import build_analyst_handoff  # noqa: E402
from scripts.parity.calculations import build_calculation_handoff  # noqa: E402
from scripts.parity.comparison import build_mode_b_comparison_handoff  # noqa: E402
from scripts.parity.critic import build_critic_handoff, write_run_parity_summary  # noqa: E402
from scripts.parity.rendering import build_render_handoff  # noqa: E402
from scripts.parity.validation import build_validation_handoff  # noqa: E402


class ParityRunnerError(RuntimeError):
    pass


def main(argv: list[str] | None = None) -> int:
    run_started_at = utc_now()
    run_start = time.perf_counter()
    stage_timings: list[dict[str, Any]] = []
    stage_timings_lock = Lock()
    args = parse_args(argv)
    mode = args.mode.strip().upper()
    language = args.lang.strip().lower()
    primary_ticker = normalize_ticker(args.ticker)
    tickers = normalize_tickers(args.tickers) or [primary_ticker]
    if mode.strip().upper() == "B" and primary_ticker not in tickers:
        tickers = [primary_ticker, *tickers]
    market = normalize_market(args.market, primary_ticker, tickers)
    run_id = args.run_id.strip()
    request_payload = parse_env_json("STOCK_ANALYSIS_REQUEST_PAYLOAD")
    peer_tickers = resolve_peer_tickers(
        cli_value=args.peer_tickers,
        env_payload=request_payload,
        market=market,
        mode=mode,
        ticker=primary_ticker,
    )

    if mode not in {"A", "B", "C"}:
        raise ParityRunnerError("A/B/C parity runner only supports modes A, B, and C.")
    if mode == "B" and len(tickers) < 2:
        raise ParityRunnerError("Mode B requires --tickers with 2-5 symbols.")
    if len(tickers) > 5:
        raise ParityRunnerError("A/B/C parity runner supports at most 5 tickers.")
    if args.render_only and mode not in {"A", "B", "C"}:
        raise ParityRunnerError("--render-only currently supports Mode A, Mode B, and Mode C only.")

    paths = build_paths(run_id)
    paths["run_root"].mkdir(parents=True, exist_ok=True)
    request_start = time.perf_counter()
    write_json(
        paths["request"],
        {
            "schema_version": "abc-parity-request-v1",
            "ticker": primary_ticker,
            "tickers": tickers,
            "mode": mode,
            "language": language,
            "market": market,
            "run_id": run_id,
            "quality_target": os.environ.get("STOCK_ANALYSIS_QUALITY_TARGET", "parity"),
            "request_payload": request_payload,
            "peer_tickers": peer_tickers,
            "created_at": utc_now(),
        },
    )
    record_stage(
        stage_timings,
        "request_write",
        request_start,
        run_id=run_id,
    )

    stage_start = time.perf_counter()
    macro_result = (
        reuse_macro(paths=paths)
        if args.reuse_collected
        else collect_macro(paths=paths, market=market, skip_network=args.skip_network)
    )
    macro_duration = record_stage(
        stage_timings,
        "macro_collect",
        stage_start,
        market=market,
        reused=args.reuse_collected,
        skipped=args.skip_network,
    )
    macro_payload = result_payload(macro_result)
    attach_performance(macro_payload, duration_seconds=macro_duration)
    ticker_results = run_ticker_collection(
        args=args,
        language=language,
        mode=mode,
        peer_tickers=peer_tickers,
        run_id=run_id,
        stage_timings=stage_timings,
        stage_timings_lock=stage_timings_lock,
        tickers=tickers,
    )

    validation_results: list[dict[str, Any]] = []
    calculation_results: list[dict[str, Any]] = []
    analyst_results: list[dict[str, Any]] = []
    render_results: list[dict[str, Any]] = []
    critic_results: list[dict[str, Any]] = []
    comparison_results = []
    if not args.collect_only:
        ticker_pipeline_results = run_ticker_pipelines(
            args=args,
            language=language,
            mode=mode,
            run_id=run_id,
            stage_timings=stage_timings,
            stage_timings_lock=stage_timings_lock,
            tickers=tickers,
        )
        validation_results = compact_pipeline_results(ticker_pipeline_results, "validation")
        calculation_results = compact_pipeline_results(ticker_pipeline_results, "calculation")
        analyst_results = compact_pipeline_results(ticker_pipeline_results, "analyst")
        render_results = compact_pipeline_results(ticker_pipeline_results, "render")
        critic_results = compact_pipeline_results(ticker_pipeline_results, "critic")
        if (
            mode == "B"
            and not args.collect_only
            and not args.validate_only
            and not args.calculate_only
            and not args.analysis_only
        ):
            stage_start = time.perf_counter()
            comparison_result = build_mode_b_comparison_handoff(
                language=language,
                market=market,
                run_id=run_id,
                tickers=tickers,
            )
            duration = record_stage(
                stage_timings,
                "comparison",
                stage_start,
                market=market,
                tickers=tickers,
            )
            comparison_payload = comparison_result_payload(comparison_result)
            attach_performance(
                comparison_payload,
                duration_seconds=duration,
                artifact_measurements={
                    "comparison_input": measure_text_artifact(comparison_result.comparison_input_path),
                    "analysis_result": measure_text_artifact(comparison_result.analysis_result_path),
                    "html": measure_text_artifact(comparison_result.html_path),
                    "render_report": measure_text_artifact(comparison_result.render_report_path),
                    "quality_report": measure_text_artifact(comparison_result.quality_report_path),
                },
            )
            comparison_results.append(comparison_payload)

    parity_summary_path = None
    if critic_results or comparison_results:
        stage_start = time.perf_counter()
        parity_summary_path = str(write_run_parity_summary(run_id=run_id, tickers=tickers).relative_to(REPO_ROOT))
        record_stage(
            stage_timings,
            "parity_summary",
            stage_start,
            run_id=run_id,
        )

    run_completed_at = utc_now()
    summary = {
        "schema_version": "abc-parity-collection-summary-v1",
        "run_id": run_id,
        "mode": mode,
        "language": language,
        "market": market,
        "tickers": tickers,
        "macro": macro_payload,
        "ticker_results": ticker_results,
        "validation_results": validation_results,
        "calculation_results": calculation_results,
        "analyst_results": analyst_results,
        "render_results": render_results,
        "critic_results": critic_results,
        "comparison_results": comparison_results,
        "abc_parity_summary_path": parity_summary_path,
        "performance": build_run_performance(
            analyst_results=analyst_results,
            completed_at=run_completed_at,
            stage_timings=stage_timings,
            started_at=run_started_at,
            total_duration_seconds=elapsed_seconds(run_start),
        ),
        "created_at": utc_now(),
    }
    write_json(paths["run_metadata"], summary)
    print(json.dumps(summary, ensure_ascii=False))

    if args.collect_only or args.validate_only or args.calculate_only or args.analysis_only or args.render_only or args.critic_only:
        return 0

    raise ParityRunnerError(
        "Session 9 implements collection, validation, calculations, analyst pass, Mode A/C rendering, Mode B comparison, and critic gate. Use a stop flag such as --critic-only for controlled runs."
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run A/B/C parity data collection")
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--tickers", default="")
    parser.add_argument("--mode", required=True, choices=["A", "B", "C", "a", "b", "c"])
    parser.add_argument("--lang", required=True, choices=["ko", "en"])
    parser.add_argument("--market", required=True, choices=["US", "KR", "mixed", "auto"])
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--collect-only", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--calculate-only", action="store_true")
    parser.add_argument("--analysis-only", action="store_true")
    parser.add_argument("--render-only", action="store_true")
    parser.add_argument("--critic-only", action="store_true")
    parser.add_argument("--reuse-collected", action="store_true")
    parser.add_argument("--reuse-stages", action="store_true")
    parser.add_argument("--skip-network", action="store_true")
    parser.add_argument("--peer-tickers", default="")
    parser.add_argument("--timeout", type=int, default=20)
    args = parser.parse_args(argv)
    selected_stops = sum(
        bool(value)
        for value in (
            args.collect_only,
            args.validate_only,
            args.calculate_only,
            args.analysis_only,
            args.render_only,
            args.critic_only,
        )
    )
    if selected_stops > 1:
        parser.error("--collect-only, --validate-only, --calculate-only, --analysis-only, --render-only, and --critic-only are mutually exclusive")
    return args


def normalize_ticker(value: str) -> str:
    ticker = value.strip().upper()
    if not ticker or len(ticker) > 32:
        raise ParityRunnerError(f"Invalid ticker: {value!r}")
    return ticker


def normalize_tickers(value: str) -> list[str]:
    tickers: list[str] = []
    for raw in value.replace(";", ",").split(","):
        raw = raw.strip()
        if not raw:
            continue
        ticker = normalize_ticker(raw)
        if ticker not in tickers:
            tickers.append(ticker)
    return tickers


def normalize_market(value: str, ticker: str, tickers: list[str]) -> str:
    if value == "mixed" and len(tickers) == 1:
        return "KR" if ticker.isdigit() and len(ticker) == 6 else "US"
    if value != "auto":
        return value
    inferred = ["KR" if item.isdigit() and len(item) == 6 else "US" for item in tickers]
    return inferred[0] if len(set(inferred)) == 1 else "mixed"


DEFAULT_US_PEER_SETS: dict[str, list[str]] = {
    "AAPL": ["MSFT", "GOOGL", "META"],
    "AMZN": ["GOOGL", "MSFT", "META"],
    "GOOGL": ["MSFT", "META", "AMZN"],
    "META": ["GOOGL", "SNAP", "PINS"],
    "MSFT": ["GOOGL", "AMZN", "ORCL"],
    "NVDA": ["AMD", "AVGO", "TSM"],
    "PLTR": ["SNOW", "DDOG", "CRWD"],
    "TSLA": ["RIVN", "GM", "F"],
}


def resolve_peer_tickers(
    *,
    cli_value: str,
    env_payload: dict[str, Any],
    market: str,
    mode: str,
    ticker: str,
) -> list[str]:
    if mode != "C" or market != "US":
        return []
    candidates = normalize_tickers(cli_value)
    if not candidates:
        payload_peers = env_payload.get("peer_tickers") if isinstance(env_payload, dict) else None
        if isinstance(payload_peers, list):
            candidates = normalize_tickers(",".join(str(item) for item in payload_peers))
        elif isinstance(payload_peers, str):
            candidates = normalize_tickers(payload_peers)
    if not candidates:
        candidates = DEFAULT_US_PEER_SETS.get(ticker, ["MSFT", "GOOGL", "META"])
    return [peer for peer in candidates if peer != ticker][:5]


def build_paths(run_id: str) -> dict[str, Path]:
    run_root = REPO_ROOT / "output" / "runs" / run_id
    return {
        "run_root": run_root,
        "macro_root": run_root / "macro",
        "request": run_root / "request.json",
        "run_metadata": run_root / "run-metadata.json",
    }


def ticker_root(run_id: str, ticker: str) -> Path:
    return REPO_ROOT / "output" / "runs" / run_id / ticker


def collect_macro(*, paths: dict[str, Path], market: str, skip_network: bool) -> SourceResult:
    output_path = paths["macro_root"] / "fred-raw.json"
    if skip_network:
        return skipped_artifact(
            output_path=output_path,
            reason="skip_network",
            source="fred",
        )
    return collect_fred(output_path=output_path, market="KR" if market == "KR" else "US")


def reuse_macro(*, paths: dict[str, Path]) -> SourceResult:
    output_path = paths["macro_root"] / "fred-raw.json"
    if not output_path.exists():
        raise ParityRunnerError(f"--reuse-collected requested but missing {output_path}")
    return SourceResult(
        source="fred",
        status="reused",
        output_path=output_path,
        summary={"reason": "reuse_collected"},
        exit_code=0,
    )


def run_ticker_collection(
    *,
    args: argparse.Namespace,
    language: str,
    mode: str,
    peer_tickers: list[str],
    run_id: str,
    stage_timings: list[dict[str, Any]],
    stage_timings_lock: Any,
    tickers: list[str],
) -> list[dict[str, Any]]:
    max_workers = ticker_max_workers(tickers)

    def collect_one(ticker: str) -> dict[str, Any]:
        ticker_market = normalize_market(args.market, ticker, [ticker])
        stage_start = time.perf_counter()
        if args.reuse_collected:
            ticker_summary = reuse_ticker_sources(
                run_id=run_id,
                ticker=ticker,
                market=ticker_market,
            )
        else:
            ticker_summary = collect_ticker_sources(
                run_id=run_id,
                ticker=ticker,
                market=ticker_market,
                mode=mode,
                language=language,
                peer_tickers=peer_tickers,
                skip_network=args.skip_network,
                timeout=args.timeout,
            )
        duration = record_stage(
            stage_timings,
            "ticker_collect",
            stage_start,
            lock=stage_timings_lock,
            market=ticker_market,
            reused=args.reuse_collected,
            skipped=args.skip_network,
            ticker=ticker,
        )
        attach_performance(
            ticker_summary,
            duration_seconds=duration,
            artifact_measurements=measure_source_artifacts(run_id, ticker, mode=mode),
        )
        write_source_collection_summary(run_id, ticker, ticker_summary)
        return ticker_summary

    results = run_ordered_ticker_tasks(
        max_workers=max_workers,
        task=collect_one,
        task_name="ticker collection",
        tickers=tickers,
    )
    return [results[ticker] for ticker in tickers]


def run_ticker_pipelines(
    *,
    args: argparse.Namespace,
    language: str,
    mode: str,
    run_id: str,
    stage_timings: list[dict[str, Any]],
    stage_timings_lock: Any,
    tickers: list[str],
) -> list[dict[str, Any]]:
    max_workers = ticker_max_workers(tickers)
    analyst_gate = BoundedSemaphore(analyst_max_workers(len(tickers)))

    def run_one(ticker: str) -> dict[str, Any]:
        ticker_market = normalize_market(args.market, ticker, [ticker])
        pipeline: dict[str, Any] = {"ticker": ticker}
        pipeline["validation"] = run_validation_stage(
            language=language,
            market=ticker_market,
            mode=mode,
            reuse_stages=args.reuse_stages,
            run_id=run_id,
            stage_timings=stage_timings,
            stage_timings_lock=stage_timings_lock,
            ticker=ticker,
        )
        if args.validate_only:
            return pipeline

        pipeline["calculation"] = run_calculation_stage(
            language=language,
            market=ticker_market,
            mode=mode,
            reuse_stages=args.reuse_stages,
            run_id=run_id,
            stage_timings=stage_timings,
            stage_timings_lock=stage_timings_lock,
            ticker=ticker,
        )
        if args.calculate_only:
            return pipeline

        analyst_gate.acquire()
        try:
            pipeline["analyst"] = run_analyst_stage(
                language=language,
                market=ticker_market,
                mode=mode,
                reuse_stages=args.reuse_stages,
                run_id=run_id,
                stage_timings=stage_timings,
                stage_timings_lock=stage_timings_lock,
                ticker=ticker,
            )
        finally:
            analyst_gate.release()
        if args.analysis_only:
            return pipeline

        if mode in {"A", "C"}:
            pipeline["render"] = run_render_stage(
                language=language,
                market=ticker_market,
                mode=mode,
                reuse_stages=args.reuse_stages,
                run_id=run_id,
                stage_timings=stage_timings,
                stage_timings_lock=stage_timings_lock,
                ticker=ticker,
            )
        if not args.render_only:
            pipeline["critic"] = run_critic_stage(
                language=language,
                market=ticker_market,
                mode=mode,
                reuse_stages=args.reuse_stages,
                run_id=run_id,
                stage_timings=stage_timings,
                stage_timings_lock=stage_timings_lock,
                ticker=ticker,
            )
        return pipeline

    results = run_ordered_ticker_tasks(
        max_workers=max_workers,
        task=run_one,
        task_name="ticker pipeline",
        tickers=tickers,
    )
    return [results[ticker] for ticker in tickers]


def run_validation_stage(
    *,
    language: str,
    market: str,
    mode: str,
    reuse_stages: bool,
    run_id: str,
    stage_timings: list[dict[str, Any]],
    stage_timings_lock: Any,
    ticker: str,
) -> dict[str, Any]:
    stage_start = time.perf_counter()
    fingerprint = validation_input_fingerprint(run_id, ticker, market=market, mode=mode, language=language)
    cache_hit = False
    if reuse_stages:
        cached_payload = cached_validation_payload(
            run_id=run_id,
            ticker=ticker,
            input_fingerprint=fingerprint,
        )
        if cached_payload is not None:
            cache_hit = True
            duration = record_stage(
                stage_timings,
                "validation",
                stage_start,
                cache_hit=True,
                lock=stage_timings_lock,
                market=market,
                ticker=ticker,
            )
            attach_stage_cache_performance(
                cached_payload,
                duration_seconds=duration,
                input_fingerprint=fingerprint,
                stage="validation",
            )
            return cached_payload

    validation_result = build_validation_handoff(
        language=language,
        market=market,
        mode=mode,
        run_id=run_id,
        ticker=ticker,
    )
    duration = record_stage(
        stage_timings,
        "validation",
        stage_start,
        cache_hit=cache_hit,
        lock=stage_timings_lock,
        market=market,
        ticker=ticker,
    )
    validation_payload = validation_result_payload(validation_result)
    validation_measurements = {
        "validated_data": measure_text_artifact(validation_result.validated_data_path),
        "evidence_pack": measure_text_artifact(validation_result.evidence_pack_path),
        "context_budget": measure_text_artifact(validation_result.context_budget_path),
        "validation_summary": measure_text_artifact(validation_result.validation_summary_path),
    }
    attach_performance(
        validation_payload,
        duration_seconds=duration,
        artifact_measurements=validation_measurements,
    )
    update_json_file(
        validation_result.validation_summary_path,
        {
            "duration_seconds": duration,
            "performance": {
                "duration_seconds": duration,
                "artifact_measurements": compact_measurements(validation_measurements),
            },
        },
    )
    update_stage_cache(
        run_id=run_id,
        ticker=ticker,
        stage="validation",
        input_fingerprint=fingerprint,
        artifacts=[
            validation_result.validated_data_path,
            validation_result.evidence_pack_path,
            validation_result.context_budget_path,
            validation_result.validation_summary_path,
        ],
    )
    return validation_payload


def run_calculation_stage(
    *,
    language: str,
    market: str,
    mode: str,
    reuse_stages: bool,
    run_id: str,
    stage_timings: list[dict[str, Any]],
    stage_timings_lock: Any,
    ticker: str,
) -> dict[str, Any]:
    stage_start = time.perf_counter()
    fingerprint = calculation_input_fingerprint(run_id, ticker, market=market, mode=mode, language=language)
    cache_hit = False
    if reuse_stages:
        cached_payload = cached_calculation_payload(
            run_id=run_id,
            ticker=ticker,
            input_fingerprint=fingerprint,
        )
        if cached_payload is not None:
            cache_hit = True
            duration = record_stage(
                stage_timings,
                "calculation",
                stage_start,
                cache_hit=True,
                lock=stage_timings_lock,
                market=market,
                ticker=ticker,
            )
            attach_stage_cache_performance(
                cached_payload,
                duration_seconds=duration,
                input_fingerprint=fingerprint,
                stage="calculation",
            )
            return cached_payload

    calculation_result = build_calculation_handoff(
        language=language,
        market=market,
        mode=mode,
        run_id=run_id,
        ticker=ticker,
    )
    duration = record_stage(
        stage_timings,
        "calculation",
        stage_start,
        cache_hit=cache_hit,
        lock=stage_timings_lock,
        market=market,
        ticker=ticker,
    )
    calculation_payload = calculation_result_payload(calculation_result)
    attach_performance(
        calculation_payload,
        duration_seconds=duration,
        artifact_measurements={
            "deterministic_calculations": measure_text_artifact(calculation_result.calculations_path),
            "context_budget": measure_text_artifact(calculation_result.context_budget_path),
        },
    )
    update_stage_cache(
        run_id=run_id,
        ticker=ticker,
        stage="calculation",
        input_fingerprint=fingerprint,
        artifacts=[
            calculation_result.calculations_path,
            calculation_result.context_budget_path,
        ],
    )
    return calculation_payload


def run_analyst_stage(
    *,
    language: str,
    market: str,
    mode: str,
    reuse_stages: bool,
    run_id: str,
    stage_timings: list[dict[str, Any]],
    stage_timings_lock: Any,
    ticker: str,
) -> dict[str, Any]:
    stage_start = time.perf_counter()
    fingerprint = analyst_input_fingerprint(run_id, ticker, market=market, mode=mode, language=language)
    cache_hit = False
    if reuse_stages:
        cached_payload = cached_analyst_payload(
            run_id=run_id,
            ticker=ticker,
            input_fingerprint=fingerprint,
        )
        if cached_payload is not None:
            cache_hit = True
            duration = record_stage(
                stage_timings,
                "analyst",
                stage_start,
                backend=cached_payload.get("provider"),
                cache_hit=True,
                lock=stage_timings_lock,
                market=market,
                model=cached_payload.get("model"),
                ticker=ticker,
            )
            attach_stage_cache_performance(
                cached_payload,
                duration_seconds=duration,
                input_fingerprint=fingerprint,
                stage="analyst",
            )
            return cached_payload

    analyst_result = build_analyst_handoff(
        language=language,
        market=market,
        mode=mode,
        run_id=run_id,
        ticker=ticker,
    )
    duration = record_stage(
        stage_timings,
        "analyst",
        stage_start,
        backend=analyst_result.provider,
        cache_hit=cache_hit,
        lock=stage_timings_lock,
        market=market,
        model=analyst_result.model,
        ticker=ticker,
    )
    analyst_payload = analyst_result_payload(analyst_result)
    analyst_input_measurement = measure_text_artifact(analyst_result.analyst_input_path)
    attach_performance(
        analyst_payload,
        duration_seconds=duration,
        analyst_input=analyst_input_measurement,
        backend_usage=load_backend_usage(analyst_result.analysis_result_path),
        artifact_measurements={
            "analyst_input": analyst_input_measurement,
            "analysis_result": measure_text_artifact(analyst_result.analysis_result_path),
        },
    )
    update_stage_cache(
        run_id=run_id,
        ticker=ticker,
        stage="analyst",
        input_fingerprint=fingerprint,
        artifacts=[
            analyst_result.analyst_input_path,
            ticker_root(run_id, ticker) / "analyst-input.compact.json",
            analyst_result.analysis_result_path,
            ticker_root(run_id, ticker) / "analyst-summary.json",
        ],
    )
    return analyst_payload


def run_render_stage(
    *,
    language: str,
    market: str,
    mode: str,
    reuse_stages: bool,
    run_id: str,
    stage_timings: list[dict[str, Any]],
    stage_timings_lock: Any,
    ticker: str,
) -> dict[str, Any]:
    stage_start = time.perf_counter()
    fingerprint = render_input_fingerprint(run_id, ticker, market=market, mode=mode, language=language)
    cache_hit = False
    if reuse_stages:
        cached_payload = cached_render_payload(
            mode=mode,
            run_id=run_id,
            ticker=ticker,
            input_fingerprint=fingerprint,
        )
        if cached_payload is not None:
            cache_hit = True
            duration = record_stage(
                stage_timings,
                "render",
                stage_start,
                cache_hit=True,
                lock=stage_timings_lock,
                market=market,
                ticker=ticker,
            )
            attach_stage_cache_performance(
                cached_payload,
                duration_seconds=duration,
                input_fingerprint=fingerprint,
                stage="render",
            )
            return cached_payload

    render_result = build_render_handoff(
        language=language,
        market=market,
        mode=mode,
        run_id=run_id,
        ticker=ticker,
    )
    duration = record_stage(
        stage_timings,
        "render",
        stage_start,
        cache_hit=cache_hit,
        lock=stage_timings_lock,
        market=market,
        ticker=ticker,
    )
    render_payload = render_result_payload(render_result)
    attach_performance(
        render_payload,
        duration_seconds=duration,
        artifact_measurements={
            "html": measure_text_artifact(render_result.html_path),
            "render_report": measure_text_artifact(render_result.render_report_path),
        },
    )
    update_stage_cache(
        run_id=run_id,
        ticker=ticker,
        stage="render",
        input_fingerprint=fingerprint,
        artifacts=[
            render_result.html_path,
            render_result.render_report_path,
        ],
    )
    return render_payload


def run_critic_stage(
    *,
    language: str,
    market: str,
    mode: str,
    reuse_stages: bool,
    run_id: str,
    stage_timings: list[dict[str, Any]],
    stage_timings_lock: Any,
    ticker: str,
) -> dict[str, Any]:
    stage_start = time.perf_counter()
    fingerprint = critic_input_fingerprint(run_id, ticker, market=market, mode=mode, language=language)
    cache_hit = False
    if reuse_stages:
        cached_payload = cached_critic_payload(
            run_id=run_id,
            ticker=ticker,
            input_fingerprint=fingerprint,
        )
        if cached_payload is not None:
            cache_hit = True
            duration = record_stage(
                stage_timings,
                "critic",
                stage_start,
                cache_hit=True,
                lock=stage_timings_lock,
                market=market,
                ticker=ticker,
            )
            attach_stage_cache_performance(
                cached_payload,
                duration_seconds=duration,
                input_fingerprint=fingerprint,
                stage="critic",
            )
            return cached_payload

    critic_result = build_critic_handoff(
        language=language,
        market=market,
        mode=mode,
        run_id=run_id,
        ticker=ticker,
    )
    duration = record_stage(
        stage_timings,
        "critic",
        stage_start,
        cache_hit=cache_hit,
        lock=stage_timings_lock,
        market=market,
        ticker=ticker,
    )
    critic_payload = critic_result_payload(critic_result)
    attach_performance(
        critic_payload,
        duration_seconds=duration,
        artifact_measurements={
            "quality_report": measure_text_artifact(critic_result.quality_report_path),
            "critic_review": measure_text_artifact(critic_result.critic_review_path),
            "critic_loop_result": measure_text_artifact(critic_result.loop_result_path),
        },
    )
    update_stage_cache(
        run_id=run_id,
        ticker=ticker,
        stage="critic",
        input_fingerprint=critic_input_fingerprint(
            run_id,
            ticker,
            market=market,
            mode=mode,
            language=language,
        ),
        artifacts=[
            critic_result.quality_report_path,
            critic_result.critic_review_path,
            critic_result.loop_result_path,
        ],
    )
    return critic_payload


def run_ordered_ticker_tasks(
    *,
    max_workers: int,
    task: Callable[[str], dict[str, Any]],
    task_name: str,
    tickers: list[str],
) -> dict[str, dict[str, Any]]:
    if max_workers == 1:
        return {ticker: task(ticker) for ticker in tickers}

    results: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="ticker-pipeline") as executor:
        futures = {executor.submit(task, ticker): ticker for ticker in tickers}
        for future in as_completed(futures):
            ticker = futures[future]
            try:
                results[ticker] = future.result()
            except Exception as exc:  # noqa: BLE001 - keep the ticker in the user-facing failure
                raise ParityRunnerError(f"{task_name} failed for {ticker}: {exc}") from exc
    return results


def compact_pipeline_results(
    pipeline_results: list[dict[str, Any]],
    key: str,
) -> list[dict[str, Any]]:
    return [
        payload
        for result in pipeline_results
        if isinstance((payload := result.get(key)), dict)
    ]


def ticker_max_workers(tickers: list[str]) -> int:
    return env_int("SAA_TICKER_MAX_WORKERS", 3, maximum=max(len(tickers), 1))


def analyst_max_workers(ticker_count: int) -> int:
    backend = os.environ.get("ANALYST_BACKEND", "").strip()
    default = 4 if backend in {"fixture", "deterministic_fixture", "local_fixture"} else 1
    return env_int("SAA_ANALYST_MAX_WORKERS", default, maximum=max(ticker_count, 1))


def validation_input_fingerprint(
    run_id: str,
    ticker: str,
    *,
    language: str,
    market: str,
    mode: str,
) -> str:
    root = ticker_root(run_id, ticker)
    return fingerprint_files(
        stage="validation",
        paths=[
            root / "research-plan.json",
            root / "financial-datasets-raw.json",
            root / "dart-api-raw.json",
            root / "yfinance-raw.json",
            root.parent / "macro" / "fred-raw.json",
        ],
        metadata={"language": language, "market": market, "mode": mode, "ticker": ticker},
    )


def calculation_input_fingerprint(
    run_id: str,
    ticker: str,
    *,
    language: str,
    market: str,
    mode: str,
) -> str:
    root = ticker_root(run_id, ticker)
    return fingerprint_files(
        stage="calculation",
        paths=[root / "validated-data.json", root / "evidence-pack.json"],
        metadata={"language": language, "market": market, "mode": mode, "ticker": ticker},
    )


def analyst_input_fingerprint(
    run_id: str,
    ticker: str,
    *,
    language: str,
    market: str,
    mode: str,
) -> str:
    root = ticker_root(run_id, ticker)
    peer_paths = sorted((root / "peers").glob("*.json")) if (root / "peers").exists() else []
    return fingerprint_files(
        stage="analyst",
        paths=[
            root / "research-plan.json",
            root / "validated-data.json",
            root / "evidence-pack.json",
            root / "context-budget.json",
            root / "deterministic-calculations.json",
            root / "peer-fetch-summary.json",
            REPO_ROOT / ".claude" / "schemas" / "analysis-result.schema.json",
            REPO_ROOT / "config" / "model_registry.yaml",
            *peer_paths,
        ],
        metadata={
            "analyst_backend": os.environ.get("ANALYST_BACKEND", ""),
            "analyst_model": os.environ.get("ANALYST_MODEL", ""),
            "anthropic_model": os.environ.get("ANTHROPIC_MODEL", ""),
            "codex_model": os.environ.get("CODEX_MODEL", ""),
            "compact_input_schema_version": "abc-parity-compact-analyst-input-v1",
            "language": language,
            "market": market,
            "mode": mode,
            "openai_model": os.environ.get("OPENAI_MODEL", ""),
            "ticker": ticker,
        },
    )


def render_input_fingerprint(
    run_id: str,
    ticker: str,
    *,
    language: str,
    market: str,
    mode: str,
) -> str:
    root = ticker_root(run_id, ticker)
    return fingerprint_files(
        stage="render",
        paths=[
            root / "analysis-result.json",
            root / "validated-data.json",
            root / "deterministic-calculations.json",
            root / "evidence-pack.json",
        ],
        metadata={"language": language, "market": market, "mode": mode, "ticker": ticker},
    )


def critic_input_fingerprint(
    run_id: str,
    ticker: str,
    *,
    language: str,
    market: str,
    mode: str,
) -> str:
    root = ticker_root(run_id, ticker)
    html_path, render_report_path = render_artifact_paths(root, mode)
    return fingerprint_files(
        stage="critic",
        paths=[
            root / "research-plan.json",
            root / "validated-data.json",
            root / "evidence-pack.json",
            root / "context-budget.json",
            root / "analysis-result.json",
            html_path,
            render_report_path,
        ],
        metadata={"language": language, "market": market, "mode": mode, "ticker": ticker},
    )


def fingerprint_files(
    *,
    metadata: dict[str, Any],
    paths: list[Path | None],
    stage: str,
) -> str:
    hasher = hashlib.sha256()
    hasher.update(
        json.dumps(
            {"schema_version": "abc-parity-stage-fingerprint-v1", "stage": stage, **metadata},
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    )
    for path in paths:
        if path is None:
            continue
        resolved = path.resolve()
        hasher.update(display_path(resolved).encode("utf-8"))
        if not resolved.exists():
            hasher.update(b"\0missing")
            continue
        hasher.update(b"\0")
        hasher.update(resolved.read_bytes())
    return hasher.hexdigest()


def stage_cache_path(run_id: str, ticker: str) -> Path:
    return ticker_root(run_id, ticker) / "stage-cache.json"


def load_stage_cache(run_id: str, ticker: str) -> dict[str, Any]:
    cache = load_json(stage_cache_path(run_id, ticker))
    if not cache:
        return {"schema_version": "abc-parity-stage-cache-v1", "ticker": ticker, "stages": {}}
    if not isinstance(cache.get("stages"), dict):
        cache["stages"] = {}
    return cache


def update_stage_cache(
    *,
    artifacts: list[Path],
    input_fingerprint: str,
    run_id: str,
    stage: str,
    ticker: str,
) -> None:
    cache = load_stage_cache(run_id, ticker)
    cache["ticker"] = ticker
    cache["updated_at"] = utc_now()
    cache["stages"][stage] = {
        "input_fingerprint": input_fingerprint,
        "artifacts": [display_path(path) for path in artifacts],
        "completed_at": utc_now(),
    }
    write_json(stage_cache_path(run_id, ticker), cache)


def stage_cache_matches(
    *,
    artifacts: list[Path],
    input_fingerprint: str,
    run_id: str,
    stage: str,
    ticker: str,
) -> bool:
    cache = load_stage_cache(run_id, ticker)
    entry = (cache.get("stages") or {}).get(stage)
    if not isinstance(entry, dict):
        return False
    if entry.get("input_fingerprint") != input_fingerprint:
        return False
    cached_artifacts = [
        REPO_ROOT / path
        for path in entry.get("artifacts", [])
        if isinstance(path, str)
    ]
    required = artifacts or cached_artifacts
    return bool(required) and all(path.exists() for path in required)


def cached_validation_payload(
    *,
    input_fingerprint: str,
    run_id: str,
    ticker: str,
) -> dict[str, Any] | None:
    root = ticker_root(run_id, ticker)
    artifacts = [
        root / "validated-data.json",
        root / "evidence-pack.json",
        root / "context-budget.json",
        root / "validation-summary.json",
    ]
    if not stage_cache_matches(
        artifacts=artifacts,
        input_fingerprint=input_fingerprint,
        run_id=run_id,
        stage="validation",
        ticker=ticker,
    ):
        return None
    summary = load_json(root / "validation-summary.json")
    evidence = load_json(root / "evidence-pack.json")
    return {
        "ticker": ticker,
        "artifact_root": str(root.relative_to(REPO_ROOT)),
        "validated_data_path": str((root / "validated-data.json").relative_to(REPO_ROOT)),
        "evidence_pack_path": str((root / "evidence-pack.json").relative_to(REPO_ROOT)),
        "context_budget_path": str((root / "context-budget.json").relative_to(REPO_ROOT)),
        "validation_summary_path": str((root / "validation-summary.json").relative_to(REPO_ROOT)),
        "overall_grade": summary.get("overall_grade"),
        "fact_count": summary.get("fact_count", len(evidence.get("facts") or [])),
        "excluded_count": summary.get("excluded_count", len(evidence.get("exclusions") or [])),
    }


def cached_calculation_payload(
    *,
    input_fingerprint: str,
    run_id: str,
    ticker: str,
) -> dict[str, Any] | None:
    root = ticker_root(run_id, ticker)
    artifacts = [root / "deterministic-calculations.json", root / "context-budget.json"]
    if not stage_cache_matches(
        artifacts=artifacts,
        input_fingerprint=input_fingerprint,
        run_id=run_id,
        stage="calculation",
        ticker=ticker,
    ):
        return None
    calculations = load_json(root / "deterministic-calculations.json")
    return {
        "ticker": ticker,
        "artifact_root": str(root.relative_to(REPO_ROOT)),
        "calculations_path": str((root / "deterministic-calculations.json").relative_to(REPO_ROOT)),
        "context_budget_path": str((root / "context-budget.json").relative_to(REPO_ROOT)),
        "status": calculations.get("status"),
        "scenario_status": (calculations.get("scenario_analysis") or {}).get("status"),
        "dcf_status": (calculations.get("dcf_analysis") or {}).get("status"),
    }


def cached_analyst_payload(
    *,
    input_fingerprint: str,
    run_id: str,
    ticker: str,
) -> dict[str, Any] | None:
    root = ticker_root(run_id, ticker)
    artifacts = [
        root / "analyst-input.json",
        root / "analyst-input.compact.json",
        root / "analysis-result.json",
        root / "analyst-summary.json",
    ]
    if not stage_cache_matches(
        artifacts=artifacts,
        input_fingerprint=input_fingerprint,
        run_id=run_id,
        stage="analyst",
        ticker=ticker,
    ):
        return None
    summary = load_json(root / "analyst-summary.json")
    analysis = load_json(root / "analysis-result.json")
    backend = (analysis.get("run_context") or {}).get("backend") if isinstance(analysis.get("run_context"), dict) else {}
    backend = backend if isinstance(backend, dict) else {}
    return {
        "ticker": ticker,
        "artifact_root": str(root.relative_to(REPO_ROOT)),
        "analyst_input_path": str((root / "analyst-input.json").relative_to(REPO_ROOT)),
        "analysis_result_path": str((root / "analysis-result.json").relative_to(REPO_ROOT)),
        "provider": summary.get("provider") or backend.get("provider"),
        "model": summary.get("model") or backend.get("model"),
        "status": "success",
    }


def cached_render_payload(
    *,
    input_fingerprint: str,
    mode: str,
    run_id: str,
    ticker: str,
) -> dict[str, Any] | None:
    root = ticker_root(run_id, ticker)
    html_path, report_path = render_artifact_paths(root, mode)
    artifacts = [path for path in (html_path, report_path) if path is not None]
    if not stage_cache_matches(
        artifacts=artifacts,
        input_fingerprint=input_fingerprint,
        run_id=run_id,
        stage="render",
        ticker=ticker,
    ):
        return None
    report = load_json(report_path) if report_path is not None else {}
    return {
        "ticker": ticker,
        "artifact_root": str(root.relative_to(REPO_ROOT)),
        "html_path": str(html_path.relative_to(REPO_ROOT)) if html_path is not None else None,
        "render_report_path": str(report_path.relative_to(REPO_ROOT)) if report_path is not None else None,
        "status": report.get("status"),
        "metrics": (report.get("validation") or {}).get("metrics") or report.get("metrics") or {},
    }


def cached_critic_payload(
    *,
    input_fingerprint: str,
    run_id: str,
    ticker: str,
) -> dict[str, Any] | None:
    root = ticker_root(run_id, ticker)
    artifacts = [
        root / "quality-report.json",
        root / "critic-review.json",
        root / "critic-loop-result.json",
    ]
    if not stage_cache_matches(
        artifacts=artifacts,
        input_fingerprint=input_fingerprint,
        run_id=run_id,
        stage="critic",
        ticker=ticker,
    ):
        return None
    loop = load_json(root / "critic-loop-result.json")
    quality = load_json(root / "quality-report.json")
    return {
        "ticker": ticker,
        "artifact_root": str(root.relative_to(REPO_ROOT)),
        "quality_report_path": str((root / "quality-report.json").relative_to(REPO_ROOT)),
        "critic_review_path": str((root / "critic-review.json").relative_to(REPO_ROOT)),
        "loop_result_path": str((root / "critic-loop-result.json").relative_to(REPO_ROOT)),
        "status": loop.get("critic_overall"),
        "patch_status": loop.get("patch_status"),
        "delivery_ready": bool((quality.get("delivery_gate") or {}).get("ready_for_delivery")),
        "failing_items": loop.get("failing_items") or [],
    }


def render_artifact_paths(root: Path, mode: str) -> tuple[Path | None, Path | None]:
    if mode == "A":
        return root / "mode-a-briefing.html", root / "mode-a-render-report.json"
    if mode == "C":
        return root / "mode-c-dashboard.html", root / "mode-c-render-report.json"
    return None, None


def attach_stage_cache_performance(
    payload: dict[str, Any],
    *,
    duration_seconds: float,
    input_fingerprint: str,
    stage: str,
) -> None:
    metrics: dict[str, Any] = {
        "artifact_measurements": measure_payload_artifacts(payload),
        "cache": {
            "enabled": True,
            "hit": True,
            "input_fingerprint": input_fingerprint,
            "stage": stage,
        },
    }
    analyst_input_path = payload.get("analyst_input_path")
    if isinstance(analyst_input_path, str):
        metrics["analyst_input"] = measure_text_artifact(REPO_ROOT / analyst_input_path)
    analysis_path = payload.get("analysis_result_path")
    if isinstance(analysis_path, str):
        metrics["backend_usage"] = load_backend_usage(REPO_ROOT / analysis_path)
    attach_performance(payload, duration_seconds=duration_seconds, **metrics)


def measure_payload_artifacts(payload: dict[str, Any]) -> dict[str, Any]:
    measurements = {}
    for key, value in payload.items():
        if not key.endswith("_path") or key == "artifact_root" or not isinstance(value, str):
            continue
        measurement = measure_text_artifact(REPO_ROOT / value)
        if measurement is not None:
            measurements[key.removesuffix("_path")] = measurement
    return measurements


def collect_ticker_sources(
    *,
    language: str,
    market: str,
    mode: str,
    peer_tickers: list[str],
    run_id: str,
    skip_network: bool,
    ticker: str,
    timeout: int,
) -> dict[str, Any]:
    root = ticker_root(run_id, ticker)
    root.mkdir(parents=True, exist_ok=True)
    write_json(
        root / "research-plan.json",
        {
            "schema_version": "abc-parity-research-plan-v1",
            "ticker": ticker,
            "market": market,
            "data_mode": "enhanced",
            "requested_mode": "enhanced",
            "effective_mode": None,
            "source_profile": None,
            "source_tier": None,
            "confidence_cap": None,
            "output_mode": mode,
            "output_language": language,
            "analysis_date": utc_now()[:10],
            "analysis_framework_path": analysis_framework_path(mode),
            "data_profile": "enhanced_if_available",
            "required_sources": required_sources_for_market(market),
            "tier1_calls": required_sources_for_market(market),
            "tier2_searches": [],
            "tier2_fetches": [],
            "macro_search_required": True,
            "macro_factors": ["rates", "inflation", "growth"],
            "run_context": {
                "run_id": run_id,
                "artifact_root": str(root.relative_to(REPO_ROOT)),
                "ticker": ticker,
            },
            "created_at": utc_now(),
        },
    )

    if skip_network:
        results = [
            skipped_artifact(
                output_path=root / "financial-datasets-raw.json",
                reason="skip_network",
                source="financial_datasets",
                ticker=ticker,
            ),
            skipped_artifact(
                output_path=root / "dart-api-raw.json",
                reason="skip_network",
                source="dart",
                ticker=ticker,
            ),
            skipped_artifact(
                output_path=root / "yfinance-raw.json",
                reason="skip_network",
                source="yfinance",
                ticker=ticker,
            ),
        ]
        if mode == "C":
            results.append(
                skipped_artifact(
                    output_path=root / "peer-fetch-summary.json",
                    reason="skip_network",
                    source="peer_mini_fetch",
                    ticker=ticker,
                )
            )
        collection_strategy = {
            "source_max_workers": 0,
            "parallel_sources": [],
            "immediate_sources": [result.source for result in results],
            "skipped": True,
        }
    else:
        source_calls = [
            (
                "financial_datasets",
                root / "financial-datasets-raw.json",
                lambda: collect_financial_datasets(
                    output_path=root / "financial-datasets-raw.json",
                    ticker=ticker,
                    market=market,
                    timeout=timeout,
                ),
                market == "US",
            ),
            (
                "dart",
                root / "dart-api-raw.json",
                lambda: collect_dart(
                    output_path=root / "dart-api-raw.json",
                    ticker=ticker,
                    market=market,
                ),
                market == "KR",
            ),
            (
                "yfinance",
                root / "yfinance-raw.json",
                lambda: collect_yfinance(
                    output_path=root / "yfinance-raw.json",
                    ticker=ticker,
                    market=market,
                    timeout=timeout,
                ),
                True,
            ),
        ]
        if mode == "C":
            source_calls.append(
                (
                    "peer_mini_fetch",
                    root / "peer-fetch-summary.json",
                    lambda: collect_peer_mini_fetch(
                        output_dir=root / "peers",
                        summary_path=root / "peer-fetch-summary.json",
                        tickers=peer_tickers,
                        timeout=timeout,
                    ),
                    bool(peer_tickers),
                )
            )
        results, collection_strategy = run_ticker_source_calls(
            source_calls,
            ticker=ticker,
        )

    summary = {
        "schema_version": "abc-parity-source-collection-summary-v1",
        "ticker": ticker,
        "market": market,
        "collection_strategy": collection_strategy,
        "sources": [result_payload(result) for result in results],
        "created_at": utc_now(),
    }
    write_json(root / "source-collection-summary.json", summary)
    return summary


def reuse_ticker_sources(*, market: str, run_id: str, ticker: str) -> dict[str, Any]:
    root = ticker_root(run_id, ticker)
    summary_path = root / "source-collection-summary.json"
    if summary_path.exists():
        summary = load_json(summary_path)
        if summary:
            summary["reused_at"] = utc_now()
            return summary
    expected = [
        root / "financial-datasets-raw.json",
        root / "dart-api-raw.json",
        root / "yfinance-raw.json",
    ]
    missing = [str(path) for path in expected if not path.exists()]
    if missing:
        raise ParityRunnerError(
            "--reuse-collected requested but missing raw artifacts: " + ", ".join(missing)
        )
    return {
        "schema_version": "abc-parity-source-collection-summary-v1",
        "ticker": ticker,
        "market": market,
        "sources": [
            {
                "source": path.name.removesuffix("-raw.json"),
                "status": "reused",
                "output_path": str(path),
                "exit_code": 0,
                "summary": {"reason": "reuse_collected"},
            }
            for path in expected
        ],
        "created_at": utc_now(),
    }


def run_ticker_source_calls(
    source_calls: list[tuple[str, Path, Callable[[], SourceResult], bool]],
    *,
    ticker: str,
) -> tuple[list[SourceResult], dict[str, Any]]:
    results_by_source: dict[str, SourceResult] = {}
    immediate_sources: list[str] = []
    worker_calls: list[tuple[str, Path, Callable[[], SourceResult]]] = []
    for source, output_path, collect, use_worker in source_calls:
        if use_worker:
            worker_calls.append((source, output_path, collect))
        else:
            immediate_sources.append(source)
            results_by_source[source] = collect_source_safely(
                collect=collect,
                output_path=output_path,
                source=source,
                ticker=ticker,
            )

    source_max_workers = 0
    if worker_calls:
        source_max_workers = env_int(
            "SAA_SOURCE_MAX_WORKERS",
            3,
            maximum=len(worker_calls),
        )
        if source_max_workers == 1:
            for source, output_path, collect in worker_calls:
                results_by_source[source] = collect_source_safely(
                    collect=collect,
                    output_path=output_path,
                    source=source,
                    ticker=ticker,
                )
        else:
            with ThreadPoolExecutor(
                max_workers=source_max_workers,
                thread_name_prefix="ticker-source",
            ) as executor:
                futures = {
                    executor.submit(collect): (source, output_path)
                    for source, output_path, collect in worker_calls
                }
                for future in as_completed(futures):
                    source, output_path = futures[future]
                    results_by_source[source] = future_source_result(
                        future=future,
                        output_path=output_path,
                        source=source,
                        ticker=ticker,
                    )

    ordered_results = [
        results_by_source[source]
        for source, _output_path, _collect, _use_worker in source_calls
    ]
    strategy = {
        "source_max_workers": source_max_workers,
        "parallel_sources": [source for source, _output_path, _collect in worker_calls],
        "immediate_sources": immediate_sources,
        "skipped": False,
    }
    return ordered_results, strategy


def collect_source_safely(
    *,
    collect: Callable[[], SourceResult],
    output_path: Path,
    source: str,
    ticker: str,
) -> SourceResult:
    try:
        return collect()
    except Exception as exc:  # noqa: BLE001 - source failures must be artifacted
        return failed_source_artifact(
            message=str(exc) or exc.__class__.__name__,
            output_path=output_path,
            source=source,
            ticker=ticker,
        )


def future_source_result(
    *,
    future: Any,
    output_path: Path,
    source: str,
    ticker: str,
) -> SourceResult:
    try:
        return future.result()
    except Exception as exc:  # noqa: BLE001 - source failures must be artifacted
        return failed_source_artifact(
            message=str(exc) or exc.__class__.__name__,
            output_path=output_path,
            source=source,
            ticker=ticker,
        )


def failed_source_artifact(
    *,
    message: str,
    output_path: Path,
    source: str,
    ticker: str,
) -> SourceResult:
    payload = {
        "schema_version": "abc-parity-raw-source-v1",
        "source": source,
        "status": "failed",
        "ticker": ticker,
        "collection_timestamp": utc_now(),
        "error": message[:500],
    }
    write_json(output_path, payload)
    return SourceResult(
        source=source,
        status="failed",
        output_path=output_path,
        summary={"error": message[:500]},
        exit_code=1,
    )


def required_sources_for_market(market: str) -> list[str]:
    if market == "KR":
        return ["dart", "yfinance", "fred"]
    if market == "US":
        return ["financial_datasets", "yfinance", "fred"]
    return ["financial_datasets", "dart", "yfinance", "fred"]


def analysis_framework_path(mode: str) -> str:
    return {
        "A": "references/analysis-framework-briefing.md",
        "B": "references/analysis-framework-comparison.md",
        "C": "references/analysis-framework-dashboard.md",
    }.get(mode, "references/analysis-framework-briefing.md")


def result_payload(result: SourceResult) -> dict[str, Any]:
    return {
        "source": result.source,
        "status": result.status,
        "output_path": str(result.output_path),
        "exit_code": result.exit_code,
        "summary": result.summary,
    }


def validation_result_payload(result: Any) -> dict[str, Any]:
    return {
        "ticker": result.ticker,
        "artifact_root": str(result.artifact_root.relative_to(REPO_ROOT)),
        "validated_data_path": str(result.validated_data_path.relative_to(REPO_ROOT)),
        "evidence_pack_path": str(result.evidence_pack_path.relative_to(REPO_ROOT)),
        "context_budget_path": str(result.context_budget_path.relative_to(REPO_ROOT)),
        "validation_summary_path": str(result.validation_summary_path.relative_to(REPO_ROOT)),
        "overall_grade": result.overall_grade,
        "fact_count": result.fact_count,
        "excluded_count": result.excluded_count,
    }


def calculation_result_payload(result: Any) -> dict[str, Any]:
    return {
        "ticker": result.ticker,
        "artifact_root": str(result.artifact_root.relative_to(REPO_ROOT)),
        "calculations_path": str(result.calculations_path.relative_to(REPO_ROOT)),
        "context_budget_path": str(result.context_budget_path.relative_to(REPO_ROOT)),
        "status": result.status,
        "scenario_status": result.scenario_status,
        "dcf_status": result.dcf_status,
    }


def analyst_result_payload(result: Any) -> dict[str, Any]:
    return {
        "ticker": result.ticker,
        "artifact_root": str(result.artifact_root.relative_to(REPO_ROOT)),
        "analyst_input_path": str(result.analyst_input_path.relative_to(REPO_ROOT)),
        "analysis_result_path": str(result.analysis_result_path.relative_to(REPO_ROOT)),
        "provider": result.provider,
        "model": result.model,
        "status": result.status,
    }


def render_result_payload(result: Any) -> dict[str, Any]:
    return {
        "ticker": result.ticker,
        "artifact_root": str(result.artifact_root.relative_to(REPO_ROOT)),
        "html_path": str(result.html_path.relative_to(REPO_ROOT)),
        "render_report_path": str(result.render_report_path.relative_to(REPO_ROOT)),
        "status": result.status,
        "metrics": result.metrics,
    }


def comparison_result_payload(result: Any) -> dict[str, Any]:
    return {
        "artifact_root": str(result.artifact_root.relative_to(REPO_ROOT)),
        "comparison_input_path": str(result.comparison_input_path.relative_to(REPO_ROOT)),
        "analysis_result_path": str(result.analysis_result_path.relative_to(REPO_ROOT)),
        "html_path": str(result.html_path.relative_to(REPO_ROOT)),
        "render_report_path": str(result.render_report_path.relative_to(REPO_ROOT)),
        "quality_report_path": str(result.quality_report_path.relative_to(REPO_ROOT)),
        "status": result.status,
        "delivery_ready": result.delivery_ready,
        "metrics": result.metrics,
        "best_pick": result.best_pick,
    }


def critic_result_payload(result: Any) -> dict[str, Any]:
    return {
        "ticker": result.ticker,
        "artifact_root": str(result.artifact_root.relative_to(REPO_ROOT)),
        "quality_report_path": str(result.quality_report_path.relative_to(REPO_ROOT)),
        "critic_review_path": str(result.critic_review_path.relative_to(REPO_ROOT)),
        "loop_result_path": str(result.loop_result_path.relative_to(REPO_ROOT)),
        "status": result.status,
        "patch_status": result.patch_status,
        "delivery_ready": result.delivery_ready,
        "failing_items": result.failing_items,
    }


def parse_env_json(name: str) -> dict[str, Any]:
    raw = os.environ.get(name, "")
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {"_parse_error": f"{name} was not valid JSON"}
    return parsed if isinstance(parsed, dict) else {"value": parsed}


def env_int(name: str, default: int, *, minimum: int = 1, maximum: int | None = None) -> int:
    raw = os.environ.get(name, "").strip()
    try:
        value = int(raw) if raw else default
    except ValueError:
        value = default
    value = max(value, minimum)
    if maximum is not None:
        value = min(value, maximum)
    return value


def elapsed_seconds(started_at: float) -> float:
    return round(max(time.perf_counter() - started_at, 0.0), 6)


def record_stage(
    stage_timings: list[dict[str, Any]],
    stage: str,
    started_at: float,
    lock: Any | None = None,
    **metadata: Any,
) -> float:
    duration = elapsed_seconds(started_at)
    record = {
        "stage": stage,
        "duration_seconds": duration,
        **{key: value for key, value in metadata.items() if value is not None},
    }
    if lock is None:
        stage_timings.append(record)
    else:
        with lock:
            stage_timings.append(record)
    return duration


def attach_performance(payload: dict[str, Any], *, duration_seconds: float, **metrics: Any) -> None:
    clean_metrics = {key: value for key, value in metrics.items() if value is not None}
    payload["duration_seconds"] = duration_seconds
    payload["performance"] = {
        "duration_seconds": duration_seconds,
        **clean_metrics,
    }


def build_run_performance(
    *,
    analyst_results: list[dict[str, Any]],
    completed_at: str,
    stage_timings: list[dict[str, Any]],
    started_at: str,
    total_duration_seconds: float,
) -> dict[str, Any]:
    analyst_inputs = [
        ((result.get("performance") or {}).get("analyst_input") or {})
        for result in analyst_results
    ]
    return {
        "schema_version": "abc-parity-performance-v1",
        "started_at": started_at,
        "completed_at": completed_at,
        "total_duration_seconds": total_duration_seconds,
        "stage_timings": stage_timings,
        "totals": {
            "stage_duration_seconds": round(
                sum(item.get("duration_seconds", 0.0) for item in stage_timings),
                6,
            ),
            "analyst_input_bytes": sum(
                item.get("bytes", 0) for item in analyst_inputs if isinstance(item, dict)
            ),
            "analyst_input_estimated_tokens": sum(
                item.get("estimated_tokens", 0)
                for item in analyst_inputs
                if isinstance(item, dict)
            ),
            "analyst_call_count": len(analyst_inputs),
        },
    }


def measure_source_artifacts(run_id: str, ticker: str, *, mode: str) -> dict[str, Any]:
    root = ticker_root(run_id, ticker)
    artifacts = {
        "research_plan": measure_text_artifact(root / "research-plan.json"),
        "financial_datasets_raw": measure_text_artifact(root / "financial-datasets-raw.json"),
        "dart_raw": measure_text_artifact(root / "dart-api-raw.json"),
        "yfinance_raw": measure_text_artifact(root / "yfinance-raw.json"),
    }
    if mode == "C":
        artifacts["peer_fetch_summary"] = measure_text_artifact(root / "peer-fetch-summary.json")
    return compact_measurements(artifacts)


def measure_text_artifact(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    return {
        "path": display_path(path),
        "bytes": path.stat().st_size,
        "chars": len(text),
        "estimated_tokens": estimate_text_tokens(text),
        "token_estimator": "chars_div_4_ceil",
    }


def estimate_text_tokens(text: str) -> int:
    return (len(text) + 3) // 4


def compact_measurements(measurements: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in measurements.items()
        if value is not None
    }


def load_backend_usage(analysis_result_path: Path) -> dict[str, Any] | None:
    analysis = load_json(analysis_result_path)
    run_context = analysis.get("run_context") if isinstance(analysis.get("run_context"), dict) else {}
    backend = run_context.get("backend") if isinstance(run_context.get("backend"), dict) else {}
    usage = backend.get("usage")
    return usage if isinstance(usage, dict) else None


def update_json_file(path: Path, updates: dict[str, Any]) -> None:
    payload = load_json(path)
    if not payload:
        return
    payload.update(updates)
    write_json(path, payload)


def write_source_collection_summary(run_id: str, ticker: str, summary: dict[str, Any]) -> None:
    path = ticker_root(run_id, ticker) / "source-collection-summary.json"
    write_json(path, summary)


def display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return str(path.resolve())


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ParityRunnerError as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        raise SystemExit(2)
