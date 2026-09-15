# 수·토 GameDil 픽 준비 — 역할별 작업

## 후속 수정 R1 — 기존 구현 완료 후 이 항목 우선 (2026-09-15)
- 근거: marketing/threads-picks-review.md의 FAIL 3건. 새 기능/순위 개편 금지.
- Gemini 담당: editorial.py 및 marketing/threads-picks-implementation.md. build.py는 이 3건 해결에 꼭 필요한 경우만 최소 변경. Claude 테스트 파일 수정 금지.
  1. 공통 후보는 app_type == 'game'인 경우만 허용. DLC/demo/tool 및 누락/알 수 없는 유형 제외. 정식 게임의 has_demo 표시는 유지.
  2. 유료 게임은 유효한 양수 price_final만 허용. store.all_games가 이력 없는 가격을 0으로 채우므로 None 검사만으로 통과시키지 말 것. 명시적 무료 게임은 토요일 후보로 유지, 수요일에서는 제외. 결측치를 무료로 추정하거나 운영 저장 로직을 바꾸지 말 것.
  3. 출력 price_checked_at은 실제 입력 price_last에서 가져올 것. 날짜만 있는 값은 그대로 보존하고 가짜 시각/UTC를 붙이지 말 것. 미관측이면 null, generated_at으로 보정 금지. 항목 스키마 설명도 실제 출처와 일치시킬 것.
- 구현 후 기존 tests/test_editorial_picks.py 실행으로 3건 해결 확인. 실패 테스트를 약화시키거나 보고서만 PASS로 변경하지 말 것. 수행 명령/결과와 수정 범위를 구현 보고서에 <=40줄로 저장.
- Claude 담당: tests/test_editorial_picks.py와 marketing/threads-picks-review.md만.
  - 실제 최신 구현으로 기존 테스트 재실행. 단독 DLC, 이력 없는 유료 0원, price_last 전달 케이스가 각각 통과해야 함.
  - 0원/None 유료 제외, 명시적 무료 토요일 유지, 관측일 결측 null, 비게임 유형 제외를 빠진 경우 작은 픽스처로 보강.
  - 기존 요일/12개 상한/정렬/50KB/상세 URL 회귀 확인. 구현의 복제 함수를 검사하지 말 것.
  - 운영 DB 대신 테스트 픽스처 사용. 기본 selftest 1회; 테스트에 실제 build.main 검증이 있으면 같은 빌드를 불필요하게 반복하지 말고 확인 범위를 명시.
  - 라이브 404는 '배포 전 사용 불가'로 따로 기록. 로컬 PASS를 라이브 배포/GA 수신 PASS로 쓰지 말 것.
- 두 작업 모두 커밋/push 금지. 기존 예약 제노니아1 유지. 최종 Codex 검토 뒤 사용자 배포, 이후 공개 JSON의 200/JSON 파싱/스키마/관측일을 확인해야 사용 가능.

공통: PROJECT_CONTEXT.md, HANDOFF.md, marketing/threads-picks-policy.md를 먼저 읽는다.
미커밋 변경 보존. 커밋/push/게시/예약 변경 금지. 운영 DB 및 스키마 변경 금지.
새 메뉴·카테고리·로그인·외부 AI API·스케줄러를 만들지 않는다. 이번 목표는 작은 후보 데이터와 편집 규칙 연결이다.

