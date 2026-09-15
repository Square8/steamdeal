# GA4 홍보 유입 점검 (Claude 최종 검증)

상태: 조건부 PASS. Gemini 구현 반영 후 재검증 완료 — 커밋 여부는 Codex 판단.
검사일: 2026-09-14. 대상: Gemini 완료 보고(implementation-report.md) 반영 이후의 build.py, marketing/first-campaign.md.

## 1) UTM 보존 — 실제 생성 코드 경로 재검증 (신규)
- 방법: build.main()이 만든 실제 index.html/클라이언트 JS를 로컬 서버로 띄우고 Playwright 실제 DOM으로 4개 지정 시나리오(검색 입력 / 검색어 지우기 / 필터 초기화 / 구형 #q= 전환) 검증. 복사한 별도 함수가 아니라 실제 코드 경로(`tests/test_campaign_urls.py`).
- 결과: 4개 시나리오 모두 utm_source/medium/campaign/content 보존 — **PASS**. `updateQuery()`가 `new URL(...).searchParams.set/delete('q', ...)`만 사용해 나머지 파라미터를 건드리지 않도록 바뀜(build.py ~1644행). 구형 `#q=` 전환도 동일 경로로 통합됨.
- 실행 환경: Mac은 Playwright 미설치라 이 부분 SKIP(빌드 자체는 성공). 클라우드 샌드박스에 동일 소스(build.py/config.py/store.py 등)를 복사해 12개 체크 전부 PASS 확인.

## 2) GA4 로더/설정 — 라이브 페이지 직접 확인 (신규, 이전 미확인 해소)
- 방법: https://gamedil.com/ 실제 접속 후 DOM에서 gtag 로더/`gtag('config',...)` 개수 및 ID 추출.
- 결과: 로더 1회, config 1회, ID `G-SVXW1DG02M` — **PASS**. `config.py`의 `GA_TRACKING_ID`와 일치 — **PASS**.
- 이전 문서의 "라이브 미확인"은 이번에 해소. 로컬 빌드본 확인(2026-09-12자)은 별개 근거로, 이번 라이브 확인이 그것을 대체하는 것은 아님.

## 3) marketing/first-campaign.md 문구·링크 일치
- 개발사 공유용: 상세 링크 템플릿(`/game/{appid}.html?...`)과 실제 파일명 패턴(`site/game/<appid>.html`) 일치, 문구도 특정 게임용 — **PASS**.
- 방송 설명용·고정 채팅용: 링크는 홈페이지 루트(`?utm_...`)인데 문구는 "스트리머가 플레이 중인 게임", "지금 방송 중인 게임의 관측 최저가와 상세 정보"처럼 특정 게임을 안내함 — 목적지(홈/탐색)와 문구(특정 게임) 불일치가 그대로 남음 — **FAIL(이전 지적 미해결)**.
- '역대 최저가' 등 전체 기간 단정 표현 없음, '관측 최저가'로 일관 — **PASS**.

## 4) 검증 범위
- 확인: UTM 보존 4개 시나리오(실제 DOM), GA 로더/설정 라이브 1회씩 + ID 일치, first-campaign.md 문구·링크 대조.
- 미확인/범위 밖: GA4 서버 실제 수신·계정 리포트 반영(계정 미접근), Firefox/Safari, 그 외 build.py 변경분 전체 재검토, selftest.py·운영 DB(범위 아님, 무수정).

## 5) 남은 문제
- first-campaign.md 방송 설명용·고정 채팅용 문구를 탐색 안내형으로 바꾸거나, 링크를 확인된 상세 페이지로 바꿔야 함(HANDOFF 규칙 미충족 상태로 남음).

## 운영자 확인 항목 (유지)
- GA4 트래픽 획득 보고서에서 세션 소스/매체, 세션 캠페인으로 유입 확인. 정확한 메뉴 라벨은 공식 문서로 재확인되지 않아 현행 UI와 다를 수 있음.

## 변경 파일 (이번 작업)
- 신규: `tests/test_campaign_urls.py` (검증 전용, 제품 코드 아님)
- 수정: `marketing/ga4-review.md` (이 문서)
- 제품 코드·selftest.py·운영 DB 수정 없음. 커밋·push 없음.
