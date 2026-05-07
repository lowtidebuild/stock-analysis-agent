# Analysis Framework — Mode E (Earnings Preview / Review)

This file defines the analytical requirements for Mode E output. The Analyst
agent reads this file when `output_mode = "E"`. Mode E is auto-routed from a
single classification produced by the `earnings-window-detector` skill: the
detector returns `window` ∈ {`preview`, `review`, `none`}, and the Analyst
selects the matching sub-mode pipeline below.

---

## Purpose & Scope

Mode E is the earnings-window specialist mode. It produces a focused,
fast-turnaround HTML report tailored to the ±N-day window around an earnings
print, instead of the full 11-section Mode C dashboard.

**Window classification** (decided by `earnings-window-detector`):

| `days_until` (today − next_earnings_date) | `window`   | Sub-mode                |
|-------------------------------------------|------------|--------------------------|
| `-7 ≤ d ≤ -1`                             | `preview`  | Earnings Preview         |
| `0 ≤ d ≤ 3`                               | `review`   | Earnings Review          |
| otherwise                                  | `none`     | Fall back to Mode C      |

If the user explicitly requests Mode E but the window is `none`, the
orchestrator either honours an `--earnings-mode preview|review` override or
declines the request and falls back to Mode C with a notice.

**Output target**: HTML file with 6 sections (sub-mode-specific) plus
hero/footer.
**Output format**: HTML (TailwindCSS + 1× Chart.js bar chart for Preview's
beat/miss history; otherwise pure Tailwind).
**Output path**:
- Preview: `output/reports/{ticker}_E_preview_{lang}_{YYYY-MM-DD}.html`
- Review:  `output/reports/{ticker}_E_review_{lang}_{YYYY-MM-DD}.html`

**Templates**:
- `.claude/skills/output-generator/references/mode-e-template-preview.md`
- `.claude/skills/output-generator/references/mode-e-template-review.md`

**Generation time target**: ≤ 3 minutes (cold), ≤ 30 seconds (cache warm)
**Total word count**: 800–1,400 words (lower than Mode C, higher than Mode A)

---

## Required Inputs

All run-local artifacts (under `output/runs/{run_id}/{ticker}/`) must be
present and sanitized. Mode E is delivery-blocked if the
`_sanitization` block is missing on any artifact (per CLAUDE.md §12).

**Common inputs (Preview AND Review)**:
- `validated-data.json` — validated metrics with confidence grades
- `evidence-pack.json` — compact analyst input
- `context-budget.json` — analyst context measurement
- `research-plan.json` — output language, ticker metadata, peer set
- `earnings-window-detector` output (Chunk 1):
  - `window` ∈ {`preview`, `review`}
  - `days_until` (signed integer)
  - `next_earnings_date` (ISO `YYYY-MM-DD`) or `actual_earnings_date`
  - `next_earnings_confirmed` boolean
- `earnings-history-fetcher` output (Chunk 2): last 4–8 quarters of
  actual EPS / consensus EPS / surprise % / next-day stock reaction %.

**Preview-only**:
- `options-fetcher` output (Chunk 2): nearest-expiry ATM straddle price,
  implied 1-day move %, IV percentile (when computable).

**Review-only**:
- Most recent prior Mode C `analysis-result.json`, resolved through
  `output/data/{ticker}/latest.json`. Used for thesis-pillar comparison and
  for the prior R/R Score / Bull-Base-Bear targets that anchor the Light
  Verdict Update. If no prior Mode C snapshot exists, the Review still
  renders, but the Thesis Impact section degrades to "No prior Mode C
  baseline — first-look review" and the Light Verdict Update marks
  `prior_rr_score = null`.

**Refusal contract**: Analyst MUST refuse to read any of the above artifacts
that lack a `_sanitization` block. If sanitization is missing, surface
`[Quality flag: unsanitized fetched content]` and treat the affected
metrics as Grade D.

---

## Preview Output Schema (analysis-result.json)

