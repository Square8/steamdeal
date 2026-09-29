# 최근 30일 평가 — 구현 보고 (Claude, 2026-09-26, R1: cursor 반복 처리 수정)

상태: **로컬 구현·테스트 완료, 커밋 전 Codex 검토 필요.** 라이브 Steam API 실호출은 미검증(아래 한계).

## 변경 파일
- `config.py`: `RECENT_REVIEW_*` 상수 12개(기간·페이지 크기·게임당/실행당 한도·후보 기준·갱신 주기·최소 표본·표시 유효기간·연속 실패 차단).
- `steam.py`: `fetch_recent_reviews()` 신규. 기존 `fetch_review_summary()`는 그대로.
- `store.py`: games 칼럼 5개(`recent_review_total/positive/computed_at/attempt_at/status`) 스키마+`_migrate` 추가, `recent_review_appids()`·`save_recent_reviews()` 신규.
- `collect.py`: `_collect_recent_reviews()` 신규, 기존 `_collect_signals()` 직후 1줄 호출. `--signals-only` 경로는 변경 없음.
- `build.py`: `recent_review_fact()` 신규, 상세 페이지 facts에 '최근 30일 평가' 행 1개 조건부 추가.
- `tests/test_recent_reviews.py`(신규), 이 문서.

## 집계 정의
- `appreviews/{appid}`를 `filter=recent`(작성 시각 내림차순), `language=all`, `review_type=all`, `purchase_type=all`, 100개/쪽, cursor(`*`부터)로 조회. `query_summary`·`day_range`는 사용하지 않음.
- 경계: `cutoff = 수집 시각 − 30×86400초`, `timestamp_created ≥ cutoff`만 포함(정확히 30일 포함). 긍정 = `voted_up is True`. 긍정률 = 긍정/30일 전체, 분모도 저장·표시. `recommendationid` 중복 제외.
- 완전 집계(complete) 조건: cutoff보다 오래된 리뷰를 만남, 또는 빈 페이지(리뷰 끝). 이 두 경우만 수치 저장.
- (R1 수정) 리뷰가 남은 응답에서 이미 쓴 cursor가 다시 오면 다음 페이지로 진행할 수 없어 30일 경계를 확인하지 못한 것이므로 `error`(불완전)로 처리. 부분 집계는 저장·표시하지 않음.
- 불완전: 게임당 20쪽 한도(`limit`), 실행 예산 소진(`budget`), 요청 실패·`success≠1`·필드 누락·cursor 누락·리뷰가 남은 상태의 cursor 반복(`error`) → 수치 미저장, 시도 시각·상태만 기록. 이전 완전 집계는 보존(집계 시각이 있어 신선도 판단 가능).
- 표시: 완전 집계가 7일 이내일 때만. 10개 이상 → "긍정 95% · 1,635개 (9월 26일 집계)", 1~9개 → "최근 평가 표본 적음 · 3개", 0개·모순값·오래된 값·집계 없음 → 행 생략. 안내문: "최근 평가는 업데이트나 이벤트 전후로 달라질 수 있습니다. 평가 변화의 원인은 판단하지 않습니다." 기존 'Steam 평가' 행 바로 아래.

## 요청 예산 / 커버리지 (운영 DB 사본 기준 추정)
- 후보: 한국어·출시·정식 게임, 전체 리뷰 ≥ 50 → **171개**(이 중 전체 리뷰 5만+ 53개).
- 실행당: 최대 40게임·200요청, 요청 간 0.8초 → **약 3분 추가**(워크플로 45분 제한, 기존 약 25분). Steam 장애 시 연속 3회 실패에서 중단(약 1분).
- 순환: 미시도 → 동접/할인 신호 → 오래전 시도 순. 60시간 내 재시도 안 함(하루 2회 실행 → 약 3일 주기). 20쪽(2,000개) 한도에 걸린 대작은 7일 쿨다운.
- 예상: 첫 전체 순회 약 7회 실행(3~4일). 이후 60시간 창당 필요 요청 ≈ 700~750 < 예산 1,000(5회×200). 월 리뷰 2,000개 초과 대작은 완전 집계 불가 → **표시 안 됨**(의도된 보수적 동작).

## 테스트 결과 (로컬, 임시 DB/SITE_DIR)
- `tests/test_recent_reviews.py`: **FAIL 0** (43항목, R1) — 30일 정확·직전·직후 경계, 긍정/부정 비율, 3쪽 cursor 순서·합산, 오래된 리뷰에서 종료(추가 요청 없음), 빈 페이지 종료, 리뷰가 남은 cursor 반복(1쪽째·2쪽째)→error, 실제 fetch→collect→build 통합으로 반복 cursor 부분 집계(5개) 미저장·기존 완전 집계(500/450) 유지·상세 행 미표시, 중복 제외, 게임당 한도·실행 예산, 요청 실패·success≠1·voted_up 누락·cursor 누락, 불완전 시도가 이전 값 미덮어쓰기, 후보 필터·60시간/7일 쿨다운, 예산 전달·소진 중단, 연속 실패 차단, 기존 전체 평점 칼럼 보존, 실제 `build.main()` 상세 HTML(정상/표본 적음/생략 5종, 최근 행 제거 시 기존 HTML과 동일).
- 변이 검증: 경계 `<`→`<=`, 0개/모순값 필터 제거, limit 저장 허용, cursor 반복을 complete로 되돌림 → 각각 해당 테스트 FAIL 확인(오라클 유효).
- `selftest.py` exit 0 (PASS 575, 기준선과 동일). `test_steam_click_tracking`/`test_wishlist_share`/`test_random_pick`/`test_editorial_picks`/`test_navigation_sorting` 실패 0.
- `test_campaign_urls`(검색어 지우기 q 제거 1건), `test_release_regressions`(Escape 합성 이벤트 1건) 실패는 **변경 전 코드에서도 동일하게 실패**(기존 이슈, 이번 변경과 무관).
- 운영 DB 사본으로 변경 전/후 전체 사이트 빌드(7,589개 상세) `diff -rq` → `editorial-picks.json`의 `generated_at` 타임스탬프 1곳만 다름. 마이그레이션 칼럼 5개 추가 확인.

## 남은 한계
- 이 환경은 store.steampowered.com이 프록시에서 차단되어 실제 API 응답 형식(filter=recent 정렬·cursor 반복)을 실측하지 못함. 차단 상태에서 `error`로 기록되고 수치가 남지 않는 것만 확인. 배포 후 Actions 로그의 "최근 30일 평가 완료 — 시도/완전/한도/실패" 줄로 확인 필요.
- Steam 상점의 '최근 평가'는 구매 경로·언어 설정·오프토픽 필터가 달라 숫자가 다를 수 있음. 오프토픽(리뷰 폭탄) 필터는 Steam API 기본값 사용.
- (R1 영향) Steam이 리뷰 목록 끝에서 빈 페이지 대신 같은 cursor를 돌려주는 경우, 전체 리뷰가 모두 최근 30일 안에 있는 게임(대략 출시 30일 이내 신작)은 경계 리뷰를 만나지 못해 `error`가 되어 표시되지 않음. 보수적 동작으로 의도된 것이며, 배포 후 로그에서 이런 사례가 많으면 종료 조건을 다시 검토.
- 운영 DB에는 아직 값이 없으므로 다음 예약/수동 수집 전까지 화면 변화 없음.
- 커밋·push 하지 않음. `steamdeal.db`, `site/`, 운영 DB 미변경.
