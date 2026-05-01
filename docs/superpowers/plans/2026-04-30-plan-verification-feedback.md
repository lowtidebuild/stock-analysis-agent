# 2026-04-30 Superpowers Plan Verification Feedback

검증 대상:
- `docs/superpowers/plans/2026-04-30-dbnomics-kr-macro.md`
- `docs/superpowers/plans/2026-04-30-reverse-dcf.md`
- `docs/superpowers/plans/2026-04-30-bull-bear-debate.md`

검증 기준:
- 현재 코드베이스의 실제 함수 시그니처, 스키마, validator, artifact path 계약과 대조
- 계획서의 테스트/스모크 명령이 그대로 실행 가능한지 확인
- 외부 의존성은 최신 공개 문서/PyPI/DBnomics provider 목록 기준으로 확인

요약 판정:
- **DBnomics KR Macro**: **BLOCKER - 재설계 필요**. 핵심 전제인 `BOK` provider가 현재 DBnomics provider 목록에 없고, `dbnomics` 패키지 라이선스도 계획서의 MIT가 아니다.
- **Reverse DCF**: **HIGH - 수정 후 구현 가능**. 수학/기능 방향은 좋지만, 테스트 코드가 현재 `compute_dcf()` 반환 타입을 잘못 가정하고 `--reverse` CLI 모드와 실제 구현 지시가 불일치한다.
- **Bull/Bear Debate**: **HIGH - 계약 정리 후 구현 가능**. 아이디어는 유효하지만 pipeline 위치, artifact 등록 위치, CLI/schema/quality-report validator 변경 범위가 계획서 안에서 서로 맞지 않는다.

## 공통 이슈

1. **계획서가 schema/validator 계약을 과소평가한다.**
   - 새 artifact나 새 macro source를 추가하는 경우 `tools/artifact_validation.py`, `.claude/skills/data-validator/scripts/validate-artifacts.py`, 관련 JSON schema, `tools/analysis_contract.py`까지 같이 바뀌어야 한다.
   - 단순히 AGENT.md나 framework 문서만 수정하면 smoke test 단계에서 validator가 막는다.

2. **계획서의 commit 단위가 너무 촘촘하다.**
   - 각 task마다 commit을 요구하는 방식은 구현 중 실패/수정이 반복될 때 히스토리를 지저분하게 만들 수 있다.
   - 권장: chunk 단위 검증 완료 후 의미 있는 commit 1개씩.

3. **`pip3 install --break-system-packages`는 위험하다.**
   - `requirements.txt` 기반 설치를 하더라도 시스템 Python을 직접 깨뜨릴 수 있다.
   - 권장: repo-local virtualenv 또는 기존 프로젝트 설치 절차를 문서화하고, smoke test는 `python3 -m pip`/venv 기준으로 바꾼다.

## DBnomics KR Macro Plan

판정: **BLOCKER - 지금 그대로 구현하면 collector의 live smoke test가 실패할 가능성이 높다.**

### BLOCKER 1 - DBnomics에 `BOK` provider가 없다

계획서는 `BOK/731Y001/0101000` 등 BOK series를 DBnomics에서 직접 가져온다고 가정한다. 하지만 현재 DBnomics provider 목록은 총 93개 provider를 보여주며 `BOK`/`Bank of Korea`가 없다. 목록에는 `BOC`, `BOE`, `BOJ`, `BIS` 등은 있지만 `BOK`는 없다.

영향:
- `fetch_series("BOK", "731Y001", "0101000", ...)`는 provider not found/404 계열로 실패할 가능성이 높다.
- 계획서의 series catalog 전체가 DBnomics series ID가 아니라 BOK ECOS 통계 코드에 가까워 보인다.
- 이 상태에서는 "6 of 8 series collect cleanly" definition of done을 만족하기 어렵다.