```json
{
  "ticker": "GOOGL",
  "company_name": "Alphabet Inc Class A",
  "currency": "USD",
  "data_mode": "standard|enhanced",
  "output_mode": "E",
  "earnings_sub_mode": "preview",
  "earnings_window": {
    "next_earnings_date": "2026-04-29",
    "next_earnings_confirmed": true,
    "days_until": -3,
    "window_label": "D-3"
  },
  "output_language": "ko",
  "analysis_date": "2026-04-26",
  "price_at_analysis": 384.20,
  "consensus_snapshot": {
    "eps": {"mean": 2.62, "high": 2.71, "low": 2.55, "median": 2.62, "tag": "[Est]"},
    "revenue": {"mean": 109200, "high": 110800, "low": 107900, "median": 109150, "unit": "millions_usd", "tag": "[Est]"},
    "segment_consensus": [
      {"segment": "Cloud", "metric": "rev_yoy_pct", "mean": 35, "high": 50, "low": 28, "tag": "[Est]"},
      {"segment": "Search", "metric": "rev_yoy_pct", "mean": 11, "high": 14, "low": 8, "tag": "[Est]"},
      {"segment": "YouTube", "metric": "rev_yoy_pct", "mean": 13, "high": 17, "low": 9, "tag": "[Est]"}
    ]
  },
  "beat_miss_history": {
    "quarters": [
      {"quarter": "Q4 2025", "report_date": "2026-01-30", "actual_eps": 2.15, "consensus_eps": 2.07, "surprise_pct": 3.9, "beat": true, "stock_reaction_1d_pct": 7.5, "tag": "[History]"}
    ],
    "summary": {"hit_rate": 0.875, "avg_surprise_pct": 12.4, "avg_reaction_1d_pct": 3.2, "tag": "[Calc]"}
  },
  "key_questions": [
    {
      "question": "Cloud +63% 모멘텀 유지될까?",
      "expected_answer": "Yes",
      "stock_impact_if_yes": "+3 to +5%",
      "stock_impact_if_no": "-8 to -10%",
      "rationale": "Q4 +63% YoY는 컨센서스(35%) 대비 +28pp 서프라이즈. Capex 가이던스 $180B 유지 여부가 fwd 12M cloud growth의 가시성을 결정.",
      "mechanism": "Cloud miss → Cloud margin 압축 → Sum-of-parts EV 하향 → 12M target -8~10%"
    }
  ],
  "options_snapshot": {
    "status": "available|unavailable",
    "spot_price": 388.43,
    "atm_strike": 388,
    "atm_call_price": 4.20,
    "atm_put_price": 4.05,
    "atm_straddle_price": 8.25,
    "implied_move_pct": 2.12,
    "iv_percentile": null,
    "nearest_expiry": "2026-05-02",
    "tag": "[Options]"
  },
  "pre_mortem": [
    {"scenario": "Cloud miss", "trigger": "Cloud growth ≤ +45% YoY", "stock_impact": "-8%", "probability": 0.20, "mechanism": "Cloud margin contraction → SOTP EV 하향 → fwd P/E 하향"},
    {"scenario": "Capex shock", "trigger": "FY26 capex 가이던스 $200B 초과", "stock_impact": "-5%", "probability": 0.25, "mechanism": "FCF 압축 → DCF fair value -7% → 단기 multiple 하향"},
    {"scenario": "In-line / mild beat", "trigger": "EPS surprise ≤ 5%, guidance 유지", "stock_impact": "±2%", "probability": 0.40, "mechanism": "옵션 시장 implied move(±2.1%) 안에서 흡수"},
    {"scenario": "Strong beat + raise", "trigger": "EPS surprise > 10% AND FY26 guidance 상향", "stock_impact": "+5 to +7%", "probability": 0.15, "mechanism": "Forward EPS 컨센서스 +5% → multiple 재평가"}
  ],
  "pre_print_position": {
    "recommendation": "Hold",
    "rationale": "Implied move ±2.1%는 historical avg reaction 3.2% 보다 좁음. Asymmetric downside (cloud miss -8% vs upside +5%) 고려 시 add 매력도 낮음.",
    "options_strategy": "Catalyst-driven traders: nearest-expiry ATM straddle ($8.25) — implied move 도달 시 break-even, cloud miss/beat 양쪽 모두 수익."
  },
  "report_path": "output/reports/GOOGL_E_preview_ko_2026-04-26.html",
  "run_context": {
    "run_id": "20260426-googl-mode-e-preview",
    "framework": "references/analysis-framework-earnings.md"
  }
}
```

**Required-fields summary** (Critic checks for presence):
`earnings_window`, `consensus_snapshot.eps`, `beat_miss_history`,
`key_questions` (≥4), `options_snapshot` (or explicit
`status="unavailable"` per OD-F2), `pre_mortem` (probabilities sum to
1.0), `pre_print_position.recommendation`.

