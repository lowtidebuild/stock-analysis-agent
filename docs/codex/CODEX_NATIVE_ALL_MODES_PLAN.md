# Codex-Native All Modes Plan

Captured: 2026-06-22

## Purpose

Codex should be able to run every stock analysis mode natively without calling
Claude Code or an external analyst LLM/API. The target is one consistent local
operator experience for Mode A, Mode B, and Mode C:

```bash
python3 scripts/run_mode.py \
  --ticker VRT \
  --mode C \
  --lang ko \
  --market US \
  --run-id codex_vrt_c \
  --analyst-backend codex_native
```

Important boundary: `codex_native` means the analyst judgment pass is generated
from local verified artifacts by Codex-native deterministic logic. Live market,
filing, macro, or web data collection may still call their configured data
providers when the operator enables networked collection.

## Current State

| Area | State | Gap |
| --- | --- | --- |
| Analyst backend | `codex_native` exists in `scripts/parity/analyst.py` and records `api_calls=0` | Add richer sector-specific native wording only if needed |
| Mode C | `scripts/run_mode.py --mode C --analyst-backend codex_native` works and publishes `output/reports/*_C_*`; `scripts/run_mode_c.py` is now a thin compatibility wrapper | Keep focused Mode C tests as the compatibility contract |
| Mode A | `scripts/run_mode.py --mode A --analyst-backend codex_native` works and publishes `output/reports/*_A_*`; `scripts/run_analysis.py --native` delegates to the unified CLI | Old non-native `scripts/run_analysis.py` path is deprecated but retained for compatibility |
| Mode B | `scripts/run_mode.py --mode B --analyst-backend codex_native` works, runs each ticker natively, builds comparison artifacts, publishes `output/reports/*_B_*`, and has US/KR mixed-market regression coverage | Add more sector/market examples over time |
| Fixture safety | Fixture/smoke output is blocked unless explicitly allowed for Mode A/B/C native delivery | Keep this as a hard delivery invariant |
| Docs | Mode A/B/C native paths documented in runbook, including KR auto-market and mixed-market examples | Keep examples aligned with regression fixtures |

Session 1 status: `scripts/run_mode.py` now exists as the public all-mode CLI
skeleton. It dispatches Mode C to the existing production path, enriches the
final JSON with `mode` and `backend_provider`, and established the shared CLI
contract that later sessions extended to Mode A and Mode B.

Session 2 status: Mode A now runs through `scripts/run_mode.py`, publishes
`output/reports/{ticker}_A_{lang}_{analysis_date}.html`, records
`codex_native` with `api_calls=0`, and blocks fixture/smoke output unless
`--allow-fixture-delivery` is explicitly passed.

Session 3 status: Mode B now runs through `scripts/run_mode.py`, enforces
2-5 comparison tickers, runs each ticker through the native analyst path,
builds `comparison/mode-b-comparison.html`, publishes
`output/reports/{primary}_B_{lang}_{analysis_date}.html`, returns
`comparison_report_path` and `best_pick`, and blocks fixture/smoke output unless
`--allow-fixture-delivery` is explicitly passed.

Session 4 status: Mode C implementation moved to `scripts/run_mode_c_impl.py`;
shared run-mode helpers moved to `scripts/run_mode_common.py`; and
`scripts/run_mode_c.py` now only parses the legacy Mode C CLI and delegates to
the shared implementation.

Session 5 status: `scripts/run_analysis.py` gained a `--native` compatibility
bridge. With `--native`, it forwards Mode A/B/C arguments to
`scripts/run_mode.py`, including backend override, fixture allowance,
reuse/skip-network flags, and comparison ticker options. Without `--native`,
the old Mode A web-runner path remains available for compatibility.

Session 6 status: the old non-native `scripts/run_analysis.py` Mode A
web-runner path is formally deprecated but not removed. It now emits a stderr
warning that points operators to `scripts/run_mode.py` or
`scripts/run_analysis.py --native`; the native bridge remains warning-free so
machine-readable JSON output stays clean.

Session 7 status: native regression coverage now includes a KR Mode A
`--market auto` run for `005930` and a mixed-market Mode B comparison across
`AAPL`, `005930`, and `000660`. The tests assert per-ticker market inference,
KRW/USD currency preservation, `codex_native` API-call-free metadata, and mixed
comparison artifacts.

## Product Goal

One Codex command should be enough to run any mode:

```bash
python3 scripts/run_mode.py \
  --ticker AAPL \
  --mode A \
  --lang ko \
  --market US \
  --run-id codex_aapl_a \
  --analyst-backend codex_native
```

```bash
python3 scripts/run_mode.py \
  --ticker VRT \
  --tickers VRT,ETN,TT,HUBB \
  --mode B \
  --lang ko \
  --market US \
  --run-id codex_vrt_b \
  --analyst-backend codex_native
```

