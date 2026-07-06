#!/usr/bin/env python3
"""Compatibility CLI for native Mode C dashboard runs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.run_mode_c_impl import ModeCEntryError, run_mode_c  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.mode.upper() != "C":
        return 2
    try:
        payload = run_mode_c(args)
    except ModeCEntryError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(payload, ensure_ascii=False))
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one production Mode C dashboard.")
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--mode", required=True, choices=["A", "C", "a", "c"])
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


if __name__ == "__main__":
    raise SystemExit(main())
