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


def _throttle() -> None:
    global _last
    gap = config.REQUEST_DELAY - (time.monotonic() - _last)
    if gap > 0:
        time.sleep(gap)
    time.sleep(random.uniform(0, 0.4))
    _last = time.monotonic()


def _get_json(url: str, params: dict | None = None):
    for attempt in range(config.MAX_RETRY + 1):
        _throttle()
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
    }
