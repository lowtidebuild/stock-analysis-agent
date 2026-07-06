# Code Review Fixes — Implementation Plan

> **For Codex (implementation agent):** 이 문서는 2026-07-06 코드 리뷰(범위:
> `fd99fd9`(Codex-native A/B/C runner) + `f659730`(security audit) 두 커밋)에서
> 확인된 결함 14건의 수정 계획이다. Task 순서대로 구현하고, Task마다 체크박스
> (`- [ ]`)를 갱신하며, **Task 단위로 커밋**한다. 각 Task는 독립적으로
> 테스트 가능해야 한다. 모든 findings는 검증 에이전트가 코드에서 직접
> 재확인(CONFIRMED)한 것이며, 각 항목에 근거 file:line을 남겨 두었다.

**Goal:** 리뷰에서 확인된 배포 무결성·보안·계약 위반 10건과 구조적 중복 4건을
회귀 테스트와 함께 수정한다.

**Architecture:** 기존 파이프라인 구조(run_mode.py 엔트리포인트 → parity 모듈 →
quality_report 게이트)는 유지한다. 새 모듈은 `tools/backend_providers.py`
(공유 상수) 하나만 추가한다. 나머지는 기존 파일의 국소 수정이다.

**Tech Stack:** Python 3.11+, pytest. 외부 의존성 추가 없음.

**전역 규칙 (모든 Task 공통):**
1. TDD: 실패하는 테스트 먼저 → 최소 구현 → 통과 확인 → 커밋.
2. 실행 전 기준선: `python3 -m pytest tests/ -q` 가 현재 GREEN인지 확인하고
   시작한다. 각 Task 완료 시에도 전체 suite GREEN 유지.
3. CLAUDE.md 준수: Section 7.1(모델 라우팅), Section 8(심각도 기반 배포),
   Section 10(경로 계약), Section 12(신뢰 경계). `.env*` 파일은 절대 읽지
   않는다(테스트 픽스처는 tmp_path에 생성).
4. 커밋 메시지는 기존 관례(`fix:`, `feat:`, `refactor:` + 소문자 요약)를 따른다.

---

## Chunk 1 — Phase 0: 배포 무결성 · 보안 (P0, 필수)

### Task 1: Mode C 대시보드 누락 섹션 3개 복원

