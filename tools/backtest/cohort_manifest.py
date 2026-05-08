"""Cohort manifest schema for the backtest harness.

A *cohort* is a group of tickers evaluated against a single historical
``as_of`` anchor. The manifest is a JSON file at
``evals/backtest/cohorts/{cohort_id}.json`` and drives
``tools/backtest_runner.py --cohort {id}`` (Task 3.2 wires the runner).

This module deliberately avoids any third-party dependency (no
``pydantic``) — the rest of ``tools/`` already validates with stdlib
dataclasses, and the manifest schema is small enough that hand-rolled
validation is clearer than a heavy framework.

Schema overview
---------------

::

    {
      "cohort_id": "2025Q1",
      "as_of": "2025-03-31",
      "tickers": [
        {"ticker": "AAPL", "market": "US", "notes": "S&P 500 mega-cap"},
        ...
      ],
      "benchmark": "MIXED",            // SPY | QQQ | KOSPI | MIXED
      "mode": "C",                       // only Mode C in Phase 1 (BT-D4)
      "run_count": 1,                    // 1 or 3 per BT-D5
      "cost_cap_usd": 50.0,              // total cohort budget
      "notes": "30-name S&P sample"
    }

Validation rules (raise ``CohortManifestError`` on violation):

1. ``cohort_id`` matches ``[A-Za-z0-9_-]{1,32}``.
2. ``as_of`` is exactly :class:`datetime.date` (not ``datetime``) and is
   not in the future.
3. ``tickers`` is non-empty; each entry has a non-empty ``ticker`` and a
   ``market`` ∈ {``US``, ``KR``}; no duplicate tickers (case-sensitive).
4. ``benchmark`` ∈ {``SPY``, ``QQQ``, ``KOSPI``, ``MIXED``}.
5. ``mode`` ∈ {``C``}.
6. ``run_count`` ∈ {1, 3}.
7. ``cost_cap_usd`` > 0.

Path safety
-----------

``cohort_manifest_path`` validates the ``cohort_id`` *before* path
construction, so traversal payloads like ``"../etc/passwd"`` raise
``CohortManifestError`` rather than escaping the cohorts directory.
"""

from __future__ import annotations

import datetime as _dt
import json
import pathlib
import re
from dataclasses import dataclass
from typing import Any, Literal

from tools.paths import REPO_ROOT

__all__ = [
    "TickerEntry",
    "CohortManifest",
    "CohortManifestError",
    "load_cohort",
    "cohort_manifest_path",
    "to_json",
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_COHORT_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,32}")
_VALID_MARKETS: frozenset[str] = frozenset({"US", "KR"})
_VALID_BENCHMARKS: frozenset[str] = frozenset({"SPY", "QQQ", "KOSPI", "MIXED"})
_VALID_MODES: frozenset[str] = frozenset({"C"})
_VALID_RUN_COUNTS: frozenset[int] = frozenset({1, 3})

_COHORTS_SUBDIR = ("evals", "backtest", "cohorts")


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class CohortManifestError(ValueError):
    """Raised when a cohort manifest fails schema validation or load."""


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TickerEntry:
    """A single ticker entry in a cohort manifest.

    Parameters
    ----------
    ticker:
        Stock symbol (e.g. ``"AAPL"``, ``"005930"``). Must be non-empty.
    market:
        Either ``"US"`` (NYSE/NASDAQ/AMEX) or ``"KR"`` (KRX/KOSPI/KOSDAQ).
    notes:
        Optional free-text annotation. Defaults to ``""``.
    """

    ticker: str
    market: Literal["US", "KR"]
    notes: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.ticker, str) or not self.ticker.strip():
            raise CohortManifestError(
                f"ticker must be a non-empty string; got {self.ticker!r}"
            )
        if self.market not in _VALID_MARKETS:
            raise CohortManifestError(
                f"market must be one of {sorted(_VALID_MARKETS)}; got {self.market!r}"
            )


