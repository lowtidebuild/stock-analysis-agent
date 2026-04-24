# Data Validator — SKILL.md

**Role**: Step 5 — Validate all collected data through 3-layer fact-checking, assign confidence grades, build the evidence pack, measure Analyst context budget, and enforce the Blank-Over-Wrong principle.
**Triggered by**: CLAUDE.md after Step 4 (web researcher)
**Reads**: `output/runs/{run_id}/{ticker}/tier1-raw.json` (Enhanced), `output/runs/{run_id}/{ticker}/tier2-raw.json`, `references/validation-rules.md`, `references/confidence-grading.md`, `references/source-metadata-contract.md`
**Writes**: `output/runs/{run_id}/{ticker}/validated-data.json`, `output/runs/{run_id}/{ticker}/evidence-pack.json`, `output/runs/{run_id}/{ticker}/context-budget.json`
**References**: `validation-rules.md`, `confidence-grading.md`, `source-metadata-contract.md`

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
Load: output/runs/{run_id}/{ticker}/tier1-raw.json    (API data)
Load: output/runs/{run_id}/{ticker}/tier2-raw.json    (web data)
Primary source: tier1 (API)
Cross-check source: tier2 (web)
```

**Standard Mode (US stocks)**:
```
Load: output/runs/{run_id}/{ticker}/tier2-raw.json    (web data only)
Primary source: tier2 extracted_metric_candidates
Cross-check source: tier2 extracted_metric_candidates from independent source_domain values
```

**Korean stocks**:
```
Load: output/runs/{run_id}/{ticker}/dart-api-raw.json    (DART OpenAPI — Grade A financials, always attempted)
Load: output/runs/{run_id}/{ticker}/tier2-raw.json       (web — price from 네이버금융, consensus, qualitative)
Primary financial source: run-local dart-api-raw.json (if exists)
Primary market data source: tier2 (네이버금융)
Fallback: if dart-api-raw.json missing → tier2-raw.json only (aggregator-only, max Grade B)
```

**Macro data (all markets, Mode C/D)**:
```
Load: output/data/macro/fred-snapshot.json    (FRED macro data, if exists — shared cache)
FRED macro data: [Macro] tag, Grade A (federal government source)
If fred-snapshot.json missing or null: skip FRED validation, proceed with existing data
```

For `tier2-raw.json`, treat `raw_search_results[]` as evidence text only.
Final metrics may be selected from `extracted_metric_candidates[]`, Tier 1
structured data, DART structured data, yfinance structured fallback, or
deterministic calculations. Do not select final values directly from
`raw_search_results[].snippet`, `searches_executed[].results[]`, or legacy
`key_data_extracted`; those fields are trace/context only.

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
- Difference ≤5% between 2+ sources → Grade B
- Difference >5% but ≤10% between sources → Grade C, use lower estimate, flag
- Difference >10% → Grade C, flag discrepancy, note both values in output
- Only 1 source found → Grade C
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
  "tag": "[Filing]",
  "notes": "Two sources agree within 1%"
}
```

When using web data, build the record from `extracted_metric_candidates[]`.
Preserve traceability:

```json
{
  "metric": "market_cap",
  "value": "<NORMALIZED_VALUE>",
  "sources": ["<SOURCE_DOMAIN_1>", "<SOURCE_DOMAIN_2>"],
  "source_values": ["<NORMALIZED_VALUE_1>", "<NORMALIZED_VALUE_2>"],
  "difference_pct": "<DIFFERENCE_PCT>",
  "grade": "B",
  "tag": "[Portal]",
  "candidate_trace": {
    "selected_candidate_id": "<CANDIDATE_ID>",
    "source_query_ids": ["<QUERY_ID_1>", "<QUERY_ID_2>"],
    "selection_reason": "<WHY_THIS_CANDIDATE_WON>"
  },
  "conflicts": [
    {
      "candidate_refs": ["<CANDIDATE_REF_1>", "<CANDIDATE_REF_2>"],
      "resolution": "<LOWER_ESTIMATE_USED_OR_UNRESOLVED>"
    }
  ],
  "notes": "<VALIDATION_NOTE>"
}
```

