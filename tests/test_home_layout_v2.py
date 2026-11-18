"""실제 생성 HTML의 반응형 목록·무료 상태·이미지 실패 회귀. 임시 파일만 사용."""
import base64
from datetime import datetime, timedelta, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build
import theme
from test_home_ux import game
from playwright.sync_api import sync_playwright

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=')

class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass

class LayoutTests(unittest.TestCase):
    def test_actual_pages_at_four_widths_and_freebie_states(self):
        now = datetime.now(timezone.utc)
        games = [game(i, name='아주 긴 한국어 게임 제목과 부제 ' + str(i),
                      header_image='/cover.png', checked_at=now.isoformat(),
                      players_current=100+i, players_at=now.isoformat(),
                      release_date=(now+timedelta(days=2 if i>24 else 0)).date().isoformat(),
                      coming_soon=i>24, discount_pct=30, price_final=14000)
                 for i in range(1, 33)]
        active = dict(id='epic:1', store='epic', title='긴 제목의 무료 배포 게임',
                      status='active', image_url='/missing.png', url='https://example.com/game',
                      korean=1, review_total=1234, review_positive_pct=95,
                      original_price=25000, currency='KRW', description='게임 설명 전체. '*12,
                      end_at=(now+timedelta(days=2)).isoformat())
        upcoming = dict(active, id='epic:2', status='upcoming', title='예정 게임', image_url='/cover.png',
                        start_at=(now+timedelta(days=3)).isoformat(),end_at=(now+timedelta(days=10)).isoformat())
        free = dict(active=[active], upcoming=[upcoming,dict(upcoming,id='epic:3')],
                    checked_at={s:now.isoformat() for s in ('epic','steam','gog')})
        sales = dict(at=now.isoformat(), appids=list(range(1,9)))
        with tempfile.TemporaryDirectory(prefix='gamedil_layout_test_') as tmp:
            dest = Path(tmp)
            (dest/'style.css').write_text(theme.CSS)
            (dest/'cover.png').write_bytes(PNG)
            (dest/'index.html').write_text(build.build_index(games,'now',{},top_sellers=sales,freebies=free))
            variants = {'single':free, 'multi':dict(free,active=[active,dict(active,id='epic:4')]),
                        'upcoming':dict(free,active=[]), 'empty':dict(free,active=[],upcoming=[])}
            for name,data in variants.items():
                (dest/f'{name}.html').write_text(build.build_free_games(data,set(),'now',{}))
                (dest/f'home-{name}.html').write_text(build.build_index(games,'now',{},freebies=data))
            server = ThreadingHTTPServer(('127.0.0.1',0),partial(QuietHandler,directory=tmp))
            threading.Thread(target=server.serve_forever,daemon=True).start()
            origin = f'http://127.0.0.1:{server.server_port}'
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch()
                    page = browser.new_page()
                    errors = []
                    page.on('pageerror',lambda error:errors.append(str(error)))
                    page.route('**/*',lambda route:route.continue_() if route.request.url.startswith(origin) else route.abort())
                    for width in (360,390,1280,1440):
                        page.set_viewport_size({'width':width,'height':844 if width<1024 else 800})
                        for name in ('index','single','multi','upcoming','empty'):
                            page.goto(f'{origin}/{name}.html',wait_until='networkidle')
                            self.assertEqual(page.evaluate('document.documentElement.scrollWidth > innerWidth'),False,(width,name))
                            self.assertEqual(page.locator('img[src="/missing.png"]').count(),0)
                            self.assertEqual(page.evaluate('Array.from(document.images).filter(i=>i.complete && !i.naturalWidth).length'),0)
                            if name=='index':
                                for sid in ('popular','selling','new','soon'):
                                    self.assertEqual(page.locator(f'#{sid} .compact-row').count(),8)
                                boxes=page.locator('#g-trend .compact-section').evaluate_all('(els)=>els.map(e=>({x:e.getBoundingClientRect().x,y:e.getBoundingClientRect().y}))')
                                self.assertEqual(abs(boxes[0]['y']-boxes[1]['y'])<2,width>=1024)
                            if name=='single':
                                card = page.locator('#freeActiveGrid .freebie-card')
                                button = card.locator('.freebie-cta').bounding_box()
                                description = card.locator('.freebie-desc').bounding_box()
                                self.assertLessEqual(button['y'] + button['height'], description['y'])
                                page.get_by_role('button',name='Steam 0',exact=True).click()
                                self.assertEqual(page.locator('#freeActiveGrid .freebie-card:visible').count(),0)
                                self.assertTrue(page.locator('#freeActiveFilterEmpty').is_visible())
                                self.assertEqual(page.locator('#freeUpcomingCnt').inner_text(),'0개')
                                self.assertEqual(page.locator('.free-summary').inner_text(),'지금 받기 0 · 예정 0')
                                page.get_by_role('button',name='전체 1',exact=True).click()
                                self.assertEqual(page.locator('#freeUpcomingGrid .freebie-card:visible').count(),2)
                                self.assertEqual(page.locator('.free-summary').inner_text(),'지금 받기 1 · 예정 2')
                    for name,count in (('single',1),('multi',2),('upcoming',1),('empty',0)):
                        page.goto(f'{origin}/home-{name}.html',wait_until='networkidle')
                        self.assertEqual(page.locator('#home-freebies article').count(),count)
                    self.assertEqual(errors,[])
                    browser.close()
            finally:
                server.shutdown();server.server_close()

if __name__ == '__main__':
    unittest.main()
