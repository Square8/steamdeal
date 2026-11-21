# 와글게임 활성화 점검 — 2026-11-06 (Claude)

## 현재 상태 (로컬 파일·로그 기준, 계정 화면 직접 확인 아님)
- Codex heartbeat `steam-threads`는 PAUSED. 지금은 launchd 4개가 운영: publish-due, auto-pipeline(4시간), inbound-reply(30분), browser-outreach(10분, 하루 최대 45).
- 팔로워 78(11/2) → 128(11/6), 최근 조회 422 → 7,750. 성장은 실제로 좋다.
- 외부 자동 댓글: 10/31 11 · 11/1 19 · 11/2 13 · 11/3 8 · 11/4 45 · 11/5 42건 발행.
- 사이트: 홈·인디·후보 JSON 200, 수집 하루 2회 정상(11/5 19:10 UTC), 후보 생성 11/5.

## 바로 막을 것
1. 11/7 19:47 예약 `gamedil-pick-bills-must-be-paid`: "7,600원에서 7,600원(-0%)까지 내려왔더라구! … 지금 털기 딱 좋은 타이밍" — 할인이 없는데 할인 글. 원인 `scripts/auto_daily_pipeline.py:556` 템플릿이 할인 0%를 거르지 않음.

## AI 티가 나는 곳 (우선순위)
1. 외부 자동 댓글(`compose_zero_token_gamer_reply`): 고정 문구 수십 개를 키워드로 골라 하루 45건. 상대 글을 보지 않고 "찰진 손맛이랑 BGM이 진국", "도트나 아트 감성이 취향 저격" 같은 내용을 단정 → 받는 사람이 봇이라고 바로 느끼는 유형. 같은 문장이 여러 사람에게 반복됨. 자동 언팔로우 기록(unfollow-history)도 있음.
   위험: Threads 스팸 판정·행동 제한, Meta 자동화 수집 약관. 계정이 막히면 지금까지 성장분 전체가 위험.
2. 뉴스 글: 기사 리드 문장·스팀 상점 설명을 그대로 붙임("빚어낸 명작", "당신을 기다리고 있어", "~합니다"체) + "다들 어떻게 생각해?ㅎㅎ". 기사체와 반말이 섞여 복붙 티가 남. 기사 원문 복제는 저작권 문제도 있음.
3. GameDil 픽: 모든 글이 같은 틀("해본 사람 있어? → 내려왔더라구! → 털기 딱 좋은 타이밍").
4. 하루 본문 약 6개(아침 뉴스·인디 뉴스·정보·픽·스포트라이트·커뮤니티). 필러가 많아 피드가 자동 계정처럼 보임.

## 잘 되고 있는 것 (유지)
- 번호 선택형 커뮤니티 질문(회고 기록상 댓글 전환 최고), 방명록 인디 스포트라이트(실제 사람을 소개 → 관계 형성), 구체적 정보 팁(11/5 동적 컬렉션).

## 제안
1. 외부 댓글은 "자동 탐색 + 초안 → 사람이 보고 누름"으로 전환. 유지한다면: 하루 15건 이하, 상대 글 내용을 단정하는 문구 삭제, 같은 문장 30일 재사용 금지, 자동 언팔로우 중지.
2. 하루 본문 3~4개로 축소: 커뮤니티 질문 + 픽 + (스포트라이트 또는 정보). 뉴스 복붙 글은 중단하거나 한 줄 요약 + 내 의견으로.
3. 픽 템플릿: 할인 0%·가격 미변동이면 게시 안 함. 문형 3~4개를 돌리고 `threads-writing-guide.md` 금지 상투구 적용.
4. 측정: 픽 첫 댓글 GameDil 링크에 UTM이 빠짐(10월엔 있었음). `utm_source=threads&utm_medium=social&utm_campaign=gamedil_picks` 복구해야 GA에서 Threads 유입을 셀 수 있음.
5. 사이트 쪽(작은 것): 스포트라이트·커뮤니티로 들어온 사람에게 맞는 GameDil 입구(예: 이번 주 픽 모음 페이지)를 프로필 링크로 두는 것 검토. 급하지 않음.

