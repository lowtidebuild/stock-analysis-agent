"""Tests for tools/backtest_runner.py subcommand structure (Task 6.1).

The runner exposes four subcommands:

- ``collect``    — runs ``BatchRunner`` (data collection only).
- ``outcomes``   — computes ``_outcome.json`` per ticker dir.
- ``aggregate``  — joins outcomes + analysis into ``results.jsonl``.
- ``all``        — runs collect → outcomes → aggregate sequentially.

A backwards-compat shim accepts the legacy ``--cohort`` shape (no
subcommand) and routes it to ``collect``.

Run via: ``python -m pytest tests/backtest/test_backtest_runner_subcommands.py -v``
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import pathlib
import subprocess
import sys
import unittest

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
CLI = ROOT / "tools" / "backtest_runner.py"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# CLI driver
# ---------------------------------------------------------------------------


def _run_cli(
    *args: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env=full_env,
    )


# ---------------------------------------------------------------------------
# Fixture helpers — build a minimal cohort tree on disk
# ---------------------------------------------------------------------------


def _seed_cohort_tree(
    data_dir: pathlib.Path,
    *,
    cohort_id: str = "smoke",
    tickers: tuple[str, ...] = ("AAPL",),
    as_of: _dt.date = _dt.date(2025, 3, 31),
    market: str = "US",
    write_outcome: bool = False,
    write_analysis: bool = True,
) -> pathlib.Path:
    """Pre-stage a cohort tree under ``$STOCK_ANALYSIS_DATA_DIR``.

    Mirrors what BatchRunner produces: ``runs/{ticker}/_backtest-meta.json``,
    optional ``analysis-result.json`` (used by aggregate), and optional
    ``_outcome.json`` (used by aggregate when present).
    """
    cohort_root = data_dir / "backtest" / "cohorts" / cohort_id
    runs_dir = cohort_root / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)

    for t in tickers:
        d = runs_dir / t
        d.mkdir(parents=True, exist_ok=True)
        meta = {
            "cohort_id": cohort_id,
            "ticker": t,
            "as_of": as_of.isoformat(),
            "market": market,
            "started_at": "2025-03-31T00:00:00+00:00",
            "freeze_strategy": "hybrid",
            "run_id": f"20250331T000000Z_{t}_backtest_{as_of.isoformat()}",
        }
        (d / "_backtest-meta.json").write_text(
            json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        if write_analysis:
            analysis = {
                "ticker": t,
                "verdict": "Buy",
                "rr_score": 2.5,
            }
            (d / "analysis-result.json").write_text(
                json.dumps(analysis, indent=2) + "\n", encoding="utf-8"
            )
        if write_outcome:
            outcome = {
                "ticker": t,
                "market": market,
                "as_of": as_of.isoformat(),
                "benchmark": "SPY" if market == "US" else "KOSPI",
                "ticker_close_at_as_of": 100.0,
                "actual_as_of_date": as_of.isoformat(),
                "horizons": {
                    "1m": {
                        "target_date": "2025-04-30",
                        "actual_date": "2025-04-30",
                        "ticker_close": 105.0,
                        "ticker_return": 0.05,
                        "benchmark_close": 480.0,
                        "benchmark_return": 0.02,
                        "excess_return": 0.03,
                    },
                    "3m": {
                        "target_date": "2025-06-30",
                        "actual_date": None,
                        "ticker_close": None,
                        "ticker_return": None,
                        "benchmark_close": None,
                        "benchmark_return": None,
                        "excess_return": None,
                        "_status": "data_unavailable",
                    },
                    "6m": {
                        "target_date": "2025-09-30",
                        "actual_date": None,
                        "ticker_close": None,
                        "ticker_return": None,
                        "benchmark_close": None,
                        "benchmark_return": None,
                        "excess_return": None,
                        "_status": "data_unavailable",
                    },
                    "12m": {
                        "target_date": "2026-03-31",
                        "actual_date": None,
                        "ticker_close": None,
                        "ticker_return": None,
                        "benchmark_close": None,
                        "benchmark_return": None,
                        "excess_return": None,
                        "_status": "data_unavailable",
                    },
                },
            }
            (d / "_outcome.json").write_text(
                json.dumps(outcome, indent=2) + "\n", encoding="utf-8"
            )
    return cohort_root


def _make_benchmark_cache(path: pathlib.Path) -> None:
    """Write a tiny but complete benchmark cache JSONL with all 3 series."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    base = _dt.date(2025, 3, 1)
    # Cover Mar 2025 → Apr 2026 lightly, every day.
    for offset in range(420):
        d = base + _dt.timedelta(days=offset)
        for bench, close in (("SPY", 500.0), ("QQQ", 480.0), ("KOSPI", 2580.0)):
            rows.append(
                {"benchmark": bench, "close": close + offset * 0.01, "date": d.isoformat()}
            )
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, sort_keys=True) + "\n")


