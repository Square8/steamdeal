"""에픽게임즈·Steam(-100%)·GOG 기간 한정 무료 배포 수집 및 파싱."""
import html
import logging
import re
from datetime import datetime, timezone

import requests

import config
import steam
import store

log = logging.getLogger("freebies")

EPIC_FREE_URL = "https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions"
STEAM_SEARCH_URL = "https://store.steampowered.com/search/results/"
GOG_CATALOG_URL = "https://catalog.gog.com/v1/catalog"

HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; GameDil/1.0; +https://gamedil.com)",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8",
}

_UUID_RE = re.compile(r"^[0-9a-f]{32}$", re.I)
_EPIC_SKIP_OFFER_TYPES = {"DLC", "ADD_ON", "VIRTUAL_CURRENCY", "SEASON_PASS", "DEMO"}


def _clean_text(raw: str | None, limit: int = 220) -> str:
    txt = re.sub(r"\s+", " ", html.unescape(raw or "")).strip()
    if len(txt) <= limit:
        return txt
    return txt[: max(limit - 1, 0)].rstrip() + "…"


def _norm_title(name: str | None) -> str:
    return re.sub(r"[^a-z0-9가-힣]", "", (name or "").lower())


def _safe_https_url(url: str | None) -> str:
    u = str(url or "").strip()
    if u.startswith("//"):
        return "https:" + u
    if u.startswith("http://") or u.startswith("https://"):
        return u
    return ""


def _parse_float(raw) -> float | None:
    try:
        return float(str(raw).strip())
    except (TypeError, ValueError):
        return None


def _epic_url(elem: dict) -> str:
    offer_type = str(elem.get("offerType") or "").upper()
    prefix = "bundles" if offer_type == "BUNDLE" else "p"
    candidates: list[str] = []
    for key in ("offerMappings",):
        for m in (elem.get(key) or []):
            if isinstance(m, dict) and m.get("pageType") == "productHome" and m.get("pageSlug"):
                candidates.append(str(m["pageSlug"]))
    ns_maps = (elem.get("catalogNs") or {}).get("mappings") or []
    for m in ns_maps:
        if isinstance(m, dict) and m.get("pageType") == "productHome" and m.get("pageSlug"):
            candidates.append(str(m["pageSlug"]))
    ps = elem.get("productSlug")
    if isinstance(ps, str) and ps.strip():
        candidates.append(re.sub(r"/home$", "", ps.strip()))
    us = elem.get("urlSlug")
    if isinstance(us, str) and us.strip() and not _UUID_RE.fullmatch(us.strip()):
        candidates.append(re.sub(r"/home$", "", us.strip()))
    for c in candidates:
        slug = c.strip().strip("/")
        if slug and not _UUID_RE.fullmatch(slug):
            return f"https://store.epicgames.com/ko/{prefix}/{slug}"
    return "https://store.epicgames.com/ko/free-games"


def _epic_image(elem: dict) -> str:
    by_type: dict[str, str] = {}
    for img in (elem.get("keyImages") or []):
        if not isinstance(img, dict):
            continue
        t = str(img.get("type") or "")
        u = _safe_https_url(img.get("url"))
        if t and u and t not in by_type:
            by_type[t] = u
    for pref in ("OfferImageWide", "DieselStoreFrontWide", "Landscape",
                 "featuredMedia", "Thumbnail", "OfferImageTall"):
        if pref in by_type:
            return by_type[pref]
    return next(iter(by_type.values()), "")


def _iter_promo_offers(groups) -> list[dict]:
    out = []
    for grp in (groups or []):
        if isinstance(grp, dict):
            for o in (grp.get("promotionalOffers") or []):
                if isinstance(o, dict):
                    out.append(o)
    return out


def _is_zero_pct_offer(offer: dict) -> bool:
    ds = offer.get("discountSetting")
    if not isinstance(ds, dict):
        return False
    return ds.get("discountType") == "PERCENTAGE" and ds.get("discountPercentage") == 0


