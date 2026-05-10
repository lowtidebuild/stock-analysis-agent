# Backtest Smoke Test Results

> Single-line summary of the most recent smoke test (1 ticker × 4
> horizons). Overwritten / appended each time §1 of the procedure runs.
> See `reports/2026-05-08-phase1-procedure.md` for the recipe.

## Most recent run

(append a one-liner per row — newest at the top)

| Date | Cohort | Ticker | as_of | return_12m | excess_12m | Notes |
|------|--------|--------|-------|------------|------------|-------|
| 2026-05-10 | smoke | AAPL | 2025-03-31 | +14.25% | -2.01% | Benchmark=SPY (default, no --prefer-qqq). All 4 horizons clean, leakage 0. |

## First-run details (2026-05-10)

**Command:** `python tools/backtest_runner.py all --cohort smoke`

**Outputs:**

```
cohort=smoke as_of=2025-03-31 done=1 failed=0 skipped=0 pending=0 running=0 total_bytes=68591
cohort=smoke done=1 failed=0 skipped=0
cohort=smoke rows=1 output=output/backtest/cohorts/smoke/results.jsonl
```

**Per-horizon (AAPL, ticker_close_at_as_of=$222.13, benchmark=SPY):**

| Horizon | Ticker return | Benchmark (SPY) return | Excess |
|---------|--------------|------------------------|--------|
| 1M  | -4.34% | -0.87% | -3.47% |
| 3M  | -7.64% | +10.45% | -18.09% |
| 6M  | +14.63% | +19.09% | -4.46% |
| 12M | +14.25% | +16.26% | -2.01% |

**Reading:** AAPL underperformed SPY meaningfully at the 3M mark (likely
the post-Q1-2025 tariff-uncertainty selloff), recovered into 6M, and
ended the 12-month window down ~2% in excess terms. This is a **single
data point**, not a signal — but it confirms the wire-up works
end-to-end on real network data.

## Status

- Smoke test infrastructure: **WIRED** (`python tools/backtest_runner.py all --cohort smoke`)
- First successful smoke run: ✅ **DONE 2026-05-10** (see row + table above)

## What "successful smoke" means

All four horizons (1m / 3m / 6m / 12m) populated in
`output/backtest/cohorts/smoke/runs/AAPL/_outcome.json` AND
`results.jsonl` has exactly 1 row AND `_outcome.json.horizons.12m`
does NOT have `_status: data_unavailable`.

If the smoke run produces 12m data_unavailable, the benchmark cache
window probably ends before 2026-03-31. Rebuild it:

```bash
python evals/backtest/scripts/cache-benchmarks.py \
  --start 2024-01-01 --end 2026-05-09 \
  --output evals/backtest/data/benchmark-prices.jsonl
```
