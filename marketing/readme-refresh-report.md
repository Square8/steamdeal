# README 정합성 수정 보고 (2026-09-30, 로컬 기준)

## 결론
- README.md 를 현재 코드·설정에 맞게 수정. 제품 코드·DB·생성물·HANDOFF.md 는 수정하지 않음. 커밋·push 없음.

## 근거 (config.py / workflow 대조)
- REFRESH_QUOTA 0.4→0.25, MAX_APPS_PER_RUN 220→800(약 20분), LANG korean→koreana, BROADCAST_MAX_PRICE 기본 80000 명시.
- MIN_DAYS_FOR_LOW(30), GA_TRACKING_ID, RECENT_REVIEW_* 설정 항목 추가. 깨져 있던 표 행 2곳(SEED_APPIDS, MIN_DAYS_FOR_ATL) 복구.
- '역대 최저가' 표현을 'GameDil 관측 최저가'로 정정(HANDOFF의 홍보 정책과 일치).
- push 는 수집 생략·빌드만, data/**·README.md 변경은 워크플로우 미실행이라는 점 명시.
- 주요 화면 목록, 문서 지도(PROJECT_CONTEXT/HANDOFF/marketing), GA4 클릭 측정 안내 추가.
- 낡은 '스팀 API 응답 미검증' 문구를 운영 중 확인 + 최근 30일 평가는 배포 후 로그 확인으로 교체.

## 검증 범위
- 로컬 `python3 selftest.py` 전 구간 통과(2026-09-30 실행). tests/test_release_regressions.py 는 playwright 없어 DOM 검증 2건 스킵.
- 라이브 배포·GA4·Steam 실응답은 확인하지 않음.

## 재검토 (2026-09-30, 조정 세션)
- README 값(REFRESH_QUOTA·MAX_APPS_PER_RUN·LANG·BROADCAST_MAX_PRICE·MIN_DAYS_*·REQUEST_DELAY·paths-ignore·cron)을 config.py/update.yml과 직접 대조해 일치 확인.
- 잔존한 '역대최저가 의미'(74행) 1곳을 '관측 최저가'로 정정. selftest 재실행 전 구간 통과(로컬).

## 남은 문제 (미수정, 사용자 결정 필요)
- 루트 steamdeal.db(0바이트, 출처 미확인 untracked)는 HANDOFF 규칙에 따라 보존함.
- 최근 30일 평가의 라이브 수집 결과는 배포 후 수동 Actions 실행으로 확인 필요.

## 변경 파일
- README.md, marketing/readme-refresh-report.md