권장 수정:
- 선택지 A: 이 계획을 **DBnomics collector**가 아니라 **BOK ECOS collector**로 재명명하고, BOK ECOS Open API를 직접 사용한다.
- 선택지 B: DBnomics를 유지하려면 OECD/IMF/WB/FRED 등 DBnomics에 실제 존재하는 provider로 KR macro proxy series를 다시 매핑한다.
- `dbnomics-series-catalog.md` 작성 전에 provider/dataset/series 조합을 live 검증하는 별도 catalog validator를 먼저 만든다.

### BLOCKER 2 - 라이선스 전제가 틀렸다

계획서는 `dbnomics` Python package를 "MIT license"라고 적었지만, PyPI의 verified metadata는 **AGPLv3+**로 표시된다. DBnomics 웹페이지도 source code license를 AGPL v3로 표시한다.

영향:
- AGPL 계열 dependency는 배포/서비스 형태에 따라 compliance 검토가 필요하다.
- `requirements.txt`에 바로 추가하기 전에 의존성 도입 승인이 필요하다.

권장 수정:
- 계획서 Tech Stack의 MIT 문구를 제거하고 AGPLv3+ compliance decision을 open question이 아니라 precondition으로 올린다.
- 가능하면 HTTP API 직접 호출 방식 또는 다른 permissive client를 검토한다.

### BLOCKER 3 - `sanitize_record()` 호출 시그니처가 현재 코드와 맞지 않는다

현재 `tools/prompt_injection_filter.py`의 `sanitize_record()`는 `(cleaned, findings)` 두 값만 반환한다. 계획서 skeleton은 다음처럼 네 값을 unpack한다.

```python
snapshot, scanned, redactions, findings = sanitize_record(snapshot)
```

영향:
- collector unit test의 `build_snapshot_shape`에서 바로 `ValueError: not enough values to unpack`이 난다.
- 기존 `fred-collector.py`는 `cleaned, sanitization_findings = sanitize_record(record)` 패턴을 사용한다.

권장 수정:
- FRED collector와 동일하게 두 값만 받고 `redactions = len(findings)`로 계산한다.
- `fields_scanned`가 필요하면 sanitizer 자체를 확장하되, FRED collector도 같이 맞춘다.

### HIGH 1 - DBnomics snapshot validator 범위가 부족하다

계획서는 `tools/artifact_validation.py`에서 `"DBnomics"` source를 허용하라고 하지만, 현재 `.claude/schemas/analysis-result.schema.json`도 `sections.macro_context.structured.source` enum을 `["FRED"]`로 제한한다.

영향:
- tier2는 schema가 느슨해서 통과할 수 있어도, final `analysis-result.json`에 DBnomics macro context가 들어가면 schema validation이 실패한다.

권장 수정:
- `.claude/schemas/analysis-result.schema.json` source enum에 `"DBnomics"`를 추가한다.
- `tools/artifact_validation.py`의 error text도 "FRED data" 고정 문구에서 generic macro wording으로 바꾼다.
- 가능하면 `VALID_MACRO_SOURCES = {"FRED", "DBnomics"}` 상수로 schema와 validator를 동기화한다.

### HIGH 2 - `DBNOMICS_API_KEY` 전제가 근거 없다

PyPI 문서는 `api_base_url` customizing은 설명하지만 `DBNOMICS_API_KEY`나 API key priority는 설명하지 않는다. 계획서의 `api_key` 인자는 skeleton에서도 실제 `fetch_series()` 호출에 전달되지 않는다.

권장 수정:
- API key 로직은 제거하거나, 실제 DBnomics 인증/rate-limit 문서가 확인된 뒤 추가한다.
- `DBNOMICS_PROVIDER_OVERRIDE`도 현재 skeleton에서 사용되지 않으므로 제거하거나 구현한다.

### HIGH 3 - cache/fallback 동작이 FRED와 다르다

계획서 상단은 "stale cache but refresh fails -> stale data"라고 쓰지만 skeleton은 ImportError나 all-series failure에서 stale cache fallback을 구현하지 않는다.

