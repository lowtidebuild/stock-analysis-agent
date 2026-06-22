#!/usr/bin/env python3
"""Portable sanitized web search wrapper.

The output is shaped as run-local ``tier2-raw.json`` so harnesses without a
native search tool can still produce a validated fetched-content artifact.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tools.prompt_injection_filter import SANITIZER_VERSION, sanitize_record


PROVIDER_ENV_KEYS = {
    "tavily": "TAVILY_API_KEY",
    "brave": "BRAVE_API_KEY",
}


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def count_string_fields(node: Any) -> int:
    if isinstance(node, dict):
        return sum(
            count_string_fields(value)
            for key, value in node.items()
            if key != "_sanitization"
        )
    if isinstance(node, list):
        return sum(count_string_fields(item) for item in node)
    if isinstance(node, str):
        return 1
    return 0


def with_sanitization(payload: dict[str, Any], *, now: str) -> dict[str, Any]:
    fields_scanned = count_string_fields(payload)
    cleaned, findings = sanitize_record(payload)
    if not isinstance(cleaned, dict):
        cleaned = {"_root": cleaned}
    cleaned["_sanitization"] = {
        "tool": "tools/prompt_injection_filter.py",
        "version": SANITIZER_VERSION,
        "timestamp": now,
        "fields_scanned": fields_scanned,
        "redactions": len(findings),
        "findings": findings,
    }
    return cleaned


def build_search_envelope(
    query: str,
    raw_results: list[dict[str, Any]],
    *,
    provider: str,
    now: str,
    query_id: str = "q1",
) -> dict[str, Any]:
    return {
        "query": query,
        "provider": provider,
        "raw_search_results": [
            normalize_result(
                result,
                query=query,
                query_id=query_id,
                rank=index,
                now=now,
            )
            for index, result in enumerate(raw_results, start=1)
        ],
    }


def build_tier2_artifact(
    ticker: str,
    market: str,
    queries: list[str],
    provider: str,
    now: str,
    raw_results_by_query: dict[str, list[dict[str, Any]]],
    *,
    reason: str | None = None,
    status: str = "ok",
) -> dict[str, Any]:
    raw_search_results: list[dict[str, Any]] = []
    for query_index, query in enumerate(queries, start=1):
        envelope = build_search_envelope(
            query,
            raw_results_by_query.get(query, []),
            provider=provider,
            now=now,
            query_id=f"q{query_index}",
        )
        raw_search_results.extend(envelope["raw_search_results"])

    payload: dict[str, Any] = {
        "ticker": ticker.strip().upper(),
        "collection_timestamp": now,
        "market": market,
        "status": status,
        "provider": provider,
        "raw_search_results": raw_search_results,
        "extracted_metric_candidates": [],
        "metric_conflicts": [],
    }
    if reason:
        payload["reason"] = reason
    return with_sanitization(payload, now=now)


def normalize_result(
    result: dict[str, Any],
    *,
    query: str,
    query_id: str,
    rank: int,
    now: str,
) -> dict[str, Any]:
    url = string_value(result.get("url") or result.get("link"))
    return {
        "query_id": query_id,
        "query": query,
        "rank": rank,
        "title": string_value(result.get("title") or result.get("name")),
        "url": url,
        "published_date": nullable_string(
            result.get("published_date")
            or result.get("published")
            or result.get("date")
            or result.get("age")
        ),
        "retrieved_at": now,
        "snippet": string_value(
            result.get("snippet")
            or result.get("content")
            or result.get("description")
            or result.get("summary")
        ),
        "source_domain": source_domain(url),
    }


def search(
    queries: list[str],
    *,
    ticker: str,
    market: str,
    max_results: int = 5,
    provider: str | None = None,
    now: str | None = None,
    timeout: int = 20,
) -> dict[str, Any]:
    timestamp = now or utc_now()
    normalized_provider = (provider or os.environ.get("WEB_SEARCH_PROVIDER") or "tavily").strip().lower()
    normalized_queries = [query.strip() for query in queries if query.strip()]

    if normalized_provider == "none":
        return build_tier2_artifact(
            ticker,
            market,
            normalized_queries,
            "none",
            timestamp,
            {},
            status="unavailable",
            reason="no_provider",
        )
    if normalized_provider not in _PROVIDERS:
        return build_tier2_artifact(
            ticker,
            market,
            normalized_queries,
            normalized_provider,
            timestamp,
            {},
            status="unavailable",
            reason="unsupported_provider",
        )

    key_name = PROVIDER_ENV_KEYS[normalized_provider]
    api_key = os.environ.get(key_name, "").strip()
    if not api_key:
        return build_tier2_artifact(
            ticker,
            market,
            normalized_queries,
            normalized_provider,
            timestamp,
            {},
            status="unavailable",
            reason="no_provider",
        )

    raw_results_by_query: dict[str, list[dict[str, Any]]] = {}
    try:
        for query in normalized_queries:
            raw_results_by_query[query] = _PROVIDERS[normalized_provider](
                query=query,
                api_key=api_key,
                max_results=max_results,
                timeout=timeout,
            )
    except Exception as exc:  # noqa: BLE001 - CLI must degrade to an artifact.
        return build_tier2_artifact(
            ticker,
            market,
            normalized_queries,
            normalized_provider,
            timestamp,
            raw_results_by_query,
            status="error",
            reason=str(exc)[:500] or exc.__class__.__name__,
        )

    return build_tier2_artifact(
        ticker,
        market,
        normalized_queries,
        normalized_provider,
        timestamp,
        raw_results_by_query,
    )


def _tavily(
    *,
    query: str,
    api_key: str,
    max_results: int,
    timeout: int,
) -> list[dict[str, Any]]:
    payload = {
        "api_key": api_key,
        "query": query,
        "max_results": max_results,
        "include_answer": False,
        "include_raw_content": False,
    }
    data = http_json(
        "https://api.tavily.com/search",
        method="POST",
        payload=payload,
        headers={"Content-Type": "application/json"},
        timeout=timeout,
    )
    results = data.get("results") if isinstance(data, dict) else None
    return [item for item in results if isinstance(item, dict)] if isinstance(results, list) else []


def _brave(
    *,
    query: str,
    api_key: str,
    max_results: int,
    timeout: int,
) -> list[dict[str, Any]]:
    params = urllib.parse.urlencode({"q": query, "count": max_results})
    data = http_json(
        f"https://api.search.brave.com/res/v1/web/search?{params}",
        method="GET",
        headers={
            "Accept": "application/json",
            "X-Subscription-Token": api_key,
        },
        timeout=timeout,
    )
    web = data.get("web") if isinstance(data, dict) else None
    results = web.get("results") if isinstance(web, dict) else None
    return [item for item in results if isinstance(item, dict)] if isinstance(results, list) else []


def http_json(
    url: str,
    *,
    method: str,
    headers: dict[str, str] | None = None,
    payload: dict[str, Any] | None = None,
    timeout: int,
) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url,
        data=body,
        headers=headers or {},
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            text = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code}: {exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"request failed: {exc.reason}") from exc

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("provider returned invalid JSON") from exc
    return parsed if isinstance(parsed, dict) else {}


def string_value(value: Any) -> str:
    return "" if value is None else str(value)


def nullable_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def source_domain(url: str) -> str:
    try:
        return urllib.parse.urlparse(url).netloc.lower()
    except Exception:  # noqa: BLE001 - malformed provider URL.
        return ""


def write_output(payload: dict[str, Any], output: str | None) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if output:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")
        return
    print(text)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run portable sanitized web search.")
    parser.add_argument("--query", action="append", required=True)
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--market", required=True, choices=["US", "KR"])
    parser.add_argument("--max-results", type=int, default=5)
    parser.add_argument("--provider", choices=["tavily", "brave", "none"], default=None)
    parser.add_argument("--output", default=None)
    parser.add_argument("--now", default=None)
    parser.add_argument("--timeout", type=int, default=20)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = search(
        args.query,
        ticker=args.ticker,
        market=args.market,
        max_results=args.max_results,
        provider=args.provider,
        now=args.now,
        timeout=args.timeout,
    )
    write_output(payload, args.output)
    return 0


_PROVIDERS = {
    "tavily": _tavily,
    "brave": _brave,
}


if __name__ == "__main__":
    sys.exit(main())
