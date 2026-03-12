# Mode B — Comparative Matrix Output Template

Mode B produces an HTML file with a peer comparison matrix. Output path: `output/reports/{tickers}_B_{lang}_{YYYY-MM-DD}.html`

Example: `output/reports/AAPL_MSFT_GOOGL_B_EN_2026-03-12.html`

**Design**: Professional light theme matching Mode C. White cards, subtle shadows, Inter font. Blue primary, green/red for semantic values only.

---

## HTML Structure Overview

```html
<!DOCTYPE html>
<html lang="{en/ko}">
<head>
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/css/all.min.css">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
  <!-- For Korean: add Noto Sans KR -->
  <title>Peer Comparison: {ticker list} | {YYYY-MM-DD}</title>
  <style>
    * { font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Noto Sans KR', sans-serif; }
    .card { background: #fff; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.06); transition: transform 0.2s, box-shadow 0.2s; }
    .card:hover { transform: translateY(-2px); box-shadow: 0 4px 14px rgba(0,0,0,0.1); }
    .stat-card { border-left: 4px solid #3b82f6; }
    ::-webkit-scrollbar { width: 6px; }
    ::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 3px; }
  </style>
</head>
<body class="bg-gray-50 text-gray-800 min-h-screen">

  <!-- Section 1: Header -->
  <!-- Section 2: Comparison Summary Table -->
  <!-- Section 3: Scenario Comparison -->
  <!-- Section 4: R/R Score Ranking -->
  <!-- Section 5: Best Pick Recommendation -->
  <!-- Section 6: Key Differentiators -->
  <!-- Section 7: Disclaimer -->

</body>
</html>
```

---

## Section 1 — Header

```html
<header style="background: linear-gradient(135deg, #0d1b38 0%, #1e3f80 30%, #2a56b0 60%, #3367d6 100%);">
  <div class="max-w-7xl mx-auto px-4 sm:px-6 py-8">
    <h1 class="text-3xl font-bold text-white tracking-tight mb-1">Peer Comparison</h1>
    <p class="text-blue-200 text-sm">{ticker1} vs {ticker2} vs {ticker3} · {sector/theme} · {YYYY-MM-DD}</p>
    <div class="flex flex-wrap gap-2 mt-3">
      <!-- Data mode badge per ticker -->
      {DATA_MODE_BADGES}
    </div>
  </div>
</header>
```

Data mode badge colors (on dark header):
- Enhanced Mode: `bg-green-500/20 text-green-200 text-xs px-3 py-1 rounded-full`
- Standard Mode: `bg-yellow-500/20 text-yellow-200 text-xs px-3 py-1 rounded-full`
- Korean stock: `bg-blue-500/20 text-blue-200 text-xs px-3 py-1 rounded-full`

---

## Section 2 — Main Comparison Table

