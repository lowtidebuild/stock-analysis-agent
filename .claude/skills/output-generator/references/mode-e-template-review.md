# Mode E Review — HTML Template (Earnings Review, D ~ D+3)

This template provides the complete structural skeleton for Mode E Review
output. The Analyst (or output-generator) populates every `{PLACEHOLDER}`
manually using the schema in
`references/analysis-framework-earnings.md` (Review Output Schema).

**Design**: Same Tailwind palette as Mode C / Mode E Preview, but the hero
uses an emerald-to-blue gradient when `actual_vs_consensus.eps.beat == true`
and a rose-to-orange gradient when `beat == false`. The "outdated" Light
Verdict badge styling is documented in Section 5.

**Manual population path**: This file is the source of truth (per ADR 0001).

**Backward-compat — no prior Mode C snapshot**: when
`thesis_impact.prior_mode_c_date == null`, substitute Section 4
(Thesis Impact) with the `{THESIS_IMPACT_NO_BASELINE_STUB}` markup defined
at the end of this file, and Section 5 (Light Verdict Update) with the
`{LIGHT_VERDICT_NO_PRIOR_STUB}` markup.

---

## CDN Block (always include in `<head>`)

```html
<script src="https://cdn.tailwindcss.com"></script>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/css/all.min.css">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
<!-- For Korean (default), also include: -->
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700&display=swap" rel="stylesheet">
<!-- Note: Review does NOT use Chart.js (no beat/miss bar chart needed —
     the Print Snapshot table is the visual focus). -->
```

---

## Full HTML Skeleton

