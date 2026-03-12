# Mode D — Investment Memo Output Template

Mode D produces a professionally formatted Word document (.docx) with section headings,
financial tables, scenario matrix, risk table, EBITDA bridge, and source tags throughout.

**Output path**: `output/reports/{ticker}_D_{lang}_{YYYY-MM-DD}.docx`
**Example**: `output/reports/AAPL_D_EN_2026-03-12.docx`

**How it works**:
1. Analyst writes all content (narrative + tables) into `output/analysis-result.json` → `sections`
2. `output-generator/SKILL.md` calls `docx-generator.py` to render the DOCX
3. Final file can be opened in Microsoft Word, Google Docs, or LibreOffice

Target narrative length: 3,000–4,000 words across 10 sections (written into JSON sections).

---

## JSON Section Structure (write to `analysis-result.json`)

The Analyst must populate `analysis-result.json → sections` with the following fields.
The `docx-generator.py` reads these fields to build the formatted document.

### Required top-level fields (outside `sections`)
```json
{
  "ticker": "AAPL",
  "company_name": "Apple Inc.",
  "exchange": "NASDAQ",
  "market": "US",
  "data_mode": "enhanced",
  "output_mode": "D",
  "output_language": "en",
  "analysis_date": "2026-03-12",
  "price_at_analysis": 175.50,
  "currency": "USD",
  "rr_score": 7.8,
  "verdict": "Overweight",
  "scenarios": {
    "bull": {"target": 225, "return_pct": 28.2, "probability": 0.30, "key_assumption": "..."},
    "base": {"target": 195, "return_pct": 11.4, "probability": 0.50, "key_assumption": "..."},
    "bear": {"target": 145, "return_pct": -17.1, "probability": 0.20, "key_assumption": "..."}
  },
  "data_quality_used": {
    "grade_A_count": 3, "grade_B_count": 5, "grade_C_count": 1, "grade_D_count": 1,
    "overall_grade": "B",
    "exclusions": [{"metric": "ev_ebitda", "reason": "EBITDA TTM unverifiable"}]
  }
}
```

