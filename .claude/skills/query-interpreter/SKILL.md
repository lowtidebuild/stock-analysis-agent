# Query Interpreter — SKILL.md

**Role**: Step 1 — Parse the user's query to extract ticker(s), determine output mode, detect language, and validate intent.
**Triggered by**: CLAUDE.md after Step 0 determines fresh collection needed
**Reads**: User query, `references/ticker-resolution-guide.md`
**Writes**: Sets session variables: ticker, market, output_mode, output_language, peers (if multi-ticker)
**References**: `ticker-resolution-guide.md`

---

## Instructions

### Step 1.1 — Detect Analysis Intent

First, determine if this is an **analysis request** or a **price-only query** (not supported).

**Price-only queries** (not supported — respond with guidance):
- "X 지금 얼마야?" / "X current price?" / "What is X trading at?"
- "X 시총이 얼마야?" / "X market cap?"
- "X 52주 최고가?" / "X 52-week high?"
- Any query asking for a single data point without analysis context

```
IF price-only query detected:
    → Respond: "가격 조회는 지원하지 않습니다. Yahoo Finance / Perplexity에서 확인하시거나,
                '{ticker} 분석해줘'로 심층 분석을 요청하세요."
    → Do not proceed further
```

**Analysis triggers** (full analysis — proceed with workflow):
- "X 분석해줘" / "Analyze X"
- "X 어때?" / "What do you think about X?"
- "X 투자할 만해?" / "Is X worth investing in?"
- Any query implying an investment recommendation or thesis

### Step 1.2 — Detect Multi-Ticker Query

Check for comparison/peer analysis indicators:

**Multi-ticker triggers**: `vs`, `versus`, `비교`, `and`, `compare`, `대`, `와`, comma-separated tickers

Examples:
- "AAPL vs MSFT" → 2 tickers, Workflow 2
- "AAPL, MSFT, GOOGL 비교" → 3 tickers, Workflow 2
- "삼성전자 vs SK하이닉스" → 2 Korean tickers, Workflow 2

```
IF multi-ticker:
    → Set workflow = 2
    → Extract all tickers (deduplicated, max 5)
    → Set output_mode = "B" (default for Workflow 2) unless user specifies differently
```

### Step 1.3 — Ticker Resolution

**US tickers** (1–5 uppercase letters):
- Direct: AAPL, MSFT, NVDA, TSLA
- Case-insensitive: "aapl" → "AAPL"
- With exchange suffix: "AAPL:NASDAQ" → "AAPL"

**Korean tickers** (6-digit numeric):
- Direct: 005930, 000660
- Korean company name → map to 6-digit code using `ticker-resolution-guide.md`
- If name not in reference table: search `"{company name}" 종목코드 site:finance.naver.com`

**Ambiguous cases**:
1. If ticker could be US or Korean: ask user to clarify market
2. If Korean company name not resolved: attempt web search, then ask if still unresolved
3. If US ticker returns no data: suggest similar tickers

**Clarification protocol** (max 3 questions total, then proceed with best guess):

Question format:
```
"{ticker}를 분석하시려는 건가요? 확인해드리기 위해 몇 가지 확인이 필요합니다:
1. [clarification question]"
```

### Step 1.4 — Output Mode Selection

Apply this decision table:

| User Signal | Output Mode |
|------------|-------------|
| "비교" / "vs" / "compare" (multi-ticker) | B |
| "심층" / "자세히" / "deep dive" / "detailed" / "full" | C |
| "투자 메모" / "memo" / "investment memo" / "리포트" | D |
| No explicit mode signal, single ticker | C (default) |
| No explicit mode signal, multi-ticker | B (default) |
| Portfolio review | C per stock (abbreviated) |
| Watchlist scan | A per stock (abbreviated) |

**Mode confirmation** (optional, for Mode C and D):
If Enhanced Mode is available and mode is C or D, briefly note:
`"[{ticker}] 심층 분석 (Mode C/D) 진행합니다. API 데이터 + 웹 리서치를 결합합니다."`

### Step 1.5 — Output Language Detection

| Condition | Language |
|-----------|----------|
| Query in Korean | Korean (ko) |
| Query in English | English (en) |
| Mixed or ambiguous | Detect by majority language |
| Korean stock (KR market) | Korean preferred, English accepted |
| US stock | English preferred, Korean accepted |

Language affects: all output text, section headers, verdict translations, price formatting (₩ vs $).

### Step 1.6 — Company Type Pre-detection

Attempt to identify company type early (for metric selection in later steps):

| Indicator | Type |
|-----------|------|
| Bank / 은행 / Insurance | Financial |
| Pharma / Biotech / biopharma / 제약 / 바이오 | Biotech/Pharma |
| REIT / 리츠 | Financial (REIT) |
| Manufacturing / 제조 / Industrial / 산업 | Industrial |
| Consumer / Retail / 유통 / 소비 | Consumer |
| Tech / Software / Platform | Technology/Platform |
| Energy / Oil / Gas / 에너지 / 정유 | Energy |

This is a preliminary assessment; `market-router/SKILL.md` will confirm via API in Step 2.

### Step 1.7 — Set Session State

Output session state block:

```
=== Query Interpretation ===
Ticker(s): {list}
Market(s): {US/KR}
Workflow: {1/2/3}
Output Mode: {B/C/D}
Output Language: {en/ko}
Company Type (pre-detected): {type or "unknown"}
Peer tickers: {list or none}
Delta mode: {yes/no}

→ Proceeding to Step 2 (Market Router)
```

---

## Completion Check

- [ ] Workflow determined (1/2/3)
- [ ] Ticker(s) resolved to canonical format (uppercase US, 6-digit KR)
- [ ] Market(s) identified (US/KR)
- [ ] Output mode selected
- [ ] Output language detected
- [ ] Company type pre-detected (or marked unknown)
- [ ] Session state block written
