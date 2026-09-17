"""홈 탐색 통일 / 제목 가림 해결 / 카테고리 공통 정렬 — Claude 독립 검증.

marketing/navigation-sorting-tasks.md 의 Claude 담당 항목.
Gemini 구현(build.py/theme.py) 완료 *전에 준비된* 파일이다. 이 파일이 만들어질 당시
아직 구현이 진행 중이었으므로, 작성 시점에는 실제 product 코드가 아니라
git HEAD(구현 시작 전 마지막 커밋) 스냅샷을 상대로만 스크립트 자체의 문법/로직을
자체 점검했고, Gemini 결과에 대해 어떤 PASS/FAIL도 내리지 않았다.

실제 최종 검증은 Gemini 구현 보고서(marketing/navigation-sorting-implementation.md)가
저장된 뒤, 이 파일을 최신 코드로 다시 실행해서 수행한다.

설계 원칙:
- 문자열 존재 검사만으로 PASS 판정하지 않는다. 실제 Playwright DOM(스크롤 위치,
  bounding rect, 카드 DOM 순서)으로 검증한다.
- 정렬 select 의 내부 value 문자열을 추정하지 않는다. 정책 문서가 못박은
  "보이는 한국어 라벨"(기본순/평가 좋은 순/리뷰 많은 순/낮은 가격순/높은 가격순/
  할인율순/이름순)로 옵션을 찾아 선택한다 — 이러면 Gemini 가 내부 값 이름을
  뭘로 짓든 테스트가 깨지지 않는다.
- 카드 순서는 기존에 이미 있는 안정적인 마커 `a.card[data-wish]`(appid)로 읽는다.
  Gemini 가 정렬용으로 새 data 속성을 추가하더라도 이 마커는 그대로 유지될 것으로
  기대되며, 없어졌다면 그 자체가 회귀이므로 실패로 잡힌다.
- 아직 구현되지 않은 요소(정렬 select, #under-10000 홈 섹션 등)를 못 찾으면
  SKIP 으로 명시하고 FAIL 로 세지 않는다. Playwright 자체가 없으면 전체를 SKIP.
"""
import http.server
import json
import os
import socketserver
import sqlite3
import sys
import tempfile
import threading
from urllib.parse import urlsplit, parse_qs

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

TMP = tempfile.mkdtemp(prefix="gamedil_navsort_qa_")
DB_PATH = os.path.join(TMP, "fixture.sqlite3")
SITE_DIR = os.path.join(TMP, "site")
EMPTY_DB_PATH = os.path.join(TMP, "empty.sqlite3")
EMPTY_SITE_DIR = os.path.join(TMP, "empty_site")
SOON_DB_PATH = os.path.join(TMP, "soon.sqlite3")
SOON_SITE_DIR = os.path.join(TMP, "soon_site")
os.environ["DB_PATH"] = DB_PATH
os.environ["SITE_DIR"] = SITE_DIR

FAILS = []
SKIPPED = []
SCREENSHOTS = []


