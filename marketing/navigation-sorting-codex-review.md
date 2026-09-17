# Codex 검수 — 2026-09-17
## 최종 확인 — 2026-09-18
- R2 구현 코드와 Claude 최신 PASS 보고를 대조해 세 가지 차단 사유 해소 확인. 사용자 커밋 가능.
- 날짜 정렬은 기존 정상 튜플로 복원, 홈/랜딩 미정 가격은 방향 비교 전에 뒤로 배치, 홈 무쿼리 복귀 시 로딩된 데이터 재렌더 적용.
- Claude 실제 빌드/브라우저/기본 selftest PASS를 근거로 사용. 이번 Codex는 같은 테스트 반복 실행 없이 관련 코드 확인과 공백 검사 수행.
- build.py 후행 공백 4곳만 Codex가 제거. 아래 FAIL은 수정 전 이력. 라이브 배포는 미확인.

## 2026-09-18 재검수 — 커밋 보류, 아래 R2 우선
- 최신 Claude 보고서도 커밋 불가 상태다. 제품 코드와 대조하고 작은 입력으로 직접 재현했다.
- 직접 재현: korean-soon의 실제 spec.sort에 release_date='2026-10-01' 입력 → TypeError: bad operand type for unary -: 'str'. 전체 빌드 전 이 경로 해결 필수.
- 높은 가격순은 홈 cmp/랜딩 apply 모두 여전히 Infinity에 pb-pa 적용. Node 확인 결과 미정 vs 10,000원 비교가 -Infinity로 미정이 앞으로 온다.
- 추가 코드 확인: 홈 syncURL은 q/sort 없는 URL로 돌아오면 select만 score로 바꾸고 apply를 호출하지 않는다. 이미 로딩된 카드도 기본 순서/검색 해제 결과로 다시 렌더해야 한다. 초기 무쿼리 진입 지연 로딩은 유지.
- git diff --check는 이번 통과. 카드/보조키/안내 문구 수정은 확인했고 Claude PASS 근거 유지. 전체 테스트/브라우저는 이번 Codex 재실행하지 않음.

### Gemini R2 (build.py 및 구현 보고서)
1. korean-soon pick/sort를 HEAD의 기존 정의로 최소 복원: 한국어+coming_soon, sort=(release_date or '9999', name or ''). 이번 작업에 불필요하게 추가된 tag 제외/날짜 음수 연산 제거. 수정된 안내 문구는 유지.
2. 홈/랜딩 가격 비교에서 미정 여부부터 판단: 한쪽만 미정이면 그쪽을 항상 뒤로; 둘 다 미정이면 이름/appid; 둘 다 정상일 때만 오름/내림 비교. Infinity끼리 뺄셈 금지. 명시적 무료는 0원 유지.
3. 홈 syncURL의 기본 URL 복귀 시 indexData가 이미 있으면 apply 실행. 무쿼리 첫 진입 때는 기존 지연 로딩 유지.
4. 다른 UI/선정/카드 변경 금지. 결과를 marketing/navigation-sorting-implementation.md에 저장. 커밋/push 금지.

### Claude R2 (검증 파일 및 검증 보고서)
- tests/test_navigation_sorting.py에서 우회로 제거했던 출시예정 release_date 픽스처를 복원해 실제 build.main 성공 확인. 별도의 날짜 있는 korean-soon 회귀 테스트 유지.
- 홈/랜딩에 미정 2개+무료+유료 2개를 넣고 낮은/높은 가격순 실제 DOM 검사. 미정은 두 방향 모두 마지막, 정상은 방향대로 정렬.
- 홈에서 정렬/검색 적용 후 쿼리 없는 URL로 popstate 복귀 시 select와 실제 목록 둘 다 기본 상태인지 검사. 첫 진입 지연 로딩도 유지 확인.
- 전체 selftest 및 관련 브라우저 테스트 실제 결과/미실행을 구분해 marketing/navigation-sorting-review.md 갱신. FAIL 남아 있으면 '완료/PASS'로 요약하지 말 것.

