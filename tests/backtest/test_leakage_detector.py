"""Tests for tools.backtest.leakage_detector.LeakageDetector.

Covers Task 1.3 of the backtest harness plan
(``docs/superpowers/plans/2026-05-08-backtest-harness.md``):

- Strict mode raises :class:`LeakageError` on the first future-dated field;
  lenient mode collects every finding without raising.
- Recursion through nested dicts and lists, building a JSON-pointer-like
  path so callers can pinpoint the offending field.
- Field-suffix matching is case-insensitive and limited to keys that end
  in ``_date`` / ``_datetime`` (no false positives on free-text fields
  that happen to contain date-shaped substrings).
- Unparseable date strings (and non-string values where a date is
  expected) are still recorded as findings, so fetchers cannot launder
  bad data through "we just couldn't read it".
- ``source_label`` becomes the root of the reported path so a caller
  can label e.g. ``"tier2-raw.json"`` vs ``"dart-api-raw.json"``.

Run via: ``python -m pytest tests/backtest/test_leakage_detector.py -v``
"""

from __future__ import annotations

import datetime as _dt
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.backtest.leakage_detector import (  # noqa: E402
    LeakageDetector,
    LeakageError,
    LeakageFinding,
)

AS_OF = _dt.date(2025, 4, 14)


# ---------------------------------------------------------------------------
# Clean payloads (no findings)
# ---------------------------------------------------------------------------


def test_no_findings_for_clean_payload() -> None:
    detector = LeakageDetector(strict=True)
    payload = {
        "ticker": "AAPL",
        "filing_date": "2025-01-15",
        "news_items": [
            {"published_date": "2025-04-10", "title": "old news"},
            {"published_date": "2025-04-14", "title": "as-of news"},
        ],
    }
    # Should not raise and should return an empty list.
    findings = detector.check(payload, AS_OF)
    assert findings == []


def test_lenient_clean_payload_returns_empty_list() -> None:
    detector = LeakageDetector(strict=False)
    findings = detector.check({"published_date": "2020-01-01"}, AS_OF)
    assert findings == []


def test_empty_payload_no_crash() -> None:
    detector = LeakageDetector(strict=True)
    assert detector.check({}, AS_OF) == []
    assert detector.check([], AS_OF) == []


def test_none_values_skipped() -> None:
    detector = LeakageDetector(strict=True)
    findings = detector.check({"published_date": None}, AS_OF)
    assert findings == []


def test_non_date_keys_ignored() -> None:
    """Free-text fields containing date-like substrings must not trigger."""
    detector = LeakageDetector(strict=True)
    payload = {
        "ticker": "AAPL",
        "name": "Apple Inc 2099-01-01 Memorial Edition",
        "description": "Released 2099 — definitely future-dated wording",
        "summary": "2099-12-31 something something",
    }
    assert detector.check(payload, AS_OF) == []


# ---------------------------------------------------------------------------
# Future-date detection
# ---------------------------------------------------------------------------


def test_strict_mode_raises_on_first_future_date() -> None:
    detector = LeakageDetector(strict=True)
    payload = {"published_date": "2099-01-01"}
    with pytest.raises(LeakageError) as excinfo:
        detector.check(payload, AS_OF)

    err = excinfo.value
    assert hasattr(err, "findings")
    assert len(err.findings) == 1
    finding = err.findings[0]
    assert isinstance(finding, LeakageFinding)
    assert finding.kind == "future_date"
    assert finding.field_name == "published_date"
    assert finding.value == "2099-01-01"
    assert finding.path == "<root>.published_date"


def test_lenient_mode_collects_all_findings() -> None:
    detector = LeakageDetector(strict=False)
    payload = {
        "filing_date": "2099-01-01",
        "news_items": [
            {"published_date": "2099-02-01"},
            {"published_date": "2099-03-01"},
        ],
    }
    findings = detector.check(payload, AS_OF)
    assert len(findings) == 3
    # All future_date kind.
    assert all(f.kind == "future_date" for f in findings)
    # Paths should be distinct.
    paths = {f.path for f in findings}
    assert paths == {
        "<root>.filing_date",
        "<root>.news_items[0].published_date",
        "<root>.news_items[1].published_date",
    }


def test_recursion_into_lists_and_dicts() -> None:
    detector = LeakageDetector(strict=False)
    payload = {
        "news_items": [
            {"published_date": "2099-01-01"},
            {"published_date": "2020-01-01"},
        ]
    }
    findings = detector.check(payload, AS_OF)
    assert len(findings) == 1
    assert findings[0].path == "<root>.news_items[0].published_date"
    assert findings[0].kind == "future_date"


