# ADR 0002: Run-Local Artifact와 Shared Snapshot 승격 규칙

작성일: 2026-04-24
상태: Accepted
관련 가이드: `docs/agent-audit-remediation-guide.ko.md` Phase 2

## 맥락

분석 실행 중 생성되는 raw artifact와 최종 보고서 입력은 재현 가능한 run-local working set이어야 한다. 동시에 staleness checker는 `latest.json`을 통해 최근 분석을 재사용해야 하므로 shared cache도 유지해야 한다.

문제는 mutable raw artifact를 shared ticker data path에 직접 쓰면 같은 티커의 동시 실행이 서로 덮어쓸 수 있다는 점이다. 반대로 모든 것을 run-local로만 두면 24시간 재사용 모델이 깨진다.

## 결정

실행 중 산출물과 공유 캐시를 분리한다.

- Run-local working set:
  - `{data_root}/runs/{run_id}/{ticker}/research-plan.json`
  - `{data_root}/runs/{run_id}/{ticker}/tier1-raw.json`
  - `{data_root}/runs/{run_id}/{ticker}/tier2-raw.json`
  - `{data_root}/runs/{run_id}/{ticker}/validated-data.json`
  - `{data_root}/runs/{run_id}/{ticker}/analysis-result.json`
  - `{data_root}/runs/{run_id}/{ticker}/quality-report.json`
- Shared immutable snapshot:
  - `{data_root}/data/{ticker}/snapshots/{snapshot_id}/...`
- Shared latest pointer:
  - `{data_root}/data/{ticker}/latest.json`

`data_root`는 `tools.paths.data_dir()`이며, `STOCK_ANALYSIS_DATA_DIR`가 설정되면 repo 내부 `output/` 대신 해당 경로를 사용한다.

## 승격 규칙

Run-local artifact는 다음 조건을 모두 만족할 때 shared snapshot으로 승격할 수 있다.

1. `research-plan.json`, `validated-data.json`, `analysis-result.json`, `quality-report.json` artifact validation이 통과한다.
2. fetched raw artifact가 포함된 경우 `ingestion_allowed = true`이다.
3. `quality-report.delivery_gate.ready_for_delivery = true`이다.
4. Mode C는 rendered output validator를 통과한 최종 HTML path가 기록되어 있다.
5. 승격 대상 파일은 기존 snapshot을 덮어쓰지 않고 새 `{snapshot_id}` directory에 쓴다.

`latest.json`은 raw artifact 본문을 직접 담지 않는다. 최신 snapshot과 freshness metadata를 가리키는 pointer만 담는다.

```json
{
  "schema_version": "1.0",
  "kind": "stock-analysis.latest-snapshot-pointer",
  "ticker": "AAPL",
  "latest_snapshot_id": "2026-04-24_run_abc123",
  "analysis_date": "2026-04-24",
  "snapshot_saved_at": "2026-04-24T09:30:00Z",
  "expires_at": "2026-04-25T09:30:00Z",
  "freshness_ttl_hours": 24,
  "data_mode": "enhanced",
  "output_mode": "C",
  "rr_score": 7.2,
  "verdict": "Neutral",
  "refs": {
    "validated_data": "output/data/AAPL/snapshots/2026-04-24_run_abc123/validated-data.json",
    "analysis_result": "output/data/AAPL/snapshots/2026-04-24_run_abc123/analysis-result.json",
    "quality_report": "output/data/AAPL/snapshots/2026-04-24_run_abc123/quality-report.json",
    "evidence_pack": "output/data/AAPL/snapshots/2026-04-24_run_abc123/evidence-pack.json"
  }
}
```

## Staleness 재사용 규칙

1. Staleness checker는 `{data_root}/data/{ticker}/latest.json`만 먼저 읽는다.
2. `expires_at`이 현재 시각 이후이고 required artifact refs가 존재하면 fresh로 판단한다.
3. Fresh snapshot은 새 run-local working set으로 복사하거나 참조 metadata로 연결한다.
4. Reuse된 run도 새 `run_id`를 가지며, 사용자 산출물에는 snapshot id와 source refs를 기록한다.
5. Pointer가 없거나 만료되었거나 참조 파일이 없으면 fresh collection으로 간다.

## 후속 작업

1. 완료: `snapshot-manager.py`를 pointer-only `latest.json` 형식으로 이관한다.
2. 완료: legacy full-snapshot `latest.json`은 읽기 호환만 유지하고 새 저장은 pointer 형식으로 한다.
3. 완료: data collector와 validator skill 문서의 shared raw artifact 예시를 run-local path로 교체한다.
4. 완료: `contract_checks.py`가 fixture를 repo `output/`에 쓰지 않도록 기본 임시 data dir isolation과 `STOCK_ANALYSIS_DATA_DIR` override를 적용한다.
