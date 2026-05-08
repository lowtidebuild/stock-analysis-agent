"""Tests for the cohort aggregator (Task 4.3).

Covers Task 4.3 of the backtest harness plan
(``docs/superpowers/plans/2026-05-08-backtest-harness.md``):

- ``load_outcome`` / ``load_analysis_result`` — robust JSON loaders that
  return ``None`` on missing files but raise on malformed content.
- ``build_row`` — pure function that joins one outcome dict with one
  analysis dict, defensive against varied production schemas.
- ``aggregate_cohort`` — walks the cohort ``runs/`` directory.
- ``write_results_jsonl`` / ``aggregate_and_write`` — atomic JSONL
  persistence sorted by ticker.

Run via: ``python -m pytest tests/backtest/test_cohort_aggregator.py -v``
"""

from __future__ import annotations

import datetime as _dt
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.backtest.cohort_aggregator import (  # noqa: E402
    CohortAggregatorError,
    CohortRow,
    aggregate_and_write,
    aggregate_cohort,
    build_row,
    load_analysis_result,
    load_outcome,
    write_results_jsonl,
)
from tools.backtest.cohort_manifest import CohortManifest, TickerEntry  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _full_outcome(ticker: str = "AAPL") -> dict:
    """Outcome dict where all 4 horizons are populated cleanly."""
    return {
        "ticker": ticker,
        "market": "US",
        "as_of": "2025-03-31",
        "benchmark": "QQQ",
        "ticker_close_at_as_of": 207.42,
        "horizons": {
            "1m": {
                "target_date": "2025-04-30",
                "actual_date": "2025-04-30",
                "ticker_close": 213.41,
                "ticker_return": 0.0289,
                "benchmark_close": 480.5,
                "benchmark_return": 0.0142,
                "excess_return": 0.0147,
            },
            "3m": {
                "target_date": "2025-06-30",
                "actual_date": "2025-06-30",
                "ticker_close": 225.0,
                "ticker_return": 0.0848,
                "benchmark_close": 495.0,
                "benchmark_return": 0.0444,
                "excess_return": 0.0404,
            },
            "6m": {
                "target_date": "2025-09-30",
                "actual_date": "2025-09-30",
                "ticker_close": 240.0,
                "ticker_return": 0.157,
                "benchmark_close": 510.0,
                "benchmark_return": 0.0760,
                "excess_return": 0.0810,
            },
            "12m": {
                "target_date": "2026-03-31",
                "actual_date": "2026-03-31",
                "ticker_close": 260.0,
                "ticker_return": 0.2535,
                "benchmark_close": 540.0,
                "benchmark_return": 0.1404,
                "excess_return": 0.1131,
            },
        },
    }


def _outcome_with_unavailable_12m() -> dict:
    out = _full_outcome()
    out["horizons"]["12m"] = {
        "target_date": "2026-03-31",
        "actual_date": None,
        "ticker_close": None,
        "ticker_return": None,
        "benchmark_close": None,
        "benchmark_return": None,
        "excess_return": None,
        "_status": "data_unavailable",
    }
    return out


def _full_analysis() -> dict:
    return {
        "ticker": "AAPL",
        "verdict": "Buy",
        "rr_score": 2.5,
        "scenarios": {
            "bull": {"target": 250.0},
            "base": {"target": 220.0},
            "bear": {"target": 180.0},
        },
    }


def _make_meta(d: _dt.date) -> dict:
    return {
        "cohort_id": "test_cohort",
        "ticker": "AAPL",
        "as_of": d.isoformat(),
        "started_at": "2026-05-09T00:00:00+00:00",
        "freeze_strategy": "hybrid",
        "run_id": "20260509T000000Z_AAPL_backtest_2025-03-31",
    }


# ---------------------------------------------------------------------------
# Loader tests
# ---------------------------------------------------------------------------


def test_load_outcome_returns_none_when_missing(tmp_path: pathlib.Path) -> None:
    assert load_outcome(tmp_path / "nope.json") is None


