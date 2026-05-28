"""Data-source adapters for the A/B/C production parity runner.

Session 2 scope is deliberately limited to raw artifact collection. The
validators and renderers consume these artifacts in later sessions.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

FINANCIAL_DATASETS_DEFAULT_BASE_URL = "https://api.financialdatasets.ai"
DEFAULT_SOURCE_CACHE_TTLS_SECONDS = {
    "financial_datasets": 15 * 60,
    "yfinance": 15 * 60,
    "dart": 24 * 60 * 60,
    "fred": 24 * 60 * 60,
}


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


def env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    if raw in {"0", "false", "no", "off"}:
        return False
    if raw in {"1", "true", "yes", "on"}:
        return True
    return default


@dataclass(frozen=True)
class SourceResult:
    source: str
    status: str
    output_path: Path
    summary: dict[str, Any]
    exit_code: int = 0


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_json(path: Path) -> dict[str, Any]:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def unavailable_artifact(
    *,
    output_path: Path,
    reason: str,
    source: str,
    ticker: str | None = None,
) -> SourceResult:
    payload = {
        "schema_version": "abc-parity-raw-source-v1",
        "source": source,
        "status": "unavailable",
        "reason": reason,
        "ticker": ticker,
        "collection_timestamp": utc_now(),
    }
    write_json(output_path, payload)
    return SourceResult(
        source=source,
        status="unavailable",
        output_path=output_path,
        summary={"reason": reason},
        exit_code=1,
    )


def skipped_artifact(
    *,
    output_path: Path,
    reason: str,
    source: str,
    ticker: str | None = None,
) -> SourceResult:
    payload = {
        "schema_version": "abc-parity-raw-source-v1",
        "source": source,
        "status": "skipped",
        "reason": reason,
        "ticker": ticker,
        "collection_timestamp": utc_now(),
    }
    write_json(output_path, payload)
    return SourceResult(
        source=source,
        status="skipped",
        output_path=output_path,
        summary={"reason": reason},
        exit_code=0,
    )


def collect_financial_datasets(
    *,
    output_path: Path,
    ticker: str,
    market: str,
    timeout: int = 20,
) -> SourceResult:
    """Collect US raw data from Financial Datasets HTTP API.

    The existing Claude Code path uses the Financial Datasets MCP. Fly workers
    need a server-side HTTP adapter instead. Endpoint names follow the official
    Financial Datasets REST docs: /financials, /prices, /filings,
    /insider-trades, /analyst-estimates.
    """

    if market != "US":
        return skipped_artifact(
            output_path=output_path,
            reason="financial_datasets_us_only",
            source="financial_datasets",
            ticker=ticker,
        )

    base_url = (
        os.environ.get("FINANCIAL_DATASETS_BASE_URL")
        or FINANCIAL_DATASETS_DEFAULT_BASE_URL
    ).rstrip("/")
    today = datetime.now(UTC).date()
    start_date = today - timedelta(days=14)
    cache_key_parts = {
        "base_url": base_url,
        "end_date": today.isoformat(),
        "market": market,
        "source": "financial_datasets",
        "start_date": start_date.isoformat(),
        "ticker": ticker,
    }
    cached = restore_collector_cache(
        cache_key_parts=cache_key_parts,
        market=market,
        output_path=output_path,
        source="financial_datasets",
        ticker=ticker,
    )
    if cached is not None:
        return cached

    api_key = os.environ.get("FINANCIAL_DATASETS_API_KEY", "").strip()
    if not api_key:
        return unavailable_artifact(
            output_path=output_path,
            reason="missing_financial_datasets_api_key",
            source="financial_datasets",
            ticker=ticker,
        )

    endpoint_specs = [
        (
            "financials_quarterly",
            "/financials",
            {"ticker": ticker, "period": "quarterly", "limit": "8"},
        ),
        (
            "financials_ttm",
            "/financials",
            {"ticker": ticker, "period": "ttm", "limit": "1"},
        ),
        (
            "prices_recent",
            "/prices",
            {
                "ticker": ticker,
                "interval": "day",
                "interval_multiplier": "1",
                "start_date": start_date.isoformat(),
                "end_date": today.isoformat(),
            },
        ),
        ("filings", "/filings", {"ticker": ticker, "limit": "10"}),
        ("insider_trades", "/insider-trades", {"ticker": ticker, "limit": "50"}),
        (
            "analyst_estimates",
            "/analyst-estimates",
            {"ticker": ticker, "period": "quarterly", "limit": "8"},
        ),
    ]

    def fetch_endpoint(spec: tuple[str, str, dict[str, str]]) -> tuple[str, Any, dict[str, str] | None]:
        label, endpoint, params = spec
        try:
            payload = financial_datasets_get(
                base_url=base_url,
                endpoint=endpoint,
                params=params,
                api_key=api_key,
                timeout=timeout,
            )
        except Exception as exc:  # noqa: BLE001 - raw adapter must preserve failures
            return (
                label,
                None,
                {"endpoint": endpoint, "label": label, "message": str(exc)[:500]},
            )
        return label, payload, None

    results_by_label: dict[str, Any] = {}
    errors_by_label: dict[str, dict[str, str]] = {}
    max_workers = env_int(
        "SAA_FINANCIAL_DATASETS_MAX_WORKERS",
        3,
        maximum=len(endpoint_specs),
    )
    if max_workers == 1:
        for spec in endpoint_specs:
            label, payload, error = fetch_endpoint(spec)
            results_by_label[label] = payload
            if error is not None:
                errors_by_label[label] = error
    else:
        with ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="financial-datasets",
        ) as executor:
            futures = [executor.submit(fetch_endpoint, spec) for spec in endpoint_specs]
            for future in as_completed(futures):
                label, payload, error = future.result()
                results_by_label[label] = payload
                if error is not None:
                    errors_by_label[label] = error

    calls = {label: results_by_label.get(label) for label, _endpoint, _params in endpoint_specs}
    errors = [
        errors_by_label[label]
        for label, _endpoint, _params in endpoint_specs
        if label in errors_by_label
    ]

    succeeded = sum(1 for value in calls.values() if value is not None)
    status = "success" if succeeded == len(endpoint_specs) else "partial" if succeeded else "failed"
    payload = {
        "schema_version": "abc-parity-financial-datasets-raw-v1",
        "source": "financial_datasets",
        "status": status,
        "ticker": ticker,
        "market": market,
        "base_url": base_url,
        "collection_timestamp": utc_now(),
        "calls": calls,
        "errors": errors,
    }
    write_json(output_path, payload)
    result = SourceResult(
        source="financial_datasets",
        status=status,
        output_path=output_path,
        summary={"calls_succeeded": succeeded, "calls_failed": len(errors)},
        exit_code=0 if succeeded else 1,
    )
    store_collector_cache(
        cache_key_parts=cache_key_parts,
        market=market,
        result=result,
        ticker=ticker,
    )
    return result


def financial_datasets_get(
    *,
    api_key: str,
    base_url: str,
    endpoint: str,
    params: dict[str, str],
    timeout: int,
) -> dict[str, Any]:
    url = f"{base_url}{endpoint}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "StockAnalysisAgent/2.2 parity-runner",
            "X-API-KEY": api_key,
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {body[:300]}") from exc
    parsed = json.loads(raw)
    return parsed if isinstance(parsed, dict) else {"data": parsed}


def collect_yfinance(
    *,
    output_path: Path,
    ticker: str,
    market: str,
    timeout: int = 20,
) -> SourceResult:
    cache_key_parts = {
        "bundle": "standard",
        "market": market if market in {"US", "KR"} else "US",
        "source": "yfinance",
        "ticker": ticker,
    }
    cached = restore_collector_cache(
        cache_key_parts=cache_key_parts,
        market=market,
        output_path=output_path,
        source="yfinance",
        ticker=ticker,
    )
    if cached is not None:
        return cached
    result = run_existing_collector(
        source="yfinance",
        command=[
            sys.executable,
            ".claude/skills/financial-data-collector/scripts/yfinance-collector.py",
            "--ticker",
            ticker,
            "--market",
            market if market in {"US", "KR"} else "US",
            "--output",
            display_path(output_path),
            "--bundle",
            "standard",
            "--timeout",
            str(timeout),
        ],
        output_path=output_path,
        ticker=ticker,
    )
    store_collector_cache(
        cache_key_parts=cache_key_parts,
        market=market,
        result=result,
        ticker=ticker,
    )
    return result


def collect_peer_mini_fetch(
    *,
    output_dir: Path,
    summary_path: Path,
    tickers: list[str],
    timeout: int = 20,
) -> SourceResult:
    if not tickers:
        return skipped_artifact(
            output_path=summary_path,
            reason="no_peer_tickers",
            source="peer_mini_fetch",
        )

    command = [
        sys.executable,
        ".claude/skills/financial-data-collector/scripts/peer-fetch.py",
        "--tickers",
        *tickers,
        "--output-dir",
        display_path(output_dir),
        "--cache-dir",
        "output/data/peers-cache",
        "--cache-ttl-hours",
        str(env_int("SAA_PEER_CACHE_TTL_HOURS", 24)),
        "--timeout",
        str(timeout),
    ]
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    summary = parse_stdout_json(result.stdout)
    collected = summary.get("tickers_collected")
    failed = summary.get("tickers_failed")
    payload = {
        "schema_version": "abc-parity-peer-mini-fetch-summary-v1",
        "source": "peer_mini_fetch",
        "status": "success" if result.returncode == 0 else "failed",
        "tickers_requested": tickers,
        "tickers_collected": collected if isinstance(collected, list) else [],
        "tickers_failed": failed if isinstance(failed, list) else tickers,
        "output_dir": display_path(output_dir),
        "cache_dir": "output/data/peers-cache",
        "collection_timestamp": utc_now(),
        "exit_code": result.returncode,
        "stderr": result.stderr[-2000:],
    }
    write_json(summary_path, payload)
    return SourceResult(
        source="peer_mini_fetch",
        status=payload["status"],
        output_path=summary_path,
        summary={
            "tickers_requested": tickers,
            "tickers_collected": payload["tickers_collected"],
            "tickers_failed": payload["tickers_failed"],
        },
        exit_code=result.returncode,
    )


def collect_dart(
    *,
    output_path: Path,
    ticker: str,
    market: str,
) -> SourceResult:
    if market != "KR":
        return skipped_artifact(
            output_path=output_path,
            reason="dart_kr_only",
            source="dart",
            ticker=ticker,
        )
    cache_key_parts = {"market": market, "source": "dart", "ticker": ticker}
    cached = restore_collector_cache(
        cache_key_parts=cache_key_parts,
        market=market,
        output_path=output_path,
        source="dart",
        ticker=ticker,
    )
    if cached is not None:
        return cached
    result = run_existing_collector(
        source="dart",
        command=[
            sys.executable,
            ".claude/skills/web-researcher/scripts/dart-collector.py",
            "--stock-code",
            ticker,
            "--output",
            display_path(output_path),
        ],
        output_path=output_path,
        ticker=ticker,
    )
    store_collector_cache(
        cache_key_parts=cache_key_parts,
        market=market,
        result=result,
        ticker=ticker,
    )
    return result


def collect_fred(
    *,
    output_path: Path,
    market: str,
) -> SourceResult:
    normalized_market = "KR" if market == "KR" else "US"
    cache_key_parts = {"market": normalized_market, "source": "fred", "ticker": "macro"}
    cached = restore_collector_cache(
        cache_key_parts=cache_key_parts,
        market=normalized_market,
        output_path=output_path,
        source="fred",
        ticker=None,
    )
    if cached is not None:
        return cached
    result = run_existing_collector(
        source="fred",
        command=[
            sys.executable,
            ".claude/skills/web-researcher/scripts/fred-collector.py",
            "--market",
            normalized_market,
            "--output",
            display_path(output_path),
        ],
        output_path=output_path,
        ticker=None,
    )
    store_collector_cache(
        cache_key_parts=cache_key_parts,
        market=normalized_market,
        result=result,
        ticker=None,
    )
    return result


def collector_cache_enabled() -> bool:
    return env_bool("SAA_COLLECTOR_CACHE", True)


def collector_cache_root() -> Path:
    raw = os.environ.get("SAA_COLLECTOR_CACHE_DIR", "output/data/source-cache").strip()
    path = Path(raw or "output/data/source-cache").expanduser()
    return path if path.is_absolute() else REPO_ROOT / path


def collector_cache_ttl_seconds(source: str) -> int:
    source_env = "SAA_" + re.sub(r"[^A-Z0-9]+", "_", source.upper()) + "_CACHE_TTL_SECONDS"
    default = DEFAULT_SOURCE_CACHE_TTLS_SECONDS.get(source, 15 * 60)
    for name in (source_env, "SAA_COLLECTOR_CACHE_TTL_SECONDS"):
        raw = os.environ.get(name, "").strip()
        if not raw:
            continue
        try:
            return max(int(raw), 0)
        except ValueError:
            continue
    return default


def collector_cache_path(source: str, cache_key_parts: dict[str, Any]) -> Path:
    key = json.dumps(cache_key_parts, ensure_ascii=False, sort_keys=True)
    digest = re.sub(r"[^a-zA-Z0-9_.-]+", "-", cache_key_parts.get("ticker", "global") or "global")
    digest = f"{digest}-{hash_text(key)[:20]}"
    return collector_cache_root() / source / f"{digest}.json"


def restore_collector_cache(
    *,
    cache_key_parts: dict[str, Any],
    market: str,
    output_path: Path,
    source: str,
    ticker: str | None,
) -> SourceResult | None:
    if not collector_cache_enabled():
        return None
    ttl_seconds = collector_cache_ttl_seconds(source)
    if ttl_seconds <= 0:
        return None
    cache_path = collector_cache_path(source, cache_key_parts)
    cache = load_json(cache_path)
    if not cache:
        return None
    payload = cache.get("payload")
    if not isinstance(payload, dict):
        return None
    cached_at = parse_utc(cache.get("cached_at"))
    if cached_at is None:
        return None
    age_seconds = (datetime.now(UTC) - cached_at).total_seconds()
    if age_seconds > ttl_seconds:
        return None

    restored = dict(payload)
    restored["source_cache"] = {
        "status": "hit",
        "cache_path": display_path(cache_path),
        "cached_at": cache.get("cached_at"),
        "age_seconds": round(max(age_seconds, 0.0), 3),
        "ttl_seconds": ttl_seconds,
        "source_status": cache.get("source_status"),
    }
    write_json(output_path, restored)
    return SourceResult(
        source=source,
        status="cached",
        output_path=output_path,
        summary={
            "cache_status": "hit",
            "cache_path": display_path(cache_path),
            "market": market,
            "source_status": cache.get("source_status"),
            "ticker": ticker,
            "ttl_seconds": ttl_seconds,
        },
        exit_code=0,
    )


def store_collector_cache(
    *,
    cache_key_parts: dict[str, Any],
    market: str,
    result: SourceResult,
    ticker: str | None,
) -> None:
    if not collector_cache_enabled() or result.status not in {"success", "partial", "cached", "stale_cache"}:
        return
    ttl_seconds = collector_cache_ttl_seconds(result.source)
    if ttl_seconds <= 0:
        return
    payload = load_json(result.output_path)
    if not payload:
        return
    payload = dict(payload)
    payload.pop("source_cache", None)
    cache_path = collector_cache_path(result.source, cache_key_parts)
    cached_at = utc_now()
    cache_record = {
        "schema_version": "abc-parity-source-cache-v1",
        "source": result.source,
        "ticker": ticker,
        "market": market,
        "cache_key": cache_key_parts,
        "cached_at": cached_at,
        "ttl_seconds": ttl_seconds,
        "expires_at": iso_from_datetime(datetime.now(UTC) + timedelta(seconds=ttl_seconds)),
        "source_status": result.status,
        "payload": payload,
    }
    write_json(cache_path, cache_record)


def parse_utc(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        if value.endswith("Z"):
            return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def iso_from_datetime(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def hash_text(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return str(path.resolve())


def run_existing_collector(
    *,
    command: list[str],
    output_path: Path,
    source: str,
    ticker: str | None,
) -> SourceResult:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    summary = parse_stdout_json(result.stdout)
    if output_path.exists():
        payload = load_json(output_path)
        status = normalize_status(
            summary.get("status") or payload.get("status") or payload.get("api_status"),
            result.returncode,
        )
        return SourceResult(
            source=source,
            status=status,
            output_path=output_path,
            summary=summary,
            exit_code=result.returncode,
        )

    payload = {
        "schema_version": "abc-parity-raw-source-v1",
        "source": source,
        "status": "failed",
        "ticker": ticker,
        "collection_timestamp": utc_now(),
        "command": command,
        "exit_code": result.returncode,
        "stdout": result.stdout[-2000:],
        "stderr": result.stderr[-2000:],
    }
    write_json(output_path, payload)
    return SourceResult(
        source=source,
        status="failed",
        output_path=output_path,
        summary={"stderr": result.stderr[-500:]},
        exit_code=result.returncode or 1,
    )


def parse_stdout_json(stdout: str) -> dict[str, Any]:
    text = stdout.strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        pass
    try:
        parsed = json.loads(text.splitlines()[-1])
    except json.JSONDecodeError:
        return {"stdout": text[-500:]}
    return parsed if isinstance(parsed, dict) else {}


def normalize_status(value: Any, exit_code: int) -> str:
    if isinstance(value, str):
        lowered = value.lower()
        if lowered in {"success", "partial", "cached", "stale_cache"}:
            return "success" if lowered in {"success", "cached"} else "partial"
        if lowered in {"fail", "failed", "unavailable", "skipped"}:
            return "failed" if lowered in {"fail", "failed"} else lowered
    return "success" if exit_code == 0 else "partial" if exit_code == 1 else "failed"
