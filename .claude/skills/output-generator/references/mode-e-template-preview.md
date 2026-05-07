# Mode E Preview — HTML Template (Earnings Preview, D-7 ~ D-1)

This template provides the complete structural skeleton for Mode E Preview
output. The Analyst (or output-generator) populates every `{PLACEHOLDER}`
manually using the schema in
`references/analysis-framework-earnings.md` (Preview Output Schema).

**Design**: Professional light theme matching Mode C. Tailwind only +
1× Chart.js bar chart for beat/miss history. Korean labels by default
(`output_language="ko"`); English variants in parentheses or comments.

**Manual population path**: This file is the source of truth. The
contract-validation MVP renderer (`scripts/render-earnings.py`) loads this
file as a string template and substitutes placeholders, but final delivery
HTML uses the same skeleton (per ADR 0001 — manual template population
parity with Mode C).

**Backward-compat — Section 4 (Options)**: when
`options_snapshot.status == "unavailable"` (OD-F2), substitute the entire
Section 4 block with the `{OPTIONS_UNAVAILABLE_STUB}` markup defined at the
end of this file.

---

## CDN Block (always include in `<head>`)

```html
<script src="https://cdn.tailwindcss.com"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/css/all.min.css">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
<!-- For Korean (default), also include: -->
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
  <title>{COMPANY_NAME} ({TICKER}) — {QUARTER_LABEL} Earnings Preview ({WINDOW_LABEL})</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/css/all.min.css">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
  {KOREAN_FONT_IF_KR}
  <style>
    * { font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Noto Sans KR', sans-serif; }
    .card { background: #fff; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.06); transition: transform 0.2s, box-shadow 0.2s; }
    .card:hover { transform: translateY(-2px); box-shadow: 0 4px 14px rgba(0,0,0,0.1); }
    .source-tag { font-family: monospace; font-size: 0.7rem; padding: 1px 5px; border-radius: 3px; background: #f3f4f6; }
    .tag-est { color: #b45309; }
    .tag-options { color: #7c3aed; }
    .tag-history { color: #0e7490; }
    .tag-calc { color: #059669; }
    .tag-company { color: #2563eb; }
    .tag-filing { color: #1e3f80; }
    .badge-d { background: #fb923c; color: #fff; }   /* D-N preview badge */
    ::-webkit-scrollbar { width: 6px; }
    ::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 3px; }
  </style>
</head>
<body class="bg-gray-50 text-gray-800">

<!-- ============================================================ -->
<!-- HERO — Earnings Preview                                       -->
<!-- ============================================================ -->
<header style="background: linear-gradient(135deg, #7c2d12 0%, #c2410c 30%, #ea580c 60%, #fb923c 100%);">
  <div class="max-w-7xl mx-auto px-4 sm:px-6 py-8">
    <div class="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
      <div>
        <div class="flex items-center gap-3 mb-2">
          <span class="badge-d px-3 py-1.5 rounded-lg text-sm font-extrabold tracking-wide">
            {WINDOW_LABEL}
          </span>
          <h1 class="text-3xl font-bold text-white tracking-tight">
            {COMPANY_NAME} <span class="text-orange-100/80 text-xl font-mono">{TICKER}</span>
          </h1>
        </div>
        <p class="text-orange-100 text-sm font-semibold mt-1">
          {QUARTER_LABEL} EARNINGS PREVIEW
        </p>
        <p class="text-orange-100/80 text-xs mt-2">
          <i class="fa-solid fa-calendar mr-1"></i>
          발표 예정: {EARNINGS_DATETIME_ET} ({DAYS_UNTIL_LABEL})
        </p>
        {CONFIRMED_WARNING_BANNER}
        <!-- When next_earnings_confirmed == false, substitute:
             <p class="mt-2 text-xs bg-yellow-300/30 text-yellow-100 inline-block px-2 py-1 rounded">
               <i class="fa-solid fa-triangle-exclamation mr-1"></i>
               실적 일정 미확정 — IR 페이지에서 재확인 필요
             </p>
             Otherwise, substitute the empty string. -->
      </div>
      <div class="flex flex-col gap-2 text-right">
        <div class="grid grid-cols-2 gap-x-6 gap-y-1 text-sm">
          <span class="text-orange-100/70">컨센서스 EPS</span>
          <span class="text-white font-semibold">{CONSENSUS_EPS} <span class="source-tag tag-est">[Est]</span></span>
          <span class="text-orange-100/70">컨센서스 매출</span>
          <span class="text-white font-semibold">{CONSENSUS_REV_FORMATTED}</span>
          <span class="text-orange-100/70">현재가</span>
          <span class="text-white font-semibold">{CURRENCY_SYMBOL}{PRICE_AT_ANALYSIS}</span>
          <span class="text-orange-100/70">옵션 implied move</span>
          <span class="text-white font-semibold">±{IMPLIED_MOVE_PCT}% <span class="source-tag tag-options">[Options]</span></span>
        </div>
      </div>
    </div>
    <div class="mt-4 pt-4 border-t border-white/10 flex flex-wrap gap-4 text-xs text-orange-100/60">
      <span>분석일: {ANALYSIS_DATE}</span>
      <span>·</span>
      <span>모드: Earnings Preview (E)</span>
      <span>·</span>
      <span>데이터: {DATA_MODE}</span>
    </div>
  </div>
</header>

<main class="max-w-7xl mx-auto px-4 sm:px-6 py-8 space-y-8">

<!-- ============================================================ -->
<!-- SECTION 1: Consensus Snapshot                                 -->
<!-- ============================================================ -->
<section id="section-consensus">
  <h2 class="text-xl font-bold text-gray-900 mb-4">
    <i class="fa-solid fa-bullseye mr-2 text-orange-500"></i>
    1. 컨센서스 스냅샷
  </h2>
  <div class="grid grid-cols-1 md:grid-cols-2 gap-4">

    <!-- Top-line consensus card -->
    <div class="card p-6">
      <h3 class="text-sm font-bold text-gray-700 mb-3">Top-line</h3>
      <table class="w-full text-sm">
        <thead>
          <tr class="text-xs uppercase text-gray-500 border-b">
            <th class="text-left py-2">항목</th>
            <th class="text-right py-2">Mean</th>
            <th class="text-right py-2">High</th>
            <th class="text-right py-2">Low</th>
            <th class="text-right py-2">출처</th>
          </tr>
        </thead>
        <tbody>
          <tr class="border-b">
            <td class="py-2 font-semibold">EPS</td>
            <td class="text-right py-2">{CONSENSUS_EPS_MEAN}</td>
            <td class="text-right py-2 text-green-600">{CONSENSUS_EPS_HIGH}</td>
            <td class="text-right py-2 text-red-600">{CONSENSUS_EPS_LOW}</td>
            <td class="text-right py-2"><span class="source-tag tag-est">[Est]</span></td>
          </tr>
          <tr class="border-b">
            <td class="py-2 font-semibold">매출 ({CURRENCY_UNIT})</td>
            <td class="text-right py-2">{CONSENSUS_REV_MEAN}</td>
            <td class="text-right py-2 text-green-600">{CONSENSUS_REV_HIGH}</td>
            <td class="text-right py-2 text-red-600">{CONSENSUS_REV_LOW}</td>
            <td class="text-right py-2"><span class="source-tag tag-est">[Est]</span></td>
          </tr>
        </tbody>
      </table>
      <p class="text-xs text-gray-400 mt-3 italic">
        Dispersion (high − low / mean): EPS {EPS_DISPERSION_PCT}% · 매출 {REV_DISPERSION_PCT}%
      </p>
    </div>

    <!-- Segment consensus card -->
    <div class="card p-6">
      <h3 class="text-sm font-bold text-gray-700 mb-3">부문별 컨센서스</h3>
      <table class="w-full text-sm">
        <thead>
          <tr class="text-xs uppercase text-gray-500 border-b">
            <th class="text-left py-2">부문</th>
            <th class="text-left py-2">지표</th>
            <th class="text-right py-2">Mean</th>
            <th class="text-right py-2">레인지</th>
          </tr>
        </thead>
        <tbody>
          {SEGMENT_CONSENSUS_ROWS}
          <!-- Each row pattern:
          <tr class="border-b">
            <td class="py-2 font-semibold">{SEGMENT_NAME}</td>
            <td class="py-2 text-gray-500 text-xs">{METRIC_LABEL}</td>
            <td class="text-right py-2">{MEAN}</td>
            <td class="text-right py-2 text-xs text-gray-500">{LOW}–{HIGH}</td>
          </tr>
          -->
        </tbody>
      </table>
      <p class="text-xs text-gray-400 mt-3">
        {SEGMENT_CONSENSUS_NOTE}
      </p>
    </div>
  </div>
</section>

<!-- ============================================================ -->
<!-- SECTION 2: Beat/Miss History (last 4-8 quarters)              -->
<!-- ============================================================ -->
<section id="section-history">
  <h2 class="text-xl font-bold text-gray-900 mb-4">
    <i class="fa-solid fa-chart-column mr-2 text-orange-500"></i>
    2. Beat/Miss 히스토리 (최근 {N_QUARTERS}분기)
  </h2>
  <p class="text-sm text-gray-500 mb-4">
    Hit rate {HIT_RATE_PCT}% · 평균 surprise {AVG_SURPRISE_PCT}% ·
    평균 1일 주가 반응 {AVG_REACTION_PCT}%
    <span class="source-tag tag-calc">[Calc]</span>
  </p>
  <div class="card p-5">
    <canvas id="beatMissChart" height="160"></canvas>
  </div>

  {INSUFFICIENT_HISTORY_FLAG}
  <!-- When fewer than 4 quarters are available, prepend:
       <p class="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded p-2 mt-2">
         <i class="fa-solid fa-triangle-exclamation mr-1"></i>
         [Quality flag: insufficient history ({N} quarters)]
       </p>
       Otherwise, substitute the empty string. -->

  <!-- Detail table below chart -->
  <div class="card overflow-x-auto mt-4">
    <table class="w-full text-sm">
      <thead>
        <tr class="bg-gray-50 text-gray-600 text-xs uppercase">
          <th class="text-left p-3 font-semibold">분기</th>
          <th class="text-left p-3 font-semibold">발표일</th>
          <th class="text-right p-3 font-semibold">Actual EPS</th>
          <th class="text-right p-3 font-semibold">Consensus</th>
          <th class="text-right p-3 font-semibold">Surprise %</th>
          <th class="text-right p-3 font-semibold">1일 반응</th>
          <th class="text-right p-3 font-semibold">출처</th>
        </tr>
      </thead>
      <tbody>
        {BEAT_MISS_TABLE_ROWS}
        <!-- Each row pattern:
        <tr class="border-b">
          <td class="p-3 font-semibold">{QUARTER}</td>
          <td class="p-3 text-gray-500 text-xs font-mono">{REPORT_DATE}</td>
          <td class="text-right p-3">{ACTUAL_EPS}</td>
          <td class="text-right p-3">{CONSENSUS_EPS}</td>
          <td class="text-right p-3 {BEAT_COLOR_CLASS}">{SURPRISE_PCT}%</td>
          <td class="text-right p-3 {REACTION_COLOR_CLASS}">{REACTION_PCT}%</td>
          <td class="text-right p-3"><span class="source-tag tag-history">[History]</span></td>
        </tr>
        BEAT_COLOR_CLASS:  beat=true → text-green-600, beat=false → text-red-600
        REACTION_COLOR_CLASS: positive → text-green-600, negative → text-red-600
        -->
      </tbody>
    </table>
  </div>
</section>

<!-- ============================================================ -->
<!-- SECTION 3: Key Questions to Watch                             -->
<!-- ============================================================ -->
<section id="section-key-questions">
  <h2 class="text-xl font-bold text-gray-900 mb-4">
    <i class="fa-solid fa-circle-question mr-2 text-orange-500"></i>
    3. 핵심 질문 ({N_KEY_QUESTIONS}개)
  </h2>
  <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
    {KEY_QUESTION_CARDS}
    <!-- Each card pattern:
    <div class="card p-5 border-l-4 border-orange-500">
      <p class="text-sm font-bold text-gray-800 mb-2">
        Q{N}. {QUESTION_TEXT}
      </p>
      <p class="text-xs text-gray-500 mb-3">
        예상 답변: <span class="font-semibold text-gray-700">{EXPECTED_ANSWER}</span>
      </p>
      <div class="grid grid-cols-2 gap-2 text-xs">
        <div class="bg-green-50 rounded p-2">
          <p class="text-green-700 font-semibold">If YES</p>
          <p class="text-green-800">{STOCK_IMPACT_IF_YES}</p>
        </div>
        <div class="bg-red-50 rounded p-2">
          <p class="text-red-700 font-semibold">If NO</p>
          <p class="text-red-800">{STOCK_IMPACT_IF_NO}</p>
        </div>
      </div>
      <p class="text-xs text-gray-600 mt-3 italic">
        <strong>근거:</strong> {RATIONALE}
      </p>
      <p class="text-xs text-gray-500 mt-2">
        <strong>메커니즘:</strong> {MECHANISM}
      </p>
    </div>
    -->
  </div>
</section>

<!-- ============================================================ -->
<!-- SECTION 4: Options & Sentiment                                -->
<!-- ============================================================ -->
{OPTIONS_SECTION}
<!--
When options_snapshot.status == "available", substitute:

<section id="section-options">
  <h2 class="text-xl font-bold text-gray-900 mb-4">
    <i class="fa-solid fa-chart-line mr-2 text-orange-500"></i>
    4. 옵션 & 센티먼트
  </h2>
  <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
    <div class="card p-5 stat-card" style="border-left: 4px solid #7c3aed">
      <p class="text-xs text-gray-500 mb-1">Spot Price</p>
      <p class="text-2xl font-bold text-gray-900">{CURRENCY_SYMBOL}{SPOT_PRICE}</p>
      <p class="text-[10px] text-gray-400 mt-1"><span class="source-tag tag-options">[Options]</span></p>
    </div>
    <div class="card p-5 stat-card" style="border-left: 4px solid #7c3aed">
      <p class="text-xs text-gray-500 mb-1">ATM Strike</p>
      <p class="text-2xl font-bold text-gray-900">{CURRENCY_SYMBOL}{ATM_STRIKE}</p>
      <p class="text-[10px] text-gray-400 mt-1">Expiry {NEAREST_EXPIRY}</p>
    </div>
    <div class="card p-5 stat-card" style="border-left: 4px solid #7c3aed">
      <p class="text-xs text-gray-500 mb-1">ATM Straddle</p>
      <p class="text-2xl font-bold text-gray-900">{CURRENCY_SYMBOL}{ATM_STRADDLE_PRICE}</p>
      <p class="text-[10px] text-gray-400 mt-1">Call {ATM_CALL} / Put {ATM_PUT}</p>
    </div>
    <div class="card p-5 stat-card" style="border-left: 4px solid #7c3aed">
      <p class="text-xs text-gray-500 mb-1">Implied 1-day Move</p>
      <p class="text-2xl font-bold text-purple-700">±{IMPLIED_MOVE_PCT}%</p>
      <p class="text-[10px] text-gray-400 mt-1">IV %ile {IV_PERCENTILE_OR_DASH}</p>
    </div>
  </div>
  <p class="text-xs text-gray-500 mt-4 italic">
    Implied move ≈ (ATM call + ATM put) / spot × 100. Options-derived move
    represents the market's price for a 1-σ event around earnings — not
    directional bias.
  </p>
</section>

When options_snapshot.status == "unavailable" (OD-F2), substitute:

<section id="section-options" class="opacity-80">
  <h2 class="text-xl font-bold text-gray-900 mb-4">
    <i class="fa-solid fa-chart-line mr-2 text-orange-500"></i>
    4. 옵션 & 센티먼트
  </h2>
  <div class="card p-6 bg-gray-50 border border-gray-200 text-center">
    <p class="text-sm text-gray-500">
      <i class="fa-solid fa-circle-exclamation mr-1 text-amber-500"></i>
      <strong>데이터 미수집</strong> — options chain unavailable
    </p>
    <p class="text-xs text-gray-400 mt-2">
      {OPTIONS_UNAVAILABLE_REASON}
    </p>
    <p class="text-xs text-gray-400 mt-1">
      Implied move 데이터 없이 분석 진행. Section 5 Pre-Mortem과 Section 6
      포지션 권고는 컨센서스 + 히스토리 기반.
    </p>
  </div>
</section>
-->

<!-- ============================================================ -->
<!-- SECTION 5: Pre-Mortem                                         -->
<!-- ============================================================ -->
<section id="section-pre-mortem">
  <h2 class="text-xl font-bold text-gray-900 mb-4">
    <i class="fa-solid fa-skull mr-2 text-orange-500"></i>
    5. Pre-Mortem 시나리오
  </h2>
  <p class="text-sm text-gray-500 mb-4">
    "If stock {drops/jumps} {X}% post-print, what would have triggered it?"
    각 시나리오의 확률 합계는 100%.
  </p>
  <div class="card overflow-x-auto">
    <table class="w-full text-sm">
      <thead>
        <tr class="bg-gray-50 text-gray-600 text-xs uppercase">
          <th class="text-left p-3 font-semibold">시나리오</th>
          <th class="text-left p-3 font-semibold">트리거 (구체적 임계치)</th>
          <th class="text-center p-3 font-semibold">주가 영향</th>
          <th class="text-center p-3 font-semibold">확률</th>
          <th class="text-left p-3 font-semibold">메커니즘</th>
        </tr>
      </thead>
      <tbody>
        {PRE_MORTEM_ROWS}
        <!-- Each row pattern:
        <tr class="border-b">
          <td class="p-3 font-semibold">{SCENARIO}</td>
          <td class="p-3 text-xs text-gray-600">{TRIGGER}</td>
          <td class="text-center p-3 {IMPACT_COLOR_CLASS} font-semibold">{STOCK_IMPACT}</td>
          <td class="text-center p-3 font-mono">{PROBABILITY_PCT}%</td>
          <td class="p-3 text-xs text-gray-500">{MECHANISM}</td>
        </tr>
        IMPACT_COLOR_CLASS: stock_impact starts with "+" → text-green-600,
                           starts with "-" → text-red-600,
                           starts with "±" → text-gray-600
        -->
      </tbody>
      <tfoot>
        <tr class="bg-gray-100 font-semibold">
          <td colspan="3" class="p-3 text-right text-gray-700">확률 합계</td>
          <td class="text-center p-3 font-mono">{PROB_TOTAL_PCT}%</td>
          <td class="p-3"></td>
        </tr>
      </tfoot>
    </table>
  </div>
</section>

<!-- ============================================================ -->
<!-- SECTION 6: Pre-Print Position                                 -->
<!-- ============================================================ -->
<section id="section-pre-print">
  <h2 class="text-xl font-bold text-gray-900 mb-4">
    <i class="fa-solid fa-flag mr-2 text-orange-500"></i>
    6. Pre-Print 포지션 권고
  </h2>
  <div class="card p-6">
    <div class="flex items-center gap-3 mb-4">
      <span class="px-4 py-2 rounded-lg text-sm font-extrabold {RECOMMENDATION_BADGE_CLASS}">
        {RECOMMENDATION_LABEL}
      </span>
      <span class="text-xs text-gray-500">
        Hold / Trim / Hedge / Add 중 1개
      </span>
    </div>
    <p class="text-sm text-gray-700 leading-relaxed mb-4">
      {PRE_PRINT_RATIONALE}
    </p>

    {OPTIONS_STRATEGY_BLOCK}
    <!-- When pre_print_position.options_strategy is non-null, substitute:
         <div class="card p-4 bg-purple-50 border border-purple-200 mt-3">
           <p class="text-sm font-bold text-purple-700 mb-1">
             <i class="fa-solid fa-arrows-spin mr-2"></i>
             옵션 전략 (catalyst-driven traders)
           </p>
           <p class="text-sm text-gray-700">{OPTIONS_STRATEGY}</p>
         </div>
         Otherwise, substitute the empty string. -->
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
        <p class="text-xs mb-2">
          <strong class="text-gray-300">Disclaimer:</strong>
          본 리포트는 정보 제공 목적으로만 작성되었으며, 투자 권유나 매수/매도 추천이
          아닙니다. 실적 발표는 변동성이 큰 이벤트로, 본 분석의 시나리오는 발생 가능한
          경로 중 일부에 불과합니다. 모든 투자 의사결정은 본인의 리서치와 리스크 허용
          범위에 따라 수행하시기 바랍니다. This is not investment advice. For
          informational purposes only.
        </p>
        <p class="text-xs">
          Last Updated: {ANALYSIS_DATETIME} · Price: {CURRENCY_SYMBOL}{PRICE_AT_ANALYSIS} ({TICKER})
        </p>
      </div>
      <div class="text-xs text-right">
        <p>Sources: {DATA_SOURCES_LIST}</p>
        <p class="mt-1 text-gray-500">
          Mode E Preview · Window {WINDOW_LABEL} · Generated {ANALYSIS_DATE}
        </p>
      </div>
    </div>
  </div>
</footer>

<!-- ============================================================ -->
<!-- CHART.JS INITIALIZATION (single bar chart for beat/miss)      -->
<!-- ============================================================ -->
<script>
const blue = 'rgba(59,130,246,';
const green = 'rgba(34,197,94,';
const red = 'rgba(239,68,68,';
const gray = 'rgba(107,114,128,';

// Chart: actual − consensus per quarter (signed bar, positive = beat green,
// negative = miss red)
new Chart(document.getElementById('beatMissChart').getContext('2d'), {
  type: 'bar',
  data: {
    labels: {BEAT_MISS_CHART_LABELS},
    datasets: [{
      label: 'EPS Surprise %',
      data: {BEAT_MISS_CHART_DATA},
      backgroundColor: ({BEAT_MISS_CHART_DATA}).map(v => v >= 0 ? green + '0.7)' : red + '0.7)'),
      borderColor: ({BEAT_MISS_CHART_DATA}).map(v => v >= 0 ? green + '1)' : red + '1)'),
      borderWidth: 1,
      borderRadius: 6
    }]
  },
  options: {
    responsive: true,
    plugins: {
      legend: { display: false },
      tooltip: { callbacks: { label: ctx => 'Surprise: ' + ctx.parsed.y.toFixed(1) + '%' } }
    },
    scales: {
      y: { grid: { color: 'rgba(0,0,0,0.05)' }, ticks: { font: { size: 10 }, callback: v => v + '%' } },
      x: { grid: { display: false }, ticks: { font: { size: 10 } } }
    }
  }
});
</script>

</body>
</html>
```