---

## Review Output Schema (analysis-result.json)

```json
{
  "ticker": "GOOGL",
  "company_name": "Alphabet Inc Class A",
  "currency": "USD",
  "data_mode": "standard|enhanced",
  "output_mode": "E",
  "earnings_sub_mode": "review",
  "earnings_window": {
    "actual_earnings_date": "2026-04-29",
    "days_since": 1,
    "window_label": "D+1"
  },
  "output_language": "ko",
  "analysis_date": "2026-04-30",
  "price_at_analysis": 408.50,
  "actual_vs_consensus": {
    "eps": {"actual": 5.11, "consensus": 2.63, "surprise_pct": 94.3, "beat": true, "tag": "[Company]"},
    "revenue": {"actual": 109930, "consensus": 109200, "surprise_pct": 0.7, "beat": true, "unit": "millions_usd", "tag": "[Company]"},
    "segments": [
      {"segment": "Cloud", "metric": "rev_yoy_pct", "actual": 63, "consensus": 35, "beat": true, "tag": "[Company]"},
      {"segment": "Search", "metric": "rev_yoy_pct", "actual": 12, "consensus": 11, "beat": true, "tag": "[Company]"},
      {"segment": "YouTube", "metric": "rev_yoy_pct", "actual": 14, "consensus": 13, "beat": true, "tag": "[Company]"}
    ],
    "operating_margin": {"actual": 0.34, "consensus": 0.32, "delta_pp": 2, "beat": true, "tag": "[Filing]"}
  },
  "stock_reaction": {"post_market_pct": 4.2, "next_day_pct": 6.5, "next_2day_pct": null, "tag": "[Portal]"},
  "guidance_delta": {
    "fy_eps_consensus_pre": 12.50,
    "fy_eps_consensus_post": 13.20,
    "delta_pct": 5.6,
    "tone": "raised",
    "company_guidance_change": "FY26 capex raised to $180-190B from $175-185B",
    "tag": "[Est]"
  },
  "key_questions_answered": [
    {
      "question": "Cloud +63% 모멘텀 유지될까?",
      "answer_status": "yes",
      "actual_data": "Cloud +63% YoY confirmed; Q1 backlog +28% QoQ",
      "thesis_impact": "Cloud growth pillar 강화 → SOTP cloud EV +12% (이전 분석 대비)"
    }
  ],
  "thesis_impact": {
    "prior_mode_c_date": "2026-04-15",
    "prior_mode_c_path": "output/data/GOOGL/snapshots/20260415-mode-c/analysis-result.json",
    "long_pillars": [
      {"pillar": "Cloud 성장 모멘텀", "prior_status": "On track", "current_status": "Strengthened", "trend": "Positive", "evidence": "Q1 +63% (컨센서스 +35% 대비 +28pp 초과)"}
    ],
    "short_pillars": [
      {"pillar": "Capex 부담 → FCF 압박", "prior_status": "Watching", "current_status": "Confirmed", "trend": "Negative", "evidence": "FY26 capex $180-190B (전년비 +20%), FCF -8% 압박"}
    ]
  },
  "light_verdict_update": {
    "prior_rr_score": 1.69,
    "updated_rr_score": null,
    "prior_verdict": "관찰",
    "updated_verdict": "관찰",
    "reason": "Forward EPS 컨센서스 +5.6% (12.50 → 13.20). Bull/Base/Bear target 유지 (DCF 미재실행). Cloud growth pillar 강화는 Bull 시나리오 가중치를 높이지만 capex 부담이 Bear 시나리오 트리거를 유지시켜 net R/R 중립.",
    "outdated_flag": true,
    "mode_c_rerun_recommended": true,
    "rerun_window": "D+2 ~ D+5"
  },
  "post_print_action": {
    "recommendation": "Hold",
    "rationale": "Beat은 옵션 시장에 이미 반영됨 (+6.5%). Cloud 모멘텀 강화는 thesis 강화이지만 entry 매력도 낮음. Mode C 재실행으로 DCF 재계산 후 의사결정 권고.",
    "entry_levels": [
      {"price": 395.00, "trigger": "Post-pop pullback to 5d MA", "size": "1/3 add"},
      {"price": 380.00, "trigger": "Pre-print level 회복", "size": "Full add"}
    ],
    "exit_levels": [
      {"price": 440.00, "trigger": "Bull target 근접", "action": "Trim 1/3"},
      {"price": 360.00, "trigger": "Cloud growth 둔화 초기 신호", "action": "Reassess"}
    ]
  },
  "report_path": "output/reports/GOOGL_E_review_ko_2026-04-30.html",
  "run_context": {
    "run_id": "20260430-googl-mode-e-review",
    "framework": "references/analysis-framework-earnings.md"
  }
}
```