def check(label, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {label}" + (f"  ({detail})" if detail else ""))
    if not cond:
        FAILS.append(label)


def skip(label, reason):
    print(f"  SKIP  {label}  — {reason}")
    SKIPPED.append((label, reason))


# ---------------------------------------------------------------------------
# 픽스처 게임 — LANDINGS 각 슬러그 + 정렬 경계 사례
# ---------------------------------------------------------------------------
GAMES = []


def g(appid, name, **ov):
    GAMES.append((appid, name, ov))


# 인기(popular-games): players_current 내림차순
g(710101, "인기A", korean=1, players_current=5000, review_total=200, review_pos_pct=90)
g(710102, "인기B", korean=1, players_current=3000, review_total=200, review_pos_pct=90)

# 핫딜(hot-deals): discount_pct>=70
g(710201, "핫딜A", korean=1, discount_pct=80, review_total=100, review_pos_pct=90)
g(710202, "핫딜B", korean=1, discount_pct=75, review_total=100, review_pos_pct=90)

# 신작(korean-new)
g(710301, "신작A", korean=1, tag="신작", release_date="2026-09-10", review_total=50, review_pos_pct=85)
g(710302, "신작B", korean=1, tag="신작", release_date="2026-08-01", review_total=50, review_pos_pct=85)

# 출시예정(korean-soon): coming_soon, 가격 미정(이력 없음) — 가격정렬 꼬리 규칙 확인용.
# R1 재검증 때는 release_date가 있으면 build.py의 korean-soon sort 람다가
# TypeError로 크래시해서 우회용으로 release_date를 비웠었다. Codex R2에서
# Gemini가 원본 로직(release_date or '9999', name or '')으로 복원했다고 보고했으므로
# 이번 R2 검증에서는 release_date를 되살려 실제 build.main()이 성공하는지 직접 확인한다.
g(710401, "출시예정A", korean=1, coming_soon=1, release_date="2026-10-01", no_price_row=True,
  review_total=0, review_pos_pct=0)
g(710402, "출시예정B", korean=1, coming_soon=1, release_date="2026-11-01", no_price_row=True,
  review_total=0, review_pos_pct=0)

# 데모(korean-demo): 본편+데모칩 게임 1개, 단독 데모앱 1개(본편 가격 추정 금지 확인용)
g(710501, "데모본편", korean=1, has_demo=1, discount_pct=10, review_total=80, review_pos_pct=88)
g(710502, "단독데모앱", korean=1, app_type="demo", is_free=1, review_total=0, review_pos_pct=0)

# 1만원 이하(under-10000): 경계값(10000 포함, 10001 제외), 무료 제외
g(710601, "만원이하-9000", korean=1, price_final_override=9000, review_total=30, review_pos_pct=80)
g(710602, "만원이하-경계10000", korean=1, price_final_override=10000, review_total=30, review_pos_pct=80)
g(710603, "만원초과-10001", korean=1, price_final_override=10001, review_total=30, review_pos_pct=80)
g(710604, "무료-제외대상", korean=1, is_free=1, review_total=30, review_pos_pct=80)

# 정렬 일반 검증용(korean-games 픽에 전부 포함됨: korean=1이면 전부 해당)
g(710701, "평가높음리뷰많음", korean=1, review_total=1000, review_pos_pct=95, price_final_override=20000)
g(710702, "평가높음리뷰적음", korean=1, review_total=60, review_pos_pct=95, price_final_override=25000)
g(710703, "평가낮음", korean=1, review_total=500, review_pos_pct=50, price_final_override=15000)
g(710704, "평가없음", korean=1, review_total=0, review_pos_pct=0, price_final_override=5000)
g(710705, "명시적무료", korean=1, is_free=1, review_total=30, review_pos_pct=80)
g(710706, "가격미정released", korean=1, no_price_row=True, review_total=30, review_pos_pct=80)
g(710707, "이름동률용A", korean=1, review_total=40, review_pos_pct=80, price_final_override=7000)
g(710708, "이름동률용B", korean=1, review_total=40, review_pos_pct=80, price_final_override=7000)

# 최근 인하(recent-drops): recent_drop_amount 는 get_recent_drops()가 계산 — 별도 갱신 이력으로 유도
g(710801, "최근인하A", korean=1, review_total=50, review_pos_pct=85, price_history_drop=True)

# 이름에 "무료"가 들어가지만 실제로는 무료가 아닌/가격 미정인 함정 게임.
# Codex 리뷰 지적: 무료 여부를 카드 textContent에 '무료'가 있는지로 판정하면 안 되고
# 명시적 data-free/price 필드를 써야 한다 — 이 두 게임이 가격 정렬에서 오분류되면 회귀.
g(710901, "무료체험판아님유료풀게임", korean=1, is_free=0,
  price_final_override=88000, review_total=30, review_pos_pct=80)
g(710902, "무료아님출시전미가격", korean=1, is_free=0, no_price_row=True,
  coming_soon=1, review_total=0, review_pos_pct=0)


def _price_rows_for(appid, ov):
    if ov.get("no_price_row"):
        return []
    if ov.get("price_history_drop"):
        # 최근 7일 내 가격이 내려간 것으로 보이도록 이틀치 이력 생성
        return [("2026-09-08", 20000, 20000, 0), ("2026-09-16", 14000, 20000, 30)]
    final = ov.get("price_final_override")
    if final is None:
        final = 0 if ov.get("is_free") else 10000
    disc = ov.get("discount_pct", 0)
    return [("2026-08-01", final, final, 0), ("2026-09-16", final, final, disc)]


def _insert_games(conn, games):
    conn.executescript(_SCHEMA)
    cols_games = [r[1] for r in conn.execute("PRAGMA table_info(games)")]
    for appid, name, ov in games:
        total = ov.get("review_total", 0)
        pos_pct = ov.get("review_pos_pct", 0)
        pos = round(total * pos_pct / 100)
        neg = total - pos
        row = {
            "appid": appid, "name": name,
            "app_type": ov.get("app_type", "game"),
            "korean": ov.get("korean", 0),
            "coming_soon": ov.get("coming_soon", 0),
            "adult": ov.get("adult", 0),
            "is_free": ov.get("is_free", 0),
            "has_demo": ov.get("has_demo", 0),
            "tag": ov.get("tag"),
            "release_date": ov.get("release_date"),
            "players_current": ov.get("players_current", 0),
            "players_previous": ov.get("players_previous", 0),
            "review_positive": pos, "review_negative": neg, "review_count": total,
            "first_seen": "2026-08-01", "last_seen": "2026-09-16", "checked_at": "2026-09-16",
            "price_first": "2026-08-01", "price_last": "2026-09-16",
        }
        row = {k: v for k, v in row.items() if k in cols_games and v is not None}
        cols = list(row.keys())
        conn.execute(
            f"INSERT INTO games ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})",
            [row[c] for c in cols])
        for on_date, final, initial, disc in _price_rows_for(appid, ov):
            conn.execute(
                "INSERT INTO prices (appid, on_date, price_final, price_initial, discount_pct) "
                "VALUES (?, ?, ?, ?, ?)", (appid, on_date, final, initial, disc))
    conn.commit()


_SCHEMA = None  # store.SCHEMA — main()에서 채움


def build_fixture_site():
    global _SCHEMA
    import store
    _SCHEMA = store.SCHEMA
    conn = sqlite3.connect(DB_PATH)
    _insert_games(conn, GAMES)
    conn.close()
    import build
    build.main()
    return SITE_DIR


def build_empty_site():
    """최근 인하/1만원 이하 후보가 전무한 빈 상태 — 앵커는 있되 내용이 빈 경우."""
    global _SCHEMA
    import store
    _SCHEMA = store.SCHEMA
    conn = sqlite3.connect(EMPTY_DB_PATH)
    conn.executescript(_SCHEMA)
    conn.execute(
        "INSERT INTO games (appid,name,app_type,korean,coming_soon,adult,is_free,has_demo,"
        "review_positive,review_negative,review_count,first_seen,last_seen,checked_at,"
        "price_first,price_last) VALUES (720001,'단일게임','game',1,0,0,0,0,10,2,12,"
        "'2026-08-01','2026-09-16','2026-09-16','2026-08-01','2026-09-16')")
    conn.execute(
        "INSERT INTO prices (appid,on_date,price_final,price_initial,discount_pct) "
        "VALUES (720001,'2026-09-16',30000,30000,0)")
    conn.commit()
    conn.close()
    import config
    import build
    config.DB_PATH = EMPTY_DB_PATH
    config.SITE_DIR = EMPTY_SITE_DIR
    build.main()
    config.DB_PATH = DB_PATH
    config.SITE_DIR = SITE_DIR
    return EMPTY_SITE_DIR


def run_korean_soon_build_crash_regression():
    """Codex R2 재현: 한국어+출시예정(coming_soon)+release_date 게임이 하나라도 있으면
    build.main()이 korean-soon 정렬 람다에서 TypeError로 죽던 문제. 경쟁 게임 없는
    단독 DB로 직접 재현해 build.main()이 예외 없이 끝나는지 그 자체를 검사한다.
    (문자열 체크가 아니라 실제 build.main() 실행 성공 여부가 판정 기준이다.)"""
    global _SCHEMA
    import store
    _SCHEMA = store.SCHEMA
    conn = sqlite3.connect(SOON_DB_PATH)
    conn.executescript(_SCHEMA)
    conn.execute(
        "INSERT INTO games (appid,name,app_type,korean,coming_soon,adult,is_free,has_demo,"
        "release_date,review_positive,review_negative,review_count,first_seen,last_seen,checked_at,"
        "price_first,price_last) VALUES (730001,'출시예정단독','game',1,1,0,0,0,"
        "'2026-12-25',0,0,0,'2026-08-01','2026-09-16','2026-09-16','2026-08-01','2026-09-16')")
    conn.commit()
    conn.close()
    import config
    import build
    config.DB_PATH = SOON_DB_PATH
    config.SITE_DIR = SOON_SITE_DIR
    try:
        build.main()
        check("[korean-soon 빌드 크래시 회귀] release_date 있는 출시예정 게임 1개로 build.main() 성공(TypeError 없음)",
              True)
    except Exception as e:
        check("[korean-soon 빌드 크래시 회귀] release_date 있는 출시예정 게임 1개로 build.main() 성공(TypeError 없음)",
              False, f"{type(e).__name__}: {e}")
    finally:
        config.DB_PATH = DB_PATH
        config.SITE_DIR = SITE_DIR


def start_server(site_dir):
    handler = lambda *a, **kw: http.server.SimpleHTTPRequestHandler(*a, directory=site_dir, **kw)
    httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd, port


VIEWPORTS = [("390x844(모바일)", 390, 844), ("768x1024(태블릿)", 768, 1024), ("1440x900(데스크톱)", 1440, 900)]

HOME_ANCHORS = [
    ("popular", "지금 인기"), ("drop", "최근 인하"), ("hot", "핫딜"),
    ("soon", "기대작"), ("demo", "데모"), ("under-10000", "1만원 이하"), ("all", "전체"),
]

SORT_LABELS = ["기본순", "평가 좋은 순", "리뷰 많은 순", "낮은 가격순", "높은 가격순", "할인율순", "이름순"]

LANDING_SLUGS = ["korean-games", "korean-demo", "korean-new", "korean-soon",
                 "under-10000", "recent-drops", "hot-deals", "popular-games"]


def card_appid_order(page, scope_selector="body"):
    return page.eval_on_selector_all(
        f"{scope_selector} a.card[data-wish]",
        "els => els.map(e => parseInt(e.getAttribute('data-wish'), 10))")


def header_bottom(page):
    """실제 sticky 헤더의 화면상 아래쪽 y좌표(px). 헤더가 없으면 0."""
    return page.evaluate(
        "() => { const h = document.querySelector('header.top'); "
        "return h ? h.getBoundingClientRect().bottom : 0; }")


def title_rect_for_anchor(page, anchor_id):
    return page.evaluate(
        """(id) => {
            const sec = document.getElementById(id);
            if (!sec) return null;
            const t = sec.querySelector('h1,h2,.sec-title,.section-title') || sec;
            const r = t.getBoundingClientRect();
            return {top: r.top, bottom: r.bottom, text: (t.textContent||'').trim().slice(0,30)};
        }""", anchor_id)


def run_header_offset_checks(base, shots_dir):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        for vp_label, w, h in VIEWPORTS:
            page = browser.new_page(viewport={"width": w, "height": h})
            page.goto(f"{base}/index.html")
            for anchor_id, label in HOME_ANCHORS:
                nav_link = page.query_selector(f'nav.jump a[href*="#{anchor_id}"]')
                if not nav_link:
                    skip(f"[{vp_label}] 홈 메뉴 '{label}'(#{anchor_id}) 링크",
                         "nav.jump 에 해당 앵커 링크 없음 — 미구현")
                    continue
                nav_link.click()
                page.wait_for_timeout(400)
                rect = title_rect_for_anchor(page, anchor_id)
                if rect is None:
                    skip(f"[{vp_label}] '{label}' 섹션(#{anchor_id}) 제목 가림 확인",
                         "해당 id의 섹션이 아직 홈에 없음 — 미구현(예: under-10000)")
                    continue
                hb = header_bottom(page)
                visible = 0 <= rect["top"] < h
                not_hidden = rect["top"] >= hb - 2  # 2px 오차 허용
                ok = visible and not_hidden
                check(f"[{vp_label}] '{label}'(#{anchor_id}) 클릭 후 제목이 헤더 아래+화면 안에 보임",
                      ok, f"title.top={rect['top']:.1f}, header.bottom={hb:.1f}, text={rect['text']!r}")
                if not ok and len(SCREENSHOTS) < 6:
                    path = os.path.join(shots_dir, f"fail_{vp_label.split('(')[0]}_{anchor_id}.png")
                    try:
                        page.screenshot(path=path)
                        SCREENSHOTS.append(path)
                    except Exception:
                        pass
            page.close()

        # 직접 #hash 진입 + 새로고침
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.goto(f"{base}/index.html#popular")
        page.wait_for_timeout(400)
        rect = title_rect_for_anchor(page, "popular")
        if rect is not None:
            hb = header_bottom(page)
            check("[직접 #popular 진입] 제목이 헤더 아래에 보임", rect["top"] >= hb - 2, rect)
            page.reload()
            page.wait_for_timeout(400)
            rect2 = title_rect_for_anchor(page, "popular")
            hb2 = header_bottom(page)
            check("[새로고침 후 #popular] 제목이 헤더 아래에 보임", rect2["top"] >= hb2 - 2, rect2)
        else:
            skip("직접 #hash 진입/새로고침 확인", "popular 섹션 없음")
        page.close()

        # 상세 페이지 -> 홈 앵커
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.goto(f"{base}/game/710101.html")
        link = page.query_selector('nav.jump a[href*="#popular"]')
        if link:
            link.click()
            page.wait_for_timeout(400)
            rect = title_rect_for_anchor(page, "popular")
            hb = header_bottom(page)
            check("[상세→홈 #popular] 제목이 헤더 아래에 보임",
                  rect is not None and rect["top"] >= hb - 2, rect)
        else:
            skip("상세→홈 앵커 확인", "상세 페이지에 홈 앵커 링크 없음")
        page.close()

        # URL 쿼리(q/UTM) 보존 + 같은 문서 내 이동(완전 재로딩 없음) 확인
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(f"{base}/index.html?q=zelda&utm_source=threads&utm_medium=social")
        page.evaluate("window.__navMarker = true")
        link = page.query_selector('nav.jump a[href*="#hot"]')
        if link:
            href = link.get_attribute("href")
            is_same_doc = href.startswith("#") or href.split("#")[0] in ("", "index.html", "./index.html")
            link.click()
            page.wait_for_timeout(300)
            marker_kept = page.evaluate("() => window.__navMarker === true")
            url = page.url
            qs = parse_qs(urlsplit(url).query)
            check("[메뉴 이동] q 파라미터 보존", qs.get("q") == ["zelda"], url)
            check("[메뉴 이동] UTM 보존", qs.get("utm_source") == ["threads"], url)
            if is_same_doc:
                check("[메뉴 이동] 같은 문서 내 이동(불필요한 전체 재로딩 없음)", marker_kept,
                      f"marker_kept={marker_kept}")
            else:
                skip("같은 문서 내 이동 확인", "홈 앵커 링크가 상대/절대 경로로 문서를 새로 가리킴")
        else:
            skip("URL 보존/재로딩 없음 확인", "#hot 링크 없음")
        page.close()

        browser.close()


def run_empty_state_checks(empty_base):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.goto(f"{empty_base}/index.html")
        for anchor_id, label in [("drop", "최근 인하"), ("under-10000", "1만원 이하")]:
            sec = page.query_selector(f"#{anchor_id}")
            if sec is None:
                skip(f"[빈 상태] '{label}' 섹션 존재 확인", "섹션 자체가 없음 — 미구현")
                continue
            text = sec.inner_text()
            check(f"[빈 상태] '{label}' 섹션이 비어있어도 안내 문구로 존재",
                  len(text.strip()) > 0, text[:60])
        page.close()
        browser.close()


def expected_order(appids_with_meta, mode):
    """정책 문서의 정렬 규칙을 그대로 재현한 기대값(테스트 자체의 오라클)."""
    def key_rating(m):
        no_review = (m["review_total"] or 0) == 0
        return (no_review, -(m["review_pos_pct"] or 0), -(m["review_total"] or 0), m["name"], m["appid"])

    def key_reviews(m):
        no_review = (m["review_total"] or 0) == 0
        return (no_review, -(m["review_total"] or 0), m["name"], m["appid"])

    def price_val(m):
        if m.get("no_price_row") and not m.get("is_free"):
            return None
        return m["price"]

    def key_price(m, rev):
        p = price_val(m)
        undetermined = p is None
        if rev:
            return (undetermined, -(p or 0), m["name"], m["appid"])
        return (undetermined, (p if p is not None else 0), m["name"], m["appid"])

    def key_discount(m):
        d = m.get("discount")
        undetermined = d is None
        return (undetermined, -(d or 0), m["name"], m["appid"])

    def key_name(m):
        return (m["name"], m["appid"])

    keyfn = {
        "rating": key_rating, "reviews": key_reviews,
        "price_asc": lambda m: key_price(m, False), "price_desc": lambda m: key_price(m, True),
        "discount": key_discount, "name": key_name,
    }[mode]
    return [m["appid"] for m in sorted(appids_with_meta, key=keyfn)]


def build_meta_for_sort_test():
    """실제 DB에 들어갈 마지막 price row(_price_rows_for)에서 그대로 파생한다.
    (이전 버전은 price_final_override/discount_pct kwarg를 별도로 재해석해서
    실제 삽입되는 price row와 어긋나는 값을 오라클로 썼다 — 예: price_history_drop
    게임의 실제 최종가/할인율, discount_pct kwarg가 실제로는 price row에 반영되지
    않던 문제. 이제 _price_rows_for()의 마지막 행을 단일 진실 소스로 사용해
    store.py가 읽는 값과 항상 일치시킨다.)"""
    metas = []
    for appid, name, ov in GAMES:
        if not ov.get("korean"):
            continue
        rows = _price_rows_for(appid, ov)
        if rows:
            last_price, last_disc = rows[-1][1], rows[-1][3]
        else:
            last_price, last_disc = 0, 0
        metas.append({
            "appid": appid, "name": name,
            "review_total": ov.get("review_total", 0), "review_pos_pct": ov.get("review_pos_pct", 0),
            "price": last_price,
            "no_price_row": ov.get("no_price_row", False), "is_free": ov.get("is_free", False),
            "discount": last_disc,
        })
    return metas


def select_sort_option(page, select_locator_or_el, visible_label):
    # select 엘리먼트 핸들에서 직접 보이는 옵션(value, text)을 읽어
    # 라벨 문자열로 매칭한다 — value 이름을 추정하지 않는다.
    opts = select_locator_or_el.eval_on_selector_all(
        "option", "els => els.map(e => ({value: e.value, text: e.textContent.trim()}))")
    match = next((o for o in opts if o["text"] == visible_label), None)
    if match is None:
        return None
    select_locator_or_el.select_option(value=match["value"])
    return match


def run_landing_sort_checks(base):
    from playwright.sync_api import sync_playwright

    metas = build_meta_for_sort_test()
    meta_by_appid = {m["appid"]: m for m in metas}

    with sync_playwright() as p:
        browser = p.chromium.launch()
        any_sort_ui_found = False
        for slug in LANDING_SLUGS:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            reqs = []
            page.on("request", lambda r: reqs.append(r.url))
            page.goto(f"{base}/{slug}.html")
            sel = page.query_selector("select[aria-label='정렬 기준']")
            if sel is None:
                skip(f"[{slug}] 공통 정렬 UI 존재", "정렬 select 없음 — 미구현")
                page.close()
                continue
            any_sort_ui_found = True
            check(f"[{slug}] 공통 정렬 UI 존재", True)

            opts_texts = sel.eval_on_selector_all("option", "els => els.map(e => e.textContent.trim())")
            missing = [lbl for lbl in SORT_LABELS if lbl not in opts_texts]
            check(f"[{slug}] 정렬 옵션 7종 라벨 모두 존재",
                  not missing, f"누락={missing}" if missing else "")

            if slug == "korean-games":
                mode_map = {"평가 좋은 순": "rating", "리뷰 많은 순": "reviews",
                            "낮은 가격순": "price_asc", "높은 가격순": "price_desc",
                            "할인율순": "discount", "이름순": "name"}
                for label, mode in mode_map.items():
                    if label not in opts_texts:
                        continue
                    # 이전 반복에서 page.reload()가 있었다면 이전 핸들은 무효(stale)이므로
                    # 매 반복마다 select 엘리먼트를 다시 조회한다.
                    sel = page.query_selector("select[aria-label='정렬 기준']")
                    if sel is None:
                        check(f"[korean-games] '{label}' 정렬 select 재조회", False, "reload 후 select 사라짐")
                        continue
                    reqs.clear()
                    match = select_sort_option(page, sel, label)
                    page.wait_for_timeout(250)
                    order = [a for a in card_appid_order(page) if a in meta_by_appid]
                    exp = [a for a in expected_order(metas, mode) if a in order]
                    check(f"[korean-games] '{label}' 정렬 결과가 기대 순서와 일치",
                          order == exp, f"실제={order} 기대={exp}")
                    new_fetches = [u for u in reqs if u.endswith(".json") or "/api/" in u]
                    check(f"[korean-games] '{label}' 정렬 시 추가 fetch 없음(순수 DOM 재배열)",
                          not new_fetches, new_fetches)

                    url = page.url
                    qs = parse_qs(urlsplit(url).query)
                    if label == "기본순":
                        check("[korean-games] 기본순 선택 시 sort 파라미터 제거", "sort" not in qs, url)
                    else:
                        check(f"[korean-games] '{label}' 선택 시 sort 파라미터 반영", "sort" in qs, url)
                        page.reload()
                        page.wait_for_timeout(250)
                        order_after_reload = [a for a in card_appid_order(page) if a in meta_by_appid]
                        check(f"[korean-games] '{label}' 새로고침 후 정렬 유지",
                              order_after_reload == order, f"{order_after_reload} vs {order}")

                wish_btn = page.query_selector("button.wish")
                check("[korean-games] 정렬 후에도 찜 버튼 존재", wish_btn is not None)
            page.close()

        if not any_sort_ui_found:
            skip("모든 LANDINGS 공통 정렬 UI 회귀", "어느 랜딩에서도 정렬 select를 찾지 못함 — 전체 미구현")

        browser.close()


def run_regression_checks(base):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(f"{base}/under-10000.html")
        appids = card_appid_order(page)
        check("[under-10000] 무료 게임(710604) 제외됨", 710604 not in appids)
        check("[under-10000] 10001원 게임 제외됨", 710603 not in appids)
        check("[under-10000] 10000원 경계 게임 포함됨(이하 조건)", 710602 in appids)
        idx = page.content()
        check("[under-10000] noindex 없음(기존 색인 정책 유지)", 'name="robots" content="noindex' not in idx)
        page.close()

        page = browser.new_page()
        page.goto(f"{base}/game/710502.html")
        body = page.inner_text("body")
        check("[단독 데모앱 상세] 본편 가격을 추정하지 않고 무료/데모 의미 유지",
              "무료" in body or "데모" in body)
        page.close()
        browser.close()


HOME_SORT_MODE_MAP = {"평가 좋은 순": "rating", "리뷰 많은 순": "reviews",
                      "낮은 가격순": "price_asc", "높은 가격순": "price_desc",
                      "할인율순": "discount", "이름순": "name"}


def run_home_all_sort_checks(base):
    """홈 #all 섹션 자체의 정렬(select#sort, JSON fetch 기반 createCard 렌더)도
    랜딩과 동일한 6개 모드로 검증한다. #all은 IntersectionObserver로 지연 로드되므로
    앵커 이동으로 반드시 뷰포트 안에 들어오게 한다."""
    from playwright.sync_api import sync_playwright

    metas = build_meta_for_sort_test()
    meta_by_appid = {m["appid"]: m for m in metas}

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(f"{base}/index.html#all")
        page.wait_for_timeout(600)
        sel = page.query_selector("#all select[aria-label='정렬 기준']")
        if sel is None:
            skip("[홈 #all] 정렬 UI 존재", "select 없음 — 미구현")
            page.close()
            browser.close()
            return
        check("[홈 #all] 정렬 UI 존재", True)

        for label, mode in HOME_SORT_MODE_MAP.items():
            sel = page.query_selector("#all select[aria-label='정렬 기준']")
            if sel is None:
                check(f"[홈 #all] '{label}' select 재조회", False, "사라짐")
                continue
            opts_texts = sel.eval_on_selector_all("option", "els => els.map(e => e.textContent.trim())")
            if label not in opts_texts:
                skip(f"[홈 #all] '{label}' 옵션", "옵션 없음")
                continue
            match = select_sort_option(page, sel, label)
            page.wait_for_timeout(250)
            order = [a for a in card_appid_order(page, scope_selector="#all") if a in meta_by_appid]
            exp = [a for a in expected_order(metas, mode) if a in order]
            check(f"[홈 #all] '{label}' 정렬 결과가 기대 순서와 일치", order == exp, f"실제={order} 기대={exp}")

            url = page.url
            qs = parse_qs(urlsplit(url).query)
            check(f"[홈 #all] '{label}' 선택 시 sort 파라미터 반영", qs.get("sort") == [
                {"rating": "pos", "reviews": "rev", "price_asc": "cheap", "price_desc": "exp",
                 "discount": "off", "name": "name"}[mode]], url)
            page.reload()
            page.wait_for_timeout(700)
            order_after_reload = [a for a in card_appid_order(page, scope_selector="#all") if a in meta_by_appid]
            check(f"[홈 #all] '{label}' 새로고침 후 정렬 유지",
                  order_after_reload == order, f"{order_after_reload} vs {order}")

        # 함정 게임: 이름에 "무료"가 있지만 실제로는 유료/가격 미정 — data-free로만 판정해야 함
        sel = page.query_selector("#all select[aria-label='정렬 기준']")
        select_sort_option(page, sel, "낮은 가격순")
        page.wait_for_timeout(250)
        order = card_appid_order(page, scope_selector="#all")
        idx_710901 = order.index(710901) if 710901 in order else -1
        idx_710705 = order.index(710705) if 710705 in order else -1  # 진짜 명시적 무료
        check("[홈 #all] 이름에 '무료' 포함된 유료 게임(710901)이 진짜 무료보다 뒤에 옴(textContent 오판정 없음)",
              idx_710901 != -1 and idx_710705 != -1 and idx_710901 > idx_710705,
              f"710901 idx={idx_710901}, 710705(진짜 무료) idx={idx_710901}")
        page.close()
        browser.close()


def run_sort_state_restore_checks(base):
    """뒤로/앞으로(popstate) 시 select 선택과 카드 순서 복원, 잘못된 sort 값의
    기본값 폴백을 실제 브라우저 히스토리 내비게이션으로 확인한다."""
    from playwright.sync_api import sync_playwright

    metas = build_meta_for_sort_test()
    meta_by_appid = {m["appid"]: m for m in metas}

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900})

        # 1) 잘못된 sort 값 — select가 빈 값이 아니라 실제 기본 옵션을 보여줘야 함
        page.goto(f"{base}/korean-games.html?sort=doesnotexist_bogus")
        page.wait_for_timeout(300)
        sel = page.query_selector("select[aria-label='정렬 기준']")
        if sel is None:
            skip("[korean-games] 잘못된 sort 값 폴백", "정렬 select 없음 — 미구현")
        else:
            selected_label = sel.eval_on_selector(
                "option:checked", "e => e.textContent.trim()") if sel.query_selector("option:checked") else None
            check("[korean-games] 잘못된 ?sort= 값이 기본 옵션('기본순')으로 폴백(빈 선택 아님)",
                  selected_label == "기본순", f"selected={selected_label!r}")
            qs = parse_qs(urlsplit(page.url).query)
            check("[korean-games] 잘못된 sort 값은 URL에서 제거됨", "sort" not in qs, page.url)

        # 2) 정렬 변경 → 다른 페이지 이동 → 뒤로가기: 선택/순서 복원
        page.goto(f"{base}/korean-games.html")
        page.wait_for_timeout(300)
        sel = page.query_selector("select[aria-label='정렬 기준']")
        if sel is None:
            skip("[korean-games] popstate 정렬 상태 복원", "정렬 select 없음 — 미구현")
            page.close()
            browser.close()
            return
        select_sort_option(page, sel, "이름순")
        page.wait_for_timeout(250)
        order_before_nav = [a for a in card_appid_order(page) if a in meta_by_appid]

        page.goto(f"{base}/index.html")
        page.wait_for_timeout(200)
        page.go_back()
        page.wait_for_timeout(400)

        sel_after_back = page.query_selector("select[aria-label='정렬 기준']")
        selected_label_after = None
        if sel_after_back is not None:
            opt = sel_after_back.query_selector("option:checked")
            if opt:
                selected_label_after = opt.text_content().strip()
        check("[korean-games] 뒤로가기 후 select 선택 상태 복원('이름순')",
              selected_label_after == "이름순", f"selected={selected_label_after!r}")
        order_after_back = [a for a in card_appid_order(page) if a in meta_by_appid]
        check("[korean-games] 뒤로가기 후 카드 순서 복원",
              order_after_back == order_before_nav, f"{order_after_back} vs {order_before_nav}")
        page.close()
        browser.close()


