# Codex Harness Port Baseline

Captured: 2026-06-22
Runtime: `python3 --version` -> `Python 3.14.3`

## Test Suite

Command:

```bash
python3 -m pytest tests/ -q
```

Result:

```text
618 passed, 3 skipped, 294 subtests passed in 14.85s
```

## Eval Harness

The originally planned glob form does not work because `tools/eval_harness.py`
accepts one `--manifest` value at a time:

```bash
python3 tools/eval_harness.py --manifest evals/cases/*.json
```

Observed result: exit code 2, `unrecognized arguments`.

Manifest-by-manifest baseline:

| Manifest | Result | Notes |
| --- | ---: | --- |
| `evals/cases/analysis-patch-regressions.json` | 6 passed, 0 failed | all matched expectation |
| `evals/cases/critic-recheck-regressions.json` | 2 passed, 0 failed | all matched expectation |
| `evals/cases/default.json` | 6 passed, 1 failed | known current failure: `run_local_fixture_should_pass` |
| `evals/cases/golden-runs.json` | 4 passed, 1 failed | known current failure: `golden_aapl_mode_c_fixture` |
| `evals/cases/legacy-regressions.json` | 4 passed, 0 failed | all matched expectation |
| `evals/cases/patch-loop-result-regressions.json` | 4 passed, 0 failed | all matched expectation |
| `evals/cases/patch-plan-regressions.json` | 6 passed, 0 failed | all matched expectation |
| `evals/cases/quality-report-regressions.json` | 2 passed, 0 failed | all matched expectation |
| `evals/cases/semantic-regressions.json` | 2 passed, 0 failed | all matched expectation |
| `evals/cases/temporal-consistency.json` | 6 passed, 0 failed | all matched expectation |

Aggregate current eval state: 42 passed, 2 failed across 44 cases.

Known eval failures:

- `default.json::run_local_fixture_should_pass`
- `golden-runs.json::golden_aapl_mode_c_fixture`

Both failures point at the same existing AAPL Mode C fixture contract gaps:

- `sections/precision_risks[*].financial_impact` missing.
- `$.sections.macro_context.structured` missing a required FRED status object.

## VRT Golden Mode C Snapshot

Pointer: `output/data/VRT/latest.json`

Snapshot id: `2026-06-20_run_run_20260620T_VRT`
Analysis date: `2026-06-20`
Snapshot root: `output/data/VRT/snapshots/2026-06-20_run_run_20260620T_VRT`

Referenced artifacts:

- `analysis-result.json`: `output/data/VRT/snapshots/2026-06-20_run_run_20260620T_VRT/analysis-result.json`
- `validated-data.json`: `output/data/VRT/snapshots/2026-06-20_run_run_20260620T_VRT/validated-data.json`
- `quality-report.json`: `output/data/VRT/snapshots/2026-06-20_run_run_20260620T_VRT/quality-report.json`
- `evidence-pack.json`: `output/data/VRT/snapshots/2026-06-20_run_run_20260620T_VRT/evidence-pack.json`
- `context-budget.json`: `output/data/VRT/snapshots/2026-06-20_run_run_20260620T_VRT/context-budget.json`
- `tier2-raw.json`: `output/data/VRT/snapshots/2026-06-20_run_run_20260620T_VRT/tier2-raw.json`

Key fields:

| Field | Value |
| --- | ---: |
| `ticker` | `VRT` |
| `market` | `US` |
| `company_name` | `Vertiv Holdings Co` |
| `output_mode` | `C` |
| `source_profile` | `mixed` |
| `confidence_cap` | `B` |
| `price_at_analysis` | 333.05 |
| `verdict` | `Neutral` |
| `rr_score` | 2.25 |
| `scenarios.bull.target` | 455.0 |
| `scenarios.base.target` | 378.0 |
| `scenarios.bear.target` | 232.0 |
| `dcf_analysis.base.fair_value` | 115.33 |
| `dcf_analysis.reverse.status` | `success` |
| `dcf_analysis.reverse.implied_fcf_growth` | 0.335 |
| `dcf_analysis.reverse.growth_gap_bp` | 1790 |
| `valuation_bridge.weighted_fair_value` | 264.15 |

Quality gate:

- `quality-report.overall_result`: `PASS_WITH_FLAGS`
- `quality-report.delivery_gate.result`: `PASS`
- `quality-report.delivery_gate.ready_for_delivery`: `true`
- Non-blocking item: `rendered_output`

## Git State At Baseline

`git status --short` reported one unrelated untracked directory:

```text
?? .understand-anything/
```

