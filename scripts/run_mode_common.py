"""Shared helpers for native run-mode entrypoints."""

from __future__ import annotations

import os
import shutil
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from scripts.parity.data_sources import load_json, write_json
from scripts.run_abc_parity import record_stage
from tools.analysis_contract import build_default_report_path
from tools.backend_providers import DETERMINISTIC_BACKEND_PROVIDERS, FIXTURE_BACKEND_PROVIDERS

REPO_ROOT = Path(__file__).resolve().parents[1]


class RunModeExecutionError(RuntimeError):
    pass


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
