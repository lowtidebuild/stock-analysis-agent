# 주식 분석 에이전트

> **Language / 언어**: [English](README.md) | 한국어

Claude Code 기반 개인 투자자용 AI 리서치 어시스턴트. 미국 주식(NYSE/NASDAQ/AMEX)과 한국 주식(KRX/KOSPI/KOSDAQ)을 지원하며, 출처 태그가 달린 구조화된 분석과 엄격한 할루시네이션 방지 정책을 적용합니다.

---

## 주요 기능

- **3가지 분석 모드** — 동종 비교(B), 심층 대시보드(C), 투자 메모(D)
- **적응형 데이터 전략** — MCP API 사용 가능 시 Enhanced Mode, 불가 시 웹 검색 Standard Mode로 자동 전환
- **할루시네이션 방지 원칙** — 검증 불가 데이터는 "—"으로 표시, 절대 수치를 임의 생성하지 않음
- **3중 팩트체크** — 산술 일관성 → 다중 출처 교차검증 → 섹터 상식 검증
- **출처 태그 의무화** — 모든 수치에 출처 태그 부착: `[API]`, `[Web]`, `[Calculated]`, `[DART]` 등
- **한국 주식 완전 지원** — DART → 네이버금융 → FnGuide 데이터 체인, 한국어 출력
- **포트폴리오 & 워치리스트** — 보유 종목 관리, 변화 비교(델타 분석), 카탈리스트 캘린더

---

## 빠른 시작

### 사전 준비

