# Release Notes — 2026-04-18

This is a bilingual companion note for the larger update published on `main` at commit `a4c7970`.

## Action Required

### English

- Please pull the latest changes from `main`.
- The remote `master` branch has been removed. If you still have a local `master`, switch to `main`.

```bash
git checkout main
git pull origin main
```

### 한국어

- 최신 변경 사항을 받으려면 `main` 브랜치에서 pull 해주세요.
- 원격 `master` 브랜치는 제거되었습니다. 아직 로컬에서 `master`를 쓰고 있다면 `main`으로 전환해 주세요.

```bash
git checkout main
git pull origin main
```

## English Summary

- Trust-boundary hardening is now in place for fetched artifacts. We added prompt-injection sanitization, `_sanitization` metadata, and validator enforcement for unsanitized raw inputs.
- Run-local artifact contracts were added for `research-plan`, `validated-data`, `analysis-result`, `quality-report`, `patch-plan`, `analysis-patch`, and `patch-loop-result`.
- The analyst/critic patch loop is now part of the workflow, including patch-plan validation, patch application, critic recheck merge, delivery gating, and eval coverage.
- Output and workflow tooling were refreshed: scripted Mode B comparison rendering, updated Mode A/C/D renderer docs, and better run-local artifact handling.
- CI/local verification is easier now because `tools/contract_checks.py` can materialize missing runtime fixtures from in-repo eval samples.
- Repository hygiene was improved: sensitive historical material was removed from git history, the remote now uses `main` only, and the repo is aligned around the clean active working copy.

## 한국어 요약

- 수집 아티팩트에 대한 신뢰 경계 보강이 적용되었습니다. 프롬프트 인젝션 sanitization, `_sanitization` 메타데이터, 그리고 미정제(raw) 입력에 대한 validator 강등 처리까지 포함됩니다.
- `research-plan`, `validated-data`, `analysis-result`, `quality-report`, `patch-plan`, `analysis-patch`, `patch-loop-result`에 대한 run-local 아티팩트 계약(schema/contract)이 추가되었습니다.
- 이제 analyst/critic patch loop가 정식 워크플로에 포함됩니다. patch-plan 검증, patch 적용, critic 재검토 병합, 전달 게이트, eval 커버리지가 함께 들어갔습니다.
- 출력/워크플로 도구도 정비했습니다. 스크립트 기반 Mode B 비교 렌더링, Mode A/C/D 렌더러 문서 업데이트, run-local 아티팩트 처리 개선이 포함됩니다.
- `tools/contract_checks.py`가 저장소 내 eval fixture를 활용해 누락된 런타임 샘플을 보완할 수 있게 되어, CI와 로컬 검증이 더 쉬워졌습니다.
- 저장소 위생도 개선했습니다. 민감한 과거 이력은 git history에서 제거했고, 원격은 `main`만 사용하도록 정리했으며, 활성 작업 레포 기준으로 구조를 맞췄습니다.

## Validation

- `python3 -m unittest discover tests -v`
- `python3 tools/contract_checks.py`

## References

- Detailed note: `docs/releases/2026-04-17-security-and-contracts.md`
- Published head: `a4c7970`
