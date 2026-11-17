# 홈·무료 배포 레이아웃 v2 — 2026-11-15
- 상태: 로컬 구현·화면·회귀·전체 생성 비교 완료. 커밋·push·배포 없음.
- 기준: PROJECT_CONTEXT/HANDOFF, proposal-review의 11/15 절, design-reference-review 및 사용자 최종 요구.
## 변경
- 홈 소개 60:40 구성(1024px 이상), 현재 무료 표지·정가→0원·마감·받기 버튼. 현재 최대 3개, 예정만 있으면 1개, 모두 없으면 전체 폭 소개.
- 기존 #free-strip 제거. 무료 예정 링크는 free-games.html#upcoming. 기존 #upcoming-free도 유지.
- 소개 바로가기는 최근 인하·1만원 이하·무료 데모 3개. 모바일 무료 카드는 표지 포함 약 100px, 긴 내용은 높이 증가 허용.
- 인기/한국 판매, 신작/출시 임박을 각각 두 열로 배치. 각 최대 8행 모두 표시, 접기 없음. 모바일은 세로 배치.
- 행에 표지(PC96×54/모바일72×40), 제목, 장르·리뷰·한국어, 동접/순위/출시일 및 할인 가격. 신작의 가격·칩도 유지.
- 동접/일정 확인 시각은 표시된 항목의 가장 오래된 확인 시각으로 섹션에 한 번 표시. 24시간 초과 개별 데이터는 행에 재확인 안내. 판매 순위 기준 시각은 상점 목록 수집 시각.
- 표지 누락은 Steam 표준 URL, 로딩 실패는 머리글자 자리표시. 새로운 표지 컴포넌트의 실패 동작도 회귀 테스트.
- hot/indie/demo 이미지 카드, drop/under-10000 바로가기 유지. 홈 묶음 여백 2.5rem. 홈 첫 카드 줄·상단 무료 표지는 eager, 하단 목록은 lazy.
- 무료 전용: 현재1+예정은 2:1, 현재2+는 그리드와 하단 예정 목록. 설명 전문·확인된 한국어/리뷰·개발사·정가·마감 보존, 높이 고정/설명 잘림 없음.
- 무료 0건은 “확인한 범위에서 현재 무료 배포 없음”. 상점별 확인 시각과 24h 신선도 조건 유지.
## 검증
- selftest.py 641 PASS. 기존 tests/test_*.py 14개 + 신규 test_home_layout_v2.py 총 15개 모두 exit0, 스킵0.
- 같은 DB 사본 전체 빌드 전후 20,894파일, 추가/삭제0. CSS 해시 제외 내용 변경은 index.html/free-games.html/style.css 및 editorial-picks.json 생성 시각뿐. [비교 결과](home-layout-v2-2026-11-15/build-comparison.json).
- 신규 브라우저 회귀: 360/390/1280/1440, 각 순위8행, 현재1/복수/예정만/모두없음, 필터·건수·빈 상태, 이미지404 자리표시.
- 실제 DB 읽기 전용 사본의 홈/무료를 네 폭에서 전체 스크롤. 가로 넘침0, JS pageerror0, 깨진 이미지0. [검사 결과](home-layout-v2-2026-11-15/checks.json).
- [테스트 결과](home-layout-v2-2026-11-15/test-results.json). 기존 앵커·필터·뒤로가기·찜·비교·UTM 회귀 포함.
- 화면 검수: 두 열 목록의 표지/제목/값이 가까워졌고 긴 제목은 줄바꿈. 모바일 8행·가격 유지. 무료 상세는 설명 전체를 보여주므로 모바일에서 받기 버튼까지 스크롤이 필요함.
- 검증은 임시 DB/생성 폴더에만 수행. 운영 DB·site/·Threads 변경 없음. 기존 미커밋 문서 보존.
## 수정 전후
| 화면 | 전 | 후 |
|---|---|---|
| 홈1280 | [전](home-layout-v2-2026-11-15/before-home-1280.jpg) | [후](home-layout-v2-2026-11-15/after-home-1280.jpg) |
| 홈390 | [전](home-layout-v2-2026-11-15/before-home-390.jpg) | [후](home-layout-v2-2026-11-15/after-home-390.jpg) |
| 무료1280 | [전](home-layout-v2-2026-11-15/before-free-1280.jpg) | [후](home-layout-v2-2026-11-15/after-free-1280.jpg) |
| 무료390 | [전](home-layout-v2-2026-11-15/before-free-390.jpg) | [후](home-layout-v2-2026-11-15/after-free-390.jpg) |
- 추가: [인기1280](home-layout-v2-2026-11-15/after-popular-1280.jpg), [인기390](home-layout-v2-2026-11-15/after-popular-390.jpg), [신작1280](home-layout-v2-2026-11-15/after-new-1280.jpg).
## 커밋 초안
- Summary: `feat: 홈 무료 카드와 이미지 순위 목록을 반응형 두 열로 개편`
- Description: `홈 소개 옆에 무료 배포 카드를 배치하고 인기·판매 및 신작·출시예정에 작은 표지를 추가합니다. 무료 전용 페이지는 현재 배포와 예정을 분리해 설명·가격·마감 정보를 유지합니다. 기존 탐색·상태 복원과 24시간 신선도 규칙을 보존하고 네 화면 폭 및 전체 회귀 테스트를 검증했습니다.`
- 이번 코드/테스트: build.py, theme.py, selftest.py, tests/test_home_ux.py, tests/test_home_free_games.py, tests/test_home_layout_v2.py.
- 이번 문서: 본 보고서·동명 캡처 폴더·HANDOFF 추가 절. 기존 미커밋 HANDOFF 부분/다른 마케팅 문서는 별도 변경으로 보존하며 일괄 커밋 대상에 넣지 않는다.

## 11/16 사용자 push 후 확인
- 구현 커밋354dd76, 병합038bd2d 확인. [Actions 43748154987](https://github.com/Square8/steamdeal/actions/runs/43748154987)는 확인 시점 in_progress.
- 공개 홈/무료는 아직 이전 CSS ce2ede99, 새 로컬 CSS28e5bae1과 불일치. 배포 완료·공개 반영 확인은 아직 아님. 이번 확인은 HTTP/Actions 조회이며 브라우저 재검증 없음.
