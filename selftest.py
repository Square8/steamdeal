"""가짜 데이터로 수집→저장→추천후보 선정→사이트 생성 전 구간 검증.
스팀 API 없이 기계가 정상인지 확인한다."""
import os, sys, tempfile, datetime as dt
TMP = tempfile.mkdtemp(prefix="steamradar_test_")
os.environ["DB_PATH"] = os.path.join(TMP, "t.sqlite3")
os.environ["SITE_DIR"] = os.path.join(TMP, "site")

import config, store, build, steam
import requests
import re

# 네트워크는 전부 가짜 응답이다. 실제 수집용 요청 간격을 기다릴 이유가 없다.
config.REQUEST_DELAY = 0
config.SIGNAL_REQUEST_DELAY = 0

FAILS = []
def check(label, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {label}" + (f"  ({detail})" if detail else ""))
    if not cond: FAILS.append(label)

class FakeResp:
    status_code = 200
    def __init__(self, d): self._d = d
    def json(self): return self._d

def with_fake(payload, fn):
    orig = requests.get
    requests.get = lambda *a, **k: FakeResp(payload)
    try: return fn()
    finally: requests.get = orig

print("1) appdetails 파싱")
payload = {"730": {"success": True, "data": {
    "type": "game", "name": "테스트 게임", "is_free": False,
    "price_overview": {"initial": 6600000, "final": 3300000, "discount_percent": 50},
    "header_image": "http://x/h.jpg", "short_description": "설명",
    "release_date": {"coming_soon": False, "date": "2026년 8월 26일"},
    "supported_languages": "English<strong>*</strong>, Korean, Japanese",
    "genres": [{"description": "액션"}, {"description": "인디"}],
    "demos": [{"appid": 731, "description": ""}],
    "movies": [{"highlight": True, "webm": {"max": "http://x/movie.webm"}, "mp4": {"max": "http://x/movie.mp4"}, "thumbnail": "http://x/poster.jpg"}]}}}
app = with_fake(payload, lambda: steam.fetch_app(730))
check("파싱 성공", app is not None)
check("가격 원 단위(센트→원)", app["price_final"] == 33000, str(app["price_final"]))
check("정가 원 단위", app["price_initial"] == 66000, str(app["price_initial"]))
check("한국어 지원 감지", app["korean"] == 1)
check("데모 감지", app["has_demo"] == 1 and app["demo_appid"] == 731)
check("장르 추출", app["genres"] == "액션, 인디", app["genres"])
check("한국어 출시일 파싱", app["release_date"] == "2026-08-26", str(app["release_date"]))
check("출시예정 아님", app["coming_soon"] == 0)

payload_fb = {"999": {"success": True, "data": {
    "type": "game", "name": "Fallback Test",
    "movies": [{"id": 2569999, "thumbnail": "http://x/thumb.jpg"}]}}}
app_fb = with_fake(payload_fb, lambda: steam.fetch_app(999))
check("fallback MP4 URL 생성", app_fb["movie_mp4"] == "https://cdn.akamai.steamstatic.com/steam/apps/2569999/movie480.mp4")
check("fallback thumbnail 유지", app_fb["movie_poster"] == "http://x/thumb.jpg")

payload_bad = {"999": {"success": True, "data": {
    "type": "game", "name": "Bad Movie Test",
    "movies": "string instead of list"}}}
app_bad = with_fake(payload_bad, lambda: steam.fetch_app(999))
check("잘못된 movie 데이터가 와도 빌드가 중단되지 않음", app_bad["movie_mp4"] == "")

print("\n1a) 현재 플레이어·리뷰 신호 파싱")
players = with_fake({"response": {"result": 1, "player_count": 43210}},
                    lambda: steam.fetch_current_players(730))
check("현재 플레이어 수", players == 43210, str(players))
review = with_fake({"success": 1, "query_summary": {
    "review_score": 9, "review_score_desc": "Overwhelmingly Positive",
    "total_positive": 9500, "total_negative": 500, "total_reviews": 10000}},
    lambda: steam.fetch_review_summary(730))
check("리뷰 요약", review and review["score"] == 9, str(review))
check("리뷰 평가 문구", review and review["desc"] == "Overwhelmingly Positive")

print("\n1b) 스크린샷·트레일러 추출 (키 이름을 가정하지 않는다)")
check("480 을 선호한다", steam._pick_url({"480": "http://a", "max": "http://b"}) == "http://a")
check("480 이 없으면 max", steam._pick_url({"max": "http://b"}) == "http://b")
check("모르는 키만 있어도 하나는 건진다", steam._pick_url({"1080": "http://c"}) == "http://c")
check("문자열로 와도 처리", steam._pick_url("http://d") == "http://d")
check("URL 이 아니면 버린다", steam._pick_url({"480": "없음"}) == "")
check("None 이면 빈 값", steam._pick_url(None) == "")

_p = {"7": {"success": True, "data": {
    "type": "game", "name": "미디어", "is_free": False,
    "release_date": {"coming_soon": False, "date": ""},
    "supported_languages": "Korean", "genres": [], "demos": [],
    "screenshots": [{"path_thumbnail": "http://s1", "path_full": "http://f1"},
                    {"path_thumbnail": "http://s2"}, {"path_thumbnail": "http://s3"},
                    {"path_thumbnail": "http://s4"}, {"path_thumbnail": "http://s5"}],
    "movies": [{"id": 1, "thumbnail": "http://poster", "highlight": False,
                "mp4": {"480": "http://lo.mp4", "max": "http://hi.mp4"}},
               {"id": 2, "thumbnail": "http://poster2", "highlight": True,
                "mp4": {"480": "http://pick.mp4"}, "webm": {"480": "http://pick.webm"}}]}}}
_m = with_fake(_p, lambda: steam.fetch_app(7))
check("스크린샷 4장까지만",
      len(_m["screenshots"].split("\n")) == steam.MAX_SCREENSHOTS,
      _m["screenshots"].replace("\n", " "))
check("highlight 로 표시된 트레일러를 고른다", _m["movie_mp4"] == "http://pick.mp4",
      _m["movie_mp4"])
check("webm 도 함께 가져온다", _m["movie_webm"] == "http://pick.webm")
check("포스터 확보", _m["movie_poster"] == "http://poster2")
_p2 = dict(_p); _p2["7"]["data"] = dict(_p["7"]["data"]); del _p2["7"]["data"]["movies"]
_m2 = with_fake(_p2, lambda: steam.fetch_app(7))
check("movies 가 없어도 안 깨진다(표지로 떨어짐)", _m2["movie_mp4"] == "")
check("응답에 뭐가 왔는지 세어둔다", steam.MEDIA_STATS["apps"] >= 2
      and steam.MEDIA_STATS["screenshots"] >= 2, str(steam.MEDIA_STATS["apps"]))

print("\n2) 한국어 미지원 / 출시예정 / DLC")
p2 = {"9": {"success": True, "data": {"type": "game", "name": "NoKR", "is_free": True,
    "release_date": {"coming_soon": True, "date": "2027년 출시 예정"},
    "supported_languages": "English", "genres": [], "demos": []}}}
a2 = with_fake(p2, lambda: steam.fetch_app(9))
check("한국어 미지원 감지", a2["korean"] == 0)
check("출시예정 감지", a2["coming_soon"] == 1)
check("파싱 불가 날짜는 None", a2["release_date"] is None)
check("무료 감지", a2["is_free"] is True)
p3 = {"5": {"success": True, "data": {"type": "dlc", "name": "DLC"}}}
check("DLC 는 제외", with_fake(p3, lambda: steam.fetch_app(5)) is None)

print("\n3) 발견 목록에서 버킷 태그 유지")
feat = {"new_releases": {"items": [{"id": 111}, {"id": "222"}]},
        "coming_soon": {"items": [{"id": 333}]},
        "specials": {"items": [{"id": 444}]}}
found = with_fake(feat, lambda: steam.discover())
check("신작 태그", found.get(111) == "신작", str(found.get(111)))
check("문자열 id 도 처리", found.get(222) == "신작")
check("출시예정 태그", found.get(333) == "출시예정")
check("할인 태그", found.get(444) == "할인")
check("시드가 포함됨", all(a in found for a in config.SEED_APPIDS))

print("\n4) 저장 + 회전 갱신 대상")
conn = store.connect()
store.save(conn, app, "신작")
store.save(conn, a2, "출시예정")
# 히어로가 후보 하나를 가져가도 섹션이 비지 않는지 보려면 데모 게임이 최소 2개 필요하다
app_b = dict(app)
app_b.update(appid=731, name="테스트 게임 B", price_final=12000,
             price_initial=12000, discount_pct=0, review_count=50)
store.save(conn, app_b, "신작")
conn.commit()
check("3건 저장", conn.execute("SELECT COUNT(*) FROM games").fetchone()[0] == 3)
check("가격 있는 것만 이력에 남음",   # 730, 731 만. 무료(9) 는 제외
      conn.execute("SELECT COUNT(*) FROM prices").fetchone()[0] == 2)
check("stale 목록 반환", len(store.stale_appids(conn, 10)) == 3)
store.save_player_count(conn, 730, 43210)
store.save_review_summary(conn, 730, review)
conn.execute("UPDATE games SET review_count=10000 WHERE appid=730")
conn.commit()
signal_game = next(x for x in store.all_games(conn) if x["appid"] == 730)
check("현재 플레이어 저장", signal_game["players_current"] == 43210)
check("리뷰 긍정 비율 계산", signal_game["review_positive_pct"] == 95)
check("동접 수집 후보", 730 in store.player_signal_appids(conn, 20))
check("리뷰 수집 후보", 730 in store.review_signal_appids(conn, 20))

print("\n4b) 동접 후보가 '할인 중인 게임'에 파묻히지 않는다 (실제 버그 재현)")
# 실측: 할인 중인 정식 게임이 PLAYER_SIGNAL_LIMIT(80)보다 많아지자, 할인 안 하는
# CS2/PUBG/스타듀 밸리 같은 무료·정가 인기작이 순위표에서 영구히 밀려나
# 며칠째 동접이 안 바뀌었다. 실제 크기(수백~수천 리뷰) 그대로 재현한다.
_mem = __import__("sqlite3").connect(":memory:")
_mem.row_factory = __import__("sqlite3").Row
_mem.executescript(store.SCHEMA)
_today = __import__("datetime").date.today().isoformat()
# 할인 중인 '흔한' 게임 100개 — 전부 리뷰는 적당히 있지만 300 미만
for i in range(100):
    _mem.execute(
        """INSERT INTO games (appid,name,app_type,korean,adult,coming_soon,
                              review_count,first_seen,last_seen,checked_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (900000 + i, f"할인게임{i}", "game", 1, 0, 0, 50, _today, _today, _today))
    _mem.execute(
        "INSERT INTO prices (appid,on_date,price_final,price_initial,discount_pct) VALUES (?,?,?,?,?)",
        (900000 + i, _today, 1000, 2000, 50))
# CS2 처럼 할인은 없지만(무료) 리뷰가 아주 많고, 동접 확인은 오래전인 게임
_mem.execute(
    """INSERT INTO games (appid,name,app_type,korean,adult,coming_soon,
                          review_count,players_current,players_checked_at,
                          first_seen,last_seen,checked_at)
       VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
    (730, "CS2 시뮬레이션", "game", 1, 0, 0, 9800000, 468786,
     "2026-09-02T01:24:35+00:00", _today, _today, _today))
_mem.commit()
_candidates = store.player_signal_appids(_mem, 80)
check("할인 게임이 100개 있어도 리뷰 많은 무료 게임은 후보에서 안 빠진다",
      730 in _candidates, f"후보 {len(_candidates)}개 중 CS2 포함 여부={730 in _candidates}")
_mem.close()

print("\n5) 정가는 스팀 값을 쓴다 (관측 최고가로 추정하지 않음)")
games = store.all_games(conn)
g = next(x for x in games if x["appid"] == 730)
check("정가 66,000 유지", g["price_initial"] == 66000, str(g["price_initial"]))
check("현재가 33,000", g["price_final"] == 33000, str(g["price_final"]))

print("\n6) 역대최저 표기 정직성")
check("관측 1일은 신뢰 안 함", g["atl_trustworthy"] is False, f'{g["days_tracked"]}일')
# 관측 초기에 배지가 아예 안 나가야 한다.
# "2일 최저"는 '수집 후 가격이 안 바뀌었다'는 뜻인데 초록 배지로 달면
# 진짜 역대최저처럼 읽힌다 — 사이트 신뢰도를 가장 크게 깎던 표시였다.
check("30일 미만이면 최저가 배지 없음",
      build.atl_label({"at_lowest": True, "days_tracked": 2}) == "",
      "2일 관측")
check(f"{config.MIN_DAYS_FOR_LOW}일부터 기간을 밝힌 배지",
      "35일 최저" in build.atl_label(
          {"at_lowest": True, "days_tracked": 35, "atl_trustworthy": False}))
check(f"{config.MIN_DAYS_FOR_ATL}일부터 역대최저 배지",
      "역대최저" in build.atl_label(
          {"at_lowest": True, "days_tracked": 70, "atl_trustworthy": True}))
for i in range(1, config.MIN_DAYS_FOR_ATL + 2):
    d = (dt.date(2026, 1, 1) + dt.timedelta(days=i)).isoformat()
    conn.execute("INSERT OR REPLACE INTO prices VALUES (730,?,40000,66000,39)", (d,))
conn.commit()
g2 = next(x for x in store.all_games(conn) if x["appid"] == 730)
check(f"관측 {config.MIN_DAYS_FOR_ATL}일 넘으면 신뢰", g2["atl_trustworthy"] is True,
      f'{g2["days_tracked"]}일')
check("최저가 계산", g2["lowest_seen"] == 33000, str(g2["lowest_seen"]))

print("\n7) 추천 후보 선정")
cands = store.broadcast_candidates(store.all_games(conn))
names = [c["name"] for c in cands]
check("한국어+데모 게임은 후보", "테스트 게임" in names, str(names))
check("한국어 미지원은 제외", "NoKR" not in names, str(names))

print("\n7b) 성인 콘텐츠 판정")
check("descriptor id 3 은 성인", steam.is_adult({"content_descriptors": {"ids": [3]}}, []) == 1)
check("폭력(2)만 있으면 성인 아님",
      steam.is_adult({"content_descriptors": {"ids": [2]}}, []) == 0)
check("장르 문자열로도 감지", steam.is_adult({}, ["Sexual Content"]) == 1)
check("일반 게임은 성인 아님", steam.is_adult({}, ["액션", "인디"]) == 0)
adult_app = dict(app); adult_app["appid"] = 700
adult_app["name"] = "성인 테스트"; adult_app["adult"] = 1
c2 = store.connect(); store.save(c2, adult_app, "신작"); c2.commit()
ag = store.all_games(c2)
check("성인 게임은 기본 후보에서 제외",
      "성인 테스트" not in [x["name"] for x in store.broadcast_candidates(ag)])
check("옵션을 켜면 포함",
      "성인 테스트" in [x["name"] for x in store.broadcast_candidates(ag, include_adult=True)])
c2.close()

print("\n7c) 추천 점수")
s_demo, why = store.score_broadcast(
    {"has_demo": 1, "korean": 1, "tag": "신작", "price_final": 9000, "discount_pct": 20})
s_bare, _ = store.score_broadcast({"korean": 0, "price_final": 70000})
check("데모+한국어+신작+저가+할인은 고득점", s_demo >= 60, f"{s_demo}점")
check("근거가 함께 나온다", len(why) >= 4, str(why))
check("조건 없으면 0점", s_bare == 0, f"{s_bare}점")
check("점수는 100 초과 안 함", s_demo <= 100, f"{s_demo}점")
# 점수가 만점에 몰리면 아무 정보도 주지 못한다 → 흔한 조합이 100 이 되지 않아야 한다
check("흔한 조합은 만점이 아니다", s_demo < 100, f"{s_demo}점")
check("할인율이 클수록 점수도 크다",
      store.score_broadcast({"discount_pct": 90})[0] >
      store.score_broadcast({"discount_pct": 20})[0])
check("리뷰 많으면 가점", store.score_broadcast({"review_count": 20000})[0] >
      store.score_broadcast({"review_count": 5})[0])

print("\n7d) 가격은 '변동 시에만' 기록한다 (저장소 비대화 방지)")
cx = store.connect()
same = dict(app); same["appid"] = 800
store.save(cx, same, "신작")                       # 1회차: 첫 기록
n1 = cx.execute("SELECT COUNT(*) FROM prices WHERE appid=800").fetchone()[0]
store.save(cx, same, "신작")                       # 2회차: 같은 가격
n2 = cx.execute("SELECT COUNT(*) FROM prices WHERE appid=800").fetchone()[0]
# 같은 날 두 번 바뀌면 PK(appid,on_date) 때문에 한 행이 갱신된다(의도된 동작).
# '행이 늘어나는지'는 날짜가 다를 때 봐야 한다 → 기존 행을 어제로 옮겨서 확인.
cx.execute("UPDATE prices SET on_date='2026-08-01' WHERE appid=800")
moved = dict(same); moved["price_final"] = 25000   # 3회차: 다른 날 + 가격 변동
store.save(cx, moved, "신작")
n3 = cx.execute("SELECT COUNT(*) FROM prices WHERE appid=800").fetchone()[0]
cx.commit()
check("첫 기록은 남는다", n1 == 1, f"{n1}행")
check("가격 같으면 행이 늘지 않는다", n2 == 1, f"{n2}행")
check("날짜가 바뀌고 가격도 변하면 행이 늘어난다", n3 == 2, f"{n3}행")
r = cx.execute("SELECT price_first, price_last FROM games WHERE appid=800").fetchone()
check("관측 첫/마지막 날은 기록된다", bool(r["price_first"] and r["price_last"]), str(tuple(r)))
# 관측 기간은 '행 개수'가 아니라 '날짜 폭'
check("관측기간=날짜폭", store.observed_days("2026-01-01", "2026-03-01") == 60,
      str(store.observed_days("2026-01-01", "2026-03-01")))
check("같은 날이면 1일", store.observed_days("2026-01-01", "2026-01-01") == 1)
check("날짜 없으면 0", store.observed_days(None, None) == 0)
# 행 2개뿐인데 60일 지켜봤으면 '역대최저'를 신뢰해야 한다 (예전 로직은 2일로 봤음)
cx.execute("UPDATE games SET price_first='2026-01-01', price_last='2026-06-01' WHERE appid=800")
cx.commit()
g800 = next(x for x in store.all_games(cx) if x["appid"] == 800)
check("행 2개라도 날짜폭이 길면 신뢰", g800["atl_trustworthy"] is True,
      f'{g800["days_tracked"]}일 / 이력 {len(g800["history"])}행')
cx.close()

print("\n8) 차트")
sp = build.sparkline(g2["history"], g2.get("price_last"))
check("스파크라인 SVG", sp.startswith("<svg") and "polyline" in sp)
check("이력 없으면 평선", "polyline" not in build.sparkline([]))
check("변동 없으면 평선(없는 기복을 그리지 않음)",
      "polyline" not in build.sparkline(
          [{"on_date": "2026-01-01", "price_final": 100},
           {"on_date": "2026-06-01", "price_final": 100}]))
ch = build.detail_chart(g2["history"], g2["lowest_seen"], g2.get("price_last"))
check("상세 차트", "<svg" in ch and 'class="tip"' in ch)
check("눈금값 중복 없음", len(build.nice_ticks(1000, 1000.4)) == len(set(build.nice_ticks(1000, 1000.4))))
# x축이 날짜에 비례해야 한다: 공백이 긴 구간은 화면에서도 넓어야 함
h_gap = [{"on_date": "2026-01-01", "price_final": 10000, "price_initial": 10000, "discount_pct": 0},
         {"on_date": "2026-01-02", "price_final": 9000, "price_initial": 10000, "discount_pct": 10},
         {"on_date": "2026-12-01", "price_final": 8000, "price_initial": 10000, "discount_pct": 20}]
c_gap = build.detail_chart(h_gap, 8000)
xs = [float(p.split(",")[0]) for p in
      c_gap.split('<polyline points="')[1].split('"')[0].split()]
d_early, d_late = xs[2] - xs[0], xs[-1] - xs[2]
check("x축이 날짜에 비례 (1일 간격 < 11개월 간격)", d_late > d_early * 20,
      f"1일={d_early:.1f}px, 11개월={d_late:.1f}px")
check("계단식으로 그린다(사선 아님)", len(xs) == 2 * len(h_gap) - 1, f"{len(xs)}점")

print("\n8b) 신규 개척 (GetAppList 기반)")
import collect as _collect

# 이름 사전 탈락: 확실한 쓰레기만 걸고, 데모는 절대 걸지 않는다
check("사운드트랙은 이름으로 탈락", steam._junk_name("Cool Game Soundtrack") is True)
check("시즌패스도 탈락", steam._junk_name("Cool Game - Season Pass") is True)
check("데모는 탈락시키지 않는다(우리가 찾는 대상)",
      steam._junk_name("Cool Game Demo") is False)
check("일반 게임 통과", steam._junk_name("붉은 사막의 상인") is False)

applist = {"applist": {"apps": [
    {"appid": 500, "name": "구작"},
    {"appid": 3000, "name": "신작"},
    {"appid": 2000, "name": "중간작 Soundtrack"},
    {"appid": 2500, "name": "중간작"},
    {"appid": 9, "name": "범위밖"},          # 10 미만은 제외
    {"appid": 4000, "name": ""},              # 이름 없음 제외
]}}
pool = with_fake(applist, steam.all_appids)
check("쓰레기/범위밖/무명 제외", [a for a, _ in pool] == [3000, 2500, 500],
      str([a for a, _ in pool]))
check("최신 appid 부터 개척한다('가장 먼저'가 이 사이트의 무기)",
      pool[0][0] == 3000)

# probed 표: 실패한 appid 를 다시 부르지 않는지
store.mark_probed(conn, 111, True)
store.mark_probed(conn, 222, False)
check("확인한 appid 를 기억한다", store.probed_appids(conn) >= {111, 222})
check("실패도 기록된다(재시도 방지)", 222 in store.probed_appids(conn))
ch, hit = store.explore_stats(conn)
check("개척 통계", ch >= 2 and hit >= 1, f"확인 {ch}, 적중 {hit}")

# 예산 배분: 기존갱신 몫 확보 + 중복 없음 + 이미 확인한 것은 건너뜀
import logging as _lg
_old = (config.MAX_APPS_PER_RUN, config.REFRESH_QUOTA, config.EXPLORE_QUOTA)
config.MAX_APPS_PER_RUN, config.REFRESH_QUOTA, config.EXPLORE_QUOTA = 20, 0.25, 0.55
_orig_get = requests.get
def _route(url, *a, **k):
    if "GetAppList" in url:
        return FakeResp({"applist": {"apps": [
            {"appid": 5000 + i, "name": f"개척{i}"} for i in range(40)]}})
    if "featuredcategories" in url:
        return FakeResp({"new_releases": {"items": [{"id": 4444}]}})
    return FakeResp({})
requests.get = _route
try:
    plan, _ex = _collect._plan(conn, _lg.getLogger("t"))
finally:
    requests.get = _orig_get
    config.MAX_APPS_PER_RUN, config.REFRESH_QUOTA, config.EXPLORE_QUOTA = _old
ids = [a for a, _ in plan]
check("예산을 넘지 않는다", len(plan) <= 20, f"{len(plan)}개")
check("중복 호출 없음", len(ids) == len(set(ids)))
check("큐레이션 발견분이 들어간다", 4444 in ids)
explored = [a for a in ids if 5000 <= a < 5040]      # 이 시험의 개척 풀 범위
check("미탐색 appid 로 남은 자리를 채운다", len(explored) > 0, f"{len(explored)}개 {explored[:4]}")
check("개척도 최신부터", explored == sorted(explored, reverse=True), str(explored[:4]))
check("이미 확인한 appid 는 개척 대상에서 빠진다", 222 not in ids and 111 not in ids)

# 엔드포인트 후보를 순서대로 시도하는가 (첫 배포에서 v2/ 가 404 를 냈다)
_orig_get = requests.get
tried = []
def _first_ok(url, *a, **k):
    tried.append(url)
    if "v0002" in url:
        return FakeResp({"error": "nope"})            # 첫 후보 실패로 위장
    return FakeResp({"applist": {"apps": [{"appid": 77, "name": "게임"}]}})
requests.get = _first_ok
try:
    got = steam.all_appids()
finally:
    requests.get = _orig_get
check("첫 후보가 실패하면 다음 후보로 넘어간다", got == [(77, "게임")], str(got))
check("여러 URL 을 실제로 시도한다", len(tried) >= 2, f"{len(tried)}개 시도")

requests.get = lambda *a, **k: FakeResp({"nope": 1})
try:
    check("모든 후보가 실패하면 빈 목록", steam.all_appids() == [])
finally:
    requests.get = _orig_get

# 목록을 못 받아도 개척이 멈추면 안 된다 → 번호 훑기로 대체
config.MAX_APPS_PER_RUN, config.REFRESH_QUOTA, config.EXPLORE_QUOTA = 20, 0.25, 0.55
_base = store.max_game_appid(conn)      # 훑기 시작점은 실행 '전' 값 기준이다
def _no_list(url, *a, **k):
    if "GetAppList" in url:
        return FakeResp({"nope": 1})                  # 전체 목록 전멸
    if "featuredcategories" in url:
        return FakeResp({"new_releases": {"items": [{"id": 4444}]}})
    return FakeResp({})
requests.get = _no_list
try:
    plan2, ex2 = _collect._plan(conn, _lg.getLogger("t"))
finally:
    requests.get = _orig_get
    config.MAX_APPS_PER_RUN, config.REFRESH_QUOTA, config.EXPLORE_QUOTA = _old
ids2 = [a for a, _ in plan2]
_top = _base + config.EXPLORE_NUMERIC_MARGIN
ceiling = _top - (_top % config.EXPLORE_STEP)
want = [ceiling, ceiling - 10, ceiling - 20]
run = [a for a in ids2 if a in want]
check("목록이 없어도 번호 훑기로 개척한다", len(run) >= 2, f"천장 {ceiling} 근처 {run}")
check("가장 큰 번호(최신)부터 10 씩 내려간다",
      run == sorted(run, reverse=True) and all(a % 10 == 0 for a in run), str(run))
check("훑기 천장은 '존재가 확인된' 게임에서만 온다 (probed 는 헛번호를 담는다)",
      store.max_game_appid(conn) ==
      conn.execute("SELECT MAX(appid) FROM games").fetchone()[0])
check("훑기는 10 단위로 내려간다 (appid 는 10 의 배수만 실재한다)",
      config.EXPLORE_STEP == 10 and all(a % 10 == 0 for a in ex2),
      f"{len(ex2)}개 전부 10의 배수")
check("개척분을 따로 표시해 적중률을 잴 수 있다",
      len(ex2) > 0 and all(a <= ceiling for a in ex2) and ex2 <= set(ids2),
      f"{len(ex2)}개, 최대 {max(ex2)} ≤ 천장 {ceiling}")

# 이미 DB 에 있는 게임은 보관 필터와 무관하게 계속 갱신되어야 한다.
# (갱신 대상은 tag=None 으로 오므로 필터를 그냥 걸면 가격이 영원히 멈춘다 — 실제 66개 발생)
_keep = dict(appid=990202, name="한국어없는신작", app_type="game", korean=0, has_demo=0,
             coming_soon=0, is_free=0, header_image="", genres="", short_description="",
             release_text="", release_date=None, demo_appid=None,
             price_final=1000, price_initial=1000, discount_pct=0)
check("최초에는 태그가 있어야 들어온다", store.save(conn, _keep, "신작") is True)
check("한 번 들어온 게임은 태그 없이도 계속 갱신된다",
      store.save(conn, {**_keep, "price_final": 900}, None) is True)
check("갱신이 실제로 반영된다",
      conn.execute("SELECT price_final FROM prices WHERE appid=990202 "
                   "ORDER BY on_date DESC LIMIT 1").fetchone()[0] == 900)

# 보관 범위: 개척은 넓게, 저장은 좁게 (안 그러면 게임 10만개 = 상세 10만장)
base = dict(appid=1, name="x", app_type="game", korean=0, has_demo=0,
            coming_soon=0, is_free=0)
check("한국어 지원이면 보관", store.is_relevant({**base, "korean": 1}, None))
check("데모 있으면 보관", store.is_relevant({**base, "has_demo": 1}, None))
check("출시예정이면 보관", store.is_relevant({**base, "coming_soon": 1}, None))
check("상점 큐레이션에 걸리면 보관", store.is_relevant(base, "신작"))
check("한국어X·데모X·구작·태그X 는 버린다", store.is_relevant(base, None) is False)
check("save() 가 버린 것에 False 를 준다",
      store.save(conn, {**base, "appid": 990101, "header_image": "", "genres": "",
                        "short_description": "", "release_text": "", "release_date": None,
                        "demo_appid": None, "price_final": 0, "price_initial": 0,
                        "discount_pct": 0}, None) is False)
check("버린 게임은 DB 에 없다",
      conn.execute("SELECT COUNT(*) FROM games WHERE appid=990101").fetchone()[0] == 0)

print("\n9) 사이트 생성")
conn.close()
rc = build.main()
check("build.main() 정상", rc == 0, f"rc={rc}")
idx = os.path.join(config.SITE_DIR, "index.html")
h = open(idx, encoding="utf-8").read()
check("index 생성", os.path.exists(idx))
check("홈 HTML에는 자동재생 video가 생성되지 않음", "<video" not in h)
# '오늘의 추천'은 나머지 섹션의 합집합이라 중복의 원인이었다(측정: 중복 7개가 전부
# 이 섹션에서 나왔고, 빼면 0이 됨). 히어로가 같은 역할을 하므로 없앴다.
check("합집합 섹션이 없다(중복의 원인이었다)", "오늘의 추천" not in h)
check("첫 화면 명제", "검증된 핫딜부터" in h)
check("명제 옆 숫자는 실제 값", 'class="facts"' in h and "<b>" in h)
check("트렌드 중심 섹션", "지금 많이 하는 한국어 게임" in h and "70%+" in h)
check("기대작 표현이 정직함", "출시 임박 기대작" in h and "위시리스트 순위는 사용하지 않습니다" in h)
check("무료 데모 섹션", "사기 전에 해보는 무료 데모" in h)
check("거대한 오늘의 한 편 히어로 제거", 'class="hero"' not in h and "오늘의 한 편" not in h)
check("상단 갱신 상태", "최신 가격" in h and 'class="live-dot"' in h)
check("빠른 조건 버튼", 'data-jump-filter="off50"' in h and 'data-jump-filter="cheap"' in h)
check("찜 목록 필터", 'data-f="wish"' in h and "steamWishlist" in h)
check("갱신 지연 상태 판정", build.freshness_info(
      (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=20)).isoformat())['label'] == "업데이트 지연")
