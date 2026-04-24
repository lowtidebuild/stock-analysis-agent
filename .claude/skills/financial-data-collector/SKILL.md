# Financial Data Collector — SKILL.md

**Role**: Step 3 — Execute Financial Datasets MCP and FMP MCP API calls to collect structured financial data. Enhanced Mode only.
**Triggered by**: CLAUDE.md when `data_mode = "enhanced"` after Step 2
**Reads**: run-local `research-plan.json`, `references/api-endpoints.md`
**Writes**: `output/data/{ticker}/tier1-raw.json`
**References**: `api-endpoints.md`

---

## Instructions

### Step 3.1 — Validate Ticker

Before running the full bundle, validate the ticker exists:

```
Call: get_current_stock_price("{ticker}")

IF valid price returned:
    → Ticker valid. Proceed to Step 3.2.
    → Cache: current_price = {price}, day_change = {change}, timestamp = {now}

IF error or empty result:
    → Retry once with slight delay
    → If still failing: "ERROR: {ticker} not found via API. Attempting web verification..."
    → Web search: "{ticker} stock NYSE NASDAQ" to confirm ticker
    → If ticker confirmed wrong: ask user to verify
    → If API down: switch to Standard Mode for this session
```

### Step 3.2 — Execute Standard Bundle

Execute calls in this order. For **each call**:
- On success: store result in memory
- On failure: retry up to 2 times with same parameters
- On 3rd failure: log `"FAILED: {function_name} — Error: {message} — Proceeding without"` and continue

**Full standard bundle** (from `api-endpoints.md`):

```
1. get_current_stock_price(ticker)
2. get_income_statements(ticker, period="quarterly", limit=8)
3. get_balance_sheets(ticker, period="quarterly", limit=8)
4. get_cash_flow_statements(ticker, period="quarterly", limit=8)
5. get_financial_metrics(ticker)
6. get_analyst_estimates(ticker)
7. get_historical_stock_prices(ticker, start="{1Y ago}", end="{today}")
8. get_company_news(ticker, limit=20)
9. get_sec_filings(ticker, filing_type="10-K,10-Q")
10. get_insider_trades(ticker, limit=20)
```

**Minimum bundle** (Mode A/B, or if time-constrained):
```
1. get_current_stock_price(ticker)
2. get_financial_metrics(ticker)
3. get_analyst_estimates(ticker)
4. get_company_news(ticker, limit=5)
```

### Step 3.3 — FMP MCP Calls (if available)

After Financial Datasets bundle, check if FMP MCP is configured:

```
Test: price_target_summary(ticker)

IF succeeds:
    → Also call: grades_summary(ticker), historical_grades(ticker, limit=10)

IF fails:
    → Log: "FMP MCP not available — analyst data will be sourced from web"
    → Set fmp_available = false (will trigger web search for analyst targets in Step 4)
```

### Step 3.3.5 — yfinance Supplement (Enhanced Mode)

After Financial Datasets + FMP, check whether any critical fields are still missing:
- `current_price`
- `market_cap`
- `pe_ratio`
- `fifty_two_week_high`
- `fifty_two_week_low`

If any are missing, run:

```bash
python .claude/skills/financial-data-collector/scripts/yfinance-collector.py \
  --ticker {ticker} \
  --market US \
  --output output/data/{ticker}/yfinance-raw.json \
  --bundle minimum
```

If `yfinance-collector.py` exits `0` or `1`:
- Read `output/data/{ticker}/yfinance-raw.json`
- Merge it into `tier1-raw.json` under `yfinance_supplement`
- Fill missing values only — do not overwrite existing Grade A fields
- Tag merged values `[Portal]`
- If yfinance agrees with existing Grade A values within 2% → Grade B
- If yfinance is the only available structured value → Grade C

If Financial Datasets MCP completely fails but yfinance succeeds:
- Keep `data_mode = "enhanced"` (structured fallback still succeeded)
- Set `data_source = "yfinance"`
- Continue the pipeline without downgrading to Standard Mode

### Step 3.4 — Data Sufficiency Check

After all calls complete, verify:

| Check | Criteria | Action if Failing |
|-------|----------|-------------------|
| Revenue data | ≥4 quarters available | Log warning, note limited TTM accuracy |
| Current price | Must be present | CRITICAL — switch to Standard Mode if unavailable |
| Key metrics | P/E, EV/EBITDA, Margins | Log missing metrics for Step 5 web gap-fill |
| Historical prices | ≥90 days | Chart will be degraded; note in output |
| Income statements | ≥4 quarters | Log; TTM calculations will use fewer periods |

