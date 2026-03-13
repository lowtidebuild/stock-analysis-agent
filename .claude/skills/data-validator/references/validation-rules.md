# Data Validation Rules Reference

This file is read by `data-validator/SKILL.md` during Step 5. It defines the complete validation ruleset for financial data.

---

## Section A — The 10 Key Figures

These 10 data points MUST be present and verified before analysis proceeds. In Standard Mode, each must be confirmed from ≥2 independent sources.

| # | Data Point | Formula / Definition | Source Priority (US) | Source Priority (KR) |
|---|-----------|---------------------|---------------------|---------------------|
| 1 | Current price | Market price at time of analysis | Yahoo Finance, Google Finance, MarketWatch | 네이버금융, KIND |
| 2 | Diluted shares outstanding | Most recent quarterly filing | SEC 10-Q/10-K, financial portal | DART 재무제표, 네이버금융 |
| 3 | Market cap | Price × Diluted Shares | Calculate; compare to stated | Calculate; compare to stated |
| 4 | Latest quarter revenue | Most recent earnings | SEC 10-Q, earnings press release, financial portal | DART 실적발표, 네이버금융 |
| 5 | Latest quarter EPS (diluted) | Net Income / Diluted Shares | SEC 10-Q, earnings press release | DART, 네이버금융 |
| 6 | Net debt (or net cash) | Total Debt - Cash & Equivalents | SEC balance sheet, financial portal | DART 재무상태표 |
| 7 | TTM EBITDA (or Operating Income) | Sum of last 4Q EBITDA | Calculate from quarterly data; compare to stated | DART, FnGuide |
| 8 | P/E ratio | Price / TTM EPS (diluted) | SELF-CALCULATE from #1 and #5 | SELF-CALCULATE |
| 9 | EV/EBITDA | (Market Cap + Net Debt) / TTM EBITDA | SELF-CALCULATE from #3, #6, #7 | SELF-CALCULATE |
| 10 | FCF or Operating Cash Flow | Operating CF - Capex | SEC cash flow statement, financial portal | DART 현금흐름표 |

**Critical rule**: Items 8 and 9 must be SELF-CALCULATED, not taken from a data source pre-calculated value. This catches the most common LLM hallucination pattern (plausible-looking but wrong ratios).

---

## Section B — Arithmetic Consistency Formulas

Run these checks after collecting data. All checks use 10% tolerance threshold.

| Check | Formula | Tolerance | Action if Fails |
|-------|---------|-----------|-----------------|
| Market Cap | Price × Diluted Shares | ±10% vs stated | Recalculate; use self-calculated value; flag source discrepancy |
| P/E | Price / TTM EPS | ±10% vs stated | Recalculate; flag source; if >50% off, grade D |
| EV | Market Cap + Net Debt | ±10% vs stated | Recalculate; trace which input is wrong |
| Gross Margin | Gross Profit / Revenue × 100 | ±2pp vs stated | Identify wrong input; recalculate |
| Revenue Growth YoY | (Current Q Revenue - Prior YA Revenue) / Prior YA Revenue × 100 | ±3pp vs stated | Recalculate; check which revenue figure is wrong |
| Net Debt | Total Debt - Cash | Exact | Identify components |
| EBITDA | Operating Income + D&A | ±15% (D&A estimation) | Note as approximate if D&A not separately disclosed |
| FCF | Operating CF - Capex | Exact | Verify both components |

**If arithmetic is inconsistent**: Trace which input figure is the outlier. The most primary source wins (SEC filing > financial portal > calculated > news article).

---

## Section C — Sanity Range Table by Sector

Use these ranges in Step 5c (Sanity Check). Values outside range → flag as suspicious, re-search.

