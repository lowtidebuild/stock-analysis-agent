# MCP 설정 가이드

> **Language**: [English](mcp-setup-guide.md) | 한국어

이 가이드는 Enhanced Mode 분석을 위한 MCP(Model Context Protocol) 서버 설정 방법을 설명합니다.

---

## Enhanced Mode란?

Enhanced Mode는 두 가지 MCP 서버를 통해 구조화된 금융 데이터를 수집합니다:

1. **Financial Datasets MCP** — 실시간 주가, 8분기 재무제표, 애널리스트 추정치, 내부자 거래, SEC 공시
2. **FMP MCP (선택)** — 애널리스트 목표주가, 투자의견 분포, 등급 변경 이력

MCP 없이도 **Standard Mode**(yfinance + 필요한 웹 검색)로 완전히 동작합니다. 차이는 데이터 신뢰도 등급뿐입니다(MCP 사용 시 최대 Grade A, 미사용 시 최대 Grade B).

**한국 주식은 MCP 설정 여부와 관계없이 항상 Standard Mode**로 동작합니다. Financial Datasets MCP가 KRX를 지원하지 않기 때문입니다.

---

## 0단계 — python-docx 설치 (Mode D DOCX 출력에 필요)

Mode D 투자 메모는 Word 문서(.docx)로 생성됩니다. 필요한 라이브러리를 설치하세요:

```bash
pip install python-docx
```

설치 확인: `python -c "from docx import Document; print('OK')"`

---

## 1단계 — Financial Datasets MCP 등록

Financial Datasets MCP는 **호스팅된 HTTP 서버**입니다 — npm 패키지 설치가 필요 없습니다.

### Claude Code에 등록 (최초 1회, 사용자 레벨)

```bash
claude mcp add --transport http financial-datasets https://mcp.financialdatasets.ai/ --header "X-API-KEY: 여기에_API_키_입력"
```

`여기에_API_키_입력`을 실제 API 키로 교체하세요 (2단계에서 발급).

등록 확인:

```bash
claude mcp list
```

`financial-datasets`가 목록에 표시되면 정상입니다.

### FMP MCP (선택 — 구조화된 애널리스트 데이터용)

FMP MCP도 호스팅 서비스입니다. FMP에서 MCP 엔드포인트를 문의하거나, 이 단계를 건너뛰세요 — 애널리스트 데이터는 웹 검색으로 대체됩니다.

---

## 2단계 — API 키 발급

### Financial Datasets API 키