---

## Population Instructions

### Hero placeholders

| Placeholder              | Source                                                  |
|--------------------------|---------------------------------------------------------|
| `{LANG_CODE}`            | `output_language` (`ko` or `en`)                        |
| `{COMPANY_NAME}`         | `company_name`                                          |
| `{TICKER}`               | `ticker`                                                |
| `{QUARTER_LABEL}`        | derived from `earnings_window.next_earnings_date` (e.g. `Q1 2026`) |
| `{WINDOW_LABEL}`         | `earnings_window.window_label` (e.g. `D-3`)             |
| `{EARNINGS_DATETIME_ET}` | `earnings_window.next_earnings_date` + ET time when known |
| `{DAYS_UNTIL_LABEL}`     | `"{abs(days_until)}일 후"` (Korean) / `"in {N} days"` (English) |
| `{CONSENSUS_EPS}`        | `consensus_snapshot.eps.mean`, formatted to 2 decimals  |
| `{CONSENSUS_REV_FORMATTED}` | `consensus_snapshot.revenue.mean` with unit (e.g. `$109.2B`) |
| `{IMPLIED_MOVE_PCT}`     | `options_snapshot.implied_move_pct`, 1 decimal          |
| `{CONFIRMED_WARNING_BANNER}` | yellow banner when `next_earnings_confirmed == false`, empty string otherwise |
| `{KOREAN_FONT_IF_KR}`    | Noto Sans KR `<link>` when `output_language == "ko"`, empty string otherwise |

