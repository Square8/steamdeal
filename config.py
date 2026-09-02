"""
GameDil — 설정

목적: 스팀 게임 할인과 최저가를 한눈에 모아서 보여준다.
"""
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
SITE_DIR = os.environ.get("SITE_DIR") or os.path.join(ROOT, "site")
DB_PATH = os.environ.get("DB_PATH") or os.path.join(ROOT, "data", "steam.sqlite3")

SITE_NAME = "GameDil"
SITE_TAGLINE = "게임 할인과 최저가를 한눈에"
# 절대 URL(사이트맵·canonical·og:url)에 쓴다. GitHub Actions 에서 주입한다.
# 비어 있으면 상대 경로로만 동작한다 (로컬 테스트용).
SITE_URL = os.environ.get("SITE_URL", "")

# ---- 검색엔진 소유 확인 ----
# 구글 서치콘솔 / 네이버 서치어드바이저가 "이 사이트가 네 것인지" 확인하는 코드.
# 각 사이트에서 'HTML 태그' 방식을 고르면 content="..." 안의 문자열을 주는데,
# 그 문자열만 GitHub 저장소 Settings > Secrets and variables > Actions > Variables 에
# 아래 이름으로 넣으면 된다. 비어 있으면 태그가 아예 나가지 않는다.
GOOGLE_VERIFY = os.environ.get("GOOGLE_SITE_VERIFICATION", "").strip()
NAVER_VERIFY = os.environ.get("NAVER_SITE_VERIFICATION", "").strip()

# ---- 스팀 API ----
CC = "kr"
# Steam Store API 언어 코드는 korean 이 아니라 koreana 다.
# 잘못된 값은 설명이 독일어 등 다른 언어로 섞여 들어오는 원인이 된다.
LANG = "koreana"
REQUEST_DELAY = 1.5      # 스팀 appdetails 는 요청수 제한이 있다. 줄이지 말 것.
TIMEOUT = 20
MAX_RETRY = 2

# 홈의 트렌드 섹션에 쓰는 보조 신호. appdetails 와 달리 후보 게임에만 붙인다.
# 전체 게임에 매번 요청하면 수집 시간이 폭증하므로, 검증된 인기/할인 후보만 갱신한다.
PLAYERS_URL = "https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/"
REVIEWS_URL = "https://store.steampowered.com/appreviews/{appid}"
SIGNAL_REQUEST_DELAY = 0.8
PLAYER_SIGNAL_LIMIT = 80
REVIEW_SIGNAL_LIMIT = 60

# 한 실행에서 상세조회할 최대 게임 수.
# REQUEST_DELAY(1.5초)를 지키므로 800개 = 약 20분. Actions 단일 잡 상한은 6시간이고
# 공개 저장소는 실행 시간이 무료라서 여기를 늘리는 데 드는 돈은 없다.
# 제약은 '속도'(스팀 rate limit → REQUEST_DELAY 로 이미 대응)가 아니라 '실행 시간'이다.
MAX_APPS_PER_RUN = 800
# 그중 '오래 갱신 안 된 기존 게임'에 최소한 배정할 몫.
# 이게 없으면 신규 발견이 목록을 다 차지해서 기존 게임 이력이 얼어붙는다.
REFRESH_QUOTA = 0.25     # 25% 는 기존 게임 갱신에 쓴다

# ---- 신규 개척 ----
# featuredcategories 는 상점 첫 화면 큐레이션이라 페이징이 없다.
# 그래서 그것만으로는 '알게 되는' 게임이 150~250개에서 영구히 멈춘다
# (실측: 1일차 61개 → 2일차 120개 = 찾을 수 있는 걸 거의 다 찾은 것).
#
# GetAppList 는 스팀 전체 appid(약 25만)를 한 번에 무료로 준다. 다만 각 게임의
# 한국어/가격을 알려면 appdetails 를 개별 호출해야 하고 그건 1.5초에 하나다
# (25만 = 104일). 그래서 한 번에 다 가져오지 않고 매 실행 조금씩 개척한다.
# DB 는 지워지지 않는 누적 자산이므로 이 방식이 성립한다.
EXPLORE_QUOTA = 0.55     # 남은 예산의 대부분을 미탐색 appid 에 쓴다
# 전체 목록 엔드포인트 후보. 첫 배포에서 v2/ 가 404 를 돌려줬다(실측).
# 어느 형태가 살아 있는지 이 환경에서 검증할 수 없어서(프록시 차단) 하나에 걸지 않고
# 순서대로 시도한다. 성공한 URL 을 로그에 남기므로 다음엔 바로 알 수 있다.
APPLIST_URLS = [
    "https://api.steampowered.com/ISteamApps/GetAppList/v0002/?format=json",
    "https://api.steampowered.com/ISteamApps/GetAppList/v2/?format=json",
    "https://api.steampowered.com/ISteamApps/GetAppList/v2",
    "https://api.steampowered.com/ISteamApps/GetAppList/v1/?format=json",
]

