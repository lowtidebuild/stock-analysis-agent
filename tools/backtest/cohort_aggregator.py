"""Cohort aggregator for the backtest harness.

Task 4.3 of the backtest plan
(``docs/superpowers/plans/2026-05-08-backtest-harness.md``).

Walks a cohort's per-ticker run directories, joins each ticker's
``_outcome.json`` (Task 4.2) with its ``analysis-result.json`` (produced
by the production Mode C analyst — wired up in Chunk 6, expected to be
**absent** for many Phase 1 rows), and emits a single ``results.jsonl``
at the cohort root with one row per ticker. Chunk 5's eval notebook
reads that file directly.

JOIN semantics
--------------

The join is ticker-level: one row per ``runs/{ticker}`` subdirectory.

- Both files present → all 16+ row fields populated, both
  ``analysis_present`` and ``outcome_present`` are ``True``.
- Outcome only → analysis fields are ``None``, ``analysis_present=False``.
- Analysis only → outcome fields are ``None``,
  ``outcome_present=False``, ``benchmark`` is ``None``.
- Neither → row is *not* emitted by :func:`aggregate_cohort` unless the
  ticker can still be anchored via ``_backtest-meta.json`` or the cohort
  manifest. Fully-empty subdirs (no meta, no outcome, no analysis) are
  skipped because there is no reliable ``as_of`` to attach.

Per-horizon outcome gaps
------------------------

The outcome computer marks individual horizons as
``_status="data_unavailable"`` when a forward close cannot be found
within the lookahead window. Those horizons are emitted with
``return_*`` and ``excess_*`` set to ``None`` and recorded in
``CohortRow.outcome_status`` as ``{horizon: "data_unavailable"}``. A
clean outcome (all 4 horizons OK) leaves ``outcome_status`` empty.

Best-effort analysis schema mapping
-----------------------------------

The production Mode C analyst output (``analysis-result.json``) does
not yet have a frozen schema for backtest consumption. This module
makes a *best-effort* mapping for the small set of fields the eval
notebook needs:

- ``verdict``: tries (in order)
    - ``analysis["verdict"]`` if it is a string,
    - ``analysis["verdict"]["label"]`` if it is a dict.
- ``rr_score``: tries
    - ``analysis["rr_score"]`` if it is a number,
    - ``analysis["rr_score"]["value"]`` if it is a dict.
- ``target_{base,bull,bear}``: tries (first hit wins)
    1. ``analysis["valuation"]["target_price"][{base,bull,bear}]``
    2. ``analysis["targets"][{base,bull,bear}]``
    3. ``analysis["scenarios"][{base,bull,bear}]["target"]`` —
       matches the schema observed in production Mode C runs
       (e.g. ``output/data/GOOGL/snapshots/.../analysis-result.json``).
    4. ``analysis["target_{base,bull,bear}"]``

All lookups use defensive nested gets and silently fall back to ``None``
on missing fields. Chunk 6 will refine the mapping once the analyst's
backtest schema is locked.

Output schema (one JSON object per JSONL line)
----------------------------------------------

::

    {
      "ticker": "AAPL",
      "cohort_id": "2025Q1",
      "as_of": "2025-03-31",
      "market": "US",
      "benchmark": "QQQ",
      "verdict": "Buy",
      "rr_score": 2.5,
      "target_base": 220.0,
      "target_bull": 250.0,
      "target_bear": 180.0,
      "return_1m": 0.0289,  "return_3m": ...,  "return_6m": ...,  "return_12m": ...,
      "excess_1m": 0.0147,  "excess_3m": ...,  "excess_6m": ...,  "excess_12m": ...,
      "outcome_status": {"12m": "data_unavailable"},  // empty dict when clean
      "analysis_present": true,
      "outcome_present":  true
    }

JSONL is sorted by ``ticker`` for byte-deterministic output across
runs — the eval notebook compares cohort-to-cohort and a stable
ordering keeps diffs readable.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import pathlib
from dataclasses import asdict, dataclass, field
from typing import Any

from tools.backtest.cohort_manifest import CohortManifest
from tools.paths import backtest_path

__all__ = [
    "CohortAggregatorError",
    "CohortRow",
    "aggregate_and_write",
    "aggregate_cohort",
    "build_row",
    "load_analysis_result",
    "load_outcome",
    "write_results_jsonl",
]


_HORIZON_LABELS: tuple[str, ...] = ("1m", "3m", "6m", "12m")
_DATA_UNAVAILABLE = "data_unavailable"


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class CohortAggregatorError(RuntimeError):
    """Raised on malformed cohort artifacts during aggregation.

    Loader functions raise this on malformed JSON. Missing files are
    *not* errors — :func:`load_outcome` and :func:`load_analysis_result`
    return ``None`` for those, and :func:`build_row` handles the join
    accordingly.
    """


# ---------------------------------------------------------------------------
# Row schema
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CohortRow:
    """One row in the cohort ``results.jsonl``.

    Parameters
    ----------
    ticker:
        Stock symbol.
    cohort_id:
        Cohort identifier the row belongs to.
    as_of:
        ISO date string (``YYYY-MM-DD``). Stored as a string to keep
        :func:`json.dumps` trivial without a custom encoder.
    market:
        ``"US"`` | ``"KR"``. Sourced from the cohort manifest when
        available, else from the outcome dict, else from the meta file.
    benchmark:
        Benchmark used by the outcome computer (e.g. ``"SPY"``,
        ``"QQQ"``, ``"KOSPI"``). ``None`` when no outcome was joined.
    verdict, rr_score, target_*:
        Best-effort fields from ``analysis-result.json``. See module
        docstring for the field-mapping contract.
    return_*, excess_*:
        Forward returns and benchmark-adjusted excess returns at each
        horizon. ``None`` for any horizon recorded as
        ``data_unavailable`` (also reflected in ``outcome_status``).
    outcome_status:
        ``{horizon: status}`` for every horizon flagged
        ``data_unavailable``. Empty dict when all 4 horizons are clean
        (the common case).
    analysis_present, outcome_present:
        Track which artifacts contributed to the row. The eval notebook
        uses these to compute coverage stats without re-checking the
        filesystem.
    """

    ticker: str
    cohort_id: str
    as_of: str
    market: str
    benchmark: str | None = None

    verdict: str | None = None
    rr_score: float | None = None
    target_base: float | None = None
    target_bull: float | None = None
    target_bear: float | None = None

    return_1m: float | None = None
    return_3m: float | None = None
    return_6m: float | None = None
    return_12m: float | None = None

    excess_1m: float | None = None
    excess_3m: float | None = None
    excess_6m: float | None = None
    excess_12m: float | None = None

    outcome_status: dict[str, str] = field(default_factory=dict)
    analysis_present: bool = False
    outcome_present: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dict of the row.

        Uses :func:`dataclasses.asdict` and copies ``outcome_status`` so
        the consumer cannot mutate the frozen instance's default.
        """
        return asdict(self)


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def load_outcome(path: pathlib.Path) -> dict[str, Any] | None:
    """Load ``_outcome.json`` from ``path``.

    Parameters
    ----------
    path:
        Path to a ticker's ``_outcome.json`` (typically
        ``backtest/cohorts/{id}/runs/{ticker}/_outcome.json``).

    Returns
    -------
    dict | None
        Parsed payload, or ``None`` if the file is missing.

    Raises
    ------
    CohortAggregatorError
        On JSON-decode failure or non-object root. Rationale: a
        malformed outcome is a regression signal that must surface,
        not get silently dropped from the cohort.
    """
    return _load_json_object_or_none(path, label="outcome")


