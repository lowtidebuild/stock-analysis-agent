# Briefing Generator — SKILL.md

**Role**: Step 8 (Mode A) — Generate the Mode A Quick Briefing HTML file from analysis-result.json.
**Triggered by**: CLAUDE.md after Analyst Agent (Step 7) completes for Mode A
**Reads**: run-local `analysis-result.json`
**Writes**: `output/reports/{ticker}_A_{lang}_{YYYY-MM-DD}.html`
**References**: `references/analysis-framework-briefing.md`, `references/html-template.md` (this directory), `scripts/render-briefing.py`

---

## Instructions

### Step 8A.1 — Load Analysis Data

Read run-local `analysis-result.json`. Extract:
- `ticker`, `company_name`, `exchange`, `market`, `currency`
- `price_at_analysis`, `price_day_change`, `price_day_change_pct`
- `analysis_date`, `data_mode`, `output_language`
- `rr_score`, `verdict`
- `key_metrics` (top 3 for company type)
- `scenarios` (bull/base/bear)
- `top_risks[0]` (first risk only)
- `upcoming_catalysts[0]` (nearest catalyst)
- `sections.one_line_thesis`
- `sections.action_signal`
- `sections.timeline_past` (array of past events)
- `sections.timeline_future` (array of future events)
- `sections.pattern_detection` (optional)

### Step 8A.2 — Generate HTML

Build a self-contained HTML file using TailwindCSS via CDN. Structure:

```html
<!DOCTYPE html>
<html lang="{lang}">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{ticker} Quick Briefing — {date}</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css">
</head>
<body class="bg-gray-950 text-gray-100 min-h-screen">
```

#### Part 1 — Verdict Card

Layout: compact card with dark background, max-width 800px centered.

```
┌─────────────────────────────────────────────┐
│  {Company Name} ({TICKER})     {Exchange}    │
│  {Price} {change} ({change%})   {Date}       │
├─────────────────────────────────────────────┤
│  "{One-line thesis}"                         │
│                                              │
│  ┌──────────┐  ┌──────────┐                 │
│  │ VERDICT  │  │ R/R Score│                 │
│  │ {verdict}│  │  {score} │                 │
│  └──────────┘  └──────────┘                 │
│                                              │
│  ┌─────┐ ┌─────┐ ┌─────┐                   │
│  │KPI 1│ │KPI 2│ │KPI 3│                   │
│  │value│ │value│ │value│                   │
│  │[tag]│ │[tag]│ │[tag]│                   │
│  └─────┘ └─────┘ └─────┘                   │
│                                              │
│  🐂 Bull: {target} ({return%}) — {assumption}│
│  📊 Base: {target} ({return%}) — {assumption}│
│  🐻 Bear: {target} ({return%}) — {assumption}│
│                                              │
│  ⚠️ {Top risk with mechanism}                │
│                                              │
│  📅 Next: {catalyst} ({date})                │
│  → Action: {action signal}                   │
└─────────────────────────────────────────────┘
```

Color scheme (from dashboard-generator color-system.md):
- Verdict badge: green (Overweight), yellow (Neutral), red (Underweight)
- R/R Score badge: green (>3.0), yellow (1.0–3.0), red (<1.0)
- KPI tiles: gray-800 background, white text
- Source tags: same as Mode C (`[Filing]` blue, `[Portal]` gray, `[KR-Portal]` purple, `[Calc]` green, `[Est]` yellow)

#### Part 2 — Event Timeline

Vertical timeline layout with a center line:

```
┌─────────────────────────────────────────────┐
│  ◀ Past 90 Days                              │
│                                              │
│  ●─── {date} {event} {significance badge}    │
│       {1-sentence narrative}                 │
│  ●─── {date} {event}                         │
│       {narrative}                            │
│  ...                                         │
│                                              │
│  ══════ YOU ARE HERE ═════════════════════   │
│  {price} | R/R {score} | {verdict}           │
│                                              │
│  ●─── {date} {event} {significance badge}    │
│       {narrative + leading indicator}        │
│  ●─── {date} {event}                         │
│  ...                                         │
│                                              │
│  Forward 90 Days ▶                           │
│                                              │
│  {Pattern detection note if available}       │
└─────────────────────────────────────────────┘
```

Timeline node styling:
- Past events: left-aligned, gray-500 connector line
- "You Are Here": centered, bold, gold/amber accent
- Future events: left-aligned, blue-500 connector line
- Significance badges: high = red, medium = yellow, low = gray

#### Footer

Footer requirements:
- short disclaimer
- data source tags or visible confidence grade for each KPI tile
- analysis date shown as the as-of date
- generation note based on run-local `analysis-result.json`

### Step 8A.3 — Write File

Write to: `output/reports/{ticker}_A_{lang}_{YYYY-MM-DD}.html`

For scripted rerenders inside the critic patch loop, use:

```bash
python .claude/skills/briefing-generator/scripts/render-briefing.py \
  --input output/runs/{run_id}/{ticker}/analysis-result.json \
  --output output/reports/{ticker}_A_{lang}_{YYYY-MM-DD}.html
```

### Step 8A.4 — Chat Summary

After writing file, output to chat:

```
=== {TICKER} Quick Briefing ===
Verdict: {verdict} | R/R Score: {score} ({interpretation})
Action: {action signal}

→ HTML: output/reports/{ticker}_A_{lang}_{date}.html
→ "자세히 분석해줘" for full Mode C dashboard
```

---

## Completion Check

- [ ] analysis-result.json loaded with all Mode A fields
- [ ] HTML file generated with both parts (Verdict Card + Timeline)
- [ ] TailwindCSS + FontAwesome CDN links present
- [ ] Verdict and R/R Score badges colored correctly
- [ ] 3 KPI tiles with source tags or visible confidence grades
- [ ] 3 scenarios with company-specific assumptions
- [ ] Timeline has ≥3 past events and ≥2 future events
- [ ] Disclaimer present in footer
- [ ] Analysis date visible as the as-of date
- [ ] File written to correct path
- [ ] Chat summary outputted with file path and upgrade prompt