def parse_epic_freebies(payload: dict, now: datetime | None = None,
                        checked_at: str | None = None) -> list[dict]:
    """Epic freeGamesPromotions JSON에서 현재/예정 무료 배포 본편만 추출한다."""
    now_dt = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    stamp = checked_at or now_dt.isoformat(timespec="seconds")
    catalog = ((payload or {}).get("data") or {}).get("Catalog") or {}
    search_store = catalog.get("searchStore") or {}
    elements = search_store.get("elements") or []
    out: list[dict] = []
    seen_ids: set[str] = set()

    for elem in elements:
        if not isinstance(elem, dict):
            continue
        if str(elem.get("offerType") or "").upper() in _EPIC_SKIP_OFFER_TYPES:
            continue
        eid = str(elem.get("id") or "").strip()
        title = str(elem.get("title") or "").strip()
        if not (eid and title):
            continue

        promos = elem.get("promotions") or {}
        total_price = (elem.get("price") or {}).get("totalPrice") or {}
        fmt_price = total_price.get("fmtPrice") or {}
        orig_krw = int(total_price.get("originalPrice") or 0)
        disc_krw = total_price.get("discountPrice")
        orig_text = str(fmt_price.get("originalPrice") or "").strip()
        if not orig_text and orig_krw > 0:
            orig_text = f"₩{orig_krw:,}"

        matched_status = ""
        start_iso = None
        end_iso = None

        for offer in _iter_promo_offers(promos.get("promotionalOffers")):
            if not _is_zero_pct_offer(offer):
                continue
            sdt = store.parse_utc(offer.get("startDate"))
            edt = store.parse_utc(offer.get("endDate"))
            if edt is None or edt <= now_dt:
                continue
            if sdt is not None and sdt > now_dt:
                continue
            if disc_krw != 0 or orig_krw <= 0:
                continue
            matched_status = "active"
            start_iso = sdt.isoformat(timespec="seconds") if sdt else None
            end_iso = edt.isoformat(timespec="seconds")
            break

        if not matched_status:
            for offer in _iter_promo_offers(promos.get("upcomingPromotionalOffers")):
                if not _is_zero_pct_offer(offer):
                    continue
                sdt = store.parse_utc(offer.get("startDate"))
                edt = store.parse_utc(offer.get("endDate"))
                if edt is None or edt <= now_dt:
                    continue
                matched_status = "upcoming"
                start_iso = sdt.isoformat(timespec="seconds") if sdt else None
                end_iso = edt.isoformat(timespec="seconds")
                break

        if not matched_status:
            continue

        fid = f"epic:{eid}"
        if fid in seen_ids:
            continue
        seen_ids.add(fid)

        seller = elem.get("seller") or {}
        out.append({
            "id": fid,
            "store": "epic",
            "status": matched_status,
            "title": title,
            "url": _epic_url(elem),
            "image_url": _epic_image(elem),
            "description": _clean_text(elem.get("description"), 180),
            "developer": str(seller.get("name") or "").strip()[:100],
            "genres": "",
            "original_price": orig_krw,
            "original_price_text": orig_text,
            "currency": str(total_price.get("currencyCode") or "KRW"),
            "korean": 0,
            "review_desc": "",
            "review_positive_pct": None,
            "review_total": 0,
            "steam_appid": None,
            "start_at": start_iso,
            "end_at": end_iso,
            "checked_at": stamp,
        })
    return out


def fetch_epic_freebies(now: datetime | None = None) -> tuple[list[dict], bool]:
    try:
        r = requests.get(
            EPIC_FREE_URL,
            params={"locale": "ko", "country": "KR", "allowCountries": "KR"},
            headers=HTTP_HEADERS,
            timeout=config.TIMEOUT,
        )
        if r.status_code != 200:
            log.warning("Epic 무료 배포 조회 실패: HTTP %s", r.status_code)
            return [], False
        data = r.json()
        if not isinstance(data, dict) or "data" not in data:
            return [], False
        return parse_epic_freebies(data, now=now), True
    except (requests.RequestException, ValueError) as e:
        log.warning("Epic 무료 배포 요청 오류: %s", e)
        return [], False