권장 수정:
- `fred-collector.py`의 `check_cache()`, `failed_using_stale`, `cache_stale`, `cache_very_stale` 패턴을 그대로 포팅한다.
- top-level `api_status` 값도 FRED와 맞춰 `"failed"`를 쓰거나 validator가 `"fail"`을 허용하도록 명시한다.

### MEDIUM - 출력 구조의 `sector` vs `sector_specific` 명칭이 혼재한다

Top-level snapshot은 `sector`, structured macro는 `sector_specific`을 쓴다. 현재 FRED와 맞추려면 괜찮지만, KR dashboard spec은 `sector.consumer.kr_consumer_sentiment.value`처럼 structured 내부에서 top-level `sector`를 참조하는 표현이 섞여 있다.

권장 수정:
- renderer가 읽을 canonical path를 하나로 고정한다. 예: `macro_context.structured.sector_specific.consumer.consumer_sentiment`.

## Reverse DCF Plan

판정: **HIGH - 구현 방향은 좋지만 테스트와 CLI 계약을 고쳐야 한다.**

### HIGH 1 - 테스트 코드가 현재 `compute_dcf()` 반환 타입과 맞지 않는다

현재 `compute_dcf()`는 `(results_dict, errors_list)` tuple을 반환한다. 계획서 테스트는 다음처럼 dict 반환을 가정한다.

```python
forward = dcf.compute_dcf(**inputs)
target_price = forward["fair_value_per_share"]
```

영향:
- 첫 테스트가 의도한 `AttributeError: solve_implied_growth missing`으로 실패하지 않고 tuple indexing/type error로 실패한다.
- edge-case tests의 `forward_max = dcf.compute_dcf(... )["fair_value_per_share"]`도 동일하게 깨진다.

권장 수정:
- 테스트는 `forward, errors = dcf.compute_dcf(**inputs)`로 받는다.
- `assert errors == []` 또는 non-fatal warning 허용 여부를 명시한다.

### HIGH 2 - `--reverse` CLI 모드와 실제 구현 지시가 불일치한다

Goal/File Structure는 `--reverse` CLI mode를 추가한다고 하지만, Task 4는 CLI flag를 만들지 않고 `current_price_for_reverse` input field만 추가한다.

권장 수정:
- 둘 중 하나로 통일한다.
  - 단순한 방향: `--reverse` 용어를 계획서에서 제거하고 "optional reverse block via `current_price_for_reverse`"로 정리한다.
  - 명시적 CLI 방향: `--reverse` flag를 추가하고, flag가 없으면 reverse block을 계산하지 않게 한다.

### HIGH 3 - `current_price_for_reverse` guard가 edge status를 숨긴다

계획서 snippet:

```python
if current_price_for_reverse and fcf_ttm and diluted_shares and wacc:
```

영향:
- `fcf_ttm == 0`이면 solver를 호출하지 않아 `negative_fcf` status가 출력되지 않는다.
- `target_price == 0`, `wacc == 0` 등도 조용히 skip된다.

권장 수정:
- truthiness 대신 `is not None` 검사를 쓴다.
- solver가 모든 invalid input을 명시 status로 반환하게 하고, `calculate_dcf()`는 그 결과를 `reverse_dcf`에 보존한다.

### MEDIUM 1 - 성공 조건과 tolerance 설명이 불일치한다

문서의 수학 계약은 "interval width < 0.0005 (5bp)"라고 되어 있는데, skeleton은 price-relative tolerance `target_price * 0.0005`와 interval width `<0.00005`를 같이 사용한다.

권장 수정:
- 목표를 하나로 정한다. 추천: growth-rate interval tolerance를 `0.0005`로 쓰고, price tolerance는 별도 optional convergence check로 둔다.

### MEDIUM 2 - test count가 틀렸다

Happy path 1개에 edge-case 4개를 append하면 총 5개 테스트다. 계획서는 "Expected: 4 PASS"라고 되어 있다.

