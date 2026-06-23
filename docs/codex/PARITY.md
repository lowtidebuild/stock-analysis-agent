# Codex Parity Report

Captured: 2026-06-22

## Scope

This report closes the required parity/regression check for the Codex harness
port and records one concrete Mode C example:

- Ticker: `000660` / SK hynix
- Market: `KR`
- Requested basis: 2026-06-22 close
- Codex run id: `codex_parity_000660_20260622_close`
- Report: `output/reports/000660_C_ko_2026-06-22.html`

The run used live as-of raw data collection where credentials/network allowed:

- `yfinance-raw.json`: collected with `--as-of 2026-06-22`
- `dart-api-raw.json`: collected with `--as-of 2026-06-22`
- `fred-raw.json`: collected with `--as-of 2026-06-22`
- `tier2-raw.json`: unavailable/skipped because no Tavily or Brave key was
  present in the Codex environment
- analyst backend: `ANALYST_BACKEND=fixture`, because `OPENAI_API_KEY` was not
  present in the Codex environment

This is therefore a data-path and delivery-gate parity smoke, not a final live
LLM-quality parity run.

## Regression Checks

Full test suite:

```bash
python3 -m pytest tests/ -q
```

Result:

```text
635 passed, 3 skipped, 294 subtests passed
```

Mode C entrypoint smoke:

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

Result: `delivery_gate=PASS` with `fixture_delivery_guard` recorded as a
non-blocking smoke flag. The same entrypoint test file also verifies that the
fixture path is blocked without `--allow-fixture-delivery`, and that the Korean
Mode C entrypoint publishes a localized dashboard with translated chart labels.

Focused Codex parity guardrail checks:

```bash
python3 -m pytest \
  tests/test_abc_parity_rendering.py \
  tests/test_rendered_output_validation.py \
  tests/test_abc_parity_analyst.py \
  tests/test_quality_report_numeric_sanity.py \
  tests/test_validation_sanity.py \
  tests/test_quality_report_scenario_consistency.py \
  tests/test_delivery_severity.py \
  tests/test_run_mode_c_entrypoint.py \
  -q
```

Result: `49 passed`.

Eval harness, manifest by manifest:

| Manifest | Result | Notes |
| --- | ---: | --- |
| `evals/cases/analysis-patch-regressions.json` | 6 passed, 0 failed | all matched expectation |
| `evals/cases/critic-recheck-regressions.json` | 2 passed, 0 failed | all matched expectation |
| `evals/cases/default.json` | 6 passed, 1 failed | existing AAPL Mode C fixture contract gap |
| `evals/cases/golden-runs.json` | 4 passed, 1 failed | existing AAPL Mode C fixture contract gap |
| `evals/cases/legacy-regressions.json` | 4 passed, 0 failed | all matched expectation |
| `evals/cases/patch-loop-result-regressions.json` | 4 passed, 0 failed | all matched expectation |
| `evals/cases/patch-plan-regressions.json` | 6 passed, 0 failed | all matched expectation |
| `evals/cases/quality-report-regressions.json` | 2 passed, 0 failed | all matched expectation |
| `evals/cases/semantic-regressions.json` | 2 passed, 0 failed | all matched expectation |
| `evals/cases/temporal-consistency.json` | 6 passed, 0 failed | all matched expectation |

Aggregate: 42 passed, 2 failed across 44 cases.

Known failures unchanged from `docs/codex/BASELINE.md`:

- `default.json::run_local_fixture_should_pass`
- `golden-runs.json::golden_aapl_mode_c_fixture`

Both still fail on the existing AAPL Mode C fixture:

- `sections.precision_risks[*].financial_impact` missing
- `sections.macro_context.structured` missing the required FRED status object

## SK Hynix Codex Mode C Example

Preparation:

```bash
ANALYST_BACKEND=fixture python3 scripts/run_abc_parity.py \
  --ticker 000660 \
  --mode C \
  --lang ko \
  --market KR \
  --run-id codex_parity_000660_20260622_close \
  --collect-only \
  --skip-network
```

