# Company Type Classification Reference

This file defines the 8 company types used for analysis focus customization. Read this during Step 2 (market-router) and Step 6 (analyst agent).

---

## Classification Table

| Type | Classification Signals | Primary Revenue Model |
|------|----------------------|----------------------|
| **Technology/Platform** | Software, SaaS, marketplace, cloud, social media, ad-tech, semiconductors | Recurring subscriptions, usage fees, advertising, chip sales |
| **Industrial/Manufacturing** | Physical goods, heavy equipment, chemicals, aerospace, defense, logistics | Product sales, service contracts, maintenance |
| **Financial** | Bank, insurance, investment bank, asset manager, fintech, REIT | NIM, fees, premiums, AUM-based fees, NOI |
| **Biotech/Pharma** | Drug discovery, clinical trials, biologics, CRO, medical devices | Drug royalties, partnerships, product sales |
| **Consumer** | Branded goods, retail, restaurants, luxury, automotive | Product sales, subscriptions, franchise fees |
| **Energy** | Oil & gas, renewables, utilities, pipelines | Commodity sales, tolling fees, regulated rates |
| **Korean-specific** | All Korean companies get this overlay ON TOP of their primary type | Applied as secondary classification |
| **Other** | Conglomerates, real estate (non-REIT), education, agriculture | Varies |

---

## Type-Specific Key Metrics

### Technology/Platform
**Primary focus metrics**:
- MAU/DAU, ARPU (for consumer platforms)
- Net Revenue Retention / NRR (for B2B SaaS)
- Rule of 40 = Revenue Growth % + FCF Margin %
- SBC as % of Revenue (key earnings quality indicator)
- Gross Margin (software should be >70%; hardware ~40-60%)
- CAC / LTV ratio (for subscription models)

**Variant View emphasis**: Technology moat durability, TAM penetration rate, platform network effects, AI integration optionality

**Risk emphasis**: Platform regulation, competitive disruption, talent retention, customer concentration

### Industrial/Manufacturing
**Primary focus metrics**:
- Order backlog ($ and months-of-revenue)
- Book-to-bill ratio
- Capacity utilization %
- Asset replacement value vs. book value
- Working capital intensity (DIO + DSO - DPO)
- Maintenance capex vs. growth capex split

**Variant View emphasis**: Cycle position, backlog visibility, pricing power, margin expansion from operating leverage

**Risk emphasis**: Commodity input costs, supply chain, labor contracts, capex cycle timing

### Financial
**Primary focus metrics**:
- Net Interest Margin (NIM) and trend
- Return on Equity (ROE) and Return on Tangible Equity (ROTE)
- Book Value and Tangible Book Value per share
- Capital ratios (CET1, Tier 1 for banks)
- Credit quality: NPL ratio, provision coverage, charge-offs
- Fee income as % of total revenue (recurring quality)
- Efficiency ratio (lower is better)

**Variant View emphasis**: NIM trajectory in rate cycle, credit normalization, fee income growth, capital return capacity

**Valuation note**: Use P/B and P/TBV instead of SOTP for banks. Use P/FFO and cap rate for REITs.

### Biotech/Pharma
**Primary focus metrics**:
- Pipeline: number of Phase 1/2/3 assets, lead indication, readout timeline
- Cash runway (months until cash depletion at current burn rate)
- Risk-adjusted NPV of pipeline (rNPV)
- Partnership/royalty agreements value
- Market share for commercial assets

**Variant View emphasis**: Trial data catalyst, regulatory path, partnership optionality, competitive landscape for indication

**Risk emphasis**: Clinical trial failure (binary risk), regulatory rejection, IP expiration, generic entry

**Note**: Pre-revenue biotechs: P/E is N/A. Use EV/Pipeline (peer comp rNPV) and cash runway instead.

### Consumer
**Primary focus metrics**:
- Same-store sales growth (SSS%)
- Brand equity metrics (pricing power, loyalty indicators)
- Inventory turnover
- Operating leverage (incremental margins)
- Loyalty program metrics (if applicable)

**Variant View emphasis**: Brand renaissance, pricing power durability, new geography/channel penetration

### Energy
**Primary focus metrics**:
- Reserve life / reserve replacement ratio
- Production cost per BOE (breakeven)
- Hedge book (% of production hedged, price)
- Free cash flow yield at spot prices
- Leverage (Net Debt/EBITDA at strip pricing)

