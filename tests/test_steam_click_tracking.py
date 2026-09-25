"""Steam 상점 클릭 GA4 이벤트(steam_store_click) — Claude 독립 검증.

대상: Gemini 구현(build.py: ga_tag() 내부 document 클릭 위임 리스너).
원칙: 문자열 존재 검사만으로 동작 PASS를 내지 않는다. 임시 DB로 실제 build.main()을
돌리고, 로컬 HTTP 서버 + Playwright 실제 브라우저에서 window.dataLayer에 실제로
쌓이는 이벤트를 읽어 appid/link_url을 검증한다. page_location은 R1 Codex 리뷰에서
GA4 표준(전체 URL 필요, gtag.js가 모든 이벤트에 자동 첨부)과 맞지 않는다는 지적을
받아 Gemini가 페이로드에서 제거했다 — 이번 R2 검증은 그 제거 상태를 확인한다.
GA_TRACKING_ID on/off 두 빌드를 모두 만들어 비교하고, 기존 클릭 기능(찜 토글) 회귀도 확인한다.
운영 DB·site/ 는 건드리지 않는다(임시 DB_PATH/SITE_DIR). 커밋·push 없음.
실행: python3 tests/test_steam_click_tracking.py  (exit 0 = FAIL 없음)
"""
import http.server
import os
import socketserver
import sqlite3
import sys
import tempfile
import threading

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

TMP = tempfile.mkdtemp(prefix="gamedil_gaclick_qa_")
FAILS, SKIPPED = [], []

FIX = {
    # appid: (name, korean, adult, soon, is_free, price, pos, neg, desc, has_demo, demo_appid)
    730001: ("기본게임", 1, 0, 0, 0, 8000, 95, 5, "Very Positive", 0, None),
    730002: ("데모있는게임", 1, 0, 0, 0, 12000, 80, 20, "Positive", 1, 730900),
}


def check(label, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {label}" + (f"  ({detail})" if detail else ""))
    if not cond:
        FAILS.append(label)


def build_site(db_path, site_dir, ga_id):
    import config
    import store
    os.environ["DB_PATH"], os.environ["SITE_DIR"] = db_path, site_dir
    config.DB_PATH, config.SITE_DIR = db_path, site_dir
    config.SITE_URL = "https://gamedil.com"
    config.GA_TRACKING_ID = ga_id
    conn = sqlite3.connect(db_path)
    conn.executescript(store.SCHEMA)
    for appid, (name, kr, adult, soon, free, price, pos, neg, desc, has_demo, demo_appid) in FIX.items():
        conn.execute(
            "INSERT INTO games (appid,name,app_type,korean,adult,coming_soon,is_free,review_positive,"
            "review_negative,review_count,review_desc,first_seen,last_seen,checked_at,price_first,price_last,"
            "header_image,has_demo,demo_appid) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (appid, name, "game", kr, adult, soon, free, pos, neg, pos + neg, desc, "2026-08-01",
             "2026-09-20", "2026-09-20", "2026-08-01", "2026-09-20", "", has_demo, demo_appid))
        for d in ("2026-08-01", "2026-09-20"):
            conn.execute("INSERT INTO prices (appid,on_date,price_final,price_initial,discount_pct) "
                         "VALUES (?,?,?,?,?)", (appid, d, price, price, 0))
    conn.commit()
    conn.close()
    import build
    build.main()


def serve(site_dir):
    h = lambda *a, **kw: http.server.SimpleHTTPRequestHandler(*a, directory=site_dir, **kw)
    httpd = socketserver.TCPServer(("127.0.0.1", 0), h)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}"


def read_events(page):
    """dataLayer에 쌓인 gtag('event', ...) 호출만 [name, params] 형태로 뽑는다."""
    return page.evaluate(
        "() => (window.dataLayer||[]).map(a => Array.prototype.slice.call(a))"
        ".filter(a => a[0] === 'event').map(a => [a[1], a[2]])"
    )


def static_off_checks(site_off):
    print("\n[GA_TRACKING_ID 빈 값 — 정적 산출물]")
    idx = open(os.path.join(site_off, "index.html"), encoding="utf-8").read()
    check("GA_TRACKING_ID 빈 값이면 Google tag 스크립트 없음", "googletagmanager.com/gtag" not in idx)
    check("GA_TRACKING_ID 빈 값이면 steam_store_click 리스너 없음", "steam_store_click" not in idx)
    check("GA_TRACKING_ID 빈 값이면 <!-- Google tag --> 블록 자체가 없음",
          "<!-- Google tag (gtag.js) -->" not in idx)


