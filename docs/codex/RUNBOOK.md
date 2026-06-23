# Codex Runbook

This runbook is the operator-facing companion to `AGENTS.md`. It documents the
portable commands Codex should use without changing the existing Claude Code
harness.

## Prerequisites

- Run commands from the repo root.
- Use `python3`.
- Do not read `.env*` files. Configure needed variables outside the agent
  session.
- For Codex-native Mode A/B/C analyst runs with no external analyst API call, pass
  `--analyst-backend codex_native`. The run still uses whatever live market,
  filing, macro, or web sources you enable for collection.
- All-mode native delivery planning lives in
  `docs/codex/CODEX_NATIVE_ALL_MODES_PLAN.md`.
- For deterministic offline analyst runs, set `ANALYST_BACKEND=fixture`.
  Fixture runs default to a `smoke` profile and are blocked from production
  delivery unless `--allow-fixture-delivery` is explicitly passed.
- For live analyst runs, provide `OPENAI_API_KEY` and optionally
  `OPENAI_ANALYST_MODEL`.
- For portable web search, set `TAVILY_API_KEY` or `BRAVE_API_KEY`, or pass
  `--web-provider none` for an unavailable/skipped tier2 artifact.

## Mode A Codex-Native Briefing

Use the unified entrypoint for native Mode A delivery:

```bash
python3 scripts/run_mode.py \
  --ticker AAPL \
  --mode A \
  --lang en \
  --market US \
  --run-id codex_aapl_a \
  --analyst-backend codex_native
```

The command publishes:

```text
output/reports/{TICKER}_A_{lang}_{analysis_date}.html
```

It records `run_context.backend.provider=codex_native`,
`run_context.backend.usage.api_calls=0`, and `run_context.run_profile=production`.
Fixture/smoke Mode A output is blocked unless `--allow-fixture-delivery` is
explicitly passed.

For KR tickers, `--market auto` infers `KR` for six-digit numeric tickers and
keeps KRW-denominated metrics in the rendered report and JSON artifacts:

```bash
python3 scripts/run_mode.py \
  --ticker 005930 \
  --mode A \
  --lang ko \
  --market auto \
  --run-id codex_005930_a \
  --analyst-backend codex_native
```

## Mode B Codex-Native Comparison

Use the unified entrypoint for native multi-ticker comparison delivery:

```bash
python3 scripts/run_mode.py \
  --ticker GOOGL \
  --tickers GOOGL,MSFT,AAPL \
  --mode B \
  --lang ko \
  --market US \
  --run-id codex_googl_b \
  --analyst-backend codex_native
```

The command runs a native analyst pass for each ticker, builds the comparison
artifact, and publishes:

```text
output/reports/{PRIMARY}_B_{lang}_{analysis_date}.html
```

The final JSON includes `comparison_report_path`, `best_pick`, `tickers`, and
the comparison `quality_report_path`. Each ticker analysis records
`run_context.backend.provider=codex_native` and
`run_context.backend.usage.api_calls=0`. Fixture/smoke Mode B output is blocked
unless `--allow-fixture-delivery` is explicitly passed.

Mixed-market comparison is supported by passing `--market mixed`; the runner
infers each ticker's local market before validation and analysis:

```bash
python3 scripts/run_mode.py \
  --ticker AAPL \
  --tickers AAPL,005930,000660 \
  --mode B \
  --lang ko \
  --market mixed \
  --run-id codex_mixed_b \
  --analyst-backend codex_native
```

## Deprecated Legacy Mode A Smoke

```bash
python3 scripts/run_analysis.py \
  --ticker AAPL \
  --mode A \
  --lang en \
  --market US \
  --run-id smoke_aapl_a
```

Expected outputs are under `output/runs/smoke_aapl_a/AAPL/`. Mode A remains the
legacy headless path for compatibility, but it is deprecated. The command emits
a warning on stderr, and new Codex-native delivery should use
`scripts/run_mode.py`.

The same legacy entrypoint can explicitly delegate to the native all-mode CLI:

```bash
python3 scripts/run_analysis.py \
  --ticker AAPL \
  --mode A \
  --lang en \
  --market US \
  --run-id codex_aapl_a \
  --native \
  --analyst-backend codex_native
```

`--native` also forwards shared native options such as `--skip-network`,
`--reuse-collected`, `--allow-fixture-delivery`, `--tickers`, and
`--peer-tickers`. This native delegation path does not emit the legacy
deprecation warning, so the JSON payload remains clean for automation.

## Mode C Live Dashboard

Use the unified entrypoint for Codex Mode C delivery:

```bash
python3 scripts/run_mode.py \
  --ticker VRT \
  --mode C \
  --lang ko \
  --market US \
  --run-id codex_vrt_c \
  --analyst-backend codex_native \
  --web-provider tavily
```

As of session 4, `scripts/run_mode.py` dispatches Mode A, Mode B, and Mode C to
native delivery paths. The legacy Mode C compatibility command is a thin
wrapper around the shared Mode C implementation and remains available:

```bash
python3 scripts/run_mode_c.py \
  --ticker VRT \
  --mode C \
  --lang ko \
  --market US \
  --run-id codex_vrt_c \
  --analyst-backend codex_native \
  --web-provider tavily
```

The unified command prints JSON containing `report_path`, `run_id`,
`quality_report_path`, `delivery_gate`, `mode`, and `backend_provider`. The
compatibility command prints the original Mode C fields without the extra
all-mode metadata. The published report is copied to:

```text
output/reports/{TICKER}_C_{lang}_{analysis_date}.html
```

The run-local dashboard and quality artifacts remain under:

```text
output/runs/{run_id}/{TICKER}/
```

