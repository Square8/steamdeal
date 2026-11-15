"""무료 배포 성공 스냅샷·표시 상태와 홈 축약 회귀. 임시 DB만 사용한다."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
import re

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build
import config
import store
from test_home_ux import game

NOW = datetime(2026, 11, 15, 0, tzinfo=timezone.utc)

def item(key, shop="steam", **kw):
    data = dict(id=f"{shop}:{key}", store=shop, title=f"Game {key}", status="active",
                url=f"https://store.steampowered.com/app/{key}/", checked_at=NOW.isoformat())
    data.update(kw)
    return data

class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.override = patch.object(config, "DB_PATH", self.tmp.name + "/test.sqlite3")
        self.override.start()
        self.conn = store.connect()
    def tearDown(self):
        self.conn.close()
        self.override.stop()
        self.tmp.cleanup()
    def save(self, shop, items, now=NOW):
        store.replace_freebies_for_store(self.conn, shop, items, checked_at=now.isoformat())
        self.conn.commit()
    def test_success_empty_removes_only_that_store(self):
        self.save("steam", [item(1)])
        self.save("gog", [item(2, "gog")])
        self.save("steam", [], NOW + timedelta(hours=1))
        self.assertEqual([g["id"] for g in store.load_freebies(self.conn, NOW+timedelta(hours=1))["active"]], ["gog:2"])
    def test_success_replaces_no_end_and_normalizes_timestamp(self):
        self.save("steam", [item(1, checked_at="2020-01-01")])
        rows = store.load_freebies(self.conn, NOW)
        self.assertEqual(rows["active"][0]["checked_at"], NOW.isoformat())
        self.save("steam", [item(2)], NOW + timedelta(hours=1))
        self.assertEqual([g["id"] for g in store.load_freebies(self.conn, NOW+timedelta(hours=1))["active"]], ["steam:2"])
    def test_failed_collection_retains_recent_but_not_indefinitely(self):
        self.save("steam", [item(1)])
        # 실패 시 replace를 호출하지 않는 기존 계약. 성공 메타가 그대로인 경우.
        self.assertEqual(len(store.load_freebies(self.conn, NOW+timedelta(hours=24))["active"]), 1)
        self.assertEqual(store.load_freebies(self.conn, NOW+timedelta(hours=24, seconds=1))["active"], [])
    def test_mismatched_or_missing_success_metadata_is_hidden(self):
        self.save("steam", [item(1)])
        store.set_meta(self.conn, "freebies_steam_checked_at", (NOW+timedelta(hours=1)).isoformat())
        self.assertEqual(store.load_freebies(self.conn, NOW+timedelta(hours=1))["active"], [])
        store.set_meta(self.conn, "freebies_steam_checked_at", "")
        self.assertEqual(store.load_freebies(self.conn, NOW)["active"], [])
    def test_dated_expiration_and_upcoming_boundary(self):
        self.save("epic", [item(1,"epic",end_at=NOW.isoformat()),
                           item(2,"epic",status="upcoming",start_at=NOW.isoformat(),end_at=(NOW+timedelta(days=3)).isoformat()),
                           item(3,"epic",status="upcoming",start_at=(NOW+timedelta(days=1)).isoformat(),end_at=(NOW+timedelta(days=8)).isoformat())])
        rows=store.load_freebies(self.conn,NOW)
        self.assertEqual([g["id"] for g in rows["active"]],["epic:2"])
        self.assertEqual([g["id"] for g in rows["upcoming"]],["epic:3"])
    def test_future_timestamp_is_not_trusted(self):
        self.save("steam", [item(1)], NOW+timedelta(hours=1))
        self.assertEqual(store.load_freebies(self.conn, NOW)["active"], [])

class PresentationTests(unittest.TestCase):
    def freebies(self):
        return dict(active=[item(1,"epic",end_at=(NOW+timedelta(days=1)).isoformat())],
                    upcoming=[item(i,"epic",status="upcoming",start_at=(NOW+timedelta(days=3)).isoformat()) for i in (2,3)],
                    checked_at={s:NOW.isoformat() for s in ("epic","steam","gog")})
    def test_counts_actions_and_check_times(self):
        html=build.build_free_games(self.freebies(),set(),"now",{})
        self.assertIn('지금 받기 1</a> · <a href="#upcoming-free">예정 2',html)
        self.assertIn('에픽게임즈 1</button>',html)
        self.assertIn('Steam 0</button>',html)
        active=html.split('<section id="active-free">')[1].split('</section>')[0]
        upcoming=html.split('<section id="upcoming-free">')[1].split('</section>')[0]
        self.assertIn('무료로 받기',active)
        self.assertEqual(upcoming.count('>상점 보기 ↗</a>'),2)
        self.assertEqual(upcoming.count('>시작 11/18 09:00 KST</div>'),2)
        checked=re.search(r'<p class="free-checked">(.*?)</p>',html).group(1)
        self.assertEqual(checked.count('title="2026-11-15 09:00 KST"'),3)
        self.assertEqual(checked.count('<time datetime='),3)
        self.assertNotIn('오염',html)
    def test_home_has_four_image_sections_and_shortcuts(self):
        games=[game(i, discount_pct=60 if i<10 else 0, has_demo=i>20,
                    players_current=100+i, players_at=NOW.isoformat(),
                    release_date=datetime.now(timezone.utc).date().isoformat()) for i in range(1,30)]
        html=build.build_index(games,'now',freebies=self.freebies())
        sections=dict(re.findall(r'<section id="([^"]+)"[^>]*>(.*?)</section>',html,re.S))
        self.assertEqual([key for key, val in sections.items() if '<div class="rail">' in val],['hot','indie','demo','new'])
        for sid, href in [('drop','recent-drops.html'),('under-10000','under-10000.html')]:
            self.assertIn(f'href="{href}"',sections[sid])
            self.assertNotIn('class="card',sections[sid])
        self.assertIn('class="compact-row"',sections['popular'])
        self.assertNotIn('class="freebie-card"',sections['free-strip'])
        ids=re.findall(r'data-wish="(\d+)"', ''.join(sections[sid] for sid in ('hot','indie','demo')))
        self.assertEqual(len(ids),len(set(ids)))
        self.assertNotIn('id="free-strip"',build.build_index(games,'now',freebies=dict(active=[],upcoming=self.freebies()['upcoming'])))
    def test_sales_rank_preserves_skipped_positions(self):
        html=build.compact_section('selling','순위','',[game(5),game(8)],'','#all','더 보기',ranks={5:1,8:4})
        self.assertEqual(re.findall(r'<span class="row-marker">(.*?)</span>',html),['1','4'])

if __name__ == '__main__':
    unittest.main()
