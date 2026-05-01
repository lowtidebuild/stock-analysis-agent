# Bull/Bear Adversarial Debate Implementation Plan

> **Status:** Revised after verification on 2026-04-30.
>
> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

## Goal

Add a structured Bull-vs-Bear debate step for Mode C/D analyses.

Two advocate agents read the same validated facts and produce compact thesis artifacts:
- `bull-thesis.json`
- `bear-thesis.json`

The Analyst reads both before drafting Variant View Q1 and explicitly integrates:
- Bull's strongest case
- Bear's strongest case
- Analyst reconciliation

## Corrected Pipeline Decision

V1 debate runs **after Step 5 Data Validation and before the Analyst draft**.

This plan no longer uses "after Analyst first draft" or "Analyst re-dispatch" language. That design would require a draft artifact and a separate rewrite loop. V1 keeps the pipeline simpler:

```text
Step 5 validation
  -> Step 6.5 bull/bear advocates in parallel
  -> Step 6/7 Analyst writes with theses available
  -> Step 8 render
  -> Step 9 quality/critic
```

## Files

Create:
- `.claude/agents/bull-advocate/AGENT.md`
- `.claude/agents/bear-advocate/AGENT.md`
- `.claude/schemas/bull-thesis.schema.json`
- `.claude/schemas/bear-thesis.schema.json`
- `tests/test_debate_artifacts.py`

Modify:
- `tools/analysis_contract.py`
- `.claude/skills/data-validator/scripts/validate-artifacts.py`
- `tools/artifact_validation.py`
- `.claude/schemas/quality-report.schema.json`
- `CLAUDE.md`
- `.claude/agents/analyst/AGENT.md`
- `.claude/agents/critic/AGENT.md`
- `references/analysis-framework-dashboard.md`
- `references/analysis-framework-memo.md`

Do not modify:
- `.claude/skills/data-manager/scripts/artifact-manager.py` for path creation unless `tools/analysis_contract.py` proves insufficient. The manifest paths come from `tools.analysis_contract.build_run_paths()`.
- Mode A/B behavior.

## Artifact Contract

Both thesis artifacts share the same shape except `advocate`.

Required fields:
- `ticker`
- `run_id`
- `advocate`
- `generated_at`
- `status`
- `ten_word_thesis`
- `top_3_arguments`
- `three_data_points_cited`
- `what_would_make_me_wrong`

Allowed `status` values:
- `ok`
- `partial`
- `blocked_unsanitized`
- `blocked_insufficient_evidence`

When `status in {"ok", "partial"}`:
- `top_3_arguments`: 2-4 items
- `three_data_points_cited`: 3-5 items
- each argument cites metric names from `validated-data.json` or `evidence-pack.json`

When `status` starts with `blocked_`:
- `top_3_arguments`: may be empty
- `three_data_points_cited`: may be empty
- `blocker_reason`: required
- `what_would_make_me_wrong`: still required, but may describe what evidence is needed to unblock the thesis

## Task 1 - Add Artifact Paths

Modify `tools/analysis_contract.py::build_run_paths()`.

Add:

```python
"bull_thesis": ticker_root / "bull-thesis.json",
"bear_thesis": ticker_root / "bear-thesis.json",
```

Verify:

```bash
python3 .claude/skills/data-manager/scripts/artifact-manager.py init \
  --tickers TEST1 \
  --run-id 20260430T000000Z_TEST1
```

Expected:
- run manifest includes `bull_thesis`
- run manifest includes `bear_thesis`

## Task 2 - Create Schemas

