# Analysis Framework — Mode A (Quick Brief)

This file defines the analytical requirements for Mode A output. The Analyst agent reads this file and applies it when `output_mode = "A"`.

---

## Purpose & Scope

Mode A is a concise, inline analysis delivered directly in chat. It prioritizes speed and actionability over depth. A user requesting Mode A wants a quick, trustworthy read in under 3 minutes.

**Output target**: 300–500 words total in chat
**Output format**: Inline markdown (no separate file)
**Template**: `.claude/skills/output-generator/references/mode-a-template.md`

---

## Required Inputs

Before analysis begins, verify these inputs are available:
- `output/validated-data.json` — validated metrics with confidence grades
- `output/data/{ticker}/tier1-raw.json` OR `output/data/{ticker}/tier2-raw.json` — raw data
- Current price (Grade D on price → critical failure, switch to Standard Mode or ask user)

---

## Step-by-Step Analytical Process

### Step 1 — Select 5 Key Metrics

Identify company type from `company-type-classification.md`. Select the 5 most relevant metrics:

| Company Type | Primary 5 Metrics |
|-------------|-------------------|
| Technology/Platform | P/E, EV/EBITDA, Revenue Growth YoY, Operating Margin, FCF Yield |
| Industrial/Manufacturing | EV/EBITDA, Operating Margin, FCF Yield, Net Debt/EBITDA, Revenue Growth |
| Financial/Banking | P/B, ROE, Net Interest Margin, Dividend Yield, Non-performing Loan Ratio |
| Biotech/Pharma (pre-profit) | EV/Revenue, Cash Runway (months), Pipeline Stage Count, R&D% Revenue, Clinical Success Rate |
| Consumer/Retail | EV/EBITDA, Same-Store Sales Growth, Gross Margin, Revenue Growth YoY, Dividend Yield |
| Energy | EV/EBITDA, FCF Yield, Net Debt/EBITDA, Dividend Yield, Production Growth |

Only include metrics with Grade A, B, or C confidence. Grade D metrics: exclude from table, note at bottom.

### Step 2 — Build 3 Scenarios

Requirements for each scenario:
1. **Key assumption must be company-specific** — not generic market assumptions
2. Price target must be derived from a named method (P/E multiple expansion, EV/EBITDA target, DCF, peer multiple)
3. Return % calculated from current price
4. Probabilities must sum to 100%

Example of acceptable vs. unacceptable assumptions:

| | Assumption Quality |
|-|---------------------|
| FAIL | "Macroeconomic conditions improve and company grows revenue" |
| FAIL | "Management executes well on strategy" |
| PASS | "AWS-equivalent margins (30%+) achieved in Azure Arc by Q4 2026, re-rating to 32x EV/EBITDA" |
| PASS | "iPhone 17 supercycle drives 8% unit volume growth; services attach rate reaches 82%" |

### Step 3 — Calculate R/R Score

```
R/R Score = (Bull_return% × Bull_prob + Base_return% × Base_prob) / |Bear_return% × Bear_prob|
```

Where probabilities are expressed as decimals (0.40, not 40%).

Interpretation:
- > 3.0 → Attractive
- 1.0–3.0 → Neutral
- < 1.0 → Unfavorable

If R/R < 0 (negative base and bull returns) → R/R Score = "N/A — Structural Bear"

### Step 4 — Write Variant View (1–2 sentences)

**This is the most important analytical output. Apply maximum rigor.**

Requirements:
1. First state what the **market currently believes** (be specific — what multiple or growth rate is implied?)
2. Then state the **specific disagreement** with supporting evidence
3. Must include **≥1 company-specific data point** (earnings figure, backlog, product metric, etc.)

**Quality gate**: Mentally replace the company name with its #1 competitor. If the sentence is still true → FAIL. Rewrite.

Example failures:
- "The market is underpricing the company's AI potential" → FAIL (generic)
- "Despite strong fundamentals, the stock is undervalued relative to peers" → FAIL (generic)

Example passes:
- "Consensus models NVDA's Data Center segment at 40% growth, but Q3 H100 order backlog of $11B implies >60% growth through Q2 2026, suggesting significant EPS upside not in consensus [1S]" → PASS
- "Market prices 삼성전자 at 1.1x PBR assuming ongoing HBM3 yield issues, but NAND ASP recovery of 15% QoQ in Q4 suggests margin floor is higher than feared [KR-Web]" → PASS

### Step 5 — Identify Top Risk

Requirements:
1. State the risk title
2. Describe the **mechanism**: how does this risk translate to stock price decline? (Step-by-step causal chain)
3. Include at least one number (impact estimate, revenue at risk, multiple compression estimate)

Example:
- FAIL: "Competition risk from Amazon"
- PASS: "AWS direct-sales expansion in enterprise storage: Amazon's $2B investment in enterprise SAN-equivalent services could displace 15-20% of {ticker}'s enterprise storage revenue ($X.XB of $X.XB TTM) within 24 months, compressing EV/Revenue from 8x to 5x at current growth rates"

### Step 6 — State Verdict

One of: **Overweight / Underweight / Neutral / Watch**

- Overweight: R/R > 2.0 AND base case return > 15% AND no critical structural risk
- Underweight: R/R < 1.0 OR base case return negative
- Watch: Insufficient data (Standard Mode, max Grade B), or thesis pending catalyst
- Neutral: All other cases

Korean verdicts: 비중확대 / 비중축소 / 중립 / 관찰

---

## Source Tagging Rules

Every value in the 5 metrics table MUST have a tag:
- `[API]` — from Financial Datasets MCP
- `[FMP]` — from FMP MCP
- `[DART]` — from DART filing
- `[네이버]` — from 네이버금융
- `[Web]` — from web search
- `[Calculated]` — computed from tagged inputs
- `[≈]` — cross-referenced, 2 sources within 5%
- `[1S]` — single source, unverified

Grade assignment per metric follows `confidence-grading.md`.

---

## Completion Check

Before outputting Mode A response:
- [ ] 5 metrics selected based on company type
- [ ] All metrics have source tags and confidence grades
- [ ] Grade D metrics excluded (noted at bottom if any excluded)
- [ ] 3 scenarios with company-specific assumptions
- [ ] Scenario probabilities sum to 100%
- [ ] R/R Score calculated with formula shown
- [ ] Variant View passes the "competitor replacement test"
- [ ] Top Risk includes mechanism + numbers
- [ ] Verdict consistent with R/R Score
- [ ] Disclaimer present
