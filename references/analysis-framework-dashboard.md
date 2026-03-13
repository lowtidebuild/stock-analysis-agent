# Analysis Framework — Mode C (Deep Dive Dashboard)

This file defines the analytical requirements for Mode C output. The Analyst agent reads this file when `output_mode = "C"`.

---

## Purpose & Scope

Mode C produces a full interactive HTML dashboard — the most visually rich output mode. It combines financial data tables, Chart.js visualizations, scenario analysis, peer comparison, analyst coverage, and portfolio strategy in a single self-contained HTML file.

**Output target**: HTML file with all 11 sections populated
**Output format**: HTML (TailwindCSS + Chart.js + FontAwesome via CDN)
**Output path**: `output/reports/{ticker}_C_{lang}_{YYYY-MM-DD}.html`
**Template**: `.claude/skills/dashboard-generator/SKILL.md` (for execution), `html-template.md` (for structure)

---

## Required Inputs

- `output/validated-data.json` — validated metrics with confidence grades
- `output/data/{ticker}/tier1-raw.json` — 8 quarters of financial data (Enhanced Mode)
- `output/data/{ticker}/tier2-raw.json` — web research results
- `output/analysis-result.json` — will be written as output of this step
- Company type from `company-type-classification.md`

---

## Section-by-Section Content Requirements

### Section 1 — Header

Required fields:
- Company name + ticker
- Exchange (NYSE/NASDAQ/AMEX for US; KOSPI/KOSDAQ for KR)
- Current price with day change and % change
- Market cap
- Data mode badge (Enhanced or Standard)
- Data Confidence Indicator: overall grade summary (e.g., "Data Confidence: B — 7 of 10 key metrics cross-referenced")
- Analysis date

Data Confidence Indicator calculation:
- Count metrics by grade: A count, B count, C count, D count
- Overall: A (all critical metrics Grade A), B (majority Grade B or above), C (majority Grade C or some Grade D), D (critical metrics unverified)

### Section 2 — Scenarios + R/R Score

For each scenario (Bull, Base, Bear):
- Price target
- Implied return %
- Probability %
- Key assumption (company-specific — must pass competitor replacement test)
- 2–3 sentence narrative explaining the scenario path

R/R Score badge:
- Score value with interpretation (Attractive/Neutral/Unfavorable)
- Color from `color-system.md`:
  - Attractive (>3.0): green badge
  - Neutral (1.0–3.0): yellow badge
  - Unfavorable (<1.0): red badge

### Section 3 — KPI Tiles

Select 8–10 KPI tiles based on company type. Each tile shows:
- Metric name
- Value with unit
- YoY change (▲ positive = green, ▼ negative = red, unless metric is cost/debt)
- Confidence badge (A/B/C)
- Source tag

| Company Type | Primary KPI Set |
|-------------|-----------------|
| Technology/Platform | Revenue TTM, Gross Margin, Operating Margin, FCF TTM, P/E, EV/EBITDA, Revenue Growth YoY, FCF Yield |
| Industrial/Manufacturing | Revenue TTM, Operating Margin, FCF TTM, EBITDA TTM, EV/EBITDA, Net Debt/EBITDA, Backlog (if available), Order Growth |
| Financial/Banking | Total Assets, Net Interest Margin, ROE, Tier 1 Capital Ratio, Non-Performing Loan Ratio, P/B, Dividend Yield |
| Biotech/Pharma | Cash Runway, R&D Spend, EV/Revenue, Pipeline Stage Count, Upcoming Readout Dates |
| Consumer/Retail | Revenue TTM, Same-Store Sales Growth, Gross Margin, Operating Margin, Dividend Yield, EV/EBITDA |

Below KPI tiles, show core ratio row:
| Market Cap | Enterprise Value | EV/EBITDA | P/E | P/B | FCF Yield | Dividend Yield |
(All with source tags)

### Section 4 — Variant View + Precision Risk

**Variant View** (Q1, Q2, Q3):

Q1 — Market vs. Analyst View (150–250 words)
- Paragraph 1: What the market currently prices in (specific implied multiple, growth rate, or assumption)
- Paragraph 2: The specific disagreement with evidence
- Paragraph 3: Why the market is mispricing this (information asymmetry, behavioral bias, temporary dislocation)
- Must pass: competitor replacement test

