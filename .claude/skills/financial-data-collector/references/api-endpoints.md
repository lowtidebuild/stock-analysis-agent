# API Endpoints Reference

This file defines all Financial Datasets MCP and FMP MCP endpoints used in Enhanced Mode (Step 3).

---

## Financial Datasets MCP — Standard Call Bundle

This is the default set of calls for every US stock in Enhanced Mode. Estimated cost: ~$0.28/stock.

| Function | Key Parameters | Data Returned | Cost | Freshness |
|----------|---------------|---------------|------|-----------|
| `get_income_statements` | ticker, period="quarterly", limit=8 | Revenue, gross profit, operating income, net income, EPS (diluted), shares | ~$0.04 | Quarterly (post-filing) |
| `get_balance_sheets` | ticker, period="quarterly", limit=8 | Total assets, total debt (short+long), cash & equivalents, equity, shares outstanding | ~$0.04 | Quarterly |
| `get_cash_flow_statements` | ticker, period="quarterly", limit=8 | Operating CF, capex, FCF, debt repayments, share buybacks | ~$0.04 | Quarterly |
| `get_current_stock_price` | ticker | Current price, volume, day change, day change % | ~$0.01 | Real-time |
| `get_historical_stock_prices` | ticker, start=1Y ago, end=today | Daily OHLCV data for charting | ~$0.05 | Daily |
| `get_financial_metrics` | ticker | 50+ pre-calculated ratios: P/E, EV/EBITDA, P/B, ROE, ROA, debt/equity, current ratio | ~$0.03 | Weekly |
| `get_analyst_estimates` | ticker | Consensus EPS estimates for next 1-4 quarters and next 1-2 years; revenue estimates | ~$0.03 | Weekly |
| `get_company_news` | ticker, limit=20 | Title, URL, publish date, sentiment, summary | ~$0.02 | Daily |
| `get_sec_filings` | ticker, filing_type="10-K,10-Q" | Latest annual and quarterly filings with URLs and period of report | ~$0.01 | As filed |
| `get_insider_trades` | ticker, limit=20 | Name, title, transaction type, shares, price, date | ~$0.01 | As reported |

**Total standard bundle cost**: ~$0.28/stock

### Data Returned — Key Fields to Extract

**From `get_income_statements`** (most recent 8 quarters):
```
Quarter label (e.g., "Q2 2026"), revenue, gross_profit, operating_income,
net_income, eps_diluted, shares_diluted, gross_margin_pct, operating_margin_pct
```

**From `get_balance_sheets`** (most recent 8 quarters):
```
Quarter label, total_assets, total_debt (= short_term_debt + long_term_debt),
cash_and_equivalents, total_equity, shares_diluted
Net Debt = total_debt - cash_and_equivalents
```

**From `get_cash_flow_statements`** (most recent 8 quarters):
```
Quarter label, operating_cashflow, capital_expenditure,
FCF = operating_cashflow - capital_expenditure (calculate this),
debt_repayment, share_repurchase, dividends_paid
TTM FCF = sum of last 4 quarters FCF
```

**From `get_financial_metrics`**:
```
pe_ratio, ev_ebitda, price_to_book, roe, roa, debt_to_equity,
current_ratio, dividend_yield, enterprise_value, market_cap,
ebitda_ttm, revenue_ttm, gross_margin, operating_margin, net_margin
```

---

## Minimum Viable Call Bundle (Mode B)

For quicker analysis where full depth not needed. Estimated cost: ~$0.05/stock.

| Function | Purpose |
|----------|---------|
| `get_current_stock_price` | Price, change |
| `get_financial_metrics` | Core ratios (P/E, EV/EBITDA, margins) |
| `get_analyst_estimates` | Consensus EPS |
| `get_company_news` limit=5 | Recent news |

---

## FMP MCP — Analyst Data Bundle (Optional)

These calls are only made if FMP MCP is configured. They supplement analyst data not available in Financial Datasets.

| Function/Endpoint | Data Returned | Use |
|------------------|---------------|-----|
| Price Target Summary | Consensus price target (avg, high, low), # analysts covering | Section 7 of dashboard |
| Grades Summary | BUY/HOLD/SELL/STRONG BUY/STRONG SELL distribution | Section 7 |
| Historical Grades | Individual analyst actions with name, firm, rating change, target change, date | Section 7 (full detail) |

**If FMP not available**: Use web search `"{ticker} analyst price target consensus site:tipranks.com OR site:marketbeat.com` for analyst data. Tag as `[Web]`.

---

## MCP Call Execution Rules

1. **Execute all standard bundle calls** before proceeding to Step 4 (web research)
2. **Retry failed calls**: Retry each failed call exactly 2 times with different parameters if applicable. If still failing on 3rd attempt, log as unavailable and continue.
3. **Log format**: For each failed call: `"FAILED: get_income_statements — Error: {message} — Proceeding without"`
4. **Data sufficiency check**: After all calls complete, verify:
   - Revenue data available for ≥4 quarters? → sufficient for TTM calculations
   - Current price available? → if not, this is critical — stop and retry or switch to Standard Mode
   - Key metrics available? → if not, fall back to web for those specific gaps
5. **Output**: Write ALL retrieved data to `output/data/{ticker}/tier1-raw.json`

---

## Ticker Validation via API

Before running the full bundle, validate the ticker exists:
1. Call `get_current_stock_price(ticker)` as the first call
2. If it returns a valid price → ticker is valid, continue
3. If it returns an error or empty → ticker may be invalid; ask user to confirm or web search to find correct ticker

---

## Data Output Format

Write to `output/data/{ticker}/tier1-raw.json`:
```json
{
  "ticker": "AAPL",
  "collection_timestamp": "2026-03-12T14:30:00Z",
  "data_source": "financial-datasets-mcp",
  "api_calls_succeeded": ["get_income_statements", "get_balance_sheets", ...],
  "api_calls_failed": [],
  "income_statements": [...],
  "balance_sheets": [...],
  "cash_flow_statements": [...],
  "current_price": {...},
  "historical_prices": [...],
  "financial_metrics": {...},
  "analyst_estimates": {...},
  "company_news": [...],
  "sec_filings": [...],
  "insider_trades": [...],
  "fmp_price_target": {...},
  "fmp_grades_summary": {...},
  "fmp_grade_history": [...]
}
```