변경 없음: steam-threads-agent 코드·예약·launchd, GameDil 코드/DB.

## 11/13 추가 — 자동화 안전장치 점검 (제미나이 보고 4건 코드 대조)
- 확인: 자동 좋아요 일일 상한 없음(browser_outreach.py like_js, 10분 실행마다), 맞팔(inboundFollows)과 선팔 상한 25 분리, auto_reply_inbound.py 고정 문구("장바구니 털기 딱 좋은 타이밍… GameDil에서", "피드에서 소개해줄게" 약속), 계정 전체 정지 스위치 없음.
- 판단: 모두 위험. 새 기능이 아니라 상한·정지 장치 보강으로 처리 권장.

## 11/21 발행 중단 원인·조치 (Claude)
- 원인: api_conversations.py 미확정 판정이 새 상태 skipped_no_reply를 "전송 미확정"으로 오판 → 답글 2건 차단이 연속 쓰기 실패로 집계 → 11/21 00:19 KST STOP_ALL_WRITES. 실제 오발송 없음(마지막 실제 답글 11/19 verified).
- 조치: skipped_* 전체를 미확정에서 제외. 정지 파일은 state/stop-history/로 보관, 연속 실패 카운터 0. dry-run에서 차단 없이 초안 생성 확인. 관련 테스트 23 통과, 2 실패(test_write_safety의 좋아요·팔로우 상한 — 이번 수정과 무관한 기존 실패).

## 11/21 후속 점검·수정 (Gemini)
- 재정지 원인: Claude 조치 6분 뒤(`19:27:44 KST`) `STOP_ALL_WRITES` 재발동. `api_conversations.py:305`의 120초 버스트 제한 쿼리에서 `skipped_*`가 빠지지 않아 `skipped_no_reply` 직후 4초 만에 `"Do not burst-send"`로 2연속 차단됨. `auto_reply_inbound.py`가 1틱 내 2초 간격으로 다중 발송을 시도하고 로컬 쿨다운 차단을 `record_write_outcome(ok=False)`로 집계하던 문제도 함께 확인.
- 수정(4건):
  1. `api_conversations.py:305` 버스트 제한 쿼리에서 `skipped_*` 제외, `auto_reply_inbound.py`는 라이브 틱당 최대 1건 발송(`break`) 및 `"Do not burst-send"`·문맥 변경 차단은 연속 쓰기 실패 미집계.
  2. `auto_daily_pipeline.py` Slot 4(`build_slot4_discount_multi_post`) `_build_slot4_reply_text()` + 본문 길이 트림으로 `reply_text` 500자 초과(`11/20` Slot 4 누락 원인) 방지.
  3. `experiment_metrics.py` 오프라인/API 실패 시 `experiment-2w-status.json` 및 `snapshots` 0건 덮어쓰기 방지(기존 상태 보존).
  4. `news_candidates.py`·`auto_daily_pipeline.py` Slot 3(`build_slot3_indie_news_post`)에 `is_indie`/장르 필터 추가(`God of War` 등 비인디 AAA 혼입 차단).
- 검증·복구: 7개 스위트 118건 통과 + `test_write_safety.py` 대상 4건 통과(날짜 하드코딩 기존 2건 제외). `experiment_metrics.py --write-report`로 라이브 상태(`experiment_2w_count=19`, `12_팁/무료` 경고) 복구. `state/STOP_ALL_WRITES`를 `state/stop-history/STOP_ALL_WRITES-2026-11-21-1927.json`으로 보관 후 `consecutiveFailures=0` 초기화, `auto_reply_inbound.py --dry-run` 정상(`processed=10`, 정지 파일 미생성) 확인. 커밋·push 없음.

