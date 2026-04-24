# Market Router — SKILL.md

**Role**: Step 2 — Detect MCP availability, determine data mode (Enhanced/Standard), classify company type, identify peers, initialize a run-local artifact root, and write the research plan.
**Triggered by**: CLAUDE.md after Step 1 (query interpretation)
**Reads**: Session state from Step 1, `references/company-type-classification.md`
**Writes**: `output/runs/{run_id}/{ticker}/research-plan.json`
**References**: `company-type-classification.md`

---

## Instructions

### Step 2.1 — MCP Availability Detection

**Always perform this check at session start** (cached for the session — do not repeat per ticker).

Test call:
```
get_current_stock_price("<TICKER>")
```

| Result | Decision |
|--------|----------|
| Valid price returned | Enhanced Mode available |
| Error / timeout | Retry once after 2 seconds |
| Second failure | Standard Mode (yfinance + targeted web) |
| Korean stock (any market) | Always Standard Mode regardless of MCP |

**Korean stocks are ALWAYS Standard Mode** — Financial Datasets MCP does not support KRX.

Cache the result as session variable: `DATA_MODE = "enhanced" | "standard"`

Log:
```
MCP check: get_current_stock_price("<TICKER>") -> {result}
DATA_MODE: {enhanced/standard}
```

### Step 2.2 — Company Type Classification

Read `company-type-classification.md`. Classify based on:
1. Ticker/company name lookup (known companies)
2. Sector from API (`get_financial_metrics` sector field, Enhanced Mode only)
3. Web search: `"{ticker}" sector industry classification site:finance.yahoo.com`
4. Keyword matching in company name

Multi-segment rule: if company has 2+ segments with different economics (e.g., cloud + hardware, banking + insurance), classify as the **primary revenue segment** type, then note the secondary type.

Output classification with confidence:
- HIGH: ticker found in known list or API sector confirmed
- MEDIUM: inferred from keywords or partial data
- LOW: unknown, using "Other" as fallback

### Step 2.3 — Peer Identification

Identify 3–5 most relevant peer tickers for comparison (used in dashboard peer section):

**Enhanced Mode**: Use sector from `get_financial_metrics` + search `"{ticker}" peers competitors sector`

**Standard Mode**: Search `"{ticker}" competitors peers {sector}` → extract ticker symbols from results

**Korean stocks**: Search `"{company}" 동종업계 경쟁사` → map Korean names to 6-digit codes

Peer selection criteria:
- Same sector/sub-industry (not just same broad sector)
- Similar market cap (within 5x of subject company)
- Listed on accessible market (US major exchange; KR: KOSPI/KOSDAQ)
- Max 5 peers

### Step 2.4 — Plan Tier 1 API Calls (Enhanced Mode Only)

Based on output_mode and company_type, select which API calls to make in Step 3:

| Output Mode | API Bundle |
|-------------|-----------|
| Mode A | Minimum bundle (current_price, financial_metrics, company_news limit=5) |
| Mode B, C, D | Full standard bundle (10 calls) |

From `api-endpoints.md`:
- Full bundle: income_statements, balance_sheets, cash_flow_statements, current_price, historical_prices, financial_metrics, analyst_estimates, company_news, sec_filings, insider_trades
- Minimum bundle: current_price, financial_metrics, analyst_estimates, company_news(limit=5)

FMP calls (if available):
- `price_target_summary`, `grades_summary`, `historical_grades` (for Mode C/D Section 7)

### Step 2.5 — Plan Tier 2 Web Searches

From `us-data-sources.md` (US) or `kr-data-sources.md` (KR), select searches:

**Standard Mode — US** (structured first, adaptive search):
1. Plan `yfinance_structured_fetch` before web search.
2. Always plan context searches:
   - `"{ticker}" latest quarterly earnings revenue EPS {YYYY}`
   - `"{ticker}" analyst price target consensus buy hold sell`
   - `"{ticker}" news catalyst {YYYY}`
   - `"{ticker}" competitors sector comparison`
3. Plan Mode C/D-only context search:
   - `"{ticker}" insider trading executives`
4. Mark these as conditional targeted searches, not default searches:
   - `"{ticker}" stock price market cap current` only if yfinance lacks price or market cap
   - `"{ticker}" P/E EV/EBITDA financial ratios` only if yfinance lacks valuation ratios
   - `"{ticker}" 10-Q SEC EDGAR financial statements` only if yfinance lacks EPS/revenue/share inputs

**Enhanced Mode — qualitative supplement** (4 searches):
1. `"{ticker}" earnings call transcript guidance {YYYY}`
2. `"{company}" industry trends competitive landscape {YYYY}`
3. `"{ticker}" recent news developments last 90 days`
4. `"{ticker}" vs competitors {peer1} {peer2}`

**Standard Mode — KR** (see `kr-data-sources.md` for full 8-query list)

### Step 2.5a — Macro Factor Determination (Mode C/D only)

**Condition**: Only execute when `output_mode` is `"C"` or `"D"`. Skip entirely for Mode A and Mode B.