def parse_steam_search_freebies(results_html: str, checked_at: str | None = None) -> list[dict]:
    """Steam 검색 결과 HTML 조각에서 -100%(0원) 기간 한정 무료 본편만 추출한다."""
    stamp = checked_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    out: list[dict] = []
    seen: set[int] = set()
    rows = re.findall(
        r'<a\b[^>]*class="[^"]*search_result_row[^"]*"[^>]*>.*?</a>',
        results_html or "",
        flags=re.S,
    )
    for row in rows:
        m_href = re.search(r'<a\b[^>]*href="([^"]+)"', row)
        href = html.unescape(m_href.group(1)) if m_href else ""
        if "/app/" not in href:
            continue
        m_id = re.search(r'data-ds-appid="(\d+)"', row)
        if not m_id:
            continue
        appid = int(m_id.group(1))
        if appid in seen:
            continue
        m_disc = re.search(r'data-discount="(\d+)"', row)
        m_fin = re.search(r'data-price-final="(\d+)"', row)
        if not (m_disc and m_disc.group(1) == "100" and m_fin and m_fin.group(1) == "0"):
            continue
        m_orig = re.search(r'<div[^>]*class="discount_original_price"[^>]*>(.*?)</div>', row, flags=re.S)
        orig_raw = re.sub(r"<[^>]+>", "", m_orig.group(1)) if m_orig else ""
        orig_text = _clean_text(orig_raw, 40)
        orig_digits = re.sub(r"\D", "", orig_text)
        orig_krw = int(orig_digits) if orig_digits else 0
        if orig_krw <= 0:
            continue
        m_title = re.search(r'<span[^>]*class="title"[^>]*>(.*?)</span>', row, flags=re.S)
        title = _clean_text(re.sub(r"<[^>]+>", "", m_title.group(1)) if m_title else "", 160)
        if not title:
            continue
        m_img = re.search(r'<div[^>]*class="search_capsule"[^>]*>\s*<img[^>]*src="([^"]+)"', row, flags=re.S)
        img = _safe_https_url(html.unescape(m_img.group(1))) if m_img else ""
        seen.add(appid)
        out.append({
            "id": f"steam:{appid}",
            "store": "steam",
            "status": "active",
            "title": title,
            "url": f"https://store.steampowered.com/app/{appid}/?cc=kr",
            "image_url": img,
            "description": "",
            "developer": "",
            "genres": "",
            "original_price": orig_krw,
            "original_price_text": f"₩{orig_krw:,}",
            "currency": "KRW",
            "korean": 0,
            "review_desc": "",
            "review_positive_pct": None,
            "review_total": 0,
            "steam_appid": appid,
            "start_at": None,
            "end_at": None,
            "checked_at": stamp,
        })
    return out


