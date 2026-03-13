# Korean Data Sources Reference

This file defines the priority-ordered list of sources for Korean stock research.

DART OpenAPI is always attempted first (free API, key pre-configured). If it fails, the web chain below serves as fallback.

---

## Priority Chain (Use in Order)

| Priority | Source | URL / Method | Data Available | Grade |
|----------|--------|--------------|----------------|-------|
| **0** | **DART OpenAPI** | `dart-collector.py` (structured API) | 재무제표 (IS/BS/CF), 최근 공시 | **A** |
| 1 | 네이버금융 | `https://finance.naver.com/item/main.naver?code={종목코드}` | 현재가, 시총, PER, PBR, 배당률, 외국인지분 | B |
| 2 | FnGuide | `http://comp.fnguide.com/SVO2/ASP/SVD_Main.asp?pGB=1&gicode=A{종목코드}` | 컨센서스, 분기 실적 | B |
| 3 | 한국거래소 KIND | `https://kind.krx.co.kr` | 공시, 외국인/기관 수급, 지분율 변동 | B |
| 4 | General web search | — | 뉴스, 증권사 리포트, 업계 동향 | C |

---

## Priority 0 — DART OpenAPI (구조화된 재무 데이터, Grade A)

**Script**: `.claude/skills/web-researcher/scripts/dart-collector.py`

**Run**:
```bash
python .claude/skills/web-researcher/scripts/dart-collector.py \
  --stock-code {6digit} \
  --output output/data/{ticker}/dart-api-raw.json
```
API key is read from `DART_API_KEY` environment variable (set in `.claude/settings.local.json`).

**Data returned** (written to `dart-api-raw.json`):
- `ttm_income_statement`: 매출액, 영업이익, 당기순이익, EPS (annual or YTD)
- `balance_sheet_latest`: 자산총계, 부채총계, 자본총계, 현금, 차입금
- `periods_detail`: up to 4 periods (Q3/H1/Q1/Annual) with all account items
- `recent_disclosures`: 최근 90일 공시 목록 (잠정실적, 사업보고서 등)
- `corp_info`: 회사명, 대표이사, 업종

**Tag**: `[Filing]` → Grade A (규제기관 공시 원본, SEC filing과 동등)

**Confidence rule**:
- DART API financial statements → Grade A (direct from regulator database)
- Cross-checked with 네이버금융 within 5% → Grade A confirmed
- Not cross-checkable → Grade A with note "Single primary source — DART OpenAPI"

**If DART API fails** (network error, invalid stock code, no data):
- Log: "DART API unavailable — falling back to web sources"
- Proceed with Priority 1–4 chain (max Grade B)

---

## DART 전자공시 Web Usage (fallback when API unavailable)

**Purpose**: DART is the Korean SEC equivalent. Most authoritative source for financial statements.

**Finding company filings**:
1. Search: `{company name} DART 사업보고서 OR 분기보고서 2026 site:dart.fss.or.kr`
2. Direct URL pattern: `https://dart.fss.or.kr/dsearch/main.do?maxResults=5&textCrpNm={company name}&sort=date`

**Key document types**:
- 사업보고서 (Annual Report — filed after FY end): Full financials, detailed business description
- 분기보고서 (Quarterly Report — Q1, Q3): Financial statements for the quarter
- 반기보고서 (Semi-annual Report — H1): Mid-year financials
- 잠정실적 발표 공시 (Preliminary earnings release): First look at quarter results

**Financial statement structure in DART**:
- 연결재무상태표 (Consolidated Balance Sheet)
- 연결손익계산서 (Consolidated Income Statement)
- 연결현금흐름표 (Consolidated Cash Flow Statement)
- Always use 연결 (Consolidated), not 별도 (Standalone), for analysis

**Unit handling**: DART financials typically in "백만원" (millions KRW) or "억원" (100 millions KRW). Standardize to absolute KRW.

---

## 네이버금융 Usage

**URL**: `https://finance.naver.com/item/main.naver?code={종목코드}`

**Data available on main page**:
- Current price (현재가), day change
- Market cap (시가총액)
- PER (P/E ratio — based on consensus)
- PBR (P/B ratio)
- Dividend yield (배당수익률)
- 52-week range (52주 최고/최저)
- Volume (거래량)
- Foreign investor ownership (외국인 소진율)

**Consensus/estimates**: Navigate to "투자의견" tab for analyst consensus ratings and target prices
**Financials**: Navigate to "종목분석" → "재무제표" for financial statement tables

---

## FnGuide Usage

**Purpose**: Detailed consensus data and financial summaries.

**URL pattern**: `http://comp.fnguide.com/SVO2/ASP/SVD_Main.asp?pGB=1&gicode=A{종목코드}`

**Data available**:
- Annual and quarterly financial statements (income, balance, cash flow)
- Operating margin, net margin history
- Analyst consensus: EPS estimates, revenue estimates, target prices
- P/E, EV/EBITDA consensus

---

## KIND (한국거래소) Usage

**Purpose**: Official disclosures, corporate actions, investor ownership data.

**Search**: `{company name} 외국인 지분율 site:kind.krx.co.kr OR KIND 한국거래소`

**Data available**:
- 외국인 지분율 (Foreign investor ownership %)
- 기관 순매수/순매도 (Institutional net buy/sell)
- 공시 (Corporate disclosures — same as DART but KRX-perspective)
- 밸류업 공시 (Value-up program disclosures)

---

## Korean Search Queries

Execute these searches in Standard Mode for KR stocks:

| # | Search Query (Korean) | Data Obtained |
|---|----------------------|---------------|
| 1 | `"{company name}" 주가 시가총액 현재가` | Price, market cap |
| 2 | `"{company name}" 실적 매출 영업이익 순이익 {current year}` | Recent financials |
| 3 | `"{company name}" PER PBR EV/EBITDA 밸류에이션` | Valuation metrics |
| 4 | `"{company name}" DART 재무제표 분기보고서` | Authoritative financials |
| 5 | `"{company name}" 증권사 목표주가 투자의견 {current year}` | Analyst views |
| 6 | `"{company name}" 뉴스 최근 실적전망` | News, guidance |
| 7 | `"{company name}" 외국인 지분율 수급 동향` | Foreign investor trend |
| 8 | `"{company name}" 사업구조 경쟁자 업계 동향` | Business context |

---

## Korean Stock Confidence Grade Notes

- Financial statements (IS/BS/CF) from DART API → **Grade A**, tag `[Filing]`
- Price/market data: 네이버금융 → Grade B, tag `[KR-Portal]`
- Analyst consensus: FnGuide/web → Grade B, tag `[KR-Portal]`
- If DART API unavailable (fallback): DART web + 네이버금융 agree → Grade B; single source → Grade C

Tag Korean web sources with `[KR-Portal]`. DART sources (API or web) tagged `[Filing]`.

---

## Common Korean Companies — Data Source Notes

**삼성전자 (005930)**:
- DART has very complete filings (quarterly + annual)
- 네이버금융 is accurate for market data
- Semiconductor segment data in 사업보고서 is detailed

**NAVER (035420)**:
- Financial data widely available
- Search advertising + content + Webtoon segment breakdown in 사업보고서

**SK하이닉스 (000660)**:
- Memory cycle sensitivity — quarterly results are key
- DART filings comprehensive

**한국 금융주 (Banking)**:
- Supplement with 금융감독원 전자공시 (FISIS) for detailed loan/NPL data
- URL: `http://fisis.fss.or.kr`
