# Dashboard Generator — SKILL.md

**Role**: Step 8 — Generate the Mode C HTML dashboard from `analysis-result.json`.
**Triggered by**: CLAUDE.md when `output_mode = "C"` after Step 7 (Analyst Agent completes analysis)
**Reads**: `output/analysis-result.json`, `references/html-template.md`, `references/color-system.md`
**Writes**: `output/reports/{ticker}_C_{lang}_{YYYY-MM-DD}.html`
**References**: `html-template.md`, `color-system.md`

---

## Instructions

### Step 8.1 — Load Inputs

Load in this order:
1. Read `references/html-template.md` — complete HTML skeleton with all 11 sections
2. Read `references/color-system.md` — Tailwind CSS classes and Chart.js color configs
3. Read `output/analysis-result.json` — analysis output from Analyst Agent
4. Verify all required sections are present in `analysis-result.json`

### Step 8.2 — Compute Data Confidence Indicator

From `output/analysis-result.json`, count the `data_quality_used` grade distribution:

```
Grade A count: {N}
Grade B count: {N}
Grade C count: {N}
Grade D count: {N}

Overall:
- All critical metrics (price, revenue, net_income) Grade A → Overall A
- ≥6 of 10 key metrics Grade A or B → Overall B
- ≥4 of 10 key metrics Grade A, B, or C → Overall C
- Otherwise → Overall D (add warning banner)
```

Translate to Data Confidence Indicator text:
- Grade A: `Data Confidence: A — All key metrics independently verified`
- Grade B: `Data Confidence: B — {N} of 10 key metrics cross-referenced`
- Grade C: `Data Confidence: C — Limited source verification. Review with caution.`
- Grade D: `Data Confidence: D — ⚠️ Insufficient verified data`

### Step 8.3 — Section-by-Section Population

Populate each section of `html-template.md` with data from `analysis-result.json`.

**JSON field → HTML placeholder mapping**:

| analysis-result.json field | HTML Section | Placeholder |
|---------------------------|-------------|-------------|
| `ticker` | Section 1 | `{TICKER}` |
| `company_name` | Section 1 | `{COMPANY_NAME}` |
| `exchange` | Section 1 | `{EXCHANGE}` |
| `price_at_analysis` | Section 1, 3 | `{CURRENT_PRICE}` |
| `price_day_change` | Section 1 | `{DAY_CHANGE}` |
| `price_day_change_pct` | Section 1 | `{DAY_CHANGE_PCT}` |
| `data_mode` | Section 1 | badge class |
| `analysis_date` | Section 1 | `{ANALYSIS_DATE}` |
| `key_metrics.market_cap` | Section 3 | `{MARKET_CAP}` |
| `key_metrics.pe_ratio` | Section 3 | `{PE_RATIO}` |
| `key_metrics.ev_ebitda` | Section 3 | `{EV_EBITDA}` |
| `key_metrics.fcf_yield` | Section 3 | `{FCF_YIELD}` |
| `key_metrics.revenue_growth_yoy` | Section 3 | `{REV_GROWTH}` |
| `key_metrics.operating_margin` | Section 3 | `{OP_MARGIN}` |
| `scenarios.bull.*` | Section 2 | bull card values |
| `scenarios.base.*` | Section 2 | base card values |
| `scenarios.bear.*` | Section 2 | bear card values |
| `rr_score` | Section 2 | R/R badge |
| `verdict` | Section 2 | verdict badge |
| `sections.variant_view_q1` | Section 4 | Q1 text |
| `sections.variant_view_q2` | Section 4 | Q2 text |
| `sections.variant_view_q3` | Section 4 | Q3 text |
| `sections.precision_risks` | Section 4 | risk table rows |
| `sections.valuation_metrics` | Section 5 | valuation table |
| `sections.sotp` | Section 5 | SOTP section |
| `sections.peer_comparison` | Section 6 | peer table rows |
| `sections.analyst_coverage` | Section 7 | analyst data |
| `historical_prices` | Section 8 | Chart 1 data array |
| `income_statements` | Section 8, 9 | Charts 2/3, quarterly table |
| `sections.qoe_summary` | Section 9 | QoE section |
| `sections.portfolio_strategy` | Section 10 | strategy text |
| `sections.what_would_make_me_wrong` | Section 10 | WWMMW list |
| `upcoming_catalysts` | Section 10 | catalyst table |

### Step 8.4 — Chart.js Data Arrays

Convert structured data to Chart.js format:

**Chart 1 — 12-Month Price History**:
```javascript
// From historical_prices array: [{date: "2025-03-12", close: 165.20}, ...]
const priceLabels = historical_prices.map(d => d.date);
const priceData = historical_prices.map(d => d.close);
// Apply color-system.md priceChart config
```

