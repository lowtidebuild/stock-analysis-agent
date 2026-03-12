# HTML Dashboard Template — Mode C

This file provides the complete structural skeleton for the Mode C Deep Dive Dashboard. Claude reads this file, then populates all `{PLACEHOLDER}` values with actual data from `output/analysis-result.json` and `output/validated-data.json`.

---

## CDN Block (always include in `<head>`)

```html
<script src="https://cdn.tailwindcss.com"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css">
<!-- For Korean language output only: -->
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700&display=swap" rel="stylesheet">
```

---

## Full HTML Skeleton

```html
<!DOCTYPE html>
<html lang="{LANG_CODE}">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{COMPANY_NAME} ({TICKER}) — Investment Dashboard</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css">
  {KOREAN_FONT_IF_KR}
  <style>
    body { background-color: #030712; }
    .gradient-header { background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 50%, #0f172a 100%); }
    .card { background: #0f172a; border: 1px solid #1e293b; border-radius: 12px; }
    .metric-card { background: #0f172a; border: 1px solid #1e293b; border-radius: 8px; transition: border-color 0.2s; }
    .metric-card:hover { border-color: #3b82f6; }
    .source-tag { font-family: monospace; font-size: 0.7rem; padding: 1px 5px; border-radius: 3px; }
    .tag-api { background: #1e3a5f; color: #60a5fa; }
    .tag-web { background: #1a2e1a; color: #86efac; }
    .tag-calc { background: #1e2a1e; color: #4ade80; }
    .tag-1s { background: #2d2510; color: #fbbf24; }
    .tag-dart { background: #2d1a3e; color: #c084fc; }
    .tag-unverified { background: #3b0f0f; color: #f87171; }
    .rr-badge { background: linear-gradient(135deg, #059669, #10b981); border-radius: 12px; }
    .rr-badge-neutral { background: linear-gradient(135deg, #d97706, #f59e0b); border-radius: 12px; }
    .rr-badge-negative { background: linear-gradient(135deg, #dc2626, #ef4444); border-radius: 12px; }
    table { width: 100%; }
    th { background: #1e293b; color: #94a3b8; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; padding: 10px 12px; text-align: left; }
    td { padding: 10px 12px; border-bottom: 1px solid #1e293b; color: #e2e8f0; font-size: 0.875rem; }
    tr:last-child td { border-bottom: none; }
    tr:hover td { background: #1e293b; }
  </style>
</head>
<body class="{FONT_CLASS} text-gray-100 min-h-screen">

<!-- ============================================================ -->
<!-- SECTION 1: PREMIUM HEADER                                    -->
<!-- ============================================================ -->
<header id="section-header" class="gradient-header px-6 py-8 border-b border-gray-800">
  <div class="max-w-7xl mx-auto">

    <!-- Top row: Company info + Data Mode Badge -->
    <div class="flex flex-wrap items-start justify-between gap-4 mb-6">
      <div>
        <div class="flex items-center gap-3 mb-2">
          <h1 class="text-4xl font-bold text-white">{COMPANY_NAME}</h1>
          <span class="bg-blue-700 text-white text-sm font-semibold px-3 py-1 rounded-full">{TICKER}</span>
          <span class="bg-gray-700 text-gray-200 text-sm px-2 py-1 rounded">{EXCHANGE}</span>
          <span class="bg-gray-700 text-gray-200 text-sm px-2 py-1 rounded">{MARKET_FLAG} {MARKET}</span>
          <span class="bg-purple-800 text-purple-200 text-xs px-2 py-1 rounded">{COMPANY_TYPE}</span>
        </div>
        <p class="text-gray-400 text-sm">{COMPANY_DESCRIPTION_ONE_LINE}</p>
      </div>

      <!-- Data Confidence Indicator -->
      <div id="data-confidence-indicator" class="card p-4 min-w-64">
        <div class="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">📊 Data Quality</div>
        <!-- Enhanced Mode: -->
        <!-- <div class="flex items-center gap-2 mb-1">
          <span class="bg-emerald-600 text-white text-xs font-bold px-2 py-0.5 rounded-full">✅ Enhanced</span>
          <span class="text-gray-300 text-xs">API-verified financial data</span>
        </div>
        <div class="w-full bg-gray-700 rounded-full h-1.5 mb-1">
          <div class="bg-emerald-500 h-1.5 rounded-full" style="width: 100%"></div>
        </div> -->

        <!-- Standard Mode: -->
        <!-- <div class="flex items-center gap-2 mb-1">
          <span class="bg-amber-600 text-white text-xs font-bold px-2 py-0.5 rounded-full">⚠ Standard</span>
          <span class="text-gray-300 text-xs">Web-sourced, cross-referenced</span>
        </div>
        <div class="w-full bg-gray-700 rounded-full h-1.5 mb-1">
          <div class="bg-amber-500 h-1.5 rounded-full" style="width: 65%"></div>
        </div>
        <div class="text-gray-400 text-xs">{N} of 10 key metrics single-source [1S]</div> -->

        <!-- Actual indicator goes here based on data_mode from validated-data.json -->
        {DATA_CONFIDENCE_INDICATOR_HTML}
        <div class="text-gray-500 text-xs mt-1">Last updated: {ANALYSIS_DATETIME}</div>
      </div>
    </div>

    <!-- Price row -->
    <div class="flex flex-wrap items-end gap-8">
      <div>
        <div class="text-5xl font-bold text-white">{CURRENCY_SYMBOL}{CURRENT_PRICE}</div>
        <div class="flex items-center gap-2 mt-1">
          <span class="{PRICE_CHANGE_COLOR} text-xl font-semibold">{PRICE_CHANGE_ABS} ({PRICE_CHANGE_PCT}%)</span>
          <span class="text-gray-500 text-sm">as of {PRICE_AS_OF}</span>
        </div>
      </div>
      <div class="flex gap-6 text-sm">
        <div><div class="text-gray-500">Mkt Cap</div><div class="text-white font-semibold">{MARKET_CAP}</div></div>
        <div><div class="text-gray-500">52W Range</div><div class="text-white font-semibold">{W52_LOW} – {W52_HIGH}</div></div>
        <div><div class="text-gray-500">Volume</div><div class="text-white font-semibold">{VOLUME}</div></div>
        <div><div class="text-gray-500">P/E (TTM)</div><div class="text-white font-semibold">{PE_RATIO}x {PE_TAG}</div></div>
        <div><div class="text-gray-500">EV/EBITDA</div><div class="text-white font-semibold">{EV_EBITDA}x {EV_EBITDA_TAG}</div></div>
      </div>
    </div>

    <!-- Analysis info bar -->
    <div class="mt-4 pt-4 border-t border-gray-800 flex flex-wrap gap-4 text-xs text-gray-500">
      <span>Analysis Date: {ANALYSIS_DATE}</span>
      <span>•</span>
      <span>Output Mode: Deep Dive Dashboard (C)</span>
      <span>•</span>
      <span>Language: {LANGUAGE}</span>
      <span>•</span>
      <span>Data Mode: {DATA_MODE}</span>
    </div>
  </div>
</header>

<main class="max-w-7xl mx-auto px-6 py-8 space-y-8">

<!-- ============================================================ -->
<!-- SECTION 2: VALUATION TARGET HIGHLIGHT + R/R SCORE           -->
<!-- ============================================================ -->
<section id="section-scenarios" class="card p-6">
  <h2 class="text-xl font-bold text-white mb-2">
    <i class="fas fa-bullseye text-blue-400 mr-2"></i>Price Targets & Risk/Reward
  </h2>
  <p class="text-gray-400 text-sm mb-5">{VARIANT_VIEW_ONE_LINE}</p>

  <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
    <!-- Bull Case -->
    <div class="bg-emerald-900/30 border border-emerald-700 rounded-xl p-5">
      <div class="text-emerald-400 text-xs font-bold uppercase tracking-wider mb-2">🚀 Bull Case</div>
      <div class="text-emerald-400 text-3xl font-bold">{CURRENCY_SYMBOL}{BULL_TARGET}</div>
      <div class="text-emerald-300 text-lg font-semibold">{BULL_RETURN_PCT}</div>
      <div class="text-gray-400 text-xs mt-1">{BULL_PROB}% probability</div>
      <div class="text-gray-300 text-sm mt-3 pt-3 border-t border-emerald-800/50">{BULL_KEY_ASSUMPTION}</div>
    </div>

    <!-- Base Case -->
    <div class="bg-blue-900/30 border border-blue-700 rounded-xl p-5">
      <div class="text-blue-400 text-xs font-bold uppercase tracking-wider mb-2">📊 Base Case</div>
      <div class="text-blue-400 text-3xl font-bold">{CURRENCY_SYMBOL}{BASE_TARGET}</div>
      <div class="text-blue-300 text-lg font-semibold">{BASE_RETURN_PCT}</div>
      <div class="text-gray-400 text-xs mt-1">{BASE_PROB}% probability</div>
      <div class="text-gray-300 text-sm mt-3 pt-3 border-t border-blue-800/50">{BASE_KEY_ASSUMPTION}</div>
    </div>

    <!-- Bear Case -->
    <div class="bg-red-900/30 border border-red-700 rounded-xl p-5">
      <div class="text-red-400 text-xs font-bold uppercase tracking-wider mb-2">⚠ Bear Case</div>
      <div class="text-red-400 text-3xl font-bold">{CURRENCY_SYMBOL}{BEAR_TARGET}</div>
      <div class="text-red-300 text-lg font-semibold">{BEAR_RETURN_PCT}</div>
      <div class="text-gray-400 text-xs mt-1">{BEAR_PROB}% probability</div>
      <div class="text-gray-300 text-sm mt-3 pt-3 border-t border-red-800/50">{BEAR_KEY_ASSUMPTION}</div>
    </div>

    <!-- R/R Score -->
    <div class="flex flex-col items-center justify-center {RR_BADGE_CLASS} p-5 text-center">
      <div class="text-white text-xs font-bold uppercase tracking-wider mb-2">R/R Score</div>
      <div class="text-white text-5xl font-black">{RR_SCORE}</div>
      <div class="text-white/80 text-sm mt-1">{RR_INTERPRETATION}</div>
      <div class="text-white/60 text-xs mt-3">Verdict: <span class="font-bold text-white">{VERDICT}</span></div>
      <div class="text-white/50 text-xs mt-1">Score &gt;3 = Attractive</div>
    </div>
  </div>
</section>

<!-- ============================================================ -->
<!-- SECTION 3: COMPANY-SPECIFIC KPI HIGHLIGHT                   -->
<!-- ============================================================ -->
<section id="section-kpi" class="card p-6">
  <h2 class="text-xl font-bold text-white mb-5">
    <i class="fas fa-chart-bar text-purple-400 mr-2"></i>Key Performance Indicators
  </h2>

  <!-- KPI tiles (4-6 tiles, company-type dependent) -->
  <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4 mb-6">
    <!-- Each KPI tile follows this pattern: -->
    {KPI_TILES_HTML}
    <!-- Example tile: -->
    <!--
    <div class="metric-card p-4 text-center">
      <div class="text-gray-400 text-xs uppercase tracking-wider mb-1">Revenue TTM</div>
      <div class="text-white text-xl font-bold">$390B</div>
      <div class="text-gray-500 text-xs">[API]</div>
      <div class="text-emerald-400 text-xs mt-1">▲ +8.2% YoY</div>
    </div>
    -->
  </div>

  <!-- Core financial ratios row -->
  <div class="grid grid-cols-3 md:grid-cols-6 gap-3">
    <div class="metric-card p-3 text-center">
      <div class="text-gray-500 text-xs">P/E TTM</div>
      <div class="text-white font-bold">{PE_RATIO}x</div>
      <div class="text-xs text-gray-600">{PE_TAG}</div>
    </div>
    <div class="metric-card p-3 text-center">
      <div class="text-gray-500 text-xs">EV/EBITDA</div>
      <div class="text-white font-bold">{EV_EBITDA}x</div>
      <div class="text-xs text-gray-600">{EV_EBITDA_TAG}</div>
    </div>
    <div class="metric-card p-3 text-center">
      <div class="text-gray-500 text-xs">FCF Yield</div>
      <div class="text-white font-bold">{FCF_YIELD}%</div>
      <div class="text-xs text-gray-600">{FCF_TAG}</div>
    </div>
    <div class="metric-card p-3 text-center">
      <div class="text-gray-500 text-xs">Op Margin</div>
      <div class="text-white font-bold">{OP_MARGIN}%</div>
      <div class="text-xs text-gray-600">{OP_MARGIN_TAG}</div>
    </div>
    <div class="metric-card p-3 text-center">
      <div class="text-gray-500 text-xs">Rev Growth</div>
      <div class="{REV_GROWTH_COLOR} font-bold">{REV_GROWTH}%</div>
      <div class="text-xs text-gray-600">{REV_GROWTH_TAG}</div>
    </div>
    <div class="metric-card p-3 text-center">
      <div class="text-gray-500 text-xs">Net Debt/EBITDA</div>
      <div class="text-white font-bold">{NET_DEBT_EBITDA}x</div>
      <div class="text-xs text-gray-600">{NET_DEBT_TAG}</div>
    </div>
  </div>
</section>

<!-- ============================================================ -->
<!-- SECTION 4: INVESTMENT THESIS & VARIANT VIEW                 -->
<!-- ============================================================ -->
<section id="section-thesis" class="card p-6">
  <h2 class="text-xl font-bold text-white mb-5">
    <i class="fas fa-lightbulb text-yellow-400 mr-2"></i>Investment Thesis & Variant View
  </h2>

  <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
    <div>
      <!-- Q1: Why Mispriced -->
      <div class="mb-5">
        <div class="text-blue-400 text-xs font-bold uppercase tracking-wider mb-2">Q1 — Why Mispriced</div>
        <p class="text-gray-200 text-sm leading-relaxed">{VARIANT_VIEW_Q1}</p>
      </div>
      <!-- Q2: Inflection Point -->
      <div class="mb-5">
        <div class="text-emerald-400 text-xs font-bold uppercase tracking-wider mb-2">Q2 — Inflection Point</div>
        <p class="text-gray-200 text-sm leading-relaxed">{VARIANT_VIEW_Q2}</p>
      </div>
      <!-- Q3: Upside Optionality -->
      <div>
        <div class="text-purple-400 text-xs font-bold uppercase tracking-wider mb-2">Q3 — Upside Optionality</div>
        <p class="text-gray-200 text-sm leading-relaxed">{VARIANT_VIEW_Q3}</p>
      </div>
    </div>

    <div>
      <!-- Precision Risk Table -->
      <div class="text-red-400 text-xs font-bold uppercase tracking-wider mb-3">⚡ Precision Risk Analysis</div>
      <div class="space-y-3">
        {RISK_ITEMS_HTML}
        <!-- Each risk item: -->
        <!--
        <div class="bg-red-900/20 border border-red-800/50 rounded-lg p-4">
          <div class="flex items-start justify-between gap-2 mb-2">
            <div class="text-red-300 font-semibold text-sm">{RISK_NAME}</div>
            <span class="text-red-400 text-xs font-bold whitespace-nowrap">P={RISK_PROB}%</span>
          </div>
          <div class="text-gray-300 text-xs mb-1"><span class="text-gray-500">Mechanism:</span> {RISK_MECHANISM}</div>
          <div class="text-gray-300 text-xs mb-1"><span class="text-gray-500">EBITDA Impact:</span> {RISK_IMPACT}</div>
          <div class="text-gray-400 text-xs"><span class="text-gray-500">Mitigant:</span> {RISK_MITIGANT}</div>
        </div>
        -->
      </div>
    </div>
  </div>
</section>

<!-- ============================================================ -->
<!-- SECTION 5: DETAILED VALUATION METRICS                       -->
<!-- ============================================================ -->
<section id="section-valuation" class="card p-6">
  <h2 class="text-xl font-bold text-white mb-5">
    <i class="fas fa-calculator text-green-400 mr-2"></i>Valuation Metrics
  </h2>

  <table class="rounded-lg overflow-hidden">
    <thead>
      <tr>
        <th>Metric</th>
        <th>{TICKER}</th>
        <th>5Y Avg</th>
        <th>Sector Avg</th>
        <th>vs Sector</th>
        <th>Source</th>
      </tr>
    </thead>
    <tbody>
      {VALUATION_TABLE_ROWS}
      <!-- Example row: -->
      <!--
      <tr>
        <td class="text-gray-300">P/E (TTM)</td>
        <td class="text-white font-semibold">28.5x</td>
        <td class="text-gray-400">24.1x</td>
        <td class="text-gray-400">22.3x</td>
        <td class="text-amber-400">+28% Premium</td>
        <td><span class="source-tag tag-api">[API]</span></td>
      </tr>
      -->
    </tbody>
  </table>

  <!-- SOTP Summary (if multi-segment) -->
  {SOTP_SECTION_IF_APPLICABLE}
  <!--
  <div class="mt-6 p-4 bg-gray-800/50 rounded-lg">
    <div class="text-white text-sm font-bold mb-3">Sum-of-the-Parts Valuation</div>
    <table class="rounded-lg overflow-hidden">
      <thead><tr><th>Segment</th><th>Revenue</th><th>EBITDA</th><th>Multiple</th><th>Value</th><th>Notes</th></tr></thead>
      <tbody>{SOTP_ROWS}</tbody>
    </table>
    <div class="mt-3 pt-3 border-t border-gray-700 grid grid-cols-3 gap-4 text-sm">
      <div><span class="text-gray-400">Enterprise Value:</span> <span class="text-white font-bold">{TEV}</span></div>
      <div><span class="text-gray-400">Less: Net Debt:</span> <span class="text-red-400 font-bold">({NET_DEBT})</span></div>
      <div><span class="text-gray-400">Equity Value:</span> <span class="text-emerald-400 font-bold">{EQUITY_VALUE}</span></div>
    </div>
  </div>
  -->
</section>

<!-- ============================================================ -->
<!-- SECTION 6: PEER COMPARISON TABLE                            -->
<!-- ============================================================ -->
<section id="section-peers" class="card p-6">
  <h2 class="text-xl font-bold text-white mb-5">
    <i class="fas fa-users text-indigo-400 mr-2"></i>Peer Comparison
  </h2>

  <div class="overflow-x-auto">
    <table class="rounded-lg overflow-hidden">
      <thead>
        <tr>
          <th>Company</th>
          <th>Price</th>
          <th>Mkt Cap</th>
          <th>P/E</th>
          <th>EV/EBITDA</th>
          <th>Rev Growth</th>
          <th>Op Margin</th>
          <th>FCF Yield</th>
          <th>R/R Score</th>
        </tr>
      </thead>
      <tbody>
        {PEER_TABLE_ROWS}
        <!-- Subject company highlighted: -->
        <!--
        <tr class="bg-blue-900/20 border-l-2 border-blue-500">
          <td class="text-blue-300 font-bold">{TICKER} ← You</td>
          ...
        </tr>
        -->
      </tbody>
    </table>
  </div>
  <p class="text-gray-500 text-xs mt-2">Peer data sourced from web research. {PEER_DATA_TAGS}</p>
</section>

<!-- ============================================================ -->
<!-- SECTION 7: ANALYST PRICE TARGETS                            -->
<!-- ============================================================ -->
<section id="section-analyst" class="card p-6">
  <h2 class="text-xl font-bold text-white mb-5">
    <i class="fas fa-chart-line text-cyan-400 mr-2"></i>Analyst Coverage
  </h2>

  <!-- Enhanced Mode: Full analyst table -->
  <!-- Standard Mode: Consensus summary only -->
  {ANALYST_CONTENT_HTML}

  <!-- Consensus summary (always shown): -->
  <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-5">
    <div class="metric-card p-4 text-center">
      <div class="text-gray-400 text-xs">Avg Target</div>
      <div class="text-white text-xl font-bold">{CURRENCY_SYMBOL}{AVG_TARGET}</div>
      <div class="{AVG_UPSIDE_COLOR} text-sm">{AVG_UPSIDE_PCT} upside</div>
    </div>
    <div class="metric-card p-4 text-center">
      <div class="text-gray-400 text-xs">High Target</div>
      <div class="text-emerald-400 text-xl font-bold">{CURRENCY_SYMBOL}{HIGH_TARGET}</div>
    </div>
    <div class="metric-card p-4 text-center">
      <div class="text-gray-400 text-xs">Low Target</div>
      <div class="text-red-400 text-xl font-bold">{CURRENCY_SYMBOL}{LOW_TARGET}</div>
    </div>
    <div class="metric-card p-4 text-center">
      <div class="text-gray-400 text-xs">Analysts</div>
      <div class="text-white text-xl font-bold">{NUM_ANALYSTS}</div>
      <div class="text-xs text-gray-500">covering</div>
    </div>
  </div>

  <!-- Rating distribution bar -->
  <div class="flex items-center gap-2 text-xs">
    <span class="text-gray-400 w-12">Buy</span>
    <div class="flex-1 h-3 bg-gray-800 rounded-full overflow-hidden">
      <div class="h-full bg-emerald-500 rounded-l-full" style="width: {BUY_PCT}%"></div>
    </div>
    <span class="text-emerald-400 w-8">{BUY_COUNT}</span>
  </div>
  <div class="flex items-center gap-2 text-xs mt-1">
    <span class="text-gray-400 w-12">Hold</span>
    <div class="flex-1 h-3 bg-gray-800 rounded-full overflow-hidden">
      <div class="h-full bg-amber-500" style="width: {HOLD_PCT}%"></div>
    </div>
    <span class="text-amber-400 w-8">{HOLD_COUNT}</span>
  </div>
  <div class="flex items-center gap-2 text-xs mt-1">
    <span class="text-gray-400 w-12">Sell</span>
    <div class="flex-1 h-3 bg-gray-800 rounded-full overflow-hidden">
      <div class="h-full bg-red-500 rounded-r-full" style="width: {SELL_PCT}%"></div>
    </div>
    <span class="text-red-400 w-8">{SELL_COUNT}</span>
  </div>
</section>

<!-- ============================================================ -->
<!-- SECTION 8: INTERACTIVE CHARTS                               -->
<!-- ============================================================ -->
<section id="section-charts" class="card p-6">
  <h2 class="text-xl font-bold text-white mb-5">
    <i class="fas fa-chart-area text-pink-400 mr-2"></i>Interactive Charts
  </h2>

  <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
    <!-- Chart A: 12-Month Price History -->
    <div>
      <div class="text-gray-400 text-sm font-semibold mb-3">12-Month Price History</div>
      <div style="height: 220px;"><canvas id="priceChart"></canvas></div>
    </div>

    <!-- Chart B: Revenue + Operating Income (8Q) -->
    <div>
      <div class="text-gray-400 text-sm font-semibold mb-3">Quarterly Revenue & Operating Income</div>
      <div style="height: 220px;"><canvas id="revenueChart"></canvas></div>
    </div>

    <!-- Chart C: Margin Trends (8Q) -->
    <div>
      <div class="text-gray-400 text-sm font-semibold mb-3">Margin Trends (%)</div>
      <div style="height: 220px;"><canvas id="marginChart"></canvas></div>
    </div>

    <!-- Chart D: Optional (Peer P/E Comparison, etc.) -->
    {OPTIONAL_CHART_D}
  </div>
</section>

<!-- ============================================================ -->
<!-- SECTION 9: FINANCIAL DETAIL ANALYSIS                        -->
<!-- ============================================================ -->
<section id="section-financials" class="card p-6">
  <h2 class="text-xl font-bold text-white mb-5">
    <i class="fas fa-table text-orange-400 mr-2"></i>Financial Detail
  </h2>

  <!-- Quarterly Income Statement (8Q) -->
  <div class="mb-6">
    <div class="text-gray-300 text-sm font-semibold mb-3">Quarterly P&L (8 quarters)</div>
    <div class="overflow-x-auto">
      <table class="text-xs rounded-lg overflow-hidden">
        <thead>
          <tr>
            <th>Quarter</th>
            {QUARTER_HEADERS}
          </tr>
        </thead>
        <tbody>
          {QUARTERLY_ROWS}
          <!-- Revenue row, Gross Profit row, Op Income row, Net Income row, EPS row -->
        </tbody>
      </table>
    </div>
  </div>

  <!-- QoE Summary -->
  <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
    <div class="bg-gray-800/50 rounded-lg p-4">
      <div class="text-gray-300 text-sm font-semibold mb-3">Quality of Earnings</div>
      <div class="space-y-2 text-sm">
        <div class="flex justify-between">
          <span class="text-gray-400">FCF Conversion (FCF/Net Income)</span>
          <span class="text-white font-semibold">{FCF_CONVERSION}%</span>
        </div>
        <div class="flex justify-between">
          <span class="text-gray-400">SBC as % of Revenue</span>
          <span class="{SBC_COLOR} font-semibold">{SBC_PCT}%</span>
        </div>
        <div class="flex justify-between">
          <span class="text-gray-400">Key Add-backs</span>
          <span class="text-gray-300">{KEY_ADDBACKS}</span>
        </div>
      </div>
      <p class="text-gray-400 text-xs mt-3">{QOE_ASSESSMENT}</p>
    </div>

    <div class="bg-gray-800/50 rounded-lg p-4">
      <div class="text-gray-300 text-sm font-semibold mb-3">Capital Structure</div>
      <div class="space-y-2 text-sm">
        <div class="flex justify-between"><span class="text-gray-400">Total Debt</span><span class="text-white">{TOTAL_DEBT}</span></div>
        <div class="flex justify-between"><span class="text-gray-400">Cash & Equivalents</span><span class="text-emerald-400">{CASH}</span></div>
        <div class="flex justify-between"><span class="text-gray-400">Net Debt / (Cash)</span><span class="{NET_DEBT_COLOR}">{NET_DEBT_DISPLAY}</span></div>
        <div class="flex justify-between"><span class="text-gray-400">Net Debt / EBITDA</span><span class="text-white">{NET_DEBT_EBITDA}x</span></div>
        <div class="flex justify-between"><span class="text-gray-400">Debt Maturity</span><span class="text-gray-300">{DEBT_MATURITY_NOTE}</span></div>
      </div>
    </div>
  </div>
</section>

<!-- ============================================================ -->
<!-- SECTION 10: PORTFOLIO STRATEGY & WHAT WOULD MAKE ME WRONG  -->
<!-- ============================================================ -->
<section id="section-strategy" class="card p-6">
  <h2 class="text-xl font-bold text-white mb-5">
    <i class="fas fa-shield-alt text-teal-400 mr-2"></i>What Would Make Me Wrong
  </h2>

  <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
    <div>
      <div class="text-gray-300 text-sm font-bold mb-2">Core Assumption</div>
      <p class="text-gray-200 text-sm leading-relaxed mb-4">{CORE_ASSUMPTION}</p>

      <div class="text-gray-300 text-sm font-bold mb-2">Kill Switch (Exit Criteria)</div>
      <ul class="space-y-1 text-sm text-gray-300">
        {EXIT_CRITERIA_ITEMS}
        <!-- <li class="flex items-start gap-2"><span class="text-red-400 mt-0.5">✗</span><span>{EXIT_CRITERION}</span></li> -->
      </ul>
    </div>

    <div>
      <div class="text-gray-300 text-sm font-bold mb-2">Monitoring Checklist</div>
      <ul class="space-y-1 text-sm text-gray-400">
        {MONITORING_ITEMS}
      </ul>

      <div class="mt-4 pt-4 border-t border-gray-700">
        <div class="flex items-center gap-3">
          <div class="{RR_BADGE_CLASS} px-4 py-2 rounded-lg text-center">
            <div class="text-white text-xs">R/R Score</div>
            <div class="text-white text-2xl font-black">{RR_SCORE}</div>
          </div>
          <div>
            <div class="text-white font-bold">{VERDICT}</div>
            <div class="text-gray-400 text-xs">Score &gt;3: Attractive | 1-3: Neutral | &lt;1: Unfavorable</div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- Upcoming Catalysts -->
  <div class="mt-6 pt-6 border-t border-gray-700">
    <div class="text-gray-300 text-sm font-bold mb-3">📅 Upcoming Catalysts</div>
    <div class="flex flex-wrap gap-3">
      {CATALYST_BADGES}
      <!-- <div class="bg-gray-800 border border-gray-600 rounded-lg px-4 py-2">
        <span class="text-blue-400 text-xs font-semibold">{DATE}</span>
        <span class="text-gray-200 text-xs ml-2">{EVENT}</span>
        <span class="ml-2 text-xs {SIGNIFICANCE_COLOR}">●</span>
      </div> -->
    </div>
  </div>
</section>

<!-- ============================================================ -->
<!-- SECTION 11: FOOTER                                          -->
<!-- ============================================================ -->
<footer id="section-footer" class="card p-6 text-xs text-gray-500">
  <div class="border-b border-gray-700 pb-4 mb-4">
    <div class="text-red-400 font-semibold text-sm mb-2">⚠ Disclaimer</div>
    <p>This analysis is for informational and educational purposes only and does not constitute financial advice, investment recommendation, or solicitation to buy or sell any security. All data is sourced from public information. Past performance does not guarantee future results. Always conduct your own due diligence and consult a licensed financial advisor before making investment decisions. The agent providing this analysis is an AI system and may contain errors.</p>
  </div>

  <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
    <div>
      <div class="text-gray-400 font-semibold mb-1">Data Sources</div>
      <div class="text-gray-500">{DATA_SOURCES_LIST}</div>
    </div>
    <div>
      <div class="text-gray-400 font-semibold mb-1">Source Tags Used</div>
      <div class="flex flex-wrap gap-1">{SOURCE_TAGS_USED}</div>
    </div>
    <div>
      <div class="text-gray-400 font-semibold mb-1">Generation Info</div>
      <div>Generated: {ANALYSIS_DATETIME}</div>
      <div>Mode: {DATA_MODE}</div>
      <div>Ticker: {TICKER} | Market: {MARKET}</div>
    </div>
  </div>
</footer>

</main>

<!-- ============================================================ -->
<!-- CHART.JS INITIALIZATION                                     -->
<!-- ============================================================ -->
<script>
const globalOptions = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: { labels: { color: '#9ca3af', font: { size: 11 } } },
    tooltip: { backgroundColor: '#1f2937', titleColor: '#f9fafb', bodyColor: '#d1d5db', borderColor: '#374151', borderWidth: 1 }
  },
  scales: {
    x: { grid: { color: '#1f2937' }, ticks: { color: '#6b7280', font: { size: 10 } } },
    y: { grid: { color: '#1f2937' }, ticks: { color: '#6b7280', font: { size: 10 } } }
  }
};

// Chart A: Price History
new Chart(document.getElementById('priceChart'), {
  type: 'line',
  data: {
    labels: {PRICE_CHART_LABELS},
    datasets: [{
      label: '{TICKER} Price',
      data: {PRICE_CHART_DATA},
      borderColor: '#3b82f6',
      backgroundColor: 'rgba(59,130,246,0.08)',
      borderWidth: 2,
      pointRadius: 0,
      fill: true,
      tension: 0.3
    }]
  },
  options: { ...globalOptions }
});

// Chart B: Revenue + Operating Income
new Chart(document.getElementById('revenueChart'), {
  type: 'bar',
  data: {
    labels: {REVENUE_CHART_LABELS},
    datasets: [
      {
        label: 'Revenue',
        data: {REVENUE_CHART_DATA},
        backgroundColor: 'rgba(59,130,246,0.7)',
        borderColor: '#3b82f6',
        borderWidth: 1,
        borderRadius: 3
      },
      {
        label: 'Operating Income',
        data: {OP_INCOME_CHART_DATA},
        backgroundColor: 'rgba(16,185,129,0.7)',
        borderColor: '#10b981',
        borderWidth: 1,
        borderRadius: 3
      }
    ]
  },
  options: { ...globalOptions }
});

// Chart C: Margin Trends
new Chart(document.getElementById('marginChart'), {
  type: 'line',
  data: {
    labels: {MARGIN_CHART_LABELS},
    datasets: [
      {
        label: 'Gross Margin',
        data: {GROSS_MARGIN_DATA},
        borderColor: '#10b981',
        backgroundColor: 'transparent',
        borderWidth: 2,
        pointRadius: 3,
        tension: 0.3
      },
      {
        label: 'Operating Margin',
        data: {OP_MARGIN_DATA},
        borderColor: '#3b82f6',
        backgroundColor: 'transparent',
        borderWidth: 2,
        pointRadius: 3,
        tension: 0.3
      },
      {
        label: 'Net Margin',
        data: {NET_MARGIN_DATA},
        borderColor: '#f59e0b',
        backgroundColor: 'transparent',
        borderWidth: 2,
        pointRadius: 3,
        tension: 0.3
      }
    ]
  },
  options: { ...globalOptions }
});
</script>

</body>
</html>
```

---

## Population Instructions

When generating a dashboard:

1. Replace ALL `{PLACEHOLDER}` values with actual data from `analysis-result.json`
2. For missing data (Grade D or not collected): replace with `<span class="text-gray-600">—</span>`
3. Source tags: use `<span class="source-tag tag-{type}">[TAG]</span>` inline after values
4. Chart data arrays: convert quarterly arrays to JS array syntax `[89.5, 94.9, ...]`
5. Color classes: apply `text-emerald-400` for positive numbers, `text-red-400` for negative
6. Data Confidence Indicator: use Enhanced or Standard template from `color-system.md`
7. R/R Score badge: choose class based on score value (`rr-badge` >3, `rr-badge-neutral` 1-3, `rr-badge-negative` <1)

## Missing Section Handling

If any section's data is unavailable or insufficient, render:
```html
<div class="text-gray-600 italic text-sm p-4 border border-gray-700 rounded-lg">
  [Data unavailable — {reason}]
</div>
```
Never omit a section entirely — the structural skeleton must be preserved.
