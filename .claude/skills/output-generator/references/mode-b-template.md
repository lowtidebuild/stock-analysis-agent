# Mode B — Comparative Matrix Output Template

Mode B produces an HTML file with a peer comparison matrix. Output path: `output/reports/{tickers}_B_{lang}_{YYYY-MM-DD}.html`

Example: `output/reports/AAPL_MSFT_GOOGL_B_EN_2026-03-12.html`

---

## HTML Structure Overview

```html
<!DOCTYPE html>
<html lang="{en/ko}">
<head>
  <!-- CDN: TailwindCSS, FontAwesome -->
  <title>Peer Comparison: {ticker list} | {YYYY-MM-DD}</title>
</head>
<body class="bg-gray-950 text-gray-100 font-sans min-h-screen p-6">

  <!-- Section 1: Header -->
  <!-- Section 2: Comparison Summary Table -->
  <!-- Section 3: Metric Deep-Dives (per metric row) -->
  <!-- Section 4: R/R Score Ranking -->
  <!-- Section 5: Best Pick Recommendation -->
  <!-- Section 6: Key Differentiators -->
  <!-- Section 7: Disclaimer -->

</body>
</html>
```

CDN block (copy exactly):
```html
<script src="https://cdn.tailwindcss.com"></script>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css"/>
```

---

## Section 1 — Header

```html
<div class="mb-8">
  <h1 class="text-3xl font-bold text-white mb-1">Peer Comparison</h1>
  <p class="text-gray-400 text-sm">{ticker1} vs {ticker2} vs {ticker3} | {sector/theme} | {YYYY-MM-DD}</p>
  <div class="flex gap-2 mt-2">
    <!-- Data mode badge per ticker -->
    <span class="text-xs px-2 py-1 rounded bg-emerald-900 text-emerald-300">{TICKER1} Enhanced</span>
    <span class="text-xs px-2 py-1 rounded bg-amber-900 text-amber-300">{TICKER2} Standard</span>
  </div>
</div>
```

Data mode badge colors:
- Enhanced Mode: `bg-emerald-900 text-emerald-300`
- Standard Mode: `bg-amber-900 text-amber-300`
- Korean stock: `bg-blue-900 text-blue-300`

---

## Section 2 — Main Comparison Table

