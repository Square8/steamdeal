# 공통 작업 현황

## 2026-10-27 동접 정확성 후속 진단 — 수정 승인 전
- 로컬 양수동접 공개조건293개 중209개가24시간이상오래됨. build는시간제한없고섹션시간은max값. 특히API실패에도touch_player_checked가이전값확인시각을새로찍어성공시각처럼보일수있음.
- 제안: 성공/시도시각과상태분리,0명/미제공/실패분리,최근24시간성공값만개별시각과함께노출. 과거checked_at을성공시각으로무조건이관금지. 한국판매수익순은별도제공검토.
- 상세 `marketing/cod-visibility-diagnosis.md` 추가절. 구현하지않음,기존진단문서만갱신.

## 2026-10-27 콜 오브 듀티 노출 진단 — 제품 변경 없음
- 한국 Steam 판매수익1위는4435490 MW4. GameDil은 동접순이며 공개 동접1/인기목록263위, 신작54위, 한국어78위. 홈8개에 못들어 노출되지 않음. 토요일후보에는12번째로포함.
- 공식 앱별 동접 재조회4435490=0(result1), 공통1938090=153124(result1). 공식공통앱설명에서MW4/BO7/Warzone지원확인. 공통수치를MW4단독동접으로옮기지말것.
- 1938090은로컬DB/공개검색인덱스에없음. 발견경로가공통실행앱을보장하지않으며판매인기도따로저장하지않음. 한국어/성인필터문제아님.
- 상세 `marketing/cod-visibility-diagnosis.md`. 한국판매인기와글로벌동접을분리하는개선제안이며미구현. 소스/DB/Threads/커밋/push변경없음(진단문서만저장).

## 2026-10-24 가격·최근 인하·신작 정확성 보완
- 최종: 로컬 검수 완료. DB 사본으로 HEAD/수정본 전체 빌드 exit0, 상세12,882개 포함 HTML12,899개 생성 비교. 공통 HTML/CSS/JSON/sitemap 변경과 인디1페이지 추가, robots/favicon 유지 확인. 운영 DB/site/변경 없음.
- 신작은 같은DB672→348개, Ori 오래된 가격은 제목/Offer에서 제외되고 안내로 전환. 모바일390px 경고 줄바꿈/넘침0 확인. 라이브 반영은 아직 아님.
- 사용자 승인으로 구현. 상세 `marketing/accuracy-hardening-implementation.md`. 게임별 확인일/지연 안내를 서버·동적 카드에 통일, 오래된 가격의 검색 제목/공유/Offer 노출 제한. 비교는 저장 당시 정보로 표기.
- 최근 인하는 현재 UTC 날짜 기준으로 판정. 신작은 출시일 기준0~30일인 출시 완료 본편으로 칩/목록/인덱스/추천점수·후보를 통일. store.save 날짜도UTC로 통일.
- 기본576PASS, 정확성 경계4/신선도5/인디4 통과, 후보·클릭·UTM·탐색·찜·최근평가 실패0. release_regressions 실패0/환경제약스킵3. 전체 생성 비교는 보고서 최종 기록 확인.
- 기존 미커밋 인디·한시픽·후보신선도 변경 보존. 커밋 대상/이름은 위 보고서에 정리. DB/site/커밋/push/Threads/GA설정 변경 없음.

## 2026-10-24 문제·개선 종합 점검 — 추가 수정 없음
- 목록 `marketing/site-audit-summary.md`. 로컬수정/공개반영/확인된문제/제안을 구분. 이번 제품코드 변경 없음.
- 신규 재현: get_recent_drops는오늘이아닌DB최종가격변동일기준으로최근7일계산(2020fixture도현재반환). 신작은영구tag로필터하여2010fixture도통과,로컬2025/04출시작1개실제포함.
- 가격신선도JSONgate만으로홈/상세/Offer전체신선도가보장되지는않음. 개별확인일/신작기한/최근인하기준일을후속정확성보완으로제안. 미승인제품변경없음.
- 공개홈7섹션51카드/47고유게임,4게임2회. 반복문제는주로고정일별선정구조가설이며실제반복률미측정. sitemap12981URLlastmod동일10/23,개별의미있는변경일로개선검토.

## 2026-10-24 매일의 정보 가치/검색 기획 — 미구현
- 제안 문서 `marketing/daily-value-plan.md`. 매일의 정보 가치는 가격 변화·최근 평가 차이·구매 판단에 필요한 사실 중심으로 구성. 홈에서 변화 정보→온도차→향후3선→인기 순위 제안.
- 개별 가격 확인일과 빌드일 구분, 없는 변화/직접 경험 추정 금지. ASO는 앱스토어이며 현재는 SEO/AI검색의 정보 이해와 접근성이 대상. 기존 주제URL을 유지하며 근거/범위/표본/확인일을 제공.
- 승인 순서 가격신선도→10/29평가→온도차→3선 유지. Threads/사이트 운영 동시 변경 금지. 제품 코드 변경 없음.

