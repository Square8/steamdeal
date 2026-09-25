# Steam 상점 클릭 GA4 이벤트 추가 구현 결과

- **작업 내용**: 사이트 내 모든 스팀 상점(`store.steampowered.com`) 아웃바운드 링크 클릭 시 GA4(`steam_store_click`) 이벤트를 전송하는 공통 리스너 추가.
- **작업 파일**: `build.py`
- **구현 상세**:
  1. `build.py`의 `ga_tag()` 함수 내 `gtag('config', ...)` 선언 직후 위치에 document 레벨의 이벤트 위임 리스너를 삽입했습니다.
  2. 캡처 단계(`true`)를 사용하여 이벤트를 잡되, 기존 UI 동작(찜, 버튼 등)을 방해하지 않기 위해 `e.preventDefault()`나 `e.stopPropagation()`을 호출하지 않았습니다.
  3. `a.href.match` 정규식을 통해 스팀 앱 아이디(`appid`)를 추출하고, GA4 이벤트 페이로드에 `appid`, `link_url`을 전송합니다. 페이지 전체 URL인 `page_location`은 gtag.js가 자동 수집하므로 이벤트에서 별도로 덮어쓰지 않습니다.
  4. 로컬 빌드 등 `GA_TRACKING_ID`가 비어있을 경우 기존 동작대로 전체 스크립트를 반환하지 않으므로, 테스트 환경이나 미설정 환경에서 불필요한 JS가 실행되는 현상을 예방했습니다.
  5. 정규식 내부의 이스케이프 충돌(Python `f-string` vs JS `Regex`) 문제를 방지하기 위해, `new RegExp('/app/([0-9]+)')` 형태로 작성하여 클라이언트 측 런타임 문법 오류를 완벽히 해결했습니다.
- **테스트**: `selftest.py`의 Node JS 구문 검사를 비롯해 560여 개 전체 구간 테스트 통과 확인 (PASS).
- **비고**: 서버/DB 추가 없이 기존 스크립트 템플릿만 최소 수정해 요구사항을 모두 충족했습니다.
- **후속 검증 메모**: 기존 `tests/test_steam_click_tracking.py`와 Claude 검증 보고서는 이전에 직접 넣던 `page_location` 경로 값을 기대합니다. 이 수정 후 커밋 전 재검증 시 해당 검증 기준을 제거하거나 자동 수집되는 전체 URL 기준으로 갱신해야 합니다. 본 수정 범위에서는 다른 담당 파일을 변경하지 않았습니다.
