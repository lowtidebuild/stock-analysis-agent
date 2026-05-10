"""SEC EDGAR post-filter wrapper for backtest as-of mode.

The yfinance and FRED collectors live under our control, so we added a
``--as-of`` flag and built ``YFinanceHistorical`` / ``FredHistorical``
adapters that pre-fetch only historical data (Tasks 2.1 / 2.2). SEC
filings, income statements, balance sheets, and cash flow statements,
however, are fetched through the **Financial Datasets MCP** — a
third-party server we cannot extend with an as-of parameter.

This module solves the problem on the consumer side: the cohort runner
calls the MCP normally, then routes the raw response through these
**pure functions** before passing it downstream. Any record dated after
``as_of`` is dropped, and a ``_backtest_meta`` block plus a
``sec_post_filter_applied`` caveat are attached so the validator and
analyst can see that a temporal filter ran.

Design choices:

- **Pure functions, no class.** There is no per-call state worth
  holding. A class would be ceremony.
- **No mutation of input.** Every function returns a new dict / list.
  This mirrors the leakage-detector contract — the upstream MCP
  response stays available for diagnostics.
- **Record-level skip, not abort.** A single malformed record (missing
  date, ``None`` date, unparseable string) is recorded under
  ``_skipped_records`` and the rest of the list is processed. Callers
  that want hard failure can pass the records through
  :class:`HistoricalFilterError` themselves.
- **Generic over source.** Although the module is named after SEC, the
  same shape works for any "list of dated records" payload (e.g.
  KR DART filings if we choose a post-filter strategy there). The
  ``source`` keyword on :func:`annotate_backtest_meta` controls the
  caveat name (``f"{source}_post_filter_applied"``).

This module is invoked by the cohort runner / orchestrator (Chunk 3 of
the backtest harness plan). It is intentionally decoupled from
:class:`tools.backtest.pipeline_context.BacktestContext` and
:class:`tools.backtest.leakage_detector.LeakageDetector` so the same
helpers can be unit-tested against synthetic payloads.
"""

from __future__ import annotations

import copy
import datetime as _dt
from typing import Any

_FILINGS_KEY = "filings"
_FILINGS_DATE_FIELD = "filing_date"

_INCOME_KEY = "income_statements"
_BALANCE_KEY = "balance_sheets"
_CASHFLOW_KEY = "cash_flow_statements"
_PERIOD_DATE_FIELD = "period_end_date"

_FREEZE_STRATEGY = "hybrid"
_DEFAULT_SOURCE = "sec"


class HistoricalFilterError(ValueError):
    """Raised for malformed inputs to a post-filter helper.

    The pure functions in this module prefer record-level skipping over
    raising — a single bad record under ``_skipped_records`` should not
    abort an entire MCP response. This exception exists so callers
    (cohort runner, eval harness) that want hard failure can construct
    one themselves with the offending record attached for diagnostics.
    """

    def __init__(self, message: str, *, record: Any | None = None) -> None:
        self.record = record
        super().__init__(message)

    def __str__(self) -> str:  # pragma: no cover — diagnostic only
        base = super().__str__()
        if self.record is None:
            return base
        return f"{base} (record={self.record!r})"


# ---------------------------------------------------------------------------
# Public filter functions
# ---------------------------------------------------------------------------


def filter_sec_filings(payload: dict, as_of: _dt.date) -> dict:
    """Drop filings with ``filing_date > as_of``.

    Parameters
    ----------
    payload:
        MCP ``get_sec_filings`` response shape — a dict with a
        ``"filings"`` list. Each filing carries a ``"filing_date"``
        ISO date string.
    as_of:
        Backtest cutoff. A :class:`datetime.date`; passing
        :class:`datetime.datetime` raises :class:`TypeError`.

    Returns
    -------
    dict
        New dict (input is not mutated). All top-level keys other than
        ``filings`` are preserved. Records with malformed
        ``filing_date`` are recorded under ``_skipped_records``.
    """
    return _filter_list(
        payload,
        list_key=_FILINGS_KEY,
        date_field=_FILINGS_DATE_FIELD,
        as_of=as_of,
    )


def filter_income_statements(payload: dict, as_of: _dt.date) -> dict:
    """Drop income statements with ``period_end_date > as_of``."""
    return _filter_list(
        payload,
        list_key=_INCOME_KEY,
        date_field=_PERIOD_DATE_FIELD,
        as_of=as_of,
    )


def filter_balance_sheets(payload: dict, as_of: _dt.date) -> dict:
    """Drop balance sheets with ``period_end_date > as_of``."""
    return _filter_list(
        payload,
        list_key=_BALANCE_KEY,
        date_field=_PERIOD_DATE_FIELD,
        as_of=as_of,
    )


def filter_cash_flow_statements(payload: dict, as_of: _dt.date) -> dict:
    """Drop cash flow statements with ``period_end_date > as_of``."""
    return _filter_list(
        payload,
        list_key=_CASHFLOW_KEY,
        date_field=_PERIOD_DATE_FIELD,
        as_of=as_of,
    )


def select_latest_pre_as_of(
    records: list[dict],
    as_of: _dt.date,
    *,
    date_field: str = _PERIOD_DATE_FIELD,
) -> dict | None:
    """Return the record with the latest ``date_field <= as_of``.

    Parameters
    ----------
    records:
        List of dict records, each with ``date_field`` set to an ISO
        date string.
    as_of:
        Cutoff date (inclusive). Must be :class:`datetime.date`.
    date_field:
        Which field on each record carries the ISO date. Defaults to
        ``"period_end_date"`` so the function works directly on the
        statement helpers; callers handling SEC filings should pass
        ``date_field="filing_date"``.

    Returns
    -------
    dict | None
        The single most-recent qualifying record (deep-copied so callers
        cannot accidentally mutate the input list), or ``None`` when
        every record is dated after ``as_of`` (or the list is empty).
        Records with malformed dates are silently skipped — the caller
        is expected to have already run them through one of the
        ``filter_*`` helpers if it cares about diagnostics.
    """
    _require_date(as_of)

    best: dict | None = None
    best_date: _dt.date | None = None

    for record in records:
        if not isinstance(record, dict):
            continue
        parsed = _parse_record_date(record, date_field)
        if parsed is None:
            continue
        if parsed > as_of:
            continue
        if best_date is None or parsed > best_date:
            best = record
            best_date = parsed

    return copy.deepcopy(best) if best is not None else None


