# Quality Checker — SKILL.md

**Role**: Step 9 — Perform 5-item quality check on the generated output before delivery to user. Auto-patch minor issues; flag persistent failures inline.
**Triggered by**: CLAUDE.md after Step 8 (output generation), before final delivery
**Reads**: Generated output file (or inline response), `output/validated-data.json`, `output/analysis-result.json`
**Writes**: Patches to the output file; `output/quality-report.json`
**References**: None (quality standards defined in this file)

---

## Instructions

### Pre-Check Setup

Load:
1. The generated output (HTML file, Markdown file, or inline text)
2. `output/validated-data.json` (for grade reference)
3. `output/analysis-result.json` (for scenario probabilities and R/R Score)

---

## 5-Item Quality Checklist

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
- Current price appears prominently in the output (Section 1 for Mode C, first table for Mode B, executive summary for Mode D)
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
- Mode B/C: Full disclaimer in footer section
- Mode D: Full disclaimer at end of Appendix section

**Fail criteria**: No disclaimer found

**Auto-fix**: Append disclaimer from `output-generator/SKILL.md` disclaimer section.

---

### Item 4 — Source Tag Coverage

**Test**: Verify that ≥80% of numerical data points in the output have source tags.

**Procedure**:
1. Count all numerical values in the output (prices, percentages, ratios, revenue figures, etc.)
2. Count how many have source tags ([API], [Web], [Calculated], etc.)
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

**Auto-fix**: Replace the incorrect value with "—" and add tag `[Unverified — excluded]`

**This check is CRITICAL**: Fabricated data is worse than missing data. If an excluded metric appears with a value and auto-fix cannot be applied confidently, escalate:
`[Quality flag: data-integrity — {metric} appears with a value but was marked Grade D in validation. Please verify this data manually.]`

---

## Quality Report Output

Write to `output/quality-report.json`:

```json
{
  "ticker": "AAPL",
  "output_mode": "C",
  "check_timestamp": "2026-03-12T14:45:00Z",
  "overall_result": "PASS",
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
    }
  },
  "auto_fixes_applied": [],
  "inline_flags_added": []
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
    IF any inline flags added → overall = PASS_WITH_FLAGS
    IF critical failure (price missing + no fix) → overall = CRITICAL_FLAG
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

Result: PASS_WITH_FLAGS — output delivered with quality notes
```

---

## Completion Check

- [ ] All 5 quality items checked
- [ ] Auto-fixes applied where possible
- [ ] Inline flags added where auto-fix insufficient
- [ ] `output/quality-report.json` written
- [ ] Quality summary reported to user before delivering output
- [ ] Output delivered (quality issues do NOT block delivery — flags accompany the output)
