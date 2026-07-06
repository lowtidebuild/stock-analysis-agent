"""Shared helpers for native run-mode entrypoints."""

from __future__ import annotations

from dataclasses import dataclass
import os
import shutil
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterable

from scripts.parity.analyst import build_analyst_handoff
from scripts.parity.calculations import build_calculation_handoff
from scripts.parity.critic import build_critic_handoff
from scripts.parity.data_sources import load_json, write_json
from scripts.parity.rendering import build_render_handoff
from scripts.parity.validation import build_validation_handoff
from scripts.run_abc_parity import (
    collect_ticker_sources,
    normalize_market,
    record_stage,
    reuse_ticker_sources,
    write_source_collection_summary,
)
from tools.analysis_contract import build_default_report_path
from tools.backend_providers import DETERMINISTIC_BACKEND_PROVIDERS, FIXTURE_BACKEND_PROVIDERS

REPO_ROOT = Path(__file__).resolve().parents[1]
REQUEST_SCHEMA_VERSIONS = {
    "A": "run-mode-entry-request-v1",
    "B": "run-mode-entry-request-v1",
    "C": "mode-c-entry-request-v1",
}


class RunModeExecutionError(RuntimeError):
    pass


@dataclass(frozen=True)
class TickerPipelineContext:
    args: Any
    language: str
    market: str
    mode: str
    run_id: str
    stage_timings: list[dict[str, Any]]
    ticker: str


@dataclass(frozen=True)
class TickerPipelineResult:
    ticker: str
    market: str
    ticker_summary: dict[str, Any]
    extra_stage_payloads: dict[str, Any]
    validation: Any
    calculation: Any
    analyst: Any
    run_profile: dict[str, Any]
    render: Any | None
    critic: Any
    quality_report_path: Path
    delivery_gate: dict[str, Any]


ExtraStage = Callable[[TickerPipelineContext], tuple[str, Any]]


def request_schema_version(mode: str) -> str:
    return REQUEST_SCHEMA_VERSIONS.get(mode.upper(), "run-mode-entry-request-v1")


def timed_stage(
    stage_timings: list[dict[str, Any]],
    stage: str,
    callback: Any,
    **details: Any,
) -> Any:
    started = time.perf_counter()
    result = callback()
    record_stage(stage_timings, stage, started, **details)
    return result


@contextmanager
def temporary_env(name: str, value: str | None) -> Any:
    if value is None:
        yield
        return
    old_value = os.environ.get(name)
    os.environ[name] = value
    try:
        yield
    finally:
        if old_value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = old_value


def annotate_analysis_run_profile(
    analysis_path: Path,
    *,
    allow_deterministic_delivery: bool,
    allow_fixture_delivery: bool,
    requested_run_profile: str | None,
) -> dict[str, Any]:
    analysis = load_json(analysis_path)
    run_context = analysis.get("run_context") if isinstance(analysis.get("run_context"), dict) else {}
    backend = run_context.get("backend") if isinstance(run_context.get("backend"), dict) else {}
    provider = str(backend.get("provider") or "").strip().lower()
    fixture_backend = provider in FIXTURE_BACKEND_PROVIDERS
    deterministic_backend = provider in DETERMINISTIC_BACKEND_PROVIDERS
    if deterministic_backend:
        run_profile = "deterministic"
    else:
        run_profile = requested_run_profile or ("smoke" if fixture_backend else "production")
    analysis["run_context"] = {
        **run_context,
        "run_profile": run_profile,
        "allow_deterministic_delivery": bool(allow_deterministic_delivery),
        "allow_fixture_delivery": bool(allow_fixture_delivery),
        "deterministic_backend": deterministic_backend,
        "fixture_backend": fixture_backend,
    }
    if deterministic_backend:
        analysis["run_context"]["verdict_provenance"] = "deterministic_rule"
    write_json(analysis_path, analysis)
    return {
        "run_profile": run_profile,
        "allow_deterministic_delivery": bool(allow_deterministic_delivery),
        "allow_fixture_delivery": bool(allow_fixture_delivery),
        "deterministic_backend": deterministic_backend,
        "fixture_backend": fixture_backend,
        "backend_provider": provider or None,
    }


def publish_report_via_contract(
    *,
    analysis_date: str,
    html_path: Path,
    language: str,
    mode: str,
    peer_tickers: list[str] | None,
    ticker: str,
) -> Path:
    contract_path = build_default_report_path(
        ticker=ticker,
        output_mode=mode,
        peer_tickers=peer_tickers,
        output_language=language,
        analysis_date=analysis_date,
    )
    if contract_path is None:
        raise RunModeExecutionError(f"cannot build contract report path for {ticker}/{mode}")
    report_path = Path(contract_path)
    if not report_path.is_absolute():
        report_path = REPO_ROOT / report_path
    report_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(html_path, report_path)
    return report_path


