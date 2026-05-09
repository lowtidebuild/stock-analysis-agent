# Backtest Smoke Test Results

> Single-line summary of the most recent smoke test (1 ticker × 4
> horizons). Overwritten / appended each time §1 of the procedure runs.
> See `reports/2026-05-08-phase1-procedure.md` for the recipe.

## Most recent run

(append a one-liner per row — newest at the top)

| Date | Cohort | Ticker | as_of | return_12m | excess_12m | Notes |
|------|--------|--------|-------|------------|------------|-------|
| _____ | smoke | AAPL | 2025-03-31 | _____ | _____ | _____ |

## Status

- Smoke test infrastructure: **WIRED** (`python tools/backtest_runner.py all --cohort smoke`)
- First successful smoke run: **PENDING** (operator runs §1 of the
  procedure, then fills in the row above)

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
