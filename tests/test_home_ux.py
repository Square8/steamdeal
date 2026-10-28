"""홈·카드 UX 규칙: 대표 장르, 칩 상한, 가격 확인 줄, 바로가기, 뒤로 가기 복원 코드."""
from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build

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


class HomeTest(unittest.TestCase):
    def test_shortcuts_and_restore(self):
        html = build.build_index([game(1, discount_pct=50, review_total=500)], TODAY, None,
                                 recent_drops=[])
        lead = html[html.index('class="lead"'):html.index("</section>", html.index('class="lead"'))]
        for href in ("#hot", "recent-drops.html", "under-10000.html", "korean-demo.html",
                     "indie-games.html", "popular-games.html", "korean-soon.html"):
            self.assertIn(f'href="{href}"', lead)
        self.assertNotIn("data-jump-filter", html)
        # 필터는 주소(?f=)에, 스크롤·펼친 개수는 sessionStorage 에 남겨 뒤로 가기 때 복원한다.
        self.assertIn("updateQuery('f'", html)
        self.assertIn("gd-home-pos", html)
        self.assertIn("'back_forward'", html)


if __name__ == "__main__":
    unittest.main()
