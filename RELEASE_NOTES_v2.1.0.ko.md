# 릴리즈 노트 — v2.1.0

**릴리즈 날짜**: 2026년 5월 7일
**한 줄 요약**: *실적 프리뷰, 실적 리뷰, 그리고 지난 분석과의 차이를 한 눈에 — 어닝 발표일 전후 7일을 위한 분석 도구 셋.*

---

## 한 눈에 보기 (TL;DR)

v2.1.0으로 할 수 있는 세 가지:

1. **Mode E로 어닝 발표일 전후 7일 전용 분석을 받습니다.** 발표일까지 7일 이내라면 에이전트가 Preview(컨센서스, 옵션시장 implied move, watchpoint) 또는 Review(실제 vs 컨센서스, 사업부별 분해, 사후 액션 플랜) 중 적합한 보고서를 자동 작성합니다.
2. **같은 종목을 다시 분석하면 무엇이 달라졌는지가 보고서 최상단에 자동으로 뜹니다.** R/R 점수 변화, 목표가 변화, Verdict 변화, 리스크 리스트 diff — 마지막 스냅샷과 비교한 결과를 별도 명령 없이 받습니다.
3. **Mode C 보고서를 valuation reconcile 문서로 사용할 수 있습니다.** Peer 표가 실제로 fetch된 숫자로 채워지고, 향후 12개월 카탈리스트 타임라인이 이벤트 cluster를 시각화하며, Valuation Bridge 위젯이 DCF / peer 멀티플 / 애널리스트 컨센서스 / base 시나리오 4개 anchor를 가중평균 적정가 하나로 reconcile합니다. Mode B 비교에는 같은 섹터 종목의 매크로 노출 차이가 추가됩니다.

이 중 하나라도 유용해 보이면 아래 본문을 읽어주세요.

---

## 무엇을 할 수 있나 (v2.1.0 신규 기능)

### 1. Mode E — 실적 프리뷰 & 리뷰

Mode E는 어닝 발표일 전후 7일 윈도우 전용 분석 모드입니다. 발표일 기준 어느 쪽에 있는지 자동 감지해서 적합한 보고서를 작성합니다.

**두 윈도우:**

| 윈도우 | 모드 | 제공 내용 |
|---|---|---|
| **D-7 ~ D-1** (발표 전 일주일) | **Preview** | 컨센서스 EPS·매출 + 분포(고점/중간/저점), 옵션시장 implied 1일 변동폭, 마지막 8분기 beat/miss 히스토리 (hit rate + 평균 surprise), 이번 발표에서 지켜볼 4-5개 핵심 watchpoint 질문, pre-mortem 시나리오, 사전 포지션 권고 |
| **D ~ D+3** (발표 당일과 이후 3일) | **Review** | 실제 vs 컨센서스 표, 사업부별 매출 분해, 가이던스 변화 요약 (FY EPS pre/post), Preview에서 던졌던 watchpoint 질문에 대한 답, thesis 영향, 가벼운 verdict + Mode C 재실행 권고 시점, 사후 액션 플랜 (Hold / Trim / Hedge / Add) — 진입·청산 levels 포함 |

**Preview 사용 예시.** AAPL이 다음 주 수요일 실적 발표 예정. 화요일에 `AAPL 프리뷰` 또는 `AAPL earnings preview`를 실행하면 다음을 받습니다:

- 컨센서스 EPS $1.62, 매출 $89.4B (애널리스트 분포: 고점/중간/저점)
- 옵션시장 implied 1일 변동폭: ±3.2%
- 마지막 8분기: hit rate 75%, 평균 surprise +5.9%
- "Cloud 성장 +30% 유지 가능?" 같은 4-5개 watchpoint 질문
- 발표 전 포지션 권고 (예: Hold + 옵션 straddle, catalyst 트레이더 옵션)

**Review 사용 예시 (실측 검증, AMD Q1 2026, D+2).** 2026-05-05 AMD 실적 발표 후 D+2 시점에 `AMD review` 명령을 실행 → 33KB HTML 보고서:

- **Print Snapshot**: EPS $1.37 vs 컨센 $1.28 (+7.0% beat) / 매출 $10.25B vs $9.89B (+3.6% beat)
- **사업부별 분해**: Data Center $5.8B (+57% YoY), Client $2.88B (+26%), Gaming $720M (+11%), Embedded $873M (+6%)
- **가이던스 변화**: Q2 매출 가이드 $11.2B vs 컨센 $10.5B (+6.7% 상회), GM 56%, Server CPU TAM $60B → $120B 두 배 상향
- **Light Verdict**: outdated_flag 설정, Mode C 재실행은 D+4~D+7 권고
- **Post-Print Action**: 종가 $421.39에서 신규 진입 비추천. 보유자는 Trim 1/3 at $470, Trim 1/3 at $525, Stop $360