권장 수정:
- "Expected: 5 PASS"로 수정한다.

### MEDIUM 3 - `OUTPUT_SCHEMA`도 업데이트가 필요하다

계획서는 input schema만 확장한다. 하지만 `--schema` 출력은 `OUTPUT_SCHEMA`도 보여주므로 `reverse_dcf`/`implied_fcf_growth` 출력 계약을 같이 추가해야 한다.

권장 수정:
- `OUTPUT_SCHEMA`에 `reverse_dcf`를 추가하고 status enum/nullable fields를 문서화한다.

### MEDIUM 4 - manual PLTR artifact edit는 재현성이 낮다

Chunk 3에서 기존 `analysis-result.json`을 수동 수정하라고 되어 있다. smoke test로는 가능하지만 definition of done으로는 약하다.

권장 수정:
- 최소한 fixture JSON을 만들어 renderer input으로 쓰는 deterministic smoke test를 추가한다.
- output HTML은 gitignored라도, `tools`/renderer가 어떤 JSON path를 읽는지 명시한다.

## Bull/Bear Debate Plan

판정: **HIGH - 컨셉은 좋지만 pipeline 계약이 서로 충돌한다.**

### HIGH 1 - debate 위치가 문서 안에서 서로 모순된다

Goal/Architecture는 "Analyst first draft 이후, Critic 전" 및 "Analyst re-dispatch"를 말한다. 그런데 design decision과 CLAUDE.md patch 지시는 "Step 6.5, Validation 이후 Analyst 초안 전"이라고 한다. Agent prompt도 "Analyst draft does not exist yet"이라고 한다.

영향:
- 구현자가 debate를 Analyst 전/후 어디에 넣어야 하는지 결정할 수 없다.
- "refined Variant View Q1"과 "initial Variant View Q1"의 artifact 흐름이 달라진다.
- 비용/timeout/quality loop 계산도 달라진다.

권장 수정:
- v1은 **Validation 이후, Analyst 전**으로 단순화하는 것을 추천한다.
- 그러면 "first draft", "re-dispatch Analyst", "refined" 표현을 모두 제거한다.
- 반대로 after-first-draft를 유지하려면 `analysis-result.draft.json` 또는 patch-plan artifact가 필요하다.

### HIGH 2 - artifact-manager 수정 위치가 틀렸다

계획서는 `.claude/skills/data-manager/scripts/artifact-manager.py`에서 per-ticker artifact dict를 수정하라고 하지만, 현재 path 목록은 `tools/analysis_contract.py::build_run_paths()`가 만든다. `artifact-manager.py`는 그 결과를 `relativize_paths()`로 받아 manifest에 넣을 뿐이다.

권장 수정:
- `tools/analysis_contract.py::build_run_paths()`에 `bull_thesis`/`bear_thesis`를 추가한다.
- 그 다음 `artifact-manager.py init`으로 manifest에 반영되는지 확인한다.

### HIGH 3 - `validate-artifacts.py --artifact-type bull-thesis`는 계획서 변경만으로 동작하지 않는다

계획서는 `tools/artifact_validation.py`의 `SCHEMA_ARTIFACT_TYPES`만 추가하라고 한다. 그러나 CLI choices는 `.claude/skills/data-validator/scripts/validate-artifacts.py`에 별도로 고정되어 있다.

영향:
- schema 파일과 validation 함수가 있어도 CLI에서 `invalid choice: 'bull-thesis'`가 난다.

권장 수정:
- `.claude/skills/data-validator/scripts/validate-artifacts.py` choices에도 `bull-thesis`, `bear-thesis`를 추가한다.
- `validate_run_directory()`의 optional artifact specs에도 추가할지 결정한다.

### HIGH 4 - quality-report schema/validator allowed item 업데이트가 빠져 있다

계획서는 Critic AGENT.md의 allowed item list에 `debate_integration_test`를 추가하라고만 한다. 하지만 실제 검증은 다음 위치에서도 enum/set으로 막힌다.

