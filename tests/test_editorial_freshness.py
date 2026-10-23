"""가격 확인일 경계·빈 후보·상한 전 필터를 실제 후보 생성기로 검증."""
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import editorial

NOW = datetime(2026, 10, 24, 0, 30, tzinfo=timezone.utc)


def game(appid=1, **changes):
    row = dict(appid=appid, name="fixture", app_type="game", korean=1,
               is_free=False, price_final=10000, discount_pct=50,
               review_total=100, review_positive_pct=90,
               price_last="2026-10-24", checked_at="2026-10-24")
    row.update(changes)
    return row


def picks(rows, now=NOW):
    return json.loads(editorial.generate_picks(rows, "https://gamedil.com", now=now))


class FreshnessTest(unittest.TestCase):
    def test_boundaries(self):
        for value, expected in [("2026-10-24", True), ("2026-10-23", True),
                                ("2026-10-22", True), ("2026-10-21", False),
                                ("2026-10-25", False), (None, False), ("", False),
                                ("2026-02-30", False), ("20261024", False),
                                ("2026-10-24T00:00:00Z", False), (12, False)]:
            with self.subTest(value=value):
                result = picks([game(price_last=value)])
                for day in ("wednesday", "saturday"):
                    self.assertEqual(bool(result[day]), expected)

    def test_free_state_separate_from_price(self):
        result = picks([game(is_free=True, price_final=0, price_last="2026-10-01")])
        self.assertEqual(result["wednesday"], [])
        item = result["saturday"][0]
        self.assertIsNone(item["price_checked_at"])
        self.assertEqual(item["availability_checked_at"], "2026-10-24")
        self.assertEqual(picks([game(is_free=True, checked_at=None)])["saturday"], [])
        self.assertEqual(picks([game(is_free=True, checked_at="2026-10-01")])["saturday"], [])

    def test_stale_discount_and_empty_no_fallback(self):
        ori = game(1057090, name="Ori and the Will of the Wisps",
                   price_last="2026-10-01", discount_pct=90)
        result = picks([ori])
        self.assertEqual(result["wednesday"], [])
        self.assertEqual(result["saturday"], [])
        self.assertEqual(result["freshness_policy"]["excluded_stale_count"], 1)

    def test_filter_before_limit(self):
        stale = [game(i, discount_pct=99, price_last="2026-10-01") for i in range(1, 20)]
        result = picks(stale + [game(30)])
        self.assertEqual([g["appid"] for g in result["wednesday"]], [30])

    def test_utc_basis(self):
        kst = timezone(timedelta(hours=9))
        now = datetime(2026, 10, 24, 0, 30, tzinfo=kst)  # UTC는 아직 23일
        result = picks([game(price_last="2026-10-24")], now)
        self.assertEqual(result["wednesday"], [])
        self.assertEqual(result["freshness_policy"]["evaluated_on"], "2026-10-23")
        self.assertEqual(result["generated_at"], "2026-10-23T15:30:00Z")


if __name__ == "__main__":
    unittest.main()
