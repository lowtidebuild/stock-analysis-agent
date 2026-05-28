# Stock Analysis Agent 성능 개선 기획서

작성일: 2026-05-28
상태: Draft
범위: `stock-analysis-agent` 본체 파이프라인, A/B/C parity runner, collector, backtest harness
비범위: `stock-analysis-agent-web` 웹 포털 UI/API 성능

진행 현황:

- Session 1 완료: A/B/C parity runner stage timing, artifact size/token estimate, analyst input/backend usage 측정 추가.
- Session 2 완료: ticker source collection과 Financial Datasets endpoint 병렬화 추가.
- Session 3 완료: multi-ticker collection 및 ticker별 validation/calculation/analyst/render/critic pipeline 병렬화 추가.
- Session 4 완료: `--reuse-stages`와 ticker별 `stage-cache.json` 기반 validation/calculation/analyst/render/critic 재사용 추가.
- Session 5 완료: `analyst-input.json` compact profile, `analyst-input.compact.json`, 압축률/토큰 guard 및 compact handoff payload 추가.
- Session 6 완료: collector-level source cache, DART corpCode master cache, source별 TTL/env override, cache hit metadata, peer mini fetch TTL 옵션 추가.
- Session 7 완료: backtest outcomes ticker price JSONL cache, CLI cache flags, hit/miss/write/mismatch reporting 추가.
- Session 8 완료: `2025Q1` 30종목 outcomes 실측에서 ticker price cache-hit 재실행 6.85s -> 0.05s, 30/30 cache hit 확인.

## 1. 목표

이 문서는 Stock Analysis Agent의 실행 시간, LLM 토큰 비용, 반복 실행 비용을 줄이기 위한 단계별 개선안을 정의한다. 핵심 방향은 "정확도와 Blank-Over-Wrong 계약을 유지하면서, 독립적인 작업은 병렬화하고, 동일 입력의 재실행은 건너뛰며, LLM에 넘기는 context를 더 작게 만드는 것"이다.

성능 개선은 다음 세 축으로 나눈다.

1. Wall-clock time 단축: 네트워크 수집, ticker별 처리, deterministic stage 병렬화.
2. LLM 비용/지연 단축: Analyst handoff context 축소, fixture/deterministic 재사용, stage cache.
3. Batch/backtest 반복 비용 절감: 수집 결과와 outcome 가격 series cache 재사용.

## 2. 현재 관찰

### 2.1 A/B/C parity runner

주요 엔트리포인트는 `scripts/run_abc_parity.py`다.

현재 구조:

- macro 수집 후 ticker별 source collection을 순차 실행한다.
- ticker별 validation, calculation, analyst, render, critic도 순차 실행한다.
- `--reuse-collected`는 raw source 재사용을 지원하지만, validation 이후 stage cache는 없다.
- Mode B 또는 multi-ticker run에서 ticker 간 독립성이 큰데도 runner가 이를 충분히 활용하지 않는다.

### 2.2 Source collection

`scripts/parity/data_sources.py`의 `collect_ticker_sources()`는 source를 순차 호출한다.

US ticker의 경우:

- Financial Datasets REST 6개 endpoint가 순차 호출된다.
- DART는 market mismatch로 skip artifact를 만들 뿐이다.
- yfinance collector가 별도 subprocess로 실행된다.
- Mode C peer mini fetch가 추가로 실행된다.

KR ticker의 경우:

- Financial Datasets는 skip artifact를 만든다.
- DART collector와 yfinance collector가 순차 실행된다.
- DART corp code master 조회가 반복될 가능성이 있다.

### 2.3 Analyst handoff

`scripts/parity/analyst.py`는 다음 artifact를 JSON으로 묶어 Analyst backend에 전달한다.

- `research-plan.json`
- `validated-data.json`
- `evidence-pack.json`
- `context-budget.json`
- `deterministic-calculations.json`
- `peers/*.json` 일부

원칙은 안전하지만, 실제 분석에 쓰지 않는 metadata와 중복 evidence가 포함될 수 있다. 이 구간은 LLM latency와 비용에 직접 영향을 준다.

### 2.4 Backtest harness

`tools/backtest/batch_runner.py`는 ticker 수집에 `ThreadPoolExecutor`와 `max_workers`를 이미 사용한다. FRED도 cohort당 1회 수집으로 잘 분리되어 있다.