## 이전 검수 기록
상태: 수정 필요 / 커밋 보류. Gemini·Claude 보고서, 제품 diff, 테스트 코드를 읽음.
직접 실행: python3 selftest.py exit 0. git diff --check exit 2 (build.py 후행 공백 8곳).
브라우저 재실행 없음. 390/768/1440 제목 가림 PASS는 Claude의 실제 DOM 검증 보고 근거.

## 수정 필요
1. 높은 가격순에서 미정 가격이 앞으로 옴. 홈 cmp와 랜딩 apply 모두 Infinity를 가격처럼 역순 비교함. Claude 랜딩 재현 + Codex 양쪽 코드 확인.
   - 무료 여부를 카드 textContent에 '무료'가 있는지로 판정하는 것도 잘못됨. 명시적 데이터 필드 사용. 이름에 '무료'가 있는 유료/미정 게임으로 재현 테스트 추가.
2. createCard()의 요청 범위 밖 재작성으로 기존 카드 표현 회귀.
   - 할인 ribbon/player-badge 제거, 기존 리뷰수·긍정률 tagline을 g.r_lbl로 교체하여 평가 칩과 중복.
   - atl/kr_ov 조건에 따라 데모·신작 칩 숨김, 기존 클래스 변경. 초기 서버 카드와 동적 카드 불일치.
   - HEAD의 기존 createCard 시각 렌더링을 복원하고 이번에 필요한 정렬 data 필드만 추가. 파일 전체를 git restore하지 말 것.
3. 정렬 상태 복원 미완성. 홈 change는 apply만 호출하고 syncURL은 q만 읽음. 랜딩은 초기 sort 읽기만 있고 popstate 리스너 없음.
   - 홈/랜딩의 사용자 정렬 변경은 sort 상태를 기록하고 새로고침·뒤로/앞으로 시 선택과 카드 순서를 복원. 기존 UTM/q/hash 보존.
   - 알 수 없는 sort는 실제 기본 옵션으로 돌릴 것. 현재 랜딩은 sel.value를 미등록 값으로 설정해 선택 UI가 비게 됨.
4. 공통 앵커 click 인터셉터는 ctrl/cmd/shift/alt 클릭까지 preventDefault하고 origin 검사도 없음. reduced-motion과 관계없이 smooth 강제.
   - 같은 origin/홈 문서의 유효한 섹션, 일반 좌클릭만 처리. 새 탭/외부 링크 동작 유지. ID 탐색은 안전한 방식, 대상 없을 때 기본 동작 보존. reduced-motion 반영.
5. 랜딩 설명은 여전히 '리뷰가 많은 순/낮은 가격 순'으로 고정. 선택 정렬과 모순됨. 기본 정렬임을 명시하거나 선택에 맞춰 안내 갱신.

## 후속 담당
- Gemini: build.py/theme.py 및 필요한 기존 selftest.py, navigation-sorting-implementation.md. 위 5개와 후행 공백 수정. 테스트 담당 파일 수정 금지.
- Claude: tests/test_navigation_sorting.py, navigation-sorting-review.md. 구현 후 기존 검증 + 홈/랜딩 높은가격순 미정 마지막, sort 상태 뒤로가기, 잘못된 sort, 카드 동적/초기 의미 일치, 보조키 클릭/reduced-motion 검사.
- '기능 없음'을 구현 대기 SKIP으로 넘기는 테스트는 최종 검증에서는 FAIL이어야 함. 환경상 미실행은 SKIP 허용하되 승인 근거로 쓰지 않음.
- 기본 selftest가 통과해도 위 회귀가 없다는 뜻은 아님. 제품 경로/실제 DOM을 검증하고 보고서의 구현 완료 주장을 결과에 맞춰 갱신.
- 운영 DB·수집·게시·커밋/push 금지. 이전 제목 가림 수정은 유지하고 관련 변경 때만 재검증.