### Required `sections` fields
```json
"sections": {
  "executive_summary": {
    "verdict": "Overweight",
    "rr_score": 7.8,
    "current_price": 175.50,
    "base_target": 195,
    "horizon": "12 months",
    "narrative": "3-5 sentence executive summary. Lead with variant view — what the market prices in vs. analysis finding..."
  },
  "business_overview": "Full Section 1 narrative (300-400 words). Business description, competitive position, TAM, key operating metrics. All numbers source-tagged.",
  "financial_performance": {
    "narrative": "Revenue quality and margin analysis narrative...",
    "revenue_table": [
      {"quarter": "Q1 FY2025", "revenue": "$124.3B", "yoy_growth": "5.1%", "source": "[API]"},
      {"quarter": "Q2 FY2025", "revenue": "$95.4B",  "yoy_growth": "4.9%", "source": "[API]"}
    ],
    "margin_table": [
      {"quarter": "Q1 FY2025", "gross_margin": "46.9%", "op_margin": "31.2%", "net_margin": "24.1%", "source": "[API]"}
    ],
    "cash_flow_table": [
      {"metric": "Operating CF", "ttm": "$118.3B", "prior_year": "$109.2B", "change": "+8.3%"},
      {"metric": "CapEx",        "ttm": "($9.4B)",  "prior_year": "($10.7B)", "change": "-12.1%"},
      {"metric": "FCF",          "ttm": "$108.9B",  "prior_year": "$98.5B",   "change": "+10.6%"},
      {"metric": "FCF Margin",   "ttm": "24.2%",    "prior_year": "22.9%",    "change": "+130bps"}
    ],
    "balance_sheet": [
      {"item": "Cash & Equivalents", "value": "$65.2B",   "source": "[API]"},
      {"item": "Total Debt",         "value": "$109.3B",  "source": "[API]"},
      {"item": "Net Debt",           "value": "$44.1B",   "source": "[Calculated]"},
      {"item": "Net Debt/EBITDA",    "value": "0.37x",    "source": "[Calculated]"},
      {"item": "Shares Outstanding", "value": "15,441M",  "source": "[API]"}
    ],
    "fcf_note": "SBC represents 2.8% of TTM revenue [API]. Working capital changes minimal. No major one-time items in TTM period."
  },
  "valuation_analysis": {
    "narrative": "Valuation context: what growth assumptions are implied by current price...",
    "valuation_table": [
      {"metric": "P/E (NTM)", "current": "28.0x [API]", "sector_avg": "~22x", "5y_historical": "~25x", "assessment": "Premium"},
      {"metric": "EV/EBITDA", "current": "—",            "sector_avg": "~16x", "5y_historical": "—",    "assessment": "[Unverified]"},
      {"metric": "P/FCF",     "current": "22.3x [Calculated]", "sector_avg": "~20x", "5y_historical": "—", "assessment": "Slight premium"},
      {"metric": "P/Sales",   "current": "7.2x [API]",  "sector_avg": "~5x",  "5y_historical": "~6x",  "assessment": "Premium"}
    ],
    "sotp_table": null
  },
  "variant_view_q1": "Full Q1 text (150-250 words). State market consensus first, then the specific disagreement, then supporting evidence with data points...",
  "variant_view_q2": "Catalyst summary text (1-2 sentences on most critical catalyst)...",
  "variant_view_q2_catalysts": [
    {"catalyst": "Q2 FY2026 earnings — Services revenue beat", "timeline": "Apr 2026", "probability": "High", "impact": "+5-8% stock reaction if Services >$28B"},
    {"catalyst": "WWDC 2026 AI features announcement",         "timeline": "Jun 2026", "probability": "Medium", "impact": "Re-rating potential if Apple Intelligence monetization confirmed"},
    {"catalyst": "China market share data — Lunar New Year",   "timeline": "Mar 2026", "probability": "Medium", "impact": "Downside risk if iPhone share < 15% in China"}
  ],
  "variant_view_q3": "Full Q3 text on optionality the market is not pricing in...",
  "variant_view_q4": "Full Q4 text on capital allocation analysis. Include buyback math, M&A track record, debt strategy...",
  "variant_view_q5": "Full Q5 text. Thesis achieved conditions, thesis broken conditions (≥3 testable), better opportunity criteria...",
  "precision_risks": [
    {
      "risk": "DOJ App Store Investigation",
      "mechanism": "Forced reduction in App Store commission rate from 30% to 15-17% → App Store revenue declines ~$6B annually → EBITDA impact ~$5B (4.2% of TTM) → P/E compression from 28x to 24x at current growth rate",
      "ebitda_impact": "~$5B (4.2% of TTM EBITDA)",
      "probability": "Medium",
      "mitigation": "Monitor: DOJ filing updates, EU DMA compliance precedent"
    }
  ],
  "macro_risk": "FX headwind: 57% of revenue ex-Americas [API]. 10% USD strengthening reduces EPS by ~$0.45 (4.5% of FY2026 consensus EPS). Interest rate sensitivity minimal — net cash position after adjusting for operational debt.",
  "investment_scenarios": {
    "narratives": {
      "bull": "Services revenue reaches 25% of total by FY2027 on Apple Intelligence monetization. iPhone cycle stable. Re-rating to 32x NTM P/E drives $225 target.",
      "base": "iPhone unit growth 6-8% annually, Services 15% YoY. Multiple holds at 28x. $195 target in 12 months on EPS growth alone.",
      "bear": "China revenue contracts 20%+ on Huawei share gains and geopolitical escalation. Services growth decelerates to <10%. Multiple compresses to 22x. $145 target."
    }
  },
  "peer_comparison": [
    {"metric": "P/E",       "AAPL": "28.0x [API]", "MSFT": "32.5x", "GOOGL": "20.1x", "sector_avg": "~22x"},
    {"metric": "EV/EBITDA", "AAPL": "— [Unverified]", "MSFT": "22.3x", "GOOGL": "14.8x", "sector_avg": "~16x"},
    {"metric": "Rev Growth","AAPL": "5.1% [API]",  "MSFT": "17.6%", "GOOGL": "12.0%", "sector_avg": "~10%"},
    {"metric": "Op Margin", "AAPL": "31.2% [API]", "MSFT": "44.8%", "GOOGL": "28.5%", "sector_avg": "~25%"},
    {"metric": "FCF Yield", "AAPL": "4.5% [Calculated]", "MSFT": "2.3%", "GOOGL": "4.1%", "sector_avg": "~3%"}
  ],
  "peer_comparison_narrative": "Relative valuation assessment: premium vs. GOOGL justified by ecosystem lock-in and Services margin expansion. Discount vs. MSFT reflects lower growth rate. Key competitive threat: MSFT's enterprise AI adoption rate outpacing Apple Intelligence consumer monetization.",
  "management_governance": "Full Section 8 text (150-200 words). CEO tenure, guidance track record (last 4 quarters), capital allocation history...",
  "quality_of_earnings": {
    "ebitda_bridge": [
      {"item": "Reported EBITDA",         "amount": "$125.0B", "note": "[API]"},
      {"item": "Less: SBC",               "amount": "($12.9B)", "note": "2.8% of revenue [API]"},
      {"item": "Less: Restructuring",     "amount": "($0.0B)",  "note": "None in TTM"},
      {"item": "Less: M&A Costs",         "amount": "($0.2B)",  "note": "One-time"},
      {"item": "Less: Maintenance CapEx", "amount": "($6.5B)",  "note": "Estimated [Calculated]"},
      {"item": "Adjusted Cash Earnings",  "amount": "$105.4B",  "note": "16% haircut vs. reported EBITDA"}
    ],
    "narrative": "FCF conversion quality analysis...",
    "fcf_conversion": "Operating CF / Net Income = 1.24x — strong accruals quality (>1.1x threshold). No unusual working capital changes.",
    "earnings_sustainability": "Margins sustainable: hardware margins stable, Services margins expanding at 73% gross [API]. No significant one-time items inflate TTM EBITDA."
  },
  "what_would_make_me_wrong": [
    {
      "assumption": "Services revenue growth sustains at 15%+ annually",
      "if_wrong": "If Services growth decelerates to <10%, our base case EPS of $8.20 misses by ~$0.40 (5%), compressing target to ~$175 at current multiple",
      "monitoring_indicator": "Watch quarterly Services revenue reports; flag if growth < 12% for 2 consecutive quarters",
      "probability": "Low"
    },
    {
      "assumption": "China revenue stabilizes after FY2025 headwinds",
      "if_wrong": "20% China revenue decline = ~$14B revenue impact = bear case trigger",
      "monitoring_indicator": "IDC China smartphone market share quarterly data; Huawei P-series sales data",
      "probability": "Medium"
    },
    {
      "assumption": "No material antitrust action reduces App Store economics",
      "if_wrong": "Commission cut to 15% reduces EBITDA by ~$5B; P/E compression to 24x = $155 fair value",
      "monitoring_indicator": "DOJ case progress; EU DMA enforcement actions",
      "probability": "Low-Medium"
    }
  ],
  "pre_mortem": "If this investment loses 30% over 12 months, the most likely cause would be a simultaneous hit from China revenue contraction exceeding 25% and a DOJ-mandated App Store commission reduction, compressing both revenue and multiple in the same fiscal year — a scenario we assign 8% probability but have not fully priced into our bear case.",
  "data_sources": [
    {"data_category": "Revenue / Earnings",  "source": "Financial Datasets MCP",  "confidence": "A", "tag": "[API]"},
    {"data_category": "Current Price",       "source": "get_current_stock_price", "confidence": "A", "tag": "[API]"},
    {"data_category": "Analyst Estimates",   "source": "FMP MCP",                 "confidence": "B", "tag": "[FMP]"},
    {"data_category": "Valuation Ratios",    "source": "ratio-calculator.py",     "confidence": "A", "tag": "[Calculated]"},
    {"data_category": "Peer Data",           "source": "Financial Datasets MCP",  "confidence": "B", "tag": "[API]"},
    {"data_category": "News / Qualitative",  "source": "Reuters / CNBC / Web",    "confidence": "C", "tag": "[Web]"}
  ]
}
```