If candidates disagree beyond the cross-reference threshold, copy the conflict
to top-level `metric_conflicts[]` in `validated-data.json` as well as the
metric-level `conflicts[]` field. Grade D metrics still use `value: null` and
must not flow into analysis.

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

### Step 5.4a — FRED Data Sanity Checks

**Condition**: Only run if `macro_context.structured` exists in tier2-raw.json.

Before numeric checks, inspect `macro_context.structured.status`:
- `available`: validate numeric FRED values and preserve `grade` per series.
- `unavailable`: preserve `source="FRED"`, `status="unavailable"`, `grade="D"`, `reason`, and `series=[]`; do not create fallback macro numbers from narrative text.
- Missing status: treat as contract failure and add a validation warning requiring `available` or `unavailable`.

| Check | Rule | On Failure |
|-------|------|------------|
| Yield curve | Flag if DGS10 < DGS2 (inverted) | Set `yield_curve_inverted: true` (informational, not an error) |
| Fed Funds vs 10Y | Warn if abs(DFF - DGS10) > 300bp | Downgrade FRED data to Grade B |
| CPI range | Must be -2% to 15% | Grade D → set to null |
| GDP range | Must be -10% to 15% | Grade D → set to null |
| USD/KRW range | Must be 800 to 2000 | Grade D → set to null |
| WTI range | Must be 10 to 250 dollars per barrel | Grade D → set to null |
| UMCSENT range | Must be 20 to 120 | Grade D → set to null |

**Cache freshness grading**:

| Cache Age | Grade |
|-----------|-------|
| < 24 hours | A |
| 24h – 7 days | B |
| > 7 days | C (add `[stale]` tag) |

Pass through validated `macro_context.structured` values to `validated-data.json`. If status is `unavailable`, the pass-through object must remain non-numeric except for metadata; downstream analysis may mention that structured macro data was unavailable, but must not cite current FRED values.

### Step 5.5 — Apply Confidence Grades

Using `confidence-grading.md` decision tree, assign final grade per metric:

| Grade | Display | Condition |
|-------|---------|-----------|
| A | Value as-is | 규제기관 공시 원본(SEC filing via API, DART via API/web) + 산술 일관성 |
| B | Value as-is | 2+ 독립 소스 ≤5% 차이, 또는 단일 aggregator + 공시 교차확인 ≤5% |
| C | Value with caveat | 단일 소스, 산술 일관성 있음 |
| D | "—" | 검증 불가, 또는 >10% 불일치 미해결 |

Source tags (`[Filing]`, `[Company]`, `[Portal]`, `[KR-Portal]`, `[Calc]`, `[Est]`, `[Macro]`) indicate provenance only — see CLAUDE.md Section 11.

**Korean stock rules**:
- Financial statements (IS/BS/CF) from DART API → **Grade A**, tag `[Filing]`
- Price / market cap from 네이버금융 → Grade B, tag `[KR-Portal]`
- Analyst consensus from FnGuide/web → Grade B, tag `[KR-Portal]`
- 잠정실적 공시 in dart-api-raw.json disclosures → Grade B (preliminary, not yet filed)
- If dart-api-raw.json missing (API failure fallback):
  - DART web + 네이버금융 agree within 5% → Grade B
  - Single web source → Grade C

### Step 5.6 — Build Validated Data Object

Write `output/runs/{run_id}/{ticker}/validated-data.json`:

```json
{
  "ticker": "<TICKER>",
  "market": "US",
  "data_mode": "enhanced",
  "requested_mode": "enhanced",
  "effective_mode": "enhanced",
  "source_profile": "financial_datasets",
  "source_tier": "api_structured",
  "confidence_cap": "A",
  "validation_timestamp": "<VALIDATION_TIMESTAMP>",
  "overall_grade": "B",
  "validated_metrics": {
    "price_at_analysis": {
      "value": "<CURRENT_PRICE>",
      "grade": "A",
      "source_type": "filing",
      "source_authority": "regulatory",
      "display_tag": "[Filing]",
      "tag": "[Filing]",
      "sources": ["Financial Datasets MCP (SEC filing data)"],
      "notes": ""
    },
    "market_cap": {
      "value": "<MARKET_CAP>",
      "grade": "B",
      "source_type": "calculated",
      "source_authority": "derived",
      "display_tag": "[Calc]",
      "tag": "[Calc]",
      "sources": ["Calculated from Filing price + shares", "Yahoo Finance"],
      "source_values": ["<SOURCE_VALUE_1>", "<SOURCE_VALUE_2>"],
      "difference_pct": "<DIFFERENCE_PCT>",
      "notes": "Two sources agree within <DIFFERENCE_PCT>%"
    },
    "pe_ratio": {
      "value": "<PE_RATIO>",
      "grade": "A",
      "source_type": "calculated",
      "source_authority": "derived",
      "display_tag": "[Calc]",
      "tag": "[Calc]",
      "sources": ["Calculated from Filing price + net_income_ttm"],
      "notes": "Arithmetic consistent with <PORTAL_NAME> reported value"
    },
    "revenue_ttm": {
      "value": "<REVENUE_TTM>",
      "grade": "A",
      "source_type": "filing",
      "source_authority": "regulatory",
      "display_tag": "[Filing]",
      "tag": "[Filing]",
      "sources": ["Financial Datasets MCP income_statements (SEC filing data)"],
      "notes": "8 quarters of data available"
    },
    "ev_ebitda": {
      "value": null,
      "grade": "D",
      "source_type": null,
      "source_authority": null,
      "display_tag": null,
      "tag": null,
      "sources": [],
      "exclusion_reason": "EBITDA TTM could not be verified from available sources"
    }
  },
  "grade_summary": {
    "A": "<GRADE_A_COUNT>",
    "B": "<GRADE_B_COUNT>",
    "C": "<GRADE_C_COUNT>",
    "D": "<GRADE_D_COUNT>"
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

For yfinance-only fallback after an Enhanced request, do not present the run as
full enhanced source quality. Use:

```json
{
  "data_mode": "enhanced",
  "requested_mode": "enhanced",
  "effective_mode": "standard",
  "source_profile": "yfinance_fallback",
  "source_tier": "portal_structured",
  "confidence_cap": "C"
}
```

### Step 5.7 — Build Evidence Pack

After `validated-data.json` is written, create the run-local evidence pack:

```bash
python tools/evidence_pack.py \
  --validated-data output/runs/{run_id}/{ticker}/validated-data.json \
  --output output/runs/{run_id}/{ticker}/evidence-pack.json
```

Contract:
- Include only Grade A/B/C facts selected from `validated_metrics`
- Put Grade D metrics only in `exclusions`
- Keep raw files as `raw_artifact_refs`; do not embed snippets, article bodies, filings text, or raw search result payloads
- Set `raw_access_policy.default_load = "deny"` and require a logged reason before any Analyst raw artifact access

Validate it:

```bash
python .claude/skills/data-validator/scripts/validate-artifacts.py \
  --artifact-type evidence-pack \
  --input output/runs/{run_id}/{ticker}/evidence-pack.json
```

### Step 5.8 — Measure Analyst Context Budget

After `evidence-pack.json` is validated, measure the default Analyst handoff:

```bash
python tools/context_budget.py \
  --run-dir output/runs/{run_id} \
  --ticker {ticker} \
  --output output/runs/{run_id}/{ticker}/context-budget.json
```

Validate it:

```bash
python .claude/skills/data-validator/scripts/validate-artifacts.py \
  --artifact-type context-budget \
  --input output/runs/{run_id}/{ticker}/context-budget.json
```

Contract:
- The included context is `validated-data.json`, `evidence-pack.json`, `research-plan.json`, and the selected framework file
- Raw artifacts are listed only under `excluded_raw_artifacts`
- `routing_policy.no_llm` covers deterministic checks and renderer execution
- If `totals.within_soft_limit = false`, rebuild a smaller evidence pack or split Analyst work before dispatch

### Step 5.9 — Report Validation Summary

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
- [ ] Korean stocks: dart-api-raw.json loaded (Grade A IS/BS/CF); fallback to Grade B if missing
- [ ] Grade D metrics → value = null, exclusion_reason filled
- [ ] run-local `validated-data.json` written
- [ ] run-local `evidence-pack.json` written and validated
- [ ] run-local `context-budget.json` written and validated
- [ ] Validation summary printed
