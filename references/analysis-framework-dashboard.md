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

- run-local `validated-data.json` — validated metrics with confidence grades
- `output/data/{ticker}/tier1-raw.json` — 8 quarters of financial data (Enhanced Mode)
- `output/data/{ticker}/tier2-raw.json` — web research results
- run-local `analysis-result.json` — will be written as output of this step
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

### Moat 스코어카드 (Mode C)

Add a compact 4-axis moat table after Q1/Q2/Q3 and before Precision Risk:

| 해자 종류 | 강도 | 근거 (1 사실) |
|---|---|---|
| 네트워크 효과 | Strong / Moderate / Weak / N/A | 사용자 ↔ 사용자 또는 구매자 ↔ 판매자 플라이휠 강도 |
| 전환 비용 | Strong / Moderate / Weak / N/A | 기술 통합 깊이, 계약 락인, 행동적 습관 |
| 규모의 경제 | Strong / Moderate / Weak / N/A | 단위 비용 우위, 최소 효율 규모 |
| 무형 자산 | Strong / Moderate / Weak / N/A | 브랜드, 독점 데이터, 규제 라이선스, 특허 |

**작성 규칙**:
- 각 행은 정확히 1개의 검증 가능한 사실로 뒷받침되어야 함 (anti-generic 원칙)
- N/A는 "이 회사는 이 해자가 없다"가 아니라 "이 해자 종류가 이 비즈니스 모델에 적용되지 않는다"는 뜻
- 4축 모두 Weak/N/A이면 → variant view에서 "moat-less commodity 비즈니스"로 명시하고 valuation framework를 P/B 또는 EV/Revenue 중심으로 재조정

**Precision Risk Table**:

For each risk (3 risks minimum):
| Risk | Mechanism | EBITDA Impact | Probability | Mitigation |
|------|-----------|---------------|-------------|------------|

- Mechanism column: full causal chain from risk event → financial impact → stock price effect
- EBITDA Impact: quantified in $ and % of EBITDA TTM
- Probability: High (>40%), Medium (15–40%), Low (<15%)
- Mitigation: specific monitoring indicator or hedge

### Macro Context (Mode C only)

**Trigger**: Only when `sections.macro_context` exists in analysis-result.json.

Display:
- **Section heading**: "Macro Environment"
- **Narrative**: 1-2 paragraphs summarizing macro factors relevant to this stock
- **Factor cards**: For each factor in `macro_context.factors`:
  - Factor name (bold)
  - Impact description (1 line)
  - Confidence badge (High/Medium/Low)
- If a macro risk was allocated a Precision Risk slot: note "(See Precision Risk #N for mechanism chain)"

If macro_context is null or absent: omit this subsection entirely.

### 섹터 트레이딩 멀티플 컨텍스트 (peer_set >=3 일 때만)

Add 1-2 sentences after the macro factors block when peer set has at least 3
companies with comparable EV/EBITDA data:

`"{sector} 섹터는 현재 EV/EBITDA 중간값 {Y}배, 5년 평균 {Z}배에 거래 중이다.
{ticker}는 EV/EBITDA {X}배로 섹터 중간값 대비 {(X-Y)/Y*100:+.1f}% 프리미엄/디스카운트.
이 차이는 {one specific factor — 성장률 격차, 마진 격차, 시장 지위 등} 때문으로 보인다."`

**작성 규칙**: 프리미엄/디스카운트의 근거는 1개의 비교 가능한 사실(growth gap,
margin gap, share position)로 한정한다. "qualitative reasons"이라고 쓰면
anti-generic 위반.

### Macro Sensitivity Card (Mode C — if `sections.macro_sensitivity` exists)

Display a card with:
- **Header**: "Macro Sensitivity: {primary_factor}"
- **Current value**: e.g., "10Y Treasury: 4.25% (as of 2026-03-24) [Macro]"
- **3-row scenario table**:

| Scenario | Value | Stock Impact | Mechanism |
|----------|-------|-------------|-----------|
| {change -} | {value} | {impact %} | {mechanism} |
| Base | {current} | 0% | Current level |
| {change +} | {value} | {impact %} | {mechanism} |

