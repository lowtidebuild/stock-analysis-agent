# Data Manager — SKILL.md

**Role**: Step 10 (post-analysis persistence) + Workflow 3 (portfolio & watchlist management)
**Triggered by**: CLAUDE.md after Step 9 (quality check) for persistence; directly for Workflow 3 commands
**Reads**: run-local `analysis-result.json`, `output/watchlist.json`, `output/portfolio.json`
**Writes**: Snapshot files, `output/watchlist.json`, `output/portfolio.json`, `output/catalyst-calendar.json`
**References**: `references/snapshot-schema.md`, `references/watchlist-schema.md`, `references/portfolio-schema.md`

---

## Part A — Step 10: Post-Analysis Persistence

Run after Step 9 (quality check passes or flags applied).

### Step 10.1 — Save Snapshot

```bash
python .claude/skills/data-manager/scripts/snapshot-manager.py save \
  --ticker {ticker} \
  --data-file output/runs/{run_id}/{ticker}/analysis-result.json
```

Expected output: confirms `output/data/{ticker}/snapshots/{snapshot_id}/analysis-result.json` created and `output/data/{ticker}/latest.json` updated as a pointer.

If script fails because the input is not schema-compliant, run:

```bash
python .claude/skills/data-validator/scripts/validate-artifacts.py --artifact-type analysis-result --input output/runs/{run_id}/{ticker}/analysis-result.json
```

If legacy artifacts must be persisted temporarily, use `--skip-validation` explicitly and treat the snapshot as a compatibility fallback.

### Step 10.2 — Update Watchlist Entry (if ticker in watchlist)

Check if ticker exists in `output/watchlist.json`. If yes:

```bash
python .claude/skills/data-manager/scripts/watchlist-manager.py update-snapshot \
  --ticker {ticker} \
  --snapshot-path output/data/{ticker}/snapshots/{snapshot_id}/analysis-result.json
```

Use the `snapshot_path` returned by `snapshot-manager.py save`. Passing `latest.json` is accepted for compatibility, but the watchlist stores the resolved immutable snapshot path. This updates: `last_snapshot_path`, `last_analysis_date`, `last_rr_score`, `last_price`, `last_verdict`.

### Step 10.3 — Rebuild Catalyst Calendar

```bash
python .claude/skills/data-manager/scripts/catalyst-aggregator.py build
```

This reads all watchlist snapshot files and aggregates upcoming catalysts into `output/catalyst-calendar.json`.

### Step 10.4 — Confirm Persistence

Log:
```
=== Data Manager: Persistence Complete ===
Snapshot: output/data/{ticker}/snapshots/{snapshot_id}/analysis-result.json ✓
Latest pointer: output/data/{ticker}/latest.json ✓
Watchlist updated: {YES/NO — not in watchlist}
Catalyst calendar rebuilt: ✓ ({N} events)
```

---

## Part B — Workflow 3: Portfolio & Watchlist Management

### Command Pattern Recognition

Recognize these natural language commands and route to the correct script:

| Natural Language | Command | Script Call |
|-----------------|---------|------------|
| "AAPL 워치리스트 추가" / "Add AAPL to watchlist" | add | `watchlist-manager.py add --ticker AAPL --market US` |
| "삼성전자 워치리스트 추가" | add (KR) | `watchlist-manager.py add --ticker 005930 --market KR` |
| "AAPL 워치리스트에서 삭제" / "Remove AAPL" | remove | `watchlist-manager.py remove --ticker AAPL` |
| "워치리스트 보여줘" / "Show watchlist" | list | `watchlist-manager.py list` |
| "워치리스트 스캔" / "Scan watchlist" | scan | (see Step B.3 Scan Protocol) |
| "포트폴리오 등록" / "Register portfolio" | portfolio add | (see Step B.4 Portfolio Protocol) |
| "포트폴리오 분석" / "Portfolio analysis" | portfolio review | (see Step B.5 Portfolio Review) |
| "카탈리스트 캘린더" / "Catalyst calendar" | show calendar | `catalyst-aggregator.py show --days 30` |

### Step B.1 — Watchlist Add

1. Parse ticker and market from user command
2. Run `watchlist-manager.py add --ticker {ticker} --market {market}`
3. Confirm to user: "{ticker} ({market}) added to watchlist. Total: {N} tickers."
4. If >30 tickers: warn "워치리스트가 30개를 초과합니다. 스캔 성능이 저하될 수 있습니다."

