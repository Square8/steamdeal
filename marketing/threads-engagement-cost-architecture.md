# Threads 소통 운영 비용 절감 구조 제안 — 2026-10-17

작성: Claude (steamdeal 세션). 대상: 사용자·조정자(Codex)·steam-threads-agent 운영.
근거 구분: **[실측]** 로컬 기록에서 직접 집계 / **[문서]** 공식 문서 확인 / **[추정]** 가정 기반 계산 / **[미확인]** 검증 안 됨.
코드는 수정하지 않았다. steam-threads-agent의 문서와 사용량 기록만 읽었다.

---

## 1. 현재 병목 진단

**핵심 결론: 비용은 "브라우저 조작"이 아니라 "한 채팅에 모든 실행을 쌓는 구조"에서 나온다.**

[실측] `~/.codex/sessions/2026/08/25/rollout-…-01a034f2….jsonl` 채팅 하나의 token_count 이벤트 기준.
이 채팅에는 8/25부터의 일반 대화와 10/16~17 개편 작업이 섞여 있어, 순수 운영 3회분이 아니다.

| 날짜 (UTC) | 모델 호출 | 입력 합계 | 그중 캐시 | 출력 | 호출당 평균 입력 |
|---|---|---|---|---|---|
| 10-12 | 40 | 9.7M | 8.9M | 7.6k | 241,708 |
| 10-14 | 43 | 14.5M | 14.0M | 10.2k | 337,411 |
| 10-16 | 449 | 133.5M | 131.3M | 75.4k | 297,346 |
| 10-17 | 649 | 135.9M | 133.3M | 204.4k | 209,381 |

- 호출 1번마다 **약 21만~34만 토큰의 채팅 이력 전체**가 다시 입력된다. 출력은 호출당 수백 토큰뿐이다.
- 입력의 약 98%가 캐시 입력이라 단가는 낮지만, 절대량이 하루 1억 토큰을 넘는다.
- 브라우저 클릭·조회 한 번이 모델 호출 한 번이다. 그래서 **(이력 크기) × (도구 호출 수)**로 곱해진다.
  댓글을 줄이거나 모델을 바꾸지 않아도, 이력 크기를 1/10로 줄이면 비용도 거의 1/10이 된다.
- 비교 기준 [실측]: 새 API 초안 경로의 합성 벤치마크는 1건에 입력 410, 출력 104 토큰이었다
  (`state/api-conversations/benchmark-v1`). 실제 대화 품질이나 30건 비용의 근거는 아니다.

**두 번째 병목은 약관 쪽 제약이다.**
[문서] Meta Automated Data Collection Terms는 스크레이퍼·봇·프로그램 방식 접근을 포괄해
"Meta의 명시적 서면 허가 없이 자동 데이터 수집을 하지 않는다"고 정한다.
그래서 "코드가 브라우저로 Threads를 긁고 LLM에는 작게 넘긴다"(요청 5번)는
기술적으로는 가능해도 **허가 없이는 권장할 수 없다**.
현재의 "AI가 브라우저를 조작해 탐색"도 같은 정의에 걸릴 여지가 있다. 이건 법률 판단이 아니라
약관 문구 기준의 위험 표시이고, 계속할지는 사용자가 정한다.

## 2. 가능한 방법 비교표

