# GameDil

스팀 게임 할인과 최저가를 한눈에 모아서 보여주는 정적 사이트. (공개 주소: https://gamedil.com)
가격 추적(GameDil 관측 최저가)은 부수 기능으로 같이 돌아간다.

주요 화면: 핫딜·최근 인하·1만원 이하·인기, 한국어 게임/신작/출시 예정/데모, 게임별 상세(가격 추이·트레일러·최근 30일 평가),
비교, 찜 목록(공유 링크 포함), 최근 본 게임, 랜덤 추천 뽑기. 분석은 GA4를 사용한다.

**이 도구의 첫 사용자는 만든 사람 자신이다.** 방문자가 0명이어도 개인용 게임 할인 탐색 도구로 쓸모가 있다.
그래서 다른 아이템들과 달리 "누가 볼까" 문제가 없다.

- **맥북을 켜놓지 않아도 된다.** GitHub Actions 가 하루 2번 클라우드에서 돌린다.
- **호스팅비 0원.** GitHub Pages.
- **스팀 API 키 불필요.** 공식 상점 API는 키 없이 쓸 수 있다.

## 왜 GameDil 인가

한국어 "스팀 최저가" 검색 1페이지를 확인한 결과, 이미 강한 선행 서비스가 있다:
싸다게임(키샵까지 비교 + 포인트 적립 + 크롬 확장), dogdrip.com/lowest(역대최저 게임 모음),
steamsale.windbell.co.kr, 그리고 해외 SteamDB / IsThereAnyDeal / GG.deals.

경쟁자가 6개나 있다는 건 **수요가 있다는 증거**다. 다만 후발주자가 검색 유입만으로 이기기는 어렵다.
그래서 **차별화된 가치 하나**로 좁혔다 — 직관적인 가격 판단, 한국어 게임 큐레이션, 그리고 숨겨진 신작·데모 발굴.

## 어떻게 굴러가나

```
GitHub Actions (하루 2번)
   │
   ├─ collect.py   스팀 API → 신작/데모/출시예정/가격/동접/리뷰를 SQLite 에 기록
   │                (대상은 스팀의 신작/출시예정/할인/인기 목록에서 자동 수집)
   ├─ build.py     SQLite → 정적 HTML (할인 및 추천 게임 선정, 가격추이 차트, 사이트맵)
   ├─ 가격 이력 커밋  data/steam.sqlite3 을 저장소에 push
   └─ GitHub Pages 배포
```

가격 이력을 저장소에 커밋하는 게 핵심이다. 이게 없으면 매 실행마다 이력이 사라져서 "관측 최저가"를 계산할 수 없다.

**실행 종류**: 예약 실행(KST 08:17, 20:17)과 Actions 의 `Run workflow` 는 수집+빌드+배포를 한다.
코드를 `main` 에 push 하면 수집은 건너뛰고 빌드·배포만 한다(약 10초). 그래서 수집 로직이나 새 데이터 필드를
바꿨다면 push 후 수동 실행 또는 다음 예약 실행이 끝나야 사이트에 반영된다.
`data/**` 와 `README.md` 만 바뀐 push 는 워크플로우를 돌리지 않는다.

## 처음 세팅 (한 번만, 약 10분)

### 1. GitHub 저장소 만들기

```bash
cd steamdeal
git init
git add .
git commit -m "스팀 최저가 추적기"
git branch -M main
git remote add origin https://github.com/<내아이디>/steamdeal.git
git push -u origin main
```

### 2. GitHub Pages 켜기

저장소 → **Settings → Pages → Build and deployment → Source** 를 **"GitHub Actions"** 로 변경.

### 3. Actions 쓰기 권한 켜기

**Settings → Actions → General → Workflow permissions** 에서
**"Read and write permissions"** 선택 후 저장. (가격 이력을 커밋해야 하므로 필요)

### 4. 첫 실행

**Actions 탭 → "가격 수집 및 사이트 배포" → Run workflow** 클릭.

수집 시간이 있어 20~30분쯤 걸린다. 이후 설정한 커스텀 도메인(`https://gamedil.com/`, `CNAME` 파일)에서 사이트가 열린다.
(도메인 미설정 시 `https://<내아이디>.github.io/steamdeal/` 에서 열림)

첫 실행에는 이력이 하루치뿐이라 차트가 안 그려진다. 며칠 지나야 추이와 관측 최저가 의미를 갖는다.

## 로컬에서 돌려보기

```bash
pip install -r requirements.txt
python collect.py     # 가격 수집 (스팀 API 호출, 최대 800개 × 1.5초 ≈ 20분)
python build.py       # 사이트 생성
open site/index.html
```

기계가 정상인지만 확인하려면 (스팀 API 호출 없음, 1초):

```bash
python selftest.py
python tests/test_random_pick.py   # tests/ 의 개별 회귀 테스트 (파일별로 실행)
```

작업 규칙·파일 지도는 `PROJECT_CONTEXT.md`, AI 협업 현황은 `HANDOFF.md`, 기능별 구현·검토 기록은 `marketing/` 에 있다.

## 손볼 곳

`config.py` 만 보면 된다.

| 항목 | 설명 |
|---|---|
| `SEED_APPIDS` | 항상 추적할 게임 앱ID. 스팀 상점 URL 의 `/app/<숫자>/` 가 앱ID |
| `REQUIRE_KOREAN` | 한국어 미지원 게임을 추천 목록에서 제외 |
| `BROADCAST_MAX_PRICE` | 이 가격을 넘는 게임은 추천 목록에서 제외 (기본 80000, 0 = 제한 없음) |
| `MIN_DAYS_FOR_ATL` | 이 일수 미만이면 '역대 최저'라고 표기하지 않음 (기본 60) |
| `MIN_DAYS_FOR_LOW` | 이 일수 미만이면 최저가 배지를 아예 달지 않음 (기본 30) |
| `REFRESH_QUOTA` | 기존 게임 갱신에 배정할 비율 (기본 0.25) |
| `MAX_APPS_PER_RUN` | 한 번에 갱신할 게임 수 (기본 800, `REQUEST_DELAY` 1.5초 기준 약 20분). 늘리면 실행 시간이 늘어난다 |
| `REQUEST_DELAY` | 요청 간격(초). **줄이지 말 것** — 스팀이 429 로 막는다 |
| `SITE_NAME` / `SITE_TAGLINE` | 사이트 제목 |
| `GA_TRACKING_ID` | GA4 측정 ID. 환경변수로 덮어쓸 수 있다 |
| `RECENT_REVIEW_*` | 상세 페이지의 '최근 30일 평가' 수집 범위·요청 예산 |
| `CC` / `LANG` | 국가·언어. `kr`/`koreana` = 원화 가격·한국어 (`korean` 이 아니라 `koreana`) |

추적 대상은 **손으로 적지 않아도 된다.** 스팀의 특별할인/인기/신작 목록에서 자동으로 모으고, 한 번 추적한 게임은 계속 따라간다. 앱ID를 손으로 적으면 하나 틀릴 때마다 죽은 항목이 생기니까 시드는 최소한만 두는 게 좋다.

## 알려진 제약

- **최저가는 "이 사이트가 관측을 시작한 이후"의 최저값이다.** 스팀의 전체 가격 역사가 아니다. 그래서 홍보·화면 문구에서도 'GameDil 관측 최저가'로 표현한다.
- 스팀 `appdetails` API 는 요청 수 제한이 있다. `REQUEST_DELAY`(1.5초)를 줄이면 429 를 맞는다.
- GitHub Actions 는 활동 없는 저장소의 예약 실행을 60일 후 중단한다. 이 워크플로우는 매 실행마다 커밋을 남기므로 해당되지 않는다.
- 무료 게임은 최저가 개념이 없어 제외한다 (`SKIP_FREE`).
- 이 저장소는 스팀 가격 정보를 표시만 한다. 구매는 스팀에서 이뤄지므로 제휴 수익은 없다. Steam 상점 클릭은 GA4 이벤트(`steam_store_click`)로만 측정한다.
- 최근 30일 평가는 스팀 API 응답이 불완전하면 수치를 공개하지 않는다(불완전한 값을 완전한 값처럼 보이지 않게 함).

## 검증 상태

`python selftest.py` 는 스팀 API 없이 전 구간(변환·저장·역대최저 계산·차트·생성 HTML·JS 문법·XSS 이스케이프 등)을 검사하고,
`tests/` 는 기능별(탐색·정렬, 찜 공유, 랜덤 뽑기, 최근 평가, 캠페인 URL, 클릭 추적 등) 회귀를 검사한다.

스팀 API 응답 형식은 GitHub Actions 예약 실행이 `data/steam.sqlite3` 에 이력을 계속 쌓는 것으로 운영 중 확인된다.
새로 붙인 수집 항목(예: 최근 30일 평가)은 배포 후 수동 Actions 실행 로그의 완전/실패 건수를 확인할 것.
