# Agent Audit Remediation Guide — 검증 리뷰

작성일: 2026-04-24
검토 대상: [`docs/agent-audit-remediation-guide.ko.md`](./agent-audit-remediation-guide.ko.md) (코덱스 작성, 1363줄)
검토 방식: 플랜의 모든 구체적 주장을 `stock-analysis-agent` 코드베이스에 대조. 4개 병렬 Explore 에이전트가 영역별로 파일·라인 단위 검증 수행.

---

## 0. 결론 요약

코덱스 플랜은 **사실 관계가 대체로 정확하고 심각한 허위 주장은 없다**. 검증 가능한 16개 주장 중 TRUE 10 / PARTIAL 5 / OVERSTATED 1 / FALSE 0.

다만 플랜을 그대로 실행하면 안 되는 이유가 네 가지 있다.

1. 우선순위가 뒤집혀 있다 — 데이터 정확도 버그(틀린 숫자)가 P3로 밀려 있다.
2. 1.1의 작업량을 과소평가했다 — "함수 추가"가 아니라 사실상 재작성이다.
3. 2.1(경로 단일화)이 staleness/snapshot 캐싱 모델과 충돌한다.
4. 6.1(Mode Q)은 CLAUDE.md의 명시적 제품 결정을 버그로 오해했다.

아래에 항목별 판정, 플랜의 결함, 수정된 실행 순서를 정리한다.

---

## 1. 주장별 검증 결과

### 1.1 판정 매트릭스

| 섹션 | 주장 | 판정 | 핵심 근거 |
|---|---|---|---|
| **P0** 1.1 | `render-dashboard.py`가 속 빈 MVP | ✅ TRUE | `render-dashboard.py:494` 하드코딩된 placeholder. `dcf_analysis`/`analyst_coverage`/`qoe_summary` 미렌더. `factors[].factor` 필드 스키마 불일치 |
| **P0** 1.2 | `quality_report.py`가 렌더된 HTML 미검증 | ✅ TRUE | JSON contract만 검사. HTML 파싱·disclaimer·chart array 검증 전혀 없음 |
| **P0** 1.3 | `analysis-result.schema.json`이 너무 느슨 | ⚠️ PARTIAL | `schema:146` `sections`를 free object로 허용. 다만 orchestrator 레벨에서는 절차적으로 강제됨 |
| **P1** 2.1 | raw artifact 경로 모순 | ⚠️ PARTIAL | CLAUDE.md §4는 `output/data/{ticker}/`, `analysis_contract.py:208` `build_run_paths`는 run-local 반환. **문서/코드 불일치는 실존**하나 collision 위험은 현 설계상 제한적 |
| **P1** 2.2 | `STOCK_ANALYSIS_DATA_DIR` 미적용 | ⚠️ PARTIAL | `analysis_contract.py:208`, `artifact-manager.py:74` 하드코딩. 범위는 좁음 |
| **P1** 2.3 | delivery gate 정책 모순 | ✅ TRUE | CLAUDE.md §8 "do NOT block"과 `quality_report.py:322-329` BLOCKED 로직 불일치 |
| **P2** 3.1 | CLAUDE.md 중복 과다 | ⚠️ OVERSTATED | 542줄이지만 이미 routing index 형태. 산문 중복은 크지 않음. 200줄 목표는 공격적 |
| **P2** 3.2 | Standard Mode 검색 우선 | ✅ TRUE | `web-researcher/SKILL.md` §4.3 확인 |
| **P2** 3.3 | Analyst가 raw tier1/2 직접 로드 | ✅ TRUE | `analyst/AGENT.md:35-36`. **CLAUDE.md §7 테이블과 AGENT.md 불일치까지 추가 발견** |
| **P3** 4.1 | data_mode conflation | ⚠️ PARTIAL | yfinance fallback 후에도 `enhanced` 유지는 사실. `source_profile` 필드 부재 |
| **P3** 4.2 | DART TTM이 사실상 Q3 YTD | ✅ TRUE | `dart-collector.py:275-280` 9M 값을 "TTM approximation"으로 라벨. 주석(268)에 언급된 공식 미구현 |
| **P3** 4.3 | CapEx/FCF 부호 모호 | ✅ TRUE | `yfinance-collector.py:309` `op_cf + capex`; SKILL.md:154는 `OpCF - CapEx` 명시 |
| **P3** 4.4 | sanitization flag가 ingestion 차단 안 함 | ✅ TRUE | `artifact_validation.py:1141-1155` `valid`는 그대로 true. `ingestion_allowed` 필드 없음. 1076-77 FETCHED_ARTIFACT_TYPES는 validation bypass |
| **P5** 5.1 | Analyst 예시에 실제 AAPL/2026-04-25/$175.50 | ✅ TRUE | `analyst/AGENT.md:337,345,364` 확인 |
| **P5** 5.3 | Critic 결정론적 체크 과다 | ✅ TRUE | 7개 항목 중 6개가 코드로 재현 가능 (Item 1 Generic Test만 판단 필요) |

