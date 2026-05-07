# Release Notes — v2.1.0

**Release date**: May 7, 2026
**Tagline**: *Earnings preview, earnings review, and a way to see what changed since the last analysis — built for the seven days around an earnings release.*

---

## TL;DR

Three things you can do with v2.1.0:

1. **Run a dedicated earnings-window analysis with Mode E.** Within seven days of a print, the agent decides whether you need a Preview (consensus, options-implied move, watchpoints) or a Review (actual vs. consensus, segment breakdown, post-print action plan) — and writes whichever one fits.
2. **Re-run any analysis and see exactly what changed.** Every report opens with a delta banner: R/R score change, target price change, verdict change, and the diff on the risk list — all measured against your most recent snapshot for that ticker.
3. **Use a Mode C report as a real reconciled valuation document.** Peer tables are populated from real fetched numbers, a 12-month catalyst timeline shows when events cluster, and a Valuation Bridge widget reconciles DCF, peer multiples, analyst consensus, and the base scenario into a single weighted fair value. Mode B comparisons also include macro context for sector pairs.

If any of those sound useful, read on.

---

## What you can do (capabilities introduced in v2.1.0)

### 1. Mode E — Earnings Preview & Review

Mode E is a dedicated analysis mode for the seven-day window around an earnings release. The agent auto-detects which side of the earnings date you are on and writes the matching report.

**The two windows:**

| Window | Mode | What you get |
|---|---|---|
| **D-7 to D-1** (week before the print) | **Preview** | Consensus EPS & revenue with the high/median/low distribution, options-implied 1-day move, last 8 quarters of beat/miss history (hit rate + average surprise), 4–5 specific watchpoint questions for the print, pre-mortem scenarios, position sizing guidance |
| **D to D+3** (day of and three days after) | **Review** | Actual vs. consensus table, segment revenue breakdown, guidance change summary (FY EPS pre/post), answers to the watchpoints flagged in Preview, thesis impact, light verdict + recommendation on when to re-run Mode C, post-print action plan (Hold / Trim / Hedge / Add) with entry and exit levels |

**Sample Preview workflow.** AAPL is reporting next Wednesday. On Tuesday, `AAPL 프리뷰` or `AAPL earnings preview` returns:

- Consensus EPS $1.62, revenue $89.4B (high/median/low spread)
- Options-implied 1-day move: ±3.2%
- Last 8 quarters: 75% hit rate, average surprise +5.9%
- Watchpoint questions like "Can Services growth hold +14% YoY at this gross margin?"
- Pre-print position recommendation (e.g. Hold + optional straddle for catalyst traders)

**Sample Review workflow (real validated case, AMD Q1 2026, D+2).** Two days after AMD's May 5 print, `AMD review` produced a 33KB HTML report with:

- **Print Snapshot**: EPS $1.37 vs. $1.28 consensus (+7.0% beat); revenue $10.25B vs. $9.89B (+3.6% beat)
- **Segment breakdown**: Data Center $5.8B (+57% YoY), Client $2.88B (+26%), Gaming $720M (+11%), Embedded $873M (+6%)
- **Guidance change**: Q2 revenue guide $11.2B vs. $10.5B consensus (+6.7%); GM 56%; Server CPU TAM raised from $60B to $120B
- **Light verdict**: outdated_flag set, with recommendation to re-run full Mode C in the D+4 to D+7 window
- **Post-print action plan**: at the close of $421.39, no new entry recommended; existing holders Trim 1/3 at $470, Trim 1/3 at $525, Stop at $360

The agent reads the earnings calendar, classifies the window, and runs Preview or Review automatically — see Quick start below for trigger phrases.

### 2. Mode E accessibility layer

Every Mode E report ships with four readability features as part of the standard template:

- **Pinned TL;DR at the top** — three bullets, designed to deliver the verdict in 30 seconds
- **Segment revenue breakdown table** — every reporting segment with revenue, YoY %, share of total, and operating margin
- **"For a regular investor" callouts** — each section explains why the number matters and how to read it, in plain English or plain Korean
- **Inline glossary** — 10 commonly-confused terms (Surprise %, Forward P/E, TAM, Multiple Re-rating, etc.) defined within the report

### 3. Auto Delta banner — every re-analysis shows what changed

