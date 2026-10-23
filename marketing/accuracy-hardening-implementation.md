# 가격·최근 인하·신작 정확성 보완 — 2026-10-24

- 상태: 사용자 승인 범위 구현. 커밋/push/라이브 배포 및 GA4 계정 설정 변경은 하지 않음.
- 서버 카드·상세·홈 동적 검색·찜·공유받은 목록·최근 본 게임에 가격 확인일 또는 미확인 안내 추가. 무료는 별도 무료 상태 확인일 사용.
- UTC 날짜 차이 0~2일을 넘으면 오래된 정보/Steam 재확인 안내. 줄바꿈 CSS로 모바일에서 경고가 잘리지 않게 처리.
- 오래된 가격은 상세 검색 제목/공유 문구에 확정 가격처럼 포함하지 않음. 신선한 유효 가격/무료 상태에만 Offer JSON-LD 제공. 가격 미정 0원을 무료 Offer로 만들지 않음.
- 비교함은 브라우저 스냅샷이라는 점을 반영해 ‘저장 당시 가격’과 확인 안내를 표시. 기존 localStorage 키와 게임 목록은 보존.
- get_recent_drops에 명시적 기준일 인자 추가, 기본은 현재 UTC 날짜. 과거 데이터 최종일로 최근 구간을 이동시키지 않음. 미래/잘못된 변경일 및 현재가와 다른 이력값 제외.
- 신작 기준은 실제 출시일로부터 0~30일, 출시 완료 본편. 영구 발견 태그 의존 제거. 서버 칩/카드/홈/랜딩/검색 인덱스/추천 점수·후보에 같은 store.is_new_release 적용.
- store.save의 가격/상세 확인 날짜를 UTC로 통일. 기존 DB의 날짜를 소급 변경하지 않으며 미래 날짜는 보수적으로 미확인 처리.
- 신선도 후보 필터(editorial)·인디 추천·가격대 혼합·기간 한정 픽의 기존 미커밋 변경은 보존.

## 검증
- test_display_accuracy.py 4개: 가격 확인 경계/미확인/무료, 최근 인하의 2020년·미래·7일 경계, 신작 30일·미래·오래된 태그, 상세 Offer/제목.
- test_editorial_freshness.py 5개 및 기존 실제 빌드 후보 검증 실패0/스킵0.
- selftest.py 576 PASS. UTC 날짜 기준으로 최근 인하 fixture 수정. Node 내장 JS 문법 검사 포함.
- Steam 클릭/UTM/탐색·정렬/찜 공유/최근30일평가 검증 실패0. 인디 실제 빌드·Chromium 4개 통과(가격 안내/줄바꿈/모바일/정렬/찜 포함).
- test_release_regressions.py 실패0/스킵3: 실제 SITE_URL을 요구하는404 자동완성 드롭다운 왕복은 환경 제약으로 미검증. 이를 PASS로 집계하지 않음.
- 운영 DB 사본 전체 빌드: HEAD/수정본 모두 exit0, 상세12,882개 포함 HTML12,899개 정상 생성. 임시 경로 `/tmp/gamedil_accuracy_compare.0Wj2RZ`.
- 비교: 기존 HTML12,898개 변경(공통 메뉴/CSS/가격 안내 등), indie-games.html 1개 추가, JSON2/XML1/CSS1 변경. robots/favicon/.nojekyll 동일, 삭제 생성물 없음.
- 같은 DB의 신작672→348개. Ori 검색 제목은2990원/90%→가격 재확인 필요, 오래된 Offer 제거/지연 안내 표시 직접 확인. 데이터가 실제로 갱신됐다는 뜻은 아님.
- 390px 실제 운영 데이터 인디 목록 캡처 확인: 경고 줄바꿈 정상, 가로 넘침0. 외부 이미지/GA 요청은 차단한 로컬 검증. 운영 DB와 site/ 직접 변경 없음.

## 커밋 가이드
- 제품: build.py, config.py, editorial.py, store.py, theme.py.
- 테스트: selftest.py, tests/test_editorial_picks.py, tests/test_editorial_freshness.py, tests/test_display_accuracy.py, tests/test_indie_games.py, tests/test_random_pick.py 삭제.
- 기록: HANDOFF.md, marketing/indie-category-implementation.md, marketing/freshness-measurement-review.md, 이 문서.
- marketing/daily-value-plan.md, product-direction-review.md, site-audit-summary.md는 관련 기획/점검 기록으로 별도 문서 커밋 가능. HANDOFF에서 참조하므로 기록도 저장소에 남길 것.
- 권장 제품 커밋명: `feat: 인디 추천 추가 및 가격·신작 정보 정확성 개선`
- 제외: DB, site/, 임시 전체 생성물. 배포 전 원격 최신 DB 확보 및 수집 성공 확인 필요. 로컬 DB10/17 기준 후보0은 라이브 최신 DB의 후보 수를 뜻하지 않음.
- GA4 이력 기반 페이지 조회 설정 교정은 아직 운영자 조치가 필요하며 이번 코드 보완으로 해결됐다고 표현하지 않음. Threads 운영/게시 규칙 변경 없음.
