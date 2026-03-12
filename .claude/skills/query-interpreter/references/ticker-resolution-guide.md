# Ticker Resolution Guide

This file is read by `query-interpreter/SKILL.md` during Step 1 to help resolve tickers from natural language queries.

---

## US Ticker Detection Rules

| Pattern | Example | Interpretation |
|---------|---------|----------------|
| 1–5 uppercase alpha characters | AAPL, MSFT, NVDA, TSLA, META | Direct US ticker |
| Company name in English | "Apple", "Microsoft", "Nvidia" | Resolve to ticker via web search |
| "$TICKER" format | $AAPL | US ticker (strip $) |
| Full company name | "Apple Inc", "NVIDIA Corporation" | Resolve to canonical ticker |

**Ambiguous US tickers** (multiple companies, same letters):
- AI → C3.ai (AI) vs general query — ask user
- APPS → Digital Turbine (APPS) — confirm
- META → Meta Platforms (META, not Metaverse ETF)
- GM → General Motors (GM) vs GameMaker abbreviation — ask user if unclear

**Resolution method (Standard Mode)**: Web search `{company name} stock ticker NYSE NASDAQ`

---

## Korean Stock Detection Rules

| Pattern | Example | Interpretation |
|---------|---------|----------------|
| 6-digit numeric string | 005930, 000660 | KR ticker directly |
| Korean company name | 삼성전자, SK하이닉스 | Resolve to 6-digit code |
| "코스피", "코스닥" in query | "코스피 삼성전자" | KR market |
| Korean characters in company name | 현대차, 카카오, 네이버 | KR market |
| English name of Korean company | "Samsung Electronics", "Hyundai" | KR market |

**Common Korean stock codes** (quick reference):

| Company | Korean Name | Code | Market |
|---------|------------|------|--------|
| Samsung Electronics | 삼성전자 | 005930 | KOSPI |
| SK Hynix | SK하이닉스 | 000660 | KOSPI |
| NAVER | NAVER | 035420 | KOSPI |
| Kakao | 카카오 | 035720 | KOSPI |
| LG Energy Solution | LG에너지솔루션 | 373220 | KOSPI |
| Hyundai Motor | 현대차 | 005380 | KOSPI |
| Kia | 기아 | 000270 | KOSPI |
| Samsung Biologics | 삼성바이오로직스 | 207940 | KOSPI |
| Celltrion | 셀트리온 | 068270 | KOSPI |
| POSCO Holdings | POSCO홀딩스 | 005490 | KOSPI |
| KB Financial | KB금융 | 105560 | KOSPI |
| Kakao Bank | 카카오뱅크 | 323410 | KOSPI |
| Krafton | 크래프톤 | 259960 | KOSPI |
| Kakao Games | 카카오게임즈 | 293490 | KOSDAQ |
| Hugel | 휴젤 | 145020 | KOSDAQ |

**Resolution method for unknown KR companies**: Web search `{company name} 종목코드` or `{company name} 주식 코스피 코스닥`

---

## Market Detection Logic

```
Step 1: Does query contain 6-digit numeric? → KR market
Step 2: Does query contain Korean characters (한글)? → KR market (resolve to code)
Step 3: Is ticker 1-5 uppercase alpha? → US market
Step 4: Is company name clearly Korean (Samsung, Hyundai, Kakao, etc.)? → KR market
Step 5: Is company name clearly US-listed? → US market
Step 6: Ambiguous? → Ask user: "US or Korean market?" (max 1 clarification)
```

---

## Multi-Ticker Query Detection

| Pattern | Example | Action |
|---------|---------|--------|
| "A vs B" | "AAPL vs MSFT" | Workflow 2 (Peer Comparison) |
| "A and B" | "AAPL and NVDA" | Workflow 2 |
| Comma-separated list | "AAPL, MSFT, GOOGL" | Workflow 2 |
| "비교해줘" with names | "삼성전자, LG전자 비교" | Workflow 2 |
| Portfolio keywords | "내 포트폴리오", "내 주식들" | Workflow 3 |
| Watchlist keywords | "워치리스트", "관심종목" | Workflow 3 |

---

## Mode Auto-Selection Rules

| Query Signal | Mode Selected | Examples |
|-------------|--------------|---------|
| Price/fact only keywords | Mode 0 (Price Check) | "얼마야", "지금 가격", "시총이", "what's the price", "current price", "market cap" |
| Quick/brief request | Mode A | "간단히", "빠르게", "요약", "quick", "brief", "summary" |
| Comparison request | Mode B | "vs", "비교", "compare", "peer" |
| Analysis request (default) | Mode C | "분석해줘", "분석", "analyze", "dashboard", "deep dive" |
| Memo/report request | Mode D | "메모", "리포트", "보고서", "투자 메모", "investment memo", "report" |
| Ambiguous | Ask user with ≤2 options | e.g., "간략하게 볼까요(A) 아니면 심층 분석(C)?" |

**Default when unclear**: Mode C (Deep Dive Dashboard) — better to over-deliver than under-deliver on analysis.

---

## Clarification Protocol

If unable to determine ticker or market:
1. Ask ONE clear question: "어떤 회사/티커를 분석할까요?" or "US or Korean market?"
2. Maximum 3 clarification exchanges total per session
3. If user says "알아서 해줘" (do whatever): Apply most reasonable interpretation, state assumptions explicitly: "AAPL (US, NASDAQ) 분석을 진행합니다. Mode C (심층 분석) 기준으로 진행할게요."
4. Never refuse due to ambiguity — make a best-effort interpretation and state it
