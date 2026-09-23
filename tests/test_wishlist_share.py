"""찜 목록 공유 링크 — Claude 독립 검증.

대상: Gemini 구현(build.py: my-games.html 공유 버튼, 신규 shared-games.html).
원칙: 문자열 존재 검사로 동작 PASS를 내지 않는다. 임시 DB로 실제 build.main()을
돌리고, 로컬 HTTP 서버 + Playwright 실제 브라우저 DOM/localStorage/클립보드/대화상자로
판정한다. 운영 DB·site/ 는 건드리지 않는다(임시 DB_PATH/SITE_DIR).
실행: python3 tests/test_wishlist_share.py  (exit 0 = FAIL 없음)
"""
import http.server
import json
import os
import socketserver
import sqlite3
import sys
import tempfile
import threading
from urllib.parse import urlsplit

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

TMP = tempfile.mkdtemp(prefix="gamedil_wishshare_qa_")
DB_PATH = os.path.join(TMP, "fixture.sqlite3")
SITE_DIR = os.path.join(TMP, "site")
os.environ["DB_PATH"] = DB_PATH
os.environ["SITE_DIR"] = SITE_DIR

FAILS, SKIPPED = [], []
WISH_KEY = "steamdeal-wishlist-v1"
TARGET_KEY = "steamdeal-target-price-v1"


def check(label, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {label}" + (f"  ({detail})" if detail else ""))
    if not cond:
        FAILS.append(label)


def skip(label, reason):
    print(f"  SKIP  {label}  — {reason}")
    SKIPPED.append(label)


# appid, name, adult, price
BASE = [(720001, "공유게임A", 0, 12000), (720002, "공유게임B", 0, 8000),
        (720003, "공유게임C", 0, 30000), (720009, "성인게임X", 1, 9000)]
BULK = [(721000 + i, f"대량게임{i:02d}", 0, 5000 + i) for i in range(35)]
ALL = BASE + BULK
GHOST = "99999999"  # 인덱스에 없는 appid


def build_fixture():
    import store
    import config
    config.DB_PATH, config.SITE_DIR = DB_PATH, SITE_DIR
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(store.SCHEMA)
    for appid, name, adult, price in ALL:
        conn.execute(
            "INSERT INTO games (appid,name,app_type,korean,adult,review_positive,review_negative,"
            "review_count,first_seen,last_seen,checked_at,price_first,price_last,header_image) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (appid, name, "game", 1, adult, 90, 10, 100, "2026-08-01", "2026-09-20",
             "2026-09-20", "2026-08-01", "2026-09-20", ""))
        for d in ("2026-08-01", "2026-09-20"):
            conn.execute("INSERT INTO prices (appid,on_date,price_final,price_initial,discount_pct) "
                         "VALUES (?,?,?,?,?)", (appid, d, price, price, 0))
    conn.commit()
    conn.close()
    import build
    build.main()


def start_server():
    handler = lambda *a, **kw: http.server.SimpleHTTPRequestHandler(*a, directory=SITE_DIR, **kw)
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


def static_checks():
    print("\n[정적 산출물]")
    p = os.path.join(SITE_DIR, "shared-games.html")
    check("build.main()이 shared-games.html 생성", os.path.exists(p))
    html = open(p, encoding="utf-8").read() if os.path.exists(p) else ""
    check("shared-games.html noindex", 'name="robots" content="noindex' in html)
    sm = open(os.path.join(SITE_DIR, "sitemap.xml"), encoding="utf-8").read()
    check("sitemap.xml에 shared-games 미포함", "shared-games" not in sm)
    idx = json.load(open(os.path.join(SITE_DIR, "assets", "game-search-index.json"), encoding="utf-8"))
    check("검색 인덱스에 픽스처 전체 포함", len(idx) >= len(ALL), f"{len(idx)}개")


def new_page(ctx, errors, dialogs):
    page = ctx.new_page()
    page.on("pageerror", lambda e: errors.append(str(e)))

    def on_dialog(d):
        dialogs.append((d.type, d.message, d.default_value))
        d.accept()
    page.on("dialog", on_dialog)
    return page