- **Secondary factors**: Listed below table as footnotes (factor name, current value, relevance)
- **Disclaimer**: "Single-variable sensitivity. Multiple variables move simultaneously in practice."
- **Data source badge**: "[Macro] Grade A — FRED"

If `macro_sensitivity` is null or absent: omit this card entirely.

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

### DCF Valuation (Mode C only, US stocks v1)

**Trigger**: Only when `sections.dcf_analysis` exists in analysis-result.json (i.e., DCF was successfully computed).

Display:
- **Base Case DCF Fair Value**: ${fair_value} ({upside_pct}% vs current price)
- **Sensitivity Table**: 3×3 HTML table — rows = WACC (low/mid/high), columns = terminal growth rate (low/mid/high). Each cell shows fair value + upside/downside %. Color-code: green (>10% upside), gray (-10% to +10%), red (>10% downside)
- **Bull/Bear DCF**: Single-line per scenario — "Bull DCF: ${X} (+Y%)" / "Bear DCF: ${X} (-Y%)"
- **Methodology note**: One line showing key assumptions (WACC, terminal growth, forecast years)
- **Transparency**: All assumptions displayed. User can see exactly what drives the valuation.

If dcf_analysis is null or absent: omit this subsection entirely. Do NOT show placeholder.

### Reverse DCF / Expectations Investing (Mode C, optional sub-section)

**Trigger**: Only when `sections.dcf_analysis.reverse` exists with `status` set.

**Purpose**: Reverse DCF is a transparency tool, not a verdict. It answers "what FCF growth rate is the market currently implying at this price?" — letting the analyst compare market expectations to the Base case growth assumption explicitly.

Render based on status:

- `success`: Display a 3-column card:
  - "Market is pricing in **{implied_fcf_growth × 100:.1f}%** annual FCF growth (10y)"
  - "Our Base assumes **{analyst_growth_assumption × 100:.1f}%** annual FCF growth"
  - "Gap: **{growth_gap_bp:+d}bp** ({verdict})"
    - verdict text (output_language-aware):
      - `growth_gap_bp > 500` → en: "Market more bullish than our base" / ko: "시장이 우리 base보다 강세"
      - `growth_gap_bp < -500` → en: "Market more bearish than our base" / ko: "시장이 우리 base보다 약세"
      - otherwise → en: "Approximately aligned" / ko: "대체로 정렬됨"
  - Color-code the gap value: red if `growth_gap_bp > 500`, green if `< -500`, gray otherwise.
  - Footer line (italic, gray): "{notes}" — pass through the solver's notes string.

- `exceeds_ceiling`: Single red banner — "⚠ Market is pricing in implausibly high growth (>100% CAGR for {forecast_years} years). Valuation requires non-DCF justification (M&A optionality, narrative re-rating, etc.)."

- `below_floor`: Single green banner — "Market is pricing in growth at or below the perpetuity rate. Either undervalued by DCF logic, or FCF sustainability is questioned by the market."

- `wacc_invalid`, `negative_fcf`, `invalid_input`: Omit this subsection entirely. Do NOT show a placeholder.

This is NOT a verdict. The analyst's verdict comes from R/R Score + scenario probabilities. Reverse DCF makes the *implicit* market assumption *explicit* so the analyst can take a position on it.

### Valuation Bridge (Mode C — required when DCF + comps + analyst targets are all available)

**Trigger**: Render between DCF/Reverse DCF (Section 5) and Peer Comparison (Section 6) whenever `analysis-result.json` carries a top-level `valuation_bridge` object. Mode C analysts MUST produce this object whenever:

- `sections.dcf_analysis.base.fair_value` is computable, AND
- `sections.dcf_analysis.valuation_reconciliation.comp_implied_per_share` is non-null (peer-median multiple computed), AND
- analyst median target price is available in `validated-data.json` (FMP, yfinance, or portal source).

If any one of those three inputs is missing, omit the field entirely — do NOT render an empty bridge or substitute a Grade D number.