```
IF current_price unavailable (critical failure):
    → If yfinance supplement succeeded: keep `data_mode = "enhanced"` and continue
    → Otherwise: "CRITICAL: Price data unavailable. Switching to Standard Mode for {ticker}."
    → Switch data_mode to "standard" for this ticker
    → Proceed to Step 4 (web researcher) to get price

IF revenue_data < 4 quarters:
    → "WARN: Only {N} quarters of income statement data available. TTM calculations may be less accurate."
    → Continue with available data
```

### Step 3.5 — Extract Key Fields

From the collected data, extract and compute these key fields for `tier1-raw.json`:

**From income_statements** (most recent 4 quarters for TTM):
- Revenue TTM = sum of last 4 quarters revenue
- Net Income TTM = sum of last 4 quarters net_income
- Operating Income TTM = sum of last 4 quarters operating_income
- Gross Profit TTM = sum of last 4 quarters gross_profit
- EPS Diluted TTM = sum of last 4 quarters eps_diluted (or Net Income TTM / diluted_shares)
- Diluted Shares = most recent quarter diluted_shares

**From balance_sheets** (most recent quarter):
- Total Debt = short_term_debt + long_term_debt
- Cash and Equivalents
- Total Assets
- Total Equity

**From cash_flow_statements** (most recent 4 quarters for TTM):
- Operating CF TTM = sum of last 4 quarters operating_cashflow
- Preserve source CapEx as `capex_raw`
- Normalize CapEx outflow to positive `capex_outflow_abs`
- Set `capital_expenditure = capex_outflow_abs` for downstream calculations
- FCF TTM = Operating CF TTM - CapEx TTM
- If source-provided FCF conflicts with calculated FCF, record the conflict instead of silently overwriting

**From financial_metrics**:
- P/E, EV/EBITDA, P/B, ROE, ROA, Current Ratio
- Market Cap, Enterprise Value
- Dividend Yield
- EBITDA TTM, Revenue TTM (for cross-check)

### Step 3.6 — Write tier1-raw.json

Write all collected data to `output/data/{ticker}/tier1-raw.json`:

```json
{
  "ticker": "AAPL",
  "collection_timestamp": "2026-03-12T14:30:00Z",
  "data_source": "financial-datasets-mcp",
  "api_calls_succeeded": ["get_current_stock_price", "get_income_statements", ...],
  "api_calls_failed": [],
  "fmp_available": true,
  "income_statements": [...],
  "balance_sheets": [...],
  "cash_flow_statements": [...],
  "current_price": {"price": 175.50, "change": 1.25, "change_pct": 0.72},
  "historical_prices": [...],
  "financial_metrics": {...},
  "analyst_estimates": {...},
  "company_news": [...],
  "sec_filings": [...],
  "insider_trades": [...],
  "fmp_price_target": {...},
  "fmp_grades_summary": {...},
  "fmp_grade_history": [...],
  "derived_ttm": {
    "revenue_ttm": 395000,
    "net_income_ttm": 97000,
    "operating_income_ttm": 118000,
    "gross_profit_ttm": 180000,
    "fcf_ttm": 110000,
    "eps_ttm": 6.27,
    "diluted_shares": 15500
  }
}
```

### Step 3.7 — Log API Call Results

Print a brief summary before proceeding to Step 4:

```
=== Tier 1 Data Collection: {TICKER} ===
Succeeded: {N} calls
Failed: {list of failed calls or "none"}
Key data available: Price ✓/✗, Revenue ({N}Q) ✓/✗, Metrics ✓/✗
FMP: ✓/✗

→ Proceeding to Step 4 (Web Researcher)
```

---

## Fallback — Python Script Unavailable

If MCP tools are temporarily unavailable but Python environment works, do NOT use Python to call MCPs — MCPs are Claude tool calls, not Python libraries.

If all API calls fail:
1. Log: `"Enhanced Mode API calls all failed — attempting yfinance fallback"`
2. Run:
   `python .claude/skills/financial-data-collector/scripts/yfinance-collector.py --ticker {ticker} --market US --output output/data/{ticker}/yfinance-raw.json --bundle standard`
3. If yfinance succeeds:
   `data_source = "yfinance"` and `data_mode = "enhanced"`
   proceed without a Standard Mode downgrade
4. If yfinance also fails:
   log `"Enhanced Mode structured fallbacks exhausted — falling back to Standard Mode"`
5. Switch `data_mode = "standard"` for this ticker
6. Proceed to Step 4 (web researcher) with Standard Mode protocol

---

## Completion Check

- [ ] Ticker validated via `get_current_stock_price`
- [ ] All standard bundle calls attempted (10 calls or minimum bundle)
- [ ] Failed calls logged individually
- [ ] FMP calls attempted (if FMP configured)
- [ ] Data sufficiency check completed
- [ ] TTM values computed from quarterly data
- [ ] `output/data/{ticker}/tier1-raw.json` written
- [ ] Summary log printed
- [ ] Current price available (critical — halts if missing)