## 2026-10-24 가격 신선도 구현 + 측정 점검
- 사용자가 N=2 수정 승인. 유료 price_last/무료 checked_at 기준 UTC 날짜차0~2일 필터 구현, 결측·오류·미래 제외, 빈 후보 허용. editorial.py/config.py, 신선도 새 테스트/기존 실제 빌드 테스트 갱신. 상세 `marketing/freshness-measurement-review.md`.
- 공개 Chromium 실측: 진입1 + 검색/정렬 history 변경2 = page_view3 생성. Analytics 요청은 로컬204로 대체해 테스트 통계 미전송. 태그 중복 설치는 발견 못함. 계정 설정에서 이력 기반 조회만 해제 권장, 아직 설정 변경 안 함.
- 기본 click과 steam_store_click을 합산하면 같은 외부 이동 중복 해석 가능. 실제 전용1클릭/1이벤트와 GA on/off/UTM/찜 회귀 통과. GA4 계정 리포트/내부 필터/서버수신은 미확인.
- 로컬 DB 최신10/17이라 새 수·토 후보0. 공개JSON 최신생성10/22와 구분. 공개 인디URL404로 미배포 상태 확인. DB 수정/Threads 운영 변경/커밋/push 없음.

## 2026-10-24 제품 계획 수정 — 구현 승인 대기
- 사용자 지정 순서: 가격 신선도 수정 → 10/29 평가 → 최근 평가 온도차 → 홈 3선. 3선 원천은 GameDil editorial.py/공개 후보 JSON. 홈 메뉴 노출 개선 검토, steam_store_click에 위치 파라미터 추가. 사이트/Threads 운영 변경은 같은 주 동시 적용 금지.
- 직접 HTTP 확인: 공개 후보 JSON generated_at 10/22 16:31Z, Ori 1057090의 가격 확인일 10/01/할인90% 잔존. 후보 생성 전 개별 가격 신선도 검사가 없음.
- 제안: N=2(UTC 날짜 차이 0~2일; 정확한 48시간 아님), 유료 price_last/무료 checked_at 검사, 결측·오류·미래 제외, 빈 목록 허용, stale fallback 금지. N과 세부 구현은 승인 전.
- 온도차 코너는 limit로 인기작 일부가 빠질 수 있다는 안내 필수. 상세 `marketing/product-direction-review.md`. 이번에는 문서만 수정, 제품 코드/Threads 운영/테스트 실행 없음.

## 2026-10-24 Claude·Gemini 제품 제안 검토
- 기록: `marketing/product-direction-review.md`. 제품 코드 변경 없이 로컬 데이터와 별도 Threads 후보 생성 코드를 확인.
- 권장 순서: 홈 추천 3선/검증된 짧은 설명 → 최근/전체 평가 비교 → 근거 있는 퀵 버튼. 구현 승인으로 간주하지 않음.
- buy_if/skip_if 무모델 생성은 존재하나 키워드 템플릿으로 사실 검수 필요. 다른 repo의 로컬 today-candidates.json은 웹 배포에서 바로 읽을 수 있다고 가정하지 않음.
- 최근 집계값 로컬 173개 중 최신 7일/최근 50개 이상 42개(공개 필터 전). 전체 대비 차이는 개선/업데이트 인과 증거가 아님. ‘최근 평가 온도차’ 제안.
- 현재 인디는 한국어 지원 기준이며 개발사 한국 국적 판정 없음. 기존 변경 배포/10월 29일 유입 실험 평가와 신규 홈 실험 시점을 구분할 것.

## 2026-10-24 No More Slimes!! 한시적 운영자 픽
- 사용자 지정 4228920을 홈/인디 목록 최상단 별도 운영자 픽으로 10/24~10/30 KST 소개. 10/31 00:00 이후 첫 예약 빌드부터 해제. 자동 추천 기준은 유지하며 이후 자동 점수로 추천.
- Steam 페이지 기준 22리뷰/77%로 일반 조건 미달임을 확인. 공개 화면에서 운영자 선정 예외로 구분. DB 미등록 시 공식 Steam 링크 소개, 수집 이후 실제 카드로 전환. `config.py` 수집 seed에 추가.
- 상세 기록 `marketing/indie-category-implementation.md`. 커밋 대상에 `config.py` 추가. DB/커밋/push 조작 없음.

