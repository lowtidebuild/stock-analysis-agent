# ADR 0001: Mode C 렌더링 전략

작성일: 2026-04-24
상태: Accepted
관련 가이드: `docs/agent-audit-remediation-guide.ko.md` Phase 2

## 맥락

Mode C 최종 HTML은 사용자가 실제로 받는 핵심 산출물이다. 현재 `.claude/skills/dashboard-generator/references/html-template.md`는 DCF, analyst coverage, macro, peer table, chart 영역을 포함한 완전한 템플릿이다.

반면 `.claude/skills/dashboard-generator/scripts/render-dashboard.py`는 contract/eval용 MVP에 가깝다. 이 스크립트는 일부 섹션을 정적으로 처리하거나 누락하고, rich analyst output과 다른 필드 형태를 기대한다. 따라서 patch loop에서 이 스크립트를 자동 실행하면, 풍부한 HTML이 얕은 대시보드로 퇴행할 수 있다.

## 결정

단기 canonical 경로는 Option B로 한다.

- Mode C 사용자 전달 HTML은 `html-template.md`를 기준으로 생성한다.
- `render-dashboard.py`는 eval/schema smoke 용도로만 둔다.
- critic patch loop는 Mode C에서 `render-dashboard.py`를 호출하지 않는다.
- patch loop가 Mode C analysis-result를 수정한 경우 render status는 `manual_render_required`가 된다.
- `manual_render_required` 상태는 redelivery ready가 아니다. patched `analysis-result.json`으로 전체 `html-template.md`를 다시 채운 뒤 rendered output validator를 통과해야 전달할 수 있다.

## 제외한 선택지

Option A, `render-dashboard.py` 전면 재작성은 지금 바로 채택하지 않는다. 필요한 작업량이 크고, 기존 MVP 스크립트를 부분 보강하면 최종 렌더러와 eval helper 책임이 다시 섞일 위험이 크다.

Option C, template engine 도입은 장기 후보로 남긴다. 도입 전에는 schema, rendered output validator, snapshot fixture가 안정되어야 한다.

## 구현 규칙

- `CLAUDE.md`, dashboard skill, analyst patch-loop 문서는 모두 `html-template.md`를 final delivery 기준으로 가리켜야 한다.
- Mode C patch-loop 자동 렌더는 금지한다.
- `patch-loop-result.render.status = "manual_render_required"`이면 `quality_gate.delivery_ready = false`여야 한다.
- Mode C rendered output validator는 DCF, analyst coverage, chart data, disclaimer 누락을 계속 차단한다.

## 후속 작업

1. `render-dashboard.py`를 계속 유지할 경우 파일 상단과 CLI 출력에 eval-only 경고를 추가한다.
2. template engine을 도입하려면 별도 ADR에서 의존성, snapshot test, renderer ownership을 먼저 확정한다.
3. Mode C HTML snapshot fixture를 추가해 full template 구조가 퇴행하지 않도록 한다.