def annotate_backtest_meta(
    payload: dict,
    as_of: _dt.date,
    *,
    source: str = _DEFAULT_SOURCE,
) -> dict:
    """Attach a ``_backtest_meta`` block and post-filter caveat.

    Mirrors the convention used by ``yfinance-collector.py`` and
    ``fred-collector.py`` outputs: the caller can inspect
    ``_backtest_meta`` for ``as_of`` / ``freeze_strategy`` / ``source``
    and ``_backtest_caveats`` for a deduped list of caveat strings.

    Parameters
    ----------
    payload:
        Source payload. Not mutated; a deep copy of all preserved
        fields is returned.
    as_of:
        Backtest cutoff date (must be :class:`datetime.date`).
    source:
        Source label, used to build the caveat name
        (``f"{source}_post_filter_applied"``) and stored in
        ``_backtest_meta.source``. Defaults to ``"sec"``.

    Returns
    -------
    dict
        New dict carrying:

        - ``_backtest_meta``: ``{"as_of", "freeze_strategy", "caveats", "source"}``
        - ``_backtest_caveats``: deduped list of caveat strings,
          including any pre-existing entries plus the new
          ``f"{source}_post_filter_applied"``.
    """
    _require_date(as_of)

    out = copy.deepcopy(payload)
    caveat = f"{source}_post_filter_applied"

    existing = out.get("_backtest_caveats")
    if not isinstance(existing, list):
        existing = []
    new_caveats = list(existing)
    if caveat not in new_caveats:
        new_caveats.append(caveat)
    out["_backtest_caveats"] = new_caveats

    out["_backtest_meta"] = {
        "as_of": as_of.isoformat(),
        "freeze_strategy": _FREEZE_STRATEGY,
        "caveats": [caveat],
        "source": source,
    }
    return out


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _filter_list(
    payload: dict,
    *,
    list_key: str,
    date_field: str,
    as_of: _dt.date,
) -> dict:
    """Generic list-filter shared by all four ``filter_*`` helpers."""
    _require_date(as_of)

    if not isinstance(payload, dict):
        raise HistoricalFilterError(
            f"expected dict payload, got {type(payload).__name__}",
            record=payload,
        )

    raw_list = payload.get(list_key, [])
    if not isinstance(raw_list, list):
        raise HistoricalFilterError(
            f"payload[{list_key!r}] must be a list, got "
            f"{type(raw_list).__name__}",
            record=raw_list,
        )

    kept: list[dict] = []
    skipped: list[dict] = []

    for record in raw_list:
        if not isinstance(record, dict):
            skipped.append(
                {
                    "reason": "record is not a dict",
                    "record": copy.deepcopy(record),
                }
            )
            continue

        if date_field not in record:
            skipped.append(
                {
                    "reason": f"record missing {date_field!r} field",
                    "record": copy.deepcopy(record),
                }
            )
            continue

        raw_value = record.get(date_field)
        parsed = _try_parse_iso_date(raw_value)
        if parsed is None:
            skipped.append(
                {
                    "reason": (
                        f"could not parse {date_field}={raw_value!r} as "
                        f"ISO date"
                    ),
                    "record": copy.deepcopy(record),
                }
            )
            continue

        if parsed <= as_of:
            kept.append(copy.deepcopy(record))

    out = {k: copy.deepcopy(v) for k, v in payload.items() if k != list_key}
    out[list_key] = kept
    if skipped:
        # Preserve any pre-existing _skipped_records entries from upstream.
        prior = out.get("_skipped_records")
        if isinstance(prior, list):
            out["_skipped_records"] = list(prior) + skipped
        else:
            out["_skipped_records"] = skipped
    return out


def _parse_record_date(record: dict, date_field: str) -> _dt.date | None:
    """Best-effort date parse for a single record. ``None`` on failure."""
    return _try_parse_iso_date(record.get(date_field))


def _try_parse_iso_date(value: Any) -> _dt.date | None:
    """Parse ``value`` as an ISO date. Returns ``None`` on failure."""
    if not isinstance(value, str):
        return None
    try:
        return _dt.date.fromisoformat(value)
    except ValueError:
        # Tolerate ISO datetime strings (e.g. "2024-06-30T00:00:00").
        try:
            return _dt.datetime.fromisoformat(value).date()
        except ValueError:
            return None


def _require_date(as_of: Any) -> None:
    """Reject ``datetime.datetime`` (and other non-date values).

    The ``date`` / ``datetime`` distinction matters — passing a
    ``datetime`` would silently pull in a tz-aware comparison and could
    let an "end-of-day" timestamp leak past the boundary.
    """
    if type(as_of) is not _dt.date:
        raise TypeError(
            f"as_of must be datetime.date (not {type(as_of).__name__}); "
            "datetime.datetime is rejected to avoid tz / EOD ambiguity."
        )


__all__ = [
    "HistoricalFilterError",
    "annotate_backtest_meta",
    "filter_balance_sheets",
    "filter_cash_flow_statements",
    "filter_income_statements",
    "filter_sec_filings",
    "select_latest_pre_as_of",
]
