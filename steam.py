"""스팀 공식 상점 API 클라이언트 (API 키 불필요)."""
import logging
import random
import re
import time

import requests

import config

log = logging.getLogger("steam")
HEADERS = {
    "User-Agent": "SteamBroadcastRadar/1.0 (personal project)",
    "Accept-Language": "ko-KR,ko;q=0.9",
}
_last = 0.0


def _throttle(delay: float | None = None) -> None:
    global _last
    delay = config.REQUEST_DELAY if delay is None else delay
    gap = delay - (time.monotonic() - _last)
    if gap > 0:
        time.sleep(gap)
    time.sleep(random.uniform(0, min(0.4, delay / 3)))
    _last = time.monotonic()


def _get_json(url: str, params: dict | None = None, delay: float | None = None):
    for attempt in range(config.MAX_RETRY + 1):
        _throttle(delay)
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=config.TIMEOUT)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 429:
                wait = 20 * (attempt + 1)
                log.warning("429 rate limit — %s초 대기", wait)
                time.sleep(wait)
                continue
            log.warning("%s → HTTP %s", url, r.status_code)
            return None
        except (requests.RequestException, ValueError) as e:
            log.warning("요청 실패 (%s/%s): %s", attempt + 1, config.MAX_RETRY + 1, e)
            time.sleep(3 * (attempt + 1))
    return None


def fetch_current_players(appid: int) -> int | None:
    """현재 Steam 접속 플레이어 수. 실패와 실제 0명을 구분해 None 을 쓴다."""
    data = _get_json(config.PLAYERS_URL, {"appid": appid},
                     delay=config.SIGNAL_REQUEST_DELAY)
    if not isinstance(data, dict):
        return None
    response = data.get("response") or {}
    try:
        count = int(response.get("player_count"))
    except (TypeError, ValueError):
        return None
    return max(count, 0)


def fetch_review_summary(appid: int) -> dict | None:
    """리뷰 본문은 받지 않고 집계만 저장한다.

    query_summary 는 평가 등급·긍정/부정·전체 리뷰 수를 한 번에 준다.
    카드에는 이 집계만 필요하므로 num_per_page=1 로 응답을 작게 유지한다.
    """
    data = _get_json(
        config.REVIEWS_URL.format(appid=appid),
        {"json": 1, "filter": "all", "language": "all", "day_range": 365,
         "review_type": "all", "purchase_type": "all", "num_per_page": 1},
        delay=config.SIGNAL_REQUEST_DELAY,
    )
    if not isinstance(data, dict) or data.get("success") != 1:
        return None
    q = data.get("query_summary") or {}
    try:
        return {
            "score": int(q.get("review_score") or 0),
            "desc": str(q.get("review_score_desc") or "")[:60],
            "positive": int(q.get("total_positive") or 0),
            "negative": int(q.get("total_negative") or 0),
            "total": int(q.get("total_reviews") or 0),
        }
    except (TypeError, ValueError):
        return None


def discover() -> dict[int, str]:
    """스팀이 제공하는 목록에서 appid 를 모은다.
    반환: {appid: 태그}  태그는 '신작' / '출시예정' / '할인' / '인기'.
    어느 목록에서 나왔는지 유지해야 신작과 할인을 구분할 수 있다."""
    out: dict[int, str] = {}
    data = _get_json(config.FEATURED_URL.format(cc=config.CC, lang=config.LANG))
    if not isinstance(data, dict):
        log.warning("featuredcategories 응답이 dict 가 아니다")
        return out

    for bucket, tag in config.BUCKETS.items():
        node = data.get(bucket)
        items = node.get("items") if isinstance(node, dict) else node
        if not isinstance(items, list):
            continue
        for it in items:
            if not isinstance(it, dict):
                continue
            appid = it.get("id") or it.get("appid")
            if isinstance(appid, str) and appid.isdigit():
                appid = int(appid)
            if isinstance(appid, int) and 10 <= appid < 10_000_000:
                # 먼저 잡힌 태그를 유지 (BUCKETS 순서가 우선순위)
                out.setdefault(appid, tag)
        log.info("  %s(%s): %d개", bucket, tag, len(items))

    for appid in config.SEED_APPIDS:
        out.setdefault(appid, "고정")
    log.info("발견 총 %d개", len(out))
    return out


def _junk_name(name: str) -> bool:
    """이름만 보고 게임이 아닌 것을 걸러낸다. appdetails 호출을 아끼기 위한 것이고,
    확실한 것만 건다 — 애매하면 불러서 확인하는 쪽이 안전하다.
    'Demo' 는 우리가 찾는 대상이라 절대 걸지 않는다."""
    low = f" {name.lower()} "
    return any(w in low for w in config.SKIP_NAME_WORDS)


