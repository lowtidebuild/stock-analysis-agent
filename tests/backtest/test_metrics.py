"""Tests for the backtest metrics module (Tasks 5.1 + 5.2).

Covers Tasks 5.1 + 5.2 of the backtest harness plan
(``docs/superpowers/plans/2026-05-08-backtest-harness.md``):

- :func:`compute_ic` — Spearman rank correlation between a score column
  (typically ``rr_score``) and a forward-return column.
- :func:`compute_hit_rate` — directional accuracy of bullish / bearish
  verdicts vs realized returns.
- :func:`compute_decile_sort` — bucketed mean returns across score
  deciles, plus top-minus-bottom spread.
- Frozen-dataclass result objects (``ICResult``, ``HitRateResult``,
  ``DecileSortResult``) and their ``to_dict()`` JSON-serialization.

Run via: ``python -m pytest tests/backtest/test_metrics.py -v``
"""

from __future__ import annotations

import json
import math
import pathlib
import random
import sys

import pandas as pd
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.backtest.metrics import (  # noqa: E402
    DecileSortResult,
    HitRateResult,
    ICResult,
    MetricsError,
    compute_decile_sort,
    compute_hit_rate,
    compute_ic,
)


# ---------------------------------------------------------------------------
# compute_ic
# ---------------------------------------------------------------------------


def test_compute_ic_perfect_positive_correlation() -> None:
    df = pd.DataFrame({"rr_score": [1.0, 2.0, 3.0, 4.0, 5.0],
                       "excess_3m": [0.01, 0.02, 0.03, 0.04, 0.05]})
    res = compute_ic(df)
    assert res.n == 5
    assert res.spearman_rho is not None
    assert math.isclose(res.spearman_rho, 1.0, abs_tol=1e-9)
    # Perfect correlation → p-value pinned to 0.0.
    assert res.p_value == 0.0


def test_compute_ic_perfect_negative_correlation() -> None:
    df = pd.DataFrame({"rr_score": [1.0, 2.0, 3.0, 4.0, 5.0],
                       "excess_3m": [0.05, 0.04, 0.03, 0.02, 0.01]})
    res = compute_ic(df)
    assert res.n == 5
    assert res.spearman_rho is not None
    assert math.isclose(res.spearman_rho, -1.0, abs_tol=1e-9)
    assert res.p_value == 0.0


def test_compute_ic_no_correlation_random_data() -> None:
    random.seed(42)
    n = 200
    scores = [random.random() for _ in range(n)]
    rets = [random.random() for _ in range(n)]
    df = pd.DataFrame({"rr_score": scores, "excess_3m": rets})
    res = compute_ic(df)
    assert res.n == n
    assert res.spearman_rho is not None
    assert abs(res.spearman_rho) < 0.3


def test_compute_ic_drops_nan_rows() -> None:
    df = pd.DataFrame({
        "rr_score": [1.0, 2.0, None, 4.0, 5.0, 6.0],
        "excess_3m": [0.1, 0.2, 0.3, None, 0.5, 0.6],
    })
    # 4 rows survive the NaN drop.
    res = compute_ic(df)
    assert res.n == 4


def test_compute_ic_returns_none_when_n_lt_3() -> None:
    df = pd.DataFrame({"rr_score": [1.0, 2.0], "excess_3m": [0.1, 0.2]})
    res = compute_ic(df)
    assert res.n == 2
    assert res.spearman_rho is None
    assert res.p_value is None


def test_compute_ic_raises_when_column_missing() -> None:
    df = pd.DataFrame({"rr_score": [1.0, 2.0, 3.0]})
    with pytest.raises(MetricsError, match="excess_3m"):
        compute_ic(df)


def test_compute_ic_p_value_present_when_n_large_enough() -> None:
    # n=50, moderate positive correlation: signal + noise.
    random.seed(7)
    n = 50
    scores = list(range(n))
    rets = [s * 0.01 + random.random() * 0.5 for s in scores]
    df = pd.DataFrame({"rr_score": scores, "excess_3m": rets})
    res = compute_ic(df)
    assert res.spearman_rho is not None
    assert res.p_value is not None
    assert 0.0 <= res.p_value <= 1.0
    # We injected real signal — at n=50 we expect p_value < 1.0.
    assert res.p_value < 1.0


