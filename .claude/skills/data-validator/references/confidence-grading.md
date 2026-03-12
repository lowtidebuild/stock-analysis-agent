# Data Confidence Grading Reference

This file provides the decision tree for assigning A/B/C/D confidence grades to each data point. Read this alongside `validation-rules.md` during Step 5d.

---

## Grade Definitions

| Grade | Name | Tag Displayed | Usage in Analysis |
|-------|------|---------------|-------------------|
| **A — Verified** | Primary source + arithmetic consistent | No tag (clean) | Full use, state value directly |
| **B — Cross-Referenced** | 2 sources + ≤5% discrepancy + arithmetic consistent | `[≈]` | Use with range notation if discrepancy visible |
| **C — Single-Source** | 1 source only, arithmetic consistent | `[1S]` | Use with "단일 소스 기준" caveat |
| **D — Unverified** | Cannot confirm OR arithmetic inconsistent | `[Unverified]` | **Exclude from analysis. Display "—"** |

---

## Decision Tree

```
For each data point:

1. Was it fetched directly from a primary authoritative source?
   (US: SEC EDGAR direct fetch of 10-K/10-Q/8-K)
   (KR: DART 전자공시 direct fetch of 재무제표)

   YES → Is it arithmetic-consistent with other verified data?
     YES → Grade A (no tag)
     NO → Investigate: is the inconsistency in this data point or another?
           If this point is clearly correct and other is wrong → Grade A
           If unclear → Grade C [1S]

   NO → Continue to step 2

2. Do ≥2 independent sources confirm this data point?
   (Independent = different companies/databases, not the same data licensed to both)

   Examples of INDEPENDENT sources: SEC filing + Yahoo Finance
   Examples of NOT independent: Yahoo Finance + Google Finance (often same vendor data)

   YES → What is the discrepancy?
     ≤5% → Grade B [≈]
     5-15% → Grade C [1S] (use primary source value)
     >15% → Grade D [Unverified]

   NO → Only 1 source available → Continue to step 3

3. Single-source check: Is this single-source value arithmetic-consistent with other data?

   YES → Grade C [1S]
   NO → Can the inconsistency be explained? (e.g., different fiscal quarter, different share count vintage)
     YES, explained → Grade C [1S] with note
     NO → Grade D [Unverified]

4. Data completely unavailable → Grade D [Unverified]
```

---

## Specific Examples

### Example 1: Self-Calculated P/E (Grade A)
- Yahoo Finance shows P/E = 28.0x
- You calculate: Price $175.50 / TTM EPS $6.43 = 27.3x
- Discrepancy = 2.6%
- SEC filing confirms EPS $6.43
- **Grade A** (self-calculated from verified inputs, note: `[Calculated]`)

### Example 2: Revenue from two portals (Grade B)
- Yahoo Finance shows Q revenue = $89.5B
- Google Finance shows Q revenue = $89.7B
- Discrepancy = 0.22% (< 5%)
- No SEC filing fetch done
- **Grade B** `[≈]` — display as "$89.5–89.7B"

### Example 3: Only one portal available (Grade C)
- Yahoo Finance shows net debt = $45B
- No other source found
- Arithmetic check: Market Cap + Net Debt = stated EV within 8% → consistent
- **Grade C** `[1S]` — display as "~$45B [1S]"

### Example 4: Sources contradict (Grade D)
- Yahoo Finance: Quarterly revenue = $89.5B
- Macrotrends: Quarterly revenue = $76.3B (15% lower)
- Cannot determine which fiscal quarter each covers
- Cannot verify via SEC fetch
- **Grade D** `[Unverified]` — display as "—" with note: "Revenue data unverified due to source discrepancy"

### Example 5: Korean stock (maximum Grade B)
- DART filing shows operating income 15.8조원
- 네이버금융 shows 15.7조원
- Discrepancy = 0.6%
- **Grade B** `[≈]` — (KR data cannot achieve Grade A regardless of primary-ness)

### Example 6: Arithmetic inconsistency (Grade D)
- Source A: Revenue = $100B, Net Margin = 30%, implies Net Income = $30B
- Source B: Net Income = $18B
- Cannot reconcile: either revenue or margin or net income is wrong
- **Grade D for net income** until resolved; re-search for clarification

---

## "빈칸 원칙" Enforcement

**Grade D data MUST**:
1. Have `value: null` in `validated-data.json`
2. Have `exclusion_reason` field explaining why
3. Display as "—" in ALL output modes (not "N/A", not "unavailable", not a guessed number)
4. Have an explicit note in the output: "해당 지표는 확인되지 않아 표시하지 않습니다"
5. NEVER be used in analysis conclusions

**Grade D data MUST NOT**:
- Appear as any numerical value in the output
- Be used to calculate other metrics (which would contaminate their grade)
- Be estimated or interpolated
- Be replaced with "typical" sector values

---

## Special Cases

### Negative Earnings
- If net income < 0: P/E is "N/A (negative earnings)" — not Grade D, just inapplicable
- Tag as `[Calculated]` with note "N/A — negative earnings"
- Still display as "—" in P/E column but with "N/A" label, not silence

### Pre-revenue Companies (Biotech)
- Revenue may legitimately be $0 or near-$0
- Grade A if SEC filing confirms zero revenue
- P/E, EV/EBITDA: N/A — display guidance to use P/S or EV/Pipeline instead

### EBITDA Not Disclosed
- Many companies don't report EBITDA directly
- Self-calculate from Operating Income + D&A
- If D&A not separately disclosed: Grade C (estimated) with note
- Tag: `[Calculated]`

### Fiscal Year Mismatch
- When two sources use different fiscal quarters → Grade C with note about timing difference
- Always specify reporting period: "FY2Q 2026" not just "Q2"

---

## Output Format in validated-data.json

```json
"validated_metrics": {
  "price": {
    "value": 175.50,
    "grade": "A",
    "sources": ["Yahoo Finance", "Self-calculated from SEC data"],
    "tag": null,
    "note": null
  },
  "pe_ratio": {
    "value": 27.3,
    "grade": "A",
    "sources": ["Self-calculated: $175.50 / $6.43"],
    "tag": "[Calculated]",
    "note": "Formula: Price / TTM EPS (diluted)"
  },
  "net_debt_ebitda": {
    "value": null,
    "grade": "D",
    "sources": [],
    "tag": "[Unverified]",
    "exclusion_reason": "Net debt figures from Yahoo Finance ($45B) and Macrotrends ($38B) differ by 18.4%, exceeding 15% threshold. Cannot resolve without SEC filing fetch. Excluded from analysis."
  }
}
```
