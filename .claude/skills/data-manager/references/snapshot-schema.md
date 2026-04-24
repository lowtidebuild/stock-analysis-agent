# Snapshot Schema Reference

This file defines the complete JSON schema for a single-ticker analysis snapshot saved to `output/data/{ticker}/snapshots/{snapshot_id}/analysis-result.json`.

Snapshots are persisted artifacts. The working pipeline artifacts live under `output/runs/{run_id}/{ticker}/...`, and the snapshot should preserve `run_context` from that run. `output/data/{ticker}/latest.json` is a pointer document only; it must not duplicate the full snapshot body.

---

## Top-Level Fields

```json
{
  "ticker": "<TICKER>",
  "market": "US",
  "data_mode": "enhanced",
  "requested_mode": "enhanced",
  "effective_mode": "standard",
  "source_profile": "yfinance_fallback",
  "source_tier": "portal_structured",
  "confidence_cap": "C",
  "run_context": {
    "run_id": "<RUN_ID>",
    "artifact_root": "output/runs/<RUN_ID>/<TICKER>",
    "ticker": "<TICKER>"
  },
  "analysis_date": "<ANALYSIS_DATE>",
  "price_at_analysis": "<CURRENT_PRICE>",
  "currency": "USD",
  "output_mode": "C",
  "company_type": "Technology/Platform",
  "key_metrics": { ... },
  "confidence_grades": { ... },
  "variant_view_summary": "...",
  "scenarios": { ... },
  "rr_score": "<RR_SCORE>",
  "top_risks": [...],
  "verdict": "Overweight",
  "upcoming_catalysts": [...],
  "report_path": "output/reports/<TICKER>_C_<LANG>_<ANALYSIS_DATE>.html",
  "data_sources_used": [...]
}
```

---

## `latest.json` Pointer

New writes store the latest reference as a compact pointer:

```json
{
  "schema_version": "1.0",
  "kind": "stock-analysis.latest-snapshot-pointer",
  "ticker": "<TICKER>",
  "latest_snapshot_id": "<SNAPSHOT_ID>",
  "analysis_date": "<ANALYSIS_DATE>",
  "snapshot_saved_at": "<SNAPSHOT_SAVED_AT>",
  "expires_at": "<EXPIRES_AT>",
  "freshness_ttl_hours": 24,
  "data_mode": "enhanced",
  "output_mode": "C",
  "rr_score": "<RR_SCORE>",
  "verdict": "Neutral",
  "refs": {
    "analysis_result": "output/data/<TICKER>/snapshots/<SNAPSHOT_ID>/analysis-result.json",
    "validated_data": "output/data/<TICKER>/snapshots/<SNAPSHOT_ID>/validated-data.json",
    "evidence_pack": "output/data/<TICKER>/snapshots/<SNAPSHOT_ID>/evidence-pack.json",
    "context_budget": "output/data/<TICKER>/snapshots/<SNAPSHOT_ID>/context-budget.json",
    "quality_report": "output/data/<TICKER>/snapshots/<SNAPSHOT_ID>/quality-report.json"
  }
}
```

Readers must support legacy full-snapshot `latest.json` files, but writers must emit pointer-only `latest.json`.

### Field Definitions

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `ticker` | string | YES | Canonical ticker (US: 1-5 uppercase alpha; KR: 6-digit numeric) |
| `market` | string | YES | "US" or "KR" |
| `data_mode` | string | YES | Requested pipeline mode, "enhanced" or "standard" |
| `requested_mode` | string | NO | User/requested collection mode; defaults to `data_mode` for legacy snapshots |
| `effective_mode` | string | NO | Actual achieved source strength, "enhanced" or "standard" |
| `source_profile` | string | NO | `financial_datasets`, `sec_or_dart_primary`, `yfinance_fallback`, `web_only`, or `mixed` |
| `source_tier` | string | NO | `filing_primary`, `api_structured`, `portal_structured`, `search_snippet`, or `user_supplied` |
| `confidence_cap` | string | NO | Maximum allowed overall confidence grade after fallback, A/B/C/D |
| `run_context` | object | YES | Run-local artifact metadata preserved from `output/runs/{run_id}/{ticker}` |
| `analysis_date` | string | YES | ISO 8601 date YYYY-MM-DD |
| `price_at_analysis` | number | YES | Price at time of analysis |
| `currency` | string | YES | "USD" or "KRW" |
| `output_mode` | string | YES | "0", "A", "B", "C", or "D" |
| `company_type` | string | YES | One of: Technology/Platform, Industrial/Manufacturing, Financial, Biotech/Pharma, Consumer, Energy, Korean, Other |
| `key_metrics` | object | YES | Core financial metrics as metric-entry objects (`value`, `grade`, `source_type`, `display_tag`, `sources`) |
| `confidence_grades` | object | NO | Legacy compatibility map only. Prefer per-metric `grade` in `key_metrics`. |
| `variant_view_summary` | string | YES | 1-2 sentence summary of thesis |
| `scenarios` | object | YES | bull/base/bear scenarios |
| `rr_score` | number | YES | Risk/Reward Score (top-level for easy extraction) |
| `top_risks` | array | YES | Max 3 risk strings |
| `verdict` | string | YES | Overweight / Neutral / Underweight (or Korean equivalents) |
| `upcoming_catalysts` | array | YES | Dated catalyst events |
| `report_path` | string | NO | Relative path to output file |
| `data_sources_used` | array | YES | List of source tags used |