def fetch_steam_freebies(conn=None, now: datetime | None = None,
                         fetch_missing_details: bool = True) -> tuple[list[dict], bool]:
    now_dt = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    stamp = now_dt.isoformat(timespec="seconds")
    by_appid: dict[int, dict] = {}
    search_ok = False

    try:
        r = requests.get(
            STEAM_SEARCH_URL,
            params={
                "query": "",
                "specials": "1",
                "category1": "998",
                "sort_by": "Price_ASC",
                "cc": config.CC,
                "l": config.LANG,
                "infinite": "1",
                "count": "50",
            },
            headers=HTTP_HEADERS,
            timeout=config.TIMEOUT,
        )
        if r.status_code == 200:
            payload = r.json()
            if isinstance(payload, dict) and payload.get("success") == 1:
                search_ok = True
                for it in parse_steam_search_freebies(payload.get("results_html") or "", checked_at=stamp):
                    by_appid[int(it["steam_appid"])] = it
    except (requests.RequestException, ValueError) as e:
        log.warning("Steam 무료 배포 검색 오류: %s", e)

    db_games_by_id: dict[int, dict] = {}
    if conn is not None:
        for row in conn.execute("SELECT * FROM games"):
            g = dict(row)
            db_games_by_id[g["appid"]] = g
        # 검색 API 자체가 실패했을 때만 오늘 관측된 DB -100% 항목을 보조로 확인한다.
        # 검색이 성공했다면 실시간 검색 결과만 신뢰해 어제 종료된 DB 잔여 할인을 막는다.
        if not search_ok:
            for g in store.steam_freebie_candidates_from_db(conn, today=now_dt.date()):
                if g.get("price_last") != now_dt.date().isoformat():
                    continue
                appid = int(g["appid"])
                orig_krw = int(g.get("price_initial") or 0)
                by_appid[appid] = {
                    "id": f"steam:{appid}",
                    "store": "steam",
                    "status": "active",
                    "title": g["name"],
                    "url": f"https://store.steampowered.com/app/{appid}/?cc=kr",
                    "image_url": g.get("header_image") or "",
                    "description": _clean_text(g.get("description"), 180),
                    "developer": g.get("developer") or "",
                    "genres": g.get("genres") or "",
                    "original_price": orig_krw,
                    "original_price_text": f"₩{orig_krw:,}" if orig_krw > 0 else "",
                    "currency": "KRW",
                    "korean": 1 if g.get("korean") else 0,
                    "review_desc": g.get("review_desc") or "",
                    "review_positive_pct": None,
                    "review_total": 0,
                    "steam_appid": appid,
                    "start_at": None,
                    "end_at": None,
                    "checked_at": stamp,
                }
            if by_appid:
                search_ok = True

    out: list[dict] = []
    extra_fetched = 0
    for appid, it in by_appid.items():
        g = db_games_by_id.get(appid)
        if g:
            if g.get("adult"):
                continue
            it["title"] = g.get("name") or it["title"]
            it["image_url"] = g.get("header_image") or it["image_url"]
            it["description"] = it["description"] or _clean_text(g.get("description"), 180)
            it["developer"] = g.get("developer") or it["developer"]
            it["genres"] = g.get("genres") or it["genres"]
            it["korean"] = 1 if g.get("korean") else it["korean"]
            pos = int(g.get("review_positive") or 0)
            neg = int(g.get("review_negative") or 0)
            tot = pos + neg
            if tot > 0:
                it["review_total"] = tot
                it["review_positive_pct"] = round(pos * 100 / tot)
            it["review_desc"] = g.get("review_desc") or ""
        elif fetch_missing_details and extra_fetched < 5:
            extra_fetched += 1
            app = steam.fetch_app(appid)
            if app:
                if app.get("adult"):
                    continue
                it["title"] = app.get("name") or it["title"]
                it["image_url"] = app.get("header_image") or it["image_url"]
                it["description"] = _clean_text(app.get("description"), 180)
                it["developer"] = app.get("developer") or ""
                it["genres"] = app.get("genres") or ""
                it["korean"] = 1 if app.get("korean") else 0
                if app.get("price_initial"):
                    it["original_price"] = int(app["price_initial"])
                    it["original_price_text"] = f"₩{it['original_price']:,}"
                it["steam_appid"] = None  # 로컬 games DB 에 없는 앱이므로 깨진 내부 링크를 만들지 않는다
            else:
                it["steam_appid"] = None
        else:
            it["steam_appid"] = None
        out.append(it)

    return out, search_ok


def parse_gog_freebies(payload: dict, checked_at: str | None = None) -> list[dict]:
    """GOG Catalog API 응답에서 유료 게임이 -100%(0원) 배포 중인 항목만 추출한다."""
    stamp = checked_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    out: list[dict] = []
    seen: set[str] = set()
    for p in ((payload or {}).get("products") or []):
        if not isinstance(p, dict):
            continue
        ptype = str(p.get("productType") or "game").lower()
        if ptype not in ("game", "pack"):
            continue
        pid = str(p.get("id") or "").strip()
        title = str(p.get("title") or "").strip()
        slug = str(p.get("slug") or "").strip()
        if not (pid and title):
            continue
        price = p.get("price") or {}
        if str(price.get("discount") or "").strip() != "-100%":
            continue
        fin_amt = _parse_float((price.get("finalMoney") or {}).get("amount"))
        base_amt = _parse_float((price.get("baseMoney") or {}).get("amount"))
        if fin_amt is None or fin_amt != 0.0 or base_amt is None or base_amt <= 0.0:
            continue

        fid = f"gog:{pid}"
        if fid in seen:
            continue
        seen.add(fid)

        link = _safe_https_url(p.get("storeLink")) or (f"https://www.gog.com/en/game/{slug}" if slug else "")
        if not link:
            continue
        img = _safe_https_url(p.get("coverHorizontal")) or _safe_https_url(p.get("coverVertical"))
        devs = [str(d).strip() for d in (p.get("developers") or []) if str(d).strip()]
        genres = [str(g.get("name") or "").strip() for g in (p.get("genres") or []) if isinstance(g, dict) and g.get("name")]
        base_txt = str(price.get("base") or "").strip() or f"${base_amt:.2f}"
        curr = str((price.get("baseMoney") or {}).get("currency") or "USD")
        out.append({
            "id": fid,
            "store": "gog",
            "status": "active",
            "title": title,
            "url": link,
            "image_url": img,
            "description": "",
            "developer": ", ".join(devs)[:100],
            "genres": ", ".join(genres[:3])[:100],
            "original_price": 0,
            "original_price_text": base_txt,
            "currency": curr,
            "korean": 0,
            "review_desc": "",
            "review_positive_pct": None,
            "review_total": 0,
            "steam_appid": None,
            "start_at": None,
            "end_at": None,
            "checked_at": stamp,
        })
    return out