When you re-analyze a ticker that has a stored snapshot, every report (Mode A, B, C, D, or E) opens with a delta banner showing:

- **R/R score change** — e.g. "1.42 → 1.69 (+0.27)"
- **Base target price change** — e.g. "$385 → $418 (+8.6%)"
- **Verdict change** — e.g. "관찰 (유지)" if unchanged, or "Hold → Buy" if it moved
- **Risk list diff** — newly added risks (e.g. "AI Capex 회수 지연"), risks resolved

**Sample workflow.** Analyze AAPL in April; re-run in May. The May report opens with the delta block above the executive summary — no extra command, no separate diff tool. Append `--no-delta` to suppress the banner for a single run.

The banner answers a question that is hard to answer manually: *did the thesis actually change, or am I reacting to noise?* If R/R moved 0.05, it is noise. If it moved 0.50 with three new risks, the thesis shifted.

### 4. Mode B — Macro context in peer comparison

A Mode B comparison (2 to 5 tickers in the same sector) ships with a macro context block: 3 to 5 key macro series for the company type, plus a per-stock narrative on macro exposure.

**Sample usage.** Trigger `삼성전자 vs SK하이닉스 비교`. The Mode B report includes:

- **Macro snapshot**: 10Y Treasury 4.45%, USD/KRW 1380, Memory ASP "Strong"
- **Per-stock macro exposure narrative**:
  - 삼성전자 (Beta 1.3): Memory + Mobile + VD diversification means USD/KRW strength partly offsets through FX gains on the consumer side
  - SK하이닉스 (Beta 2.0): single-bet exposure to memory means 100% leverage to the ASP cycle; +50bp rate move has historically driven an additional 10–15% drawdown

This is the difference between *"both are memory stocks, looks similar"* and *"these are not interchangeable bets."*

### 5. Mode C — Peer mini-pipeline (real numbers in the peer table)

The Mode C peer table is populated by an abbreviated yfinance fetch on each peer (5–7 metrics, 24-hour cache).

**Sample output for a GOOGL Mode C report:**

| Peer | P/E | EV/EBITDA | Op. Margin |
|---|---|---|---|
| MSFT | 31.5x | 22.5x | 44.5% |
| META | 24.0x | 16.5x | 38% |
| AMZN | 33.0x | 19.0x | 11% |
| AAPL | 30.5x | 22.0x | 31% |

Cells where the peer fetch failed display a clear flag rather than a fabricated number — *blank > wrong number* still applies. The 24-hour cache means a follow-up analysis on a related ticker reuses the same peer data instantly.

### 6. Mode C — 12-month Catalyst Timeline

Mode C reports include a horizontal-bar timeline of the next 12 months of catalysts, color-coded by category:

- **Earnings** (blue) — quarterly prints
- **Regulatory** (red) — FDA decisions, antitrust rulings, FOMC
- **Product** (green) — major launches, GTC keynotes, Investor Days
- **Macro** (yellow) — CPI releases, jobs reports, key central-bank meetings
- **Other** (grey) — legal verdicts, dividend declarations, special meetings

Bar length encodes duration: a single-date event renders as a point; a quarter-long event renders as a bar. Same-period events render side-by-side so clusters are visible at a glance — e.g. "Q4 2026 has the earnings print, the DC Circuit appeal, and the Gemini product event all in the same window — concentrated volatility band."

If the peer mini-pipeline populated peer data, peer catalysts also appear on the same timeline.

### 7. Mode C — Valuation Bridge widget

A Mode C report can produce, under different assumptions, a DCF fair value pointing one direction and a base-case scenario target pointing another. The Valuation Bridge widget reconciles all anchors on a single chart and produces one weighted-average fair value, with a paragraph explaining the weighting.

**Sample reconciliation (real case, GOOGL):**

- **DCF fair value**: $241 (−37.9% from current $388)
- **Peer multiples fair value**: $300 (−22.8%)
- **Analyst consensus target**: $428.50 (+10.3%)
- **Our base scenario target**: $418 (+7.6%)
- **Weighted average**: $346.84 (−10.7%) — *"market is pricing more optimism than our base case"*

