"""스팀 공식 상점 API 클라이언트 (API 키 불필요)."""
import logging
import random
import time

import requests

import config

log = logging.getLogger("steam")

APPDETAILS = "https://store.steampowered.com/api/appdetails"
HEADERS = {
    "User-Agent": "SteamDealTracker/1.0 (personal project)",
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


def discover_appids() -> list[int]:
    """스팀이 직접 제공하는 목록(특별할인/인기/신작)에서 앱 ID를 모은다.
    ID를 손으로 적지 않으므로 죽은 항목이 생기지 않는다."""
    found: list[int] = []
    for tpl in config.DISCOVER_ENDPOINTS:
        data = _get_json(tpl.format(cc=config.CC, lang=config.LANG))
        if not isinstance(data, dict):
            continue
        found.extend(_walk_for_appids(data))
    # 중복 제거 (순서 유지)
    seen, uniq = set(), []
    for a in config.SEED_APPIDS + found:
        if a not in seen:
            seen.add(a)
            uniq.append(a)
    log.info("추적 대상 %d개 확보 (시드 %d + 자동수집 %d)",
             len(uniq), len(config.SEED_APPIDS), len(found))
    return uniq


def _walk_for_appids(node, out=None) -> list[int]:
    """응답 구조가 자주 바뀌므로 중첩 dict/list 를 훑어서 id 를 긁는다."""
    if out is None:
        out = []
    if isinstance(node, dict):
        for key in ("id", "appid"):
            v = node.get(key)
            if isinstance(v, int) and 10 <= v < 10_000_000:
                out.append(v)
            elif isinstance(v, str) and v.isdigit():
                out.append(int(v))
        for v in node.values():
            _walk_for_appids(v, out)
    elif isinstance(node, list):
        for v in node:
            _walk_for_appids(v, out)
    return out


def fetch_app(appid: int) -> dict | None:
    """게임 하나의 현재 한국 가격 정보. 반환 형태:
    {appid, name, price_final, price_initial, discount_pct, is_free, header_image}"""
    data = _get_json(APPDETAILS, {"appids": appid, "cc": config.CC, "l": config.LANG})
    if not isinstance(data, dict):
        return None
    entry = data.get(str(appid))
    if not isinstance(entry, dict) or not entry.get("success"):
        return None
    d = entry.get("data") or {}
    if d.get("type") != "game":
        return None

    is_free = bool(d.get("is_free"))
    po = d.get("price_overview") or {}
    if not po and not is_free:
        return None   # 출시 예정 등 가격 없음

    return {
        "appid": appid,
        "name": d.get("name") or f"App {appid}",
        "is_free": is_free,
        # 스팀은 가격을 '센트' 단위 정수로 준다. 원화는 100으로 나눠야 원 단위.
        "price_final": int(po.get("final", 0)) // 100 if po else 0,
        "price_initial": int(po.get("initial", 0)) // 100 if po else 0,
        "discount_pct": int(po.get("discount_percent", 0)) if po else 0,
        "header_image": d.get("header_image") or "",
        "short_description": (d.get("short_description") or "")[:300],
    }