개선 여지는 outcome 단계다. `tools/backtest/outcome_computer.py`는 forward price를 yfinance에서 ticker별로 가져오므로 반복 실행 시 동일 price series를 다시 fetch할 수 있다.

## 3. 원칙

1. 정확도 계약을 깨지 않는다.
   병렬화와 cache는 결과 JSON의 의미를 바꾸면 안 된다.

2. 재사용은 입력 fingerprint 기반으로 한다.
   timestamp나 run id만으로 stage skip을 결정하지 않는다.

3. LLM stage와 network stage의 concurrency limit을 분리한다.
   API rate-limit과 모델 비용 폭주를 막기 위해 각각 다른 limit을 둔다.

4. 실패는 ticker 단위로 격리한다.
   한 ticker의 source failure가 전체 multi-ticker run을 불필요하게 막지 않도록 한다. 단, macro/core contract failure는 기존처럼 명확히 실패시킨다.

5. 성능 측정 artifact를 남긴다.
   추측으로 개선하지 않고, stage별 duration/token/byte metric을 `run-metadata.json` 또는 별도 `performance-summary.json`에 기록한다.

## 4. Phase 1 - 측정 기반 만들기

목표: 개선 전후를 비교할 수 있도록 stage별 timing과 token estimate를 기록한다.

### 작업

1. `scripts/run_abc_parity.py`에 stage timer 추가.
   - `macro_collect`
   - `ticker_collect`
   - `validation`
   - `calculation`
   - `analyst`
   - `render`
   - `critic`
   - `comparison`

2. ticker별 summary에 duration 추가.
   - `source-collection-summary.json`
   - `validation-summary.json`
   - `run-metadata.json`

3. Analyst input size 기록.
   - `analyst-input.json` byte size
   - `context-budget.json.totals.included_estimated_tokens`
   - backend usage가 있으면 prompt/completion/total tokens

4. baseline command를 문서화.

예시:

```bash
python scripts/run_abc_parity.py \
  --ticker AAPL \
  --mode C \
  --lang ko \
  --market US \
  --run-id perf_baseline_AAPL_C \
  --critic-only
```

### 완료 기준

- 동일 run에서 각 stage duration이 `run-metadata.json`에 남는다.
- fixture backend와 real backend 모두 summary schema가 깨지지 않는다.
- 기존 tests가 통과한다.

## 5. Phase 2 - Source collection 병렬화

목표: 네트워크 대기 시간이 긴 source collection을 병렬화한다.

### 작업

1. `collect_ticker_sources()` 내부 source 호출 병렬화.
   - Financial Datasets
   - DART
   - yfinance
   - peer mini fetch

2. source별 skip artifact는 즉시 생성하되, 실제 네트워크 source만 worker pool에 넣는다.

3. Financial Datasets endpoint 병렬화.
   - `/financials` quarterly
   - `/financials` ttm
   - `/prices`
   - `/filings`
   - `/insider-trades`
   - `/analyst-estimates`

4. 환경 변수로 concurrency 조정.
   - `SAA_SOURCE_MAX_WORKERS`, 기본 3
   - `SAA_FINANCIAL_DATASETS_MAX_WORKERS`, 기본 3

5. partial failure semantics 유지.
   - 일부 endpoint 실패 시 기존처럼 `status = partial`
   - 전체 실패 시 `status = failed`

### 완료 기준

- `collect-only` 실행에서 기존 output contract와 동일한 필드가 생성된다.
- endpoint 호출 순서에 의존하는 test가 없거나 안정적으로 수정된다.
- rate-limit 발생 시 실패가 명확히 summary에 남는다.

## 6. Phase 3 - Ticker-level 병렬화

목표: Mode B/multi-ticker run에서 ticker별 독립 stage를 병렬 실행한다.

### 작업

1. ticker별 collection을 병렬화.
   - `--ticker` + `--tickers` 조합에서 ticker 단위 source collection을 동시에 수행.

2. validation/calculation을 ticker 단위로 병렬화.
   - deterministic stage이므로 LLM concurrency와 분리 가능.

3. analyst stage는 별도 limit 적용.
   - `SAA_ANALYST_MAX_WORKERS`, 기본 1
   - fixture backend일 때는 4까지 허용 가능.

4. render/critic stage는 안전한 범위에서 병렬화.
   - renderer는 파일 경로가 ticker별로 분리되어 있으므로 병렬화 가능.
   - critic은 patch/render 재실행을 포함하므로 ticker별 lock 또는 ticker-local path 보장 필요.

