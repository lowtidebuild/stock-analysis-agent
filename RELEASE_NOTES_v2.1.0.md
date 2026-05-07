# Release Notes — v2.1.0

**Release date**: May 7, 2026
**Tagline**: *Earnings season, finally readable. Plus: every report now remembers what it told you last time.*

---

## TL;DR

Three things you should care about, even if you skip everything else below:

1. **Mode E is new.** A dedicated mode for the seven-day window around an earnings release. Tells you what to watch for *before* the print, and what actually changed *after* the print — written for humans, not for analysts.
2. **Every report now opens with "What changed since last time."** Re-run AAPL, NVDA, or 삼성전자 and you immediately see the delta in R/R score, target price, verdict, and risk list.
3. **Mode C reports got five upgrades.** Real peer numbers, not placeholders. A 12-month catalyst timeline. A "valuation bridge" that reconciles DCF vs. peer multiples vs. analyst targets vs. our base case in one chart. And Mode B comparisons now include macro context so you can see *why* one stock moves more than another when rates change.

If any of those sound useful, read on.

---

## What's new

### 1. Mode E — Earnings Preview & Review (the big one)

A new analysis mode dedicated to the earnings window. The agent **auto-detects** which side of the earnings date you are on:

| Window | Mode | What you get |
|---|---|---|
| **D-7 to D-1** (week before) | **Preview** | Consensus EPS & revenue, options-implied 1-day move, last 8 quarters of beat/miss history, 4–5 specific watchpoint questions for the print, pre-mortem scenarios, position sizing guidance |
| **D to D+3** (day of and three days after) | **Review** | Actual vs. consensus table, guidance change (FY EPS pre/post), answers to the watchpoints you flagged in Preview, thesis impact, light verdict update + recommendation to re-run Mode C, post-print actions (Hold / Trim / Hedge / Add) with entry and exit levels |

**Why it matters for you**

Earnings windows are where retail investors lose the most money — buying right before the print, panic-selling right after, missing the actual signal in the guidance. Mode E is built for that exact moment.

**Real example** — AMD Q1 2026, two days after the print: the stock had jumped +18.61% overnight on a Data Center beat. A normal Mode C report would have just said "stock is up, multiple has expanded." The Mode E Review broke down which segment drove it (Data Center revenue +57% YoY), what guidance changed for the rest of the year, which of our pre-print watchpoints actually mattered, and whether a +18% post-print pop is something to chase or fade.

**How to trigger it**

Just say `AMD 어닝 분석해줘` or `Analyze AMD earnings` within seven days of an earnings date. The agent detects the window automatically and picks Preview or Review.

**Accessibility layer (added May 7, 2026)**

After we tested Mode E on a real earnings call, the first feedback was *"too dense, I can't follow this without a finance background."* So we added four things to every Mode E report:

- **Pinned TL;DR at the top** — three bullets, 30 seconds to the bottom line
- **Segment revenue breakdown table** — Data Center / Client / Gaming / etc., each with revenue, YoY %, share of total, and operating margin
- **"For a regular investor" callouts** — every section has a plain-Korean / plain-English explanation of *why this number matters*
- **Glossary** — 10 jargon terms (Surprise %, Forward P/E, TAM, Multiple Re-rating, etc.) defined inline so you don't need to Google anything mid-read

The report grew from 22KB to 33KB — but every empty cell is now filled in, and a non-finance reader can actually finish it.

---

### 2. Auto Delta banner — every report remembers last time

**Before** — Each analysis was a standalone snapshot. If you analyzed NVDA last week and again today, you had to manually compare the two reports to see what changed.

**After** — Every report now opens with a delta banner showing four things:

- **R/R score change** — e.g. "1.42 → 1.69 (+0.27)"
- **Target price change**
- **Verdict change** (e.g. Hold → Buy)
- **Risk list diff** — newly added risks, risks that resolved

**How to use it**

Nothing to do. It runs automatically on any re-analysis where a previous snapshot exists. To turn it off for a specific run, add the `--no-delta` flag.

**Why it matters** — The hardest question in stock research is "did the thesis actually change, or am I just reacting to noise?" The delta banner forces an answer: if R/R moved 0.05, you're noise-trading; if it moved 0.50 with three new risks, the thesis genuinely shifted.

---

### 3. Mode B — Macro context in peer comparison

**Before** — A 2-stock Mode B comparison (e.g. 삼성전자 vs. SK하이닉스) showed P/E, margins, and growth side-by-side. It did not show *why* the two stocks behave differently when macro conditions move.

**After** — Mode B now includes a light macro context block: 3–5 key macro series for the company type, plus a per-stock macro exposure narrative.

**Real example** — 삼성전자 (Beta 1.3) vs. SK하이닉스 (Beta 2.0): the new macro block tells you that on a +50bp rate hike, SK하이닉스historically moves roughly 1.5x as much as 삼성전자, and explains why (HBM concentration, customer base, balance sheet leverage). That's the difference between *"both are memory stocks, looks similar"* and *"these are not interchangeable bets."*

