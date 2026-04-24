# Data Confidence Grading Reference

This file provides the decision tree for assigning A/B/C/D confidence grades to each data point. Read this alongside `validation-rules.md` during Step 5d.

**Core principle**: Grades are determined by the **original authority** of the data (who published it), NOT the **delivery method** (API vs web). Financial Datasets MCP serves SEC filing data — the authority is SEC. DART OpenAPI serves FSS filing data — the authority is Korean FSS. Both are regulatory sources eligible for Grade A.

**Canonical metadata rule**: A metric must distinguish `source_type`, `source_authority`, and `display_tag`. Legacy tags like `[KR-Web]`, `[DART-API]`, `[Calculated]`, and `[≈]` are not canonical.

---

## Grade Definitions

| Grade | Name | Criteria | Usage in Analysis |
|-------|------|----------|-------------------|
| **A — Verified** | Regulatory filing source (SEC/DART) + arithmetic consistent | Full use, state value directly |
| **B — Cross-Referenced** | 2+ independent sources within 5% + arithmetic consistent | Use, note range if discrepancy visible |
| **C — Single-Source** | 1 source only, arithmetic consistent | Use with "단일 소스 기준" caveat |
| **D — Unverified** | Cannot confirm OR arithmetic inconsistent | **Exclude from analysis. Display "—"** |

---

## Decision Tree

```
For each data point:

1. Does it originate from a primary regulatory filing?
   (US: SEC filing data — whether via Financial Datasets MCP, SEC EDGAR WebFetch, or other source)
   (KR: DART filing data — whether via DART OpenAPI, DART web scraping, or other source)

   YES → Is it arithmetic-consistent with other verified data?
     YES → Grade A
     NO → Investigate: is the inconsistency in this data point or another?
           If this point is clearly correct and other is wrong → Grade A
           If unclear → Grade C

   NO → Continue to step 2

2. Do ≥2 independent sources confirm this data point?
   (Independent = different companies/databases, not the same data licensed to both)

   Examples of INDEPENDENT sources: SEC filing + Yahoo Finance, DART + 네이버금융
   Examples of NOT independent: Yahoo Finance + Google Finance (often same vendor data)

   YES → What is the discrepancy?
     ≤5% → Grade B
     5-15% → Grade C (use primary source value)
     >15% → Grade D

   NO → Only 1 source available → Continue to step 3

3. Single-source check: Is this single-source value arithmetic-consistent with other data?

   YES → Grade C
   NO → Can the inconsistency be explained? (e.g., different fiscal quarter, different share count vintage)
     YES, explained → Grade C with note
     NO → Grade D

4. Data completely unavailable → Grade D
```

---

## Specific Examples

### Example 1: Self-Calculated P/E (Grade A)
- <PORTAL_NAME> shows P/E = <PORTAL_PE>x
- You calculate: Price <CURRENT_PRICE> / TTM EPS <EPS_TTM> = <CALCULATED_PE>x
- Discrepancy = <DIFFERENCE_PCT>%
- SEC filing confirms EPS <EPS_TTM>
- **Grade A** `[Calc]` — self-calculated from verified inputs

### Example 2: Revenue from two portals (Grade B)
- <PORTAL_1> shows Q revenue = <REVENUE_VALUE_1>
- <PORTAL_2> shows Q revenue = <REVENUE_VALUE_2>
- Discrepancy = <DIFFERENCE_PCT>% (< 5%)
- No SEC filing fetch done
- **Grade B** `[Portal]` — display as "<SOURCE_RANGE>"

### Example 3: Only one portal available (Grade C)
- <PORTAL_NAME> shows net debt = <NET_DEBT_VALUE>
- No other source found
- Arithmetic check: Market Cap + Net Debt = stated EV within 8% → consistent
- **Grade C** `[Portal]` — display as "~<NET_DEBT_VALUE>"