def load_analysis_result(path: pathlib.Path) -> dict[str, Any] | None:
    """Load ``analysis-result.json`` from ``path``.

    Same contract as :func:`load_outcome` — missing → ``None``,
    malformed → :class:`CohortAggregatorError`.
    """
    return _load_json_object_or_none(path, label="analysis-result")


def _load_json_object_or_none(
    path: pathlib.Path, *, label: str
) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CohortAggregatorError(
            f"cannot read {label} file {path}: {exc}"
        ) from exc
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CohortAggregatorError(
            f"malformed JSON in {label} file {path}: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise CohortAggregatorError(
            f"{label} root must be a JSON object; got "
            f"{type(payload).__name__} (in {path})"
        )
    return payload


# ---------------------------------------------------------------------------
# Defensive nested gets
# ---------------------------------------------------------------------------


def _safe_get(d: Any, *keys: str) -> Any:
    """Walk a nested dict by keys, returning ``None`` on any miss."""
    cur: Any = d
    for k in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
        if cur is None:
            return None
    return cur


def _coerce_float(v: Any) -> float | None:
    """Coerce ``v`` to ``float`` or return ``None`` on any failure.

    Booleans return ``None`` — ``True == 1`` would otherwise sneak
    through as a numeric and silently corrupt the row.
    """
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        try:
            f = float(v)
        except (TypeError, ValueError):
            return None
        # NaN / Inf would survive json.dumps as Python objects but break
        # downstream consumers (pandas read_json, JS notebooks). Filter.
        if f != f or f in (float("inf"), float("-inf")):
            return None
        return f
    return None