## 11/21 22시 전체 점검 (Claude, 코드·로그·큐 확인, 코드 수정 없음)
- 정상: STOP 없음, 연속 실패 0, 답글 기록에 전송 미확정 0(verified 70·skipped 14), 오발송 없음. browser-outreach는 launchd `disabled`라 재부팅해도 안 켜짐.
- 오늘 실제 발행 1개(08 뉴스, 19:2x 지연 발행). 12시 `news-midday-2026-11-21`은 큐에 추가된 뒤 기록 없이 사라짐(파이프라인 코드에 삭제 경로 없음 → 수동 삭제 추정). 16시는 주간 인디 3회 충족으로 정상 생략. 19시는 18~20시 실행에서 사유 없이 미생성. 지금 같은 로직을 재현하면 정상 생성(3개, reply 487자), 500자 수정 전 실패로 추정. 실패 사유가 결과에 남지 않는 구조.
- 받은 답글 자동응답: 20:2x 이후 매 실행 중단(exit 1). `inbox()`→`prepare()`가 대상 1건의 `ConversationBlocked`("Target identity, text or permalink is missing", "Already answered this target")로 전체 예외 종료. 쓰기는 없어 위험은 아니지만 답글 응답이 전부 멈춤. 기록되지 않아 매번 같은 대상에서 반복.
- 테스트: 231 통과, 4 실패(브라우저 상한 2, 날짜 의존 `test_check_and_heal_queue...` 1, 인디 태그 기대값 `게임개발`≠`인디게임` 1).
- 글 품질: 답글 존댓말·반말 혼용, 끝 이모지 반복, 근거 없는 단정("프레임 저하 문제", "기대에 못 미칠 때가 많더라"), 할인작 끼워넣기("Shape of Dreams도 놓치지 말고"). 11/20 16시 "스팀 인디·신작 God of War"(필터 수정됨).

### 안전 활성화 순서
1. inbox에서 대상별 차단은 건너뛰고 `skipped_unavailable`로 기록(전체 중단 방지).
2. 파이프라인 슬롯 실패 사유를 결과에 기록(조용한 누락 제거). 큐 파일은 사람이 지우지 말고 blocked로 옮기기.
3. 정지 해제 후 밀린 글 일괄 발행 방지: 예약 시각보다 3시간 넘게 늦은 글은 발행하지 않고 건너뛰기.
4. 답글 글쓰기 기준: 반말 통일, 이모지 최소, 사실 단정·할인 홍보 금지, 모르면 질문으로.
5. 실패 테스트 4개 정리.
6. 위가 끝나고 3일간 5슬롯이 빠짐없이 나가는지 본 뒤에만 다른 개선 검토.

### 11/21 22시 조치 — 답글 자동응답 중단 수정 (Claude)
- `api_conversations.py` `inbox()`: 대상별로 맥락을 읽고, 막힌 대상은 건너뜀(전체 중단 없음). 다시 실행해도 바뀌지 않는 차단(글자 없음·이미 답함·내 댓글·이미 참여)만 `skipped_unavailable`로 기록해 다음부터 제외. 일시적 차단은 기록 없이 이번 회차만 건너뜀. 결과에 `unavailable` 목록 추가.
- 테스트: `test_inbox_skips_unusable_target_without_aborting` 추가. 대화 테스트 19 통과, 전체 232 통과 / 기존 실패 4 그대로.
- 실데이터 dry-run: 중단 없이 초안 생성, 대상 1건(18277522210305441, 글자 없는 답글) `skipped_unavailable` 기록. 정지 파일 없음. 실제 발송은 30분마다 1건씩.
- 남은 일: 슬롯 실패 사유 기록, 3시간 넘게 늦은 글 건너뛰기, 답글 글쓰기 기준(dry-run 초안에도 "데이즈곤도 꽤 재밌더라"처럼 해본 척하는 문장·이모지 반복 있음), 실패 테스트 4개.