def test_compute_ic_perfect_correlation_p_value_zero() -> None:
    df = pd.DataFrame({"rr_score": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
                       "excess_3m": [10.0, 20.0, 30.0, 40.0, 50.0, 60.0]})
    res = compute_ic(df)
    assert res.spearman_rho is not None
    assert math.isclose(res.spearman_rho, 1.0, abs_tol=1e-9)
    assert res.p_value == 0.0


def test_compute_ic_custom_columns() -> None:
    df = pd.DataFrame({"foo": [1.0, 2.0, 3.0, 4.0],
                       "bar": [4.0, 3.0, 2.0, 1.0]})
    res = compute_ic(df, score_col="foo", return_col="bar")
    assert res.score_col == "foo"
    assert res.return_col == "bar"
    assert res.spearman_rho is not None
    assert math.isclose(res.spearman_rho, -1.0, abs_tol=1e-9)


# ---------------------------------------------------------------------------
# compute_hit_rate
# ---------------------------------------------------------------------------


def test_compute_hit_rate_all_bullish_all_positive() -> None:
    df = pd.DataFrame({
        "verdict": ["비중확대"] * 5,
        "return_12m": [0.05, 0.10, 0.02, 0.20, 0.15],
    })
    res = compute_hit_rate(df)
    assert res.n_total == 5
    assert res.n_hits == 5
    assert res.hit_rate == 1.0
    assert res.bullish_n == 5
    assert res.bullish_hits == 5
    assert res.bullish_hit_rate == 1.0
    assert res.bearish_n == 0
    assert res.bearish_hit_rate is None


def test_compute_hit_rate_all_bullish_all_negative() -> None:
    df = pd.DataFrame({
        "verdict": ["Buy"] * 4,
        "return_12m": [-0.05, -0.10, -0.02, -0.20],
    })
    res = compute_hit_rate(df)
    assert res.n_total == 4
    assert res.n_hits == 0
    assert res.hit_rate == 0.0
    assert res.bullish_hit_rate == 0.0


def test_compute_hit_rate_all_bearish_all_negative() -> None:
    df = pd.DataFrame({
        "verdict": ["비중축소"] * 3,
        "return_12m": [-0.05, -0.10, -0.20],
    })
    res = compute_hit_rate(df)
    assert res.n_total == 3
    assert res.n_hits == 3
    assert res.hit_rate == 1.0
    assert res.bearish_hit_rate == 1.0
    assert res.bullish_n == 0
    assert res.bullish_hit_rate is None


def test_compute_hit_rate_mixed_labels() -> None:
    df = pd.DataFrame({
        "verdict": ["비중확대", "비중확대", "비중확대", "비중축소", "비중축소"],
        "return_12m": [0.10, 0.05, -0.02, -0.10, 0.05],
    })
    # Bullish: 2 hits, 1 miss (3 total, hit_rate=2/3).
    # Bearish: 1 hit, 1 miss (2 total, hit_rate=1/2).
    # Combined: 3 hits, 5 total → 0.6.
    res = compute_hit_rate(df)
    assert res.n_total == 5
    assert res.n_hits == 3
    assert math.isclose(res.hit_rate, 0.6, abs_tol=1e-9)
    assert res.bullish_n == 3
    assert res.bullish_hits == 2
    assert math.isclose(res.bullish_hit_rate, 2 / 3, abs_tol=1e-9)
    assert res.bearish_n == 2
    assert res.bearish_hits == 1
    assert math.isclose(res.bearish_hit_rate, 0.5, abs_tol=1e-9)


def test_compute_hit_rate_excludes_neutral() -> None:
    df = pd.DataFrame({
        "verdict": ["중립"] * 5 + ["비중확대"] * 2,
        "return_12m": [0.01] * 7,
    })
    res = compute_hit_rate(df)
    assert res.n_neutral_excluded == 5
    assert res.n_total == 2  # only the 2 bullish rows count
    assert res.n_hits == 2