Create `.claude/schemas/bull-thesis.schema.json`:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "Bull Thesis Artifact",
  "type": "object",
  "required": [
    "ticker",
    "run_id",
    "advocate",
    "generated_at",
    "status",
    "ten_word_thesis",
    "top_3_arguments",
    "three_data_points_cited",
    "what_would_make_me_wrong"
  ],
  "additionalProperties": true,
  "properties": {
    "ticker": { "type": "string", "pattern": "^[A-Z0-9]{1,10}$" },
    "run_id": { "type": "string" },
    "advocate": { "const": "bull" },
    "generated_at": { "type": "string" },
    "status": {
      "type": "string",
      "enum": ["ok", "partial", "blocked_unsanitized", "blocked_insufficient_evidence"]
    },
    "ten_word_thesis": { "type": "string", "minLength": 20, "maxLength": 220 },
    "top_3_arguments": {
      "type": "array",
      "maxItems": 4,
      "items": {
        "type": "object",
        "required": ["argument", "evidence_facts", "expected_impact", "why_consensus_misses"],
        "properties": {
          "argument": { "type": "string", "minLength": 30, "maxLength": 500 },
          "evidence_facts": {
            "type": "array",
            "items": { "type": "string" },
            "minItems": 1
          },
          "expected_impact": { "type": "string" },
          "why_consensus_misses": { "type": "string", "minLength": 20 }
        },
        "additionalProperties": true
      }
    },
    "three_data_points_cited": {
      "type": "array",
      "maxItems": 5,
      "items": {
        "type": "object",
        "required": ["metric", "value", "tag", "weight"],
        "properties": {
          "metric": { "type": "string" },
          "value": {},
          "tag": {
            "enum": ["[Filing]", "[Company]", "[Calc]", "[Est]", "[Portal]", "[KR-Portal]", "[Macro]", "[News]"]
          },
          "weight": { "enum": ["primary", "supporting"] }
        },
        "additionalProperties": true
      }
    },
    "what_would_make_me_wrong": { "type": "string", "minLength": 20 },
    "blocker_reason": { "type": ["string", "null"] },
    "model_routing_tier": { "enum": ["cheap", "strong", null] },
    "model_used": { "type": ["string", "null"] }
  }
}
```

Create `.claude/schemas/bear-thesis.schema.json` with the same shape and:

```json
"advocate": { "const": "bear" }
```

Because this repository's schema validator does not support conditional `if/then`, add semantic checks in `tools/artifact_validation.py`:

- [ ] If `status in {"ok", "partial"}`, require `len(top_3_arguments) >= 2`.
- [ ] If `status in {"ok", "partial"}`, require `len(three_data_points_cited) >= 3`.
- [ ] If `status.startswith("blocked_")`, require non-empty `blocker_reason`.

## Task 3 - Register Artifact Types

Modify `tools/artifact_validation.py`:

- [ ] Add `"bull-thesis"` and `"bear-thesis"` to `SCHEMA_ARTIFACT_TYPES`.
- [ ] Add semantic thesis validation after JSON schema validation.
- [ ] Add optional run-directory validation support if thesis files exist.

Modify `.claude/skills/data-validator/scripts/validate-artifacts.py`:

- [ ] Add `"bull-thesis"` and `"bear-thesis"` to `--artifact-type` choices.

Verify:

```bash
PYTHONPATH=. python3 - <<'PY'
from tools.artifact_validation import validate_artifact_data

