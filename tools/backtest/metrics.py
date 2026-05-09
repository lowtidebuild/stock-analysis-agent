"""Backtest metrics module.

Tasks 5.1 + 5.2 of the backtest plan
(``docs/superpowers/plans/2026-05-08-backtest-harness.md``).

Pure-function metrics that operate on a results-DataFrame produced by
the cohort aggregator (Task 4.3 — see
:mod:`tools.backtest.cohort_aggregator`). Three metrics are exported:

- :func:`compute_ic` — Spearman rank correlation between a score column
  (typically ``rr_score``) and a forward-return column (typically
  ``excess_3m`` or ``excess_12m``). Returns rho plus an *approximate*
  two-sided p-value.
- :func:`compute_hit_rate` — directional accuracy: how often does a
  bullish verdict precede a positive return, and a bearish verdict a
  negative return. Neutral verdicts and rows with NaN returns are
  excluded; zero-return ties resolve to "miss" (conservative). Pure
  binary scoring — no half-credit.
- :func:`compute_decile_sort` — bucketed mean returns across score
  deciles, plus the top-minus-bottom spread. Falls back to fewer
  buckets when the sample is small or score ties collapse the qcut
  edges.

Each function returns a frozen dataclass (:class:`ICResult`,
:class:`HitRateResult`, :class:`DecileSortResult`) with a
``to_dict()`` helper that emits a JSON-serializable dict — Phase 1's
notebook (Task 5.3) and CLI consume that surface, not the dataclass.

Dependency rationale
--------------------

This module uses **pandas** (already installed as a transitive of
``yfinance``, version 3.0.2 at the time of writing — but **not pinned
in ``requirements.txt``**, so add it explicitly there before relying on
this module in production). Pandas is the natural API for the tabular
shape this module receives.

It does **not** require **scipy**. The Spearman p-value is computed via
a t-distribution + ``math.erfc`` approximation — accurate for ``n >=
~30``, rough for very small samples. Callers who need an exact small-n
p-value should run ``scipy.stats.spearmanr`` separately; we deliberately
do not pull scipy into the backtest harness's runtime dependency list
(it is a heavy native install for marginal benefit at our sample
sizes).

Conventions
-----------

- All return values that depend on a non-empty sample are typed
  ``float | None``: ``None`` signals "not enough data to compute" so
  the notebook can render a blank cell instead of a misleading 0.0.
- Source columns missing from the input DataFrame raise
  :class:`MetricsError` (a ``ValueError`` subclass), not ``KeyError``,
  so the calling layer can branch on a single typed exception.
- All input frames are read-only; functions never mutate them.
"""

from __future__ import annotations

import datetime as _dt  # noqa: F401  -- intentional: matches sibling modules' import baseline
import math
import warnings
from dataclasses import asdict, dataclass, field
from typing import Any

import pandas as pd

__all__ = [
    "DecileSortResult",
    "HitRateResult",
    "ICResult",
    "MetricsError",
    "compute_decile_sort",
    "compute_hit_rate",
    "compute_ic",
]


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class MetricsError(ValueError):
    """Raised on malformed inputs to a metric function.

    Examples: a required column is missing from the input DataFrame, or
    the bullish / bearish / neutral label tuples passed to
    :func:`compute_hit_rate` overlap. We subclass ``ValueError`` so
    callers that already catch ``ValueError`` (e.g. notebook cells) keep
    working without explicit imports.
    """


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ICResult:
    """Result of :func:`compute_ic`.

    Parameters
    ----------
    score_col, return_col:
        Echo of the columns the function read.
    n:
        Sample size after dropping rows with NaN in either column.
    spearman_rho:
        Spearman rank correlation in ``[-1.0, 1.0]``. ``None`` when
        ``n < 3`` (Spearman is undefined / meaningless).
    p_value:
        Approximate two-sided p-value for ``H0: rho = 0``. ``None``
        when ``n < 3`` or when ``rho`` is undefined. Pinned to ``0.0``
        when ``|rho| == 1`` (the t-statistic diverges to infinity).
        For ``n < 30`` the approximation is rough — see module
        docstring.
    """

    score_col: str
    return_col: str
    n: int
    spearman_rho: float | None
    p_value: float | None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dict of this result."""
        return asdict(self)


@dataclass(frozen=True)
class HitRateResult:
    """Result of :func:`compute_hit_rate`.

    Parameters
    ----------
    verdict_col, return_col:
        Echo of the columns the function read.
    n_total:
        Number of rows that were scored (bullish or bearish, with a
        non-NaN return).
    n_hits:
        Number of correct directional calls.
    hit_rate:
        ``n_hits / n_total``. ``None`` when ``n_total == 0``.
    bullish_n, bullish_hits, bullish_hit_rate:
        Breakdown for bullish verdicts. ``bullish_hit_rate`` is
        ``None`` when ``bullish_n == 0``.
    bearish_n, bearish_hits, bearish_hit_rate:
        Breakdown for bearish verdicts. Same ``None`` semantics.
    n_neutral_excluded:
        Rows whose verdict matched the neutral label list (excluded
        from scoring entirely).
    n_nan_excluded:
        Rows whose return was NaN (excluded from scoring entirely).
    """

    verdict_col: str
    return_col: str
    n_total: int
    n_hits: int
    hit_rate: float | None
    bullish_n: int
    bullish_hits: int
    bullish_hit_rate: float | None
    bearish_n: int
    bearish_hits: int
    bearish_hit_rate: float | None
    n_neutral_excluded: int
    n_nan_excluded: int

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dict of this result."""
        return asdict(self)