- [Claude Code](https://claude.ai/code) CLI 설치 및 인증 완료
- Python 3.8 이상 (비율 계산 스크립트 실행용)
- (선택) Financial Datasets MCP + FMP MCP API 키 — Enhanced Mode용

### 1. 저장소 복제

```bash
git clone <your-repo-url>
cd stock-analysis-agent
```

### 2. (선택) MCP 설정 — Enhanced Mode

전체 설정 방법은 [MCP 설정 가이드 (한국어)](docs/mcp-setup-guide.ko.md) 또는 [영어 가이드](docs/mcp-setup-guide.md)를 참고하세요.

MCP 없이도 Standard Mode(웹 검색)로 완전히 동작합니다. 데이터 신뢰도 등급이 최대 Grade B(API 사용 시 Grade A)라는 차이만 있습니다.

### 3. Claude Code 실행

```bash
claude
```

Claude Code는 세션 시작 시 `CLAUDE.md`를 자동으로 읽습니다. 다음과 같은 상태 블록이 표시됩니다:

```
=== Stock Analysis Agent ===
Data Mode: Enhanced (MCP active)   ← 또는 "Standard (Web-only)"
Date: 2026-03-12
Ready. Send a ticker or question to begin.
```

---

## 사용 방법

### Workflow 1 — 단일 종목 분석

전체 분석 파이프라인. 표현 방식에 따라 모드가 자동 선택되며, 명시적으로 지정할 수도 있습니다.

| 표현 방식 | 모드 | 출력 형식 |
|----------|------|---------|
| "분석해줘" (기본값) | C — 심층 대시보드 | HTML 파일 |
| "심층 분석" / "자세히" | C — 심층 대시보드 | HTML 파일 |
| "투자 메모" / "investment memo" | D — 투자 메모 | 마크다운 파일 |

**사용 예시**:
```
삼성전자 심층 분석해줘
TSLA 투자 메모 써줘
005930 분석해줘
NVDA 분석해줘
```

**Mode C — 심층 대시보드** (HTML 파일):
`output/reports/AAPL_C_KR_2026-03-12.html`에 저장 → 브라우저에서 바로 열기

**Mode D — 투자 메모** (마크다운 파일):
`output/reports/AAPL_D_KR_2026-03-12.md`에 저장 — 10개 섹션, 약 3,000단어 분량

---

### Workflow 2 — 동종 비교

2~5개 종목을 나란히 비교하고 R/R Score 순위와 최선호 종목을 제시합니다.

```
AAPL vs MSFT vs GOOGL
삼성전자 vs SK하이닉스 비교해줘
NVDA, AMD, INTC 비교
```

**출력**: HTML 비교 매트릭스 (`output/reports/AAPL_GOOGL_MSFT_B_KR_2026-03-12.html`)

---

### Workflow 3 — 포트폴리오 & 워치리스트

**워치리스트 관리**:
```
AAPL 워치리스트 추가
삼성전자 워치리스트 추가
NVDA 워치리스트에서 삭제
워치리스트 보여줘
워치리스트 스캔해줘
카탈리스트 캘린더 보여줘
```

**포트폴리오 등록** (3가지 형식 지원):

*인라인 채팅*:
```
AAPL 100주 $150, MSFT 50주 $380, 삼성전자 200주 72000원
```

*JSON*:
```json
[
  {"ticker": "AAPL", "shares": 100, "avg_cost": 150, "currency": "USD"},
  {"ticker": "005930", "shares": 200, "avg_cost": 72000, "currency": "KRW"}
]
```

*CSV*:
```
ticker,shares,avg_cost,currency
AAPL,100,150,USD
005930,200,72000,KRW
```

**포트폴리오 분석**:
```
포트폴리오 분석해줘
내 포트폴리오 리뷰해줘
```

**변화 비교 (델타 분석)**:
```
AAPL 지난번 분석이랑 비교해줘
삼성전자 이전 분석과 달라진 것 뭐야?
```

---

## 출력 파일

모든 생성 파일은 `output/` 아래에 저장됩니다(기본적으로 `.gitignore` 처리):

| 경로 | 내용 |
|------|------|
| `output/reports/{ticker}_C_*.html` | Mode C HTML 대시보드 |
| `output/reports/{ticker}_D_*.md` | Mode D 투자 메모 |
| `output/reports/{tickers}_B_*.html` | Mode B 동종 비교 매트릭스 |
| `output/data/{ticker}/latest.json` | 가장 최근 스냅샷 |
| `output/data/{ticker}/{ticker}_{date}_snapshot.json` | 버전별 아카이브 |
| `output/watchlist.json` | 워치리스트 |
| `output/portfolio.json` | 포트폴리오 보유 종목 |
| `output/catalyst-calendar.json` | 카탈리스트 캘린더 |

---

## 데이터 신뢰도 체계

출력의 모든 수치에는 신뢰도 등급과 출처 태그가 부착됩니다.

| 등급 | 태그 | 의미 |
|-----|------|------|
| A | *(없음)* | 1차 출처 검증 + 산술 일관성 확인 |
| B | `[≈]` | 2개 이상 출처 교차검증, 차이 5% 이내 |
| C | `[1S]` | 단일 출처, 미검증 |
| D | `[Unverified]` | 검증 불가 → "—"으로 표시 |

**출처 태그 일람**:

| 태그 | 출처 |
|------|------|
| `[API]` | Financial Datasets MCP |
| `[FMP]` | FMP MCP (애널리스트 데이터) |
| `[DART]` | 한국 DART 공시 |
| `[네이버]` | 네이버금융 |
| `[Web]` | 웹 검색 결과 |
| `[Calculated]` | 태그된 입력값으로 계산 |
| `[KR-Web]` | 한국 금융 포털 (FnGuide 등) |

---

## Enhanced Mode vs Standard Mode

| 항목 | Enhanced Mode | Standard Mode |
|------|--------------|---------------|
| 필요 조건 | Financial Datasets MCP API 키 | 추가 설정 없음 |
| 데이터 출처 | 구조화된 API (8분기 재무제표) | 웹 검색 + 스크래핑 |
| 최대 신뢰도 등급 | Grade A | Grade B |
| 과거 주가 차트 | ✓ (Chart.js) | ✗ (텍스트 표로 대체) |
| 애널리스트 추정치 | ✓ (구조화) | ✓ (웹 수집) |
| 한국 주식 | 항상 Standard Mode | Standard Mode |
| 비용 | 분석당 약 $0.05–$0.28 | 무료 |

---

## R/R Score (위험보상비율)

시나리오 분석을 하나의 숫자로 요약합니다.

```
R/R Score = (강세 수익률% × 강세 확률 + 기본 수익률% × 기본 확률)
            ──────────────────────────────────────────────────────
                         |약세 수익률% × 약세 확률|
```

| R/R Score | 신호 | 일반적 투자의견 |
|-----------|------|---------------|
| 3.0 초과 | 매력적 | 비중확대 |
| 1.0 – 3.0 | 중립 | 중립 / 관찰 |
| 1.0 미만 | 비매력적 | 비중축소 |

---

## 프로젝트 구조

```
stock-analysis-agent/
├── CLAUDE.md                    ← 마스터 오케스트레이터 (Claude가 자동으로 읽음)
├── README.md                    ← 영어 README
├── README.ko.md                 ← 이 파일
├── .gitignore
├── references/                  ← 분석 프레임워크 (Mode B/C/D)
├── docs/
│   ├── mcp-setup-guide.md       ← MCP 설정 가이드 (영어)
│   └── mcp-setup-guide.ko.md   ← MCP 설정 가이드 (한국어)
├── output/                      ← 생성 파일 (gitignore 처리)
│   ├── watchlist.json
│   ├── portfolio.json
│   ├── catalyst-calendar.json
│   ├── reports/
│   └── data/
└── .claude/
    ├── skills/                  ← SKILL.md 10개 (단계별 상세 지침)
    └── agents/                  ← AGENT.md 3개 (analyst, critic, data-researcher)
```

---

## 면책 조항

**이 도구는 오직 정보 제공 목적으로만 제공됩니다. 투자 조언, 증권 매수·매도 권유, 또는 투자 수익 보장이 아닙니다.**

- 모든 분석은 AI가 생성하며 오류나 누락이 있을 수 있습니다
- 과거 실적 데이터가 미래 결과를 보장하지 않습니다
- 투자 결정 전 반드시 자체 실사(due diligence)를 수행하세요
- 개인화된 투자 조언은 공인 재무 전문가와 상담하세요
- 시장 데이터는 지연될 수 있으므로, 시간에 민감한 정보는 1차 출처에서 확인하세요

할루시네이션 방지 시스템(Grade D → "—")은 데이터 오류 위험을 줄이지만 완전히 제거하지는 못합니다. 실제 투자 결정 전 모든 출력을 독립적으로 검증하세요.

---

## 라이선스 및 이용

개인 리서치용 도구입니다. 직접 활용하거나 수정하실 경우:
- 할루시네이션 방지 장치를 그대로 유지하세요
- 생성된 출력물에서 면책 조항을 제거하지 마세요
- 투자 결정 전 데이터 신뢰도 등급을 반드시 확인하세요