payload = {
    "ticker": "AFRM",
    "run_id": "test-run",
    "advocate": "bull",
    "generated_at": "2026-04-30T00:00:00Z",
    "status": "ok",
    "ten_word_thesis": "Affirm Card adoption and Amazon renewal can compound durable FY27 revenue growth.",
    "top_3_arguments": [
        {
            "argument": "Affirm Card adoption can convert episodic BNPL users into recurring daily-spend customers.",
            "evidence_facts": ["affirm_card_holders"],
            "expected_impact": "+$30/share over 12 months",
            "why_consensus_misses": "Consensus treats card growth as a temporary campaign rather than a product mix shift."
        },
        {
            "argument": "Amazon renewal reduces distribution risk and improves transaction visibility into FY27.",
            "evidence_facts": ["amazon_renewal"],
            "expected_impact": "+150bp revenue durability",
            "why_consensus_misses": "Consensus underweights renewal duration and attached merchant credibility."
        }
    ],
    "three_data_points_cited": [
        {"metric": "affirm_card_holders", "value": 1000000, "tag": "[Company]", "weight": "primary"},
        {"metric": "amazon_renewal", "value": "renewed", "tag": "[Company]", "weight": "primary"},
        {"metric": "gmv_growth_yoy", "value": 32, "tag": "[Company]", "weight": "supporting"}
    ],
    "what_would_make_me_wrong": "Card GMV growth slows below 20 percent year over year for two consecutive quarters."
}
errs = validate_artifact_data("bull-thesis", payload)
print(errs or "NONE")
PY
```

Expected: `NONE`.

Also verify the CLI:

```bash
PYTHONPATH=. python3 .claude/skills/data-validator/scripts/validate-artifacts.py \
  --artifact-type bull-thesis \
  --input output/runs/<run_id>/<ticker>/bull-thesis.json
```

## Task 4 - Quality Report Contract

Modify `.claude/agents/critic/AGENT.md`:

- [ ] Add `debate_integration_test` to allowed critic item names.
- [ ] Add Item 1.5 Debate Integration Test.

Modify `.claude/schemas/quality-report.schema.json`:

- [ ] Add `"debate_integration_test"` to `critic_review.items[].item` enum.

Modify `tools/artifact_validation.py`:

- [ ] Add `"debate_integration_test"` to `CRITIC_REVIEW_ALLOWED_ITEMS`.

If failure status should be non-blocking, set critic item severity to `MAJOR` and delivery impact to non-blocking. Do not create a new top-level `quality-report.debate_status` unless the schema and builder also preserve it.

Canonical status location:
- `analysis-result.sections.debate_integration_status`
- `quality-report.critic_review.items[]` for failures

## Task 5 - Advocate Agents

Create `.claude/agents/bull-advocate/AGENT.md`.

Core requirements:
- Reads only run-local `evidence-pack.json`, `validated-data.json`, and `research-plan.json`.
- Does not read raw artifacts.
- Does not read Bear thesis.
- Writes `output/runs/{run_id}/{ticker}/bull-thesis.json`.
- Uses `status: "ok"` when a proper bull case can be made.
- Uses blocked status with `blocker_reason` instead of fabricating when evidence is insufficient or unsanitized.
- Must validate with `validate-artifacts.py --artifact-type bull-thesis`.

Create `.claude/agents/bear-advocate/AGENT.md` with mirrored rules and `advocate: "bear"`.

Banned behavior for both:
- Fabricating metrics.
- Citing data not present in validated artifacts.
- Reading raw artifacts.
- Hedging into the other advocate's role.

## Task 6 - CLAUDE.md Orchestrator

Modify `CLAUDE.md`.

Add Step 6.5 between Step 5 and Analyst:

```markdown
### Step 6.5 - Bull/Bear Adversarial Debate (Mode C/D only)

Skip for Mode A and Mode B.