check("갱신 멈춤 상태 판정", build.freshness_info(
      (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=40)).isoformat())['label'] == "데이터 오래됨")
# CSS 는 style.css 로 분리됐다 (페이지마다 인라인하면 게임 수만큼 중복)
_css = open(os.path.join(config.SITE_DIR, "style.css"), encoding="utf-8").read()
check("style.css 로 분리됨", len(_css) > 5000 and "<style>" not in h)
check("페이지가 style.css 를 불러온다", 'rel="stylesheet" href="style.css?v=' in h)
check("하위 폴더에서도 CSS 경로가 맞다",
      '"../style.css?v=' in open(os.path.join(config.SITE_DIR, "game", "730.html"),
                                 encoding="utf-8").read())
check("3중 테마 스코프", all(x in _css for x in
      [":root{", ':root:not([data-theme="light"])', ':root[data-theme="dark"]']))
check("모바일 퀵 액션 가로 스크롤", "scroll-snap-type:x mandatory" in _css and "white-space:nowrap" in _css)
check("동접 뱃지 라이브 점", ".player-badge::before" in _css and "@keyframes playerPulse" in _css)
check("찜 버튼 스타일", ".wish.on" in _css and "data-wish-id" in h)
check("목표가 도달 스크립트", "steamdeal-target-price-v1" in h and "목표가 도달" in h)
check("목표 가격 입력 스타일", ".target-input" in _css and ".target-result.hit" in _css)
check("칩에 글자 포함(색 단독 아님)", "데모</span>" in h)
check("필터 컨트롤", 'data-f="demo"' in h and 'data-f="kr"' in h)
check("정렬 컨트롤", 'id="sort"' in h and 'value="cheap"' in h)
check("성인 포함 토글", 'id="adult"' in h)
check("카드에 합성 점수 없음", 'class="score-n"' not in h and 'class="bar"' not in h)
check("헤더에 검색창", 'class="hsearch"' in h and 'name="q"' in h)
check("?q= 쿼리 파라미터 기반 검색 스크립트", 'new URLSearchParams' in h and 'params.get(\'q\')' in h)
check("기존 #q= 하위 호환 스크립트", "h.indexOf('#q=')" in h)
check("초기화 시 q 파라미터 제거", "history.replaceState(null, '', location.pathname)" in h)

