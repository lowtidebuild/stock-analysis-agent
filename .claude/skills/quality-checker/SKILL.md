# Quality Checker — SKILL.md

**Role**: Step 9 — Perform output-facing quality checks and rebuild the deterministic run-local quality report before delivery to user. Auto-patch minor issues; flag persistent failures inline.
**Triggered by**: CLAUDE.md after Step 8 (output generation), before final delivery
**Reads**: Generated output file (or inline response), run-local `validated-data.json`, run-local `analysis-result.json`
**Writes**: Patches to the output file; run-local `quality-report.json`
**References**: None (quality standards defined in this file)

---

## Instructions

### Pre-Check Setup

Load:
1. The generated output (HTML file, Markdown file, or inline text)
2. run-local `validated-data.json` (for grade reference)
3. run-local `analysis-result.json` (for scenario probabilities and R/R Score)
4. Existing run-local `quality-report.json` if present (merge output-facing checks with contract/semantic checks)

After the output-facing checks, rebuild the canonical run-local quality report:

```bash
python .claude/skills/quality-checker/scripts/quality-report-builder.py --run-dir output/runs/{run_id}
```

---

## Mode A Simplified Check (3 items only)

Mode A uses a lightweight quality check — Items 1, 2, and 5 only. Skip Items 3 (disclaimer — checked during HTML generation) and 4 (source tag coverage — Mode A has only 3 KPIs). No Critic Agent is dispatched for Mode A.

```
IF output_mode = "A":
    Run Items 1, 2, 5 only
    Skip Items 3, 4
    Skip Critic dispatch
    Write quality-report.json with 3-item result
```

---

## 5-Item Output-Facing Checklist

These manual checks focus on the rendered user output. The canonical quality-report builder also adds deterministic artifact checks, including `contract_validation`, `scenario_consistency`, `semantic_consistency`, `verdict_policy`, `cross_artifact_consistency`, and optional `rendered_output`. Do not delegate these mechanical checks to the critic agent.

### Item 1 — Financial Data Consistency

**Test**: Randomly sample 3 numerical values from the output and verify them against `validated-data.json`.

**Procedure**:
1. Pick 3 values from the output (prefer: market cap, P/E, revenue — the most commonly cited)
2. Look up the same values in `validated-data.json`
3. Check if they match (within 1% rounding tolerance)

**Pass criteria**: All 3 sampled values match their source within 1% rounding
**Fail criteria**: Any value differs from source by >1% without explanation

**Auto-fix**: Correct the wrong value to match `validated-data.json`. Mark correction as `[corrected]` in output.

**If auto-fix fails**: Add inline flag: `[Quality flag: financial-consistency — {metric} value may be incorrect, please verify]`

---

### Item 2 — Price and Date Presence

**Test**: Verify that the current price and analysis date are both present and non-null in the output.

**Pass criteria**:
- Current price appears prominently in the output (verdict card for Mode A, Section 1 for Mode C, first table for Mode B, executive summary for Mode D)
- Analysis date appears in the output
- Price is in correct currency format ($ for US, ₩ for KR)
- Date is in YYYY-MM-DD format

**Fail criteria**:
- Price field is missing, null, or shows "—" (price Grade D = critical failure, not just quality issue)
- Analysis date missing

**Auto-fix**: Add price from `validated-data.json.validated_metrics.price_at_analysis` if available.

**If price is null**: Do NOT substitute. Add: `[Quality flag: price-missing — Current price unavailable. Analysis based on most recent available data.]`

---

### Item 3 — Disclaimer Presence

**Test**: Verify that a disclaimer is present in the output.

**Pass criteria**:
- Mode A: Disclaimer in HTML footer (checked during generation — skip in quality check)
- Mode B/C: Full disclaimer in footer section
- Mode D: Full disclaimer at end of Appendix section

**Fail criteria**: No disclaimer found

**Auto-fix**: Append disclaimer from `output-generator/SKILL.md` disclaimer section.

---

### Item 4 — Source Tag Coverage

**Test**: Verify that ≥80% of numerical data points in the output have source tags.

**Procedure**:
1. Count all numerical values in the output (prices, percentages, ratios, revenue figures, etc.)
2. Count how many have source tags ([Filing], [Company], [Portal], [KR-Portal], [Calc], [Est], [Macro])
3. Calculate: tagged_count / total_count × 100

**Pass criteria**: ≥80% of numerical values have source tags

**Fail criteria**: <80% coverage

**Auto-fix**: Identify untagged values, look them up in `validated-data.json`, add appropriate tags.

**If auto-fix fails** (cannot determine correct tag): Add blanket note at bottom: `[Quality flag: source-tags — Some numerical values may lack source attribution. Data from {data_mode} collection on {date}.]`

---

### Item 5 — Blank-Over-Wrong Principle Enforcement

**Test**: Verify that no Grade D metric from `validated-data.json.exclusions` appears as a real value in the output.

**Procedure**:
1. Read `validated-data.json.exclusions` → list of Grade D metric names
2. For each excluded metric, search the output for the metric name
3. Check: if the metric appears in the output, does it show "—" or "[Data unavailable]"?

**Pass criteria**: All excluded (Grade D) metrics display as "—" or are absent from output

**Fail criteria**: An excluded metric appears with a numerical value (not "—")

**Auto-fix**: Replace the incorrect value with "—" and add note `[Grade D — excluded]`