def static_on_checks(site_on):
    print("\n[GA_TRACKING_ID 설정됨 — 정적 산출물]")
    idx = open(os.path.join(site_on, "index.html"), encoding="utf-8").read()
    detail = open(os.path.join(site_on, "game", "730001.html"), encoding="utf-8").read()
    check("index.html에 steam_store_click 리스너 존재", "steam_store_click" in idx)
    check("상세 페이지에도 steam_store_click 리스너 존재(공용 ga_tag)", "steam_store_click" in detail)
    check("capture 단계 등록(true 세 번째 인자)",
          "document.addEventListener('click', function(e){" in idx and idx.count("}, true);") >= 1)
    check("preventDefault 호출 없음(기존 클릭 기능 방해 금지)", "e.preventDefault()" not in idx.split("steam_store_click")[0][-400:]
          and ".preventDefault()" not in _listener_block(idx))
    check("stopPropagation 호출 없음(기존 클릭 기능 방해 금지)", ".stopPropagation()" not in _listener_block(idx))
    check("리스너 코드에 page_location 커스텀 파라미터 없음(R1 지적 반영, GA4 자동 수집에 위임)",
          "page_location" not in _listener_block(idx))
    return idx


def _listener_block(html):
    i = html.find("document.addEventListener('click'")
    j = html.find("</script>", i)
    return html[i:j] if i >= 0 and j >= 0 else ""


def browser_checks(browser, base_on):
    print("\n[실제 클릭 → dataLayer 이벤트]")
    ctx = browser.new_context()
    page = ctx.new_page()
    errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))
    # 참고: index.html 카드는 상세 페이지(./game/xxx.html)로만 연결되고 스팀 상점 직접 링크가 없다
    # (히어로 섹션은 별도 추천 조건 충족 시에만 렌더링됨). 따라서 실제 클릭 검증은 상세 페이지에서 한다.
    page.goto(f"{base_on}/game/730001.html")
    page.wait_for_selector(".btn-p")

    with ctx.expect_page() as new_tab_info:
        page.click('a.btn-p[href*="store.steampowered.com/app/730001"]')
    new_tab = new_tab_info.value
    new_tab.close()
    page.wait_for_timeout(200)
    events = read_events(page)
    hero_events = [e for e in events if e[0] == "steam_store_click"]
    check("상세 페이지 '스팀 상점에서 보기' 클릭 → steam_store_click 이벤트 1건", len(hero_events) == 1, str(hero_events))
    if hero_events:
        params = hero_events[0][1]
        check("appid=730001 정확히 추출", str(params.get("appid")) == "730001", str(params))
        check("link_url에 store.steampowered.com/app/730001 포함", "store.steampowered.com/app/730001" in params.get("link_url", ""), params.get("link_url"))
        check("페이로드에 page_location 커스텀 키 없음(GA4 자동 수집에 위임, R1 지적 반영)",
              "page_location" not in params, str(params))

    # 2) 다른 게임 상세 페이지의 "스팀 상점에서 보기" 버튼
    page.goto(f"{base_on}/game/730002.html")
    page.wait_for_selector(".btn-p")
    with ctx.expect_page() as new_tab_info2:
        page.click('a.btn-p[href*="store.steampowered.com/app/730002"]')
    new_tab_info2.value.close()
    page.wait_for_timeout(200)
    events2 = [e for e in read_events(page) if e[0] == "steam_store_click"]
    # 페이지 이동(goto) 시 dataLayer는 새로 초기화되므로 이 페이지 기준 1건이 정상.
    check("상세 페이지(730002) 구매 버튼 클릭 → steam_store_click 이벤트 1건", len(events2) == 1, str(events2))
    if len(events2) == 1:
        p2 = events2[0][1]
        check("두 번째 페이지 이벤트 appid=730002", str(p2.get("appid")) == "730002", str(p2))
        check("두 번째 페이지 이벤트도 page_location 커스텀 키 없음", "page_location" not in p2, str(p2))

    # 3) 데모 받기 링크(다른 appid: demo_appid)도 매칭되는지
    events_before = len(read_events(page))
    demo_link = page.query_selector('a.btn-s[href*="store.steampowered.com/app/730900"]')
    check("데모 링크가 실제로 존재(테스트 전제 확인)", demo_link is not None)
    if demo_link:
        with ctx.expect_page() as new_tab_info3:
            demo_link.click()
        new_tab_info3.value.close()
        page.wait_for_timeout(200)
        events3 = [e for e in read_events(page) if e[0] == "steam_store_click"]
        check("데모 링크 클릭 → appid=730900로 별도 이벤트", any(str(e[1].get("appid")) == "730900" for e in events3), str(events3))

    check("클릭 추적 도입 후 콘솔/페이지 오류 없음", not errs, str(errs))
    ctx.close()

    print("\n[회귀: 찜 토글 — capture 리스너가 기존 클릭 기능을 막지 않는지]")
    ctx2 = browser.new_context()
    page2 = ctx2.new_page()
    page2.goto(f"{base_on}/index.html")
    page2.wait_for_selector(".wish")
    btn = page2.query_selector('.wish[data-wish-id="730001"]')
    before_pressed = btn.get_attribute("aria-pressed")
    page2.click('.wish[data-wish-id="730001"]')
    page2.wait_for_timeout(150)
    after_pressed = page2.query_selector('.wish[data-wish-id="730001"]').get_attribute("aria-pressed")
    wish_ls = page2.evaluate("localStorage.getItem('steamdeal-wishlist-v1')")
    check("찜 버튼 클릭 시 실제 localStorage에 반영(capture 리스너로 인한 회귀 없음)",
          before_pressed == "false" and after_pressed == "true" and wish_ls and "730001" in wish_ls,
          f"before={before_pressed} after={after_pressed} ls={wish_ls}")
    check("찜 버튼 클릭이 카드 링크(상세 페이지 이동)를 발생시키지 않음(같은 페이지 유지)",
          page2.url.endswith("/index.html"), page2.url)
    wish_events = [e for e in read_events(page2) if e[0] == "steam_store_click"]
    check("찜 버튼 클릭은 steam_store_click을 발생시키지 않음(스팀 링크 아님)", not wish_events, str(wish_events))
    ctx2.close()


