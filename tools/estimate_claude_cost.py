#!/usr/bin/env python3
"""Summarize Claude Code session token usage and optional model costs.

Usage:
    python tools/estimate_claude_cost.py --repo-cwd .
    python tools/estimate_claude_cost.py --repo-cwd . --latest 3
    python tools/estimate_claude_cost.py --project-dir ~/.claude/projects/my-project
    python tools/estimate_claude_cost.py --repo-cwd . --session 00215236-a09f-47a8-bd47-4f7d2f034e45
    python tools/estimate_claude_cost.py --repo-cwd . --pricing pricing.json

The tool reads Claude Code ``.jsonl`` session logs, de-duplicates streamed
assistant updates by message id, and reports token totals for:

- ``input_tokens``
- ``output_tokens``
- ``cache_creation_input_tokens``
- ``cache_read_input_tokens``

Pricing is optional because model rates can change. Pass a JSON file like:

    {
      "default": {
        "input_per_million": 15.0,
        "output_per_million": 75.0,
        "cache_write_per_million": 18.75,
        "cache_read_per_million": 1.5
      },
      "claude-opus-4-6": {
        "input_per_million": 15.0,
        "output_per_million": 75.0
      }
    }
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import unicodedata
from dataclasses import dataclass
from typing import Any

TOKEN_FIELDS = (
    "input_tokens",
    "output_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
)
RATE_FIELDS = (
    "input_per_million",
    "output_per_million",
    "cache_write_per_million",
    "cache_read_per_million",
)


@dataclass
class PricingSummary:
    priced_cost_usd: float
    total_cost_usd: float | None
    unpriced_models: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "priced_cost_usd": round(self.priced_cost_usd, 6),
            "total_cost_usd": None if self.total_cost_usd is None else round(self.total_cost_usd, 6),
            "unpriced_models": self.unpriced_models,
            "complete": not self.unpriced_models,
        }


def _safe_int(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Estimate Claude Code session token usage and optional costs.",
    )
    parser.add_argument(
        "--repo-cwd",
        default=".",
        help="Repo working directory used to auto-discover matching Claude project logs.",
    )
    parser.add_argument(
        "--claude-projects-dir",
        default="~/.claude/projects",
        help="Root Claude Code projects directory.",
    )
    parser.add_argument(
        "--project-dir",
        action="append",
        default=[],
        help="Explicit Claude project log directory. Can be repeated.",
    )
    parser.add_argument(
        "--session",
        action="append",
        default=[],
        help="Specific session id or .jsonl path to include. Can be repeated.",
    )
    parser.add_argument(
        "--latest",
        type=int,
        default=None,
        help="Only keep the N most recent sessions after discovery.",
    )
    parser.add_argument(
        "--pricing",
        default=None,
        help="Optional JSON file mapping model names to per-million-token USD rates.",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Optional output path. Defaults to stdout.",
    )
    return parser.parse_args(argv)


def _first_text_part(message: object) -> str | None:
    if not isinstance(message, dict):
        return None
    content = message.get("content")
    if not isinstance(content, list):
        return None
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text":
            text = item.get("text")
            if isinstance(text, str) and text.strip():
                return " ".join(text.split())
    return None


def _session_timestamp_bounds(start: str | None, end: str | None, timestamp: object) -> tuple[str | None, str | None]:
    if not isinstance(timestamp, str) or not timestamp:
        return start, end
    if start is None or timestamp < start:
        start = timestamp
    if end is None or timestamp > end:
        end = timestamp
    return start, end


def _blank_token_totals() -> dict[str, int]:
    return {field: 0 for field in TOKEN_FIELDS}


def _usage_totals(usage: dict[str, object]) -> dict[str, int]:
    return {field: _safe_int(usage.get(field)) for field in TOKEN_FIELDS}


def _add_token_totals(target: dict[str, int], usage: dict[str, int]) -> None:
    for field in TOKEN_FIELDS:
        target[field] += usage.get(field, 0)


def _normalize_excerpt(text: str | None, *, limit: int = 160) -> str | None:
    if not text:
        return None
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 1] + "…"


def _iter_jsonl(path: pathlib.Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    with path.open(encoding="utf-8") as fh:
        for line_number, line in enumerate(fh, start=1):
            raw = line.strip()
            if not raw:
                continue
            try:
                item = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}: line {line_number} is not valid JSON: {exc}") from exc
            if not isinstance(item, dict):
                raise ValueError(f"{path}: line {line_number} must be a JSON object")
            records.append(item)
    return records


def _extract_cwd(path: pathlib.Path) -> str | None:
    for record in _iter_jsonl(path):
        cwd = record.get("cwd")
        if isinstance(cwd, str) and cwd:
            return cwd
    return None


def _normalize_path_string(raw: str) -> str:
    return unicodedata.normalize(
        "NFC",
        str(pathlib.Path(os.path.expanduser(raw)).resolve()),
    )


def discover_project_dirs(claude_projects_dir: pathlib.Path, repo_cwd: pathlib.Path) -> list[pathlib.Path]:
    if not claude_projects_dir.exists():
        return []

    resolved_repo_cwd = _normalize_path_string(str(repo_cwd))
    matches: list[pathlib.Path] = []
    for child in sorted(claude_projects_dir.iterdir()):
        if not child.is_dir():
            continue
        for session_path in sorted(child.glob("*.jsonl")):
            cwd = _extract_cwd(session_path)
            if isinstance(cwd, str) and _normalize_path_string(cwd) == resolved_repo_cwd:
                matches.append(child)
                break
    return matches


def resolve_session_paths(project_dirs: list[pathlib.Path], sessions: list[str]) -> list[pathlib.Path]:
    if not sessions:
        discovered: list[pathlib.Path] = []
        for project_dir in project_dirs:
            discovered.extend(sorted(project_dir.glob("*.jsonl")))
        return discovered

    resolved: list[pathlib.Path] = []
    seen: set[pathlib.Path] = set()
    for raw in sessions:
        candidate = pathlib.Path(os.path.expanduser(raw))
        if candidate.exists():
            path = candidate.resolve()
            if path not in seen:
                seen.add(path)
                resolved.append(path)
            continue

        session_name = raw if raw.endswith(".jsonl") else f"{raw}.jsonl"
        matches: list[pathlib.Path] = []
        for project_dir in project_dirs:
            path = (project_dir / session_name).resolve()
            if path.exists():
                matches.append(path)

        if not matches:
            raise ValueError(f"session not found: {raw}")
        if len(matches) > 1:
            rendered = ", ".join(str(path) for path in matches)
            raise ValueError(f"session id is ambiguous: {raw} -> {rendered}")

        path = matches[0]
        if path not in seen:
            seen.add(path)
            resolved.append(path)
    return resolved


def summarize_session(path: pathlib.Path) -> dict[str, Any]:
    records = _iter_jsonl(path)
    assistant_messages: dict[str, dict[str, object]] = {}
    title: str | None = None
    first_user_text: str | None = None
    start_at: str | None = None
    end_at: str | None = None
    session_id = path.stem
    cwd: str | None = None

    for index, record in enumerate(records, start=1):
        start_at, end_at = _session_timestamp_bounds(start_at, end_at, record.get("timestamp"))

        if cwd is None and isinstance(record.get("cwd"), str):
            cwd = record.get("cwd")
        if isinstance(record.get("sessionId"), str):
            session_id = record["sessionId"]

        if record.get("type") == "ai-title" and isinstance(record.get("aiTitle"), str):
            title = record["aiTitle"]

        if record.get("type") == "user" and first_user_text is None:
            first_user_text = _first_text_part(record.get("message"))

        if record.get("type") != "assistant":
            continue
        message = record.get("message")
        if not isinstance(message, dict):
            continue
        usage = message.get("usage")
        if not isinstance(usage, dict):
            continue
        usage_totals = _usage_totals(usage)
        if not any(usage_totals.values()):
            continue
        key = str(message.get("id") or record.get("uuid") or f"line-{index}")
        assistant_messages[key] = {
            "model": message.get("model") if isinstance(message.get("model"), str) else "unknown",
            "usage": usage_totals,
        }

    token_totals = _blank_token_totals()
    model_totals: dict[str, dict[str, Any]] = {}
    for payload in assistant_messages.values():
        model = str(payload["model"])
        usage_totals = payload["usage"]  # type: ignore[assignment]
        _add_token_totals(token_totals, usage_totals)
        if model not in model_totals:
            model_totals[model] = {
                "assistant_messages": 0,
                "tokens": _blank_token_totals(),
            }
        model_totals[model]["assistant_messages"] += 1
        _add_token_totals(model_totals[model]["tokens"], usage_totals)

    return {
        "session_id": session_id,
        "path": str(path.resolve()),
        "cwd": cwd,
        "started_at": start_at,
        "ended_at": end_at,
        "title": title,
        "first_user_text": _normalize_excerpt(first_user_text),
        "assistant_messages": len(assistant_messages),
        "tokens": token_totals,
        "models": model_totals,
    }


def _validate_rate_map(label: str, rates: dict[str, Any]) -> dict[str, float]:
    normalized: dict[str, float] = {}
    for field in RATE_FIELDS:
        value = rates.get(field, 0.0)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError(f"{label}: {field} must be numeric")
        normalized[field] = float(value)
    return normalized


def load_pricing(path: pathlib.Path) -> dict[str, dict[str, float]]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: invalid JSON: {exc}") from exc

    if not isinstance(raw, dict):
        raise ValueError(f"{path}: pricing file must contain a JSON object")

    if any(field in raw for field in RATE_FIELDS):
        raw = {"default": raw}

    pricing: dict[str, dict[str, float]] = {}
    for label, rates in raw.items():
        if not isinstance(label, str):
            raise ValueError(f"{path}: pricing keys must be strings")
        if not isinstance(rates, dict):
            raise ValueError(f"{path}: pricing entry {label!r} must be an object")
        pricing[label] = _validate_rate_map(label, rates)
    return pricing


def _cost_from_tokens(tokens: dict[str, int], rates: dict[str, float]) -> float:
    return (
        tokens["input_tokens"] / 1_000_000 * rates["input_per_million"]
        + tokens["output_tokens"] / 1_000_000 * rates["output_per_million"]
        + tokens["cache_creation_input_tokens"] / 1_000_000 * rates["cache_write_per_million"]
        + tokens["cache_read_input_tokens"] / 1_000_000 * rates["cache_read_per_million"]
    )


def attach_costs(summary: dict[str, Any], pricing: dict[str, dict[str, float]] | None) -> None:
    if pricing is None:
        return

    priced_cost = 0.0
    unpriced_models: list[str] = []
    for model, model_summary in summary["models"].items():
        rates = pricing.get(model) or pricing.get("default")
        if rates is None:
            unpriced_models.append(model)
            continue
        cost = _cost_from_tokens(model_summary["tokens"], rates)
        model_summary["cost_usd"] = round(cost, 6)
        priced_cost += cost

    pricing_summary = PricingSummary(
        priced_cost_usd=priced_cost,
        total_cost_usd=None if unpriced_models else priced_cost,
        unpriced_models=sorted(unpriced_models),
    )
    summary["cost"] = pricing_summary.to_dict()


def build_report(
    sessions: list[dict[str, Any]],
    project_dirs: list[pathlib.Path],
    pricing: dict[str, dict[str, float]] | None,
) -> dict[str, Any]:
    total_tokens = _blank_token_totals()
    model_totals: dict[str, dict[str, Any]] = {}

    for session in sessions:
        attach_costs(session, pricing)
        _add_token_totals(total_tokens, session["tokens"])
        for model, model_summary in session["models"].items():
            if model not in model_totals:
                model_totals[model] = {
                    "assistant_messages": 0,
                    "tokens": _blank_token_totals(),
                }
            model_totals[model]["assistant_messages"] += model_summary["assistant_messages"]
            _add_token_totals(model_totals[model]["tokens"], model_summary["tokens"])

    summary = {
        "project_dirs": [str(path.resolve()) for path in project_dirs],
        "session_count": len(sessions),
        "assistant_messages": sum(session["assistant_messages"] for session in sessions),
        "tokens": total_tokens,
        "models": model_totals,
        "sessions": sessions,
    }
    attach_costs(summary, pricing)
    return summary


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    claude_projects_dir = pathlib.Path(os.path.expanduser(args.claude_projects_dir)).resolve()
    repo_cwd = pathlib.Path(args.repo_cwd).resolve()
    explicit_project_dirs = [pathlib.Path(os.path.expanduser(raw)).resolve() for raw in args.project_dir]

    project_dirs = explicit_project_dirs or discover_project_dirs(claude_projects_dir, repo_cwd)
    if not project_dirs:
        print(
            "error: no Claude project logs matched this repo cwd; pass --project-dir explicitly",
            file=sys.stderr,
        )
        return 2

    try:
        session_paths = resolve_session_paths(project_dirs, args.session)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if not session_paths:
        print("error: no session logs found", file=sys.stderr)
        return 2

    try:
        summaries = [summarize_session(path) for path in session_paths]
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    summaries.sort(key=lambda item: item.get("ended_at") or item.get("started_at") or "", reverse=True)
    if args.latest is not None:
        if args.latest <= 0:
            print("error: --latest must be a positive integer", file=sys.stderr)
            return 2
        summaries = summaries[: args.latest]

    pricing = None
    if args.pricing:
        try:
            pricing = load_pricing(pathlib.Path(os.path.expanduser(args.pricing)).resolve())
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

    report = build_report(summaries, project_dirs, pricing)
    payload = json.dumps(report, ensure_ascii=False, indent=2)

    if args.out:
        out_path = pathlib.Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