Q2 — Catalyst Map (100–150 words)
- 3–5 specific catalysts with timelines
- Each catalyst: "If X happens by Y, it would trigger Z re-rating because..."
- Include probability assessment (High/Medium/Low) for each

Q3 — Optionality Not in Consensus (100–150 words)
- 1–2 specific options not in analyst consensus
- Each with rough size estimate: "If {option} achieves $X revenue by {date} at {Y}x multiple, it adds ~${Z} to fair value"
- Be explicit about why consensus excludes this

**Precision Risk Table**:

For each risk (3 risks minimum):
| Risk | Mechanism | EBITDA Impact | Probability | Mitigation |
|------|-----------|---------------|-------------|------------|

- Mechanism column: full causal chain from risk event → financial impact → stock price effect
- EBITDA Impact: quantified in $ and % of EBITDA TTM
- Probability: High (>40%), Medium (15–40%), Low (<15%)
- Mitigation: specific monitoring indicator or hedge

### Section 5 — Valuation + SOTP

**Valuation Metrics Table**:
| Metric | Current | Sector Avg | Historical Avg | Assessment |
(Sector avg and historical avg from web research; tag with [Portal] if not filing-sourced)

**SOTP Analysis** (if ≥2 distinct segments):
| Segment | Revenue TTM | Multiple | Implied EV | Notes |
- Show calculation: Sum of EV → Less Net Debt → Equity Value → Per Share → vs. Current Price
- If single-segment or data insufficient: "SOTP not applicable — single business model"

**Implied Growth Rate Analysis**:
If P/E available: calculate what EPS growth the current P/E implies (reverse Gordon Growth Model or simple P/E growth formula)
Note if implied growth is achievable, too high, or too low based on historical rates

### Section 6 — Peer Comparison

Identify 3–5 most relevant peers (from tier2-raw.json or research-plan.json peer_tickers).

For each peer:
- Current price, market cap
- P/E, EV/EBITDA, Revenue Growth YoY, Operating Margin, FCF Yield
- R/R Score if analyzed in current session

Relative positioning:
- Color-code the subject company row to distinguish from peers
- Identify metrics where subject company is best-in-class (green) or worst (red)

### Section 7 — Analyst Coverage

Data from FMP MCP (if available) or web research:

**Rating Distribution Bar** (horizontal stacked bar):
- Strong Buy | Buy | Hold | Sell | Strong Sell
- Show count and % for each

**Consensus Price Target**:
- Average target, High target, Low target, Current price, Implied upside/downside

**Individual Analyst Actions** (if FMP available, last 6 months):
| Analyst/Firm | Date | Action | Rating | Previous Target | New Target |

If FMP not available: tag section with `[Portal]` and note data source

**Analyst Consensus vs. Our View**:
- Where does our base case target diverge from analyst consensus?
- Why? (briefly, 2–3 sentences)

### Section 8 — Charts

Three Chart.js charts:

**Chart 1 — 12-Month Price History**:
- Line chart, daily or weekly closes
- Add 52-week high/low horizontal reference lines
- Annotate major events (earnings dates, significant news) with vertical markers

**Chart 2 — Quarterly Revenue + Operating Income Bar Chart**:
- Dual-axis bar chart: Revenue (left axis), Operating Income (right axis)
- Last 8 quarters
- Label each bar with value
- Color: Revenue = blue, Operating Income = emerald if positive / red if negative

**Chart 3 — Margin Trend Lines**:
- Multi-line chart: Gross Margin, Operating Margin, Net Margin
- Last 8 quarters
- Color per `color-system.md`: Gross=blue, Operating=emerald, Net=orange

Data for charts comes from `tier1-raw.json` (Enhanced Mode) or web research (Standard Mode).

If historical price data not available (Standard Mode without price API): substitute a text table for Chart 1.

### Section 9 — Quarterly Financials + QoE

**Quarterly P&L Table** (last 8 quarters):
| Quarter | Revenue | Gross Profit | Op. Income | Net Income | EPS | Gross Margin | Op. Margin |
(All with source tags in header)

