# Phase 1 Backtest — Operator Procedure

> Step-by-step recipe for running the first Phase 1 backtest cohort end
> to end. Anchor date: 2025-03-31. Universe: 30 US tickers (mega + large
> cap, see `evals/backtest/cohorts/2025Q1.json`).

**Today is 2026-05-09.** All forward windows up to 12M (target 2026-03-31)
are now realized — first Phase 1 should produce all four horizons cleanly.

## Prerequisites (one-time)

```bash
# Eval-layer Python deps (pandas + matplotlib). Not in requirements.txt
# because the production pipeline doesn't need them.
pip install pandas matplotlib jupyter
```

Optional but recommended:

- `FRED_API_KEY` exported (so the cohort fetches macro). Without it the
  collect step still runs; the `fred-raw.json` will be marked
  `data_unavailable`.
- DART API key in `.claude/settings.local.json` (only matters when the
  cohort includes KR tickers — Phase 1 is US-only).

## §1 — Smoke test (do this FIRST, every time)

Verifies the entire chain (collect → outcomes → aggregate) end to end on
a single ticker. Fast (~30 sec) and does NOT cost money.

```bash
# Build the benchmark price cache once. Reusable across cohorts.
python evals/backtest/scripts/cache-benchmarks.py \
  --start 2024-01-01 \
  --end 2026-05-09 \
  --output evals/backtest/data/benchmark-prices.jsonl

# Run the full chain on the smoke cohort (1 ticker = AAPL).
python tools/backtest_runner.py all --cohort smoke
```

Expected:

```
cohort=smoke as_of=2025-03-31 done=1 failed=0 skipped=0 ...
cohort=smoke done=1 failed=0 skipped=0
cohort=smoke rows=1 output=output/backtest/cohorts/smoke/results.jsonl
```

Verify the outputs:

```bash
ls output/backtest/cohorts/smoke/runs/AAPL/        # _backtest-meta.json + yfinance-raw.json + _outcome.json
cat output/backtest/cohorts/smoke/runs/AAPL/_outcome.json | jq .horizons.12m
cat output/backtest/cohorts/smoke/results.jsonl
```

If everything looks right, write the one-line smoke summary:

```bash
# Update ../smoke-results.md with the AAPL row.
python -c "
import json, pathlib
row = json.loads(pathlib.Path('output/backtest/cohorts/smoke/results.jsonl').read_text())
print(f\"Smoke: AAPL 2025-03-31 -> return_12m={row['return_12m']}, excess_12m={row['excess_12m']}\")
" >> evals/backtest/smoke-results.md
```

If smoke fails, investigate before kicking off the 30-ticker cohort.
Look at `output/backtest/cohorts/smoke/state.json` — the `failures[]`
list points at the first ticker that broke and why.

## §2 — Phase 1 cohort run (30 tickers)

Once smoke passes:

```bash
# Step 1 — data collection (yfinance + FRED). Parallel 5; ~18-30h
# wall-clock for 30 US tickers.
python tools/backtest_runner.py collect --cohort 2025Q1 --max-workers 5

# Step 2 — forward-outcome computation. Fast (<1 min for 30 tickers).
python tools/backtest_runner.py outcomes --cohort 2025Q1 --prefer-qqq

# Step 3 — aggregation into results.jsonl.
python tools/backtest_runner.py aggregate --cohort 2025Q1
```

Or in one command (chain auto-aborts on the first non-zero exit):

```bash
python tools/backtest_runner.py all --cohort 2025Q1 --prefer-qqq
```

### Resumability

The `collect` step writes `output/backtest/cohorts/2025Q1/state.json`
after every status transition. Re-running the same command resumes from
where it left off — DONE tickers are skipped, FAILED tickers are
retried. To force a fresh run, delete the cohort root:

```bash
rm -rf output/backtest/cohorts/2025Q1/
```

### Consecutive-failure abort

If 3 tickers in a row fail (default threshold), the runner aborts the
whole cohort and exits 1. This usually indicates a network outage or
rate limit. Investigate, then resume with the same `collect` command.

## §3 — Mode C analysis (currently MANUAL)

**Important limitation:** the BatchRunner only collects data. It does
NOT invoke the analyst (Mode C) or critic. To produce a real
`analysis-result.json` per ticker, you need to invoke the existing
analyst pipeline manually:

For each ticker in the cohort, in a `claude` session:

```
NVDA를 2025-03-31 기준으로 Mode C 심층 분석 해줘.
시점 데이터는 output/backtest/cohorts/2025Q1/runs/NVDA/yfinance-raw.json 사용해.
결과는 output/backtest/cohorts/2025Q1/runs/NVDA/analysis-result.json에 저장.
```

(See `docs/superpowers/plans/2026-05-08-backtest-harness.md` Phase 2
for plans to wire this in.)

After analysis, re-run aggregate so verdicts/rr_score join the rows:

```bash
python tools/backtest_runner.py aggregate --cohort 2025Q1
```

## §4 — Eval notebook

Once `results.jsonl` exists with both outcome and analysis fields:

```bash
jupyter notebook evals/backtest/notebook/2026-05-08-phase1-results.ipynb
```

The default `COHORT_ID = "2025Q1"` matches Phase 1. Run All to compute:

- Information Coefficient (Spearman ρ) by horizon
- Hit Rate (bullish vs bearish vs neutral verdicts)
- Decile Sort (R/R Score buckets vs excess_12m)
- Verdict-level mean returns (matplotlib bar chart)

## §5 — Write the report

Copy the skeleton:

```bash
cp evals/backtest/reports/2026-05-08-phase1-report.md \
   evals/backtest/reports/$(date +%Y-%m-%d)-phase1-report-final.md
```

Open the new file and fill in every `_____` placeholder using the
notebook's outputs. Then commit.

## Common pitfalls

- **Forgot to build the benchmark cache** → `outcomes` exits 2 with a
  message about missing `benchmark-prices.jsonl`. Run §1 step 1.
- **yfinance rate limit** → `outcomes` records `data_unavailable` for
  affected horizons. Re-run `outcomes --no-skip-existing` after a
  cooldown.
- **Manifest drift** → if you edit the manifest after a partial collect
  run, the new tickers are added as PENDING (good), but tickers removed
  from the manifest still have artifacts on disk (orphan rows in
  results.jsonl).
- **Manual analysis takes the longest** — at ~10 minutes per ticker for
  Mode C, 30 tickers = 5 hours of human attention. Plan accordingly.

## Cost estimate (Phase 1)

| Cost type | Estimate |
|-----------|----------|
| yfinance + FRED API | $0 (free) |
| Mode C × 30 tickers | $6-34 (analyst LLM tokens; `cost_cap_usd: 50.0` in manifest) |
| Operator time | ~1h smoke + 1h kick-off + ~5h manual analysis + 1h report = ~8h |

If `total_cost_usd` exceeds the manifest's `cost_cap_usd`, the future
token-aware cap (Chunk 6 follow-up) will abort. Today the cap is only
checked against `total_bytes_written` (a fetch-volume sanity check).
