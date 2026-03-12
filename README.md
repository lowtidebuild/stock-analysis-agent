# 📊 Stock Analysis Agent

> **Language / 언어**: English | [한국어](README.ko.md)

**Institutional-grade stock research, delivered in minutes.**
Built on Claude Code + [Financial Datasets API](https://financialdatasets.ai) — real SEC filings, 8 quarters of verified financials, zero hallucinated numbers.

---

## What Does This Do?

You type a ticker. You get a research-grade analysis — the kind a buy-side analyst would produce — complete with:

- **Scenario analysis** (Bull / Base / Bear) with probability-weighted R/R Score
- **Variant View** — where the market is wrong and why (company-specific, not generic)
- **Precision Risk Analysis** — every risk has a mechanism chain: event → P&L impact → stock price effect
- **Source-tagged data** — every number traces back to its origin. Nothing fabricated.
- **Korean stock support** — DART filings, 네이버금융, FnGuide data chain

> **Core principle**: Blank beats wrong. If a number can't be verified, it shows as "—" — never made up.

---

## 3 Output Modes

### 📈 Mode C — Deep Dive Dashboard *(default)*
**Interactive HTML** — open in any browser. Built for quick decision-making.

```
┌─────────────────────────────────────────────────────────────┐
│  NVIDIA Corp (NVDA)          $875.40  ▲ +2.3%              │
│  Data Confidence: ████████░░ Grade A  |  Enhanced Mode      │
├──────────────┬──────────────┬──────────────────────────────┤
│  🐂 Bull     │  📊 Base     │  🐻 Bear                     │
│  $1,100      │  $980        │  $650                        │
│  +25.7%      │  +11.9%      │  -25.8%                      │
│  Prob: 30%   │  Prob: 50%   │  Prob: 20%                   │
├──────────────┴──────────────┴──────────────────────────────┤
│  R/R Score: 4.2  →  ✅ ATTRACTIVE  |  Verdict: Overweight  │
├─────────────────────────────────────────────────────────────┤
│  KPI Tiles: P/E · EV/EBITDA · FCF Yield · Rev Growth ···  │
│  Variant View Q1–Q3 · Precision Risk Table · Peer Compare  │
│  Chart.js Charts · Quarterly Financials · QoE Summary      │
└─────────────────────────────────────────────────────────────┘
```

### 📝 Mode D — Investment Memo *(DOCX)*
**Word document** — 3,000+ words, 10 structured sections. Think Goldman Sachs equity research note.

| Section | Content |
|---------|---------|
| Executive Summary | 1-sentence thesis · Verdict · R/R Score |
| Business Overview | Revenue streams · Market share · TAM |
| Financial Performance | 8-quarter tables · Margin trends · FCF |
| Valuation Analysis | P/E · EV/EBITDA · SOTP breakdown |
| **5-Question Variant View** | Where the market is wrong (most important section) |
| Precision Risk Analysis | 3 risks × full mechanism chain + EBITDA impact |
| Investment Scenarios | Bull / Base / Bear with R/R formula shown |
| Peer Comparison | 5-metric table vs. 3–5 peers |
| Management & Governance | CEO track record · Capital allocation |
| Quality of Earnings | EBITDA Bridge · FCF conversion · SBC haircut |
| What Would Make Me Wrong | 3 assumptions · Pre-mortem paragraph |
| Appendix | All data sources · Confidence grades · Exclusions |

### ⚖️ Mode B — Peer Comparison *(HTML)*
**Side-by-side matrix** for 2–5 tickers. R/R Score ranking, Best Pick with rationale, Key Differentiators.

---

## Why Financial Datasets API?

> **Strongly recommended.** This is what separates this agent from a generic LLM stock analysis.

When connected to [financialdatasets.ai](https://financialdatasets.ai), the agent pulls:

| Data | Source | Confidence |
|------|--------|------------|
| Real-time price | `get_current_stock_price` | Grade A |
| 8 quarters income statement | `get_income_statements` | Grade A |
| Balance sheet (8 quarters) | `get_balance_sheets` | Grade A |
| Cash flow statement (8 quarters) | `get_cash_flow_statements` | Grade A |
| Analyst price targets | FMP MCP | Grade B |
| Insider transactions | `get_insider_transactions` | Grade A |
| SEC filings (10-K, 10-Q) | `get_sec_filings` | Grade A |

**Without it:** the agent still works — it runs web research and cross-references multiple sources. Max data confidence drops from Grade A to Grade B.

**With it:** structured, machine-readable financial data from SEC filings. Numbers that match the 10-K. No ambiguity.

```
💡 Setup takes 5 minutes. See → docs/mcp-setup-guide.md
```

---

## Data Confidence System

Every number in the output carries a grade and source tag. You always know what to trust.

| Grade | Tag | Meaning | When |
|-------|-----|---------|------|
| **A** | *(none)* | Verified from primary source, arithmetic consistent | API data matching SEC filings |
| **B** | `[≈]` | 2+ sources agree within 5% | Web cross-reference |
| **C** | `[1S]` | Single source, unverified | One web mention |
| **D** | `—` | Cannot verify → **shown as blank** | Never fabricated |

```
Example in output:
  Revenue TTM: $123.5B [API]        ← Grade A, from SEC via API
  P/E Ratio: 28.4x [Calculated]    ← Derived from Grade A inputs
  EV/EBITDA: —                     ← Grade D, excluded (EBITDA unverifiable)
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
git clone https://github.com/your-username/stock-analysis-agent.git
cd stock-analysis-agent
```

### (Strongly Recommended) Connect Financial Datasets API

```bash
# Register the MCP — takes 5 minutes, makes a huge difference
claude mcp add --transport http financial-datasets https://mcp.financialdatasets.ai/ \
  --header "X-API-KEY: your_api_key_here"
```

Get your API key at [financialdatasets.ai](https://financialdatasets.ai).
Full setup guide: [docs/mcp-setup-guide.md](docs/mcp-setup-guide.md)

### Run

```bash
claude
```

Claude Code reads `CLAUDE.md` automatically. You'll see:

```
=== Stock Analysis Agent ===
Data Mode: Enhanced (MCP active)   ← Grade A data from SEC filings
Date: 2026-03-12
Ready. Send a ticker or question to begin.
```

---

## Output Files

All generated files go under `output/` (gitignored):

| File | Mode | Open with |
|------|------|-----------|
| `output/reports/{ticker}_C_*.html` | C — Dashboard | Any browser |
| `output/reports/{ticker}_D_*.docx` | D — Investment Memo | Word / Google Docs / LibreOffice |
| `output/reports/{tickers}_B_*.html` | B — Peer Comparison | Any browser |
| `output/data/{ticker}/latest.json` | — | Snapshot for delta analysis |
| `output/watchlist.json` | — | Watchlist registry |
| `output/catalyst-calendar.json` | — | Upcoming events calendar |

---

## Enhanced vs Standard Mode

| | Enhanced Mode 🟢 | Standard Mode 🟡 |
|-|-----------------|-----------------|
| **Requires** | Financial Datasets API key | Nothing extra |
| **Data source** | SEC filings via structured API | Web research + scraping |
| **Price data** | Real-time, Grade A | Web-sourced, Grade B |
| **Financials** | 8 quarters, machine-readable | Web-scraped, may vary |
| **Max grade** | **Grade A** | Grade B |
| **Charts** | Historical price (Chart.js) | Text table fallback |
| **Korean stocks** | Always Standard Mode | Standard Mode |
| **Cost** | ~$0.05–$0.28/analysis | Free |

---

## Korean Stock Support

Full support for KOSPI / KOSDAQ stocks:

- **DART filings** — 사업보고서, 분기보고서 direct fetch
- **네이버금융** — price, shareholding data
- **FnGuide / KIND** — consensus estimates
- **Korean-language output** — all analysis in Korean when you ask in Korean
- **Korean market overlay** — 외국인 지분율, 밸류업 프로그램, 자사주 소각 policy

```
삼성전자 심층 분석해줘  →  한국어로 Mode C 대시보드 생성
SK하이닉스 투자 메모     →  한국어로 Mode D DOCX 생성
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