```bash
python3 scripts/run_mode.py \
  --ticker VRT \
  --mode C \
  --lang ko \
  --market US \
  --run-id codex_vrt_c \
  --peer-tickers ETN,TT,HUBB,EMR \
  --analyst-backend codex_native
```

Each command should print JSON with:

- `report_path`
- `run_id`
- `quality_report_path`
- `delivery_gate`
- `run_profile`
- `mode`
- `backend_provider`

## Non-Goals

- Do not remove the existing Claude Code-compatible artifacts or schemas.
- Do not remove external data provider support.
- Do not treat fixture output as production output.
- Do not make Mode C less strict to accommodate Mode A/B.
- Do not hide quality gate failures behind a successfully rendered HTML file.

## Architecture

### Proposed Entrypoint

Add `scripts/run_mode.py` as the public all-mode CLI. Keep existing scripts as
compatibility surfaces:

- `scripts/run_mode_c.py`: Mode C compatibility wrapper
- `scripts/run_mode_c_impl.py`: shared Mode C implementation used by both
  unified and compatibility CLIs
- `scripts/run_mode_common.py`: backend override, timing, and run-profile
  annotation helpers shared across modes
- `scripts/run_abc_parity.py`: low-level parity/stage runner
- `scripts/run_analysis.py`: deprecated legacy Mode A path plus `--native`
  bridge to the unified all-mode CLI

`scripts/run_mode.py` should own:

- CLI normalization
- run profile annotation
- backend override via `--analyst-backend`
- mode-specific publish path
- quality gate enforcement
- final JSON response

### Backend Selection

All production-style native runs should use:

```text
run_context.backend.provider = codex_native
run_context.backend.model = local-deterministic-analyst
run_context.backend.usage.api_calls = 0
run_context.run_profile = production
run_context.fixture_backend = false
```

Fixture runs remain:

```text
run_context.backend.provider = fixture
run_context.run_profile = smoke
run_context.fixture_backend = true
```

### Mode-Specific Outputs

| Mode | Local HTML | Published report | Quality artifact |
| --- | --- | --- | --- |
| A | `output/runs/{run_id}/{ticker}/mode-a-briefing.html` | `output/reports/{ticker}_A_{lang}_{date}.html` | `quality-report.json` |
| B | `output/runs/{run_id}/comparison/mode-b-comparison.html` | `output/reports/{primary}_B_{lang}_{date}.html` | `comparison/comparison-quality-report.json` plus per-ticker `quality-report.json` |
| C | `output/runs/{run_id}/{ticker}/mode-c-dashboard.html` | `output/reports/{ticker}_C_{lang}_{date}.html` | `quality-report.json` |

## Mode A Plan

Mode A should become a first-class native briefing run.

Work:

- Route Mode A through `build_analyst_handoff(..., ANALYST_BACKEND=codex_native)`.
- Use the existing Mode A renderer from parity rendering when possible.
- Publish to `output/reports/{ticker}_A_{lang}_{analysis_date}.html`.
- Ensure precision risks are populated and source-grounded.
- Add Mode A quality gate enforcement to the unified CLI.
- Keep legacy `scripts/run_analysis.py` available as a deprecated compatibility
  path, but route new native usage through `scripts/run_analysis.py --native`
  or `scripts/run_mode.py`.

Acceptance:

- `python3 scripts/run_mode.py --mode A ... --analyst-backend codex_native` exits 0.
- Output uses `codex_native`, `api_calls=0`, `run_profile=production`.
- Report exists under `output/reports`.
- Quality gate is `PASS` or returns a blocking error before final delivery.

## Mode B Plan

Mode B should become a first-class native comparison run.

Work:

- Route each ticker analyst pass through `codex_native`.
- Preserve Mode B requirement for `--tickers` with 2-5 names.
- Build comparison artifact through `build_mode_b_comparison_handoff`.
- Publish the comparison HTML to `output/reports/{primary}_B_{lang}_{analysis_date}.html`.
- Add a B-specific final payload that includes `comparison_report_path`.
- Validate peer-relative tables are not placeholders.

Acceptance:

- `python3 scripts/run_mode.py --mode B --ticker VRT --tickers VRT,ETN,TT,HUBB ...` exits 0.
- Every ticker analysis result records `provider=codex_native`.
- Comparison HTML exists and is not a per-ticker Mode C dashboard.
- Quality gate blocks if fewer than two valid tickers are available.

## Mode C Plan

Mode C already has the first native production path. The all-mode wrapper should
reuse that behavior without loosening it.

Work:

- Move reusable pieces from `scripts/run_mode_c.py` into shared helpers, or call
  the existing Mode C function from `scripts/run_mode.py`.
- Keep public report sections lean; internal audit artifacts stay in JSON.
- Preserve `fixture_delivery_guard`, `numeric_sanity`, DCF, reverse DCF, and
  valuation bridge checks.

