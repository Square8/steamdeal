# 찜 목록 공유 기능 구현 및 버그 픽스 결과

- **작업 내용**: 내 찜 목록을 다른 사람과 공유하고, 공유받은 목록을 내 찜에 통합할 수 있는 기능 추가 및 이슈 수정
- **작업 대상**: `build.py` (DB 및 기존 데이터 구조 수정 없음)
- **변경 상세 (최초 기능)**:
  1. `my-games.html`
     - '친구에게 공유' 버튼 추가
     - `localStorage`의 `steamdeal-wishlist-v1` 값을 추출해 `https://gamedil.com/shared-games.html#ids=...` 형태의 링크 생성
     - 복사 기능 지원 (최대 30개로 제한 처리 및 안내)
     - 찜 목록이 비어있으면 공유 버튼 숨김 처리
  2. `shared-games.html` 신규 페이지 추가
     - URL hash(`location.hash`)에서 `ids` 값을 추출하여 렌더링
     - 목표가 설정/보기 UI를 제거해 깔끔한 목록만 제공
     - 검색 노출 방지를 위해 `<meta name="robots" content="noindex,follow">` 추가 및 `sitemap.xml` 제외

- **추가 수정 (리뷰 결과 반영)**:
  1. `shared-games.html`의 카드 컨테이너 클래스 오타 수정 (`my-grid` -> `grid`)
  2. 성인 게임(`adult=1`) 기본 숨김 처리 및 '성인 게임 포함' 토글 체크박스(`myAdult`) 추가. '내 찜 목록에 추가' 버튼 역시 **현재 화면에 표시된 (필터링된) 게임들만** 추가되도록 `currentDisplayed` 배열 적용.
  3. 해시에 전달된 ID가 `game-search-index.json`에 없거나 필터 결과 화면에 표시할 게임이 0개인 경우 "조건에 맞는 게임이 없습니다" 빈 화면 표시 처리 완료.

- **테스트**: `selftest.py` 560여 개 전체 구간 테스트 통과 확인 (PASS)
- **비고**: 서버/DB 추가 없이 100% 정적 페이지와 클라이언트 JS만으로 요구사항 완벽히 구현. 기존 미커밋 변경사항 보존.