def test_load_outcome_raises_on_malformed_json(tmp_path: pathlib.Path) -> None:
    p = tmp_path / "_outcome.json"
    p.write_text("{not json", encoding="utf-8")
    with pytest.raises(CohortAggregatorError):
        load_outcome(p)


def test_load_analysis_result_returns_none_when_missing(
    tmp_path: pathlib.Path,
) -> None:
    assert load_analysis_result(tmp_path / "missing.json") is None


def test_load_analysis_result_raises_on_malformed_json(
    tmp_path: pathlib.Path,
) -> None:
    p = tmp_path / "analysis-result.json"
    p.write_text("not even close to json", encoding="utf-8")
    with pytest.raises(CohortAggregatorError):
        load_analysis_result(p)


# ---------------------------------------------------------------------------
# build_row tests
# ---------------------------------------------------------------------------


def test_build_row_with_full_data() -> None:
    row = build_row(
        ticker="AAPL",
        cohort_id="test",
        as_of=_dt.date(2025, 3, 31),
        market="US",
        outcome=_full_outcome(),
        analysis=_full_analysis(),
    )
    assert row.ticker == "AAPL"
    assert row.cohort_id == "test"
    assert row.as_of == "2025-03-31"
    assert row.market == "US"
    assert row.benchmark == "QQQ"
    assert row.verdict == "Buy"
    assert row.rr_score == 2.5
    assert row.target_base == 220.0
    assert row.target_bull == 250.0
    assert row.target_bear == 180.0
    assert row.return_1m == pytest.approx(0.0289)
    assert row.return_12m == pytest.approx(0.2535)
    assert row.excess_1m == pytest.approx(0.0147)
    assert row.excess_12m == pytest.approx(0.1131)
    assert row.outcome_status == {}
    assert row.analysis_present is True
    assert row.outcome_present is True


def test_build_row_outcome_only() -> None:
    row = build_row(
        ticker="AAPL",
        cohort_id="test",
        as_of=_dt.date(2025, 3, 31),
        market="US",
        outcome=_full_outcome(),
        analysis=None,
    )
    assert row.verdict is None
    assert row.rr_score is None
    assert row.target_base is None
    assert row.target_bull is None
    assert row.target_bear is None
    assert row.return_1m == pytest.approx(0.0289)
    assert row.analysis_present is False
    assert row.outcome_present is True


def test_build_row_analysis_only() -> None:
    row = build_row(
        ticker="AAPL",
        cohort_id="test",
        as_of=_dt.date(2025, 3, 31),
        market="US",
        outcome=None,
        analysis=_full_analysis(),
    )
    assert row.verdict == "Buy"
    assert row.rr_score == 2.5
    assert row.return_1m is None
    assert row.return_3m is None
    assert row.excess_12m is None
    assert row.benchmark is None
    assert row.outcome_status == {}
    assert row.analysis_present is True
    assert row.outcome_present is False


def test_build_row_neither() -> None:
    row = build_row(
        ticker="AAPL",
        cohort_id="test",
        as_of=_dt.date(2025, 3, 31),
        market="US",
        outcome=None,
        analysis=None,
    )
    assert row.verdict is None
    assert row.rr_score is None
    assert row.target_base is None
    assert row.return_1m is None
    assert row.excess_12m is None
    assert row.benchmark is None
    assert row.analysis_present is False
    assert row.outcome_present is False


def test_build_row_data_unavailable_horizon_records_status() -> None:
    row = build_row(
        ticker="AAPL",
        cohort_id="test",
        as_of=_dt.date(2025, 3, 31),
        market="US",
        outcome=_outcome_with_unavailable_12m(),
        analysis=None,
    )
    assert row.return_12m is None
    assert row.excess_12m is None
    # 1m / 3m / 6m still populated
    assert row.return_1m == pytest.approx(0.0289)
    assert row.return_3m == pytest.approx(0.0848)
    assert row.return_6m == pytest.approx(0.157)
    assert row.outcome_status == {"12m": "data_unavailable"}