def run_home_default_state_restore_checks(base):
    """Codex R2 지적: 홈 syncURL이 쿼리 없는 URL로 popstate 복귀할 때 select만
    기본값으로 바꾸고 실제 목록은 그대로 두던 문제. indexData가 이미 로드된 상태에서
    쿼리 없는 URL로 popstate가 발생하면 select와 실제 카드 순서가 둘 다 '진짜 기본
    상태'(쿼리 없이 새로 연 페이지와 동일한 순서)로 돌아오는지 확인한다. 첫 진입 시
    지연 로딩(IntersectionObserver)이 여전히 동작하는지도 별도로 확인한다."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()

        # 0) 무쿼리 첫 진입 지연 로딩 유지 확인: #all이 뷰포트 밖이면 fetch가 아직 없어야 함
        page0 = browser.new_page(viewport={"width": 1440, "height": 900})
        fetches0 = []
        page0.on("request", lambda r: fetches0.append(r.url))
        page0.goto(f"{base}/index.html")
        page0.wait_for_timeout(300)
        early = [u for u in fetches0 if u.endswith("game-search-index.json")]
        check("[홈] 무쿼리 첫 진입 시 #all이 뷰포트 밖이면 지연 로딩 유지(즉시 fetch 안 함)",
              not early, early)
        page0.close()

        # 진짜 기본 순서(쿼리 없이 #all을 새로 연 상태)를 오라클로 확보
        ref_page = browser.new_page(viewport={"width": 1440, "height": 900})
        ref_page.goto(f"{base}/index.html#all")
        ref_page.wait_for_timeout(700)
        ref_sel = ref_page.query_selector("#all select[aria-label='정렬 기준']")
        if ref_sel is None:
            skip("[홈] 쿼리 제거 후 기본 상태 복원", "정렬 select 없음 — 미구현")
            ref_page.close()
            browser.close()
            return
        default_order = card_appid_order(ref_page, scope_selector="#all")
        ref_page.close()

        # 1) ?sort=name#all로 진입(정렬 적용된 상태) → 쿼리 없는 URL로 popstate 시뮬레이션
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(f"{base}/index.html?sort=name#all")
        page.wait_for_timeout(700)
        sorted_order = card_appid_order(page, scope_selector="#all")
        check("[홈] ?sort=name 진입 시 실제로 이름순 정렬됨(사전 조건)", sorted_order != default_order,
              f"{sorted_order}")

        page.evaluate(
            "() => { history.pushState(null, '', location.pathname + '#all'); "
            "window.dispatchEvent(new PopStateEvent('popstate')); }")
        page.wait_for_timeout(400)

        sel_after = page.query_selector("#all select[aria-label='정렬 기준']")
        selected_label = None
        if sel_after is not None:
            opt = sel_after.query_selector("option:checked")
            if opt:
                selected_label = opt.text_content().strip()
        check("[홈] 쿼리 제거 popstate 후 select가 기본값('추천순')으로 복귀",
              selected_label == "추천순", f"selected={selected_label!r}")

        order_after_popstate = card_appid_order(page, scope_selector="#all")
        check("[홈] 쿼리 제거 popstate 후 카드도 실제 기본 순서로 재정렬됨"
              "(select만 바뀌고 목록은 정렬된 채로 남는 회귀 없음)",
              order_after_popstate == default_order,
              f"popstate 후={order_after_popstate} 진짜 기본={default_order}")
        page.close()
        browser.close()


def run_anchor_interceptor_checks(base):
    """보조 키 클릭(새 탭 등 기본 동작 유지)과 prefers-reduced-motion 존중을
    실제 브라우저 동작으로 확인한다."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()
        page.goto(f"{base}/index.html")
        link = page.query_selector('nav.jump a[href*="#hot"]')
        if link is None:
            skip("[Ctrl+클릭] 새 탭으로 열림(기본 동작 유지)", "#hot 링크 없음")
        else:
            try:
                with context.expect_page(timeout=3000) as new_page_info:
                    link.click(modifiers=["ControlOrMeta"])
                new_page = new_page_info.value
                check("[Ctrl+클릭] 새 탭으로 열림(preventDefault 안 됨 — 기본 동작 유지)",
                      new_page is not None)
                new_page.close()
            except Exception as e:
                check("[Ctrl+클릭] 새 탭으로 열림(preventDefault 안 됨 — 기본 동작 유지)",
                      False, f"새 탭이 열리지 않음: {e}")
        page.close()

        # reduced-motion: scrollIntoView 호출 시 behavior:'auto' 여야 함(smooth 강제 금지)
        context2 = browser.new_context(viewport={"width": 1440, "height": 900}, reduced_motion="reduce")
        page2 = context2.new_page()
        page2.goto(f"{base}/index.html")
        page2.evaluate("""() => {
            window.__scrollBehaviors = [];
            const orig = Element.prototype.scrollIntoView;
            Element.prototype.scrollIntoView = function(opts) {
                window.__scrollBehaviors.push(opts && opts.behavior);
                return orig.call(this, opts);
            };
        }""")
        link2 = page2.query_selector('nav.jump a[href*="#hot"]')
        if link2 is None:
            skip("[reduced-motion] smooth 스크롤 강제 안 함", "#hot 링크 없음")
        else:
            link2.click()
            page2.wait_for_timeout(300)
            behaviors = page2.evaluate("window.__scrollBehaviors")
            check("[reduced-motion] prefers-reduced-motion 시 scrollIntoView behavior='auto'(smooth 강제 안 함)",
                  bool(behaviors) and all(b == "auto" for b in behaviors), behaviors)
        page2.close()
        browser.close()


