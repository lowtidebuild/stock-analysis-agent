# HTML Dashboard Template — Mode C

This file provides the complete structural skeleton for the Mode C Deep Dive Dashboard. Claude reads this file, then populates all `{PLACEHOLDER}` values with actual data from run-local `analysis-result.json` and run-local `validated-data.json`.

**Design**: Professional light theme with company-branded header. White cards, subtle shadows, Inter font. Green/red for semantic values only.

---

## CDN Block (always include in `<head>`)

```html
<script src="https://cdn.tailwindcss.com"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/css/all.min.css">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
<!-- For Korean language output, also add: -->
<!-- <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700&display=swap" rel="stylesheet"> -->
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
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/css/all.min.css">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
  {KOREAN_FONT_IF_KR}
  <style>
    * { font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Noto Sans KR', sans-serif; }
    @keyframes pulse-price { 0%, 100% { opacity: 1; } 50% { opacity: 0.7; } }
    @keyframes grad { 0% { background-position: 0% 50%; } 50% { background-position: 100% 50%; } 100% { background-position: 0% 50%; } }
    .pulse-price { animation: pulse-price 2s ease-in-out infinite; }
    .grad-ani { background-size: 200% 200%; animation: grad 4s ease infinite; }
    .card { background: #fff; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.06); transition: transform 0.2s, box-shadow 0.2s; }
    .card:hover { transform: translateY(-2px); box-shadow: 0 4px 14px rgba(0,0,0,0.1); }
    .stat-card { border-left: 4px solid; }
    .source-tag { font-family: monospace; font-size: 0.7rem; padding: 1px 5px; border-radius: 3px; background: #f3f4f6; }
    .tag-api { color: #2563eb; }
    .tag-web { color: #4b5563; }
    .tag-calc { color: #059669; }
    .tag-1s { color: #d97706; }
    .tag-dart { color: #7c3aed; }
    .tag-naver { color: #2563eb; }
    .tag-unverified { color: #dc2626; }
    ::-webkit-scrollbar { width: 6px; }
    ::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 3px; }
  </style>
  <script>
    tailwind.config = { theme: { extend: { colors: {
      brand: { 50: '#eef3fc', 100: '#d4e2f9', 400: '#4285F4', 500: '#3367d6', 600: '#2a56b0', 700: '#1e3f80', 800: '#142a55', 900: '#0d1b38' }
    }}}}
  </script>
</head>
<body class="bg-gray-50 text-gray-800">

<!-- ============================================================ -->
<!-- SECTION 1: HEADER (dark, company-branded gradient)            -->
<!-- ============================================================ -->
<header id="section-header" style="background: linear-gradient(135deg, #0d1b38 0%, #1e3f80 30%, #2a56b0 60%, #3367d6 100%);">
  <div class="max-w-7xl mx-auto px-4 sm:px-6 py-8">
    <div class="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
      <div>
        <div class="flex items-center gap-3 mb-2">
          <div class="w-12 h-12 bg-white/20 rounded-xl flex items-center justify-center">
            <i class="{COMPANY_ICON} text-2xl text-white"></i>
          </div>
          <div>
            <h1 class="text-3xl font-bold text-white tracking-tight">{COMPANY_NAME}</h1>
            <p class="text-blue-200 text-sm font-medium">{EXCHANGE}: {TICKER} · {COMPANY_TYPE}</p>
          </div>
        </div>
        <div class="flex items-center gap-3 mt-4">
          <span class="text-4xl font-extrabold text-white pulse-price">{CURRENCY_SYMBOL}{CURRENT_PRICE}</span>
          <span class="{PRICE_BADGE_CLASS} px-3 py-1 rounded-full text-sm font-semibold">
            <i class="fa-solid fa-caret-{PRICE_DIRECTION} mr-1"></i>{PRICE_CHANGE_PCT}%
          </span>
        </div>
        <p class="text-blue-200/60 text-xs mt-1">{PRICE_AS_OF} · Prev Close {CURRENCY_SYMBOL}{PREV_CLOSE}</p>
      </div>
      <div class="flex flex-col gap-2 text-right">
        <div class="grid grid-cols-2 gap-x-6 gap-y-1 text-sm">
          <span class="text-blue-200/60">Market Cap</span>
          <span class="text-white font-semibold">{MARKET_CAP}</span>
          <span class="text-blue-200/60">52-Wk Range</span>
          <span class="text-white font-semibold">{W52_LOW} – {W52_HIGH}</span>
          <span class="text-blue-200/60">P/E (TTM)</span>
          <span class="text-white font-semibold">{PE_RATIO}x</span>
          <span class="text-blue-200/60">Volume</span>
          <span class="text-white font-semibold">{VOLUME}</span>
        </div>
        <div class="flex gap-2 mt-3 justify-end">
          {EXTERNAL_LINKS_HTML}
          <!-- Pattern: <a href="..." target="_blank" class="bg-white/10 hover:bg-white/20 text-white text-xs px-3 py-1.5 rounded-lg transition"><i class="..."></i> Label</a> -->
        </div>
      </div>
    </div>
    <!-- Data mode + analysis info bar -->
    <div class="mt-4 pt-4 border-t border-white/10 flex flex-wrap gap-4 text-xs text-blue-200/50">
      <span>Analysis Date: {ANALYSIS_DATE}</span>
      <span>·</span>
      <span>Mode: Deep Dive Dashboard (C)</span>
      <span>·</span>
      <span>Data Mode: {DATA_MODE}</span>
    </div>
  </div>
</header>

<main class="max-w-7xl mx-auto px-4 sm:px-6 py-8 space-y-8">

<!-- ============================================================ -->
<!-- SECTION 2: SCENARIO VALUATION (dark gradient card)            -->
<!-- ============================================================ -->
<section id="section-scenarios" class="rounded-2xl overflow-hidden grad-ani" style="background: linear-gradient(135deg, #0d1b38, #1e3f80, #2a56b0, #142a55);">
  <div class="p-6 sm:p-8">
    <h2 class="text-lg font-bold text-blue-200 mb-1"><i class="fa-solid fa-bullseye mr-2"></i>Scenario Valuation (12-Month Targets)</h2>
    <p class="text-blue-200/50 text-xs mb-6">{VARIANT_VIEW_ONE_LINE}</p>
    <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
      <!-- Bear Case -->
      <div class="bg-white/10 backdrop-blur-sm rounded-xl p-5 text-center border border-red-400/30">
        <p class="text-red-300 text-sm font-semibold mb-1">Bear Case</p>
        <p class="text-3xl font-extrabold text-white">{CURRENCY_SYMBOL}{BEAR_TARGET}</p>
        <p class="text-red-300 text-sm mt-1"><i class="fa-solid fa-arrow-down mr-1"></i>{BEAR_RETURN_PCT}</p>
        <p class="text-blue-200/40 text-xs mt-2">{BEAR_KEY_ASSUMPTION}</p>
      </div>
      <!-- Base Case (emphasized) -->
      <div class="bg-white/15 backdrop-blur-sm rounded-xl p-5 text-center border-2 border-blue-300/50 scale-105">
        <p class="text-blue-200 text-sm font-semibold mb-1">Base Case</p>
        <p class="text-4xl font-extrabold text-white">{CURRENCY_SYMBOL}{BASE_TARGET}</p>
        <p class="text-green-300 text-sm mt-1"><i class="fa-solid fa-arrow-up mr-1"></i>{BASE_RETURN_PCT}</p>
        <p class="text-blue-200/40 text-xs mt-2">{BASE_KEY_ASSUMPTION}</p>
      </div>
      <!-- Bull Case -->
      <div class="bg-white/10 backdrop-blur-sm rounded-xl p-5 text-center border border-green-400/30">
        <p class="text-green-300 text-sm font-semibold mb-1">Bull Case</p>
        <p class="text-3xl font-extrabold text-white">{CURRENCY_SYMBOL}{BULL_TARGET}</p>
        <p class="text-green-300 text-sm mt-1"><i class="fa-solid fa-arrow-up mr-1"></i>{BULL_RETURN_PCT}</p>
        <p class="text-blue-200/40 text-xs mt-2">{BULL_KEY_ASSUMPTION}</p>
      </div>
    </div>
  </div>
</section>

<!-- ============================================================ -->
<!-- SECTION 3: COMPANY-SPECIFIC KPI HIGHLIGHT                     -->
<!-- ============================================================ -->
<section id="section-kpi">
  <h2 class="text-xl font-bold text-gray-900 mb-4"><i class="fa-solid fa-chart-bar mr-2 text-brand-400"></i>Key Performance Indicators</h2>
  <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
    {KPI_TILES_HTML}
    <!-- Each KPI tile pattern: -->
    <!--
    <div class="card p-5 stat-card" style="border-left-color: #3b82f6">
      <p class="text-xs text-gray-500 mb-1">{KPI_LABEL}</p>
      <p class="text-2xl font-bold text-brand-700">{KPI_VALUE}</p>
      <p class="text-xs {POS_NEG_COLOR} mt-1"><i class="fa-solid fa-arrow-{up/down}"></i> {KPI_CHANGE}</p>
    </div>
    -->
  </div>
</section>

<!-- ============================================================ -->
<!-- SECTION 4: INVESTMENT THESIS & VARIANT VIEW                   -->
<!-- ============================================================ -->
<section id="section-thesis">
  <h2 class="text-xl font-bold text-gray-900 mb-4"><i class="fa-solid fa-scale-balanced mr-2 text-brand-400"></i>Investment Thesis & Variant View</h2>
  <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
    <!-- Bull / Strengths -->
    <div class="card p-6 border-l-4 border-green-500">
      <h3 class="text-lg font-bold text-green-700 mb-3"><i class="fa-solid fa-arrow-trend-up mr-2"></i>{BULL_HEADING}</h3>
      <div class="space-y-3 text-sm text-gray-700">
        <div class="bg-green-50 rounded-lg p-3">
          <p class="font-semibold text-green-800 mb-1">{VARIANT_VIEW_LABEL}</p>
          <p>{VARIANT_VIEW_CONTENT}</p>
        </div>
        {BULL_POINTS_HTML}
        <!-- Each point:
        <div>
          <p class="font-semibold">{POINT_TITLE}</p>
          <p>{POINT_CONTENT}</p>
        </div>
        -->
      </div>
    </div>
    <!-- Bear / Risks -->
    <div class="card p-6 border-l-4 border-red-500">
      <h3 class="text-lg font-bold text-red-700 mb-3"><i class="fa-solid fa-arrow-trend-down mr-2"></i>{BEAR_HEADING}</h3>
      <div class="space-y-3 text-sm text-gray-700">
        <div class="bg-red-50 rounded-lg p-3">
          <p class="font-semibold text-red-800 mb-1">{KEY_RISK_LABEL}</p>
          <p>{KEY_RISK_CONTENT}</p>
        </div>
        {BEAR_POINTS_HTML}
      </div>
    </div>
  </div>
</section>

<!-- ============================================================ -->
<!-- SECTION 5: VALUATION METRICS                                  -->
<!-- ============================================================ -->
<section id="section-valuation">
  <h2 class="text-xl font-bold text-gray-900 mb-4"><i class="fa-solid fa-calculator mr-2 text-brand-400"></i>Valuation Metrics</h2>
  <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
    {VALUATION_TILES_HTML}
    <!-- Each tile pattern: -->
    <!--
    <div class="card p-4 stat-card" style="border-left-color: #3b82f6">
      <p class="text-xs text-gray-500">{METRIC_LABEL}</p>
      <p class="text-xl font-bold">{METRIC_VALUE}</p>
      <p class="text-xs text-gray-400">{METRIC_CONTEXT}</p>
    </div>
    -->
  </div>
</section>

<!-- ============================================================ -->
<!-- SECTION 6: PEER COMPARISON TABLE                              -->
<!-- ============================================================ -->
<section id="section-peers">
  <h2 class="text-xl font-bold text-gray-900 mb-4"><i class="fa-solid fa-users mr-2 text-brand-400"></i>Peer Comparison</h2>
  <div class="card overflow-x-auto">
    <table class="w-full text-sm">
      <thead>
        <tr class="bg-gray-50 text-gray-600 text-xs uppercase">
          <th class="text-left p-4 font-semibold">Company</th>
          <th class="text-right p-4 font-semibold">Mkt Cap</th>
          <th class="text-right p-4 font-semibold">Revenue (FY)</th>
          <th class="text-right p-4 font-semibold">Rev Growth</th>
          <th class="text-right p-4 font-semibold">Op Margin</th>
          <th class="text-right p-4 font-semibold">P/E</th>
          <th class="text-right p-4 font-semibold">EV/EBITDA</th>
        </tr>
      </thead>
      <tbody>
        {PEER_TABLE_ROWS}
        <!-- Subject company row: class="bg-blue-50/60 border-b font-semibold" -->
        <!-- Peer rows: class="border-b hover:bg-gray-50" -->
        <!-- Positive growth: class="text-green-600" -->
      </tbody>
    </table>
  </div>
</section>

<!-- ============================================================ -->
<!-- SECTION 7: ANALYST PRICE TARGETS                              -->
<!-- ============================================================ -->
<section id="section-analyst">
  <h2 class="text-xl font-bold text-gray-900 mb-4"><i class="fa-solid fa-bullhorn mr-2 text-brand-400"></i>Analyst Price Targets</h2>
  <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
    <div class="card p-5 text-center">
      <p class="text-xs text-gray-500 mb-1">Consensus Average</p>
      <p class="text-3xl font-bold text-brand-600">{CURRENCY_SYMBOL}{AVG_TARGET}</p>
      <p class="text-sm text-green-500 mt-1">{AVG_UPSIDE_PCT} upside</p>
    </div>
    <div class="card p-5 text-center">
      <p class="text-xs text-gray-500 mb-1">Street High</p>
      <p class="text-3xl font-bold text-green-600">{CURRENCY_SYMBOL}{HIGH_TARGET}</p>
      <p class="text-sm text-green-500 mt-1">{HIGH_UPSIDE_PCT} upside</p>
    </div>
    <div class="card p-5 text-center">
      <p class="text-xs text-gray-500 mb-1">Street Low</p>
      <p class="text-3xl font-bold text-red-600">{CURRENCY_SYMBOL}{LOW_TARGET}</p>
      <p class="text-sm text-red-500 mt-1">{LOW_DOWNSIDE_PCT} downside</p>
    </div>
  </div>
  <!-- Rating distribution bar -->
  <div class="card p-5 mt-4">
    <div class="flex justify-between items-center mb-2">
      <span class="text-sm font-semibold">Rating Distribution</span>
      <span class="text-xs text-gray-400">{NUM_ANALYSTS} analysts</span>
    </div>
    <div class="flex h-6 rounded-full overflow-hidden">
      <div class="bg-green-600" style="width: {BUY_PCT}%" title="Buy"></div>
      <div class="bg-gray-400" style="width: {HOLD_PCT}%" title="Hold"></div>
      <div class="bg-red-500" style="width: {SELL_PCT}%" title="Sell"></div>
    </div>
    <div class="flex justify-between text-xs text-gray-500 mt-2">
      <span class="text-green-600 font-semibold">Buy: {BUY_COUNT} ({BUY_PCT}%)</span>
      <span class="text-gray-600 font-semibold">Hold: {HOLD_COUNT} ({HOLD_PCT}%)</span>
      <span class="text-gray-400">Sell: {SELL_COUNT} ({SELL_PCT}%)</span>
    </div>
    {ANALYST_NOTES_HTML}
    <!-- Optional: <div class="mt-3 p-3 bg-blue-50 rounded-lg text-xs text-gray-600"><p><strong>Recent upgrades:</strong> ...</p></div> -->
  </div>
</section>

<!-- ============================================================ -->
<!-- SECTION 8: INTERACTIVE CHARTS                                 -->
<!-- ============================================================ -->
<section id="section-charts">
  <h2 class="text-xl font-bold text-gray-900 mb-4"><i class="fa-solid fa-chart-bar mr-2 text-brand-400"></i>Financial Charts</h2>
  <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
    <div class="card p-5">
      <h3 class="text-sm font-semibold text-gray-700 mb-3">Annual Revenue & Operating Income</h3>
      <canvas id="revenueChart" height="200"></canvas>
    </div>
    <div class="card p-5">
      <h3 class="text-sm font-semibold text-gray-700 mb-3">{CHART_B_TITLE}</h3>
      <canvas id="segmentChart" height="200"></canvas>
    </div>
  </div>
  <div class="card p-5 mt-4">
    <h3 class="text-sm font-semibold text-gray-700 mb-3">Stock Price vs Analyst Targets (52-Week)</h3>
    <canvas id="priceChart" height="180"></canvas>
  </div>
</section>

<!-- ============================================================ -->
<!-- SECTION 9: FINANCIAL DETAIL                                   -->
<!-- ============================================================ -->
<section id="section-financials">
  <h2 class="text-xl font-bold text-gray-900 mb-4"><i class="fa-solid fa-file-invoice-dollar mr-2 text-brand-400"></i>Financial Detail Analysis</h2>
  <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
    {FINANCIAL_DETAIL_CARDS_HTML}
    <!-- Each card pattern: -->
    <!--
    <div class="card p-5">
      <h3 class="text-sm font-bold text-brand-600 mb-3"><i class="fa-solid fa-chart-line mr-2"></i>{CARD_TITLE}</h3>
      <div class="space-y-2 text-sm">
        <div class="flex justify-between"><span class="text-gray-500">{LABEL}</span><span class="font-semibold">{VALUE}</span></div>
      </div>
    </div>
    -->
  </div>
  <!-- Key Insight -->
  <div class="card p-5 mt-4 bg-blue-50 border border-blue-200">
    <p class="text-sm text-gray-700">{KEY_INSIGHT_HTML}</p>
  </div>
</section>

<!-- ============================================================ -->
<!-- SECTION 10: PORTFOLIO STRATEGY & EXECUTION                    -->
<!-- ============================================================ -->
<section id="section-strategy">
  <h2 class="text-xl font-bold text-gray-900 mb-4"><i class="fa-solid fa-chess-knight mr-2 text-brand-400"></i>Portfolio Strategy & Execution</h2>
  <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
    <!-- Scenario Positioning -->
    <div class="card p-6">
      <h3 class="text-sm font-bold text-gray-700 mb-4">Scenario Positioning</h3>
      <div class="space-y-4 text-sm">
        <div class="bg-green-50 rounded-lg p-4">
          <p class="font-bold text-green-700">Bull (Probability {BULL_PROB}%)</p>
          <p class="text-gray-600 mt-1">{BULL_STRATEGY}</p>
        </div>
        <div class="bg-blue-50 rounded-lg p-4">
          <p class="font-bold text-blue-700">Base (Probability {BASE_PROB}%)</p>
          <p class="text-gray-600 mt-1">{BASE_STRATEGY}</p>
        </div>
        <div class="bg-red-50 rounded-lg p-4">
          <p class="font-bold text-red-700">Bear (Probability {BEAR_PROB}%)</p>
          <p class="text-gray-600 mt-1">{BEAR_STRATEGY}</p>
        </div>
      </div>
    </div>
    <!-- Execution Guidelines -->
    <div class="card p-6">
      <h3 class="text-sm font-bold text-gray-700 mb-4">Execution Guidelines</h3>
      <div class="space-y-3 text-sm">
        {EXECUTION_ITEMS_HTML}
        <!-- Pattern:
        <div class="flex items-center gap-3 p-3 bg-gray-50 rounded-lg">
          <div class="w-10 h-10 bg-brand-400 rounded-full flex items-center justify-center flex-shrink-0">
            <i class="fa-solid fa-{icon} text-white text-xs"></i>
          </div>
          <div>
            <p class="font-semibold text-gray-700">{LABEL}</p>
            <p class="text-gray-500 text-xs">{DETAIL}</p>
          </div>
        </div>
        -->
        <div class="mt-2 p-3 bg-blue-50 rounded-lg border border-blue-200">
          <p class="font-bold text-blue-800 text-xs mb-2">Key Monitoring Points</p>
          <ul class="text-xs text-gray-600 space-y-1">
            {MONITORING_ITEMS_HTML}
          </ul>
        </div>
      </div>
    </div>
  </div>
</section>

</main>

<!-- ============================================================ -->
<!-- FOOTER                                                        -->
<!-- ============================================================ -->
<footer class="bg-gray-900 text-gray-400 mt-12">
  <div class="max-w-7xl mx-auto px-4 sm:px-6 py-8">
    <div class="flex flex-col md:flex-row justify-between items-start gap-4">
      <div>
        <p class="text-xs mb-2"><strong class="text-gray-300">Disclaimer:</strong> This dashboard is for informational purposes only and does not constitute investment advice, a recommendation, or solicitation to buy or sell securities. All investment decisions should be made based on your own research and risk tolerance. Past performance does not guarantee future results.</p>
        <p class="text-xs">Last Updated: {ANALYSIS_DATETIME} · Price: {CURRENCY_SYMBOL}{CURRENT_PRICE} ({TICKER})</p>
      </div>
      <div class="text-xs text-right">
        <p>Sources: {DATA_SOURCES_LIST}</p>
      </div>
    </div>
  </div>
</footer>

<!-- ============================================================ -->
<!-- CHART.JS INITIALIZATION (light theme)                         -->
<!-- ============================================================ -->
<script>
const blue = 'rgba(59,130,246,';
const green = 'rgba(52,168,83,';
const yellow = 'rgba(251,188,5,';
const red = 'rgba(234,67,53,';
const gray = 'rgba(107,114,128,';

// Chart A: Revenue & Operating Income
new Chart(document.getElementById('revenueChart').getContext('2d'), {
  type: 'bar',
  data: {
    labels: {REVENUE_CHART_LABELS},
    datasets: [
      { label: 'Revenue', data: {REVENUE_CHART_DATA}, backgroundColor: blue + '0.55)', borderColor: blue + '1)', borderWidth: 1, borderRadius: 6, order: 2 },
      { label: 'Op Income', type: 'line', data: {OP_INCOME_CHART_DATA}, borderColor: green + '1)', backgroundColor: green + '0.1)', borderWidth: 2.5, pointRadius: 5, pointBackgroundColor: green + '1)', fill: false, order: 1 }
    ]
  },
  options: { responsive: true, plugins: { legend: { position: 'bottom', labels: { font: { size: 11 }, usePointStyle: true } } }, scales: { y: { grid: { color: 'rgba(0,0,0,0.05)' }, ticks: { font: { size: 10 }, callback: v => '{CURRENCY_PREFIX}' + v + '{UNIT_SUFFIX}' } }, x: { grid: { display: false }, ticks: { font: { size: 10 } } } } }
});

// Chart B: Segment/Category breakdown
new Chart(document.getElementById('segmentChart').getContext('2d'), {
  type: 'bar',
  data: {
    labels: {SEGMENT_CHART_LABELS},
    datasets: [{ label: '{SEGMENT_CHART_DATASET_LABEL}', data: {SEGMENT_CHART_DATA}, backgroundColor: [blue + '0.7)', green + '0.7)', yellow + '0.7)', blue + '0.35)', gray + '0.5)'], borderColor: [blue + '1)', green + '1)', yellow + '1)', blue + '0.6)', gray + '0.8)'], borderWidth: 1, borderRadius: 6 }]
  },
  options: { responsive: true, indexAxis: 'y', plugins: { legend: { display: false } }, scales: { x: { grid: { color: 'rgba(0,0,0,0.05)' }, ticks: { font: { size: 10 }, callback: v => '{CURRENCY_PREFIX}' + v + '{UNIT_SUFFIX}' } }, y: { grid: { display: false }, ticks: { font: { size: 10 } } } } }
});

// Chart C: Price vs Analyst Targets
new Chart(document.getElementById('priceChart').getContext('2d'), {
  type: 'line',
  data: {
    labels: {PRICE_CHART_LABELS},
    datasets: [
      { label: '{TICKER} Price', data: {PRICE_CHART_DATA}, borderColor: blue + '1)', backgroundColor: blue + '0.06)', borderWidth: 2.5, pointRadius: 4, pointBackgroundColor: blue + '1)', fill: true, tension: 0.3 },
      { label: 'Bull Target ({CURRENCY_SYMBOL}{BULL_TARGET})', data: {BULL_LINE_DATA}, borderColor: green + '0.5)', borderWidth: 1.5, borderDash: [8, 4], pointRadius: 0, fill: false },
      { label: 'Consensus ({CURRENCY_SYMBOL}{AVG_TARGET})', data: {CONSENSUS_LINE_DATA}, borderColor: yellow + '0.6)', borderWidth: 1.5, borderDash: [4, 4], pointRadius: 0, fill: false },
      { label: 'Bear Target ({CURRENCY_SYMBOL}{BEAR_TARGET})', data: {BEAR_LINE_DATA}, borderColor: red + '0.5)', borderWidth: 1.5, borderDash: [8, 4], pointRadius: 0, fill: false }
    ]
  },
  options: { responsive: true, plugins: { legend: { position: 'bottom', labels: { font: { size: 10 }, usePointStyle: true } } }, scales: { y: { grid: { color: 'rgba(0,0,0,0.05)' }, ticks: { font: { size: 10 }, callback: v => '{CURRENCY_PREFIX}' + v } }, x: { grid: { display: false }, ticks: { font: { size: 10 } } } } }
});
</script>

</body>
</html>
```

---

## Population Instructions

When generating a dashboard:

1. Replace ALL `{PLACEHOLDER}` values with actual data from `analysis-result.json`
2. For missing data (Grade D or not collected): replace with `<span class="text-gray-400">—</span>`
3. Source tags: use `<span class="source-tag tag-{type}">[TAG]</span>` inline after values
4. Chart data arrays: convert to JS array syntax `[89.5, 94.9, ...]`
5. Price change badge: positive → `bg-green-500/20 text-green-200`, negative → `bg-red-500/25 text-red-200`
6. Positive metric changes: `text-green-600`, negative: `text-red-600`, neutral: `text-gray-500`
7. `stat-card` border colors: use `#3b82f6` (blue) as default. Vary sparingly for visual rhythm.
8. Company icon: use appropriate FontAwesome icon (e.g., `fa-brands fa-google`, `fas fa-microchip`)

## Missing Section Handling

If any section's data is unavailable or insufficient, render:
```html
<div class="text-gray-400 italic text-sm p-4 border border-gray-200 rounded-lg bg-gray-50">
  [Data unavailable — {reason}]
</div>
```
Never omit a section entirely — the structural skeleton must be preserved.
