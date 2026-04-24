# Agent Audit Remediation Guide

작성일: 2026-04-24  
대상 프로젝트: `stock-analysis-agent`  
문서 목적: 엔지니어링 및 설계 감사에서 발견된 문제를 실제 개선 작업으로 전환하기 위한 상세 실행 가이드

## 0. 이 문서의 사용법

이 문서는 현재 에이전트의 동작을 설명하는 문서가 아니다. 이미 존재하는 파이프라인을 더 정확하고, 저렴하고, 안정적으로 만들기 위한 변경 지침이다.

각 항목은 다음 기준으로 작성한다.

- 문제: 현재 설계 또는 구현에서 실제로 실패할 수 있는 지점
- 영향: 출력 품질, 비용, 안정성, 유지보수성 중 무엇을 해치는지
- 수정안: 구체적으로 어떤 파일과 계약을 어떻게 바꿀지
- 완료 기준: 구현 후 무엇이 통과해야 하는지

권장 적용 순서는 다음과 같다. 이 순서는 `docs/agent-audit-remediation-guide-review.ko.md`의 검증 리뷰를 반영한 수정본이다.

1. P0: 데이터 무결성, 보안, prompt example 리크 제거
2. P1: 최종 산출물 품질 계약, mode별 schema, delivery gate 정리
3. P2: Mode C renderer와 run-local/cache 설계의 trade-off 확정
4. P3: 토큰 효율화와 context payload 축소
5. 유보: 제품 스코프 결정이 필요한 기능 제안

가장 중요한 실행 원칙은 두 가지다.

1. 틀린 숫자나 오염된 외부 텍스트를 전달하는 문제는 렌더링 품질 문제보다 먼저 고친다.
2. 분석 JSON이 맞다는 것과 사용자에게 전달되는 HTML/DOCX가 맞다는 것은 다른 문제다. 품질 게이트는 최종 산출물까지 검증해야 한다.

---

## 1. 최종 산출물 품질 계약 닫기

### 1.1 Mode C canonical renderer를 하나로 통일

#### 문제

Mode C 렌더링 지시가 서로 충돌한다.

- `CLAUDE.md`는 최종 사용자 산출물에 `.claude/skills/dashboard-generator/scripts/render-dashboard.py`를 쓰지 말라고 한다.
- `.claude/skills/dashboard-generator/SKILL.md`는 critic patch loop의 scripted rerender에 그 스크립트를 쓰라고 한다.
- `.claude/agents/analyst/AGENT.md`도 Mode C 자동 rerender에 그 스크립트를 지정한다.
- 실제 `render-dashboard.py`는 다음 핵심 섹션을 온전히 렌더하지 않는다.
  - `sections.dcf_analysis`
  - `sections.analyst_coverage`
  - `sections.qoe_summary`
  - quarterly financial detail
  - 실제 Chart.js data arrays
  - full template 기반 11개 섹션

결과적으로 patch loop를 거치면 처음에는 풍부했던 Mode C 대시보드가 얕은 MVP HTML로 퇴행할 수 있다.

#### 영향

- 출력 품질: 사용자에게 핵심 투자 판단 블록이 빠진 대시보드가 전달된다.
- 안정성: 어떤 렌더 경로를 탔는지에 따라 산출물 품질이 달라진다.
- 유지보수성: 문서와 코드가 충돌해 미래 수정자가 잘못된 경로를 강화할 가능성이 높다.

#### 수정 대상

- `CLAUDE.md`
- `.claude/skills/dashboard-generator/SKILL.md`
- `.claude/agents/analyst/AGENT.md`
- `.claude/skills/dashboard-generator/scripts/render-dashboard.py`
- `.claude/skills/dashboard-generator/references/html-template.md`
- `tools/eval_harness.py`
- `tests/`

#### 착수 전 결정 사항

이 작업은 단순한 함수 추가가 아니라 사실상 Mode C renderer 재설계에 가깝다. 현재 스크립트는 필드 스키마, Chart.js data path, DCF, analyst coverage, QoE, quarterly table 렌더링이 모두 부족하므로 800-1500줄 규모의 작업이 될 수 있다.

착수 전에 짧은 ADR을 작성해 다음 중 하나를 선택한다.

```text
Option A: render-dashboard.py 전면 재작성
- 장점: 최종 산출물 생성이 완전히 scriptable해진다.
- 단점: 초기 작업량이 가장 크다.

Option B: html-template.md 기반 manual/template rendering을 canonical로 명문화
- 장점: 현재 CLAUDE.md의 의도와 가장 가깝고 빠르게 충돌을 제거한다.
- 단점: 사람이 개입하는 렌더 경로가 남아 자동 회귀 테스트가 약하다.

Option C: Jinja 또는 lightweight template engine 도입
- 장점: template과 renderer 책임 분리가 명확하다.
- 단점: 새 의존성과 template migration 비용이 생긴다.
```

권장 경로는 단기적으로 Option B로 충돌을 제거하고, rendered output validator와 snapshot test를 먼저 붙인 뒤, Option C 또는 A로 자동화를 강화하는 것이다.

#### 구현 절차

1. ADR에서 canonical render strategy를 먼저 선택한다.
2. Option A 또는 C를 선택한 경우 `render-dashboard.py`를 최종 사용자용 canonical renderer로 승격하거나 template engine 기반 renderer로 대체한다.
3. Option B를 선택한 경우 `render-dashboard.py` 참조를 final delivery path에서 제거하고, `html-template.md` 기반 rendering을 canonical로 명문화한다.
4. placeholder 기반 렌더링을 명시적으로 구현한다.
5. 다음 렌더 함수 또는 동등한 모듈을 추가한다.
   - `render_header`
   - `render_scenarios`
   - `render_key_metrics`
   - `render_variant_view`
   - `render_precision_risks`
   - `render_valuation_metrics`
   - `render_sotp`
   - `render_dcf_analysis`
   - `render_macro_context`
   - `render_peer_comparison`
   - `render_analyst_coverage`
   - `render_charts`
   - `render_quarterly_financials`
   - `render_qoe_summary`
   - `render_portfolio_strategy`
   - `render_what_would_make_me_wrong`
   - `render_catalysts`
   - `render_disclaimer`
6. 기존 문서에서 “manual rendering”과 “scripted MVP renderer”의 이중 경로를 제거한다.
7. Analyst patch loop의 Mode C rerender 지시를 선택된 canonical 경로로만 통일한다.
8. 필드 스키마 불일치도 함께 정리한다. 예를 들어 `macro_context.factors[].factor`와 `factors[].thesis`, 구조화된 `what_would_make_me_wrong`과 flat string renderer 기대값을 하나로 맞춘다.

#### 권장 renderer 동작

입력:

- run-local `analysis-result.json`
- 선택 입력: run-local `validated-data.json`
- 선택 입력: run-local `quality-report.json`

출력:

- `output/reports/{ticker}_C_{lang}_{YYYY-MM-DD}.html`
- renderer metadata block