def test_compute_hit_rate_excludes_nan_returns() -> None:
    df = pd.DataFrame({
        "verdict": ["비중확대", "비중확대", "비중확대"],
        "return_12m": [0.05, None, 0.10],
    })
    res = compute_hit_rate(df)
    assert res.n_nan_excluded == 1
    assert res.n_total == 2
    assert res.n_hits == 2


def test_compute_hit_rate_zero_return_is_miss_for_bullish() -> None:
    df = pd.DataFrame({
        "verdict": ["비중확대", "비중확대"],
        "return_12m": [0.0, 0.10],
    })
    res = compute_hit_rate(df)
    # Zero return is a miss (return > 0 required for bullish hit).
    assert res.n_total == 2
    assert res.n_hits == 1
    assert res.hit_rate == 0.5


def test_compute_hit_rate_zero_return_is_miss_for_bearish() -> None:
    df = pd.DataFrame({
        "verdict": ["비중축소", "비중축소"],
        "return_12m": [0.0, -0.10],
    })
    res = compute_hit_rate(df)
    # Zero return is a miss (return < 0 required for bearish hit).
    assert res.n_total == 2
    assert res.n_hits == 1
    assert res.hit_rate == 0.5


def test_compute_hit_rate_unknown_label_not_counted() -> None:
    df = pd.DataFrame({
        "verdict": ["Mystery", "Buy", "비중확대"],
        "return_12m": [0.10, 0.10, 0.10],
    })
    res = compute_hit_rate(df)
    # "Mystery" is not in any list → not counted, not in n_total.
    assert res.n_total == 2
    assert res.n_hits == 2


def test_compute_hit_rate_raises_when_overlapping_labels() -> None:
    df = pd.DataFrame({"verdict": ["Buy"], "return_12m": [0.1]})
    with pytest.raises(MetricsError, match="overlap"):
        compute_hit_rate(
            df,
            bullish_labels=("Buy", "비중확대"),
            bearish_labels=("Buy", "비중축소"),
        )


def test_compute_hit_rate_raises_when_column_missing() -> None:
    df = pd.DataFrame({"verdict": ["Buy"]})
    with pytest.raises(MetricsError, match="return_12m"):
        compute_hit_rate(df)


# ---------------------------------------------------------------------------
# compute_decile_sort
# ---------------------------------------------------------------------------


def test_compute_decile_sort_basic_10_buckets() -> None:
    # 100 rows, scores 0..99, returns proportional to score.
    n = 100
    df = pd.DataFrame({
        "rr_score": list(range(n)),
        "excess_12m": [s * 0.01 for s in range(n)],
    })
    res = compute_decile_sort(df)
    assert res.n_buckets == 10
    assert len(res.buckets) == 10
    # Bucket 1 (lowest scores) mean_return < bucket 10 mean_return.
    assert res.buckets[0]["mean_return"] < res.buckets[-1]["mean_return"]
    assert res.top_minus_bottom_spread is not None
    assert res.top_minus_bottom_spread > 0


def test_compute_decile_sort_small_sample_caps_buckets() -> None:
    df = pd.DataFrame({
        "rr_score": [1.0, 2.0, 3.0, 4.0, 5.0],
        "excess_12m": [0.01, 0.02, 0.03, 0.04, 0.05],
    })
    res = compute_decile_sort(df, n_buckets=10)
    # Cap at min(10, 5) = 5.
    assert res.n_buckets == 5
    assert len(res.buckets) == 5


def test_compute_decile_sort_drops_nan_rows() -> None:
    df = pd.DataFrame({
        "rr_score": [1.0, 2.0, None, 4.0, 5.0, 6.0],
        "excess_12m": [0.1, 0.2, 0.3, None, 0.5, 0.6],
    })
    res = compute_decile_sort(df, n_buckets=4)
    assert res.n_dropped_nan == 2
    assert res.n_buckets == 4


