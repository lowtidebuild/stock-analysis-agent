# MCP Setup Guide

This guide explains how to configure the MCP (Model Context Protocol) servers for Enhanced Mode analysis.

---

## What is Enhanced Mode?

Enhanced Mode uses two MCP servers for structured financial data:
1. **Financial Datasets MCP** — real-time price, 8 quarters of financials, analyst estimates, insider trades, SEC filings
2. **FMP MCP (optional)** — analyst price targets, rating distributions, analyst grade history

Without MCP, the agent operates in **Standard Mode** (web-only) — fully functional but with lower data confidence grades (max Grade B vs. Grade A).

---

## Step 1 — Install MCP Servers

### Financial Datasets MCP

```bash
# Install via npm
npm install -g financial-datasets-mcp

# Or via npx (no global install)
npx financial-datasets-mcp
```

### FMP MCP (optional but recommended for analyst data)

```bash
npm install -g fmp-mcp
```

---

## Step 2 — Get API Keys

### Financial Datasets API Key
1. Go to [https://financialdatasets.ai](https://financialdatasets.ai)
2. Create an account and subscribe to a plan
3. Copy your API key from the dashboard

### FMP (Financial Modeling Prep) API Key (optional)
1. Go to [https://financialmodelingprep.com](https://financialmodelingprep.com)
2. Create an account (free tier available)
3. Copy your API key from the dashboard

---

## Step 3 — Configure Claude Desktop / Claude Code

Add MCP servers to your Claude configuration file:

### For Claude Code (recommended — edit `.claude/settings.local.json`)

```json
{
  "mcpServers": {
    "financial-datasets": {
      "command": "npx",
      "args": ["-y", "financial-datasets-mcp"],
      "env": {
        "FINANCIAL_DATASETS_API_KEY": "your_api_key_here"
      }
    },
    "fmp": {
      "command": "npx",
      "args": ["-y", "fmp-mcp"],
      "env": {
        "FMP_API_KEY": "your_fmp_api_key_here"
      }
    }
  }
}
```

### For Claude Desktop

Edit `~/.config/claude/claude_desktop_config.json` (macOS/Linux) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "financial-datasets": {
      "command": "npx",
      "args": ["-y", "financial-datasets-mcp"],
      "env": {
        "FINANCIAL_DATASETS_API_KEY": "your_api_key_here"
      }
    },
    "fmp": {
      "command": "npx",
      "args": ["-y", "fmp-mcp"],
      "env": {
        "FMP_API_KEY": "your_fmp_api_key_here"
      }
    }
  }
}
```

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
| Single stock (Minimum bundle — Mode A) | ~$0.05/analysis |
| Peer comparison (3 stocks, full bundle) | ~$0.84/analysis |
| Watchlist scan (10 tickers, price only) | ~$0.10/scan |

Costs are based on Financial Datasets MCP pricing as of 2026. Check current pricing at financialdatasets.ai.

### FMP MCP

FMP calls (analyst data bundle) add approximately $0.01–$0.03 per analysis.

---

## Troubleshooting

### "DATA_MODE: standard" even after MCP setup
- Verify API key is set correctly (no extra spaces, no quotes inside the string)
- Restart Claude Code after editing configuration
- Check that `npx financial-datasets-mcp` runs without error in a terminal

### API calls returning errors
- Verify API key is active and has sufficient credits
- Check that the ticker is valid (US stocks only for Financial Datasets MCP)
- Korean stocks always use Standard Mode — this is expected

### Python scripts failing
- Ensure Python 3.8+ is installed: `python --version`
- Set UTF-8 encoding: `set PYTHONUTF8=1` (Windows) or `export PYTHONUTF8=1` (Mac/Linux)
- Scripts are in `.claude/skills/data-validator/scripts/` and `.claude/skills/data-manager/scripts/`

---

## Operating Without MCP (Standard Mode)

If you prefer not to use MCP servers (or cannot access APIs), the agent works fully in Standard Mode:

- All analysis outputs remain available (Mode A, B, C, D)
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