def _extract_verdict(analysis: dict[str, Any]) -> str | None:
    raw = analysis.get("verdict")
    if isinstance(raw, str):
        return raw or None
    if isinstance(raw, dict):
        label = raw.get("label")
        return label if isinstance(label, str) and label else None
    return None


def _extract_rr_score(analysis: dict[str, Any]) -> float | None:
    raw = analysis.get("rr_score")
    if isinstance(raw, dict):
        return _coerce_float(raw.get("value"))
    return _coerce_float(raw)


def _extract_target(analysis: dict[str, Any], variant: str) -> float | None:
    """Extract a price target for ``variant`` ∈ {base, bull, bear}.

    Tries paths in declared priority order; first non-None hit wins.
    """
    candidates = (
        _safe_get(analysis, "valuation", "target_price", variant),
        _safe_get(analysis, "targets", variant),
        _safe_get(analysis, "scenarios", variant, "target"),
        analysis.get(f"target_{variant}"),
    )
    for c in candidates:
        f = _coerce_float(c)
        if f is not None:
            return f
    return None


# ---------------------------------------------------------------------------
# build_row
# ---------------------------------------------------------------------------


def build_row(
    *,
    ticker: str,
    cohort_id: str,
    as_of: _dt.date,
    market: str,
    outcome: dict[str, Any] | None,
    analysis: dict[str, Any] | None,
) -> CohortRow:
    """Build one :class:`CohortRow` from raw outcome + analysis dicts.

    Pure function — no I/O, no mutation of inputs. The caller resolves
    ``(ticker, cohort_id, as_of, market)`` from the cohort manifest or
    from ``_backtest-meta.json`` before calling here.
    """
    benchmark: str | None = None
    horizon_returns: dict[str, float | None] = dict.fromkeys(_HORIZON_LABELS)
    horizon_excess: dict[str, float | None] = dict.fromkeys(_HORIZON_LABELS)
    outcome_status: dict[str, str] = {}

    if outcome is not None:
        bench_raw = outcome.get("benchmark")
        if isinstance(bench_raw, str) and bench_raw:
            benchmark = bench_raw
        horizons = outcome.get("horizons") or {}
        if isinstance(horizons, dict):
            for label in _HORIZON_LABELS:
                h = horizons.get(label)
                if not isinstance(h, dict):
                    continue
                status = h.get("_status")
                if status == _DATA_UNAVAILABLE:
                    outcome_status[label] = _DATA_UNAVAILABLE
                    # ticker_return / excess_return remain None
                    continue
                horizon_returns[label] = _coerce_float(h.get("ticker_return"))
                horizon_excess[label] = _coerce_float(h.get("excess_return"))

    verdict: str | None = None
    rr_score: float | None = None
    target_base: float | None = None
    target_bull: float | None = None
    target_bear: float | None = None
    if analysis is not None:
        verdict = _extract_verdict(analysis)
        rr_score = _extract_rr_score(analysis)
        target_base = _extract_target(analysis, "base")
        target_bull = _extract_target(analysis, "bull")
        target_bear = _extract_target(analysis, "bear")

    return CohortRow(
        ticker=ticker,
        cohort_id=cohort_id,
        as_of=as_of.isoformat(),
        market=market,
        benchmark=benchmark,
        verdict=verdict,
        rr_score=rr_score,
        target_base=target_base,
        target_bull=target_bull,
        target_bear=target_bear,
        return_1m=horizon_returns["1m"],
        return_3m=horizon_returns["3m"],
        return_6m=horizon_returns["6m"],
        return_12m=horizon_returns["12m"],
        excess_1m=horizon_excess["1m"],
        excess_3m=horizon_excess["3m"],
        excess_6m=horizon_excess["6m"],
        excess_12m=horizon_excess["12m"],
        outcome_status=dict(outcome_status),
        analysis_present=analysis is not None,
        outcome_present=outcome is not None,
    )


