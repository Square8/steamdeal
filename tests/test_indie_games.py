"""인디 추천 카테고리: 실제 임시 DB 빌드 및 브라우저 회귀 검사."""
import functools
import http.server
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build
import config
import store


class IndieGamesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="gamedil_indie_")
        cls.site = Path(cls.tmp.name) / "site"
        cls.old_config = config.DB_PATH, config.SITE_DIR, config.SITE_URL
        config.DB_PATH = str(Path(cls.tmp.name) / "test.sqlite3")
        config.SITE_DIR = str(cls.site)
        config.SITE_URL = "https://gamedil.com"
        conn = sqlite3.connect(config.DB_PATH)
        conn.executescript(store.SCHEMA)
        cls.expected = {810001, 810002, 810003}
        fixtures = [
            (810001, "경계값", "액션, 인디", 1, 0, 0, "game", 40, 10, 10000, 0),
            (810002, "무료 인디", "Indie, RPG", 1, 0, 0, "game", 95, 5, 0, 1),
            (810003, "고가 인디", " indie ", 1, 0, 0, "game", 900, 100, 25000, 0),
            (810004, "분류없음", "액션", 1, 0, 0, "game", 95, 5, 3000, 0),
            (810005, "한국어없음", "인디", 0, 0, 0, "game", 95, 5, 3000, 0),
            (810006, "성인", "인디", 1, 1, 0, "game", 95, 5, 3000, 0),
            (810007, "출시예정", "인디", 1, 0, 1, "game", 95, 5, 3000, 0),
            (810008, "데모앱", "인디", 1, 0, 0, "demo", 95, 5, 3000, 0),
            (810009, "리뷰49", "인디", 1, 0, 0, "game", 49, 0, 3000, 0),
            (810010, "긍정79", "인디", 1, 0, 0, "game", 79, 21, 3000, 0),
            (810011, "부분일치금지", "NotIndie", 1, 0, 0, "game", 95, 5, 3000, 0),
        ]
        for appid, name, genres, kr, adult, soon, kind, pos, neg, price, free in fixtures:
            conn.execute(
                "INSERT INTO games (appid,name,genres,korean,adult,coming_soon,app_type,"
                "review_positive,review_negative,review_count,is_free,first_seen,last_seen,checked_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (appid, name, genres, kr, adult, soon, kind, pos, neg, pos + neg, free,
                 "2026-10-01", "2026-10-24", "2026-10-24"))
            conn.execute("INSERT INTO prices (appid,on_date,price_final,price_initial,discount_pct) "
                         "VALUES (?,?,?,?,?)", (appid, "2026-10-24", price, price, 0))
        conn.commit()
        conn.close()
        assert build.main() == 0

    @classmethod
    def tearDownClass(cls):
        config.DB_PATH, config.SITE_DIR, config.SITE_URL = cls.old_config
        cls.tmp.cleanup()

    def test_selection_and_metadata(self):
        from html.parser import HTMLParser
        class Cards(HTMLParser):
            def __init__(self):
                super().__init__()
                self.ids = set()
            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                if "card" in attrs.get("class", "").split() and "data-wish" in attrs:
                    self.ids.add(int(attrs["data-wish"]))
        html = (self.site / "indie-games.html").read_text()
        cards = Cards()
        cards.feed(html)
        self.assertEqual(cards.ids, self.expected)
        self.assertIn('href="https://gamedil.com/indie-games.html"', html)
        sitemap = (self.site / "sitemap.xml").read_text()
        self.assertIn("https://gamedil.com/indie-games.html", sitemap)
        self.assertNotIn("https://gamedil.com/pick.html", sitemap)
        for path in ("index.html", "game/810001.html", "indie-games.html"):
            text = (self.site / path).read_text()
            self.assertIn("인디·데모</a>", text)
            self.assertNotIn("가챠", text)
        home = (self.site / "index.html").read_text()
        self.assertIn('id="indie"', home)
        legacy = (self.site / "pick.html").read_text()
        self.assertIn('content="noindex,follow"', legacy)
        self.assertIn('content="0;url=indie-games.html"', legacy)
        self.assertNotIn("btnPick", legacy)

    def test_empty(self):
        spec = next(s for s in build.LANDINGS if s["slug"] == "indie-games")
        html = build.build_landing(spec, [], "2026-10-24")
        self.assertIn("아직 조건에 맞는 게임이 수집되지 않았습니다", html)

    def test_browser(self):
        from playwright.sync_api import sync_playwright
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(self.site))
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page()
                page.route("https://**/*", lambda route: route.abort())
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(base + "/indie-games.html?utm_source=test")
                ids = lambda: page.locator("#top > .grid .card").evaluate_all(
                    "cs => cs.map(c => Number(c.dataset.wish))")
                default_ids = ids()
                self.assertEqual(page.locator('#top > .grid .price-note').count(), 3)
                self.assertIn("가격 확인", page.locator('#top > .grid [data-wish="810001"] .price-note').inner_text())
                self.assertEqual(page.locator('#top > .grid .price-note').first.evaluate(
                    "e => getComputedStyle(e).whiteSpace"), "normal")
                page.select_option("#lsort", "cheap")
                self.assertEqual(ids(), [810002, 810001, 810003])
                self.assertIn("utm_source=test", page.url)
                page.reload()
                self.assertEqual(ids(), [810002, 810001, 810003])
                page.select_option("#lsort", "exp")
                self.assertEqual(ids(), [810003, 810001, 810002])
                page.select_option("#lsort", "pos")
                self.assertEqual(ids(), [810002, 810003, 810001])
                page.select_option("#lsort", "default")
                self.assertEqual(ids(), default_ids)
                wish = page.locator('.grid button[data-wish-id="810001"]')
                wish.click()
                self.assertEqual(wish.get_attribute("aria-pressed"), "true")
                wish.click()
                self.assertEqual(wish.get_attribute("aria-pressed"), "false")
                for width in (390, 1440):
                    page.set_viewport_size({"width": width, "height": 900})
                    self.assertLessEqual(page.evaluate(
                        "document.documentElement.scrollWidth - innerWidth"), 0)
                page.goto(base + "/pick.html#appid=810001")
                page.wait_for_url("**/indie-games.html")
                self.assertEqual(errors, [])
                browser.close()
        finally:
            server.shutdown()
            server.server_close()

    def test_indie_picks(self):
        picks = [{"appid": 4228920, "until": "2026-10-30"}]
        with patch.object(config, "INDIE_PICKS", picks):
            self.assertEqual(build.active_indie_picks(datetime(2026, 10, 24, tzinfo=build.KST)), [4228920])
            self.assertEqual(build.active_indie_picks(datetime(2026, 10, 30, 23, 59, tzinfo=build.KST)), [4228920])
            self.assertEqual(build.active_indie_picks(datetime(2026, 10, 31, tzinfo=build.KST)), [])
        # 설정한 게임은 수집 대상에 자동 포함된다.
        for p in config.INDIE_PICKS:
            self.assertIn(p["appid"], config.SEED_APPIDS)

        spec = next(s for s in build.LANDINGS if s["slug"] == "indie-games")
        pick = dict(appid=4228920, name="No More Slimes!!", app_type="game",
                    genres="인디", korean=1, review_total=22, review_positive_pct=77,
                    price_final=10000, price_initial=10000, discount_pct=0,
                    score=0, header_image="", description="", review_count=22)
        auto = dict(appid=111, name="Auto Indie", app_type="game", genres="인디", korean=1,
                    review_total=500, review_positive_pct=95, price_final=5000,
                    price_initial=5000, discount_pct=0, score=99, header_image="",
                    description="", review_count=500)
        self.assertFalse(build.is_indie_recommendation(pick))
        self.assertTrue(build.is_indie_recommendation(auto))

        with patch.object(build, "active_indie_picks", return_value=[4228920]):
            html = build.build_landing(spec, [auto, pick], "2026-10-24")
            # 별도 섹션·라벨 없이 일반 카드로 맨 앞에 나온다.
            self.assertNotIn("운영자 픽", html)
            self.assertLess(html.index('data-wish="4228920"'), html.index('data-wish="111"'))
            self.assertEqual(html.count('data-wish="4228920"'), 1)
            self.assertIn("GameDil이 고른", html)
            # 아직 수집되지 않은 게임은 빈 카드를 만들지 않는다.
            missing = build.build_landing(spec, [auto], "2026-10-24")
            self.assertNotIn("4228920", missing)
            # 성인·출시 전 게임은 올리지 않는다.
            adult = build.build_landing(spec, [auto, dict(pick, adult=1)], "2026-10-24")
            self.assertNotIn('data-wish="4228920"', adult)
        with patch.object(build, "active_indie_picks", return_value=[]):
            expired = build.build_landing(spec, [auto, pick], "2026-10-31")
            self.assertNotIn('data-wish="4228920"', expired)


if __name__ == "__main__":
    unittest.main()
