"""동접 정확성: 응답 구분 → 저장 → 24시간 신선도 → 화면 표시, 그리고 홈 섹션 규칙."""
from datetime import datetime, timedelta, timezone
import logging
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build
import collect
import config
import steam
import store

NOW = datetime(2026, 10, 27, 3, 0, tzinfo=timezone.utc)   # 한국 12:00


def iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


class TempDB(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="gamedil_players_")
        self.old_db = config.DB_PATH
        config.DB_PATH = str(Path(self.tmp.name) / "t.sqlite3")
        self.conn = store.connect()

    def tearDown(self):
        self.conn.close()
        config.DB_PATH = self.old_db
        self.tmp.cleanup()

    def add(self, appid, name="게임", **cols):
        row = dict(appid=appid, name=name, app_type="game", korean=1, adult=0, coming_soon=0,
                   review_count=1000, first_seen="2026-10-01", last_seen="2026-10-27",
                   checked_at="2026-10-27")
        row.update(cols)
        keys = ",".join(row)
        self.conn.execute(f"INSERT INTO games ({keys}) VALUES ({','.join('?' * len(row))})",
                          tuple(row.values()))
        self.conn.execute("INSERT INTO prices (appid,on_date,price_final,price_initial,discount_pct) "
                          "VALUES (?,?,?,?,?)", (appid, "2026-10-27", 10000, 10000, 0))

    def row(self, appid):
        return dict(self.conn.execute("SELECT * FROM games WHERE appid=?", (appid,)).fetchone())


class ResponseTest(unittest.TestCase):
    def fetch(self, payload):
        with patch.object(steam, "_get_json", return_value=payload):
            return steam.fetch_player_count(1)

    def test_classification(self):
        self.assertEqual(self.fetch({"response": {"result": 1, "player_count": 5}}), ("ok", 5))
        self.assertEqual(self.fetch({"response": {"result": 1, "player_count": 0}}), ("ok", 0))
        self.assertEqual(self.fetch({"response": {"result": 42}}), ("unavailable", None))
        self.assertEqual(self.fetch(None), ("error", None))                     # 통신 실패
        for bad in ({}, {"response": []}, {"response": {"result": 1}},
                    {"response": {"result": 1, "player_count": -3}},
                    {"response": {"result": 1, "player_count": "12"}},
                    {"response": {"result": 1, "player_count": True}},
                    {"response": {"result": 1, "player_count": 1.5}}):
            self.assertEqual(self.fetch(bad), ("error", None), bad)
        with patch.object(steam, "_get_json", return_value={"response": {"result": 42}}):
            self.assertIsNone(steam.fetch_current_players(1))