```html
<!DOCTYPE html>
<html lang="{LANG_CODE}">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{COMPANY_NAME} ({TICKER}) — {QUARTER_LABEL} Earnings Review ({WINDOW_LABEL})</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/css/all.min.css">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
  {KOREAN_FONT_IF_KR}
  <style>
    * { font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Noto Sans KR', sans-serif; }
    .card { background: #fff; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.06); transition: transform 0.2s, box-shadow 0.2s; }
    .card:hover { transform: translateY(-2px); box-shadow: 0 4px 14px rgba(0,0,0,0.1); }
    .source-tag { font-family: monospace; font-size: 0.7rem; padding: 1px 5px; border-radius: 3px; background: #f3f4f6; }
    .tag-est { color: #b45309; }
    .tag-history { color: #0e7490; }
    .tag-calc { color: #059669; }
    .tag-company { color: #2563eb; }
    .tag-filing { color: #1e3f80; }
    .tag-portal { color: #4b5563; }
    .badge-d-plus { background: #10b981; color: #fff; }   /* D+N badge (beat) */
    .badge-d-plus-miss { background: #ef4444; color: #fff; }  /* D+N badge (miss) */
    .badge-outdated {
      background: repeating-linear-gradient(
        45deg,
        #fef3c7,
        #fef3c7 6px,
        #fde68a 6px,
        #fde68a 12px
      );
      color: #92400e;
      border: 1px dashed #d97706;
      font-style: italic;
    }
    ::-webkit-scrollbar { width: 6px; }
    ::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 3px; }
  </style>
</head>
<body class="bg-gray-50 text-gray-800">

<!-- ============================================================ -->
<!-- HERO — Earnings Review                                        -->
<!-- ============================================================ -->
<header style="background: {HERO_GRADIENT_CSS};">
  <!-- HERO_GRADIENT_CSS:
       beat == true → linear-gradient(135deg, #064e3b 0%, #047857 30%, #059669 60%, #10b981 100%)
       beat == false → linear-gradient(135deg, #7f1d1d 0%, #b91c1c 30%, #dc2626 60%, #f97316 100%) -->
  <div class="max-w-7xl mx-auto px-4 sm:px-6 py-8">
    <div class="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
      <div>
        <div class="flex items-center gap-3 mb-2">
          <span class="{HERO_BADGE_CLASS} px-3 py-1.5 rounded-lg text-sm font-extrabold tracking-wide">
            {WINDOW_LABEL}
          </span>
          <h1 class="text-3xl font-bold text-white tracking-tight">
            {COMPANY_NAME} <span class="text-white/80 text-xl font-mono">{TICKER}</span>
          </h1>
        </div>
        <p class="text-white/90 text-sm font-semibold mt-1">
          {QUARTER_LABEL} EARNINGS REVIEW
        </p>
        <div class="flex items-center gap-3 mt-3">
          <span class="px-3 py-1 rounded-full text-sm font-bold {BEAT_MISS_FLAG_CLASS}">
            <i class="fa-solid fa-{BEAT_MISS_ICON} mr-1"></i>
            {BEAT_MISS_LABEL}
          </span>
          <span class="text-white/80 text-sm">
            EPS surprise <span class="font-semibold">{EPS_SURPRISE_PCT}%</span>
          </span>
        </div>
      </div>
      <div class="flex flex-col gap-2 text-right">
        <div class="grid grid-cols-2 gap-x-6 gap-y-1 text-sm">
          <span class="text-white/70">Post-market</span>
          <span class="text-white font-semibold">{POST_MARKET_PCT_OR_DASH}</span>
          <span class="text-white/70">Next-day</span>
          <span class="text-white font-semibold">{NEXT_DAY_PCT_OR_DASH}</span>
          <span class="text-white/70">Verdict</span>
          <span class="text-white font-semibold">{PRIOR_VERDICT} → {UPDATED_VERDICT}</span>
          <span class="text-white/70">현재가</span>
          <span class="text-white font-semibold">{CURRENCY_SYMBOL}{PRICE_AT_ANALYSIS}</span>
        </div>
      </div>
    </div>
    <div class="mt-4 pt-4 border-t border-white/10 flex flex-wrap gap-4 text-xs text-white/60">
      <span>분석일: {ANALYSIS_DATE}</span>
      <span>·</span>
      <span>모드: Earnings Review (E)</span>
      <span>·</span>
      <span>발표일: {ACTUAL_EARNINGS_DATE}</span>
      <span>·</span>
      <span>데이터: {DATA_MODE}</span>
    </div>
  </div>
</header>

<main class="max-w-7xl mx-auto px-4 sm:px-6 py-8 space-y-8">

<!-- ============================================================ -->
<!-- SECTION 1: Print Snapshot (beat/miss table)                   -->
<!-- ============================================================ -->
<section id="section-print-snapshot">
  <h2 class="text-xl font-bold text-gray-900 mb-4">
    <i class="fa-solid fa-table-cells mr-2 text-emerald-600"></i>
    1. Print Snapshot
  </h2>
  <div class="card overflow-x-auto">
    <table class="w-full text-sm">
      <thead>
        <tr class="bg-gray-50 text-gray-600 text-xs uppercase">
          <th class="text-left p-3 font-semibold">항목</th>
          <th class="text-right p-3 font-semibold">Actual</th>
          <th class="text-right p-3 font-semibold">Consensus</th>
          <th class="text-right p-3 font-semibold">Surprise %</th>
          <th class="text-center p-3 font-semibold">Beat?</th>
          <th class="text-right p-3 font-semibold">출처</th>
        </tr>
      </thead>
      <tbody>
        <!-- Top-line rows (always 2: EPS + Revenue) -->
        <tr class="border-b font-semibold">
          <td class="p-3">EPS</td>
          <td class="text-right p-3">{EPS_ACTUAL}</td>
          <td class="text-right p-3 text-gray-500">{EPS_CONSENSUS}</td>
          <td class="text-right p-3 {EPS_BEAT_COLOR}">{EPS_SURPRISE_PCT}%</td>
          <td class="text-center p-3">
            <span class="inline-block px-2 py-0.5 rounded text-xs font-bold {EPS_BEAT_BADGE_CLASS}">
              {EPS_BEAT_LABEL}
            </span>
          </td>
          <td class="text-right p-3"><span class="source-tag tag-company">[Company]</span></td>
        </tr>
        <tr class="border-b font-semibold">
          <td class="p-3">매출 ({CURRENCY_UNIT})</td>
          <td class="text-right p-3">{REV_ACTUAL}</td>
          <td class="text-right p-3 text-gray-500">{REV_CONSENSUS}</td>
          <td class="text-right p-3 {REV_BEAT_COLOR}">{REV_SURPRISE_PCT}%</td>
          <td class="text-center p-3">
            <span class="inline-block px-2 py-0.5 rounded text-xs font-bold {REV_BEAT_BADGE_CLASS}">
              {REV_BEAT_LABEL}
            </span>
          </td>
          <td class="text-right p-3"><span class="source-tag tag-company">[Company]</span></td>
        </tr>
        <!-- Segment rows -->
        {SEGMENT_PRINT_ROWS}
        <!-- Each segment row pattern:
        <tr class="border-b">
          <td class="p-3 text-gray-700">{SEGMENT_NAME} ({METRIC_LABEL})</td>
          <td class="text-right p-3">{ACTUAL}</td>
          <td class="text-right p-3 text-gray-500">{CONSENSUS}</td>
          <td class="text-right p-3 {BEAT_COLOR}">{SURPRISE_PCT}%</td>
          <td class="text-center p-3">
            <span class="inline-block px-2 py-0.5 rounded text-xs font-bold {BEAT_BADGE_CLASS}">
              {BEAT_LABEL}
            </span>
          </td>
          <td class="text-right p-3"><span class="source-tag tag-company">[Company]</span></td>
        </tr>
        BEAT_COLOR: beat==true → text-green-600, beat==false → text-red-600
        BEAT_BADGE_CLASS: beat==true → bg-green-100 text-green-800,
                          beat==false → bg-red-100 text-red-800
        BEAT_LABEL: beat==true → "Beat", beat==false → "Miss"
        -->
        {OP_MARGIN_ROW_OPTIONAL}
        <!-- When actual_vs_consensus.operating_margin is non-null, append:
        <tr class="border-b">
          <td class="p-3 text-gray-700">영업이익률</td>
          <td class="text-right p-3">{OM_ACTUAL_PCT}%</td>
          <td class="text-right p-3 text-gray-500">{OM_CONSENSUS_PCT}%</td>
          <td class="text-right p-3 {OM_BEAT_COLOR}">+{OM_DELTA_PP}pp</td>
          <td class="text-center p-3">
            <span class="inline-block px-2 py-0.5 rounded text-xs font-bold {OM_BEAT_BADGE_CLASS}">
              {OM_BEAT_LABEL}
            </span>
          </td>
          <td class="text-right p-3"><span class="source-tag tag-filing">[Filing]</span></td>
        </tr>
        -->
      </tbody>
    </table>
  </div>
  <p class="text-xs text-gray-400 mt-3 italic">
    Surprise % = (actual − consensus) / |consensus| × 100. Beat 정의: top-line은 surprise > 0, cost 항목 (capex 가이던스 등)은 surprise &lt; 0.
  </p>
</section>

<!-- ============================================================ -->
<!-- SECTION 2: Guidance Update                                    -->
<!-- ============================================================ -->
<section id="section-guidance">
  <h2 class="text-xl font-bold text-gray-900 mb-4">
    <i class="fa-solid fa-arrow-trend-up mr-2 text-emerald-600"></i>
    2. 가이던스 업데이트
  </h2>
  <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
    <div class="card p-5 text-center">
      <p class="text-xs text-gray-500 mb-1">FY EPS 컨센서스 (Pre)</p>
      <p class="text-3xl font-bold text-gray-700">{CURRENCY_SYMBOL}{FY_EPS_PRE}</p>
      <p class="text-[10px] text-gray-400 mt-1"><span class="source-tag tag-est">[Est]</span></p>
    </div>
    <div class="card p-5 text-center">
      <p class="text-xs text-gray-500 mb-1">FY EPS 컨센서스 (Post)</p>
      <p class="text-3xl font-bold text-emerald-600">{CURRENCY_SYMBOL}{FY_EPS_POST}</p>
      <p class="text-[10px] text-gray-400 mt-1"><span class="source-tag tag-est">[Est]</span></p>
    </div>
    <div class="card p-5 text-center">
      <p class="text-xs text-gray-500 mb-1">변화</p>
      <p class="text-3xl font-bold {GUIDANCE_DELTA_COLOR}">
        {GUIDANCE_DELTA_PCT}%
      </p>
      <p class="text-xs text-gray-400 mt-1">
        Tone: <strong class="{GUIDANCE_TONE_COLOR}">{GUIDANCE_TONE_LABEL}</strong>
      </p>
    </div>
  </div>
  <div class="card p-5 mt-4 bg-blue-50 border border-blue-200">
    <p class="text-sm font-bold text-blue-800 mb-2">
      <i class="fa-solid fa-bullhorn mr-2"></i>
      회사 가이던스 변화
    </p>
    <p class="text-sm text-gray-700">{COMPANY_GUIDANCE_CHANGE}</p>
  </div>
</section>

<!-- ============================================================ -->
<!-- SECTION 3: Key Questions Answered (vs Preview)                -->
<!-- ============================================================ -->
<section id="section-questions-answered">
  <h2 class="text-xl font-bold text-gray-900 mb-4">
    <i class="fa-solid fa-circle-check mr-2 text-emerald-600"></i>
    3. 핵심 질문 답변 (vs Preview)
  </h2>
  <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
    {QUESTIONS_ANSWERED_CARDS}
    <!-- Each card pattern:
    <div class="card p-5 border-l-4 {ANSWER_BORDER_CLASS}">
      <p class="text-sm font-bold text-gray-800 mb-2">
        Q{N}. {QUESTION_TEXT}
      </p>
      <div class="flex items-center gap-2 mb-3">
        <span class="px-2 py-0.5 rounded text-xs font-bold {ANSWER_BADGE_CLASS}">
          {ANSWER_STATUS_LABEL}
        </span>
        <span class="text-xs text-gray-500">실제 데이터</span>
      </div>
      <p class="text-sm text-gray-700 mb-3"><strong>실제:</strong> {ACTUAL_DATA}</p>
      <p class="text-xs text-gray-600 italic">
        <strong>Thesis 영향:</strong> {THESIS_IMPACT}
      </p>
    </div>

    ANSWER_BORDER_CLASS:
      yes → border-green-500
      no → border-red-500
      partial → border-amber-500
    ANSWER_BADGE_CLASS:
      yes → bg-green-100 text-green-800
      no → bg-red-100 text-red-800
      partial → bg-amber-100 text-amber-800
    ANSWER_STATUS_LABEL:
      yes → "✓ YES"
      no → "✗ NO"
      partial → "± 부분"
    -->
  </div>
</section>

<!-- ============================================================ -->
<!-- SECTION 4: Thesis Impact (long + short pillars)               -->
<!-- ============================================================ -->
{THESIS_IMPACT_SECTION}
<!--
When thesis_impact.prior_mode_c_date is non-null, substitute:

<section id="section-thesis-impact">
  <h2 class="text-xl font-bold text-gray-900 mb-4">
    <i class="fa-solid fa-scale-balanced mr-2 text-emerald-600"></i>
    4. Thesis Impact (vs prior Mode C, {PRIOR_MODE_C_DATE})
  </h2>
  <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
    <!-- Long pillars -->
    <div class="card p-6 border-l-4 border-green-500">
      <h3 class="text-lg font-bold text-green-700 mb-3">
        <i class="fa-solid fa-arrow-trend-up mr-2"></i>Long Pillars
      </h3>
      <div class="space-y-3">
        {LONG_PILLAR_ROWS}
        <!-- Each pillar row pattern:
        <div class="border-b last:border-b-0 pb-3 last:pb-0">
          <p class="font-semibold text-gray-800 text-sm mb-1">{PILLAR_NAME}</p>
          <p class="text-xs text-gray-500 mb-2">
            <span class="inline-block px-2 py-0.5 rounded {PRIOR_STATUS_BADGE_CLASS}">{PRIOR_STATUS}</span>
            <i class="fa-solid fa-arrow-right text-gray-400 mx-1"></i>
            <span class="inline-block px-2 py-0.5 rounded {CURRENT_STATUS_BADGE_CLASS}">{CURRENT_STATUS}</span>
            <span class="ml-2 text-xs {TREND_COLOR}">{TREND_LABEL}</span>
          </p>
          <p class="text-xs text-gray-700">{EVIDENCE}</p>
        </div>

        Status badge color contract:
          Strengthened → bg-emerald-100 text-emerald-800
          On track    → bg-blue-100 text-blue-800
          Watching    → bg-gray-100 text-gray-700
          Weakened    → bg-amber-100 text-amber-800
          Broken      → bg-red-100 text-red-800
        Trend label color:
          Positive → text-green-600 ↑
          Stable   → text-gray-500 →
          Negative → text-red-600 ↓
        -->
      </div>
    </div>
    <!-- Short pillars -->
    <div class="card p-6 border-l-4 border-red-500">
      <h3 class="text-lg font-bold text-red-700 mb-3">
        <i class="fa-solid fa-arrow-trend-down mr-2"></i>Short Pillars
      </h3>
      <div class="space-y-3">
        {SHORT_PILLAR_ROWS}
        <!-- Same pattern as LONG_PILLAR_ROWS -->
      </div>
    </div>
  </div>
</section>

When thesis_impact.prior_mode_c_date is null (no prior Mode C baseline),
substitute the {THESIS_IMPACT_NO_BASELINE_STUB}:

<section id="section-thesis-impact" class="opacity-90">
  <h2 class="text-xl font-bold text-gray-900 mb-4">
    <i class="fa-solid fa-scale-balanced mr-2 text-emerald-600"></i>
    4. Thesis Impact
  </h2>
  <div class="card p-6 bg-amber-50 border border-amber-200">
    <p class="text-sm text-amber-800">
      <i class="fa-solid fa-circle-info mr-1"></i>
      <strong>No prior Mode C baseline</strong> — first-look review
    </p>
    <p class="text-xs text-amber-700 mt-2">
      이 종목은 이전 Mode C 분석 snapshot이 없어 thesis pillar 변화를 추적할 수 없습니다.
      "{REVIEW_FIRST_LOOK_NOTE}"
    </p>
    <p class="text-xs text-amber-700 mt-2">
      Mode C 분석을 먼저 실행하면 다음 실적 발표 시 thesis 변화를 자동으로 추적할 수 있습니다.
    </p>
  </div>
</section>
-->

<!-- ============================================================ -->
<!-- SECTION 5: Light Verdict Update                               -->
<!-- ============================================================ -->
{LIGHT_VERDICT_SECTION}
<!--
When light_verdict_update.prior_rr_score is non-null, substitute:

<section id="section-light-verdict">
  <h2 class="text-xl font-bold text-gray-900 mb-4">
    <i class="fa-solid fa-flag-checkered mr-2 text-emerald-600"></i>
    5. Light Verdict Update
  </h2>
  <div class="card p-6">
    <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
      <div class="text-center p-4 bg-gray-50 rounded-lg">
        <p class="text-xs text-gray-500 mb-1">Prior R/R Score</p>
        <p class="text-3xl font-bold text-gray-700">{PRIOR_RR_SCORE}</p>
        <p class="text-xs text-gray-400 mt-1">Mode C, {PRIOR_MODE_C_DATE}</p>
      </div>
      <div class="text-center p-4 bg-amber-50 rounded-lg badge-outdated">
        <p class="text-xs text-amber-800 mb-1">Updated R/R Score</p>
        <p class="text-3xl font-bold text-amber-700">—</p>
        <p class="text-xs text-amber-700 mt-1">
          <i class="fa-solid fa-triangle-exclamation mr-1"></i>
          Outdated · DCF 미재실행
        </p>
      </div>
      <div class="text-center p-4 bg-blue-50 rounded-lg">
        <p class="text-xs text-blue-700 mb-1">Verdict</p>
        <p class="text-2xl font-bold text-blue-700">{PRIOR_VERDICT} → {UPDATED_VERDICT}</p>
        <p class="text-xs text-blue-600 mt-1">{VERDICT_CHANGE_LABEL}</p>
      </div>
    </div>
    <div class="card p-4 bg-gray-50 border border-gray-200 mt-3">
      <p class="text-sm font-bold text-gray-700 mb-2">
        <i class="fa-solid fa-info-circle mr-1"></i>
        업데이트 사유
      </p>
      <p class="text-sm text-gray-700 leading-relaxed">{LIGHT_VERDICT_REASON}</p>
    </div>
  </div>
</section>

When light_verdict_update.prior_rr_score is null (no prior Mode C),
substitute the {LIGHT_VERDICT_NO_PRIOR_STUB}:

<section id="section-light-verdict" class="opacity-90">
  <h2 class="text-xl font-bold text-gray-900 mb-4">
    <i class="fa-solid fa-flag-checkered mr-2 text-emerald-600"></i>
    5. Light Verdict Update
  </h2>
  <div class="card p-6 bg-amber-50 border border-amber-200">
    <p class="text-sm text-amber-800">
      <i class="fa-solid fa-circle-info mr-1"></i>
      <strong>Mode C 재실행으로 R/R 산출 권고</strong>
    </p>
    <p class="text-xs text-amber-700 mt-2">
      이전 Mode C 분석이 없어 R/R Score 비교가 불가능합니다. {REASON_TEXT}
    </p>
  </div>
</section>
-->

<!-- ============================================================ -->
<!-- SECTION 6: Post-Print Action                                  -->
<!-- ============================================================ -->
<section id="section-post-print">
  <h2 class="text-xl font-bold text-gray-900 mb-4">
    <i class="fa-solid fa-bullseye mr-2 text-emerald-600"></i>
    6. Post-Print 액션 권고
  </h2>
  <div class="card p-6">
    <div class="flex items-center gap-3 mb-4">
      <span class="px-4 py-2 rounded-lg text-sm font-extrabold {ACTION_BADGE_CLASS}">
        {ACTION_RECOMMENDATION_LABEL}
      </span>
      <span class="text-xs text-gray-500">
        Add / Trim / Hold / Reverse 중 1개
      </span>
    </div>
    <p class="text-sm text-gray-700 leading-relaxed mb-5">
      {POST_PRINT_RATIONALE}
    </p>

    <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
      <!-- Entry levels -->
      <div class="card p-4 bg-green-50 border border-green-200">
        <p class="text-sm font-bold text-green-800 mb-2">
          <i class="fa-solid fa-arrow-down-to-line mr-1"></i>
          Entry Levels
        </p>
        <ul class="text-xs text-gray-700 space-y-2">
          {ENTRY_LEVEL_ROWS}
          <!-- Each row pattern:
          <li class="flex items-start gap-2 border-b last:border-b-0 pb-2 last:pb-0">
            <span class="font-mono font-bold text-green-700 w-20 flex-shrink-0">
              {CURRENCY_SYMBOL}{PRICE}
            </span>
            <span class="flex-1">
              {TRIGGER}
              <span class="block text-gray-400 text-[10px] mt-0.5">Size: {SIZE}</span>
            </span>
          </li>
          When ENTRY_LEVEL_ROWS is empty, render:
          <li class="text-gray-400 italic">
            (해당 없음 — 현재 권고 = Hold 또는 Trim)
          </li>
          -->
        </ul>
      </div>
      <!-- Exit levels -->
      <div class="card p-4 bg-rose-50 border border-rose-200">
        <p class="text-sm font-bold text-rose-800 mb-2">
          <i class="fa-solid fa-arrow-up-from-line mr-1"></i>
          Exit Levels
        </p>
        <ul class="text-xs text-gray-700 space-y-2">
          {EXIT_LEVEL_ROWS}
          <!-- Same pattern as ENTRY_LEVEL_ROWS, with action label
               instead of size:
          <li class="flex items-start gap-2 border-b last:border-b-0 pb-2 last:pb-0">
            <span class="font-mono font-bold text-rose-700 w-20 flex-shrink-0">
              {CURRENCY_SYMBOL}{PRICE}
            </span>
            <span class="flex-1">
              {TRIGGER}
              <span class="block text-gray-400 text-[10px] mt-0.5">Action: {ACTION}</span>
            </span>
          </li>
          -->
        </ul>
      </div>
    </div>
  </div>
</section>

</main>

<!-- ============================================================ -->
<!-- FOOTER + Mode C Rerun Banner                                  -->
<!-- ============================================================ -->
<div class="max-w-7xl mx-auto px-4 sm:px-6 mb-8">
  {MODE_C_RERUN_BANNER}
  <!--
  When light_verdict_update.mode_c_rerun_recommended == true, substitute:

  <div class="card p-5 bg-gradient-to-r from-blue-50 to-indigo-50 border-2 border-blue-300">
    <div class="flex items-start gap-3">
      <div class="w-10 h-10 bg-blue-500 rounded-full flex items-center justify-center flex-shrink-0">
        <i class="fa-solid fa-arrows-rotate text-white"></i>
      </div>
      <div class="flex-1">
        <p class="text-sm font-bold text-blue-900 mb-1">
          Mode C 재실행 권고 (다음 윈도우: {RERUN_WINDOW})
        </p>
        <p class="text-xs text-gray-700 mb-2">
          이번 Review는 forward EPS 컨센서스만 light recompute한 결과입니다.
          DCF / Bull-Base-Bear target / R/R Score는 prior Mode C 시점 ({PRIOR_MODE_C_DATE}) 그대로 유지되며 outdated로 표시됩니다.
          가격 발견 메커니즘이 안정화되는 D+2 ~ D+5 사이에 Mode C를 재실행하면 새로운 실적 데이터를
          반영한 valuation을 얻을 수 있습니다.
        </p>
        <p class="text-xs text-blue-600 font-mono">
          명령 예시: "{TICKER} 다시 분석해줘" 또는 "{TICKER} Mode C"
        </p>
      </div>
    </div>
  </div>

  When mode_c_rerun_recommended == false, substitute the empty string.
  -->
</div>

<footer class="bg-gray-900 text-gray-400 mt-8">
  <div class="max-w-7xl mx-auto px-4 sm:px-6 py-8">
    <div class="flex flex-col md:flex-row justify-between items-start gap-4">
      <div>
        <p class="text-xs mb-2">
          <strong class="text-gray-300">Disclaimer:</strong>
          본 리포트는 정보 제공 목적으로만 작성되었으며, 투자 권유나 매수/매도 추천이 아닙니다.
          실적 발표 직후의 주가 반응은 단기 가격 발견 과정으로, 본 분석의 권고 레벨은 발생
          가능한 경로 중 일부에 불과합니다. 모든 투자 의사결정은 본인의 리서치와 리스크 허용
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
          Mode E Review · Window {WINDOW_LABEL} · Generated {ANALYSIS_DATE}
        </p>
      </div>
    </div>
  </div>
</footer>

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
| `{QUARTER_LABEL}`        | derived from `earnings_window.actual_earnings_date`     |
| `{WINDOW_LABEL}`         | `earnings_window.window_label` (e.g. `D+1`)             |
| `{ACTUAL_EARNINGS_DATE}` | `earnings_window.actual_earnings_date`                  |
| `{HERO_GRADIENT_CSS}`    | beat → emerald gradient, miss → rose-orange gradient    |
| `{HERO_BADGE_CLASS}`     | beat → `badge-d-plus`, miss → `badge-d-plus-miss`       |
| `{BEAT_MISS_FLAG_CLASS}` | beat → `bg-green-500/20 text-green-100`, miss → `bg-red-500/20 text-red-100` |
| `{BEAT_MISS_ICON}`       | beat → `circle-check`, miss → `circle-xmark`            |
| `{BEAT_MISS_LABEL}`      | beat → `BEAT`, miss → `MISS`                            |
| `{EPS_SURPRISE_PCT}`     | `actual_vs_consensus.eps.surprise_pct`, 1 decimal       |
| `{POST_MARKET_PCT_OR_DASH}` | signed % from `stock_reaction.post_market_pct`, else `—` |
| `{NEXT_DAY_PCT_OR_DASH}` | signed % from `stock_reaction.next_day_pct`, else `—`   |
| `{PRIOR_VERDICT}`        | `light_verdict_update.prior_verdict` (or `—` if null)   |
| `{UPDATED_VERDICT}`      | `light_verdict_update.updated_verdict` (or `—` if null) |
| `{KOREAN_FONT_IF_KR}`    | Noto Sans KR `<link>` when `output_language == "ko"`    |

### Section 1 (Print Snapshot)

- `{EPS_ACTUAL}`, `{EPS_CONSENSUS}`: from `actual_vs_consensus.eps`
- `{REV_ACTUAL}`, `{REV_CONSENSUS}`: from `actual_vs_consensus.revenue`
- `{SEGMENT_PRINT_ROWS}`: one `<tr>` per `actual_vs_consensus.segments[i]`
- `{OP_MARGIN_ROW_OPTIONAL}`: render only when `operating_margin` is
  non-null. Format `actual` / `consensus` as percentages, `delta_pp` with
  sign + `pp` suffix.

### Section 2 (Guidance Update)

- `{FY_EPS_PRE}`, `{FY_EPS_POST}`: from `guidance_delta`
- `{GUIDANCE_DELTA_PCT}`: signed `guidance_delta.delta_pct`, 1 decimal
- `{GUIDANCE_DELTA_COLOR}`: positive → `text-green-600`, negative →
  `text-red-600`, zero → `text-gray-600`
- `{GUIDANCE_TONE_LABEL}`: `raised` → `상향`, `maintained` → `유지`,
  `lowered` → `하향` (Korean) / `Raised`, `Maintained`, `Lowered` (English)
- `{GUIDANCE_TONE_COLOR}`: same color logic as `delta`

### Section 3 (Key Questions Answered)

- `{QUESTIONS_ANSWERED_CARDS}`: one card per `key_questions_answered[i]`
- Color contract is documented inline in the comment block

### Section 4 (Thesis Impact) — backward compat

- `{THESIS_IMPACT_SECTION}`: when `thesis_impact.prior_mode_c_date` is
  non-null, render the full markup. When null, render the
  no-baseline stub.
- `{LONG_PILLAR_ROWS}`, `{SHORT_PILLAR_ROWS}`: one row per pillar in the
  respective list. Status badge colors and trend colors are documented
  inline.
- `{REVIEW_FIRST_LOOK_NOTE}`: 1-sentence note describing what the print
  showed without a thesis baseline (e.g., "EPS surprise +94% suggests
  thesis tailwind, but no formal pillar tracking until Mode C is run.")

### Section 5 (Light Verdict Update) — outdated styling per OD-F3

- `{LIGHT_VERDICT_SECTION}`: when `light_verdict_update.prior_rr_score` is
  non-null, render the full markup. When null, render the
  no-prior stub.
- The "Updated R/R Score" card uses the `.badge-outdated` class (striped
  amber background + dashed border + italic) — this is the canonical
  outdated-flag styling per OD-F3. The card displays `—` instead of a
  fabricated number, and the caption explicitly states "DCF 미재실행".
- `{VERDICT_CHANGE_LABEL}`:
  - `prior == updated` → `유지`
  - `prior == "관찰" AND updated == "비중확대"` → `상향 ↑`
  - `prior == "비중확대" AND updated == "관찰"` → `하향 ↓`
  - similar for other transitions
- `{LIGHT_VERDICT_REASON}`: passthrough from `light_verdict_update.reason`.
  MUST be 50+ words; renderer asserts this and falls back to a `[Quality
  flag]` annotation if shorter.

### Section 6 (Post-Print Action)

- `{ACTION_RECOMMENDATION_LABEL}`: localized label for
  `post_print_action.recommendation`.
- `{ACTION_BADGE_CLASS}`:
  - `Add` → `bg-green-100 text-green-800`
  - `Hold` → `bg-blue-100 text-blue-800`
  - `Trim` → `bg-amber-100 text-amber-800`
  - `Reverse` → `bg-red-100 text-red-800`
- `{ENTRY_LEVEL_ROWS}` / `{EXIT_LEVEL_ROWS}`: one `<li>` per entry. When
  the array is empty AND `recommendation == "Hold"`, render the
  "(해당 없음 — 현재 권고 = Hold 또는 Trim)" placeholder. When empty AND
  recommendation is anything else, surface a `[Quality flag: missing
  actionable level]`.

### Mode C Rerun Banner

- `{MODE_C_RERUN_BANNER}`: render the full banner card when
  `light_verdict_update.mode_c_rerun_recommended == true`. The banner
  lives between `</main>` and `<footer>` so it sits visually as a
  call-to-action above the disclaimer.
- `{RERUN_WINDOW}`: `light_verdict_update.rerun_window` (default
  `"D+2 ~ D+5"`).
- `{PRIOR_MODE_C_DATE}`: from `thesis_impact.prior_mode_c_date`. When
  the prior date is unknown, render `—` and prepend "(알 수 없음)".

### Footer

- `{ANALYSIS_DATETIME}`: ISO `analysis_date` + `T00:00:00Z` (or actual
  generation time).
- `{DATA_SOURCES_LIST}`: comma-separated list of unique source tags
  appearing in the analysis (e.g. `[Company], [Filing], [Est], [History],
  [Portal], [Calc]`).

---

## Missing Data Handling

- `actual_vs_consensus.eps` missing → BLOCKER. Review cannot render
  without actual EPS — abort and surface
  `[Quality flag: missing actual EPS — Mode E Review requires print data]`.
- `stock_reaction.post_market_pct` AND `next_day_pct` BOTH null → render
  `—` in the hero, surface a MINOR `[Quality flag]`.
- `guidance_delta` null → omit Section 2, surface a MAJOR
  `[Quality flag: missing guidance delta]`.
- `key_questions_answered` empty AND no prior Preview existed → render
  Section 3 with a single placeholder card noting "이전 Preview가 없어
  핵심 질문 추적 불가". Critic completeness check is relaxed for this
  section per the framework's backward-compat clause.
- `thesis_impact.prior_mode_c_date` null → use the no-baseline stub
  (graceful, not a flag).
- `light_verdict_update.prior_rr_score` null → use the no-prior stub
  (graceful, not a flag).

---

## Backward Compatibility Notes

- This template is additive — it does NOT modify Mode A/B/C/D templates.
- Older snapshots without `earnings_sub_mode` are routed to their original
  mode templates by the orchestrator; this template is only selected when
  `output_mode == "E" AND earnings_sub_mode == "review"`.
- Review intentionally omits Chart.js (the Print Snapshot table is the
  visual focus). Do NOT add Chart.js to this template without a contract
  update.
- The "outdated" verdict styling (`.badge-outdated`) is NEW in Phase F.
  Mode C does not use this class — keep it scoped to this template's
  `<style>` block to avoid leaking the visual into Mode C dashboards.
- The Mode C rerun banner is rendered between `</main>` and `<footer>`,
  giving it a "call-to-action" visual weight without polluting the main
  content sections.
