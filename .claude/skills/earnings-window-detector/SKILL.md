# Earnings Window Detector — SKILL.md

**Role**: Mode E 진입 자동 감지 — 티커 + 오늘 날짜로부터 실적 발표 윈도우 (preview / review / none) 분류.
**Triggered by**: CLAUDE.md Workflow 1 Step 0 직후 (Chunk 5에서 staleness-checker와 함께 호출). 또는 사용자가 `--earnings-mode preview|review` 강제 지정 시 검증 용도.
**Reads**: yfinance.Ticker(t).calendar (1차) → yfinance.Ticker(t).earnings_dates (2차).
**Writes**: `output/runs/{run_id}/earnings-window/{ticker}.json` per ticker.
**References**: `.claude/skills/earnings-window-detector/scripts/window-classifier.py`

---

## 목적 (Purpose)

Mode E (Earnings Preview/Review)는 실적 발표 D-7 ~ D+3 윈도우에서만 의미가 있다. 이 skill은 그 윈도우 안인지 밖인지를 결정해서 orchestrator의 모드 분기 결정을 돕는다. **Stateless** 분류기이며 캐시 레이어를 가지지 않는다 (orchestrator가 Mode E 재진입 시점에 1h TTL 정책을 처리).

---

## 호출 시점 (When to Invoke)

1. **Mode E 자동 감지** — Workflow 1 진입 시 staleness-checker 직후. `window != "none"`이면 Mode E 자동 제안 (Chunk 5에서 wiring).
2. **수동 검증** — 사용자가 `--earnings-mode preview|review`를 강제 지정한 경우, 실제 윈도우와 일치하는지 sanity-check 용도.
3. **워치리스트 스캔** — 워치리스트 전체를 스캔할 때 어떤 종목이 곧 실적 발표를 앞두고 있는지 식별 (멀티 티커 CLI).

호출하지 않는 경우:
- Mode A/B/C/D 명시적 요청 시 (단, Mode E 후보임을 알리는 informational 호출은 가능)
- 유럽/홍콩 티커 (yfinance 데이터 품질 낮음 — 향후 별도 source 필요)

---

## 입력 (Inputs)

### CLI

```bash
python .claude/skills/earnings-window-detector/scripts/window-classifier.py \
  --ticker GOOGL AAPL MSFT \
  --output-dir output/runs/{run_id}/earnings-window/ \
  --today-date 2026-05-07 \
  --timeout 30
```

| 인자 | 필수 | 기본값 | 설명 |
|------|-----|------|------|
| `--ticker` | ✅ | — | 1개 이상 ticker 심볼 (공백 구분) |
| `--output-dir` | ✅ | — | 출력 디렉토리 (per-ticker JSON 작성 위치) |
| `--today-date` | ❌ | UTC 오늘 | 분류 기준 날짜 (YYYY-MM-DD) — 테스트/재현 용도 |
| `--timeout` | ❌ | 30 | 티커당 yfinance 호출 timeout (초) |

### 프로그래매틱

```python
from window_classifier import classify_window, classify_windows

# 단일 티커
record = classify_window(ticker="GOOGL", today_date="2026-05-07", timeout=30)

# 멀티 티커 + 디스크 작성
results = classify_windows(
    tickers=["GOOGL", "AAPL"],
    output_dir="output/runs/RUN/earnings-window/",
    today_date="2026-05-07",
    timeout=30,
)
```

---

## 출력 스키마 (Output Schema)

```json
{
  "ticker": "GOOGL",
  "today_date": "2026-05-07",
  "next_earnings_date": "2026-07-29",
  "next_earnings_confirmed": true,
  "days_until": 83,
  "window": "none",
  "override_mode": null,
  "lookup_source": "yfinance.Ticker.calendar",
  "fallback_used": false,
  "_sanitization": {
    "tool": "tools/prompt_injection_filter.py",
    "version": "1",
    "timestamp": "2026-05-07T12:00:00Z",
    "redactions": 0,
    "findings": []
  }
}
```

| 필드 | 타입 | 의미 |
|-----|------|------|
| `ticker` | string | 대문자 ticker 심볼 |
| `today_date` | string (ISO date) | 분류 기준 날짜 |
| `next_earnings_date` | string (ISO date) \| null | 다음 실적 발표 예정일. 알 수 없으면 `null` |
| `next_earnings_confirmed` | bool | yfinance가 실제 날짜를 제공했는지 (false면 `window`는 항상 `"none"`) |
| `days_until` | int \| null | `(earnings_date - today_date).days`. 미확인이면 `null` |
| `window` | enum | `"preview"` / `"review"` / `"none"` |
| `override_mode` | null \| string | (Chunk 5 예약 필드 — orchestrator가 채움. 이 skill은 항상 `null`) |
| `lookup_source` | enum | `"yfinance.Ticker.calendar"` / `"yfinance.Ticker.earnings_dates"` / `"none"` |
| `fallback_used` | bool | 양쪽 yfinance 경로가 모두 실패해서 `"none"`으로 graceful degrade했는지 |
| `_sanitization` | object | CLAUDE.md §12 trust boundary 블록 (필수) |

### Window 분류 규칙

`days_until = (earnings_date - today_date).days`

| `days_until` | `window` |
|-------------|---------|
| `1` ~ `7` (D-7 ~ D-1, 미래) | `"preview"` |
| `-3` ~ `0` (D ~ D+3, 발표일 포함 ~ 3일 후) | `"review"` |
| 그 외 | `"none"` |

---

## Lookup 우선순위 (Fallback Chain)