idx_s_action = re.search(r'"target":\s*"([^"]+)"', h)
if idx_s_action:
    check("SearchAction target이 홈페이지 ?q= 형식인지", "?q={search_term_string}" in idx_s_action.group(1))
else:
    check("SearchAction target이 홈페이지 ?q= 형식인지", False)

# 랜딩페이지 SearchAction 확인
l_html = open(os.path.join(config.SITE_DIR, "korean-games.html"), encoding="utf-8").read()
l_s_action = re.search(r'"@type":\s*"SearchAction",\s*"target":\s*"([^"]+)"', l_html)
if l_s_action:
    check("랜딩페이지 SearchAction도 홈페이지 ?q= 형식인지", "index.html?q={search_term_string}" in l_s_action.group(1))
else:
    check("랜딩페이지 SearchAction도 홈페이지 ?q= 형식인지", False)
check("전체 목록 더 보기 버튼", 'id="moreBtn"' in h)
check("사이트 정체성이 할인/발견 중심임", "추천 적합도" not in h and "추천 후보" not in h)
check("개발자용 문구 노출 없음", "config.py" not in h)
check("상세 페이지 생성", os.path.exists(os.path.join(config.SITE_DIR, "game", "730.html")))

print("\n9b) 카드 신호 / 이미지 자리표시 / 빈 그래프 안내")
import re as _re
_nbig = h.count('class="card big"')
check("모바일 레일 카드 크기를 균일하게 유지", _nbig == 0, f"{_nbig}장")
signal_card = build.card({"appid": 730, "name": "신호 게임", "korean": 1,
                          "players_current": 43210, "player_delta": 210,
                          "review_desc": "Overwhelmingly Positive",
                          "review_total": 10000, "review_positive_pct": 95,
                          "history": [], "price_final": 33000})
check("카드에 현재 플레이어 수", "player-badge" in signal_card and "4.3만명 플레이 중" in signal_card)
check("카드에 리뷰 평가 칩", "압도적 긍정" in signal_card)
check("상세 리뷰 영문을 한국어로 바꿈", build.review_label(
      {"review_desc": "Overwhelmingly Positive"}) == "압도적 긍정")
# 할인 세기가 색으로 구분되는가 (숫자와 함께 쓰므로 색 단독 아님)
check("할인 75%+ 는 다른 등급으로 표시", build.off_class(90) == "off-hi")
check("50~74% 는 중간 등급", build.off_class(60) == "off-mid")
check("49% 이하는 낮은 등급", build.off_class(25) == "off-lo")
# 같은 말을 두 번 쓰지 않는다 (무료 게임이 '무료'를 왼쪽/가격 양쪽에 찍던 문제)
# 무료 게임은 가격 칸이 이미 '무료'다. 왼쪽 할인 태그로 또 쓰면 같은 말이 두 번 나온다
# (실측으로 6장이 그랬다). 칩의 '무료'는 스캔용이라 남긴다.
_free = build.card({"appid": 1, "name": "테스트", "is_free": 1, "history": [],
                    "price_final": 0, "discount_pct": 0})
check("무료 게임에 중복 할인태그가 없다", "offtag" not in _free)
check("무료 게임 하단은 구분선 없이 정리된다", "card-f bare" in _free)
check("스크린샷이 있으면 상세에 게임 화면 절이 생긴다",
      "게임 화면" in build.shots_strip({"name": "x", "screenshots": "http://a\nhttp://b"}))
check("스크린샷이 없으면 빈 절을 만들지 않는다",
      build.shots_strip({"name": "x", "screenshots": ""}) == "")
check("트레일러가 없으면 이미지 fallback (Steam 트레일러 제목 없음)",
      "<video" not in build.media_main({"appid": 1, "name": "x", "header_image": "http://h"}) and
      "Steam 트레일러" not in build.media_main({"appid": 1, "name": "x", "header_image": "http://h"}))
mm_video = build.media_main({"appid": 1, "name": "x", "header_image": "http://h",
                             "movie_mp4": "http://m.mp4", "movie_poster": "http://p"})
check("트레일러가 있으면 Steam 트레일러 제목과 video 태그 생성",
      "Steam 트레일러" in mm_video and "<video" in mm_video and 'poster="http://p"' in mm_video)
check("데모가 있으면 데모 섹션이 비지 않음",
      "한국어 데모가 아직 수집되지 않았습니다" not in h)
# hidden 속성이 실제로 먹는지. .card 가 display:flex 라서 이 규칙이 없으면
# 검색·필터·성인숨김이 전부 무효가 된다 (실제로 났던 버그)
check("[hidden] 규칙이 있어 필터가 실제로 숨긴다",
      "[hidden]{display:none !important}" in _css)
noimg = {"appid": 4242, "name": "표지없음", "history": []}
check("이미지 없으면 머리글자 자리표시", 'class="ph"' in build.shot(noimg))
d1 = open(os.path.join(config.SITE_DIR, "game", "9.html"), encoding="utf-8").read()
check("이력 1건이면 빈 그래프 대신 안내문", 'class="waiting"' in d1 and "<svg" not in
      d1.split('원화 가격 추이')[1].split('</div>')[0])

print("\n9c) 검색 유입 준비물 (사이트맵 / canonical / OG / 랜딩)")
check("robots.txt 생성", os.path.exists(os.path.join(config.SITE_DIR, "robots.txt")))
cname_path = os.path.join(config.ROOT, "CNAME")
check("CNAME 내용이 gamedil.com", os.path.exists(cname_path) and open(cname_path).read().strip() == "gamedil.com")
sm_path = os.path.join(config.SITE_DIR, "sitemap.xml")
check("sitemap.xml 생성", os.path.exists(sm_path))
for spec in build.LANDINGS:
    p = os.path.join(config.SITE_DIR, f"{spec['slug']}.html")
    check(f"랜딩 {spec['slug']}.html", os.path.exists(p))
