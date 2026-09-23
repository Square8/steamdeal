# 찜 목록 공유 링크 — Claude 최종 검증 (R1 재검증)

상태: **로컬 PASS — FAIL 0 / SKIP 0. Codex 최종 diff 검토 후 커밋 가능.** 검사일: 2026-09-23.
기준: **로컬** 검증. Gemini R1 수정본(build.py 미커밋)을 임시 DB로 `build.main()` 빌드 → 로컬 서버 + Playwright 실제 DOM/localStorage/클립보드/대화상자로 판정. 라이브 미점검.
실행: `python3 tests/test_wishlist_share.py` → FAIL 0 / SKIP 0. `selftest.py` exit 0, `tests/test_navigation_sorting.py` 실패 0(회귀 없음).

## 이전 FAIL 3건 → 해결 확인(실제 동작)
1. 레이아웃: 카드 컨테이너 computed `display=grid`. 카드 폭은 1440px에서 242px, 390px에서 160px이고 가로 스크롤 없음(이전: block, 1008px 한 줄 쌓임).
2. 성인 게임: 기본 상태에서 숨김. '성인 게임 포함' 체크 시에만 표시.
   "모두 추가"는 화면에 보이는 항목만 병합한다. 토글 해제면 성인 게임 제외, 체크면 포함 — 두 경우 모두 실제 localStorage로 확인.
3. 없는 appid:
   - 없는 appid만 든 링크 → "조건에 맞는 게임이 없습니다." 안내 표시.
   - 병합 시 없는 appid는 저장되지 않음. 헤더 찜 수와 화면 카드 수 일치(1/1).
   - 표시 0개 링크에서 기존 찜 변경 없음.

## 기존 PASS 재확인(회귀 없음)
- shared-games.html 생성, noindex, sitemap 미포함.
- 공유 버튼: 찜 0개면 숨김, 있으면 표시.
- 클립보드 링크가 찜 순서 그대로. 35개 → 30개 제한과 안내. 복사 거부 시 prompt 폴백.
- 잘못된 hash 4종에 안내 문구. 숫자 아닌 값/중복 무시. hash 변경 시 재렌더. 열람만으로 내 찜 불변.
- 합집합 병합 시 **기존 목표가 보존**. my-games.html 이동.
- 홈 카드 ♡ 토글과 my-games 목표가 UI 유지, JS 오류 없음.

## 참고(FAIL 아님)
안내가 `alert()`/`prompt()` 차단형 대화상자다. 동작은 정상이고, 토스트로 바꾸는 건 선택 개선이다.

## 변경 파일
- `tests/test_wishlist_share.py`: 성인 토글별 병합, 표시 0개 병합 검사 추가.
- `marketing/wishlist-share-review.md`(이 문서).
- 제품 코드·selftest.py·운영 DB 수정 없음. 커밋·push 없음.

## 남은 문제
없음(이번 로컬 검증 범위 내). 배포 후 공개 사이트에서 링크 생성 → 다른 브라우저로 열기 1회 확인 권장.