def off_browser_checks(browser, base_off):
    print("\n[GA_TRACKING_ID 빈 값 — 실제 브라우저에서도 리스너 없음]")
    ctx = browser.new_context()
    page = ctx.new_page()
    errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))
    page.goto(f"{base_off}/game/730001.html")
    page.wait_for_selector(".btn-p")
    has_datalayer = page.evaluate("typeof window.dataLayer !== 'undefined'")
    check("GA_TRACKING_ID 빈 값이면 dataLayer 자체가 생성되지 않음", not has_datalayer)
    with ctx.expect_page() as new_tab_info:
        page.click('a.btn-p[href*="store.steampowered.com/app/730001"]')
    new_tab_info.value.close()
    page.wait_for_timeout(150)
    check("GA 꺼짐 상태에서 스팀 링크 클릭해도 오류 없음(리스너가 아예 없으므로 당연히 이벤트도 없음)", not errs, str(errs))
    ctx.close()


def main():
    site_on = os.path.join(TMP, "site_on")
    site_off = os.path.join(TMP, "site_off")
    build_site(os.path.join(TMP, "fixture_on.sqlite3"), site_on, "G-TESTID123")
    static_on_checks(site_on)
    build_site(os.path.join(TMP, "fixture_off.sqlite3"), site_off, "")
    static_off_checks(site_off)

    from playwright.sync_api import sync_playwright
    httpd_on, base_on = serve(site_on)
    httpd_off, base_off = serve(site_off)
    with sync_playwright() as p:
        b = p.chromium.launch()
        for fn in (lambda: browser_checks(b, base_on), lambda: off_browser_checks(b, base_off)):
            try:
                fn()
            except Exception as e:
                check("검증 구역 실행 중 예외 없음", False, repr(e)[:300])
        b.close()
    httpd_on.shutdown()
    httpd_off.shutdown()

    print(f"\n결과: FAIL {len(FAILS)} / SKIP {len(SKIPPED)}  (산출물: {TMP})")
    for f in FAILS:
        print("  - FAIL:", f)
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