def require_delivery_gate_ready(
    *,
    delivery_ready: bool,
    error_cls: type[Exception],
    gate_message: str,
    not_ready_message: str,
    quality_report_path: Path,
) -> dict[str, Any]:
    if not delivery_ready:
        raise error_cls(not_ready_message)
    quality = load_json(quality_report_path)
    delivery_gate = quality.get("delivery_gate") if isinstance(quality.get("delivery_gate"), dict) else {}
    if delivery_gate.get("ready_for_delivery") is not True:
        raise error_cls(gate_message)
    return delivery_gate


def run_ticker_pipeline(
    ticker: str,
    mode: str,
    args: Any,
    *,
    error_cls: type[Exception] = RunModeExecutionError,
    extra_stages: Iterable[ExtraStage] = (),
    include_render: bool = True,
    market: str | None = None,
    peer_tickers: list[str] | None = None,
    stage_timings: list[dict[str, Any]] | None = None,
    stage_ticker_details: bool = False,
) -> TickerPipelineResult:
    mode = mode.upper()
    language = args.lang.lower()
    run_id = args.run_id.strip()
    ticker_market = market or normalize_market(args.market, ticker, [ticker])
    timings = stage_timings if stage_timings is not None else []
    details = {"ticker": ticker} if stage_ticker_details else {}

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
            peer_tickers=peer_tickers or [],
            run_id=run_id,
            skip_network=args.skip_network,
            ticker=ticker,
            timeout=args.timeout,
        )
    ticker_summary["duration_seconds"] = record_stage(
        timings,
        "ticker_collect",
        stage_start,
        market=ticker_market,
        reused=args.reuse_collected,
        skipped=args.skip_network,
        ticker=ticker,
    )
    write_source_collection_summary(run_id, ticker, ticker_summary)

    context = TickerPipelineContext(
        args=args,
        language=language,
        market=ticker_market,
        mode=mode,
        run_id=run_id,
        stage_timings=timings,
        ticker=ticker,
    )
    extra_stage_payloads: dict[str, Any] = {}
    for extra_stage in extra_stages:
        key, payload = extra_stage(context)
        extra_stage_payloads[key] = payload

    validation = timed_stage(
        timings,
        "validation",
        lambda: build_validation_handoff(
            language=language,
            market=ticker_market,
            mode=mode,
            run_id=run_id,
            ticker=ticker,
        ),
        **details,
    )
    calculation = timed_stage(
        timings,
        "calculation",
        lambda: build_calculation_handoff(
            language=language,
            market=ticker_market,
            mode=mode,
            run_id=run_id,
            ticker=ticker,
        ),
        **details,
    )
    with temporary_env("ANALYST_BACKEND", args.analyst_backend):
        analyst = timed_stage(
            timings,
            "analyst",
            lambda: build_analyst_handoff(
                language=language,
                market=ticker_market,
                mode=mode,
                run_id=run_id,
                ticker=ticker,
            ),
            **details,
        )
    run_profile = annotate_analysis_run_profile(
        analyst.analysis_result_path,
        allow_deterministic_delivery=args.allow_deterministic_delivery,
        allow_fixture_delivery=args.allow_fixture_delivery,
        requested_run_profile=args.run_profile,
    )
    render = None
    if include_render:
        render = timed_stage(
            timings,
            "render",
            lambda: build_render_handoff(
                language=language,
                market=ticker_market,
                mode=mode,
                run_id=run_id,
                ticker=ticker,
            ),
            **details,
        )
    critic = timed_stage(
        timings,
        "critic",
        lambda: build_critic_handoff(
            language=language,
            market=ticker_market,
            mode=mode,
            run_id=run_id,
            ticker=ticker,
        ),
        **details,
    )
    delivery_gate = require_delivery_gate_ready(
        delivery_ready=critic.delivery_ready,
        error_cls=error_cls,
        not_ready_message=(
            f"Mode {mode} ticker quality gate is not ready for delivery: {ticker}"
            if stage_ticker_details
            else f"Mode {mode} quality gate is not ready for delivery"
        ),
        gate_message="quality-report delivery_gate.ready_for_delivery is not true",
        quality_report_path=critic.quality_report_path,
    )
    return TickerPipelineResult(
        ticker=ticker,
        market=ticker_market,
        ticker_summary=ticker_summary,
        extra_stage_payloads=extra_stage_payloads,
        validation=validation,
        calculation=calculation,
        analyst=analyst,
        run_profile=run_profile,
        render=render,
        critic=critic,
        quality_report_path=critic.quality_report_path,
        delivery_gate=delivery_gate,
    )
