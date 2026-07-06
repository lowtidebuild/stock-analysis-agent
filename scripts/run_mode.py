#!/usr/bin/env python3
"""Unified Codex-native entrypoint for stock analysis modes."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.parity.comparison import build_mode_b_comparison_handoff  # noqa: E402
from scripts.parity.data_sources import load_json, utc_now, write_json  # noqa: E402
from scripts.run_abc_parity import (  # noqa: E402
    analyst_result_payload,
    build_paths,
    build_run_performance,
    calculation_result_payload,
    collect_macro,
    comparison_result_payload,
    critic_result_payload,
    display_path,
    elapsed_seconds,
    normalize_market,
    normalize_ticker,
    normalize_tickers,
    parse_env_json,
    ParityRunnerError,
    record_stage,
    render_result_payload,
    result_payload,
    reuse_macro,
    validation_result_payload,
)
from scripts.run_mode_c_impl import ModeCEntryError, run_mode_c  # noqa: E402
from scripts.run_mode_common import (  # noqa: E402
    RunModeExecutionError,
    publish_report_via_contract,
    request_schema_version,
    require_delivery_gate_ready,
    run_ticker_pipeline,
    timed_stage,
)
from tools.paths import data_path  # noqa: E402


class RunModeInputError(RuntimeError):
    pass


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        payload = run_mode(args)
    except RunModeInputError as exc:
        print(
            json.dumps(
                {
                    "error": str(exc),
                    "mode": args.mode.upper(),
                    "run_id": args.run_id,
                },
                ensure_ascii=False,
            )
        )
        return 2
    except (ModeCEntryError, RunModeExecutionError, ParityRunnerError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "error": str(exc),
                    "mode": args.mode.upper(),
                    "run_id": args.run_id,
                },
                ensure_ascii=False,
            )
        )
        return 1
    except Exception as exc:  # Contract guard: stdout should remain one-line JSON for automation.
        print(
            json.dumps(
                {
                    "error": f"unexpected: {type(exc).__name__}: {exc}",
                    "mode": args.mode.upper(),
                    "run_id": args.run_id,
                },
                ensure_ascii=False,
            )
        )
        return 1

    print(json.dumps(payload, ensure_ascii=False))
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a Codex-native stock analysis mode.")
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--tickers", default="")
    parser.add_argument("--mode", required=True, choices=["A", "B", "C", "a", "b", "c"])
    parser.add_argument("--lang", required=True, choices=["ko", "en"])
    parser.add_argument("--market", required=True, choices=["US", "KR", "mixed", "auto"])
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--skip-network", action="store_true")
    parser.add_argument("--reuse-collected", action="store_true")
    parser.add_argument("--peer-tickers", default="")
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument(
        "--run-profile",
        choices=["production", "smoke", "fixture"],
        default=None,
        help="Delivery profile. Defaults to smoke for fixture backends and production otherwise.",
    )
    parser.add_argument(
        "--allow-fixture-delivery",
        action="store_true",
        help="Allow fixture/smoke runs to pass delivery for deterministic tests.",
    )
    parser.add_argument(
        "--allow-deterministic-delivery",
        action="store_true",
        help="Allow deterministic template runs to pass delivery with a visible disclosure flag.",
    )
    parser.add_argument(
        "--web-provider",
        choices=["tavily", "brave", "none"],
        default=None,
        help="Override WEB_SEARCH_PROVIDER for tier2 qualitative search.",
    )
    parser.add_argument(
        "--analyst-backend",
        default=None,
        help="Override ANALYST_BACKEND for this run, for example codex_native, fixture, or the configured live backend.",
    )
    return parser.parse_args(argv)


def run_mode(args: argparse.Namespace) -> dict[str, Any]:
    mode = args.mode.upper()
    ticker = normalize_ticker(args.ticker)
    args.ticker = ticker
    tickers = normalize_tickers(args.tickers) if args.tickers else []

    if mode == "B":
        tickers = validate_mode_b_tickers(ticker, tickers)

    if mode == "A":
        payload = run_mode_a(args)
        return enrich_payload(payload, mode=mode, run_id=args.run_id, ticker=ticker)

    if mode == "C":
        payload = run_mode_c(args)
        return enrich_payload(payload, mode=mode, run_id=args.run_id, ticker=ticker)

    payload = run_mode_b(args, tickers)
    return payload


def run_mode_a(args: argparse.Namespace) -> dict[str, Any]:
    started_at = utc_now()
    run_start = time.perf_counter()
    stage_timings: list[dict[str, Any]] = []

    ticker = normalize_ticker(args.ticker)
    mode = "A"
    language = args.lang.lower()
    market = normalize_market(args.market, ticker, [ticker])
    run_id = args.run_id.strip()
    if not run_id:
        raise RunModeInputError("--run-id is required")

    request_payload = parse_env_json("STOCK_ANALYSIS_REQUEST_PAYLOAD")
    paths = build_paths(run_id)
    paths["run_root"].mkdir(parents=True, exist_ok=True)
    (REPO_ROOT / "output" / "reports").mkdir(parents=True, exist_ok=True)

    write_json(
        paths["request"],
        {
            "schema_version": request_schema_version(mode),
            "ticker": ticker,
            "tickers": [ticker],
            "mode": mode,
            "language": language,
            "market": market,
            "run_id": run_id,
            "skip_network": args.skip_network,
            "reuse_collected": args.reuse_collected,
            "run_profile": args.run_profile,
            "allow_fixture_delivery": args.allow_fixture_delivery,
            "analyst_backend": args.analyst_backend,
            "request_payload": request_payload,
            "created_at": utc_now(),
        },
    )

    stage_start = time.perf_counter()
    macro_result = (
        reuse_macro(paths=paths)
        if args.reuse_collected
        else collect_macro(paths=paths, market=market, skip_network=args.skip_network)
    )
    macro_payload = result_payload(macro_result)
    macro_payload["duration_seconds"] = record_stage(
        stage_timings,
        "macro_collect",
        stage_start,
        market=market,
        reused=args.reuse_collected,
        skipped=args.skip_network,
    )

    pipeline = run_ticker_pipeline(
        ticker,
        mode,
        args,
        error_cls=RunModeExecutionError,
        market=market,
        stage_timings=stage_timings,
    )
    if pipeline.render is None:
        raise RunModeExecutionError("Mode A render stage did not produce an HTML artifact")

    analysis = load_json(pipeline.analyst.analysis_result_path)
    analysis_date = str(analysis.get("analysis_date") or utc_now()[:10])
    report_path = publish_report_via_contract(
        analysis_date=analysis_date,
        html_path=pipeline.render.html_path,
        language=language,
        mode=mode,
        peer_tickers=None,
        ticker=ticker,
    )
    quality_path = pipeline.quality_report_path
    delivery_gate = pipeline.delivery_gate

    completed_at = utc_now()
    metadata = {
        "schema_version": "run-mode-entry-run-metadata-v1",
        "run_id": run_id,
        "mode": mode,
        "language": language,
        "market": market,
        "ticker": ticker,
        "macro": macro_payload,
        "ticker_result": pipeline.ticker_summary,
        "validation": validation_result_payload(pipeline.validation),
        "calculation": calculation_result_payload(pipeline.calculation),
        "analyst": analyst_result_payload(pipeline.analyst),
        "run_profile": pipeline.run_profile,
        "render": render_result_payload(pipeline.render),
        "critic": critic_result_payload(pipeline.critic),
        "published_report_path": display_path(report_path),
        "quality_report_path": display_path(quality_path),
        "delivery_gate": delivery_gate,
        "performance": build_run_performance(
            analyst_results=[analyst_result_payload(pipeline.analyst)],
            completed_at=completed_at,
            stage_timings=stage_timings,
            started_at=started_at,
            total_duration_seconds=elapsed_seconds(run_start),
        ),
        "created_at": completed_at,
    }
    write_json(paths["run_metadata"], metadata)
    return {
        "report_path": str(report_path),
        "run_id": run_id,
        "quality_report_path": str(quality_path),
        "delivery_gate": delivery_gate.get("result"),
        "run_profile": pipeline.run_profile.get("run_profile"),
    }


def run_mode_b(args: argparse.Namespace, tickers: list[str]) -> dict[str, Any]:
    started_at = utc_now()
    run_start = time.perf_counter()
    stage_timings: list[dict[str, Any]] = []

    primary_ticker = tickers[0]
    mode = "B"
    language = args.lang.lower()
    market = normalize_market(args.market, primary_ticker, tickers)
    run_id = args.run_id.strip()
    if not run_id:
        raise RunModeInputError("--run-id is required")

    request_payload = parse_env_json("STOCK_ANALYSIS_REQUEST_PAYLOAD")
    paths = build_paths(run_id)
    paths["run_root"].mkdir(parents=True, exist_ok=True)
    (REPO_ROOT / "output" / "reports").mkdir(parents=True, exist_ok=True)

    write_json(
        paths["request"],
        {
            "schema_version": request_schema_version(mode),
            "ticker": primary_ticker,
            "tickers": tickers,
            "mode": mode,
            "language": language,
            "market": market,
            "run_id": run_id,
            "skip_network": args.skip_network,
            "reuse_collected": args.reuse_collected,
            "run_profile": args.run_profile,
            "allow_fixture_delivery": args.allow_fixture_delivery,
            "analyst_backend": args.analyst_backend,
            "request_payload": request_payload,
            "created_at": utc_now(),
        },
    )

    stage_start = time.perf_counter()
    macro_result = (
        reuse_macro(paths=paths)
        if args.reuse_collected
        else collect_macro(paths=paths, market=market, skip_network=args.skip_network)
    )
    macro_payload = result_payload(macro_result)
    macro_payload["duration_seconds"] = record_stage(
        stage_timings,
        "macro_collect",
        stage_start,
        market=market,
        reused=args.reuse_collected,
        skipped=args.skip_network,
    )

    ticker_results: list[dict[str, Any]] = []
    validation_results: list[Any] = []
    calculation_results: list[Any] = []
    analyst_results: list[Any] = []
    critic_results: list[Any] = []
    run_profiles: list[dict[str, Any]] = []

    for ticker in tickers:
        ticker_market = normalize_market(args.market, ticker, [ticker])
        pipeline = run_ticker_pipeline(
            ticker,
            mode,
            args,
            error_cls=RunModeExecutionError,
            include_render=False,
            market=ticker_market,
            stage_ticker_details=True,
            stage_timings=stage_timings,
        )
        ticker_results.append(pipeline.ticker_summary)
        validation_results.append(pipeline.validation)
        calculation_results.append(pipeline.calculation)
        analyst_results.append(pipeline.analyst)
        critic_results.append(pipeline.critic)
        run_profiles.append(pipeline.run_profile)

    try:
        comparison = timed_stage(
            stage_timings,
            "comparison",
            lambda: build_mode_b_comparison_handoff(
                language=language,
                market=market,
                run_id=run_id,
                tickers=tickers,
            ),
        )
    except ValueError as exc:
        raise RunModeExecutionError(str(exc)) from exc

    quality_path = comparison.quality_report_path
    delivery_gate = require_delivery_gate_ready(
        delivery_ready=comparison.delivery_ready,
        error_cls=RunModeExecutionError,
        not_ready_message="Mode B comparison quality gate is not ready for delivery",
        gate_message="comparison-quality-report delivery_gate.ready_for_delivery is not true",
        quality_report_path=quality_path,
    )

    primary_analysis = load_json(data_path("runs", run_id, primary_ticker, "analysis-result.json"))
    analysis_date = str(primary_analysis.get("analysis_date") or utc_now()[:10])
    report_path = publish_report_via_contract(
        analysis_date=analysis_date,
        html_path=comparison.html_path,
        language=language,
        mode=mode,
        peer_tickers=tickers,
        ticker=primary_ticker,
    )
    completed_at = utc_now()
    analyst_payloads = [analyst_result_payload(result) for result in analyst_results]
    validation_payloads = [validation_result_payload(result) for result in validation_results]
    calculation_payloads = [calculation_result_payload(result) for result in calculation_results]
    critic_payloads = [critic_result_payload(result) for result in critic_results]
    provider = common_value([item.get("provider") for item in analyst_payloads])
    profile = common_value([item.get("run_profile") for item in run_profiles])

    metadata = {
        "schema_version": "run-mode-entry-run-metadata-v1",
        "run_id": run_id,
        "mode": mode,
        "language": language,
        "market": market,
        "ticker": primary_ticker,
        "tickers": tickers,
        "macro": macro_payload,
        "ticker_results": ticker_results,
        "validation_results": validation_payloads,
        "calculation_results": calculation_payloads,
        "analyst_results": analyst_payloads,
        "run_profiles": run_profiles,
        "critic_results": critic_payloads,
        "comparison": comparison_result_payload(comparison),
        "published_report_path": display_path(report_path),
        "quality_report_path": display_path(quality_path),
        "delivery_gate": delivery_gate,
        "performance": build_run_performance(
            analyst_results=analyst_payloads,
            completed_at=completed_at,
            stage_timings=stage_timings,
            started_at=started_at,
            total_duration_seconds=elapsed_seconds(run_start),
        ),
        "created_at": completed_at,
    }
    write_json(paths["run_metadata"], metadata)

    return {
        "schema_version": "run-mode-entry-result-v1",
        "mode": mode,
        "ticker": primary_ticker,
        "tickers": tickers,
        "backend_provider": provider,
        "report_path": str(report_path),
        "comparison_report_path": str(report_path),
        "run_id": run_id,
        "quality_report_path": str(quality_path),
        "delivery_gate": delivery_gate.get("result"),
        "run_profile": profile,
        "best_pick": comparison.best_pick,
        "ticker_quality_report_paths": {
            result.ticker: str(result.quality_report_path) for result in critic_results
        },
    }


def validate_mode_b_tickers(primary_ticker: str, tickers: list[str]) -> list[str]:
    if not tickers:
        raise RunModeInputError("Mode B requires --tickers with at least two comma-separated tickers.")
    comparison_tickers = [primary_ticker, *[ticker for ticker in tickers if ticker != primary_ticker]]
    if len(comparison_tickers) < 2:
        raise RunModeInputError("Mode B requires at least two distinct tickers.")
    if len(comparison_tickers) > 5:
        raise RunModeInputError("Mode B supports at most five distinct tickers in this native CLI contract.")
    return comparison_tickers


def common_value(values: list[Any]) -> Any:
    normalized = [value for value in values if value not in (None, "")]
    if not normalized:
        return None
    first = normalized[0]
    return first if all(value == first for value in normalized) else "mixed"


def enrich_payload(
    payload: dict[str, Any],
    *,
    mode: str,
    run_id: str,
    ticker: str,
) -> dict[str, Any]:
    analysis = load_json(data_path("runs", run_id, ticker, "analysis-result.json"))
    run_context = analysis.get("run_context") if isinstance(analysis.get("run_context"), dict) else {}
    backend = run_context.get("backend") if isinstance(run_context.get("backend"), dict) else {}
    return {
        "schema_version": "run-mode-entry-result-v1",
        "mode": mode,
        "ticker": ticker,
        "backend_provider": backend.get("provider"),
        **payload,
    }

if __name__ == "__main__":
    raise SystemExit(main())
