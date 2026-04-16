"""Prompt-injection sanitizer for fetched content.

This is the trust-boundary enforcement module described in CLAUDE.md §12.
Every artifact written from a fetch (web research, DART, yfinance, FRED,
news, search snippets, document conversions) MUST be passed through
``sanitize_record`` (or equivalently ``sanitize_text`` for individual
strings) before any agent reads it.

Design choices
--------------
- Zero external dependencies (stdlib only).
- Conservative redaction: matched ranges are replaced with a sentinel
  token; the original text is never repaired.
- Unicode-aware: zero-width characters, tag chars, and bidi controls
  are stripped before pattern matching.
- Pure functions: this module never reads/writes files.
"""

from __future__ import annotations

import copy
import re
import unicodedata
from typing import Any

REDACTION_TOKEN = "[REDACTED:prompt-injection]"
SANITIZER_VERSION = "1"

_INVISIBLE_CHARS = {
    "\u200b",  # ZERO WIDTH SPACE
    "\u200c",  # ZERO WIDTH NON-JOINER
    "\u200d",  # ZERO WIDTH JOINER
    "\u2060",  # WORD JOINER
    "\ufeff",  # ZERO WIDTH NO-BREAK SPACE / BOM
    "\u202a",  # LRE
    "\u202b",  # RLE
    "\u202c",  # PDF
    "\u202d",  # LRO
    "\u202e",  # RLO
    "\u2066",  # LRI
    "\u2067",  # RLI
    "\u2068",  # FSI
    "\u2069",  # PDI
}

_TAG_CHAR_RE = re.compile(r"[\U000e0000-\U000e007f]")


_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "ignore_previous_instructions",
        re.compile(
            r"""
            \b
            (?:ignore|disregard|forget|override)
            \s+
            (?:(?:the|all|any|previous|prior|above|earlier|preceding|system|user)\s+){0,4}
            (?:instructions?|prompts?|rules?|directives?|guidelines?|context|guardrails?)
            \b
            """,
            re.IGNORECASE | re.VERBOSE,
        ),
    ),
    (
        "chatml_marker",
        re.compile(
            r"<\|(?:im_start|im_end|im_sep|endoftext|system|user|assistant)\|>",
            re.IGNORECASE,
        ),
    ),
    (
        "role_override",
        re.compile(
            r"(?im)(?:^|(?<=[\.\!\?\)\]\>\"'\s]))\s*(?:system|assistant|developer|tool)\s*:\s*\S",
        ),
    ),
    (
        "secret_exfil",
        re.compile(
            r"""
            (?:print|reveal|show|leak|exfiltrate|email|send|post|upload|reply\s+with|dump|paste|output)
            \s+
            (?:[\w\.\-]+\s+){0,6}?
            (?:
                api[\s_-]?keys? |
                secrets? |
                tokens? |
                credentials? |
                passwords? |
                \.env |
                env\s+vars? |
                environment\s+variables? |
                system\s+prompts? |
                instructions?
            )
            """,
            re.IGNORECASE | re.VERBOSE,
        ),
    ),
    (
        "shell_command",
        re.compile(
            r"""
            (?:
                rm\s+-rf\s+/ |
                curl\s+\S+\s*\|\s*(?:sh|bash|zsh) |
                wget\s+\S+\s*\|\s*(?:sh|bash|zsh) |
                sudo\s+rm |
                dd\s+if= |
                mkfs\. |
                :\(\)\{\s*:\|:&\s*\};: |
                chmod\s+[0-7]{3,4}\s+/ |
                eval\s*\(\s*atob\(
            )
            """,
            re.IGNORECASE | re.VERBOSE,
        ),
    ),
    (
        "jailbreak",
        re.compile(
            r"""
            (?:
                (?:enable|activate|switch\s+to)\s+
                (?:developer|dan|jailbreak|god|admin|root|debug|unrestricted)\s+mode
                |
                (?:skip|bypass|disable|turn\s+off)\s+
                (?:all\s+)?(?:safety|content|moderation|guardrails?)\s+
                (?:filters?|rules?|checks?|policies?)
                |
                pretend\s+you\s+are\s+(?:an?\s+)?(?:unrestricted|uncensored|evil)
                |
                act\s+as\s+(?:an?\s+)?(?:unrestricted|uncensored|jailbroken)
                |
                you\s+are\s+now\s+(?:a|an)\s+(?:different|new|unrestricted|uncensored)
            )
            """,
            re.IGNORECASE | re.VERBOSE,
        ),
    ),
    (
        "indirect_action",
        re.compile(
            r"""
            (?:
                (?:please\s+)?(?:now\s+)?(?:open|fetch|navigate\s+to|visit|go\s+to)
                \s+(?:this\s+)?url\s*:\s*https?://
                |
                install\s+(?:this\s+)?package\s*:\s*\S+
                |
                run\s+(?:this\s+)?command\s*:\s*\S+
            )
            """,
            re.IGNORECASE | re.VERBOSE,
        ),
    ),
    (
        "rating_override",
        re.compile(
            r"""
            (?:
                (?:rate|classify|tag|mark|recommend|set)\s+
                (?:this\s+)?(?:stock|company|ticker|analysis|review)\s+
                (?:as\s+)?(?:strong\s+)?(?:buy|sell|hold|pass|fail|approved)
                |
                (?:set|change|update|override)\s+(?:the\s+)?
                (?:verdict|rating|recommendation|score)\s+to\s+\w+
            )
            """,
            re.IGNORECASE | re.VERBOSE,
        ),
    ),
)