```html
<div class="overflow-x-auto mb-8">
  <table class="w-full text-sm border-collapse">
    <thead>
      <tr class="bg-gray-800">
        <th class="text-left p-3 text-gray-400 font-medium">Metric</th>
        <th class="text-right p-3 text-white font-semibold">{TICKER1}</th>
        <th class="text-right p-3 text-white font-semibold">{TICKER2}</th>
        <th class="text-right p-3 text-white font-semibold">{TICKER3}</th>
        <th class="text-right p-3 text-gray-400 font-medium">Winner</th>
      </tr>
    </thead>
    <tbody>
      <!-- Price & Size -->
      <tr class="border-t border-gray-800 bg-gray-900/30">
        <td class="p-3 text-gray-400 text-xs uppercase tracking-wide font-semibold" colspan="5">Price & Size</td>
      </tr>
      <tr class="border-t border-gray-800 hover:bg-gray-800/30">
        <td class="p-3 text-gray-300">Current Price</td>
        <td class="p-3 text-right text-white">${t1_price}</td>
        <td class="p-3 text-right text-white">${t2_price}</td>
        <td class="p-3 text-right text-white">${t3_price}</td>
        <td class="p-3 text-right text-gray-500">—</td>
      </tr>
      <tr class="border-t border-gray-800 hover:bg-gray-800/30">
        <td class="p-3 text-gray-300">Market Cap</td>
        <td class="p-3 text-right text-white">${t1_mktcap}B</td>
        <td class="p-3 text-right text-white">${t2_mktcap}B</td>
        <td class="p-3 text-right text-white">${t3_mktcap}B</td>
        <td class="p-3 text-right text-gray-500">—</td>
      </tr>

      <!-- Valuation -->
      <tr class="border-t border-gray-800 bg-gray-900/30">
        <td class="p-3 text-gray-400 text-xs uppercase tracking-wide font-semibold" colspan="5">Valuation</td>
      </tr>
      <tr class="border-t border-gray-800 hover:bg-gray-800/30">
        <td class="p-3 text-gray-300">P/E (TTM) <span class="text-gray-500 text-xs">{[tag]}</span></td>
        <td class="p-3 text-right {winner-class}">{t1_pe}x</td>
        <td class="p-3 text-right {normal-class}">{t2_pe}x</td>
        <td class="p-3 text-right {normal-class}">{t3_pe}x</td>
        <td class="p-3 text-right text-emerald-400 font-semibold">{TICKER_lowest}</td>
      </tr>
      <tr class="border-t border-gray-800 hover:bg-gray-800/30">
        <td class="p-3 text-gray-300">EV/EBITDA <span class="text-gray-500 text-xs">{[tag]}</span></td>
        <td class="p-3 text-right">{t1_ev_ebitda}x</td>
        <td class="p-3 text-right">{t2_ev_ebitda}x</td>
        <td class="p-3 text-right">{t3_ev_ebitda}x</td>
        <td class="p-3 text-right text-emerald-400 font-semibold">{TICKER_lowest}</td>
      </tr>
      <tr class="border-t border-gray-800 hover:bg-gray-800/30">
        <td class="p-3 text-gray-300">P/B <span class="text-gray-500 text-xs">{[tag]}</span></td>
        <td class="p-3 text-right">{t1_pb}x</td>
        <td class="p-3 text-right">{t2_pb}x</td>
        <td class="p-3 text-right">{t3_pb}x</td>
        <td class="p-3 text-right text-emerald-400 font-semibold">{TICKER_lowest}</td>
      </tr>

      <!-- Growth -->
      <tr class="border-t border-gray-800 bg-gray-900/30">
        <td class="p-3 text-gray-400 text-xs uppercase tracking-wide font-semibold" colspan="5">Growth</td>
      </tr>
      <tr class="border-t border-gray-800 hover:bg-gray-800/30">
        <td class="p-3 text-gray-300">Revenue Growth YoY <span class="text-gray-500 text-xs">{[tag]}</span></td>
        <td class="p-3 text-right {pos/neg-class}">{t1_rev_growth}%</td>
        <td class="p-3 text-right {pos/neg-class}">{t2_rev_growth}%</td>
        <td class="p-3 text-right {pos/neg-class}">{t3_rev_growth}%</td>
        <td class="p-3 text-right text-emerald-400 font-semibold">{TICKER_highest}</td>
      </tr>
      <tr class="border-t border-gray-800 hover:bg-gray-800/30">
        <td class="p-3 text-gray-300">EPS Growth YoY <span class="text-gray-500 text-xs">{[tag]}</span></td>
        <td class="p-3 text-right">{t1_eps_growth}%</td>
        <td class="p-3 text-right">{t2_eps_growth}%</td>
        <td class="p-3 text-right">{t3_eps_growth}%</td>
        <td class="p-3 text-right text-emerald-400 font-semibold">{TICKER_highest}</td>
      </tr>

      <!-- Profitability -->
      <tr class="border-t border-gray-800 bg-gray-900/30">
        <td class="p-3 text-gray-400 text-xs uppercase tracking-wide font-semibold" colspan="5">Profitability</td>
      </tr>
      <tr class="border-t border-gray-800 hover:bg-gray-800/30">
        <td class="p-3 text-gray-300">Gross Margin <span class="text-gray-500 text-xs">{[tag]}</span></td>
        <td class="p-3 text-right">{t1_gross_margin}%</td>
        <td class="p-3 text-right">{t2_gross_margin}%</td>
        <td class="p-3 text-right">{t3_gross_margin}%</td>
        <td class="p-3 text-right text-emerald-400 font-semibold">{TICKER_highest}</td>
      </tr>
      <tr class="border-t border-gray-800 hover:bg-gray-800/30">
        <td class="p-3 text-gray-300">Operating Margin <span class="text-gray-500 text-xs">{[tag]}</span></td>
        <td class="p-3 text-right">{t1_op_margin}%</td>
        <td class="p-3 text-right">{t2_op_margin}%</td>
        <td class="p-3 text-right">{t3_op_margin}%</td>
        <td class="p-3 text-right text-emerald-400 font-semibold">{TICKER_highest}</td>
      </tr>
      <tr class="border-t border-gray-800 hover:bg-gray-800/30">
        <td class="p-3 text-gray-300">FCF Yield <span class="text-gray-500 text-xs">{[tag]}</span></td>
        <td class="p-3 text-right">{t1_fcf_yield}%</td>
        <td class="p-3 text-right">{t2_fcf_yield}%</td>
        <td class="p-3 text-right">{t3_fcf_yield}%</td>
        <td class="p-3 text-right text-emerald-400 font-semibold">{TICKER_highest}</td>
      </tr>
      <tr class="border-t border-gray-800 hover:bg-gray-800/30">
        <td class="p-3 text-gray-300">ROE <span class="text-gray-500 text-xs">{[tag]}</span></td>
        <td class="p-3 text-right">{t1_roe}%</td>
        <td class="p-3 text-right">{t2_roe}%</td>
        <td class="p-3 text-right">{t3_roe}%</td>
        <td class="p-3 text-right text-emerald-400 font-semibold">{TICKER_highest}</td>
      </tr>

      <!-- Balance Sheet -->
      <tr class="border-t border-gray-800 bg-gray-900/30">
        <td class="p-3 text-gray-400 text-xs uppercase tracking-wide font-semibold" colspan="5">Balance Sheet</td>
      </tr>
      <tr class="border-t border-gray-800 hover:bg-gray-800/30">
        <td class="p-3 text-gray-300">Net Debt/EBITDA <span class="text-gray-500 text-xs">{[tag]}</span></td>
        <td class="p-3 text-right">{t1_nd_ebitda}x</td>
        <td class="p-3 text-right">{t2_nd_ebitda}x</td>
        <td class="p-3 text-right">{t3_nd_ebitda}x</td>
        <td class="p-3 text-right text-emerald-400 font-semibold">{TICKER_lowest}</td>
      </tr>
      <tr class="border-t border-gray-800 hover:bg-gray-800/30">
        <td class="p-3 text-gray-300">Dividend Yield <span class="text-gray-500 text-xs">{[tag]}</span></td>
        <td class="p-3 text-right">{t1_div_yield}%</td>
        <td class="p-3 text-right">{t2_div_yield}%</td>
        <td class="p-3 text-right">{t3_div_yield}%</td>
        <td class="p-3 text-right text-gray-500">—</td>
      </tr>

      <!-- R/R Score Row -->
      <tr class="border-t-2 border-gray-600 bg-gray-800">
        <td class="p-3 text-white font-semibold">R/R Score</td>
        <td class="p-3 text-right"><span class="{rr_badge_class}">{t1_rr_score}</span></td>
        <td class="p-3 text-right"><span class="{rr_badge_class}">{t2_rr_score}</span></td>
        <td class="p-3 text-right"><span class="{rr_badge_class}">{t3_rr_score}</span></td>
        <td class="p-3 text-right text-emerald-400 font-semibold">{TICKER_highest}</td>
      </tr>
      <tr class="border-t border-gray-700 bg-gray-800">
        <td class="p-3 text-white font-semibold">Verdict</td>
        <td class="p-3 text-right"><span class="{verdict_badge}">{t1_verdict}</span></td>
        <td class="p-3 text-right"><span class="{verdict_badge}">{t2_verdict}</span></td>
        <td class="p-3 text-right"><span class="{verdict_badge}">{t3_verdict}</span></td>
        <td class="p-3 text-right text-gray-500">—</td>
      </tr>
    </tbody>
  </table>
</div>
```