권장 metadata:

```json
{
  "renderer": "dashboard-renderer",
  "renderer_version": "2",
  "input_analysis_path": "output/runs/{run_id}/{ticker}/analysis-result.json",
  "required_sections_rendered": true,
  "chart_arrays_rendered": true,
  "render_warnings": []
}
```

#### 완료 기준

- Mode C 최종 HTML에 DCF, analyst coverage, macro, peer table, quarterly table, chart data arrays가 모두 존재한다.
- `render-dashboard.py`를 사용해도 “fixture narrative only” 같은 정적 안내문이 나오지 않는다.
- `CLAUDE.md`, dashboard skill, analyst agent가 모두 같은 renderer 경로를 가리킨다.
- fixture 기반 snapshot test가 기존 MVP HTML로 회귀하면 실패한다.

---

### 1.2 rendered output validator 추가

#### 문제

현재 품질 검사는 생성된 HTML/DOCX 자체를 충분히 보지 않는다. `quality_report.py`는 주로 `research-plan`, `validated-data`, `analysis-result`의 JSON 계약을 검사한다.

하지만 실제 실패는 렌더 단계에서 자주 발생한다.

- JSON에는 있는 섹션이 HTML에 빠짐
- Grade D 값이 `-` 대신 숫자로 노출됨
- 숫자에 source tag가 붙지 않음
- disclaimer 누락
- chart canvas는 있지만 data arrays가 비어 있음
- DOCX table이 비거나 섹션 순서가 깨짐

#### 영향

- 출력 품질: 사용자에게 보이는 산출물이 검증 대상에서 빠진다.
- 안정성: renderer 버그가 품질 게이트를 우회한다.
- 유지보수성: JSON contract와 output contract가 분리되어 회귀를 잡기 어렵다.

#### 수정 대상

- `tools/quality_report.py`
- `tools/artifact_validation.py`
- `.claude/skills/quality-checker/SKILL.md`
- `.claude/skills/quality-checker/scripts/quality-report-builder.py`
- `tests/`

#### 구현 절차

1. `quality-report-builder.py`에 `--report-path` 인자를 추가한다.
2. `quality_report.py`에 `build_rendered_output_item`을 추가한다.
3. HTML validator와 DOCX validator를 분리한다.
4. HTML validator는 최소 다음 항목을 확인한다.
   - `<html>` 구조 유효성
   - disclaimer 존재
   - mode별 필수 heading 존재
   - Mode C chart data arrays 존재
   - Grade D excluded metrics가 숫자로 노출되지 않음
   - rendered output 안의 주요 숫자 source tag coverage
5. DOCX validator는 최소 다음 항목을 확인한다.
   - 문서가 열림
   - 필수 heading 존재
   - 표가 비어 있지 않음
   - disclaimer 존재
   - Grade D excluded metrics 노출 금지

#### 권장 HTML 검사 항목

```python
def build_rendered_output_item(report_path, analysis, validated):
    checks = {
        "file_exists": check_file_exists(report_path),
        "required_sections": check_required_sections(report_path, analysis["output_mode"]),
        "disclaimer": check_disclaimer(report_path),
        "source_tag_coverage": check_source_tags(report_path),
        "blank_over_wrong": check_excluded_metrics_absent(report_path, validated),
        "mode_c_charts": check_mode_c_chart_arrays(report_path, analysis),
    }
    return summarize_checks(checks)
```

#### 완료 기준

- `quality-report.json`에 `rendered_output` 항목이 생긴다.
- Mode C에서 DCF 또는 analyst coverage를 제거한 fixture가 FAIL한다.
- chart array가 없는 Mode C HTML이 FAIL한다.
- disclaimer 없는 HTML/DOCX가 FAIL한다.
- Grade D metric이 숫자로 노출되면 FAIL한다.

---

### 1.3 `analysis-result` schema를 output mode별로 강화

#### 문제

현재 `analysis-result.schema.json`은 top-level 필드만 강제하고 `sections`를 거의 자유 object로 둔다. 이 때문에 Mode C/D에서 필요한 구조가 빠져도 schema validation을 통과할 수 있다.

#### 영향

- 출력 품질: renderer가 기대하는 구조와 analyst가 생성하는 구조가 어긋난다.
- 안정성: 누락 섹션이 runtime 렌더 오류 또는 빈 HTML로 이어진다.
- 유지보수성: 새 섹션 추가 시 검증 지점이 없다.

#### 수정 대상

- `.claude/schemas/analysis-result.schema.json`
- `tools/eval_harness.py`
- `tools/artifact_validation.py`
- `.claude/agents/analyst/AGENT.md`
- fixture files under `evals/`

#### 구현 절차

1. `output_mode`를 discriminator로 사용한다.
2. Mode A, B, C, D 별 required sections를 분리한다.
3. Mode C required sections를 최소 다음처럼 정의한다.
   - `variant_view_q1`
   - `variant_view_q2`
   - `variant_view_q3`
   - `precision_risks`
   - `valuation_metrics`
   - `dcf_analysis`
   - `macro_context`
   - `peer_comparison`
   - `analyst_coverage`
   - `qoe_summary`
   - `portfolio_strategy`
   - `what_would_make_me_wrong`
4. Mode D required sections를 memo spec에 맞춰 별도 정의한다.
5. 각 배열에는 최소 길이를 둔다.
6. 각 narrative section에는 최소 문자 수 또는 word count를 둔다.

#### 권장 schema 방향

```json
{
  "if": {
    "properties": {
      "output_mode": { "const": "C" }
    }
  },
  "then": {
    "required": ["sections", "scenarios", "key_metrics"],
    "properties": {
      "sections": {
        "required": [
          "variant_view_q1",
          "variant_view_q2",
          "variant_view_q3",
          "precision_risks",
          "valuation_metrics",
          "dcf_analysis",
          "macro_context",
          "peer_comparison",
          "analyst_coverage",
          "qoe_summary",
          "portfolio_strategy",
          "what_would_make_me_wrong"
        ]
      }
    }
  }
}
```

#### 완료 기준

- Mode C fixture에서 `dcf_analysis`를 제거하면 schema/eval이 실패한다.
- Mode C fixture에서 `precision_risks`가 3개 미만이면 실패한다.
- Mode D fixture에서 memo 핵심 섹션이 누락되면 실패한다.
- renderer가 schema에 없는 필드명을 임의로 기대하지 않는다.

---

## 2. 경로, delivery gate, 실행 구조 정리

### 2.1 run-local artifact 경로를 단일화

#### 문제

문서와 코드가 raw artifact 위치를 다르게 본다.

- 일부 문서와 skill은 `output/data/{ticker}/tier1-raw.json`, `output/data/{ticker}/tier2-raw.json`을 사용한다.
- `tools/analysis_contract.py`의 `build_run_paths`는 run-local path 아래 raw artifact를 둔다.

