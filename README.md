# 📊 Stock Analysis Agent

> **Language / 언어**: English | [한국어](README.ko.md)

**Institutional-grade stock research for US and Korean equities — delivered in minutes.**

Built on Claude Code with dual data pipelines:
- 🇺🇸 **US stocks** — [Financial Datasets API](https://financialdatasets.ai) → real SEC filings, Grade A financial data
- 🇰🇷 **Korean stocks** — [DART OpenAPI](https://opendart.fss.or.kr) → 금융감독원 직접 수집, Grade A financial data
- 🌐 **Macro context** — [FRED API](https://fred.stlouisfed.org) → Fed economic data for DCF precision & sector sensitivity (Mode C/D)

Zero hallucinated numbers. Every figure traces back to its source.

---

## What Does This Do?

You type a ticker — US or Korean. You get a research-grade analysis complete with:

- **Scenario analysis** (Bull / Base / Bear) with probability-weighted R/R Score
- **Variant View** — where the market is wrong and why (company-specific, not generic)
- **Precision Risk Analysis** — every risk has a mechanism chain: event → P&L impact → stock price effect
- **Source-tagged data** — every number traces back to its origin. Nothing fabricated.
- **Korean market overlay** — 외국인 지분율, 밸류업 프로그램, DART 공시 직접 연동

> **Core principle**: Blank beats wrong. If a number can't be verified, it shows as "—" — never made up.

---

## 4 Output Modes

### 🔍 Mode A — Quick Briefing *(HTML)*
**A** as in **A**t-a-glance. Quick verdict card + 180-day event timeline on a single page. Screening before deep dive.

> **[See live example →](https://codepen.io/lowtidebuild/full/xbEgpdE)**

### ⚖️ Mode B — Peer Comparison *(HTML)*
**B** as in **B**enchmark. Side-by-side matrix for 2–5 tickers. R/R Score ranking, Best Pick with rationale, Key Differentiators.

> **[See live example →](https://codepen.io/lowtidebuild/full/emdgGdW)**

### 📈 Mode C — Deep Dive Dashboard *(default)*
**C** as in **C**hart. Interactive HTML — open in any browser. Built for quick decision-making.

| Section | Contents |
|---------|----------|
| **Header** | Company name · live price · market cap · 52W range · YIR links |
| **Scenario Cards** | 🐂 Bull / 📊 Base / 🐻 Bear price targets · probabilities |
| **R/R Score Badge** | Weighted risk/reward score → Attractive / Neutral / Unfavorable |
| **KPI Tiles** | P/E · EV/EBITDA · FCF Yield · Revenue Growth · Operating Margin |
| **Variant View** | Q1–Q3: where the market is wrong, company-specific evidence |
| **Precision Risk** | 3 risks × causal chain × EBITDA impact × mitigation |
| **Macro Environment** | Macro factors affecting the stock · impact assessment · confidence badges |
| **Valuation** | SOTP breakdown · comparable multiples · **DCF sensitivity table (3×3 WACC × terminal growth)** |
| **Analyst Targets** | Consensus · high/low · rating distribution bar |
| **Charts** | Revenue trend · margin history · price vs targets (Chart.js) |
| **Quarterly Financials** | 8-quarter income statement · QoE bridge |
| **Strategy** | Bull/Base/Bear positioning guide · key monitoring catalysts |

> **[See live example →](https://codepen.io/lowtidebuild/full/vEXgYGL)**

### 📝 Mode D — Investment Memo *(DOCX)*
**D** as in **D**ocument. Word document — 3,000+ words, 10 structured sections. Think Goldman Sachs equity research note.

| Section | Content |
|---------|---------|
| Executive Summary | 1-sentence thesis · Verdict · R/R Score |
| Business Overview | Revenue streams · Market share · TAM |
| Financial Performance | 8-quarter tables · Margin trends · FCF |
| Valuation Analysis | P/E · EV/EBITDA · SOTP breakdown · **DCF fair value + sensitivity table** |
| **5-Question Variant View** | Where the market is wrong (most important section) |
| Precision Risk Analysis | 3 risks × full mechanism chain + EBITDA impact |
| Macro Risk Overlay | Top-down macro factors · sector sensitivity · quantified impact pathways |
| Investment Scenarios | Bull / Base / Bear with R/R formula shown |
| Peer Comparison | 5-metric table vs. 3–5 peers |
| Management & Governance | CEO track record · Capital allocation |
| Quality of Earnings | EBITDA Bridge · FCF conversion · SBC haircut |
| What Would Make Me Wrong | 3 assumptions · Pre-mortem paragraph |
| Appendix | All data sources · Confidence grades · Exclusions |

> **[See live example →](https://docs.google.com/document/d/1PX4FIrb1a4nBeKj3L7HanoYBfG6hSwOS/edit?usp=sharing&ouid=105178834220477378953&rtpof=true&sd=true)**

---

## Data Sources — US Stocks

> **Strongly recommended.** Connect [Financial Datasets API](https://financialdatasets.ai) for Grade A data.

When connected, the agent pulls structured data directly from SEC filings:

| Data | API Call | Confidence |
|------|----------|------------|
| Real-time price | `get_current_stock_price` | Grade A |
| 8 quarters income statement | `get_income_statements` | Grade A |
| Balance sheet (8 quarters) | `get_balance_sheets` | Grade A |
| Cash flow (8 quarters) | `get_cash_flow_statements` | Grade A |
| Analyst price targets | FMP MCP | Grade B |
| Insider transactions | `get_insider_transactions` | Grade A |
| SEC filings (10-K, 10-Q) | `get_sec_filings` | Grade A |

**Without MCP (or alongside it)**, the agent also pulls from major financial web sources:

| Data | Source | Confidence |
|------|--------|------------|
| Price · Market cap · Ratios | Yahoo Finance, Google Finance, MarketWatch | Grade B |
| Financial statements | SEC EDGAR (direct fetch) | Grade A |
| Earnings results | PR Newswire, Business Wire, Seeking Alpha | Grade B |
| Analyst price targets | TipRanks, MarketBeat | Grade B |
| News · Qualitative context | Reuters, Bloomberg, CNBC, Financial Times | Qualitative |
| Insider trading | SEC Form 4 (EDGAR), Finviz | Grade B |

With MCP: API data (Grade A) + web sources for qualitative context.
Without MCP: web-only, max confidence Grade B. Still fully functional.

```
💡 MCP setup takes 5 minutes. See → docs/mcp-setup-guide.md
```

---

## Data Sources — Korean Stocks

The agent always pulls structured financial statements directly from 금융감독원 via **DART OpenAPI** (free).

| Data | Source | Confidence |
|------|--------|------------|
| 연결 재무제표 (IS/BS/CF) | DART OpenAPI `fnlttSinglAcntAll` | Grade A |
| 기업 기본정보 (corp_code, CEO) | DART OpenAPI `company` | Grade A |
| 최근 공시 목록 (90일) | DART OpenAPI `list` | Grade A |
| 현재가 · PER · PBR · 외국인지분율 | 네이버금융 (always fetched for market data) | Grade B |
| 애널리스트 컨센서스 | FnGuide / 웹 검색 | Grade B |

Get your free DART API key at [opendart.fss.or.kr](https://opendart.fss.or.kr) and add it to `.claude/settings.local.json → env → DART_API_KEY`. It's the Korean equivalent of SEC EDGAR's API.

---

## Data Confidence System

Every number in the output carries a grade and source tag. You always know what to trust.

| Grade | Tag | Meaning | Example |
|-------|-----|---------|---------|
| **A** | `[Filing]` | Primary filing source, arithmetic consistent | SEC/DART API |
| **A** | `[Macro]` | Government economic statistics | FRED API (Fed Reserve) |
| **B** | `[Portal]` / `[KR-Portal]` | 2+ sources cross-referenced, within 5% | Web cross-reference |
| **C** | *(Grade C note)* | Single source, unverified | One web mention |
| **D** | `—` | Cannot verify → **shown as blank** | Never fabricated |

```
US stock example (Enhanced Mode):
  Revenue TTM: $402.8B [Filing]    ← Grade A, SEC filing via Financial Datasets
  P/E Ratio: 28.0x [Calc]         ← Derived from Grade A inputs
  EV/EBITDA: —                    ← Grade D, excluded

Korean stock example (DART-Enhanced):
  매출액 TTM: 302.2조원 [Filing]    ← Grade A, 금융감독원 DART OpenAPI
  영업이익률: 9.2% [Calc]           ← Derived from Grade A inputs
  컨센서스 PER: 12.4x [KR-Portal]  ← Grade B, FnGuide + 네이버 cross-check
```

---

## How to Use

### Single Stock Analysis

```
NVDA 분석해줘
Analyze TSLA
005930 심층 분석
AAPL investment memo
삼성전자 투자 메모 써줘
SK하이닉스 분석해줘
```

### Peer Comparison

```
NVDA vs AMD vs INTC
삼성전자 vs SK하이닉스 비교
AAPL vs MSFT vs GOOGL
```

### Portfolio & Watchlist

```
AAPL 워치리스트 추가
워치리스트 스캔해줘
포트폴리오 분석해줘
카탈리스트 캘린더 보여줘
NVDA 지난번 분석이랑 비교해줘
```

### Price-Only Queries

This agent doesn't do price lookups. For a quick price check, use Yahoo Finance or Perplexity.
Type `"AAPL 분석해줘"` to get the full research instead.

---

## R/R Score — Risk/Reward in One Number

Every analysis computes a single score that summarizes the scenario-weighted upside vs. downside.

```
R/R Score = (Bull_return% × Bull_prob + Base_return% × Base_prob)
            ─────────────────────────────────────────────────────
                       |Bear_return% × Bear_prob|
```

**Example**: Bull +25% × 30% + Base +12% × 50% = 13.5 upside weighted
            Bear -25% × 20% = 5.0 downside weighted
            **R/R Score = 13.5 / 5.0 = 2.7 → Neutral**

| Score | Signal | Typical Verdict |
|-------|--------|-----------------|
| **> 3.0** | 🟢 Attractive | Overweight |
| **1.0 – 3.0** | 🟡 Neutral | Neutral / Watch |
| **< 1.0** | 🔴 Unfavorable | Underweight |

---

## Quick Start

### Prerequisites

```bash
# 1. Claude Code
npm install -g @anthropic-ai/claude-code

# 2. Python library for Mode D (Word document output)
pip install python-docx

# 3. Clone this repo
git clone https://github.com/lowtidebuild/stock-analysis-agent.git
cd stock-analysis-agent
```

### (Strongly Recommended) Connect Financial Datasets API — US Stocks

```bash
# Register the MCP — takes 5 minutes, makes a huge difference for US stocks
claude mcp add --transport http financial-datasets https://mcp.financialdatasets.ai/ \
  --header "X-API-KEY: your_api_key_here"
```

Get your API key at [financialdatasets.ai](https://financialdatasets.ai).
Full setup guide: [docs/mcp-setup-guide.md](docs/mcp-setup-guide.md)

### (Optional) Connect FRED API — Macro Data for Mode C/D

Get a free API key at [fred.stlouisfed.org](https://fred.stlouisfed.org/docs/api/api_key.html), then add to `.env`:

```
FRED_API_KEY=your_key_here
```

Adds Grade A economic data (10Y Treasury, Fed Funds Rate, CPI, GDP, unemployment) for WACC precision and macro sensitivity analysis. Without it, macro context falls back to web search (Grade B/C).

### Connect DART API — Korean Stocks *(free, required)*

Get a free API key at [opendart.fss.or.kr](https://opendart.fss.or.kr), then add it to `.claude/settings.local.json`:

```json
"env": { "DART_API_KEY": "your_key_here" }
```

### Run

```bash
claude
```

Claude Code reads `CLAUDE.md` automatically. You'll see:

```
=== Stock Analysis Agent ===
Data Mode (US):  Enhanced (MCP active)     ← Grade A data from SEC filings
Data Mode (KR):  DART-Enhanced (Grade A)   ← Grade A data from 금융감독원
Date: 2026-03-12
Ready. Send a ticker or question to begin.
```

---

## Output Files

All generated files go under `output/` (gitignored):

| File | Mode | Open with |
|------|------|-----------|
| `output/reports/{ticker}_A_*.html` | A — Quick Briefing | Any browser |
| `output/reports/{tickers}_B_*.html` | B — Peer Comparison | Any browser |
| `output/reports/{ticker}_C_*.html` | C — Dashboard | Any browser |
| `output/reports/{ticker}_D_*.docx` | D — Investment Memo | Word / Google Docs / LibreOffice |
| `output/data/{ticker}/latest.json` | — | Snapshot for delta analysis |
| `output/watchlist.json` | — | Watchlist registry |
| `output/catalyst-calendar.json` | — | Upcoming events calendar |

---

## US Stock Mode Comparison

| | Enhanced Mode 🟢 | Standard Mode 🟡 |
|-|-----------------|--------------------|
| **Requires** | Financial Datasets API key | Nothing extra |
| **Data source** | SEC filings via structured API | Web research + scraping |
| **Price data** | Real-time, Grade A | Web-sourced, Grade B |
| **Financials** | 8 quarters, machine-readable | Web-scraped, may vary |
| **Max grade** | **Grade A** | Grade B |
| **Cost** | ~$0.05–$0.28/analysis | Free |

Korean stocks always use DART OpenAPI (Grade A financials) + 네이버금융 (Grade B price). DART API is free — no mode distinction needed.

---

## Korean Stock Support

Full support for KOSPI / KOSDAQ stocks with **Grade A financial data via DART OpenAPI**.

- **DART OpenAPI** — structured 재무제표 directly from 금융감독원 (IS/BS/CF, 공시 목록). Free API, always used.
- **네이버금융** — real-time price, PER/PBR, 외국인 지분율 (always fetched for market data)
- **FnGuide / KIND** — analyst consensus, 수급 data
- **Korean-language output** — all analysis in Korean when you ask in Korean
- **Korean market overlay** — 외국인 지분율, 밸류업 프로그램, 자사주 소각 policy

```
삼성전자 빠르게 봐줘    →  Mode A quick briefing (DART API Grade A data)
삼성전자 심층 분석해줘  →  Mode C dashboard (DART API Grade A data)
SK하이닉스 투자 메모     →  Mode D DOCX investment memo
삼성전자 vs SK하이닉스  →  Mode B peer comparison
```

---

## Project Structure

```
stock-analysis-agent/
├── CLAUDE.md                    ← Master orchestrator (Claude reads this on start)
├── references/                  ← Analysis frameworks for each mode
│   ├── analysis-framework-comparison.md
│   ├── analysis-framework-dashboard.md
│   └── analysis-framework-memo.md
├── docs/
│   ├── mcp-setup-guide.md       ← Financial Datasets API setup (English)
│   └── mcp-setup-guide.ko.md   ← Financial Datasets API setup (Korean)
├── output/                      ← Generated files (gitignored)
│   ├── reports/                 ← HTML / DOCX analysis outputs
│   └── data/                    ← Raw data + snapshots per ticker
└── .claude/
    ├── skills/                  ← 10 SKILL.md files (step-by-step pipeline)
    └── agents/                  ← analyst · critic · data-researcher
```

---

## Disclaimer

**This tool is for informational purposes only. It does not constitute investment advice, a solicitation to buy or sell any security, or a guarantee of investment returns.**

- All analysis is AI-generated and may contain errors
- Verify time-sensitive data with primary sources before acting
- Past performance data does not predict future results
- Always consult a qualified financial advisor before making investment decisions

The anti-hallucination system (Grade D → "—") reduces but does not eliminate the risk of data errors. Independently verify all outputs before acting on them.
