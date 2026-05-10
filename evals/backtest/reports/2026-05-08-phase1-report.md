# Phase 1 Backtest Report — 2025Q1 cohort

> **Status:** SKELETON. Fill `_____` placeholders after running the
> procedure at `2026-05-08-phase1-procedure.md`. Then rename to
> `YYYY-MM-DD-phase1-report-final.md` and commit.

**Cohort:** `2025Q1` (30 US tickers, anchor date 2025-03-31)
**Universe:** 15 mega-cap + 15 large-cap (S&P 500 constituents — see
`evals/backtest/cohorts/2025Q1.json` for the full list)
**Benchmark policy:** MIXED (per-ticker auto: tech-heavy → QQQ; rest →
SPY)
**Run date:** _____ (YYYY-MM-DD)
**Operator:** _____
**Plan:** `docs/superpowers/plans/2026-05-08-backtest-harness.md`

---

## 1 — Headline numbers

| Metric | Value | Significance |
|--------|-------|--------------|
| **Spearman IC (12M)** | _____ | p = _____ |
| **Hit Rate (12M, all verdicts)** | _____% | n = _____ |
| **Hit Rate (bullish only)** | _____% | n = _____ |
| **Hit Rate (bearish only)** | _____% | n = _____ |
| **Decile Sort top − bottom (12M excess)** | _____pp | _____ |
| **Mean excess_12m (bullish verdicts)** | _____% | _____ |
| **Mean excess_12m (bearish verdicts)** | _____% | _____ |

### One-line verdict on the system

_____ (e.g., "Signal present at 12M (IC = 0.18, p < 0.05); 1M is
indistinguishable from noise.")

## 2 — IC by horizon

| Horizon | n | Spearman ρ | Approx. p |
|---------|---|-----------|-----------|
| 1M | _ | _ | _ |
| 3M | _ | _ | _ |
| 6M | _ | _ | _ |
| 12M | _ | _ | _ |

**Reading:** Higher ρ at longer horizons would indicate the system's
edge is fundamental (multi-quarter realization) vs short-term momentum.

## 3 — Hit Rate by horizon and direction

| Horizon | Bullish (n / hit%) | Bearish (n / hit%) | Combined (n / hit%) |
|---------|-------------------|-------------------|---------------------|
| 1M | _ / _% | _ / _% | _ / _% |
| 3M | _ / _% | _ / _% | _ / _% |
| 6M | _ / _% | _ / _% | _ / _% |
| 12M | _ / _% | _ / _% | _ / _% |

Excluded: _ neutral verdicts, _ NaN-return rows.

## 4 — Decile sort (R/R Score → excess_12m)

| Decile | n | Mean R/R Score | Mean excess_12m | Edge range |
|--------|---|----------------|-----------------|------------|
| 1 (lowest) | _ | _ | _% | [_, _] |
| 2 | _ | _ | _% | [_, _] |
| 3 | _ | _ | _% | [_, _] |
| 4 | _ | _ | _% | [_, _] |
| 5 | _ | _ | _% | [_, _] |
| 6 | _ | _ | _% | [_, _] |
| 7 | _ | _ | _% | [_, _] |
| 8 | _ | _ | _% | [_, _] |
| 9 | _ | _ | _% | [_, _] |
| 10 (highest) | _ | _ | _% | [_, _] |
| **Top − Bottom spread** | | | **_pp** | |

Monotonicity: _____ (e.g., "Mostly monotonic — only deciles 4 and 5 are
inverted; spread of 8.2pp is the headline number.")

## 5 — Failure cases (top 5 surprises)

For each, name the ticker, what the verdict said, what actually
happened, and a one-sentence post-hoc rationalization (or "still
unexplained").

| Ticker | Verdict | R/R Score | excess_12m | Surprise | Rationalization |
|--------|---------|-----------|------------|----------|-----------------|
| _____ | _____ | _____ | _____% | _____ | _____ |
| _____ | _____ | _____ | _____% | _____ | _____ |
| _____ | _____ | _____ | _____% | _____ | _____ |
| _____ | _____ | _____ | _____% | _____ | _____ |
| _____ | _____ | _____ | _____% | _____ | _____ |

## 6 — Caveats and limitations

- **Survivorship bias** (BT-D6 in the plan): The 30-ticker manifest is
  hand-picked from current S&P 500 constituents. Stocks that
  delisted between 2024 and today are absent. Estimated bias
  inflation on Hit Rate: ~5-15pp (typical for S&P 500 universes).
- **shares_outstanding leakage** (ADR 0004): yfinance `Ticker.info`
  fields are current-state, not historical. P/E and market-cap
  references in any analyst narrative may use 2026-05 shares
  rather than 2025-03-31 shares. Material impact: usually ±5%.
- **Single-run LLM noise** (BT-D5 = single-run): Each ticker analyzed
  once. Mode C verdict is non-deterministic; rerunning could move
  some borderline calls.
- **Macro narrative leakage** (acknowledged in ADR 0004 §"Inevitable
  limitations"): The analyst's macro-context section may use
  forward-looking macro views (e.g., "Fed will cut in late 2025")
  even with FRED `observation_end=2025-03-31`. Not detected by the
  leakage_detector (which only scans `*_date` fields).
- **Phase 1 sample N** (BT-D3 = 30 ticker × 4 cohort plan, this is 1 of
  4 cohorts): N=30 single cohort is too small for cross-sectional IC
  to clear conventional p < 0.05 (need ~|ρ| ≥ 0.36). Phase 2 expands
  to multi-cohort, larger universe.

## 7 — Data quality summary

| Status | Count |
|--------|-------|
| DONE (fully successful) | _ / 30 |
| FAILED (any horizon data_unavailable) | _ / 30 |
| Leakage findings | _ |
| Manual analysis: completed | _ / 30 |
| Manual analysis: skipped | _ / 30 |

## 8 — Phase 2 recommendations

Based on the headline IC and the failure-case analysis above:

- [ ] _____ (Wire Mode C analyst into the BatchRunner so 30 tickers
      can be analyzed in a single command — the biggest operator-time
      saver)
- [ ] _____ (Survivorship-bias fix: scrape historical S&P 500
      constituent list, rerun cohort with as-of universe)
- [ ] _____ (Multi-cohort backtest: 2024Q3, 2024Q4, 2025Q1, 2025Q2 to
      confirm the signal isn't anchor-date-specific)
- [ ] _____ (Failure-case-driven prompt updates for the analyst)

## 9 — Reproducibility

```text
Branch: feature/backtest-harness-chunk1 (or merged main commit ____)
Manifest: evals/backtest/cohorts/2025Q1.json
Benchmark cache: evals/backtest/data/benchmark-prices.jsonl
                 (start 2024-01-01, end _____ )
Notebook: evals/backtest/notebook/2026-05-08-phase1-results.ipynb

To reproduce:
  python tools/backtest_runner.py all --cohort 2025Q1 --prefer-qqq
  jupyter notebook evals/backtest/notebook/2026-05-08-phase1-results.ipynb
```

---

**Decision after this report:** _____ (e.g., "Phase 2 GO — IC strong
enough to justify 100-ticker × 4-cohort follow-up." OR "Phase 2 NO —
IC indistinguishable from zero; revisit prompt design first." OR
"Phase 2 PARTIAL — fix survivorship bias before scaling.")
