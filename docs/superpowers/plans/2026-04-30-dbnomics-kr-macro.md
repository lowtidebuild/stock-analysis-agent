# BOK ECOS KR Macro Implementation Plan

> **Status:** Revised after verification on 2026-04-30.
> **Important:** This file keeps the original `dbnomics-kr-macro` filename for continuity, but the implementation **must not use the `dbnomics` Python package**. DBnomics currently does not expose a `BOK` provider, and the Python package license is AGPLv3+, not MIT. This plan supersedes the DBnomics-based version.
>
> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

## Goal

Add a Korean macro collector backed by the Bank of Korea ECOS Open API so KR stock analyses get Grade A structured macro context comparable to US FRED coverage.

The collector fetches:
- BOK base rate
- USD/KRW
- KR CPI YoY
- KR unemployment
- KR total exports YoY
- KR semiconductor exports YoY
- KR industrial production
- KR consumer sentiment

The output is `output/data/macro/bok-ecos-snapshot.json`. For KR Mode C/D analyses, `web-researcher` loads this snapshot into `tier2-raw.json -> macro_context.structured`.

## Design Corrections From Prior Version

- Do **not** add `dbnomics>=1.2.0` to `requirements.txt`.
- Do **not** create `dbnomics-collector.py`.
- Do **not** assume `DBNOMICS_API_KEY`, `DBNOMICS_PROVIDER_OVERRIDE`, or `fetch_series("BOK", ...)`.
- Use the repo's current sanitizer contract: `cleaned, findings = sanitize_record(record)`.
- Update both validator and JSON schema wherever `macro_context.structured.source` is currently restricted to `"FRED"`.

## Architecture

Mirror `fred-collector.py` behavior:
- 24h cache TTL
- stale-cache fallback when refresh fails
- `.env` auto-load via `python-dotenv`
- top-level snapshot keys: `common`, `sector`, `kr_overlay`, `errors`, `macro_context`
- `_sanitization` metadata using `tools.prompt_injection_filter`

Differences from FRED:
- Source is `"BOK_ECOS"`.
- API key is `ECOS_API_KEY`.
- No new Python dependency; use `urllib.request`.
- If `ECOS_API_KEY` is missing and no stale cache exists, write a Grade D failure snapshot.

## Files

Create:
- `.claude/skills/web-researcher/scripts/bok-ecos-collector.py`
- `.claude/skills/web-researcher/references/bok-ecos-series-catalog.md`
- `tests/test_bok_ecos_collector.py`

Modify:
- `.claude/skills/web-researcher/SKILL.md`
- `.claude/skills/market-router/references/company-type-classification.md`
- `.claude/schemas/analysis-result.schema.json`
- `tools/artifact_validation.py`
- `references/analysis-framework-dashboard.md`
- `references/analysis-framework-memo.md`
- `.claude/skills/dashboard-generator/references/html-template.md`
- `CLAUDE.md`

Do not touch:
- `requirements.txt` unless a later implementation proves a dependency is required.
- `fred-collector.py`, except for shared helper extraction if explicitly chosen.
- `dart-collector.py`.

## Canonical Output Contract

`output/data/macro/bok-ecos-snapshot.json`:

```json
{
  "collection_timestamp": "2026-04-30T05:00:00Z",
  "cache_ttl_hours": 24,
  "api_status": "success",
  "source": "BOK_ECOS",
  "tag": "[Macro]",
  "confidence_grade": "A",
  "common": {
    "bok_base_rate": {
      "value": 2.75,
      "date": "2026-04",
      "unit": "percent",
      "series_name": "BOK Base Rate",
      "category": "common",
      "provider": "BOK_ECOS",
      "stat_code": "731Y001",
      "cycle": "M",
      "item_code1": "0101000"
    }
  },
  "sector": {
    "industrial": {},
    "consumer": {}
  },
  "kr_overlay": {
    "usd_krw": {
      "value": 1370.5,
      "date": "2026-04-29",
      "unit": "krw_per_usd",
      "series_name": "USD/KRW Exchange Rate",
      "category": "kr_overlay",
      "provider": "BOK_ECOS",
      "stat_code": "731Y004",
      "cycle": "D",
      "item_code1": "0000007"
    }
  },
  "errors": [],
  "macro_context": {
    "structured": {
      "source": "BOK_ECOS",
      "status": "available",
      "tag": "[Macro]",
      "grade": "A",
      "retrieved_at": "2026-04-30T05:00:00Z",
      "series": [
        {
          "id": "bok_base_rate",
          "label": "BOK Base Rate",
          "value": 2.75,
          "as_of_date": "2026-04",
          "unit": "percent",
          "grade": "A",
          "source": "BOK_ECOS"
        }
      ],
      "risk_free_rate": null,
      "fed_funds_rate": null,
      "yield_curve_spread": null,
      "yield_curve_inverted": null,
      "cpi_yoy": 2.4,
      "gdp_growth": null,
      "unemployment": 2.8,
      "sector_specific": {
        "industrial": {
          "industrial_production": 103.2
        },
        "consumer": {
          "consumer_sentiment": 98.4
        }
      },
      "kr_overlay": {
        "usd_krw": 1370.5,
        "kr_base_rate": 2.75,
        "kr_export_yoy": 5.2,
        "kr_semicon_export_yoy": 12.4
      }
    }
  },
  "_sanitization": {
    "tool": "tools/prompt_injection_filter.py",
    "version": "1",
    "timestamp": "2026-04-30T05:00:00Z",
    "redactions": 0,
    "findings": []
  }
}
```

