# Snapshot Schema Reference

This file defines the complete JSON schema for a single-ticker analysis snapshot saved to `output/data/{ticker}/{ticker}_{YYYY-MM-DD}_snapshot.json`.

---

## Top-Level Fields

```json
{
  "ticker": "AAPL",
  "market": "US",
  "data_mode": "enhanced",
  "analysis_date": "2026-03-12",
  "price_at_analysis": 175.50,
  "currency": "USD",
  "output_mode": "C",
  "company_type": "Technology/Platform",
  "key_metrics": { ... },
  "confidence_grades": { ... },
  "variant_view_summary": "...",
  "scenarios": { ... },
  "rr_score": 9.3,
  "top_risks": [...],
  "verdict": "Overweight",
  "upcoming_catalysts": [...],
  "report_path": "output/reports/AAPL_C_EN_2026-03-12.html",
  "data_sources_used": [...]
}
```

### Field Definitions

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `ticker` | string | YES | Canonical ticker (US: 1-5 uppercase alpha; KR: 6-digit numeric) |
| `market` | string | YES | "US" or "KR" |
| `data_mode` | string | YES | "enhanced" or "standard" |
| `analysis_date` | string | YES | ISO 8601 date YYYY-MM-DD |
| `price_at_analysis` | number | YES | Price at time of analysis |
| `currency` | string | YES | "USD" or "KRW" |
| `output_mode` | string | YES | "0", "A", "B", "C", or "D" |
| `company_type` | string | YES | One of: Technology/Platform, Industrial/Manufacturing, Financial, Biotech/Pharma, Consumer, Energy, Korean, Other |
| `key_metrics` | object | YES | Core financial metrics (see below) |
| `confidence_grades` | object | YES | A/B/C/D grade per metric key |
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
  "market_cap": "2.7T",
  "market_cap_raw": 2700000000000,
  "pe_ratio": 28.5,
  "ev_ebitda": 22.1,
  "fcf_yield": 3.8,
  "revenue_growth_yoy": 8.2,
  "operating_margin": 31.5,
  "gross_margin": 43.8,
  "net_margin": 24.9,
  "net_debt_ebitda": 0.3,
  "revenue_ttm": 390000000000,
  "ebitda_ttm": 130000000000,
  "eps_ttm": 6.43,
  "fcf_ttm": 99000000000,
  "roe": 147.9,
  "dividend_yield": 0.5
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

## `confidence_grades` Object

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

Grade meanings: A=Verified, B=Cross-Referenced [≈], C=Single-Source [1S], D=Unverified (excluded)

---

## `scenarios` Object

```json
"scenarios": {
  "bull": {
    "target": 220.0,
    "return_pct": "+25.4%",
    "probability": 0.30,
    "key_assumption": "Services revenue accelerates to 20%+ growth driven by AI monetization"
  },
  "base": {
    "target": 195.0,
    "return_pct": "+11.4%",
    "probability": 0.50,
    "key_assumption": "Steady iPhone cycle + mid-teens Services growth"
  },
  "bear": {
    "target": 145.0,
    "return_pct": "-17.3%",
    "probability": 0.20,
    "key_assumption": "China revenue declines 25%+ due to regulatory action or competitive loss"
  }
}
```

**Constraint**: `bull.probability + base.probability + bear.probability` must equal 1.0 exactly.

---

## `upcoming_catalysts` Array

```json
"upcoming_catalysts": [
  {
    "date": "2026-04-25",
    "event": "FY2Q 2026 Earnings",
    "significance": "high",
    "leading_indicators": "iPhone shipment data from supply chain checks"
  },
  {
    "date": "2026-06-09",
    "event": "WWDC 2026 — AI features announcement",
    "significance": "high",
    "leading_indicators": "Beta developer leak, App Store review changes"
  }
]
```

`significance` must be one of: "high", "medium", "low"

---

## `data_sources_used` Array

List of source tags actually used in this analysis:

```json
"data_sources_used": ["[API]", "[Calculated]", "[Web]", "[FMP]"]
```

Valid values: `[API]`, `[FMP]`, `[DART]`, `[네이버]`, `[Web]`, `[Calculated]`, `[KR-Web]`, `[≈]`, `[1S]`

---

## Complete Example (AAPL, Enhanced Mode, Mode C)

```json
{
  "ticker": "AAPL",
  "market": "US",
  "data_mode": "enhanced",
  "analysis_date": "2026-03-12",
  "price_at_analysis": 175.50,
  "currency": "USD",
  "output_mode": "C",
  "company_type": "Technology/Platform",
  "key_metrics": {
    "market_cap": "2.7T",
    "market_cap_raw": 2717250000000,
    "pe_ratio": 28.5,
    "ev_ebitda": 22.1,
    "fcf_yield": 3.8,
    "revenue_growth_yoy": 8.2,
    "operating_margin": 31.5,
    "gross_margin": 43.8,
    "net_margin": 24.9,
    "net_debt_ebitda": 0.3,
    "revenue_ttm": 390000000000,
    "ebitda_ttm": 130000000000,
    "eps_ttm": 6.43,
    "fcf_ttm": 99000000000,
    "roe": 147.9,
    "dividend_yield": 0.5
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
  "variant_view_summary": "Market treats Apple as a hardware company exposed to iPhone cycle risk, ignoring the structural shift: Services is now 25% of revenue at 75%+ gross margins, creating a recurring-revenue business the market prices at hardware multiples.",
  "scenarios": {
    "bull": {"target": 220, "return_pct": "+25%", "probability": 0.30, "key_assumption": "AI-native iPhone supercycle drives 15% unit growth + Services accelerates to 20%+ growth"},
    "base": {"target": 195, "return_pct": "+11%", "probability": 0.50, "key_assumption": "Steady iPhone replacement + mid-teens Services growth, stable margins"},
    "bear": {"target": 145, "return_pct": "-17%", "probability": 0.20, "key_assumption": "China revenue -25%+ from regulatory action; Services growth decelerates to <10%"}
  },
  "rr_score": 9.3,
  "top_risks": [
    "China regulatory restriction on App Store or device sales (mechanism: forced revenue removal, ~$70B revenue at risk)",
    "AI features fail to drive upgrade cycle (mechanism: elongated replacement cycle, ~5% unit volume miss)",
    "DOJ antitrust action on App Store 30% commission (mechanism: forced margin compression, ~$3-5B annual Services impact)"
  ],
  "verdict": "Overweight",
  "upcoming_catalysts": [
    {"date": "2026-04-25", "event": "FY2Q Earnings", "significance": "high", "leading_indicators": "Taiwan Semiconductor monthly revenue data"},
    {"date": "2026-06-09", "event": "WWDC 2026", "significance": "medium", "leading_indicators": "Developer beta registrations"}
  ],
  "report_path": "output/reports/AAPL_C_EN_2026-03-12.html",
  "data_sources_used": ["[API]", "[Calculated]", "[Web]", "[FMP]"]
}
```