이 구조에서는 같은 티커를 동시에 분석하거나 재실행할 때 raw data가 덮일 수 있다.

#### 영향

- 안정성: multi-run, multi-ticker 실행에서 입력 artifact가 섞인다.
- 재현성: 특정 report가 어떤 raw input으로 만들어졌는지 추적하기 어렵다.
- 유지보수성: skill마다 참조 경로가 달라진다.

#### 수정 대상

- `CLAUDE.md`
- `.claude/skills/financial-data-collector/SKILL.md`
- `.claude/skills/web-researcher/SKILL.md`
- `.claude/agents/analyst/AGENT.md`
- `.claude/agents/data-researcher/AGENT.md`
- `tools/analysis_contract.py`
- `tools/artifact-manager.py`
- tests and fixtures

#### 설계 전제

run-local 경로 단일화는 캐시와 staleness 재사용을 없애자는 뜻이 아니다. 현재의 `latest.json` 기반 24시간 재사용 모델은 유지하되, mutable raw artifact를 shared path에서 직접 갱신하는 구조를 피해야 한다.

권장 구조는 다음과 같다.

```text
Run-local working set:
output/runs/{run_id}/{ticker}/tier1-raw.json
output/runs/{run_id}/{ticker}/tier2-raw.json
output/runs/{run_id}/{ticker}/validated-data.json
output/runs/{run_id}/{ticker}/analysis-result.json

Shared immutable cache:
output/data/{ticker}/snapshots/{snapshot_id}/tier1-raw.json
output/data/{ticker}/snapshots/{snapshot_id}/tier2-raw.json
output/data/{ticker}/snapshots/{snapshot_id}/validated-data.json
output/data/{ticker}/snapshots/{snapshot_id}/evidence-pack.json

Shared latest pointer:
output/data/{ticker}/latest.json
```

`latest.json`은 raw 파일 자체가 아니라 최신 snapshot pointer와 freshness metadata를 담는다.

```json
{
  "ticker": "AAPL",
  "latest_snapshot_id": "2026-04-24_run_abc123",
  "created_at": "2026-04-24T09:30:00Z",
  "source_profile": "financial_datasets",
  "overall_grade": "B",
  "expires_at": "2026-04-25T09:30:00Z",
  "artifact_refs": {
    "validated_data": "output/data/AAPL/snapshots/2026-04-24_run_abc123/validated-data.json",
    "evidence_pack": "output/data/AAPL/snapshots/2026-04-24_run_abc123/evidence-pack.json"
  }
}
```

Workflow 2에서는 `run_id`를 batch 전체에 하나 부여하고, ticker별 artifact는 `{run_id}/{ticker}/` 아래에 둔다. ticker별 재사용은 `latest.json` pointer를 읽어 run-local working set으로 복사하거나 참조하는 방식으로 처리한다.

#### 구현 절차

1. 모든 run 입력/중간 산출물은 다음 위치로 통일한다.

```text
output/runs/{run_id}/{ticker}/research-plan.json
output/runs/{run_id}/{ticker}/tier1-raw.json
output/runs/{run_id}/{ticker}/tier2-raw.json
output/runs/{run_id}/{ticker}/validated-data.json
output/runs/{run_id}/{ticker}/analysis-result.json
output/runs/{run_id}/{ticker}/quality-report.json
```

2. `output/data/{ticker}/`는 immutable snapshot/cache와 `latest.json` pointer 전용으로 축소한다.

```text
output/data/{ticker}/{ticker}_{date}_snapshot.json
output/data/{ticker}/latest.json
output/data/{ticker}/snapshots/{snapshot_id}/...
```

3. run이 성공적으로 validation과 quality gate를 통과하면 run-local artifact를 shared snapshot으로 승격한다.
4. staleness checker는 `output/data/{ticker}/latest.json`만 읽고, fresh하면 해당 snapshot을 새 run의 input으로 재사용한다.
5. `collection-complete.json`은 전역 파일로 두지 않는다. 필요하면 run-local manifest에 넣는다.

```text
output/runs/{run_id}/run-manifest.json
```

6. skill 문서의 모든 `output/data/{ticker}/tier*-raw.json` 예시를 run-local path로 바꾼다.
7. collector script의 `--output` 예시도 run-local path로 바꾼다.
8. `CLAUDE.md`의 analyst handoff 표와 `.claude/agents/analyst/AGENT.md`의 raw artifact 입력 목록을 일치시킨다.

#### 완료 기준

- `rg "output/data/\\{ticker\\}/tier" .` 결과가 0개가 된다.
- 같은 ticker 두 개 run을 동시에 실행해도 raw artifact가 충돌하지 않는다.
- report metadata에서 run-local input path를 추적할 수 있다.
- 24시간 staleness 재사용이 깨지지 않고 `latest.json` pointer를 통해 동작한다.
- Workflow 2 batch run에서 하나의 `run_id` 아래 ticker별 subdirectory가 생성된다.

---

### 2.2 `STOCK_ANALYSIS_DATA_DIR` 적용 범위 통합

#### 문제

`tools/paths.py`는 `STOCK_ANALYSIS_DATA_DIR`를 지원하지만, 일부 path builder는 repo 하위 `output`을 직접 조립한다.

#### 영향

- 안정성: CI나 임시 실행에서 artifact가 repo 내부로 새어 나간다.
- 보안: private output을 외부 지정 경로로 격리하려는 의도가 깨진다.
- 유지보수성: path 정책을 찾기 어렵다.

#### 수정 대상

- `tools/paths.py`
- `tools/analysis_contract.py`
- `tools/artifact-manager.py`
- `tools/contract_checks.py`
- renderer scripts
- collector scripts

#### 구현 절차

1. `analysis_contract.py`에서 `output_dir = base / "output"` 하드코딩을 제거한다.
2. `tools.paths.data_dir()`를 단일 runtime artifact root로 사용한다.
3. `build_run_paths` signature를 다음 방향으로 바꾼다.

```python
def build_run_paths(run_id: str, ticker: str, data_root: Path | None = None) -> dict[str, Path]:
    output_dir = data_root or data_dir()
```

4. report path builder도 `data_dir() / "reports"`를 사용한다.
5. `contract_checks.py`는 fixture를 repo `output`에 복사하지 않고 temp dir에서 실행한다.

#### 완료 기준

- `STOCK_ANALYSIS_DATA_DIR=/tmp/stock-agent-test`로 contract checks를 돌렸을 때 repo `output/`이 생성되지 않는다.
- 모든 artifact manager와 renderer가 같은 root를 사용한다.
- tests에서 temp dir isolation이 가능하다.

---

### 2.3 delivery gate 정책을 severity 기반으로 재정의

#### 문제

문서는 quality issue가 delivery를 막지 않는다고 하고, 코드는 FAIL/critic FAIL을 BLOCKED로 처리한다. 이 충돌 때문에 에이전트가 어떤 상황에서 결과를 전달해야 하는지 불명확하다.

#### 영향