def set_storage(page, base, wish, targets=None):
    page.goto(f"{base}/404.html")
    page.evaluate("([k,v,tk,tv]) => { localStorage.setItem(k, JSON.stringify(v));"
                  " if (tv) localStorage.setItem(tk, JSON.stringify(tv)); else localStorage.removeItem(tk); }",
                  [WISH_KEY, wish, TARGET_KEY, targets])


def share_checks(browser, base):
    print("\n[my-games 공유 버튼]")
    origin = base
    ctx = browser.new_context(permissions=["clipboard-read", "clipboard-write"])
    errors, dialogs = [], []
    page = new_page(ctx, errors, dialogs)

    set_storage(page, base, [])
    page.goto(f"{base}/my-games.html")
    page.wait_for_timeout(300)
    btn = page.query_selector("#shareBtn")
    check("찜 0개: 공유 버튼 숨김", btn is not None and not btn.is_visible())

    wish = ["720002", "720001", "720003"]
    set_storage(page, base, wish)
    page.goto(f"{base}/my-games.html")
    page.wait_for_selector(".my-card", timeout=5000)
    btn = page.query_selector("#shareBtn")
    check("찜 3개: 공유 버튼 표시", btn is not None and btn.is_visible())
    dialogs.clear()
    btn.click()
    page.wait_for_timeout(400)
    clip = page.evaluate("navigator.clipboard.readText()")
    exp = f"{origin}/shared-games.html#ids=720002,720001,720003"
    check("클립보드 링크 = origin/shared-games.html#ids=(찜 순서 그대로)", clip == exp, clip)
    check("복사 성공 안내 표시", any("복사" in m for _, m, _ in dialogs), str(dialogs))

    many = [str(a) for a, *_ in BULK]  # 35개
    set_storage(page, base, many)
    page.goto(f"{base}/my-games.html")
    page.wait_for_selector(".my-card", timeout=5000)
    dialogs.clear()
    page.click("#shareBtn")
    page.wait_for_timeout(400)
    clip = page.evaluate("navigator.clipboard.readText()")
    ids = clip.split("#ids=", 1)[-1].split(",")
    check("35개 찜 → 링크에는 앞 30개만", ids == many[:30], f"{len(ids)}개")
    check("30개 초과 안내 표시", any("30" in m for _, m, _ in dialogs), str(dialogs))
    check("my-games 콘솔/JS 오류 없음", not errors, str(errors[:2]))
    ctx.close()

    print("\n[클립보드 실패 폴백]")
    ctx = browser.new_context()
    ctx.add_init_script("try{Object.defineProperty(navigator,'clipboard',{value:{writeText:function(){"
                        "return Promise.reject(new Error('denied'));}},configurable:true});}catch(e){}")
    errors, dialogs = [], []
    page = new_page(ctx, errors, dialogs)
    set_storage(page, base, ["720001"])
    page.goto(f"{base}/my-games.html")
    page.wait_for_selector(".my-card", timeout=5000)
    page.click("#shareBtn")
    page.wait_for_timeout(400)
    pr = [d for d in dialogs if d[0] == "prompt"]
    check("writeText 거부 시 링크가 담긴 prompt 폴백",
          bool(pr) and pr[0][2] == f"{origin}/shared-games.html#ids=720001", str(dialogs))
    ctx.close()


def shared_cards(page):
    return page.eval_on_selector_all("#myApp .my-card .my-card-title", "els => els.map(e => e.textContent)")