### 1.2 판정 분포

- TRUE: 10 (62%)
- PARTIAL: 5 (31%)
- OVERSTATED: 1 (7%)
- FALSE: 0

코덱스가 제시한 문제 자체는 신뢰할 수 있다. 근거가 빈약한 주장은 없다.

---

## 2. 플랜의 네 가지 결함

검증 과정에서 플랜 자체의 문제를 발견했다.

### 2.1 우선순위 뒤집힘 (가장 심각)

플랜은 다음 순서를 권장한다.

```
P0 최종 산출물 품질 계약 (렌더러, 스키마, HTML 검증)
P1 경로 및 delivery gate
P2 토큰 효율화
P3 데이터 정확도, prompt/tool 계약, critic 결정론화
```

하지만 4.2(DART TTM), 4.3(CapEx/FCF), 4.4(sanitization ingestion)는 **사용자에게 틀린 숫자 또는 오염된 텍스트를 전달한다**. 이는 CLAUDE.md §1의 첫 번째 원칙 "빈칸 > 틀린 숫자"의 직접 위반이다.

렌더러가 풍부하게 잘못된 숫자를 보여주는 것보다, 얕게 맞는 숫자를 보여주는 게 낫다.

> **권고**: 4.2, 4.3, 4.4, 5.1을 P0로 격상한다.

### 2.2 1.1(render-dashboard.py 승격)의 작업량 과소평가

플랜은 "17개 렌더 함수 추가"로 단순하게 기술한다. 검증에서 드러난 실제 조건:

- 현재 스크립트는 `factors[].factor` 필드 사용 → analyst는 `factors[].thesis` 산출
- `what_would_make_me_wrong`이 flat string → analyst는 구조화 객체 산출
- Chart.js data array 렌더 경로 없음
- DCF, analyst coverage, QoE, quarterly table 블록 전무

즉 **함수 추가가 아니라 사실상 재작성**이다. 800~1500줄 규모의 Python 작업으로 추정된다.

플랜에는 effort 추정이 없고, 중간 대안(CLAUDE.md가 현재 권장하는 "manual rendering from `html-template.md`" 유지) 대비 trade-off 논증이 약하다.

> **권고**: 1.1 착수 전에 대안 비교 문서를 별도로 작성한다. 선택지:
> - (A) render-dashboard.py 재작성
> - (B) html-template.md 기반 manual rendering을 canonical로 명문화하고 SKILL.md/AGENT.md에서 render-dashboard.py 참조 제거
> - (C) template driven 방식으로 Jinja/lightweight DSL 도입

### 2.3 2.1 경로 단일화가 캐싱 모델과 충돌

플랜은 `tier1/tier2-raw.json`을 전부 run-local로 이동시키고 `output/data/{ticker}/`는 snapshot/cache 전용으로 축소하라고 한다. 하지만:

- CLAUDE.md §0 Staleness Check는 `output/data/{ticker}/latest.json`에 의존
- "24시간 이내 재분석 skip"이라는 효율성 최적화가 run-local 이동 시 **매번 재수집**으로 바뀜
- Workflow 2 "session reuse" 규칙도 ticker 단위 shared path 전제

플랜은 "snapshot/cache 전용으로 축소"라고만 쓰고 다음을 명세하지 않는다.

- run-local 수집 결과가 언제·어떻게 shared snapshot으로 승격되는가
- staleness-checker가 무엇을 읽을 것인가
- tier1/tier2에 해당하는 스냅샷 구조는 유지되는가