- 출력 품질: 심각한 결함이 flag만 달고 전달될 수 있다.
- UX: 반대로 가벼운 문제 때문에 결과가 불필요하게 block될 수 있다.
- 유지보수성: 문서와 코드 중 어느 쪽이 진실인지 알 수 없다.

#### 수정 대상

- `CLAUDE.md`
- `.claude/skills/quality-checker/SKILL.md`
- `tools/quality_report.py`
- `tools/patch_loop.py`
- tests

#### 권장 정책

severity를 네 단계로 나눈다.

```text
BLOCKER
- unsanitized artifact consumed
- schema invalid
- final report missing
- rendered output structurally invalid
- required mode section missing
- price/date completely missing for current analysis

MAJOR
- source tag coverage below threshold
- Grade D value rendered
- scenario math inconsistent
- DCF sensitivity missing in Mode C

MINOR
- formatting defect
- partial narrative thinness
- non-critical citation density issue

INFO
- historical migration warning
- limited source warning already disclosed
```

delivery rule:

```text
BLOCKER -> delivery_gate.result = BLOCKED
MAJOR -> delivery_gate.result = PASS_WITH_FLAGS unless policy says hard fail
MINOR -> PASS_WITH_FLAGS
INFO -> PASS
```

#### 구현 절차

1. `infer_delivery_impact`를 status 중심이 아니라 severity 중심으로 바꾼다.
2. 각 quality item이 `severity`를 반환하게 한다.
3. 문서의 “Quality issues do NOT block output delivery” 문장을 제거하거나 다음처럼 바꾼다.

```text
Non-blocking quality issues do not block delivery. Structural, security, and data-integrity failures block delivery.
```

4. patch loop도 `BLOCKER`일 때는 기본적으로 redelivery를 막고, `MAJOR/MINOR`는 inline flags로 전달하도록 맞춘다.
5. 단, `BLOCKER` 중 renderer 누락, schema 누락처럼 deterministic patch가 가능한 항목은 남은 patch budget 안에서 한 번 재시도할 수 있게 한다. unsanitized artifact consumption, schema-invalid raw input처럼 보안/데이터 무결성 항목은 자동 재시도보다 ingestion 차단을 우선한다.

#### 완료 기준

- critic FAIL이 모두 무조건 BLOCKED가 되지 않는다.
- rendered output missing, unsanitized consumed, schema invalid는 항상 BLOCKED가 된다.
- patch 가능한 BLOCKER와 즉시 차단해야 하는 BLOCKER가 구분된다.
- quality report에 `severity`, `delivery_impact`, `ready_for_delivery`가 일관되게 기록된다.

---

## 3. 토큰 효율화

### 3.1 `CLAUDE.md` 중복 지시 정리

#### 문제

상위 오케스트레이터가 일부 skill/agent 문서의 절차를 반복한다. 다만 현재 `CLAUDE.md` 전체를 공격적으로 줄이는 것이 항상 높은 ROI를 보장하지는 않는다. 문제의 핵심은 줄 수 자체가 아니라 renderer, path, delivery gate처럼 서로 충돌하는 정책이 여러 곳에 존재한다는 점이다.

#### 영향

- 비용: 매 실행마다 긴 지시문이 모델 컨텍스트에 들어간다.
- 품질: 같은 주제에 다른 지시가 있으면 모델이 잘못된 쪽을 따른다.
- 유지보수성: 정책 변경 시 여러 파일을 동시에 고쳐야 한다.

#### 수정 대상

- `CLAUDE.md`
- `.claude/skills/*/SKILL.md`
- `.claude/agents/*/AGENT.md`

#### 구현 절차

1. 먼저 충돌이 확인된 정책만 단일 출처로 이동한다.
   - Mode C renderer 경로
   - run-local/shared cache path contract
   - delivery severity policy
   - analyst input handoff contract
2. ROI가 확인되면 `CLAUDE.md`에는 다음만 남기는 방향으로 축소한다.
   - routing decision
   - mode selection
   - artifact lifecycle overview
   - hard safety rules
   - skill/agent dispatch table
3. 세부 실행 절차는 각 skill/agent에만 둔다.
4. 공통 규칙은 새 파일로 분리한다.

권장 파일:

```text
.claude/contracts/core-policies.md
.claude/contracts/path-contract.md
.claude/contracts/quality-gate-policy.md
.claude/contracts/source-confidence-policy.md
```

5. skill/agent 문서는 공통 규칙을 복사하지 않고 참조한다.

#### 완료 기준

- renderer/path/delivery/analyst handoff 정책이 각각 하나의 canonical source를 가진다.
- 같은 정책 문장이 3개 이상 파일에 반복되지 않는다.
- Mode C renderer 관련 지시가 한 곳에만 존재한다.

---

### 3.2 Standard Mode 수집 순서 변경

#### 문제

Standard Mode에서 가격, 시총, P/E 같은 구조화 데이터를 먼저 웹 검색으로 찾고, 검색이 부족할 때 yfinance를 fallback으로 사용한다.

#### 영향

- 비용: 검색 결과 snippet이 많이 들어가 토큰을 소모한다.
- 품질: 구조화 가능한 값을 검색 snippet에서 추출하면 오류 가능성이 높다.
- 안정성: 검색 결과 순위에 따라 값이 흔들린다.

#### 수정 대상

- `.claude/skills/web-researcher/SKILL.md`
- `.claude/skills/financial-data-collector/SKILL.md`
- `docs/yfinance-integration-spec.md`
- `README.md`

#### 새 Standard Mode 순서

1. yfinance structured fetch
2. validated-data candidate 생성
3. 누락 필드 목록 계산
4. 누락 필드만 targeted search
5. qualitative context search
6. validator에서 confidence grade 결정

#### 권장 검색 정책

기존 8개 고정 검색을 다음처럼 바꾼다.

```text
Always run:
- earnings/news/catalyst query
- analyst coverage query
- competitor query

Run only if missing:
- price/market cap query
- P/E or valuation query
- SEC filing query
- insider trading query
```

#### 완료 기준

- Standard Mode에서 yfinance 성공 시 price/market cap/P/E 검색을 생략한다.
- tier2 raw가 아니라 distilled evidence pack이 analyst로 전달된다.
- 동일 ticker 분석의 검색 query 수가 평균 30-50% 감소한다.

---

### 3.3 raw artifact 대신 evidence pack 전달

#### 문제

Analyst가 `tier1-raw.json`, `tier2-raw.json`을 직접 읽는다. raw artifact는 중복 필드, 긴 snippet, 검색 결과 noise를 포함한다.

#### 영향

- 비용: 분석 모델 컨텍스트가 불필요하게 커진다.
- 품질: 검증 전 정보와 검증 후 정보가 섞인다.
- 안정성: prompt injection 방어 후에도 raw external text 노출면이 넓다.

#### 수정 대상