def shared_page_checks(browser, base):
    print("\n[shared-games 렌더링/방어]")
    ctx = browser.new_context()
    errors, dialogs = [], []
    page = new_page(ctx, errors, dialogs)
    set_storage(page, base, [])

    page.goto(f"{base}/shared-games.html#ids=720001,720002")
    page.wait_for_selector(".my-card", timeout=5000)
    names = shared_cards(page)
    check("유효 ids 2개 → 카드 2개", sorted(names) == ["공유게임A", "공유게임B"], str(names))
    check("공유 페이지에 목표가 UI 없음", page.query_selector("#myApp .target-input") is None)
    wish_after_view = page.evaluate(f"localStorage.getItem('{WISH_KEY}')")
    check("열람만으로 내 찜 변경 없음", wish_after_view in ("[]", None), str(wish_after_view))

    page.goto(f"{base}/shared-games.html#ids=720001,abc,,720002,720002,-5")
    page.wait_for_selector(".my-card", timeout=5000)
    check("숫자 아닌 값/중복 무시 → 카드 2개", len(shared_cards(page)) == 2, str(shared_cards(page)))

    for h in ["", "#ids=", "#ids=abc,,x", "#foo=720001"]:
        page.goto(f"{base}/shared-games.html{h}")
        page.wait_for_timeout(400)
        txt = page.inner_text("#myApp")
        check(f"잘못된 hash '{h or '(없음)'}' → 안내 문구, 카드 0", "잘못된 링크" in txt and not shared_cards(page), txt[:40])

    page.goto(f"{base}/shared-games.html#ids={GHOST}")
    page.wait_for_timeout(800)
    txt = page.inner_text("#myApp").strip()
    cnt = page.inner_text("#myCnt") if page.query_selector("#myCnt") else ""
    check("인덱스에 없는 appid만 있는 링크 → 빈 화면 대신 안내 문구", bool(txt),
          f"myApp='{txt[:30]}', 카운트='{cnt}'")

    page.goto(f"{base}/shared-games.html#ids=720001")
    page.wait_for_selector(".my-card", timeout=5000)
    page.evaluate("location.hash = '#ids=720002,720003'")
    page.wait_for_timeout(500)
    check("같은 페이지 hash 변경 시 재렌더", sorted(shared_cards(page)) == ["공유게임B", "공유게임C"],
          str(shared_cards(page)))

    page.goto(f"{base}/shared-games.html#ids=720001,720009")
    page.wait_for_selector(".my-card", timeout=5000)
    names = shared_cards(page)
    check("성인 게임은 기본 화면에서 숨김(사이트 공통 정책)", "성인게임X" not in names, str(names))

    # 레이아웃: 내 찜 목록과 같은 그리드인지 실제 computed style로 비교
    for label, w, h in [("1440 데스크톱", 1440, 900), ("390 모바일", 390, 844)]:
        page.set_viewport_size({"width": w, "height": h})
        page.goto(f"{base}/shared-games.html#ids=720001,720002,720003")
        page.wait_for_selector(".my-card", timeout=5000)
        disp = page.evaluate("getComputedStyle(document.querySelector('#myApp > div')).display")
        cw = page.evaluate("document.querySelector('#myApp .my-card').getBoundingClientRect().width")
        over = page.evaluate("document.documentElement.scrollWidth > window.innerWidth")
        check(f"{label}: 카드 컨테이너가 grid", disp == "grid", f"display={disp}, 카드폭={cw:.0f}px")
        check(f"{label}: 가로 스크롤 없음", not over)
        page.screenshot(path=os.path.join(TMP, f"shared_{w}.png"), full_page=True)
    page.set_viewport_size({"width": 1440, "height": 900})
    check("shared-games 콘솔/JS 오류 없음", not errors, str(errors[:2]))
    ctx.close()