Korean company names → 6-digit code lookup (see `ticker-resolution-guide.md`):
- 삼성전자 → 005930
- SK하이닉스 → 000660
- 네이버 → 035420
- 카카오 → 035720
- LG에너지솔루션 → 373220
- 현대차 → 005380
- POSCO홀딩스 → 005490
- 셀트리온 → 068270

### Step B.2 — Watchlist Remove

1. Run `watchlist-manager.py remove --ticker {ticker}`
2. Confirm to user: "{ticker} removed from watchlist."

### Step B.3 — Watchlist Scan Protocol

**Scan = lightweight update for all watchlist tickers.**

For each ticker in watchlist:
1. Load `last_snapshot_path` and check age
2. If age < 24 hours → SKIP (reuse existing data, do NOT re-collect)
3. If age 24h–7 days → QUICK_UPDATE: run minimal Steps 3+4 (price + news only)
4. If age > 7 days → ABBREVIATED_PIPELINE: Steps 3+4+simplified Step 5 (no deep analysis)
5. After update, run `watchlist-manager.py update-snapshot` for each ticker

**Abbreviated pipeline** (not full Workflow 1):
- Get current price
- Get 5 most recent news items
- Check for earnings since last snapshot → flag EARNINGS_UPCOMING if within 14 days
- Check price change > 5% → flag PRICE_MOVE_5PCT
- No scenarios, no R/R Score, no Variant View (data only)

After scan, display a summary table:

```
=== Watchlist Scan Summary ===
Scanned: {N} tickers | Skipped (fresh): {N} | Updated: {N}

Ticker   | Last R/R | Price    | Change  | Alerts
---------|----------|----------|---------|--------
AAPL     | 7.8      | $175.50  | +2.3%   | —
005930   | 5.1      | ₩74,500  | -1.2%   | STALE_30D
NVDA     | 9.2      | $875.00  | +8.1%   | PRICE_MOVE_5PCT

Catalyst calendar rebuilt: {N} events in next 30 days
```

### Step B.4 — Portfolio Registration

Accept these 3 input formats (from `portfolio-schema.md`):

**Format 1 — Inline chat**:
"AAPL 100주 $150, MSFT 50주 $380, 삼성전자 200주 72000원"

Parse each holding:
- Extract: ticker (or company name → resolve to ticker), shares (숫자 + 주), avg_cost (숫자 + $ or 원)
- Determine currency: $ → USD, 원/₩ → KRW
- Determine market: USD → US, KRW → KR
- Map Korean company names to 6-digit codes

**Format 2 — JSON**: Parse directly.

**Format 3 — CSV**: Parse as TSV/CSV.

After parsing:
1. Validate all tickers (attempt price lookup or web search)
2. Write to `output/portfolio.json` (full replace of holdings array)
3. Confirm: "포트폴리오 {N}개 종목 등록 완료. 포트폴리오 분석을 실행하시겠습니까?"

### Step B.5 — Portfolio Review

1. Read `output/portfolio.json`
2. For each holding:
   - Get current price (API or web)
   - Calculate: `current_value = shares × current_price`
   - Calculate: `unrealized_pnl = current_value - (shares × avg_cost)`
   - Calculate: `unrealized_pnl_pct = unrealized_pnl / (shares × avg_cost) × 100`
3. Compute portfolio-level metrics:
   - Total value in USD (convert KRW at current FX rate)
   - Total cost in USD
   - Total P&L in USD and %
   - Sector concentration %
   - Weighted R/R Score (weighted by position value)
4. Run abbreviated Mode C analysis per stock (no redundant data collection if recently analyzed)
5. Display portfolio summary + per-stock verdicts

**KRW/USD conversion**: Search `KRW USD exchange rate` for current rate. Tag with `[Portal]`.

---

## Completion Check — Step 10

- [ ] `snapshot-manager.py save` executed successfully
- [ ] Watchlist entry updated (if ticker in watchlist)
- [ ] `catalyst-aggregator.py build` executed
- [ ] Persistence confirmation logged

## Completion Check — Workflow 3

- [ ] Natural language command correctly routed to appropriate sub-operation
- [ ] Ticker resolved (including Korean company name → 6-digit code)
- [ ] Script executed (or manual fallback performed)
- [ ] User confirmation message provided
- [ ] watchlist.json / portfolio.json atomically updated
