# Steam 상점 클릭 GA4 이벤트(steam_store_click) — Claude 재검증 (R2)

상태: **로컬 PASS — FAIL 0 / SKIP 0. Codex 최종 diff 검토 후 커밋 가능.** 검사일: 2026-09-25(R2).
기준: **로컬** 검증. Codex R1 리뷰에서 지적된 `page_location` 문제(GA4 표준은 전체 URL
필요, gtag.js가 모든 이벤트에 자동 첨부하는 예약 파라미터라 커스텀 이벤트에서 경로만
넣는 건 표준 불일치)를 Gemini가 반영해 페이로드에서 `page_location` 자체를 제거한
수정본을 검증. 라이브 GA4 실제 수신 미확인(로컬 네트워크 제약, R1과 동일).
실행: `python3 tests/test_steam_click_tracking.py` → FAIL 0. `selftest.py`,
`tests/test_wishlist_share.py`, `tests/test_random_pick.py` 모두 exit 0(회귀 없음).

## R1 → R2 변경 사항
- **인정: R1의 제 검증 기준 자체가 오라클 버그였음.** R1에서 `page_location: location.pathname`
  값을 정답으로 확인했는데, GA4에서 `page_location`은 gtag.js가 모든 이벤트에 자동으로
  붙이는 예약 파라미터(전체 URL 필요)라 경로만 넣는 건 애초에 표준과 맞지 않았다.
  Codex가 diff에서 이를 지적했고, 재확인 결과 타당했다.
- Gemini 수정: `build.py`의 `steam_store_click` 이벤트 페이로드에서 `page_location` 줄
  삭제. `appid`/`link_url`, capture 단계 리스너는 그대로 유지.
- Claude 재검증: `tests/test_steam_click_tracking.py`에서 `page_location` 관련 검사 3건을
  "커스텀 페이로드에 `page_location` 키가 없어야 한다"는 검사로 교체, 리스너 코드 내
  `page_location` 문자열 부재도 정적으로 재확인.

## 실제 동작 확인(R2)
1. 상세 페이지 "스팀 상점에서 보기"/데모 링크 클릭 → `steam_store_click` 이벤트가
   `appid`, `link_url`만 담아 정확히 발생. `page_location` 키 자체가 페이로드에 없음
   (실제 `dataLayer` 내용으로 확인).
2. `GA_TRACKING_ID` 빈 값 빌드: 리스너/스크립트/`dataLayer` 전부 없음(R1과 동일, 회귀 없음).
3. capture 단계 등록, `preventDefault`/`stopPropagation` 미호출 유지 확인(R1과 동일).
4. 찜(♡) 버튼 클릭 회귀 없음 재확인(localStorage 반영, 카드 이동 안 함, `steam_store_click`
   오발생 없음).
5. 콘솔/페이지 오류 없음.

## 참고(FAIL 아님, 검증 범위 한계)
- `page_location`을 제거했으므로 GA4가 자동으로 채우는 전체 URL 값 자체는 로컬(외부
  네트워크 차단) 환경에서 실측 불가 — gtag.js 외부 스크립트가 실제로 로드되는 배포
  환경에서만 확인 가능. 배포 후 GA4 실시간 보고서에서 `steam_store_click` 이벤트의
  `Page location` 필드가 실제 전체 URL로 채워지는지 1회 확인 권장.
- 홈(index.html)에는 여전히 스팀 직접 링크가 없어(R1과 동일 사유) 상세 페이지 기준으로
  클릭 실측.

## 변경 파일
- `tests/test_steam_click_tracking.py`: `page_location` 관련 검사 3건을
  "키 부재 확인"으로 교체(R1 지적 반영).
- `marketing/steam-click-tracking-review.md`(이 문서, R2로 갱신).
- 제품 코드(`build.py`)·`selftest.py`·운영 DB 수정 없음. 커밋·push 없음.

## 남은 문제
없음(이번 로컬 R2 검증 범위 내). 배포 후 GA4 실시간 보고서에서 `steam_store_click`
이벤트의 `Page location`이 실제 전체 URL로 정상 수집되는지 1회 확인 권장.