| Sector | P/E Range | EV/EBITDA Range | Op Margin Range | Rev Growth Range |
|--------|-----------|-----------------|-----------------|------------------|
| Technology/Platform (large cap) | 15–60x | 15–40x | 15–40% | 5–30% |
| Technology/Platform (growth) | 30–150x or N/A | 20–80x | -20–30% | 20–80% |
| Industrial/Manufacturing | 10–25x | 7–15x | 5–20% | -5–15% |
| Financial (bank) | 8–20x | N/A (use P/B) | 20–50% (ROE-based) | -5–10% |
| Financial (insurance) | 8–18x | N/A | 5–20% | 0–10% |
| Biotech/Pharma (commercial) | 15–35x | 10–25x | 15–40% | 0–20% |
| Biotech/Pharma (pre-revenue) | N/A | N/A | <0% | N/A |
| Consumer Staples | 15–25x | 10–18x | 10–25% | 0–8% |
| Consumer Discretionary | 15–35x | 10–20x | 5–20% | 0–15% |
| Energy | 8–20x (cyclical) | 4–12x | 10–30% | -15–30% |
| Korean large-cap (chaebol) | 8–18x | 6–12x | 5–20% | -5–15% |
| Korean mid-cap | 10–25x | 7–15x | 5–20% | 0–20% |
| REIT | 15–30x (P/FFO) | 15–25x | 30–60% (NOI margin) | 0–10% |
| S&P 500 average (reference) | ~20x | ~13x | ~12% | ~5% |

**Sanity flag actions**:
- P/E > 100x without growth justification → flag as "extremely high, verify"
- Negative P/E → note "negative earnings, P/E not meaningful"
- Revenue growth > 2× historical average without explanation → flag + re-search
- Margins > 2× sector average → flag as "potential data error or exceptional business model"
- Market cap / Revenue < 0.1x → sanity check (possible data error)
- Market cap / Revenue > 50x → sanity check (extremely high premium)

---

## Section D — Cross-Reference Disagreement Rules

When two independent sources disagree on the same data point:

| Disagreement Level | Action |
|-------------------|--------|
| ≤5% difference | Grade B — use average or primary source value |
| 5–15% difference | Grade C — use primary source; flag discrepancy |
| >15% difference | Grade D unless arithmetic explains the gap — display "—" |
| Sources disagree on direction (positive vs negative) | Grade D — never guess which is right |

**Source hierarchy for disagreement resolution (US)**:
1. SEC filing (10-K, 10-Q, 8-K earnings) — most primary
2. Company earnings press release (IR website)
3. Financial portals (Yahoo Finance, Google Finance)
4. News articles
5. Analyst reports (opinion, not fact)

**Source hierarchy for disagreement resolution (KR)**:
1. DART 전자공시 (공식 재무제표) — most primary
2. 네이버금융 (official aggregation)
3. FnGuide
4. General web search

---

## Section E — Korean Stock Special Rules

1. **DART as primary**: Financial figures from DART override all other sources. DART is the regulatory filing system.

2. **KRW unit consistency**: Revenue/profit figures from DART may be in "억원" (100M KRW) or "백만원" (1M KRW). Always standardize to absolute KRW before calculations. Note the unit explicitly in validated-data.json.

3. **Consolidated vs. separate financials**: Korean companies file both consolidated (연결) and separate (별도) financials. Always use consolidated unless explicitly noted.

4. **Foreign investor ownership (외국인 지분율)**: Available from KIND (kind.krx.co.kr). Note current % and trend (increasing/decreasing vs 6-month average).

5. **DART = Grade A eligible**: DART 재무제표는 한국 금융감독원(FSS) 규제 공시 원본으로, SEC filing과 동등한 권위를 가진다. DART API 또는 DART 웹에서 가져온 공시 데이터는 산술 일관성 확인 시 Grade A. 네이버금융/FnGuide 등 aggregator-only 데이터는 max Grade B.

6. **Korean company name → ticker resolution**: Company name → 6-digit code lookup via 네이버금융 search or KIND. Common examples:
   - 삼성전자 → 005930
   - SK하이닉스 → 000660
   - NAVER → 035420
   - 카카오 → 035720
   - LG에너지솔루션 → 373220
   - 현대차 → 005380
   - 기아 → 000270

7. **밸류업 프로그램**: Note if company has submitted a Value-up (기업가치 제고) plan. Check KIND corporate disclosures. This is relevant for valuation premium/discount assessment.

8. **Earnings announcement format**: Korean companies report "잠정실적" (preliminary) before the formal DART filing. Preliminary figures are Grade C unless confirmed by DART filing.