def merge_checks(browser, base):
    print("\n[내 찜 목록에 모두 추가]")
    ctx = browser.new_context()
    errors, dialogs = [], []
    page = new_page(ctx, errors, dialogs)
    set_storage(page, base, ["720003"], {"720003": 25000})
    page.goto(f"{base}/shared-games.html#ids=720001,720003")
    page.wait_for_selector("#addAllBtn", state="visible", timeout=5000)
    with page.expect_navigation():
        page.click("#addAllBtn")
    page.wait_for_selector(".my-card", timeout=5000)
    check("추가 후 my-games.html로 이동", urlsplit(page.url).path.endswith("/my-games.html"), page.url)
    wish = set(json.loads(page.evaluate(f"localStorage.getItem('{WISH_KEY}')")))
    tg = json.loads(page.evaluate(f"localStorage.getItem('{TARGET_KEY}')") or "{}")
    check("기존 찜과 합집합(중복 없음)", wish == {"720001", "720003"}, str(sorted(wish)))
    check("기존 목표가 보존", tg.get("720003") == 25000, str(tg))
    check("my-games에 합쳐진 2개 표시", len(page.query_selector_all("#myApp .my-card")) == 2)

    set_storage(page, base, [])
    page.goto(f"{base}/shared-games.html#ids=720001,{GHOST}")
    page.wait_for_selector("#addAllBtn", state="visible", timeout=5000)
    with page.expect_navigation():
        page.click("#addAllBtn")
    page.wait_for_selector(".my-card", timeout=5000)
    wish = json.loads(page.evaluate(f"localStorage.getItem('{WISH_KEY}')"))
    badge = page.inner_text(".wish-count")
    check("인덱스에 없는 appid는 내 찜에 추가하지 않음", GHOST not in wish,
          f"저장={wish}, 헤더 찜 수={badge}, 화면 카드={len(page.query_selector_all('#myApp .my-card'))}")
    # 성인 토글: 기본(해제) → 성인 게임은 병합 제외, 체크 시 표시·병합
    for checked, expect in [(False, {"720001"}), (True, {"720001", "720009"})]:
        set_storage(page, base, [])
        page.goto(f"{base}/shared-games.html#ids=720001,720009")
        page.wait_for_selector(".my-card", timeout=5000)
        toggle = page.query_selector("#myAdult")
        if checked:
            if not toggle:
                check("공유 페이지 '성인 게임 포함' 토글 존재", False)
                continue
            toggle.check()
            page.wait_for_timeout(300)
            check("토글 체크 시 성인 게임 표시", "성인게임X" in shared_cards(page), str(shared_cards(page)))
        with page.expect_navigation():
            page.click("#addAllBtn")
        page.wait_for_selector(".my-card", timeout=5000)
        wish = set(json.loads(page.evaluate(f"localStorage.getItem('{WISH_KEY}')")))
        check(f"성인 토글 {'체크' if checked else '해제'} 상태 병합 = 화면 표시 항목만", wish == expect, str(sorted(wish)))

    # 표시 항목 0개(없는 appid만)일 때 모두 추가가 아무것도 저장하지 않는지
    set_storage(page, base, ["720002"])
    page.goto(f"{base}/shared-games.html#ids={GHOST}")
    page.wait_for_timeout(800)
    add_btn = page.query_selector("#addAllBtn")
    if add_btn and add_btn.is_visible():
        add_btn.click()
        page.wait_for_timeout(800)
    wish = json.loads(page.evaluate(f"localStorage.getItem('{WISH_KEY}')"))
    check("표시 0개 링크에서 기존 찜 변경 없음", wish == ["720002"], str(wish))
    check("merge 흐름 콘솔/JS 오류 없음", not errors, str(errors[:2]))
    ctx.close()


def regression_checks(browser, base):
    print("\n[회귀]")
    ctx = browser.new_context()
    errors, dialogs = [], []
    page = new_page(ctx, errors, dialogs)
    set_storage(page, base, [])
    page.goto(f"{base}/index.html")
    btn = page.query_selector("[data-wish-id='720001']")
    if not btn:
        skip("홈 카드 찜 버튼 토글", "홈에 720001 찜 버튼 없음")
    else:
        btn.scroll_into_view_if_needed()
        btn.click()
        wish = json.loads(page.evaluate(f"localStorage.getItem('{WISH_KEY}')") or "[]")
        check("홈 카드 ♡ 클릭 → 찜 저장(기존 동작 유지)", wish == ["720001"], str(wish))
        set_storage(page, base, ["720001"])
    page.goto(f"{base}/my-games.html")
    page.wait_for_selector(".my-card", timeout=5000)
    check("my-games 목표가 입력 UI 유지", page.query_selector("#myApp .target-input") is not None)
    check("회귀 흐름 콘솔/JS 오류 없음", not errors, str(errors[:2]))
    ctx.close()


def main():
    build_fixture()
    static_checks()
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        skip("브라우저 검증 전체", "playwright 없음")
        return finish()
    httpd, port = start_server()
    base = f"http://127.0.0.1:{port}"
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for fn in (share_checks, shared_page_checks, merge_checks, regression_checks):
            try:
                fn(browser, base)
            except Exception as e:  # 한 구역 실패가 나머지 검증을 막지 않게
                check(f"{fn.__name__} 실행 중 예외 없음", False, repr(e)[:160])
        browser.close()
    httpd.shutdown()
    return finish()


def finish():
    print(f"\n결과: FAIL {len(FAILS)} / SKIP {len(SKIPPED)}  (산출물: {TMP})")
    for f in FAILS:
        print("  - FAIL:", f)
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
