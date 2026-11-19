"""가격 표시/검색 Offer 및 최근 인하·신작의 실제 시간 경계를 검증한다."""
import json
from datetime import date, datetime, timezone
from pathlib import Path
import re
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build
import store


class Clock(datetime):
    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 10, 24, 12, tzinfo=timezone.utc)


def game(**changes):
    row = dict(appid=1, name="Fixture", korean=1, app_type="game", adult=0,
               price_final=5000, price_initial=10000, discount_pct=50,
               price_last="2026-10-24", checked_at="2026-10-24", is_free=0,
               release_date="2026-10-24", release_text="2026-10-24",
               history=[], review_count=100, review_total=100, review_positive_pct=90,
               name_lower="fixture", coming_soon=0)
    row.update(changes)
    return row


class AccuracyTest(unittest.TestCase):
    def setUp(self):
        self.clock = patch.object(build, "datetime", Clock)
        self.clock.start()
        self.addCleanup(self.clock.stop)

    def test_new_release_boundary(self):
        for released, expected in [("2026-10-24", True), ("2026-09-24", True),
                                   ("2026-09-23", False), ("2010-01-01", False),
                                   ("2026-10-25", False), (None, False), ("invalid", False)]:
            with self.subTest(released=released):
                self.assertEqual(store.is_new_release(game(tag="신작", release_date=released),
                                                     date(2026, 10, 24)), expected)
        self.assertFalse(store.is_new_release(game(coming_soon=1), date(2026, 10, 24)))
        self.assertFalse(store.is_new_release(game(app_type="demo"), date(2026, 10, 24)))

    def test_drops_use_today_and_reject_future(self):
        for changed, expected in [("2026-10-24", True), ("2026-10-17", True),
                                  ("2026-10-16", False), ("2020-01-02", False),
                                  ("2026-10-25", False), ("invalid", False)]:
            with self.subTest(changed=changed):
                hist = [dict(on_date="2019-01-01", price_final=10000),
                        dict(on_date=changed, price_final=5000)]
                self.assertEqual(bool(build.get_recent_drops([game(history=hist)])), expected)

    def test_price_notes(self):
        self.assertNotIn("오래된", build.price_note(game(price_last="2026-10-22")))
        self.assertIn("오래된", build.price_note(game(price_last="2026-10-21")))
        self.assertIn("미확인", build.price_note(game(price_last="2026-10-25")))
        self.assertIn("미확인", build.price_note(game(price_last=None)))
        self.assertIn("무료 상태 확인", build.price_note(game(is_free=1, price_last=None)))
        self.assertEqual(build.price_note(game(coming_soon=1)), "")

    def test_detail_offer_only_with_fresh_valid_price(self):
        for changes, expected in [({}, True), ({"price_last":"2026-10-01"}, False),
                                  ({"price_last":None}, False), ({"price_final":0}, False),
                                  ({"coming_soon":1}, False),
                                  ({"is_free":1, "price_final":0}, True),
                                  ({"is_free":1, "checked_at":"2026-10-01"}, False)]:
            with self.subTest(changes=changes):
                html = build.build_detail(game(**changes), [], "2026-10-24")
                schema = json.loads(re.search(
                    r'<script type="application/ld\+json">(.*?)</script>', html, re.S)[1])
                self.assertEqual("offers" in schema, expected)
                self.assertIn("가격 정보 확인", html)
                if changes.get("price_last") == "2026-10-01":
                    self.assertIn("가격 재확인 필요", html.split("</title>")[0])
                    self.assertIn("오래된 정보", html)

    def test_missing_review_breakdown_not_zero_percent(self):
        import sqlite3
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript(store.SCHEMA)
        conn.execute(
            "INSERT INTO games (appid, name, app_type, korean, coming_soon, adult, "
            "review_count, review_positive, review_negative, first_seen, last_seen, checked_at) "
            "VALUES (2868840, 'Slay the Spire 2', 'game', 1, 0, 0, 217546, 0, 0, '2026-10-24', '2026-10-24', '2026-10-24')"
        )
        # 빈 0/0 요약이 와도 기존 정상 집계를 지우지 않는다
        conn.execute(
            "INSERT INTO games (appid, name, app_type, korean, coming_soon, adult, "
            "review_count, review_positive, review_negative, review_score, review_desc, first_seen, last_seen, checked_at) "
            "VALUES (999, 'Keep Review', 'game', 1, 0, 0, 100, 95, 5, 9, 'Overwhelmingly Positive', '2026-10-24', '2026-10-24', '2026-10-24')"
        )
        store.save_review_summary(conn, 999, {"score": 0, "desc": "", "positive": 0, "negative": 0, "total": 0})
        conn.commit()
        by_id = {g["appid"]: g for g in store.all_games(conn)}
        self.assertIsNone(by_id[2868840]["review_positive_pct"])
        self.assertEqual(by_id[999]["review_positive_pct"], 95)

        html = build.build_detail(by_id[2868840], [], "2026-10-24")
        self.assertNotIn("긍정 0%", html)
        self.assertIn("스팀 리뷰 217,546개", html)
        self.assertIn('data-wish-id="2868840" data-wish-text="1"', html)
        self.assertIn('&quot;review_count&quot;: 217546', html)
        schema = json.loads(re.search(
            r'<script type="application/ld\+json">(.*?)</script>', html, re.S)[1])
        self.assertNotIn("aggregateRating", schema)

    def test_status_warning_excludes_upcoming_and_free_games(self):
        games = [
            game(appid=1, coming_soon=0, is_free=0, history=[{"price_final": 5000}], media_checked_at="2026-10-24"),
            game(appid=2, coming_soon=0, is_free=0, history=[{"price_final": 9000}], media_checked_at="2026-10-24"),
            game(appid=3, coming_soon=1, is_free=0, history=[], media_checked_at="2026-10-24"),
            game(appid=4, coming_soon=1, is_free=0, history=[], media_checked_at="2026-10-24"),
            game(appid=5, coming_soon=0, is_free=1, history=[], media_checked_at="2026-10-24"),
            game(appid=6, coming_soon=0, is_free=1, history=[], media_checked_at="2026-10-24"),
        ]
        html = build.build_status(games, "2026-10-24 12:00", {"label": "최신 가격", "class": "ok", "display": "10-24 12:00"})
        self.assertNotIn("가격 이력 미수집 비율 높음", html)
        self.assertIn("정상 운영", html)

    def test_ui_audit_css_and_markup_fixes(self):
        import theme
        self.assertIn(".ac-p-row .ribbon", theme.CSS)
        self.assertIn("position: static;", theme.CSS)
        self.assertIn("minmax(250px,1fr)", theme.CSS)
        self.assertIn(".to-top{", theme.CSS)
        self.assertIn("word-break: keep-all;", theme.CSS)
        lead_html = build.lead([], [])
        self.assertIn("한국어 스팀 게임, <br>지금 가격으로 고르기.", lead_html)


if __name__ == "__main__":
    unittest.main()