- `.claude/agents/analyst/AGENT.md`
- `.claude/skills/web-researcher/SKILL.md`
- `.claude/skills/data-validator/SKILL.md`
- `tools/artifact_validation.py`
- schemas

#### 새 artifact 제안

```text
output/runs/{run_id}/{ticker}/evidence-pack.json
```

권장 구조:

```json
{
  "ticker": "AAPL",
  "as_of": "2026-04-24",
  "facts": [
    {
      "id": "fact_001",
      "claim": "Current market price is ...",
      "source_url": "https://...",
      "source_type": "market_data",
      "as_of_date": "2026-04-24",
      "confidence": "B"
    }
  ],
  "catalysts": [],
  "risks": [],
  "analyst_coverage": [],
  "conflicts": [],
  "raw_artifact_refs": [
    "output/runs/{run_id}/{ticker}/tier2-raw.json"
  ]
}
```

#### 구현 절차

1. Web researcher는 raw search results를 저장한다.
2. Data validator 또는 별도 summarizer가 `evidence-pack.json`을 만든다.
3. Analyst input에서 raw artifact를 제거하고 evidence pack만 기본 로드한다.
4. Analyst가 raw를 열 수 있는 경우를 명시한다.
   - validator가 conflict를 표시한 경우
   - 특정 Grade C/D metric을 재검토하는 경우
   - critic이 source mismatch를 지적한 경우

#### 완료 기준

- Analyst 기본 입력 목록에 raw `tier2-raw.json`이 없다.
- evidence pack에는 snippet 전문이 아니라 검증 가능한 fact 단위만 있다.
- raw artifact를 직접 읽은 경우 quality report에 이유가 남는다.

---

### 3.4 모델 라우팅 비용 최적화

#### 문제

모든 하위 작업을 같은 고성능 모델에 맡길 필요가 없다. 특히 수집 결과 정리, 렌더링, 기계적 검증은 LLM 사용 자체가 불필요하거나 저렴한 모델로 충분하다.

#### 영향

- 비용: output-heavy 작업에 비싼 모델이 쓰인다.
- 안정성: deterministic하게 처리할 수 있는 일을 모델이 매번 다르게 수행한다.
- 유지보수성: 오류 재현이 어렵다.

#### 권장 라우팅

```text
Strong model:
- final investment reasoning
- variant view
- risk mechanism critique
- what-would-make-me-wrong

Cheaper model:
- evidence pack summarization
- analyst coverage summary
- news catalyst grouping
- first-pass critic narrative comments

No LLM:
- schema validation
- source tag count
- scenario probability sum
- word count
- HTML required section check
- DOCX heading/table check
- ratio recomputation
- path contract validation
- renderer execution
```

#### 완료 기준

- `quality_report.py`의 핵심 품질 항목은 LLM 없이 재현 가능하다.
- renderer는 LLM 없이 같은 입력에서 같은 출력이 나온다.
- Analyst에게 주입되는 context token 수가 run별로 측정된다.

---

## 4. 데이터 정확도와 안전성 강화

### 4.1 `data_mode`와 `source_profile` 분리

#### 문제

Enhanced Mode 요청에서 Financial Datasets가 실패하고 yfinance만 성공해도 `data_mode = "enhanced"`를 유지하라는 지시가 있다. 이는 사용자에게 SEC-grade 수준의 데이터가 확보된 것처럼 보일 수 있다.

#### 영향

- 출력 품질: 데이터 신뢰도 설명이 부정확하다.
- 안정성: downstream prompt가 enhanced data라고 믿고 더 강한 결론을 낼 수 있다.
- 사용자 신뢰: 실제 source tier와 표시 mode가 불일치한다.

#### 수정 대상

- `.claude/skills/financial-data-collector/SKILL.md`
- `.claude/schemas/validated-data.schema.json`
- `.claude/schemas/analysis-result.schema.json`
- renderer templates
- quality report

#### 새 필드 제안

```json
{
  "requested_mode": "enhanced",
  "effective_mode": "standard",
  "source_profile": "yfinance_fallback",
  "source_tier": "portal_structured",
  "confidence_cap": "C"
}
```

권장 enum:

```text
source_profile:
- financial_datasets
- sec_or_dart_primary
- yfinance_fallback
- web_only
- mixed

source_tier:
- filing_primary
- api_structured
- portal_structured
- search_snippet
- user_supplied
```

#### 완료 기준

- yfinance fallback만 사용한 run은 `source_profile=yfinance_fallback`으로 표시된다.
- renderer의 confidence badge가 `data_mode`가 아니라 `source_profile`과 `overall_grade`를 함께 반영한다.
- Analyst prompt가 `enhanced`라는 단어만 보고 데이터 강도를 과대평가하지 않는다.

---

### 4.2 DART TTM 계산 수정

#### 문제

DART collector의 TTM 계산은 주석상 true TTM을 언급하지만, 실제로는 Q3 YTD를 proxy로 사용하는 경로가 있다.

#### 영향

- 출력 품질: KR 기업의 TTM revenue, operating income, net income이 과소 또는 왜곡될 수 있다.
- 비용: 잘못된 값으로 valuation과 scenario를 다시 계산하게 된다.
- 안정성: confidence grade가 실제 계산 정밀도를 반영하지 못한다.

#### 수정 대상

- `.claude/skills/web-researcher/scripts/dart-collector.py`
- tests
- data validator confidence grading

#### 권장 계산

```text
true_ttm = current_ytd + prior_annual - prior_same_period_ytd
```

예:

```text
2026 Q3 TTM = 2026 Q3 YTD + 2025 Annual - 2025 Q3 YTD
```

필요 데이터:

- current Q3
- prior annual
- prior Q3

대체 정책:

```text
If true TTM possible:
  ttm_precision = "high"
  grade eligible for A/B

If only annual:
  ttm_precision = "medium"
  label = "latest annual, not TTM"

If only Q3/H1 YTD:
  ttm_precision = "low"
  confidence_cap = "C"
  output label must say "YTD proxy"
```

#### 완료 기준

- Q3 + prior annual + prior Q3 fixture에서 true TTM이 계산된다.
- Q3만 있는 fixture는 TTM이라고 표시하지 않고 YTD proxy로 표시한다.
- confidence grade가 precision에 따라 제한된다.

---

### 4.3 CapEx와 FCF 표준 필드 분리

#### 문제

yfinance collector는 `free_cash_flow = operating_cashflow + capital_expenditure`로 계산한다. 이는 yfinance에서 CapEx가 음수로 들어오는 관례에 기대는 방식이다. 반면 문서에서는 CapEx를 절대값으로 보고 `Operating CF - CapEx`라고 설명한다.

#### 영향

- 출력 품질: source별 CapEx 부호가 다르면 FCF가 뒤집힌다.
- 안정성: downstream ratio calculator와 renderer가 어떤 부호 convention을 쓰는지 모호하다.
- 유지보수성: 새 데이터 source 추가 시 같은 버그가 반복된다.

#### 수정 대상