@dataclass(frozen=True)
class DecileSortResult:
    """Result of :func:`compute_decile_sort`.

    Parameters
    ----------
    score_col, return_col:
        Echo of the columns the function read.
    n_buckets:
        Actual bucket count used. Capped at ``min(requested, n)`` and
        further reduced by ``pd.qcut(duplicates="drop")`` when score
        ties collapse bucket edges. ``0`` when ``n < 2``.
    n_dropped_nan:
        Rows dropped because either column was NaN.
    buckets:
        One dict per bucket, sorted ascending by score. Schema::

            {"bucket": int (1..n_buckets, 1 = lowest score),
             "n": int,
             "mean_return": float,
             "mean_score": float,
             "low_edge": float,
             "high_edge": float}

    top_minus_bottom_spread:
        ``mean_return(last_bucket) - mean_return(first_bucket)``.
        ``None`` when ``n_buckets < 2``.
    """

    score_col: str
    return_col: str
    n_buckets: int
    n_dropped_nan: int
    buckets: list[dict[str, Any]] = field(default_factory=list)
    top_minus_bottom_spread: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dict of this result."""
        return asdict(self)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_columns(df: pd.DataFrame, *cols: str) -> None:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise MetricsError(
            f"missing required column(s) in DataFrame: {missing}"
        )


def _approx_two_sided_p_from_rho(rho: float, n: int) -> float | None:
    """Approximate two-sided p-value for Spearman rho via t-distribution.

    Uses ``t = rho * sqrt((n - 2) / (1 - rho**2))`` and approximates the
    two-tailed survival function of the standard normal as
    ``erfc(|t| / sqrt(2))``. This is the large-sample limit of the
    Student-t distribution and is reasonable for ``n >= ~30``. For
    smaller ``n`` the p-value will be slightly anti-conservative; this
    module documents that and does not pretend otherwise.

    Returns
    -------
    float | None
        Approximate p-value in ``[0.0, 1.0]``. ``None`` when ``n < 3``.
        Pinned to ``0.0`` when ``|rho| == 1`` (t diverges).
    """
    if n < 3:
        return None
    # Perfect correlation → t is infinite → p-value collapses to 0.
    # (We compare |rho| to 1.0 with a generous epsilon because
    # .rank().corr() can produce values like -0.9999999999999999 for
    # exactly-anticorrelated inputs.)
    if abs(rho) >= 1.0 - 1e-12:
        return 0.0
    denom = 1.0 - rho * rho
    if denom <= 0.0:
        return 0.0
    t = rho * math.sqrt((n - 2) / denom)
    p = math.erfc(abs(t) / math.sqrt(2.0))
    # Clamp into [0, 1] defensively (erfc is in (0, 2) but for very
    # small |t| it can return values numerically just above 1.0).
    if p < 0.0:
        return 0.0
    if p > 1.0:
        return 1.0
    return p


# ---------------------------------------------------------------------------
# compute_ic
# ---------------------------------------------------------------------------


def compute_ic(
    df: pd.DataFrame,
    *,
    score_col: str = "rr_score",
    return_col: str = "excess_3m",
) -> ICResult:
    """Compute the Spearman Information Coefficient (IC).

    Spearman is computed by ranking both columns and then taking
    Pearson correlation of the ranks (this is Spearman by definition,
    and avoids the scipy dependency that pandas's
    ``Series.corr(method="spearman")`` requires under the hood).

    Parameters
    ----------
    df:
        Results DataFrame from
        :func:`tools.backtest.cohort_aggregator.aggregate_cohort`.
    score_col:
        Score column. Default ``"rr_score"``.
    return_col:
        Forward (or excess) return column. Default ``"excess_3m"``.

    Returns
    -------
    ICResult
        See class docstring for field semantics.

    Raises
    ------
    MetricsError
        If ``score_col`` or ``return_col`` is not a column in ``df``.
    """
    _require_columns(df, score_col, return_col)

    # Coerce to numeric so a string-typed score column (e.g. caller meant
    # rr_score but accidentally passed verdict) does NOT silently
    # produce a perfect lexicographic-rank correlation. Non-numeric
    # values become NaN and get dropped along with real NaN rows.
    sub = df[[score_col, return_col]].copy()
    for col in (score_col, return_col):
        sub[col] = pd.to_numeric(sub[col], errors="coerce")
    sub = sub.dropna()
    n = len(sub)

    if n < 3:
        return ICResult(
            score_col=score_col,
            return_col=return_col,
            n=n,
            spearman_rho=None,
            p_value=None,
        )

    # Suppress the numpy "invalid value encountered in divide"
    # RuntimeWarning that fires when a rank column has zero variance.
    # We detect the resulting NaN ourselves below.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        rho = sub[score_col].rank().corr(sub[return_col].rank())
    # `.corr` returns NaN if a column has zero variance after ranking
    # (e.g. all rows have identical score). Treat that as "undefined".
    if pd.isna(rho):
        return ICResult(
            score_col=score_col,
            return_col=return_col,
            n=n,
            spearman_rho=None,
            p_value=None,
        )

    rho_f = float(rho)
    # Floating-point cleanup: clamp to [-1, 1] and round perfect
    # correlations that come back as -0.9999999999999999.
    if rho_f > 1.0:
        rho_f = 1.0
    elif rho_f < -1.0:
        rho_f = -1.0
    if abs(rho_f) >= 1.0 - 1e-12:
        rho_f = math.copysign(1.0, rho_f)

    p_value = _approx_two_sided_p_from_rho(rho_f, n)

    return ICResult(
        score_col=score_col,
        return_col=return_col,
        n=n,
        spearman_rho=rho_f,
        p_value=p_value,
    )


# ---------------------------------------------------------------------------
# compute_hit_rate
# ---------------------------------------------------------------------------


def compute_hit_rate(
    df: pd.DataFrame,
    *,
    verdict_col: str = "verdict",
    return_col: str = "return_12m",
    bullish_labels: tuple[str, ...] = (
        "비중확대", "Buy", "Strong Buy", "Overweight",
    ),
    bearish_labels: tuple[str, ...] = (
        "비중축소", "Sell", "Strong Sell", "Underweight",
    ),
    neutral_labels: tuple[str, ...] = ("중립", "Hold", "Neutral"),
) -> HitRateResult:
    """Compute the directional hit rate of analyst verdicts.

    Scoring rules
    -------------

    For each row that survives the NaN-return and neutral-verdict
    filters:

    - bullish + ``return > 0`` → hit
    - bullish + ``return <= 0`` → miss (zero-return ties resolve to
      miss, the conservative choice)
    - bearish + ``return < 0`` → hit
    - bearish + ``return >= 0`` → miss (same tie-break)
    - other verdict labels → not counted (excluded from ``n_total``)

    Parameters
    ----------
    df:
        Results DataFrame from the cohort aggregator.
    verdict_col:
        Verdict column. Default ``"verdict"``.
    return_col:
        Realized-return column. Default ``"return_12m"`` (the longest
        horizon, where directional calls have had the most time to
        play out).
    bullish_labels, bearish_labels, neutral_labels:
        Label tuples. Defaults cover the Korean ("비중확대" /
        "비중축소" / "중립") and English ("Buy" / "Sell" / "Hold")
        verdict vocabularies the production analyst emits.

    Returns
    -------
    HitRateResult
        See class docstring for field semantics.

    Raises
    ------
    MetricsError
        If a required column is missing, or if any label appears in
        more than one of the three label lists (which would make the
        scoring ambiguous).
    """
    _require_columns(df, verdict_col, return_col)

    bullish = set(bullish_labels)
    bearish = set(bearish_labels)
    neutral = set(neutral_labels)
    overlap = (bullish & bearish) | (bullish & neutral) | (bearish & neutral)
    if overlap:
        raise MetricsError(
            f"label overlap between bullish/bearish/neutral lists: "
            f"{sorted(overlap)}"
        )

    # Drop NaN returns (record count). Keep the verdict column even if
    # it is empty-string — the unknown-label branch below handles that.
    nan_mask = df[return_col].isna()
    n_nan_excluded = int(nan_mask.sum())
    work = df.loc[~nan_mask, [verdict_col, return_col]]

    # Drop neutral verdicts (record count).
    neutral_mask = work[verdict_col].isin(list(neutral))
    n_neutral_excluded = int(neutral_mask.sum())
    work = work.loc[~neutral_mask]

    bullish_n = 0
    bullish_hits = 0
    bearish_n = 0
    bearish_hits = 0
    for verdict, ret in zip(work[verdict_col].tolist(),
                             work[return_col].tolist()):
        if verdict in bullish:
            bullish_n += 1
            if ret > 0:
                bullish_hits += 1
        elif verdict in bearish:
            bearish_n += 1
            if ret < 0:
                bearish_hits += 1
        # else: unknown label — silently dropped from scoring.

    n_total = bullish_n + bearish_n
    n_hits = bullish_hits + bearish_hits
    hit_rate = (n_hits / n_total) if n_total > 0 else None
    bullish_hit_rate = (bullish_hits / bullish_n) if bullish_n > 0 else None
    bearish_hit_rate = (bearish_hits / bearish_n) if bearish_n > 0 else None

    return HitRateResult(
        verdict_col=verdict_col,
        return_col=return_col,
        n_total=n_total,
        n_hits=n_hits,
        hit_rate=hit_rate,
        bullish_n=bullish_n,
        bullish_hits=bullish_hits,
        bullish_hit_rate=bullish_hit_rate,
        bearish_n=bearish_n,
        bearish_hits=bearish_hits,
        bearish_hit_rate=bearish_hit_rate,
        n_neutral_excluded=n_neutral_excluded,
        n_nan_excluded=n_nan_excluded,
    )


# ---------------------------------------------------------------------------
# compute_decile_sort
# ---------------------------------------------------------------------------


def compute_decile_sort(
    df: pd.DataFrame,
    *,
    score_col: str = "rr_score",
    return_col: str = "excess_12m",
    n_buckets: int = 10,
) -> DecileSortResult:
    """Bucket rows by score quantile and report mean return per bucket.

    Uses :func:`pandas.qcut` with ``duplicates="drop"`` so dense ties
    in the score column collapse buckets instead of crashing. The
    requested ``n_buckets`` is capped at ``min(n_buckets, n)`` so a
    5-row sample with ``n_buckets=10`` still produces a sensible
    output.

    Parameters
    ----------
    df:
        Results DataFrame from the cohort aggregator.
    score_col:
        Score column. Default ``"rr_score"``.
    return_col:
        Realized (or excess) return column. Default ``"excess_12m"``.
    n_buckets:
        Requested bucket count (typically ``10`` for deciles, ``5`` for
        quintiles). Effective count may be lower — see ``n_buckets``
        on :class:`DecileSortResult`.

    Returns
    -------
    DecileSortResult
        See class docstring for field semantics.

    Raises
    ------
    MetricsError
        If a required column is missing.
    """
    _require_columns(df, score_col, return_col)

    # Coerce to numeric (mirror compute_ic) so accidental string
    # columns don't sneak through ranking.
    sub = df[[score_col, return_col]].copy()
    for col in (score_col, return_col):
        sub[col] = pd.to_numeric(sub[col], errors="coerce")
    sub = sub.dropna()
    n = len(sub)
    n_dropped_nan = int(len(df) - n)

    if n < 2:
        return DecileSortResult(
            score_col=score_col,
            return_col=return_col,
            n_buckets=0,
            n_dropped_nan=n_dropped_nan,
            buckets=[],
            top_minus_bottom_spread=None,
        )

    effective_q = min(n_buckets, n)
    try:
        bucket_codes = pd.qcut(
            sub[score_col],
            q=effective_q,
            labels=False,
            duplicates="drop",
        )
    except ValueError:
        # qcut can still raise when *all* edges collapse (e.g. a single
        # unique value across all rows). Fall back to a single bucket.
        bucket_codes = pd.Series([0] * n, index=sub.index)
    else:
        # Modern pandas (3.0+) does NOT raise on all-identical scores
        # — it returns an all-NaN coded series. Detect and fall back
        # to a single bucket so downstream int() coercion doesn't
        # crash.
        if bucket_codes.isna().all():
            bucket_codes = pd.Series([0] * n, index=sub.index)

    sub = sub.assign(_bucket=bucket_codes)
    actual_n_buckets = int(sub["_bucket"].nunique())

    grouped = sub.groupby("_bucket", sort=True)
    buckets: list[dict[str, Any]] = []
    # `sorted_codes` maps the dense qcut codes (0..k-1, ascending by
    # score) onto our 1..n_buckets bucket numbers (1 = lowest scores).
    sorted_codes = sorted(int(c) for c in sub["_bucket"].unique())
    for bucket_num, code in enumerate(sorted_codes, start=1):
        g = grouped.get_group(code)
        buckets.append({
            "bucket": bucket_num,
            "n": int(len(g)),
            "mean_return": float(g[return_col].mean()),
            "mean_score": float(g[score_col].mean()),
            "low_edge": float(g[score_col].min()),
            "high_edge": float(g[score_col].max()),
        })

    spread: float | None = None
    if actual_n_buckets >= 2:
        spread = buckets[-1]["mean_return"] - buckets[0]["mean_return"]

    return DecileSortResult(
        score_col=score_col,
        return_col=return_col,
        n_buckets=actual_n_buckets,
        n_dropped_nan=n_dropped_nan,
        buckets=buckets,
        top_minus_bottom_spread=spread,
    )