def test_build_row_handles_verdict_string() -> None:
    row = build_row(
        ticker="AAPL",
        cohort_id="t",
        as_of=_dt.date(2025, 3, 31),
        market="US",
        outcome=None,
        analysis={"verdict": "Hold"},
    )
    assert row.verdict == "Hold"


def test_build_row_handles_verdict_dict() -> None:
    row = build_row(
        ticker="AAPL",
        cohort_id="t",
        as_of=_dt.date(2025, 3, 31),
        market="US",
        outcome=None,
        analysis={"verdict": {"label": "비중확대"}},
    )
    assert row.verdict == "비중확대"


def test_build_row_handles_rr_score_dict() -> None:
    row = build_row(
        ticker="AAPL",
        cohort_id="t",
        as_of=_dt.date(2025, 3, 31),
        market="US",
        outcome=None,
        analysis={"rr_score": {"value": 1.8}},
    )
    assert row.rr_score == 1.8


def test_build_row_handles_alternate_target_paths() -> None:
    # Path A: top-level "target_base" / "target_bull" / "target_bear"
    row_a = build_row(
        ticker="AAPL",
        cohort_id="t",
        as_of=_dt.date(2025, 3, 31),
        market="US",
        outcome=None,
        analysis={"target_base": 100.0, "target_bull": 130.0, "target_bear": 70.0},
    )
    assert row_a.target_base == 100.0
    assert row_a.target_bull == 130.0
    assert row_a.target_bear == 70.0

    # Path B: nested under "targets"
    row_b = build_row(
        ticker="AAPL",
        cohort_id="t",
        as_of=_dt.date(2025, 3, 31),
        market="US",
        outcome=None,
        analysis={"targets": {"base": 110.0, "bull": 140.0, "bear": 80.0}},
    )
    assert row_b.target_base == 110.0
    assert row_b.target_bull == 140.0
    assert row_b.target_bear == 80.0

    # Path C: "valuation.target_price.{base,bull,bear}"
    row_c = build_row(
        ticker="AAPL",
        cohort_id="t",
        as_of=_dt.date(2025, 3, 31),
        market="US",
        outcome=None,
        analysis={
            "valuation": {
                "target_price": {"base": 120.0, "bull": 150.0, "bear": 90.0}
            }
        },
    )
    assert row_c.target_base == 120.0
    assert row_c.target_bull == 150.0
    assert row_c.target_bear == 90.0


def test_build_row_handles_production_scenarios_path() -> None:
    """Regression: real Mode C output uses scenarios.{bull,base,bear}.target."""
    row = build_row(
        ticker="GOOGL",
        cohort_id="t",
        as_of=_dt.date(2025, 3, 31),
        market="US",
        outcome=None,
        analysis={
            "scenarios": {
                "bull": {"target": 450.0},
                "base": {"target": 418.0},
                "bear": {"target": 290.0},
            }
        },
    )
    assert row.target_base == 418.0
    assert row.target_bull == 450.0
    assert row.target_bear == 290.0


def test_build_row_to_dict_round_trip() -> None:
    row = build_row(
        ticker="AAPL",
        cohort_id="test",
        as_of=_dt.date(2025, 3, 31),
        market="US",
        outcome=_full_outcome(),
        analysis=_full_analysis(),
    )
    d = row.to_dict()
    assert d["ticker"] == "AAPL"
    assert d["analysis_present"] is True
    assert d["outcome_present"] is True
    assert d["verdict"] == "Buy"
    assert d["return_1m"] == pytest.approx(0.0289)
    # Serializable
    json.dumps(d)


# ---------------------------------------------------------------------------
# aggregate_cohort tests
# ---------------------------------------------------------------------------


