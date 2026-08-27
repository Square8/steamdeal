"""
스팀 최저가 추적기 — 설정

핵심 아이디어: 스팀 게임의 '역대 최저가'를 한국 원화로 추적한다.
스팀 상점은 지금 가격만 보여주고, 이게 역대 최저인지 알려주지 않는다.
그 정보가 이 사이트의 가치다.

스팀 공식 상점 API를 쓴다. API 키가 필요 없고 무료다.
"""
import os

# ---- 출력 위치 ----
ROOT = os.path.dirname(os.path.abspath(__file__))
SITE_DIR = os.environ.get("SITE_DIR") or os.path.join(ROOT, "site")
DB_PATH = os.environ.get("DB_PATH") or os.path.join(ROOT, "data", "prices.sqlite3")

# ---- 사이트 정보 ----
SITE_NAME = "스팀 최저가 추적"
SITE_TAGLINE = "지금 할인가가 역대 최저인지 알려준다"
SITE_URL = os.environ.get("SITE_URL", "")   # 예: https아이디.github.io/steamdeal

# ---- 스팀 API ----
CC = "kr"          # 국가: 한국 (원화 가격)
LANG = "korean"
REQUEST_DELAY = 1.5   # 스팀은 appdetails 를 분당 요청수로 제한한다. 여유있게.
TIMEOUT = 20
MAX_RETRY = 2

# 한 번 실행에서 가격을 갱신할 최대 게임 수.
# GitHub Actions 무료 한도와 스팀 rate limit 를 함께 고려한 값.
MAX_APPS_PER_RUN = 220

# ---- 추적 대상 확보 방식 ----
# 앱 ID를 손으로 적지 않는다. 스팀이 직접 알려주는 목록에서 자동으로 모은다.
# (손으로 적으면 ID 하나 틀릴 때마다 죽은 항목이 생김)
DISCOVER_ENDPOINTS = [
    "https://store.steampowered.com/api/featuredcategories/?cc={cc}&l={lang}",
    "https://store.steampowered.com/api/featured/?cc={cc}&l={lang}",
]

# 위 자동 수집에 더해 항상 추적할 게임 (한국에서 특히 많이 찾는 것들)
SEED_APPIDS = [
    730,      # Counter-Strike 2
    578080,   # PUBG: BATTLEGROUNDS
    271590,   # Grand Theft Auto V
    1245620,  # ELDEN RING
    1091500,  # Cyberpunk 2077
    292030,   # The Witcher 3
    1174180,  # Red Dead Redemption 2
    413150,   # Stardew Valley
    105600,   # Terraria
    553850,   # HELLDIVERS 2
    367520,   # Hollow Knight
    252490,   # Rust
    322330,   # Don't Starve Together
    431960,   # Wallpaper Engine
    4000,     # Garry's Mod
    550,      # Left 4 Dead 2
    620,      # Portal 2
]

# 무료 게임은 최저가 개념이 없으므로 제외
SKIP_FREE = True