def test_compute_decile_sort_top_minus_bottom_spread() -> None:
    # 10 rows: scores 1..10. Returns: bottom decile = 0.02, top = 0.10.
    # We construct so qcut into 5 buckets gives clean groups.
    df = pd.DataFrame({
        "rr_score": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
        "excess_12m": [0.02, 0.02, 0.04, 0.04, 0.06,
                        0.06, 0.08, 0.08, 0.10, 0.10],
    })
    res = compute_decile_sort(df, n_buckets=5)
    assert res.n_buckets == 5
    assert res.top_minus_bottom_spread is not None
    # First bucket mean = 0.02, last bucket mean = 0.10 → spread = 0.08.
    assert math.isclose(res.top_minus_bottom_spread, 0.08, abs_tol=1e-9)


def test_compute_decile_sort_buckets_ordered_low_to_high() -> None:
    df = pd.DataFrame({
        "rr_score": list(range(20)),
        "excess_12m": [s * 0.01 for s in range(20)],
    })
    res = compute_decile_sort(df, n_buckets=4)
    # Bucket numbers run 1..n_buckets; mean_score must increase.
    bucket_nums = [b["bucket"] for b in res.buckets]
    assert bucket_nums == list(range(1, res.n_buckets + 1))
    means = [b["mean_score"] for b in res.buckets]
    assert means == sorted(means)


def test_compute_decile_sort_returns_empty_for_n_lt_2() -> None:
    df = pd.DataFrame({"rr_score": [1.0], "excess_12m": [0.05]})
    res = compute_decile_sort(df)
    assert res.n_buckets == 0
    assert res.buckets == []
    assert res.top_minus_bottom_spread is None


def test_compute_decile_sort_returns_empty_for_n_zero() -> None:
    df = pd.DataFrame({"rr_score": [], "excess_12m": []})
    res = compute_decile_sort(df)
    assert res.n_buckets == 0
    assert res.buckets == []
    assert res.top_minus_bottom_spread is None


def test_compute_decile_sort_raises_when_column_missing() -> None:
    df = pd.DataFrame({"rr_score": [1.0, 2.0, 3.0]})
    with pytest.raises(MetricsError, match="excess_12m"):
        compute_decile_sort(df)


def test_compute_decile_sort_handles_duplicate_score_edges() -> None:
    # Many rows with the same score → qcut(duplicates="drop") collapses.
    df = pd.DataFrame({
        "rr_score": [1.0] * 8 + [2.0] * 8 + [3.0] * 4,
        "excess_12m": [0.01] * 8 + [0.05] * 8 + [0.10] * 4,
    })
    res = compute_decile_sort(df, n_buckets=10)
    # Should not crash; reports actual bucket count after dup-drop.
    assert res.n_buckets >= 1
    assert res.n_buckets <= 3
    assert len(res.buckets) == res.n_buckets


# ---------------------------------------------------------------------------
# Dataclass to_dict round-trips
# ---------------------------------------------------------------------------


def test_ic_result_to_dict_roundtrip() -> None:
    df = pd.DataFrame({"rr_score": [1.0, 2.0, 3.0, 4.0, 5.0],
                       "excess_3m": [0.05, 0.04, 0.03, 0.02, 0.01]})
    res = compute_ic(df)
    d = res.to_dict()
    # JSON-serializable.
    s = json.dumps(d)
    parsed = json.loads(s)
    assert parsed["score_col"] == "rr_score"
    assert parsed["return_col"] == "excess_3m"
    assert parsed["n"] == 5
    assert math.isclose(parsed["spearman_rho"], -1.0, abs_tol=1e-9)


def test_hit_rate_result_to_dict_roundtrip() -> None:
    df = pd.DataFrame({
        "verdict": ["비중확대", "비중축소"],
        "return_12m": [0.05, -0.05],
    })
    res = compute_hit_rate(df)
    d = res.to_dict()
    s = json.dumps(d)
    parsed = json.loads(s)
    assert parsed["n_total"] == 2
    assert parsed["n_hits"] == 2
    assert parsed["hit_rate"] == 1.0