```html
<main class="max-w-7xl mx-auto px-4 sm:px-6 py-8 space-y-8">

<section>
  <h2 class="text-xl font-bold text-gray-900 mb-4"><i class="fa-solid fa-table-columns mr-2 text-blue-500"></i>Comparison Matrix</h2>
  <div class="card overflow-x-auto">
    <table class="w-full text-sm">
      <thead>
        <tr class="bg-gray-50 text-gray-600 text-xs uppercase">
          <th class="text-left p-4 font-semibold">Metric</th>
          <th class="text-right p-4 font-semibold text-gray-900">{TICKER1}</th>
          <th class="text-right p-4 font-semibold text-gray-900">{TICKER2}</th>
          <th class="text-right p-4 font-semibold text-gray-900">{TICKER3}</th>
          <th class="text-right p-4 font-semibold">Winner</th>
        </tr>
      </thead>
      <tbody>
        <!-- Section header row -->
        <tr class="bg-gray-50/50">
          <td class="p-3 text-gray-400 text-xs uppercase tracking-wide font-semibold" colspan="5">Price & Size</td>
        </tr>
        <!-- Data rows -->
        <tr class="border-t border-gray-100 hover:bg-gray-50">
          <td class="p-3 text-gray-600">Current Price</td>
          <td class="p-3 text-right text-gray-900 font-medium">{CURRENCY_SYMBOL}{t1_price}</td>
          <td class="p-3 text-right text-gray-900 font-medium">{CURRENCY_SYMBOL}{t2_price}</td>
          <td class="p-3 text-right text-gray-900 font-medium">{CURRENCY_SYMBOL}{t3_price}</td>
          <td class="p-3 text-right text-gray-400">—</td>
        </tr>
        <tr class="border-t border-gray-100 hover:bg-gray-50">
          <td class="p-3 text-gray-600">Market Cap</td>
          <td class="p-3 text-right text-gray-900 font-medium">{t1_mktcap}</td>
          <td class="p-3 text-right text-gray-900 font-medium">{t2_mktcap}</td>
          <td class="p-3 text-right text-gray-900 font-medium">{t3_mktcap}</td>
          <td class="p-3 text-right text-gray-400">—</td>
        </tr>

        <!-- Valuation -->
        <tr class="bg-gray-50/50">
          <td class="p-3 text-gray-400 text-xs uppercase tracking-wide font-semibold" colspan="5">Valuation</td>
        </tr>
        <tr class="border-t border-gray-100 hover:bg-gray-50">
          <td class="p-3 text-gray-600">P/E (TTM) <span class="text-gray-400 text-xs">{[tag]}</span></td>
          <td class="p-3 text-right {winner_class} font-medium">{t1_pe}x</td>
          <td class="p-3 text-right {normal_class} font-medium">{t2_pe}x</td>
          <td class="p-3 text-right {normal_class} font-medium">{t3_pe}x</td>
          <td class="p-3 text-right text-green-600 font-semibold">{TICKER_lowest}</td>
        </tr>
        <!-- Continue: EV/EBITDA, P/B rows -->

        <!-- Growth -->
        <tr class="bg-gray-50/50">
          <td class="p-3 text-gray-400 text-xs uppercase tracking-wide font-semibold" colspan="5">Growth</td>
        </tr>
        <tr class="border-t border-gray-100 hover:bg-gray-50">
          <td class="p-3 text-gray-600">Revenue Growth YoY <span class="text-gray-400 text-xs">{[tag]}</span></td>
          <td class="p-3 text-right {pos_neg_class} font-medium">{t1_rev_growth}%</td>
          <td class="p-3 text-right {pos_neg_class} font-medium">{t2_rev_growth}%</td>
          <td class="p-3 text-right {pos_neg_class} font-medium">{t3_rev_growth}%</td>
          <td class="p-3 text-right text-green-600 font-semibold">{TICKER_highest}</td>
        </tr>
        <!-- Continue: EPS Growth rows -->

        <!-- Profitability -->
        <tr class="bg-gray-50/50">
          <td class="p-3 text-gray-400 text-xs uppercase tracking-wide font-semibold" colspan="5">Profitability</td>
        </tr>
        <!-- Gross Margin, Operating Margin, FCF Yield, ROE rows -->

        <!-- Balance Sheet -->
        <tr class="bg-gray-50/50">
          <td class="p-3 text-gray-400 text-xs uppercase tracking-wide font-semibold" colspan="5">Balance Sheet</td>
        </tr>
        <!-- Net Debt/EBITDA, Dividend Yield rows -->

        <!-- R/R Score Row (highlighted) -->
        <tr class="border-t-2 border-gray-300 bg-gray-50">
          <td class="p-3 text-gray-900 font-semibold">R/R Score</td>
          <td class="p-3 text-right"><span class="{rr_badge_class}">{t1_rr_score}</span></td>
          <td class="p-3 text-right"><span class="{rr_badge_class}">{t2_rr_score}</span></td>
          <td class="p-3 text-right"><span class="{rr_badge_class}">{t3_rr_score}</span></td>
          <td class="p-3 text-right text-green-600 font-semibold">{TICKER_highest}</td>
        </tr>
        <tr class="border-t border-gray-200 bg-gray-50">
          <td class="p-3 text-gray-900 font-semibold">Verdict</td>
          <td class="p-3 text-right"><span class="{verdict_badge}">{t1_verdict}</span></td>
          <td class="p-3 text-right"><span class="{verdict_badge}">{t2_verdict}</span></td>
          <td class="p-3 text-right"><span class="{verdict_badge}">{t3_verdict}</span></td>
          <td class="p-3 text-right text-gray-400">—</td>
        </tr>
      </tbody>
    </table>
  </div>
</section>
```