**사용법.** 어닝 발표일 7일 이내 시점에 `AMD 어닝 분석해줘`, `Analyze AMD earnings`, `AAPL 프리뷰` 등으로 말하면 됩니다. 에이전트가 캘린더를 읽어 윈도우를 자동 분류하고 Preview 또는 Review를 선택합니다.

### 2. Mode E 접근성 레이어

모든 Mode E 보고서에는 4가지 가독성 요소가 표준 템플릿으로 포함됩니다:

- **최상단 TL;DR** — 3개 핵심 bullet, 30초 안에 결론 파악
- **사업부별 매출 분해 표** — 매 사업부의 매출 / YoY% / 전사 비중 / 영업이익률
- **"일반 투자자 입장에서" 콜아웃** — 각 섹션마다 "왜 이 숫자가 중요한가"를 평이한 한국어로 설명
- **본문 내 용어 풀이** — Surprise %, Forward P/E, TAM, Multiple Re-rating 등 헷갈리는 jargon 10개를 보고서 안에서 plain Korean으로 정의 (검색하지 않고도 끝까지 읽을 수 있음)

옵션이 아닌 표준 구성입니다.

### 3. Auto Delta 배너 — 재분석할 때마다 차이가 자동 표시

이미 스냅샷이 저장된 종목을 다시 분석하면, Mode A/B/C/D/E 어느 모드든 보고서 최상단에 delta 배너가 자동으로 추가됩니다:

- **R/R 점수 변화** — 예: "1.42 → 1.69 (+0.27)"
- **Base 목표가 변화** — 예: "$385 → $418 (+8.6%)"
- **Verdict 변화** — 변화 없으면 "관찰 (유지)", 변했으면 "Hold → Buy"
- **리스크 리스트 diff** — 신규 리스크 (예: "AI Capex 회수 지연"), 해제된 리스크

**사용 예시.** 4월에 AAPL을 분석했고 5월에 다시 분석하면, 5월 보고서가 executive summary 위에 위 delta 블록을 자동으로 표시합니다 — 별도 명령 없음, 별도 diff 도구 없음. 특정 분석에서 끄고 싶다면 명령에 `--no-delta`를 추가하세요.

배너는 손으로 답하기 어려운 질문에 답합니다: *thesis가 진짜로 바뀐 건가, 아니면 노이즈에 반응하는 건가?* R/R이 0.05만 움직였다면 노이즈 트레이딩이고, 0.50 움직이고 신규 리스크가 3개 추가됐다면 thesis가 실제로 변한 것입니다.

### 4. Mode B — Peer 비교에 매크로 컨텍스트

Mode B 비교 (같은 섹터 2-5종목)에 매크로 컨텍스트 블록이 추가됩니다: 회사 type별 핵심 매크로 시리즈 3-5개, 그리고 종목별 매크로 노출 차이 narrative.

**사용 예시.** `삼성전자 vs SK하이닉스 비교` 명령 → Mode B 보고서:

- **매크로 스냅샷**: 10Y Treasury 4.45%, USD/KRW 1380, Memory ASP "Strong"
- **종목별 매크로 노출 narrative**:
  - 삼성전자 (Beta 1.3): "Memory + Mobile + VD 다각화로 USD/KRW 강세 시 환차익이 부분적으로 상쇄"
  - SK하이닉스 (Beta 2.0): "Memory 단일 베팅으로 ASP 사이클에 100% 노출. 금리 +50bp 시 -10~15% 추가 하락 risk"

*"둘 다 메모리 종목이니 비슷하겠지"* 와 *"이 둘은 절대 같은 베팅이 아니다"* 의 차이입니다.

### 5. Mode C — Peer 미니 파이프라인 (실제 숫자)

Mode C 보고서 내부의 peer 비교 표는 각 peer에 대해 yfinance로 abbreviated fetch (peer당 5-7개 metric, 24시간 캐시)를 거친 실제 숫자로 채워집니다.

**GOOGL Mode C 보고서 sample 출력:**

