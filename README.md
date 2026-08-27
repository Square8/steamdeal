# 스팀 방송 레이더

스팀 **신작 · 데모 · 출시예정**을 매일 자동으로 모아서 "이번 주 방송할 만한 게임"을 뽑아주는 정적 사이트.
가격 추적(역대 최저가)은 부수 기능으로 같이 돌아간다.

**이 도구의 첫 사용자는 만든 사람 자신이다.** 방문자가 0명이어도 방송 소재 발굴 도구로 쓸모가 있다.
그래서 다른 아이템들과 달리 "누가 볼까" 문제가 없다.

- **맥북을 켜놓지 않아도 된다.** GitHub Actions 가 하루 2번 클라우드에서 돌린다.
- **호스팅비 0원.** GitHub Pages.
- **스팀 API 키 불필요.** 공식 상점 API는 키 없이 쓸 수 있다.

## 왜 최저가가 아니라 신작·데모인가

한국어 "스팀 최저가" 검색 1페이지를 확인한 결과, 이미 강한 선행 서비스가 있다:
싸다게임(키샵까지 비교 + 포인트 적립 + 크롬 확장), dogdrip.com/lowest(역대최저 게임 모음),
steamsale.windbell.co.kr, 그리고 해외 SteamDB / IsThereAnyDeal / GG.deals.

경쟁자가 6개나 있다는 건 **수요가 있다는 증거**다. 다만 후발주자가 검색 유입만으로 이기기는 어렵다.
그래서 **아무도 주력으로 하지 않는 것 하나**로 좁혔다 — 신작·데모 발굴과 방송 소재.

## 어떻게 굴러가나

```
GitHub Actions (하루 2번)
   │
   ├─ collect.py   스팀 API → 신작/데모/출시예정/가격을 SQLite 에 기록
   │                (대상은 스팀의 신작/출시예정/할인/인기 목록에서 자동 수집)
   ├─ build.py     SQLite → 정적 HTML (방송 후보 선정, 가격추이 차트)
   ├─ 가격 이력 커밋  data/steam.sqlite3 을 저장소에 push
   └─ GitHub Pages 배포
```

가격 이력을 저장소에 커밋하는 게 핵심이다. 이게 없으면 매 실행마다 이력이 사라져서 "역대 최저가"를 계산할 수 없다.

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

3~6분 후 `https://<내아이디>.github.io/steamdeal/` 에서 사이트가 열린다.

첫 실행에는 이력이 하루치뿐이라 차트가 안 그려진다. 며칠 지나야 추이와 역대최저가 의미를 갖는다.

## 로컬에서 돌려보기

```bash
pip install -r requirements.txt
python collect.py     # 가격 수집 (스팀 API 호출, 5~8분)
python build.py       # 사이트 생성
open site/index.html
```

기계가 정상인지만 확인하려면 (스팀 API 호출 없음, 1초):

```bash
python selftest.py
```

## 손볼 곳

`config.py` 만 보면 된다.

| 항목 | 설명 |
|---|---|
| `SEED_APPIDS` | 항상 추적할 게임 앱ID. 스팀 상점 URL 의 `/app/<숫자>/` 가 앱ID
| `REQUIRE_KOREAN` | 한국어 미지원 게임을 방송 후보에서 제외 |
| `BROADCAST_MAX_PRICE` | 이 가격 넘는 게임은 후보에서 제외 (0 = 제한 없음) |
| `MIN_DAYS_FOR_ATL` | 이 일수 미만이면 '역대 최저'라고 표기하지 않음 (기본 60)
| `REFRESH_QUOTA` | 기존 게임 갱신에 배정할 비율 (기본 0.4) |
| `MAX_APPS_PER_RUN` | 한 번에 갱신할 게임 수. 스팀 rate limit 때문에 220 정도가 안전 |
| `REQUEST_DELAY` | 요청 간격(초). **줄이지 말 것** — 스팀이 429 로 막는다 |
| `SITE_NAME` / `SITE_TAGLINE` | 사이트 제목 |
| `CC` / `LANG` | 국가·언어. `kr`/`korean` = 원화 가격 |

추적 대상은 **손으로 적지 않아도 된다.** 스팀의 특별할인/인기/신작 목록에서 자동으로 모으고, 한 번 추적한 게임은 계속 따라간다. 앱ID를 손으로 적으면 하나 틀릴 때마다 죽은 항목이 생기니까 시드는 최소한만 두는 게 좋다.

## 알려진 제약

- **역대 최저가는 "이 사이트가 추적을 시작한 이후"의 최저값이다.** 스팀의 전체 가격 역사가 아니다. 사이트 하단에 그렇게 표시해 뒀다.
- 스팀 `appdetails` API 는 요청 수 제한이 있다. `MAX_APPS_PER_RUN` 과 `REQUEST_DELAY` 를 줄이면 429 를 맞는다.
- GitHub Actions 는 활동 없는 저장소의 예약 실행을 60일 후 중단한다. 이 워크플로우는 매 실행마다 커밋을 남기므로 해당되지 않는다.
- 무료 게임은 최저가 개념이 없어 제외한다 (`SKIP_FREE`).
- 이 저장소는 스팀 가격 정보를 표시만 한다. 구매는 스팀에서 이뤄지므로 제휴 수익은 없다. 수익화가 필요하면 애드센스 등을 별도로 붙여야 한다.

## 검증 상태

`selftest.py` 가 스팀 API 없이 전 구간을 검사한다. 현재 전부 통과.

검증한 것: 센트→원 단위 변환, 무료/DLC 제외, 앱ID 자동수집(중첩 구조 훑기), 가격 이력 저장,
**역대최저 계산 및 갱신 플래그**, 스파크라인/상세차트 SVG, 이력 1건일 때 폴백,
가격 불변 게임의 축 눈금, 눈금값 중복 제거, 라이트/다크 3중 스코프, XSS 이스케이프.

검증 못 한 것: 스팀 API 실제 응답 형식(이 코드를 만든 환경에서 스팀 접속이 차단되어 있었음).
`collect.py` 첫 실행에서 실패가 많으면 로그를 확인할 것.