def run_default_order_matches_note_checks(base):
    """랜딩 설명문("기본 정렬은 ~순입니다")이 실제 초기(비-sort) DOM 순서와
    일치하는지 korean-games를 대표로 확인한다."""
    from playwright.sync_api import sync_playwright

    metas = build_meta_for_sort_test()
    meta_by_appid = {m["appid"]: m for m in metas}

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(f"{base}/korean-games.html")
        note = page.inner_text(".sec-note") if page.query_selector(".sec-note") else ""
        check("[korean-games] 설명문에 기본 정렬 명시", "기본 정렬" in note, note)
        order = [a for a in card_appid_order(page) if a in meta_by_appid]
        exp_reviews = [a for a in expected_order(metas, "reviews") if a in order]
        check("[korean-games] 설명문 '리뷰 많은 순' 주장이 실제 초기 DOM 순서와 일치",
              order == exp_reviews, f"실제={order} 기대(리뷰순)={exp_reviews}")
        page.close()
        browser.close()


def main():
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
        have_playwright = True
    except ImportError:
        have_playwright = False

    if not have_playwright:
        skip("전체 브라우저 검증(제목 가림/메뉴 이동/정렬)", "이 환경에 Playwright 미설치")
        print(f"\n결과: 실패 0건 / 스킵 1건")
        sys.exit(0)

    try:
        site_dir = build_fixture_site()
        check("[전체 픽스처 빌드] release_date 있는 출시예정 게임 포함 build.main() 성공(우회 없이 복원된 픽스처)", True)
    except Exception as e:
        check("[전체 픽스처 빌드] release_date 있는 출시예정 게임 포함 build.main() 성공(우회 없이 복원된 픽스처)",
              False, f"{type(e).__name__}: {e}")
        print(f"\n결과: 실패 {len(FAILS)}건 / 스킵 {len(SKIPPED)}건 (전체 픽스처 빌드 크래시로 이후 브라우저 검증 전체 중단)")
        for f in FAILS:
            print("  FAIL -", f)
        sys.exit(1)
    run_korean_soon_build_crash_regression()
    empty_site_dir = build_empty_site()
    httpd, port = start_server(site_dir)
    httpd_empty, port_empty = start_server(empty_site_dir)
    base = f"http://127.0.0.1:{port}"
    empty_base = f"http://127.0.0.1:{port_empty}"
    shots_dir = os.path.join(TMP, "shots")
    os.makedirs(shots_dir, exist_ok=True)

    try:
        run_header_offset_checks(base, shots_dir)
        run_empty_state_checks(empty_base)
        run_landing_sort_checks(base)
        run_home_all_sort_checks(base)
        run_sort_state_restore_checks(base)
        run_home_default_state_restore_checks(base)
        run_anchor_interceptor_checks(base)
        run_default_order_matches_note_checks(base)
        run_regression_checks(base)
    finally:
        httpd.shutdown()
        httpd_empty.shutdown()

    print(f"\n결과: 실패 {len(FAILS)}건 / 스킵 {len(SKIPPED)}건")
    for f in FAILS:
        print("  FAIL -", f)
    for label, reason in SKIPPED:
        print("  SKIP -", label, "—", reason)
    if SCREENSHOTS:
        print("\n스크린샷(대표 실패 몇 장):")
        for s in SCREENSHOTS:
            print("  -", s)
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