- `.claude/skills/financial-data-collector/scripts/yfinance-collector.py`
- `.claude/skills/financial-data-collector/SKILL.md`
- data validator
- ratio/valuation calculators

#### 새 표준 필드

```json
{
  "operating_cashflow": 100,
  "capex_raw": -20,
  "capex_outflow_abs": 20,
  "capex_sign_convention": "negative_outflow",
  "free_cash_flow": 80
}
```

#### 구현 절차

1. collector boundary에서 source-specific raw 값을 보존한다.
2. 모든 downstream 계산은 `capex_outflow_abs`만 사용한다.
3. `free_cash_flow`가 source에서 제공되면 cross-check한다.
4. source FCF와 계산 FCF 차이가 threshold를 넘으면 conflict로 기록한다.

#### 완료 기준

- CapEx가 음수인 fixture와 양수인 fixture 모두 같은 FCF가 나온다.
- FCF 계산에 사용한 convention이 artifact에 기록된다.
- Analyst output에는 raw CapEx 부호가 직접 노출되지 않는다.

---

### 4.4 sanitization failure를 ingestion block으로 승격

#### 문제

문서는 sanitization 실패가 downstream consumption을 막는다고 하지만, validator는 unsanitized fetched artifact에 flag를 달면서도 `valid`는 true일 수 있다.

#### 영향

- 보안: 외부 fetched text가 prompt injection 필터 없이 분석 단계에 들어갈 수 있다.
- 안정성: Grade D flag만으로는 ingestion 차단을 보장하지 않는다.
- 유지보수성: “valid”의 의미가 schema-valid인지 consumption-safe인지 불명확하다.

#### 수정 대상

- `tools/artifact_validation.py`
- `tools/sanitize_artifact.py`
- `.claude/skills/web-researcher/SKILL.md`
- `.claude/agents/analyst/AGENT.md`
- tests

#### 권장 필드

```json
{
  "valid": true,
  "schema_valid": true,
  "ingestion_allowed": false,
  "security_flags": ["unsanitized_fetched_content"]
}
```

strict mode:

```text
If artifact_type is fetched raw and _sanitization is missing:
  schema_valid may be true
  ingestion_allowed must be false
  delivery severity must be BLOCKER if consumed
```

#### 완료 기준

- unsanitized raw artifact는 Analyst 기본 입력에서 제외된다.
- unsanitized artifact를 소비한 흔적이 있으면 quality gate가 BLOCKED가 된다.
- tests가 `valid=true`만 확인하지 않고 `ingestion_allowed=false`를 확인한다.

---

### 4.5 FRED macro 수집 실패와 confidence grade 명시

#### 문제

FRED collector 실패는 timeout/fallback 표에는 등장하지만, `macro_context`가 FRED 데이터를 어느 grade로 표시하고 어떤 경우에 비워야 하는지 산출물 계약이 약하다. 이 상태에서는 macro data가 누락되어도 narrative가 일반론으로 채워지거나, 반대로 오래된 macro snapshot이 현재 데이터처럼 보일 수 있다.

#### 영향

- 출력 품질: 금리, 인플레이션, 환율 같은 macro assumption이 source freshness 없이 쓰일 수 있다.
- 안정성: FRED 실패가 quality gate에서 구조적으로 드러나지 않는다.
- 유지보수성: macro_context가 정량 데이터인지 일반 서술인지 구분하기 어렵다.

#### 수정 대상

- `.claude/skills/web-researcher/SKILL.md`
- `.claude/schemas/analysis-result.schema.json`
- `tools/quality_report.py`
- `tools/artifact_validation.py`
- FRED collector tests

#### 수정안

`macro_context`에 structured status를 명시한다.

```json
{
  "macro_context": {
    "structured": {
      "source": "FRED",
      "retrieved_at": "2026-04-24T09:30:00Z",
      "series": [
        {
          "id": "DGS10",
          "label": "10Y Treasury",
          "value": 4.52,
          "as_of_date": "2026-04-23",
          "grade": "A"
        }
      ],
      "status": "available"
    },
    "narrative": "<macro interpretation>"
  }
}
```

FRED 실패 시:

```json
{
  "structured": {
    "source": "FRED",
    "status": "unavailable",
    "grade": "D",
    "reason": "collector_timeout"
  }
}
```

#### 완료 기준

- FRED 실패가 `macro_context.structured.status=unavailable`로 표시된다.
- FRED가 없는 경우 macro 숫자를 임의 생성하지 않는다.
- rendered output은 macro data unavailable을 명시하거나 해당 정량 카드를 비운다.

---

## 5. Prompt engineering 및 tool contract 개선

### 5.1 실제 기업/날짜/수치가 들어간 prompt example 제거

#### 문제

Analyst prompt 예시가 AAPL, 2026년 이벤트, 구체적인 가격과 성장률을 포함한다. 모델이 예시 값을 대상 기업 분석에 끌어올 위험이 있다.

#### 영향

- 출력 품질: plausible하지만 사실이 아닌 catalyst나 수치가 생성될 수 있다.
- 안정성: 같은 예시가 여러 분석에 반복적으로 새어 나갈 수 있다.
- 유지보수성: 시간이 지나면 예시 날짜 자체가 낡은 사실이 된다.

#### 수정 대상

- `.claude/agents/analyst/AGENT.md`
- `.claude/agents/critic/AGENT.md`
- framework reference docs

#### 수정 방식

잘못된 예:

```json
{
  "ticker": "AAPL",
  "price_at_analysis": 175.50,
  "upcoming_catalysts": [
    {"date": "2026-04-25", "description": "Q2 FY2026 earnings"}
  ]
}
```

권장 예:

```json
{
  "ticker": "<TICKER>",
  "price_at_analysis": "<CURRENT_PRICE>",
  "upcoming_catalysts": [
    {
      "date": "<CATALYST_DATE>",
      "description": "<SOURCE_BACKED_EVENT>"
    }
  ]
}
```

#### 완료 기준

- prompt examples에 실제 ticker, 실제 날짜, 실제 기업 이벤트가 없다.
- 예시는 schema shape만 보여준다.
- “do not copy examples” 같은 자연어 주의문에 의존하지 않는다.

---

### 5.2 search result와 extracted metric schema 명시

#### 문제

도구 설명은 검색 순서와 fallback은 설명하지만, 검색 결과에서 값을 어떻게 추출하고 충돌을 어떻게 기록할지 schema가 없다.

#### 영향

- 출력 품질: 서로 다른 source의 값을 임의로 섞을 수 있다.
- 안정성: validator가 어떤 후보를 왜 버렸는지 추적하기 어렵다.
- 유지보수성: 새 검색 도구 추가 시 결과 shape가 계속 달라진다.

#### 수정 대상

- `.claude/skills/web-researcher/SKILL.md`
- `.claude/schemas/`
- `tools/artifact_validation.py`
- data validator

#### 새 schema 제안

`SearchResult`:

```json
{
  "query_id": "q_001",
  "query": "<QUERY>",
  "rank": 1,
  "title": "<TITLE>",
  "url": "<URL>",
  "published_date": "<DATE_OR_NULL>",
  "retrieved_at": "<TIMESTAMP>",
  "snippet": "<SANITIZED_SNIPPET>",
  "source_domain": "<DOMAIN>"
}
```

`ExtractedMetricCandidate`:

```json
{
  "metric": "market_cap",
  "raw_value": "$2.7T",
  "normalized_value": 2700000000000,
  "unit": "USD",
  "as_of_date": "2026-04-24",
  "source_url": "https://...",
  "extraction_method": "search_snippet",
  "confidence_candidate": "C",
  "notes": "Snippet-based, not filing verified"
}
```

#### 완료 기준

- Web researcher output에 raw search results와 extracted candidates가 분리되어 있다.
- validator는 extracted candidates만 사용해 final metric을 고른다.
- conflict가 있는 metric은 `conflicts` 배열에 남는다.

---

### 5.3 Critic을 결정론적 검사와 판단형 비평으로 분리

#### 문제

현재 critic은 source tag coverage, scenario probability sum, required section completeness, blank-over-wrong 같은 기계적 검사까지 담당한다. 일부 항목은 이미 `quality_report.py`에 결정론적으로 구현되어 있으므로, 이 작업은 완전한 신설이 아니라 기존 deterministic check를 확장하고 critic prompt에서 중복 책임을 줄이는 작업이다.

#### 영향

- 비용: 코드로 할 수 있는 검사를 모델이 수행한다.
- 안정성: 동일 산출물도 critic 응답에 따라 PASS/FAIL이 흔들린다.
- 유지보수성: 실패 원인을 자동으로 재현하기 어렵다.

#### 수정 대상

- `.claude/agents/critic/AGENT.md`
- `tools/quality_report.py`
- `tools/eval_harness.py`
- tests

#### 분리 기준

deterministic validator:

- existing: financial consistency
- existing: blank-over-wrong
- source tag coverage
- scenario probabilities sum to 100
- bull/base/bear target ordering
- required section presence
- required section word count
- rendered Grade D exclusion
- disclaimer
- HTML/DOCX structure
- numeric consistency against validated data

critic model:

- variant view가 consensus와 충분히 다른가
- risk causal chain이 설득력 있는가
- scenario assumptions가 서로 실질적으로 다른가
- conclusion이 evidence 대비 과도하지 않은가
- what-would-make-me-wrong이 실제 반증 조건인가

#### 완료 기준

- critic prompt에서 기계적 체크리스트가 줄어든다.
- 이미 존재하는 `quality_report.py` checks는 유지하고 coverage를 확장한다.
- deterministic failure는 critic 없이 재현된다.
- critic output은 narrative reasoning quality에 집중한다.

---

## 6. Feature 조정

### 6.1 price-only query는 제품 결정으로 분리

#### 문제

현재 정책은 price-only 요청을 의도적으로 거절하고 외부 시세 확인 도구로 리다이렉트하는 방향이다. 따라서 price-only query 지원은 엔지니어링 결함 수정이 아니라 제품 스코프 변경이다.

#### 영향

- 제품성: 에이전트가 심층 투자 분석 도구인지, 시세 조회 도구까지 겸하는지 포지셔닝을 바꾼다.
- 비용: price-only 사용이 늘면 분석 가치 대비 토큰 비용이 왜곡될 수 있다.
- 유지보수성: Mode Q를 추가하면 routing, disclaimer, source freshness, rate-limit 정책이 새로 필요하다.

#### 수정 대상

- `CLAUDE.md`
- `.claude/skills/financial-data-collector/SKILL.md`
- briefing generator

#### 결정 방식

이 항목은 remediation backlog에서 제외하고 별도 제품 ADR로 다룬다. ADR에서 최소 다음 질문에 답한 뒤 채택 여부를 정한다.

- price-only query가 core use case인가?
- 외부 시세 서비스로 redirect하는 현재 정책을 유지할 것인가?
- 지원한다면 전체 분석 pipeline과 완전히 분리된 cheap quote path를 둘 것인가?
- quote output에 투자 disclaimer와 source timestamp를 어떤 강도로 붙일 것인가?

#### 선택적으로 채택할 경우의 Mode 초안

```text
Mode Q: Quote Card

Inputs:
- ticker
- market

Output:
- current price
- day change
- market cap
- currency
- as-of timestamp
- source profile
- short disclaimer
```

#### 완료 기준

- 이 가이드의 필수 개선 범위에서는 Mode Q를 구현하지 않는다.
- 제품 ADR에서 승인된 경우에만 “AAPL 현재가만 알려줘” 요청이 전체 Mode A/C/D로 가지 않게 한다.
- Quote Card는 yfinance 또는 primary price API만 호출한다.
- source timestamp와 disclaimer가 항상 포함된다.

---

### 6.2 Mode A도 최소 disclaimer와 source tag 검사를 유지

#### 문제

Mode A는 간단한 output이라는 이유로 disclaimer와 source tag coverage 일부를 건너뛴다. 짧은 출력일수록 오히려 사용자가 caveat를 놓치기 쉽다.

#### 영향

- 안전성: 투자 관련 짧은 답변이 조언처럼 보일 수 있다.
- 출력 품질: 숫자 출처가 없는 KPI 요약이 생성될 수 있다.
- 유지보수성: mode별 예외가 늘어난다.

#### 수정 대상

- `.claude/skills/quality-checker/SKILL.md`
- `tools/quality_report.py`
- briefing renderer

#### 수정안

Mode A는 full source tag coverage가 아니라 다음만 강제한다.

```text
- 모든 KPI 숫자 옆 source tag
- as-of date
- short disclaimer
- Grade D blank-over-wrong
```

#### 완료 기준

- Mode A HTML에도 disclaimer가 있다.
- Mode A KPI 숫자 3개 모두 source tag 또는 confidence label이 있다.
- Mode A quality gate가 너무 무겁지 않게 유지된다.

---

## 7. 테스트 및 검증 매트릭스

### 7.1 새로 추가할 테스트

#### Renderer tests

```text
tests/test_mode_c_renderer.py

Cases:
- renders DCF section
- renders analyst coverage
- renders Chart.js arrays
- renders quarterly table
- omits unavailable section only when schema permits null
- does not render fixture-only placeholder text
```

#### Rendered output quality tests

```text
tests/test_rendered_output_validation.py

Cases:
- missing disclaimer fails
- missing required heading fails
- Grade D value displayed fails
- source tag coverage below threshold fails
- Mode C chart arrays missing fails
```

#### Path contract tests

```text
tests/test_run_local_paths.py

Cases:
- build_run_paths honors STOCK_ANALYSIS_DATA_DIR
- tier1/tier2 raw paths are run-local
- snapshot paths remain under data/{ticker}
- latest.json points to immutable snapshot artifacts
- fresh latest.json can seed a new run without recollection
- Workflow 2 uses one batch run_id with ticker subdirectories
- contract checks do not create repo output when temp data dir is set
```

