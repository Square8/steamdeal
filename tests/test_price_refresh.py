"""가격 일괄 확인: 응답 분류, 저장 규칙, 대상 순서 (네트워크 없이)."""
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config
import steam
import store

TODAY = datetime.now(timezone.utc).date().isoformat()


def po(final, initial=None, pct=0, currency="KRW"):
    return {"success": True, "data": {"price_overview": {
        "currency": currency, "final": final * 100,
        "initial": (initial or final) * 100, "discount_percent": pct}}}


class FetchPricesTest(unittest.TestCase):
    def test_classify(self):
        resp = {
            "1": po(9900, 33000, 70),
            "2": {"success": True, "data": []},          # 무료·판매 중단
            "3": {"success": False},
            "4": po(1000, currency="USD"),
            "5": {"success": True, "data": {"price_overview": {"currency": "KRW"}}},
        }
        with patch.object(steam, "_get_json", return_value=resp) as get:
            out = steam.fetch_prices([1, 2, 3, 4, 5, 6])
        self.assertEqual(get.call_args[0][1]["filters"], "price_overview")
        self.assertEqual(get.call_args[0][1]["appids"], "1,2,3,4,5,6")
        self.assertEqual(out[1], ("ok", 9900, 33000, 70))
        self.assertEqual(out[2], ("none",))
        self.assertEqual(out[3], ("error",))
        self.assertEqual(out[4], ("error",))
        self.assertEqual(out[5], ("error",))
        self.assertEqual(out[6], ("error",))             # 응답에 빠진 appid

    def test_failed_request_leaves_chunk_out(self):
        with patch.object(config, "PRICE_BATCH_SIZE", 2), \
             patch.object(steam, "_get_json", side_effect=[None, {"3": po(5000)}]):
            out = steam.fetch_prices([1, 2, 3])
        self.assertEqual(out, {3: ("ok", 5000, 5000, 0)})


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(store.SCHEMA)

    def tearDown(self):
        self.conn.close()

    def add(self, appid, **kw):
        row = dict(appid=appid, name=f"G{appid}", app_type="game", korean=1, adult=0,
                   coming_soon=0, is_free=0, first_seen="2026-09-01",
                   last_seen="2026-09-01", checked_at="2026-09-01", price_last="2026-09-01")
        row.update(kw)
        cols = ",".join(row)
        self.conn.execute(f"INSERT INTO games ({cols}) VALUES ({','.join('?' * len(row))})",
                          list(row.values()))

    def test_save_price_only_adds_row_on_change(self):
        self.add(1)
        self.conn.execute("INSERT INTO prices VALUES (1,'2026-09-01',3300,33000,90)")
        store.save_price(self.conn, 1, 33000, 33000, 0)
        store.save_price(self.conn, 1, 33000, 33000, 0)
        rows = self.conn.execute("SELECT on_date, price_final FROM prices ORDER BY on_date").fetchall()
        self.assertEqual([tuple(r) for r in rows], [("2026-09-01", 3300), (TODAY, 33000)])
        g = self.conn.execute("SELECT price_first, price_last FROM games").fetchone()
        self.assertEqual(tuple(g), (TODAY, TODAY))       # price_first 가 비어 있던 픽스처

    def test_refresh_order(self):
        self.add(1, korean=0, price_last="2026-01-01")      # 한국어 아님 → 뒤로
        self.add(2, price_last="2026-10-01")
        self.add(3, price_last="2026-09-01")
        self.add(4, is_free=1)                               # 무료 → 제외
        self.add(5, coming_soon=1)                           # 출시 전 → 제외
        self.add(6, adult=1, price_last="2025-01-01")        # 성인 → 뒤로
        self.assertEqual(store.price_refresh_appids(self.conn, 10), [3, 2, 6, 1])
        self.assertEqual(store.price_refresh_appids(self.conn, 2), [3, 2])

    def test_review_signal_order(self):
        # 최근 가격 확인한 할인 게임 중 평가 미수집이 먼저, 이미 확인한 인기작은 뒤로.
        self.add(1, review_count=5000, reviews_checked_at="2026-10-28T00:00:00+00:00")
        self.add(2, review_count=10, price_last=TODAY)
        self.add(3, review_count=10, price_last="2026-09-01")       # 오래된 가격의 할인
        self.add(4, review_count=2000)                              # 할인 아님, 미수집
        for appid in (2, 3):
            self.conn.execute("INSERT INTO prices VALUES (?, ?, 5000, 10000, 50)", (appid, TODAY))
        self.assertEqual(store.review_signal_appids(self.conn, 10), [2, 3, 4, 1])


if __name__ == "__main__":
    unittest.main()
