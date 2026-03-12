# Mode A — Quick Brief Output Template

Mode A produces an inline chat response (no file output). Concise, scannable, actionable. Target length: 300–500 words.

---

## Template Structure

```
## {Company Name} ({TICKER}) — Quick Brief
*{YYYY-MM-DD} | {Enhanced/Standard} Mode | {Language}*

---

### Current Price
**${price}** ({change_pct}% {▲/▼} today) | Mkt Cap: ${mkt_cap}B | 52W: ${low_52}–${high_52}

---

### 5 Key Metrics
| Metric | Value | Grade |
|--------|-------|-------|
| {metric_1_name} | {value} {[tag]} | {A/B/C} |
| {metric_2_name} | {value} {[tag]} | {A/B/C} |
| {metric_3_name} | {value} {[tag]} | {A/B/C} |
| {metric_4_name} | {value} {[tag]} | {A/B/C} |
| {metric_5_name} | {value} {[tag]} | {A/B/C} |

---

### Scenarios
| | Price Target | Return | Probability | Key Assumption |
|-|-------------|--------|-------------|----------------|
| 🟢 Bull | ${bull_target} | +{bull_return}% | {bull_prob}% | {bull_assumption} |
| 🟡 Base | ${base_target} | +{base_return}% | {base_prob}% | {base_assumption} |
| 🔴 Bear | ${bear_target} | {bear_return}% | {bear_prob}% | {bear_assumption} |

**R/R Score: {rr_score}** — {Attractive/Neutral/Unfavorable}

---

### Variant View
{1–2 sentences max. Must include ≥1 company-specific data point. What the market is missing or mispricing.}

---

### Top Risk
**{Risk Title}**: {Mechanism — how this risk translates to price decline, with specific numbers.}

---

### Verdict
**{Overweight/Underweight/Neutral/Watch}** — {1 sentence rationale with specific metric or event.}

---

*Disclaimer: This is not investment advice. For informational purposes only.*
*Sources: {source_list}*
```

---

## Field Population Rules

### Price Section
- `price`: Current price with 2 decimal places
- `change_pct`: Day change %; use ▲ for positive, ▼ for negative
- `mkt_cap`: In billions (e.g., "$2.8T" for trillion)
- `52W range`: From historical data or Yahoo Finance

### 5 Key Metrics Selection (by Company Type)
Select the 5 most relevant metrics based on `company-type-classification.md`:

| Company Type | Preferred Metrics |
|-------------|-------------------|
| Technology/Platform | P/E, EV/EBITDA, Rev Growth YoY, Operating Margin, FCF Yield |
| Industrial/Manufacturing | EV/EBITDA, Operating Margin, FCF Yield, Net Debt/EBITDA, Rev Growth |
| Financial | P/B, ROE, Net Interest Margin, Dividend Yield, Tier 1 Ratio |
| Biotech/Pharma | EV/Revenue (if pre-profit), Cash Runway, Pipeline Value, R&D% Revenue |
| Consumer | EV/EBITDA, Gross Margin, Rev Growth YoY, Dividend Yield, FCF Yield |
| Energy | EV/EBITDA, FCF Yield, Net Debt/EBITDA, Dividend Yield, Reserve Life |

Always include `[tag]` (source tag) next to each value. Omit row entirely if Grade D — do not show "—" in Mode A table (just drop the row and note at bottom).

### Scenarios
- All 3 scenarios REQUIRED
- Probability must sum to 100%
- Key assumption must be company-specific (not generic)
- Return % = (target - current) / current × 100

### R/R Score Calculation
```
R/R Score = (Bull_return × Bull_prob% + Base_return × Base_prob%) / |Bear_return × Bear_prob%|
```
Interpretation: >3.0 = Attractive | 1.0–3.0 = Neutral | <1.0 = Unfavorable

### Variant View Rules
- MUST start with what the market currently believes
- MUST state the specific disagreement with that view
- MUST include ≥1 company-specific data point (revenue figure, contract size, unit economics, etc.)
- FAIL: "Company has strong competitive moat and growing TAM" (generic — applicable to any company)
- PASS: "Market prices NVDA at 35x NTM earnings assuming 40% revenue growth, but H100 backlog visibility through Q3 suggests 55% growth is more likely [API]"

### Source List Format
List abbreviated sources: `Yahoo Finance [Web], SEC EDGAR [API], Financial Datasets MCP [API]`

---

## Korean Output Variant

When `output_language = "Korean"`, translate all section headers and labels to Korean:

| English | Korean |
|---------|--------|
| Quick Brief | 빠른 분석 |
| Current Price | 현재 주가 |
| Key Metrics | 핵심 지표 |
| Scenarios | 시나리오 |
| Variant View | 차별화 시각 |
| Top Risk | 주요 리스크 |
| Verdict | 투자 의견 |
| Overweight | 비중확대 |
| Underweight | 비중축소 |
| Neutral | 중립 |
| Watch | 관찰 |
| Attractive | 매력적 |
| Unfavorable | 비매력적 |

Price formatting for Korean stocks: ₩{price:,} (comma separator, no decimals for KRW)

---

## Completion Checklist

Before outputting, verify:
- [ ] All 5 metrics have source tags
- [ ] Scenario probabilities sum to 100%
- [ ] R/R Score formula applied correctly
- [ ] Variant View contains ≥1 specific data point (not generic)
- [ ] No Grade D data values shown (excluded rows noted at bottom if any)
- [ ] Disclaimer present