**Winner column logic**:
- For valuation metrics (P/E, EV/EBITDA, P/B, Net Debt/EBITDA): lowest value = winner (cheapest)
- For growth/profitability metrics: highest value = winner
- For Dividend Yield: no winner (preference-dependent)
- For price, market cap: no winner
- If a ticker has Grade D for the metric: show "—" for that ticker and exclude from winner calculation

**CSS classes for pos/neg values**:
- Positive: `text-green-600`
- Negative: `text-red-600`
- Neutral: `text-gray-900`
- Winner column winner: `text-green-600 font-semibold`

**R/R Score badge classes** (inline):
- Score >3.0: `bg-green-50 text-green-700 border border-green-200 text-sm px-3 py-1 rounded-full font-bold`
- Score 1.0–3.0: `bg-gray-100 text-gray-700 border border-gray-200 text-sm px-3 py-1 rounded-full font-bold`
- Score <1.0: `bg-red-50 text-red-700 border border-red-200 text-sm px-3 py-1 rounded-full font-bold`

**Verdict badge classes**:
- Overweight/비중확대: `bg-green-50 text-green-700 text-xs font-bold px-3 py-1 rounded-full border border-green-200`
- Underweight/비중축소: `bg-red-50 text-red-700 text-xs font-bold px-3 py-1 rounded-full border border-red-200`
- Neutral/중립: `bg-gray-100 text-gray-700 text-xs font-bold px-3 py-1 rounded-full border border-gray-200`
- Watch/관찰: `bg-blue-50 text-blue-700 text-xs font-bold px-3 py-1 rounded-full border border-blue-200`

---

## Section 3 — Scenario Comparison

```html
<section>
  <h2 class="text-xl font-bold text-gray-900 mb-4"><i class="fa-solid fa-bullseye mr-2 text-blue-500"></i>Scenario Comparison</h2>
  <div class="grid grid-cols-1 md:grid-cols-{N} gap-4">

    <!-- Per ticker scenario card -->
    <div class="card p-5">
      <div class="flex items-center justify-between mb-3">
        <h3 class="font-bold text-gray-900 text-lg">{TICKER1}</h3>
        <span class="{rr_badge_class}">{t1_rr_score}</span>
      </div>
      <div class="space-y-2 text-sm">
        <div class="flex justify-between p-2 bg-green-50 rounded">
          <span class="text-green-700 font-medium">Bull ({bull_prob}%)</span>
          <span class="text-gray-900 font-semibold">{CURRENCY_SYMBOL}{bull_target} (+{bull_return}%)</span>
        </div>
        <div class="flex justify-between p-2 bg-blue-50 rounded">
          <span class="text-blue-700 font-medium">Base ({base_prob}%)</span>
          <span class="text-gray-900 font-semibold">{CURRENCY_SYMBOL}{base_target} (+{base_return}%)</span>
        </div>
        <div class="flex justify-between p-2 bg-red-50 rounded">
          <span class="text-red-700 font-medium">Bear ({bear_prob}%)</span>
          <span class="text-gray-900 font-semibold">{CURRENCY_SYMBOL}{bear_target} ({bear_return}%)</span>
        </div>
      </div>
      <div class="mt-3 pt-3 border-t border-gray-100">
        <p class="text-gray-500 text-xs">{variant_view_1_sentence}</p>
      </div>
    </div>

    <!-- repeat for each ticker -->
  </div>
</section>
```

---

## Section 4 — R/R Score Ranking

```html
<section>
  <h2 class="text-xl font-bold text-gray-900 mb-4"><i class="fa-solid fa-ranking-star mr-2 text-blue-500"></i>R/R Score Ranking</h2>
  <div class="space-y-3">
    <!-- Ranked 1 to N, highest score first -->
    <div class="card p-4 flex items-center gap-4 border-l-4 border-green-500">
      <span class="text-2xl font-bold text-green-600">#1</span>
      <div class="flex-1">
        <div class="flex items-center gap-2">
          <span class="font-bold text-gray-900 text-lg">{TICKER}</span>
          <span class="{rr_badge_class}">{rr_score}</span>
        </div>
        <p class="text-gray-500 text-sm mt-1">{1-sentence rationale for ranking — must be company-specific}</p>
      </div>
    </div>
    <!-- #2: border-l-4 border-blue-500, text-blue-600 for rank number -->
    <!-- #3+: border-l-4 border-gray-300, text-gray-500 for rank number -->
  </div>
</section>
```

