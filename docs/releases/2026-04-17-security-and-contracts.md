# Release Notes — 2026-04-17

## Highlights

- Hardened the trust boundary for fetched artifacts with prompt-injection sanitization, `_sanitization` metadata, and validator enforcement for unsanitized raw inputs.
- Added run-local artifact contracts for `research-plan`, `validated-data`, `analysis-result`, `quality-report`, `patch-plan`, `analysis-patch`, and `patch-loop-result`.
- Introduced an analyst/critic patch loop with contract-validated patch plans, patch application, critic recheck merge, delivery gating, and repo-level eval coverage.
- Added scriptable Mode B peer comparison rendering plus refreshed Mode A/C/D generators and docs for the run-local artifact layout.
- Made contract checks CI-friendly by shipping runtime eval fixtures in-repo and auto-materializing missing `output/` samples during `tools/contract_checks.py`.

## Security Hardening

- Added trust-boundary guidance in `CLAUDE.md` and agent / skill docs.
- Added `tools/prompt_injection_filter.py` and `tools/sanitize_artifact.py`.
- Wired sanitization into `dart-collector.py`, `yfinance-collector.py`, and `fred-collector.py`.
- Validator now marks fetched artifacts without `_sanitization` as Grade D with an explicit quality flag instead of crashing the pipeline.
- Removed the historical FRED-plan files from git history and force-pushed the rewritten history.

## Artifact Contracts And Patch Loop

- Added schema files under `.claude/schemas/` for the run-local artifact set.
- Added shared tooling under `tools/analysis_contract.py`, `tools/artifact_validation.py`, `tools/patch_plan.py`, `tools/patch_loop.py`, and `tools/quality_report.py`.
- Added analyst patch-loop scripts:
  - `build-patch-plan.py`
  - `apply-analysis-patch.py`
  - `run-patch-loop.py`
- Added critic merge / recheck scripts:
  - `merge-critic-review.py`
  - `apply-critic-recheck.py`
- Added `quality-report-builder.py` to rebuild canonical run-local quality reports from artifacts.

## Output And Workflow Updates

- Added `render-comparison.py` for scripted Mode B peer comparisons.
- Updated Mode A / C / D renderer docs and run-local path handling.
- Added `artifact-manager.py` and updated data-manager guidance around run manifests, snapshot persistence, and validation.
- Documented `yfinance` as the middle fallback layer in English and Korean READMEs.
- Added `requirements.txt` and CI contract checks workflow.

## Validation

- `python3 -m unittest discover tests -v`
- `python3 tools/contract_checks.py`