---

## Content Requirements by Section

---

## Content Requirements by Section

The following shows the expected content structure for each section. Write this content
into the JSON `sections` object — do NOT write a separate Markdown file.

```markdown
# Section Content Guide (for analyst reference — output goes into analysis-result.json)
# Investment Memo: {Company Name} ({TICKER})
**Date**: {YYYY-MM-DD}
**Analysis Mode**: {Enhanced/Standard} | **Data Confidence**: {summary_grade}
**Prepared by**: AI Research Assistant

---

## Executive Summary

**Verdict**: {Overweight / Underweight / Neutral / Watch}
**R/R Score**: {score} ({Attractive / Neutral / Unfavorable})
**Current Price**: ${price} | **Base Case Target**: ${base_target} | **Horizon**: 12 months

{3–5 sentences. The single most important thing to understand about this company right now. Lead with the variant view — what the market is pricing in vs. what the analysis suggests. Include price, market cap, sector. State the thesis in one clear sentence.}

---

## 1. Business Overview & Competitive Position

*Target: 300–400 words*

**Business Description**
{What the company does, how it makes money, primary revenue streams with % breakdown [tag]}

**Competitive Position**
{Market share [tag], key competitive advantages — each must have a supporting data point specific to this company. Do NOT use generic language like "strong moat" without quantification.}

**Addressable Market**
{TAM with source [tag], company's current penetration %, growth rate of market [tag]}

**Key Operating Metrics**
{Company-type specific KPIs with values — e.g., MAUs for consumer tech, ASP trends for hardware, backlog for industrials. All values tagged.}

---

## 2. Financial Performance

*Target: 400–500 words*

### Revenue Trend (Last 8 Quarters)
| Quarter | Revenue | YoY Growth | Source |
|---------|---------|------------|--------|
| {Q} | ${rev}B | {pct}% | {[tag]} |
| ... | | | |

**Revenue Quality Analysis**: {Comment on organic vs. inorganic, geographic mix, product mix shifts, pricing power evidence}

### Profitability Trend
| Quarter | Gross Margin | Op. Margin | Net Margin | Source |
|---------|-------------|------------|------------|--------|
| {Q} | {pct}% | {pct}% | {pct}% | {[tag]} |
| ... | | | | |

**Margin Analysis**: {Trend direction, key drivers, one-time items excluded or flagged}

### Cash Flow Analysis
| Metric | TTM | Prior Year | Change |
|--------|-----|-----------|--------|
| Operating CF | ${val}B | ${val}B | {pct}% |
| CapEx | ${val}B | ${val}B | {pct}% |
| FCF | ${val}B | ${val}B | {pct}% |
| FCF Margin | {pct}% | {pct}% | — |

**FCF Quality Note**: {Comment on SBC as % of revenue [tag], major working capital items, one-time charges}

### Balance Sheet Snapshot
| Item | Value | Source |
|------|-------|--------|
| Cash & Equivalents | ${val}B | {[tag]} |
| Total Debt | ${val}B | {[tag]} |
| Net Debt | ${val}B | {[Calculated]} |
| Net Debt/EBITDA | {val}x | {[Calculated]} |
| Shares Outstanding | {val}M | {[tag]} |

---

## 3. Valuation Analysis

*Target: 300–400 words*

### Core Valuation Metrics
| Metric | Current | Sector Avg | 5Y Historical | Assessment |
|--------|---------|-----------|---------------|------------|
| P/E (NTM) | {val}x {[tag]} | ~{val}x | ~{val}x | {Premium/Discount/In-line} |
| EV/EBITDA | {val}x {[tag]} | ~{val}x | ~{val}x | {Premium/Discount/In-line} |
| P/FCF | {val}x {[Calculated]} | ~{val}x | — | — |
| P/Sales | {val}x {[tag]} | ~{val}x | — | — |
| Dividend Yield | {val}% {[tag]} | ~{val}% | — | — |

*Sector average sourced from [tag]. Historical average sourced from [tag] or estimated from peer data.*

**Valuation Context**
{Why is the current multiple justified or unjustified? What growth/margin assumptions are implied by current price? Calculate implied growth rate from Gordon Growth Model or reverse DCF if applicable.}

### SOTP Analysis (if applicable)
{For companies with 2+ distinct segments. If single-segment or data insufficient, omit this sub-section.}

| Segment | Revenue TTM | EV/Revenue or EV/EBITDA | Implied EV | Rationale |
|---------|------------|------------------------|-----------|-----------|
| {Segment 1} | ${val}B | {mult}x | ${val}B | {peer multiple justification} |
| {Segment 2} | ${val}B | {mult}x | ${val}B | {peer multiple justification} |
| **Total EV** | | | **${val}B** | |
| Less: Net Debt | | | (${val}B) | |
| **Equity Value** | | | **${val}B** | |
| **Per Share** | | | **${val}** | |
| **vs. Current Price** | | | **{pct}% premium/discount** | |

---

## 4. 5-Question Variant View

*Target: 500–600 words*

### Q1: What is the Market Currently Pricing In — and Where Do We Disagree?

**Market Consensus View**: {Explicitly state what the market believes — specific implied growth rate, multiple, or assumption embedded in current price. Not generic.}

**Our View**: {State the specific disagreement with supporting evidence. Must include ≥1 company-specific data point not widely covered or mispriced.}

**Supporting Evidence**:
- {Evidence 1 with data point [tag]}
- {Evidence 2 with data point [tag]}
- {Evidence 3 with data point [tag]}

*Variant View Quality Test: Replace the company name with a direct competitor. If the argument still holds → rewrite. It must be company-specific.*

### Q2: What Would Change the Market's Mind? (Catalyst Map)

| Catalyst | Timeline | Probability | Impact if Triggered |
|----------|----------|-------------|---------------------|
| {Specific event/data point} | {Q1 2026 / H2 2026 / etc.} | {High/Medium/Low} | {Specific effect on price or multiple} |
| {Specific event/data point} | | | |
| {Specific event/data point} | | | |

{1–2 sentences on the most critical catalyst and why it's the key swing factor}

### Q3: What Optionality Is the Market Not Pricing In?

{Describe 1–2 specific upside options not in consensus estimates. Could be: new product, geographic expansion, regulatory tailwind, technology transition. Each must have a rough size estimate — e.g., "if {optionality} achieves {x} revenue by 2027, it adds ~${y} to fair value at {z}x multiple".}

### Q4: Capital Allocation — How Is Management Creating (or Destroying) Value?

**Buyback Math**: {If applicable — shares outstanding trend [tag], buyback yield %, effect on EPS growth}

**M&A Track Record**: {Recent acquisitions, integration success, capital deployed [tag]}

**Debt Strategy**: {Leverage trend, maturity profile, refinancing risk}

**Dividend Policy**: {Yield [tag], payout ratio [tag], sustainability assessment}

**Assessment**: {One paragraph on whether management is creating or destroying value with capital, with specific examples}

### Q5: Exit Conditions — When Would We Close the Position?

**Thesis Achieved** (positive exit): {Specific price/multiple target, event, or timeline that would indicate full value realization → reduce/exit}

**Thesis Broken** (stop-loss conditions):
- {Condition 1 — specific and testable, e.g., "Revenue growth decelerates below 10% for 2 consecutive quarters"}
- {Condition 2}
- {Condition 3}

**Better Opportunity**: {What would constitute a clearly superior risk/reward in the same sector at time of review}

---

## 5. Precision Risk Analysis

*Target: 300–400 words*

### Risk Matrix
| Risk | Mechanism | EBITDA Impact | Probability | Mitigation |
|------|-----------|---------------|-------------|------------|
| {Risk 1} | {How risk → P&L → stock price, step by step} | {$XB or X% reduction} | {H/M/L} | {Specific hedge or monitoring indicator} |
| {Risk 2} | | | | |
| {Risk 3} | | | | |

*Risk Rule: Every risk must have a mechanism. "Competition risk" → FAIL. "Amazon AWS entering enterprise HR SaaS at 30-40% discount, compressing {TICKER}'s blended ASP from $120 to $85/seat, reducing revenue by ~$800M (12% of TTM) at current seat count" → PASS.*

### Macro Risk Overlay
{Interest rate sensitivity, FX exposure [% revenue from non-domestic], commodity exposure if relevant. All with quantified impact estimates.}

### Regulatory & ESG Risks
{Only include if material. Must specify mechanism and probable timeline.}

---

## 6. Investment Scenarios

*Target: 200–300 words*

| | Bull Case | Base Case | Bear Case |
|-|-----------|-----------|-----------|
| **Probability** | {pct}% | {pct}% | {pct}% |
| **Price Target** | ${val} | ${val} | ${val} |
| **Implied Return** | +{pct}% | +{pct}% | {pct}% |
| **Key Assumption** | {company-specific} | {company-specific} | {company-specific} |
| **Key Metric Driver** | {specific metric} | {specific metric} | {specific metric} |
| **Timeline** | 12 months | 12 months | 12 months |

**R/R Score**: {score}
`R/R = (Bull_return × {bull_prob}% + Base_return × {base_prob}%) / |Bear_return × {bear_prob}%| = {score}`

**Scenario Narratives**:

*Bull*: {2–3 sentences. Specific triggers, specific metrics, specific price level.}

*Base*: {2–3 sentences. Most likely path, key assumption that must hold.}

*Bear*: {2–3 sentences. Specific catalyst for downside, how far price could fall.}

Probability sum: {bull}% + {base}% + {bear}% = 100% ✓

---

## 7. Peer Comparison

*Target: 200–300 words*

| Metric | {TICKER} | {Peer1} | {Peer2} | Sector Avg |
|--------|----------|---------|---------|-----------|
| P/E | {val}x | {val}x | {val}x | ~{val}x |
| EV/EBITDA | {val}x | {val}x | {val}x | ~{val}x |
| Rev Growth | {pct}% | {pct}% | {pct}% | ~{pct}% |
| Op. Margin | {pct}% | {pct}% | {pct}% | ~{pct}% |
| FCF Yield | {pct}% | {pct}% | {pct}% | ~{pct}% |

**Relative Valuation Assessment**:
{Is the premium or discount vs. peers justified? What explains the difference? Must cite specific operational or structural reason — not just "better quality business".}

**Key Competitive Threat Assessment**:
{Which peer poses the most direct competitive threat and why? What metric is most at risk?}

---

## 8. Management & Corporate Governance

*Target: 150–200 words*

**Leadership**
{CEO tenure, relevant background, alignment (insider ownership % [tag] or stock-based comp %)}

**Guidance Track Record**
{Last 4 quarters: did management meet, beat, or miss their own guidance? Pattern assessment [tag for each quarter if data available]}

**Capital Allocation History**
{Key decisions over past 2 years — acquisitions, buybacks, dividends, divestitures. Value creation or destruction assessment.}

**Korean Overlay** (if market = KR):
- 외국인 지분율: {pct}% [tag]
- 지배구조 구조: {Chaebol / Independent / etc.}
- 밸류업 참여 여부: {Yes/No/Pending}
- 주요 대주주: {Name, % [tag]}

---

## 9. Quality of Earnings (QoE) Assessment

*Target: 200–250 words*

### EBITDA Bridge
| Item | Amount | Note |
|------|--------|------|
| Reported EBITDA | ${val}B | [tag] |
| Less: SBC | (${val}B) | {X}% of revenue [tag] |
| Less: Restructuring | (${val}B) | One-time / recurring? |
| Less: M&A Costs | (${val}B) | One-time |
| Less: Maintenance CapEx | (${val}B) | Estimated [Calculated] |
| **Adjusted Cash Earnings** | **${val}B** | |
| vs. Reported EBITDA | | {pct}% haircut |

**FCF Conversion Quality**
{Operating CF / Net Income = {val}x. High (>1.1x) = good accruals quality. If low (<0.8x), explain why.}

**Earnings Sustainability**
{Are current margins sustainable? Any one-time revenue or cost items that inflate or depress reported numbers? Key add-backs that should be scrutinized.}

---

## 10. What Would Make Me Wrong

*Target: 200–250 words*

*This section requires the analyst to steelman the bear case and identify the 3 most important ways the thesis could fail.*

**Assumption 1: {Core assumption underlying the thesis}**
- If wrong: {Specific consequence for price target or earnings model}
- Monitoring indicator: {What data point or event would confirm this assumption is breaking?}
- Probability of being wrong: {H/M/L}

**Assumption 2: {Second core assumption}**
- If wrong: {Specific consequence}
- Monitoring indicator: {What to watch}
- Probability of being wrong: {H/M/L}

**Assumption 3: {Third core assumption}**
- If wrong: {Specific consequence}
- Monitoring indicator: {What to watch}
- Probability of being wrong: {H/M/L}

**Pre-Mortem**: *If this investment loses 30% over 12 months, the most likely cause would be: {one specific scenario, written as if it already happened}.*

---

## Appendix: Data Sources & Confidence

| Data Category | Source | Confidence | Tag |
|--------------|--------|-----------|-----|
| Revenue / Earnings | {SEC EDGAR / Financial Datasets MCP / DART} | {A/B/C} | {[API]/[DART]/[Web]} |
| Current Price | {Yahoo Finance / get_current_stock_price} | {A/B} | {[API]/[Web]} |
| Analyst Estimates | {FMP / TipRanks / MarketBeat} | {B/C} | {[FMP]/[Web]} |
| Valuation Ratios | {Calculated / get_financial_metrics} | {A/B} | {[Calculated]/[API]} |
| Peer Data | {Financial Datasets MCP / Web} | {B/C} | {[API]/[Web]} |
| News / Qualitative | {Reuters / CNBC / Seeking Alpha} | {C} | {[Web]} |

**Data Exclusions**: {List any Grade D metrics excluded from this analysis, with reason}

**Data Mode**: {Enhanced (Financial Datasets MCP active) / Standard (web-only)}

---

*Disclaimer: This investment memo is generated by an AI research assistant for informational purposes only. It does not constitute investment advice, a recommendation to buy or sell any security, or a guarantee of investment returns. All projections are hypothetical and based on available public information. Actual results may differ materially. This memo is not a substitute for professional financial advice. Always conduct your own research and consult a qualified financial advisor before making investment decisions.*

*Generated: {YYYY-MM-DD HH:MM} UTC | Model: Claude Code | Data Sources: {abbreviated list}*
```

