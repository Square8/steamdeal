"""가짜 가격 데이터로 수집→저장→역대최저 계산→사이트 생성 전 구간 검증.
스팀 API 없이 기계가 정상인지 확인한다."""
import os, sys, tempfile, re
TMP = tempfile.mkdtemp(prefix="steamdeal_test_")
os.environ["DB_PATH"] = os.path.join(TMP, "t.sqlite3")
os.environ["SITE_DIR"] = os.path.join(TMP, "site")

import config, store, build, steam
FAILS = []
def check(label, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {label}" + (f"  ({detail})" if detail else ""))
    if not cond: FAILS.append(label)

print("1) 스팀 응답 파싱 (센트→원 변환)")
import json
class FakeResp:
    status_code = 200
    def __init__(self, d): self._d = d
    def json(self): return self._d
sample = {"730": {"success": True, "data": {
    "type": "game", "name": "Counter-Strike 2", "is_free": False,
    "price_overview": {"initial": 6600000, "final": 3300000, "discount_percent": 50},
    "header_image": "http://x/h.jpg", "short_description": "설명"}}}
import requests
orig = requests.get
requests.get = lambda *a, **k: FakeResp(sample)
try:
    app = steam.fetch_app(730)
finally:
    requests.get = orig
check("게임 정보 파싱", app is not None)
check("최종가 원 단위 변환", app["price_final"] == 33000, str(app["price_final"]))
check("정가 원 단위 변환", app["price_initial"] == 66000, str(app["price_initial"]))
check("할인율", app["discount_pct"] == 50, str(app["discount_pct"]))

print("\n2) 무료 게임 / 게임 아닌 것 제외")
requests.get = lambda *a, **k: FakeResp({"9": {"success": True, "data": {
    "type": "dlc", "name": "DLC", "price_overview": {"final": 100, "initial": 100,
    "discount_percent": 0}}}})
try: check("type!=game 은 None", steam.fetch_app(9) is None)
finally: requests.get = orig

print("\n3) appid 자동 수집 (중첩 구조 훑기)")
ids = steam._walk_for_appids({"specials": {"items": [{"id": 730}, {"id": "570"}]},
                              "top_sellers": {"items": [{"id": 271590}]}})
check("중첩 dict/list 에서 3개 추출", sorted(set(ids)) == [570, 730, 271590], str(sorted(set(ids))))

print("\n4) 저장 + 역대 최저가 계산")
conn = store.connect()
hist = [(70000, 0), (50000, 28), (35000, 50), (42000, 40)]
import datetime as dt
for i, (final, pct) in enumerate(hist):
    d = (dt.date(2026, 8, 1) + dt.timedelta(days=i)).isoformat()
    conn.execute("INSERT INTO games (appid,name,header_image,description,first_seen,last_seen)"
                 " VALUES (730,'Counter-Strike 2','','설명',?,?) ON CONFLICT(appid) DO UPDATE SET last_seen=?",
                 (d, d, d))
    conn.execute("INSERT INTO prices VALUES (730,?,?,70000,?)", (d, final, pct))
conn.commit()
games = store.all_games(conn)
g = games[0]
check("이력 4일", g["days_tracked"] == 4, str(g["days_tracked"]))
check("역대 최저가 = 35,000", g["all_time_low"] == 35000, str(g["all_time_low"]))
check("현재가 = 42,000", g["price_final"] == 42000, str(g["price_final"]))
check("현재는 역대최저 아님", g["is_all_time_low"] is False)

# 오늘 가격을 역대최저로 떨어뜨리면 플래그가 켜지는가
d2 = (dt.date(2026, 8, 1) + dt.timedelta(days=4)).isoformat()
conn.execute("INSERT INTO prices VALUES (730,?,30000,70000,57)", (d2,))
conn.commit()
g2 = store.all_games(conn)[0]
check("최저가 갱신 시 플래그 ON", g2["is_all_time_low"] is True)
check("역대최저 갱신 = 30,000", g2["all_time_low"] == 30000, str(g2["all_time_low"]))

print("\n5) 차트 생성")
sp = build.sparkline(g2["history"])
check("스파크라인 SVG", sp.startswith("<svg") and "polyline" in sp)
check("끝점 강조 원 포함", "<circle" in sp)
one = build.sparkline([{"on_date":"2026-08-01","price_final":1000,"discount_pct":0}])
check("데이터 1건이면 평선 폴백", "<svg" in one and "polyline" not in one)
ch = build.detail_chart(g2["history"], g2["all_time_low"])
check("상세 차트 SVG", "<svg" in ch and "polyline" in ch)
check("역대최저 기준선(점선)", "stroke-dasharray" in ch)
check("호버용 크로스헤어/툴팁", 'class="cross"' in ch and 'class="tip"' in ch)
check("접근성 aria-label", 'aria-label="가격 추이' in ch)
check("이력 1건이면 차트 대신 안내문", "<svg" not in build.detail_chart(
    [{"on_date":"2026-08-01","price_final":1000,"discount_pct":0}], 1000))

print("\n6) 사이트 생성")
conn.close()
rc = build.main()
check("build.main() 정상 종료", rc == 0, f"rc={rc}")
idx = os.path.join(config.SITE_DIR, "index.html")
det = os.path.join(config.SITE_DIR, "game", "730.html")
check("index.html 생성", os.path.exists(idx))
check("상세 페이지 생성", os.path.exists(det))
h = open(idx, encoding="utf-8").read()
check("3개 테마 스코프 정의", all(x in h for x in
      [":root{", ':root:not([data-theme="light"])', ':root[data-theme="dark"]']))
check("역대최저 배지에 아이콘+텍스트 동시 사용", "역대최저</span>" in h and "<svg" in h)
check("검색/필터 컨트롤", 'id="q"' in h and 'data-f="atl"' in h)
check("lang=ko", '<html lang="ko">' in h)
d = open(det, encoding="utf-8").read()
check("상세: 표로 보기(테이블 뷰) 제공", "표로 보기" in d and "<table>" in d)
check("상세: 스팀 상점 링크", "store.steampowered.com/app/730" in d)
check("XSS 이스케이프", "<script>alert" not in h)

print("\n7) 이름에 HTML 특수문자가 있어도 깨지지 않는가")
conn = store.connect()
conn.execute("INSERT INTO games VALUES (999,'<b>Bad</b> & \"Game\"','','x','2026-08-01','2026-08-01')")
conn.execute("INSERT INTO prices VALUES (999,'2026-08-01',1000,2000,50)")
conn.execute("INSERT INTO prices VALUES (999,'2026-08-02',900,2000,55)")
conn.commit(); conn.close()
build.main()
h2 = open(idx, encoding="utf-8").read()
check("태그가 이스케이프됨", "&lt;b&gt;Bad&lt;/b&gt;" in h2)
check("원본 태그가 살아있지 않음", "<b>Bad</b>" not in h2)

print()
if FAILS:
    print(f"!! 실패 {len(FAILS)}건: {FAILS}"); sys.exit(1)
print("전 구간 통과 — 수집/저장/역대최저계산/차트/사이트생성 기계는 정상")
print(f"(테스트 산출물: {config.SITE_DIR})")