5. Mode B comparison은 ticker별 artifact가 모두 준비된 뒤 실행.

### 완료 기준

- Mode B 2-5 ticker run에서 결과 artifact 경로 충돌이 없다.
- 한 ticker 실패가 다른 ticker summary 작성을 막지 않는다.
- comparison stage는 성공 ticker set을 명확히 기록하거나, 필요한 ticker 누락 시 명시적으로 fail한다.

## 7. Phase 4 - Stage cache와 reuse 확장

목표: 동일 입력으로 반복 실행할 때 불필요한 stage를 건너뛴다.

### Cache 단위

| Stage | 입력 fingerprint | 재사용 대상 |
|---|---|---|
| validation | raw source files + research-plan | `validated-data.json`, `evidence-pack.json`, `context-budget.json` |
| calculation | `validated-data.json` + mode + market | `deterministic-calculations.json` |
| analyst | compact analyst input + schema version + backend/model | `analysis-result.json` |
| render | `analysis-result.json` + renderer version | HTML + render report |
| critic | `analysis-result.json` + rendered report + critic version | `quality-report.json`, `critic-review.json`, `critic-loop-result.json` |

### 작업

1. `stage-cache.json` 또는 각 summary에 `input_fingerprint` 기록.
2. `--reuse-stages` 플래그 추가.
3. stage별 `cache_hit`, `cache_miss`, `cache_invalidated`를 summary에 기록.
4. backend/model 변경 시 analyst cache invalidation.
5. schema/renderer/critic version 변경 시 downstream cache invalidation.

### 완료 기준

- 같은 run id 또는 copied artifacts 기준 재실행 시 deterministic stage가 skip된다.
- 입력 artifact가 1 byte라도 바뀌면 관련 downstream stage가 재실행된다.
- cache hit가 결과 contract를 우회하지 않는다. 필요하면 validation은 cheap recheck만 수행한다.

## 8. Phase 5 - Analyst context 압축

목표: LLM에 넘기는 JSON을 줄여 latency와 비용을 낮춘다.

### 작업

1. `build_compact_analyst_input()` 추가.
   - validated metric 중 Grade A-C, analysis에 필요한 fields만 유지.
   - raw source excerpts는 evidence summary로 축약.
   - deterministic calculations는 scenario/DCF/reverse DCF/valuation bridge 핵심만 유지.
   - context-budget 전체 대신 totals와 routing policy summary만 유지.

2. compact input 저장.
   - `analyst-input.compact.json`
   - 기존 `analyst-input.json`은 debug 또는 `--verbose-input`일 때만 생성하는 선택지 검토.

3. 품질 회귀 방지.
   - golden fixture 기준 `analysis-result` contract test 유지.
   - critic pass rate 비교.
   - Mode C dashboard required section 유지.

4. threshold guard.
   - compact input이 기존 대비 25% 이상 줄지 않으면 warning.
   - included estimated tokens가 soft limit 초과 시 fail 또는 cheap-model preprocessor 권고.

### 완료 기준

- fixture backend test 통과.
- real backend smoke에서 critic delivery gate가 기존과 동등하거나 개선.
- `analyst-input` byte/token estimate가 baseline 대비 유의미하게 감소.

## 9. Phase 6 - Collector-level cache

목표: 반복 수집 비용을 줄이고 rate-limit 노출을 낮춘다.

### 작업

1. DART corp code master cache.
   - 경로: `output/data/dart/corp-code-map.json`
   - TTL: 24시간 또는 파일 생성일 기준 1일
   - cache miss 또는 parse failure 시 재다운로드

2. peer mini fetch cache 강화.
   - 이미 `output/data/peers-cache` 경로를 사용하므로 TTL/status 정책 점검.

3. yfinance fast bundle 검토.
   - Mode A smoke와 Mode C production이 필요한 필드를 분리.
   - 정상 호출 간 고정 sleep은 rate-limit 감지 기반 backoff로 전환 검토.

4. Financial Datasets cache는 보수적으로 접근.
   - 최신 가격/filings는 stale 위험이 크므로 TTL 짧게.
   - backtest/as-of 모드에서는 현재-state cache를 사용하지 않는다.

### 완료 기준

- KR batch에서 동일 실행 중 corpCode.xml 반복 다운로드가 발생하지 않는다.
- cache artifact에 source timestamp와 TTL metadata가 남는다.
- backtest leakage detector 계약을 깨지 않는다.

