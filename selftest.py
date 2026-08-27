"""가짜 데이터로 수집→저장→방송후보 선정→사이트 생성 전 구간 검증.
스팀 API 없이 기계가 정상인지 확인한다."""
import os, sys, tempfile, datetime as dt
TMP = tempfile.mkdtemp(prefix="steamradar_test_")
os.environ["DB_PATH"] = os.path.join(TMP, "t.sqlite3")
os.environ["SITE_DIR"] = os.path.join(TMP, "site")

import config, store, build, steam
import requests

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
    "demos": [{"appid": 731, "description": ""}]}}}
app = with_fake(payload, lambda: steam.fetch_app(730))
check("파싱 성공", app is not None)
check("가격 원 단위(센트→원)", app["price_final"] == 33000, str(app["price_final"]))
check("정가 원 단위", app["price_initial"] == 66000, str(app["price_initial"]))
check("한국어 지원 감지", app["korean"] == 1)
check("데모 감지", app["has_demo"] == 1 and app["demo_appid"] == 731)
check("장르 추출", app["genres"] == "액션, 인디", app["genres"])
check("한국어 출시일 파싱", app["release_date"] == "2026-08-26", str(app["release_date"]))
check("출시예정 아님", app["coming_soon"] == 0)

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

print("\n5) 정가는 스팀 값을 쓴다 (관측 최고가로 추정하지 않음)")
games = store.all_games(conn)
g = next(x for x in games if x["appid"] == 730)
check("정가 66,000 유지", g["price_initial"] == 66000, str(g["price_initial"]))
check("현재가 33,000", g["price_final"] == 33000, str(g["price_final"]))

print("\n6) 역대최저 표기 정직성")
check("관측 1일은 신뢰 안 함", g["atl_trustworthy"] is False, f'{g["days_tracked"]}일')
for i in range(1, config.MIN_DAYS_FOR_ATL + 2):
    d = (dt.date(2026, 1, 1) + dt.timedelta(days=i)).isoformat()
    conn.execute("INSERT OR REPLACE INTO prices VALUES (730,?,40000,66000,39)", (d,))
conn.commit()
g2 = next(x for x in store.all_games(conn) if x["appid"] == 730)
check(f"관측 {config.MIN_DAYS_FOR_ATL}일 넘으면 신뢰", g2["atl_trustworthy"] is True,
      f'{g2["days_tracked"]}일')
check("최저가 계산", g2["lowest_seen"] == 33000, str(g2["lowest_seen"]))

print("\n7) 방송 후보 선정")
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

print("\n7c) 방송 점수")
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

print("\n8) 차트")
sp = build.sparkline(g2["history"])
check("스파크라인 SVG", sp.startswith("<svg") and "polyline" in sp)
check("이력 없으면 평선", "polyline" not in build.sparkline([]))
ch = build.detail_chart(g2["history"], g2["lowest_seen"])
check("상세 차트", "<svg" in ch and 'class="tip"' in ch)
check("눈금값 중복 없음", len(build.nice_ticks(1000, 1000.4)) == len(set(build.nice_ticks(1000, 1000.4))))

print("\n9) 사이트 생성")
conn.close()
rc = build.main()
check("build.main() 정상", rc == 0, f"rc={rc}")
idx = os.path.join(config.SITE_DIR, "index.html")
h = open(idx, encoding="utf-8").read()
check("index 생성", os.path.exists(idx))
check("방송 후보 섹션", "이번 주 방송 후보" in h)
check("데모 섹션", "데모로 먼저 해볼 수 있는 게임" in h)
check("히어로(오늘 하나) 존재", 'class="hero"' in h and "오늘 가장 방송할 만한" in h)
check("3중 테마 스코프", all(x in h for x in
      [":root{", ':root:not([data-theme="light"])', ':root[data-theme="dark"]']))
check("칩에 글자 포함(색 단독 아님)", "데모</span>" in h)
check("필터 컨트롤", 'data-f="demo"' in h and 'data-f="kr"' in h)
check("정렬 컨트롤", 'id="sort"' in h and 'value="cheap"' in h)
check("성인 포함 토글", 'id="adult"' in h)
check("점수 막대에 숫자 병기", 'class="score-n"' in h)
check("개발자용 문구 노출 없음", "config.py" not in h)
check("상세 페이지 생성", os.path.exists(os.path.join(config.SITE_DIR, "game", "730.html")))

print("\n9b) 중복 노출 / 이미지 자리표시 / 빈 그래프 안내")
import re as _re
# 히어로에 쓴 게임이 바로 아래 '방송 후보' 그리드에 또 나오지 않아야 한다
hero_block = h.split('<section id="pick"')[0]
pick_block = h.split('<section id="pick"')[1].split("</section>")[0]
hero_ids = set(_re.findall(r'./game/(\d+)\.html', hero_block))
pick_ids = set(_re.findall(r'./game/(\d+)\.html', pick_block))
check("히어로 게임이 아래 섹션에서 중복되지 않음",
      not (hero_ids & pick_ids), f"겹침={hero_ids & pick_ids}")
check("데모가 있으면 데모 섹션이 비지 않음",
      "데모가 있는 게임이 아직 수집되지 않았습니다" not in h)
# hidden 속성이 실제로 먹는지. .card 가 display:flex 라서 이 규칙이 없으면
# 검색·필터·성인숨김이 전부 무효가 된다 (실제로 났던 버그)
check("[hidden] 규칙이 있어 필터가 실제로 숨긴다",
      "[hidden]{display:none !important}" in h)
noimg = {"appid": 4242, "name": "표지없음", "history": []}
check("이미지 없으면 머리글자 자리표시", 'class="ph"' in build.shot(noimg))
d1 = open(os.path.join(config.SITE_DIR, "game", "9.html"), encoding="utf-8").read()
check("이력 1건이면 빈 그래프 대신 안내문", 'class="waiting"' in d1 and "<svg" not in
      d1.split('원화 가격 추이')[1].split('</div>')[0])

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
print("전 구간 통과 — 파싱/저장/회전/방송후보/차트/사이트 기계는 정상")
print(f"(테스트 산출물: {config.SITE_DIR})")