## Gemini — 구현
- 담당: 새 editorial.py, build.py의 최소 연결, marketing/first-campaign.md, marketing/threads-picks-implementation.md.
- 기존 build.py UTM 변경을 보존한다. 이전 ga4-review.md에서 FAIL인 홈페이지 링크/특정 게임 안내 문구 불일치를 탐색 안내 문구로 해결한다.
- 기존 빌드가 이미 메모리에 읽은 games를 재사용하여 assets/editorial-picks.json 생성. 추가 Steam 요청·DB 쓰기 금지.
- editorial.py에 순수 후보 선정 함수를 분리하고 기준/스키마를 짧게 문서화한다. build.py에는 호출/출력 연결만 추가한다.
- 스키마: schema_version, generated_at(UTC), wednesday 배열, saturday 배열. 요일별 최대 12개. 점수 동률은 appid 등으로 결정적 정렬.
- 항목: appid, 이름, GameDil 상세 URL, 현재가/할인/무료 여부, 한국어/데모, 리뷰 수/긍정률, 실제 가격·미디어 관측 시각 등 필요한 원시 필드와 선정 근거 코드만. 없는 값은 null. generated_at을 관측 시각으로 대체하지 않는다.
- 공통: 성인 제외, 정식 출시 게임, 유효 appid와 생성되는 상세 페이지가 있는 게임. 유효한 가격/무료 상태와 리뷰 근거 필요. 양수 가격/평가 없는 것을 0원/호평으로 보정하지 않는다.
- 수요일: 유료 할인 중, 긍정률 >=80, 리뷰 >=50. 할인율과 기존 추천 점수를 활용하되 할인만으로 최저가라 부르지 않는다.
- 토요일: 긍정률 >=80, 리뷰 >=50. 한국어·데모·기존 추천 점수로 우선순위. 데이터에 없는 짧은 플레이타임/친구와 하기 좋음 등을 생성하지 않는다.
- 필드 의미는 실제 저장/빌드 경로에서 확인하고 기존 score가 없으면 단순하고 문서화된 순위를 사용. 12개 미달은 그대로 반환하고 조건을 몰래 완화하지 않는다.
- 이력 제외는 편집 단계에서 수행. 예약된 제노니아1을 후보에 강제 삽입하거나 appid를 추정하지 않는다.
- JSON에 HTML 조각/전체 설명/이력 배열 불포함. 홈 초기 로딩·네비·sitemap 변경 없이 빌드당 한 번 생성. 최대 50KB 예산.
- 검증: 작은 픽스처로 직접 확인, 기존 selftest와 빌드 검증. 대량 빌드 전 비용/범위를 알리고 반복 최소화. 임시 출력 경로 사용을 우선하며 운영 DB 변경 여부 확인.
- 보고서 <=40줄: 변경 파일, 기준/스키마, 검증 실행 여부, JSON 크기, 후보 수, 남은 문제. 배포 전 URL 사용 가능 주장 금지.

## Claude — Gemini와 병행 가능한 준비, 구현 후 최종 검증
- 담당: tests/test_editorial_picks.py, marketing/threads-picks-review.md만. 제품 코드/공통 현황 수정 금지.
- 구현 중에는 정책 기반 테스트 케이스를 준비한다. 구현 완료 후 실제 editorial.py 함수를 import하여 테스트한다. 복제한 선정 함수를 테스트하지 않는다.
- 성인/미출시/가격미정/리뷰부족/잘못된 값 제외, 요일별 분기, 12개 상한, 빈 후보, 결정적 순서, null 유지, 관측일/생성일 구분을 확인한다.
- 실제 생성 JSON의 스키마/50KB 제한/상세 경로, HTML 조각 부재를 검사. 홈에 추가 fetch/전체 후보 인라인이 생기지 않았는지 diff로 확인.
- first-campaign.md의 이전 링크/문구 불일치 해결 여부 확인. 기존 tests/test_campaign_urls.py 검증은 가능 환경에서 1회; 불가능하면 SKIP 이유 명시.
- 예약 제노니아1은 변경하지 않는다. 정책에 존재하는 예약 이력과 날짜/요일/UTM/공개 링크 규칙만 확인한다. 게임 사실을 검증하지 않았으면 미확인으로 남긴다.
- 보고서 <=40줄: PASS/FAIL/SKIP, 실제 실행환경/명령, 실패 위치, 미확인 사항. 이전 검증을 새 실행으로 표현하지 않는다.

## 완료 조건
- Gemini 구현 후 Claude 검증 완료, Codex가 두 보고서와 관련 diff 검토.
- 배포 전에는 후보 URL 준비 완료가 아니다. 배포 후 공개 JSON 200 응답/스키마 확인 필요.
- Threads 채팅방에 정책 파일/짧은 연결 지침 전달 후, 2026-09-19 토요일 추천 요청으로 흐름 확인.