# 위가 전부 실패해도 개척이 멈추면 안 된다.
# 스팀 appid 는 대체로 순차 배정이라 '큰 번호 = 최근 등록'이다. 그래서 목록 없이도
# 우리가 아는 가장 큰 appid 위쪽부터 번호를 훑어 내려오면 최신 게임을 만난다.
# 이름 사전탈락을 못 써서 헛호출이 늘지만, 실패한 appid 는 probed 에 남아
# 다시 부르지 않으므로 낭비는 1회씩뿐이다.
# 훑기 시작점을 '아는 최대 appid 보다 위'로 잡으면 안 된다.
# 첫 시도에서 +20,000 위에서 시작했다가 440개 중 8개만 건졌다(적중률 1.8%, 실측).
# 그 구간은 번호만 배정되고 아직 공개되지 않은 앱이라 appdetails 가 전부 실패한다.
# 아는 최대 appid 는 큐레이션이 준 '오늘 나온 신작'이므로, 거기서부터 아래로 훑어야
# 실제로 공개된 앱을 만난다. 새 게임은 큐레이션이 계속 물어다 주므로 천장은 알아서 오른다.
EXPLORE_NUMERIC_MARGIN = 0

# 스팀 appid 는 10 단위로 배정된다. 보유 게임 216개가 100% 10의 배수였고,
# 헛호출 870건 중 792건(91%)이 10의 배수가 아닌 번호였다 — 존재할 수 없는 번호를
# 부르고 있었던 것이다. 1씩 훑으면 호출의 90%가 그냥 버려진다.
# 10씩 훑으면 같은 구간에서 적중률이 1.8% → 20.5% 가 된다(같은 데이터로 재계산).
EXPLORE_STEP = 10

# 개척 순서: appid 내림차순 = 최근 등록된 것부터.
# 이 사이트의 무기가 '가장 먼저'이므로 오래된 appid 부터 파면 방향이 어긋난다.
EXPLORE_NEWEST_FIRST = True

# appdetails 를 아끼기 위한 이름 기반 사전 탈락.
# 호출이 유일한 희소 자원이라, 이름만 봐도 게임이 아닌 것은 부르지 않는다.
# 주의: 'Demo' 는 우리가 찾는 대상이므로 절대 넣지 말 것.
SKIP_NAME_WORDS = (
    "soundtrack", "ost", " sdk", "dedicated server", "trailer", "teaser",
    "artbook", "art book", "wallpaper", "digital deluxe upgrade",
    "season pass", "bonus content", "upgrade pack", "playtest",
)

# ---- 발견 경로 ----
# 어느 목록에서 나왔는지 태그를 유지한다 (신작인지 할인인지 구분해야 하므로)
FEATURED_URL = "https://store.steampowered.com/api/featuredcategories/?cc={cc}&l={lang}"
APPDETAILS_URL = "https://store.steampowered.com/api/appdetails"

# featuredcategories 응답의 버킷 이름 → 우리 태그
BUCKETS = {
    "new_releases": "신작",
    "coming_soon": "출시예정",
    "specials": "할인",
    "top_sellers": "인기",
}

# 항상 추적할 게임 (스팀 상점 URL 의 /app/<숫자>/ 가 앱ID)
SEED_APPIDS = [730, 578080, 1245620, 1091500, 292030, 413150, 553850, 367520]

# ---- 추천 후보 판정 ----
# 추천 목록에 띄울 기준. 취향에 맞게 바꾸면 된다.
REQUIRE_KOREAN = True    # 한국어 지원 안 하면 추천 목록에서 제외
BROADCAST_MAX_PRICE = 80000   # 이 가격 넘으면 후보에서 빼기 (0 = 제한 없음)

# ---- 역대최저 표기 정직성 ----
# 관측 일수가 이보다 짧으면 '역대 최저'라고 말하지 않는다.
# 스팀 대형 세일은 계절 주기(여름/겨울)라서, 한 사이클을 못 본 상태의
# '역대 최저'는 거짓이 될 수 있다.
MIN_DAYS_FOR_ATL = 60

# 최저가 배지를 아예 달지 않는 문턱. 관측 2일차에 "2일 최저"를 초록 배지로 달면
# 사실상 "수집 후 가격이 안 바뀌었다"는 뜻인데 진짜 역대최저처럼 보인다.
# 30일은 스팀 주말/미드위크 세일이 최소 한 번은 지나가는 길이다.
MIN_DAYS_FOR_LOW = 30

SKIP_FREE_IN_PRICE = True   # 무료 게임은 가격 추적에서 제외 (추천 후보에는 포함)

# ---- 무엇을 '보관'할지 ----
# 개척은 넓게 하되 저장은 좁게 한다.
# 스팀 전체를 다 보관하면 게임 10만 개 → 상세 페이지 10만 장이 되고,
# 그건 GitHub Pages 빌드 시간과 DB 커밋 크기 양쪽에서 무너진다.
#
# 이 사이트가 보여주는 것은 '한국어로 할 수 있는 게임'이다. 그래서
# 한국어 지원 / 데모 있음 / 출시예정 / 상점 큐레이션에 걸린 것만 남기고
# 나머지(한국어 없고 데모도 없는 옛 게임)는 probed 에 표시만 하고 버린다.
# 어차피 화면에 나가지 않는 것들이라 버려도 사이트가 잃는 게 없다.
KEEP_ONLY_RELEVANT = True

# 홈의 '전체에서 찾기' 격자에 서버가 미리 그려두는 카드 수 상한.
# 무제한이면 게임 9천개에서 index.html 이 6.9MB 가 된다(실측). 그건 모바일에서
# 열리지 않는다. 더 좁은 목록은 상단 메뉴의 랜딩 페이지가 담당한다.
MAX_INDEX_CARDS = 240

# 최근 가격 인하 판정 기준일
RECENT_DROP_DAYS = 7