**현상** (CONFIRMED): `build_mode_c_dashboard_html`의 `<main>` 블록에서
`render_quality_gate_section` / `render_portfolio_section` /
`render_source_appendix` 호출 3줄이 삭제되어
([scripts/parity/rendering.py:978-987](../../scripts/parity/rendering.py#L978-L987),
HEAD~2에는 784-786행에 존재), 세 함수(현재 1411/1474/1498행)가 죽은 코드가
됐다. analyst는 여전히 `sections.portfolio_strategy`(analyst.py:743, 955)와
`source_tagged_claims`(analyst.py:745, 957)를 생성하므로, 배포 HTML에서
포트폴리오 전략·이익 품질 게이트·클레임별 출처 태그 표가 조용히 사라진다.
같은 커밋의 테스트(tests/test_abc_parity_rendering.py:221-226)는 이 문자열들을
**금지 목록**에 넣어 누락을 고착화했다.

**Files:**
- Modify: `scripts/parity/rendering.py` (`build_mode_c_dashboard_html`의 `<main>` 블록)
- Modify: `tests/test_abc_parity_rendering.py`

**Steps:**

- [x] **1-1. 테스트 수정 (RED 확인):** `tests/test_abc_parity_rendering.py`의
  영어 렌더 기대 목록에 `"Portfolio Strategy"`, `"Source-Tagged Claims Appendix"`,
  `"Quality of Earnings"`(quality gate 섹션의 실제 헤딩 문자열은 함수 구현에서
  확인)를 **required**로 옮기고, 한국어 렌더 기대 목록(195행 부근)에
  `"포트폴리오 전략"`, `"출처 태그 클레임 부록"`, `"이익 품질 및 증거 게이트"`를
  추가한다. 금지 목록(214행 이후)에서는 해당 문자열을 제거하되, 언어 교차
  금지(한국어 렌더에 영어 헤딩 금지)는 유지한다.
  실행: `python3 -m pytest tests/test_abc_parity_rendering.py -q` → **FAIL** 확인.
- [x] **1-2. 렌더 호출 복원:** `build_mode_c_dashboard_html`의 `<main>` 블록에서
  `{render_financial_detail_section(...)}` 다음에 HEAD~2와 동일한 순서로 복원:
  ```python
      {render_quality_gate_section(analysis, calculations, evidence, validated)}
      {render_portfolio_section(analysis, sections, scenarios)}
      {render_source_appendix(source_claims)}
  ```
  주의: 함수 시그니처가 리팩터링 과정에서 바뀌었을 수 있으니 현재 정의
  (1411/1474/1498행)의 파라미터에 맞춰 호출한다. `source_claims` 변수가
  현재 함수 스코프에 없다면 HEAD~2 (`git show HEAD~2:scripts/parity/rendering.py`)
  에서 그 도출부도 함께 복원한다.
- [x] **1-3.** `python3 -m pytest tests/test_abc_parity_rendering.py -q` → PASS.
- [x] **1-4.** 전체 suite: `python3 -m pytest tests/ -q` → GREEN.
- [x] **1-5. Commit:** `fix(rendering): restore portfolio, quality-gate, and source-appendix sections in mode c dashboard`

### Task 2: Mode C 골든 게이트 정상화

**현상** (CONFIRMED): 같은 diff에서
(a) `DEFAULT_GOLDEN_CONFIG`의 `body_text_chars` 10000→5000,
`html_byte_size` 50000→40000으로 하향([rendering.py:19,21](../../scripts/parity/rendering.py#L19)),
(b) 신설된 `normalize_public_mode_c_golden_config`(1770-1783행)가
`min(설정값, 기본값)`으로 **더 엄격한 운영자 설정을 하향 클램프**하고
(설정값 0이 들어오면 `min(0, 5000)=0`으로 검사 자체가 꺼짐),
(c) `id == "portfolio"` 헤딩 그룹을 외부 설정에서도 무조건 제거하며,
(d) `required_heading_groups` 키가 없으면 `or []`로 빈 리스트가 되어
1696행 검증 루프가 아무것도 검사하지 않는다.
결과: hollow 대시보드를 잡으라고 만든 게이트가 무력화됐다
(ADR: docs/adr/0001-mode-c-rendering-strategy.ko.md).

**Files:**
- Modify: `scripts/parity/rendering.py` (`DEFAULT_GOLDEN_CONFIG`, `normalize_public_mode_c_golden_config`)
- Test: `tests/test_abc_parity_rendering.py` (신규 테스트 함수 추가)

**Steps:**

- [x] **2-1. 실패 테스트 작성:**
  ```python
  def test_golden_config_normalization_never_weakens() -> None:
      from scripts.parity.rendering import (
          DEFAULT_GOLDEN_CONFIG,
          normalize_public_mode_c_golden_config,
      )
      # (1) 더 엄격한 운영자 설정은 그대로 존중된다
      strict = normalize_public_mode_c_golden_config(
          {"minimums": {"body_text_chars": 12000, "html_byte_size": 60000}}
      )
      assert strict["minimums"]["body_text_chars"] == 12000
      assert strict["minimums"]["html_byte_size"] == 60000
      # (2) 0 / 누락값은 기본값으로 바닥이 깔린다 (검사 비활성화 불가)
      zeroed = normalize_public_mode_c_golden_config(
          {"minimums": {"body_text_chars": 0}}
      )
      assert zeroed["minimums"]["body_text_chars"] == DEFAULT_GOLDEN_CONFIG["minimums"]["body_text_chars"]
      # (3) required_heading_groups 누락 시 기본 그룹으로 폴백 (빈 리스트 금지)
      fallback = normalize_public_mode_c_golden_config({})
      assert fallback["required_heading_groups"] == DEFAULT_GOLDEN_CONFIG["required_heading_groups"]
      assert any(g.get("id") == "portfolio" for g in fallback["required_heading_groups"])
      # (4) 외부 설정의 portfolio 그룹을 임의로 제거하지 않는다
      keep = normalize_public_mode_c_golden_config(
          {"required_heading_groups": [{"id": "portfolio", "pattern": "Portfolio Strategy|포트폴리오 전략"}]}
      )
      assert any(g.get("id") == "portfolio" for g in keep["required_heading_groups"])
  ```
  실행 → **FAIL** 확인.
- [x] **2-2. 구현:**
  - `DEFAULT_GOLDEN_CONFIG`를 HEAD~2 값으로 복원: `body_text_chars: 10000`,
    `html_byte_size: 50000`, `required_heading_groups`에
    `{"id": "portfolio", "pattern": "Portfolio Strategy|포트폴리오 전략"}` 재추가.
  - `normalize_public_mode_c_golden_config`를 다음 의미로 재작성
    ("정규화는 절대 게이트를 약화시키지 않는다"):
    ```python
    def normalize_public_mode_c_golden_config(config: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(config)
        minimums = dict(DEFAULT_GOLDEN_CONFIG["minimums"])
        minimums.update(config.get("minimums") or {})
        for key in ("body_text_chars", "html_byte_size"):
            configured = int(minimums.get(key) or 0)
            minimums[key] = max(configured, DEFAULT_GOLDEN_CONFIG["minimums"][key])
        normalized["minimums"] = minimums
        groups = config.get("required_heading_groups")
        normalized["required_heading_groups"] = (
            list(groups) if groups else list(DEFAULT_GOLDEN_CONFIG["required_heading_groups"])
        )
        return normalized
    ```
  - 주의: Task 1이 먼저 머지되어 있어야 한다 — portfolio 헤딩을 다시 요구하는
    순간 렌더에 해당 섹션이 실제로 존재해야 게이트가 통과한다.
- [x] **2-3.** 신규 테스트 + `tests/test_abc_parity_rendering.py` 전체 PASS 확인.
- [x] **2-4.** 리포 내 골든 설정 파일(`web/data/golden/mode-c-parity.json`이
  존재하는 경우)의 값이 구 기준(10000/50000, portfolio 그룹 포함)과 일치하는지
  확인하고, 하향된 값이 있으면 복원한다.
- [x] **2-5. Commit:** `fix(rendering): golden gate normalization floors at defaults instead of clamping down`

### Task 3: 백엔드 provider 집합 단일화 + codex_native 배포 게이트

**현상** (CONFIRMED ×2):
(a) `FIXTURE_BACKEND_PROVIDERS = {"fixture", "deterministic_fixture", "local_fixture"}`
가 3곳에 중복 정의: [scripts/run_mode_common.py:14](../../scripts/run_mode_common.py#L14),
[tools/quality_report.py:62](../../tools/quality_report.py#L62),
[scripts/parity/analyst.py:30](../../scripts/parity/analyst.py#L30)(`FIXTURE_BACKEND_NAMES`).
각각 run_profile 스탬핑·배포 게이트·백엔드 선택을 좌우하므로 드리프트 = 버그.
(b) 완전 결정론적 템플릿 백엔드 `codex_native`(analyst.py:770-983, LLM 호출 0회,
`verdict_from_rr`로 최종 verdict 결정, 4개 티커 외 범용 보일러플레이트 —
`company_domain_profile` analyst.py:1093-1103)가 이 집합에 없어
`run_profile="production"`으로 스탬프되고(run_mode_common.py:56)
`fixture_delivery_guard`를 그대로 통과한다(quality_report.py:1093-1100).
CLAUDE.md §7.1("결정론적 전처리는 최종 verdict를 정할 수 없다") 및
원칙 3(회사-특수성) 위반. RUNBOOK(225-235행)이 이 동작을 의도로 문서화했으나,
게이트/표식 없는 production 배포는 계약 위반이므로 **명시적 opt-in + 가시적
표식**으로 바꾼다.

**설계 결정:**
- `codex_native`는 fixture가 아니라 **deterministic** 클래스로 구분한다
  (fixture = 가짜 데이터, deterministic = 실데이터 + 템플릿 서사).
- run_profile 값: `"deterministic"` (기존: production / smoke).
- 배포 게이트: deterministic 프로파일은 기본 **BLOCKER**,
  `blocker_action="terminal"` (패치 루프로 해소 불가 — 입력/백엔드 교체가
  필요하므로 terminal로 분류; CLAUDE.md §8은 patchable|terminal 이분법만
  허용한다). 단 `--allow-deterministic-delivery` 플래그(신규)로 opt-in 시
  `PASS_WITH_FLAGS`(MINOR) + 경고 문구. 기존 `--allow-fixture-delivery`의
  opt-in 분기 패턴(quality_report.py의 `build_fixture_delivery_guard_item`
  내부 ~1102-1112행)을 따른다.
- opt-in 배포 시 analysis-result의 `verdict` 필드는 유지하되
  `run_context.verdict_provenance = "deterministic_rule"`을 기록하고,
  렌더된 HTML 상단(헤더 아래 첫 요소)에 배너를 추가한다:
  ko: `"본 리포트는 LLM 분석 없이 검증 지표 기반 결정론적 템플릿으로 생성되었습니다. 투자 판단(verdict)은 규칙 기반 산출값입니다."`
  en: `"This report was generated from a deterministic template without LLM analysis; the verdict is rule-derived."`

**Files:**
- Create: `tools/backend_providers.py`
- Modify: `scripts/run_mode_common.py`, `tools/quality_report.py`,
  `scripts/parity/analyst.py`, `scripts/run_mode.py`(플래그 추가·전달),
  `scripts/run_mode_c_impl.py`(플래그 전달), `scripts/parity/rendering.py`(배너),
  `docs/codex/RUNBOOK.md`(문서 갱신)
- Test: `tests/test_run_mode_entrypoint.py`, `tests/test_quality_report_numeric_sanity.py`
  또는 신규 `tests/test_deterministic_delivery_guard.py`

**Steps:**

- [x] **3-1. 공유 상수 모듈 생성:**
  ```python
  # tools/backend_providers.py
  """Single source of truth for analyst-backend provider classes.

  FIXTURE: synthetic/fixture data paths - never production-deliverable.
  DETERMINISTIC: real validated data, template narrative, rule-based verdict -
  deliverable only with explicit opt-in and a visible disclosure banner.
  """
  FIXTURE_BACKEND_PROVIDERS: frozenset[str] = frozenset(
      {"fixture", "deterministic_fixture", "local_fixture"}
  )
  DETERMINISTIC_BACKEND_PROVIDERS: frozenset[str] = frozenset({"codex_native"})
  ```
- [x] **3-2.** 3곳의 로컬 정의를 삭제하고 import로 교체
  (`from tools.backend_providers import FIXTURE_BACKEND_PROVIDERS`;
  analyst.py의 `FIXTURE_BACKEND_NAMES`는 alias 유지 가능:
  `FIXTURE_BACKEND_NAMES = FIXTURE_BACKEND_PROVIDERS`).
  `python3 -m pytest tests/ -q` → GREEN (동작 불변 리팩터링).
  Commit: `refactor: single-source fixture backend provider set`
- [x] **3-3. 실패 테스트 작성** (신규 `tests/test_deterministic_delivery_guard.py`):
  - `annotate_analysis_run_profile`가 provider `codex_native`에 대해
    `run_profile == "deterministic"`을 기록한다.
  - `build_fixture_delivery_guard_item`(또는 신설
    `build_deterministic_delivery_guard_item`)이 deterministic 프로파일 +
    opt-in 없음 → `status FAIL / severity BLOCKER / blocker_action terminal`.
  - opt-in(`run_context.allow_deterministic_delivery is True`) →
    `status PASS_WITH_FLAGS / severity MINOR`.
  - fixture 백엔드 동작(기존 테스트)은 불변.
  실행 → FAIL 확인.
- [x] **3-4. 구현:**
  - `run_mode_common.annotate_analysis_run_profile`(56행 부근): provider가
    `DETERMINISTIC_BACKEND_PROVIDERS`에 있으면 `run_profile="deterministic"`,
    `run_context.verdict_provenance="deterministic_rule"` 기록.
  - `quality_report.build_fixture_delivery_guard_item`(1069행 부근):
    `deterministic_profile = run_profile == "deterministic"` 분기 추가 —
    구조는 기존 fixture 분기와 동일, opt-in 키만
    `allow_deterministic_delivery`.
  - `run_mode.py` parse_args에 `--allow-deterministic-delivery`
    (`action="store_true"`) 추가, 기존 `--allow-fixture-delivery`가
    run_context로 전달되는 경로(grep으로 확인)와 동일하게 전달.
  - `rendering.py`: `analysis.run_context.run_profile == "deterministic"`일 때
    Mode A/B/C 렌더 헤더 직후 배너 div 삽입(위 문구, ko/en은 `language` 인자로 분기).
- [x] **3-5.** 신규 테스트 PASS + 전체 suite GREEN.
- [x] **3-6.** `docs/codex/RUNBOOK.md`의 codex_native 안내(69, 111, 225-235행 등
  `run_profile=production` 서술)를 `deterministic` + opt-in 플래그 설명으로 갱신.
- [x] **3-7. Commit:** `feat(gate): classify codex_native as deterministic profile with explicit delivery opt-in`

### Task 4: security_audit — `.env.*` 스테이징 전면 차단

**현상** (CONFIRMED): [tools/security_audit.py:51-60](../../tools/security_audit.py#L51-L60)
의 `FORBIDDEN_STAGED_PATTERNS`는 `.env`, `.env.local`, `.env.*.local`만 커버 —
`.env.production` / `.env.staging`은 fnmatch에 걸리지 않는다. 동시에
`NEVER_READ_PATTERNS`(47-50행)의 `.env.*` 때문에 내용 스캔도 스킵되어
WARN(`skipped_sensitive_path`)만 남고, 기본 플래그(`--fail-on-warn` 없음)에서는
exit 0(388-392행) → 실제 시크릿 파일이 감사 통과 상태로 커밋된다.

**Files:**
- Modify: `tools/security_audit.py`
- Test: `tests/test_security_audit.py`

**Steps:**

- [x] **4-1. 실패 테스트 작성** (기존 테스트 파일의 픽스처 패턴 재사용):
  ```python
  @pytest.mark.parametrize(
      "name",
      [".env.production", ".env.staging", ".env.dev", "config/.env.production"],
  )
  def test_staged_env_variants_are_forbidden(name, ...):
      # staged file list에 name을 넣고 run_audit 실행
      # → severity ERROR, rule "forbidden_staged_path" finding 존재, exit != 0
      # 주의: 중첩 경로(config/.env.production)도 반드시 커버해야 한다

  def test_staged_env_example_is_allowed(...):
      # ".env.example"은 ERROR 없이 통과 (내용 스캔도 하지 않음 — never-read 유지)
  ```
  실행 → FAIL 확인.
- [x] **4-2. 구현:** 주의 — `forbidden_staged_findings`(security_audit.py:176-190)
  는 **repo 상대 전체 경로 문자열**에 fnmatch를 적용한다(Path가 아니라 str이며,
  `normalized = name.replace("\\", "/")`). 따라서 `".env"`/`".env.*"`만 넣으면
  루트 파일만 걸리고 `config/.env.production` 같은 중첩 경로는 통과한다.
  env 패턴을 다음 4종으로 교체:
  ```python
  ".env", ".env.*", "*/.env", "*/.env.*",
  ```
  허용 예외는 basename 비교(문자열 기준)로 처리:
  ```python
  ALLOWED_ENV_BASENAMES = {".env.example"}
  # forbidden 판정부에서:
  if normalized.rsplit("/", 1)[-1] in ALLOWED_ENV_BASENAMES:
      continue
  ```
  `.env.example`은 여전히 NEVER_READ(내용 미스캔) 대상으로 남긴다 —
  CLAUDE.md Security 절이 `.env.example` 읽기도 금지하므로 일관적이다.
- [x] **4-3.** 테스트 PASS + `python3 -m pytest tests/test_security_audit.py -q` GREEN.
- [x] **4-4. Commit:** `fix(security-audit): forbid staging any .env variant except .env.example`

### Task 5: security_audit — 따옴표 키 시크릿 정규식 수정

**현상** (CONFIRMED): [tools/security_audit.py:84-90](../../tools/security_audit.py#L84-L90)
`SENSITIVE_ASSIGNMENT_RE`는 키워드 그룹 뒤에 곧바로 `\s*[:=]\s*`를 요구한다.
JSON/따옴표 YAML의 `"api_key": "..."`는 키워드와 콜론 사이에 닫는 따옴표가
있어 절대 매칭되지 않는다. `.json`이 `TEXT_SUFFIXES`(29행)에 포함된 스캔
대상인데도 이 규칙이 무용지물이다.

**Files:**
- Modify: `tools/security_audit.py:84-90`
- Test: `tests/test_security_audit.py`

**Steps:**

- [x] **5-1. 실패 테스트 작성:**
  ```python
  def test_sensitive_assignment_matches_quoted_json_keys(tmp_path):
      f = tmp_path / "config.json"
      f.write_text('{"password": "hunter2secret9012", "api_key": "abcd1234efgh5678"}')
      findings = scan_file(f)   # 실제 함수 시그니처에 맞출 것
      rules = {x.rule for x in findings}
      assert "sensitive_assignment" in rules

  def test_sensitive_assignment_still_matches_env_style(tmp_path):
      f = tmp_path / "settings.py"
      f.write_text('API_KEY = "abcd1234efgh5678"')
      assert any(x.rule == "sensitive_assignment" for x in scan_file(f))
  ```
  실행 → 첫 테스트 FAIL 확인.
- [x] **5-2. 구현:** 정규식의 구분자 부분에 선택적 닫는 따옴표를 허용:
  ```python
  SENSITIVE_ASSIGNMENT_RE = re.compile(
      r"""(?ix)
      \b(?:[A-Za-z0-9_]+[_-])?(api[_-]?key|secret|token|password|passwd|credential|private[_-]?key)\b
      ["']?\s*[:=]\s*
      ["']?([^"',\s#}]+)
      """
  )
  ```
  (변경점: `\s*[:=]\s*` 앞에 `["']?` 추가.)
- [x] **5-3.** 기존 sensitive_assignment 관련 테스트 포함 전체
  `tests/test_security_audit.py` GREEN — false positive가 늘지 않는지
  PLACEHOLDER_VALUES 필터 경로도 함께 확인.
- [x] **5-4. Commit:** `fix(security-audit): detect sensitive assignments with quoted keys (json/yaml)`

---

## Chunk 2 — Phase 1: 계약 · 견고성 (P1)

### Task 6: 리포트 발행 경로를 analysis_contract로 일원화 (Mode B 덮어쓰기 수정)

**현상** (CONFIRMED): [scripts/run_mode.py:651-664](../../scripts/run_mode.py#L651-L664)
`publish_mode_b_report`가 `{primary}_B_{소문자lang}_{date}.html`로 저장 —
표준 계약(`tools/analysis_contract.build_default_report_path`, CLAUDE.md §4/§10)은
`{T1}_{T2}_{T3}_B_{대문자LANG}_{date}.html`. 같은 날 primary가 같은 두 비교가
서로 덮어쓰고(shutil.copyfile 663행), `patch_loop.py:75-81` 등 계약 기반 소비자는
파일을 못 찾는다. 소문자 lang 문제는 `publish_mode_report`(646행, Mode A/C)에도
동일. 추가로 세 publish 헬퍼(run_mode.py ×2, run_mode_c_impl.py `publish_report`)
가 같은 로직의 복사본이며, `REPO_ROOT / "output" / "reports"` 하드코딩으로
`STOCK_ANALYSIS_DATA_DIR` 오버라이드(tools/paths.data_path, CLAUDE.md §10)를
무시한다 (PLAUSIBLE 판정 2건 포함 일괄 수정).

**Files:**
- Modify: `scripts/run_mode_common.py` (통합 헬퍼 신설)
- Modify: `scripts/run_mode.py` (`publish_mode_report`/`publish_mode_b_report` 제거·위임,
  `enrich_payload`의 하드코딩 경로도 `tools.paths` 경유로)
- Modify: `scripts/run_mode_c_impl.py` (`publish_report` 위임)
- Test: `tests/test_run_mode_entrypoint.py`, `tests/test_run_mode_c_entrypoint.py`

**Steps:**

- [x] **6-1. 실패 테스트 작성** (`tests/test_run_mode_entrypoint.py`):
  ```python
  def test_mode_b_report_filename_follows_contract(...):
      # 기존 Mode B 엔트리포인트 테스트 픽스처 재사용
      # tickers = AAPL + peer MSFT, lang ko → 발행 파일명이
      # "AAPL_MSFT_B_KO_{analysis_date}.html" 이어야 한다
  def test_mode_a_report_filename_uses_uppercase_lang(...):
      # "AAPL_A_KO_{date}.html"
  ```
  실행 → FAIL 확인.
- [x] **6-2. 구현:** `run_mode_common.py`에 단일 헬퍼:
  ```python
  from tools.analysis_contract import build_default_report_path

  def publish_report_via_contract(
      *,
      html_path: Path,
      mode: str,
      ticker: str,
      peer_tickers: list[str] | None,
      language: str,
      analysis_date: str,
  ) -> Path:
      contract_path = build_default_report_path(
          ticker=ticker,
          output_mode=mode,
          peer_tickers=peer_tickers,
          output_language=language,
          analysis_date=analysis_date,
      )
      if contract_path is None:
          raise RunModeExecutionError(f"cannot build contract report path for {ticker}/{mode}")
      report_path = Path(contract_path)
      if not report_path.is_absolute():
          report_path = REPO_ROOT / report_path
      report_path.parent.mkdir(parents=True, exist_ok=True)
      shutil.copyfile(html_path, report_path)
      return report_path
  ```
  주의사항:
  - 시그니처 확인 완료: `build_default_report_path(*, ticker, output_mode,
    output_language, analysis_date, report_key=None, peer_tickers=None,
    sub_mode=None)` (tools/analysis_contract.py:176-185). Mode B 다중 티커
    조합·대문자 lang 처리는 이미 계약 함수 안에 있다(213-235행).
  - `run_mode_common.py`에는 현재 `REPO_ROOT`/`shutil`이 없다. 상단에
    `import shutil` 과 `REPO_ROOT = Path(__file__).resolve().parents[1]` 를
    추가할 것.
  - `RunModeExecutionError`는 run_mode.py에서 import 순환이 생기면
    `run_mode_common.py`에 예외 클래스를 내리고 run_mode.py가 re-export.
  - run_mode.py의 두 publish 함수와 run_mode_c_impl.py `publish_report`를
    이 헬퍼 호출로 교체. Mode B는 `peer_tickers=comparison 대상 전체`를 전달.
  - `enrich_payload`(623행)의 `REPO_ROOT / "output" / ...`도
    `tools.paths.data_path("runs", run_id, ticker, "analysis-result.json")`로 교체.
- [x] **6-3.** 테스트 PASS. 기존 엔트리포인트 테스트 중 구 파일명을 단언하는
  것이 있으면 계약 파일명으로 갱신.
- [x] **6-4.** 전체 suite GREEN.
- [x] **6-5. Commit:** `fix(publish): route all report filenames through analysis_contract (fixes mode b overwrite)`

### Task 7: numeric_sanity — MAJOR 플래그의 terminal BLOCKER 격상 완화

**현상** (CONFIRMED): 신설 `build_numeric_sanity_item`
([tools/quality_report.py:1041-1053](../../tools/quality_report.py#L1041-L1053))이
validated-data의 MAJOR sanity 플래그를 무조건
`severity BLOCKER / blocker_action "terminal"`로 매핑 →
`build_delivery_gate`(1307-1312행)가 terminal_blocking_items로 분류해 1-loop
패치 경로까지 차단한다. 그런데 유일한 MAJOR 발생원인
`check_margin_invariant`(tools/artifact_validation.py:486-508, 허용오차 0)는
D&A가 매출원가에 있는 자본집약 기업(예: SK하이닉스 — 총마진 25%,
EBITDA마진 50%가 정상)에서 구조적 오탐이다. validation-rules.md:145는 이
플래그를 "정보성"으로 설계했다고 명시한다. CLAUDE.md §8: MAJOR는 플래그와
함께 배포한다.

**설계 결정:** 심각도 체계를 CLAUDE.md §8에 다시 맞춘다 —
sanity 플래그 `BLOCKER` → BLOCKER(terminal), `MAJOR` → **배포 허용 +
MAJOR 플래그**(non_blocking), `MINOR` → MINOR 플래그. margin_invariant 규칙
자체의 오탐 완화(D&A 위치 인지)는 이번 범위에서 제외하고 TODO 주석만 남긴다
(artifact_validation.py는 이 diff 밖의 기존 코드).

**Files:**
- Modify: `tools/quality_report.py` (`build_numeric_sanity_item`)
- Test: `tests/test_quality_report_numeric_sanity.py`

**Steps:**

- [x] **7-1. 실패 테스트 작성/수정** (기존 테스트 파일에 케이스 추가):
  ```python
  def test_major_sanity_flag_delivers_with_flag():
      item = build_numeric_sanity_item(
          {"_validation": {"sanity_flags": [
              {"rule": "margin_invariant", "severity": "MAJOR",
               "detail": "Gross margin (25%) < EBITDA margin (50%) - check inputs"}]}}
      )
      assert item["status"] == "PASS_WITH_FLAGS"
      assert item["severity"] == "MAJOR"
      assert item["delivery_impact"] == "non_blocking_flag"
      assert item["blocker_action"] == "none"

  def test_blocker_sanity_flag_still_blocks():
      item = build_numeric_sanity_item(
          {"_validation": {"sanity_flags": [
              {"rule": "impossible_value", "severity": "BLOCKER", "detail": "negative market cap"}]}}
      )
      assert item["severity"] == "BLOCKER"
      assert item["blocker_action"] == "terminal"
  ```
  기존 테스트 중 "MAJOR → BLOCKER"를 단언하는 케이스는 새 정책으로 갱신.
  실행 → FAIL 확인.
- [x] **7-2. 구현:** `build_numeric_sanity_item`에서 분기 분리:
  `severity == "BLOCKER"`인 플래그만 FAIL/BLOCKER/terminal;
  MAJOR만 있으면 `PASS_WITH_FLAGS / severity "MAJOR" /
  delivery_impact "non_blocking_flag" / blocker_action "none"` +
  warnings에 기존 문구 유지; MINOR-only 분기는 기존 유지.
- [x] **7-3.** 테스트 PASS + 전체 suite GREEN. artifact_validation.py의
  margin_invariant에 TODO 주석 1줄 추가:
  `# TODO: D&A-in-COGS firms legitimately have EBITDA margin > gross margin; needs sector-aware tolerance before any severity above MAJOR.`
- [x] **7-4. Commit:** `fix(quality): major sanity flags deliver with flags instead of terminal blocker`

### Task 8: analyst-coverage 필수 섹션 토큰에서 '목표가' 제거

**현상** (CONFIRMED): [tools/quality_report.py:77](../../tools/quality_report.py#L77)
이 `("analyst coverage", (..., "애널리스트 커버리지", "목표가"))`로 확장됐는데
매처(442-444행)는 문서 전체 substring 매칭이다. 한국어 Mode C 대시보드는
시나리오 밸류에이션 표("기준 목표가"/"강세 목표가", rendering.py:149-151)와
analyst 서사(analyst.py:829-858)에 항상 "목표가"가 있으므로, Analyst Coverage
섹션이 통째로 빠져도 검사가 통과한다.

**Files:**
- Modify: `tools/quality_report.py:77`
- Test: 신규 테스트 함수. 주의 — 기존 tests/에는 `MODE_REQUIRED_RENDERED_TERMS`
  를 참조하는 테스트가 없다. 검사 로직은
  `tools/quality_report.build_rendered_output_item`(442-444행의 substring 루프
  포함)이 단위 대상이다.

**Steps:**

- [x] **8-1. 실패 테스트 작성:** `build_rendered_output_item`을 직접 호출 —
  한국어 Mode C HTML 픽스처에서 "애널리스트 커버리지" 섹션 문자열을 제거하되
  시나리오 표의 "기준 목표가"는 남긴 입력으로, 결과 item이 analyst coverage
  누락을 **실패(missing section)** 로 보고해야 한다.
  실행 → FAIL 확인(현재는 통과해버리므로).
- [x] **8-2. 구현:** 후보 목록에서 `"목표가"`를 제거하고 섹션 특정적 토큰으로
  교체: `("analyst coverage", ("analyst coverage", "analyst target",
  "analyst rating", "애널리스트 커버리지", "애널리스트 목표가"))`.
  (한국어 커버리지 섹션의 실제 렌더 문자열은 rendering.py:89-91의
  "중앙값/최고/최저 목표가" — 필요하면 `"중앙값 목표가"`를 추가 토큰으로.)
- [x] **8-3.** 테스트 PASS + 전체 suite GREEN.
- [x] **8-4. Commit:** `fix(quality): make korean analyst-coverage required-term section-specific`

### Task 9: run_mode.py main() 예외 커버리지 — JSON stdout 계약 보장

**현상** (CONFIRMED): [scripts/run_mode.py:64-94](../../scripts/run_mode.py#L64-L94)
main()은 RunModeInputError(→2) / ModeCEntryError·RunModeExecutionError(→1)만
잡는다. 실제 파이프라인은 `ParityRunnerError`(reuse_macro,
scripts/run_abc_parity.py:359-361 — `--reuse-collected` 아티팩트 부재 시)와
`ValueError`(build_analyst_handoff, scripts/parity/analyst.py:65,192)를 던지며,
이는 원시 트레이스백으로 새어 stdout JSON 계약(RUNBOOK.md:161,193)을 깬다.
ValueError→RunModeExecutionError 변환은 Mode B 한 곳(522-523행)에만 존재.

**Files:**
- Modify: `scripts/run_mode.py` (main)
- Test: `tests/test_run_mode_entrypoint.py`

**Steps:**

- [x] **9-1. 실패 테스트 작성:**
  ```python
  def test_main_emits_json_error_for_parity_runner_error(tmp_path, capsys):
      # --reuse-collected + 존재하지 않는 run-id 조합으로 main() 직접 호출
      rc = run_mode_main([...적절한 인자..., "--reuse-collected", "--run-id", "nonexistent"])
      out = capsys.readouterr().out.strip()
      payload = json.loads(out)          # stdout은 반드시 단일 라인 JSON
      assert "error" in payload
      assert rc == 1
  ```
  실행 → 현재는 예외 전파로 FAIL.
- [x] **9-2. 구현:** main()의 두 번째 except를 확장 + 최후 방어선 추가:
  ```python
  from scripts.run_abc_parity import ParityRunnerError  # 실제 정의 위치 확인 후 import

  except (ModeCEntryError, RunModeExecutionError, ParityRunnerError, ValueError) as exc:
      ...기존 JSON 출력...
      return 1
  except Exception as exc:  # 계약 최후 방어선: stdout은 항상 JSON 한 줄
      print(json.dumps({"error": f"unexpected: {type(exc).__name__}: {exc}",
                        "mode": args.mode.upper(), "run_id": args.run_id},
                       ensure_ascii=False))
      return 1
  ```
  broad except에는 위 주석(계약 사유)을 그대로 남긴다 — 삼킴이 아니라
  형식 보장이 목적임을 명시.
- [x] **9-3.** 테스트 PASS + 전체 suite GREEN.
- [x] **9-4. Commit:** `fix(run-mode): keep stdout json contract for pipeline-raised exceptions`

### Task 10: 소형 버그 2건 — `--timeout 0` 삼킴, pe_forward 죽은 폴백

**현상** (PLAUSIBLE ×2):
(a) [scripts/run_analysis.py:180-181](../../scripts/run_analysis.py#L180):
`if args.timeout:` 이 명시적 `--timeout 0`을 버리고 run_mode 기본 20초가 적용됨.
(b) [scripts/parity/analyst.py:814](../../scripts/parity/analyst.py#L814):
`metric_display(...)`는 결측 시 truthy `"-"`를 반환(1123-1129행)하므로
`or metric_display(metrics, "pe_ratio", ...)` 폴백은 죽은 코드 — pe_ratio가
있어도 서사에 "forward P/E -"가 찍힌다.

**Files:**
- Modify: `scripts/run_analysis.py:180`, `scripts/parity/analyst.py:814`
- Test: `tests/test_abc_parity_analyst.py`, `tests/test_run_mode_entrypoint.py`(포워딩 검사 존재 시)

**Steps:**

- [x] **10-1.** (a) 수정: `if args.timeout is not None:` 로 교체.
- [x] **10-2.** (b) 실패 테스트: `pe_forward` 결측 + `pe_ratio` 존재 metrics로
  `build_codex_native_analysis` 실행 → variant_q3 텍스트에 pe_ratio 값이
  포함되고 `" -"`(대시 placeholder)가 forward P/E 자리에 오지 않는다.
  구현:
  ```python
  forward_pe_text = metric_display(metrics, "pe_forward", currency=currency)
  if forward_pe_text == "-":
      forward_pe_text = metric_display(metrics, "pe_ratio", currency=currency)
  ```
  (metric_display의 반환 계약 자체는 바꾸지 않는다 — 다른 호출부 영향 방지.)
- [x] **10-3.** 전체 suite GREEN.
- [x] **10-4. Commit:** `fix: honor explicit --timeout 0 and repair dead pe_ratio fallback`

---

## Chunk 3 — Phase 2: 감사 도구 품질 · 성능 (P2)

### Task 11: security_audit — 디렉터리 순회 프루닝 + WARN 홍수 제거

**현상** (CONFIRMED): [tools/security_audit.py:141-150](../../tools/security_audit.py#L141-L150)
`iter_path_inputs`가 `path.rglob("*")`로 SKIP_DIRS(.git/node_modules/
__pycache__/.pytest_cache)까지 전부 열거·정렬하고, 각 파일이 scan_file에서
`skipped_sensitive_path` WARN 1건씩(306-315행)을 만든다. 실제 리포에서
`--paths .` 실행 시 수천 건 junk WARN이 쏟아지고 `--fail-on-warn`(390행)과
조합하면 항상 exit 1.

**Files:**
- Modify: `tools/security_audit.py` (`iter_path_inputs`, scan_file의 WARN 발행 지점)
- Test: `tests/test_security_audit.py`

**Steps:**

- [x] **11-1. 실패 테스트 작성:**
  ```python
  def test_iter_path_inputs_prunes_skip_dirs(tmp_path):
      (tmp_path / ".git" / "objects").mkdir(parents=True)
      (tmp_path / ".git" / "objects" / "aa").write_text("x")
      (tmp_path / "node_modules" / "pkg").mkdir(parents=True)
      (tmp_path / "node_modules" / "pkg" / "index.js").write_text("x")
      (tmp_path / "src").mkdir()
      (tmp_path / "src" / "app.py").write_text("print('hi')")
      files = iter_path_inputs([tmp_path])
      names = {f.name for f in files}
      assert "app.py" in names
      assert "aa" not in names and "index.js" not in names

  def test_directory_scan_emits_no_skip_warn_per_pruned_file(tmp_path):
      # 위 구조에서 --paths 스캔 실행 → skipped_sensitive_path WARN 0건
  ```
  실행 → FAIL 확인.
- [x] **11-2. 구현:** `iter_path_inputs`를 os.walk 기반으로 교체:
  ```python
  def iter_path_inputs(paths: Iterable[Path]) -> list[Path]:
      files: list[Path] = []
      for path in paths:
          if path.is_dir():
              for root, dirnames, filenames in os.walk(path):
                  dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
                  for filename in sorted(filenames):
                      files.append(Path(root) / filename)
          elif path.exists():
              files.append(path)
      return files
  ```
  WARN 정책: 디렉터리 순회로 발견된 never-read 파일(.env 등)은 **조용히
  스킵**하고, 사용자가 **명시적으로 인자에 지정한** 파일이 never-read일 때만
  기존 `skipped_sensitive_path` WARN 1건을 낸다(발견 경로 구분 플래그를
  scan 호출부에서 전달).
- [x] **11-3.** 테스트 PASS + 기존 skipped_sensitive_path 테스트(명시 경로
  케이스)가 여전히 GREEN인지 확인.
- [x] **11-4. Commit:** `fix(security-audit): prune skip dirs during traversal and stop warn flooding`

### Task 12: security_audit — fixture 판정을 문자열 마커에서 구조적 검사로

**현상** (PLAUSIBLE, 검증자 확인): [tools/security_audit.py:93-102](../../tools/security_audit.py#L93-L102)
`FIXTURE_MARKERS`는 `"provider": "fixture"` 등 정확 substring 8종만 본다.
`deterministic_fixture`/`local_fixture` 철자는 누락, 공백/따옴표 변형에 무력,
그리고 실제 렌더 HTML에는 run_context JSON이 아예 임베드되지 않아(검증자
grep 결과: 기존 output/reports/*.html에 JSON 형태 `"provider":` 마커 0건 —
산문 속 'provider' 단어와 혼동하지 말 것) 이 검사는 사실상 아무것도 못 잡는다.

**설계 결정:** 발행 리포트 파일명에서 `{ticker}`/`{date}`를 파싱해
`output/data/{ticker}/snapshots/` 및 `output/runs/` 의 대응
`analysis-result.json`을 찾고, `run_context.run_profile` /
`run_context.backend.provider`를 **구조적으로** 읽어 fixture/smoke(그리고
Task 3 이후의 deterministic + opt-in 부재) 여부를 판정한다. 대응 아티팩트를
찾지 못하면 WARN(`fixture_provenance_unverifiable`) 1건.
기존 문자열 마커는 보조 수단으로 유지하되 `FIXTURE_BACKEND_PROVIDERS`
(Task 3의 tools/backend_providers.py)에서 마커 문자열을 생성해 철자 누락을
구조적으로 방지한다.

**Files:**
- Modify: `tools/security_audit.py`
- Test: `tests/test_security_audit.py`

**Steps:**

- [x] **12-1. 실패 테스트:** tmp_path에 가짜 리포트 HTML + 대응
  analysis-result.json(`run_context.backend.provider="deterministic_fixture"`,
  run_profile="smoke")을 만들고 delivery-report 검사 실행 →
  ERROR finding(fixture 리포트 발행 시도) 발생해야 한다. provider가
  `"live"`류면 finding 없음. 아티팩트 부재 시 WARN 1건.
- [x] **12-2. 구현:** 위 설계대로. 마커 튜플은
  `tuple(f'"provider": "{p}"' for p in sorted(FIXTURE_BACKEND_PROVIDERS))` +
  공백 없는 변형으로 생성.
- [x] **12-3.** 테스트 PASS + 전체 suite GREEN.
- [x] **12-4. Commit:** `feat(security-audit): verify report fixture provenance from run artifacts`

---

## Chunk 4 — Phase 3: 구조 리팩터링 (선택, 별도 PR 권장)

> 아래 3건은 동작 버그가 아니라 유지보수성 이슈다. **각각 별도 PR**로,
> 위 Phase 0-2가 모두 머지된 뒤 진행한다. 동작 불변(리팩터링)이므로
> 기존 테스트 GREEN 유지가 완료 기준이다.

### Task 13: 파이프라인 스캐폴드 3중복 추출

**현상** (PLAUSIBLE): `run_mode_a`(scripts/run_mode.py:155-349),
`run_mode_b` per-ticker 루프(413-509), `run_mode_c`(scripts/run_mode_c_impl.py:58-283)
가 request 기록→macro→collect→validation→calculation→analyst→profile→
render→critic→gate→metadata 스캐폴드의 근사-복사본. 이미 드리프트 존재:
schema_version `run-mode-entry-request-v1`(run_mode.py:176,373) vs
`mode-c-entry-request-v1`(run_mode_c_impl.py:87); Mode C만 tier2 스테이지 보유.

**수정 방향:** `run_mode_common.py`에
`run_ticker_pipeline(ticker, mode, args, *, extra_stages=(), include_render=True,
error_cls=RunModeExecutionError) -> TickerPipelineResult` 를 신설하고 세 호출부가
이를 사용. schema_version은 mode별 상수 테이블로 통일. 게이트 이중 검사
(critic.delivery_ready 확인 직후 quality-report 재로드 재확인 — run_mode.py:299/311
등 3곳)는 헬퍼 안에서 1회로 축소한다.

- [x] 구현 + 기존 엔트리포인트 테스트 전체 GREEN
- [x] Commit: `refactor(run-mode): extract shared per-ticker pipeline helper`

### Task 14: 지표 포매터 이원화 해소

**현상** (PLAUSIBLE): analyst.py:1106-1165(+1685-1698)와
rendering.py:1953-2078에 각각 포매터 세트가 존재하고 휴리스틱이 다르다 —
rendering은 market_cap/revenue_ttm/fcf_ttm/net_debt를 무조건 `$X.XB`로,
analyst는 unit 문자열에 "billion"/"b"가 있을 때만 B 표기(1135행). 같은 값이
대시보드와 서사에서 다르게 찍힐 수 있고, critic의 semantic-consistency 검사와
충돌 위험.

**수정 방향:** `scripts/parity/formatting.py` 신설 → rendering.py 구현(발행물
기준)을 정본으로 이관, analyst.py와 rendering.py 모두 여기서 import.
analyst 쪽 자체 구현 삭제. 이관 시 두 구현의 차이를 표로 정리해 정본 규칙을
명시(달러/원화, %, 배수, plain number)하고, 회귀 테스트로 대표 지표 6종
(market_cap, revenue_ttm, operating_margin, fcf_yield, ev_ebitda, beta)의
포맷 스냅숏을 추가.

- [ ] 구현 + `tests/test_abc_parity_analyst.py`·`test_abc_parity_rendering.py` GREEN
- [ ] Commit: `refactor(parity): single metric formatting module for analyst and rendering`

### Task 15: 한국어 로컬라이제이션 후처리 제거 (대형)

**현상** (CONFIRMED-adjacent, 효율/취약성): `localize_mode_c_static_html`이
완성된 50-100KB HTML에 ~130개 literal replace + ~28개 regex를 순차 적용
(중복 엔트리 'Operating Margin' 포함). 짧은 키('Risk', 'Current')가 속성/단어
일부에 오폭할 수 있는 order-sensitive 구조.

**수정 방향:** `LABELS: dict[str, dict[str, str]]` (en/ko) 테이블을 두고 각
`render_*_section`이 렌더 시점에 조회. `localize_mode_c_static_html`과 치환
테이블 3종 삭제. 규모가 크므로 섹션 단위로 나눠 커밋(섹션당: 라벨 치환 →
한국어 골든 테스트 GREEN → commit).

- [ ] 구현 + 한국어/영어 Mode C 렌더 테스트 GREEN, 최종적으로
  `localize_mode_c_static_html` 삭제
- [ ] Commit(들): `refactor(rendering): render-time korean labels for <section>`

---

## 전역 완료 기준 (Definition of Done)

1. `python3 -m pytest tests/ -q` 전체 GREEN.
2. Phase 0-2 완료 후 수동 스모크:
   ```bash
   # (1) Mode C 오프라인 스모크 — 복원된 3개 섹션이 HTML에 존재하는지
   ANALYST_BACKEND=fixture python3 -m pytest tests/test_run_mode_c_entrypoint.py -q
   # (2) deterministic 게이트 — opt-in 없이 codex_native가 BLOCKED되는지
   python3 scripts/run_mode.py --ticker AAPL --mode A --lang en --market US \
     --run-id smoke-$(date +%s) --skip-network --reuse-collected \
     --analyst-backend codex_native ; echo "exit=$?"   # exit=1 + JSON error 기대
   # (3) security audit 회귀
   python3 -m pytest tests/test_security_audit.py -q
   ```
3. `docs/codex/RUNBOOK.md`가 새 플래그(`--allow-deterministic-delivery`)와
   deterministic run_profile을 반영.
4. 각 Task가 독립 커밋으로 남아 있고, 커밋 메시지가 수정 대상 finding을
   설명한다.

## 리스크 및 주의사항

- **Task 1↔2 순서 고정:** 골든 게이트를 먼저 복원하면 섹션이 없는 현재
  렌더가 게이트에 걸려 다른 테스트가 깨진다. 반드시 Task 1 → Task 2.
- **Task 3의 RUNBOOK 정합성:** RUNBOOK 곳곳(69, 111, 225-235행)에
  `run_profile=production` 서술이 있다. 코드만 바꾸고 문서를 남기면 다음
  작업자가 되돌릴 위험이 있으므로 같은 커밋에서 문서를 갱신한다.
- **Task 6의 하위 호환:** 구 파일명(`{primary}_B_{ko}_...`)을 참조하는
  스크립트/테스트가 있는지 `grep -rn "_B_" tests/ scripts/ docs/`로 확인 후
  일괄 갱신. 이미 발행된 구명 리포트 파일은 건드리지 않는다.
- **Task 7은 정책 변경:** MAJOR sanity 오탐이 배포를 막던 동작에 의존하는
  워크플로가 있다면(없을 것으로 판단) 배포 후 quality-report의
  `non_blocking_items`에 MAJOR가 표기되는지로 대체 감시한다.
- **테스트 픽스처에서 `.env` 계열 파일명 생성은 tmp_path 안에서만** —
  리포 워킹트리에 만들지 말 것 (CLAUDE.md Security).
