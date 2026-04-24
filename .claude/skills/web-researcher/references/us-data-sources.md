# US Data Sources Reference

This file defines the priority-ordered list of web sources for US stock research in Standard Mode (Step 4) and Enhanced Mode qualitative supplement.

---

## Standard Mode — Primary Data Sources by Type

### Current Price & Market Cap
| Priority | Source | URL Pattern | Method |
|----------|--------|------------|--------|
| 1 | Yahoo Finance | `https://finance.yahoo.com/quote/{ticker}/` | fetch or search |
| 2 | Google Finance | `https://www.google.com/finance/quote/{ticker}:NASDAQ` | search |
| 3 | MarketWatch | `https://www.marketwatch.com/investing/stock/{ticker}` | fetch |

### Financial Statements (Most Authoritative)
| Priority | Source | Notes | Method |
|----------|--------|-------|--------|
| 1 | SEC EDGAR direct | 10-Q and 10-K filings | fetch direct URL |
| 2 | Macrotrends | Historical financials | fetch or search |
| 3 | WSJ Markets | Clean financial tables | search |

**SEC EDGAR fetch URL patterns**:
- Search for filings: `https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={ticker}&type=10-Q&dateb=&owner=include&count=5`
- For most recent 10-Q: search `{ticker} 10-Q SEC EDGAR {YYYY} site:sec.gov`

### Earnings & Quarterly Results
| Priority | Source | Notes |
|----------|--------|-------|
| 1 | PR Newswire / Business Wire | Company press releases — most authoritative for preliminary earnings |
| 2 | Seeking Alpha earnings page | Analysis + transcript |
| 3 | Earnings Whispers | EPS estimates + actuals |
| 4 | Financial portal earnings tables | Yahoo Finance, Macrotrends |

**Search queries**:
- `"{ticker}" Q{N} {YYYY} earnings results revenue EPS`
- `"{ticker}" quarterly results press release site:prnewswire.com OR site:businesswire.com`

### Analyst Price Targets
| Priority | Source | Notes |
|----------|--------|-------|
| 1 | TipRanks | Individual analyst ratings, targets, track records |
| 2 | MarketBeat | Consensus + individual analyst table |
| 3 | Wall Street Horizon | Forward estimates |
| 4 | Benzinga | Analyst actions |

**Search query**: `"{ticker}" analyst price target {YYYY} site:tipranks.com OR site:marketbeat.com`

### News & Qualitative Context
| Priority | Source | Notes |
|----------|--------|-------|
| 1 | Reuters | Factual, reliable |
| 2 | Bloomberg (public articles) | Depth |
| 3 | Financial Times | Premium analysis |
| 4 | CNBC | Speed |
| 5 | Seeking Alpha | Community analysis (opinion) |

**Search queries**:
- `"{ticker}" news {YYYY} site:reuters.com OR site:ft.com`
- `"{ticker}" recent catalyst developments`

### Insider Trading
| Priority | Source |
|----------|--------|
| 1 | SEC Form 4 filings (EDGAR) |
| 2 | OpenInsider.com |
| 3 | Finviz insider transactions |

---

## Standard Mode — Adaptive Search Policy

Start Standard Mode US collection with the yfinance structured fetch:

```bash
python .claude/skills/financial-data-collector/scripts/yfinance-collector.py \
  --ticker {ticker} \
  --market US \
  --output output/runs/{run_id}/{ticker}/yfinance-raw.json \
  --bundle standard
```

After yfinance, build a missing-field list for:
`price_at_analysis`, `market_cap`, `pe_ratio`, `eps_ttm`, `revenue_ttm`,
`fifty_two_week_high`, and `fifty_two_week_low`.

Run these qualitative/context searches by default:

| Search Query | Priority | Data Obtained |
|-------------|----------|---------------|
| `"{ticker}" latest quarterly earnings revenue EPS {YYYY}` | Critical | Most recent earnings context |
| `"{ticker}" analyst price target consensus buy hold sell` | High | Analyst views |
| `"{ticker}" news catalyst {YYYY}` | High | Qualitative context |
| `"{ticker}" competitors sector comparison` | Medium | Peer context |
| `"{ticker}" insider trading executives` | Medium (Mode C/D only) | Management alignment |

Run these targeted searches only when yfinance leaves the related field missing
or unusable:

| Missing field | Targeted query | Data Obtained |
|---------------|----------------|---------------|
| `price_at_analysis` or `market_cap` | `"{ticker}" stock price market cap current` | Price, market cap |
| `pe_ratio` or `ev_ebitda` | `"{ticker}" P/E EV/EBITDA financial ratios` | Valuation metrics |
| `revenue_ttm`, `eps_ttm`, or `diluted_shares` | `"{ticker}" 10-Q SEC EDGAR financial statements` | Raw financial data |

If yfinance supplies usable price, market cap, and valuation candidates, skip
those targeted searches and keep only the default context searches.

---

## Enhanced Mode — Qualitative Supplement Searches

These 4 searches are added in Enhanced Mode after API data collection:

| # | Search Query | Purpose |
|---|-------------|---------|
| 1 | `"{ticker}" earnings call transcript guidance {YYYY}` | Management outlook, qualitative guidance |
| 2 | `"{company}" industry trends competitive landscape {YYYY}` | Sector context |
| 3 | `"{ticker}" recent news developments last 90 days` | Catalyst monitoring |
| 4 | `"{ticker}" vs competitors {peer1} {peer2}` | Relative positioning |

---

## Source Reliability Tiers

| Tier | Sources | Confidence Grade Eligible |
|------|---------|--------------------------|
| Primary (filing-level) | SEC EDGAR direct fetch, Company IR press releases | Grade A (if arithmetic consistent) |
| Secondary (major portals) | Yahoo Finance, Google Finance, MarketWatch | Grade B (if 2 agree) or Grade C (if 1) |
| Tertiary (analysis sites) | Macrotrends, Seeking Alpha, MarketBeat | Grade C (single source) |
| Opinion sources | Analyst reports, news articles | Not used for facts; used for qualitative context only |

---

## Fetch vs Search Strategy

**Use fetch (direct URL)** when:
- You know the exact URL (SEC EDGAR for a specific company)
- The data is in a predictable URL format
- You need raw financial table data

**Use search** when:
- You need to find the most recent/relevant document
- URL format is unknown
- Searching for news or qualitative content
