"""GameDil 릴리스 회귀 테스트 — 독립 QA (2026-09-14 작성).

목적: Gemini 가 build.py 를 수정하는 동안/이후, 아래 세 영역이 실제로 정상 동작하는지
     '문자열 존재 검사'나 'JS 문법 검사'가 아니라 실제 동작으로 검증한다.
     운영 DB(data/steam.sqlite3)와 site/ 산출물은 절대 건드리지 않는다 — 전부 임시 경로에서 동작.

담당 범위 (3개):
  1) 404 경로 해석 — /missing, /game/missing.html, /a/b/missing/ 세 요청 경로에서
     404.html이 실제로 서빙됐다고 가정하고, CSS·favicon·홈 버튼·헤더 검색 action·
     자동완성 JSON fetch·자동완성 상세 링크가 배포 루트로 정확히 해석되는지 확인한다.
     GitHub Pages 404 폴백(요청 URL은 그대로 두고 404.html '내용'만 응답)을 재현하는
     최소 HTTP 서버 + 실제 Chromium(Playwright)으로 검증한다. 파일을 그냥 여는 것으로는
     이 문제를 재현할 수 없다(그러면 항상 파일 시스템 루트 기준으로만 해석되어 통과처럼 보인다).
  2) 자동완성 지연 응답 — fetch('assets/game-search-index.json') 응답을 Playwright route로
     붙잡아 두고, 정해진 이벤트 순서(삭제/바깥클릭/Escape/검색어 교체/IME) 뒤에 응답을
     풀어주어, 닫힌 드롭다운이 다시 열리지 않고 최신 검색만 반영되는지 실제 DOM으로 확인한다.
  3) 관측 최저가 정직성 — 29/30/59/60/120일 경계 + at_lowest 참/거짓 픽스처를 만들어
     atl_label / price_judge_summary / build_detail(상세 facts 행 · 공유 문구)가
     'Steam 전체 역사상 최저가'라고 주장하지 않는지, 관측 기간·가격차 계산이 보존되는지 확인한다.
     이건 순수 Python 함수 호출 기반이라 항상 실행된다(외부 의존성 없음).

Playwright(1·2번에 필요)가 이 실행 환경에 없으면 해당 항목은 '검증 못 함'으로 명시하고
건너뛴다 — 조용히 통과 처리하지 않는다. 3번은 항상 실행된다.

실행:
    python3 tests/test_release_regressions.py
(저장소 루트 기준 상대 경로로 build/store/config를 import한다.)
"""
import datetime as dt
import json
import os
import re
import sqlite3
import sys
import tempfile
import threading

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

TMP = tempfile.mkdtemp(prefix="gamedil_release_qa_")
FIXTURE_DB = os.path.join(TMP, "fixture.sqlite3")
SITE_DIR_LOCAL = os.path.join(TMP, "site_local")       # SITE_URL 미설정 (로컬 상대경로 빌드)
SITE_DIR_PROD = os.path.join(TMP, "site_prod")         # SITE_URL=https://gamedil.com (운영 흉내)

# store/build 는 모듈 최상단에서 config.DB_PATH / config.SITE_DIR 를 읽으므로,
# import 전에 환경변수를 먼저 세팅해야 한다 (selftest.py 와 동일한 관례).
os.environ["DB_PATH"] = FIXTURE_DB
os.environ["SITE_DIR"] = SITE_DIR_LOCAL
os.environ.setdefault("SITE_URL", "")

import config     # noqa: E402
import store      # noqa: E402
import build      # noqa: E402

FAILS = []
SKIPPED = []