def all_appids() -> list[tuple[int, str]]:
    """스팀 전체 appid 목록. 요청 1회, 키 불필요, 무료.
    이름까지 주므로 사운드트랙 같은 것은 appdetails 를 부르기 전에 떨어뜨린다.

    이 목록만으로는 한국어 지원·가격을 알 수 없다(그건 appdetails 뿐). 그래서
    여기서 얻은 appid 를 매 실행 조금씩 소비하는 '개척 풀'로 쓴다."""
    data = None
    for url in config.APPLIST_URLS:
        data = _get_json(url)
        if isinstance(data, dict) and data.get("applist"):
            log.info("전체 목록 엔드포인트: %s", url)
            break
        data = None
    if data is None:
        log.warning("전체 목록 엔드포인트 후보 %d개가 모두 실패했다", len(config.APPLIST_URLS))
        return []
    apps = ((data.get("applist") or {}).get("apps")) or []
    if not isinstance(apps, list):
        log.warning("GetAppList 응답 형태가 예상과 다르다")
        return []
    out = []
    skipped = 0
    for a in apps:
        if not isinstance(a, dict):
            continue
        appid, name = a.get("appid"), a.get("name") or ""
        if not isinstance(appid, int) or not (10 <= appid < 100_000_000):
            continue
        if not name.strip():
            continue          # 이름 없는 항목은 대체로 비공개/삭제된 것
        if _junk_name(name):
            skipped += 1
            continue
        out.append((appid, name))
    out.sort(key=lambda t: -t[0] if config.EXPLORE_NEWEST_FIRST else t[0])
    log.info("전체 목록 %d개 → 후보 %d개 (이름으로 %d개 사전 탈락)",
             len(apps), len(out), skipped)
    return out


MAX_SCREENSHOTS = 4      # 상세 페이지 스트립용. 늘리면 페이지가 무거워진다

# 응답에 실제로 뭐가 오는지 세어둔다.
# 첫 실행에서 스크린샷은 264개 들어왔는데 트레일러는 0개였다 — 같은 응답에서
# 하나는 되고 하나는 안 됐으니 movies 의 형태가 예상과 다르다는 뜻이다.
# 추측으로 또 고치지 말고, 다음 실행이 스스로 답을 알려주게 한다.
MEDIA_STATS = {"apps": 0, "screenshots": 0, "movies_key": 0, "movies_items": 0,
               "got_mp4": 0, "sample_movie_keys": "", "sample_src_keys": ""}


def _pick_url(node) -> str:
    """{'480': url, 'max': url} 같은 사전에서 쓸 만한 URL 하나. 키 이름을 가정하지 않는다.
    480 을 선호하되(모바일 용량), 없으면 아무거나 하나라도 쓴다."""
    if isinstance(node, str):
        return node if node.startswith("http") else ""
    if not isinstance(node, dict):
        return ""
    for key in ("480", 480, "max", "recommended"):
        v = node.get(key)
        if isinstance(v, str) and v.startswith("http"):
            return v
    for v in node.values():
        if isinstance(v, str) and v.startswith("http"):
            return v
    return ""


_KO_DATE = re.compile(r"(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일")

# 스팀 content_descriptor 중 성적 콘텐츠에 해당하는 id.
# 스팀이 공식 문서로 이 매핑을 공개하지 않아 관측에 기반한 값이며, 바뀔 수 있다.
# 그래서 id 만 믿지 않고 장르/태그 문자열도 같이 본다 (아래 is_adult).
ADULT_DESCRIPTOR_IDS = {3, 4}
_ADULT_WORDS = (
    "sexual content", "nudity", "hentai", "adults only",
    "성적", "성인", "노출",
)


def is_adult(d: dict, genres: list[str]) -> int:
    """성인용 성적 콘텐츠 여부. 기본 화면에서 감추는 데 쓴다.
    폭력/고어(descriptor 2)나 단순 required_age>=18 은 여기 넣지 않는다 —
    괜찮은 게임이 많아서 감추면 오히려 놓치게 된다."""
    desc = d.get("content_descriptors") or {}
    ids = desc.get("ids")
    if isinstance(ids, list) and any(
            isinstance(i, int) and i in ADULT_DESCRIPTOR_IDS for i in ids):
        return 1
    notes = str(desc.get("notes") or "").lower()
    blob = (" ".join(genres) + " " + notes).lower()
    return 1 if any(w in blob for w in _ADULT_WORDS) else 0


def parse_release(date_text: str | None) -> str | None:
    """'2026년 8월 26일' → '2026-08-26'. 못 읽으면 None (원문은 따로 보관)."""
    if not date_text:
        return None
    m = _KO_DATE.search(date_text)
    if m:
        y, mo, d = m.groups()
        return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
    return None


