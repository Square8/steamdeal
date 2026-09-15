# Threads GameDil 픽 — R2 재검증 (기본 회귀 정합성)

상태: **로컬 PASS(기본 selftest + 후보 테스트 모두)**. Codex 승인/사용자 배포 전. 검사일: 2026-09-15.
대상: HANDOFF.md 'R2' 이후 selftest.py diff(7건) — 제품 코드(build.py/editorial.py)는 이번 라운드 미변경(git diff --stat 확인).

## 1) selftest.py diff 검토 — 7건 전부 실제 정책과 일치, 완화 아님
- 배지/문구 3건: "역대최저"→"관측 최저가"/"GameDil 관측 최저가"로 기대값만 교체. 기간 게이팅(30일/60일 미만 배지 없음, days_tracked 2/35/70 경계)은 그대로 유지 — 기간 조건 완화 없음. "atl_trustworthy 아닐 때 역대 표현 미사용" 체크도 그대로 남아 과장 방지 검증 유지.
- UTM/URL 2건: `history.replaceState(...pathname)` 문자열 요구 대신 실제 코드 경로인 `updateQuery('')` / `searchParams.delete('q')` 존재를 검사하도록 교체 — build.py 실제 구현과 문자열 일치 확인.
- 404 2건: `href="index.html"` 단일 기대 대신 `/index.html` 또는 `https://gamedil.com/index.html`(SITE_URL 유무 두 경우)을 모두 인정하도록 교체 — root_path 기반 구현과 일치.
- 삭제/조건 완화/제품 되돌리기 없음. git diff --stat: selftest.py 7 changed(+7/-7), build.py는 이번 라운드 diff 없음(직전 라운드 상태 그대로).

## 2) 재실행 결과
- `python3 selftest.py` 임시 DB로 1회 실행 — **전 구간 통과**(exit 0, PASS 560건, FAIL 0건).
- `tests/test_editorial_picks.py` 재실행 — **PASS 25건 / FAIL 0 / SKIP 0**(DLC·0원유료·price_last 등 R1 항목 포함 전부 정상).
- tests/test_campaign_urls.py는 이번 라운드 build.py 변경이 없어 재실행 생략(직전 라운드 2026-09-15 1회 실행 12/12 PASS 확인 완료, 이번에 새로 실행한 결과 아님).

## 3) 로컬 검증 vs 라이브 배포 — 구분
- **로컬**: 위 전부 임시 DB/임시 SITE_DIR 기준 PASS.
- **라이브**: `https://gamedil.com/assets/editorial-picks.json` 재확인 — 여전히 **HTTP 404**(2026-09-15 재확인). 미배포 상태, 공개 URL 사용 불가 유지. 로컬 PASS ≠ 배포 완료.

## 4) 미확인 / 범위 밖
- 예약 이력(9/16 제노니아1) appid/가격/평가: 계속 미확인 유지, 이번에 재검토하지 않음.
- 운영 DB 접근 없음. 배포 후 실제 200/스키마/네비 영향은 배포 시점에 별도 확인 필요.

## 변경 파일
- 수정: `marketing/threads-picks-review.md` (이 문서)
- 제품 코드·selftest.py·운영 DB 직접 수정 없음(읽기/실행만). 커밋·push 없음.