**QoE Summary**:
- FCF Conversion: Operating CF / Net Income (TTM)
- SBC as % of Revenue (TTM)
- EBITDA to Cash Earnings Bridge (see mode-d-template.md Section 9 for format)
- Earnings Quality Assessment: High/Medium/Low with 1-sentence rationale

**Capital Structure** (if data available):
- Cash, Total Debt, Net Debt, Shares Outstanding
- Net Debt/EBITDA trend (last 4 quarters if available)

### Section 10 — Portfolio Strategy + "What Would Make Me Wrong"

**Portfolio Strategy Section**:
- Suggested position sizing: Overweight (>4% allocation) / Neutral Weight (2–4%) / Underweight (<2%) / Avoid
- Rationale tied to R/R Score and data confidence
- Suggested entry conditions (if not immediate buy): "Consider adding if price reaches ${X} or after {catalyst event}"
- Suggested exit trigger: specific price or event

**"What Would Make Me Wrong"** (2–3 bullet points):
- Each: Core assumption → If wrong → Monitoring indicator
- Most important assumption first
- Pre-mortem: "If this position loses 30% over 12 months, the most likely cause would be..."

**Upcoming Catalysts** (from snapshot or web research):
| Date | Event | Significance | Expected Impact |
(Ordered by date, next 90 days)

### Section 11 — Disclaimer + Data Sources

Standard disclaimer (see mode-d-template.md for full text)
Data sources table (abbreviated): Source | Type | Confidence | Tag
Generation timestamp + data freshness date

---

## Company-Type Variations

### Financial/Banking Companies
- Replace SOTP with Book Value Decomposition: Tangible Book Value + Franchise Value + Capital Distribution Value
- Key metrics: CET1 ratio, NIM, NPL ratio, ROTE
- Section 4 Precision Risk must include credit cycle risk with specific loan book exposure

### Biotech/Pharma (Pre-Revenue)
- Replace standard valuation with EV/Revenue or NPV-based approach
- Section 3 KPIs: Cash runway (months), burn rate, pipeline stage summary
- Section 4 Precision Risk: clinical trial failure risk with % impact on NPV
- Section 5: No SOTP; replace with Pipeline Value Table

### Korean Stocks
- All KRW pricing with comma formatting
- Section 8 Chart 1: Include KRX composite index overlay if available
- Section 9: Add DART filing reference link
- Section 10: Include 밸류업 program status, 외국인 지분율 trend
- Section 7: Note if analyst coverage is limited (Korean market typically fewer analysts covering mid/small cap)

---

## Data Confidence Indicator Logic

Displayed in Section 1 header:

```
Grade A: ≥8 of 10 key metrics have Grade A confidence
Grade B: ≥6 of 10 key metrics have Grade A or B confidence
Grade C: ≥4 of 10 key metrics have Grade A, B, or C confidence
Grade D: <4 key metrics verifiable (very sparse data) — show warning banner
```

When overall Grade D: add prominent warning banner below header:
```html
<div class="bg-red-950 border border-red-800 rounded-lg p-3 mb-4 text-red-300 text-sm">
  ⚠️ Data Quality Warning: Fewer than 4 key metrics could be independently verified.
  Analysis conclusions should be treated with significant caution.
</div>
```

---

## Completion Check

Before calling `dashboard-generator/SKILL.md` to generate HTML:
- [ ] All 11 section content objects prepared in `analysis-result.json`
- [ ] All chart data arrays populated (or text fallback noted)
- [ ] Scenario probabilities sum to 100%
- [ ] R/R Score computed with formula
- [ ] Variant View Q1–Q3 each pass competitor replacement test
- [ ] Precision Risk table: 3 risks, each with mechanism + quantified EBITDA impact
- [ ] SOTP computed (or documented as not applicable)
- [ ] Peer comparison includes ≥3 peers
- [ ] "What Would Make Me Wrong" includes pre-mortem
- [ ] All metrics have source tags
- [ ] Grade D metrics excluded from analysis body (noted in data sources table)
- [ ] Data Confidence Indicator grade computed
- [ ] Disclaimer present
