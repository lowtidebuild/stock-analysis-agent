# Portfolio Schema Reference

This file defines the schema for `output/portfolio.json`.

---

## Schema

```json
{
  "version": "1.0",
  "last_updated": "2026-03-12T14:30:00Z",
  "holdings": [
    {
      "ticker": "AAPL",
      "market": "US",
      "shares": 100,
      "avg_cost": 150.00,
      "currency": "USD",
      "last_snapshot_path": "output/data/AAPL/snapshots/2026-03-12_run_20260312T000000Z_AAPL/analysis-result.json",
      "current_price": 175.50,
      "current_value": 17550.00,
      "unrealized_pnl": 2550.00,
      "unrealized_pnl_pct": 17.0,
      "last_rr_score": 9.3,
      "last_verdict": "Overweight"
    }
  ],
  "last_total_value": null,
  "portfolio_analytics": null
}
```

---

## Field Definitions

### Root Object

| Field | Type | Description |
|-------|------|-------------|
| `version` | string | Schema version |
| `last_updated` | string/null | ISO 8601 datetime |
| `holdings` | array | List of portfolio positions |
| `last_total_value` | number/null | Total portfolio value at last analysis |
| `portfolio_analytics` | object/null | Portfolio-level metrics (see below) |

### Holding Entry

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `ticker` | string | YES | Canonical ticker |
| `market` | string | YES | "US" or "KR" |
| `shares` | number | YES | Number of shares held |
| `avg_cost` | number | YES | Average cost basis per share |
| `currency` | string | YES | "USD" or "KRW" |
| `last_snapshot_path` | string/null | NO | Link to most recent immutable snapshot `analysis-result.json` |
| `current_price` | number/null | NO | Price at last portfolio review |
| `current_value` | number/null | NO | shares × current_price |
| `unrealized_pnl` | number/null | NO | current_value - (shares × avg_cost) |
| `unrealized_pnl_pct` | number/null | NO | unrealized_pnl / (shares × avg_cost) × 100 |
| `last_rr_score` | number/null | NO | From last analysis snapshot |
| `last_verdict` | string/null | NO | From last analysis snapshot |

### `portfolio_analytics` Object (populated after analysis)

```json
"portfolio_analytics": {
  "total_value_usd": 85000,
  "total_cost_usd": 72000,
  "total_pnl_usd": 13000,
  "total_pnl_pct": 18.1,
  "sector_concentration": {
    "Technology/Platform": 55.0,
    "Industrial/Manufacturing": 20.0,
    "Consumer": 15.0,
    "Korean": 10.0
  },
  "weighted_rr_score": 7.8,
  "top_portfolio_risks": [
    "US-China tech decoupling affects AAPL and NVDA (combined 40% of portfolio)",
    "Rate sensitivity: REIT position exposed to prolonged high rates"
  ],
  "correlation_concerns": [
    "AAPL + NVDA high correlation (both AI/semiconductor exposure) — 40% position concentration"
  ],
  "analysis_date": "2026-03-12"
}
```

---

## Input Formats → Internal Schema Conversion

The portfolio manager must handle three input formats and convert to the internal schema:

### Format 1 — Chat Inline
```
Input: "AAPL 100주 $150, MSFT 50주 $380, 삼성전자 200주 72000원"

Parsed:
- AAPL: shares=100, avg_cost=150, currency=USD, market=US
- MSFT: shares=50, avg_cost=380, currency=USD, market=US
- 삼성전자 → ticker=005930: shares=200, avg_cost=72000, currency=KRW, market=KR
```

### Format 2 — JSON
```json
[
  {"ticker": "AAPL", "shares": 100, "avg_cost": 150, "currency": "USD"},
  {"ticker": "MSFT", "shares": 50, "avg_cost": 380, "currency": "USD"},
  {"ticker": "005930", "shares": 200, "avg_cost": 72000, "currency": "KRW"}
]
```

### Format 3 — CSV
```csv
ticker,shares,avg_cost,currency
AAPL,100,150,USD
MSFT,50,380,USD
005930,200,72000,KRW
```

All three formats produce the same internal holding schema.

---

## Complete Example

```json
{
  "version": "1.0",
  "last_updated": "2026-03-12T14:30:00Z",
  "holdings": [
    {
      "ticker": "AAPL",
      "market": "US",
      "shares": 100,
      "avg_cost": 150.00,
      "currency": "USD",
      "last_snapshot_path": "output/data/AAPL/snapshots/2026-03-12_run_20260312T000000Z_AAPL/analysis-result.json",
      "current_price": 175.50,
      "current_value": 17550.00,
      "unrealized_pnl": 2550.00,
      "unrealized_pnl_pct": 17.0,
      "last_rr_score": 9.3,
      "last_verdict": "Overweight"
    },
    {
      "ticker": "005930",
      "market": "KR",
      "shares": 200,
      "avg_cost": 72000,
      "currency": "KRW",
      "last_snapshot_path": "output/data/005930/snapshots/2026-03-12_run_20260312T000000Z_005930/analysis-result.json",
      "current_price": 74500,
      "current_value": 14900000,
      "unrealized_pnl": 500000,
      "unrealized_pnl_pct": 3.47,
      "last_rr_score": 5.1,
      "last_verdict": "중립"
    }
  ],
  "last_total_value": 32450,
  "portfolio_analytics": {
    "total_value_usd": 32450,
    "total_cost_usd": 27200,
    "total_pnl_usd": 5250,
    "total_pnl_pct": 19.3,
    "sector_concentration": {"Technology/Platform": 54.1, "Korean": 45.9},
    "weighted_rr_score": 7.4,
    "top_portfolio_risks": ["High concentration in 2 positions", "KRW/USD FX risk on 삼성전자 position"],
    "correlation_concerns": ["Both positions exposed to semiconductor cycle"],
    "analysis_date": "2026-03-12"
  }
}
```
