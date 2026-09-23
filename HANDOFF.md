# 공통 작업 현황

## 최신 결론 — 2026-09-24 찜 목록 공유 최종 검토
- 판정: 로컬 기준 커밋 가능. 라이브 배포와 브라우저 간 링크 전달은 아직 확인하지 않았다.
- 근거: marketing/wishlist-share-implementation.md 및 marketing/wishlist-share-review.md를 읽고 build.py 실제 diff 대조. Claude는 임시 DB 빌드와 Playwright로 공유 링크·30개 제한·성인 기본 숨김/토글·화면에 표시된 항목만 병합·없는 ID·모바일 그리드·기존 목표가 보존을 재검증해 FAIL 0 / SKIP 0 보고. Codex는 이번 턴에 전체 브라우저 테스트를 다시 실행하지 않았다.
- Codex 직접 확인: 신규 shared-games.html은 정적 생성되고 noindex이며 sitemap 경로에 추가되지 않음. ID는 숫자만 수용하고, 렌더링은 DOM textContent 기반이며 성인 필터 뒤의 currentDisplayed만 병합. build.py 후행 공백 6곳과 함수 사이 공백만 정리했으며 `git diff --check`, `python3 -m py_compile build.py` 통과.
- 커밋 대상: build.py, tests/test_wishlist_share.py, marketing/wishlist-share-implementation.md, marketing/wishlist-share-review.md, HANDOFF.md.
- 커밋명: feat: 찜 목록 공유 링크와 공유받은 게임 병합 추가
- 제외: steamdeal.db. 기존 미커밋 marketing/navigation-sorting-live-review.md는 이 기능과 별도인 배포 검증 문서이므로 이번 대상에서 제외. 생성된 site/와 운영 DB도 추가하지 않는다.
- 비차단 후속 사항: 브라우저가 localStorage 쓰기를 거부하면 병합 코드가 실패를 숨기고 성공 안내를 띄울 수 있다. 일반 저장 성공 흐름은 Claude가 검증했으며, 저장 실패 안내 개선은 별도 작업으로 남긴다.
- 사용자 커밋/push 전까지 배포 상태로 간주하지 않는다. Codex는 커밋/push하지 않았다.

## 배포 확인 — 2026-09-18
- 사용자 커밋 완료 후 Codex가 공개 사이트 Chrome에서 직접 핵심 흐름 확인.
- 홈 7개 메뉴 제목 가림 없음, 데모 랜딩 577개 가격 양방향/평가순 정렬 및 상세 방문 후 뒤로가기 순서 복원 PASS.
- 범위/근거: marketing/navigation-sorting-live-review.md. 현재 데스크톱 스모크 검사이며 전체 모바일/랜딩 재검사나 GA 수신 확인 아님.
- 제품 코드 수정 불필요. 이번에는 보고 문서만 저장하며 추가 커밋/push하지 않음. 다음은 신규 기능보다 추천 게시물 유입 실험.

## 최신 결론 — 2026-09-18 홈 탐색/정렬 검토 완료
- 커밋 가능. 아래 같은 작업의 보류/FAIL 문구는 수정 전 이력이다.
- Codex가 R2 실제 코드 대조: korean-soon 날짜 정렬 복원, 홈/랜딩 가격 미정 우선 분리, 홈 무쿼리 복귀 시 재렌더 확인.
- Claude 최신 R2 보고: 실제 픽스처 build.main, 기본 selftest, 브라우저 홈/랜딩 가격순·상태복원·제목 가림 등 PASS. 보고서 날짜는 9월 17일로 적혀 있으므로 결과의 최신성은 R2 코드/보고서 내용 기준으로 대조함. Codex는 이번에 브라우저/전체 테스트를 반복 실행하지 않았다.
- Codex 변경: build.py 후행 공백 4곳만 제거. 기능 변경 없음.
- 커밋명: feat: 홈 메뉴 이동 통일 및 카테고리 정렬 추가
- 대상: build.py, theme.py, selftest.py, tests/test_navigation_sorting.py, HANDOFF.md, marketing/navigation-sorting-{tasks,implementation,review,codex-review}.md.
- 제외: steamdeal.db. 다음 단계는 사용자 커밋/push 후 배포 화면 확인. 로컬 검증이며 라이브 배포 완료를 뜻하지 않는다.