**Chart 2 — Quarterly Revenue + Operating Income**:
```javascript
// From income_statements (last 8 quarters, oldest first)
const quarters = income_statements.slice(-8).map(q => q.period_label || q.period);
const revenueData = income_statements.slice(-8).map(q => q.revenue / 1000000); // in billions
const opIncomeData = income_statements.slice(-8).map(q => q.operating_income / 1000000);
// Apply color-system.md revenueBar and operatingIncomeBar configs
```

**Chart 3 — Margin Trends**:
```javascript
// From income_statements (last 8 quarters)
const grossMarginData = income_statements.slice(-8).map(q =>
  q.gross_profit && q.revenue ? (q.gross_profit / q.revenue * 100).toFixed(1) : null
);
const opMarginData = income_statements.slice(-8).map(q =>
  q.operating_income && q.revenue ? (q.operating_income / q.revenue * 100).toFixed(1) : null
);
const netMarginData = income_statements.slice(-8).map(q =>
  q.net_income && q.revenue ? (q.net_income / q.revenue * 100).toFixed(1) : null
);
// Apply color-system.md grossMarginLine, operatingMarginLine, netMarginLine configs
```

**If historical_prices unavailable** (Standard Mode without price API):
Replace Chart 1 canvas with a text table:
```html
<div class="text-gray-400 text-sm italic p-4">
  Price chart data not available in Standard Mode. Use Enhanced Mode for historical price chart.
</div>
```

### Step 8.5 — Apply Color System

From `color-system.md`:

**R/R Score badge**:
```
rr_score > 3.0 → class: "bg-emerald-900 text-emerald-300 border border-emerald-700"
rr_score 1.0–3.0 → class: "bg-yellow-900 text-yellow-300 border border-yellow-700"
rr_score < 1.0 → class: "bg-red-900 text-red-300 border border-red-700"
```

**Price change colors**:
```
day_change_pct > 0 → text-emerald-400, ▲
day_change_pct < 0 → text-red-400, ▼
day_change_pct = 0 → text-gray-400, —
```

**Verdict badges**:
```
Overweight / 비중확대 → bg-emerald-900 text-emerald-300
Underweight / 비중축소 → bg-red-900 text-red-300
Neutral / 중립 → bg-gray-700 text-gray-300
Watch / 관찰 → bg-blue-900 text-blue-300
```

**Data confidence badge colors**:
```
Grade A → bg-emerald-900 text-emerald-300
Grade B → bg-blue-900 text-blue-300
Grade C → bg-amber-900 text-amber-300
Grade D → bg-red-900 text-red-300
```

### Step 8.6 — Missing Data Handling

For any section where data is null or Grade D:

```html
<!-- Instead of leaving empty or omitting: -->
<div class="text-gray-500 text-sm italic">[Data unavailable]</div>
```

Do NOT remove the section from the HTML. Do NOT substitute fabricated data. Always show the placeholder.

Sections with all-null data: collapse the section with a note:
```html
<div class="bg-gray-800/50 border border-gray-700 rounded-lg p-4 text-gray-500 text-sm">
  Section data not available for this analysis. Data confidence insufficient.
</div>
```

### Step 8.7 — Write HTML File

1. Replace all placeholders with actual values
2. Ensure Chart.js initialization code is complete with actual data arrays
3. Verify HTML is well-formed (all tags closed)
4. Write to: `output/reports/{ticker}_C_{lang}_{YYYY-MM-DD}.html`
5. Report path to user

Language suffixes: `EN` or `KR`
Example: `output/reports/AAPL_C_EN_2026-03-12.html`

---

## Multi-Ticker Mode B HTML Generation

When called for Mode B (comparison), use `mode-b-template.md` instead of `html-template.md`.

Path: `output/reports/{T1}_{T2}_{T3}_B_{lang}_{YYYY-MM-DD}.html`

Load each ticker's validated-data from `output/data/{ticker}/validated-data.json`.

---

## Completion Check

- [ ] `html-template.md` loaded
- [ ] `color-system.md` loaded
- [ ] `analysis-result.json` loaded and all required fields present
- [ ] Data Confidence Indicator computed
- [ ] All 11 sections populated (or placeholder for missing)
- [ ] Chart.js data arrays correctly formatted (labels array, datasets array)
- [ ] R/R Score badge uses correct color class
- [ ] Verdict badge uses correct color class
- [ ] Missing data uses `[Data unavailable]` placeholder (NOT removed)
- [ ] HTML written to correct path
- [ ] File path reported to user
