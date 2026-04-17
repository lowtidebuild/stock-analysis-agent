# Analysis Framework — Mode B (Peer Comparison)

This file defines the analytical requirements for Mode B output. The Analyst agent reads this file when `output_mode = "B"`.

---

## Purpose & Scope

Mode B produces a comparative analysis of 2–5 peer companies side-by-side. The output is an HTML file showing a structured matrix with relative valuations, R/R Score rankings, and a reasoned Best Pick recommendation.

**Output target**: HTML file, 800–1,200 words of narrative
**Output format**: HTML file (see `mode-b-template.md`)
**Output path**: `output/reports/{tickers}_B_{lang}_{YYYY-MM-DD}.html`
**Template**: `.claude/skills/output-generator/references/mode-b-template.md`

---

## Required Inputs

- `output/runs/{run_id}/{ticker}/validated-data.json` for EACH ticker in the comparison
- Current price for each ticker (Grade D price → exclude from ranking, note in output)
- Company type identified for each ticker

---

## Step-by-Step Analytical Process

### Step 1 — Per-Ticker Mini-Analysis

For each ticker, perform a condensed mini-analysis:

1. Select 5–8 key metrics (choose consistent metrics across all peers for comparability)
2. Build 3 scenarios with company-specific assumptions
3. Calculate R/R Score
4. Write Q1 + Q2 Variant View (2 questions, not 5)

**Variant View for Mode B**: Only Q1 and Q2 required per ticker

- Q1 (1–2 sentences): Market consensus vs. analyst disagreement for this specific company
- Q2 (1 sentence): Primary catalyst that would validate or invalidate the thesis

**Consistency requirement**: Use the same metric set for all peers. If one peer lacks data for a metric, show "—" for that peer (do not substitute a different metric).

### Step 2 — Build the Comparison Matrix

**Column structure**: Metric | Ticker1 | Ticker2 | Ticker3 | Winner

**Metric categories** (use all applicable, skip if all peers have Grade D):
1. Price & Size (current price, market cap)
2. Valuation (P/E, EV/EBITDA, P/B)
3. Growth (Revenue Growth YoY, EPS Growth YoY)
4. Profitability (Gross Margin, Operating Margin, FCF Yield, ROE)
5. Balance Sheet (Net Debt/EBITDA, Dividend Yield)
6. R/R Score (bottom row, highlighted)
7. Verdict (bottom row, color-coded)

**Winner column rules**:
- Valuation metrics (lower = better): P/E, EV/EBITDA, P/B, Net Debt/EBITDA → lowest value wins
- Growth/profitability metrics (higher = better): Revenue Growth, Margins, FCF Yield, ROE → highest value wins
- If only one peer has a valid value for a metric → no winner declared for that row
- R/R Score: highest value wins

### Step 3 — Relative Valuation Assessment

For each valuation metric (P/E, EV/EBITDA):
1. Identify the cheapest peer (lowest multiple)
2. Calculate premium/discount of others vs. cheapest:
   `Premium = (Peer_Multiple - Cheapest_Multiple) / Cheapest_Multiple × 100%`
3. Assess whether the premium/discount is justified:
   - Justified if: higher growth rate, structurally higher margins, superior FCF conversion, unique competitive position
   - Unjustified if: premium exists without corresponding financial advantage
   - Inconclusive if: insufficient data

**Justification must cite specific numbers** — not general quality statements.

Example:
- FAIL: "MSFT deserves a premium to GOOGL because it has better enterprise relationships"
- PASS: "MSFT trades at 32x EV/EBITDA vs. GOOGL at 22x — a 45% premium justified in part by Azure's 29% growth [Filing] vs. GCP's 22% [Portal], and MSFT's 20% higher operating margin. The remaining premium (~10x turns) requires sustaining current Copilot adoption rates."

### Step 4 — R/R Score Ranking

Rank all peers by R/R Score (highest to lowest). For each rank:
1. State the R/R Score and interpretation (Attractive/Neutral/Unfavorable)
2. Write 1–2 sentence rationale explaining why this peer ranks here
3. The rationale MUST be company-specific (not just "higher R/R Score means better value")

Format:
```
#1: {TICKER} — R/R {score} (Attractive)
{Company-specific reason for top ranking — cite specific metric advantage or catalyst}

#2: {TICKER} — R/R {score} (Neutral)
{Reason — cite specific limitation vs. #1}
```

