# 랜덤 갓겜 가챠(pick.html) — Claude 최종 검증 (R1 재검증)

상태: **로컬 PASS — FAIL 0 / SKIP 0. Codex 최종 diff 검토 후 커밋 가능.** 검사일: 2026-09-23.
기준: **로컬** 검증. Gemini R1 수정본(build.py 미커밋)을 임시 DB로 `build.main()` 빌드 → 로컬 서버 + Playwright 실제 DOM/hash/클립보드로 판정. 라이브 미점검.
실행: `python3 tests/test_random_pick.py` → FAIL 0 / SKIP 0. `selftest.py` exit 0, `test_navigation_sorting.py`·`test_wishlist_share.py` 실패 0(회귀 없음).

## 이전 FAIL 2건 → 해결 확인(실제 동작)
1. 비후보 링크: `#appid=`로 3만원 게임, 긍정 89% 게임, 출시예정 게임을 직접 열어도 결과가 표시되지 않고 대기 화면이 나온다. 같은 페이지에서 hash를 비후보로 바꾸는 경우(hashchange)도 표시되지 않는다.
2. 문구: 본문과 meta description이 "긍정 평가 90% 이상, 1만원 이하 한국어 게임…"으로 실제 후보 기준과 일치한다. '압도적으로 긍정' 표현은 제거됐다.
- 선택 개선: 첫 진입 버튼 "🎲 뽑기", 추첨 후 "🎲 다시 뽑기"로 바뀌는 것 확인.

## 기존 PASS 재확인(회귀 없음)
- pick.html 생성, noindex 아님, sitemap에 절대 URL 포함.
- 150회 추첨이 전부 후보 조건을 충족했다.
  - 경계값(10000원·90%·리뷰 50)은 포함, 제외 8종은 미출현.
  - 후보 3개 전부 출현, 연속 중복 0회.
- 공유 링크 = `origin/pick.html#appid=현재 게임`. 복사 거부 시 prompt 폴백.
- 후보 링크 진입 시 같은 게임이 뜨고 새로고침 후에도 유지.
- 성인/없는 appid/숫자 아님/빈 값 링크는 대기 화면.
- 후보 0개 빌드에서 안내 문구.
- 상세 → 가챠 링크 이동, 390/1440px 가로 스크롤 없음, JS 오류 없음.

## 참고(FAIL 아님)
모바일 헤더에서 "가챠 🎲"가 메뉴 맨 끝이라 가로로 밀어야 보인다. 유입 목적이면 홈 상단 진입점 추가를 권장한다.

## 변경 파일
- `tests/test_random_pick.py`: 버튼 문구, 같은 페이지 비후보 hashchange 검사 추가.
- `marketing/random-pick-review.md`(이 문서). 제품 코드·운영 DB 수정 없음. 커밋·push 없음.

## 남은 문제
없음(이번 로컬 검증 범위 내).