def check(label, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {label}" + (f"  ({detail})" if detail else ""))
    if not cond:
        FAILS.append(label)


def skip(label, reason):
    print(f"  SKIP  {label}  — {reason}")
    SKIPPED.append((label, reason))


# ============================================================
# 픽스처 DB 생성 (store.SCHEMA 재사용 — 스키마 드리프트 방지)
# ============================================================

def build_fixture_db(db_path):
    if os.path.exists(db_path):
        os.remove(db_path)
    conn = sqlite3.connect(db_path)
    conn.executescript(store.SCHEMA)

    today = dt.date(2026, 9, 14)

    def insert_game(appid, name, **kw):
        cols = dict(
            app_type="game", tag=None, header_image="", description="", genres="인디",
            korean=1, coming_soon=0, release_text="2026년 8월 1일", release_date="2026-08-01",
            has_demo=0, demo_appid=None, is_free=0, adult=0, review_count=100,
            review_score=8, review_desc="복합적", review_positive=80, review_negative=20,
            reviews_checked_at=None, players_current=0, players_previous=0,
            players_checked_at=None, developer="QA Studio",
            screenshots="", movie_mp4="", movie_webm="", movie_poster="", media_checked_at=None,
            price_first=None, price_last=None,
            first_seen=today.isoformat(), last_seen=today.isoformat(), checked_at=today.isoformat(),
        )
        cols.update(kw)
        cols["appid"] = appid
        cols["name"] = name
        keys = list(cols.keys())
        conn.execute(f"INSERT INTO games ({','.join(keys)}) VALUES ({','.join('?' for _ in keys)})",
                     [cols[k] for k in keys])

    def insert_price_history(appid, first_day, last_day, high_price, low_price, at_lowest):
        """실제 수집 방식(가격 변동 시에만 행을 남김)과 동일하게 이력행은 최소로만 넣는다.
        at_lowest=True면 마지막 관측일 가격이 곧 최저가, False면 중간에만 저점을 찍고
        마지막엔 다시 비싸진 상태로 만든다."""
        if at_lowest:
            conn.execute("INSERT INTO prices VALUES (?,?,?,?,?)",
                         (appid, first_day.isoformat(), low_price, high_price,
                          round((1 - low_price / high_price) * 100)))
            if last_day != first_day:
                conn.execute("INSERT INTO prices VALUES (?,?,?,?,?)",
                             (appid, last_day.isoformat(), low_price, high_price,
                              round((1 - low_price / high_price) * 100)))
        else:
            mid = first_day + dt.timedelta(days=(last_day - first_day).days // 2)
            conn.execute("INSERT INTO prices VALUES (?,?,?,?,?)",
                         (appid, first_day.isoformat(), high_price, high_price, 0))
            conn.execute("INSERT INTO prices VALUES (?,?,?,?,?)",
                         (appid, mid.isoformat(), low_price, high_price,
                          round((1 - low_price / high_price) * 100)))
            conn.execute("INSERT INTO prices VALUES (?,?,?,?,?)",
                         (appid, last_day.isoformat(), high_price, high_price, 0))
        conn.execute("UPDATE games SET price_first=?, price_last=? WHERE appid=?",
                     (first_day.isoformat(), last_day.isoformat(), appid))

    # ---- 가격 정직성 경계값 매트릭스 ----
    global PRICE_MATRIX
    PRICE_MATRIX = [
        (900029, "Boundary29Low", 29, True),
        (900030, "Boundary30Low", 30, True),
        (900059, "Boundary59Low", 59, True),
        (900060, "Boundary60Atl", 60, True),
        (900120, "Boundary120AtlNotLow", 120, False),
    ]
    for appid, name, days, at_lowest in PRICE_MATRIX:
        insert_game(appid, name, is_free=0, coming_soon=0)
        first_day = today - dt.timedelta(days=days - 1)
        insert_price_history(appid, first_day, today, 10000, 8000, at_lowest)

    # ---- 검색/자동완성/404 테스트용 게임 ----
    insert_game(910001, "Autocomplete Alpha", price_first=today.isoformat(), price_last=today.isoformat())
    insert_price_history(910001, today, today, 20000, 15000, True)
    insert_game(910002, "Autocomplete Beta", price_first=today.isoformat(), price_last=today.isoformat())
    insert_price_history(910002, today, today, 5000, 5000, True)

    conn.commit()
    conn.close()


def build_site(db_path, site_dir, site_url=""):
    old_db, old_site, old_url = config.DB_PATH, config.SITE_DIR, config.SITE_URL
    config.DB_PATH, config.SITE_DIR, config.SITE_URL = db_path, site_dir, site_url
    try:
        build.main()
    finally:
        config.DB_PATH, config.SITE_DIR, config.SITE_URL = old_db, old_site, old_url


print("=" * 70)
print("0) 픽스처 준비 (임시 DB/디렉터리 — 운영 데이터 미사용)")
print("=" * 70)
build_fixture_db(FIXTURE_DB)
check("픽스처 DB 생성됨", os.path.exists(FIXTURE_DB))
build_site(FIXTURE_DB, SITE_DIR_LOCAL, site_url="")
check("로컬(SITE_URL 미설정) 사이트 빌드됨", os.path.exists(os.path.join(SITE_DIR_LOCAL, "404.html")))
build_site(FIXTURE_DB, SITE_DIR_PROD, site_url="https://gamedil.com")
check("운영(SITE_URL 설정) 사이트 빌드됨", os.path.exists(os.path.join(SITE_DIR_PROD, "404.html")))


# ============================================================
# 3) 관측 최저가 정직성 — 순수 함수 호출, 항상 실행
# ============================================================
print("\n" + "=" * 70)
print("3) 관측 최저가 정직성 (29/30/59/60/120일 경계)")
print("=" * 70)

conn = sqlite3.connect(FIXTURE_DB)
conn.row_factory = sqlite3.Row
games_by_id = {g["appid"]: g for g in store.all_games(conn)}
all_games_list = list(store.all_games(conn))

FORBIDDEN_PHRASES = ["스팀 역사상", "전체 역사상", "Steam 역사상", "역대 전체"]


def facts_row(appid):
    g = games_by_id[appid]
    html = build.build_detail(g, all_games_list, "2026-09-14", {})
    m = re.search(r'<table>(<tr>.*?)</table>', html, re.S)
    rows = re.findall(r'<tr><th>(.*?)</th><td>(.*?)</td></tr>', m.group(1))
    for k, v in rows:
        if "최저" in k or "추적" in k:
            return k, v, html
    return None, None, html


# 경계값 정확성 (29일=미만, 30일=문턱, 59일=바로 아래, 60일=문턱)
g29 = games_by_id[900029]
check("29일은 30일 미만 — days_tracked 그대로 29", g29["days_tracked"] == 29, str(g29["days_tracked"]))
check("29일 + at_lowest=True 인데도 배지 없음 (30일 미만은 표시 안 함)",
      build.atl_label(g29) == "", repr(build.atl_label(g29)))

g30 = games_by_id[900030]
check("30일 경계 — days_tracked=30", g30["days_tracked"] == 30, str(g30["days_tracked"]))
check("30일부터 'N일 최저' 배지 (아직 신뢰도 문턱 전)",
      "30일 최저" in build.atl_label(g30) and "역대" not in build.atl_label(g30),
      build.atl_label(g30))
check("30일은 atl_trustworthy 아직 False (60일 문턱 전)", g30["atl_trustworthy"] is False)

g59 = games_by_id[900059]
check("59일 — atl_trustworthy 아직 False", g59["atl_trustworthy"] is False, str(g59["days_tracked"]))
check("59일 배지에 '59일 최저' 표기, 전체역사상 주장 없음",
      "59일 최저" in build.atl_label(g59), build.atl_label(g59))

g60 = games_by_id[900060]
check("60일 경계 — atl_trustworthy True로 전환", g60["atl_trustworthy"] is True, str(g60["days_tracked"]))
check("60일 배지에 'Steam 전체 역사상' 류 주장이 없음",
      not any(p in build.atl_label(g60) for p in FORBIDDEN_PHRASES), build.atl_label(g60))

g120 = games_by_id[900120]
check("120일이지만 at_lowest=False → 배지 자체가 없음 (현재가가 최저가 아님)",
      build.atl_label(g120) == "", repr(build.atl_label(g120)))

# price_judge_summary — 상세 페이지 '가격 판단 요약' 패널
pj29 = build.price_judge_summary(g29)
check("29일: '아직 충분한 가격 이력' 경고, 최저가 주장 없음",
      "아직 충분한" in pj29 and not any(p in pj29 for p in FORBIDDEN_PHRASES), None)

pj120 = build.price_judge_summary(g120)
check("120일 + 현재가>최저가: '더 높습니다' 형태로만 표현 (최저가라고 하지 않음)",
      "높습니다" in pj120, pj120[:120])
# 가격차 계산 보존: 10000 - 8000 = 2000원, 25%
check("120일 케이스 가격차 금액 보존 (2,000원)", "2,000원" in pj120, pj120[:200])
check("120일 케이스 가격차 비율 보존 (25%)", "25%" in pj120, pj120[:200])

# facts 테이블 행 — 알려진 모호성: at_lowest=False 여도 '관측 최저가' 라벨이
# 과거 최저값과 함께 표시된다(사실 자체는 참이지만, 같은 페이지의 price_judge_summary는
# '더 높습니다'라고 말하는 것과 나란히 있어 혼동 소지가 있다). 버그로 강하게 단정하지 않고
# 정확히 무엇이 나오는지만 고정 검증한다 — 이후 문구가 조건부로 바뀌면 이 값도 같이 갱신할 것.
label120, value120, _ = facts_row(900120)
check("[참고/모호성] 120일·at_lowest=False에서도 facts 표에 최저값 행이 노출됨 "
      "(같은 페이지 price_judge_summary와 대조 필요 — 리포트 참고)",
      label120 is not None and value120 == "8,000원", (label120, value120))

# share_text — curr<=low && atl_trustworthy 일 때만 강한 주장을 붙여야 한다
_, _, html60 = facts_row(900060)
m60 = re.search(r'text:\s*"([^"]*)"', html60)
check("60일(at_lowest·atl_trustworthy 모두 True) 공유문구에 최저가 표기 포함",
      m60 is not None and ("최저가" in m60.group(1)), m60.group(1) if m60 else None)
check("60일 공유문구도 'Steam 전체 역사상' 류 주장은 아님",
      m60 is not None and not any(p in m60.group(1) for p in FORBIDDEN_PHRASES))

_, _, html120 = facts_row(900120)
m120 = re.search(r'text:\s*"([^"]*)"', html120)
check("120일이지만 at_lowest=False → 공유문구에 최저가 주장 없음",
      m120 is not None and "최저가" not in m120.group(1), m120.group(1) if m120 else None)

conn.close()


# ============================================================
# 1) & 2) Playwright 기반 실제 DOM 검증 (없으면 SKIP 명시)
# ============================================================
try:
    from playwright.sync_api import sync_playwright
    HAVE_PLAYWRIGHT = True
except ImportError:
    HAVE_PLAYWRIGHT = False

if not HAVE_PLAYWRIGHT:
    print("\n" + "=" * 70)
    print("1)/2) 404 경로 · 자동완성 지연응답 — Playwright 미설치로 실제 DOM 검증 불가")
    print("=" * 70)
    skip("404 경로 실제 DOM 해석 검증", "이 실행 환경에 playwright 모듈 없음 (pip install playwright 필요)")
    skip("자동완성 지연응답 실제 DOM 검증", "이 실행 환경에 playwright 모듈 없음")
    # ---- 구현과 독립적인 최소 대체 검증 (문자열 검사가 아니라 urljoin 기반 URL 산술) ----
    # 실제 브라우저 없이도, '이 attribute 값이 어떤 요청 경로에서든 항상 같은 절대 URL로
    # 풀리는가'는 urllib.parse.urljoin으로 검증 가능하다 — attribute 존재 여부가 아니라
    # 실제 URL 해석 결과를 비교한다는 점에서 문자열 존재 검사와는 다르다.
    from urllib.parse import urljoin
    with open(os.path.join(SITE_DIR_LOCAL, "404.html"), encoding="utf-8") as f:
        html404 = f.read()
    css_m = re.search(r'<link rel="stylesheet" href="([^"]+style\.css[^"]*)"', html404)
    logo_m = re.search(r'<a class="logo" href="([^"]+)"', html404)
    for req_path in ["http://x/missing", "http://x/game/missing.html", "http://x/a/b/missing/"]:
        css_resolved = urljoin(req_path, css_m.group(1)) if css_m else None
        logo_resolved = urljoin(req_path, logo_m.group(1)) if logo_m else None
        check(f"[urljoin 대체검증][{req_path}] CSS가 사이트 루트로 해석됨",
              css_resolved == "http://x/style.css?v=" + css_resolved.split("v=")[-1] if css_resolved else False,
              css_resolved)
        check(f"[urljoin 대체검증][{req_path}] 홈 링크가 사이트 루트로 해석됨",
              logo_resolved == "http://x/index.html", logo_resolved)
else:
    print("\n" + "=" * 70)
    print("1) 404 경로 — 실제 GitHub Pages 폴백 재현 + 실제 브라우저 DOM 검증")
    print("=" * 70)

    def make_gh_pages_handler(site_dir):
        import http.server
        class Handler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *a, **kw):
                super().__init__(*a, directory=site_dir, **kw)
            def do_GET(self):
                path = self.path.split("?")[0].split("#")[0]
                fs_path = os.path.join(site_dir, path.lstrip("/"))
                if path.endswith("/"):
                    fs_path = os.path.join(fs_path, "index.html")
                if os.path.isfile(fs_path):
                    return super().do_GET()
                data = open(os.path.join(site_dir, "404.html"), "rb").read()
                self.send_response(404)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            def log_message(self, *a, **k):
                pass
        return Handler

    def start_gh_pages_server(site_dir):
        import socketserver
        httpd = socketserver.TCPServer(("127.0.0.1", 0), make_gh_pages_handler(site_dir))
        port = httpd.server_address[1]
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        return httpd, port

    REQUEST_PATHS = ["/missing", "/game/missing.html", "/a/b/missing/"]

    def run_404_checks(site_dir, variant_label):
        httpd, port = start_gh_pages_server(site_dir)
        base = f"http://127.0.0.1:{port}"
        print(f" -- {variant_label} (root={base}) --")
        with sync_playwright() as p:
            browser = p.chromium.launch()
            for req_path in REQUEST_PATHS:
                page = browser.new_page()
                seen = []
                page.on("request", lambda r: seen.append(r.url))
                resp = page.goto(base + req_path, wait_until="networkidle")
                check(f"[{variant_label}|{req_path}] 404 상태코드", resp is not None and resp.status == 404)
                check(f"[{variant_label}|{req_path}] 404 본문 렌더됨",
                      "찾는 페이지가 없어요" in page.inner_text("body"))

                css_href = page.eval_on_selector('link[rel="stylesheet"][href*="style.css"]', 'el => el.href')
                is_external = "gamedil.com" in css_href
                check(f"[{variant_label}|{req_path}] CSS href가 배포 루트로 해석됨", "/style.css" in css_href, css_href)
                if not is_external:
                    bg = page.evaluate("getComputedStyle(document.body).backgroundColor")
                    check(f"[{variant_label}|{req_path}] CSS 실제 적용됨(빈 배경 아님)",
                          bg not in ("rgba(0, 0, 0, 0)", "rgb(0, 0, 0)", ""), bg)

                favicon_href = page.eval_on_selector('link[rel="icon"]', 'el => el.href')
                check(f"[{variant_label}|{req_path}] favicon href가 배포 루트로 해석됨",
                      favicon_href.endswith("/favicon.svg"), favicon_href)

                logo_href = page.eval_on_selector('a.logo', 'el => el.href')
                check(f"[{variant_label}|{req_path}] 홈 버튼 href가 배포 루트로 해석됨",
                      logo_href.endswith("/index.html"), logo_href)

                home_btn = page.eval_on_selector('.err-actions a.btn-p', 'el => el.href')
                check(f"[{variant_label}|{req_path}] '홈으로 돌아가기' 버튼 href 정상",
                      home_btn.endswith("/index.html"), home_btn)

                form_action = page.eval_on_selector('form.hsearch', 'el => el.action')
                check(f"[{variant_label}|{req_path}] 헤더 검색 폼 action 정상",
                      form_action.endswith("/index.html"), form_action)

                seen.clear()
                sinput = page.query_selector('form.hsearch input[name="q"]')
                check(f"[{variant_label}|{req_path}] 헤더 검색 입력창 존재", sinput is not None)
                if sinput:
                    sinput.click()
                    sinput.type("Autocomplete", delay=10)
                    page.wait_for_timeout(300)
                    json_reqs = [u for u in seen if "game-search-index.json" in u]
                    check(f"[{variant_label}|{req_path}] 자동완성 JSON fetch 발생함", len(json_reqs) > 0)
                    if json_reqs:
                        check(f"[{variant_label}|{req_path}] 자동완성 JSON fetch가 배포 루트로 해석됨",
                              json_reqs[0].endswith("/assets/game-search-index.json"), json_reqs[0])
                    try:
                        page.wait_for_selector(".ac-dropdown .ac-item", timeout=3000)
                        item_href = page.eval_on_selector(".ac-dropdown .ac-item", "el => el.href")
                        ok = (item_href.startswith(base + "/game/") if not is_external
                              else item_href.startswith("https://gamedil.com/game/"))
                        check(f"[{variant_label}|{req_path}] 자동완성 상세 링크가 배포 루트로 해석됨",
                              ok, item_href)
                    except Exception:
                        if not is_external:
                            check(f"[{variant_label}|{req_path}] 자동완성 상세 링크가 배포 루트로 해석됨",
                                  False, "드롭다운 미표시 — 로컬 서버인데도 실패(실결함)")
                        else:
                            skip(f"[{variant_label}|{req_path}] 자동완성 드롭다운 렌더 확인",
                                 "SITE_URL이 실제 gamedil.com을 가리켜 이 샌드박스 네트워크로는 "
                                 "왕복 재현 불가 (URL 자체 해석은 위에서 이미 검증됨)")
                page.close()
            browser.close()
        httpd.shutdown()

    run_404_checks(SITE_DIR_LOCAL, "SITE_URL 미설정")
    run_404_checks(SITE_DIR_PROD, "SITE_URL=https://gamedil.com")

    print("\n" + "=" * 70)
    print("2) 자동완성 지연 응답 — 실제 DOM + 네트워크 제어")
    print("=" * 70)

    def dropdown_state(page):
        return page.evaluate("""() => {
            var d = document.querySelector('.ac-dropdown');
            if (!d) return {exists:false};
            return {exists:true, visible: d.style.display !== 'none', items: d.querySelectorAll('.ac-item').length};
        }""")

    def setup_held_fetch(page):
        box = {"route": None}
        page.route("**/assets/game-search-index.json", lambda route: box.__setitem__("route", route))
        def release(json_path):
            r = box["route"]
            with open(json_path, "rb") as f:
                body = f.read()
            r.fulfill(status=200, content_type="application/json", body=body)
        return release

    json_path = os.path.join(SITE_DIR_LOCAL, "assets", "game-search-index.json")
    httpd, port = start_gh_pages_server(SITE_DIR_LOCAL)
    base = f"http://127.0.0.1:{port}"

    with sync_playwright() as p:
        browser = p.chromium.launch()

        page = browser.new_page()
        page.goto(base + "/index.html")
        release = setup_held_fetch(page)
        inp = page.query_selector('form.hsearch input[name="q"]')
        inp.click(); inp.type("Auto", delay=5)
        page.wait_for_timeout(150)
        inp.fill(""); inp.dispatch_event("input")
        page.wait_for_timeout(50)
        release(json_path)
        page.wait_for_timeout(300)
        check("[전부삭제→응답도착] 드롭다운이 다시 열리지 않음", not dropdown_state(page)["visible"])
        page.close()

        page = browser.new_page()
        page.goto(base + "/index.html")
        release = setup_held_fetch(page)
        inp = page.query_selector('form.hsearch input[name="q"]')
        inp.click(); inp.type("Auto", delay=5)
        page.wait_for_timeout(150)
        page.mouse.click(5, 5)
        page.wait_for_timeout(50)
        release(json_path)
        page.wait_for_timeout(300)
        check("[바깥클릭→응답도착] 드롭다운이 다시 열리지 않음", not dropdown_state(page)["visible"])
        page.close()

        # Escape: 신뢰된 실제 입력 vs 합성(비신뢰) dispatchEvent — 후자가 앱 자체 로직만 검증한다.
        # Chromium은 type="search" 입력에 신뢰된 Escape가 오면 네이티브로 값을 지우는데,
        # 그게 우연히 input 이벤트를 내어 search('')->close() 를 태우고 실제 결함을 가린다.
        for variant, synthetic in [("실제키입력", False), ("합성dispatchEvent(네이티브우회)", True)]:
            page = browser.new_page()
            page.goto(base + "/index.html")
            release = setup_held_fetch(page)
            inp = page.query_selector('form.hsearch input[name="q"]')
            inp.click(); inp.type("Auto", delay=5)
            page.wait_for_timeout(150)
            if synthetic:
                page.evaluate("""() => {
                    var el = document.querySelector('form.hsearch input[name="q"]');
                    el.dispatchEvent(new KeyboardEvent('keydown', {key:'Escape', bubbles:true, cancelable:true}));
                }""")
            else:
                inp.press("Escape")
            page.wait_for_timeout(50)
            release(json_path)
            page.wait_for_timeout(300)
            st = dropdown_state(page)
            check(f"[Escape({variant})→응답도착] 드롭다운이 다시 열리지 않음", not st["visible"], st)
            page.close()

        page = browser.new_page()
        page.goto(base + "/index.html")
        release = setup_held_fetch(page)
        inp = page.query_selector('form.hsearch input[name="q"]')
        inp.click(); inp.type("Alpha", delay=5)
        page.wait_for_timeout(80)
        inp.fill(""); inp.type("Beta", delay=5)
        page.wait_for_timeout(80)
        release(json_path)
        page.wait_for_timeout(300)
        names = page.eval_on_selector_all(".ac-item .ac-name", "els => els.map(e => e.textContent)")
        check("[검색어A→B→응답도착] 최신 검색어(B) 결과만 반영됨", names == ["Autocomplete Beta"], names)
        page.close()

        page = browser.new_page()
        page.goto(base + "/index.html")
        inp = page.query_selector('form.hsearch input[name="q"]')
        inp.click(); inp.type("Auto", delay=5)
        page.wait_for_selector(".ac-dropdown .ac-item", timeout=3000)
        page.keyboard.press("ArrowDown")
        url_before = page.url
        page.evaluate("""() => {
            var el = document.querySelector('form.hsearch input[name="q"]');
            el.dispatchEvent(new CompositionEvent('compositionstart'));
            var ev = new KeyboardEvent('keydown', {key:'Enter', bubbles:true, cancelable:true});
            Object.defineProperty(ev, 'isComposing', {value:true});
            el.dispatchEvent(ev);
        }""")
        page.wait_for_timeout(200)
        check("[IME 조합 중 Enter] 페이지 이동(제안 클릭) 발생 안 함", page.url == url_before,
              f"{url_before} -> {page.url}")
        page.close()

        browser.close()
    httpd.shutdown()


print("\n" + "=" * 70)
print(f"결과: 실패 {len(FAILS)}건 / 스킵 {len(SKIPPED)}건")
print("=" * 70)
if FAILS:
    print("실패 목록:")
    for f in FAILS:
        print("  -", f)
if SKIPPED:
    print("스킵 목록(검증 못 함 — 미통과로 세지 않았을 뿐 커버리지 공백임):")
    for label, reason in SKIPPED:
        print(f"  - {label}: {reason}")

sys.exit(1 if FAILS else 0)