---

## `key_metrics` Object

```json
"key_metrics": {
  "market_cap": {
    "value": "<MARKET_CAP>",
    "unit": "millions_usd",
    "grade": "A",
    "source_type": "calculated",
    "source_authority": "derived",
    "display_tag": "[Calc]",
    "tag": "[Calc]",
    "sources": ["Calculated from filing-backed price and shares"]
  },
  "pe_ratio": {
    "value": "<PE_RATIO>",
    "grade": "A",
    "source_type": "calculated",
    "source_authority": "derived",
    "display_tag": "[Calc]",
    "tag": "[Calc]",
    "sources": ["Calculated from filing-backed price and EPS"]
  }
}
```

| Field | Unit | Notes |
|-------|------|-------|
| `market_cap` | human-readable string | e.g., "2.7T", "485B", "12.3B" |
| `market_cap_raw` | number (absolute) | In USD or KRW |
| `pe_ratio` | multiple (x) | NaN or null if negative earnings |
| `ev_ebitda` | multiple (x) | null if EBITDA ≤ 0 |
| `fcf_yield` | percent (%) | FCF / Market Cap × 100 |
| `revenue_growth_yoy` | percent (%) | Year-over-year |
| `operating_margin` | percent (%) | Op Income / Revenue × 100 |
| `gross_margin` | percent (%) | |
| `net_margin` | percent (%) | |
| `net_debt_ebitda` | ratio | Negative = net cash position |
| `revenue_ttm` | absolute number | In USD or KRW |
| `ebitda_ttm` | absolute number | |
| `eps_ttm` | per share | |
| `fcf_ttm` | absolute number | Operating CF - Capex |
| `roe` | percent (%) | |
| `dividend_yield` | percent (%) | 0 if no dividend |

---

## `confidence_grades` Object (Legacy Compatibility)

One letter grade (A/B/C/D) per metric key, matching keys in `key_metrics`:

```json
"confidence_grades": {
  "price": "A",
  "market_cap": "A",
  "pe_ratio": "A",
  "ev_ebitda": "B",
  "fcf_yield": "A",
  "revenue_growth_yoy": "A",
  "operating_margin": "A",
  "revenue_ttm": "A",
  "eps_ttm": "A",
  "net_debt_ebitda": "B",
  "fcf_ttm": "A"
}
```

Grade meanings: A=규제기관 공시 원본+산술 일관성, B=2+소스 교차검증, C=단일 소스, D=검증 불가 (excluded)

---

## `scenarios` Object

```json
"scenarios": {
  "bull": {
    "target": "<BULL_TARGET>",
    "return_pct": "<BULL_RETURN_PCT>",
    "probability": 0.30,
    "key_assumption": "<SOURCE_BACKED_BULL_ASSUMPTION>"
  },
  "base": {
    "target": "<BASE_TARGET>",
    "return_pct": "<BASE_RETURN_PCT>",
    "probability": 0.50,
    "key_assumption": "<SOURCE_BACKED_BASE_ASSUMPTION>"
  },
  "bear": {
    "target": "<BEAR_TARGET>",
    "return_pct": "<BEAR_RETURN_PCT>",
    "probability": 0.20,
    "key_assumption": "<SOURCE_BACKED_BEAR_ASSUMPTION>"
  }
}
```

**Constraint**: `bull.probability + base.probability + bear.probability` must equal 1.0 exactly.