| 수단 | 현재 권한으로 | 근거 | 비용 | 비고 |
|---|---|---|---|---|
| 우리 글에 달린 답글 조회 (`/replies`, `/conversation`) | **가능** | [실측] 실계정 inbox 동작 | 모델 0 | 이미 구현됨 |
| 우리 루트 글 안에서 답글 게시 (`reply_to_id`) | **가능 (문서상)** | [문서] 루트 글 소유 시 허용 | 모델 0 | live 잠금 해제 전 1건 실전 검증 필요 |
| 타인 글에 API로 댓글 | **문서상 조건부** | [문서] `threads_keyword_search` 또는 `threads_manage_mentions` 권한 보유 시 허용 | 모델 0 | 승인 전(표준 접근)에서도 되는지 [미확인] |
| 타인 글 원문·대화 API 조회 | **[미확인]** | [문서] 소유 제한 문구 없음, 지원 명시도 없음 | 모델 0 | 승인 없이 media ID를 얻는 공식 경로가 없음 |
| 공개 키워드 검색 | **승인 필요** | [문서] 승인 전에는 본인 글만, 24시간 2,200쿼리 | 모델 0 | [실측] 8건 모두 우리 글 |
| 멘션 조회 | **승인 필요** | [문서] advanced access 전에는 테스터 멘션만 | 모델 0 | |
| 기존 상대 새 글 (`profile_lookup`, `profile_posts`) | **사실상 승인 필요** | [문서] 표준 접근은 Meta 공식 계정만 조회 | 모델 0 | `profile_posts` 권한 [미확인] |
| oEmbed | **수집 용도 불가** | [문서] 임베드 외 사용 금지, 메타데이터로 분석 금지 | — | 원문 확보 수단으로 쓰면 안 됨 |
| 외부 검색엔진 | 제한적 | Google Custom Search JSON API는 신규 불가, 2027-01-01 종료 | 쿼리 비용 | 색인 지연·누락 [미측정]. 몇 시간짜리 대화엔 늦음. 결과 페이지를 코드로 긁으면 다시 약관 문제 |
| 코드 브라우저 자동화 (Playwright 등) 수집 | **권장 불가** | [문서] 자동 수집은 서면 허가 필요 | 모델 0 | 요청 5번의 답 |
| AI 브라우저 조작 (현재) | 사용자 판단 | 위와 같은 약관 위험 | **[실측] 하루 1억+ 토큰** | 세션 분리만으로도 크게 절감 |
| **사람이 탐색 → URL·본문을 큐에 등록** | **가능** | 사람의 일반 사용 | 모델 소량 | 하루 15~25분 [추정] |

## 3. 추천 구조와 선정 이유

**추천: "들어오는 대화는 API로 완전 자동화 + 나가는 대화는 사람이 발견하고 코드가 처리"하는 하이브리드.**
공개 검색 승인 여부는 별도 결정으로 분리한다.

| 단계 | 일반 코드 | LLM | 브라우저·사람 |
|---|---|---|---|
| 1. 발견 | inbox API 조회. 사람 큐 파일 수집 | 없음 | 사람이 폰·앱에서 평소처럼 보다가 "공유 → 큐" |
| 2. 선별 | 중복(대상 ID·URL·작성자), 쿨다운, 이미 참여, 24시간 경과, 키워드 규칙 | 애매한 것만 1회 배치 판정 (선택) | 없음 |
| 3. 대화 조회 | 우리 글은 API `/conversation`. 외부 글은 사람이 붙여넣은 본문·답글 | 없음 | 외부 글은 사람 |
| 4. 초안 | packet 생성(원문·답글 최대 N개·우리 이력 요약·정책 해시) | **단발 Responses 호출, 3~5개 묶음** | 없음 |
| 5. 검수 | 금지어·링크·길이·반복 문체 n-gram·같은 상대 연속 규칙 | 선택: 위험 플래그만 재검 | 사람 승인 (초기 필수) |
| 6. 전송 | 우리 글: API `reply_to_id`. 외부 글: API 지원 검증 전엔 사람이 앱에 붙여넣기 | 없음 | 외부 글은 사람 |
| 7. 완료 확인 | API로 우리 최근 답글 조회 → 본문·부모 ID·permalink 대조 → verified | 없음 | 없음 |
| 8. 후속 추적 | 다음 실행 inbox가 우리 답글의 답을 자동 수집, 대화 상대 기록 갱신 | 없음 | 없음 |

**선정 이유**
1. 약관 위험 없이 현재 권한으로 바로 구현할 수 있다. 위 표에서 [미확인]인 단계는 전부 사람이 대신한다.
2. LLM은 4단계 한 군데에서만 호출된다. 브라우저 도구 루프가 사라져서 호출 수가 하루 수백 회에서 10~15회로 준다 [추정].
3. 품질은 오히려 오른다. 대상 선택은 사람 판단이고, 초안은 정책을 담은 짧은 문맥에서 나온다.
4. 비용이 줄어드는 대신 사람 시간이 늘어난다. 이 교환을 받아들일지가 핵심 판단이다.