## Mode C Codex-Native Reuse

When collection artifacts already exist and you want the analyst pass to run
locally without an external analyst API call:

```bash
python3 scripts/run_mode.py \
  --ticker VRT \
  --mode C \
  --lang ko \
  --market US \
  --run-id codex_vrt_c \
  --skip-network \
  --reuse-collected \
  --analyst-backend codex_native
```

This records `run_context.backend.provider=codex_native`,
`run_context.backend.usage.api_calls=0`, and keeps the run profile as
`production` rather than `smoke`.

## Mode C Offline Fixture Smoke

The lowest-friction offline check is the test-backed smoke:

```bash
ANALYST_BACKEND=fixture python3 -m pytest tests/test_run_mode_c_entrypoint.py -q
```

That test performs the full offline pattern:

1. Build skipped collection artifacts through `scripts/run_abc_parity.py`
   `--collect-only --skip-network`.
2. Add deterministic yfinance fixture data.
3. Run `scripts/run_mode_c.py --reuse-collected --skip-network
   --allow-fixture-delivery`.
4. Assert the HTML report exists and the quality gate passes with
   `fixture_delivery_guard` listed as a non-blocking smoke flag.

The same suite also exercises a Korean Mode C entrypoint run and checks that
the published dashboard, run-local HTML, translated headings, translated chart
labels, `numeric_sanity`, and `fixture_delivery_guard` all agree.

For manual reuse of an already prepared run:

```bash
ANALYST_BACKEND=fixture python3 scripts/run_mode_c.py \
  --ticker AAPL \
  --mode C \
  --lang en \
  --market US \
  --run-id pytest_run_mode_c_entrypoint_AAPL_C \
  --skip-network \
  --reuse-collected \
  --allow-fixture-delivery
```

Only use the manual command when the matching collected artifacts already exist
under `output/runs/{run_id}/`.

Without `--allow-fixture-delivery`, fixture/smoke Mode C runs should render
run-local artifacts but return a blocked delivery gate. This prevents a
deterministic smoke report from being mistaken for production-quality analysis.

## Output Map

- `output/runs/{run_id}/request.json`: normalized request payload.
- `output/runs/{run_id}/macro/fred-raw.json`: macro collection artifact.
- `output/runs/{run_id}/{TICKER}/tier2-raw.json`: portable qualitative web
  artifact with `_sanitization`.
- `output/runs/{run_id}/{TICKER}/validated-data.json`: validated facts.
- `output/runs/{run_id}/{TICKER}/evidence-pack.json`: compact sourced facts.
- `output/runs/{run_id}/{TICKER}/deterministic-calculations.json`: DCF,
  reverse DCF, and valuation bridge outputs.
- `output/runs/{run_id}/{TICKER}/analysis-result.json`: analyst contract.
- `output/runs/{run_id}/{TICKER}/mode-a-briefing.html`: run-local Mode A
  briefing.
- `output/runs/{run_id}/comparison/mode-b-comparison.html`: run-local Mode B
  comparison.
- `output/runs/{run_id}/comparison/comparison-quality-report.json`: Mode B
  comparison delivery gate.
- `output/runs/{run_id}/{TICKER}/mode-c-dashboard.html`: run-local dashboard.
- `output/runs/{run_id}/{TICKER}/quality-report.json`: final delivery gate.
- `output/reports/{TICKER}_A_{lang}_{date}.html`: published briefing.
- `output/reports/{PRIMARY}_B_{lang}_{date}.html`: published comparison.
- `output/reports/{TICKER}_C_{lang}_{date}.html`: published dashboard.
- `output/data/{TICKER}/latest.json`: latest persisted snapshot pointer.

## Parity And Regression Checks

Full Python suite:

```bash
python3 -m pytest tests/ -q
```

Eval harness manifests must be run one manifest at a time:

```bash
python3 tools/eval/run_harness.py --manifest evals/manifests/default.json
python3 tools/eval/run_harness.py --manifest evals/manifests/golden-runs.json
```

Current baseline notes live in `docs/codex/BASELINE.md`.

## Quality Gate

Before delivering a native report, inspect:

```text
output/runs/{run_id}/{TICKER}/quality-report.json
output/runs/{run_id}/comparison/comparison-quality-report.json  # Mode B final comparison
```

Delivery is acceptable only when:

- `delivery_gate.result` is `PASS`
- `delivery_gate.ready_for_delivery` is `true`
- `items.numeric_sanity.status` is not `FAIL`; MAJOR/BLOCKER validated-data
  sanity flags are terminal input blockers, not analyst-patch issues
- For production Mode A/B/C, `items.fixture_delivery_guard.status` is not `FAIL`

If the gate is not ready, treat the report as failed even if HTML was rendered.

## Troubleshooting

- `python: command not found`: use `python3`.
- Missing analyst API key: use `--analyst-backend codex_native` for local
  production-style Mode A/B/C analysis, use `ANALYST_BACKEND=fixture` for smoke
  tests, or configure `OPENAI_API_KEY` outside the agent session.
- `run_abc_parity.py` raises after a full unflagged run: this is intentional.
  Use stop flags such as `--collect-only` for parity steps, or use
  `scripts/run_mode_c.py` for production Mode C.
- Eval harness fails on a glob: pass one `--manifest` path at a time.
- `tier2-raw.json` is present but expected facts are missing: check that values
  are under `extracted_metric_candidates` with `normalized_value`,
  `confidence_candidate`, and source metadata. Raw search snippets are kept out
  of analyst prompts unless investigating a logged mismatch.
- Quality gate fails after rendering: debug `quality-report.json`,
  `mode-c-render-report.json`, and `analysis-result.rejected.json` if present.
