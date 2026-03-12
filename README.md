# Stock Analysis Agent

> **Language / 언어**: English | [한국어](README.ko.md)

A Claude Code-based AI research assistant for retail investors. Covers US equities (NYSE/NASDAQ/AMEX) and Korean equities (KRX/KOSPI/KOSDAQ) with structured, source-tagged analysis and a strict anti-hallucination policy.

---

## Key Features

- **4 Analysis Modes** — Quick Brief (A), Peer Comparison (B), Deep Dive Dashboard (C), Investment Memo (D)
- **Adaptive Data Strategy** — Enhanced Mode via MCP APIs when available; Standard Mode via web research as fallback
- **Anti-Hallucination Policy** — unverifiable data is displayed as "—", never fabricated
- **3-Layer Fact-Checking** — arithmetic consistency → multi-source cross-reference → sector sanity check
- **Source Tagging** — every number carries a tag: `[API]`, `[Web]`, `[Calculated]`, `[DART]`, etc.
- **Korean Stock Support** — DART → 네이버금융 → FnGuide data chain; Korean-language output
- **Portfolio & Watchlist** — tracking, delta comparison, catalyst calendar

---

## Quick Start

### Prerequisites

- [Claude Code](https://claude.ai/code) CLI installed and authenticated
- Python 3.8+ (for ratio calculation scripts)
- (Optional) Financial Datasets MCP + FMP MCP API keys for Enhanced Mode

### 1. Clone the repository

```bash
git clone <your-repo-url>
cd stock-analysis-agent
```

### 2. (Optional) Configure MCP for Enhanced Mode

See the full [MCP Setup Guide](docs/mcp-setup-guide.md) | [한국어 가이드](docs/mcp-setup-guide.ko.md).

Without MCP, the agent runs in Standard Mode (web-only) — fully functional with slightly lower data confidence.

### 3. Open in Claude Code

```bash
claude
```

Claude Code reads `CLAUDE.md` automatically on session start. You'll see:

```
=== Stock Analysis Agent ===
Data Mode: Enhanced (MCP active)   ← or "Standard (Web-only)"
Date: 2026-03-12
Ready. Send a ticker or question to begin.
```

---

## How to Use

### Workflow 0 — Price Check

A quick price lookup. No analysis generated.

```
AAPL 지금 얼마야?
What is NVDA trading at?
삼성전자 현재 주가?
```

**Output** (inline):
```
Apple Inc. (AAPL): $175.50 (▲0.72% today) | Mkt Cap: $2.72T
52W: $164.08–$199.62
[Source: [API] | 2026-03-12]
```

---

### Workflow 1 — Single Stock Analysis

Full analysis pipeline. Mode is auto-selected based on your phrasing, or specify explicitly.

| Phrasing | Mode | Output |
|----------|------|--------|
| "간단히 분석" / "quick brief" | A — Quick Brief | Inline markdown, ~400 words |
| "분석해줘" (default) | C — Deep Dive Dashboard | HTML file |
| "심층 분석" / "deep dive" | C — Deep Dive Dashboard | HTML file |
| "투자 메모" / "investment memo" | D — Investment Memo | Markdown file |

**Examples**:
```
AAPL 간단히 분석해줘
Analyze NVDA
삼성전자 심층 분석해줘
TSLA investment memo
005930 분석 (Mode C)
```

**Mode A — Quick Brief** (inline):
```
## Apple Inc. (AAPL) — Quick Brief
*2026-03-12 | Standard Mode*

Current Price: $175.50 (▲0.72%)  Mkt Cap: $2.72T

| Metric | Value | Grade |
|--------|-------|-------|
| P/E (TTM) | 28.0x [≈] | B |
| EV/EBITDA | 22.1x [Calculated] | B |
| Revenue Growth YoY | +4.9% [API] | A |
...

R/R Score: 7.8 — Attractive
Verdict: Overweight
```

**Mode C — Deep Dive Dashboard** (HTML file):
Saved to `output/reports/AAPL_C_EN_2026-03-12.html` — open in any browser.

**Mode D — Investment Memo** (Markdown file):
Saved to `output/reports/AAPL_D_EN_2026-03-12.md` — ~3,000 words across 10 sections.

---

### Workflow 2 — Peer Comparison

Compare 2–5 tickers side-by-side with R/R Score ranking and Best Pick.

```
AAPL vs MSFT vs GOOGL
삼성전자 vs SK하이닉스 비교
Compare NVDA, AMD, INTC
```

**Output**: HTML comparison matrix (`output/reports/AAPL_GOOGL_MSFT_B_EN_2026-03-12.html`).

---

### Workflow 3 — Portfolio & Watchlist

**Watchlist management**:
```
AAPL 워치리스트 추가
Add NVDA to watchlist
삼성전자 워치리스트 추가
워치리스트 보여줘
워치리스트 스캔
카탈리스트 캘린더 보여줘
```

**Portfolio registration** (3 supported formats):

*Inline chat*:
```
AAPL 100주 $150, MSFT 50주 $380, 삼성전자 200주 72000원
```

*JSON*:
```json
[
  {"ticker": "AAPL", "shares": 100, "avg_cost": 150, "currency": "USD"},
  {"ticker": "005930", "shares": 200, "avg_cost": 72000, "currency": "KRW"}
]
```

*CSV*:
```
ticker,shares,avg_cost,currency
AAPL,100,150,USD
005930,200,72000,KRW
```

**Portfolio review**:
```
포트폴리오 분석해줘
Analyze my portfolio
```

**Delta comparison** (compare to a previous analysis):
```
AAPL 지난번 분석이랑 비교해줘
What changed since the last AAPL analysis?
```

---

## Output Files

All generated files are saved under `output/` (gitignored by default):

| Path | Content |
|------|---------|
| `output/reports/{ticker}_A_*.md` | Mode A inline text (if saved) |
| `output/reports/{ticker}_C_*.html` | Mode C HTML dashboard |
| `output/reports/{ticker}_D_*.md` | Mode D investment memo |
| `output/reports/{tickers}_B_*.html` | Mode B comparison matrix |
| `output/data/{ticker}/latest.json` | Most recent snapshot |
| `output/data/{ticker}/{ticker}_{date}_snapshot.json` | Versioned archive |
| `output/watchlist.json` | Watchlist registry |
| `output/portfolio.json` | Portfolio holdings |
| `output/catalyst-calendar.json` | Aggregated catalyst calendar |

---

## Data Confidence System

Every value in the output carries a confidence grade and source tag.

| Grade | Tag | Meaning |
|-------|-----|---------|
| A | *(none)* | Verified from primary source; arithmetic consistent |
| B | `[≈]` | Cross-referenced; 2+ sources agree within 5% |
| C | `[1S]` | Single source; unverified |
| D | `[Unverified]` | Cannot verify → displayed as "—" |

**Source tags**:

| Tag | Source |
|-----|--------|
| `[API]` | Financial Datasets MCP |
| `[FMP]` | FMP MCP (analyst data) |
| `[DART]` | Korea DART filing |
| `[네이버]` | 네이버금융 |
| `[Web]` | Web research |
| `[Calculated]` | Derived from tagged inputs |
| `[KR-Web]` | Korean financial portals |

---

## Enhanced vs Standard Mode

| Feature | Enhanced Mode | Standard Mode |
|---------|--------------|---------------|
| Requires | Financial Datasets MCP API key | Nothing additional |
| Data source | Structured API (8 quarters financials) | Web search + scraping |
| Max confidence grade | Grade A | Grade B |
| Historical price chart | ✓ (Chart.js) | ✗ (text table fallback) |
| Analyst estimates | ✓ (structured) | ✓ (web-sourced) |
| Korean stocks | Always Standard Mode | Standard Mode |
| Cost | ~$0.05–$0.28/analysis | Free |

---

## R/R Score

The Risk/Reward Score summarizes each scenario analysis into a single number.

```
R/R Score = (Bull_return% × Bull_prob + Base_return% × Base_prob)
            ─────────────────────────────────────────────────────
                       |Bear_return% × Bear_prob|
```

| R/R Score | Signal | Typical Verdict |
|-----------|--------|-----------------|
| > 3.0 | Attractive | Overweight |
| 1.0 – 3.0 | Neutral | Neutral / Watch |
| < 1.0 | Unfavorable | Underweight |

---

## Project Structure

```
stock-analysis-agent/
├── CLAUDE.md                    ← Master orchestrator (Claude reads this)
├── README.md                    ← This file
├── README.ko.md                 ← Korean README
├── .gitignore
├── references/                  ← Analysis frameworks (Mode A/B/C/D)
├── docs/
│   ├── mcp-setup-guide.md       ← MCP setup (English)
│   └── mcp-setup-guide.ko.md   ← MCP setup (Korean)
├── output/                      ← Generated files (gitignored)
│   ├── watchlist.json
│   ├── portfolio.json
│   ├── catalyst-calendar.json
│   ├── reports/
│   └── data/
└── .claude/
    ├── skills/                  ← 10 SKILL.md files (step-by-step instructions)
    └── agents/                  ← 3 AGENT.md files (analyst, critic, data-researcher)
```

---

## Disclaimer

**This tool is for informational purposes only. It does not constitute investment advice, a solicitation to buy or sell any security, or a guarantee of investment returns.**

- All analysis is generated by AI and may contain errors or omissions
- Past performance data does not guarantee future results
- Always conduct your own due diligence before making investment decisions
- Consult a qualified financial advisor for personalized investment guidance
- Market data may be delayed; verify time-sensitive information with primary sources

The anti-hallucination system (Grade D → "—") reduces but does not eliminate the risk of data errors. All outputs should be independently verified before acting on them.

---

## Contributing

This is a personal research tool. If you adapt it for your own use, please:
- Keep the anti-hallucination safeguards intact
- Do not remove the disclaimer from generated outputs
- Review the data confidence grades before making investment decisions