---

## `upcoming_catalysts` Array

```json
"upcoming_catalysts": [
  {
    "date": "<CATALYST_DATE>",
    "event": "<SOURCE_BACKED_EVENT>",
    "significance": "high",
    "leading_indicators": "<SOURCE_BACKED_LEADING_INDICATOR>"
  },
  {
    "date": "<CATALYST_DATE>",
    "event": "<SOURCE_BACKED_EVENT>",
    "significance": "high",
    "leading_indicators": "<SOURCE_BACKED_LEADING_INDICATOR>"
  }
]
```

`significance` must be one of: "high", "medium", "low"

---

## `data_sources_used` Array

List of source tags actually used in this analysis:

```json
"data_sources_used": ["[Filing]", "[Calc]", "[Portal]", "[Est]"]
```

Valid values: `[Filing]`, `[Company]`, `[Portal]`, `[KR-Portal]`, `[Calc]`, `[Est]`, `[Macro]`

---

## Complete Example (Enhanced Mode, Mode C)

```json
{
  "ticker": "<TICKER>",
  "market": "US",
  "data_mode": "enhanced",
  "analysis_date": "<ANALYSIS_DATE>",
  "price_at_analysis": "<CURRENT_PRICE>",
  "currency": "USD",
  "output_mode": "C",
  "company_type": "Technology/Platform",
  "key_metrics": {
    "market_cap": "<MARKET_CAP>",
    "market_cap_raw": "<MARKET_CAP_RAW>",
    "pe_ratio": "<PE_RATIO>",
    "ev_ebitda": "<EV_EBITDA>",
    "fcf_yield": "<FCF_YIELD>",
    "revenue_growth_yoy": "<REVENUE_GROWTH_YOY>",
    "operating_margin": "<OPERATING_MARGIN>",
    "gross_margin": "<GROSS_MARGIN>",
    "net_margin": "<NET_MARGIN>",
    "net_debt_ebitda": "<NET_DEBT_EBITDA>",
    "revenue_ttm": "<REVENUE_TTM>",
    "ebitda_ttm": "<EBITDA_TTM>",
    "eps_ttm": "<EPS_TTM>",
    "fcf_ttm": "<FCF_TTM>",
    "roe": "<ROE>",
    "dividend_yield": "<DIVIDEND_YIELD>"
  },
  "confidence_grades": {
    "price": "A",
    "market_cap": "A",
    "pe_ratio": "A",
    "ev_ebitda": "A",
    "revenue": "A",
    "eps_ttm": "A",
    "net_debt_ebitda": "A",
    "fcf_ttm": "A"
  },
  "variant_view_summary": "<SOURCE_BACKED_VARIANT_VIEW_SUMMARY>",
  "scenarios": {
    "bull": {"target": "<BULL_TARGET>", "return_pct": "<BULL_RETURN_PCT>", "probability": 0.30, "key_assumption": "<SOURCE_BACKED_BULL_ASSUMPTION>"},
    "base": {"target": "<BASE_TARGET>", "return_pct": "<BASE_RETURN_PCT>", "probability": 0.50, "key_assumption": "<SOURCE_BACKED_BASE_ASSUMPTION>"},
    "bear": {"target": "<BEAR_TARGET>", "return_pct": "<BEAR_RETURN_PCT>", "probability": 0.20, "key_assumption": "<SOURCE_BACKED_BEAR_ASSUMPTION>"}
  },
  "rr_score": "<RR_SCORE>",
  "top_risks": [
    "<SOURCE_BACKED_RISK_1>",
    "<SOURCE_BACKED_RISK_2>",
    "<SOURCE_BACKED_RISK_3>"
  ],
  "verdict": "Overweight",
  "upcoming_catalysts": [
    {"date": "<CATALYST_DATE>", "event": "<SOURCE_BACKED_EVENT>", "significance": "high", "leading_indicators": "<SOURCE_BACKED_LEADING_INDICATOR>"},
    {"date": "<CATALYST_DATE>", "event": "<SOURCE_BACKED_EVENT>", "significance": "medium", "leading_indicators": "<SOURCE_BACKED_LEADING_INDICATOR>"}
  ],
  "report_path": "output/reports/<TICKER>_C_<LANG>_<ANALYSIS_DATE>.html",
  "data_sources_used": ["[Filing]", "[Calc]", "[Portal]", "[Est]"]
}
```