**This check is CRITICAL**: Fabricated data is worse than missing data. If an excluded metric appears with a value and auto-fix cannot be applied confidently, escalate:
`[Quality flag: data-integrity — {metric} appears with a value but was marked Grade D in validation. Please verify this data manually.]`

---

## Quality Report Output

Write to `output/runs/{run_id}/{ticker}/quality-report.json`:

```json
{
  "ticker": "AAPL",
  "output_mode": "C",
  "check_timestamp": "2026-03-12T14:45:00Z",
  "overall_result": "PASS",
  "delivery_gate": {
    "result": "PASS",
    "ready_for_delivery": true,
    "blocking_items": [],
    "patchable_blocking_items": [],
    "terminal_blocking_items": [],
    "blocker_actions": {},
    "non_blocking_items": [],
    "historical_only_items": [],
    "max_severity": "NONE",
    "item_severities": {},
    "critic_overall": null,
    "critic_severity": "NONE",
    "critic_delivery_impact": "none"
  },
  "items": {
    "financial_consistency": {
      "status": "PASS",
      "sampled_values": [
        {"metric": "market_cap", "output_value": 2718000, "source_value": 2718000, "match": true},
        {"metric": "pe_ratio", "output_value": 28.0, "source_value": 28.0, "match": true},
        {"metric": "revenue_ttm", "output_value": 395000, "source_value": 395000, "match": true}
      ]
    },
    "price_and_date": {
      "status": "PASS",
      "price_found": 175.50,
      "date_found": "2026-03-12"
    },
    "disclaimer": {
      "status": "PASS"
    },
    "source_tags": {
      "status": "PASS",
      "total_numeric_values": 45,
      "tagged_values": 38,
      "coverage_pct": 84.4
    },
    "blank_over_wrong": {
      "status": "PASS",
      "excluded_metrics_checked": ["ev_ebitda"],
      "violations_found": 0
    },
    "contract_validation": {
      "status": "PASS"
    },
    "scenario_consistency": {
      "status": "PASS",
      "probability_sum": 1.0
    },
    "semantic_consistency": {
      "status": "PASS",
      "error_count": 0
    },
    "verdict_policy": {
      "status": "PASS"
    },
    "cross_artifact_consistency": {
      "status": "PASS",
      "error_count": 0
    }
  },
  "auto_fixes_applied": [],
  "inline_flags_added": [],
  "generated_by": "quality-report-builder"
}
```

---

## Pass / Fail / Auto-fix Protocol

```
FOR each of the 5 items:
    IF PASS → continue
    IF FAIL:
        1. Attempt auto-fix (patch the output directly)
        2. Re-check the patched output
        3. IF re-check PASS → log auto_fix_applied, continue
        4. IF re-check FAIL → add [Quality flag: {item}] inline to output
            (do NOT block output delivery — user still gets the output with flags)

After all 5 checks:
    IF all PASS or auto-fixed → overall = PASS
    Assign severity per item:
        - BLOCKER: structural, security, data-integrity, or fabricated-value failure
        - MAJOR: important but deliverable quality issue
        - MINOR: wording, historical migration, or localized polish issue
        - NONE: PASS/SKIP
    IF any inline flags added → overall = PASS_WITH_FLAGS
    IF critical failure (price missing + no fix) → overall = CRITICAL_FLAG
    THEN compute delivery_gate separately:
        - BLOCKER → delivery_gate.result = BLOCKED
        - patchable BLOCKER → add to patchable_blocking_items and use one repair/recheck attempt if budget remains
        - terminal BLOCKER → add to terminal_blocking_items and do not auto-retry delivery
        - MAJOR/MINOR → delivery_gate.result = PASS with non_blocking_items
        - historical-only flags → delivery_gate.result = PASS with historical_only_items
```

---

## Inline Flag Format

Flags are added inline in the output where the issue is located:

**HTML output**:
```html
<div class="bg-amber-950 border border-amber-700 rounded px-3 py-2 text-amber-300 text-xs my-2">
  ⚠️ Quality flag: {item} — {description}
</div>
```

**Markdown output**:
```
> ⚠️ **Quality flag**: {item} — {description}
```

---

## Summary Report to User

After quality check:

```
=== Quality Check: {TICKER} Mode {mode} ===
✓ Financial consistency: PASS (3/3 sampled values verified)
✓ Price and date: PASS
✓ Disclaimer: PASS
✓ Source tag coverage: PASS (84.4%)
✓ Blank-over-wrong: PASS

Result: PASS — delivering output
```

If flags:
```
=== Quality Check: {TICKER} ===
✓ Financial consistency: PASS
✗ Source tags: FAIL → Auto-fix applied (added tags to 7 values) → PASS after fix
✓ Disclaimer: PASS
⚠️ Blank-over-wrong: FAIL → [Quality flag added inline]

Result: PASS_WITH_FLAGS — output delivered with quality notes when delivery_gate = PASS
```

---

## Completion Check

- [ ] All 5 quality items checked
- [ ] Auto-fixes applied where possible
- [ ] Inline flags added where auto-fix insufficient
- [ ] `output/runs/{run_id}/{ticker}/quality-report.json` written
- [ ] Quality summary reported to user before delivering output
- [ ] Output delivered only when `delivery_gate.ready_for_delivery = true`; MAJOR/MINOR flags accompany the output
