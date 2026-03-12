# Data Validator — SKILL.md

**Role**: Step 5 — Validate all collected data through 3-layer fact-checking, assign confidence grades, and enforce the Blank-Over-Wrong principle.
**Triggered by**: CLAUDE.md after Step 4 (web researcher)
**Reads**: `output/data/{ticker}/tier1-raw.json` (Enhanced), `output/data/{ticker}/tier2-raw.json`, `references/validation-rules.md`, `references/confidence-grading.md`
**Writes**: `output/validated-data.json`
**References**: `validation-rules.md`, `confidence-grading.md`

---

## THE BLANK-OVER-WRONG PRINCIPLE

**빈칸 > 틀린 숫자** (An empty cell is better than a wrong number)

If a data point cannot be verified to Grade C or above, it is:
1. Set to `null` in validated output
2. Listed in `exclusions` with reason
3. Displayed as "—" in all output modes
4. NEVER filled with an estimate, approximation, or best guess

This principle is ABSOLUTE. No exceptions. Grade D = excluded.

---

## Instructions

### Step 5.1 — Load Data Sources

**Enhanced Mode**:
```
Load: output/data/{ticker}/tier1-raw.json    (API data)
Load: output/data/{ticker}/tier2-raw.json    (web data)
Primary source: tier1 (API)
Cross-check source: tier2 (web)
```

**Standard Mode**:
```
Load: output/data/{ticker}/tier2-raw.json    (web data only)
Primary source: tier2 (first source found)
Cross-check source: tier2 (second source found)
```

### Step 5.2 — Layer 1: Arithmetic Consistency (ratio-calculator.py)

Extract raw inputs from data sources, then run:

```bash
python .claude/skills/data-validator/scripts/ratio-calculator.py --inline '{
  "price": {price},
  "diluted_shares": {diluted_shares},
  "net_income_ttm": {net_income_ttm},
  "ebitda_ttm": {ebitda_ttm},
  "total_debt": {total_debt},
  "cash": {cash},
  "operating_cf": {operating_cf_ttm},
  "capex": {capex_ttm},
  "revenue_ttm": {revenue_ttm},
  "operating_income_ttm": {operating_income_ttm},
  "gross_profit_ttm": {gross_profit_ttm}
}'
```

**Manual fallback** (if Python unavailable):
```
Market Cap = Price × Diluted Shares
Net Debt = Total Debt - Cash
Enterprise Value = Market Cap + Net Debt
EPS = Net Income TTM / Diluted Shares
P/E = Price / EPS
EV/EBITDA = Enterprise Value / EBITDA TTM
FCF = Operating CF - CapEx
FCF Yield = FCF / Market Cap × 100
Gross Margin = Gross Profit / Revenue × 100
Operating Margin = Operating Income / Revenue × 100
Net Margin = Net Income / Revenue × 100
Net Debt/EBITDA = Net Debt / EBITDA
```

**Arithmetic consistency check**: Compare calculated ratios against source-reported ratios.
- Tolerance: ≤10% difference → consistent
- >10% difference → flag as ARITHMETIC_INCONSISTENCY for that metric

```
IF Market Cap (calculated) vs Market Cap (reported) difference > 10%:
    → Flag: ARITHMETIC_INCONSISTENCY: market_cap
    → Use calculated value (from raw inputs) as primary
    → Downgrade reported source to Grade C
```

### Step 5.3 — Layer 2: Multi-Source Cross-Reference

For each of the 10 key metrics from `validation-rules.md`:

| Metric | Cross-Reference Rule |
|--------|---------------------|
| Current Price | API price vs Yahoo Finance (Enhanced) or 2 web sources (Standard) |
| Diluted Shares | API vs SEC 10-Q |
| Market Cap | Calculated vs 2 portals |
| Revenue TTM | API vs SEC 10-Q vs portal |
| EPS TTM | Calculated vs API vs portal |
| Net Debt | Calculated (API balance sheet) vs portal |
| EBITDA TTM | API vs portal (often estimated) |
| P/E | Calculated vs portal |
| EV/EBITDA | Calculated vs portal |
| FCF TTM | Calculated vs portal |

**Cross-reference disagreement rules** (from `validation-rules.md`):
- Difference ≤5% between 2+ sources → Grade B, tag `[≈]`
- Difference >5% but ≤10% between sources → Grade C, use lower estimate, flag
- Difference >10% → Grade C, flag discrepancy, note both values in output
- Only 1 source found → Grade C, tag `[1S]`
- 0 sources → Grade D → EXCLUDE

For each metric, record:
```json
{
  "metric": "revenue_ttm",
  "value": 395000,
  "sources": ["SEC EDGAR 10-Q", "Yahoo Finance"],
  "source_values": [395000, 392000],
  "difference_pct": 0.76,
  "grade": "B",
  "tag": "[≈]",
  "notes": "Two sources agree within 1%"
}
```

### Step 5.4 — Layer 3: Sector Sanity Check

From `validation-rules.md` sanity range tables, check each ratio against sector-typical ranges.

