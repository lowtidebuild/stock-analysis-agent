# Watchlist Schema Reference

This file defines the schema for `output/watchlist.json`.

**Design principle**: The watchlist stores only metadata + snapshot pointer. It does NOT duplicate the full snapshot. The full snapshot is always read from `output/data/{ticker}/latest.json`.

---

## Schema

```json
{
  "version": "1.0",
  "last_updated": "2026-03-12T14:30:00Z",
  "tickers": [
    {
      "ticker": "AAPL",
      "market": "US",
      "added_date": "2026-02-01",
      "last_snapshot_path": "output/data/AAPL/AAPL_2026-03-12_snapshot.json",
      "last_analysis_date": "2026-03-12",
      "last_rr_score": 9.3,
      "last_price": 175.50,
      "last_verdict": "Overweight",
      "alert_flags": []
    }
  ]
}
```

---

## Field Definitions

### Root Object

| Field | Type | Description |
|-------|------|-------------|
| `version` | string | Schema version |
| `last_updated` | string/null | ISO 8601 datetime of last modification |
| `tickers` | array | List of watchlist entries |

### Ticker Entry

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `ticker` | string | YES | Canonical ticker (case-sensitive, uppercase) |
| `market` | string | YES | "US" or "KR" |
| `added_date` | string | YES | YYYY-MM-DD when added |
| `last_snapshot_path` | string/null | YES | Relative path to most recent snapshot |
| `last_analysis_date` | string/null | YES | YYYY-MM-DD of most recent analysis |
| `last_rr_score` | number/null | YES | R/R Score from most recent analysis |
| `last_price` | number/null | YES | Price at most recent analysis |
| `last_verdict` | string/null | YES | Verdict from most recent analysis |
| `alert_flags` | array | YES | Active alert flags (see below) |

### Alert Flags

Alert flags are strings describing active alerts. The watchlist scan generates these:

| Flag | Trigger |
|------|---------|
| `"EARNINGS_UPCOMING:{date}"` | Earnings within 14 days |
| `"PRICE_MOVE_5PCT"` | Price changed >5% since last snapshot |
| `"RR_SCORE_DROP_20PCT"` | R/R Score dropped >20% since last snapshot |
| `"MAJOR_NEWS"` | Significant news event detected |
| `"ANALYST_UPGRADE"` | Analyst rating upgrade detected |
| `"ANALYST_DOWNGRADE"` | Analyst rating downgrade detected |
| `"STALE_30D"` | Analysis >30 days old |

---

## Validation Rules

1. **No duplicates**: Ticker must be unique in the array (case-insensitive comparison)
2. **Valid market**: Must be "US" or "KR"
3. **Max size**: No hard limit, but watchlist scan becomes slow >50 tickers (warn user at >30)
4. **Ticker format**: US = 1-5 uppercase alpha; KR = 6-digit zero-padded numeric string (e.g., "005930")
5. **Atomic writes**: Always write to `.tmp` file then `os.replace()` to prevent corruption

---

## Relationship to Catalyst Aggregation

The `catalyst-aggregator.py` script reads `watchlist.json` to get the list of tickers, then reads each ticker's `last_snapshot_path` to extract `upcoming_catalysts`. This is why keeping `last_snapshot_path` current is critical — it is the link between the watchlist and the catalyst calendar.

---

## Complete Example

```json
{
  "version": "1.0",
  "last_updated": "2026-03-12T14:30:00Z",
  "tickers": [
    {
      "ticker": "AAPL",
      "market": "US",
      "added_date": "2026-01-15",
      "last_snapshot_path": "output/data/AAPL/AAPL_2026-03-12_snapshot.json",
      "last_analysis_date": "2026-03-12",
      "last_rr_score": 9.3,
      "last_price": 175.50,
      "last_verdict": "Overweight",
      "alert_flags": ["EARNINGS_UPCOMING:2026-04-25"]
    },
    {
      "ticker": "005930",
      "market": "KR",
      "added_date": "2026-02-01",
      "last_snapshot_path": "output/data/005930/005930_2026-03-10_snapshot.json",
      "last_analysis_date": "2026-03-10",
      "last_rr_score": 5.1,
      "last_price": 72000,
      "last_verdict": "중립",
      "alert_flags": ["STALE_30D"]
    }
  ]
}
```