def fetch_gog_freebies() -> tuple[list[dict], bool]:
    try:
        r = requests.get(
            GOG_CATALOG_URL,
            params={
                "limit": 48,
                "order": "desc:discount",
                "discounted": "eq:true",
                "productType": "in:game,pack",
                "countryCode": "KR",
                "locale": "en-US",
                "currencyCode": "USD",
            },
            headers=HTTP_HEADERS,
            timeout=config.TIMEOUT,
        )
        if r.status_code != 200:
            log.warning("GOG 무료 배포 조회 실패: HTTP %s", r.status_code)
            return [], False
        data = r.json()
        if not isinstance(data, dict) or "products" not in data:
            return [], False
        return parse_gog_freebies(data), True
    except (requests.RequestException, ValueError) as e:
        log.warning("GOG 무료 배포 요청 오류: %s", e)
        return [], False


def enrich_with_steam_db(conn, items: list[dict]) -> list[dict]:
    """로컬 Steam DB와 정확히 이름이 일치하는 단일 비성인 본편만 교차 정보로 보강한다."""
    if not items or conn is None:
        return items
    by_norm: dict[str, list[dict]] = {}
    for row in conn.execute(
        "SELECT appid, name, genres, korean, review_desc, review_positive, review_negative, developer "
        "FROM games WHERE app_type='game' AND adult=0"
    ):
        g = dict(row)
        nk = _norm_title(g.get("name"))
        if len(nk) >= 4:
            by_norm.setdefault(nk, []).append(g)

    for it in items:
        if it.get("store") == "steam":
            continue
        hits = by_norm.get(_norm_title(it.get("title")), [])
        if len(hits) != 1:
            continue
        g = hits[0]
        it["steam_appid"] = g["appid"]
        if g.get("korean"):
            it["korean"] = 1
        if not it.get("genres") and g.get("genres"):
            it["genres"] = g["genres"]
        if not it.get("developer") and g.get("developer"):
            it["developer"] = g["developer"]
        pos = int(g.get("review_positive") or 0)
        neg = int(g.get("review_negative") or 0)
        tot = pos + neg
        if tot > 0:
            it["review_total"] = tot
            it["review_positive_pct"] = round(pos * 100 / tot)
            it["review_desc"] = g.get("review_desc") or ""
    return items


def collect_all_freebies(conn, logger=None) -> dict[str, dict]:
    """에픽·Steam·GOG 무료 배포를 스토어별로 독립 수집해 저장한다."""
    lg = logger or log
    now_dt = datetime.now(timezone.utc)
    stamp = now_dt.isoformat(timespec="seconds")

    epic_items, epic_ok = fetch_epic_freebies(now=now_dt)
    steam_items, steam_ok = fetch_steam_freebies(conn=conn, now=now_dt)
    gog_items, gog_ok = fetch_gog_freebies()

    results = {
        "epic": {"ok": epic_ok, "items": epic_items},
        "steam": {"ok": steam_ok, "items": steam_items},
        "gog": {"ok": gog_ok, "items": gog_items},
    }
    for sname, info in results.items():
        if not info["ok"]:
            lg.warning("무료 배포(%s) 수집 실패 — 기존 데이터 보존", sname)
            continue
        enriched = enrich_with_steam_db(conn, info["items"]) if sname != "steam" else info["items"]
        saved = store.replace_freebies_for_store(conn, sname, enriched, checked_at=stamp)
        info["saved"] = saved
    conn.commit()
    lg.info(
        "무료 배포 — Epic %s(%d), Steam %s(%d), GOG %s(%d)",
        "OK" if epic_ok else "ERR", len(epic_items),
        "OK" if steam_ok else "ERR", len(steam_items),
        "OK" if gog_ok else "ERR", len(gog_items),
    )
    return results
