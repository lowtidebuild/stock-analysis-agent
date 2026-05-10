"""Tests for tools.backtest.sec_historical post-filter helpers.

Covers Task 2.3 of the backtest harness plan
(``docs/superpowers/plans/2026-05-08-backtest-harness.md``).

SEC EDGAR data flows through the Financial Datasets MCP, which we cannot
parameterize with ``--as-of``. Instead this module post-filters raw MCP
responses: any record dated after the as-of date is dropped, and a
``_backtest_meta`` block plus a ``sec_post_filter_applied`` caveat are
attached so downstream consumers can see the filter ran.

Run via: ``python -m pytest tests/backtest/test_sec_historical.py -v``
"""

from __future__ import annotations

import copy
import datetime as _dt
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.backtest.sec_historical import (  # noqa: E402
    HistoricalFilterError,
    annotate_backtest_meta,
    filter_balance_sheets,
    filter_cash_flow_statements,
    filter_income_statements,
    filter_sec_filings,
    select_latest_pre_as_of,
)

AS_OF = _dt.date(2024, 6, 30)


# ---------------------------------------------------------------------------
# filter_sec_filings
# ---------------------------------------------------------------------------


def test_filter_sec_filings_keeps_only_pre_as_of() -> None:
    payload = {
        "filings": [
            {"filing_date": "2024-01-15", "type": "10-K"},
            {"filing_date": "2024-06-30", "type": "10-Q"},
            {"filing_date": "2025-01-15", "type": "10-K"},
        ],
    }

    result = filter_sec_filings(payload, AS_OF)

    assert len(result["filings"]) == 2
    kept_dates = {f["filing_date"] for f in result["filings"]}
    assert kept_dates == {"2024-01-15", "2024-06-30"}


def test_filter_sec_filings_does_not_mutate_input() -> None:
    payload = {
        "filings": [
            {"filing_date": "2024-01-15", "type": "10-K"},
            {"filing_date": "2025-01-15", "type": "10-K"},
        ],
    }
    snapshot = copy.deepcopy(payload)

    filter_sec_filings(payload, AS_OF)

    assert payload == snapshot


def test_filter_sec_filings_preserves_other_top_level_keys() -> None:
    payload = {
        "ticker": "AAPL",
        "filings": [
            {"filing_date": "2024-01-15", "type": "10-K"},
        ],
    }

    result = filter_sec_filings(payload, AS_OF)

    assert result["ticker"] == "AAPL"
    assert "filings" in result


# ---------------------------------------------------------------------------
# filter_income_statements / balance_sheets / cash_flow_statements
# ---------------------------------------------------------------------------


def test_filter_income_statements_by_period_end() -> None:
    payload = {
        "income_statements": [
            {"period_end_date": "2023-12-31", "revenue": 100},
            {"period_end_date": "2024-03-31", "revenue": 110},
            {"period_end_date": "2024-06-30", "revenue": 120},
        ],
    }
    cutoff = _dt.date(2024, 4, 30)

    result = filter_income_statements(payload, cutoff)

    assert len(result["income_statements"]) == 2
    kept = {s["period_end_date"] for s in result["income_statements"]}
    assert kept == {"2023-12-31", "2024-03-31"}


def test_filter_balance_sheets_by_period_end() -> None:
    payload = {
        "balance_sheets": [
            {"period_end_date": "2023-12-31", "assets": 1000},
            {"period_end_date": "2024-03-31", "assets": 1100},
            {"period_end_date": "2024-06-30", "assets": 1200},
        ],
    }
    cutoff = _dt.date(2024, 4, 30)

    result = filter_balance_sheets(payload, cutoff)

    assert len(result["balance_sheets"]) == 2
    kept = {s["period_end_date"] for s in result["balance_sheets"]}
    assert kept == {"2023-12-31", "2024-03-31"}


def test_filter_cash_flow_statements_by_period_end() -> None:
    payload = {
        "cash_flow_statements": [
            {"period_end_date": "2023-12-31", "ocf": 50},
            {"period_end_date": "2024-03-31", "ocf": 55},
            {"period_end_date": "2024-06-30", "ocf": 60},
        ],
    }
    cutoff = _dt.date(2024, 4, 30)

    result = filter_cash_flow_statements(payload, cutoff)

    assert len(result["cash_flow_statements"]) == 2
    kept = {s["period_end_date"] for s in result["cash_flow_statements"]}
    assert kept == {"2023-12-31", "2024-03-31"}