**Purpose**: The bridge resolves the cognitive conflict that occurs when DCF disagrees sharply with peer multiples and analyst consensus (e.g., GOOGL DCF -38% vs Base +7.6%). Instead of asking the reader to silently reconcile four different numbers, the bridge surfaces all four anchors, weights them explicitly, and pairs the result with a 50+ word `reconciliation_logic` paragraph that explains the gap to current price and ties the weighted output back to the verdict.

**Schema** (canonical, write to `analysis-result.json` at top level — NOT nested under `sections`):

```json
"valuation_bridge": {
  "anchors": [
    {"label": "DCF (Base)", "value_per_share": 241.20, "weight": 0.25, "method": "10Y FCF + terminal", "tag": "[Calc]"},
    {"label": "Comp Multiples", "value_per_share": 299.67, "weight": 0.25, "method": "Peer median EV/EBITDA × TTM", "tag": "[Calc]"},
    {"label": "Analyst Median Target", "value_per_share": 428.50, "weight": 0.25, "method": "52 analysts consensus", "tag": "[Est]"},
    {"label": "우리 Base Scenario", "value_per_share": 418.00, "weight": 0.25, "method": "Probability-weighted 12M target", "tag": "[Calc]"}
  ],
  "current_price": 388.43,
  "weighted_fair_value": 346.84,
  "implied_view_vs_market": "-10.7%",
  "reconciliation_logic": "[Korean paragraph, ≥50 words, explaining why DCF is conservative, why comps/analyst are bullish, what the weighted average tells us about the gap to current price, and how it ties to the verdict.]",
  "decision_anchor": "scenarios.base"
}
```

**Required fields per anchor**: `label`, `value_per_share` (numeric, USD or KRW per share), `weight` (decimal, 0–1), `method` (≤80 chars), `tag` (one of `[Calc]`, `[Filing]`, `[Est]`, `[Portal]`, `[Macro]`).

**Default weights**: 0.25 each (equal-weight). Adjust ONLY when one anchor is materially more or less reliable in the current company's context, and explain the deviation in `reconciliation_logic`. Weights MUST sum to 1.0.

**Arithmetic invariants** (Critic checks; analyst self-checks before writing):

1. `sum(anchor.weight) == 1.0` (within ±0.001)
2. `weighted_fair_value ≈ sum(anchor.value_per_share × anchor.weight)` within ±0.1
3. `implied_view_vs_market` matches `(weighted_fair_value − current_price) / current_price × 100`, formatted as a signed percentage string with one decimal (e.g., `"-10.7%"`, `"+5.2%"`)
4. `reconciliation_logic` ≥ 50 words/tokens (whitespace-split; Korean tokens count)
5. `decision_anchor` ∈ {`scenarios.base`, `scenarios.bull`, `scenarios.bear`, `weighted_fair_value`}

**Render contract**: 4 anchor cards side-by-side (md+) with method + weight + tag, downward arrow, weighted fair value box (3 columns: Weighted FV / Current Price / Implied View, color-coded — red for negative, green for positive, gray for ~0), then a reconciliation paragraph card. See `dashboard-generator/references/html-template.md` Section 5b comment block for the markup pattern.

**Critic note**: This bridge is the dashboard's primary defense against the "DCF says one thing, analyst targets say another" criticism. The `reconciliation_logic` paragraph MUST address why the disagreement exists in mechanism terms (capex assumptions, terminal multiple, narrative re-rating, etc.), not merely restate the numbers.

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

### Catalyst Timeline (Mode C — Phase E)

**Trigger**: Render whenever `analysis-result.json.upcoming_catalysts` is a
non-empty list. Replaces (or augments — see backward-compat below) the plain
"Upcoming Catalysts" table with a Gantt-style 12-month timeline grouped by
category. The timeline lives inside the existing **Section 10 — Portfolio
Strategy & Execution** block, immediately after the "What Would Make Me
Wrong" pre-mortem so the reader sees pillar status, then the falsifiable
exit conditions, then the cluster of upcoming events that could trigger
either side of the trade.

**Schema** — `upcoming_catalysts[]` items must carry the following fields
(legacy `date` single-field schema is still accepted; see backward-compat):