1. **`yfinance.Ticker(ticker).calendar`** — dict-like, key `"Earnings Date"` (가장 최신 yfinance 형식). 즉시 사용 가능하면 `lookup_source="yfinance.Ticker.calendar"`.
2. **`yfinance.Ticker(ticker).earnings_dates`** — pandas DataFrame, `index`가 DatetimeIndex. `today` 이후의 가장 가까운 미래 날짜를 선택. 사용 시 `lookup_source="yfinance.Ticker.earnings_dates"`.
3. **양쪽 실패** — `next_earnings_date=null`, `next_earnings_confirmed=false`, `fallback_used=true`, `window="none"`. **절대 raise하지 않음**.

이 skill은 1.0에서는 web search fallback을 의도적으로 포함하지 않는다 (불확실성을 `next_earnings_confirmed=false`로 노출하는 편이 정확도가 높음).

---

## 에러 모드 (Error Modes)

| 상황 | 처리 |
|------|------|
| yfinance 미설치 | `fallback_used=true`, `window="none"`, `lookup_errors=["yfinance is not installed"]` |
| `Ticker(t).calendar` 예외 (network, parse) | calendar 결과 폐기 → earnings_dates 시도 |
| `Ticker(t).earnings_dates` 예외 | 양쪽 실패 처리 (위와 동일) |
| 30초 timeout | 강제 종료, 양쪽 실패 처리 |
| 빈 calendar dict (`{}`) | earnings_dates DataFrame로 fallback |
| 잘못된 `--today-date` 포맷 | argparse가 거부하지 않으나 strptime이 ValueError → caller에 전파 (CLI는 이 경우 stderr) |
| 잘못된 ticker 심볼 (yfinance가 빈 응답) | calendar/earnings_dates 모두 비어있을 → `window="none"`, `fallback_used=true` |

**핵심 규칙**: per-ticker 실패는 멀티 티커 batch를 abort하지 않는다. 각 티커는 독립.

---

## Trust Boundary (CLAUDE.md §12)

* yfinance가 반환하는 모든 string 필드는 `tools/prompt_injection_filter.py`의 `sanitize_record`를 통과한 후 디스크에 저장된다.
* 출력 JSON은 항상 `_sanitization` 블록을 포함한다 (`redactions`, `findings`, `tool`, `version`).
* downstream agent (Chunk 5의 analyst, critic, output-generator)는 `_sanitization` 블록이 없는 artifact를 읽으면 안 된다.

---

## 캐시 정책 (Cache Policy)

이 skill 자체는 **stateless** (캐시 레이어 없음). orchestrator가 다음과 같이 처리:

* **권장 TTL**: 1시간 — 실적 일정은 회사가 발표한 후 자주 바뀌지 않음
* **재실행 조건**: Mode E 진입 시마다 (orchestrator가 1h 이내 stale check)
* **스토리지 키**: `output/runs/{run_id}/earnings-window/{ticker}.json`

OD-F1에 따라 Mode E 자체 진입 시에는 **항상 fresh fetch** (snapshot 무시) — 단 윈도우 분류기 결과는 1h 동안 reuse 가능. 두 정책이 모순되지 않는 이유는 분류기 출력은 발표일이지 실제 financial data가 아니기 때문.

---

## 출력 예시 (Examples)

### Preview (D-3, GOOGL)

```json
{
  "ticker": "GOOGL",
  "today_date": "2026-05-07",
  "next_earnings_date": "2026-05-10",
  "next_earnings_confirmed": true,
  "days_until": 3,
  "window": "preview",
  "override_mode": null,
  "lookup_source": "yfinance.Ticker.calendar",
  "fallback_used": false,
  "_sanitization": {...}
}
```

### Review (D+1, NVDA)

```json
{
  "ticker": "NVDA",
  "today_date": "2026-05-07",
  "next_earnings_date": "2026-05-06",
  "next_earnings_confirmed": true,
  "days_until": -1,
  "window": "review",
  "override_mode": null,
  "lookup_source": "yfinance.Ticker.calendar",
  "fallback_used": false,
  "_sanitization": {...}
}
```

### None (D+30, MSFT)

```json
{
  "ticker": "MSFT",
  "today_date": "2026-05-07",
  "next_earnings_date": "2026-06-06",
  "next_earnings_confirmed": true,
  "days_until": 30,
  "window": "none",
  "override_mode": null,
  "lookup_source": "yfinance.Ticker.calendar",
  "fallback_used": false,
  "_sanitization": {...}
}
```

### Both lookups failed (BADTKR)

```json
{
  "ticker": "BADTKR",
  "today_date": "2026-05-07",
  "next_earnings_date": null,
  "next_earnings_confirmed": false,
  "days_until": null,
  "window": "none",
  "override_mode": null,
  "lookup_source": "none",
  "fallback_used": true,
  "lookup_errors": [
    "calendar: RuntimeError: ...",
    "earnings_dates: RuntimeError: ..."
  ],
  "_sanitization": {...}
}
```

---

## 통합 지점 (Integration Points)

* **Chunk 5 — query-interpreter SKILL.md**: Mode E auto-detect (output mode 결정 표에 추가).
* **Chunk 5 — staleness-checker SKILL.md**: window != "none" + OD-F1 → 항상 FRESH_COLLECTION + `mode_override="E"`.
* **Chunk 5 — analyst AGENT.md**: 입력에 `earnings_window` 필드 추가, preview/review 분기.
* **Chunk 4 — render-earnings.py**: window 값으로 Preview vs Review 템플릿 선택.

---

## 참고 (References)

- 마스터 플랜: `docs/superpowers/plans/2026-05-07-mode-e-earnings-detail.md` Chunk 1
- yfinance 패턴 원본: `.claude/skills/financial-data-collector/scripts/peer-fetch.py`
- Sanitization: `tools/prompt_injection_filter.py`
