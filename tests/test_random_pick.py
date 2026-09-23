"""랜덤 갓겜 가챠(pick.html) — Claude 독립 검증.

원칙: 임시 DB로 실제 build.main() 빌드 → 로컬 서버 + Playwright 실제 DOM/hash/클립보드로 판정.
문자열 존재만으로 동작 PASS를 내지 않는다. 운영 DB·site/ 미사용.
기대 후보는 픽스처 정의에서 직접 계산하고, 빌드된 인덱스 값과도 대조해
(테스트 오라클 자체 오류 방지) 판정한다.
실행: python3 tests/test_random_pick.py  (exit 0 = FAIL 없음)
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
TMP = tempfile.mkdtemp(prefix="gamedil_pick_qa_")
FAILS, SKIPPED = [], []


def check(label, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {label}" + (f"  ({detail})" if detail else ""))
    if not cond:
        FAILS.append(label)


# appid: (name, korean, adult, soon, is_free, price, pos, neg, review_desc)
FIX = {
    730001: ("후보-기본", 1, 0, 0, 0, 8000, 95, 5, "Very Positive"),
    730002: ("후보-경계가격10000", 1, 0, 0, 0, 10000, 180, 20, "Very Positive"),
    730003: ("후보-경계긍정90리뷰50", 1, 0, 0, 0, 5000, 45, 5, "Very Positive"),
    730101: ("제외-가격10001", 1, 0, 0, 0, 10001, 95, 5, "Very Positive"),
    730102: ("제외-긍정89", 1, 0, 0, 0, 5000, 89, 11, "Very Positive"),
    730103: ("제외-리뷰49", 1, 0, 0, 0, 5000, 49, 0, "Positive"),
    730104: ("제외-한국어없음", 0, 0, 0, 0, 5000, 95, 5, "Very Positive"),
    730105: ("제외-출시예정", 1, 0, 1, 0, 5000, 95, 5, "Very Positive"),
    730106: ("제외-무료", 1, 0, 0, 1, 0, 95, 5, "Very Positive"),
    730107: ("제외-성인", 1, 1, 0, 0, 5000, 95, 5, "Very Positive"),
    730108: ("제외-비싼인기작", 1, 0, 0, 0, 30000, 900, 100, "Very Positive"),
}
EXPECTED = {a for a, v in FIX.items() if v[1] and not v[2] and not v[3] and not v[4]
            and 0 < v[5] <= 10000 and v[6] + v[7] >= 50 and round(v[6] * 100 / (v[6] + v[7])) >= 90}


def build_site(db_path, site_dir, fixture):
    import config
    import store
    os.environ["DB_PATH"], os.environ["SITE_DIR"] = db_path, site_dir
    config.DB_PATH, config.SITE_DIR = db_path, site_dir
    config.SITE_URL = "https://gamedil.com"  # 비면 sitemap이 빈 urlset이 되어 포함/미포함 검사가 무의미해진다
    conn = sqlite3.connect(db_path)
    conn.executescript(store.SCHEMA)
    for appid, (name, kr, adult, soon, free, price, pos, neg, desc) in fixture.items():
        conn.execute(
            "INSERT INTO games (appid,name,app_type,korean,adult,coming_soon,is_free,review_positive,"
            "review_negative,review_count,review_desc,first_seen,last_seen,checked_at,price_first,price_last,"
            "header_image) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (appid, name, "game", kr, adult, soon, free, pos, neg, pos + neg, desc, "2026-08-01",
             "2026-09-20", "2026-09-20", "2026-08-01", "2026-09-20", ""))
        if not soon:
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


def shown(page):
    return page.eval_on_selector_all("#myApp .my-card-title", "e => e.map(x => x.textContent)")


def new_page(ctx, errors, dialogs):
    page = ctx.new_page()
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("dialog", lambda d: (dialogs.append((d.type, d.message, d.default_value)), d.accept()))
    return page


def wait_ready(page):
    page.wait_for_function("!document.querySelector('#myApp').textContent.includes('불러오는 중')", timeout=5000)


def static_checks(site):
    print("\n[정적 산출물/인덱스 대조]")
    p = os.path.join(site, "pick.html")
    html = open(p, encoding="utf-8").read() if os.path.exists(p) else ""
    check("pick.html 생성", bool(html))
    check("pick.html noindex 아님", 'content="noindex' not in html)
    sm = open(os.path.join(site, "sitemap.xml"), encoding="utf-8").read()
    check("sitemap.xml에 https://gamedil.com/pick.html 포함", "https://gamedil.com/pick.html" in sm, f"url {sm.count('<url>')}개")
    idx = {g["appid"]: g for g in json.load(open(os.path.join(site, "assets", "game-search-index.json"), encoding="utf-8"))}
    mism = [a for a, v in FIX.items() if a in idx and (idx[a]["price"] != (0 if v[3] else v[5]) or idx[a]["r_tot"] != v[6] + v[7])]
    check("픽스처 값이 인덱스에 의도대로 반영(오라클 점검)", not mism and all(a in idx for a in FIX), str(mism))
    return html


def browser_checks(browser, base, name_of):
    errors, dialogs = [], []
    ctx = browser.new_context(permissions=["clipboard-read", "clipboard-write"])
    page = new_page(ctx, errors, dialogs)

    print("\n[추첨]")
    page.goto(f"{base}/pick.html")
    wait_ready(page)
    check("첫 진입: 안내 문구 + 공유 버튼 숨김", "뽑아보세요" in page.inner_text("#myApp") and not page.is_visible("#btnShare"))
    first_label = page.inner_text("#btnPick")
    check("첫 진입 버튼 문구 '뽑기'(다시 없음)", "뽑기" in first_label and "다시" not in first_label, first_label)
    seen, prev, repeat, outside = {}, None, 0, []
    for _ in range(150):
        page.click("#btnPick")
        names = shown(page)
        appid = int(urlsplit(page.url).fragment.split("=", 1)[-1] or 0)
        if len(names) != 1 or name_of.get(appid) != names[0]:
            outside.append((appid, names))
            continue
        if appid not in EXPECTED:
            outside.append((appid, names))
        if appid == prev:
            repeat += 1
        seen[appid] = seen.get(appid, 0) + 1
        prev = appid
    check("150회 추첨 결과가 전부 후보 조건 충족(경계값 포함, 제외 8종 미출현)", not outside, str(outside[:3]))
    check("후보 3개 모두 한 번 이상 출현", set(seen) == EXPECTED, str(seen))
    check("연속 같은 게임 없음(다시 뽑기 중복 방지)", repeat == 0, f"{repeat}회")
    check("추첨 후 버튼 문구 '다시 뽑기'", "다시 뽑기" in page.inner_text("#btnPick"), page.inner_text("#btnPick"))
    page.evaluate("location.hash = 'appid=730108'")
    page.wait_for_timeout(400)
    check("같은 페이지 hash를 비후보로 변경 → 결과 표시 안 함", not shown(page), str(shown(page)))
    page.click("#btnPick")  # 공유 검사를 위해 정상 결과 상태로 복귀

    print("\n[공유]")
    cur = int(urlsplit(page.url).fragment.split("=", 1)[-1])
    dialogs.clear()
    page.click("#btnShare")
    page.wait_for_timeout(400)
    clip = page.evaluate("navigator.clipboard.readText()")
    check("공유 링크 = origin/pick.html#appid=현재 게임", clip == f"{base}/pick.html#appid={cur}", clip)
    check("복사 안내 표시", any("복사" in m for _, m, _ in dialogs), str(dialogs))

    print("\n[hash 진입]")
    tgt = sorted(EXPECTED)[0]
    for url in (f"{base}/pick.html#appid={tgt}",):
        page.goto(f"{base}/404.html")
        page.goto(url)
        wait_ready(page)
        check("후보 appid 링크 진입 → 그 게임 표시", shown(page) == [name_of[tgt]], str(shown(page)))
        page.reload()
        wait_ready(page)
        check("새로고침 후에도 같은 결과 유지", shown(page) == [name_of[tgt]], str(shown(page)))
    for label, h in [("성인 게임", "730107"), ("인덱스에 없는 appid", "99999999"),
                     ("숫자 아님", "abc"), ("빈 값", ""),
                     ("후보 아님: 3만원 게임", "730108"), ("후보 아님: 긍정 89%", "730102"),
                     ("후보 아님: 출시예정", "730105")]:
        page.goto(f"{base}/404.html")
        page.goto(f"{base}/pick.html#appid={h}")
        wait_ready(page)
        check(f"{label} 링크 → 결과 표시 안 함, 대기 화면", not shown(page) and "뽑아보세요" in page.inner_text("#myApp"),
              f"표시={shown(page)}")
    ctx.close()

    print("\n[클립보드 실패 폴백]")
    ctx = browser.new_context()
    ctx.add_init_script("try{Object.defineProperty(navigator,'clipboard',{value:{writeText:function(){"
                        "return Promise.reject(new Error('denied'));}},configurable:true});}catch(e){}")
    d2 = []
    page = new_page(ctx, errors, d2)
    page.goto(f"{base}/pick.html#appid={tgt}")
    wait_ready(page)
    page.click("#btnShare")
    page.wait_for_timeout(400)
    pr = [d for d in d2 if d[0] == "prompt"]
    check("writeText 거부 시 링크가 담긴 prompt", bool(pr) and pr[0][2] == f"{base}/pick.html#appid={tgt}", str(d2))
    ctx.close()

    print("\n[진입 링크/레이아웃/회귀]")
    ctx = browser.new_context()
    page = new_page(ctx, errors, [])
    page.goto(f"{base}/game/{tgt}.html")
    link = page.query_selector("a[href$='pick.html']")
    check("상세 페이지 헤더에 가챠 링크", link is not None)
    if link:
        with page.expect_navigation():
            link.click()
        check("상세 → 가챠 링크가 /pick.html로 이동", urlsplit(page.url).path == "/pick.html", page.url)
    for w, h in [(390, 844), (1440, 900)]:
        page.set_viewport_size({"width": w, "height": h})
        for path in ("index.html", f"pick.html#appid={tgt}"):
            page.goto(f"{base}/{path}")
            page.wait_for_timeout(500)
            over = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
            check(f"{w}px {path.split('#')[0]}: 가로 스크롤 없음(메뉴 추가 영향)", over <= 0, f"초과 {over}px")
        page.screenshot(path=os.path.join(TMP, f"pick_{w}.png"), full_page=True)
    check("전 흐름 JS 오류 없음", not errors, str(errors[:2]))
    ctx.close()


def copy_accuracy_check(html, base, browser):
    print("\n[문구 정확성]")
    ctx = browser.new_context()
    page = ctx.new_page()
    page.goto(f"{base}/game/730001.html")
    body = page.inner_text("body")
    ctx.close()
    claims_overwhelming = "압도적으로 긍정" in html
    check("페이지 문구가 실제 후보 기준(긍정 90%+·리뷰 50+)과 일치 — '압도적 긍정'(Steam 95%+·500+) 과장 없음",
          not claims_overwhelming,
          f"문구에 '압도적으로 긍정' 포함={claims_overwhelming}, 후보 예시 730001 상세 표기 '매우 긍정적' 포함={'매우 긍정적' in body}")


def no_candidate_checks(browser):
    print("\n[후보 0개]")
    fx = {a: v for a, v in FIX.items() if a not in EXPECTED}
    site = os.path.join(TMP, "site_empty")
    build_site(os.path.join(TMP, "empty.sqlite3"), site, fx)
    httpd, base = serve(site)
    ctx = browser.new_context()
    page = ctx.new_page()
    errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))
    page.goto(f"{base}/pick.html")
    wait_ready(page)
    page.click("#btnPick")
    page.wait_for_timeout(300)
    check("후보 0개: 안내 문구, 카드 없음, 오류 없음",
          "후보 게임이 없습니다" in page.inner_text("#myApp") and not shown(page) and not errs, page.inner_text("#myApp")[:30])
    ctx.close()
    httpd.shutdown()


def main():
    site = os.path.join(TMP, "site")
    build_site(os.path.join(TMP, "fixture.sqlite3"), site, FIX)
    html = static_checks(site)
    from playwright.sync_api import sync_playwright
    httpd, base = serve(site)
    name_of = {a: v[0] for a, v in FIX.items()}
    with sync_playwright() as p:
        b = p.chromium.launch()
        for fn in (lambda: browser_checks(b, base, name_of), lambda: copy_accuracy_check(html, base, b),
                   lambda: no_candidate_checks(b)):
            try:
                fn()
            except Exception as e:
                check("검증 구역 실행 중 예외 없음", False, repr(e)[:200])
        b.close()
    httpd.shutdown()
    print(f"\n결과: FAIL {len(FAILS)} / SKIP {len(SKIPPED)}  (산출물: {TMP})")
    for f in FAILS:
        print("  - FAIL:", f)
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