---

## Section 5 — Best Pick

```html
<section>
  <div class="card p-6 bg-green-50 border border-green-200">
    <div class="flex items-start gap-3">
      <i class="fas fa-star text-green-600 text-xl mt-1"></i>
      <div>
        <h2 class="text-xl font-semibold text-green-800 mb-2">Best Pick (as of {date})</h2>
        <p class="text-gray-900 font-bold text-lg mb-2">{TICKER} — {verdict}</p>
        <p class="text-gray-700 text-sm mb-3">{2–3 sentences. Must include: specific metric advantage, specific catalyst, specific risk acknowledgment. This is an opinion — clearly labeled.}</p>
        <p class="text-gray-500 text-xs italic">This represents the analyst's view based on available data. Not investment advice.</p>
      </div>
    </div>
  </div>
</section>
```

Best Pick rules:
- MUST cite ≥2 specific metrics or data points
- MUST acknowledge the key risk to the thesis
- MUST include "This is an opinion" language
- If all R/R Scores are Unfavorable (<1.0): state "No clear best pick — all peers appear overvalued at current prices"

---

## Section 6 — Key Differentiators

```html
<section>
  <h2 class="text-xl font-bold text-gray-900 mb-4"><i class="fa-solid fa-not-equal mr-2 text-blue-500"></i>Key Differentiators</h2>
  <div class="space-y-3">
    <!-- 2–3 differentiator points -->
    <div class="card p-4 flex gap-3">
      <i class="fas fa-not-equal text-blue-500 mt-1"></i>
      <div>
        <p class="text-gray-900 font-semibold">{Differentiator Title}</p>
        <p class="text-gray-600 text-sm">{Specific comparison with numbers.}</p>
      </div>
    </div>
  </div>
</section>
```

Differentiator rules:
- Must identify 2–3 genuinely distinct factors (not generic "growth vs. value")
- Each must include specific numbers from at least 2 peers
- Focus on what explains divergent valuations or risk profiles

---

## Section 7 — Disclaimer

```html
<footer class="bg-gray-900 text-gray-400 mt-12">
  <div class="max-w-7xl mx-auto px-4 sm:px-6 py-8">
    <p class="text-xs mb-2"><strong class="text-gray-300">Disclaimer:</strong> This report is generated by an AI research assistant for informational purposes only. It does not constitute investment advice, a solicitation to buy or sell securities, or a guarantee of investment returns. All data is sourced from public information and may not reflect the most current market conditions. Past performance is not indicative of future results. Always conduct your own due diligence before making investment decisions.</p>
    <p class="text-xs">Data sources: {source_list} · Generated: {YYYY-MM-DD HH:MM} UTC</p>
  </div>
</footer>

</main>
```

---

## Missing Data Handling

| Situation | Action |
|-----------|--------|
| Metric Grade D for one ticker | Show `<span class="text-gray-400">—</span>` for that ticker; exclude from winner column |
| Metric Grade D for all tickers | Hide entire metric row; note at bottom: "X metrics excluded due to insufficient data" |
| R/R Score unavailable for one ticker | Show "N/A" badge; exclude from ranking |
| Scenario unavailable | Show "Scenarios not computed" in that ticker's card |

---

## File Naming

`output/reports/{T1}_{T2}_{T3}_B_{lang}_{YYYY-MM-DD}.html`

- Tickers: uppercase, underscore-separated, alphabetical order
- Lang: `EN` or `KR`
- Example: `output/reports/AAPL_GOOGL_MSFT_B_EN_2026-03-12.html`

---

## Completion Checklist

Before writing the file, verify:
- [ ] All metric values have source tags in the Metric column
- [ ] Winner column correctly identifies best value (low for valuation, high for growth/profitability)
- [ ] All R/R Scores computed with correct formula
- [ ] Best Pick section explicitly labeled as opinion
- [ ] Key Differentiators contain specific numbers (not generic statements)
- [ ] Disclaimer present
- [ ] File saved to correct path with correct naming convention