### 11/21 22시반 조치 — 남은 항목 수정 (Claude)
- 새로 찾은 문제: `daily_health_check.py`가 매시간 파이프라인 안에서 (1) 문제 있어 보이는 예약 글을 기록 없이 삭제(12시 `news-midday` 실종의 유력 원인, 사유는 남지 않아 확인 불가), (2) 답글을 직접 live 발송(인바운드 전용 작업과 별도로 두 번째 발송 경로)하고 있었음. dry-run도 `skipped_*`를 기록해 그 댓글에 영영 답하지 않게 만들고 있었음.
- 수정:
  1. `publish_due.py`: 예약(또는 미룸) 시각보다 3시간 넘게 늦은 글은 발행하지 않고 blocked로, 상태 `skipped_stale` 기록. 쓰기 실패로 세지 않음.
  2. `auto_daily_pipeline.py`: 슬롯마다 건너뜀·실패 사유 기록(`weekly_indie_limit_reached`, `no_discount_candidates`, `build_failed`, `multi_preflight_failed`, `already_attempted`, 그 외 `no_candidate_generated`). 19시 묶음 글 생성 오류가 파이프라인 전체를 멈추지 않음.
  3. `daily_health_check.py`: 불량 예약 글은 `data/queue/removed/`로 옮기고 `state/operations/queue-removals.jsonl`에 사유 기록(재생성은 그대로). 답글 발송 제거, 인바운드 작업 상태만 보고.
  4. `auto_reply_inbound.py`: 프롬프트에 경험담·근거 없는 평가·홍보 금지, 이모지 금지, 15~60자. 코드에서도 검사: 이모지 제거, "해봤/더라/좋았어(질문 제외)" 같은 경험담, "할인/최저가/○○원/구매" 같은 홍보, 100자 초과는 한 번 다시 쓰게 하고 또 걸리면 보내지 않음. dry-run은 기록을 남기지 않음.
- 정리: 내 dry-run이 남긴 `skipped_no_reply` 3건 삭제(백업 `ledger.backup-2026-11-21-2225.sqlite3`).
- 테스트: 236 통과, 2 실패(브라우저 좋아요·팔로우 상한, 브라우저 자동화는 꺼져 있음). 옛 기대값 테스트 3개를 현재 규칙에 맞게 고치고 새 테스트 3개 추가.
- 실데이터 dry-run: 이모지 없음, 질문형으로 바뀜. 남은 약점은 "위쳐 3는 영화처럼 느껴질 때가 있네" 같은 가벼운 의견 단정. 10건 중 3건은 규칙 위반으로 보내지 않음(안전한 쪽).

### 11/22 04시 — 답글 속도 적용 + 재정지 원인 (Claude)
- 적용(`auto_reply_inbound.py`): 한 번 실행에 최대 3건, 건 사이 130초(120초 연속 발송 차단 유지), 하루 40건 상한(KST 자정 기준, 실제 발송만 셈). launchd `inbound-reply`를 30분→10분 간격으로 바꾸되, 22~02시 외에는 스크립트가 약 30분마다만 실제 처리. 기존 plist 백업 `state/generated-launchd/inbound-reply.plist.bak-1800`.
- 재정지: 11/21 23:59 `STOP_ALL_WRITES`. 23:27 답글(@mbkilar)이 실제로 올라갔지만, API가 돌려준 본문에서 맨 앞 `@`가 빠져 글자 비교가 실패 → `unverified` → 다음 답글이 "미확정"으로 막힘 → 2연속 실패.
- 조치: 발행 후 확인에서 "맨 앞 @ 한 글자 빠짐"만 허용(`published_text_matches`, 나머지는 완전 일치). 해당 답글은 읽기 전용 대조(`resolve`)로 `verified` 처리(https://www.threads.com/@waglegame/post/DgAcZNUEggo). 미확정 0건.
- 정지 해제는 하지 않음(자동 권한에서 막힘, 사용자 확인 필요). 정지 중이라 11/22 08시 글도 나가지 않음.
- 테스트: 실패 2(기존 브라우저 상한)만 남음, 새 테스트 4개 추가. dry-run 정상(10건 중 7건 초안). 초안에 "설원에서의 첫 경험은 항상 감동적이야" 같은 지어낸 문장이 아직 있음.
- 11/22 04:30 사용자 요청으로 정지 해제: `STOP_ALL_WRITES`를 `state/stop-history/STOP_ALL_WRITES-2026-11-21-2359.json`으로 보관, 연속 실패 2→0. 대기 중인 예약 글 없음(11/21 23시 글은 23:40 정상 발행). 08시 글은 06~10시 파이프라인이 생성.