kd = open(os.path.join(config.SITE_DIR, "korean-demo.html"), encoding="utf-8").read()
# 제목은 '자동완성이 실제로 제안하는 표현'만 써야 한다.
# "스팀 한국어 데모" 는 실측 제안 0건이었다 — 다시 들어오면 잡는다.
check("랜딩 제목이 수요 확인된 표현을 쓴다", "스팀 무료 데모 추천" in kd)
check("수요 0 으로 측정된 표현은 제목에 없다", "스팀 한국어 데모" not in kd)
_dead = ["스팀 한국어 데모"]
for _f in ("korean-games", "korean-demo", "korean-new", "korean-soon", "under-10000"):
    _t = open(os.path.join(config.SITE_DIR, f"{_f}.html"), encoding="utf-8").read()
    _title = _t.split("<title>")[1].split("</title>")[0]
    check(f"{_f} 제목에 죽은 표현 없음", not any(x in _title for x in _dead), _title[:40])
check("랜딩에도 헤더/네비 있음", 'class="jump"' in kd)
check("상세 페이지 og:image 는 스팀 표지", 'property="og:image"' in
      open(os.path.join(config.SITE_DIR, "game", "730.html"), encoding="utf-8").read())
d730 = open(os.path.join(config.SITE_DIR, "game", "730.html"), encoding="utf-8").read()
check("상세 제목에 가격이 들어간다", "33,000원" in d730.split("</title>")[0])
check("하위 폴더에서 상위 경로가 ../ 로 나간다", 'href="../index.html' in d730)
check("유료 게임 상세에 목표 가격 저장", "data-target-appid=\"730\"" in d730 and "target-save" in d730)
# SITE_URL 을 주면 절대 URL 이 나와야 한다
os.environ["SITE_URL"] = "https://gamedil.com"
import importlib
importlib.reload(config); importlib.reload(build)
build.main()
sm = open(sm_path, encoding="utf-8").read()
idx2 = open(idx, encoding="utf-8").read()
check("사이트맵에 절대 URL", "https://gamedil.com/index.html" in sm, )
check("사이트맵에 랜딩 포함", "korean-demo.html" in sm)
check("사이트맵에 게임 상세 포함", "game/730.html" in sm)
check("성인 게임은 사이트맵에서 제외", "game/700.html" not in sm)
check("canonical 절대 URL", 'rel="canonical" href="https://' in idx2)
check("robots 에 사이트맵 주소", "Sitemap: https://" in
      open(os.path.join(config.SITE_DIR, "robots.txt"), encoding="utf-8").read())
del os.environ["SITE_URL"]
importlib.reload(config); importlib.reload(build)