### Section 1 (Consensus)

- `{SEGMENT_CONSENSUS_ROWS}`: render one `<tr>` per
  `consensus_snapshot.segment_consensus[i]`.
- `{EPS_DISPERSION_PCT}`: `(eps.high − eps.low) / eps.mean × 100`, 1 decimal.
- `{REV_DISPERSION_PCT}`: same formula on revenue.

### Section 2 (Beat/Miss History)

- `{N_QUARTERS}`: `len(beat_miss_history.quarters)`.
- `{HIT_RATE_PCT}`: `summary.hit_rate × 100`, 1 decimal.
- `{AVG_SURPRISE_PCT}`: `summary.avg_surprise_pct`, 1 decimal.
- `{AVG_REACTION_PCT}`: `summary.avg_reaction_1d_pct`, 1 decimal.
- `{INSUFFICIENT_HISTORY_FLAG}`: amber banner when
  `len(quarters) < 4`, empty string otherwise.
- `{BEAT_MISS_TABLE_ROWS}`: one `<tr>` per quarter, oldest → newest left to right.
- `{BEAT_MISS_CHART_LABELS}`: JS array of quarter labels in chronological
  order.
- `{BEAT_MISS_CHART_DATA}`: JS array of `surprise_pct` values matching the
  labels.

### Section 3 (Key Questions)

