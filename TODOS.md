# TODOS

## Pending

### 카카오톡 챗봇 레이어 구현
- **What:** 카카오톡 → Mac Mini 서버 → Claude Code CLI → GitHub Pages → 카톡 응답 파이프라인 구축
- **Why:** 친구들(20~50명)이 카톡으로 주식 분석 요청 가능하게
- **Design doc:** stored locally outside the repo (path tracked privately, see `.git/info/exclude`)
- **Prerequisites:** Mac Mini 구매 + 설정
- **Sub-tasks:**
  1. [ ] Mac Mini 초기 설정 (Claude Code CLI 설치, Python 환경)
  2. [ ] 카카오 i 오픈빌더 계정 + 채널 개설
  3. [ ] Flask/FastAPI 서버 프로토타입 (`server/app.py`) — webhook 수신 → CLI 호출 → 결과 반환
  4. [ ] Cloudflare Tunnel 설정 (cloudflared 설치, 도메인 연결)
  5. [ ] GitHub Pages 리포트 레포 생성 + 자동 배포 스크립트
  6. [ ] 사용자 관리 (whitelist.json) + 사용량 트래킹
  7. [ ] 비용 모니터링 (일/주/월 API 호출 비용 추정)
  8. [ ] 대화형 후속 질문 처리 (세션 유지, 즉시 응답 vs 비동기 분류)
  9. [ ] systemd/launchd 서비스 등록 (자동 시작, 자동 복구)
  10. [ ] 친구 3명 테스트 → 피드백 수집

### Claude API 비용 추정 추가
- **What:** 디자인 문서 Open Questions에 Claude API 분석당 비용 추정치 추가 (~$0.50-2.00/Mode C)
- **Why:** 리뷰어가 단위 경제 검증 불가 플래그를 남김. Financial Datasets API 비용만 명시되고 Claude API 비용 미명시
- **Pros:** 수익화 계획의 실현 가능성 판단 근거
- **Cons:** 정확한 측정 어려움 (input/output token 변동)
- **Context:** 디자인 문서 Open Questions #4 (private design doc, path stored locally only)
- **Depends on:** 실제 분석 2-3건 실행 후 token 사용량 측정

## Completed
(none yet)
