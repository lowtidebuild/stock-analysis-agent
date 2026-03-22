# Web Researcher — SKILL.md

**Role**: Step 4 — Collect qualitative context and fill data gaps via web search and direct URL fetch.
**Triggered by**: CLAUDE.md after Step 3 (Enhanced Mode) or Step 2 (Standard Mode)
**Reads**: `output/research-plan.json`, tier2 search list, `references/us-data-sources.md` or `references/kr-data-sources.md`
**Writes**: `output/data/{ticker}/tier2-raw.json`
**References**: `us-data-sources.md`, `kr-data-sources.md`

---

## Instructions

### Step 4.1 — Load Research Plan

Read `output/research-plan.json` (or per-ticker path for Workflow 2).

Extract:
- `market` (US/KR) → determines which source reference file to use
- `data_mode` (enhanced/standard) → determines search scope
- `tier2_searches` — ordered list of searches to execute
- `tier2_fetches` — direct URL fetches

### Step 4.2 — Execute Searches

**MCP Search Tool Priority**:
1. `mcp__tavily__search` (preferred — real-time, structured)
2. `mcp__brave__search` (fallback)
3. `WebSearch` tool (Claude built-in, last resort)
4. `WebFetch` for direct URL access

Execute searches in the order defined in `research-plan.json`. For each search:
- Use the exact query string from the plan (do not paraphrase)
- Collect the top 3–5 results per search
- Extract: title, URL, date, relevant snippet (max 500 chars per result)

### Step 4.3 — Standard Mode US Protocol (8 searches)

Execute ALL 8 searches from `us-data-sources.md` Standard Mode section:

| # | Query Template | Purpose |
|---|----------------|---------|
| 1 | `"{ticker}" stock price market cap current` | Price, market cap |
| 2 | `"{ticker}" latest quarterly earnings revenue EPS 2026` | Recent financials |
| 3 | `"{ticker}" P/E EV/EBITDA financial ratios` | Valuation metrics |
| 4 | `"{ticker}" 10-Q SEC EDGAR financial statements` | Raw financial data |
| 5 | `"{ticker}" analyst price target consensus buy hold sell` | Analyst views |
| 6 | `"{ticker}" news catalyst 2026` | Qualitative context |
| 7 | `"{ticker}" competitors sector comparison` | Peer context |
| 8 | `"{ticker}" insider trading executives` | Management alignment |

**After search, attempt direct fetches** (if URLs found):
- Yahoo Finance: `https://finance.yahoo.com/quote/{ticker}/`
- SEC EDGAR: `https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={ticker}&type=10-Q`

### Step 4.4 — Korean Stock Protocol

Read `kr-data-sources.md` for full source priority chain. Execute in this order:

**Step 4.4.0 — DART OpenAPI (structured data, Grade A)**:

Always run dart-collector.py for Korean stocks (DART API is free, key is pre-configured):

```bash
python .claude/skills/web-researcher/scripts/dart-collector.py \
  --stock-code {6digit_ticker} \
  --output output/data/{ticker}/dart-api-raw.json
```

- **Success** → `dart-api-raw.json` written with Grade A financial data. Proceed to Step 4.4.2 (skip web DART scraping — Step 4.4.1).
- **Failure** (network error, invalid stock code, API issue) → log the error, proceed with web fallback from Step 4.4.1.

**Step 4.4.1 — DART web (fallback only, skip if dart-api-raw.json exists)**:
- Search: `"{company}" 사업보고서 분기보고서 DART site:dart.fss.or.kr`
- OR fetch: `https://dart.fss.or.kr/dsearch/main.do?maxResults=5&textCrpNm={company}`
- Extract: 매출액, 영업이익, 당기순이익, EPS from most recent 분기보고서
- Tag: `[KR-Portal]`, Grade B (if confirmed by 네이버) or Grade C (single source)

**Step 4.4.2 — 네이버금융 (always run — price + market data)**:
- Fetch: `https://finance.naver.com/item/main.naver?code={6digit_ticker}`
- Extract: 현재가, 거래량, PER, PBR, EPS, 배당수익률, 외국인 지분율, 52주 고/저
- Tag: `[KR-Portal]`
- Note: 네이버금융 is the primary source for real-time price and market metrics (DART API does not provide price data)

**Step 4.4.3 — FnGuide** (if consensus data needed):
- Fetch: `http://comp.fnguide.com/SVO2/ASP/SVD_Main.asp?pGB=1&gicode=A{6digit_ticker}`
- Extract: consensus EPS, revenue estimates, analyst target prices
- Tag: `[KR-Portal]`

**Step 4.4.4 — KIND** (수급/지분율):
- Search: `"{company}" 외국인 지분율 기관 수급 site:kind.krx.co.kr`
- Extract: 외국인 지분율, 기관 순매수/순매도

**Step 4.4.5 — General search**:
- Search: `"{company}" 실적발표 2026 영업이익 매출`
- Search: `"{company}" 잠정실적 2026`

### Step 4.5 — Enhanced Mode Qualitative Supplement (4 searches)

When `data_mode = "enhanced"`, execute these additional searches AFTER Tier 1 API collection:

| # | Query Template | Purpose |
|---|----------------|---------|
| 1 | `"{ticker}" earnings call transcript guidance 2026` | Management outlook |
| 2 | `"{company}" industry trends competitive landscape 2026` | Sector context |
| 3 | `"{ticker}" recent news developments last 90 days` | Catalyst monitoring |
| 4 | `"{ticker}" vs competitors {peer1} {peer2}` | Relative positioning |

### Step 4.6 — Data Extraction & Tagging

For each piece of data extracted from web sources:

**Tag assignment** (tags indicate provenance; grades assigned by decision tree in confidence-grading.md):
- Financial Datasets MCP / DART OpenAPI / DART web → `[Filing]` (규제기관 공시 원본)
- Yahoo Finance, Google Finance, MarketWatch → `[Portal]`
- 네이버금융, FnGuide, KIND → `[KR-Portal]`
- Self-calculated ratios (P/E, EV/EBITDA etc.) → `[Calc]`
- Analyst consensus, price targets → `[Est]`

**Confidence rule**: 2+ independent portals agree within 5% → Grade B. Single source only → Grade C. Tags do not determine grade.

### Step 4.7 — Gap-Fill Priority

After collecting data, identify which of the 10 key metrics from `validation-rules.md` are:
- FILLED (from web or API)
- MISSING (not found in any source)

For each MISSING metric, attempt one additional targeted search:
- Revenue missing → `"{ticker}" annual revenue TTM 2025`
- EPS missing → `"{ticker}" diluted EPS TTM 2025`
- P/E missing → try Yahoo Finance direct fetch

If still missing after targeted search → mark as Grade D (will be excluded from analysis).

### Step 4.8 — Macro Context Search (Mode C/D only)

Check `output/research-plan.json` for `macro_search_required`. If `false` or absent, skip this step entirely.

**Execution**:
1. Read the `macro_search_query` field from `research-plan.json`
2. Execute the query using the MCP search priority chain:
   - `mcp__tavily__search` → `mcp__brave__search` → `WebSearch` → `WebFetch`
3. **Timeout**: 20 seconds. If search fails or times out, log warning and proceed without macro data — do NOT stall the pipeline.

**Extract from results**:

| Field | Description |
|-------|-------------|
| `factor` | What macro force (e.g., "Fed rate cuts", "China tariffs", "USD/KRW depreciation") |
| `narrative` | How it affects the sector/ticker — must be specific, not generic |
| `timeline` | When impact occurs (e.g., "Q2 2026", "next 6 months", "immediate") |
| `confidence` | High / Medium / Low — based on source authority and consensus |
| `tag` | Source tag: `[News]`, `[Filing]`, or `[Est]` |

**Write to tier2-raw.json** under a new `macro_context` field:

```json
"macro_context": {
  "search_query": "the query executed",
  "collection_timestamp": "ISO 8601",
  "factors": [
    {
      "factor": "...",
      "narrative": "...",
      "timeline": "...",
      "confidence": "High|Medium|Low",
      "tag": "[News]|[Filing]|[Est]",
      "sources": ["url1", "url2"]
    }
  ],
  "macro_risks": [
    {
      "risk": "...",
      "impact": "...",
      "ticker_relevance": "...",
      "monitoring": "..."
    }
  ]
}
```

**Edge cases**:
- If macro search returns no useful results → set `macro_context` to `null` (not an empty object)
- If `macro_search_required` is `true` but `macro_search_query` is missing → skip and log warning
- Always proceed to the next step regardless of macro search outcome

### Step 4.9 — Write tier2-raw.json

```json
{
  "ticker": "AAPL",
  "collection_timestamp": "2026-03-12T14:30:00Z",
  "market": "US",
  "searches_executed": [
    {
      "query": "\"AAPL\" stock price market cap current",
      "results": [
        {
          "source": "Yahoo Finance",
          "url": "https://finance.yahoo.com/quote/AAPL/",
          "date": "2026-03-12",
          "snippet": "Apple Inc. (AAPL) $175.50 +1.25 (+0.72%)",
          "data_extracted": {
            "price": 175.50,
            "market_cap": "2.71T",
            "52w_high": 199.62,
            "52w_low": 164.08
          },
          "tag": "[Portal]",
          "confidence_grade": "B"
        }
      ]
    }
  ],
  "key_data_extracted": {
    "price": {"value": 175.50, "source": "Yahoo Finance", "tag": "[Portal]", "grade": "B"},
    "market_cap": {"value": 2710000, "source": "Yahoo Finance + MarketWatch", "tag": "[Portal]", "grade": "B"},
    "revenue_ttm": {"value": 395000, "source": "SEC EDGAR 10-Q", "tag": "[Portal]", "grade": "B"},
    "pe_ratio": {"value": 28.0, "source": "Yahoo Finance", "tag": "[Portal]", "grade": "C"}
  },
  "news_items": [...],
  "analyst_coverage": {...},
  "insider_trades": [...],
  "qualitative_context": "...",
  "macro_context": null
}
```

---

## Multi-Ticker Workflow 2

For peer comparison, run a parallel (or sequential) web research for each ticker:
- Each ticker writes to `output/data/{ticker}/tier2-raw.json` (namespaced)
- Do NOT share a single `tier2-raw.json` across tickers
- Use session context: if a ticker was researched earlier in the session, skip and reuse

---

## Completion Check

- [ ] All planned searches executed (Standard: 8 minimum; Enhanced supplement: 4 minimum)
- [ ] Korean stocks: dart-collector.py attempted first; outcome logged (success/fallback)
- [ ] Korean stocks: 네이버금융 fetched for price/market data regardless of DART API result
- [ ] Source tags applied to all extracted data points
- [ ] Confidence grades assigned (A/B/C/D)
- [ ] 10 key metrics coverage check performed
- [ ] Gap-fill targeted searches run for missing metrics
- [ ] Macro context search executed (Mode C/D) or skipped (Mode A/B or macro_search_required=false)
- [ ] `output/data/{ticker}/tier2-raw.json` written (includes `macro_context` field if applicable)
- [ ] All news items dated and attributed