def _normalize_for_matching(text: str) -> str:
    """Strip invisible/tag characters then NFKC-normalize."""
    if not text:
        return text
    cleaned = "".join(ch for ch in text if ch not in _INVISIBLE_CHARS)
    cleaned = _TAG_CHAR_RE.sub("", cleaned)
    return unicodedata.normalize("NFKC", cleaned)


def _snippet_around(text: str, start: int, end: int, radius: int = 30) -> str:
    lo = max(0, start - radius)
    hi = min(len(text), end + radius)
    return text[lo:hi].replace("\n", " ").strip()


def sanitize_text(
    value: Any,
    *,
    field_path: str = "",
) -> tuple[Any, list[dict[str, str]]]:
    """Sanitize a single value.

    Non-string scalars are returned unchanged with no findings.
    """
    if not isinstance(value, str) or not value:
        return value, []

    findings: list[dict[str, str]] = []

    if any(ch in value for ch in _INVISIBLE_CHARS) or _TAG_CHAR_RE.search(value):
        findings.append(
            {
                "field": field_path,
                "pattern": "unicode_tag_chars",
                "snippet": repr(value[:80]),
            }
        )

    working = _normalize_for_matching(value)

    matches: list[tuple[int, int, str]] = []
    for name, pattern in _PATTERNS:
        for m in pattern.finditer(working):
            matches.append((m.start(), m.end(), name))

    if not matches:
        return working, findings

    matches.sort(key=lambda x: (x[0], -x[1]))
    out: list[str] = []
    cursor = 0
    seen_spans: list[tuple[int, int]] = []
    for start, end, name in matches:
        if any(s <= start < e for s, e in seen_spans):
            continue
        if start < cursor:
            continue
        out.append(working[cursor:start])
        out.append(REDACTION_TOKEN)
        findings.append(
            {
                "field": field_path,
                "pattern": name,
                "snippet": _snippet_around(working, start, end),
            }
        )
        seen_spans.append((start, end))
        cursor = end
    out.append(working[cursor:])
    return "".join(out), findings


def _walk(node: Any, path: str, findings: list[dict[str, str]]) -> Any:
    if isinstance(node, dict):
        out: dict[str, Any] = {}
        for key, child in node.items():
            if key == "_sanitization":
                # Never recurse into prior sanitization metadata.
                out[key] = copy.deepcopy(child)
                continue
            child_path = f"{path}.{key}" if path else str(key)
            out[key] = _walk(child, child_path, findings)
        return out
    if isinstance(node, list):
        return [_walk(item, f"{path}[{i}]", findings) for i, item in enumerate(node)]
    if isinstance(node, str):
        cleaned, item_findings = sanitize_text(node, field_path=path)
        findings.extend(item_findings)
        return cleaned
    return node


def sanitize_record(record: Any) -> tuple[Any, list[dict[str, str]]]:
    """Recursively sanitize a JSON-like structure. Input is not mutated."""
    findings: list[dict[str, str]] = []
    cleaned = _walk(copy.deepcopy(record), "", findings)
    return cleaned, findings


__all__ = [
    "REDACTION_TOKEN",
    "SANITIZER_VERSION",
    "sanitize_record",
    "sanitize_text",
]