# ===========================================================================
# Subcommand routing
# ===========================================================================


def test_collect_subcommand_works() -> None:
    """`collect --cohort smoke --dry-run` exits 0 and prints JSON payload."""
    result = _run_cli("collect", "--cohort", "smoke", "--as-of", "2025-03-31", "--dry-run")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["cohort"] == "smoke"
    assert payload["as_of"] == "2025-03-31"
    assert payload["dry_run"] is True


def test_outcomes_subcommand_works(tmp_path: pathlib.Path) -> None:
    """`outcomes --cohort X --allow-fixture` runs end-to-end on a seeded tree."""
    _seed_cohort_tree(tmp_path, cohort_id="smoke", tickers=("AAPL",))
    # Use the repo's shipped fixture (the cohort dir we seeded under tmp
    # uses --allow-fixture so we don't need a real benchmark cache).
    result = _run_cli(
        "outcomes",
        "--cohort", "smoke",
        "--allow-fixture",
        env={"STOCK_ANALYSIS_DATA_DIR": str(tmp_path)},
    )
    # Even if forward prices are unavailable for the fixture date, the
    # subcommand should not crash — it logs failures and exits 1 (best-
    # effort batch). Ensure the summary line was printed.
    assert "cohort=smoke" in result.stdout, result.stdout + result.stderr
    assert "done=" in result.stdout
    assert "failed=" in result.stdout
    assert "skipped=" in result.stdout
    assert result.returncode in (0, 1)


def test_aggregate_subcommand_works(tmp_path: pathlib.Path) -> None:
    """`aggregate --cohort X` writes results.jsonl with one row per ticker."""
    cohort_root = _seed_cohort_tree(
        tmp_path,
        cohort_id="smoke",
        tickers=("AAPL",),
        write_outcome=True,
        write_analysis=True,
    )
    result = _run_cli(
        "aggregate",
        "--cohort", "smoke",
        env={"STOCK_ANALYSIS_DATA_DIR": str(tmp_path)},
    )
    assert result.returncode == 0, result.stderr
    out_path = cohort_root / "results.jsonl"
    assert out_path.exists()
    assert "cohort=smoke" in result.stdout
    assert "rows=1" in result.stdout
    assert "output=" in result.stdout
    parsed = [json.loads(line) for line in out_path.read_text().strip().split("\n")]
    assert parsed[0]["ticker"] == "AAPL"
    assert parsed[0]["outcome_present"] is True
    assert parsed[0]["analysis_present"] is True


