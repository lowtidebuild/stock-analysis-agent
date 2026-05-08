# ADR 0004: Backtest Data Freeze 전략

작성일: 2026-05-08
상태: Accepted
관련 plan: `docs/superpowers/plans/2026-05-08-backtest-harness.md` (BT-D1)
구현: Chunk 2 (Tasks 2.1–2.4) on `feature/backtest-harness-chunk1`

## 맥락

Stock Analysis Agent의 R/R Score · Verdict · Variant View가 *실제 예측력*이 있는지를 검증하려면 과거 시점 데이터로 파이프라인을 다시 돌려야 한다. 백테스트의 본질은 "그 시점에만 알 수 있던 정보"로 분석을 재현하는 것이다.

문제: 우리가 의존하는 4개 데이터 소스는 historical 시점 재현 가능성이 제각각 다르다.

| 소스 | as-of API 지원 | 한계 |
|------|---------------|------|
| **yfinance** (가격, 시총, 재무제표, 기본 메타) | 부분 지원 | `Ticker.history(start, end)`은 historical OK. `Ticker.info`는 항상 현재 상태. options chain은 historical 미지원 (yfinance 한계). |
| **FRED** (매크로) | 완전 지원 | `observation_end` 파라미터가 native time-aware. |
| **SEC EDGAR (Financial Datasets MCP)** | 미지원 (MCP가 시점 파라미터 노출 X) | 응답에 `filing_date` / `period_end_date` 포함 → post-filter 가능. |
| **DART OpenAPI** (한국 공시) | 부분 지원 | `bgn_de` / `end_de` (필링 리스트), `bsns_year` / `reprt_code` (재무제표) — 보고서 단위 선택은 가능하지만 계산 필요. |

이론적 ideal은 모든 fetch가 as-of 시점 상태를 정확히 재현하는 것이지만, yfinance `info`와 옵션 체인은 시점 데이터가 *물리적으로 존재하지 않는다*. 그러나 backtest를 시작하지 못하면 시스템이 진짜 알파를 만드는지 영원히 모른다.

## 결정

**Hybrid freeze 전략**을 채택한다. 시점 데이터를 얻을 수 있는 것은 historical로 가져오고, 얻을 수 없는 것은 *현재 상태*를 사용하되 caveat로 명시한다.

| 항목 | 처리 | 캐브이엇 |
|------|------|---------|
| 가격 (yfinance) | `Ticker.history(start=as_of-10d, end=as_of+1d)` | — (정확) |
| 재무제표 (yfinance) | `period_end <= as_of` post-filter | — (정확) |
| `Ticker.info` 필드 (시총·shares_outstanding 등) | **현재 상태 그대로 통과** | `info_fields_use_current_state` |
| 애널리스트 목표가 | **as-of 모드에서 skip** (forward-looking) | `analyst_targets_skipped_as_of_mode` |
| 옵션 체인 | **as-of 모드에서 미수집** | `options_unavailable_in_backtest` (Mode E backtest는 별도 plan에서) |
| FRED 매크로 | `observation_end` native param | `macro_observation_end_applied` |
| FRED 캐시 | as-of 모드에서 bypass (현재 상태 캐시 = future leak) | `cache_bypassed_in_as_of_mode` |
| SEC filings (MCP) | `filing_date <= as_of` post-filter | `sec_post_filter_applied` |
| SEC 재무제표 (MCP) | `period_end_date <= as_of` post-filter | `sec_post_filter_applied` |
| DART 최근 공시 | `end_de = as_of` native param | `dart_as_of_mode_applied` |
| DART 정기보고서 | 통상 신고 마감일이 `as_of` 이전인 보고서만 시도 (자본시장법: 연간 90일, 분기 45일) | `dart_as_of_mode_applied` (+ `dart_attempts_filtered_by_filing_deadline` if 적용됨) |

모든 결과 JSON에는 다음 두 블록이 추가된다:

```json
"_backtest_caveats": [...],
"_backtest_meta": {
  "as_of": "YYYY-MM-DD",
  "freeze_strategy": "hybrid",
  "caveats": [...]
}
```