---

## Writing Rules

### Anti-Generic Enforcement
Every section must pass this test: **Replace company name with a direct competitor — does the statement still hold?**
- If YES → rewrite with company-specific data
- If NO → acceptable (company-specific)

### Data Tagging Requirement
- Every numerical claim must have a source tag: `[API]`, `[DART]`, `[Web]`, `[Calculated]`, `[FMP]`, `[≈]`, `[1S]`
- Grade D data: never appears in the memo. Referenced only in Appendix exclusion list.

### Section Writing Order
Write sections sequentially. Do NOT go back and modify earlier sections after writing later ones. If a later section reveals inconsistency, add a correction note inline rather than editing.

### Word Count Targets
| Section | Target |
|---------|--------|
| Executive Summary | 100–150 words |
| 1. Business Overview | 300–400 words |
| 2. Financial Performance | 400–500 words |
| 3. Valuation Analysis | 300–400 words |
| 4. 5-Question Variant View | 500–600 words |
| 5. Precision Risk | 300–400 words |
| 6. Investment Scenarios | 200–300 words |
| 7. Peer Comparison | 200–300 words |
| 8. Management & Governance | 150–200 words |
| 9. Quality of Earnings | 200–250 words |
| 10. What Would Make Me Wrong | 200–250 words |
| **Total** | **2,950–3,750 words** |