이대로 구현하면 staleness 재사용이 깨진다.

> **권고**: 2.1 착수 전에 "run-local → shared snapshot 승격 규칙"을 먼저 설계한다.

### 2.4 6.1 Mode Q가 명시적 제품 결정과 충돌

플랜은 price-only 질의용 Mode Q(Quote Card)를 신설하자고 한다. 하지만 CLAUDE.md §3는 **의도적으로** 거절하고 "Yahoo Finance / Perplexity에서 확인하세요"로 리다이렉트한다.

이는 버그가 아니라 제품 스코프 결정이다. 에이전트가 간단한 시세 조회용으로 쓰이면:

- 토큰 비용이 분석 가치 대비 왜곡됨
- "투자 판단 도구"라는 포지셔닝 희석
- 사용자가 price-only로 습관화되면 심층 분석 활용도 하락

플랜은 이 배경을 인지하지 못하고 "UX 개선"으로 포장했다.

> **권고**: 6.1 섹션을 제거하거나 별도 제품 논의(CEO-mode 리뷰)로 분리한다.

---

## 3. 플랜이 놓친 것

1. **FRED 수집 실패 처리**: CLAUDE.md §9 timeout 표에 FRED collector가 있지만, macro_context 스키마에서 FRED 데이터의 Grade 표시 경로가 명시되지 않음. 플랜 미언급.
2. **`quality_report.py`에 이미 존재하는 결정론 체크**: 플랜 5.3은 "critic의 결정론 체크를 코드로"라고 하지만, `blank_over_wrong`, `financial_consistency` 등 일부는 이미 존재. 플랜은 "확장"이 아닌 "신설"처럼 서술.
3. **Workflow 2 멀티티커의 run-local 경로 의미**: 플랜 2.1은 `{run_id}/{ticker}/`라고 쓰는데 Workflow 2에서 run_id가 티커당인지 글로벌인지 명확화 필요.
4. **Critic re-dispatch 한계 재검토**: CLAUDE.md §7은 critic 1 loop 한계. 플랜 2.3이 severity 기반이면 BLOCKER일 때 loop 횟수 늘려야 할 수도 있는데 언급 없음.
5. **CLAUDE.md §7 분석가 입력 테이블 불일치**: 검증 중 발견. `analyst receives`에 tier1/tier2-raw가 없지만 AGENT.md는 이를 읽는다고 명시. 플랜 2.1과 3.3의 접점이지만 직접 지적되지 않음.

---

## 4. 권장 실행 순서 (수정본)

### 즉시 (데이터 정확도 + 보안)

1. **4.4** sanitization failure → ingestion block 승격 (보안)
2. **4.2** DART true TTM 계산 수정 (틀린 숫자)
3. **4.3** CapEx/FCF 표준 필드 분리 (틀린 숫자)
4. **5.1** Prompt 예시에서 실제 ticker/date/price 제거 (리크 위험)

### 짧은 주기 (품질 계약 강화)

5. **1.2** rendered output validator 추가 (현 quality gate 맹점)
6. **1.3** analysis-result schema per-mode 강제 (회귀 방지 테스트 기반)
7. **2.3** delivery gate severity 체계 도입

### 중간 주기 (설계 trade-off 필요)

8. **1.1** Mode C canonical renderer — **먼저 effort 추정 + 대안 비교 문서 작성**
9. **2.1** 경로 단일화 — **먼저 run-local → shared snapshot 승격 규칙 설계**
10. **5.3** critic 범위 축소 — **기존 `quality_report.py` 확장 방식으로 재포장**
11. **4.1** `source_profile` / `effective_mode` 도입

### 토큰 효율화

12. **3.2** Standard Mode yfinance-first 재정렬
13. **3.3** evidence pack 도입
14. **3.4** 모델 라우팅 비용 최적화

### 유보

- **3.1** CLAUDE.md 축소 — 현재 중복 크지 않음. 별도 ROI 분석 후 결정
- **6.1** Mode Q — 제품 결정 영역. 엔지니어링 이슈로 다루지 않음

---

## 5. 한 줄 요약

코덱스 플랜의 **사실은 맞지만 우선순위와 일부 설계 전제가 틀렸다**. 위 수정된 순서로 재구성하면 실행 가능하다.