## 10. Phase 7 - Backtest outcome cache

목표: backtest outcome 반복 계산에서 yfinance forward price fetch를 줄인다.

### 작업

1. cohort 단위 ticker price cache 추가.
   - 경로 예: `evals/backtest/data/ticker-prices/{cohort_id}.jsonl`
   - key: ticker, market, start_date, end_date

2. `OutcomeComputer`에 optional price cache loader 추가.

3. `tools/backtest_runner.py outcomes`에 cache flag 추가.
   - `--ticker-price-cache`
   - `--refresh-ticker-price-cache`

4. cache miss는 기존 yfinance fetch로 fallback.

### 완료 기준

- `outcomes` 재실행이 network 없이 완료되는 경로가 생긴다.
- cache hit/miss count가 CLI 출력 또는 meta에 남는다.
- benchmark cache와 ticker price cache의 날짜 window mismatch가 명확히 에러 처리된다.

## 11. 권장 구현 순서

1. Phase 1: measurement
2. Phase 2: source collection 병렬화
3. Phase 3: ticker-level 병렬화
4. Phase 5: analyst context 압축
5. Phase 4: stage cache
6. Phase 6: collector cache
7. Phase 7: backtest outcome cache

Phase 4는 효과가 크지만 invalidation 설계가 중요하므로, 먼저 Phase 1-3으로 병목을 측정하고 단순 병렬화 효과를 확인한 뒤 들어간다.

## 12. 검증 계획

### 단위 테스트

- `tests/test_abc_parity_collection.py`
- `tests/test_abc_parity_validation.py`
- `tests/test_abc_parity_calculations.py`
- `tests/test_abc_parity_analyst.py`
- `tests/test_abc_parity_rendering.py`
- `tests/test_abc_parity_critic.py`
- `tests/backtest/*`

### 회귀 실행

```bash
python scripts/run_abc_parity.py \
  --ticker AAPL \
  --mode A \
  --lang ko \
  --market US \
  --run-id perf_smoke_AAPL_A \
  --critic-only
```

```bash
python scripts/run_abc_parity.py \
  --ticker AAPL \
  --mode C \
  --lang ko \
  --market US \
  --run-id perf_smoke_AAPL_C \
  --critic-only
```

```bash
python scripts/run_abc_parity.py \
  --ticker AAPL \
  --tickers AAPL,MSFT \
  --mode B \
  --lang ko \
  --market US \
  --run-id perf_smoke_AAPL_MSFT_B \
  --critic-only
```

### 측정 지표

| 지표 | 목표 |
|---|---|
| collect-only wall-clock | baseline 대비 30% 이상 감소 |
| Mode B multi-ticker wall-clock | ticker 수 증가 대비 선형보다 낮은 증가율 |
| analyst input estimated tokens | baseline 대비 25% 이상 감소 |
| real backend analyst latency | token 감소와 같은 방향으로 감소 |
| critic delivery_ready rate | baseline 대비 악화 없음 |
| network failure clarity | source별 partial/failure summary 유지 |

## 13. 리스크와 대응

| 리스크 | 영향 | 대응 |
|---|---|---|
| API rate-limit | 병렬화 후 실패 증가 | source별 max workers, backoff, partial status 유지 |
| 파일 경로 충돌 | artifact overwrite | ticker-local path만 병렬화, comparison은 barrier 이후 실행 |
| cache stale | 잘못된 분석 | input fingerprint + versioned invalidation |
| LLM 품질 저하 | critic fail 증가 | compact input rollout 전/후 golden run 비교 |
| 디버깅 어려움 | failure 분석 비용 증가 | stage timing, cache hit/miss, source summary 강화 |

## 14. Non-goals

- 분석 품질 기준 완화.
- Grade D 값을 채워 넣는 보정.
- web portal API/UI 성능 개선.
- 새로운 유료 데이터 벤더 도입.
- backtest freeze 전략 변경.

## 15. 다음 액션

1. `run_abc_parity.py`에 stage timing summary를 먼저 추가한다.
2. `collect_ticker_sources()` 내부 source 병렬화를 작은 PR로 분리한다.
3. Financial Datasets endpoint 병렬화를 별도 PR로 분리한다.
4. compact analyst input 설계 전, baseline `analyst-input.json` 크기와 token estimate를 3개 mode(A/B/C)에서 수집한다.
5. cache 설계는 fingerprint schema 초안을 만든 뒤 구현한다.