**Required-fields summary** (Critic checks for presence):
`earnings_window.actual_earnings_date`, `actual_vs_consensus.eps`,
`stock_reaction.post_market_pct` OR `next_day_pct` (whichever the window
allows), `guidance_delta`, `key_questions_answered`, `thesis_impact`
(or graceful "no prior baseline" stub), `light_verdict_update.outdated_flag`,
`post_print_action.recommendation`.

---

## Step-by-Step Analytical Process — Preview

### Step P1 — Window Verification

1. Read `earnings-window-detector` output. Confirm `window == "preview"` and
   `days_until ∈ [-7, -1]`.
2. If `next_earnings_confirmed == false`: surface a warning banner in the
   hero ("실적 일정 미확정 — 재확인 필요") and proceed with best-effort.
3. If window is `none` and `--earnings-mode preview` was forced: tag the
   output with `[Override: forced preview]` in run_context.

### Step P2 — Consensus Snapshot Construction

1. Pull EPS / Revenue consensus mean/high/low from `validated-data.json`
   (`forward_estimates.eps_q`, `forward_estimates.revenue_q`).
2. If segment consensus is available (cloud / search / YouTube for GOOGL,
   iPhone / Services for AAPL, etc.), include 3–5 segment rows. Use
   `analyst-coverage` data from tier2-raw.json. Skip segments with
   Grade D consensus data.
3. Tag every numeric field `[Est]`. Dispersion (high − low / mean) is
   computed but stored only as a derived metric, not a separate field.

### Step P3 — Beat/Miss History Aggregation

1. Read `earnings-history-fetcher` output (Chunk 2).
2. Use the 4–8 most recent quarters. Prefer 8 when available; never < 4
   without a `[Quality flag: insufficient history]` annotation.
3. Compute `summary.hit_rate`, `summary.avg_surprise_pct`,
   `summary.avg_reaction_1d_pct` from quarter rows. Tag `[Calc]`. Each
   quarter row carries `[History]`.
4. The Preview HTML renders these 4–8 rows as a Chart.js bar chart
   (actual − consensus per quarter); summary numbers go in the section
   subtitle.

### Step P4 — Key Questions (4–5, GOOGL-specific)

Each `key_questions[i]` MUST satisfy:

1. **Specificity**: question must reference a company-specific metric or
   segment (e.g., "Cloud +63% 모멘텀", "iPhone unit growth", "HBM 점유율").
   Replacing the ticker with a peer must make the question wrong or
   irrelevant — the competitor replacement test.
2. **Mechanism**: `mechanism` field MUST contain an explicit causal chain
   (event → financial impact → stock-price effect). 1–2 sentences.
3. **Quantified impact**: both `stock_impact_if_yes` and
   `stock_impact_if_no` are signed % ranges, not vague directional language.

Minimum 4 questions, maximum 5. Critic FAILs Generic test if any question
is generic.

### Step P5 — Options Sentiment Integration

1. Read `options-fetcher` output. If `status == "unavailable"` (per
   OD-F2), set `options_snapshot.status = "unavailable"` and proceed —
   the renderer will omit Section 4. Do NOT fail the Preview.
2. When available, store `spot_price`, `atm_strike`, `atm_straddle_price`,
   `implied_move_pct`, `nearest_expiry`. Tag `[Options]`.
3. Verify the implied-move arithmetic:
   `implied_move_pct ≈ (atm_call + atm_put) / spot_price × 100`. The
   Critic re-runs this check; off by > 0.05pp is a MINOR flag.

### Step P6 — Pre-Mortem Scenarios

1. Construct 3–5 pre-mortem scenarios. Each row carries:
   `scenario`, `trigger` (specific metric threshold), `stock_impact`
   (signed %), `probability` (decimal 0–1), `mechanism` (causal chain).
2. **Probabilities MUST sum to 1.0** within ±0.01 (Critic check).
3. Scenarios MUST be mutually exclusive at the trigger level (no two rows
   trigger on the same metric threshold).

