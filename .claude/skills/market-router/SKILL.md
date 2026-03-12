# Market Router — SKILL.md

**Role**: Step 2 — Detect MCP availability, determine data mode (Enhanced/Standard), classify company type, identify peers, and write the research plan.
**Triggered by**: CLAUDE.md after Step 1 (query interpretation)
**Reads**: Session state from Step 1, `references/company-type-classification.md`
**Writes**: `output/research-plan.json`
**References**: `company-type-classification.md`

---

## Instructions

### Step 2.1 — MCP Availability Detection

**Always perform this check at session start** (cached for the session — do not repeat per ticker).

Test call:
```
get_current_stock_price("AAPL")
```

| Result | Decision |
|--------|----------|
| Valid price returned | Enhanced Mode available |
| Error / timeout | Retry once after 2 seconds |
| Second failure | Standard Mode (web-only) |
| Korean stock (any market) | Always Standard Mode regardless of MCP |

**Korean stocks are ALWAYS Standard Mode** — Financial Datasets MCP does not support KRX.

Cache the result as session variable: `DATA_MODE = "enhanced" | "standard"`

Log:
```
MCP check: get_current_stock_price("AAPL") → {result}
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
- Listed on accessible market (US: NYSE/NASDAQ/AMEX; KR: KOSPI/KOSDAQ)
- Max 5 peers

### Step 2.4 — Plan Tier 1 API Calls (Enhanced Mode Only)

Based on output_mode and company_type, select which API calls to make in Step 3:

| Output Mode | API Bundle |
|-------------|-----------|
| Mode B, C, D | Full standard bundle (10 calls) |

From `api-endpoints.md`:
- Full bundle: income_statements, balance_sheets, cash_flow_statements, current_price, historical_prices, financial_metrics, analyst_estimates, company_news, sec_filings, insider_trades
- Minimum bundle: current_price, financial_metrics, analyst_estimates, company_news(limit=5)

FMP calls (if available):
- `price_target_summary`, `grades_summary`, `historical_grades` (for Mode C/D Section 7)

### Step 2.5 — Plan Tier 2 Web Searches

From `us-data-sources.md` (US) or `kr-data-sources.md` (KR), select searches:

**Standard Mode — US** (8 searches minimum):
1. `"{ticker}" stock price market cap current`
2. `"{ticker}" latest quarterly earnings revenue EPS 2026`
3. `"{ticker}" P/E EV/EBITDA financial ratios`
4. `"{ticker}" 10-Q SEC EDGAR financial statements`
5. `"{ticker}" analyst price target consensus buy hold sell`
6. `"{ticker}" news catalyst 2026`
7. `"{ticker}" competitors sector comparison`
8. `"{ticker}" insider trading executives` (Mode C/D only)

**Enhanced Mode — qualitative supplement** (4 searches):
1. `"{ticker}" earnings call transcript guidance 2026`
2. `"{company}" industry trends competitive landscape 2026`
3. `"{ticker}" recent news developments last 90 days`
4. `"{ticker}" vs competitors {peer1} {peer2}`

**Standard Mode — KR** (see `kr-data-sources.md` for full 8-query list)

### Step 2.6 — Write Research Plan

Write to `output/research-plan.json`:

```json
{
  "ticker": "AAPL",
  "market": "US",
  "data_mode": "enhanced",
  "company_type": "Technology/Platform",
  "company_type_confidence": "HIGH",
  "output_mode": "C",
  "output_language": "en",
  "analysis_date": "2026-03-12",
  "peer_tickers": ["MSFT", "GOOGL", "META", "AMZN"],
  "analysis_framework_path": "references/analysis-framework-dashboard.md",
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
    "\"AAPL\" latest quarterly earnings revenue EPS 2026",
    "\"AAPL\" P/E EV/EBITDA financial ratios",
    "\"AAPL\" analyst price target consensus buy hold sell",
    "\"AAPL\" news catalyst 2026",
    "\"AAPL\" earnings call transcript guidance 2026",
    "\"AAPL\" recent news developments last 90 days"
  ],
  "tier2_fetches": [
    "https://finance.yahoo.com/quote/AAPL/"
  ]
}
```

**Multi-ticker Workflow 2**: Write separate research plan per ticker using `output/data/{ticker}/research-plan.json` namespace. Do NOT overwrite the shared `output/research-plan.json` for multi-ticker scenarios.

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

→ Proceeding to Step 3 (Financial Data Collector) [Enhanced] or Step 4 (Web Researcher) [Standard]
```

---

## Completion Check

- [ ] MCP availability confirmed (or retrieved from session cache)
- [ ] Korean stock correctly routed to Standard Mode
- [ ] Company type classified with confidence level
- [ ] 3–5 peer tickers identified
- [ ] Tier 1 API call list selected based on output_mode
- [ ] Tier 2 search list built (≥5 searches for Standard Mode)
- [ ] `output/research-plan.json` written (or per-ticker path for Workflow 2)
- [ ] Analysis framework path set correctly for output_mode