## 현재 작업 — 2026-09-17 홈 탐색 통일 및 카테고리 정렬
- 2026-09-18 최신 판정: 커밋 보류. korean-soon 날짜 문자열 정렬 TypeError 직접 재현, 높은가격순 미정 우선 오류 잔존. 홈 무쿼리 URL 복귀 시 재렌더 누락도 코드 확인. marketing/navigation-sorting-codex-review.md의 9월 18일 R2를 우선 수행.
- Codex 최종 검수: 수정 필요/커밋 보류. 최신 후속 지시 marketing/navigation-sorting-codex-review.md 우선 적용.
- Claude의 높은가격순 FAIL 외 카드 렌더링 회귀, sort 복원 누락, 앵커 보조키/reduced-motion 문제, 안내 문구 모순 확인. Codex 직접 selftest exit 0, diff --check 후행 공백 8건 실패. 테스트 통과만으로 승인하지 않음.
- 최신 사용자 요청은 제목 가림 해결, 홈 메뉴 앵커 통일, 카테고리 전체 페이지 정렬이다. 아래 9월 15일 내용은 이전 작업 이력.
- 지시서: marketing/navigation-sorting-tasks.md.
- 코드 확인: sticky 헤더와 고정 76px 앵커 여백, 최근 인하/1만원 이하만 페이지 링크, 1만원 이하 홈 섹션 없음, 랜딩 사용자 정렬 없음.
- Gemini: build.py/theme.py/필요한 selftest.py 구현. 결과 marketing/navigation-sorting-implementation.md.
- Claude: tests/test_navigation_sorting.py 독립 검증. 결과 marketing/navigation-sorting-review.md. 준비 병행 가능, 최종 검증은 구현 후.
- Codex: 두 보고서와 실제 diff 최종 검토 후 커밋 대상/이름 제공. 이번 문서는 작업 지시이며 구현 완료가 아님.
- 시작 git status: untracked steamdeal.db만 존재. 보존하고 커밋 제외.

## 최신 결론 — 2026-09-15, R2 최종 검토 완료
- 상태: 로컬 검증 통과, 사용자 커밋/push 가능. 아래 R1/R2의 보류·FAIL 기록은 해결 전 이력이다.
- Codex: 최신 Gemini/Claude 보고서 및 selftest.py의 7개 변경을 검토했고 git diff --check 통과 확인. 제품 코드 R1은 이전 턴에서 직접 검토/후보 테스트 실행 완료.
- Claude R2 실행 보고: 기본 selftest 560 PASS/0 FAIL, 후보 테스트 25 PASS/0 FAIL/0 SKIP. Codex는 이번에 같은 테스트를 반복 실행하지 않았다.
- UTM 동작은 이전 실제 DOM 테스트 12/12 PASS 근거를 유지한다. selftest의 문자열 검사는 그 동작 검증을 대체하지 않는다.
- 커밋명: feat: GameDil 수·토 추천 후보 및 홍보 유입 추적 준비
- 커밋 대상: AGENTS.md, GEMINI.md, CLAUDE.md, HANDOFF.md, build.py, editorial.py, selftest.py, tests/test_campaign_urls.py, tests/test_editorial_picks.py, marketing/의 현재 7개 문서.
- 제외: 출처 미확인 steamdeal.db. 운영 DB/생성 산출물 추가 불필요.
- 다음: 사용자 push 후 GitHub Actions 배포 성공 확인 → 공개 assets/editorial-picks.json의 HTTP 200/JSON 스키마/상세 URL 확인 → Threads 채팅방에 사용 가능 안내.
- 라이브 상태: 마지막 보고는 HTTP 404. 이번 최종 검토에서 라이브 재조회하지 않았으며 배포 완료로 취급하지 않는다. GA4 실제 서버 수신도 미확인 유지.