# ---------------------------------------------------------------------------
# Cohort walk
# ---------------------------------------------------------------------------


def _resolve_cohort_root(
    cohort_id: str, cohort_root: pathlib.Path | None
) -> pathlib.Path:
    """Return the cohort root directory, honoring an explicit override."""
    if cohort_root is not None:
        return pathlib.Path(cohort_root)
    return backtest_path("cohorts", cohort_id)


def _read_meta_as_of(meta_path: pathlib.Path) -> _dt.date | None:
    if not meta_path.exists():
        return None
    try:
        payload = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    raw = payload.get("as_of") if isinstance(payload, dict) else None
    if not isinstance(raw, str):
        return None
    try:
        return _dt.date.fromisoformat(raw)
    except ValueError:
        return None


def _read_meta_market(meta_path: pathlib.Path) -> str | None:
    """Some meta files include market; tolerate its absence."""
    if not meta_path.exists():
        return None
    try:
        payload = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    raw = payload.get("market")
    return raw if isinstance(raw, str) and raw else None


def aggregate_cohort(
    *,
    cohort_id: str,
    manifest: CohortManifest | None = None,
    cohort_root: pathlib.Path | None = None,
) -> list[CohortRow]:
    """Walk ``cohort_root/runs/*`` and build one row per ticker.

    Parameters
    ----------
    cohort_id:
        Cohort identifier. Used to build the row's ``cohort_id`` field
        and (when ``cohort_root`` is None) to locate the cohort
        directory under :func:`tools.paths.backtest_path`.
    manifest:
        Optional :class:`CohortManifest`. When provided, it is the
        source of truth for ``(ticker, market, as_of)``: any ticker not
        listed in the manifest is still walked (so orphaned runs surface
        in the JSONL), but tickers in the manifest get the manifest's
        ``market`` and ``as_of`` even if the on-disk artifacts disagree.
    cohort_root:
        Optional directory override (used by tests). Defaults to
        ``backtest/cohorts/{cohort_id}`` under the configured data dir.

    Returns
    -------
    list[CohortRow]
        Rows in directory-iteration order. :func:`write_results_jsonl`
        sorts before writing.

    Raises
    ------
    CohortAggregatorError
        Propagated from the loaders when a ticker has malformed JSON.
        A cohort with one bad ticker fails the whole walk loud — silent
        skipping would mask data-quality regressions.
    """
    root = _resolve_cohort_root(cohort_id, cohort_root)
    runs_dir = root / "runs"
    if not runs_dir.exists():
        return []

    # Manifest lookup: ticker → (market, as_of).
    manifest_lookup: dict[str, tuple[str, _dt.date]] = {}
    if manifest is not None:
        for entry in manifest.tickers:
            manifest_lookup[entry.ticker] = (entry.market, manifest.as_of)

    rows: list[CohortRow] = []
    for ticker_dir in sorted(p for p in runs_dir.iterdir() if p.is_dir()):
        ticker = ticker_dir.name
        outcome_path = ticker_dir / "_outcome.json"
        analysis_path = ticker_dir / "analysis-result.json"
        meta_path = ticker_dir / "_backtest-meta.json"

        outcome = load_outcome(outcome_path)
        analysis = load_analysis_result(analysis_path)

        # Resolve (market, as_of). Manifest > outcome > meta. If none
        # yields an as_of, skip — there is no defensible anchor.
        market: str | None = None
        as_of: _dt.date | None = None

        if ticker in manifest_lookup:
            market, as_of = manifest_lookup[ticker]
        else:
            if outcome is not None:
                m = outcome.get("market")
                if isinstance(m, str) and m:
                    market = m
                a = outcome.get("as_of")
                if isinstance(a, str):
                    try:
                        as_of = _dt.date.fromisoformat(a)
                    except ValueError:
                        as_of = None
            if as_of is None:
                as_of = _read_meta_as_of(meta_path)
            if market is None:
                market = _read_meta_market(meta_path) or ""

        if as_of is None:
            # No outcome, no manifest entry, no meta → cannot anchor.
            continue

        rows.append(
            build_row(
                ticker=ticker,
                cohort_id=cohort_id,
                as_of=as_of,
                market=market or "",
                outcome=outcome,
                analysis=analysis,
            )
        )

    return rows


