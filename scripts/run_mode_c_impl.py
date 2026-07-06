"""Mode C native implementation shared by unified and compatibility CLIs."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.parity.analyst import build_analyst_handoff  # noqa: E402
from scripts.parity.calculations import build_calculation_handoff  # noqa: E402
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
    critic_result_payload,
    display_path,
    elapsed_seconds,
    measure_text_artifact,
    normalize_market,
    normalize_ticker,
    parse_env_json,
    record_stage,
    render_result_payload,
    resolve_peer_tickers,
    result_payload,
    reuse_macro,
    reuse_ticker_sources,
    validation_result_payload,
    write_source_collection_summary,
)
from scripts.run_mode_common import (  # noqa: E402
    annotate_analysis_run_profile,
    publish_report_via_contract,
    temporary_env,
    timed_stage,
)
from tools.artifact_validation import validate_artifact_data  # noqa: E402
from tools.web_search import search as web_search  # noqa: E402


class ModeCEntryError(RuntimeError):
    pass


def run_mode_c(args: argparse.Namespace) -> dict[str, Any]:
    started_at = utc_now()
    run_start = time.perf_counter()
    stage_timings: list[dict[str, Any]] = []

    ticker = normalize_ticker(args.ticker)
    mode = "C"
    language = args.lang.lower()
    market = normalize_market(args.market, ticker, [ticker])
    run_id = args.run_id.strip()
    if not run_id:
        raise ModeCEntryError("--run-id is required")

    request_payload = parse_env_json("STOCK_ANALYSIS_REQUEST_PAYLOAD")
    peer_tickers = resolve_peer_tickers(
        cli_value=args.peer_tickers,
        env_payload=request_payload,
        market=market,
        mode=mode,
        ticker=ticker,
    )
    paths = build_paths(run_id)
    paths["run_root"].mkdir(parents=True, exist_ok=True)
    reports_dir = REPO_ROOT / "output" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    write_json(
        paths["request"],
        {
            "schema_version": "mode-c-entry-request-v1",
            "ticker": ticker,
            "mode": mode,
            "language": language,
            "market": market,
            "run_id": run_id,
            "skip_network": args.skip_network,
            "reuse_collected": args.reuse_collected,
            "peer_tickers": peer_tickers,
            "run_profile": args.run_profile,
            "allow_deterministic_delivery": args.allow_deterministic_delivery,
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
            peer_tickers=peer_tickers,
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

    stage_start = time.perf_counter()
    tier2_path = ensure_tier2_artifact(
        market=market,
        provider=args.web_provider,
        run_id=run_id,
        skip_network=args.skip_network,
        ticker=ticker,
    )
    tier2_duration = record_stage(
        stage_timings,
        "tier2_web",
        stage_start,
        market=market,
        path=display_path(tier2_path),
        skipped=args.skip_network,
        ticker=ticker,
    )
    tier2_payload = {
        "path": display_path(tier2_path),
        "duration_seconds": tier2_duration,
        "artifact": measure_text_artifact(tier2_path),
    }

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
        allow_deterministic_delivery=args.allow_deterministic_delivery,
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
        raise ModeCEntryError("Mode C quality gate is not ready for delivery")

    analysis = load_json(analyst.analysis_result_path)
    analysis_date = str(analysis.get("analysis_date") or utc_now()[:10])
    report_path = publish_report_via_contract(
        analysis_date=analysis_date,
        html_path=render.html_path,
        language=language,
        mode=mode,
        peer_tickers=None,
        ticker=ticker,
    )
    quality_path = critic.quality_report_path
    quality = load_json(quality_path)
    delivery_gate = quality.get("delivery_gate") if isinstance(quality.get("delivery_gate"), dict) else {}
    if delivery_gate.get("ready_for_delivery") is not True:
        raise ModeCEntryError("quality-report delivery_gate.ready_for_delivery is not true")

    completed_at = utc_now()
    metadata = {
        "schema_version": "mode-c-entry-run-metadata-v1",
        "run_id": run_id,
        "mode": mode,
        "language": language,
        "market": market,
        "ticker": ticker,
        "macro": macro_payload,
        "ticker_result": ticker_summary,
        "tier2": tier2_payload,
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


def ensure_tier2_artifact(
    *,
    market: str,
    provider: str | None,
    run_id: str,
    skip_network: bool,
    ticker: str,
) -> Path:
    ticker_dir = REPO_ROOT / "output" / "runs" / run_id / ticker
    tier2_path = ticker_dir / "tier2-raw.json"
    if tier2_path.exists():
        payload = load_json(tier2_path)
    else:
        queries = default_web_queries(ticker, market)
        payload = web_search(
            queries,
            ticker=ticker,
            market="KR" if market == "KR" else "US",
            provider="none" if skip_network else provider,
            now=utc_now(),
        )
        write_json(tier2_path, payload)
        update_research_plan_with_tier2(ticker_dir, queries, tier2_path)

    errors = validate_artifact_data("tier2-raw", payload)
    if errors:
        raise ModeCEntryError("tier2-raw failed contract checks: " + "; ".join(errors[:5]))
    return tier2_path


def default_web_queries(ticker: str, market: str) -> list[str]:
    if market == "KR":
        return [
            f"{ticker} analyst target consensus news",
            f"{ticker} earnings guidance catalysts",
        ]
    return [
        f"{ticker} analyst price target consensus news",
        f"{ticker} earnings guidance catalysts",
    ]


def update_research_plan_with_tier2(
    ticker_dir: Path,
    queries: list[str],
    tier2_path: Path,
) -> None:
    research_path = ticker_dir / "research-plan.json"
    research = load_json(research_path)
    if not research:
        return
    research["tier2_searches"] = queries
    research["tier2_fetches"] = research.get("tier2_fetches") or []
    research["tier2_raw_path"] = display_path(tier2_path)
    write_json(research_path, research)

