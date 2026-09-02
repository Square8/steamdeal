"""가짜 데이터로 수집→저장→추천후보 선정→사이트 생성 전 구간 검증.
스팀 API 없이 기계가 정상인지 확인한다."""
import os, sys, tempfile, datetime as dt
TMP = tempfile.mkdtemp(prefix="steamradar_test_")
os.environ["DB_PATH"] = os.path.join(TMP, "t.sqlite3")
os.environ["SITE_DIR"] = os.path.join(TMP, "site")

import config, store, build, steam
import requests

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
check("첫 화면 명제", "지금 살 만한 것부터" in h)
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
import re
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

print()
if FAILS:
    print(f"!! 실패 {len(FAILS)}건: {FAILS}"); sys.exit(1)
print("전 구간 통과 — 파싱/저장/회전/추천후보/차트/사이트 기계는 정상")
print(f"(테스트 산출물: {config.SITE_DIR})")