The report includes a written paragraph explaining the weighting choice ("DCF de-weighted because terminal value sensitivity is high; peer multiples up-weighted given a symmetric peer set"). The reader does not have to choose between conflicting anchors — the report does the reconciliation.

---

## Quick start

| What you want | Trigger phrase | Output mode | Output location |
|---|---|---|---|
| Earnings preview (within D-7 to D-1) | `AAPL 프리뷰`, `AAPL earnings preview` | Mode E (Preview) | `output/reports/AAPL_E_*.html` |
| Earnings review (within D to D+3) | `AMD review`, `AMD 실적 분석` | Mode E (Review) | `output/reports/AMD_E_*.html` |
| Sector pair comparison + macro | `삼성전자 vs SK하이닉스 비교` | Mode B | `output/reports/{T1}_{T2}_B_*.html` |
| Full dashboard with all v2.1 widgets | `GOOGL 분석해줘`, `analyze GOOGL` | Mode C | `output/reports/GOOGL_C_*.html` |
| Re-run with delta banner | Same trigger as before — banner is automatic | Any mode | Same path |
| Suppress delta banner | Append `--no-delta` to trigger | Any mode | Same path |

The agent picks Mode E automatically when you use an earnings-window keyword ("earnings", "어닝", "프리뷰", "review", "실적") and the ticker has a print within seven days. Outside that window, the same query routes to Mode C.

---

## Tested workflows

### AMD Q1 2026 Review (D+2, validated 2026-05-07)

After AMD's May 5 print, a `AMD review` request produced the 33KB Mode E Review described above: print snapshot, segment breakdown, guidance change, light verdict with `outdated_flag`, and the post-print action plan with entry/trim/stop levels — end-to-end on real fetched data.

### 삼성전자 vs SK하이닉스 (Mode B + macro)

`삼성전자 vs SK하이닉스 비교` produces the Mode B comparison with macro snapshot, per-stock beta-weighted macro exposure narrative, and side-by-side P/E / margin / growth panels — making differential macro sensitivity explicit.

### GOOGL Mode C (peer pipeline + Valuation Bridge)

`GOOGL 분석해줘` produces a Mode C dashboard with a peer table populated from real numbers (MSFT / META / AMZN / AAPL), the 12-month catalyst timeline, and the Valuation Bridge reconciling DCF / peer / consensus / base-case anchors into a single weighted fair value.

---

## Under the hood (developer notes)

- **Tests**: 256 → 262 passing. Coverage spans schema validation, renderer contract tests, peer-fetch determinism, and earnings-window detection.
- **Architecture additions**:
  - `earnings-window-detector` skill (D-7 to D+3 detection from the calendar)
  - `peer-fetch` mini-pipeline (5–7 metrics per peer, 24-hour cache, blank-on-failure)
  - `options-fetcher` (Mode E Preview implied 1-day move)
  - `valuation-bridge` widget renderer (weighted reconcile + justification paragraph)
  - `delta-banner` block (diffs against `output/data/{ticker}/latest.json`)
- **Phases shipped**: 6 (A through F), each through dual-stage spec compliance + code quality review.
- **Sessions**: 4 working sessions across the v2.1 arc.
- **Trust boundary unchanged**: all fetched content still flows through `tools/prompt_injection_filter.py`; Mode E artifacts carry the same `_sanitization` block as Mode C artifacts.

---

## How to upgrade

```bash
git pull origin main
```

No dependency changes, no migration script. Existing reports in `output/reports/` are not rewritten — new analyses pick up the new layout. The delta banner activates the first time you re-analyze a ticker with a snapshot under `output/data/{ticker}/latest.json`.

---

## Coming next

Two items on the near-term roadmap (no committed dates):

- **Backtesting framework** — replay any historical analysis ("what would the agent have said about TSLA in Jan 2024?") and score the verdict against the actual one-year return. Useful for self-auditing thesis accuracy.
- **MINOR maintenance pass** — catalyst-aggregator deduplication, FRED cache TTL, and peer-cache invalidation rules.

If either would be specifically useful for your workflow, open an issue.

---

## Disclaimer

This agent produces investment research, not investment advice. Every output ships with the standard disclaimer: *for informational purposes only, not investment advice.* Always do your own due diligence and consider consulting a licensed advisor before making any trade.