# ---------------------------------------------------------------------------
# select_latest_pre_as_of
# ---------------------------------------------------------------------------


def test_select_latest_pre_as_of_returns_most_recent() -> None:
    records = [
        {"period_end_date": "2023-12-31", "revenue": 100},
        {"period_end_date": "2024-03-31", "revenue": 110},
        {"period_end_date": "2024-06-30", "revenue": 120},
    ]
    cutoff = _dt.date(2024, 4, 30)

    result = select_latest_pre_as_of(records, cutoff)

    assert result is not None
    assert result["period_end_date"] == "2024-03-31"


def test_select_latest_pre_as_of_returns_none_when_all_future() -> None:
    records = [
        {"period_end_date": "2024-03-31"},
        {"period_end_date": "2024-06-30"},
    ]
    cutoff = _dt.date(2023, 12, 31)

    result = select_latest_pre_as_of(records, cutoff)

    assert result is None


def test_select_latest_pre_as_of_custom_date_field() -> None:
    records = [
        {"filing_date": "2024-01-15", "type": "10-K"},
        {"filing_date": "2024-06-30", "type": "10-Q"},
        {"filing_date": "2025-01-15", "type": "10-K"},
    ]
    cutoff = _dt.date(2024, 7, 1)

    result = select_latest_pre_as_of(records, cutoff, date_field="filing_date")

    assert result is not None
    assert result["filing_date"] == "2024-06-30"


# ---------------------------------------------------------------------------
# annotate_backtest_meta
# ---------------------------------------------------------------------------


def test_annotate_backtest_meta_adds_block() -> None:
    payload: dict = {}

    result = annotate_backtest_meta(payload, AS_OF)

    assert result["_backtest_meta"]["as_of"] == "2024-06-30"
    assert result["_backtest_meta"]["freeze_strategy"] == "hybrid"
    assert result["_backtest_meta"]["source"] == "sec"
    assert result["_backtest_meta"]["caveats"] == ["sec_post_filter_applied"]
    assert "sec_post_filter_applied" in result["_backtest_caveats"]


def test_annotate_backtest_meta_preserves_existing_caveats() -> None:
    payload = {"_backtest_caveats": ["foo"]}

    result = annotate_backtest_meta(payload, AS_OF)

    assert result["_backtest_caveats"] == ["foo", "sec_post_filter_applied"]
    # Idempotent: applying twice does not duplicate the caveat.
    again = annotate_backtest_meta(result, AS_OF)
    assert again["_backtest_caveats"].count("sec_post_filter_applied") == 1


def test_annotate_backtest_meta_custom_source() -> None:
    payload: dict = {}

    result = annotate_backtest_meta(payload, AS_OF, source="dart")

    assert result["_backtest_meta"]["source"] == "dart"
    assert "dart_post_filter_applied" in result["_backtest_caveats"]
    assert result["_backtest_meta"]["caveats"] == ["dart_post_filter_applied"]


def test_annotate_backtest_meta_does_not_mutate_input() -> None:
    payload = {"_backtest_caveats": ["foo"]}
    snapshot = copy.deepcopy(payload)

    annotate_backtest_meta(payload, AS_OF)

    assert payload == snapshot


# ---------------------------------------------------------------------------
# Malformed / edge cases
# ---------------------------------------------------------------------------


def test_filter_records_with_malformed_dates_skipped() -> None:
    payload = {
        "income_statements": [
            {"period_end_date": "2023-12-31", "revenue": 100},
            {"period_end_date": None, "revenue": 0},
            {"period_end_date": "2024-03-31", "revenue": 110},
        ],
    }
    cutoff = _dt.date(2024, 4, 30)

    result = filter_income_statements(payload, cutoff)

    # Two valid records kept (the null-date row is skipped, not dropped silently).
    assert len(result["income_statements"]) == 2
    kept = {s["period_end_date"] for s in result["income_statements"]}
    assert kept == {"2023-12-31", "2024-03-31"}

    # The skipped record is recorded for caller-side debugging.
    assert "_skipped_records" in result
    assert len(result["_skipped_records"]) == 1
    skipped = result["_skipped_records"][0]
    assert "reason" in skipped
    assert skipped["reason"]  # non-empty
    assert skipped["record"]["revenue"] == 0