**Variant View emphasis**: Commodity price scenario, cost structure advantage, capital discipline

---

## Korean Company Overlay

**Applied to ALL Korean companies in addition to their primary type**:

| Analysis Item | What to Include |
|--------------|----------------|
| Chaebol structure | Is this a chaebol affiliate? Cross-shareholding, circular ownership, controlling family stake |
| Governance assessment | Board independence, minority shareholder rights, related-party transactions |
| Governance premium/discount | Estimate the governance discount vs. international peers (typically 20-40% for Korean chaebols) |
| KRW/USD sensitivity | % of revenue in USD/foreign currency; natural hedges; impact of KRW move on earnings |
| 금융위/공정위 actions | Recent or pending regulatory actions by FSC (금융위) or FTC (공정위) |
| 밸류업 프로그램 | Has the company filed a Value-up (기업가치 제고 계획) plan? Board commitment? Buyback/cancellation track record |
| 외국인 지분율 추이 | Current foreign investor ownership % and trend (increasing = positive signal) |
| 자사주 매입/소각 | Buyback history: announced vs. actually cancelled (many Korean companies buy but don't cancel) |
| 배당 정책 | Dividend consistency, progressive vs. irregular payment |

---

## Macro Risk Factors by Type

**Used by**: Market Router (Step 2) to select macro search queries for Mode C/D analysis. Web Researcher (Step 4) executes the macro search. Analyst Agent includes macro context in Precision Risk analysis.

**Rule**: Macro searches execute for Mode C/D only. Mode A/B skip macro context.

### Macro Factor Lookup Table

| Type | Primary Macro Factors | Default Search Query Template |
|------|----------------------|-------------------------------|
| **Technology/Platform** | Interest rates (growth multiple sensitivity), AI/semiconductor capex cycle, US-China tech policy | `"{sector}" interest rates AI capex semiconductor regulation {YYYY}` |
| **Industrial/Manufacturing** | Commodity input costs (steel, copper, oil), capex cycle, supply chain disruption, labor costs | `"{sector}" commodity prices capex cycle supply chain {YYYY}` |
| **Financial** | Interest rate trajectory (NIM impact), credit cycle / delinquency trends, inflation expectations | `"interest rates" "credit cycle" bank NIM delinquency {YYYY}` |
| **Biotech/Pharma** | FDA regulatory posture, drug pricing legislation, healthcare policy, patent cliff | `FDA "drug pricing" legislation pharmaceutical regulation {YYYY}` |
| **Consumer** | Consumer spending / confidence, inflation (input costs + pricing power), credit conditions | `"consumer spending" inflation "retail sales" credit conditions {YYYY}` |
| **Energy** | Oil/gas spot + strip prices, energy transition policy, OPEC+ decisions, carbon pricing | `"oil price" "energy policy" OPEC+ renewable transition {YYYY}` |

### Korean Overlay Macro Factors

Applied to ALL Korean companies in addition to their type-specific factors:

| Factor | Search Query Addendum |
|--------|----------------------|
| KRW/USD exchange rate | `"원달러 환율" {YYYY} 전망` |
| 외국인 매수/매도 동향 | `"외국인 투자" KOSPI {YYYY}` |
| 한국 수출 지표 | `"한국 수출" 반도체 {YYYY}` |

### Macro → Precision Risk Allocation Rule

If a macro factor has a **direct, quantifiable impact pathway** on the ticker (e.g., "10% USD strengthening → Samsung export revenue decreases X%"), the Analyst MUST allocate one of the 3 Precision Risk slots to this macro risk with full mechanism chain.

If the macro factors are **contextual but not directly quantifiable** for this specific ticker, include them in the `macro_context` narrative section only — do NOT consume a Precision Risk slot.

---

## Multi-Segment Classification

When a company spans multiple types, classify by PRIMARY revenue driver:
- TSMC: Primary = Technology/Platform (fab services), Secondary = Industrial/Manufacturing → use Tech metrics with capital intensity focus
- Samsung Electronics: Primary = Technology/Platform + Korean overlay
- Tesla: Primary = Consumer (automotive) with Technology/Platform optionality (software, energy) → use Consumer metrics with note
- Berkshire Hathaway: Primary = Financial (insurance float) with Industrial/Manufacturing subsidiaries → use Financial approach with conglomerate SOTP

**Rule**: Never split analysis framework 50/50. Commit to primary type, note secondary type as "optionality / watch item".