As-of raw data collection:

```bash
python3 .claude/skills/financial-data-collector/scripts/yfinance-collector.py \
  --ticker 000660 \
  --market KR \
  --output output/runs/codex_parity_000660_20260622_close/000660/yfinance-raw.json \
  --bundle standard \
  --timeout 30 \
  --as-of 2026-06-22

python3 .claude/skills/web-researcher/scripts/dart-collector.py \
  --stock-code 000660 \
  --output output/runs/codex_parity_000660_20260622_close/000660/dart-api-raw.json \
  --as-of 2026-06-22

python3 .claude/skills/web-researcher/scripts/fred-collector.py \
  --market KR \
  --output output/runs/codex_parity_000660_20260622_close/macro/fred-raw.json \
  --as-of 2026-06-22
```

Mode C run:

```bash
ANALYST_BACKEND=fixture python3 scripts/run_mode_c.py \
  --ticker 000660 \
  --mode C \
  --lang ko \
  --market KR \
  --run-id codex_parity_000660_20260622_close \
  --reuse-collected \
  --skip-network \
  --web-provider none \
  --allow-fixture-delivery
```

Result:

```json
{
  "report_path": "output/reports/000660_C_ko_2026-06-22.html",
  "run_id": "codex_parity_000660_20260622_close",
  "quality_report_path": "output/runs/codex_parity_000660_20260622_close/000660/quality-report.json",
  "delivery_gate": "PASS",
  "run_profile": "smoke"
}
```

Key fields:

| Field | Codex 2026-06-22 close run |
| --- | ---: |
| `analysis_date` | `2026-06-22` |
| `company_name` | `SK하이닉스` |
| `source_profile` | `sec_or_dart_primary` |
| `confidence_cap` | `A` |
| `overall_grade` | `B` |
| `price_at_analysis` | 2,919,000 KRW |
| `price_at_analysis.grade` | `C` |
| `price_at_analysis.as_of` | `2026-06-22` |
| `market_cap` | 2,072,066.4382 KRW bn |
| `revenue_ttm` | 132,083.821 KRW bn |
| `operating_margin` | 58.5811% |
| `fcf_ttm` | 40,689.552 KRW bn |
| `analyst_target_mean` | `null` / Grade D |
| `verdict` | `underweight` |
| `rr_score` | 0.5591 |
| `bull.target` | 3,524,692.5 KRW |
| `base.target` | 3,064,950.0 KRW |
| `bear.target` | 1,313,550.0 KRW |
| `dcf_analysis.base.fair_value` | 1,277,742.24 KRW |
| `dcf_analysis.reverse.implied_fcf_growth` | 0.3182 |
| `valuation_bridge.weighted_fair_value` | `null` |
| `quality_report.overall_result` | `PASS_WITH_FLAGS` |
| `delivery_gate.result` | `PASS` |
| `delivery_gate.ready_for_delivery` | `true` |
| `run_context.run_profile` | `smoke` |
| `quality_report.items.fixture_delivery_guard.status` | `PASS_WITH_FLAGS` |
| `quality_report.items.numeric_sanity.status` | `PASS` |
| `mode_c_render_report.validation.status` | `PASS` |

The regenerated smoke HTML is about 63 KB. It is useful for renderer and
delivery-gate regression checks, but it is not a production-quality analyst
report because it still uses the fixture backend and no qualitative web
provider.

## Quality Parity Benchmark

This SK하이닉스 report remains a quality-parity benchmark, not a deliverable
production report. The current smoke rerun has better Korean renderer chrome and
chart labels than the original failing sample, but it is still structurally
useful rather than analyst-complete because it uses fixture analysis and no live
Tier2 research provider.

