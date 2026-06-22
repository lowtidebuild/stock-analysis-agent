# Codex Runbook

This runbook is the operator-facing companion to `AGENTS.md`. It documents the
portable commands Codex should use without changing the existing Claude Code
harness.

## Prerequisites

- Run commands from the repo root.
- Use `python3`.
- Do not read `.env*` files. Configure needed variables outside the agent
  session.
- For deterministic offline analyst runs, set `ANALYST_BACKEND=fixture`.
- For live analyst runs, provide `OPENAI_API_KEY` and optionally
  `OPENAI_ANALYST_MODEL`.
- For portable web search, set `TAVILY_API_KEY` or `BRAVE_API_KEY`, or pass
  `--web-provider none` for an unavailable/skipped tier2 artifact.

## Mode A Smoke

```bash
python3 scripts/run_analysis.py \
  --ticker AAPL \
  --mode A \
  --lang en \
  --market US \
  --run-id smoke_aapl_a
```

Expected outputs are under `output/runs/smoke_aapl_a/AAPL/`. Mode A remains the
legacy headless path.

## Mode C Live Dashboard

Use `scripts/run_mode_c.py` for Codex Mode C delivery:

```bash
python3 scripts/run_mode_c.py \
  --ticker VRT \
  --mode C \
  --lang ko \
  --market US \
  --run-id codex_vrt_c \
  --web-provider tavily
```

The command prints JSON containing `report_path`, `run_id`,
`quality_report_path`, and `delivery_gate`. The published report is copied to:

```text
output/reports/{TICKER}_C_{lang}_{analysis_date}.html
```

The run-local dashboard and quality artifacts remain under:

```text
output/runs/{run_id}/{TICKER}/
```

## Mode C Offline Fixture Smoke

The lowest-friction offline check is the test-backed smoke:

```bash
ANALYST_BACKEND=fixture python3 -m pytest tests/test_run_mode_c_entrypoint.py -q
```

That test performs the full offline pattern:

1. Build skipped collection artifacts through `scripts/run_abc_parity.py`
   `--collect-only --skip-network`.
2. Add deterministic yfinance fixture data.
3. Run `scripts/run_mode_c.py --reuse-collected --skip-network`.
4. Assert the HTML report exists and the quality gate passes.

For manual reuse of an already prepared run:

```bash
ANALYST_BACKEND=fixture python3 scripts/run_mode_c.py \
  --ticker AAPL \
  --mode C \
  --lang en \
  --market US \
  --run-id pytest_run_mode_c_entrypoint_AAPL_C \
  --skip-network \
  --reuse-collected
```

Only use the manual command when the matching collected artifacts already exist
under `output/runs/{run_id}/`.

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
- `output/runs/{run_id}/{TICKER}/mode-c-dashboard.html`: run-local dashboard.
- `output/runs/{run_id}/{TICKER}/quality-report.json`: final delivery gate.
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

Before delivering a Mode C report, inspect:

```text
output/runs/{run_id}/{TICKER}/quality-report.json
```

Delivery is acceptable only when:

- `delivery_gate.result` is `PASS`
- `delivery_gate.ready_for_delivery` is `true`

If the gate is not ready, treat the report as failed even if HTML was rendered.

## Troubleshooting

- `python: command not found`: use `python3`.
- Missing analyst API key: use `ANALYST_BACKEND=fixture` for offline tests, or
  configure `OPENAI_API_KEY` outside the agent session.
- `run_abc_parity.py` raises after a full unflagged run: this is intentional.
  Use stop flags such as `--collect-only` for parity steps, or use
  `scripts/run_mode_c.py` for production Mode C.
- Eval harness fails on a glob: pass one `--manifest` path at a time.
- `tier2-raw.json` is present but no qualitative facts reach the analyst:
  validation currently does not consume tier2 fields directly. Keep raw tier2
  out of prompts unless investigating a logged mismatch.
- Quality gate fails after rendering: debug `quality-report.json`,
  `mode-c-render-report.json`, and `analysis-result.rejected.json` if present.