| Peer | P/E | EV/EBITDA | 영업이익률 |
|---|---|---|---|
| MSFT | 31.5x | 22.5x | 44.5% |
| META | 24.0x | 16.5x | 38% |
| AMZN | 33.0x | 19.0x | 11% |
| AAPL | 30.5x | 22.0x | 31% |

Peer fetch가 실패한 셀은 명확한 표시로 띄우며 가짜 숫자를 채우지 않습니다 — *빈칸 > 틀린 숫자* 원칙 그대로 적용됩니다. 24시간 캐시 덕분에 같은 peer set을 다른 분석에서 재사용할 때 즉시 사용됩니다.

### 6. Mode C — 12개월 카탈리스트 타임라인

Mode C 보고서에 향후 12개월 카탈리스트의 horizontal-bar 타임라인이 포함됩니다. 카테고리별 색상 구분:

- **실적** (파랑) — 분기 발표
- **규제** (빨강) — FDA 결정, 반독점 판결, FOMC
- **제품** (녹색) — 주요 런치, GTC 키노트, Investor Day
- **매크로** (노랑) — CPI 발표, 고용지표, 주요 중앙은행 회의
- **기타** (회색) — 법적 판결, 배당 발표, 임시 주총

Bar 길이가 이벤트 기간을 나타냅니다: 단일 일자 이벤트는 점, 분기 단위 이벤트는 막대. 같은 시기 이벤트가 나란히 배치되어 cluster를 한눈에 볼 수 있습니다 — 예: "2026 Q4에 실적 발표 + DC Circuit 항소심 + Gemini 신제품 런치가 동시 발생 → 변동성 집중 구간".

Peer 미니 파이프라인이 peer 데이터를 채웠다면 peer 카탈리스트도 같은 타임라인에 함께 표시됩니다 — subject 종목 이벤트와 peer 이벤트가 겹치는 시점이 보입니다.

### 7. Mode C — Valuation Bridge 위젯

Mode C 보고서는 가정에 따라 한 방향을 가리키는 DCF 적정가와 다른 방향을 가리키는 base 시나리오 목표가를 동시에 산출할 수 있습니다. Valuation Bridge 위젯은 4개 anchor를 한 차트에 reconcile하고 가중평균 적정가 하나를 산출하며, 가중치 선택 이유를 paragraph로 설명합니다.

**Sample reconcile (실측, GOOGL):**

- **DCF 적정가**: $241 (현재가 $388 대비 −37.9%)
- **Peer 멀티플 적정가**: $300 (−22.8%)
- **애널리스트 컨센서스 목표가**: $428.50 (+10.3%)
- **우리 base 시나리오 목표가**: $418 (+7.6%)
- **가중평균**: $346.84 (−10.7%) — *"시장이 우리 base case 보다 낙관 편향"*

보고서에 가중치 선택 이유 paragraph가 포함됩니다 (예: "DCF는 terminal value 민감도가 높아 가중치 낮춤; peer 멀티플은 peer set이 대칭적이라 가중치 높임"). 독자가 충돌하는 anchor 사이에서 알아서 선택할 필요가 없습니다 — 보고서가 reconcile합니다.

---

## 사용 시작하기 (Quick Start)

| 원하는 결과 | 트리거 문구 | 출력 모드 | 출력 위치 |
|---|---|---|---|
| 어닝 프리뷰 (D-7 ~ D-1) | `AAPL 프리뷰`, `AAPL earnings preview` | Mode E (Preview) | `output/reports/AAPL_E_*.html` |
| 어닝 리뷰 (D ~ D+3) | `AMD review`, `AMD 실적 분석` | Mode E (Review) | `output/reports/AMD_E_*.html` |
| 같은 섹터 짝 비교 + 매크로 | `삼성전자 vs SK하이닉스 비교` | Mode B | `output/reports/{T1}_{T2}_B_*.html` |
| 모든 v2.1 위젯 포함 풀 대시보드 | `GOOGL 분석해줘`, `analyze GOOGL` | Mode C | `output/reports/GOOGL_C_*.html` |
| Delta 배너 포함 재분석 | 기존과 동일 — 배너는 자동 | 모든 모드 | 같은 경로 |
| Delta 배너 끄기 | 명령에 `--no-delta` 추가 | 모든 모드 | 같은 경로 |

"earnings", "어닝", "프리뷰", "review", "실적" 같은 어닝 윈도우 키워드와 함께 ticker가 언급되고 7일 이내에 발표가 예정된 경우 자동으로 Mode E로 라우팅됩니다. 윈도우 밖이면 같은 쿼리는 Mode C로 라우팅됩니다.

