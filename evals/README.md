# Eval Harness

This directory stores repository-level evaluation manifests for the stock analysis agent.

## What it checks

- Artifact schema compliance (`research-plan.json`, `validated-data.json`, `analysis-result.json`, `quality-report.json`, `patch-plan.json`, `analysis-patch.json`, `snapshot.json`)
- Artifact schema compliance (`research-plan.json`, `validated-data.json`, `analysis-result.json`, `quality-report.json`, `patch-plan.json`, `analysis-patch.json`, `patch-loop-result.json`, `snapshot.json`)
- Run-local layout compliance under `output/runs/{run_id}/{ticker}/`
- Canonical source metadata usage (`display_tag`, `source_type`, `source_authority`)
- Basic mode completeness checks for `analysis-result.json`
- Semantic consistency checks for scenario math, derived ratios, verdict policy, `validated-data` ↔ `analysis-result` alignment, and analyst patch-loop state

## Run

```bash
python tools/contract_checks.py
python tools/contract_checks.py --verbose
python .claude/skills/quality-checker/scripts/quality-report-builder.py --run-dir output/runs/20260328T000000Z_AAPL_C
python .claude/skills/briefing-generator/scripts/render-briefing.py --input output/runs/20260313T000000Z_NVDA_A_LEGACY/NVDA/analysis-result.json --output /tmp/nvda-briefing-rendered.html
python .claude/skills/output-generator/scripts/render-comparison.py --input output/runs/20260312T000000Z_005930_B_LEGACY/005930/analysis-result.json --output /tmp/005930-peer-comparison.html
python .claude/agents/critic/scripts/merge-critic-review.py --quality-report output/runs/20260328T000000Z_AAPL_C/AAPL/quality-report.json --critic-json evals/fixtures/critic-review-input.json --output /tmp/aapl-quality-report-with-critic.json
python .claude/skills/dashboard-generator/scripts/render-dashboard.py --input output/runs/20260328T000000Z_AAPL_C/AAPL/analysis-result.json --output /tmp/aapl-dashboard-rendered.html
python .claude/agents/critic/scripts/apply-critic-recheck.py --quality-report /tmp/aapl-quality-report-with-critic.json --recheck-json evals/fixtures/critic-recheck-pass.json --output /tmp/aapl-quality-report-after-recheck.json
python .claude/agents/analyst/scripts/build-patch-plan.py --quality-report /tmp/aapl-quality-report-with-critic.json --output /tmp/aapl-patch-plan.json
python .claude/skills/data-validator/scripts/validate-artifacts.py --artifact-type patch-plan --input /tmp/aapl-patch-plan.json
python .claude/agents/analyst/scripts/apply-analysis-patch.py --patch-plan output/runs/20260328T000000Z_AAPL_C/AAPL/patch-plan.json --patch-json evals/fixtures/analysis-patch-aapl-valid.json --output-analysis-result /tmp/aapl-analysis-result-patched.json --output-patch-record /tmp/aapl-analysis-patch.json
python .claude/skills/data-validator/scripts/validate-artifacts.py --artifact-type analysis-patch --input /tmp/aapl-analysis-patch.json
python .claude/agents/analyst/scripts/run-patch-loop.py --patch-plan output/runs/20260328T000000Z_AAPL_C/AAPL/patch-plan.json --patch-json evals/fixtures/analysis-patch-aapl-valid.json --quality-report /tmp/aapl-quality-report-with-critic.json --critic-recheck-json evals/fixtures/critic-recheck-pass.json --output-analysis-result /tmp/aapl-analysis-result-loop.json --output-analysis-patch /tmp/aapl-analysis-patch-loop.json --output-quality-report /tmp/aapl-quality-report-loop.json --output-next-patch-plan /tmp/aapl-patch-plan-loop.json --output-loop-result /tmp/aapl-patch-loop-result.json
python .claude/skills/data-validator/scripts/validate-artifacts.py --artifact-type patch-loop-result --input /tmp/aapl-patch-loop-result.json
python tools/eval_harness.py --manifest evals/cases/default.json
python tools/eval_harness.py --manifest evals/cases/analysis-patch-regressions.json
python tools/eval_harness.py --manifest evals/cases/critic-recheck-regressions.json
python tools/eval_harness.py --manifest evals/cases/golden-runs.json
python tools/eval_harness.py --manifest evals/cases/legacy-regressions.json
python tools/eval_harness.py --manifest evals/cases/patch-plan-regressions.json
python tools/eval_harness.py --manifest evals/cases/patch-loop-result-regressions.json
python tools/eval_harness.py --manifest evals/cases/quality-report-regressions.json
python tools/eval_harness.py --manifest evals/cases/semantic-regressions.json
python tools/eval_harness.py --manifest evals/cases/temporal-consistency.json
```

## Promote Legacy Samples

```bash
python tools/migrate_legacy_runs.py
python tools/eval_harness.py --manifest evals/cases/default.json
```

## Notes

- The harness supports both positive and negative cases.
- Negative cases are useful for proving that the new validator catches legacy artifacts that still use old tags, semantic math drift, incomplete structures, or inconsistent patch-loop state.
- `quality-report.json` now separates `overall_result` from `delivery_gate.result`. This allows historical-only flags to remain visible without automatically blocking delivery.
- `patch-plan.json` is optional inside a run directory. If it exists, run-directory validation will validate it; if it does not exist, the run still passes.
- `analysis-patch.json` is also optional inside a run directory. If present, it must match its referenced `patch-plan.json` and only modify allowed analysis targets.
- `patch-loop-result.json` is optional inside a run directory. If present, it must reconcile render state, recheck state, next patch-plan state, and delivery readiness.