1. Read `company_type` from the Step 2.2 classification result.
2. Look up macro risk factors in `company-type-classification.md` → "Macro Risk Factors by Type" section for the matching `company_type`.
3. Build macro search query using the template:
   ```
   "{sector}" macro risk factors economic outlook {YYYY}
   ```
   Substitute `{sector}` with the company's sector (from classification) and `{YYYY}` with the current year.
4. **Korean stocks overlay**: If `market == "KR"`, also add Korean-specific macro factors:
   - Append to the factor list: `["원/달러 환율", "한국은행 기준금리", "수출입 동향"]`
   - Add an additional search query: `"{sector}" 거시경제 리스크 전망 {YYYY}`
5. Set output fields:
   - `macro_search_required`: `true`
   - `macro_search`: the constructed query string (or list of queries if KR overlay applies)
   - `macro_factors`: list of factor names from the classification lookup (+ KR overlay if applicable)

If `company_type` is not found in the macro factors table, use the sector's closest match or default to `["GDP growth", "interest rates", "inflation"]`.

### Step 2.6 — Write Research Plan

Before writing the research plan, initialize the run-local artifact namespace:

```bash
python .claude/skills/data-manager/scripts/artifact-manager.py init --tickers {ticker}
```

This creates `output/runs/{run_id}/run-manifest.json` and `output/runs/{run_id}/{ticker}/`.

Write to `output/runs/{run_id}/{ticker}/research-plan.json`:

```json
{
  "ticker": "<TICKER>",
  "market": "US",
  "data_mode": "enhanced",
  "company_type": "<COMPANY_TYPE>",
  "company_type_confidence": "HIGH",
  "output_mode": "C",
  "output_language": "en",
  "analysis_date": "<ANALYSIS_DATE>",
  "peer_tickers": ["<PEER_1>", "<PEER_2>", "<PEER_3>", "<PEER_4>"],
  "analysis_framework_path": "references/analysis-framework-dashboard.md",  // Mode A: "references/analysis-framework-briefing.md"
  "tier1_calls": [
    "get_income_statements",
    "get_balance_sheets",
    "get_cash_flow_statements",
    "get_current_stock_price",
    "get_historical_stock_prices",
    "get_financial_metrics",
    "get_analyst_estimates",
    "get_company_news",
    "get_sec_filings",
    "get_insider_trades"
  ],
  "tier1_fmp_calls": ["price_target_summary", "grades_summary", "historical_grades"],
  "tier2_searches": [
    "\"<TICKER>\" latest quarterly earnings revenue EPS <YYYY>",
    "\"<TICKER>\" analyst price target consensus buy hold sell",
    "\"<TICKER>\" news catalyst <YYYY>",
    "\"<TICKER>\" earnings call transcript guidance <YYYY>",
    "\"<TICKER>\" recent news developments last 90 days"
  ],
  "tier2_search_policy": {
    "standard_us_order": "yfinance_structured_fetch_then_missing_field_search",
    "default_context_searches": [
      "earnings",
      "analyst_coverage",
      "news_catalyst",
      "competitors"
    ],
    "conditional_targeted_searches": {
      "price_market_cap": "only_if_missing_after_yfinance",
      "valuation_ratios": "only_if_missing_after_yfinance",
      "sec_filing_financials": "only_if_missing_after_yfinance"
    }
  },
  "tier2_fetches": [
    "<PORTAL_QUOTE_URL>"
  ],
  "macro_search_required": true,
  "macro_search": "\"<SECTOR>\" macro risk factors economic outlook <YYYY>",
  "macro_factors": ["<MACRO_FACTOR_1>", "<MACRO_FACTOR_2>", "<MACRO_FACTOR_3>"],
  "run_context": {
    "run_id": "<RUN_ID>",
    "ticker": "<TICKER>",
    "artifact_root": "output/runs/<RUN_ID>/<TICKER>",
    "reports_dir": "output/reports",
    "compatibility_mirror_enabled": false
  }
}
```

**Multi-ticker Workflow 2**: write separate research plans per ticker using `output/runs/{run_id}/{ticker}/research-plan.json`. Do NOT overwrite a deprecated shared `output/research-plan.json`.

### Step 2.7 — Report Plan Summary

```
=== Research Plan: {TICKER} ===
Data Mode: {Enhanced/Standard}
Company Type: {type} ({confidence})
Output Mode: {mode}
Language: {en/ko}
Peers: {list}
Tier 1 calls: {N} API calls planned
Tier 2 searches: {N} web searches planned
Macro factors: {Yes (N factors) / Skipped (Mode A/B)}

→ Proceeding to Step 3 (Financial Data Collector) [Enhanced] or Step 4 (Web Researcher) [Standard]
```

---

## Completion Check

- [ ] MCP availability confirmed (or retrieved from session cache)
- [ ] Korean stock correctly routed to Standard Mode
- [ ] Company type classified with confidence level
- [ ] 3–5 peer tickers identified
- [ ] Macro factors determined (Mode C/D) or skipped (Mode A/B)
- [ ] Tier 1 API call list selected based on output_mode
- [ ] Tier 2 search policy built (Standard Mode uses yfinance-first adaptive searches)
- [ ] Run-local artifact root initialized
- [ ] `output/runs/{run_id}/{ticker}/research-plan.json` written
- [ ] Analysis framework path set correctly for output_mode
