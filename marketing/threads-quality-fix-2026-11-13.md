# Threads 품질 수정 — 2026-11-13 KST

- 사용자 승인: 네 문제 수정, 기존 제미나이 자동 운영 유지. 자동화 연결/담당 모델/launchd 등록·주기/다른 게시 작업은 변경하지 않았다.
- 결과: `/Users/Work/steam-threads-agent` 운영 스크립트와 테스트·운영 인계를 수정했다. 다음 프로세스 실행부터 새 코드를 읽는다. 실행 중이던 프로세스까지 교체하거나 강제 재시작하지 않았다.

## 변경
1. 인디 후보: 게임+개발 근거 필수, 해시태그/URL만으로 통과 금지. 학원 모집·카메라 앱·달력 펀딩 등 제외. 방명록/피드 수집/기존 후보 생성에 같은 규칙 적용.
2. 실제 게임 문맥인 ‘마법학원 퍼즐 게임’, ‘앱스토어 출시 액션 게임’, ‘달력을 넘기는 게임’은 단어만으로 차단하지 않는다. 최종 게임/개발 주체/구체적 요소 판정은 LLM과 원문 발췌 검사로 보완한다.
3. 소개 전체 문장 LLM 생성: 고정 머리말/마무리 폐기, 최근10개 소개와 유사도 검사, 상투구/허위 플레이 표현 제한. 분류·생성·검증 실패 시 템플릿 대신 생략. 임의 URL을 상점으로 붙이지 않고 작성자의 원본 Threads 링크만 첨부한다.
4. `state/context/indie-spotlight-checks/`에 원문·게임/개발/세부 요소 발췌·생성 본문·전체 예약 payload 해시를 저장한다. `publish_once.py`의 실제 발행 및 validate-only에서 재검증한다. 기존 미검수 초안은 자동 통과하지 않는다.
5. 소개 하루1회: 프로세스 간 예약 잠금, 날짜별 생성/예약 기록, 날짜별 발행 시도 잠금을 추가했다. blocked/failed/unknown/과거 시도 lock도 당일 슬롯 사용으로 계산한다. 실패 후 다른 후보로 교체하거나 반복 모델 호출하지 않는다.
6. `featured`는 예약 즉시 설정하지 않고, 다음 예약 점검에서 published 확인 후 갱신한다. 예약된 후보는 중복 선택하지 않으며, 검토 실패한 첫 후보가 매일 순서를 독점하지 않도록 미검토 후보를 우선한다. 과거 상태는 임의 복구/삭제하지 않았다.
7. 외부 댓글: 5~35자 중심(최대80자), 최소40자 강제 폐기. ‘대단하/흥미롭/기대돼/잘 되길/바래/소중하지’ 등 상투적 칭찬 차단. 질문/이모지/ㅋㅋ 강제 없음, 최근 댓글 문맥 전달, 사실 근거·30일 중복·7일 작성자 제한 유지.
8. 외부 댓글 상한 **20개/일**, 전송 성공 후 **30~60분 무작위 대기** 저장. 이전 nextAllowedAt에도 최근 시도+30분 하한 적용. 동시 실행 잠금 및 전송 직전 일일 상한/활동시간 재확인 추가.
9. 기존 launchd 10분 폴링/0~90초 지터는 유지하므로 실제 간격은 대기 설정보다 더 길 수 있다. 20개는 채우는 목표가 아니다. 자동 운영 모델은 전환하지 않았으며, 내부 문장 생성은 기존 코드의 gpt-4o-mini 경로를 사용한다.

## 검증
- 전체 `.venv/bin/python -m pytest`: **208 passed**, 3.31초. 기존 관련14개 및 신규 포함50개 테스트를 먼저 실행한 뒤 전체 회귀를 확인했다.
- 변경 Python 파일 `ruff check --select F,E9`: 통과. 임시 디렉터리/모의 LLM·클라이언트로 검증, 직접 외부 게시·댓글·실제 LLM 호출 없음.
- 실제 저장된 @soldesk_itcareer/@raccoon_reaf/@blankpoint_prjnote 원문을 새 필터로 읽기 전용 재검증: **3/3 제외**.
- 기존 approved 인디 초안1개 읽기 전용 검사: 검수 기록 없어 차단1/통과0. 큐 파일을 삭제하거나 재예약하지 않았다. 다음 기존 실행기가 새 발행 검증을 적용한다.
- 실패/미확정 후 대체 예약 차단, 날짜별 다른 queue_id 발행 차단, payload/발췌 변조 차단, LLM 거절/잘못된 결과/상투구의 생략, 짧은 댓글·중복/근거 검사, 20개 상한·기존 간격 상태 적용 검증.
- 한계: 생성 문장 품질은 모의 응답으로 동작 검증했으며 다음 실제 자동 실행의 문장·게시 성공은 아직 미확인. 규칙/LLM 조합이 모든 비게임이나 허위 세부 사항을 완벽히 판별한다는 뜻은 아니다. 기존 HTTP 오류 원인 해결은 별개다.

## 변경 파일 및 인계
- 운영: `scripts/indie_spotlight.py`, `scripts/browser_outreach.py`, `scripts/publish_once.py`, `src/steam_threads_agent/browser_outreach.py`, 신규 `src/steam_threads_agent/indie_quality.py`.
- 테스트: `tests/unit/test_browser_outreach.py`, `tests/unit/test_community_growth_features.py`, 신규 `tests/unit/test_indie_quality.py`.
- 인계: `docs/OPERATIONS_COMPACT.md`, `state/context/daily-operating-handoff.txt`; 과거 인계를 보존하고 11/13 기준 우선 명시. 별도 메시지 발송·자동화 신규 생성 없음.
- steamdeal: 본 보고서와 HANDOFF만 추가 수정. 기존 사이트 미커밋 변경, 운영 DB, 큐/발행 이력 보존. 커밋/push 없음.
- steam-threads-agent는 작업 시작부터 전체가 untracked였으므로 git diff만으로 변경을 식별할 수 없다. 변경 전 파일 사본은 `/var/folders/6r/kdgx2jgs2970dzr6h0c74vs40000gn/T/threads-quality-before-l3jax32r`에 보관했다.