**대안 (현행 AI 브라우저 탐색 유지)**
약관 위험을 감수하고 유지하더라도, 아래 "즉시 변경 1"(세션 분리)만으로 [실측] 호출당 21만~34만 토큰을
수만 토큰대로 낮출 수 있다 [추정]. 활동 방식은 그대로 두고 문맥만 줄이는 방법이다.

**장기 (승인 경로)**
공개 키워드 검색이 승인되면 1·3단계를 API로 옮길 수 있다. 다만 앱 검수 버튼이 Tech Provider 전환을
요구하고 되돌릴 수 없다는 경고가 있다. 전환이 가져오는 의무·제약은 이번에 확인하지 못했으므로,
공식 문서로 확인한 뒤 사용자가 결정해야 한다.

## 4. 즉시 적용할 변경 3가지

**1. 운영 실행을 장기 채팅에서 분리** (효과가 가장 큼)
- 매 실행(11·15·21시)을 새 세션으로 띄운다. 예: `codex exec --ephemeral`.
  [문서] `--ephemeral`은 세션 기록을 디스크에 남기지 않고, `-o`로 마지막 메시지만 파일에 쓰고,
  `--output-schema`로 JSON 결과를 강제한다.
- 시작 문맥은 `operation_context.py --brief` + 인계 1,200자 + `OPERATIONS_COMPACT.md`만 둔다.
  필요한 원문 정책은 해시가 바뀔 때만 읽는다.
- 이 대화형 채팅은 의사결정용으로만 남긴다.
- 측정은 `operation_usage.py`로 새 세션 rollout의 호출 수와 호출당 입력을 기록한다.

**2. 받은 답글 경로를 API로 완결**
- 이미 있는 `inbox → prepare → draft → approve → publish`에서 live 잠금을 풀기 위한 두 가지를 끝낸다.
  (a) 기존 브라우저 일지·DB의 미확정 전송과 대조한다.
  (b) 사용자 승인하에 **우리 루트 글 안 답글 1건**으로 실전 검증한다.
- 이 경로는 문서상 지원되고 약관 문제도 없다. 브라우저가 전혀 필요 없다.

**3. 외부 발견을 "사람 큐"로 전환**
- `queue/manual-targets.jsonl` 형식을 정하고, Apple 단축어(공유 시트)로 URL·본문·한 줄 메모를 붙여 추가한다.
- 코드는 큐만 읽어 2~4단계를 처리한다. 외부 글 전송은 사람이 앱에서 붙여넣기로 한다.
- 7단계 확인은 API로 우리 답글 목록을 조회해서 한다. 우리 계정의 답글 목록 조회 엔드포인트 사용 가능 여부는
  한 번 확인해야 한다 [미확인].
- 타인 글 API 댓글은 "권한 보유 시 허용"이라는 문서 문구가 있으므로, 사용자 승인하에 1건 테스트한 뒤 전환을 결정한다.

## 5. 구현 순서와 데이터 형식

**구현 순서**
1. 세션 분리 실행기: launchd → 래퍼 스크립트 → `codex exec --ephemeral -o result.json --output-schema run.schema.json`.
   종료 시 인계와 사용량을 기록한다.
2. 사용량 비교: 기존 채팅 기준선 [실측]과 새 세션 실행 3회를 비교한다.
3. live 잠금 해제 전 검증: 이력 대조 → 우리 글 답글 1건 → verified 확인 → 잠금 해제는 사용자가 결정한다.
4. 사람 큐: 스키마, 단축어, 수집기, 중복 검사.
5. 초안 배치화: packet 3~5개를 묶어 1회 호출하고, 결과를 대상 ID별로 분리해 저장한다.
6. (선택) 외부 글 API 댓글 1건 검증 → 성공하면 6단계 자동화, 실패하면 사람 전송 유지.

