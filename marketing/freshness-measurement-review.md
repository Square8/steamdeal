# 가격 신선도 수정 및 측정 점검 — 2026-10-24 KST

- 가격 수정: editorial.py에서 UTC 기준 날짜 차이 0~2일만 허용. 유료 price_last / 무료 checked_at 사용. 결측/오류/미래 제외. 필터 뒤 정렬·상한 적용, 빈 목록 허용, stale fallback 없음.
- schema_version 1 및 수·토 배열/기존 키 유지. 무료 price_checked_at은 null, availability_checked_at 추가. freshness_policy에 기준일/최대 날짜 차이/요일 조건 적용 전 신선도 제외 수 추가.
- generated_at은 후보 JSON 생성 시각일 뿐 가격 확인일이 아님. now 인자를 주입해 UTC 경계·0/2/3일·오류·무료·Ori 오래된90%·빈 목록·상한 전 필터 검증.
- 기존 후보 검증은 실제 build.main 경로를 유지하고 추천 기준시각만 2026-09-10 UTC로 고정. 유효 fixture의 실제 관측일은 경계인09/08로 조정.
- 테스트: 신선도 unittest 5개 통과, 기존 editorial 실패0/스킵0, selftest 576 PASS. Steam 클릭/UTM/찜 공유/탐색·정렬 실패0/스킵0, 인디 4개 통과.
- 로컬 운영 DB는 읽기 전용 확인. 마지막 가격/상세 날짜10/17, 마지막 수집2026-10-17T14:38:32Z. 현재 신선도 규칙으로 수·토 후보 모두0개. 라이브 최신 DB와 같다고 판단하지 않음. 배포 시 최신 DB/가격 수집 성공 확인 필요.

## 공개 사이트 및 GA4 발신 경로
- HTTP: 홈/1057090 상세200, indie-games.html404. 기존 인디 변경이 공개 반영됐다고 볼 수 없음.
- 위3개 응답의 GA 로더/config/steam_store_click 코드 각1회, GTM 코드 중복 없음. 404 응답에도 공통 GA 태그 존재.
- 실제 공개 gtag.js를 Chromium에서 실행. Analytics collect 요청은 외부 전송 전에 로컬204 응답으로 대체해 테스트 통계를 보내지 않음.
- 홈 진입 page_view 1건(_s1), 검색 q=slime 변경 page_view(_s2), 정렬 sort=cheap 변경 page_view(_s3) 확인. 후속 이벤트는 지연 전송되어 정렬 후 함께 포착. 네트워크 abort 재시도는 별도204 재검증으로 배제함.
- 원인: 검색/정렬의 replaceState URL 변경과 GA 향상된 측정의 이력 기반 페이지 조회. 실제 HTML 재탐색 없이도 조회가 추가되어 홈 조회수/참여세션 해석에 영향 가능. 일반적인 중복 설치와 구분.
- 권장 GA 설정: 웹 스트림 → 향상된 측정 → 페이지 조회 고급 설정 → ‘브라우저 방문 기록 이벤트에 따른 페이지 변경’ 해제, 페이지 로드 측정 유지. 계정 설정은 이번에 접근/변경하지 않음. 실제 집계 과거 수치를 소급 정정할 수 있다고 약속하지 않음.
- click은 GA 기본 외부 클릭, steam_store_click은 사이트 전용 Steam 이동 이벤트. 같은 이동에서 둘 다 발생할 수 있으므로 합산하지 않음. 내부 메뉴/찜은 이 전용 이벤트의 대상 아님.
- 기존 전용 리스너는 실제 Steam 앱 링크 1클릭당 dataLayer 이벤트1건을 브라우저 실측. GA on/off·appid/link_url·찜 회귀 검사 통과. GA 서버 수신/보고서 반영·필터·키이벤트 설정은 계정 미접근으로 미확인.
- 정적 검토 후속: 현재 리스너는 href 문자열 포함으로 Steam 대상을 선택한다. 실제 링크는 정상이나 엄격한 hostname/path 검증과 placement 추가는 별도 개선 대상. 이번 승인 범위인 가격 신선도 외 측정 코드는 변경하지 않음.
- 공식 근거: https://support.google.com/analytics/answer/9216061?hl=en 및 https://developers.google.com/analytics/devguides/collection/ga4/views

## 배포/운영 경계
- Threads 운영 파일·예약·게시 주기는 수정하지 않음. 수·토 소비자는 빈 배열일 때 추측 추천 보충 없이 보류 필요(기존 원칙). 공개 배포 후 실제 소비 동작은 별도 확인.
- 이번 추가 커밋 대상: editorial.py, config.py, tests/test_editorial_picks.py, tests/test_editorial_freshness.py, 이 보고서, HANDOFF.md. 기존 인디/가격대 혼합 변경도 미커밋 상태로 보존.
- DB/공개 배포/GA4 계정 설정/커밋/push 변경 없음. 전체 업무·리포트의 무결성을 확정한 감사가 아니라 가격 생성기와 사이트 측정 경로의 점검임.
