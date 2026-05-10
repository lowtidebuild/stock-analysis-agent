# Phase 1 Partial Results — Data-Collection Only

> **Status:** First Phase 1 cohort run completed for the **data
> collection + outcome computation** path. Mode C analysis is still
> manual (Phase 2 will wire it in), so verdicts / rr_score / target
> prices are all null and IC / Hit Rate / Decile Sort cannot be
> computed yet. This is a **partial** report capturing what we DO
> know after the data-only pass.

**Cohort:** `2025Q1` (30 US tickers, anchor 2025-03-31)
**Run date:** 2026-05-10
**Run wall-clock:** 42 seconds (3 commands)
**Per-ticker duration:** 5.1–6.4 sec, mean 5.6 sec
**Total bytes fetched:** 1,841,710 (~1.8 MB)
**Concurrency:** 5 parallel workers
**Benchmark:** SPY (default — `--prefer-qqq` not used because cohort
mixes tech / finance / healthcare / consumer)
**Leakage findings:** 0

## Reproducibility

```bash
# After §1 of evals/backtest/reports/2026-05-08-phase1-procedure.md
python tools/backtest_runner.py all --cohort 2025Q1
```

Wall-clock estimate from the original plan was 18-30h — that estimate
assumed Mode C analysis ran per ticker. Pure data collection clocks
in at ~1 min for 30 tickers.

## 12M Realized Returns (sorted desc by absolute return)

| Ticker | Return 12M | Excess vs SPY | Return 3M | Excess 3M |
|--------|------------|---------------|-----------|-----------|
| TSM   | +103.58% | +87.33% | +36.44% | +25.99% |
| AMD   |  +98.00% | +81.75% | +38.12% | +27.66% |
| INTC  |  +94.32% | +78.06% |  -1.37% | -11.82% |
| GOOGL |  +85.95% | +69.70% | +13.96% |  +3.51% |
| NVDA  |  +60.92% | +44.66% | +45.77% | +35.32% |
| JNJ   |  +47.40% | +31.14% |  -7.89% | -18.34% |
| XOM   |  +42.66% | +26.40% |  -9.36% | -19.81% |
| WMT   |  +41.57% | +25.31% | +11.38% |  +0.93% |
| CVX   |  +23.68% |  +7.42% | -14.41% | -24.86% |
| JPM   |  +19.92% |  +3.66% | +18.19% |  +7.74% |
| BAC   |  +16.82% |  +0.56% | +13.40% |  +2.94% |
| AAPL  |  +14.25% |  -2.01% |  -7.64% | -18.09% |
| VZ    |  +10.67% |  -5.59% |  -4.61% | -15.06% |
| AMZN  |   +9.47% |  -6.79% | +15.31% |  +4.86% |
| KO    |   +6.19% | -10.07% |  -1.21% | -11.67% |
| COST  |   +5.36% | -10.90% |  +4.67% |  -5.78% |
| ORCL  |   +5.22% | -11.04% | +56.38% | +45.93% |
| PEP   |   +3.57% | -12.69% | -11.94% | -22.39% |
| NFLX  |   +3.11% | -13.15% | +43.60% | +33.15% |
| T     |   +2.51% | -13.75% |  +2.33% |  -8.12% |
| META  |   -0.73% | -16.99% | +28.06% | +17.61% |
| MSFT  |   -1.39% | -17.65% | +32.50% | +22.05% |
| BRK-B |  -10.02% | -26.28% |  -8.79% | -19.24% |
| HD    |  -10.26% | -26.52% |  +0.04% | -10.41% |
| V     |  -13.76% | -30.02% |  +1.31% |  -9.14% |
| PG    |  -15.24% | -31.50% |  -6.51% | -16.96% |
| ABT   |  -22.60% | -38.86% |  +2.53% |  -7.92% |
| CRM   |  -30.44% | -46.70% |  +1.61% |  -8.84% |
| ADBE  |  -36.62% | -52.88% |  +0.87% |  -9.58% |
| UNH   |  -48.34% | -64.59% | -40.44% | -50.89% |

## Cohort-level statistics

| Metric | Value |
|--------|-------|
| 12M return mean | **+16.86%** |
| 12M excess return mean | **+0.60%** |
| 12M positive (absolute) | 20 / 30 = 66.7% |
| 12M beat benchmark (excess > 0) | 11 / 30 = 36.7% |
| 12M return range | -48.3% to +103.6% (~152pp dispersion) |

## Sanity checks (passed)

1. **Universe selection produced realistic dispersion** — ~152pp spread,
   no degenerate clustering.
2. **Benchmark calibration** — cohort mean (+16.86%) ≈ SPY benchmark
   (~+16.3% over the same window) ≈ excess ≈ 0. Correct because the
   30 names ARE 30 of the largest S&P 500 constituents.
3. **Heavy-tail composition** — beat-rate (36.7%) is BELOW 50% even
   though mean excess is positive. A few big winners (TSM/AMD/INTC
   +80–88pp excess) carried the cohort. Typical equity backtest
   property — winners-take-most.
4. **3M vs 12M divergence** — top-3M names (ORCL +56%, NFLX +44%,
   MSFT +33%) all faded to single-digit or negative 12M. Short-term
   momentum ≠ long-term return.

## What's MISSING for "first signal"

Without `analysis-result.json` per ticker, **`rr_score`, `verdict`,
`target_*` are all null** in `results.jsonl`. Therefore:

- ❌ **Spearman IC** — no score column to correlate against returns
- ❌ **Hit Rate** — no verdicts to score (bullish/bearish/neutral)
- ❌ **Decile Sort** — no score column to bucket on
- ❌ **Phase 1 notebook eval** — would crash on `compute_ic` because
  `rr_score` is all-NaN

What we CAN see is reflected in the table above: pure forward-return
distribution. Useful for cohort-design sanity checks; not yet useful
for evaluating the analyst.

## Recommendation: bridge to first signal

Three paths from here, ordered by effort:

### Option A — Single-ticker analysis pilot (lowest effort, ~15 min)
Pick one ticker with a clear story (e.g., NVDA — semiconductor
leader, rich news, well-formed 12M signal). Run Mode C analysis
manually with `as_of=2025-03-31`, save `analysis-result.json` next
to its outcome data, re-aggregate. Verifies the analysis-side
schema mapping in `cohort_aggregator` works on real Mode C output.

### Option B — Top/bottom 5 analysis sample (~2 hr)
Run Mode C on the 5 best (TSM, AMD, INTC, GOOGL, NVDA) and 5 worst
(UNH, ADBE, CRM, ABT, PG). Gives 10 verdicts — enough to see if
the analyst's bullish/bearish calls correlate with the realized
extremes. Cheap proxy for IC.

### Option C — Full 30-ticker analysis (~5 hr + $6-34)
Per `2026-05-08-phase1-procedure.md` §3. Produces the headline IC
/ Hit Rate / Decile Sort numbers in the notebook.

## Files

- `output/backtest/cohorts/2025Q1/state.json` — full per-ticker run state
- `output/backtest/cohorts/2025Q1/runs/{TICKER}/_outcome.json` — per-ticker forward returns
- `output/backtest/cohorts/2025Q1/results.jsonl` — joined rows (analysis fields null)
- `output/backtest/cohorts/2025Q1/fred-raw.json` — cohort-shared macro snapshot