Acceptance:

- Existing Mode C native command still passes.
- Korean dashboard still excludes public audit appendices.
- `quality-report.json` remains the delivery authority.

## Implementation Phases

### Phase 1 - Contracts And CLI

Status: complete for the session 1 contract skeleton.

- Add `scripts/run_mode.py`.
- Add `--mode A|B|C`, `--analyst-backend`, `--run-profile`,
  `--allow-fixture-delivery`, `--reuse-collected`, `--skip-network`,
  `--peer-tickers`, and `--tickers`.
- Reuse Mode C temporary backend env override and run profile annotation.
- Preserve Mode C request metadata with selected backend.
- Validate Mode B ticker cardinality before comparison orchestration.

Exit criteria:

- CLI rejects invalid mode/ticker combinations clearly.
- CLI can dispatch to existing Mode C path without behavior drift.

### Phase 2 - Mode A Native Delivery

Status: complete for native Mode A delivery through the unified CLI.

- Wire A through parity validation, calculation, analyst, render, critic.
- Publish Mode A report.
- Add tests for fixture-blocking and codex_native production delivery.

Exit criteria:

- Focused Mode A native tests pass.
- Legacy Mode A tests still pass.

### Phase 3 - Mode B Native Delivery

Status: complete for native Mode B delivery through the unified CLI.

- Wire B through multi-ticker parity pipeline.
- Publish comparison report.
- Add tests for missing peer data, stale placeholder rows, and native backend
  metadata for every ticker.

Exit criteria:

- Focused Mode B native tests pass.
- Mode B blocks when comparison quality is not ready.

### Phase 4 - Mode C Convergence

Status: complete for shared Mode C implementation and thin compatibility
wrapper.

- Make Mode C use the shared all-mode helpers.
- Keep `scripts/run_mode_c.py` as a thin compatibility wrapper.
- Update runbook examples to prefer `scripts/run_mode.py`.

Exit criteria:

- Current Mode C focused tests pass unchanged or with only command-path updates.

### Phase 5 - Full Regression And Docs

- Run focused native tests for A/B/C.
- Run broader rendering and quality tests.
- Update `docs/codex/RUNBOOK.md`.
- Update parity notes once all-mode native delivery is proven.

Exit criteria:

- All documented native commands work from repo root.
- Quality gate semantics are consistent across modes.

## Test Plan

Focused tests to add:

- `test_run_mode_entrypoint_mode_a_codex_native_delivery`
- `test_run_mode_entrypoint_mode_b_codex_native_delivery`
- `test_run_mode_entrypoint_mode_c_codex_native_delivery`
- `test_run_mode_blocks_fixture_without_allowance_for_all_modes`
- `test_run_mode_records_api_calls_zero_for_codex_native`
- `test_run_mode_b_requires_two_or_more_tickers`
- `test_run_mode_publishes_mode_specific_report_names`

Regression commands:

```bash
python3 -m pytest \
  tests/test_abc_parity_analyst.py \
  tests/test_run_mode_c_entrypoint.py \
  tests/test_abc_parity_rendering.py \
  tests/test_rendered_output_validation.py \
  tests/test_quality_report_numeric_sanity.py \
  -q
```

After adding the unified entrypoint:

```bash
python3 -m pytest tests/test_run_mode_entrypoint.py -q
```

## Quality Gate Rules

All native modes must obey:

- No public delivery when `delivery_gate.ready_for_delivery` is false.
- No production delivery for fixture backend unless explicitly allowed.
- `codex_native` is production eligible only when input artifacts are valid.
- Missing live data should be disclosed as unavailable, not guessed.
- Rendered HTML should not leak local absolute paths.

## Risks

| Risk | Mitigation |
| --- | --- |
| A/B quality gates are less mature than C | Keep focused acceptance tests and add market/sector examples over time |
| `codex_native` prose becomes too generic | Keep deterministic, metric-bound templates and add company profile hints |
| Mode B comparison publishes stale per-ticker artifacts | Require comparison quality report as final gate |
| Fixture and native outputs get confused | Preserve backend metadata and fixture guard |
| Live provider availability varies by environment | Keep `--reuse-collected` and `--skip-network` paths explicit |

## Open Questions

- Should Mode A use the parity renderer exclusively, or keep the legacy briefing
  generator as a compatibility renderer?
- Should Mode B publish one comparison report only, or also publish per-ticker
  Mode A/C companion reports?
- Should `scripts/run_mode_c.py` eventually be deprecated, or remain as the
  stable Mode C shortcut?
- Should `codex_native` include richer company profile templates per sector, or
  stay strictly metric-driven?

## Recommended Next Step

Add more sector-specific native wording only where deterministic templates are
too generic, and keep expanding live-style smoke examples without weakening the
fixture delivery guard.