**큐 한 줄 (`queue/manual-targets.jsonl`)**
```json
{"queued_at":"2026-10-18T11:02:00+09:00","url":"https://www.threads.com/@user/post/XXXX","author":"user","text":"원문 전문","context":["보이는 답글 2~5개"],"note":"인디 데모 추천 질문","source":"manual"}
```

**중복 방지**
- 키는 `url` 정규화 값(쿼리 제거, `/t/` 형식 통일)과, 외부 글이면 작성자+본문 해시로 한다.
- SQLite `targets(key UNIQUE, status, first_seen, last_action)`를 둔다.
  기존 sends 테이블(대상·문구 예약, 120초 간격, 동일 문구 차단)을 그대로 재사용한다.
- 같은 작성자에게 우리 답이 미응답 상태면 쿨다운을 건다(예: 72시간). 기존 정책
  "답 없이 반복 댓글 금지"를 코드화한 것이다.

**packet (LLM 입력)**
- 고정 접두부(시스템 지시 + 톤 정책 + 금지 규칙)를 1,024토큰 이상으로 두고 앞에 고정한다.
  [문서] 1,024토큰 이상이면 캐시 대상이고, 접두부가 완전히 일치해야 재사용된다.
  GPT-5.6 이후 TTL은 30분이라 같은 실행 안의 묶음끼리만 캐시 이득이 있다.
- 가변부는 대상별 원문(최대 1,500자) + 답글 최대 5개 + 우리 이력 요약 3줄로 둔다.
- 출력은 Structured Outputs 스키마 `{target_key, reply_text, tone, risk_flags[], needs_human_fact}`로 받는다.

**검증 절차**
- 전송 전: 계정 `@waglegame` 일치, 대상 상태가 미참여인지, 문구 해시 중복 여부, 120초 간격.
- 전송 후: API로 우리 답글을 조회해 본문·부모 ID·permalink가 일치해야 verified.
  불일치·타임아웃은 미확정 → 해당 실행의 쓰기를 중단하고 재전송하지 않는다(현행 유지).

## 6. 비용 산정 (댓글 30개/일)

**가정 [추정]**
- 선별 LLM 3회/일: 고정부 1.5k + 후보 30개 × 80토큰 ≈ 3.9k 입력, 400 출력.
- 초안 10회/일: 3개 묶음, 고정부 2k + packet 3 × 1.5k ≈ 6.5k 입력, 추론 포함 1k 출력.
- LLM 검수는 하지 않는다(코드 규칙 + 사람 승인).

| 항목 | 호출 | 입력 | 출력 |
|---|---|---|---|
| 선별 | 3 | 약 12k | 약 1.2k |
| 초안 | 10 | 약 65k | 약 10k |
| **합계** | **13** | **약 77k** | **약 11k** |

**가격** [문서, OpenAI 공식 가격표]
- gpt-6-luna Standard: 입력 $0.10, 캐시 입력 $0.01, 출력 $0.50 (1M토큰당). Batch·Flex는 50%.
- 위 합계는 캐시를 무시해도 **하루 약 $0.013** [추정]이다.
  출력이 2배, 입력이 3배로 늘어도 하루 $0.05 안팎이다.

**현행과 비교**
- [실측] 10-17 Codex 채팅 한 곳의 입력은 1억 3,590만 토큰(캐시 1억 3,330만), 출력은 20만 토큰이었다.
- 참고 환산 [추정]: 같은 토큰을 gpt-6-luna API 단가로 매기면 약 $1.7/일, gpt-6-sol 단가면 약 $34/일이다.
- 다만 Codex는 ChatGPT 플랜 사용량으로 소진되고, 실제 사용 모델과 청구액은 확인하지 못했다.
  비교는 **토큰량 기준(약 1,000배 차이)**으로만 본다.

**API 쿼터 [문서]**
- 키워드 검색은 24시간 2,200쿼리, profile_lookup은 1,000건, oEmbed는 시간당 1,000건이다.
- 이번 구조의 API 읽기는 하루 수십 회 수준이다.