def _seed_ticker_dir(
    cohort_root: pathlib.Path,
    ticker: str,
    *,
    write_outcome: bool = True,
    write_analysis: bool = True,
    write_meta: bool = True,
    as_of: _dt.date = _dt.date(2025, 3, 31),
) -> pathlib.Path:
    d = cohort_root / "runs" / ticker
    d.mkdir(parents=True, exist_ok=True)
    if write_meta:
        meta = _make_meta(as_of)
        meta["ticker"] = ticker
        (d / "_backtest-meta.json").write_text(
            json.dumps(meta, indent=2) + "\n", encoding="utf-8"
        )
    if write_outcome:
        out = _full_outcome(ticker=ticker)
        out["as_of"] = as_of.isoformat()
        (d / "_outcome.json").write_text(
            json.dumps(out, indent=2) + "\n", encoding="utf-8"
        )
    if write_analysis:
        analysis = _full_analysis()
        analysis["ticker"] = ticker
        (d / "analysis-result.json").write_text(
            json.dumps(analysis, indent=2) + "\n", encoding="utf-8"
        )
    return d


def test_aggregate_cohort_walks_runs_dir(tmp_path: pathlib.Path) -> None:
    cohort_root = tmp_path / "cohort_x"
    for t in ("AAPL", "MSFT", "GOOGL"):
        _seed_ticker_dir(cohort_root, t)

    rows = aggregate_cohort(cohort_id="cohort_x", cohort_root=cohort_root)
    assert len(rows) == 3
    tickers = sorted(r.ticker for r in rows)
    assert tickers == ["AAPL", "GOOGL", "MSFT"]
    for r in rows:
        assert r.outcome_present is True
        assert r.analysis_present is True


def test_aggregate_cohort_skips_dir_without_meta_or_outcome(
    tmp_path: pathlib.Path,
) -> None:
    cohort_root = tmp_path / "cohort_y"
    # Empty subdir → nothing to anchor as_of on, so we skip.
    (cohort_root / "runs" / "EMPTY").mkdir(parents=True, exist_ok=True)
    # Valid subdir
    _seed_ticker_dir(cohort_root, "AAPL")

    rows = aggregate_cohort(cohort_id="cohort_y", cohort_root=cohort_root)
    assert len(rows) == 1
    assert rows[0].ticker == "AAPL"


def test_aggregate_cohort_uses_manifest_when_provided(
    tmp_path: pathlib.Path,
) -> None:
    cohort_root = tmp_path / "cohort_m"
    # Seed with a stale (wrong) market in outcome by mutating after seed.
    d = _seed_ticker_dir(cohort_root, "AAPL")
    out = json.loads((d / "_outcome.json").read_text(encoding="utf-8"))
    out["market"] = "WRONG"
    (d / "_outcome.json").write_text(
        json.dumps(out, indent=2) + "\n", encoding="utf-8"
    )

    manifest = CohortManifest(
        cohort_id="cohort_m",
        as_of=_dt.date(2025, 3, 31),
        tickers=(TickerEntry(ticker="AAPL", market="US"),),
    )
    rows = aggregate_cohort(
        cohort_id="cohort_m", manifest=manifest, cohort_root=cohort_root
    )
    assert len(rows) == 1
    # Manifest market wins
    assert rows[0].market == "US"
    assert rows[0].as_of == "2025-03-31"


def test_aggregate_cohort_handles_missing_analysis(tmp_path: pathlib.Path) -> None:
    """Phase 1 expectation: Mode C analysis hasn't been run yet."""
    cohort_root = tmp_path / "cohort_p1"
    _seed_ticker_dir(cohort_root, "AAPL", write_analysis=False)
    rows = aggregate_cohort(cohort_id="cohort_p1", cohort_root=cohort_root)
    assert len(rows) == 1
    assert rows[0].analysis_present is False
    assert rows[0].outcome_present is True
    assert rows[0].verdict is None


def test_aggregate_cohort_skips_runs_dir_absent(tmp_path: pathlib.Path) -> None:
    """Cohort root exists but ``runs/`` does not — return [] (no crash)."""
    cohort_root = tmp_path / "cohort_empty"
    cohort_root.mkdir()
    rows = aggregate_cohort(cohort_id="cohort_empty", cohort_root=cohort_root)
    assert rows == []


