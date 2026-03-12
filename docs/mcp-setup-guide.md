# MCP Setup Guide

This guide explains how to configure the MCP (Model Context Protocol) servers for Enhanced Mode analysis.

---

## What is Enhanced Mode?

Enhanced Mode uses two MCP servers for structured financial data:
1. **Financial Datasets MCP** — real-time price, 8 quarters of financials, analyst estimates, insider trades, SEC filings
2. **FMP MCP (optional)** — analyst price targets, rating distributions, analyst grade history

Without MCP, the agent operates in **Standard Mode** (web-only) — fully functional but with lower data confidence grades (max Grade B vs. Grade A).

---

## Step 0 — Install python-docx (required for Mode D DOCX output)

Mode D investment memos are generated as Word documents (.docx). Install the required library:

```bash
pip install python-docx
```

Verify: `python -c "from docx import Document; print('OK')`

---

## Step 1 — Register Financial Datasets MCP

Financial Datasets MCP is a **hosted HTTP server** — no npm package to install.

### Register in Claude Code (one-time, user-level)

```bash
claude mcp add --transport http financial-datasets https://mcp.financialdatasets.ai/ --header "X-API-KEY: your_api_key_here"
```

Replace `your_api_key_here` with your actual API key (see Step 2 below).

Verify the registration:

```bash
claude mcp list
```

You should see `financial-datasets` listed with the hosted URL.

### FMP MCP (optional — for structured analyst data)

FMP MCP is also a hosted service. Contact FMP for their MCP endpoint, or skip this step — analyst data will be sourced from web search instead.

---

## Step 2 — Get API Keys

### Financial Datasets API Key
1. Go to [https://financialdatasets.ai](https://financialdatasets.ai)
2. Create an account and subscribe to a plan
3. Copy your API key from the dashboard

**Security note**: Do not share your API key in chat or commit it to a public repository. Regenerate it immediately if accidentally exposed.

### FMP (Financial Modeling Prep) API Key (optional)
1. Go to [https://financialmodelingprep.com](https://financialmodelingprep.com)
2. Create an account (free tier available)
3. Copy your API key from the dashboard

---

## Step 3 — Register the MCP with Your Key

After obtaining your Financial Datasets API key, re-register to include it:

```bash
claude mcp remove financial-datasets
claude mcp add --transport http financial-datasets https://mcp.financialdatasets.ai/ --header "X-API-KEY: your_api_key_here"
```

The configuration is saved to `~/.claude.json` (user-level — applies to all projects).

**Alternative — project-level config** (from the project directory):

```bash
claude mcp add --transport http financial-datasets https://mcp.financialdatasets.ai/ --header "X-API-KEY: your_api_key_here" --scope project
```

This saves to `.claude/settings.local.json` (project-specific, gitignored).

---

## Step 4 — Verify Setup

Start a new session in Claude Code and the agent will automatically test MCP availability:

```
Test call: get_current_stock_price("AAPL")
→ If price returned: DATA_MODE = "enhanced" ✓
→ If error: DATA_MODE = "standard" (MCP not configured or API key issue)
```

You should see in the session status block:
```
Data Mode: Enhanced (MCP active) ✓
```

---

## Step 5 — Estimated API Costs

### Financial Datasets MCP

| Analysis Type | Estimated Cost |
|--------------|---------------|
| Single stock (Full bundle — Mode C/D) | ~$0.28/analysis |
| Single stock (Minimum bundle — Mode B) | ~$0.05/analysis |
| Peer comparison (3 stocks, full bundle) | ~$0.84/analysis |
| Watchlist scan (10 tickers, price only) | ~$0.10/scan |

Costs are based on Financial Datasets MCP pricing as of 2026. Check current pricing at financialdatasets.ai.

### FMP MCP

FMP calls (analyst data bundle) add approximately $0.01–$0.03 per analysis.

---

## Troubleshooting

### "DATA_MODE: standard" even after MCP setup
- Verify API key is set correctly (no extra spaces, no quotes inside the string)
- Run `claude mcp list` to confirm `financial-datasets` is registered
- Restart Claude Code after registering the MCP

### API calls returning errors
- Verify API key is active and has sufficient credits
- Check that the ticker is valid (US stocks only for Financial Datasets MCP)
- Korean stocks always use Standard Mode — this is expected

### python-docx not found (Mode D fails)
- Run: `pip install python-docx`
- Verify: `python -c "from docx import Document; print('OK')"`

### Python scripts failing
- Ensure Python 3.8+ is installed: `python --version`
- Set UTF-8 encoding: `set PYTHONUTF8=1` (Windows) or `export PYTHONUTF8=1` (Mac/Linux)
- Scripts are in `.claude/skills/data-validator/scripts/`, `.claude/skills/data-manager/scripts/`, and `.claude/skills/output-generator/scripts/`

---

## Operating Without MCP (Standard Mode)

If you prefer not to use MCP servers (or cannot access APIs), the agent works fully in Standard Mode:

- All analysis outputs remain available (Mode B, C, D)
- Data confidence grades max at Grade B (vs. Grade A with MCP)
- Source tags will show `[Web]`, `[≈]`, `[1S]` instead of `[API]`
- Korean stocks are always Standard Mode regardless

Standard Mode is suitable for most research purposes. Enhanced Mode adds speed and higher data confidence.

---

## Environment Variables (Alternative to Config File)

You can also set API keys as environment variables:

```bash
# Windows
set FINANCIAL_DATASETS_API_KEY=your_api_key_here
set FMP_API_KEY=your_fmp_api_key_here

# macOS/Linux
export FINANCIAL_DATASETS_API_KEY=your_api_key_here
export FMP_API_KEY=your_fmp_api_key_here
```