### Example 4: Sources contradict (Grade D)
- <PORTAL_1>: Quarterly revenue = <REVENUE_VALUE_1>
- <PORTAL_2>: Quarterly revenue = <REVENUE_VALUE_2> (<DIFFERENCE_PCT>% lower)
- Cannot determine which fiscal quarter each covers
- Cannot verify via SEC fetch
- **Grade D** — display as "—" with note: "Revenue data unverified due to source discrepancy"

### Example 5: Korean stock from DART (Grade A)
- DART filing shows operating income <DART_OPERATING_INCOME>
- 네이버금융 shows <PORTAL_OPERATING_INCOME>
- Discrepancy = <DIFFERENCE_PCT>%
- **Grade A** `[Filing]` — `source_type=filing`, `source_authority=regulatory`. DART is the Korean FSS regulatory filing (equivalent authority to SEC EDGAR). Primary regulatory source + arithmetic consistent = Grade A.

### Example 5a: Company IR release (not a filing)
- <COMPANY_NAME> IR publishes an earnings release before the 10-Q is filed
- The release is authoritative issuer guidance, but not a regulatory filing
- **Tag as** `[Company]` with `source_type=company_release`, `source_authority=issuer`
- Grade can still be B or C depending on corroboration, but it should not be mislabeled `[Filing]`

### Example 6: Arithmetic inconsistency (Grade D)
- Source A: Revenue = <REVENUE>, Net Margin = <NET_MARGIN>, implies Net Income = <IMPLIED_NET_INCOME>
- Source B: Net Income = <REPORTED_NET_INCOME>
- Cannot reconcile: either revenue or margin or net income is wrong
- **Grade D for net income** until resolved; re-search for clarification

### Example 7: API data grading (Grade A)
- Financial Datasets MCP `get_income_statements` returns revenue = <REVENUE_VALUE>
- This is SEC 10-Q filing data delivered via API
- **Grade A** `[Filing]` — Grade A because the underlying authority is SEC, not because the delivery method is API. The API is a reliable pipe to regulatory filing data.

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
- Tag as `[Calc]` with note "N/A — negative earnings"
- Still display as "—" in P/E column but with "N/A" label, not silence

### Pre-revenue Companies (Biotech)
- Revenue may legitimately be zero or near-zero
- Grade A if SEC filing confirms zero revenue
- P/E, EV/EBITDA: N/A — display guidance to use P/S or EV/Pipeline instead

### EBITDA Not Disclosed
- Many companies don't report EBITDA directly
- Self-calculate from Operating Income + D&A
- If D&A not separately disclosed: Grade C (estimated) with note
- Tag: `[Calc]`

### Fiscal Year Mismatch
- When two sources use different fiscal quarters → Grade C with note about timing difference
- Always specify reporting period: "<FISCAL_PERIOD>" not just "Q2"

---

## Output Format in validated-data.json

```json
"validated_metrics": {
  "price": {
    "value": "<CURRENT_PRICE>",
    "grade": "A",
    "sources": ["Financial Datasets MCP (SEC filing data)"],
    "source_type": "filing",
    "source_authority": "regulatory",
    "display_tag": "[Filing]",
    "tag": "[Filing]",
    "note": null
  },
  "pe_ratio": {
    "value": "<PE_RATIO>",
    "grade": "A",
    "sources": ["Self-calculated: <CURRENT_PRICE> / <EPS_TTM>"],
    "source_type": "calculated",
    "source_authority": "derived",
    "display_tag": "[Calc]",
    "tag": "[Calc]",
    "note": "Formula: Price / TTM EPS (diluted)"
  },
  "net_debt_ebitda": {
    "value": null,
    "grade": "D",
    "sources": [],
    "source_type": null,
    "source_authority": null,
    "display_tag": null,
    "tag": null,
    "exclusion_reason": "Net debt figures from <PORTAL_1> and <PORTAL_2> differ by <DIFFERENCE_PCT>%, exceeding 15% threshold. Excluded from analysis."
  }
}
```
