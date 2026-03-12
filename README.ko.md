# 📊 주식 분석 에이전트

> **Language / 언어**: [English](README.md) | 한국어

**기관급 주식 리서치를, 몇 분 안에.**
Claude Code + [Financial Datasets API](https://financialdatasets.ai) 기반 — SEC 공시·DART 직접 수집, 8분기 검증 재무 데이터, 임의 숫자 생성 없음.

---

## 이게 뭘 해주는 건가요?

티커 하나 입력하면, 바이사이드 애널리스트가 쓰는 수준의 리서치가 나옵니다:

- **시나리오 분석** — 강세/기본/약세, 확률 가중 R/R Score
- **차별적 관점 (Variant View)** — 시장이 틀린 이유, 구체적 근거로 (제네릭 분석 금지)
- **정밀 리스크 분석** — 모든 리스크에 인과 체인 필수: 이벤트 → P&L 임팩트 → 주가 효과
- **출처 태그 데이터** — 모든 수치가 출처를 가짐. 임의 생성 없음.
- **한국 주식 완전 지원** — DART 공시, 네이버금융, FnGuide 데이터 체인

> **핵심 원칙**: 빈칸 > 틀린 숫자. 검증할 수 없는 수치는 "—"으로 표시하고, 절대 임의로 생성하지 않습니다.

---

## 3가지 출력 모드

### 📈 Mode C — 심층 대시보드 *(기본값)*
**HTML 파일** — 브라우저에서 바로 열기. 빠른 의사결정용으로 최적화.

```
┌─────────────────────────────────────────────────────────────┐
│  삼성전자 (005930)         ₩75,400  ▲ +1.8%               │
│  데이터 신뢰도: ████████░░ Grade B  |  Standard Mode        │
├──────────────┬──────────────┬──────────────────────────────┤
│  🐂 강세     │  📊 기본     │  🐻 약세                     │
│  ₩90,000     │  ₩82,000     │  ₩58,000                    │
│  +19.4%      │  +8.8%       │  -23.1%                      │
│  확률: 25%   │  확률: 55%   │  확률: 20%                   │
├──────────────┴──────────────┴──────────────────────────────┤
│  R/R Score: 2.8  →  🟡 중립  |  투자의견: 중립             │
├─────────────────────────────────────────────────────────────┤
│  KPI: P/B · ROE · 배당수익률 · 영업이익률 · 매출성장률 ··  │
│  차별적 관점 Q1–Q3 · 리스크 테이블 · 동종업계 비교         │
│  분기 실적 테이블 · 이익의 질 요약 · 포트폴리오 전략       │
└─────────────────────────────────────────────────────────────┘
```

### 📝 Mode D — 투자 메모 *(DOCX)*
**Word 문서** — 3,000단어 이상, 10개 구조화 섹션. Goldman Sachs 에쿼티 리서치 노트 스타일.

| 섹션 | 내용 |
|------|------|
| 개요 | 1문장 투자 논거 · 투자의견 · R/R Score |
| 사업 개요 | 매출 구조 · 시장점유율 · TAM |
| 재무 성과 | 8분기 테이블 · 마진 추이 · FCF |
| 밸류에이션 | P/E · EV/EBITDA · SOTP 분해 |
| **5가지 차별적 관점** | 시장이 틀린 이유 (가장 중요한 섹션) |
| 정밀 리스크 분석 | 3가지 리스크 × 완전 인과 체인 + EBITDA 임팩트 |
| 투자 시나리오 | 강세/기본/약세 · R/R 공식 표시 |
| 동종업계 비교 | 5개 지표 × 3–5개 피어사 테이블 |
| 경영진 & 지배구조 | CEO 실적 · 자본 배분 이력 |
| 이익의 질 | EBITDA 브릿지 · FCF 전환율 · SBC 차감 |
| 내가 틀릴 경우 | 핵심 가정 3가지 · 프리모텀 단락 |
| 부록 | 데이터 출처 · 신뢰도 등급 · 제외 항목 |

### ⚖️ Mode B — 동종 비교 *(HTML)*
**나란히 비교 매트릭스** — 2~5개 종목 비교. R/R Score 순위, 최선호 종목, 핵심 차이점 제시.

---

## 왜 Financial Datasets API인가?

> **강력히 권장합니다.** 이것이 일반 LLM 주식 분석과 이 에이전트를 구분하는 핵심입니다.

[financialdatasets.ai](https://financialdatasets.ai)에 연동하면, 에이전트가 다음을 직접 수집합니다:

| 데이터 | 수집 방법 | 신뢰도 |
|--------|----------|--------|
| 실시간 주가 | `get_current_stock_price` | Grade A |
| 손익계산서 8분기 | `get_income_statements` | Grade A |
| 재무상태표 8분기 | `get_balance_sheets` | Grade A |
| 현금흐름표 8분기 | `get_cash_flow_statements` | Grade A |
| 애널리스트 목표주가 | FMP MCP | Grade B |
| 내부자 거래 | `get_insider_transactions` | Grade A |
| SEC 공시 (10-K, 10-Q) | `get_sec_filings` | Grade A |

**연동 없이도:** 웹 리서치 + 다중 출처 교차검증으로 완전히 동작합니다. 다만 최대 데이터 신뢰도가 Grade A → Grade B로 낮아집니다.

**연동하면:** SEC 공시 직접 수집. 10-K와 일치하는 숫자. 모호함 없음.

```
💡 설정은 5분이면 됩니다. → docs/mcp-setup-guide.ko.md 참고
```

---

## 데이터 신뢰도 체계

출력의 모든 수치에 등급과 출처 태그가 붙습니다. 무엇을 신뢰해야 하는지 항상 알 수 있습니다.

| 등급 | 태그 | 의미 | 상황 |
|------|------|------|------|
| **A** | *(없음)* | 1차 출처 검증 + 산술 일관성 확인 | SEC/DART 직접 수집 |
| **B** | `[≈]` | 2개 이상 출처 교차검증, 5% 이내 | 웹 교차검증 |
| **C** | `[1S]` | 단일 출처, 미검증 | 웹 단일 출처 |
| **D** | `—` | 검증 불가 → **빈칸으로 표시** | 절대 임의 생성 안 함 |

```
출력 예시:
  매출 TTM: ₩302.2조 [DART]        ← Grade A, DART 공시 직접 수집
  P/B 비율: 1.8x [Calculated]      ← Grade A 입력값으로 계산
  EV/EBITDA: —                     ← Grade D, 제외 (EBITDA 검증 불가)
```

---

## 사용 방법

### 단일 종목 분석

```
삼성전자 분석해줘
NVDA 심층 분석
005930 투자 메모 써줘
TSLA investment memo
LG에너지솔루션 분석해줘
```

### 동종 비교

```
삼성전자 vs SK하이닉스 비교
NVDA vs AMD vs INTC
AAPL vs MSFT vs GOOGL
삼성전자, LG전자, SK하이닉스 비교해줘
```

### 포트폴리오 & 워치리스트

```
AAPL 워치리스트 추가
삼성전자 워치리스트 추가
워치리스트 스캔해줘
포트폴리오 분석해줘
카탈리스트 캘린더 보여줘
NVDA 지난번 분석이랑 비교해줘
```

### 단순 가격 질문

이 에이전트는 단순 가격 조회는 지원하지 않습니다. 빠른 가격 확인은 네이버금융 또는 Yahoo Finance를 이용하세요.
"삼성전자 분석해줘"처럼 요청하면 전체 심층 분석을 받을 수 있습니다.

---

## R/R Score — 위험보상비율, 하나의 숫자로

모든 분석이 시나리오 가중 업사이드 대 다운사이드를 하나의 점수로 요약합니다.

```
R/R Score = (강세 수익률% × 강세 확률 + 기본 수익률% × 기본 확률)
            ──────────────────────────────────────────────────────
                         |약세 수익률% × 약세 확률|
```

**예시**: 강세 +25% × 30% + 기본 +12% × 50% = 업사이드 가중치 13.5
          약세 -25% × 20% = 다운사이드 가중치 5.0
          **R/R Score = 13.5 / 5.0 = 2.7 → 🟡 중립**

| 점수 | 신호 | 일반적 투자의견 |
|------|------|---------------|
| **3.0 초과** | 🟢 매력적 | 비중확대 |
| **1.0 – 3.0** | 🟡 중립 | 중립 / 관찰 |
| **1.0 미만** | 🔴 비매력적 | 비중축소 |

---

## 빠른 시작

### 사전 준비

```bash
# 1. Claude Code 설치
npm install -g @anthropic-ai/claude-code

# 2. Mode D (Word 문서 출력)용 Python 라이브러리
pip install python-docx

# 3. 저장소 복제
git clone https://github.com/your-username/stock-analysis-agent.git
cd stock-analysis-agent
```

### (강력 권장) Financial Datasets API 연동

```bash
# MCP 등록 — 5분이면 완료, 데이터 품질이 크게 달라집니다
claude mcp add --transport http financial-datasets https://mcp.financialdatasets.ai/ \
  --header "X-API-KEY: 여기에_API_키_입력"
```

API 키 발급: [financialdatasets.ai](https://financialdatasets.ai)
전체 설정 가이드: [docs/mcp-setup-guide.ko.md](docs/mcp-setup-guide.ko.md)

### 실행

```bash
claude
```

Claude Code가 시작 시 `CLAUDE.md`를 자동으로 읽습니다:

```
=== Stock Analysis Agent ===
Data Mode: Enhanced (MCP active)   ← SEC 공시 Grade A 데이터 연동됨
Date: 2026-03-12
Ready. Send a ticker or question to begin.
```

---

## 출력 파일

모든 생성 파일은 `output/` 아래에 저장됩니다 (gitignore 처리):

| 파일 | 모드 | 열기 |
|------|------|------|
| `output/reports/{ticker}_C_*.html` | C — 대시보드 | 브라우저 |
| `output/reports/{ticker}_D_*.docx` | D — 투자 메모 | Word / Google Docs / LibreOffice |
| `output/reports/{tickers}_B_*.html` | B — 동종 비교 | 브라우저 |
| `output/data/{ticker}/latest.json` | — | 델타 분석용 스냅샷 |
| `output/watchlist.json` | — | 워치리스트 |
| `output/catalyst-calendar.json` | — | 카탈리스트 캘린더 |

---

## Enhanced vs Standard Mode

| | Enhanced Mode 🟢 | Standard Mode 🟡 |
|-|-----------------|-----------------|
| **필요 조건** | Financial Datasets API 키 | 추가 설정 없음 |
| **데이터 출처** | SEC 공시 구조화 API | 웹 검색 + 스크래핑 |
| **주가 데이터** | 실시간, Grade A | 웹 수집, Grade B |
| **재무 데이터** | 8분기, 기계 판독 가능 | 웹 스크랩, 변동 가능 |
| **최대 신뢰도** | **Grade A** | Grade B |
| **차트** | 과거 주가 (Chart.js) | 텍스트 테이블 대체 |
| **한국 주식** | 항상 Standard Mode | Standard Mode |
| **비용** | 분석당 약 $0.05–$0.28 | 무료 |

---

## 한국 주식 지원

KOSPI / KOSDAQ 종목 완전 지원 — 이제 **DART OpenAPI 연동으로 Grade A 데이터** 제공.

| 모드 | 재무 데이터 출처 | 최대 신뢰도 |
|------|----------------|-----------|
| 🟢 DART-Enhanced | DART OpenAPI (구조화 재무제표, 미국 SEC EDGAR와 동급) | **Grade A** |
| 🟡 Standard | 웹 수집 (DART 웹사이트, 네이버금융) | Grade B |

- **DART OpenAPI** — 금융감독원에서 직접 구조화 재무제표 수집 (무료, API 키 필요)
- **네이버금융** — 실시간 주가, PER/PBR, 외국인 지분율 (항상 시장 데이터로 사용)
- **FnGuide / KIND** — 애널리스트 컨센서스, 수급 데이터
- **한국어 출력** — 한국어로 요청하면 한국어로 분석 생성
- **한국 시장 오버레이** — 외국인 지분율, 밸류업 프로그램, 자사주 소각 정책

```bash
# DART-Enhanced 활성화: opendart.fss.or.kr에서 무료 API 키 발급
# .claude/settings.local.json → env → DART_API_KEY에 입력
```

```
삼성전자 심층 분석해줘  →  한국어 Mode C 대시보드 생성 (Grade A 데이터)
SK하이닉스 투자 메모    →  한국어 Mode D DOCX 생성
```

---

## 프로젝트 구조

```
stock-analysis-agent/
├── CLAUDE.md                    ← 마스터 오케스트레이터 (시작 시 자동 로드)
├── references/                  ← 각 모드별 분석 프레임워크
│   ├── analysis-framework-comparison.md
│   ├── analysis-framework-dashboard.md
│   └── analysis-framework-memo.md
├── docs/
│   ├── mcp-setup-guide.md       ← Financial Datasets API 설정 (영어)
│   └── mcp-setup-guide.ko.md   ← Financial Datasets API 설정 (한국어)
├── output/                      ← 생성 파일 (gitignore 처리)
│   ├── reports/                 ← HTML / DOCX 분석 결과
│   └── data/                    ← 종목별 원시 데이터 + 스냅샷
└── .claude/
    ├── skills/                  ← SKILL.md 10개 (단계별 파이프라인)
    └── agents/                  ← analyst · critic · data-researcher
```

---

## 면책 조항

**이 도구는 오직 정보 제공 목적으로만 제공됩니다. 투자 조언, 증권 매수·매도 권유, 또는 투자 수익 보장이 아닙니다.**

- 모든 분석은 AI가 생성하며 오류나 누락이 있을 수 있습니다
- 시간에 민감한 데이터는 행동 전 1차 출처에서 반드시 확인하세요
- 과거 실적 데이터가 미래 결과를 보장하지 않습니다
- 투자 결정 전 반드시 공인 재무 전문가와 상담하세요

할루시네이션 방지 시스템(Grade D → "—")은 데이터 오류 위험을 줄이지만 완전히 제거하지는 못합니다. 실제 투자 결정 전 모든 출력을 독립적으로 검증하세요.