---

## 검증된 사용 시나리오

### AMD Q1 2026 Review (D+2, 2026-05-07 검증 완료)

2026-05-05 AMD 실적 발표 후, `AMD review` 요청으로 섹션 1에 기술된 33KB Mode E Review가 실제로 생성됐습니다: print snapshot, 사업부별 분해, 가이던스 변화, `outdated_flag` 가 포함된 light verdict, 진입·trim·stop 레벨이 명시된 사후 액션 플랜. 픽스처가 아닌 실제 fetch 데이터로 end-to-end 실행.

### 삼성전자 vs SK하이닉스 (Mode B with macro context)

`삼성전자 vs SK하이닉스 비교` 요청으로 매크로 스냅샷, 종목별 beta-weighted 매크로 노출 narrative, 그리고 P/E / 마진 / 성장률 사이드 패널이 포함된 Mode B 비교 보고서가 생성됩니다. 매크로 블록이 차등 매크로 민감도를 implicit이 아닌 explicit으로 가시화합니다.

### GOOGL Mode C (peer 파이프라인 + Valuation Bridge)

`GOOGL 분석해줘` 요청으로 실제 숫자가 채워진 peer 표 (MSFT / META / AMZN / AAPL), 12개월 카탈리스트 타임라인 (실적 + DC Circuit 항소심 + 제품 이벤트), 그리고 DCF / peer / 컨센서스 / base case 4개 anchor를 가중평균 적정가 하나로 reconcile하는 Valuation Bridge가 포함된 Mode C 대시보드가 생성됩니다.

---

## 내부 구조 (개발자용)

기여자와 ship된 내용을 알고 싶은 사용자를 위한 구현 세부:

- **테스트 수**: 256개 → 262개 (모두 통과). 스키마 검증, 렌더러 contract test, peer-fetch 결정성, 어닝 윈도우 detector를 커버.
- **아키텍처 추가**:
  - `earnings-window-detector` 스킬 (캘린더에서 D-7 ~ D+3 윈도우 감지)
  - `peer-fetch` 미니 파이프라인 (peer당 5-7 metric, 24시간 캐시, 실패 시 빈칸)
  - `options-fetcher` (Mode E Preview에서 implied 1일 변동폭 계산용)
  - `valuation-bridge` 위젯 렌더러 (가중평균 reconcile + 근거 paragraph)
  - `delta-banner` 블록 (`output/data/{ticker}/latest.json` 과 diff)
- **Phase**: 6개 (A부터 F까지), 각 단계에서 spec compliance + code quality dual-stage 리뷰 통과.
- **세션**: v2.1 개발 아크 동안 4개 세션.
- **Trust boundary 변경 없음**: fetch된 모든 콘텐츠 (yfinance, 옵션 체인, 뉴스, 공시) 는 여전히 `tools/prompt_injection_filter.py` 를 통과합니다. Mode E 산출물도 Mode C와 동일한 `_sanitization` 블록을 캐립니다.

---

## 업그레이드 방법

```bash
git pull origin main
```

의존성 변경 없음, 마이그레이션 스크립트 없음. `output/reports/` 안의 기존 보고서는 재작성되지 않습니다 — 새 분석부터 새 레이아웃이 자동으로 적용됩니다. Delta 배너는 `output/data/{ticker}/latest.json` 에 스냅샷이 있는 종목을 처음 재분석할 때 활성화됩니다.

---

## 다음 예정

근시일 로드맵 (확정 일정 아님):

- **백테스팅 프레임워크** — 과거 시점의 분석을 재실행하고 ("2024년 1월 시점에 TSLA에 대해 에이전트는 뭐라고 했을까?") verdict를 실제 1년 수익률에 대해 채점. Thesis 정확도 자체 감사에 유용.
- **MINOR 유지보수 패스** — 카탈리스트-aggregator 중복 제거, FRED 캐시 TTL, peer 캐시 invalidation rule 등.

본인 워크플로에 특별히 유용한 항목이 있다면 issue로 알려주세요.

---

## 면책 조항

이 에이전트는 투자 *리서치*를 생성하며, 투자 *조언*이 아닙니다. 모든 출력은 표준 면책 조항과 함께 제공됩니다: *정보 제공 목적이며, 투자 조언이 아닙니다.* 거래 전에는 항상 본인의 due diligence를 수행하시고, 라이선스가 있는 자문가와의 상담을 고려해주세요.