# ---------------------------------------------------------------------------
# write_results_jsonl tests
# ---------------------------------------------------------------------------


def test_write_results_jsonl_atomic(tmp_path: pathlib.Path) -> None:
    rows = [
        build_row(
            ticker="AAPL",
            cohort_id="t",
            as_of=_dt.date(2025, 3, 31),
            market="US",
            outcome=_full_outcome(),
            analysis=_full_analysis(),
        )
    ]
    out_path = tmp_path / "results.jsonl"
    written = write_results_jsonl(rows=rows, output_path=out_path)
    assert written == out_path
    assert out_path.exists()
    # Tmp file must be cleaned up
    assert not (out_path.parent / "results.jsonl.tmp").exists()


def test_write_results_jsonl_sorted_by_ticker(tmp_path: pathlib.Path) -> None:
    rows = [
        build_row(
            ticker=t,
            cohort_id="t",
            as_of=_dt.date(2025, 3, 31),
            market="US",
            outcome=None,
            analysis=None,
        )
        for t in ("MSFT", "AAPL", "GOOGL")
    ]
    out_path = tmp_path / "results.jsonl"
    write_results_jsonl(rows=rows, output_path=out_path)
    lines = out_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 3
    parsed = [json.loads(line) for line in lines]
    assert [p["ticker"] for p in parsed] == ["AAPL", "GOOGL", "MSFT"]


def test_write_results_jsonl_one_object_per_line(tmp_path: pathlib.Path) -> None:
    rows = [
        build_row(
            ticker=t,
            cohort_id="t",
            as_of=_dt.date(2025, 3, 31),
            market="US",
            outcome=None,
            analysis=None,
        )
        for t in ("AAPL", "MSFT")
    ]
    out_path = tmp_path / "results.jsonl"
    write_results_jsonl(rows=rows, output_path=out_path)
    text = out_path.read_text(encoding="utf-8")
    # Each non-empty line parses as a complete JSON object.
    for line in text.splitlines():
        assert json.loads(line)


# ---------------------------------------------------------------------------
# aggregate_and_write convenience
# ---------------------------------------------------------------------------


def test_aggregate_and_write_smoke(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Override data dir to tmp_path so backtest_path() points here.
    monkeypatch.setenv("STOCK_ANALYSIS_DATA_DIR", str(tmp_path))
    cohort_id = "cohort_smoke"

    # tools.paths reads env var lazily inside data_dir(), but tools.backtest
    # imports may have cached the path. backtest_path() re-reads each call.
    cohort_root = tmp_path / "backtest" / "cohorts" / cohort_id
    for t in ("AAPL", "MSFT"):
        _seed_ticker_dir(cohort_root, t)

    manifest = CohortManifest(
        cohort_id=cohort_id,
        as_of=_dt.date(2025, 3, 31),
        tickers=(
            TickerEntry(ticker="AAPL", market="US"),
            TickerEntry(ticker="MSFT", market="US"),
        ),
    )
    out_path = aggregate_and_write(cohort_id=cohort_id, manifest=manifest)
    assert out_path.exists()
    assert out_path.name == "results.jsonl"
    lines = out_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2
    parsed = [json.loads(l) for l in lines]
    assert [p["ticker"] for p in parsed] == ["AAPL", "MSFT"]
    for p in parsed:
        assert p["analysis_present"] is True
        assert p["outcome_present"] is True


# ---------------------------------------------------------------------------
# Loader malformed-cohort coverage (defensive — aggregate must not crash other rows)
# ---------------------------------------------------------------------------


def test_aggregate_cohort_propagates_malformed_outcome(
    tmp_path: pathlib.Path,
) -> None:
    cohort_root = tmp_path / "cohort_bad"
    d = _seed_ticker_dir(cohort_root, "AAPL")
    (d / "_outcome.json").write_text("{bad json", encoding="utf-8")
    with pytest.raises(CohortAggregatorError):
        aggregate_cohort(cohort_id="cohort_bad", cohort_root=cohort_root)
