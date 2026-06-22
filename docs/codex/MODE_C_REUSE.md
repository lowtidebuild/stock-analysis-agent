# Mode C Reuse Analysis

Captured: 2026-06-22

## Decision

Choose Option B for the first Codex port:

Create a new `scripts/run_mode_c.py` production entrypoint that directly
reuses the existing parity builders and selected collection helpers, without
refactoring `scripts/run_abc_parity.py` in this session.

Reasoning:

- `scripts/run_abc_parity.py` already proves the Mode C stage order, but its
  full `main()` intentionally raises after an unflagged full run.
- Option B avoids changing the existing parity runner and therefore has the
  smallest risk to the Claude Code path.
- A later cleanup can extract a shared function if the new entrypoint and the
  parity runner drift.

Do not shell out to or wrap `scripts/run_abc_parity.py main()` for production
Mode C. Reuse its stage functions or the `scripts/parity/*` builders directly.

## Existing Stage Order

The working one-ticker sequence in `scripts/run_abc_parity.py` is:

1. Macro collection: `collect_macro(paths, market, skip_network)`.
2. Ticker collection: `collect_ticker_sources(...)` or `reuse_ticker_sources(...)`.
3. Validation: `build_validation_handoff(...)`.
4. Deterministic calculations: `build_calculation_handoff(...)`.
5. Analyst pass: `build_analyst_handoff(...)`.
6. Rendering: `build_render_handoff(...)`.
7. Critic and quality gate: `build_critic_handoff(...)`.

The full parity runner prints run metadata and then raises unless one of the
stop flags is present. That behavior is useful for parity sessions but not for
a production Codex entrypoint.

## Builder Inventory

### Collection Helpers

Source: `scripts/run_abc_parity.py` plus `scripts/parity/data_sources.py`

- `collect_macro(*, paths, market, skip_network) -> SourceResult`
  - Writes: `output/runs/{run_id}/macro/fred-raw.json`.
  - With `skip_network=True`, writes a skipped FRED artifact.
- `collect_ticker_sources(*, language, market, mode, peer_tickers, run_id, skip_network, ticker, timeout) -> dict`
  - Writes: `research-plan.json`.
  - Writes raw source artifacts: `financial-datasets-raw.json`, `dart-api-raw.json`, `yfinance-raw.json`.
  - For Mode C, writes `peer-fetch-summary.json` and optional `peers/*.json`.
  - Does not currently call a portable web search layer.
- `reuse_ticker_sources(*, market, run_id, ticker) -> dict`
  - Reuses existing raw artifacts and `source-collection-summary.json`.
  - Requires the structured raw artifacts to exist.

Portable scripts called by collectors are Python scripts under `.claude/skills`,
not Claude Code harness tools. They are safe to reuse from Codex.

### Validation

Source: `scripts/parity/validation.py`

Signature:

```python
build_validation_handoff(
    *,
    language: str,
    market: str,
    mode: str,
    run_id: str,
    ticker: str,
) -> ValidationResult
```

Reads:

- `output/runs/{run_id}/{ticker}/financial-datasets-raw.json`
- `output/runs/{run_id}/{ticker}/dart-api-raw.json`
- `output/runs/{run_id}/{ticker}/yfinance-raw.json`
- `output/runs/{run_id}/{ticker}/tier2-raw.json` when present
- `output/runs/{run_id}/macro/fred-raw.json`

Writes:

- `validated-data.json`
- `evidence-pack.json`
- `context-budget.json`
- `validation-summary.json`

Tier2 handling:

`build_validation_handoff` now reads a run-local sanitized
`output/runs/{run_id}/{ticker}/tier2-raw.json` when present. Validation consumes
only `extracted_metric_candidates` and `metric_conflicts`; raw search snippets
remain outside analyst prompts by default. Validated facts still flow through
`validated-data.json` and `evidence-pack.json`.

### Calculations

Source: `scripts/parity/calculations.py`

Signature:

```python
build_calculation_handoff(
    *,
    language: str,
    market: str,
    mode: str,
    run_id: str,
    ticker: str,
) -> CalculationResult
```

Reads:

- `validated-data.json`
- `evidence-pack.json`