def test_filter_records_with_missing_date_field_skipped() -> None:
    payload = {
        "filings": [
            {"filing_date": "2024-01-15", "type": "10-K"},
            {"type": "10-Q"},  # missing filing_date entirely
        ],
    }

    result = filter_sec_filings(payload, AS_OF)

    assert len(result["filings"]) == 1
    assert result["filings"][0]["filing_date"] == "2024-01-15"
    assert len(result["_skipped_records"]) == 1


def test_datetime_as_of_rejected() -> None:
    payload = {"filings": []}
    bad_as_of = _dt.datetime(2024, 6, 30, 12, 0, 0)

    with pytest.raises(TypeError):
        filter_sec_filings(payload, bad_as_of)  # type: ignore[arg-type]

    with pytest.raises(TypeError):
        filter_income_statements(payload, bad_as_of)  # type: ignore[arg-type]

    with pytest.raises(TypeError):
        filter_balance_sheets(payload, bad_as_of)  # type: ignore[arg-type]

    with pytest.raises(TypeError):
        filter_cash_flow_statements(payload, bad_as_of)  # type: ignore[arg-type]

    with pytest.raises(TypeError):
        select_latest_pre_as_of([], bad_as_of)  # type: ignore[arg-type]

    with pytest.raises(TypeError):
        annotate_backtest_meta({}, bad_as_of)  # type: ignore[arg-type]


def test_empty_input_handled() -> None:
    # Empty filings list — no crash, empty output.
    result = filter_sec_filings({"filings": []}, AS_OF)
    assert result["filings"] == []

    # Empty income statements.
    result = filter_income_statements({"income_statements": []}, AS_OF)
    assert result["income_statements"] == []

    # Empty record list to selector.
    assert select_latest_pre_as_of([], AS_OF) is None


def test_historical_filter_error_includes_record() -> None:
    # The exception type exists and stringifies usefully when invoked
    # directly by callers (e.g. cohort runner that wants to fail loud
    # rather than skip).
    bad_record = {"period_end_date": "not-a-date", "revenue": 1}
    err = HistoricalFilterError(
        "could not parse date", record=bad_record
    )
    assert "not-a-date" in str(err) or "could not parse date" in str(err)
    assert err.record == bad_record


# ---------------------------------------------------------------------------
# Mutation-safety regressions for the deep-copy contract
# ---------------------------------------------------------------------------


def test_skipped_records_are_independent_of_input() -> None:
    """Mutating a record inside _skipped_records must not touch the
    caller's payload. Filters that share references on the skip path
    silently leak mutations through the cohort runner."""
    original = {
        "filings": [
            {"filing_date": None, "type": "10-K", "nested": {"value": 1}},
        ],
    }
    snapshot = copy.deepcopy(original)
    result = filter_sec_filings(original, AS_OF)
    assert "_skipped_records" in result
    skipped_record = result["_skipped_records"][0]["record"]
    skipped_record["nested"]["value"] = 999
    skipped_record["mutated"] = True
    assert original == snapshot, (
        "filter_sec_filings leaked a mutation through _skipped_records"
    )


def test_select_latest_pre_as_of_returns_independent_copy() -> None:
    """Mutating the returned dict must not touch the caller's input
    list. Otherwise the selector's return contract diverges from the
    filter_* helpers (which already deep-copy)."""
    records = [
        {"period_end_date": "2024-01-15", "nested": {"value": 1}},
        {"period_end_date": "2024-03-31", "nested": {"value": 2}},
    ]
    snapshot = copy.deepcopy(records)
    selected = select_latest_pre_as_of(records, AS_OF)
    assert selected is not None
    selected["nested"]["value"] = 999
    selected["new_key"] = "added"
    assert records == snapshot, (
        "select_latest_pre_as_of returned a shared reference"
    )