**Alert triggers** (not automatic grade downgrade — requires human judgment):
- P/E > 100 for profitable company → "SANITY_ALERT: P/E={val} is unusually high. Verify earnings base."
- P/E < 5 for growth company → "SANITY_ALERT: P/E={val} is unusually low. Verify no one-time items."
- EV/EBITDA < 0 → "SANITY_ALERT: Negative EV/EBITDA — EBITDA may be negative."
- Revenue Growth > 100% YoY for non-startup → "SANITY_ALERT: Revenue growth {val}% — verify no merger."
- Operating Margin > 60% for non-software → "SANITY_ALERT: Very high margin — verify no misclassification."
- Operating Margin < -50% → "SANITY_ALERT: Very negative margin — verify company is not pre-revenue startup."

Sanity alerts → log but do NOT automatically downgrade grade. Include in validated output under `sanity_alerts`.

### Step 5.5 — Apply Confidence Grades

Using `confidence-grading.md` decision tree, assign final grade per metric:

| Grade | Tag | Display | Condition |
|-------|-----|---------|-----------|
| A | (none) | Value as-is | SEC/DART direct + arithmetic consistent |
| B | `[≈]` | Value as-is | 2 sources within 5%, or API + cross-check within 5% |
| C | `[1S]` | Value with tag | 1 source only, arithmetic consistent |
| D | `[Unverified]` | "—" | No sources, or >10% disagreement unresolved |

**Korean stock special rules**:
- Maximum grade B (no Grade A for KR stocks — DART is web-fetched, not API)
- DART-sourced data: Grade B if consistent with 네이버금융
- 잠정실적 (preliminary earnings): Grade C until confirmed by official DART filing

### Step 5.6 — Build Validated Data Object

Write `output/validated-data.json`:

```json
{
  "ticker": "AAPL",
  "market": "US",
  "data_mode": "enhanced",
  "validation_timestamp": "2026-03-12T14:32:00Z",
  "overall_grade": "B",
  "validated_metrics": {
    "price_at_analysis": {
      "value": 175.50,
      "grade": "A",
      "tag": "[API]",
      "sources": ["Financial Datasets MCP"],
      "notes": ""
    },
    "market_cap": {
      "value": 2718000,
      "grade": "B",
      "tag": "[≈]",
      "sources": ["Calculated from API price + shares", "Yahoo Finance"],
      "source_values": [2718000, 2710000],
      "difference_pct": 0.3,
      "notes": "Two sources agree within 0.3%"
    },
    "pe_ratio": {
      "value": 28.0,
      "grade": "B",
      "tag": "[Calculated]",
      "sources": ["Calculated from API price + net_income_ttm"],
      "notes": "Arithmetic consistent with Yahoo Finance reported 27.9x"
    },
    "revenue_ttm": {
      "value": 395000,
      "grade": "A",
      "tag": "[API]",
      "sources": ["Financial Datasets MCP income_statements"],
      "notes": "8 quarters of data available"
    },
    "ev_ebitda": {
      "value": null,
      "grade": "D",
      "tag": "[Unverified]",
      "sources": [],
      "exclusion_reason": "EBITDA TTM could not be verified from available sources"
    }
  },
  "grade_summary": {
    "A": 3,
    "B": 5,
    "C": 1,
    "D": 1
  },
  "exclusions": [
    {
      "metric": "ev_ebitda",
      "reason": "EBITDA TTM unverifiable — excluded per blank-over-wrong principle",
      "display": "—"
    }
  ],
  "arithmetic_inconsistencies": [],
  "sanity_alerts": [],
  "ratio_calculator_output": {...}
}
```

### Step 5.7 — Report Validation Summary

```
=== Data Validation: {TICKER} ===
Mode: {Enhanced/Standard}
Metrics validated: {N total}
Grade A: {N} | Grade B: {N} | Grade C: {N} | Grade D: {N} (excluded)
Overall confidence: {A/B/C/D}
Arithmetic inconsistencies: {N}
Sanity alerts: {list or "none"}
Excluded metrics: {list}

→ Proceeding to Step 6 (Analyst Agent)
```

---

## Fallback — Python Script Unavailable

If `ratio-calculator.py` cannot be executed:
1. Log: "ratio-calculator.py not available — using manual calculation"
2. Perform manual arithmetic (formulas in Step 5.2 above)
3. Document manual calculation in `notes` field for each metric
4. Treat manual calculations as Grade C (cannot verify programmatic accuracy without script)

---

## Completion Check

- [ ] Data loaded from tier1-raw.json (Enhanced) and/or tier2-raw.json
- [ ] ratio-calculator.py executed (or manual fallback used)
- [ ] Arithmetic consistency check: all 10 key metrics compared calculated vs. reported
- [ ] Cross-reference check: each metric validated against ≥2 sources where possible
- [ ] Sanity check: all values compared against sector ranges
- [ ] Confidence grades assigned (A/B/C/D) for all 10 key metrics
- [ ] Korean stocks: max grade B applied
- [ ] Grade D metrics → value = null, exclusion_reason filled
- [ ] `output/validated-data.json` written
- [ ] Validation summary printed
