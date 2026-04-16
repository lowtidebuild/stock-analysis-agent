#!/usr/bin/env python3
"""Apply tools.prompt_injection_filter to a JSON artifact.

This is the post-fetch sanitization step described in CLAUDE.md §12 and
in `.claude/skills/web-researcher/SKILL.md` Step 4.10.

Usage
-----
  # In-place (most common — the collectors call it this way)
  python tools/sanitize_artifact.py --in output/data/AAPL/tier2-raw.json --in-place

  # Separate output file
  python tools/sanitize_artifact.py --in src.json --out cleaned.json

  # Strict mode: exit 1 if any redactions occur (useful in CI / hooks)
  python tools/sanitize_artifact.py --in artifact.json --in-place --strict

The output JSON gains a top-level ``_sanitization`` block:

    {
      "_sanitization": {
        "tool": "tools/prompt_injection_filter.py",
        "version": "1",
        "timestamp": "2026-04-16T00:00:00Z",
        "fields_scanned": 42,
        "redactions": 0,
        "findings": []
      }
    }

Downstream agents must refuse to read any artifact lacking this block.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import tempfile
from datetime import datetime, timezone

THIS_FILE = pathlib.Path(__file__).resolve()
sys.path.insert(0, str(THIS_FILE.parent.parent))

from tools.prompt_injection_filter import (  # noqa: E402
    SANITIZER_VERSION,
    sanitize_record,
)


def _count_string_fields(node: object) -> int:
    if isinstance(node, dict):
        return sum(_count_string_fields(v) for k, v in node.items() if k != "_sanitization")
    if isinstance(node, list):
        return sum(_count_string_fields(item) for item in node)
    if isinstance(node, str):
        return 1
    return 0


def _atomic_write(path: pathlib.Path, payload: str) -> None:
    """Write payload to ``path`` atomically (same-filesystem temp + rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=path.name + ".",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Sanitize a JSON artifact against prompt-injection patterns.",
    )
    parser.add_argument("--in", dest="in_path", required=True, help="Input JSON file.")
    parser.add_argument("--out", dest="out_path", default=None, help="Output JSON file.")
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="Rewrite the input file in place (mutually exclusive with --out).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 if any redactions occurred.",
    )
    args = parser.parse_args(argv)

    if args.in_place and args.out_path:
        parser.error("--in-place and --out are mutually exclusive")
    if not args.in_place and not args.out_path:
        parser.error("must provide either --in-place or --out")

    in_path = pathlib.Path(args.in_path)
    if not in_path.exists():
        print(f"error: input file not found: {in_path}", file=sys.stderr)
        return 2

    try:
        record = json.loads(in_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"error: input is not valid JSON: {exc}", file=sys.stderr)
        return 2

    fields_scanned = _count_string_fields(record)
    cleaned, findings = sanitize_record(record)

    if not isinstance(cleaned, dict):
        # We only attach _sanitization to top-level objects. If the
        # artifact is a list or a scalar we wrap it.
        cleaned = {"_root": cleaned}

    cleaned["_sanitization"] = {
        "tool": "tools/prompt_injection_filter.py",
        "version": SANITIZER_VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "fields_scanned": fields_scanned,
        "redactions": len(findings),
        "findings": findings,
    }

    payload = json.dumps(cleaned, ensure_ascii=False, indent=2)
    out_path = in_path if args.in_place else pathlib.Path(args.out_path)
    _atomic_write(out_path, payload)

    print(
        f"sanitized {in_path} -> {out_path} "
        f"(scanned={fields_scanned}, redactions={len(findings)})"
    )

    if args.strict and findings:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