## 2026-10-24 가챠 → 인디게임 추천 교체 — 로컬 완료
- 사용자 요청으로 공통 메뉴를 `인디 추천`으로 교체하고 홈 8개 미리보기 및 `indie-games.html` 전체 목록 추가. Steam 장르 인디/Indie, 한국어, 출시 완료 본편, 비성인, 리뷰 50개 이상/긍정률 80% 이상 기준. 기존 정렬 기능 재사용.
- 가챠 코드는 제거. 기존 `pick.html`은 noindex 호환 이동 페이지로 유지하고 새 목록만 sitemap에 포함. 로컬 운영 DB 읽기 전용 조건 집계는 65개이며 라이브 수치 확인 아님.
- 검증: 임시 DB 전체 빌드 및 Chromium 테스트 3개 통과(선별 경계/가격·평가 정렬/복원/UTM/찜/390·1440px/이전 URL 이동), 기본 selftest 576 PASS, diff --check 통과. 상세는 `marketing/indie-category-implementation.md`.
- 기존 미커밋 1만원 이하 가격대 혼합 변경은 `build.py`에 보존되어 함께 커밋됨.
- 커밋 대상: `build.py`, `tests/test_indie_games.py`, `tests/test_random_pick.py` 삭제, `marketing/indie-category-implementation.md`, `HANDOFF.md`. 권장 이름: `feat: 가챠를 인디게임 추천 카테고리로 교체`.
- 커밋/push/라이브 배포는 하지 않음. DB/생성물 변경 없음. 다음 단계는 사용자 커밋/push 후 공개 페이지 확인.

## 2026-09-26 최근 30일 평가 Codex R1 재검토 — 커밋 가능
- `steam.py`의 반복 cursor 처리가 `complete`에서 불완전 `error`로 바뀐 것을 실제 diff로 확인했다. 오래된 리뷰/빈 페이지에서만 완전 집계하며, 기존 완전값 보존은 `store.py` 저장 경로와 맞는다.
- `tests/test_recent_reviews.py`의 반복 cursor 1·2쪽 검사 및 fetch→collect→build 통합 검사를 확인했다. 구현 보고서도 새 종료 조건으로 갱신됐다. Claude 보고: 43항목 FAIL 0, selftest 575 PASS. Codex는 이번 재검토에서 테스트/실제 Steam API 호출을 반복 실행하지 않았고 `git diff --check`만 직접 통과 확인했다.
- 커밋 대상: `config.py`, `steam.py`, `store.py`, `collect.py`, `build.py`, `tests/test_recent_reviews.py`, `marketing/recent-reviews-implementation.md`. 커밋명: `feat: 최근 30일 Steam 평가 수집 및 상세 표시 추가`.
- 제외: 출처 미확인 `steamdeal.db`, 기존 미커밋 `HANDOFF.md`의 다른 내용, 별도 `marketing/60-day-growth-plan.md`, `marketing/navigation-sorting-live-review.md`, 생성물. 이 HANDOFF 검토 기록은 별도 정리 전까지 커밋에 포함하지 않는다.
- 라이브 Steam API 응답은 미확인. push 실행은 수집을 건너뛰므로 배포 후 예약/수동 Actions 수집 로그의 완전/실패 건수를 확인한다. 반복 cursor 오류가 많더라도 불완전 수치를 공개하지 않는 현재 정책을 유지한다. Codex는 커밋/push하지 않았다.

## 2026-09-26 GA4 Steam 상점 클릭 후속 확인
- `steam_store_click` 이벤트는 커밋 `55f0911` 배포 후 공개 페이지에서 실행됐고, GA4 화면에 이벤트 1건이 표시되어 실제 수신을 확인했다.
- 사용자가 맞춤 측정기준 `Steam App ID`를 생성함(범위 `이벤트`, 매개변수 `appid`). 보고서 반영까지 24~48시간 걸릴 수 있다.
- 다음 GA4 점검이나 마케팅 성과 리뷰 때 이 항목을 먼저 상기시키고, 탐색(Explore)에서 `steam_store_click`을 `Steam App ID`별로 분석하도록 안내한다. 생성 전 이벤트는 게임별 보고에 포함되지 않을 수 있으므로 설정 후 수집분을 기준으로 본다.