For Mode C/D:
1. Dispatch `bull-advocate` and `bear-advocate` in parallel.
2. Inputs: run-local `evidence-pack.json`, `validated-data.json`, `research-plan.json`.
3. Outputs: run-local `bull-thesis.json`, `bear-thesis.json`.
4. Validate both artifacts.
5. If one advocate fails, proceed with the available thesis and set `sections.debate_integration_status = "partial"` in `analysis-result.json`.
6. If both fail, proceed with legacy Analyst flow and set `sections.debate_integration_status = "skipped"`.
```

Update Section 7 dispatch table:

```markdown
| bull-advocate | Mode C/D after Step 5 | evidence-pack, validated-data, research-plan | bull-thesis.json | 1 per workflow run |
| bear-advocate | Mode C/D after Step 5, parallel with bull | same as bull | bear-thesis.json | 1 per workflow run |
```

Update file paths:

```text
bull-advocate receives: ["output/runs/{run_id}/{ticker}/evidence-pack.json", "output/runs/{run_id}/{ticker}/validated-data.json", "output/runs/{run_id}/{ticker}/research-plan.json"]
bear-advocate receives: same as bull
```

Update timeout table:

```markdown
| Sub-agent (bull-advocate) | 90 seconds | Proceed with bear-only or skip debate |
| Sub-agent (bear-advocate) | 90 seconds | Proceed with bull-only or skip debate |
```

Update Quality Gate Summary:
- Mention `debate_integration_test` as an optional narrative critic item for Mode C/D when both thesis artifacts exist.

## Task 7 - Analyst Integration

Modify `.claude/agents/analyst/AGENT.md`.

Inputs:
- [ ] Add optional `bull-thesis.json` and `bear-thesis.json` for Mode C/D.

Variant View Q1 rule:

When both thesis artifacts have `status in {"ok", "partial"}`, Q1 must use four paragraphs:

1. Market consensus
2. **Bull's strongest case**
3. **Bear's strongest case**
4. **My reconciliation**

When only one thesis is available:
- Use three paragraphs: market consensus, available advocate case, analyst reconciliation.
- Set `sections.debate_integration_status = "partial"`.

When neither thesis is available:
- Use legacy Q1 pattern.
- Set `sections.debate_integration_status = "skipped"`.

## Task 8 - Framework Docs

Modify `references/analysis-framework-dashboard.md`:

- [ ] Section 4 Variant View Q1 requires Bull/Bear pattern when thesis artifacts exist.
- [ ] Include fallback patterns for partial/skipped debate.

Modify `references/analysis-framework-memo.md`:

- [ ] Apply the same Q1 structure for Mode D.

## Task 9 - Contract Tests

Create `tests/test_debate_artifacts.py`.

Required tests:
- [ ] Minimal bull with `status: "ok"` passes.
- [ ] Minimal bear with `status: "ok"` passes.
- [ ] Bull artifact with `advocate: "bear"` fails.
- [ ] `status: "ok"` with one argument fails semantic validation.
- [ ] `status: "ok"` with two data points fails semantic validation.
- [ ] `status: "blocked_insufficient_evidence"` with empty arguments passes when `blocker_reason` exists.
- [ ] `debate_integration_test` is accepted by `quality-report` schema and validator.
- [ ] `artifact-manager.py init` manifest includes `bull_thesis` and `bear_thesis`.

Run:

```bash
PYTHONPATH=. python3 -m pytest tests/test_debate_artifacts.py -v
```

Expected: all tests pass.

## Definition of Done

- [ ] `tools/analysis_contract.py` exposes bull/bear thesis paths.
- [ ] `validate-artifacts.py --artifact-type bull-thesis` works.
- [ ] `validate-artifacts.py --artifact-type bear-thesis` works.
- [ ] Thesis schemas and semantic validators agree on blocked vs ok status.
- [ ] Quality report schema and validator both allow `debate_integration_test`.
- [ ] CLAUDE.md places debate after Step 5 and before Analyst.
- [ ] Analyst docs require explicit Bull/Bear Q1 integration.
- [ ] Mode A/B unchanged.
- [ ] A PLTR or AFRM Mode C/D smoke run can produce, validate, and integrate both thesis artifacts.

## Open Decisions

1. **Cost**: V1 adds two advocate calls for Mode C/D. Default: strong model for both advocates.
2. **Backfill**: Do not re-analyze historical snapshots by default.
3. **Output language**: Thesis JSON text should match `output_language` when known; otherwise English is acceptable.
4. **Partial debate UX**: Partial debate should be visible in `sections.debate_integration_status`, not a hard delivery blocker.

## Out of Scope

- Multi-round debate.
- Moderator agent.
- Mode A/B debate.
- Advocates collecting new data.
- Post-draft Analyst re-dispatch.

