# ADR 0003 - Research Methodology Update (2026-05-06)

## Status
Accepted

## Context
본 프로젝트는 한국어 retail 투자자 대상 HTML/DOCX 리서치 에이전트로, 10-step orchestrator + source tag A/B/C/D 계약 + prompt-injection sanitization을 핵심 계약으로 삼는다. 2026-05-06 시점 외부 reference material 검토를 통해 우리 5원칙(빈칸>틀린숫자, 출처 없으면 수치 없음, 회사-특수성, 적응형 데이터, 메커니즘 필수)과 정렬되는 methodology를 식별하였다.

## Decision
신규 plugin/skill을 install하지 않는다. 자동 발동 skill이 기존 파이프라인을 shadow하면 contract가 깨질 수 있기 때문이다. 대신 기존 skill/agent 파일에 peer-comp metric discipline, cross-source sanity, moat scorecard, DCF sanity guardrail, valuation reconciliation, delta-mode diff 등 12개 영역의 methodology 보강을 직접 통합한다.

상세 변경 목록은 로컬 plan 파일(`docs/superpowers/plans/2026-05-06-research-methodology-update.md`, gitignored)을 참조한다.

## Consequences
- Pro: 10-step orchestrator, A/B/C/D 등급 계약, sanitization 계약 보존.
- Pro: peer-comp metric discipline, moat scorecard, DCF sanity guardrail, 평가 통합 등 methodology 보강.
- Con: 외부 reference material 업데이트는 자동 추적되지 않음. 다음 재검토 일자: 2026-08-06.
- Con: Excel/.pptx 산출물은 본 프로젝트 범위 밖. 사용자 요청 시 별도 스킬로 분리한다.
