#!/usr/bin/env python3
"""Unified Codex-native entrypoint for stock analysis modes."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.parity.analyst import build_analyst_handoff  # noqa: E402
from scripts.parity.calculations import build_calculation_handoff  # noqa: E402
from scripts.parity.comparison import build_mode_b_comparison_handoff  # noqa: E402
from scripts.parity.critic import build_critic_handoff  # noqa: E402
from scripts.parity.data_sources import load_json, utc_now, write_json  # noqa: E402
from scripts.parity.rendering import build_render_handoff  # noqa: E402
from scripts.parity.validation import build_validation_handoff  # noqa: E402
from scripts.run_abc_parity import (  # noqa: E402
    analyst_result_payload,
    build_paths,
    build_run_performance,
    calculation_result_payload,
    collect_macro,
    collect_ticker_sources,
    comparison_result_payload,
    critic_result_payload,
    display_path,
    elapsed_seconds,
    normalize_market,
    normalize_ticker,
    normalize_tickers,
    parse_env_json,
    record_stage,
    render_result_payload,
    result_payload,
    reuse_macro,
    reuse_ticker_sources,
    validation_result_payload,
    write_source_collection_summary,
)
from scripts.run_mode_c_impl import ModeCEntryError, run_mode_c  # noqa: E402
from scripts.run_mode_common import (  # noqa: E402
    annotate_analysis_run_profile,
    temporary_env,
    timed_stage,
)


class RunModeInputError(RuntimeError):
    pass


class RunModeExecutionError(RuntimeError):
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
    except (ModeCEntryError, RunModeExecutionError) as exc:
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
            "schema_version": "run-mode-entry-request-v1",
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

    stage_start = time.perf_counter()
    if args.reuse_collected:
        ticker_summary = reuse_ticker_sources(
            market=market,
            run_id=run_id,
            ticker=ticker,
        )
    else:
        ticker_summary = collect_ticker_sources(
            language=language,
            market=market,
            mode=mode,
            peer_tickers=[],
            run_id=run_id,
            skip_network=args.skip_network,
            ticker=ticker,
            timeout=args.timeout,
        )
    ticker_summary["duration_seconds"] = record_stage(
        stage_timings,
        "ticker_collect",
        stage_start,
        market=market,
        reused=args.reuse_collected,
        skipped=args.skip_network,
        ticker=ticker,
    )
    write_source_collection_summary(run_id, ticker, ticker_summary)

    validation = timed_stage(
        stage_timings,
        "validation",
        lambda: build_validation_handoff(
            language=language,
            market=market,
            mode=mode,
            run_id=run_id,
            ticker=ticker,
        ),
    )
    calculation = timed_stage(
        stage_timings,
        "calculation",
        lambda: build_calculation_handoff(
            language=language,
            market=market,
            mode=mode,
            run_id=run_id,
            ticker=ticker,
        ),
    )
    with temporary_env("ANALYST_BACKEND", args.analyst_backend):
        analyst = timed_stage(
            stage_timings,
            "analyst",
            lambda: build_analyst_handoff(
                language=language,
                market=market,
                mode=mode,
                run_id=run_id,
                ticker=ticker,
            ),
        )
    run_profile = annotate_analysis_run_profile(
        analyst.analysis_result_path,
        allow_fixture_delivery=args.allow_fixture_delivery,
        requested_run_profile=args.run_profile,
    )
    render = timed_stage(
        stage_timings,
        "render",
        lambda: build_render_handoff(
            language=language,
            market=market,
            mode=mode,
            run_id=run_id,
            ticker=ticker,
        ),
    )
    critic = timed_stage(
        stage_timings,
        "critic",
        lambda: build_critic_handoff(
            language=language,
            market=market,
            mode=mode,
            run_id=run_id,
            ticker=ticker,
        ),
    )
    if not critic.delivery_ready:
        raise RunModeExecutionError("Mode A quality gate is not ready for delivery")

    report_path = publish_mode_report(
        html_path=render.html_path,
        language=language,
        mode=mode,
        ticker=ticker,
    )
    quality_path = critic.quality_report_path
    quality = load_json(quality_path)
    delivery_gate = quality.get("delivery_gate") if isinstance(quality.get("delivery_gate"), dict) else {}
    if delivery_gate.get("ready_for_delivery") is not True:
        raise RunModeExecutionError("quality-report delivery_gate.ready_for_delivery is not true")

    completed_at = utc_now()
    metadata = {
        "schema_version": "run-mode-entry-run-metadata-v1",
        "run_id": run_id,
        "mode": mode,
        "language": language,
        "market": market,
        "ticker": ticker,
        "macro": macro_payload,
        "ticker_result": ticker_summary,
        "validation": validation_result_payload(validation),
        "calculation": calculation_result_payload(calculation),
        "analyst": analyst_result_payload(analyst),
        "run_profile": run_profile,
        "render": render_result_payload(render),
        "critic": critic_result_payload(critic),
        "published_report_path": display_path(report_path),
        "quality_report_path": display_path(quality_path),
        "delivery_gate": delivery_gate,
        "performance": build_run_performance(
            analyst_results=[analyst_result_payload(analyst)],
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
        "run_profile": run_profile.get("run_profile"),
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
            "schema_version": "run-mode-entry-request-v1",
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
        stage_start = time.perf_counter()
        if args.reuse_collected:
            ticker_summary = reuse_ticker_sources(
                market=ticker_market,
                run_id=run_id,
                ticker=ticker,
            )
        else:
            ticker_summary = collect_ticker_sources(
                language=language,
                market=ticker_market,
                mode=mode,
                peer_tickers=[],
                run_id=run_id,
                skip_network=args.skip_network,
                ticker=ticker,
                timeout=args.timeout,
            )
        ticker_summary["duration_seconds"] = record_stage(
            stage_timings,
            "ticker_collect",
            stage_start,
            market=ticker_market,
            reused=args.reuse_collected,
            skipped=args.skip_network,
            ticker=ticker,
        )
        write_source_collection_summary(run_id, ticker, ticker_summary)
        ticker_results.append(ticker_summary)

        validation = timed_stage(
            stage_timings,
            "validation",
            lambda ticker=ticker, ticker_market=ticker_market: build_validation_handoff(
                language=language,
                market=ticker_market,
                mode=mode,
                run_id=run_id,
                ticker=ticker,
            ),
            ticker=ticker,
        )
        validation_results.append(validation)

        calculation = timed_stage(
            stage_timings,
            "calculation",
            lambda ticker=ticker, ticker_market=ticker_market: build_calculation_handoff(
                language=language,
                market=ticker_market,
                mode=mode,
                run_id=run_id,
                ticker=ticker,
            ),
            ticker=ticker,
        )
        calculation_results.append(calculation)

        with temporary_env("ANALYST_BACKEND", args.analyst_backend):
            analyst = timed_stage(
                stage_timings,
                "analyst",
                lambda ticker=ticker, ticker_market=ticker_market: build_analyst_handoff(
                    language=language,
                    market=ticker_market,
                    mode=mode,
                    run_id=run_id,
                    ticker=ticker,
                ),
                ticker=ticker,
            )
        analyst_results.append(analyst)

        run_profile = annotate_analysis_run_profile(
            analyst.analysis_result_path,
            allow_fixture_delivery=args.allow_fixture_delivery,
            requested_run_profile=args.run_profile,
        )
        run_profiles.append(run_profile)

        critic = timed_stage(
            stage_timings,
            "critic",
            lambda ticker=ticker, ticker_market=ticker_market: build_critic_handoff(
                language=language,
                market=ticker_market,
                mode=mode,
                run_id=run_id,
                ticker=ticker,
            ),
            ticker=ticker,
        )
        critic_results.append(critic)
        if not critic.delivery_ready:
            raise RunModeExecutionError(f"Mode B ticker quality gate is not ready for delivery: {ticker}")

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

    if not comparison.delivery_ready:
        raise RunModeExecutionError("Mode B comparison quality gate is not ready for delivery")

    quality_path = comparison.quality_report_path
    quality = load_json(quality_path)
    delivery_gate = quality.get("delivery_gate") if isinstance(quality.get("delivery_gate"), dict) else {}
    if delivery_gate.get("ready_for_delivery") is not True:
        raise RunModeExecutionError("comparison-quality-report delivery_gate.ready_for_delivery is not true")

    report_path = publish_mode_b_report(
        html_path=comparison.html_path,
        language=language,
        primary_ticker=primary_ticker,
        run_id=run_id,
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
    analysis = load_json(REPO_ROOT / "output" / "runs" / run_id / ticker / "analysis-result.json")
    run_context = analysis.get("run_context") if isinstance(analysis.get("run_context"), dict) else {}
    backend = run_context.get("backend") if isinstance(run_context.get("backend"), dict) else {}
    return {
        "schema_version": "run-mode-entry-result-v1",
        "mode": mode,
        "ticker": ticker,
        "backend_provider": backend.get("provider"),
        **payload,
    }


def publish_mode_report(
    *,
    html_path: Path,
    language: str,
    mode: str,
    ticker: str,
) -> Path:
    analysis = load_json(html_path.parent / "analysis-result.json")
    analysis_date = str(analysis.get("analysis_date") or utc_now()[:10])
    reports_dir = REPO_ROOT / "output" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / f"{ticker}_{mode}_{language}_{analysis_date}.html"
    shutil.copyfile(html_path, report_path)
    return report_path


def publish_mode_b_report(
    *,
    html_path: Path,
    language: str,
    primary_ticker: str,
    run_id: str,
) -> Path:
    analysis = load_json(REPO_ROOT / "output" / "runs" / run_id / primary_ticker / "analysis-result.json")
    analysis_date = str(analysis.get("analysis_date") or utc_now()[:10])
    reports_dir = REPO_ROOT / "output" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / f"{primary_ticker}_B_{language}_{analysis_date}.html"
    shutil.copyfile(html_path, report_path)
    return report_path


if __name__ == "__main__":
    raise SystemExit(main())