- `.claude/schemas/quality-report.schema.json`의 `critic_review.items[].item` enum
- `tools/artifact_validation.py::CRITIC_REVIEW_ALLOWED_ITEMS`

영향:
- Critic이 `debate_integration_test`를 출력하면 quality-report validation이 실패한다.

권장 수정:
- AGENT.md, schema, validator의 allowed item set을 모두 같이 수정한다.

### HIGH 5 - schema와 agent failure mode가 충돌한다

`bull-thesis.schema.json`은 `top_3_arguments`에 `minItems: 2`를 요구한다. 하지만 bull agent failure mode는 insufficient evidence일 때 `top_3_arguments`를 "single entry"로 남기라고 한다.

영향:
- failure artifact가 schema를 통과하지 못한다.

권장 수정:
- schema에 `status` field를 추가하고 `status == "blocked_insufficient_evidence"`일 때 별도 `data_gap_summary`를 허용한다.
- 또는 failure mode에서도 placeholder가 아닌 2개 이상의 evidence-gap argument를 쓰도록 명시한다.

### HIGH 6 - 계획서의 shell JSON 검증 명령이 invalid JSON이다

Task 2 verification command는 JSON 문자열 안에 `"x"*40`, `"z"*40`를 넣는다. 이것은 Python 표현식이지 JSON이 아니다.

영향:
- `json.load(sys.stdin)` 단계에서 바로 실패한다.

권장 수정:
- heredoc으로 Python에서 payload를 만들거나, 실제 반복된 문자열을 JSON에 넣는다.

### MEDIUM 1 - `quality-report.debate_status` 위치가 schema에 정의되지 않았다

Failure handling은 `quality-report.debate_status`를 요구한다. 현재 quality-report schema는 additionalProperties를 허용하므로 완전히 막히지는 않지만, deterministic builder가 이 값을 생성/보존한다는 보장이 없다.

권장 수정:
- `analysis-result.debate_integration_status`와 `quality-report.critic_review` 중 어느 곳이 canonical인지 정한다.
- quality-report builder가 debate_status를 보존/계산하도록 할지 명시한다.

### MEDIUM 2 - CLAUDE.md Quality Gate Summary도 같이 업데이트해야 한다

계획서는 Step 6.5와 dispatch table은 수정하지만, CLAUDE.md의 "Critic 7-item review" 요약은 그대로 남는다.

권장 수정:
- Critic review count/목록을 업데이트하거나, "narrative critic items"로 일반화한다.

## 권장 실행 순서

1. **DBnomics 계획은 보류**한다.
   - 먼저 BOK 데이터를 DBnomics로 가져올지, BOK ECOS 직접 collector로 갈지 결정한다.
   - AGPLv3+ dependency 허용 여부를 결정한다.
   - 이 결정 전에는 `requirements.txt`에 `dbnomics`를 추가하지 않는다.

2. **Reverse DCF를 먼저 구현**한다.
   - 외부 의존성이 없고 blast radius가 작다.
   - 단, 테스트 snippet과 CLI 계약을 고친 뒤 시작한다.

3. **Bull/Bear Debate는 artifact/quality 계약부터 정리**한다.
   - pipeline 위치를 하나로 확정한다.
   - `tools/analysis_contract.py`, CLI choices, schema, validator, quality-report enum을 먼저 업데이트한다.
   - 그 다음 agent prompts와 framework 문서를 수정한다.

## 외부 확인 출처

- DBnomics provider list: https://db.nomics.world/providers
  - 현재 provider 목록에서 `BOK`/`Bank of Korea`가 검색되지 않음.
- DBnomics Python package PyPI: https://pypi.org/project/dbnomics/
  - 최신 릴리스 1.2.7, license metadata는 AGPLv3+, `Requires: Python >=3.11`.
  - 문서에는 `api_base_url` customization이 설명되어 있으나 `DBNOMICS_API_KEY` priority는 확인되지 않음.