| Area | Original gap | Current smoke state |
| --- | --- | --- |
| Visual | Basic Tailwind card/grid dashboard, below Claude Code report polish | Still functional rather than premium |
| Korean localization | English headings, chart labels, table labels, footer, and fallback prose | Major chrome, count suffixes, chart labels, and footer are localized |
| Analyst content | Fixture analyst text with repeated generic thesis language | Still fixture-driven and smoke-only |
| Research completeness | Tier2 unavailable, analyst target cards blank, peer row placeholder | Still no live qualitative provider; coverage remains unavailable |
| Data presentation | KR market peer row displayed market cap with `$` and mixed English labels | KRW formatting and common Korean labels improved; source appendix claims remain raw evidence text |
| Gate strictness | Old structural delivery gate passed despite quality gaps | Fixture delivery is blocked unless explicitly allowed; allowed runs carry a non-blocking smoke flag |

Session 1 of the quality-parity work adds a production/smoke profile guard:

- `scripts/run_mode_c.py` now records `run_profile` in
  `analysis-result.run_context`.
- Fixture backends default to `run_profile=smoke`.
- `tools/quality_report.py` adds `fixture_delivery_guard` for Mode C.
- Fixture/smoke runs are delivery-blocked unless
  `--allow-fixture-delivery` is explicitly supplied.

Expected behavior after Session 1:

| Run type | Expected delivery behavior |
| --- | --- |
| Live analyst backend, production profile | Can pass if all other gates pass |
| Fixture backend without `--allow-fixture-delivery` | `delivery_gate.result=BLOCKED` |
| Fixture backend with `--allow-fixture-delivery` | `delivery_gate.result=PASS`, with `fixture_delivery_guard` as a non-blocking smoke flag |

## Nearby Claude Snapshot Comparison

The latest local 000660 snapshot before this Codex example is:

```text
output/data/000660/snapshots/2026-06-18_run_run_20260618T0909Z_000660
```

It is a 2026-06-18 snapshot, not the same 2026-06-22 close basis. Differences
below therefore mix data-date movement with harness/analyst differences.

| Field | Claude/local 2026-06-18 snapshot | Codex 2026-06-22 close run |
| --- | ---: | ---: |
| `price_at_analysis` | 2,685,000 | 2,919,000 |
| `source_profile` | `sec_or_dart_primary` | `sec_or_dart_primary` |
| `confidence_cap` | `A` | `A` |
| `overall_grade` | `B` | `B` |
| `verdict` | `Neutral` | `underweight` |
| `rr_score` | 1.15 | 0.5591 |
| `bull.target` | 3,410,000 | 3,524,692.5 |
| `base.target` | 2,800,000 | 3,064,950.0 |
| `bear.target` | 1,745,000 | 1,313,550.0 |
| `dcf_analysis.base.fair_value` | 793,194.67 | 1,277,742.24 |
| `dcf_analysis.reverse.implied_fcf_growth` | 0.2316 | 0.3182 |
| `valuation_bridge.weighted_fair_value` | `null` | `null` |
| `delivery_gate.result` | `PASS` | `PASS` |
| `delivery_gate.ready_for_delivery` | `true` | `true` |

Interpretation:

- The Codex run reaches the same artifact structure and delivery gate.
- The data path is materially working for a KR Mode C run, including
  yfinance-as-of, DART-as-of, and FRED-as-of artifacts.
- The report-quality comparison is not conclusive because this run used the
  fixture analyst and no qualitative tier2 web research.
- The largest visible quality gap is still qualitative research density:
  analyst target remained Grade D in the Codex example because portable web
  search had no provider key and the yfinance as-of mode intentionally skips
  forward-looking analyst targets.

## Next Quality Work

To raise Codex output quality toward Claude Code output quality:

1. Run the same 000660 flow with `OPENAI_API_KEY` and a web provider key present
   so the analyst and tier2 qualitative layer are both live.
2. Improve portable tier2 extraction for KR equities:
   `analyst_coverage`, `news_items`, `macro_context.qualitative`, and
   `extracted_metric_candidates`.
3. Add an explicit `--as-of` option to `scripts/run_mode_c.py` so the manual
   prepare-and-reuse flow above becomes a single supported command.
4. Re-run a same-date Claude/Codex comparison when a Claude 2026-06-22
   snapshot is available.
