# Staleness Rules Reference

This file is read by `staleness-checker/SKILL.md` during Step 0. It defines the freshness evaluation rules for existing analysis snapshots.

---

## Snapshot Freshness Rules

| Condition | Action | User Message |
|-----------|--------|-------------|
| No snapshot exists | Full analysis (fresh start) | (no message, proceed silently) |
| Earnings released since last analysis | Full re-analysis (data fundamentally changed) | "마지막 분석 이후 실적이 발표되어 전체 재분석을 진행합니다." |
| Snapshot < 7 days old + no recent earnings | Offer reuse choice | "최근 분석이 있습니다 ({date}). 업데이트할까요, 기존 것을 볼까요?" |
| Snapshot 7–30 days old | Suggest delta update | "30일 이내 분석이 있습니다. 변동사항만 업데이트할까요?" |
| Snapshot > 30 days old | Full re-analysis (expired) | "마지막 분석이 30일 이상 경과했습니다. 전체 재분석을 진행합니다." |

---

## Snapshot Location

Check for snapshot existence at:
1. `output/data/{ticker}/latest.json` — pointer to the most recent immutable snapshot
2. `output/data/{ticker}/snapshots/{snapshot_id}/analysis-result.json` — immutable snapshot body
3. `output/data/{ticker}/{ticker}_{YYYY-MM-DD}_snapshot.json` — legacy specific-date snapshot

For pointer-format `latest.json`, first validate:
- `kind == "stock-analysis.latest-snapshot-pointer"`
- `refs.analysis_result` exists on disk
- `expires_at` is still in the future for the 24-hour reuse path

Legacy full-snapshot `latest.json` remains read-compatible. In that case, parse the snapshot body directly.

To read snapshot age: parse the `analysis_date` field in the JSON, not the file modification timestamp (timestamps are unreliable across systems).

---

## Earnings Detection Protocol

### Enhanced Mode (Financial Datasets MCP available)
1. Call `get_company_news(ticker, limit=10)`
2. Scan titles for keywords: "earnings", "quarterly results", "Q1/Q2/Q3/Q4", "EPS beat", "EPS miss", "results"
3. Check dates: if any earnings news within 30 days AND after `last_analysis_date` in snapshot → stale

### Standard Mode (Web search only)
1. Web search: `"{ticker}" earnings results site:prnewswire.com OR site:businesswire.com last:30d`
2. Web search: `"{ticker} Q" earnings date 2026`
3. If any results dated after snapshot `analysis_date` → stale

### Earnings Calendar Lookup (for upcoming earnings detection)
1. Web search: `"{ticker}" next earnings date`
2. Parse date from result
3. Store in `upcoming_catalysts` field of snapshot

---

## Delta Analysis Detection

Route to Delta Analysis path (§2.7) when user query contains ANY of:

**Korean triggers**: "지난 분석이랑", "이전 분석", "비교해줘", "지난번이랑", "전에 분석한 거랑", "변동사항", "뭐가 달라졌어", "업데이트된 게", "새로 바뀐 게"

**English triggers**: "what changed", "compare to last", "delta", "since last analysis", "what's different", "update since", "prior analysis"

---

## Session Context Triggers

Route to session context reuse when query contains ANY of (AND there is a completed analysis in the current session):

**Korean**: "그럼", "그 다음", "비교하면", "같이 보면", "그것도", "얘는"
**English**: "how about", "what about", "compare to", "vs", "versus", referencing a previously discussed ticker

---

## Reuse Decision Logic

```
Does snapshot exist for {ticker}?
  NO → Fresh start (Steps 1-10 fully)

  YES → Check earnings
    Earnings released after snapshot date?
      YES → Full re-analysis
      NO → Check age
        < 7 days?
          YES → Ask user: reuse or update?
            User says reuse → Load snapshot, display it, skip analysis
            User says update → Full re-analysis
        7-30 days?
          YES → Suggest delta update
            User accepts delta → Delta Analysis path (§2.7)
            User declines → Full re-analysis
        > 30 days?
          YES → Full re-analysis (no user prompt)
```

---

## Watchlist Scan Reuse Rules

For watchlist scan (abbreviated pipeline), more aggressive reuse:

| Condition | Action |
|-----------|--------|
| Snapshot < 24 hours old | Reuse entirely, no data collection |
| Snapshot 24h–7 days + no earnings | Price-only update (1 search query) |
| Snapshot > 7 days OR earnings detected | Full abbreviated pipeline (Steps 3/4 + condensed Step 5, no Step 6/7) |