def test_field_suffix_matching_case_insensitive() -> None:
    detector = LeakageDetector(strict=False)
    payload = {
        "published_DATE": "2099-01-01",
        "Filing_Date": "2099-02-01",
        "period_end_DATETIME": "2099-03-01T12:00:00",
    }
    findings = detector.check(payload, AS_OF)
    assert len(findings) == 3
    fields = {f.field_name for f in findings}
    assert fields == {"published_DATE", "Filing_Date", "period_end_DATETIME"}


def test_deeply_nested_payload() -> None:
    detector = LeakageDetector(strict=False)
    payload = {
        "level1": {
            "level2": {
                "level3": [
                    {"items": [{"published_date": "2099-01-01"}]},
                ],
            },
        },
    }
    findings = detector.check(payload, AS_OF)
    assert len(findings) == 1
    assert (
        findings[0].path
        == "<root>.level1.level2.level3[0].items[0].published_date"
    )


# ---------------------------------------------------------------------------
# Unparseable / malformed values
# ---------------------------------------------------------------------------


def test_unparseable_date_field_recorded() -> None:
    detector = LeakageDetector(strict=False)
    payload = {"published_date": "yesterday"}
    findings = detector.check(payload, AS_OF)
    assert len(findings) == 1
    assert findings[0].kind == "unparseable"
    assert findings[0].value == "yesterday"
    assert findings[0].field_name == "published_date"


def test_non_string_in_date_field_recorded_as_unparseable() -> None:
    detector = LeakageDetector(strict=False)
    payload = {"published_date": 12345}
    findings = detector.check(payload, AS_OF)
    assert len(findings) == 1
    assert findings[0].kind == "unparseable"


def test_strict_unparseable_raises() -> None:
    detector = LeakageDetector(strict=True)
    payload = {"published_date": "not-a-date"}
    with pytest.raises(LeakageError) as excinfo:
        detector.check(payload, AS_OF)
    assert excinfo.value.findings[0].kind == "unparseable"


# ---------------------------------------------------------------------------
# Datetime + timezone handling
# ---------------------------------------------------------------------------


def test_datetime_iso_with_offset_handled() -> None:
    detector = LeakageDetector(strict=False)
    payload = {"published_datetime": "2025-04-15T12:00:00+09:00"}
    findings = detector.check(payload, AS_OF)
    assert len(findings) == 1
    assert findings[0].kind == "future_datetime"


def test_datetime_naive_iso_handled() -> None:
    detector = LeakageDetector(strict=False)
    payload = {"published_datetime": "2099-04-15T12:00:00"}
    findings = detector.check(payload, AS_OF)
    assert len(findings) == 1
    assert findings[0].kind == "future_datetime"


def test_datetime_at_or_before_as_of_no_finding() -> None:
    detector = LeakageDetector(strict=False)
    payload = {
        "published_datetime": "2025-04-14T23:59:59",
        "earlier_datetime": "2020-01-01T00:00:00",
    }
    findings = detector.check(payload, AS_OF)
    assert findings == []


# ---------------------------------------------------------------------------
# Source label
# ---------------------------------------------------------------------------


def test_source_label_used_in_path() -> None:
    detector = LeakageDetector(strict=False)
    payload = {"published_date": "2099-01-01"}
    findings = detector.check(payload, AS_OF, source_label="tier2-raw.json")
    assert len(findings) == 1
    assert findings[0].path == "tier2-raw.json.published_date"


def test_source_label_default_is_root() -> None:
    detector = LeakageDetector(strict=False)
    payload = {"published_date": "2099-01-01"}
    findings = detector.check(payload, AS_OF)
    assert findings[0].path.startswith("<root>")


# ---------------------------------------------------------------------------
# LeakageError ergonomics
# ---------------------------------------------------------------------------


def test_findings_attached_to_leakage_error() -> None:
    detector = LeakageDetector(strict=True)
    payload = {"published_date": "2099-01-01"}
    with pytest.raises(LeakageError) as excinfo:
        detector.check(payload, AS_OF)

    err = excinfo.value
    assert isinstance(err.findings, list)
    assert len(err.findings) == 1
    # str(err) should mention the path and kind so a human can debug.
    msg = str(err)
    assert "published_date" in msg
    assert "future_date" in msg


# ---------------------------------------------------------------------------
# Top-level non-container payloads
# ---------------------------------------------------------------------------


def test_top_level_scalar_no_crash() -> None:
    """A non-container payload at the top level shouldn't crash the walker."""
    detector = LeakageDetector(strict=False)
    assert detector.check("a string", AS_OF) == []
    assert detector.check(42, AS_OF) == []
    assert detector.check(None, AS_OF) == []