1. [https://financialdatasets.ai](https://financialdatasets.ai) 접속
2. 계정 생성 후 플랜 구독
3. 대시보드에서 API 키 복사

**예상 비용**:
| 분석 유형 | 예상 비용 |
|----------|---------|
| 단일 종목 — 전체 번들 (Mode C/D) | 약 $0.28/회 |
| 단일 종목 — 최소 번들 (Mode A/B) | 약 $0.05/회 |
| 동종 비교 — 3개 종목, 전체 번들 | 약 $0.84/회 |
| 워치리스트 스캔 — 10개 종목, 주가만 | 약 $0.10/회 |

### FMP (Financial Modeling Prep) API 키 (선택)

1. [https://financialmodelingprep.com](https://financialmodelingprep.com) 접속
2. 계정 생성 (무료 티어 사용 가능)
3. 대시보드에서 API 키 복사

FMP 추가 비용: 분석당 약 $0.01–$0.03 추가

---

## 3단계 — API 키로 MCP 재등록

Financial Datasets API 키를 발급받은 후, 키를 포함해서 재등록합니다:

```bash
claude mcp remove financial-datasets
claude mcp add --transport http financial-datasets https://mcp.financialdatasets.ai/ --header "X-API-KEY: 여기에_API_키_입력"
```

설정은 `~/.claude.json`(사용자 레벨 — 모든 프로젝트에 적용)에 저장됩니다.

**프로젝트별 설정을 원하는 경우** (프로젝트 디렉토리에서):

```bash
claude mcp add --transport http financial-datasets https://mcp.financialdatasets.ai/ --header "X-API-KEY: 여기에_API_키_입력" --scope project
```

이 경우 `.claude/settings.local.json`(프로젝트별, gitignore 처리 권장)에 저장됩니다.

> **보안 주의**: API 키를 채팅창에 입력하지 마세요. 실수로 공개된 경우 즉시 재발급하세요.

---

## 4단계 — 설정 확인

Claude Code에서 새 세션을 시작하면 에이전트가 자동으로 MCP 가용성을 테스트합니다:

```
테스트 호출: get_current_stock_price("AAPL")
→ 가격 반환 시: DATA_MODE = "enhanced" ✓
→ 오류 발생 시: DATA_MODE = "standard" (MCP 미설정 또는 API 키 문제)
```

세션 상태 블록에서 다음을 확인하세요:
```
=== Stock Analysis Agent ===
Data Mode: Enhanced (MCP active) ✓
```

MCP가 연결되었다면 `Enhanced (MCP active)`가, 연결 실패 시 `Standard (yfinance + Web)`가 표시됩니다.

---

## 문제 해결

### "Standard (yfinance + Web)"가 표시됨 (MCP 설정 후에도)

1. `claude mcp list` 실행하여 `financial-datasets`가 등록되었는지 확인
2. API 키가 올바르게 입력되었는지 확인 (앞뒤 공백 없는지)
3. Claude Code 재시작 후 다시 시도

### API 호출 오류

- API 키가 활성 상태이고 크레딧이 충분한지 확인
- 해당 종목이 미국 주식인지 확인 (Financial Datasets MCP는 미국 주식만 지원)
- 한국 주식은 항상 Standard Mode — 이것은 정상 동작입니다

### python-docx 없음 (Mode D 실패)

- 설치: `pip install python-docx`
- 확인: `python -c "from docx import Document; print('OK')"`

### Python 스크립트 오류

- Python 버전 확인: `python --version` (3.8 이상 필요)
- 한국어/특수문자 인코딩 설정:
  ```bash
  # Windows
  set PYTHONUTF8=1
  # macOS/Linux
  export PYTHONUTF8=1
  ```
- 스크립트 위치: `.claude/skills/data-validator/scripts/`, `.claude/skills/data-manager/scripts/`, `.claude/skills/output-generator/scripts/`

---

## MCP 없이 사용 (Standard Mode)

MCP 서버를 설정하지 않아도 에이전트는 완전히 동작합니다:

- Mode A, B, C, D 모든 분석 출력 가능
- 데이터 신뢰도 등급 최대 Grade B (MCP 사용 시 Grade A)
- 미국 주식은 먼저 yfinance로 주가, 기본 밸류에이션, 재무제표를 수집하고 부족한 필드와 정성 맥락만 웹 검색으로 보완
- 출처 태그: `[Portal]` (Grade B) 또는 단일 출처 (Grade C) (MCP 사용 시 `[Filing]`)
- 한국 주식: 동일하게 Standard Mode

대부분의 개인 투자 리서치에 Standard Mode로 충분합니다. Enhanced Mode는 더 빠른 수집 속도와 더 높은 데이터 신뢰도를 제공합니다.

---

## 자주 묻는 질문

**Q. 한국 주식도 MCP로 분석할 수 있나요?**

아니요. Financial Datasets MCP는 미국 주식(NYSE/NASDAQ/AMEX)만 지원합니다. 한국 주식은 MCP 설정 여부와 관계없이 항상 DART → 네이버금융 → FnGuide 웹 수집 방식으로 분석됩니다.

**Q. FMP MCP는 꼭 필요한가요?**

선택 사항입니다. FMP MCP가 없으면 애널리스트 목표주가와 투자의견 데이터를 웹 검색으로 수집합니다(TipRanks, MarketBeat 등). 구조화된 데이터보다 신뢰도가 약간 낮지만 분석에 지장은 없습니다.

**Q. API 비용이 얼마나 드나요?**

분석 빈도에 따라 다릅니다. 주 2~3회 심층 분석 기준으로 월 $5~20 수준입니다. Financial Datasets MCP 웹사이트에서 최신 요금을 확인하세요.

**Q. API 키를 안전하게 보관하는 방법은?**

`.claude/settings.local.json`을 `.gitignore`에 추가하거나, 환경 변수 방식을 사용하세요. API 키가 담긴 파일은 절대 공개 저장소에 커밋하지 마세요.
