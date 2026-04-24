# yfinance Integration Spec

**Target implementer**: Codex (or any coding agent)
**Author**: Claude (review pass), 2026-04-14
**Status**: Spec — implementation not started

---

## 1. Goal

Add [yfinance](https://github.com/ranaroussi/yfinance) as a **middle-tier fallback** for both US and Korean stock data collection. It sits between the primary paid sources (Financial Datasets MCP / 네이버금융) and the unstructured web search fallback, providing a more stable intermediate layer.

**This is a fallback, not a replacement.** Financial Datasets MCP remains the Grade A primary source for US filings. 네이버금융 remains primary for KR price/market metrics.

---

## 2. Fallback Chain (After This Change)

### US (Enhanced Mode)
```
1. Financial Datasets MCP     → [Filing]   Grade A   (primary — SEC filings)
2. FMP MCP                    → [Portal]   Grade B   (analyst data)
3. yfinance           NEW     → [Portal]   Grade B/C (stable intermediate fallback)
4. Tavily / Brave / WebSearch → [Portal]   Grade C
5. WebFetch (direct URL)      → [Portal]   Grade C
```

### US (Standard Mode — MCP unavailable)
```
1. yfinance           NEW     → [Portal]   Grade B/C (new primary for price/basics)
2. Tavily / Brave / WebSearch → [Portal]   Grade C
3. WebFetch                   → [Portal]   Grade C
```

### KR
```
1. DART OpenAPI (dart-collector.py) → [Filing]    Grade A   (financial filings, free)
2. 네이버금융                        → [KR-Portal] Grade B   (primary for price/PER/PBR/EPS/배당수익률/52주/외국인지분)
3. yfinance (suffix .KS/.KQ) NEW    → [Portal]    Grade B/C (fallback if 네이버금융 fetch fails or data incomplete)
4. FnGuide                          → [KR-Portal] Grade B   (consensus)
5. KIND / general web               → [KR-Portal] Grade C
```

**KR routing rule**: 네이버금융은 항상 먼저 시도한다. 네이버에서 필요한 필드가 빠지거나 fetch가 실패한 경우에만 yfinance로 보완한다 — yfinance를 네이버와 병렬로 호출하지 않는다 (중복 + rate limit 낭비).

---

## 3. Installation & Dependencies

### 3.1 Python package

Add to project requirements. Minimum version:

```
yfinance>=0.2.40
```

Version ≥0.2.40 includes fixes for Yahoo's late-2024 / 2026 anti-bot changes. Earlier versions may break silently.

Install location: same Python environment used by existing scripts (`dart-collector.py`, `fred-collector.py`, `dcf-calculator.py`). Check `tools/` directory scripts to confirm the environment.

### 3.2 Optional: curl_cffi

If plain `yfinance` starts failing due to Yahoo's bot detection, install the `curl_cffi` extra:

```
pip install 'yfinance[nospam]'
```

Do **not** install this preemptively. Only add if runtime tests show failures.

### 3.3 No API key required

yfinance scrapes public Yahoo Finance endpoints. No key, no auth, no `.env` changes.

---

## 4. Script Contract

### 4.1 File location
```
.claude/skills/financial-data-collector/scripts/yfinance-collector.py
```

(New directory — `financial-data-collector/scripts/` does not yet exist. Create it.)

### 4.2 CLI signature

```bash
python .claude/skills/financial-data-collector/scripts/yfinance-collector.py \
  --ticker AAPL \
  --market US \
  --output output/runs/20260424T000000Z_AAPL/AAPL/yfinance-raw.json \
  [--bundle minimum|standard] \
  [--timeout 15]
```

**Arguments**:
- `--ticker` (required): Raw ticker symbol. Script handles suffix conversion internally (e.g., `005930` + `--market KR` → `005930.KS`).
- `--market` (required): `US` or `KR`. Determines suffix rules and field normalization.
- `--output` (required): Absolute or project-relative path for JSON output.
- `--bundle` (optional, default `standard`): `minimum` = price + basic metrics only; `standard` = full bundle incl. financial statements.
- `--timeout` (optional, default 15): Per-call timeout in seconds.

**Exit codes**:
- `0` — success (JSON written, `current_price` non-null)
- `1` — partial success (JSON written but `current_price` null; caller should log and continue)
- `2` — complete failure (no JSON written; caller must fall back further)

### 4.3 KR ticker suffix rules

Input `--ticker` for KR should be the 6-digit code (e.g., `005930`, `035720`). Script maps to Yahoo suffix:

| Market tier | Suffix | Detection |
|-------------|--------|-----------|
| KOSPI       | `.KS`  | Try `.KS` first |
| KOSDAQ      | `.KQ`  | If `.KS` returns no price, retry with `.KQ` |

Cache the successful suffix in the output JSON (`yahoo_symbol` field) so callers can reuse it.

---

## 5. Output JSON Schema

Write to `--output` path. Schema:

```json
{
  "ticker": "AAPL",
  "market": "US",
  "yahoo_symbol": "AAPL",
  "collection_timestamp": "2026-04-14T09:30:00Z",
  "data_source": "yfinance",
  "yfinance_version": "0.2.40",
  "bundle": "standard",
  "calls_succeeded": ["info", "history", "income_stmt", "balance_sheet", "cashflow"],
  "calls_failed": [],

  "current_price": {
    "price": 175.50,
    "currency": "USD",
    "change": 1.25,
    "change_pct": 0.72,
    "as_of": "2026-04-14T09:30:00Z",
    "source_field": "regularMarketPrice"
  },

  "info": {
    "market_cap": 2710000000000,
    "enterprise_value": 2800000000000,
    "shares_outstanding": 15500000000,
    "float_shares": 15400000000,
    "pe_trailing": 28.0,
    "pe_forward": 26.5,
    "pb_ratio": 45.2,
    "ev_ebitda": 22.5,
    "dividend_yield": 0.0054,
    "beta": 1.28,
    "fifty_two_week_high": 199.62,
    "fifty_two_week_low": 164.08,
    "sector": "Technology",
    "industry": "Consumer Electronics",
    "country": "United States",
    "website": "https://www.apple.com",
    "raw_info_keys_present": ["regularMarketPrice", "marketCap", "..."]
  },

  "income_statements": [
    {
      "period_end": "2025-12-31",
      "period_type": "quarterly",
      "revenue": 99800000000,
      "gross_profit": 45000000000,
      "operating_income": 30000000000,
      "net_income": 26000000000,
      "eps_diluted": 1.68,
      "diluted_shares": 15500000000
    }
  ],

  "balance_sheets": [
    {
      "period_end": "2025-12-31",
      "period_type": "quarterly",
      "total_assets": 350000000000,
      "total_equity": 62000000000,
      "total_debt": 105000000000,
      "cash_and_equivalents": 30000000000,
      "short_term_debt": 15000000000,
      "long_term_debt": 90000000000
    }
  ],

  "cash_flow_statements": [
    {
      "period_end": "2025-12-31",
      "period_type": "quarterly",
      "operating_cashflow": 35000000000,
      "capital_expenditure": 3500000000,
      "capex_raw": -3500000000,
      "capex_outflow_abs": 3500000000,
      "capex_sign_convention": "negative_outflow",
      "free_cash_flow": 31500000000,
      "free_cash_flow_calculated": 31500000000
    }
  ],

  "historical_prices": {
    "range": "1y",
    "interval": "1d",
    "rows": [
      {"date": "2025-04-14", "open": 170.0, "high": 172.0, "low": 169.5, "close": 171.8, "volume": 52000000}
    ]
  },

  "analyst_targets": {
    "mean_target": 190.0,
    "median_target": 192.0,
    "high_target": 220.0,
    "low_target": 160.0,
    "analyst_count": 42,
    "recommendation_mean": 1.9,
    "recommendation_key": "buy"
  },

  "derived_ttm": {
    "revenue_ttm": 395000000000,
    "net_income_ttm": 97000000000,
    "operating_income_ttm": 118000000000,
    "eps_ttm": 6.27,
    "fcf_ttm": 110000000000,
    "quarters_used": 4
  },

  "data_quality": {
    "price_available": true,
    "quarters_available": 4,
    "statements_complete": true,
    "warnings": []
  }
}
```

### 5.1 Null handling

**Blank > Wrong Number**. If a field is missing from yfinance response, write `null` — never fabricate or interpolate. Downstream validator (Step 5) grades nulls as D and displays as "—".

### 5.2 Currency & units

- US tickers: USD. Report raw numbers (not in thousands/millions).
- KR tickers: KRW. Report raw numbers. Mark `currency: "KRW"` in `current_price`.
- Do NOT convert KR to USD. Validator handles currency normalization separately.

---

## 6. yfinance API Field Mapping

Reference for implementer. yfinance's `Ticker` object has these accessors:

| yfinance call | Our field | Notes |
|---------------|-----------|-------|
| `t.info["regularMarketPrice"]` | `current_price.price` | Primary price field |
| `t.info["currency"]` | `current_price.currency` | |
| `t.info["marketCap"]` | `info.market_cap` | |
| `t.info["enterpriseValue"]` | `info.enterprise_value` | |
| `t.info["sharesOutstanding"]` | `info.shares_outstanding` | |
| `t.info["trailingPE"]` | `info.pe_trailing` | |
| `t.info["forwardPE"]` | `info.pe_forward` | |
| `t.info["priceToBook"]` | `info.pb_ratio` | |
| `t.info["enterpriseToEbitda"]` | `info.ev_ebitda` | |
| `t.info["dividendYield"]` | `info.dividend_yield` | Already decimal (0.0054 = 0.54%) |
| `t.info["fiftyTwoWeekHigh"]` | `info.fifty_two_week_high` | |
| `t.info["fiftyTwoWeekLow"]` | `info.fifty_two_week_low` | |
| `t.quarterly_income_stmt` | `income_statements[]` | DataFrame → list of dicts |
| `t.quarterly_balance_sheet` | `balance_sheets[]` | |
| `t.quarterly_cashflow` | `cash_flow_statements[]` | |
| `t.history(period="1y")` | `historical_prices.rows` | DataFrame → list of dicts |
| `t.analyst_price_targets` | `analyst_targets` | May be None |
| `t.recommendations` | Use for `recommendation_mean` | Optional |

### 6.1 Field name variability

yfinance `info` dict keys change across versions. Implementer should:
1. Attempt the expected key.
2. On `KeyError`, log to `calls_failed` with the missing key name.
3. Continue with `null` for that field.
4. Record all keys actually present in `raw_info_keys_present` for debugging.

### 6.2 Financial statement normalization

yfinance returns statements as pandas DataFrames with dates as columns and line items as row indices. Line item names are **not** stable — they follow Yahoo's display labels ("Total Revenue", "Net Income Common Stockholders", etc.).

Build a normalization map:

```python
INCOME_STMT_ALIASES = {
    "revenue": ["Total Revenue", "Revenue"],
    "gross_profit": ["Gross Profit"],
    "operating_income": ["Operating Income", "Operating Revenue"],
    "net_income": ["Net Income", "Net Income Common Stockholders", "Net Income From Continuing Operations"],
    "eps_diluted": ["Diluted EPS"],
    "diluted_shares": ["Diluted Average Shares"],
}
```

Try each alias in order. Write `null` if none match and append to `data_quality.warnings`.

---

## 7. Error Handling

### 7.1 Per-call timeout

Each yfinance call (`info`, `history`, each statement) runs with the `--timeout` budget. Implementation options:
- `signal.alarm` (Unix only)
- `concurrent.futures.ThreadPoolExecutor` with `future.result(timeout=N)`

Prefer the ThreadPoolExecutor approach for portability.

### 7.2 Rate limiting

- Insert `time.sleep(0.3)` between major calls within a single ticker.
- If called for multiple tickers in sequence (workflow 2), caller should space ticker invocations by ≥1 second.
- On HTTP 429 or empty response after retry, abort and return exit code 2.

### 7.3 Retry policy

- Per-call: 1 retry with 2-second backoff.
- On second failure: log to `calls_failed` and continue with remaining calls. Do NOT abort the whole collection unless `current_price` specifically fails.

### 7.4 Critical failure condition

If `current_price` is `null` after all retries → exit code 2, no JSON written. Caller falls back to next source.

All other missing fields → exit code 0 or 1 (still write JSON; caller continues).

---

## 8. Integration Points

The following files need edits. Do not rewrite — add yfinance as a new fallback step.

### 8.1 `.claude/skills/financial-data-collector/SKILL.md`

Add a new **Step 3.3.5 — yfinance Supplement** between Step 3.3 (FMP) and Step 3.4 (Data Sufficiency):

```
### Step 3.3.5 — yfinance Supplement (Enhanced Mode)

After Financial Datasets + FMP, check if any critical fields are still missing
(current_price, market_cap, pe_ratio, 52w_high/low). If any are missing:

```bash
python .claude/skills/financial-data-collector/scripts/yfinance-collector.py \
  --ticker {ticker} --market US \
  --output output/runs/{run_id}/{ticker}/yfinance-raw.json \
  --bundle minimum
```

Merge into tier1-raw.json under `yfinance_supplement` key. Tag merged values
`[Portal]` Grade B (if they agree with existing Grade A values within 2%) or
Grade C (standalone).
```

Also update Step 3's fallback clause: if MCP completely fails AND yfinance
succeeds, mark data_source as `"yfinance"` and keep data_mode as "enhanced"
(it's still structured, just from a lower-authority source).

### 8.2 `.claude/skills/web-researcher/SKILL.md`

Add a new **Step 4.3.5 — yfinance Fallback (US Standard Mode)** before Step 4.3's direct fetches:

```
### Step 4.3.5 — yfinance Fallback

If Standard Mode and any of the 8 searches fail to produce price/market_cap/PE:

```bash
python .claude/skills/financial-data-collector/scripts/yfinance-collector.py \
  --ticker {ticker} --market US \
  --output output/runs/{run_id}/{ticker}/yfinance-raw.json \
  --bundle standard
```

Merge extracted fields into tier2-raw.json key_data_extracted with tag [Portal].
```

Update **Step 4.4.2 — 네이버금융** to add a yfinance fallback:

```
### Step 4.4.2b — yfinance fallback (if 네이버금융 failed or incomplete)

If 네이버금융 fetch returned HTTP error OR missing any of:
{price, PER, PBR, EPS, 52w_high, 52w_low}, run:

```bash
python .claude/skills/financial-data-collector/scripts/yfinance-collector.py \
  --ticker {6digit_ticker} --market KR \
  --output output/runs/{run_id}/{ticker}/yfinance-raw.json \
  --bundle minimum
```

Merge missing fields only — do NOT overwrite fields 네이버금융 already provided.
Tag merged values `[Portal]` Grade C (unless cross-confirmed with DART,
then Grade B).
```

### 8.3 `CLAUDE.md` — Section 9 (Failure Handling)

Update the MCP Fallback Chain list to insert yfinance:

```
1. Financial Datasets MCP → `get_*` tools
2. FMP MCP → analyst data only
3. yfinance (Python script) → price, basic ratios, statements     ← NEW
4. Tavily search → web search
5. Brave search → web search
6. WebSearch (built-in) → web search
7. WebFetch (direct URL) → specific page fetch
```

Add a new row to the **Stall Detection & Timeout Protocol** table:

```
| yfinance-collector.py | 15 seconds | Abort, log, skip to next fallback |
```

### 8.4 Source tagging reference

No changes to `CLAUDE.md` Section 11. yfinance data uses the existing `[Portal]` tag. Grade assignment follows the existing decision tree in `confidence-grading.md`:
- Cross-confirmed with Grade A source within 2% → Grade B
- Standalone → Grade C
- Missing or >15% divergence → Grade D

### 8.5 README updates (both languages)

Update **both** `README.md` (English) and `README.ko.md` (Korean). Keep the two files in sync — every edit to one must have a matching edit in the other.

Specifically, update the data source / fallback sections so readers see yfinance in the chain:

1. **Data source table** (around `README.md:291` / `README.ko.md:291`):
   - Add a row for yfinance as the intermediate fallback. Example:
     - EN: `| 🔄 Middle fallback | yfinance | Stable Python library — no API key, used when MCP/portal sources fail |`
     - KO: `| 🔄 중간 폴백 | yfinance | 안정적인 Python 라이브러리 — API 키 불필요, MCP/포털 실패 시 사용 |`

2. **MCP / data strategy section** (around `README.md:387-401` / `README.ko.md:386-400`):
   - In the Grade table, add a row describing yfinance (Grade B/C, `[Portal]` tag).
   - In the "Major web sources" / "주요 웹 소스" list, add yfinance as the recommended fallback before plain web scraping.

3. **Enhanced vs Standard Mode comparison** (around `README.md:450-454` / `README.ko.md:449-453`):
   - In "Requires" / "필요 조건" rows, note that Standard Mode now relies on yfinance first (no API key needed), web search only if yfinance also fails.

4. **Korean data sources** — if the Korean README has a KR sources table separate from the US one, add yfinance as the fallback below 네이버금융 (primary) with `.KS`/`.KQ` suffix note.

**Do NOT**:
- Rewrite the README's structure or tone.
- Change the core messaging that Financial Datasets MCP is the recommended primary.
- Add yfinance to principles, hero, or headline sections — it's a fallback, not a feature to promote.

**Verification**: After editing, search both READMEs for `Financial Datasets` and ensure every place that describes the data hierarchy now mentions yfinance in the correct position. The two files must remain translations of each other.

---

## 9. Testing Checklist

Implementer must verify these before marking the task done:

### 9.1 US ticker (happy path)
```bash
python .claude/skills/financial-data-collector/scripts/yfinance-collector.py \
  --ticker AAPL --market US --output /tmp/test_aapl.json
```
- [ ] Exit code 0
- [ ] `/tmp/test_aapl.json` exists and is valid JSON
- [ ] `current_price.price` is a number > 0
- [ ] `info.market_cap` is populated
- [ ] `income_statements` has ≥4 entries
- [ ] `derived_ttm.revenue_ttm` is populated and > 0

### 9.2 KR ticker — KOSPI
```bash
python .claude/skills/financial-data-collector/scripts/yfinance-collector.py \
  --ticker 005930 --market KR --output /tmp/test_samsung.json
```
- [ ] `yahoo_symbol` == `"005930.KS"`
- [ ] `current_price.currency` == `"KRW"`
- [ ] `current_price.price` is a number > 0

### 9.3 KR ticker — KOSDAQ (suffix fallback)
```bash
python .claude/skills/financial-data-collector/scripts/yfinance-collector.py \
  --ticker 035720 --market KR --output /tmp/test_kakao.json
```
(Kakao is actually KOSPI but use a real KOSDAQ ticker like `247540` for ecopro)
- [ ] Script tries `.KS` first, falls back to `.KQ`
- [ ] `yahoo_symbol` reflects the successful suffix

### 9.4 Invalid ticker
```bash
python .claude/skills/financial-data-collector/scripts/yfinance-collector.py \
  --ticker ZZZZZZZ --market US --output /tmp/test_bad.json
```
- [ ] Exit code 2
- [ ] No JSON file created (or JSON created with explicit error status — decide and document)

### 9.5 Timeout test
- Run with `--timeout 1` on a fresh DNS cache.
- [ ] Script aborts within ~2 seconds
- [ ] Exit code is 1 or 2, not a hang

### 9.6 Integration smoke test
- Run a full Mode A analysis for a US ticker with Financial Datasets MCP intentionally disabled.
- [ ] Pipeline completes
- [ ] Output shows `[Portal]` tags for price/metrics (not [Filing])
- [ ] No fabricated values; missing fields render as "—"

---

## 10. Out of Scope

These are NOT part of this task:
- Replacing Financial Datasets MCP as primary source
- Adding yfinance for options chain, dividends history, or fundamentals beyond what's listed in Section 5
- Caching yfinance responses to disk (aside from the single write to `--output`)
- Parallelizing multi-ticker yfinance calls
- Any UI changes to output reports — source tags already handle display differentiation

---

## 11. Acceptance Criteria

Codex's implementation is complete when:

1. `yfinance-collector.py` exists, is executable, and passes all tests in Section 9.
2. Two SKILL.md files and CLAUDE.md are updated per Sections 8.1–8.3. No existing behavior is removed.
3. Both `README.md` and `README.ko.md` are updated per Section 8.5 and remain synchronized translations of each other.
4. `yfinance>=0.2.40` is added to the project's Python requirements file (find existing pattern — likely `requirements.txt` or similar; check `tools/` scripts for conventions).
5. Running a US ticker analysis with MCP disabled produces a valid Mode A report with `[Portal]` tags, no fabricated values, and no pipeline stalls.
6. Running a KR ticker analysis with 네이버금융 intentionally broken (e.g., bad URL) produces a valid report with yfinance-sourced fields tagged `[Portal]` Grade C.

---

## 12. Open Questions for Implementer

Flag these back to the user if unclear during implementation:

1. Python environment: Is there a single `requirements.txt` at project root, or do scripts manage deps individually? (Check `dart-collector.py` header comments.)
2. Should `yfinance-raw.json` be promoted into immutable snapshots along with `tier1-raw.json`, or treated as run-local transient evidence only? Current implementation promotes it when present beside `analysis-result.json`.
3. For Workflow 2 (multi-ticker), should yfinance calls run in parallel via `concurrent.futures`, or sequentially with sleep? Spec assumes sequential for rate-limit safety — confirm if parallelism is preferred.