# ---------------------------------------------------------------------------
# JSONL write
# ---------------------------------------------------------------------------


def write_results_jsonl(
    *,
    rows: list[CohortRow],
    output_path: pathlib.Path,
) -> pathlib.Path:
    """Atomically write ``rows`` as JSONL to ``output_path``.

    Output is one JSON object per line (no trailing comma, no array
    wrapper), UTF-8 encoded, sorted by ``ticker`` for byte-deterministic
    output. Atomic via ``.tmp`` + :func:`os.replace`.

    Parameters
    ----------
    rows:
        List of :class:`CohortRow` instances.
    output_path:
        Destination for ``results.jsonl``. Parent directories are
        created if missing.

    Returns
    -------
    pathlib.Path
        ``output_path``.
    """
    output_path = pathlib.Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")

    sorted_rows = sorted(rows, key=lambda r: r.ticker)
    with tmp_path.open("w", encoding="utf-8") as fh:
        for row in sorted_rows:
            fh.write(json.dumps(row.to_dict(), sort_keys=True))
            fh.write("\n")
    os.replace(tmp_path, output_path)
    return output_path


def aggregate_and_write(
    *,
    cohort_id: str,
    manifest: CohortManifest | None = None,
) -> pathlib.Path:
    """Aggregate a cohort and write ``results.jsonl`` at its root.

    Convenience wrapper that resolves the cohort root from
    :func:`tools.paths.backtest_path`, calls :func:`aggregate_cohort`,
    and persists via :func:`write_results_jsonl`.

    Parameters
    ----------
    cohort_id:
        Cohort identifier.
    manifest:
        Optional cohort manifest (recommended — it is the source of
        truth for ``(market, as_of)``).

    Returns
    -------
    pathlib.Path
        Path to the written ``results.jsonl``.
    """
    root = _resolve_cohort_root(cohort_id, None)
    rows = aggregate_cohort(cohort_id=cohort_id, manifest=manifest, cohort_root=root)
    return write_results_jsonl(rows=rows, output_path=root / "results.jsonl")