@dataclass(frozen=True)
class CohortManifest:
    """Frozen value object describing a backtest cohort.

    Parameters
    ----------
    cohort_id:
        Short identifier matching ``[A-Za-z0-9_-]{1,32}`` (e.g.
        ``"2025Q1"``, ``"smoke"``).
    as_of:
        Historical anchor date. Must be :class:`datetime.date` (not
        ``datetime``) and not in the future.
    tickers:
        Non-empty tuple of :class:`TickerEntry`. Tickers must be unique
        (case-sensitive).
    benchmark:
        One of ``SPY`` | ``QQQ`` | ``KOSPI`` | ``MIXED``. ``MIXED``
        means the runner picks per ticker (KR→KOSPI, US→SPY).
    mode:
        Output mode. Phase 1 only ships Mode C (per BT-D4).
    run_count:
        How many runs per ticker (1 in Phase 1, 3 to measure variance —
        see BT-D5). Defaults to 1.
    cost_cap_usd:
        Total cohort cost cap. Must be > 0. Defaults to 50.0.
    notes:
        Optional free-text manifest-level annotation.
    """

    cohort_id: str
    as_of: _dt.date
    tickers: tuple[TickerEntry, ...]
    benchmark: Literal["SPY", "QQQ", "KOSPI", "MIXED"] = "MIXED"
    mode: Literal["C"] = "C"
    run_count: Literal[1, 3] = 1
    cost_cap_usd: float = 50.0
    notes: str = ""

    def __post_init__(self) -> None:
        # cohort_id
        if not isinstance(self.cohort_id, str) or not _COHORT_ID_PATTERN.fullmatch(
            self.cohort_id
        ):
            raise CohortManifestError(
                "cohort_id must match [A-Za-z0-9_-]{1,32}; "
                f"got {self.cohort_id!r}"
            )

        # as_of: exact date type (not datetime), not future
        if type(self.as_of) is not _dt.date:
            raise CohortManifestError(
                "as_of must be datetime.date (not datetime); got "
                f"{type(self.as_of).__name__}"
            )
        if self.as_of > _dt.date.today():
            raise CohortManifestError(
                f"as_of must not be in the future; got {self.as_of.isoformat()}"
            )

        # tickers
        if not isinstance(self.tickers, tuple):
            raise CohortManifestError(
                f"tickers must be a tuple of TickerEntry; got {type(self.tickers).__name__}"
            )
        if len(self.tickers) == 0:
            raise CohortManifestError("tickers must contain at least one entry")
        for entry in self.tickers:
            if not isinstance(entry, TickerEntry):
                raise CohortManifestError(
                    f"tickers entries must be TickerEntry; got {type(entry).__name__}"
                )
        seen: set[str] = set()
        for entry in self.tickers:
            if entry.ticker in seen:
                raise CohortManifestError(
                    f"duplicate ticker in cohort: {entry.ticker!r}"
                )
            seen.add(entry.ticker)

        # benchmark
        if self.benchmark not in _VALID_BENCHMARKS:
            raise CohortManifestError(
                f"benchmark must be one of {sorted(_VALID_BENCHMARKS)}; "
                f"got {self.benchmark!r}"
            )

        # mode
        if self.mode not in _VALID_MODES:
            raise CohortManifestError(
                f"mode must be one of {sorted(_VALID_MODES)}; got {self.mode!r}"
            )

        # run_count
        if self.run_count not in _VALID_RUN_COUNTS:
            raise CohortManifestError(
                f"run_count must be one of {sorted(_VALID_RUN_COUNTS)}; "
                f"got {self.run_count!r}"
            )

        # cost_cap_usd
        if not isinstance(self.cost_cap_usd, (int, float)) or self.cost_cap_usd <= 0:
            raise CohortManifestError(
                f"cost_cap_usd must be > 0; got {self.cost_cap_usd!r}"
            )


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def cohort_manifest_path(cohort_id: str) -> pathlib.Path:
    """Resolve the on-disk path for a cohort manifest.

    Validates ``cohort_id`` before path construction so that traversal
    payloads (``../foo``, ``a/b``) cannot escape the cohorts directory.

    Parameters
    ----------
    cohort_id:
        Cohort identifier matching ``[A-Za-z0-9_-]{1,32}``.

    Returns
    -------
    pathlib.Path
        ``<repo>/evals/backtest/cohorts/{cohort_id}.json`` (no I/O).

    Raises
    ------
    CohortManifestError
        If ``cohort_id`` is not a valid identifier.
    """
    if not isinstance(cohort_id, str) or not _COHORT_ID_PATTERN.fullmatch(cohort_id):
        raise CohortManifestError(
            "cohort_id must match [A-Za-z0-9_-]{1,32}; "
            f"got {cohort_id!r}"
        )
    return REPO_ROOT.joinpath(*_COHORTS_SUBDIR, f"{cohort_id}.json")