**Winner column logic**:
- For valuation metrics (P/E, EV/EBITDA, P/B, Net Debt/EBITDA): lowest value = winner (cheapest)
- For growth/profitability metrics: highest value = winner
- For Dividend Yield: no winner (preference-dependent)
- For price, market cap: no winner
- If a ticker has Grade D for the metric: show "—" for that ticker and exclude from winner calculation

**CSS classes for pos/neg values**:
- Positive: `text-emerald-400`
- Negative: `text-red-400`
- Neutral: `text-white`
- Winner column winner: `text-emerald-400 font-semibold`

---

## Section 3 — Scenario Comparison

```html
<div class="mb-8">
  <h2 class="text-xl font-semibold text-white mb-4">Scenario Comparison</h2>
  <div class="grid grid-cols-1 md:grid-cols-{N} gap-4">

    <!-- Per ticker scenario card -->
    <div class="bg-gray-800 rounded-xl p-4 border border-gray-700">
      <div class="flex items-center justify-between mb-3">
        <h3 class="font-bold text-white text-lg">{TICKER1}</h3>
        <span class="{rr_badge_class} text-sm px-3 py-1 rounded-full font-bold">R/R {t1_rr_score}</span>
      </div>
      <div class="space-y-2 text-sm">
        <div class="flex justify-between">
          <span class="text-emerald-400">🟢 Bull ({bull_prob}%)</span>
          <span class="text-white font-semibold">${bull_target} (+{bull_return}%)</span>
        </div>
        <div class="flex justify-between">
          <span class="text-yellow-400">🟡 Base ({base_prob}%)</span>
          <span class="text-white font-semibold">${base_target} (+{base_return}%)</span>
        </div>
        <div class="flex justify-between">
          <span class="text-red-400">🔴 Bear ({bear_prob}%)</span>
          <span class="text-white font-semibold">${bear_target} ({bear_return}%)</span>
        </div>
      </div>
      <div class="mt-3 pt-3 border-t border-gray-700">
        <p class="text-gray-400 text-xs">{variant_view_1_sentence}</p>
      </div>
    </div>

    <!-- repeat for each ticker -->
  </div>
</div>
```

