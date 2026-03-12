# Staleness Checker — SKILL.md

**Role**: Step 0 — Evaluate whether existing snapshot data is fresh enough to reuse, or whether new data collection is required.
**Triggered by**: CLAUDE.md at the start of Workflow 1 (Single Stock Analysis) and Workflow 3 (Watchlist Scan)
**Reads**: `output/data/{ticker}/latest.json`, staleness rules from this file
**Writes**: Nothing (read-only evaluation; result is reported inline to orchestrator)
**References**: `references/staleness-rules.md`

---

## Instructions

### Step 0.1 — Check for Existing Snapshot

Check if `output/data/{ticker}/latest.json` exists.

```
IF file does not exist:
    → Routing decision: FRESH_COLLECTION (no cached data)
    → Proceed to Step 1 (query-interpreter)
```

If file exists, read it and extract:
- `analysis_date` (YYYY-MM-DD)
- `data_mode` (enhanced / standard)
- `output_mode` (A / B / C / D)
- `rr_score`
- `verdict`

### Step 0.2 — Calculate Staleness

Calculate `days_since_analysis = today - analysis_date`.

Apply staleness rules:

| Days Since Analysis | Data Mode | Routing Decision |
|--------------------|-----------|-----------------|
| ≤ 1 day (same day) | Any | REUSE — skip Steps 1–5, proceed directly to output generation |
| 2–6 days | Enhanced | DELTA_FAST — re-collect price only (Step 3 minimal), regenerate output |
| 2–6 days | Standard | DELTA_FAST — run web search Step 4 only (skip full re-research) |
| 7–29 days | Any | STALE — full re-collection required (Steps 1–9) |
| ≥ 30 days | Any | VERY_STALE — full re-collection + flag STALE_30D in watchlist |

### Step 0.3 — Earnings Detection (Override Staleness Rules)

Regardless of staleness, check if an earnings event occurred since `analysis_date`:

**Enhanced Mode check**: Call `get_company_news(ticker, limit=5)`. If any news title contains earnings keywords, flag EARNINGS_OVERRIDE.

**Standard Mode check**: Search `"{ticker}" earnings results Q{N} 2026`. If results dated after `analysis_date` contain earnings data, flag EARNINGS_OVERRIDE.

Earnings keywords: `earnings`, `quarterly results`, `Q1`, `Q2`, `Q3`, `Q4`, `revenue beat`, `EPS beat`, `revenue miss`, `실적`, `분기`, `매출`, `영업이익`

```
IF EARNINGS_OVERRIDE:
    → Routing decision: FULL_COLLECTION regardless of days_since_analysis
    → Reason: earnings data fundamentally changes valuation inputs
```

### Step 0.4 — Delta Analysis Detection

Check if the user's query contains delta analysis trigger keywords:

**English triggers**: "compare", "vs last time", "since last analysis", "what changed", "update", "delta", "difference from before", "how has it changed"

**Korean triggers**: "이전이랑", "지난번이랑", "비교해줘", "달라진 것", "바뀐 것", "업데이트", "뭐가 달라졌어", "전이랑 비교"

```
IF delta keywords detected AND snapshot exists:
    → Set delta_mode = true
    → After new analysis completes (Steps 1–9), run:
      python delta-comparator.py compare --ticker {ticker} --old-date {previous_date} --new-date latest
    → Prepend delta report to output
```

### Step 0.5 — Session Context Check

Before any file checks, verify session context:

```
IF ticker was analyzed in the current session:
    → Use session-cached validated data (skip Steps 3–5)
    → Only regenerate output if different output_mode requested
    → Log: "Using session-cached data for {ticker} from {session_time}"
```

Session context keywords: "same stock", "same company", "just analyzed", 같은 종목", "방금 분석한"

### Step 0.6 — Report Routing Decision

Output a concise routing decision block:

```
=== Staleness Check: {TICKER} ===
Snapshot found: {YES/NO}
Analysis date: {date or N/A}
Days since: {N or N/A}
Earnings override: {YES/NO}
Delta mode: {YES/NO}

→ Routing: {REUSE / DELTA_FAST / STALE / FRESH_COLLECTION / EARNINGS_OVERRIDE}
→ Action: {brief description of what will happen next}
```

---

## Watchlist Scan Mode

When called from Workflow 3 (watchlist scan), apply these rules per ticker:

| Condition | Action |
|-----------|--------|
| `latest.json` age < 24 hours | SKIP — reuse existing data |
| `latest.json` age 24h–7 days | QUICK_UPDATE — price + news only |
| `latest.json` age > 7 days | FULL_SCAN — abbreviated pipeline (Steps 3+4+simplified 5) |
| No `latest.json` | FRESH — full pipeline |

For watchlist scan, do NOT run full Steps 6–9 (analysis generation). Only collect data and update alert flags.

---

## Completion Check

- [ ] Confirmed whether `output/data/{ticker}/latest.json` exists
- [ ] Calculated days_since_analysis if snapshot exists
- [ ] Applied staleness rules to determine routing
- [ ] Checked for earnings override condition
- [ ] Checked for delta analysis trigger in user query
- [ ] Checked session context for recently analyzed tickers
- [ ] Reported routing decision with clear action statement