def _parse_as_of(raw: Any) -> _dt.date:
    if not isinstance(raw, str):
        raise CohortManifestError(
            f"as_of must be an ISO-8601 date string; got {type(raw).__name__}"
        )
    try:
        parsed = _dt.date.fromisoformat(raw)
    except ValueError as exc:
        raise CohortManifestError(
            f"as_of is not a valid ISO-8601 date: {raw!r} ({exc})"
        ) from exc
    return parsed


def _parse_tickers(raw: Any) -> tuple[TickerEntry, ...]:
    if not isinstance(raw, list):
        raise CohortManifestError(
            f"tickers must be a JSON array; got {type(raw).__name__}"
        )
    entries: list[TickerEntry] = []
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            raise CohortManifestError(
                f"tickers[{idx}] must be a JSON object; got {type(item).__name__}"
            )
        ticker = item.get("ticker")
        market = item.get("market")
        notes = item.get("notes", "")
        if ticker is None:
            raise CohortManifestError(f"tickers[{idx}].ticker is required")
        if market is None:
            raise CohortManifestError(f"tickers[{idx}].market is required")
        try:
            entries.append(TickerEntry(ticker=ticker, market=market, notes=notes))
        except CohortManifestError as exc:
            raise CohortManifestError(f"tickers[{idx}]: {exc}") from exc
    return tuple(entries)


def load_cohort(path: pathlib.Path) -> CohortManifest:
    """Load and validate a cohort manifest from disk.

    Parameters
    ----------
    path:
        Path to a JSON file conforming to the cohort manifest schema.

    Returns
    -------
    CohortManifest
        Fully validated, frozen manifest.

    Raises
    ------
    CohortManifestError
        On any I/O error, malformed JSON, missing required field, or
        schema-validation failure.
    """
    if not path.exists():
        raise CohortManifestError(f"cohort manifest not found: {path}")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CohortManifestError(f"cannot read cohort manifest {path}: {exc}") from exc

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CohortManifestError(
            f"malformed JSON in {path}: {exc}"
        ) from exc

    if not isinstance(payload, dict):
        raise CohortManifestError(
            f"cohort manifest root must be a JSON object; got {type(payload).__name__}"
        )

    required = ("cohort_id", "as_of", "tickers")
    for key in required:
        if key not in payload:
            raise CohortManifestError(
                f"cohort manifest is missing required field {key!r} (in {path})"
            )

    cohort_id = payload["cohort_id"]
    as_of = _parse_as_of(payload["as_of"])
    tickers = _parse_tickers(payload["tickers"])
    benchmark = payload.get("benchmark", "MIXED")
    mode = payload.get("mode", "C")
    run_count = payload.get("run_count", 1)
    cost_cap_usd = payload.get("cost_cap_usd", 50.0)
    notes = payload.get("notes", "")

    return CohortManifest(
        cohort_id=cohort_id,
        as_of=as_of,
        tickers=tickers,
        benchmark=benchmark,
        mode=mode,
        run_count=run_count,
        cost_cap_usd=cost_cap_usd,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def to_json(manifest: CohortManifest) -> str:
    """Serialize a manifest to JSON text.

    Output is pretty-printed (``indent=2``), sorted by key, and ends in
    a single trailing newline. ``load_cohort(write(to_json(m))) == m``
    holds.

    Parameters
    ----------
    manifest:
        Validated cohort manifest.

    Returns
    -------
    str
        UTF-8 JSON text suitable for writing to a manifest file.
    """
    payload: dict[str, Any] = {
        "cohort_id": manifest.cohort_id,
        "as_of": manifest.as_of.isoformat(),
        "tickers": [
            {
                "ticker": entry.ticker,
                "market": entry.market,
                "notes": entry.notes,
            }
            for entry in manifest.tickers
        ],
        "benchmark": manifest.benchmark,
        "mode": manifest.mode,
        "run_count": manifest.run_count,
        "cost_cap_usd": manifest.cost_cap_usd,
        "notes": manifest.notes,
    }
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"