- `{N_KEY_QUESTIONS}`: `len(key_questions)`.
- `{KEY_QUESTION_CARDS}`: one card per `key_questions[i]`. The renderer
  MUST include the `mechanism` line — the Critic Mode E Mechanism test
  fails if the rendered HTML lacks it.

### Section 4 (Options) — backward compat per OD-F2

- `{OPTIONS_SECTION}`: when `options_snapshot.status == "available"`, use
  the "available" markup. When `status == "unavailable"`, use the
  "unavailable" stub.
- `{OPTIONS_UNAVAILABLE_REASON}`: passthrough from
  `options_snapshot._unavailable_reason` if present, else
  `"yfinance option chain not available for this ticker"`.
- `{IV_PERCENTILE_OR_DASH}`: `iv_percentile` formatted as `{x}%` if
  numeric, else `—` (em-dash).

### Section 5 (Pre-Mortem)

- `{PRE_MORTEM_ROWS}`: one row per `pre_mortem[i]`.
- `{PROB_TOTAL_PCT}`: `sum(pre_mortem[*].probability) × 100`, formatted to
  1 decimal. Renderer asserts the value is in `[99.0, 101.0]`. Off-spec
  values trigger a `[Quality flag]` banner above the table.

### Section 6 (Pre-Print Position)

