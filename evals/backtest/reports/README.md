# Backtest Reports

Phase 1 backtest harness procedural docs and result reports. Built per
the plan at `docs/superpowers/plans/2026-05-08-backtest-harness.md`.

## Files

| File | Purpose | Lifecycle |
|------|---------|-----------|
| `2026-05-08-phase1-procedure.md` | Step-by-step recipe for running Phase 1 (smoke + cohort + analysis + report) | Reference; updated as the harness evolves |
| `2026-05-08-phase1-report.md` | Phase 1 results write-up. Skeleton with `_____` placeholders that the human fills in after the cohort completes | One per cohort run; copy + rename for new runs |
| `../smoke-results.md` | One-line summary of the most recent smoke test (1 ticker × 1 horizon) | Overwritten each smoke run |

## Workflow

1. **Smoke test first** — see procedure §1. Verifies wire-up end-to-end
   on a single ticker. Fast (~30 sec real network). Output:
   `../smoke-results.md`.
2. **Phase 1 cohort** — see procedure §2. 30 US tickers × 2025-03-31
   anchor. Wall-clock 18-30 hours for data collection (parallel 5);
   analysis is currently manual (Phase 2 wires it in). Output:
   `2026-05-08-phase1-report.md` (filled by human).

## Status

- **Phase 1 not yet run.** This report directory ships with skeletons
  only. The first `_____` in `2026-05-08-phase1-report.md` will be
  filled by the operator (kipeum86) after running the procedure.