### Step P7 — Pre-Print Position Recommendation

1. `pre_print_position.recommendation` ∈ {`Hold`, `Trim`, `Hedge`, `Add`}.
2. `rationale` is 2–4 sentences and MUST cite ≥1 datapoint from
   `consensus_snapshot`, `beat_miss_history`, or `options_snapshot`.
3. `options_strategy` is OPTIONAL. When included, must specify the
   instrument (straddle / butterfly / put spread), the strike anchor, and
   the implied-move break-even level. Pure narrative ("hedge with options")
   is rejected by Critic.

---

## Step-by-Step Analytical Process — Review

### Step R1 — Print Snapshot Reconciliation

1. Read official EPS / Revenue / segment numbers from the company press
   release (sanitized into `tier2-raw.json` or pulled into validated-data
   under `last_print.*`).
2. Cross-check actuals against the `consensus_snapshot` of the most recent
   Preview snapshot (if one exists in `output/data/{ticker}/`). When no
   Preview exists, pull consensus from `validated-data.json.last_consensus`.
3. Compute `surprise_pct = (actual − consensus) / |consensus| × 100`.
   Tag `[Company]` for actuals (press release origin) and `[Est]` for
   pre-print consensus baseline.
4. `beat = surprise_pct > 0` for revenue/EPS positive metrics; for cost
   metrics (e.g., capex guidance), `beat = surprise_pct < 0`.

### Step R2 — Guidance Delta Extraction

1. From the press-release transcript / IR deck (sanitized
   `tier2-raw.json`), extract the new FY guidance.
2. Compare to pre-print `forward_estimates.fy_eps` consensus (stored in
   `validated-data.json` as the pre-print baseline). Compute
   `delta_pct = (post − pre) / pre × 100`.
3. `tone` ∈ {`raised`, `maintained`, `lowered`} from the dollar-magnitude
   change AND the management commentary.