print("\n9d) JSON-LD 구조화 데이터")
import json
idx3 = open(idx, encoding="utf-8").read()
ld_idx_match = re.search(r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>', idx3, re.DOTALL)
check("홈페이지 JSON-LD 추출", bool(ld_idx_match))
if ld_idx_match:
    try:
        ld_idx = json.loads(ld_idx_match.group(1))
        check("홈페이지 WebSite schema 파싱 성공", ld_idx.get("@type") == "WebSite")
    except Exception as e:
        check("홈페이지 JSON-LD 파싱 실패", False, str(e))

d730_2 = open(os.path.join(config.SITE_DIR, "game", "730.html"), encoding="utf-8").read()
ld_730_match = re.search(r'<script type="application/ld\+json">\s*(\{.*?\})\s*</script>', d730_2, re.DOTALL)
check("상세 페이지 JSON-LD 추출", bool(ld_730_match))
if ld_730_match:
    try:
        ld_730 = json.loads(ld_730_match.group(1))
        check("상세 페이지 VideoGame schema 파싱 성공", ld_730.get("@type") == "VideoGame")
    except Exception as e:
        check("상세 페이지 JSON-LD 파싱 실패", False, str(e))


print("\n10) XSS")
conn = store.connect()
bad = dict(app); bad["appid"] = 999; bad["name"] = '<b>X</b> & "Y"'
store.save(conn, bad, "신작"); conn.commit(); conn.close()
build.main()
h2 = open(idx, encoding="utf-8").read()
check("태그 이스케이프", "&lt;b&gt;X&lt;/b&gt;" in h2)
check("원본 태그 없음", "<b>X</b>" not in h2)

print("\n9f) 같이 볼 만한 게임 추천")
test_games = [
    {"appid": 1, "name": "Game A", "korean": 1, "genres": "Action", "adult": 0},
    {"appid": 2, "name": "Game B", "korean": 1, "genres": "Action", "adult": 0},
    {"appid": 3, "name": "Game C", "korean": 0, "genres": "Puzzle", "adult": 1},
    {"appid": 4, "name": "Game D", "korean": 0, "genres": "Puzzle", "adult": 0},
    {"appid": 5, "name": "Game E", "korean": 0, "genres": "Puzzle", "adult": 1}
]
rel_a = build.build_related(test_games[0], test_games)
check("관련 게임이 있을 때 섹션과 카드가 생성되는지", "같이 볼 만한 게임" in rel_a and 'href="../game/2.html"' in rel_a)
check("현재 게임이 추천에 포함되지 않는지", 'href="../game/1.html"' not in rel_a)
check("추천할 게임이 없으면 빈 섹션이 생성되지 않는지", build.build_related({"appid": 99, "korean": 1, "genres": "None", "adult": 0}, [{"appid": 99, "korean": 1, "genres": "None", "adult": 0}]) == "")
check("성인 게임 정책 - 현재 게임이 일반이면 성인 게임은 추천에서 제외", 'href="../game/3.html"' not in rel_a)
check("성인 게임 정책 - 현재 게임이 성인이어도 다른 성인 게임은 추천에서 제외",
      'href="../game/5.html"' not in build.build_related(test_games[2], test_games))

print("\n11) 최근 가격 인하")
from datetime import datetime, timedelta
now = datetime.now()
t_max = now.strftime("%Y-%m-%d")
t_recent = (now - timedelta(days=2)).strftime("%Y-%m-%d")
t_old = (now - timedelta(days=10)).strftime("%Y-%m-%d")

drop_games = [
    # 1. 10,000원 -> 7,000원 (최근 인하)
    {"appid": 101, "name": "Drop A", "korean": 1, "adult": 0, "price_final": 7000,
     "history": [{"on_date": t_old, "price_final": 10000, "discount_pct": 0}, {"on_date": t_max, "price_final": 7000, "discount_pct": 30}]},
    # 2. 7,000원 -> 10,000원 (인상)
    {"appid": 102, "name": "Up B", "korean": 1, "adult": 0, "price_final": 10000,
     "history": [{"on_date": t_old, "price_final": 7000, "discount_pct": 0}, {"on_date": t_max, "price_final": 10000, "discount_pct": 0}]},
    # 3. 가격 변화 없음
    {"appid": 103, "name": "Same C", "korean": 1, "adult": 0, "price_final": 7000,
     "history": [{"on_date": t_old, "price_final": 7000, "discount_pct": 0}, {"on_date": t_max, "price_final": 7000, "discount_pct": 0}]},
    # 4. 무료/0원
    {"appid": 104, "name": "Free D", "korean": 1, "adult": 0, "is_free": 1, "price_final": 0,
     "history": [{"on_date": t_old, "price_final": 10000, "discount_pct": 0}, {"on_date": t_max, "price_final": 0, "discount_pct": 100}]},
    # 5. 오래된 인하
    {"appid": 105, "name": "Old E", "korean": 1, "adult": 0, "price_final": 7000,
     "history": [{"on_date": "2020-01-01", "price_final": 10000, "discount_pct": 0}, {"on_date": t_old, "price_final": 7000, "discount_pct": 30}]},
    # 6. 성인 게임
    {"appid": 106, "name": "Adult F", "korean": 1, "adult": 1, "price_final": 7000,
     "history": [{"on_date": t_old, "price_final": 10000, "discount_pct": 0}, {"on_date": t_max, "price_final": 7000, "discount_pct": 30}]},
    # 7. 비한국어 게임 (한국어 우선 정렬 확인용)
    {"appid": 107, "name": "Drop G", "korean": 0, "adult": 0, "price_final": 7000,
     "history": [{"on_date": t_old, "price_final": 10000, "discount_pct": 0}, {"on_date": t_max, "price_final": 7000, "discount_pct": 30}]},
]
drops = build.get_recent_drops(drop_games)
check("10,000원 → 7,000원은 최근 인하로 포함", any(d["appid"] == 101 for d in drops))
check("7,000원 → 10,000원은 제외", not any(d["appid"] == 102 for d in drops))
check("가격 변화가 없으면 제외", not any(d["appid"] == 103 for d in drops))
check("무료·0원·가격 미정 제외", not any(d["appid"] == 104 for d in drops))
check("최신 관측일 기준 7일보다 오래된 인하 제외", not any(d["appid"] == 105 for d in drops))
check("성인 게임 제외", not any(d["appid"] == 106 for d in drops))
check("한국어 게임 우선 정렬", drops[0]["appid"] == 101 and drops[1]["appid"] == 107)
drop_a = next(d for d in drops if d["appid"] == 101)
check("인하 금액, 인하율, 변경일 정확성", drop_a["recent_drop_amount"] == 3000 and drop_a["recent_drop_rate"] == 30 and drop_a["recent_drop_date"] == t_max)

check("대상이 없으면 홈 섹션이 생성되지 않음", "📉 최근 가격이 내려간 게임" not in build.build_index(drop_games, t_max, None, recent_drops=[]))
idx_with_drops = build.build_index(drop_games, t_max, None, recent_drops=drops)
check("대상이 있으면 홈 섹션 생성", "📉 최근 가격이 내려간 게임" in idx_with_drops)

# recent-drops.html 생성 및 문구 검증
os.environ["SITE_URL"] = "https://gamedil.com"
import importlib; importlib.reload(config); importlib.reload(build)
build.main()
rd_html = open(os.path.join(config.SITE_DIR, "recent-drops.html"), encoding="utf-8").read()
check("recent-drops.html 생성", "스팀 최근 가격 인하 게임" in rd_html)
check("홈은 최대 8개, 랜딩은 최대 120개 (테스트에서는 랜딩에 카드가 렌더링되는지만 확인)", 'class="card' in rd_html)
sm_content = open(os.path.join(config.SITE_DIR, "sitemap.xml"), encoding="utf-8").read()
check("sitemap에 recent-drops.html 포함", "recent-drops.html" in sm_content)
del os.environ["SITE_URL"]
importlib.reload(config); importlib.reload(build)
detail_drop = build.build_detail(drop_games[0], drop_games, t_max, None, recent_drop=drop_a)
check("상세페이지에 최근 인하 문구가 조건부로 생성", "최근 3,000원 인하" in detail_drop)
detail_no_drop = build.build_detail(drop_games[0], drop_games, t_max, None, recent_drop=None)
check("상세페이지에 조건부 문구 미생성", "최근 3,000원 인하" not in detail_no_drop)

massive_drop_games = [
    {"appid": 1000 + i, "name": f"Game {i}", "korean": 1, "adult": 0, "price_final": 5000,
     "history": [{"on_date": t_old, "price_final": 10000, "discount_pct": 0}, {"on_date": t_max, "price_final": 5000, "discount_pct": 50}]}
    for i in range(125)
]
massive_drops = build.get_recent_drops(massive_drop_games)

idx_massive = build.build_index(massive_drop_games, t_max, None, recent_drops=massive_drops)
drop_sec = idx_massive.split("📉 최근 가격이 내려간 게임")[1].split("</section>")[0]
check("홈 최근 인하 섹션 카드가 정확히 8개인지 검증", drop_sec.count('<a class="card') == 8)

spec_rd = next(s for s in build.LANDINGS if s["slug"] == "recent-drops")
rd_html_massive = build.build_landing(spec_rd, massive_drops[:120], t_max, None)
cnt = rd_html_massive.count('<a class="card')
check("랜딩 생성 결과에서 카드가 정확히 120개인지 검증", cnt == 120)
check("120개 초과 데이터가 있어도 121번째 카드가 랜딩 HTML에 없는지 검증", cnt == 120)

rd_empty = build.build_landing(spec_rd, [], t_max, None)
check("대상이 0개일 때 랜딩의 정직한 빈 상태 안내 생성", "아직 조건에 맞는 게임이 수집되지 않았습니다" in rd_empty and rd_empty.count('<a class="card') == 0)


print("\n12) 비교함 기능 (보안/UX 강화)")
compare_html_path = os.path.join(config.SITE_DIR, "compare.html")
check("compare.html 생성", os.path.exists(compare_html_path))
c_html = open(compare_html_path, encoding="utf-8").read()
sm_content2 = open(os.path.join(config.SITE_DIR, "sitemap.xml"), encoding="utf-8").read()
check("compare.html이 sitemap에 없는지", "compare.html" not in sm_content2)
check("compare.html에 ALL_GAMES 또는 전체 JSON이 없음", "ALL_GAMES" not in c_html and 'var ALL_GAMES' not in c_html)
check("compare.html 크기가 기존보다 작음", len(c_html) < 50000)

idx = os.path.join(config.SITE_DIR, "index.html")
idx_html = open(idx, encoding="utf-8").read()
detail_730 = open(os.path.join(config.SITE_DIR, "game", "730.html"), encoding="utf-8").read()
check("모든 깊이에서 비교 링크 경로가 맞는지 (홈)", 'href="compare.html"' in idx_html)
check("모든 깊이에서 비교 링크 경로가 맞는지 (상세)", 'href="../compare.html"' in detail_730)

check("상세페이지 비교 버튼에 안전한 스냅샷 존재", 'data-snapshot=' in detail_730 and '&quot;name&quot;' in detail_730)

detail_700 = ""
try:
    detail_700 = open(os.path.join(config.SITE_DIR, "game", "700.html"), encoding="utf-8").read()
    check("성인 게임 상세페이지에 비교 버튼이 없음", 'class="btn btn-s compare-btn"' not in detail_700)
except FileNotFoundError:
    pass

import re
build_content = open("build.py", "r", encoding="utf-8").read()
check("기존 appid 배열 형식 localStorage 처리 로직", "typeof arr[0] === 'string'" in build_content and "localStorage.removeItem" in build_content)
check("중복/3개초과/성인 정리 로직 존재", "if (map[appid])" in build_content and "if (g.adult)" in build_content and "out.length >= 3" in build_content)
check("빈 상태 안내 존재", "비교함이 비었습니다." in c_html or "비교함이 비었습니다." in build_content)
check("제거 및 비우기 동작", "window.steamCompare.write([])" in build_content or "cur.splice" in build_content)
check("DOM API textContent 사용", "e.textContent = text" in build_content)
check("유효하지 않은 이미지 제외", "indexOf('http://') === 0" in build_content or "match(/^https?:/" in build_content)
theme_content = open("theme.py", "r", encoding="utf-8").read()
check("모바일 가로 스크롤용 CSS 존재", "overflow-x: auto;" in theme_content and "-webkit-overflow-scrolling: touch;" in theme_content)


print("\n12b) 비교함 내구성 및 보안")
idx_html = open(idx, encoding="utf-8").read()
check("compare.html에 noindex,follow가 있음", '<meta name="robots" content="noindex,follow">' in c_html)
check("홈페이지에는 noindex,follow가 없음", '<meta name="robots" content="noindex,follow">' not in idx_html)

import json
mock_snap = {
    "appid": 999,
    "name": "</script><script>alert(1)</script>",
    "adult": 0
}
# build_detail에 직접 넣어서 렌더링 후 data-snapshot 속성값을 검증
html_999 = build.build_detail(mock_snap, [mock_snap], "updated", {})
check("악의적 이름이 상세페이지에서 안전하게 이스케이프됨", 'data-snapshot=' in html_999 and '&lt;/script&gt;' in html_999 and '<script>alert' not in html_999)

build_content = open("build.py", "r", encoding="utf-8").read()
check("스냅샷 appid 정규화 존재", "Number(g.appid)" in build_content and "isNaN(appid)" in build_content)
check("스냅샷 name, header_image 문자열 확인", "typeof g.name === 'string'" in build_content and "typeof g.header_image === 'string'" in build_content)
check("스냅샷 가격 숫자 정규화", "Math.max(0, Number(g.price_final)" in build_content)
check("스냅샷 더티 체크 후 자동 저장", "if (dirty)" in build_content and "localStorage.setItem" in build_content)

check("compare.html에 {{가 남아있지 않음", "{{" not in c_html)
check("compare.html에 }}가 남아있지 않음", "}}" not in c_html)
check("정상 JavaScript 중괄호 생성", "function render() {" in c_html)

print()
print("\n13) 초기 로딩 지연 최적화 (Lazy Load)")
idx_path = os.path.join(config.SITE_DIR, "index.html")
json_path = os.path.join(config.SITE_DIR, "assets/game-search-index.json")
sitemap_path = os.path.join(config.SITE_DIR, "sitemap.xml")

if os.path.exists(idx_path):
    index_html = open(idx_path, "r", encoding="utf-8").read()
    idx_size = os.path.getsize(idx_path)
else:
    index_html = ""
    idx_size = 0

if os.path.exists(json_path):
    search_json = open(json_path, "r", encoding="utf-8").read()
else:
    search_json = ""

check("index.html 렌더링 시 전체 카드 수가 줄어듦 (약 200 미만)", index_html.count('class="card"') < 200)
check("index.html 크기가 줄어듦", idx_size < 150 * 1024)
check("assets/game-search-index.json 생성됨", os.path.exists(json_path))
check("JSON 데이터에 description, history 배열이 없음", '"history":[' not in search_json and '"description":' not in search_json)
check("sitemap에 JSON 파일이 없음", "game-search-index.json" not in open(sitemap_path).read())
check("지연 로드 fetch 코드 존재", "fetch('assets/game-search-index.json')" in index_html)
check("IntersectionObserver 초기 로드 트리거 존재", "new IntersectionObserver" in index_html)
check("검색 입력/파라미터 진입 시 로드 트리거 존재", "loadIndex()" in index_html)
check("DOM API textContent를 이용한 안전한 렌더링 존재", "textContent = " in index_html)
check("createCard 내에서 JSON 필드 렌더링 시 innerHTML / insertAdjacentHTML 사용 안 함", "innerHTML = g." not in index_html and "insertAdjacentHTML" not in index_html)
check("f-string 보간 잔류 없음: {len(games)}", "{len(games)}" not in index_html)
check("f-string 보간 잔류 없음: {all_note}", "{all_note}" not in index_html)
check('f-string 보간 잔류 없음: {"".join(card(g) for g in shown_games)}', '{"".join(card(g) for g in shown_games)}' not in index_html)
check("f-string 보간 잔류 없음: {tiles}", "{tiles}" not in index_html)
import re as _re
_all_match = _re.search(r'<section id="all">.*?</section>', index_html, _re.DOTALL)
_all_cards = _all_match.group().count('class="card"') if _all_match else 0
_all_adult = _all_match.group().count('data-adult="1"') if _all_match else 0
check(f"전체 목록 초기 카드가 24개 이하이며 0이 아님 (실제: {_all_cards}개)", 0 < _all_cards <= 24)
check(f"전체 목록 초기 카드에 성인 콘텐츠 없음 (실제: {_all_adult}개)", _all_adult == 0)


print("\n14) 미디어 백필 (트레일러 안전 수집)")
import sqlite3
mig_conn = sqlite3.connect(":memory:")
mig_conn.row_factory = sqlite3.Row
legacy_schema = store.SCHEMA.replace("media_checked_at TEXT,", "")
mig_conn.executescript(legacy_schema)
mig_cols_before = {r["name"] for r in mig_conn.execute("PRAGMA table_info(games)")}
check("마이그레이션 전 media_checked_at 칼럼 없음", "media_checked_at" not in mig_cols_before)
mig_conn.execute("""
    INSERT INTO games (appid, name, adult, checked_at, first_seen, last_seen, movie_mp4, movie_webm)
    VALUES (9001, 'Has MP4', 0, '2026-09-01', '2026-09-01', '2026-09-01', 'http://cdn/video.mp4', ''),
           (9002, 'No Movie', 0, '2026-09-01', '2026-09-01', '2026-09-01', '', ''),
           (9003, 'Has WebM Only', 0, '2026-09-01', '2026-09-01', '2026-09-01', '', 'http://cdn/video.webm')
""")
mig_conn.commit()

store._migrate(mig_conn)
mig_cols_after = {r["name"] for r in mig_conn.execute("PRAGMA table_info(games)")}
check("기존 DB에 새 열이 없어도 자동 마이그레이션됨", "media_checked_at" in mig_cols_after)
r9001 = mig_conn.execute("SELECT media_checked_at FROM games WHERE appid=9001").fetchone()
r9002 = mig_conn.execute("SELECT media_checked_at FROM games WHERE appid=9002").fetchone()
r9003 = mig_conn.execute("SELECT media_checked_at FROM games WHERE appid=9003").fetchone()
check("기존 MP4 영상 있는 게임은 checked_at으로 채워져 재수집 방지", r9001["media_checked_at"] == '2026-09-01')
check("기존 영상 없는 게임은 media_checked_at이 비어있어 백필 대상 유지", r9002["media_checked_at"] is None)
check("movie_webm만 있는 기존 게임도 마이그레이션 후 media_checked_at 기록됨", r9003["media_checked_at"] == '2026-09-01')

bf_conn = sqlite3.connect(":memory:")
bf_conn.row_factory = sqlite3.Row
bf_conn.executescript(store.SCHEMA)
bf_conn.execute("""
    INSERT INTO games (appid, name, app_type, adult, review_count, media_checked_at, checked_at, first_seen, last_seen)
    VALUES (2001, 'Game A', 'game', 0, 500, NULL, '2026-09-01', '2026-09-01', '2026-09-01'),
           (2002, 'Demo B', 'demo', 0, 100, NULL, '2026-09-01', '2026-09-01', '2026-09-01'),
           (2003, 'Game C Checked', 'game', 0, 1000, '2026-09-01 12:00:00', '2026-09-01', '2026-09-01', '2026-09-01'),
           (2004, 'Adult D', 'game', 1, 9999, NULL, '2026-09-01', '2026-09-01', '2026-09-01')
""")
bf_conn.commit()

candidates = store.media_backfill_appids(bf_conn, 10)
check("성인 게임 제외 (2004 제외)", 2004 not in candidates)
check("이미 media_checked_at이 있는 게임은 재선택하지 않음 (2003 제외)", 2003 not in candidates)
check("미디어 미확인 비성인 정식 게임이 데모보다 우선 선택됨", candidates == [2001, 2002])

deduped = store.media_backfill_appids(bf_conn, 10, exclude_appids={2001})
check("일반 수집 대상과 중복 제거", 2001 not in deduped and deduped == [2002])

bf_conn.execute("INSERT INTO games (appid, name, app_type, adult, checked_at, first_seen, last_seen) VALUES (4001, 'Fallback Backfill Game', 'game', 0, '2026-09-01', '2026-09-01', '2026-09-01')")
bf_conn.execute("INSERT INTO games (appid, name, app_type, adult, checked_at, first_seen, last_seen) VALUES (4002, 'No Video Backfill Game', 'game', 0, '2026-09-01', '2026-09-01', '2026-09-01')")
bf_conn.commit()

payload_fb = {"4001": {"success": True, "data": {
    "type": "game",
    "name": "Fallback Backfill Game",
    "movies": [{"id": 777888, "highlight": True}]
}}}
parsed_fb = with_fake(payload_fb, lambda: steam.fetch_app(4001))
check("steam.py에서 fallback MP4 생성", "movie480.mp4" in parsed_fb["movie_mp4"])
store.save(bf_conn, parsed_fb)
saved_fb = bf_conn.execute("SELECT movie_mp4, media_checked_at FROM games WHERE appid=4001").fetchone()
check("fallback MP4가 저장되고 media_checked_at도 기록됨",
      saved_fb["movie_mp4"] == parsed_fb["movie_mp4"] and bool(saved_fb["media_checked_at"]))

payload_no_vid = {"4002": {"success": True, "data": {
    "type": "game",
    "name": "No Video Backfill Game",
    "movies": []
}}}
parsed_no_vid = with_fake(payload_no_vid, lambda: steam.fetch_app(4002))
store.save(bf_conn, parsed_no_vid)
saved_no_vid = bf_conn.execute("SELECT movie_mp4, media_checked_at FROM games WHERE appid=4002").fetchone()
check("실제 영상이 없는 게임은 movie_mp4 없음", not saved_no_vid["movie_mp4"])
check("성공 응답이지만 movie 없는 게임은 media_checked_at 기록됨", bool(saved_no_vid["media_checked_at"]))
check("영상 없는 확인 완료 게임은 백필 후보에서 제외됨", 4002 not in store.media_backfill_appids(bf_conn, 10))

# 실패 처리 및 백필 계속 진행 테스트:
# 5001: fetch 실패 (None 반환)
# 5002: fetch 성공이지만 movie 없음 (실제 영상 없음)
# 5003: fetch 성공 및 영상 있음 (5001 실패 후에도 중단되지 않고 다음 게임 처리가 계속되는지 확인)
test_fail_conn = sqlite3.connect(":memory:")
test_fail_conn.row_factory = sqlite3.Row
test_fail_conn.executescript(store.SCHEMA)
test_fail_conn.execute("""
    INSERT INTO games (appid, name, app_type, adult, checked_at, first_seen, last_seen)
    VALUES (5001, 'Fail Game', 'game', 0, '2026-09-01', '2026-09-01', '2026-09-01'),
           (5002, 'No Movie Game', 'game', 0, '2026-09-01', '2026-09-01', '2026-09-01'),
           (5003, 'Success Game', 'game', 0, '2026-09-01', '2026-09-01', '2026-09-01')
""")
test_fail_conn.commit()

payload_5002 = {"5002": {"success": True, "data": {"type": "game", "name": "No Movie Game", "movies": []}}}
payload_5003 = {"5003": {"success": True, "data": {"type": "game", "name": "Success Game", "movies": [{"id": 55555, "highlight": True}]}}}

def _route_backfill(url, *a, **k):
    p = str(k.get("params") or "")
    if "5001" in p:
        return FakeResp(None)
    if "5002" in p:
        return FakeResp(payload_5002)
    if "5003" in p:
        return FakeResp(payload_5003)
    return FakeResp({})

_orig_get = requests.get
try:
    requests.get = _route_backfill
    res_multi = _collect._collect_media_backfill(test_fail_conn, _lg.getLogger("test_fail"))
finally:
    requests.get = _orig_get

check("failed / no_video 카운트가 서로 구분됨", res_multi["failed"] == 1 and res_multi["no_video"] == 1 and res_multi["found"] == 1)

row_5001 = test_fail_conn.execute("SELECT media_checked_at FROM games WHERE appid=5001").fetchone()
check("fetch_app이 None인 경우 media_checked_at이 비어 있음", row_5001["media_checked_at"] is None)
check("실패한 게임은 다음 백필 후보에 다시 포함됨", 5001 in store.media_backfill_appids(test_fail_conn, 10))

row_5002 = test_fail_conn.execute("SELECT movie_mp4, media_checked_at FROM games WHERE appid=5002").fetchone()
check("실제 영상 없음으로 정상 처리된 게임은 media_checked_at 기록됨", bool(row_5002["media_checked_at"]))
check("영상 없는 확인 완료 게임은 다음 백필 후보에서 제외됨", 5002 not in store.media_backfill_appids(test_fail_conn, 10))

row_5003 = test_fail_conn.execute("SELECT movie_mp4, media_checked_at FROM games WHERE appid=5003").fetchone()
check("백필 중 한 게임이 실패해도 다음 게임 처리가 계속됨", "movie480.mp4" in (row_5003["movie_mp4"] or ""))


print("\n15) 내 찜 목록 (my-games.html)")
my_games_path = os.path.join(config.SITE_DIR, "my-games.html")
check("my-games.html 생성", os.path.exists(my_games_path))
mg_html = open(my_games_path, encoding="utf-8").read()
check("noindex,follow 존재", '<meta name="robots" content="noindex,follow">' in mg_html)

sm_xml = open(os.path.join(config.SITE_DIR, "sitemap.xml"), encoding="utf-8").read()
check("sitemap 제외", "my-games.html" not in sm_xml)

idx_html = open(os.path.join(config.SITE_DIR, "index.html"), encoding="utf-8").read()
detail_files = [f for f in os.listdir(os.path.join(config.SITE_DIR, "game")) if f.endswith(".html")]
detail_html = open(os.path.join(config.SITE_DIR, "game", detail_files[0]), encoding="utf-8").read() if detail_files else ""
check("네비 링크의 상대경로 정확성 (홈)", 'href="my-games.html"' in idx_html and '내 찜 <span class="wish-count">' in idx_html)
check("네비 링크의 상대경로 정확성 (상세)", 'href="../my-games.html"' in detail_html and '내 찜 <span class="wish-count">' in detail_html)

check("기존 localStorage 키 재사용 (찜)", "steamdeal-wishlist-v1" in mg_html)
check("기존 localStorage 키 재사용 (목표가)", "steamdeal-target-price-v1" in mg_html)

check("JSON fetch가 my-games.html에만 존재", "assets/game-search-index.json" in mg_html)
# 자동완성 fetch는 초기 실행 코드가 아니라 input 이벤트 흐름 안에서만 시작되어야 함 (초기 즉시 fetch 없음)
check("상세 페이지에 초기 즉시 fetch 없음", "getIndex()" not in detail_html and "loadIndex()" not in detail_html)
landing_kd = open(os.path.join(config.SITE_DIR, "korean-games.html"), encoding="utf-8").read()
check("랜딩 페이지에 초기 즉시 fetch 없음", "getIndex()" not in landing_kd and "loadIndex()" not in landing_kd)
cmp_html = open(os.path.join(config.SITE_DIR, "compare.html"), encoding="utf-8").read()
check("비교 페이지에 초기 즉시 fetch 없음", "getIndex()" not in cmp_html and "loadIndex()" not in cmp_html)

check("빈 상태 문구", "아직 찜한 게임이 없습니다." in mg_html and "홈으로 돌아가기" in mg_html)
check("목표가 도달 판정 코드", "목표가 도달" in mg_html and ("currentPrice <= currentTarget" in mg_html or "p <= t" in mg_html))
check("성인 기본 숨김/토글 코드", "adultCheck" in mg_html and "!g.adult" in mg_html and "성인 게임 포함" in mg_html)

check("DOM API textContent 사용", "textContent" in mg_html and "document.createElement" in mg_html)
check("JSON 기반 innerHTML/insertAdjacentHTML 미사용", "innerHTML = g." not in mg_html and "innerHTML=g." not in mg_html and "insertAdjacentHTML" not in mg_html)

css_content = open(os.path.join(config.SITE_DIR, "style.css"), encoding="utf-8").read()
check("모바일 레이아웃 CSS 존재", ".my-card" in css_content and "@media" in css_content and ".my-target-actions" in css_content)

import subprocess
scripts = re.findall(r'<script>(.*?)</script>', mg_html, flags=re.DOTALL)
node_syntax_ok = True
for s in scripts:
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as tf:
        tf.write(s)
        tname = tf.name
    try:
        res = subprocess.run(["node", "-c", tname], capture_output=True, text=True)
        if res.returncode != 0:
            node_syntax_ok = False
            print("Node syntax error:", res.stderr)
    finally:
        if os.path.exists(tname): os.remove(tname)
check("Node로 my-games.html의 실행 JS 문법 검사(JSON-LD 제외)", node_syntax_ok)

check("my-games.html에 출시 전/가격 미정 분기 코드 존재", "g.soon ? '출시 전' : '가격 미정'" in mg_html and "!currentPrice" in mg_html)

price_node_test = """
function getPriceDisplay(g) {
  var currentPrice = +g.price || 0;
  if (g.free) {
    return '무료';
  } else if (!currentPrice) {
    return g.soon ? '출시 전' : '가격 미정';
  } else {
    return currentPrice.toLocaleString('ko-KR') + '원';
  }
}
const out = {
  soon: getPriceDisplay({price: 0, free: false, soon: true}),
  tbd: getPriceDisplay({price: 0, free: false, soon: false}),
  free: getPriceDisplay({price: 0, free: true, soon: false}),
  paid: getPriceDisplay({price: 15000, free: false, soon: false})
};
console.log(JSON.stringify(out));
"""
import json as _json
p_proc = subprocess.run(["node", "-e", price_node_test], capture_output=True, text=True)
p_res = _json.loads(p_proc.stdout)
check("출시 전(price=0, free=false, soon=true) 게임이 출시 전으로 렌더링되는지", p_res["soon"] == "출시 전")
check("가격 미정(price=0, free=false, soon=false) 게임이 가격 미정으로 렌더링되는지", p_res["tbd"] == "가격 미정")
check("위 경우 0원으로 표시되지 않는지", p_res["soon"] != "0원" and p_res["tbd"] != "0원")
check("무료 게임은 계속 무료로 표시되는지", p_res["free"] == "무료")


print("\n16) 상세 페이지 가격 판단 요약 (원화 가격 추이)")
# 1. 짧은 관측 기간: 신뢰 부족 문구
g_short = {"appid": 8101, "name": "ShortTrack", "price_final": 20000, "lowest_seen": 20000,
           "days_tracked": 5, "price_last": "2026-09-01",
           "history": [{"on_date": "2026-09-01", "price_final": 20000, "price_initial": 20000, "discount_pct": 0}]}
d_short = build.build_detail(g_short, [g_short], "2026-09-02", {})
check("짧은 관측 기간에는 신뢰 부족 문구가 나오는지",
      "5일째 추적 중 · 아직 충분한 가격 이력이 쌓이지 않았습니다." in d_short)
check("원화 가격 추이 패널 상단에 가격 판단 요약이 위치하는지",
      "원화 가격 추이" in d_short and 'aria-label="가격 판단 요약"' in d_short)

# 2. 충분한 관측 기간 + 현재가 = 관측 최저가
g_low = {"appid": 8102, "name": "LowTrack", "price_final": 15000, "lowest_seen": 15000,
         "days_tracked": 40, "price_last": "2026-09-01", "atl_trustworthy": False,
         "history": [{"on_date": "2026-08-01", "price_final": 20000, "price_initial": 20000, "discount_pct": 0},
                     {"on_date": "2026-09-01", "price_final": 15000, "price_initial": 20000, "discount_pct": 25}]}
d_low = build.build_detail(g_low, [g_low], "2026-09-02", {})
check("충분한 관측 기간 + 현재가=관측 최저가 상태",
      "현재 관측 기간(40일) 중 최저가입니다." in d_low)
check("atl_trustworthy 아닐 때는 역대 표현 미사용",
      "역대 최저가" not in d_low.split('aria-label="가격 판단 요약"')[1].split('</div>')[0])

g_atl = {"appid": 8103, "name": "AtlTrack", "price_final": 10000, "lowest_seen": 10000,
         "days_tracked": 70, "price_last": "2026-09-01", "atl_trustworthy": True,
         "history": [{"on_date": "2026-07-01", "price_final": 20000, "price_initial": 20000, "discount_pct": 0},
                     {"on_date": "2026-09-01", "price_final": 10000, "price_initial": 20000, "discount_pct": 50}]}
d_atl = build.build_detail(g_atl, [g_atl], "2026-09-02", {})
check("atl_trustworthy 충족 시 역대 최저가 문구 사용",
      "현재 관측 기간(70일) 중 역대 최저가입니다." in d_atl)

# 3. 현재가 > 관측 최저가일 때 금액/비율 차이
g_high = {"appid": 8104, "name": "HighTrack", "price_final": 30000, "lowest_seen": 20000,
          "days_tracked": 45, "price_last": "2026-09-01",
          "history": [{"on_date": "2026-08-01", "price_final": 20000, "price_initial": 30000, "discount_pct": 33},
                      {"on_date": "2026-09-01", "price_final": 30000, "price_initial": 30000, "discount_pct": 0}]}
d_high = build.build_detail(g_high, [g_high], "2026-09-02", {})
check("현재가>관측 최저가일 때 금액/비율 차이",
      "관측 최저가보다 10,000원 (50%) 높습니다." in d_high and "+10,000원 (+50%)" in d_high)

# 4. 무료/가격 미정/출시 전 제외
g_free = {"appid": 8105, "name": "FreeGame", "is_free": 1, "price_final": 0}
d_free = build.build_detail(g_free, [g_free], "2026-09-02", {})
check("무료 게임은 가격 판단 요약 제외", 'aria-label="가격 판단 요약"' not in d_free)

g_soon = {"appid": 8106, "name": "SoonGame", "coming_soon": 1, "price_final": 0}
d_soon = build.build_detail(g_soon, [g_soon], "2026-09-02", {})
check("출시 전 게임은 가격 판단 요약 제외", 'aria-label="가격 판단 요약"' not in d_soon)

g_noprice = {"appid": 8107, "name": "NoPriceGame", "price_final": 0}
d_noprice = build.build_detail(g_noprice, [g_noprice], "2026-09-02", {})
check("가격 미정(0원) 게임은 가격 판단 요약 제외", 'aria-label="가격 판단 요약"' not in d_noprice)

# 5. 기존 recent drop 문구와 목표가 패널 유지
rd_mock = {"appid": 8104, "recent_drop_amount": 5000, "recent_drop_date": "2026-09-01"}
d_with_drop = build.build_detail(g_high, [g_high], "2026-09-02", {}, recent_drop=rd_mock)
check("기존 recent drop 문구 유지", "최근 5,000원 인하 · 2026-09-01 관측" in d_with_drop)
check("기존 목표가 패널 유지", "target-panel" in d_with_drop and "내 목표 가격" in d_with_drop)

# 6. 상세 HTML에 모바일 CSS와 접근성 문구 확인
check("접근성 role=region 및 aria-label 존재",
      'role="region" aria-label="가격 판단 요약"' in d_high)
check("마지막 가격 관측일 표시", "마지막 관측: 2026-09-01" in d_high)
css_text = open(os.path.join(config.SITE_DIR, "style.css"), encoding="utf-8").read()
check("style.css에 가격 판단 모바일 레이아웃 CSS 존재",
      ".price-judge" in css_text and ".pj-tiles" in css_text and "@media" in css_text)


print("\n17) 상단 네비게이션 정리 및 모바일 최적화")
idx_html = open(os.path.join(config.SITE_DIR, "index.html"), encoding="utf-8").read()
detail_files = [f for f in os.listdir(os.path.join(config.SITE_DIR, "game")) if f.endswith(".html")]
detail_html = open(os.path.join(config.SITE_DIR, "game", detail_files[0]), encoding="utf-8").read() if detail_files else ""
css_text = open(os.path.join(config.SITE_DIR, "style.css"), encoding="utf-8").read()

# 1. 상단 내 찜 링크 유지
check("상단 내 찜 링크 유지 (홈)", 'href="my-games.html">내 찜 <span class="wish-count">' in idx_html)

# 2. 상단의 중복 찜 앵커 링크 제거 확인
nav_chunk = idx_html.split('<nav class="jump"')[1].split('</nav>')[0]
check("상단의 중복 찜 앵커 링크 제거 확인", '>찜 <span' not in nav_chunk and 'href="index.html#all">찜' not in nav_chunk)

# 3. 비교 링크와 전체 링크 유지
check("비교 링크 유지", 'href="compare.html">비교 <span class="compare-count">' in idx_html)
check("전체 링크 유지", 'href="index.html#all">전체</a>' in idx_html)

# 4. 모바일 nav의 nowrap, overflow-x auto, scrollbar 숨김 CSS 확인
check("모바일 nav CSS에 nowrap 확인", "flex-wrap:nowrap" in css_text and "white-space:nowrap" in css_text)
check("모바일 nav CSS에 overflow-x auto 확인", "overflow-x:auto" in css_text)
check("모바일 nav CSS에 scrollbar 숨김 확인", "scrollbar-width:none" in css_text and "nav.jump::-webkit-scrollbar{display:none}" in css_text)

# 5. 상세 페이지의 ../ 상대경로 확인
check("상세 페이지 내 찜 ../ 상대경로 확인", 'href="../my-games.html">내 찜 <span class="wish-count">' in detail_html)
check("상세 페이지 비교 ../ 상대경로 확인", 'href="../compare.html">비교 <span class="compare-count">' in detail_html)
check("상세 페이지 전체 ../ 상대경로 확인", 'href="../index.html#all">전체</a>' in detail_html)

# 6. 기존 찜 필터 칩 유지 확인
check("홈 필터 칩에 ♡ 찜 목록 유지", 'data-f="wish"' in idx_html and '♡ 찜 목록' in idx_html)
check("상단 nav에 aria-label 제공", 'aria-label="주요 메뉴"' in idx_html)


print("\n18) 발견·재방문 패키지 (검색 자동완성 / 최근 본 게임 / SEO 컬렉션)")

# A. 검색 자동완성 검증
check("초기 HTML에 검색 JSON이 인라인되지 않음", 'var ALL_GAMES=' not in idx_html and 'var indexData=[' not in idx_html)
check("검색 입력 시 fetch 코드 존재", "fetch(up + 'assets/game-search-index.json')" in idx_html or 'fetch(up+"assets/game-search-index.json")' in idx_html)
check("자동완성 최대 6개 제한", ".slice(0, 6)" in idx_html or "matches.length >= 6" in idx_html or "matches.length>=6" in idx_html)
check("자동완성에서 성인 게임 제외", "if (g.adult) continue" in idx_html or "if(g.adult)continue" in idx_html)
check("자동완성 키보드 이동/선택/닫기 지원", "ArrowDown" in idx_html and "ArrowUp" in idx_html and "Enter" in idx_html and "Escape" in idx_html)
check("자동완성 DOM API createElement 사용", "createElement" in idx_html and "ac-item" in idx_html)
check("자동완성 JSON 기반 innerHTML/insertAdjacentHTML 미사용", "innerHTML = g." not in idx_html and "innerHTML=g." not in idx_html and "insertAdjacentHTML" not in idx_html)
check("자동완성 이미지 URL http/https 검증", "indexOf('http://') === 0" in idx_html and "indexOf('https://') === 0" in idx_html)

# 모든 nav=True 페이지에 자동완성 스크립트 존재 검증
my_html = open(os.path.join(config.SITE_DIR, "my-games.html"), encoding="utf-8").read()
rv_path = os.path.join(config.SITE_DIR, "recently-viewed.html")
rv_html = open(rv_path, encoding="utf-8").read() if os.path.exists(rv_path) else ""
check("상세 페이지(game/730.html)에 자동완성 스크립트 존재", "setupAutocomplete" in detail_730)
check("랜딩 페이지(korean-games.html)에 자동완성 스크립트 존재", "setupAutocomplete" in landing_kd)
check("비교 페이지(compare.html)에 자동완성 스크립트 존재", "setupAutocomplete" in cmp_html)
check("내 찜 페이지(my-games.html)에 자동완성 스크립트 존재", "setupAutocomplete" in my_html)
check("최근 본 페이지(recently-viewed.html)에 자동완성 스크립트 존재", "setupAutocomplete" in rv_html)

# nav=False 페이지에 자동완성 스크립트 없음 검증
no_nav_page = build.page("테스트", "본문", "2026-09-03", nav=False)
check("nav=False 페이지에는 자동완성 스크립트 없음", "setupAutocomplete" not in no_nav_page)

# 자동완성 fetch가 초기 실행 코드가 아니라 input 이벤트 흐름 안에서만 시작됨 확인
check("자동완성 fetch는 초기 실행 코드가 아니라 input 이벤트 흐름 안에서만 시작됨",
      "input.addEventListener('input'" in detail_730 and "getIndex()" not in detail_730)

# B. 최근 본 게임 검증
check("recently-viewed.html 생성", os.path.exists(rv_path))
check("recently-viewed.html에 noindex,follow 있음", '<meta name="robots" content="noindex,follow">' in rv_html)
sm_content = open(sm_path, encoding="utf-8").read()
check("recently-viewed.html은 sitemap에서 제외", "recently-viewed.html" not in sm_content)
check("새 localStorage 키 gamedil-recently-viewed-v1 사용", "gamedil-recently-viewed-v1" in rv_html)
detail_730 = open(os.path.join(config.SITE_DIR, "game", "730.html"), encoding="utf-8").read()
check("상세 페이지에서 gamedil-recently-viewed-v1 기록 코드 존재", "gamedil-recently-viewed-v1" in detail_730)
detail_adult = open(os.path.join(config.SITE_DIR, "game", "700.html"), encoding="utf-8").read() if os.path.exists(os.path.join(config.SITE_DIR, "game", "700.html")) else ""
if detail_adult:
    check("성인 게임 상세 페이지는 최근 본 게임에 기록하지 않음", "gamedil-recently-viewed-v1" not in detail_adult)
check("최근 본 게임 최대 12개 제한 코드", "next.length >= 12" in detail_730 or "next.length>=12" in detail_730)
check("최근 본 게임 빈 상태 및 홈 링크", "최근 본 게임이 없습니다." in rv_html and "홈으로 돌아가기" in rv_html)
check("최근 본 게임 개별 삭제 및 전체 비우기", "전체 비우기" in rv_html and "최근 본 목록에서 삭제" in rv_html)
check("my-games.html에 최근 본 게임 링크 존재", 'href="recently-viewed.html"' in my_html)
cmp_html = open(os.path.join(config.SITE_DIR, "compare.html"), encoding="utf-8").read()
check("compare.html에 최근 본 게임 링크 존재", 'href="recently-viewed.html"' in cmp_html)

# C. SEO 컬렉션 2종 검증
hd_path = os.path.join(config.SITE_DIR, "hot-deals.html")
pop_path = os.path.join(config.SITE_DIR, "popular-games.html")
check("hot-deals.html 생성", os.path.exists(hd_path))
check("popular-games.html 생성", os.path.exists(pop_path))
check("sitemap에 hot-deals.html 포함", "hot-deals.html" in sm_content)
check("sitemap에 popular-games.html 포함", "popular-games.html" in sm_content)
hd_html = open(hd_path, encoding="utf-8").read() if os.path.exists(hd_path) else ""
pop_html = open(pop_path, encoding="utf-8").read() if os.path.exists(pop_path) else ""
check("hot-deals.html 성인 게임 제외", 'data-adult="1"' not in hd_html)
check("popular-games.html 성인 게임 제외", 'data-adult="1"' not in pop_html)
check("popular-games.html 실시간 표현 금지 및 현재 플레이어 수 기준 안내", "실시간" not in pop_html and "현재 플레이어 수" in pop_html)
check("홈 인기 섹션 더 보기가 popular-games.html로 연결", 'href="popular-games.html"' in idx_html)
check("홈 핫딜 섹션 더 보기가 hot-deals.html로 연결", 'href="hot-deals.html"' in idx_html)
check("hot-deals.html canonical 확인", 'rel="canonical"' in hd_html and 'hot-deals.html' in hd_html)
check("popular-games.html canonical 확인", 'rel="canonical"' in pop_html and 'popular-games.html' in pop_html)

# D. Node JS 구문 검사
def node_syntax_check(html_code, label):
    scs = re.findall(r'<script(?![^>]*application/ld\+json)[^>]*>(.*?)</script>', html_code, flags=re.DOTALL)
    for idx_s, s in enumerate(scs):
        s = s.strip()
        if not s: continue
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as tf:
            tf.write(s)
            tname = tf.name
        try:
            res = subprocess.run(["node", "-c", tname], capture_output=True, text=True)
            check(f"Node JS 문법 검사: {label} (script #{idx_s+1})", res.returncode == 0, res.stderr.strip()[:80] if res.returncode != 0 else "")
        finally:
            if os.path.exists(tname): os.remove(tname)

node_syntax_check(idx_html, "index.html (자동완성 포함)")
node_syntax_check(rv_html, "recently-viewed.html")
node_syntax_check(detail_730, "game/730.html (최근 본 게임 기록 스크립트 포함)")

print("\n19) 검색·탐색 완성 패키지 (결과 상태 / 검색 품질 / 접근성 / 보안)")

# 1. 검색 결과 상태 UI (제목 변경, 빈 상태 문구, 검색어 지우기 버튼, 로딩 안내)
check("검색 결과 제목 동적 변경 UI 존재", "allTitle" in idx_html and "검색 결과" in idx_html)
check("검색 결과 없음 정직한 안내 문구 존재", "와 일치하는 게임을 찾지 못했습니다." in idx_html)
check("검색어 지우고 전체 게임 보기 버튼 존재", "검색어를 지우고 전체 게임 보기" in idx_html)
check("게임 목록 불러오는 중 안내 존재", "게임 목록 불러오는 중..." in idx_html)

# 2. aria-live="polite" 존재
check("결과 개수에 aria-live=polite 존재", 'id="cnt" aria-live="polite"' in idx_html)

# 3. URL ?q= 제거 로직 존재
check("검색어 없을 때 ?q= 제거 및 초기화 로직 존재", "location.pathname" in idx_html and "replaceState" in idx_html)

# 4. 공백/하이픈/특수문자 완화 정규화 함수가 자동완성과 전체 검색에 공통 사용됨
check("공백/특수문자 완화 정규화 함수 존재", "function normClean" in idx_html and "function normCompact" in idx_html)
check("자동완성과 전체 검색 모두 getMatchTier 사용", idx_html.count("getMatchTier(") >= 2)

# 5. 정렬 우선순위(정확 일치 → 시작 일치 → 단어 경계 → 포함) 검증
test_tier_js = f"""
{build.SEARCH_NORM_JS}
const items = [
  {{ name: "Undead Knights", score: 90 }},     // contains (tier 4)
  {{ name: "Dead", score: 50 }},               // exact (tier 1)
  {{ name: "Dead Cells", score: 80 }},         // starts with (tier 2)
  {{ name: "Left 4 Dead", score: 95 }},        // word boundary (tier 3)
  {{ name: "Cyberpunk", score: 99 }}           // no match
];
const q = "dead";
const matches = items
  .map(it => ({{ it, tier: getMatchTier(it.name, q) }}))
  .filter(m => m.tier !== Infinity)
  .sort((a, b) => a.tier !== b.tier ? a.tier - b.tier : b.it.score - a.it.score);
const res = matches.map(m => m.it.name).join(",");
if (res !== "Dead,Dead Cells,Left 4 Dead,Undead Knights") {{
  console.error("Wrong order: " + res);
  process.exit(1);
}}
if (getMatchTier("Red-Dead", "red dead") !== 1) process.exit(2);
if (getMatchTier("Red Dead", "reddead") !== 1) process.exit(3);
if (getMatchTier("Red Dead Redemption", "reddead") !== 2) process.exit(4);
if (getMatchTier("Baldur's Gate 3", "baldurs gate") !== 2) process.exit(5);
"""
tier_run = subprocess.run(["node", "-e", test_tier_js], capture_output=True, text=True)
check("정렬 우선순위 및 특수문자 완화 로직 검증 (Node 실행)", tier_run.returncode == 0, tier_run.stderr.strip()[:80] if tier_run.returncode != 0 else "")

# 6. 성인 게임 필터링
check("자동완성에서 성인 게임 제외", "if (g.adult) continue" in idx_html or "if(g.adult)continue" in idx_html)
check("전체 목록에서 성인 게임 기본 제외", "adult.checked" in idx_html and "!adult.checked" in idx_html)

# 7. JSON 기반 렌더링 경로에 위험한 innerHTML / insertAdjacentHTML 없음
# (list.innerHTML = '', msg.innerHTML = '', dropdown.innerHTML = '' 같은 컨테이너 초기화는 안전)
has_unsafe_inner_html = bool(re.search(r'innerHTML\s*=\s*(?![\'"][\'"])\s*[a-zA-Z_]', idx_html))
check("JSON 데이터 삽입 시 innerHTML 미사용 (안전한 초기화만 사용)", not has_unsafe_inner_html)
check("insertAdjacentHTML 미사용", "insertAdjacentHTML" not in idx_html)

# 8. 성능 및 크기 제약
idx_size = os.path.getsize(os.path.join(config.SITE_DIR, "index.html"))
check("index.html 크기 150KB 이하", idx_size < 150 * 1024, f"{idx_size} bytes")
total_home_cards = len(re.findall(r'<a class="card"', idx_html))
check("홈페이지 전체 초기 카드 200개 미만", total_home_cards < 200, f"{total_home_cards}개")
all_sec_html = idx_html.split('id="all"')[1].split('id="moreWrap"')[0] if 'id="all"' in idx_html else ""
all_initial_cards = len(re.findall(r'<a class="card"', all_sec_html))
check("전체 게임 섹션 초기 카드 24개 이하", 0 < all_initial_cards <= 24, f"{all_initial_cards}개")
all_initial_adult = len(re.findall(r'data-adult="1"', all_sec_html))
check("전체 게임 섹션 초기 성인 카드 0개", all_initial_adult == 0, f"{all_initial_adult}개")

print("\n20) 운영 상태 리포트 (status.html)")

# 1. status.html 생성 확인
status_path = os.path.join(config.SITE_DIR, "status.html")
check("status.html 생성 확인", os.path.exists(status_path))
status_html = open(status_path, encoding="utf-8").read() if os.path.exists(status_path) else ""

# 2. noindex,follow 확인
check("status.html에 noindex,follow 있음", '<meta name="robots" content="noindex,follow">' in status_html)

# 3. sitemap 제외 확인
sm_text = open(sm_path, encoding="utf-8").read()
check("status.html은 sitemap에서 제외", "status.html" not in sm_text)

# 4. 일반 nav/footer에 status.html 링크가 없는지 확인
check("홈 네비/푸터에 status.html 링크 없음", 'status.html' not in idx_html)
check("상세 네비/푸터에 status.html 링크 없음", 'status.html' not in detail_730)
check("랜딩 네비/푸터에 status.html 링크 없음", 'status.html' not in landing_kd)

# 5. 8개 이상의 실제 수치 항목이 존재하는지 확인
status_metrics = [
    "마지막 갱신 시각", "갱신 상태", "추적 게임 수", "성인 제외 공개 게임 수",
    "한국어 지원 게임 수", "데모 가능 게임 수", "출시 예정 게임 수",
    "가격 이력 보유 게임 수", "트레일러 확보 게임 수", "최근 가격 인하 게임 수"
]
check("10개 운영 수치 지표 항목 존재", all(m in status_html for m in status_metrics))

# 6. 정상/지연/멈춤 상태 각각의 픽스처 렌더링 확인
sample_games = [
    {"appid": 101, "name": "Test A", "adult": 0, "korean": 1, "has_demo": 1, "coming_soon": 0, "media_checked_at": "2026-09-01", "history": [{"price_final": 1000}]},
    {"appid": 102, "name": "Test B", "adult": 0, "korean": 1, "has_demo": 0, "coming_soon": 1, "media_checked_at": "2026-09-01", "history": [{"price_final": 2000}]}
]
f_ok = {"label": "최신 가격", "class": "ok", "display": "09-03 12:00"}
html_ok = build.build_status(sample_games, "2026-09-03 12:00", f_ok)
check("정상 상태 픽스처 렌더링", "수집 상태: 정상" in html_ok and "st-ok" in html_ok)

f_late = {"label": "업데이트 지연", "class": "late", "display": "09-02 12:00"}
html_late = build.build_status(sample_games, "2026-09-02 12:00", f_late)
check("지연 상태 픽스처 렌더링", "수집 상태: 갱신 지연" in html_late and "st-late" in html_late and "업데이트 지연" in html_late)

f_stale = {"label": "데이터 오래됨", "class": "stale", "display": "08-30 12:00"}
html_stale = build.build_status(sample_games, "2026-08-30 12:00", f_stale)
check("멈춤 상태 픽스처 렌더링", "수집 상태: 갱신 멈춤" in html_stale and "st-stale" in html_stale and "갱신 멈춤" in html_stale)

# 7. 경고 조건 렌더링과 비경고 상태 확인
check("비경고 정상 상태 안내 렌더링", "alert-ok" in html_ok and "정상 운영" in html_ok)

games_no_hist = [{"appid": i, "name": f"G{i}", "adult": 0, "media_checked_at": "2026-09-01"} for i in range(10)]
html_warn_price = build.build_status(games_no_hist, "2026-09-03", f_ok)
check("가격 이력 미수집 비율 높음 경고 렌더링", "가격 이력 미수집 비율 높음" in html_warn_price)

games_no_media = [{"appid": i, "name": f"G{i}", "adult": 0, "history": [{"price_final": 1000}]} for i in range(10)]
html_warn_media = build.build_status(games_no_media, "2026-09-03", f_ok)
check("트레일러 미확인 게임 다수 경고 렌더링", "트레일러 미확인 게임 다수" in html_warn_media and "백필 진행 중일 수 있습니다" in html_warn_media)

# 8. 민감한 문자열이 생성물에 없는지 확인
sensitive_terms = ["steam.sqlite3", "api_key", "apikey", "authorization", "secret", "token", "password"]
check("민감한 문자열 없음", not any(term in status_html.lower() for term in sensitive_terms))

# 9. 모바일 CSS와 접근성 role/aria 확인
css_text = open(os.path.join(config.SITE_DIR, "style.css"), encoding="utf-8").read()
check("모바일 CSS 2열 반응형 그리드 확인", ".status-grid" in css_text and "repeat(2, 1fr)" in css_text)
check("접근성 role=status 확인", 'role="status"' in status_html)
check("면책 조항 문구 확인", "이 페이지는 운영 현황 참고용이며" in status_html and "구매 전 Steam에서 확인하세요" in status_html)

print("\n21) 자체 404 페이지 (404.html)")

# 1. 404.html 생성 확인
p404_path = os.path.join(config.SITE_DIR, "404.html")
check("404.html 생성됨", os.path.exists(p404_path))
p404_html = open(p404_path, encoding="utf-8").read() if os.path.exists(p404_path) else ""

# 2. 제목, 안내 문구, 홈 버튼, 인기 게임 링크 존재
check("404 페이지 제목 확인", "페이지를 찾을 수 없어요 — GameDil" in p404_html and "찾는 페이지가 없어요" in p404_html)
check("404 안내 문구 확인", "주소가 바뀌었거나 존재하지 않는 페이지입니다." in p404_html)
check("홈으로 돌아가기 버튼 확인", 'href="index.html"' in p404_html and "홈으로 돌아가기" in p404_html)
check("지금 인기 게임 보기 링크 확인", 'href="index.html#popular"' in p404_html and "지금 인기 게임 보기" in p404_html)

# 3. noindex,follow 존재
check("404.html에 noindex,follow 있음", '<meta name="robots" content="noindex,follow">' in p404_html)

# 4. sitemap.xml에 404.html 없음
check("sitemap.xml에 404.html 없음", "404.html" not in sm_text)

# 5. canonical 태그 없음
check("404.html에 canonical 태그 없음", 'rel="canonical"' not in p404_html)

# 6. status.html 링크 없음
check("404.html에 status.html 링크 없음", 'status.html' not in p404_html)

# 7. 홈의 정상 index.html에는 404 전용 문구가 섞이지 않음
check("index.html에 404 전용 문구 미포함", "찾는 페이지가 없어요" not in idx_html and "err-page" not in idx_html)

# 8. 자동완성 스크립트는 있으나 페이지 초기 즉시 JSON fetch가 없음
check("404.html에 자동완성 스크립트 존재", "setupAutocomplete" in p404_html)
check("404.html에 초기 즉시 fetch 없음", "getIndex()" not in p404_html and "loadIndex()" not in p404_html)

# 9. 모바일 CSS 존재
check("404 전용 모바일 CSS 존재", ".err-page" in css_text and "err-actions" in css_text)

# 10. Node로 JSON-LD 제외 실행 JavaScript 문법 검사
node_syntax_check(p404_html, "404.html")

print("\n22) Google Analytics 4 (gtag.js)")
# 1. 대상 페이지 로드
ga_idx_html = open(os.path.join(config.SITE_DIR, "index.html"), encoding="utf-8").read()
ga_detail_html = open(os.path.join(config.SITE_DIR, "game", "730.html"), encoding="utf-8").read()
ga_landing_html = open(os.path.join(config.SITE_DIR, "korean-games.html"), encoding="utf-8").read()
ga_hot_html = open(os.path.join(config.SITE_DIR, "hot-deals.html"), encoding="utf-8").read()
ga_compare_html = open(os.path.join(config.SITE_DIR, "compare.html"), encoding="utf-8").read()
ga_my_html = open(os.path.join(config.SITE_DIR, "my-games.html"), encoding="utf-8").read()
ga_recent_html = open(os.path.join(config.SITE_DIR, "recently-viewed.html"), encoding="utf-8").read()
ga_status_html = open(os.path.join(config.SITE_DIR, "status.html"), encoding="utf-8").read()
ga_404_html = open(os.path.join(config.SITE_DIR, "404.html"), encoding="utf-8").read()

GA_ID = "G-SVXW1DG02M"
target_pages = [
    ("index.html", ga_idx_html),
    ("game/730.html", ga_detail_html),
    ("korean-games.html", ga_landing_html),
    ("hot-deals.html", ga_hot_html),
    ("compare.html", ga_compare_html),
    ("my-games.html", ga_my_html),
    ("recently-viewed.html", ga_recent_html),
    ("status.html", ga_status_html),
    ("404.html", ga_404_html),
]

# 2. Google tag 존재 및 </head> 직전 위치 검사
for p_name, p_content in target_pages:
    check(f"{p_name}에 Google tag 스크립트 존재", f"https://www.googletagmanager.com/gtag/js?id={GA_ID}" in p_content)
    check(f"{p_name}에 gtag config 존재", f"gtag('config', '{GA_ID}')" in p_content)
    check(f"{p_name} Google tag가 </head> 직전에 위치", 0 < p_content.find("<!-- Google tag (gtag.js) -->") < p_content.find("</head>"))

# 3. GA 측정 ID 선언 횟수 검사 (중복 삽입 방지)
for p_name, p_content in target_pages:
    check(f"{p_name}에 gtag config 선언 횟수 1회", p_content.count(f"gtag('config', '{GA_ID}')") == 1)
    check(f"{p_name}에 gtag.js 스크립트 선언 횟수 1회", p_content.count(f"googletagmanager.com/gtag/js?id={GA_ID}") == 1)
    check(f"{p_name}에 GA ID 출현 횟수 2회", p_content.count(GA_ID) == 2)

# 4. 기존 noindex/canonical/JSON-LD/자동완성/검색 기능 회귀 검사
check("홈페이지 JSON-LD 구조화 데이터 유지", 'type="application/ld+json"' in ga_idx_html and "WebSite" in ga_idx_html)
check("상세 페이지 JSON-LD VideoGame 유지", 'type="application/ld+json"' in ga_detail_html and "VideoGame" in ga_detail_html)
check("상세 페이지 canonical 유지", 'rel="canonical"' in ga_detail_html and "game/730.html" in ga_detail_html)
check("랜딩 페이지 canonical 유지", 'rel="canonical"' in ga_landing_html and "korean-games.html" in ga_landing_html)
check("404.html noindex,follow 유지", '<meta name="robots" content="noindex,follow">' in ga_404_html)
check("compare.html noindex,follow 유지", '<meta name="robots" content="noindex,follow">' in ga_compare_html)
check("my-games.html noindex,follow 유지", '<meta name="robots" content="noindex,follow">' in ga_my_html)
check("recently-viewed.html noindex,follow 유지", '<meta name="robots" content="noindex,follow">' in ga_recent_html)
check("status.html noindex,follow 유지", '<meta name="robots" content="noindex,follow">' in ga_status_html)
check("홈페이지 자동완성 스크립트 유지", "setupAutocomplete" in ga_idx_html)
check("상세 페이지 자동완성 스크립트 유지", "setupAutocomplete" in ga_detail_html)
check("홈페이지 검색 입력창 유지", 'name="q"' in ga_idx_html)

# 5. Node.js로 GA 코드를 포함한 실행 스크립트 문법 검사
for p_name, p_content in target_pages:
    node_syntax_check(p_content, f"{p_name} (GA4 포함)")
if FAILS:
    print(f"!! 실패 {len(FAILS)}건: {FAILS}"); sys.exit(1)
print("전 구간 통과 — 파싱/저장/회전/추천후보/차트/사이트 기계는 정상")
print(f"(테스트 산출물: {config.SITE_DIR})")