## 2026-09-25 실행 점검 — Threads 클릭 측정 / 게시 준비
- GA4 `참여도 > 이벤트`의 지난 28일(2026-08-28~09-24) `click`은 8회, 사용자 6명으로 표시됐다. GameDil 웹 스트림의 향상된 측정과 `이탈 클릭` 수집도 켜져 있다. 따라서 외부 링크 클릭 이벤트 수집은 작동 중인 것으로 보인다.
- 단, 현재 GA4 이벤트 요약에는 목적지 도메인별 분해가 없어 Steam 상점 클릭이 몇 회인지 확인하지 못했다. 라이브 `build.py` 페이지에는 `gtag('event', ...)` 형태의 명시적 Steam 클릭 이벤트도 없다. 다음 측정 작업은 `link_domain`/`link_url`로 Steam 목적지를 분리하거나 전용 `steam_store_click` 이벤트를 구현·검증하는 것이다. GA4 설정·사이트 코드는 이번에 변경하지 않았다.
- `steam-threads-agent` 로컬 큐에는 2026-09-25 승인 글이 없고, DREDGE 2026-09-24 건은 완료 상태다. 실제 게시/예약은 하지 않았다. 금요일 초안 후보로 Subnautica, 2026-09-26 토요일 GameDil 픽 후보로 프랑스 브라세리 시뮬레이터를 검토했다. 후자는 GameDil 상세의 리뷰 수(577)와 현재 Steam 리뷰 수(619)가 달라 공개 초안에서 리뷰 수는 빼고, 예약 전 재검수해야 한다.
- 위 결과는 검수 메모이며 예약 또는 게시 이력으로 기록하지 않는다.

## 2026-09-25 성장 실험 방향
- 30~60일 실행 초안: `marketing/60-day-growth-plan.md`. GameDil의 가격·리뷰·데모 데이터에 운영자의 실제 플레이 판단을 결합하는 주간 실험이다. 아직 성과가 입증된 계획은 아니다.
- 이 작업의 채팅방은 사이트·측정·마케팅 전략을 맡고, Threads 일일 게시와 수·토 GameDil 픽의 초안·게시는 기존 `steam-threads-agent` 작업에서 담당한다. 기존 예약과 하루 1개 규칙을 유지한다.
- 2026-09-25 제공 화면 기준 GA4·Search Console의 28일 기준선을 `marketing/60-day-growth-plan.md`에 기록했다. GA4 트래픽 획득에서 289세션 중 `l.threads.com / referral` 120세션(41.52%)을 확인했고, 별도로 `threads / social` 3세션이다. Steam 외부 클릭 계측과 IP 형태 referral의 정체는 미확인. 이를 확인한 뒤 목표를 보정하고, 30일/60일 결과 전에는 대규모 신규 기능·수익화 개발을 보류한다.
- 이번 턴에는 계획 문서와 이 핸드오프만 작성했다. 제품 코드·DB·생성물 수정, 커밋·push 없음.

## 최신 결론 — 2026-09-24 랜덤 게임 뽑기 최종 검토
- 판정: 로컬 기준 커밋 가능. 라이브 배포는 이번에 확인하지 않았다.
- 근거: marketing/random-pick-implementation.md 및 marketing/random-pick-review.md를 읽고 build.py 실제 diff 대조. Claude는 임시 DB 빌드와 Playwright로 후보 조건·경계값·150회 추첨·연속 중복 방지·유효/무효 해시·링크 복사·모바일 레이아웃·회귀를 확인해 FAIL 0 / SKIP 0 보고. Codex는 이번 턴에 브라우저 테스트를 반복 실행하지 않았다.
- Codex 직접 확인: 후보는 한국어, 비성인, 출시 완료, 리뷰 50건 이상, 긍정률 90% 이상, 유료 1만 원 이하로 제한. 결과 해시는 validGames 기준으로 검사하고, pick.html은 공개 페이지로 생성되어 sitemap에 포함된다. 변경 빈 줄의 후행 공백 12곳과 함수 사이 공백만 정리; `python3 -m py_compile build.py` 통과.
- tests/test_wishlist_share.py의 별도 변경은 SITE_URL을 지정해 sitemap이 비어 있는 상태의 거짓 PASS를 막는 회귀 테스트 강화다. 이번 커밋에 함께 포함한다.
- 커밋 대상: build.py, tests/test_random_pick.py, tests/test_wishlist_share.py, marketing/random-pick-implementation.md, marketing/random-pick-review.md, HANDOFF.md.
- 커밋명: feat: 한국어 게임 랜덤 추천 페이지 추가
- 제외: steamdeal.db. 기존 미커밋 marketing/navigation-sorting-live-review.md는 별도 배포 검증 문서이므로 이번 대상에서 제외. 운영 DB와 생성된 site/도 추가하지 않는다.
- 선택 개선: 모바일 메뉴 맨 끝의 가챠 링크 발견성이 낮을 수 있다. 배포 후 실제 이용 반응을 보고 진입점 보강 여부를 정한다.
- Codex는 커밋/push하지 않았다.

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