## 제외한 선택지

### Option A — 순수 historical (purist)

**거부 이유**: yfinance `Ticker.info` 시점 데이터는 *존재하지 않는다*. 시총·shares_outstanding을 재구성하려면 별도 historical shares 데이터 소스가 필요한데, Phase 1 가치 대비 셋업 비용이 과하다. 옵션 체인은 yfinance 한계로 historical 불가능. 순수성을 요구하면 Phase 1을 영원히 시작 못 한다.

### Option C — 현재 상태 인정 (look-ahead 전면 허용)

**거부 이유**: as-of 이후에 발표된 가이던스, 실적, 매크로 이벤트가 모두 분석에 흘러 들어와서 backtest 자체가 의미 없어진다. R/R Score가 좋은 게 *그 시점에 알 수 있어서*인지 *지나고 보니 알 수 있어서*인지 구별 불가.

## 구현 규칙

1. **모든 historical fetcher는 `--as-of` 플래그를 받는다.** Flag가 unset이면 production 동작과 byte-identical (회귀 0).
2. **leakage detector가 안전망**이다 (`tools/backtest/leakage_detector.py`). 모든 fetched 페이로드를 `_date` / `_datetime` 필드 기준으로 스캔하여 `as_of`보다 미래 날짜 발견 시 strict 모드에서 즉시 raise.
3. **Caveat는 항상 명시적으로** 출력 JSON `_backtest_caveats` 리스트에 추가. Cohort runner (Chunk 3)는 이 caveat을 집계하여 분석 메타데이터로 보존한다.
4. **모든 fetcher의 시점 거부는 일관**: future `--as-of` → 즉시 exit 2 + stderr 메시지 "future".
5. **DART 정기보고서는 보수적**: 통상 신고 마감일 기준으로 거를 때, 회사가 *늦게 신고*했다면 과거 데이터를 누락한다. 이는 의도된 false-negative — leak보다는 skip이 항상 우선.

## 인정하는 한계

본 결정은 다음 leakage 가능성을 *인정*한다:

- **`Ticker.info` 필드의 forward-looking 영향**: 현재 시총 / shares는 backtest 시점과 다를 수 있다. 보통 ±5% 이내 (분할/병합/대규모 발행 없는 한). Caveat로 명시.
- **DART 정기보고서 신고 지연**: 자본시장법 마감일 후에 늦게 신고한 회사는 통계적으로 잡지 못함. KOSDAQ 관리종목·상장폐지 watchlist 일부 종목에서 발생 가능. Caveat 없음 (드물게 발생).
- **분석 narrative의 macro 인사이트**: macro narrative LLM 분석이 forward-looking 매크로 모델 가정을 사용할 수 있다 (예: "Fed가 내년 인하할 것"). Phase 1은 이를 leakage로 잡지 않으며, leakage detector는 *날짜* 필드만 본다.

## Phase 2 후보 (이번 plan 범위 외)

- Historical shares_outstanding 데이터 소스 검토 (예: Polygon historical, FactSet) — `Ticker.info` 의존 제거.
- DART 정기보고서를 *실제 `rcept_dt`* 기준으로 선택 (현재는 통상 신고 마감일 추정). `list` 엔드포인트로 회사 단위 history 조회 후 매핑.
- Macro narrative analyst를 as-of-aware하게 수정 (별도 prompt 분기).
- Mode E backtest용 옵션 체인 historical 데이터 소스 (yfinance 외부, 비용 발생 가능).

## 후속 작업

1. **Chunk 3 cohort runner**가 모든 caveat을 코호트 manifest level에서 aggregate하여 `cohorts/{cohort}/runs/{ticker}/_backtest-meta.json`의 `caveats[]`에 보존.
2. **`_parse_iso_date` 4개 사본** (runner + 3 collectors) — 5번째 collector 추가 시 `tools/iso_date.py`로 prom공통화.
3. **DART filing-deadline 추정 함수** unit test 추가 (현재는 CLI tests로 간접 검증).
4. **leakage detector 통합 테스트**: Phase 1 cohort 실행 시 leakage 위반 0건 자동 검증.