**How to use it**

Trigger as before: `삼성전자 vs SK하이닉스 비교`. The macro block appears automatically in any Mode B output.

---

### 4. Mode C — Peer mini-pipeline (real numbers, not placeholders)

**Before** — A Mode C report on NVDA showed a "Peer Comparison" table for MSFT / META / AMZN / AAPL — but the cells were `[Est]` placeholders, because we only collected real data for the subject ticker.

**After** — Peer tickers now go through an abbreviated data fetch via yfinance (5–7 metrics per peer, 24-hour cache) and land in the table as real Portal-grade numbers.

You will see:

- Real P/E, EV/EBITDA, operating margin, revenue growth, gross margin for each peer
- A clear `⚠️` flag if any peer's data was unavailable (no fabricated numbers — *blank > wrong number* is still the rule)
- A 24-hour peer cache so re-running the same analysis doesn't re-fetch unnecessarily

**Why it matters** — Peer comparison is the second-most-important section of any equity report (after the thesis itself). If those numbers are estimates, the whole comp set is fiction. They are now real.

---

### 5. Mode C — 12-month Catalyst Timeline

**Before** — The "Upcoming catalysts" section was a bulleted list of five items in chronological order. Easy to skim, hard to spot clusters.

**After** — A 12-month Gantt-style visual timeline with five color-coded categories:

- **Earnings** (e.g. Q2 print, Q3 print)
- **Regulatory** (e.g. FDA decision, antitrust ruling, FOMC)
- **Product** (e.g. iPhone launch, GTC keynote, Investor Day)
- **Macro** (e.g. CPI release, jobs report)
- **Other** (e.g. legal verdict, dividend declaration)

If the peer mini-pipeline (Phase D) populated peer data, **peer catalysts also appear on the same timeline** — so you can see when the subject company's earnings clusters with peer earnings, or when a regulatory event affects multiple holdings at once.

**Why it matters** — Catalyst clustering is a real risk. Buying NVDA the week before its earnings, MSFT's earnings, *and* a Fed meeting is not three independent decisions — it's one big macro bet. The timeline makes the cluster visible.

---

### 6. Mode C — Valuation Bridge widget

**Before** — A Mode C report could simultaneously show a DCF fair value implying −38% downside and a base-case scenario target implying +7% upside. Both were technically correct under different assumptions, but the report did not reconcile them. The reader was left to choose.

**After** — A new "Valuation Bridge" section reconciles four anchors into a single weighted-average fair value, with a written paragraph explaining the weighting choice:

| Anchor | What it measures |
|---|---|
| **DCF fair value** | Discounted cash flow under our base assumptions |
| **Peer multiples fair value** | Implied price applying peer-median P/E and EV/EBITDA |
| **Analyst consensus target** | Street median 12-month target |
| **Our base scenario target** | Our own scenario-weighted 12-month target |

The widget visually shows where the four anchors land relative to today's price, then lands on a weighted average — with a paragraph explaining *why* (e.g. "DCF de-weighted because terminal value sensitivity is high; peer multiples up-weighted given symmetric peer set").

**Why it matters** — The most common reader complaint about valuation sections is "the numbers contradict each other and nobody admits it." The Valuation Bridge admits it, then resolves it on the page.

---

## How to upgrade

```bash
git pull origin main
```

That's it. No dependency changes, no migration script. All previously-generated reports continue to work; the delta banner activates the next time you re-analyze a ticker that already has a snapshot.

Old report HTMLs in `output/reports/` are not rewritten — only new analyses pick up the new layout.

---

## What's coming next (preview)

We're not committing to dates, but the next two items on the roadmap:

- **Backtesting framework** — replay any historical analysis ("what would the agent have said about TSLA in Jan 2024?") and score the verdict against the actual one-year return. Useful for self-auditing thesis accuracy.
- **MINOR maintenance pass** — a few rough edges around catalyst-aggregator deduplication, FRED cache TTL, and peer-cache invalidation rules.

If either of those would be useful for you specifically, open an issue.

---

## Acknowledgments — tested with

This release was end-to-end validated against **AMD Q1 2026 earnings (D+2 Review window)**. The accessibility layer redesign was driven directly by the user feedback from that test ("compact and hard to follow without a finance background"). Without that real-world stress test, Mode E would have shipped as v1 (22KB, dense, half-empty cells) instead of v2 (33KB, complete, readable by non-specialists).

**Quick stats for this release:**

- **37 commits** since v1.1.0
- **+127 tests** (135 → 262, +94%)
- **81 files changed**, +16,935 / −2,159 lines
- **6 phases** shipped (A through F), all passing dual-stage spec compliance + code quality review

---

## Disclaimer

This agent produces investment research, not investment advice. Every output ships with the standard disclaimer: *for informational purposes only, not investment advice.* Always do your own due diligence and consider consulting a licensed advisor before making any trade.