class StoreTest(TempDB):
    def test_failure_keeps_success(self):
        self.add(10)
        store.save_player_count(self.conn, 10, 777)
        first = self.row(10)
        self.assertEqual((first["players_current"], first["players_status"]), (777, "ok"))
        self.conn.execute("UPDATE games SET players_success_at=?, players_checked_at=? WHERE appid=10",
                          ("2026-10-26T00:00:00+00:00", "2026-10-26T00:00:00+00:00"))
        for status in ("error", "unavailable"):
            self.assertFalse(store.save_player_result(self.conn, 10, status, None))
            r = self.row(10)
            self.assertEqual(r["players_current"], 777)
            self.assertEqual(r["players_success_at"], "2026-10-26T00:00:00+00:00")
            self.assertEqual(r["players_status"], status)
            self.assertGreater(r["players_checked_at"], "2026-10-26T00:00:00+00:00")
        self.assertTrue(store.save_player_result(self.conn, 10, "ok", 0))   # 실제 0명은 정상값
        self.assertEqual((self.row(10)["players_current"], self.row(10)["players_status"]), (0, "ok"))

    def test_migration_does_not_trust_old_checked_at(self):
        path = Path(self.tmp.name) / "old.sqlite3"
        old = sqlite3.connect(path)
        old.executescript("""
          CREATE TABLE games (appid INTEGER PRIMARY KEY, name TEXT NOT NULL, first_seen TEXT NOT NULL,
            last_seen TEXT NOT NULL, checked_at TEXT NOT NULL, korean INTEGER DEFAULT 0,
            players_current INTEGER DEFAULT 0, players_previous INTEGER DEFAULT 0,
            players_checked_at TEXT);
          INSERT INTO games VALUES (1,'옛 게임','2026-09-01','2026-10-27','2026-10-27',1,5000,4000,
                                    '2026-10-27T02:00:00+00:00');""")
        old.commit()
        old.close()
        config.DB_PATH = str(path)
        conn = store.connect()
        try:
            r = dict(conn.execute("SELECT * FROM games WHERE appid=1").fetchone())
            self.assertIsNone(r["players_success_at"])
            g = next(x for x in store.all_games(conn, NOW) if x["appid"] == 1)
            self.assertEqual((g["players_current"], g["players_at"]), (0, None))
        finally:
            conn.close()

    def test_freshness_boundaries(self):
        f = lambda at, n=900: store.fresh_player_count(
            {"players_current": n, "players_success_at": at}, NOW)
        self.assertEqual(f(iso(NOW - timedelta(hours=24))), (900, iso(NOW - timedelta(hours=24))))
        self.assertEqual(f(iso(NOW - timedelta(hours=24, seconds=1))), (0, None))
        self.assertEqual(f(iso(NOW + timedelta(minutes=10))), (0, None))           # 미래 시각
        self.assertEqual(f("2026-10-27T02:00:00Z")[0], 900)                        # Z 표기
        self.assertEqual(f("2026-10-27T11:00:00+09:00")[0], 900)                   # KST 표기
        self.assertEqual(f("2026-10-27T02:00:00")[0], 900)                         # 시간대 없음=UTC
        self.assertEqual(f(None), (0, None))
        self.assertEqual(f("깨진 값"), (0, None))
        self.assertEqual(f(iso(NOW), 0), (0, iso(NOW)))                            # 0명 성공

    def test_candidates(self):
        self.add(1, review_count=10)                                   # 일반 순환
        self.add(2, review_count=10, players_status="unavailable", tag="인기")
        self.add(3, review_count=10, players_checked_at="2026-10-26T00:00:00+00:00")
        self.add(4, review_count=5000, players_checked_at="2026-10-27T00:00:00+00:00")
        ids = store.player_signal_appids(self.conn, 10, [3])
        self.assertEqual(ids[:2], [3, 4])            # 판매 상위·인기작이 먼저
        self.assertEqual(set(ids[2:]), {1, 2})       # 통계 미제공은 '인기' 태그여도 우선 후보에서 빠짐
        self.assertEqual(store.player_signal_appids(self.conn, 1), [4])

    def test_collect_to_build(self):
        self.add(20, "성공 게임")
        self.add(21, "실패 게임")
        self.conn.execute("UPDATE games SET players_current=50, players_success_at=? WHERE appid=21",
                          (iso(datetime.now(timezone.utc) - timedelta(hours=30)),))
        store.save_top_sellers(self.conn, [21, 20])
        self.conn.commit()
        answers = {20: ("ok", 3210), 21: ("error", None)}
        with patch.object(steam, "fetch_player_count", side_effect=lambda a: answers.get(a, ("error", None))), \
             patch.object(steam, "fetch_review_summary", return_value=None):
            collect._collect_signals(self.conn, logging.getLogger("t"))
        games = {g["appid"]: g for g in store.all_games(self.conn)}
        self.assertEqual(games[20]["players_current"], 3210)
        self.assertEqual(games[21]["players_current"], 0)             # 30시간 전 값은 숨김
        self.assertEqual(self.row(21)["players_current"], 50)         # DB 성공값은 보존
        html = build.build_index(list(games.values()), "2026-10-27", None, recent_drops=[],
                                 top_sellers=store.load_top_sellers(self.conn))
        self.assertIn(">3,210명 · ", html)
        self.assertNotIn("50명 · ", html)
        self.assertIn("Steam 한국 판매 상위", html)
        sell = html[html.index('id="selling"'):]
        self.assertLess(sell.index('data-wish="21"'), sell.index('data-wish="20"'))
        detail = build.build_detail(games[20], list(games.values()), "2026-10-27", {})
        self.assertIn("Steam 동접", detail)
        self.assertIn("KST 확인", detail)


def sec(html, sid):
    """홈 HTML 에서 id 가 sid 인 섹션 하나만 잘라낸다(섹션 순서와 무관)."""
    i = html.index(f'<section id="{sid}"')
    return html[i:html.index("</section>", i)]