### Step 5 — Best Pick Recommendation

**When to give a Best Pick**:
- At least one peer has R/R > 1.5
- Sufficient data available (not all tickers are Grade C or below)

**When to decline Best Pick**:
- All peers have R/R < 1.0 → State: "No clear Best Pick — all peers appear overvalued at current prices"
- Data quality too low (all Grade C or D) → State: "Insufficient data quality for a recommendation"

**Best Pick requirements**:
1. Must explicitly state it is an **opinion**
2. Must cite ≥2 specific metrics or data points supporting the choice
3. Must acknowledge the primary risk to the pick
4. Must compare to at least one other peer (why this one vs. others)

Example:
- FAIL: "AAPL is the best pick due to its strong brand and ecosystem"
- PASS: "AAPL is the preferred pick at current prices. At 28x P/E vs. MSFT's 35x, AAPL offers better valuation with comparable FCF yield (3.8% vs. 3.2% [Filing]), and iPhone services revenue growing 15% YoY provides more visible earnings than GOOGL's ad-cyclical revenue. Primary risk: China revenue (18% of total [Filing]) faces regulatory pressure. This is an opinion — not a buy recommendation."

### Step 6 — Key Differentiators

Identify 2–3 fundamental differences that explain divergent valuations or risk profiles:

Rules:
- Each must include specific numbers from ≥2 peers
- Must be genuinely distinct (not restating the same point)
- Must explain *why* the difference matters for valuation

Example differentiators:
1. "Margin structure: MSFT's software-heavy model generates 45% operating margins vs. GOOGL's 32% [Filing] — this ~13pp gap implies ~$40B/year in additional free cash flow at similar revenue"
2. "Capital return: AAPL returned $90B via buybacks in FY2025 (6% of market cap [Filing]) vs. MSFT's $25B (1.1%) — AAPL's buyback yield provides structural EPS support at current valuation"
3. "Growth quality: GOOGL's 15% revenue growth [Portal] is primarily ad-driven (cyclical) vs. MSFT's 17% [Filing] which is 60% recurring enterprise contract revenue (defensive)"

---

## Multi-Ticker Data Management

For Workflow 2 (peer comparison), each ticker's validated data is stored separately:
- `output/runs/{run_id}/{ticker}/validated-data.json`

Do NOT use a shared `output/validated-data.json` for multi-ticker analysis (prevents collision). Use run-local or per-ticker namespaced artifacts only.

If a ticker was analyzed in the same session (session context):
- Re-use the validated data already in memory — do not re-collect
- Note: "Using session-cached data for {TICKER}"

If data is stale (> analysis_date freshness threshold):
- Flag: "Data for {TICKER} from {date} — may be stale, re-collect recommended"

---

## Handling Asymmetric Data Quality

When one peer has higher data quality (Enhanced Mode) than others (Standard Mode):

1. Tag each ticker's data mode in the header
2. When drawing comparisons involving higher-grade data, note the advantage: "MSFT data from API [Filing] is higher confidence than GOOGL data from web (Grade C, single source)"
3. Do NOT elevate the confidence of lower-grade data when comparing
4. If a metric is Grade A for one peer but Grade C for another: in the winner column, add a note like "Winner: {TICKER} [higher confidence data]"

---

## Source Tagging in Mode B

All metric values in the comparison table must have source tags. Apply tags in the Metric header cell:

`P/E (TTM) [Grade B]` — means the P/E values across the table all come from cross-referenced sources (2+ sources agree)

If different peers have different source grades for the same metric, apply the lowest grade to the column header and note the per-ticker grades in a footnote.

---

## Completion Check

Before generating the HTML file:
- [ ] All tickers have validated data loaded
- [ ] Same metric set applied to all peers (no substitutions)
- [ ] Winner column correctly identifies low (valuation) vs. high (growth/quality) winners
- [ ] Premium/discount calculations verified arithmetically
- [ ] R/R Score computed with formula for each peer
- [ ] R/R ranking has company-specific rationale for each position
- [ ] Best Pick explicitly labeled as opinion
- [ ] Key Differentiators have ≥2 specific numbers each
- [ ] All metric values in table have source tags
- [ ] Disclaimer present
- [ ] HTML file saved to correct path