def test_decile_sort_result_to_dict_roundtrip() -> None:
    df = pd.DataFrame({
        "rr_score": list(range(10)),
        "excess_12m": [s * 0.01 for s in range(10)],
    })
    res = compute_decile_sort(df, n_buckets=5)
    d = res.to_dict()
    s = json.dumps(d)
    parsed = json.loads(s)
    assert parsed["n_buckets"] == 5
    assert len(parsed["buckets"]) == 5


# ---------------------------------------------------------------------------
# Frozen-dataclass invariant
# ---------------------------------------------------------------------------


def test_ic_result_is_frozen() -> None:
    res = ICResult(score_col="x", return_col="y", n=0,
                   spearman_rho=None, p_value=None)
    with pytest.raises((AttributeError, Exception)):
        res.n = 99  # type: ignore[misc]


def test_hit_rate_result_is_frozen() -> None:
    res = HitRateResult(
        verdict_col="v", return_col="r", n_total=0, n_hits=0,
        hit_rate=None, bullish_n=0, bullish_hits=0, bullish_hit_rate=None,
        bearish_n=0, bearish_hits=0, bearish_hit_rate=None,
        n_neutral_excluded=0, n_nan_excluded=0,
    )
    with pytest.raises((AttributeError, Exception)):
        res.n_total = 99  # type: ignore[misc]


def test_decile_sort_result_is_frozen() -> None:
    res = DecileSortResult(score_col="x", return_col="y", n_buckets=0,
                            n_dropped_nan=0, buckets=[],
                            top_minus_bottom_spread=None)
    with pytest.raises((AttributeError, Exception)):
        res.n_buckets = 99  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Regression tests for code-quality NIT fixes
# ---------------------------------------------------------------------------


def test_compute_decile_sort_all_identical_scores() -> None:
    """Modern pandas (3.0+) does NOT raise on all-identical-score qcut;
    it returns an all-NaN coded series. The aggregator must detect this
    and fall back to a single bucket so downstream int() coercion does
    not crash mid-notebook."""
    df = pd.DataFrame(
        {"rr_score": [3.0] * 20, "excess_12m": [s * 0.01 for s in range(20)]}
    )
    res = compute_decile_sort(df, n_buckets=10)
    assert res.n_buckets == 1
    assert res.top_minus_bottom_spread is None
    assert res.buckets[0]["n"] == 20
    assert res.buckets[0]["mean_score"] == 3.0


def test_compute_ic_rejects_string_score_column() -> None:
    """A string score column would otherwise silently produce a
    perfect-correlation lexicographic rank match. pd.to_numeric coerces
    non-numeric values to NaN so the rank is computed only on numeric
    rows; string-only inputs collapse to n=0."""
    df = pd.DataFrame(
        {"rr_score": ["a", "b", "c", "d", "e"], "excess_3m": [0.1, 0.2, 0.3, 0.4, 0.5]}
    )
    res = compute_ic(df)
    # String column coerces to all-NaN, dropna leaves n=0, rho=None.
    assert res.spearman_rho is None
    assert res.n == 0


def test_compute_ic_silences_numpy_runtime_warnings() -> None:
    """Zero-variance score columns trigger a numpy 'invalid value
    encountered in divide' RuntimeWarning before .corr() returns NaN.
    The wrapper warnings.catch_warnings should suppress that noise so
    notebooks/CLI don't show cosmetic warnings on every degenerate
    cohort."""
    import warnings as _warnings

    df = pd.DataFrame(
        {"rr_score": [5.0] * 10, "excess_3m": list(range(10))}
    )
    with _warnings.catch_warnings(record=True) as caught:
        _warnings.simplefilter("always")
        res = compute_ic(df)
    runtime_warnings = [w for w in caught if issubclass(w.category, RuntimeWarning)]
    assert runtime_warnings == [], (
        f"Expected no RuntimeWarning leakage, got: "
        f"{[str(w.message) for w in runtime_warnings]}"
    )
    assert res.spearman_rho is None  # zero-variance → undefined