def test_all_subcommand_chains_collect_outcomes_aggregate(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`all --cohort smoke --dry-run` runs collect (dry-run) then short-
    circuits the subsequent steps because no actual data was written."""
    # Use --dry-run so collect is a no-op (no real network calls). The
    # subsequent outcomes/aggregate steps run on empty trees but must
    # not crash. This validates the chaining contract.
    monkeypatch.setenv("STOCK_ANALYSIS_DATA_DIR", str(tmp_path))
    result = _run_cli(
        "all",
        "--cohort", "smoke",
        "--as-of", "2025-03-31",
        "--dry-run",
        "--allow-fixture",
        env={"STOCK_ANALYSIS_DATA_DIR": str(tmp_path)},
    )
    # In dry-run mode, only the dry-run JSON is printed; the chain still
    # ran without error. We don't assert exit code 0 strictly because
    # outcomes on an empty tree is a no-op (0 done, 0 failed) and
    # aggregate writes an empty results.jsonl (0 rows).
    assert result.returncode == 0, result.stderr
    # The dry-run JSON from collect should appear in stdout.
    assert "smoke" in result.stdout


# ===========================================================================
# Backwards compatibility
# ===========================================================================


def test_legacy_cli_shape_falls_back_to_collect() -> None:
    """Old CLI shape (no subcommand, just --cohort X) routes to `collect`."""
    result = _run_cli("--cohort", "smoke", "--as-of", "2025-03-31", "--dry-run")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["cohort"] == "smoke"
    assert payload["as_of"] == "2025-03-31"
    # Deprecation hint in stderr (so it doesn't pollute machine-parseable
    # stdout).
    assert (
        "deprecat" in result.stderr.lower()
        or "legacy" in result.stderr.lower()
        or "collect" in result.stderr.lower()
    ), result.stderr


# ===========================================================================
# Help text
# ===========================================================================


def test_help_lists_all_subcommands() -> None:
    result = _run_cli("--help")
    assert result.returncode == 0, result.stderr
    out = result.stdout.lower()
    for sub in ("collect", "outcomes", "aggregate", "all"):
        assert sub in out, f"missing subcommand {sub!r} in --help output"


def test_per_subcommand_help_works() -> None:
    for sub in ("collect", "outcomes", "aggregate", "all"):
        result = _run_cli(sub, "--help")
        assert result.returncode == 0, f"{sub} --help failed: {result.stderr}"
        assert "--cohort" in result.stdout, (
            f"{sub} --help missing --cohort flag: {result.stdout}"
        )


# ===========================================================================
# outcomes subcommand specifics
# ===========================================================================


def test_outcomes_skips_existing_outcome_json_by_default(
    tmp_path: pathlib.Path,
) -> None:
    """If _outcome.json already exists, the default skip-existing path
    must not recompute (we detect this by checking the summary's
    skipped count)."""
    _seed_cohort_tree(
        tmp_path,
        cohort_id="smoke",
        tickers=("AAPL",),
        write_outcome=True,
    )
    result = _run_cli(
        "outcomes",
        "--cohort", "smoke",
        "--allow-fixture",
        env={"STOCK_ANALYSIS_DATA_DIR": str(tmp_path)},
    )
    assert result.returncode == 0, result.stderr
    assert "skipped=1" in result.stdout
    assert "done=0" in result.stdout
    assert "failed=0" in result.stdout


def test_outcomes_no_skip_existing_recomputes(tmp_path: pathlib.Path) -> None:
    """`--no-skip-existing` forces recomputation even when _outcome.json
    is already on disk."""
    _seed_cohort_tree(
        tmp_path,
        cohort_id="smoke",
        tickers=("AAPL",),
        write_outcome=True,
    )
    bench_path = tmp_path / "bench.jsonl"
    _make_benchmark_cache(bench_path)
    result = _run_cli(
        "outcomes",
        "--cohort", "smoke",
        "--no-skip-existing",
        "--benchmark-cache", str(bench_path),
        env={"STOCK_ANALYSIS_DATA_DIR": str(tmp_path)},
    )
    # Either succeeds (done=1) or fails because yfinance is unmocked
    # (failed=1) — but never skipped, since we explicitly disabled it.
    assert "skipped=0" in result.stdout, result.stdout + result.stderr


def test_outcomes_handles_forward_price_unavailable_per_ticker(
    tmp_path: pathlib.Path,
) -> None:
    """One ticker failing must not abort the rest — best-effort batch."""
    _seed_cohort_tree(
        tmp_path,
        cohort_id="smoke",
        tickers=("AAPL", "MSFT"),
        write_outcome=False,
    )
    bench_path = tmp_path / "bench.jsonl"
    _make_benchmark_cache(bench_path)
    result = _run_cli(
        "outcomes",
        "--cohort", "smoke",
        "--benchmark-cache", str(bench_path),
        env={"STOCK_ANALYSIS_DATA_DIR": str(tmp_path)},
    )
    # Both tickers will fail (no real yfinance data for these dates with
    # the dummy fetcher path), but the summary must include both in
    # done+failed and exit code 1 (any ticker failed).
    assert "cohort=smoke" in result.stdout
    # done + failed should equal 2 — we don't care which is which, only
    # that we processed both rather than aborting on the first.
    summary = result.stdout
    # Parse the trailing "done=N failed=M skipped=K" tokens.
    tokens = {
        kv.split("=")[0]: int(kv.split("=")[1])
        for kv in summary.split()
        if "=" in kv and kv.split("=")[0] in ("done", "failed", "skipped")
    }
    assert tokens["done"] + tokens["failed"] == 2, summary


def test_outcomes_exits_2_when_no_benchmark_cache_and_no_fixture(
    tmp_path: pathlib.Path,
) -> None:
    """If the user gives a missing --benchmark-cache path and does NOT
    pass --allow-fixture, the subcommand exits 2 with a helpful message."""
    _seed_cohort_tree(tmp_path, cohort_id="smoke", tickers=("AAPL",))
    bogus_cache = tmp_path / "no_such_cache.jsonl"
    result = _run_cli(
        "outcomes",
        "--cohort", "smoke",
        "--benchmark-cache", str(bogus_cache),
        env={"STOCK_ANALYSIS_DATA_DIR": str(tmp_path)},
    )
    assert result.returncode == 2, result.stdout + result.stderr
    msg = (result.stderr + result.stdout).lower()
    # Must mention how to remediate (build the cache) or the fixture flag.
    assert "benchmark" in msg or "cache" in msg or "fixture" in msg


def test_outcomes_uses_fixture_with_allow_fixture_flag(
    tmp_path: pathlib.Path,
) -> None:
    """With --allow-fixture and no real cache present, outcomes loads
    the shipped fixture and proceeds (exit 0 or 1, never 2)."""
    _seed_cohort_tree(tmp_path, cohort_id="smoke", tickers=("AAPL",))
    # Point --benchmark-cache at a missing path and toggle --allow-fixture.
    bogus_cache = tmp_path / "no_such_cache.jsonl"
    result = _run_cli(
        "outcomes",
        "--cohort", "smoke",
        "--benchmark-cache", str(bogus_cache),
        "--allow-fixture",
        env={"STOCK_ANALYSIS_DATA_DIR": str(tmp_path)},
    )
    # Exit 2 would mean the fixture fallback failed.
    assert result.returncode in (0, 1), result.stdout + result.stderr
    assert "cohort=smoke" in result.stdout


# ===========================================================================
# aggregate subcommand specifics
# ===========================================================================


def test_aggregate_writes_results_jsonl(tmp_path: pathlib.Path) -> None:
    cohort_root = _seed_cohort_tree(
        tmp_path,
        cohort_id="smoke",
        tickers=("AAPL", "MSFT"),
        write_outcome=True,
        write_analysis=True,
    )
    result = _run_cli(
        "aggregate",
        "--cohort", "smoke",
        env={"STOCK_ANALYSIS_DATA_DIR": str(tmp_path)},
    )
    assert result.returncode == 0, result.stderr
    out_path = cohort_root / "results.jsonl"
    assert out_path.exists()
    # Two lines, one per ticker, sorted alphabetically.
    lines = out_path.read_text().strip().split("\n")
    assert len(lines) == 2
    parsed = [json.loads(line) for line in lines]
    assert [p["ticker"] for p in parsed] == ["AAPL", "MSFT"]
    assert "rows=2" in result.stdout


def test_aggregate_handles_empty_cohort(tmp_path: pathlib.Path) -> None:
    """Cohort with no runs/ subdir should write an empty results.jsonl
    and exit 0 (not crash)."""
    cohort_root = tmp_path / "backtest" / "cohorts" / "empty"
    cohort_root.mkdir(parents=True, exist_ok=True)
    result = _run_cli(
        "aggregate",
        "--cohort", "empty",
        env={"STOCK_ANALYSIS_DATA_DIR": str(tmp_path)},
    )
    assert result.returncode == 0, result.stderr
    assert "rows=0" in result.stdout
    out_path = cohort_root / "results.jsonl"
    assert out_path.exists()
    assert out_path.read_text() == ""


# ---------------------------------------------------------------------------
# Regression tests for code-quality NIT fixes
# ---------------------------------------------------------------------------


def test_collect_rejects_negative_max_workers_with_argparse_error(
    tmp_path: pathlib.Path,
) -> None:
    """Argparse should bounce --max-workers -3 at the boundary so the
    operator sees a clean exit-2 message instead of a Python traceback
    bubbling out of BatchRunner.__init__."""
    result = _run_cli(
        "collect", "--cohort", "smoke", "--max-workers", "-3",
        env={"STOCK_ANALYSIS_DATA_DIR": str(tmp_path)},
    )
    assert result.returncode == 2, result.stdout + result.stderr
    assert "Traceback" not in result.stderr
    assert ">= 1" in result.stderr or "positive" in result.stderr.lower()


def test_collect_rejects_zero_max_workers(tmp_path: pathlib.Path) -> None:
    result = _run_cli(
        "collect", "--cohort", "smoke", "--max-workers", "0",
        env={"STOCK_ANALYSIS_DATA_DIR": str(tmp_path)},
    )
    assert result.returncode == 2, result.stdout + result.stderr
    assert "Traceback" not in result.stderr


def test_outcomes_uses_warn_prefix_for_missing_manifest(
    tmp_path: pathlib.Path,
) -> None:
    """outcomes treats the manifest as best-effort. Misleading 'ERROR:'
    prefix at 11pm wastes operator time investigating a non-issue —
    use 'WARN:' for non-fatal manifest problems."""
    # Seed a cohort tree but don't add the cohort to evals/backtest/cohorts.
    cohort_root = tmp_path / "backtest" / "cohorts" / "no_manifest_cohort"
    cohort_root.mkdir(parents=True, exist_ok=True)
    (cohort_root / "runs").mkdir()
    result = _run_cli(
        "outcomes", "--cohort", "no_manifest_cohort", "--allow-fixture",
        env={"STOCK_ANALYSIS_DATA_DIR": str(tmp_path)},
    )
    # Best-effort: empty runs/ → exit 0, but the warning appears.
    assert "WARN:" in result.stderr or result.returncode == 0
    assert "ERROR:" not in result.stderr


def test_outcomes_fails_loud_on_unknown_market(tmp_path: pathlib.Path) -> None:
    """When the manifest is missing AND _backtest-meta.json has no
    market field, outcomes must NOT silently default to 'US' — that
    would corrupt KR ticker analysis. Mark the ticker as failed and
    print a clear FAIL: message."""
    cohort_root = tmp_path / "backtest" / "cohorts" / "no_market_cohort"
    runs_dir = cohort_root / "runs"
    aapl_dir = runs_dir / "AAPL"
    aapl_dir.mkdir(parents=True)
    # Meta without market field — what BacktestContext.write_meta()
    # produces today.
    meta = {
        "cohort_id": "no_market_cohort",
        "ticker": "AAPL",
        "as_of": "2025-03-31",
        "started_at": "2025-04-01T00:00:00+00:00",
        "freeze_strategy": "hybrid",
        "run_id": "AAPL_2025-03-31",
    }
    (aapl_dir / "_backtest-meta.json").write_text(
        json.dumps(meta), encoding="utf-8"
    )

    result = _run_cli(
        "outcomes", "--cohort", "no_market_cohort", "--allow-fixture",
        env={"STOCK_ANALYSIS_DATA_DIR": str(tmp_path)},
    )
    # Should not silently default to "US" and produce an outcome file.
    assert not (aapl_dir / "_outcome.json").exists()
    assert "cannot resolve market" in result.stderr or "FAIL: AAPL" in result.stderr
    # 1 ticker failed → exit 1.
    assert result.returncode == 1, result.stdout + result.stderr


def test_all_with_dry_run_short_circuits_after_collect(
    tmp_path: pathlib.Path,
) -> None:
    """`all --dry-run` should NOT proceed to outcomes (which would call
    yfinance) or aggregate (which would write results.jsonl). The
    conventional --dry-run contract is 'no externally observable side
    effects'."""
    # Seed a cohort tree so outcomes/aggregate WOULD have something
    # to do — ensures the short-circuit is what's stopping them, not
    # an empty cohort.
    cohort_root = tmp_path / "backtest" / "cohorts" / "smoke"
    runs_dir = cohort_root / "runs"
    aapl_dir = runs_dir / "AAPL"
    aapl_dir.mkdir(parents=True)
    meta = {
        "cohort_id": "smoke",
        "ticker": "AAPL",
        "as_of": "2025-03-31",
        "started_at": "2025-04-01T00:00:00+00:00",
        "freeze_strategy": "hybrid",
        "run_id": "AAPL_2025-03-31",
        "market": "US",
    }
    (aapl_dir / "_backtest-meta.json").write_text(
        json.dumps(meta), encoding="utf-8"
    )

    result = _run_cli(
        "all", "--cohort", "smoke", "--dry-run", "--allow-fixture",
        env={"STOCK_ANALYSIS_DATA_DIR": str(tmp_path)},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    # Collect's dry-run JSON is the only output — no outcomes/aggregate
    # summary lines should appear.
    assert "dry_run" in result.stdout
    assert "rows=" not in result.stdout  # aggregate did not run
    # Definitive: no _outcome.json or results.jsonl was written.
    assert not (aapl_dir / "_outcome.json").exists()
    assert not (cohort_root / "results.jsonl").exists()


if __name__ == "__main__":
    unittest.main()