4. `company_guidance_change` is a 1-sentence summary of the explicit
   management guidance change (e.g., "FY26 capex raised to $180-190B from
   $175-185B"). Pure consensus drift without management action is
   represented in `delta_pct` only.

### Step R3 — Key Questions Answered (vs Preview)

1. If a Preview snapshot exists, copy the `key_questions[]` list.
   Otherwise, reconstruct 3–4 questions from the prior Mode C
   `analysis-result.json.bull_pillars` / `short_pillars`.
2. For each question:
   - `answer_status` ∈ {`yes`, `no`, `partial`}
   - `actual_data` cites the specific number from the print
   - `thesis_impact` ties the answer back to the thesis pillars
3. Critic Generic test: each `actual_data` must include ≥1 specific
   metric value, not just "confirmed" / "denied".

### Step R4 — Thesis Impact Tracking (vs Prior Mode C)

1. Resolve `output/data/{ticker}/latest.json` to find the most recent
   Mode C snapshot. Read its `bull_pillars` and `short_pillars` lists.
2. For each pillar, determine the new `current_status`:
   - `Strengthened` — print confirmed and exceeded the pillar's expected level
   - `On track` — print roughly confirmed
   - `Watching` — print provided no new evidence
   - `Weakened` — print provided counter-evidence below trigger
   - `Broken` — print disconfirmed the pillar (reversal level breached)
3. `trend` ∈ {`Positive`, `Stable`, `Negative`} summarizes the directional
   change.
4. If no prior Mode C snapshot exists: emit a single
   "No prior Mode C baseline — first-look review" line in
   `thesis_impact`. The renderer collapses long_pillars / short_pillars
   into a single empty-state card.

### Step R5 — Light Verdict Update (per OD-F3)

1. Recompute `forward_eps_consensus` using the post-print FY EPS estimate.
2. Do NOT re-run DCF or recompute Bull/Base/Bear targets. Set
   `updated_rr_score = null` and keep `prior_rr_score` from the last
   Mode C snapshot.
3. `outdated_flag = true` whenever `updated_rr_score == null` AND a
   prior Mode C snapshot exists. The renderer surfaces a banner ("R/R
   점수는 outdated — Mode C 재실행 권고").
4. `mode_c_rerun_recommended = true`.
   `rerun_window` defaults to `"D+2 ~ D+5"`.
5. `updated_verdict` may differ from `prior_verdict` only when the
   guidance delta is large (>10% in either direction) AND the thesis_impact
   shows ≥1 pillar `Broken`. Otherwise carry over the prior verdict.

### Step R6 — Post-Print Action

1. `recommendation` ∈ {`Add`, `Trim`, `Hold`, `Reverse`}.
2. `rationale` is 3–5 sentences citing ≥2 datapoints from
   `actual_vs_consensus`, `stock_reaction`, or `thesis_impact`.
3. `entry_levels[]` and `exit_levels[]` are arrays of `{price, trigger, …}`
   objects. Empty arrays are permitted only when `recommendation == "Hold"`
   AND the rationale explicitly states "no new actionable level".

---

## Quality Gates (Critic Mode E variant)

The Critic 7-item review is adapted for Mode E sub-modes. Every item must
pass before delivery; severity follows CLAUDE.md §8.

1. **Generic test** — `key_questions` (Preview) or
   `key_questions_answered` (Review) MUST be ticker-specific. Replacing
   the ticker with a peer must make the question wrong or irrelevant.
   Same rule for `pre_mortem.scenario` triggers and
   `consensus_snapshot.segment_consensus` segments.

2. **Mechanism test** — every `key_questions[i]` carries a
   `mechanism` field (Preview) and every `pre_mortem[i]` carries a
   `mechanism` field. Each mechanism MUST have a 3-link causal chain
   (event → financial impact → stock-price effect). Review's
   `thesis_impact.long_pillars[i].evidence` plays the same mechanism role.

3. **Data backing** — `consensus_snapshot.eps`, `consensus_snapshot.revenue`,
   and at least 4 of 8 `beat_miss_history.quarters[*].actual_eps` rows
   MUST carry source tags. Sample 5 random numeric values; if any lacks a
   tag, MAJOR fail.

4. **Scenario consistency** — Preview only:
   `sum(pre_mortem[*].probability) ∈ [0.99, 1.01]`. Mutual exclusivity:
   no two scenarios trigger on the same metric threshold. Review only:
   `actual_vs_consensus.eps.beat == (actual > consensus)` (sign sanity).

5. **Math consistency** — Preview:
   - `options_snapshot.implied_move_pct ≈ (atm_call + atm_put) / spot × 100`
     (±0.05pp tolerance)
   - `beat_miss_history.summary.hit_rate ==
     count(beat==true) / count(quarters)` (±0.01 tolerance)

   Review:
   - `actual_vs_consensus.eps.surprise_pct ==
     (actual − consensus) / |consensus| × 100` (±0.1pp tolerance)
   - `guidance_delta.delta_pct ==
     (fy_eps_consensus_post − fy_eps_consensus_pre) / fy_eps_consensus_pre × 100`
     (±0.1pp tolerance)

6. **Completeness** — Preview must populate all 6 sections (Consensus,
   Beat/Miss History, Key Questions, Options & Sentiment, Pre-Mortem,
   Pre-Print Position) with ≥50 words each. Per OD-F2, Section 4
   (Options) may be replaced with an explicit "데이터 미수집" stub when
   `options_snapshot.status == "unavailable"` — that stub still counts as
   populated. Review must populate all 6 sections (Print Snapshot,
   Guidance Update, Key Questions Answered, Thesis Impact, Light Verdict
   Update, Post-Print Action) with ≥50 words each. Thesis Impact stub
   ("No prior Mode C baseline") counts as populated when no prior snapshot
   exists.

7. **Blank-over-wrong** — Grade D fields display as `—` (em-dash).
   No fabricated numbers. If `iv_percentile` is not computable, render `—`
   and tag as Grade D in the data sources footer. Never substitute zero or
   a peer-average.

**Feedback loop**: Critic FAIL → Analyst patches once → Critic re-checks.
After 1 loop, MAJOR/MINOR flags are delivered with `[Quality flag]`
inline; BLOCKER terminal failures (e.g., unsanitized fetched content) stop
delivery.

---

## Source Tagging

Mode E reuses the canonical tag set from `confidence-grading.md` plus
two new tags introduced in Phase F:

| Tag           | Source                                                                  |
|---------------|-------------------------------------------------------------------------|
| `[Filing]`    | SEC 10-Q/8-K, DART 사업보고서/공시 (regulator-of-record)                |
| `[Company]`   | 회사 IR press release, earnings deck, management commentary             |
| `[Portal]`    | Yahoo Finance, MarketWatch, Finviz, etc. (US/global aggregators)        |
| `[KR-Portal]` | 네이버금융, FnGuide, KIND (KR aggregators)                              |
| `[Calc]`      | Self-computed from validated inputs (hit_rate, avg_surprise, etc.)      |
| `[Est]`       | Analyst consensus, estimates, target prices                             |
| `[Macro]`     | FRED, BoK, etc. (macro context)                                         |
| `[News]`      | Sanitized news bodies (`tier2-raw.json.news_items[*]`)                  |
| **`[Options]`** *(new)* | Option chain data via `options-fetcher.py` (Preview Section 4) |
| **`[History]`** *(new)* | Historical actual-vs-consensus rows via `earnings-history-fetcher.py` (Preview Section 2 / Review Section 1) |

Grade A is reserved for `[Filing]` and `[Macro]` regulator-original
sources, and for `[Calc]` derived from Grade A inputs. `[Options]` and
`[History]` are Grade B by default (single sanitized source from
yfinance, but cross-validated against the price tape) and can be elevated
to Grade A when the actual print numbers in `[History]` are reconciled
against the corresponding `[Filing]`.

Display tags are normalized via the canonical metadata contract before
rendering (`grade`, `source_type`, `source_authority`, `display_tag`,
`sources`). Legacy tags such as `[KR-Web]` or `[≈]` are rejected.

---

## Backward Compatibility

- **Snapshots without `earnings_sub_mode`** — older Mode A/B/C/D snapshots
  do not carry `earnings_window` or `earnings_sub_mode`. The Critic
  Mode E variant is NOT applied to them.
- **Missing options data** — per OD-F2, Section 4 of Preview is omitted
  with a `[데이터 미수집 — options chain unavailable]` stub. The
  Pre-Print Position section omits the `options_strategy` line.
- **Missing history** — when fewer than 4 quarters are available, render
  what we have and prepend a `[Quality flag: insufficient history (N
  quarters)]` annotation above the chart.
- **Missing prior Mode C** — Review degrades to "first-look review" as
  described in Step R4. Light Verdict Update sets `prior_rr_score = null`
  and surfaces a banner "Mode C 재실행으로 R/R 산출 권고".
- **Empty `key_questions_answered`** — Review may collapse this section
  when no Preview existed and the prior Mode C had no enumerated pillars.
  The renderer emits a placeholder card; Critic completeness check is
  relaxed to ≥30 words for that section only.

---

## Completion Check

Before calling the renderer:

**Preview**:
- [ ] `earnings_window.window_label` matches `D-N` for `N ∈ {1..7}`
- [ ] `consensus_snapshot.eps` and `consensus_snapshot.revenue` populated
- [ ] `beat_miss_history.quarters` has ≥4 rows (or `[Quality flag]`)
- [ ] `key_questions` has ≥4 entries, all GOOGL-specific (or
      ticker-specific equivalent), each with `mechanism`
- [ ] `options_snapshot.status` ∈ {`available`, `unavailable`} —
      `unavailable` is permitted (OD-F2)
- [ ] `pre_mortem` probabilities sum to 1.0 (±0.01)
- [ ] `pre_print_position.recommendation` ∈ {`Hold`, `Trim`, `Hedge`, `Add`}
- [ ] Disclaimer present in renderer footer
- [ ] `output_language` matches `research-plan.json.output_language`
- [ ] HTML file saved to `output/reports/{ticker}_E_preview_{lang}_{date}.html`

**Review**:
- [ ] `earnings_window.window_label` matches `D+N` for `N ∈ {0..3}`
- [ ] `actual_vs_consensus.eps` and `actual_vs_consensus.revenue` populated
- [ ] `stock_reaction` populated (post_market_pct OR next_day_pct,
      whichever the window allows)
- [ ] `guidance_delta.tone` ∈ {`raised`, `maintained`, `lowered`}
- [ ] `key_questions_answered` populated (or graceful empty stub)
- [ ] `thesis_impact` populated (or "No prior Mode C baseline" stub)
- [ ] `light_verdict_update.outdated_flag` set
- [ ] `light_verdict_update.mode_c_rerun_recommended` set
- [ ] `post_print_action.recommendation` ∈
      {`Add`, `Trim`, `Hold`, `Reverse`}
- [ ] Mode C rerun banner rendered in footer
- [ ] Disclaimer present
- [ ] `output_language` matches `research-plan.json.output_language`
- [ ] HTML file saved to `output/reports/{ticker}_E_review_{lang}_{date}.html`