class HomeRulesTest(unittest.TestCase):
    def game(self, appid, **kw):
        g = dict(appid=appid, name=f"G{appid}", app_type="game", korean=1, adult=0, coming_soon=0,
                 price_final=20000, price_initial=20000, discount_pct=0, review_count=1000,
                 review_total=1000, review_positive_pct=90, players_current=0, players_at=None,
                 header_image="", description="", history=[], score=0,
                 price_last=datetime.now(timezone.utc).date().isoformat())
        g.update(kw)
        return g

    def test_popular_empty_without_fresh(self):
        games = [self.game(1, players_current=9999), self.game(2, review_count=99999)]
        html = build.build_index(games, "2026-10-27", None, recent_drops=[])
        self.assertIn("최근 확인한 동접 정보가 없습니다", html)
        self.assertNotIn("지금 많이 찾는", html)                       # 리뷰순 대체 금지

    def test_top_sellers_age_and_filters(self):
        games = [self.game(1), self.game(2, adult=1), self.game(3, coming_soon=1), self.game(4)]
        fresh = {"at": iso(NOW - timedelta(hours=3)), "appids": [4, 2, 3, 99, 1]}
        items, stamp = build.top_seller_games(fresh, games, NOW)
        self.assertEqual([g["appid"] for g in items], [4, 1])
        self.assertEqual(stamp, "10/27 09:00")
        stale = dict(fresh, at=iso(NOW - timedelta(hours=config.TOP_SELLERS_MAX_AGE_HOURS, seconds=1)))
        self.assertEqual(build.top_seller_games(stale, games, NOW), ([], ""))
        self.assertEqual(build.top_seller_games(dict(fresh, at=iso(NOW + timedelta(hours=1))), games, NOW), ([], ""))
        self.assertEqual(build.top_seller_games(None, games, NOW), ([], ""))

    def test_daily_rotate(self):
        items = [self.game(i) for i in range(30)]
        day1 = datetime(2026, 10, 27, tzinfo=build.KST)
        day2 = datetime(2026, 10, 28, tzinfo=build.KST)
        a = build.daily_rotate(items, "s", pool=10, now=day1)
        self.assertEqual(a, build.daily_rotate(items, "s", pool=10, now=day1))   # 같은 날 같은 순서
        self.assertNotEqual(a, build.daily_rotate(items, "s", pool=10, now=day2))
        self.assertEqual({g["appid"] for g in a[:10]}, set(range(10)))           # 기준 밖은 안 끼어듦
        self.assertEqual(a[10:], items[10:])

    def test_sections(self):
        games = [
            self.game(1, discount_pct=55, review_total=500, review_positive_pct=90),   # 1단계
            self.game(2, discount_pct=80, review_total=1000, review_positive_pct=97),  # 1단계
            self.game(3, discount_pct=55, review_positive_pct=60),                     # 평가 미달 → 제외
            self.game(4, coming_soon=1, app_type="demo", name="곧 나올 데모"),
            self.game(5, coming_soon=1, name="곧 나올 게임"),
            self.game(6, discount_pct=90, price_last="2026-09-01"),                    # 오래된 가격 → 제외
        ]
        html = build.build_index(games, "2026-10-27", None, recent_drops=[])
        hot = sec(html, "hot")
        self.assertIn('data-wish="1"', hot)
        self.assertIn('data-wish="2"', hot)
        self.assertNotIn('data-wish="3"', hot)
        self.assertNotIn('data-wish="6"', hot)
        self.assertNotIn("기준을 넓혔습니다", hot)
        soon = sec(html, "soon")
        self.assertIn('data-wish="5"', soon)
        self.assertNotIn('data-wish="4"', soon)

    def test_deal_tiers_and_dedupe(self):
        # 1단계 후보가 없으면 다음 단계로 넓히고, 실제 쓴 기준을 부제에 적는다.
        low = self.game(7, discount_pct=25, review_total=40, review_positive_pct=72)
        html = build.build_index([low], "2026-10-27", None, recent_drops=[])
        hot = sec(html, "hot")
        self.assertIn('data-wish="7"', hot)
        self.assertIn("할인 20% 이상 · Steam 긍정률 70% 이상 · 리뷰 30개 이상", hot)
        self.assertIn("후보가 적어 기준을 넓혔습니다", hot)
        # 마지막 단계 미만(리뷰 29개)은 넣지 않는다.
        weak = self.game(8, discount_pct=60, review_total=29, review_positive_pct=99)
        self.assertEqual(build.deal_picks([weak]), ([], None))
        # 할인 추천에 나온 게임은 바로 아래 최근 인하에서 다시 보여주지 않는다.
        drop = dict(self.game(9, discount_pct=60), recent_drop_amount=1000,
                    recent_drop_rate=10, recent_drop_date="2026-10-27")
        html = build.build_index([self.game(9, discount_pct=60)], "2026-10-27", None,
                                 recent_drops=[drop])
        self.assertIn('data-wish="9"', sec(html, "hot"))
        self.assertNotIn('data-wish="9"', sec(html, "drop"))

    def test_under_10k_quality(self):
        good = [self.game(10 + i, price_final=3000 + i, review_total=100, review_positive_pct=90)
                for i in range(5)]
        junk = self.game(99, price_final=500, review_total=0, review_positive_pct=0, review_count=0)
        html = build.build_index(good + [junk], "2026-10-27", None, recent_drops=[])
        part = sec(html, "under-10000")
        self.assertNotIn('data-wish="99"', part)
        self.assertIn('data-wish="10"', part)


if __name__ == "__main__":
    unittest.main()