## 7. 1일 실험 계획 (활동량·품질·비용 동시 측정)

- **설계**: 같은 날 11시는 현행(장기 채팅), 15시·21시는 새 구조(새 세션 + 사람 큐 + API inbox)로 돌린다.
  또는 하루씩 교대한다. 같은 날이 시간대 편차가 작다.
- **활동량**: verified 댓글 수 / 시도 수 / 미확정 수 / 사람 소요 시간(분, 큐 등록 + 붙여넣기).
- **품질** (사람 블라인드 평가 10건씩, 1~5점): 맥락 적합, 자연스러움, 반복 문체, 정책 위반 0건 여부.
  24시간 뒤 받은 답·좋아요 수도 함께 본다. 이건 표본이 작아 참고용이다.
- **비용**: 실행별 모델 호출 수, 호출당 입력·캐시·출력(rollout token_count), API usage(model-requests.sqlite3).
- **판정 기준 (사전 고정)**:
  - 품질 평균 하락이 0.5점 이내이고, 정책 위반 0건, 미확정 증가가 없을 때 새 구조로 전환한다.
  - 사람 시간이 하루 30분을 넘으면 큐 UX부터 개선한다.

## 8. 추가로 확인해야 할 사항

1. 타인 글에 `reply_to_id` 게시가 표준 접근(승인 전)에서도 되는가. 문서는 "권한 보유"만 요구한다 [미확인].
   사용자 승인하에 1건만 시험한다.
2. 타인 media ID로 `GET /{id}`, `/conversation`이 되는가. 그리고 승인 없이 URL → media ID를 얻는
   문서화된 방법이 있는가 [미확인]. 비공식 변환(shortcode 디코딩 등)은 쓰지 않는다.
3. 우리 계정의 답글 목록 조회(완료 확인용) 엔드포인트와 필요한 권한 [미확인].
4. Tech Provider 전환의 의무·제약·되돌릴 수 없는 범위. 공식 문서 확인 후 사용자가 결정한다.
5. Meta Automated Data Collection Terms가 현재 AI 브라우저 운영에 어떻게 적용되는가.
   필요하면 Meta 문의나 법률 검토가 필요하다. 이 문서는 판단하지 않는다.
6. `profile_posts`의 필요 권한과 접근 등급 [미확인].
7. 외부 검색엔진의 Threads 게시물 색인 지연은 실측하지 않았다. 쓰려면 1주간 표본 측정이 먼저다.

## 출처

- Meta Threads Keyword Search: https://developers.facebook.com/docs/threads/keyword-search
- Meta Threads Create Replies: https://developers.facebook.com/documentation/threads/retrieve-and-manage-replies/create-replies.md
- Meta Threads Replies and Conversations: https://developers.facebook.com/documentation/threads/retrieve-and-manage-replies/replies-and-conversations.md
- Meta Threads Mentions: https://developers.facebook.com/documentation/threads/threads-mentions.md
- Meta Threads Profiles (Profile Discovery): https://developers.facebook.com/documentation/threads/threads-profiles.md
- Meta Threads User reference (`profile_posts`): https://developers.facebook.com/documentation/threads/reference/user.md
- Meta Threads oEmbed: https://developers.facebook.com/documentation/threads/tools-and-resources/embed-a-threads-post.md
- Meta Automated Data Collection Terms: https://www.facebook.com/legal/automated_data_collection_terms
- OpenAI API Pricing: https://developers.openai.com/api/docs/pricing
- OpenAI Prompt Caching: https://developers.openai.com/api/docs/guides/prompt-caching
- Codex non-interactive mode: https://learn.chatgpt.com/docs/non-interactive-mode
- Google Custom Search JSON API 종료 (2차 출처): https://brave.com/learn/google-api-shutdown/ , https://cloro.dev/blog/google-custom-search-api-shutdown/
- 확인 못 함: Threads 이용약관 원문(검색·접속 실패). 자동화 관련 조항은 Meta ADC Terms로만 근거를 들었다.