## 협업 규칙
- 조정자(Codex)만 이 파일을 갱신한다. Gemini·Claude는 각자 담당 보고서에 결과를 기록한다.
- 시작 시 이 파일과 선행 보고서만 읽고, 코드가 필요하면 rg로 범위를 좁힌다.
- 공유 폴더의 파일은 저장 후 다른 도구에서도 읽을 수 있지만, 상대 채팅으로 자동 전달되지는 않는다.
- 구현과 최종 검증은 순서대로 진행한다. 구현 중 검증자는 테스트 계획만 준비하고 제품 파일을 수정하지 않는다.
- 보고서는 결론·근거·검증 범위·남은 문제·변경 파일을 40줄 이내로 기록한다.
- 이전 결과를 덮어쓸 때 검사 기준(로컬/라이브), 날짜, 실행 여부를 명시한다. 이전 PASS를 새 검사로 표현하지 않는다.
- 전체 코드 재독·대량 생성·반복 브라우저 검사 등 비용이 큰 작업은 이유와 범위를 먼저 사용자에게 알린다.
- 커밋은 Codex의 결과 검토 후 사용자가 한다. steamdeal.db는 출처 미확인 기존 파일로 보존하며 이번 커밋에서 제외한다.

## 현재 작업: 첫 홍보 캠페인 준비
- 2026-09-15 추가: Gemini/Claude 보고서 저장 확인. Claude 보고서에 홈페이지 링크와 특정 게임 소개 문구 불일치 FAIL이 남아 있음. 이번 픽 준비 작업에서 해결 후 재검증한다. Codex 최종 승인 전이다.
- 상태: 커밋 보류. 구현 수정 후 Claude 검증 필요.
- Gemini 산출물: marketing/first-campaign.md
- Claude 기존 점검: marketing/ga4-review.md
- Gemini 후속 보고서: marketing/implementation-report.md
- Claude 최종 보고서: marketing/ga4-review.md (수정 후 재검증 결과로 갱신)

## Gemini 담당 — 사용자에게 후속 작업 전달 시 적용
- 담당 파일: build.py, marketing/first-campaign.md, marketing/implementation-report.md
- 검색 입력, 검색어 지우기, 필터 초기화, 구형 #q= 전환에서 URL 전체를 재작성하지 말고 q만 추가/수정/삭제하여 기존 UTM과 다른 파라미터를 보존한다.
- 기존 검색·필터 동작과 필요한 앵커 동작을 유지한다. 제품 변경은 이 URL 처리 범위에 한정한다.
- 홈페이지 홍보 링크는 게임 탐색 안내 문구와 연결한다. 특정 게임 정보 안내는 확인된 상세 링크 또는 명시적인 템플릿을 사용한다.
- 자체 가격 이력을 Steam 전체 역대 최저가처럼 홍보하지 않는다. 현재 가격·GameDil 관측 가격 이력으로 표현한다.
- 작업 후 보고서를 저장한다. Claude 담당 파일은 수정하지 않는다.

## Claude 담당 — Gemini 완료 보고서가 저장된 후
- 담당 파일: marketing/ga4-review.md, 필요 시 tests/test_campaign_urls.py (기존 파일 존재 여부 먼저 확인)
- 최신 구현과 보고서를 읽고 검색 입력·지우기·초기화·구형 해시 전환에서 UTM 보존을 동작으로 검증한다.
- 구현을 복사한 별도 함수만 검사하지 말고 실제 생성 JS 또는 제품 코드 경로에 연결된 테스트를 사용한다.
- 공개 홈페이지 HTML을 한 번 읽어 GA 로더/config 각 1회 및 ID 일치를 확인한다. 브라우저 실행 없이 HTTP로 확인 가능하면 사용한다.
- HTML 태그 확인과 GA4 서버 실제 수신 확인을 구분한다. 계정 보고서 미접근 시 수신은 미확인으로 남긴다.
- marketing/first-campaign.md의 링크·안내 문구 일치도 확인한다.
- 제품 코드·selftest.py·DB는 수정하지 않는다. 실패하면 위치와 재현 조건만 보고한다.

## Codex 담당
- 담당 보고서를 읽고 실제 diff를 좁게 검토한다.
- 필요한 수정이 남았으면 커밋명을 주지 않는다. 통과 후 정확한 커밋 대상과 이름을 안내한다.