---

## Section 4 — R/R Score Ranking

```html
<div class="mb-8">
  <h2 class="text-xl font-semibold text-white mb-4">R/R Score Ranking</h2>
  <div class="space-y-3">
    <!-- Ranked 1 to N, highest score first -->
    <div class="flex items-center gap-4 p-3 bg-gray-800 rounded-lg border border-emerald-800">
      <span class="text-2xl font-bold text-emerald-400">#1</span>
      <div class="flex-1">
        <div class="flex items-center gap-2">
          <span class="font-bold text-white text-lg">{TICKER}</span>
          <span class="{rr_badge_class} text-sm px-2 py-0.5 rounded-full">{rr_score}</span>
        </div>
        <p class="text-gray-400 text-sm mt-1">{1-sentence rationale for ranking — must be company-specific}</p>
      </div>
    </div>
    <!-- repeat for each ticker in rank order -->
  </div>
</div>
```

---

## Section 5 — Best Pick

```html
<div class="bg-emerald-950 border border-emerald-800 rounded-xl p-5 mb-8">
  <div class="flex items-start gap-3">
    <i class="fas fa-star text-emerald-400 text-xl mt-1"></i>
    <div>
      <h2 class="text-xl font-semibold text-emerald-300 mb-2">Best Pick (as of {date})</h2>
      <p class="text-white font-bold text-lg mb-2">{TICKER} — {verdict}</p>
      <p class="text-gray-300 text-sm mb-3">{2–3 sentences. Must include: specific metric advantage, specific catalyst, specific risk acknowledgment. This is an opinion — clearly labeled.}</p>
      <p class="text-gray-500 text-xs italic">This represents the analyst's view based on available data. Not investment advice.</p>
    </div>
  </div>
</div>
```

Best Pick rules:
- MUST cite ≥2 specific metrics or data points
- MUST acknowledge the key risk to the thesis
- MUST include "This is an opinion" language
- If all R/R Scores are Unfavorable (<1.0): state "No clear best pick — all peers appear overvalued at current prices"

---

## Section 6 — Key Differentiators

```html
<div class="mb-8">
  <h2 class="text-xl font-semibold text-white mb-4">Key Differentiators</h2>
  <div class="space-y-3">
    <!-- 2–3 differentiator points -->
    <div class="flex gap-3 p-4 bg-gray-800 rounded-lg">
      <i class="fas fa-not-equal text-blue-400 mt-1"></i>
      <div>
        <p class="text-white font-semibold">{Differentiator Title}</p>
        <p class="text-gray-400 text-sm">{Specific comparison with numbers. E.g., "MSFT operating margin 45% vs GOOGL 32% reflects Azure's enterprise pricing power vs. ad market cyclicality"}</p>
      </div>
    </div>
  </div>
</div>
```

Differentiator rules:
- Must identify 2–3 genuinely distinct factors (not generic "growth vs. value")
- Each must include specific numbers from at least 2 peers
- Focus on what explains divergent valuations or risk profiles

---

## Section 7 — Disclaimer

```html
<div class="mt-8 pt-6 border-t border-gray-800 text-xs text-gray-500">
  <p><strong class="text-gray-400">Disclaimer:</strong> This report is generated by an AI research assistant for informational purposes only. It does not constitute investment advice, a solicitation to buy or sell securities, or a guarantee of investment returns. All data is sourced from public information and may not reflect the most current market conditions. Past performance is not indicative of future results. Always conduct your own due diligence before making investment decisions.</p>
  <p class="mt-2">Data sources: {source_list} | Generated: {YYYY-MM-DD HH:MM} UTC</p>
</div>
```

---

## Missing Data Handling

| Situation | Action |
|-----------|--------|
| Metric Grade D for one ticker | Show "—" for that ticker; exclude from winner column |
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