### Prohibited Phrases (Auto-Fail for Critic)
These phrases are banned because they are generic and meaningless:
- "strong competitive moat" (without quantification)
- "significant market opportunity" (without TAM data)
- "experienced management team" (without specific track record)
- "positioned for growth" (without specific growth driver + metric)
- "multiple revenue streams" (without segment breakdown)

Replace with specific, quantified, company-specific language.

---

## Korean Output Variant

When `output_language = "ko"` (set in `analysis-result.json`):
1. All narrative text in `sections` written in Korean
2. Section 8 Korean Overlay mandatory — include `외국인 지분율`, `지배구조 구조`, `밸류업 참여 여부`, `주요 대주주`
3. Prices in KRW (₩ prefix, comma separator, no decimals) — set `"currency": "KRW"`
4. `verdict` value in Korean: "비중확대" / "비중축소" / "중립" / "관찰"
5. Include DART filing reference in `data_sources` array
6. `docx-generator.py` automatically uses Korean section headings when `output_language = "ko"`

---

## File Output

Save all content to: `output/analysis-result.json` (sections object as defined above)

The output-generator calls `docx-generator.py` to produce: `output/reports/{ticker}_D_{lang}_{YYYY-MM-DD}.docx`

The `.docx` file includes: formatted headings, financial tables, scenario matrix, risk table, EBITDA bridge, disclaimer, and data sources appendix. No separate `.md` file is written for Mode D.

---

## Completion Checklist

Before finalizing:
- [ ] All 10 sections present with ≥50 words each
- [ ] Total word count 2,950–3,750 (estimate acceptable)
- [ ] Q1 Variant View explicitly states market consensus vs. analyst disagreement
- [ ] Q2 Catalyst Map has ≥3 specific, dated catalysts
- [ ] Q3 Optionality has rough size estimate
- [ ] Q5 has ≥3 specific, testable exit conditions
- [ ] All 3 Precision Risks have mechanism (cause → effect chain)
- [ ] Scenario probabilities sum to 100%
- [ ] R/R Score formula shown and verified
- [ ] All numerical claims have source tags
- [ ] No Grade D data in analysis body (check Appendix exclusions)
- [ ] "What Would Make Me Wrong" — pre-mortem paragraph present
- [ ] Disclaimer present
- [ ] Appendix data sources table complete