- `{RECOMMENDATION_LABEL}`: localized label for `pre_print_position.recommendation`.
  - `Hold` → 한국어 `보유 / Hold`
  - `Trim` → `일부 매도 / Trim`
  - `Hedge` → `헤지 / Hedge`
  - `Add` → `추가 매수 / Add`
- `{RECOMMENDATION_BADGE_CLASS}`:
  - `Add` → `bg-green-100 text-green-800`
  - `Hold` → `bg-blue-100 text-blue-800`
  - `Trim` → `bg-amber-100 text-amber-800`
  - `Hedge` → `bg-purple-100 text-purple-800`
- `{OPTIONS_STRATEGY_BLOCK}`: when `pre_print_position.options_strategy`
  is non-null AND `options_snapshot.status == "available"`, render the
  strategy card. Otherwise, substitute empty string.

### Footer

- `{ANALYSIS_DATETIME}`: ISO `analysis_date` + `T00:00:00Z` (or actual
  generation time).
- `{DATA_SOURCES_LIST}`: comma-separated list of unique source tags that
  appear in the analysis (e.g. `[Est], [History], [Options], [Calc]`).

---

## Missing Data Handling

If any required Preview field is absent:

- `consensus_snapshot.eps` missing → render the entire EPS row with `—`
  in every numeric cell + `[Quality flag: missing consensus]` annotation
  above the section.
- `beat_miss_history.quarters` empty → omit the chart and the table,
  show a single banner `<div class="text-gray-400 italic text-sm p-4
  border border-gray-200 rounded-lg bg-gray-50">[Data unavailable —
  earnings history not collected]</div>`.
- `key_questions` empty → omit the section AND surface a BLOCKER
  `[Quality flag: no key questions — Mode E Preview requires ≥4]`.
  The Critic refuses delivery; this is not a graceful fallback.
- `pre_mortem` empty → same as `key_questions` (BLOCKER).
- `options_snapshot.status == "unavailable"` → graceful per OD-F2; use
  the unavailable stub markup.

---

## Backward Compatibility Notes

- This template is additive — it does NOT modify Mode A/B/C/D templates.
- Older snapshots without `earnings_sub_mode` are routed to their
  original mode templates by the orchestrator; this template is only
  selected when `output_mode == "E" AND earnings_sub_mode == "preview"`.
- The Chart.js `beatMissChart` is the ONLY Chart.js usage in this
  template (per plan: 1 chart only). Do NOT add additional charts in
  follow-up phases without updating this contract.
