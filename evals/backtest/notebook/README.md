# Backtest Notebooks

Phase 1 analysis notebook for the backtest harness.

## Prerequisites

```bash
pip install pandas matplotlib jupyter
```

pandas 3.0+ is installed system-wide on the dev machine but is
NOT in `requirements.txt` (it's a heavyweight optional dep). The
metrics module (`tools/backtest/metrics.py`) requires pandas for
its DataFrame API; matplotlib is only needed by this notebook.

## Running

1. Run the cohort: `python tools/backtest_runner.py --cohort 2025Q1`
2. Compute outcomes (one-off Python snippet for Phase 1 — wired
   into the runner in Chunk 6):
   ```python
   # see Chunk 6 Task 6.1 smoke recipe in the plan
   ```
3. Aggregate results:
   ```python
   from tools.backtest.cohort_aggregator import aggregate_and_write
   aggregate_and_write(cohort_id="2025Q1")
   ```
4. Open `2026-05-08-phase1-results.ipynb` in Jupyter and Run All.