def fetch_app(appid: int) -> dict | None:
    """게임 하나의 상세 정보. 방송 판단에 필요한 항목까지 함께 가져온다."""
    data = _get_json(config.APPDETAILS_URL,
                     {"appids": appid, "cc": config.CC, "l": config.LANG})
    if not isinstance(data, dict):
        return None
    entry = data.get(str(appid))
    if not isinstance(entry, dict) or not entry.get("success"):
        return None
    d = entry.get("data") or {}
    app_type = d.get("type")
    if app_type not in ("game", "demo"):
        return None      # dlc / music / video 등은 제외

    po = d.get("price_overview") or {}
    rel = d.get("release_date") or {}
    langs = d.get("supported_languages") or ""
    genres = [g.get("description", "") for g in (d.get("genres") or [])
              if isinstance(g, dict)]
    demos = d.get("demos") or []

    # 리뷰 수 = 인지도 대리 지표. appdetails 안에 있어서 추가 요청이 필요 없다.
    # (평가 등급 텍스트 '매우 긍정적' 은 appreviews 라는 별도 엔드포인트에만 있어서
    #  요청 수가 두 배가 된다. 지금은 넣지 않고, 필요하면 후보에 한해 따로 붙인다.)
    rec = d.get("recommendations") or {}
    try:
        review_count = int(rec.get("total") or 0)
    except (TypeError, ValueError):
        review_count = 0
    devs = [x for x in (d.get("developers") or []) if isinstance(x, str)]

    # 스크린샷·트레일러는 이 응답 안에 이미 들어 있다 — 추가 호출이 없다.
    # 표지(header_image)는 460x215 배너라 대부분 로고와 제목뿐이어서
    # '이게 무슨 게임인지'를 답하지 못한다. 실제 화면과 영상이 그 답을 한다.
    # 스팀이 필드를 안 줄 수도 있으므로 전부 없으면 조용히 빈 값으로 둔다.
    shots = []
    for sc in (d.get("screenshots") or [])[:MAX_SCREENSHOTS]:
        if not isinstance(sc, dict):
            continue
        u = sc.get("path_thumbnail") or sc.get("path_full")
        if isinstance(u, str) and u.startswith("http"):
            shots.append(u)

    mp4 = webm = poster = ""
    raw_movies = d.get("movies")
    movies = [m for m in (raw_movies or []) if isinstance(m, dict)]
    if movies:
        # highlight 로 표시된 것이 대표 트레일러다. 없으면 첫 번째.
        mv = next((m for m in movies if m.get("highlight")), movies[0])
        mp4 = _pick_url(mv.get("mp4"))
        webm = _pick_url(mv.get("webm"))
        poster = _pick_url(mv.get("thumbnail"))
        if not MEDIA_STATS["sample_movie_keys"]:
            MEDIA_STATS["sample_movie_keys"] = ",".join(sorted(mv.keys()))[:160]
            src = mv.get("mp4") or mv.get("webm")
            if isinstance(src, dict):
                MEDIA_STATS["sample_src_keys"] = ",".join(str(k) for k in src.keys())[:80]

    MEDIA_STATS["apps"] += 1
    MEDIA_STATS["screenshots"] += 1 if shots else 0
    MEDIA_STATS["movies_key"] += 1 if raw_movies is not None else 0
    MEDIA_STATS["movies_items"] += 1 if movies else 0
    MEDIA_STATS["got_mp4"] += 1 if (mp4 or webm) else 0

    return {
        "appid": appid,
        "name": d.get("name") or f"App {appid}",
        "app_type": app_type,
        "is_free": bool(d.get("is_free")),
        # 스팀은 가격을 최소통화단위 정수로 준다. 원화는 100으로 나눠 원 단위.
        "price_final": int(po.get("final", 0)) // 100 if po else 0,
        "price_initial": int(po.get("initial", 0)) // 100 if po else 0,
        "discount_pct": int(po.get("discount_percent", 0)) if po else 0,
        "header_image": d.get("header_image") or "",
        "short_description": (d.get("short_description") or "")[:300],
        # --- 방송 판단용 ---
        "coming_soon": 1 if rel.get("coming_soon") else 0,
        "release_text": (rel.get("date") or "")[:40],
        "release_date": parse_release(rel.get("date")),
        "korean": 1 if "korean" in langs.lower() or "한국어" in langs else 0,
        "genres": ", ".join(genres)[:120],
        "has_demo": 1 if demos else 0,
        "demo_appid": (demos[0].get("appid") if demos and isinstance(demos[0], dict) else None),
        # --- 화면 정리용 ---
        "adult": is_adult(d, genres),
        "review_count": review_count,
        "developer": (devs[0][:60] if devs else ""),
        # --- '이게 무슨 게임인가'에 답하는 것들 ---
        "screenshots": "\n".join(shots),
        "movie_mp4": mp4,
        "movie_webm": webm,
        "movie_poster": poster,
    }