```json
{
  "date": "2026-07-29",          // legacy field, retained for backward compat
  "start_date": "2026-07-29",   // NEW (required for new format)
  "end_date": "2026-07-29",     // NEW (required, single = same as start)
  "event_type": "earnings",
  "category": "earnings",        // NEW: enum {earnings, regulatory, product, macro, other}
  "ticker": "GOOGL",              // NEW: subject or peer ticker (subject = default)
  "description": "Q2 2026 실적 발표",
  "significance": "high",        // existing: low/medium/high
  "expected_impact": "±5-8%"
}
```

**Categories** (5 buckets — Tailwind color codes are the contract):

| Category | 한국어 라벨 | Tailwind badge classes |
|----------|------------|------------------------|
| `earnings` | 실적 | `bg-blue-50 text-blue-700` |
| `regulatory` | 규제 | `bg-rose-50 text-rose-700` |
| `product` | 제품 | `bg-emerald-50 text-emerald-700` |
| `macro` | 매크로 | `bg-amber-50 text-amber-700` |
| `other` | 기타 | `bg-slate-50 text-slate-700` |

**Visual rules**:

- 12-month horizontal axis starting at the analysis month. Catalysts beyond
  the 12-month window collapse to a "12M+" bucket on the right edge.
- Vertical groups follow the 5 categories (in the order above). Empty
  groups still render their row label so the reader can see the absence.
- Marker size by `significance`:
  - `high` → filled bar/dot, full opacity
  - `medium` → filled dot, 70% opacity
  - `low` → outlined dot, narrow width
- Range catalysts (`start_date != end_date`) render as a Tailwind bar
  spanning the relevant cells; single-day catalysts render as a centered
  dot in the appropriate cell.
- Subject ticker dots are emphasized (border or shadow); peer ticker dots
  are dimmed and labeled with the peer ticker on hover (`title=` attribute).

**Peer merge (OD-4 — Phase D dependency)**:

- When `output/runs/{run_id}/peers/*.json` files exist (Phase D peer
  mini-pipeline), merge each peer's `next_earnings_date` (and any
  `upcoming_catalysts[]` provided) into the timeline payload.
- Peer catalysts always render below the subject in the same category row,
  with `is_subject=false` so the renderer can apply muted styling.
- Refuse any peer JSON lacking `_sanitization` (CLAUDE.md §12).

**Backward compatibility**:

- Snapshots written before Phase E only carry `date`, `event_type`,
  `description`, `significance`. The aggregator's
  `normalize_catalyst_for_timeline()` helper maps:
  - `date` → `start_date == end_date`
  - missing `category` → inferred from `description` + `event_type` keywords
    (earnings/regulatory/product/macro), falling back to `"other"` when no
    keyword matches
  - missing `ticker` → subject ticker
- Items whose `date` cannot be parsed as ISO `YYYY-MM-DD` (e.g. "TBD",
  "2026 Q4") are silently dropped from the timeline (they remain in the
  text catalyst list).
- An empty `upcoming_catalysts` list → omit the timeline section silently.

**Renderer contract**: see `dashboard-generator/references/html-template.md`
"Catalyst Timeline" section for the `{CATALYST_TIMELINE}` placeholder
markup. The orchestrator runs:

```bash
python .claude/skills/data-manager/scripts/catalyst-aggregator.py timeline \
  --ticker {SUBJECT} \
  --snapshot output/runs/{run_id}/{ticker}/analysis-result.json \
  --run-dir  output/runs/{run_id}/{ticker} \
  --include-peers \
  --output   output/runs/{run_id}/{ticker}/catalyst-timeline.json
```

then populates `{CATALYST_TIMELINE}` from the resulting JSON.

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
- [ ] Valuation Bridge produced when DCF + comps + analyst target are all available (4 anchors, weights sum to 1.0, weighted fair value arithmetic verified, ≥50-word reconciliation_logic)
- [ ] "What Would Make Me Wrong" includes pre-mortem
- [ ] All metrics have source tags
- [ ] Grade D metrics excluded from analysis body (noted in data sources table)
- [ ] Data Confidence Indicator grade computed
- [ ] Disclaimer present