#### Data calculation tests

```text
tests/test_dart_ttm.py

Cases:
- Q3 + prior annual + prior Q3 computes true TTM
- Q3 only is labeled YTD proxy
- annual only is labeled latest annual, not TTM
```

```text
tests/test_cashflow_normalization.py

Cases:
- negative source capex yields positive capex_outflow_abs
- positive source capex yields same capex_outflow_abs
- FCF uses operating_cashflow - capex_outflow_abs
- provided source FCF conflict is recorded
```

#### Security tests

```text
tests/test_ingestion_allowed.py

Cases:
- unsanitized fetched raw artifact has ingestion_allowed=false
- strict validation blocks consumed unsanitized artifact
- sanitized artifact passes ingestion check
```

#### Macro collector tests

```text
tests/test_fred_macro_context.py

Cases:
- successful FRED response produces macro_context.structured.status=available
- FRED timeout produces status=unavailable and grade=D
- unavailable FRED data is not rendered as current macro fact
```

### 7.2 CI command set

권장 CI:

```bash
python3 -m unittest discover tests -v
python3 tools/contract_checks.py
python3 tools/eval_harness.py
```

추가할 선택 검사:

```bash
STOCK_ANALYSIS_DATA_DIR="$(mktemp -d)" python3 tools/contract_checks.py
```

완료 기준:

- repo root에 불필요한 `output/` 생성 없음
- fixture 기반 Mode C render snapshot 통과
- unsanitized artifact ingestion block 테스트 통과

---

## 8. 권장 적용 순서

### Phase 0: 데이터 무결성 + 보안

목표: 틀린 숫자와 오염된 외부 텍스트가 사용자 산출물에 들어가는 경로를 먼저 막는다.

작업:

1. sanitization failure를 `ingestion_allowed=false`로 승격
2. consumed unsanitized artifact를 delivery `BLOCKER`로 처리
3. DART true TTM 계산 수정
4. CapEx/FCF 표준 필드 분리
5. prompt example에서 실제 ticker/date/price 제거
6. 관련 회귀 테스트 추가

완료 기준:

- unsanitized fetched artifact는 Analyst 기본 입력으로 들어가지 않는다.
- KR TTM과 FCF 계산 오류가 fixture test로 재현 및 방지된다.
- prompt examples에 실제 기업/날짜/수치가 없다.

### Phase 1: 최종 산출물 품질 계약 강화

목표: JSON artifact뿐 아니라 사용자에게 전달되는 HTML/DOCX까지 품질 게이트에 포함한다.

작업:

1. rendered output validator 추가
2. `analysis-result` schema를 output mode별로 강화
3. delivery severity policy 도입
4. patch 가능한 BLOCKER와 즉시 차단 BLOCKER 구분

완료 기준:

- Mode C 필수 섹션 누락이 schema/eval/rendered validation 중 하나에서 실패한다.
- rendered output missing, unsanitized consumed, schema invalid는 항상 BLOCKED가 된다.
- non-blocking 품질 이슈는 flags와 함께 전달될 수 있다.

### Phase 2: 설계 trade-off 확정 후 구조 변경

목표: 큰 작업에 들어가기 전 캐시와 렌더링 설계의 전제를 명확히 한다.

작업:

1. Mode C renderer ADR 작성
2. 선택된 canonical renderer 경로로 `CLAUDE.md`, skill, analyst 지시 통일
3. run-local → shared snapshot 승격 규칙 설계
4. `latest.json` 기반 staleness reuse 보존
5. `STOCK_ANALYSIS_DATA_DIR` 전면 적용
6. contract checks temp dir isolation

완료 기준:

- renderer 경로가 하나로 통일된다.
- shared cache를 유지하면서 concurrent run artifact 충돌이 없다.
- `STOCK_ANALYSIS_DATA_DIR` 설정 시 repo `output/`에 runtime artifact가 생기지 않는다.

### Phase 3: critic과 tool contract 정리

목표: 모델 판단과 결정론적 검증의 책임을 분리한다.

작업:

1. 기존 `quality_report.py` checks를 확장
2. critic prompt에서 기계적 검사 책임 축소
3. search result와 extracted metric schema 도입
4. `source_profile` / `effective_mode` 도입
5. FRED macro_context status/grade 계약 추가

완료 기준:

- deterministic failure는 critic 없이 재현된다.
- critic은 narrative reasoning quality에 집중한다.
- yfinance fallback과 FRED 실패가 산출물 confidence에 명시된다.

### Phase 4: 토큰/context 효율화

목표: 같은 입력으로 더 싸고 안정적인 분석을 만든다.

작업:

1. Standard Mode yfinance-first로 변경
2. evidence pack 도입
3. Analyst raw artifact 기본 로드 제거
4. `CLAUDE.md` 중복 지시 정리
5. 모델 라우팅 비용 최적화

완료 기준:

- 평균 검색 query 수 감소
- Analyst context payload 감소
- raw artifact를 직접 읽은 경우 이유가 기록된다.

### 유보: 제품 결정 영역

다음 항목은 엔지니어링 remediation 필수 범위에서 제외하고 별도 제품 ADR로 결정한다.

- price-only Mode Q
- `CLAUDE.md`의 공격적 200줄 이하 축소

---

## 9. Definition Of Done

전체 개선 작업이 끝났다고 볼 수 있는 기준은 다음과 같다.

1. unsanitized fetched artifact는 ingestion이 차단된다.
2. DART TTM과 FCF 계산은 테스트로 고정되어 있다.
3. prompt examples에는 실제 기업/날짜/수치가 없다.
4. Mode C final HTML은 선택된 canonical renderer 경로 하나로만 생성된다.
5. quality report는 JSON artifact뿐 아니라 최종 HTML/DOCX를 검증한다.
6. `analysis-result` schema는 output mode별 필수 구조를 강제한다.
7. raw artifact는 run-local path에 저장되고 shared `output/data`는 immutable snapshot/cache와 `latest.json` pointer 전용이다.
8. staleness reuse는 shared `latest.json` pointer를 통해 유지된다.
9. `STOCK_ANALYSIS_DATA_DIR`가 모든 runtime artifact에 적용된다.
10. delivery gate는 severity 기반으로 문서와 코드가 일치한다.
11. Standard Mode는 structured data first, targeted search second로 동작한다.
12. Analyst 기본 context는 validated data와 evidence pack으로 제한된다.
13. FRED macro data의 available/unavailable 상태와 grade가 산출물에 명시된다.
14. critic은 기계적 검사보다 논리 품질 검토에 집중한다.
15. price-only Mode Q는 별도 제품 ADR 없이는 필수 개선 범위에 포함하지 않는다.

이 기준을 만족하면 출력 품질, 비용, 안정성, 유지보수성의 가장 큰 병목은 해소된 것으로 볼 수 있다.
