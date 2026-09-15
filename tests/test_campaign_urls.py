"""첫 홍보 캠페인(UTM 링크) 대응 - Claude 담당 검증.

HANDOFF.md 지시에 따라, Gemini가 수정한 build.py의 updateQuery() 로직이
- 검색 입력
- 검색어 지우기(결과 없음 버튼)
- 필터 초기화(resetBtn)
- 구형 #q= 해시 → 쿼리 전환
네 시나리오에서 기존 UTM 파라미터(utm_source/medium/campaign/content)를 실제로
보존하는지, build.py를 복사한 별도 함수가 아니라 build.main()이 생성한 실제
site/index.html + 실제 클라이언트 JS를 로컬 서버로 띄워 Playwright 실제 DOM으로
확인한다.

Playwright가 없는 환경에서는 이 부분을 SKIP으로 명시하고 죽지 않는다
(문자열 검사로 대체 판정하지 않는다).

임시 DB·임시 SITE_DIR만 사용한다. 운영 DB·운영 site/ 는 건드리지 않는다.
"""
import http.server
import os
import socketserver
import sqlite3
import sys
import tempfile
import threading
from urllib.parse import urlsplit, parse_qs

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

TMP = tempfile.mkdtemp(prefix="gamedil_utm_qa_")
DB_PATH = os.path.join(TMP, "fixture.sqlite3")
SITE_DIR = os.path.join(TMP, "site")
os.environ["DB_PATH"] = DB_PATH
os.environ["SITE_DIR"] = SITE_DIR

import config  # noqa: E402
import store  # noqa: E402
import build  # noqa: E402

FAILS = []
SKIPPED = []


def check(label, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {label}" + (f"  ({detail})" if detail else ""))
    if not cond:
        FAILS.append(label)


def skip(label, reason):
    print(f"  SKIP  {label}  — {reason}")
    SKIPPED.append((label, reason))


def build_fixture_site():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(store.SCHEMA)
    cols_games = [r[1] for r in conn.execute("PRAGMA table_info(games)")]
    defaults = {
        "korean": 1, "adult": 0, "is_free": 0,
        "price_first": "2026-08-01", "price_last": "2026-09-01",
        "review_count": 500, "review_score": 8, "review_positive": 450,
        "review_negative": 50,
        "first_seen": "2026-08-01", "last_seen": "2026-09-01",
        "checked_at": "2026-09-01",
    }

    def insert_game(appid, name):
        row = {"appid": appid, "name": name}
        for c in cols_games:
            if c in ("appid", "name"):
                continue
            if c in defaults:
                row[c] = defaults[c]
        cols = list(row.keys())
        conn.execute(
            f"INSERT INTO games ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})",
            [row[c] for c in cols],
        )
        for d in ("2026-08-01", "2026-09-01"):
            conn.execute(
                "INSERT INTO prices (appid, on_date, price_final, price_initial, discount_pct) "
                "VALUES (?, ?, 10000, 10000, 0)", (appid, d))

    insert_game(700001, "Zelda-like Adventure")
    insert_game(700002, "Another Quest")
    conn.commit()
    conn.close()
    build.main()
    return SITE_DIR


UTM = "utm_source=live_channel&utm_medium=referral&utm_campaign=gamedil_first_play&utm_content=pinned_chat"


def utm_intact(url):
    qs = parse_qs(urlsplit(url).query)
    return (qs.get("utm_source") == ["live_channel"] and
            qs.get("utm_medium") == ["referral"] and
            qs.get("utm_campaign") == ["gamedil_first_play"] and
            qs.get("utm_content") == ["pinned_chat"])


def start_server(site_dir):
    handler = lambda *a, **kw: http.server.SimpleHTTPRequestHandler(*a, directory=site_dir, **kw)
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd, port


def run_playwright_checks(site_dir):
    from playwright.sync_api import sync_playwright

    httpd, port = start_server(site_dir)
    base = f"http://127.0.0.1:{port}"
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()

            page = browser.new_page()
            page.goto(f"{base}/index.html?q=zelda&{UTM}")
            page.wait_for_timeout(300)
            check("[최초진입 q+UTM] URL의 UTM 보존", utm_intact(page.url), page.url)
            val = page.eval_on_selector('form.hsearch input[name="q"]', "el => el.value")
            check("[최초진입 q+UTM] 검색창에 q 값 반영", val == "zelda", val)
            page.close()

            page = browser.new_page()
            page.goto(f"{base}/index.html?{UTM}")
            page.wait_for_timeout(200)
            inp = page.query_selector('form.hsearch input[name="q"]')
            inp.click()
            inp.type("Zelda", delay=10)
            page.wait_for_timeout(200)
            check("[검색 입력] UTM 보존", utm_intact(page.url), page.url)
            check("[검색 입력] q 파라미터 반영", "q=Zelda" in page.url, page.url)
            page.close()

            page = browser.new_page()
            page.goto(f"{base}/index.html?{UTM}")
            page.wait_for_timeout(200)
            inp = page.query_selector('form.hsearch input[name="q"]')
            inp.click()
            inp.type("존재하지않는게임쿼리", delay=10)
            page.wait_for_timeout(200)
            clear_btn = page.query_selector("#noneMsg button")
            check("[검색어 지우기] 버튼 노출됨", clear_btn is not None)
            if clear_btn:
                clear_btn.click()
                page.wait_for_timeout(200)
                check("[검색어 지우기] UTM 보존", utm_intact(page.url), page.url)
                check("[검색어 지우기] q 제거됨", "q=" not in urlsplit(page.url).query, page.url)
            page.close()

            page = browser.new_page()
            page.goto(f"{base}/index.html?q=zelda&{UTM}")
            page.wait_for_timeout(300)
            reset_btn = page.query_selector("#resetBtn")
            check("[필터 초기화] resetBtn 존재", reset_btn is not None)
            if reset_btn:
                page.evaluate("document.getElementById('resetBtn').style.display='inline-block'")
                reset_btn.click()
                page.wait_for_timeout(200)
                check("[필터 초기화] UTM 보존", utm_intact(page.url), page.url)
                check("[필터 초기화] q 제거됨", "q=" not in urlsplit(page.url).query, page.url)
            page.close()

            page = browser.new_page()
            page.goto(f"{base}/index.html?{UTM}#q=zelda")
            page.wait_for_timeout(300)
            check("[구형 #q= 전환] UTM 보존", utm_intact(page.url), page.url)
            check("[구형 #q= 전환] q가 쿼리로 이전됨", "q=zelda" in page.url, page.url)
            check("[구형 #q= 전환] 해시 제거됨", urlsplit(page.url).fragment == "", page.url)
            page.close()

            browser.close()
    finally:
        httpd.shutdown()


def main():
    print("0) 픽스처 DB + 실제 build.main() 로 사이트 생성")
    site_dir = build_fixture_site()
    assert os.path.exists(os.path.join(site_dir, "index.html"))

    print("\n1) UTM 보존 - 실제 생성 JS + 실제 DOM (Playwright)")
    try:
        import playwright  # noqa: F401
        run_playwright_checks(site_dir)
    except ImportError:
        skip("UTM 보존 DOM 검증 4개 시나리오",
             "이 실행 환경에 playwright 미설치 — 코드 정적 검토(HANDOFF/보고서)로만 대체되며 "
             "동작 검증이 아니므로 커버리지 공백으로 남긴다")

    print(f"\n결과: 실패 {len(FAILS)}건 / 스킵 {len(SKIPPED)}건")
    for f in FAILS:
        print("  FAIL -", f)
    for label, reason in SKIPPED:
        print("  SKIP -", label, "—", reason)
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