Writes:

- `deterministic-calculations.json`
- updated `context-budget.json`

Mode C DCF, reverse DCF, and valuation bridge logic already live here and
should not be reauthored.

### Analyst

Source: `scripts/parity/analyst.py`

Signature:

```python
build_analyst_handoff(
    *,
    language: str,
    market: str,
    mode: str,
    run_id: str,
    ticker: str,
) -> AnalystResult
```

Reads:

- `research-plan.json`
- `validated-data.json`
- `evidence-pack.json`
- `context-budget.json`
- `deterministic-calculations.json`
- optional `peers/*.json`

Writes:

- `analyst-input.compact.json`
- `analyst-input.json`
- `analysis-result.json`
- `analyst-summary.json`
- `analysis-result.rejected.json` on contract failure

Backend behavior:

- Uses `ANALYST_BACKEND=fixture` for deterministic offline tests.
- Otherwise resolves the backend via `get_backend(..., logical_tier="analyst_main")`.
- OpenAI remains the default through `config/model_registry.yaml`.

### Rendering

Source: `scripts/parity/rendering.py`

Signature:

```python
build_render_handoff(
    *,
    language: str,
    market: str,
    mode: str,
    run_id: str,
    ticker: str,
) -> RenderResult
```

Mode C implementation:

- Dispatches to `build_mode_c_render_handoff(...)`.
- Reads `analysis-result.json`, `validated-data.json`,
  `deterministic-calculations.json`, and `evidence-pack.json`.
- Writes `mode-c-dashboard.html`.
- Writes `mode-c-render-report.json`.
- Validates the rendered HTML through `validate_mode_c_rendered_html(...)` and
  `tools.quality_report.build_rendered_output_item(...)`.

This is the real Mode C renderer. Do not use
`.claude/skills/dashboard-generator/scripts/render-dashboard.py` for delivery.

### Critic

Source: `scripts/parity/critic.py`

Signature:

```python
build_critic_handoff(
    *,
    language: str,
    market: str,
    mode: str,
    patch_once: bool = True,
    run_id: str,
    ticker: str,
) -> CriticResult
```

Reads:

- `research-plan.json`
- `validated-data.json`
- `evidence-pack.json`
- `context-budget.json`
- `analysis-result.json`
- rendered Mode C dashboard path

Writes:

- `quality-report.json`
- `critic-review.json`
- `critic-loop-result.json`
- optional `analysis-patch.json`
- optional `analysis-result.precritic.json`

Quality:

- Calls `build_quality_report(...)` directly with the ticker artifact set and
  rendered report path.
- This avoids the known `build_quality_report_from_run_dir` issue when a run
  directory contains sibling folders such as `macro/`, `peers/`, or
  `earnings-window/`.

## Proposed `scripts/run_mode_c.py` Shape

The new entrypoint should:

1. Parse: `--ticker`, `--mode C`, `--lang`, `--market`, `--run-id`,
   `--skip-network`, `--reuse-collected`, optional `--peer-tickers`, optional
   `--timeout`.
2. Normalize ticker and market using the same rules as `run_abc_parity.py`.
3. Ensure `output/runs/{run_id}` and `output/reports` exist.
4. Collect or reuse macro and ticker structured sources.
5. Call the portable web search layer to write
   `output/runs/{run_id}/{ticker}/tier2-raw.json`.
6. Run validation, calculations, analyst, render, and critic in order.
7. Require `quality-report.json.delivery_gate.ready_for_delivery == true`.
8. Copy or expose the report path consistently with `run_analysis.py`.
9. Print a small JSON payload such as:

```json
{"report_path":"output/runs/<run_id>/<ticker>/mode-c-dashboard.html","run_id":"<run_id>"}
```

## Implementation Notes

- `tools/web_search.py` and `tools/web_fetch.py` provide the portable web layer.
- `scripts/parity/validation.py` maps sanitized tier2 metric candidates into
  missing validated metrics at Grade C or below and preserves tier2 conflicts
  in the validation/evidence handoff.
- Offline Mode C tests should use `ANALYST_BACKEND=fixture`, not an OpenAI
  monkeypatch.
