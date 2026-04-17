# Analysis Framework — Mode A (Quick Briefing)

This file defines the analytical requirements for Mode A output. The Analyst agent reads this file when `output_mode = "A"`.

---

## Purpose & Scope

Mode A produces a single-page HTML briefing — the fastest output mode. It combines a quick verdict card with a 180-day event timeline. Designed for screening before a full Mode C deep dive.

**Output target**: HTML file with 2 parts (Verdict Card + Event Timeline)
**Output format**: HTML (TailwindCSS via CDN, no Chart.js needed)
**Output path**: `output/reports/{ticker}_A_{lang}_{YYYY-MM-DD}.html`
**Template**: `.claude/skills/briefing-generator/SKILL.md` (for execution)
**Total word count**: 500–700 words
**Generation time target**: 2–3 minutes

---

## Required Inputs

- run-local `validated-data.json` — validated metrics with confidence grades
- run-local `research-plan.json` — company type, output mode, analysis framework path
- `output/data/{ticker}/tier2-raw.json` — web research results (for timeline events)
- `output/data/{ticker}/tier1-raw.json` — (Enhanced Mode only, for precise metrics)
- `output/data/{ticker}/dart-api-raw.json` — (Korean stocks only)

---

## Part 1 — Quick Verdict Card (~200 words)

### 1.1 — One-Line Thesis (20 words max)

A single sentence capturing the investment thesis. Must pass the competitor replacement test.

**Good**: "Market prices Samsung as a commodity DRAM maker, missing the HBM monopoly driving 40%+ margins."
**Bad**: "Strong company with good growth potential in a large market."

### 1.2 — Verdict Badge + R/R Score

- Verdict: Overweight / Neutral / Underweight (비중확대 / 중립 / 비중축소)
- R/R Score: single number with color (green >3.0, yellow 1.0–3.0, red <1.0)
- Use same R/R formula as Mode C/D

### 1.3 — KPI Tiles (3 only)

Select the 3 most important metrics for this company type:

| Company Type | KPI 1 | KPI 2 | KPI 3 |
|-------------|-------|-------|-------|
| Technology/Platform | P/E | Revenue Growth YoY | FCF Yield |
| Industrial/Manufacturing | EV/EBITDA | Operating Margin | Net Debt/EBITDA |
| Financial | P/B | ROE | Dividend Yield |
| Biotech/Pharma | EV/Revenue | Cash Runway (months) | Pipeline Value |
| Consumer | P/E | Revenue Growth YoY | Gross Margin |
| Energy | EV/EBITDA | FCF Yield | Dividend Yield |
| Korean (default) | PER | 영업이익률 | 외국인지분율 |

Each tile shows: metric name, value, source tag, grade badge.

### 1.4 — Scenario Summary (3 lines)

One line per scenario:
```
🐂 Bull: ₩85,000 (+22%) — HBM 점유율 60% 달성, AI capex 사이클 지속
📊 Base: ₩72,000 (+3%) — 현재 점유율 유지, DRAM 가격 안정
🐻 Bear: ₩55,000 (-21%) — 중국 경쟁 심화, AI capex 둔화
```

Probabilities shown inline. Key assumption must be company-specific.

### 1.5 — Top Risk (1 only)

The single highest-impact risk with condensed mechanism chain:
```
⚠️ 중국 CXMT의 HBM3 양산 성공 → SK하이닉스 점유율 10%p 하락 → EBITDA -15% → 목표 P/E 하향
```

One sentence. Must have causal chain (event → impact → price effect).

### 1.6 — Next Catalyst + Action Signal

- Next dated catalyst with significance
- Action signal: one sentence ("현재가 매수 적정" / "실적 확인 후 진입" / "₩X 이하 매수 대기")

---

## Part 2 — Event Timeline (~300–500 words)

### 2.1 — Past 90 Days (backward-looking)

Collect from tier2-raw.json (news, filings) and tier1-raw.json (insider trades, SEC filings):

Event types to include:
- Earnings releases with beat/miss indicator
- SEC/DART filings (10-K, 10-Q, 사업보고서, 분기보고서)
- Insider transactions (significant buys/sells only, >$100K or >1억원)
- Analyst upgrades/downgrades
- Price moves >5% in a single day (with identified cause)
- Material corporate actions (M&A, buyback announcements, dividend changes)

For each event: date, event description, significance (high/medium/low), 1-sentence narrative.

Maximum 8 events. Prioritize by significance.

### 2.2 — Current Snapshot ("You Are Here")

- Current price with day change
- R/R Score badge
- Verdict badge
- Data confidence grade

### 2.3 — Forward 90 Days (forward-looking)

From catalyst calendar, research-plan, and web research:

- Confirmed earnings dates
- Known regulatory decisions / FDA dates
- Product launches / conferences / investor days
- DART filing deadlines (Korean stocks)
- Analyst day / guidance updates

For each: date, event description, expected significance, leading indicators to watch.

Maximum 5 forward events.

### 2.4 — Pattern Detection (optional)

If sufficient historical data available (4+ quarters):
- Earnings reaction pattern: "이 종목은 최근 4분기 중 3분기에서 실적 발표 후 상승"
- Seasonal patterns: "Q4 historically strongest quarter (3yr avg: +8% revenue QoQ)"

Only include if data supports the claim. Do not fabricate patterns.

---

## Chat Summary (delivered alongside HTML file)

After generating the HTML file, output a brief chat summary:

```
=== {TICKER} Quick Briefing ===
Verdict: {Overweight/Neutral/Underweight} | R/R Score: {X.X} ({Attractive/Neutral/Unfavorable})
Action: {one-line action signal}

→ HTML: output/reports/{ticker}_A_{lang}_{date}.html
→ "자세히 분석해줘" for full Mode C dashboard
```

---

## What Mode A Does NOT Include

These are covered by Mode C/D — do NOT generate for Mode A:
- Full Variant View (Q1–Q5) — only the one-line thesis
- 8-quarter financial tables
- SOTP valuation breakdown
- Quality of Earnings / EBITDA Bridge
- Peer comparison table
- Analyst coverage distribution
- Chart.js visualizations
- Portfolio strategy section
- "What Would Make Me Wrong" section

---

## Anti-Generic Enforcement

Same rules as Mode C/D apply:
- One-line thesis must pass competitor replacement test
- Scenario assumptions must be company-specific
- Risk must have mechanism chain
- No banned phrases without quantification

The 200-word limit forces natural specificity — no room for generic filler.

---

## Mode A Minimum Quality Gates (self-check)

- [ ] One-line thesis present and passes competitor replacement test
- [ ] R/R Score computed correctly (formula matches)
- [ ] 3 KPI tiles have source tags and correct grades
- [ ] All 3 scenarios have company-specific assumptions
- [ ] Probabilities sum = 100%
- [ ] Top risk has causal chain
- [ ] ≥3 past events in timeline
- [ ] ≥2 forward events in timeline
- [ ] Disclaimer present
- [ ] Total word count 500–700
