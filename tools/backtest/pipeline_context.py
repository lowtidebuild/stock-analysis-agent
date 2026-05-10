"""Backtest pipeline context for as-of date injection.

A ``BacktestContext`` carries the three coordinates that scope a single
backtest pipeline run:

- ``cohort_id``  — manifest grouping (e.g. ``"2025Q1"``),
- ``ticker``    — symbol under analysis (e.g. ``"AAPL"``),
- ``as_of``     — historical pipeline date (no future leakage).

It also tracks ``started_at`` (UTC, when the run kicked off) and a
``freeze_strategy`` flag (default ``"hybrid"`` per BT-D1 in the backtest
plan: snapshot price/financial inputs but allow news to flow with as-of
filtering).

Why a dedicated dataclass:

- The production pipeline integration happens in Chunk 3 via the cohort
  runner — wiring this through ``.claude/skills/data-manager`` happens
  there. For Task 1.2 we keep the backtest scaffolding cleanly isolated
  in ``tools/backtest/`` so unit tests stay fast and focused.
- ``run_id`` and ``artifact_root`` give callers a single source of truth
  for where backtest artifacts live (``backtest/cohorts/{cohort}/runs/
  {ticker}/``), honoring ``$STOCK_ANALYSIS_DATA_DIR`` via
  :func:`tools.paths.backtest_path`.
- ``write_meta`` persists a small ``_backtest-meta.json`` next to the
  artifacts so post-hoc inspection (eval harness, leakage detector) can
  reconstruct the exact as-of context for a given run.
"""

from __future__ import annotations

import datetime as _dt
import json
import pathlib
from dataclasses import dataclass, field

from tools.paths import backtest_path

_META_FILENAME = "_backtest-meta.json"
_DEFAULT_FREEZE_STRATEGY = "hybrid"


def _utcnow() -> _dt.datetime:
    """Return the current UTC time as a timezone-aware datetime."""
    return _dt.datetime.now(tz=_dt.UTC)


@dataclass(frozen=True)
class BacktestContext:
    """Immutable scope object for a single backtest pipeline run.

    Parameters
    ----------
    cohort_id:
        Cohort manifest identifier (e.g. ``"2025Q1"``, ``"smoke"``).
    ticker:
        Stock ticker under analysis (e.g. ``"AAPL"``, ``"005930"``).
    as_of:
        Historical date the pipeline should pretend "today" is.
    started_at:
        UTC timestamp when the run kicked off. Defaults to
        :func:`datetime.datetime.now` (UTC).
    freeze_strategy:
        Data-freezing policy. Defaults to ``"hybrid"`` (snapshot
        structured inputs, filter news by date — see BT-D1 in the
        backtest plan).
    """

    cohort_id: str
    ticker: str
    as_of: _dt.date
    started_at: _dt.datetime = field(default_factory=_utcnow)
    freeze_strategy: str = _DEFAULT_FREEZE_STRATEGY

    def __post_init__(self) -> None:
        if type(self.as_of) is not _dt.date:
            raise TypeError(
                "as_of must be datetime.date (not datetime); got "
                f"{type(self.as_of).__name__}"
            )
        if self.started_at.tzinfo is None:
            raise ValueError(
                "started_at must be timezone-aware (UTC). Naive datetimes "
                "would silently shift by the local offset during "
                "run_id generation."
            )

    def run_id(self) -> str:
        """Return a deterministic run id for this context.

        Format: ``{started_at:YYYYMMDDTHHMMSSZ}_{ticker}_backtest_
        {as_of:YYYY-MM-DD}``. The ``Z`` suffix on the timestamp marks
        UTC explicitly.
        """
        ts = self.started_at.astimezone(_dt.UTC).strftime("%Y%m%dT%H%M%SZ")
        return f"{ts}_{self.ticker}_backtest_{self.as_of.isoformat()}"

    def artifact_root(self) -> pathlib.Path:
        """Return the directory where this run's artifacts live.

        Resolves to ``backtest/cohorts/{cohort_id}/runs/{ticker}`` under
        the configured data directory. Honors
        ``$STOCK_ANALYSIS_DATA_DIR``.
        """
        return backtest_path("cohorts", self.cohort_id, "runs", self.ticker)

    def meta_path(self) -> pathlib.Path:
        """Return the path to this run's ``_backtest-meta.json``."""
        return self.artifact_root() / _META_FILENAME

    def write_meta(self) -> None:
        """Write ``_backtest-meta.json`` describing this context.

        Creates the artifact root directory if needed. Overwrites any
        existing meta file (idempotent — safe to call multiple times).
        Writes UTF-8 JSON with ``indent=2``, sorted keys, and a trailing
        newline.
        """
        root = self.artifact_root()
        root.mkdir(parents=True, exist_ok=True)

        payload = {
            "cohort_id": self.cohort_id,
            "ticker": self.ticker,
            "as_of": self.as_of.isoformat(),
            "started_at": self.started_at.isoformat(),
            "freeze_strategy": self.freeze_strategy,
            "run_id": self.run_id(),
        }
        text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        self.meta_path().write_text(text, encoding="utf-8")


__all__ = ["BacktestContext"]