Failure snapshot:
- `api_status`: `"failed"` or `"failed_using_stale"`
- `confidence_grade`: `"D"` for no data, `"B"`/`"C"` for stale cache
- `macro_context.structured.status`: `"unavailable"`
- `macro_context.structured.reason`: required
- `macro_context.structured.series`: `[]`

## Series Catalog

Create `.claude/skills/web-researcher/references/bok-ecos-series-catalog.md`.

The catalog must include the exact ECOS request parameters and a verification status for each series. Initial definitions can start from the codes below, but every code must be live-verified before the collector is considered done.

| Field | ECOS stat code | Cycle | Item code | Unit | Category | Transform |
|---|---:|---|---|---|---|---|
| `bok_base_rate` | `731Y001` | `M` | `0101000` | percent | common | latest value |
| `usd_krw` | `731Y004` | `D` | `0000007` | krw_per_usd | kr_overlay | latest value |
| `kr_cpi_yoy` | `901Y009` | `M` | `0` | percent_yoy | common | compute YoY if ECOS returns index |
| `kr_unemployment` | `901Y027` | `M` | `I61BC` | percent | common | latest value |
| `kr_export_yoy` | `901Y011` | `M` | `0` | percent_yoy | kr_overlay | latest value or compute YoY |
| `kr_semicon_export_yoy` | `901Y011` | `M` | `I22A` | percent_yoy | kr_overlay | latest value or compute YoY |
| `kr_industrial_production` | `901Y033` | `M` | `I16A` | index | industrial | latest value |
| `kr_consumer_sentiment` | `511Y001` | `M` | `0001000` | index_100 | consumer | latest value |

Catalog must include:
- API endpoint template
- sample verification command
- date range used for daily/monthly/YoY data
- fallback behavior when one series fails
- last verified date

## Collector Implementation

### Task 1 - Build skeleton and cache helpers

- [ ] Create `.claude/skills/web-researcher/scripts/bok-ecos-collector.py`.
- [ ] Implement:
  - `_REPO_ROOT` path insertion
  - `.env` auto-load
  - `CACHE_TTL_HOURS = 24`
  - `utc_now_iso()`
  - `check_cache(output_path, force=False)` matching `fred-collector.py`
  - `write_snapshot(output_path, snapshot)`
  - `attach_sanitization_metadata(record)` using the current sanitizer contract:

```python
cleaned, findings = sanitize_record(record)
cleaned["_sanitization"] = {
    "tool": "tools/prompt_injection_filter.py",
    "version": SANITIZER_VERSION,
    "timestamp": utc_now_iso(),
    "redactions": len(findings),
    "findings": findings,
}
```

### Task 2 - Implement ECOS request adapter

- [ ] Implement `ecos_request(api_key, stat_code, cycle, start, end, item_code1, limit=100)`.
- [ ] Use `urllib.request.Request` with a clear user agent.
- [ ] Timeout each request at 10 seconds.
- [ ] Return parsed rows or a structured error.
- [ ] Do not crash the whole collector when one series fails.

Recommended endpoint shape:

```text
https://ecos.bok.or.kr/api/StatisticSearch/{api_key}/json/kr/1/{limit}/{stat_code}/{cycle}/{start}/{end}/{item_code1}
```

Validate this endpoint against the official ECOS API docs before finalizing implementation.

### Task 3 - Implement series transforms

- [ ] `parse_latest_value(rows)` returns `(value, period)`.
- [ ] `compute_yoy_change(rows)` computes YoY when ECOS returns an index rather than a YoY rate.
- [ ] `build_snapshot(series_data, errors, cache_status=None)` builds the canonical output.
- [ ] `build_macro_context_structured(snapshot, reason=None, cache_status=None)` mirrors FRED but sets source to `"BOK_ECOS"`.

### Task 4 - Unit tests

Create `tests/test_bok_ecos_collector.py`.

Required tests:
- [ ] `test_build_snapshot_shape`
- [ ] `test_build_failure_snapshot`
- [ ] `test_cache_valid_uses_cached_data`
- [ ] `test_sanitization_metadata_uses_two_value_contract`
- [ ] `test_partial_series_failure_keeps_available_series`
- [ ] `test_yoy_transform_from_index_rows`

No live network calls in unit tests.

Run:

```bash
PYTHONPATH=. python3 -m pytest tests/test_bok_ecos_collector.py -v
```

Expected: all tests pass.

### Task 5 - Live smoke test

After `ECOS_API_KEY` is available:

```bash
python3 .claude/skills/web-researcher/scripts/bok-ecos-collector.py \
  --output output/data/macro/bok-ecos-snapshot.json \
  --force
```

Expected:
- `status` is `"success"` or `"partial"`
- `series_collected >= 6`
- `macro_context.structured.source == "BOK_ECOS"`
- `_sanitization.redactions` is present

If `series_collected < 6`, stop and fix the catalog before pipeline wiring.

## Pipeline Wiring

### Task 6 - Web researcher

Modify `.claude/skills/web-researcher/SKILL.md` Step 4.8:

- [ ] For `market == "KR"` and `output_mode in {"C", "D"}`, run `bok-ecos-collector.py`.
- [ ] For KR stocks, `BOK_ECOS` structured macro replaces FRED structured macro.
- [ ] For US-listed Korean ADRs, merge:
  - Keep FRED `risk_free_rate`, `fed_funds_rate`, `yield_curve_spread`.
  - Overlay BOK ECOS `kr_overlay`.
- [ ] If BOK ECOS fails, use stale BOK cache if available.
- [ ] FRED `DEXKOUS` remains a USD/KRW fallback only when BOK ECOS has no usable FX value.

### Task 7 - Validator and schema

Modify:
- `.claude/schemas/analysis-result.schema.json`
- `tools/artifact_validation.py`

Required changes:
- [ ] Allow `macro_context.structured.source` in `{"FRED", "BOK_ECOS"}`.
- [ ] Replace hardcoded error text "FRED data" with "structured macro data".
- [ ] Keep unavailable macro rules source-agnostic:
  - Grade D required
  - `reason` required
  - no numeric macro fields
  - no series values
- [ ] Available BOK ECOS data must pass if at least one numeric `series[]` value exists.

Run a minimal validation smoke test against a hand-built KR tier2 payload and final `analysis-result` fixture.

### Task 8 - Market router and analysis frameworks

Modify `.claude/skills/market-router/references/company-type-classification.md`:

- [ ] Common KR factors: BOK base rate, USD/KRW, KR CPI YoY.
- [ ] Technology/Semiconductor: add `kr_semicon_export_yoy`.
- [ ] Industrial: add `kr_industrial_production` and USD/KRW export-margin sensitivity.
- [ ] Financial: add BOK base rate and credit spread proxies.
- [ ] Consumer: add KR CCSI.

Modify `references/analysis-framework-dashboard.md`:

- [ ] Add KR macro card when `macro_context.structured.source == "BOK_ECOS"`.
- [ ] Use canonical paths:
  - `structured.kr_overlay.kr_base_rate`
  - `structured.kr_overlay.usd_krw`
  - `structured.cpi_yoy`
  - `structured.unemployment`
  - `structured.kr_overlay.kr_semicon_export_yoy`
  - `structured.sector_specific.consumer.consumer_sentiment`

Modify `references/analysis-framework-memo.md`:

- [ ] Add Mode D KR macro narrative for BOK base rate, USD/KRW, inflation, exports, and semicon exports when available.

Modify `.claude/skills/dashboard-generator/references/html-template.md`:

- [ ] Add a KR macro snippet that reads `BOK_ECOS` structured macro.
- [ ] Do not reference `sector.consumer.*` under structured; use `sector_specific`.

### Task 9 - Orchestrator docs

Modify `CLAUDE.md`:

- [ ] Step 4 Web Research: mention `bok-ecos-collector.py` for KR Mode C/D.
- [ ] MCP fallback chain: add BOK ECOS before web search for structured KR macro.
- [ ] Timeout table: add `BOK ECOS collector (bok-ecos-collector.py)` with 15 seconds and stale-cache fallback.
- [ ] Data handoff section: macro cache path is `output/data/macro/bok-ecos-snapshot.json`.

## Definition of Done

- [ ] No `dbnomics` dependency added.
- [ ] `tests/test_bok_ecos_collector.py` passes.
- [ ] Live ECOS smoke test collects at least 6 of 8 series.
- [ ] `validate-artifacts.py --artifact-type tier2-raw` accepts BOK ECOS macro context.
- [ ] `analysis-result` schema accepts `sections.macro_context.structured.source == "BOK_ECOS"`.
- [ ] Samsung Electronics Mode C analysis renders a KR macro card with BOK ECOS values.
- [ ] AFRM/PLTR US analyses still use FRED with no regression.

## Open Decisions

1. **ECOS key management**: `ECOS_API_KEY` must be added to `.env.example` only if the project wants to document it. Do not expose real keys.
2. **GDP**: Skip KR GDP in v1 unless a verified ECOS series is added.
3. **Automated catalog verification**: Recommended after v1, but not required for initial collector.
4. **Fallback providers**: If ECOS proves unstable, add OECD/IMF fallbacks in a separate plan.

## Out of Scope

- Time-series charts.
- BOK rate-decision calendar.
- KOSPI/KOSDAQ market index data.
- Korean news sentiment.
- Any DBnomics dependency or DBnomics provider mapping.