## 새 작업: 수·토 Threads GameDil 픽 준비 (2026-09-15)
- 최신 상태: Claude 보고서 FAIL 3건을 Codex가 editorial.py/store.py 관련 코드와 대조 확인. 아래 후속 수정 우선. 제품 테스트는 이번 Codex 확인에서 재실행하지 않았다.
- 공개 후보 URL은 사용자 보고 기준 HTTP 404. 배포 확인 전 사용 금지 유지. 404를 없애기 위해 미검증 코드를 먼저 배포하지 않는다.
- 정책/예약 이력: marketing/threads-picks-policy.md. 9월 16일 제노니아1 기존 예약 유지.
- 상세 분담: marketing/threads-picks-tasks.md. 위 이전 과제 중 잔여 FAIL도 이 작업에 포함한다.
- Gemini: 후보 JSON 생성 구현 및 marketing/threads-picks-implementation.md 저장.
- Claude: 테스트 준비는 병행 가능, 실제 구현 후 최종 검증 및 marketing/threads-picks-review.md 저장.
- Codex: 두 보고서/diff 검토 후 커밋 대상/이름 안내. 아직 구현·배포 완료가 아님.
- 다른 채팅방은 자동 동기화되지 않는다. 정책 파일을 전달하거나 같은 저장소에서 읽도록 연결해야 한다.

## 현재 최우선: 후보 생성 FAIL 3건 수정
- 2026-09-15 Codex 재검토: R1 제품 수정 확인. tests/test_editorial_picks.py 직접 실행 실패 0/스킵 0, 실제 픽스처 build.main 출력 확인. git diff --check 통과.
- 새 차단 사유: python3 selftest.py 직접 실행 exit 1, 실패 7건. 기존 테스트가 과거 최저가 문구/UTM 제거 코드/404 상대경로를 기대함. 아래 R2 테스트 정합성 작업 필요. 커밋 보류 유지.
- Gemini: marketing/threads-picks-tasks.md의 '후속 수정 R1' 수행 후 구현 보고서 갱신.
- Claude: 수정 완료 후 같은 절차의 재검증 수행. 보고서 갱신 전 기존 실패 근거를 보존한다.
- 이전 홍보 문구/링크 불일치는 최신 threads-picks-review.md에서 PASS로 확인됨. 다시 수정하지 않는다.
- Codex 승인 → 사용자 커밋/push → 배포 성공 및 공개 JSON 검증 순서. 커밋명은 최종 검토 후 제공한다.

## 현재 최우선 R2: 기본 회귀 테스트 정합성 (R1 수정은 완료)
- Gemini 담당: selftest.py와 marketing/threads-picks-implementation.md만. 제품 코드 변경 금지.
- 실패 항목: '60일부터 역대최저 배지', '초기화 시 q 파라미터 제거', '충분한 관측 기간 + 현재가=관측 최저가 상태', 'atl_trustworthy 충족 시 역대 최저가 문구 사용', '검색어 없을 때 ?q= 제거 및 초기화 로직 존재', '홈으로 돌아가기 버튼 확인', '지금 인기 게임 보기 링크 확인'.
- 최저가 3개: 실제 현재 정책인 관측 최저가/GameDil 관측 최저가를 검사하고 과장된 역대 최저가 표현 미사용도 검증. 기간 조건은 유지.
- URL 2개: 옛 history.replaceState(...location.pathname) 문자열을 요구하지 말 것. 현재 updateQuery 경로에서 q 삭제 및 UTM 보존을 실제 생성 JS로 확인. tests/test_campaign_urls.py와 중복 실행 최소화하되 단순 무조건 PASS로 대체 금지.
- 404 2개: 실제 base 경로 규칙에 맞춰 홈/인기 링크가 루트로 연결되는지 검증. 깊은 잘못된 URL에서도 경로가 깨지지 않는 기존 수정 보존.
- 테스트 삭제/조건 완화/제품을 과거 동작으로 복원 금지. 임시 DB selftest 1회 실행 후 결과 저장.
- Claude 담당: selftest.py diff 읽기 + marketing/threads-picks-review.md 갱신만. 7건이 의도한 정책을 계속 검증하는지 확인하고 기본 selftest와 후보 테스트 재검증. 제품/테스트 수정 금지. 로컬 PASS/라이브 미확인 구분.
- 기본 selftest까지 통과 후 Codex 최종 확인. 라이브 후보 URL 사용 금지 유지. 운영 DB/커밋/push는 건드리지 않는다.
