"""홈·카드 UX 규칙: 대표 장르, 칩 상한, 가격 확인 줄, 바로가기, 뒤로 가기 복원 코드."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build
import store

TODAY = datetime.now(timezone.utc).date().isoformat()


def game(appid, **kw):
    g = dict(appid=appid, name=f"G{appid}", app_type="game", korean=1, adult=0, coming_soon=0,
             price_final=20000, price_initial=20000, discount_pct=0, review_count=1000,
             review_total=1000, review_positive_pct=90, genres="인디, 액션",
             header_image="", description="", history=[], score=0, price_last=TODAY)
    g.update(kw)
    return g


class CardTest(unittest.TestCase):
    def test_main_genre(self):
        self.assertEqual(build.main_genre(game(1)), "액션")                 # 인디는 건너뛴다
        self.assertEqual(build.main_genre(game(1, genres="Indie")), "Indie")  # 그것뿐이면 그대로
        self.assertEqual(build.main_genre(game(1, genres="")), "")
        self.assertIn("액션 · 리뷰 1,000", build.card(game(1)))

    def test_chip_cap_keeps_review_and_warnings(self):
        g = game(1, has_demo=1, release_date=TODAY, is_free=1, korean=0,
                 review_score=9, review_desc="Very Positive")
        chips = build.chips_for(g)
        self.assertLessEqual(chips.count('class="t '), build.CHIP_MAX)
        self.assertIn("t nokr", chips)                                     # 경고는 남는다
        if build.review_label(g):
            self.assertIn("t review", chips)

    def test_price_note_only_when_stale(self):
        self.assertNotIn("price-note", build.card(game(1)))
        stale = build.card(game(1, price_last="2026-09-01"))
        self.assertIn("price-note", stale)
        self.assertIn("오래된 정보", stale)


class DetailSearchTextTest(unittest.TestCase):
    def test_upcoming_title_and_description(self):
        g = game(1, coming_soon=1, price_final=0, price_initial=0, release_text="2026년 12월 3일",
                 has_demo=1, description="재료를 옮기고 요리하는 협동 게임", header_image="h.jpg")
        html = build.build_detail(g, [g], TODAY)
        self.assertIn("<title>G1 — 출시일 2026년 12월 3일 · 한국어 지원 · 데모", html)
        self.assertIn('content="G1: 재료를 옮기고 요리하는 협동 게임 ', html)
        self.assertIn('class="dhead-thumb" src="h.jpg"', html)

    def test_released_title_keeps_price(self):
        html = build.build_detail(game(1, discount_pct=50, price_final=10000), [], TODAY)
        self.assertIn("<title>G1 — 10,000원 (50% 할인) · 한국어 지원", html)


class FreebieImageTest(unittest.TestCase):
    def test_epic_images_are_resized(self):
        src = "https://cdn1.epicgames.com/spt-assets/x/cover.png"
        self.assertEqual(build.epic_sized(src, 320), src + "?h=180&quality=medium&resize=1&w=320")
        self.assertEqual(build.epic_sized(src + "?w=1", 320), src + "?w=1")     # 이미 조정된 주소
        steam = "https://cdn.akamai.steamstatic.com/steam/apps/1/header.jpg"
        self.assertEqual(build.epic_sized(steam, 320), steam)


class HomeTest(unittest.TestCase):
    def test_upcoming_excludes_past_dates_and_distinguishes_unknown_schedule(self):
        today = store.release_today()
        games = [
            game(1, coming_soon=1, release_date=(today - timedelta(days=1)).isoformat()),
            game(2, coming_soon=1, release_date=today.isoformat()),
            game(3, coming_soon=1),
        ]
        home = build.build_index(games, TODAY)
        soon = home.split('<section id="soon"', 1)[1].split('</section>', 1)[0]
        self.assertIn('href="game/2.html"', soon)
        self.assertNotIn('href="game/1.html"', soon)
        self.assertNotIn('href="game/3.html"', soon)
        spec = next(spec for spec in build.LANDINGS if spec["slug"] == "korean-soon")
        landing = build.build_landing(spec, games, TODAY)
        self.assertNotIn('href="game/1.html"', landing)
        self.assertLess(landing.index('href="game/2.html"'), landing.index('href="game/3.html"'))
        self.assertIn("출시 일정 · 미정", landing)

    def test_refresh_prioritizes_overdue_games_within_existing_budget(self):
        yesterday = (store.release_today() - timedelta(days=1)).isoformat()
        checked_today = datetime.now(timezone.utc).date().isoformat()
        with sqlite3.connect(":memory:") as conn:
            conn.row_factory = sqlite3.Row
            conn.executescript(store.SCHEMA)
            conn.executemany(
                """INSERT INTO games(appid, name, app_type, korean, coming_soon, release_date,
                                     checked_at, first_seen, last_seen)
                   VALUES (?, 'fixture', 'game', 1, ?, ?, ?, '2020-01-01', '2020-01-01')""",
                [(i, 0, None, "2020-01-01") for i in range(1, 9)]
                + [(9, 1, yesterday, "2021-01-01"), (10, 1, yesterday, checked_today)],
            )
            ids = store.stale_appids(conn, 4)
            self.assertEqual(len(ids), 4)
            self.assertEqual(ids[0], 9)
            self.assertNotIn(10, ids)

    def test_shortcuts_and_restore(self):
        html = build.build_index([game(1, discount_pct=50, review_total=500)], TODAY, None,
                                 recent_drops=[])
        lead = html[html.index('class="lead"'):html.index("</section>", html.index('class="lead"'))]
        for href in ("recent-drops.html", "under-10000.html", "korean-demo.html"):
            self.assertIn(f'href="{href}"', lead)
        self.assertEqual(lead.count('<a href='), 3)
        self.assertNotIn("data-jump-filter", html)
        # 필터는 주소(?f=)에, 스크롤·펼친 개수는 sessionStorage 에 남겨 뒤로 가기 때 복원한다.
        self.assertIn("updateQuery('f'", html)
        self.assertIn("gd-home-pos", html)
        self.assertIn("'back_forward'", html)


if __name__ == "__main__":
    unittest.main()
