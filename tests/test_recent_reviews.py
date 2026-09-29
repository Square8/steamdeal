"""최근 30일 평가 — 수집(steam.py) · 저장/순환(store.py) · 예산(collect.py) · 표시(build.py) 검증.

네트워크 없음: steam._get_json 을 가짜 Steam appreviews 서버로 바꿔 cursor·경계·실패를 재현한다.
운영 DB·site/ 미사용(임시 DB_PATH/SITE_DIR). 실제 build.main() 산출 HTML로 표시를 판정한다.
실행: python3 tests/test_recent_reviews.py  (exit 0 = FAIL 없음)
"""
import os
import re
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)
TMP = tempfile.mkdtemp(prefix="gamedil_recent_qa_")
os.environ["DB_PATH"] = os.path.join(TMP, "fixture.sqlite3")
os.environ["SITE_DIR"] = os.path.join(TMP, "site")

import config  # noqa: E402
import steam  # noqa: E402
import store  # noqa: E402

FAILS = []
DAY = 86400
NOW = 1_790_000_000


def check(label, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {label}" + (f"  ({detail})" if detail else ""))
    if not cond:
        FAILS.append(label)


def rv(rid, age_sec, up=True):
    return {"recommendationid": str(rid), "timestamp_created": NOW - age_sec, "voted_up": up}


class FakeSteam:
    """cursor -> (reviews, next_cursor) 또는 None(요청 실패) / dict(원본 응답)."""

    def __init__(self, pages):
        self.pages, self.calls = pages, []

    def __call__(self, url, params=None, delay=None):
        self.calls.append(dict(params or {}))
        page = self.pages.get(params.get("cursor"))
        if page is None or isinstance(page, dict):
            return page
        reviews, nxt = page
        body = {"success": 1, "reviews": reviews}
        if nxt is not ...:
            body["cursor"] = nxt
        return body


def run(pages, **kw):
    fake = FakeSteam(pages)
    steam._get_json = fake
    return steam.fetch_recent_reviews(730, now_ts=NOW, **kw), fake


def fetch_tests():
    print("\n[수집: 경계·비율·cursor·종료·한도·실패]")
    d30 = config.RECENT_REVIEW_DAYS * DAY
    r, f = run({"*": ([rv(1, 0), rv(2, d30 - 1), rv(3, d30), rv(4, d30 + 1), rv(5, d30 + 5)], "c1")})
    check("경계: 방금·30일 직전·정확히 30일 포함, 30일+1초 제외", r["total"] == 3, str(r))
    check("오래된 리뷰를 만나면 complete로 종료, 다음 페이지 요청 안 함",
          r["status"] == "complete" and len(f.calls) == 1, f"{r['status']} calls={len(f.calls)}")
    p = f.calls[0]
    check("요청: filter=recent, language=all, cursor=*, day_range 미사용",
          p.get("filter") == "recent" and p.get("language") == "all" and p.get("cursor") == "*"
          and "day_range" not in p, str(p))

    r, _ = run({"*": ([rv(i, 100 + i, i <= 7) for i in range(1, 11)] + [rv(99, d30 + 10)], "c1")})
    check("긍정 7 / 전체 10 (voted_up 기준)", r["positive"] == 7 and r["total"] == 10, str(r))

    per = config.RECENT_REVIEW_PER_PAGE
    p1 = [rv(i, 1000 + i) for i in range(per)]
    p2 = [rv(per + i, 2000 + i, i % 2 == 0) for i in range(per)]
    p3 = [rv(2 * per + i, 3000 + i) for i in range(5)] + [rv(9999, d30 + 1)]
    r, f = run({"*": (p1, "c1"), "c1": (p2, "c2"), "c2": (p3, "c3")})
    exp_pos = per + per // 2 + 5
    check("여러 페이지 cursor 순서(*→c1→c2)", [c["cursor"] for c in f.calls] == ["*", "c1", "c2"],
          str([c["cursor"] for c in f.calls]))
    check("3쪽 합산: 전체 205 / 긍정 155, complete",
          r["total"] == 2 * per + 5 and r["positive"] == exp_pos and r["status"] == "complete", str(r))

    r, _ = run({"*": (p1[:3], "c1"), "c1": ([], "c2")})
    check("빈 페이지 = 리뷰 끝 → complete(3개)", r["status"] == "complete" and r["total"] == 3, str(r))
    r, _ = run({"*": (p1[:3], "*")})
    check("리뷰가 남은 응답에서 cursor 반복 → error(불완전)", r["status"] == "error", str(r))
    r, _ = run({"*": (p1, "c1"), "c1": (p2[:5], "c1")})
    check("2쪽째에서 cursor 반복(경계 미도달) → error", r["status"] == "error", str(r))
    r, _ = run({"*": (p1[:3] + [p1[0]], "c1"), "c1": ([p1[1], rv(5555, d30 + 1)], "c2")})
    check("중복 recommendationid는 한 번만 셈", r["total"] == 3, str(r))

    endless = {("*" if i == 0 else f"c{i}"): ([rv(10_000 + i * 10 + j, 50 + i) for j in range(10)], f"c{i + 1}")
               for i in range(config.RECENT_REVIEW_MAX_PAGES + 5)}
    r, f = run(endless)
    check("게임당 페이지 한도 도달 → limit(불완전), 요청 수 = 한도",
          r["status"] == "limit" and len(f.calls) == config.RECENT_REVIEW_MAX_PAGES, f"{r['status']} {len(f.calls)}")
    r, f = run(endless, page_budget=3)
    check("실행 예산 3 → budget(불완전), 요청 3회", r["status"] == "budget" and len(f.calls) == 3,
          f"{r['status']} {len(f.calls)}")

    r, _ = run({"*": (p1, "c1"), "c1": None})
    check("2쪽째 요청 실패 → error", r["status"] == "error", str(r["status"]))
    r, _ = run({"*": {"success": 2}})
    check("success!=1 → error", r["status"] == "error")
    r, _ = run({"*": ([{"recommendationid": "1", "timestamp_created": NOW}], "c1")})
    check("voted_up 누락 → error", r["status"] == "error")
    r, _ = run({"*": (p1[:3], ...)})
    check("다음 cursor 없음(다음 여부 불명) → error", r["status"] == "error")


def fixture_db():
    if os.path.exists(config.DB_PATH):
        os.remove(config.DB_PATH)
    conn = store.connect()

    def add(appid, name, total=500, kr=1, soon=0, **extra):
        pos = int(total * 0.9)
        conn.execute(
            "INSERT INTO games (appid,name,app_type,korean,coming_soon,review_positive,review_negative,"
            "review_count,review_score,review_desc,first_seen,last_seen,checked_at,price_first,price_last)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (appid, name, "game", kr, soon, pos, total - pos, total, 8, "Very Positive",
             "2026-08-01", "2026-09-20", "2026-09-20", "2026-08-01", "2026-09-20"))
        for k, v in extra.items():
            conn.execute(f"UPDATE games SET {k}=? WHERE appid=?", (v, appid))
        conn.execute("INSERT INTO prices VALUES (?,?,?,?,?)", (appid, "2026-09-20", 10000, 10000, 0))
    return conn, add


def store_collect_tests():
    print("\n[저장·순환·예산]")
    import collect
    conn, add = fixture_db()
    now = datetime.now(timezone.utc)
    iso = lambda dt: dt.isoformat(timespec="seconds")
    add(1, "신규후보")
    add(2, "리뷰부족", total=20)
    add(3, "한국어없음", kr=0)
    add(4, "출시예정", soon=1)
    add(5, "방금시도", recent_review_attempt_at=iso(now - timedelta(hours=5)), recent_review_status="complete")
    add(6, "오래전시도", recent_review_attempt_at=iso(now - timedelta(days=4)), recent_review_status="complete")
    add(7, "한도쿨다운중", recent_review_attempt_at=iso(now - timedelta(days=3)), recent_review_status="limit")
    add(8, "한도쿨다운끝", recent_review_attempt_at=iso(now - timedelta(days=8)), recent_review_status="limit")
    conn.commit()
    ids = store.recent_review_appids(conn, 50)
    check("후보 = 신규(1)·오래전(6)·쿨다운 끝난 한도(8), 신규 먼저", ids[:1] == [1] and set(ids) == {1, 6, 8}, str(ids))

    store.save_recent_reviews(conn, 1, {"status": "complete", "total": 40, "positive": 30, "now_ts": int(now.timestamp())})
    before = dict(conn.execute("SELECT * FROM games WHERE appid=1").fetchone())
    for st in ("error", "limit", "budget"):
        store.save_recent_reviews(conn, 1, {"status": st, "total": 3, "positive": 0, "now_ts": int(now.timestamp())})
        row = dict(conn.execute("SELECT * FROM games WHERE appid=1").fetchone())
        check(f"{st} 시도는 이전 완전 집계(40/30)를 덮지 않고 상태만 기록",
              row["recent_review_total"] == 40 and row["recent_review_positive"] == 30
              and row["recent_review_computed_at"] == before["recent_review_computed_at"]
              and row["recent_review_status"] == st, f"{row['recent_review_total']}/{row['recent_review_status']}")
    store.save_recent_reviews(conn, 6, {"status": "limit", "total": 2000, "positive": 1900, "now_ts": int(now.timestamp())})
    row = dict(conn.execute("SELECT * FROM games WHERE appid=6").fetchone())
    check("한도 도달 게임은 수치 미저장(완전 집계 아님)", row["recent_review_total"] is None, str(row["recent_review_total"]))

    # collect: 예산 소진 시 중단, 기존 전체 평점 칼럼 보존
    conn2, add2 = fixture_db()
    for a in range(101, 111):
        add2(a, f"후보{a}", total=1000 + a)
    conn2.commit()
    overall_before = conn2.execute(
        "SELECT appid,review_positive,review_negative,review_score,review_desc,review_count FROM games ORDER BY appid").fetchall()
    seen = []

    def fake_fetch(appid, now_ts=None, page_budget=None):
        seen.append((appid, page_budget))
        used = min(4, page_budget)
        return {"status": "complete" if used == 4 else "budget", "total": 50, "positive": 45,
                "pages": used, "now_ts": int(now.timestamp())}
    orig_budget, orig_fetch = config.RECENT_REVIEW_PAGE_BUDGET, steam.fetch_recent_reviews
    config.RECENT_REVIEW_PAGE_BUDGET, steam.fetch_recent_reviews = 10, fake_fetch

    class L:
        def info(self, *a): pass
        warning = info
    try:
        st = collect._collect_recent_reviews(conn2, L())
    finally:
        config.RECENT_REVIEW_PAGE_BUDGET, steam.fetch_recent_reviews = orig_budget, orig_fetch
    check("예산 10: 4+4+2(budget)에서 멈춤, 남은 예산을 다음 게임에 전달",
          [b for _, b in seen] == [10, 6, 2] and st["pages"] == 10 and st["complete"] == 2 and st["budget"] == 1,
          f"{seen} {st}")
    stored = conn2.execute("SELECT COUNT(*) FROM games WHERE recent_review_total IS NOT NULL").fetchone()[0]
    check("완전 집계 2건만 수치 저장(예산 소진 게임 제외)", stored == 2, str(stored))
    overall_after = conn2.execute(
        "SELECT appid,review_positive,review_negative,review_score,review_desc,review_count FROM games ORDER BY appid").fetchall()
    check("기존 전체 평점 칼럼(긍정/부정/등급/리뷰수) 보존", [tuple(r) for r in overall_before] == [tuple(r) for r in overall_after])

    # 연속 실패 차단: Steam 장애 시 후보 전체를 돌며 시간을 태우지 않는다
    conn3, add3 = fixture_db()
    for a in range(301, 311):
        add3(a, f"장애{a}", total=1000 + a)
    conn3.commit()
    calls = []

    def failing(appid, now_ts=None, page_budget=None):
        calls.append(appid)
        return {"status": "error", "total": 0, "positive": 0, "pages": 1}
    steam.fetch_recent_reviews = failing
    try:
        st3 = collect._collect_recent_reviews(conn3, L())
    finally:
        steam.fetch_recent_reviews = orig_fetch
    check(f"연속 실패 {config.RECENT_REVIEW_MAX_CONSECUTIVE_ERRORS}회에서 중단(10개 전부 시도 안 함)",
          len(calls) == config.RECENT_REVIEW_MAX_CONSECUTIVE_ERRORS and st3["error"] == len(calls), str(calls))
    stored3 = conn3.execute("SELECT COUNT(*) FROM games WHERE recent_review_total IS NOT NULL").fetchone()[0]
    check("실패 게임은 수치 미저장, 상태만 error", stored3 == 0 and conn3.execute(
        "SELECT COUNT(*) FROM games WHERE recent_review_status='error'").fetchone()[0] == len(calls))
    conn.close()
    conn2.close()
    conn3.close()


def detail(site, appid):
    return open(os.path.join(site, "game", f"{appid}.html"), encoding="utf-8").read()


def recent_row(h):
    m = re.search(r"<tr><th>최근 30일 평가</th><td>(.*?)</td></tr>", h, re.S)
    return m.group(1) if m else None


def build_tests():
    print("\n[표시: 실제 build.main() 상세 페이지]")
    import build
    now = datetime.now(timezone.utc)
    iso = lambda dt: dt.isoformat(timespec="seconds")
    cases = {
        201: dict(recent_review_total=1635, recent_review_positive=1553, recent_review_computed_at=iso(now - timedelta(hours=2))),
        202: dict(recent_review_total=3, recent_review_positive=3, recent_review_computed_at=iso(now - timedelta(hours=2))),
        203: dict(recent_review_total=0, recent_review_positive=0, recent_review_computed_at=iso(now - timedelta(hours=2))),
        204: dict(recent_review_status="error", recent_review_attempt_at=iso(now)),
        205: dict(recent_review_total=500, recent_review_positive=450, recent_review_computed_at=iso(now - timedelta(days=10))),
        206: dict(recent_review_status="limit", recent_review_attempt_at=iso(now)),
        207: dict(recent_review_total=10, recent_review_positive=12, recent_review_computed_at=iso(now - timedelta(hours=2))),
    }

    def make(with_recent, site):
        conn, add = fixture_db()
        for a, extra in cases.items():
            add(a, f"게임{a}", total=2000, **(extra if with_recent else {}))
        conn.commit()
        conn.close()
        config.SITE_DIR = site
        config.SITE_URL = "https://gamedil.com"
        build.main()

    site_a, site_b = os.path.join(TMP, "site_recent"), os.path.join(TMP, "site_plain")
    make(True, site_a)
    make(False, site_b)
    row = recent_row(detail(site_a, 201))
    check("정상: '긍정 95% · 1,635개' 표시", row is not None and "긍정 95% · 1,635개" in row, str(row)[:120])
    check("정상: 집계일 표시", row is not None and "일 집계" in row)
    check("업데이트 가능성 안내는 있되 원인 단정 표현 없음",
          row is not None and "업데이트" in row and "원인은 판단하지 않습니다" in row
          and not any(w in row for w in ("때문", "탓", "원인입니다")), str(row)[-120:] if row else "")
    h = detail(site_a, 201)
    check("전체 Steam 평가 행이 최근 평가 행보다 먼저(보조 정보)",
          0 < h.find("<th>Steam 평가</th>") < h.find("<th>최근 30일 평가</th>"))
    row = recent_row(detail(site_a, 202))
    check("표본 3개(<최소 표본): '최근 평가 표본 적음 · 3개', 긍정률 미표시",
          row is not None and "최근 평가 표본 적음 · 3개" in row and "%" not in row, str(row)[:120])
    for a, why in ((203, "0개 완전 집계"), (204, "수집 실패만 있음"), (205, "10일 지난 집계"),
                   (206, "페이지 한도(불완전)"), (207, "긍정>전체 모순값")):
        check(f"{why} → 최근 30일 행 생략(0%/0개 미표시)", recent_row(detail(site_a, a)) is None,
              str(recent_row(detail(site_a, a)))[:80])
    same = all(re.sub(r"<tr><th>최근 30일 평가</th><td>.*?</td></tr>", "", detail(site_a, a), flags=re.S)
               .replace(site_a, "") == detail(site_b, a).replace(site_b, "") for a in cases)
    check("최근 행을 빼면 상세 HTML이 기존과 동일(전체 평점·다른 표시 보존)", same)
    check("모든 상세 페이지에 기존 'Steam 평가' 행 유지",
          all("<th>Steam 평가</th>" in detail(site_a, a) for a in cases))


def repeat_cursor_integration():
    print("\n[통합: cursor 반복 부분 집계는 저장·표시되지 않음]")
    import build
    import collect
    now = datetime.now(timezone.utc)
    conn, add = fixture_db()
    add(401, "반복신규", total=2000)
    add(402, "반복기존값", total=2000, recent_review_total=500, recent_review_positive=450,
        recent_review_computed_at=(now - timedelta(days=4)).isoformat(timespec="seconds"),
        recent_review_attempt_at=(now - timedelta(days=4)).isoformat(timespec="seconds"),
        recent_review_status="complete")
    conn.commit()
    t = int(now.timestamp())
    page = [{"recommendationid": str(i), "timestamp_created": t - 3600 - i, "voted_up": True} for i in range(5)]
    orig = steam._get_json
    steam._get_json = lambda url, params=None, delay=None: {"success": 1, "reviews": page, "cursor": params.get("cursor")}

    class L:
        def info(self, *a): pass
        warning = info
    try:
        st = collect._collect_recent_reviews(conn, L())
    finally:
        steam._get_json = orig
    rows = {r["appid"]: dict(r) for r in conn.execute("SELECT * FROM games WHERE appid IN (401,402)")}
    check("collect 결과: 두 게임 모두 error 로 집계(complete 0)", st["complete"] == 0 and st["error"] == 2, str(st))
    check("신규 게임: 부분 집계(5개) 수치 미저장, 상태 error",
          rows[401]["recent_review_total"] is None and rows[401]["recent_review_positive"] is None
          and rows[401]["recent_review_computed_at"] is None and rows[401]["recent_review_status"] == "error",
          str({k: rows[401][k] for k in rows[401] if k.startswith("recent")}))
    check("기존 완전 집계 게임: 이전 값(500/450, 집계 시각) 유지, 부분값으로 덮지 않음",
          rows[402]["recent_review_total"] == 500 and rows[402]["recent_review_positive"] == 450
          and rows[402]["recent_review_status"] == "error", f"{rows[402]['recent_review_total']}")
    conn.close()
    config.SITE_DIR = os.path.join(TMP, "site_repeat")
    config.SITE_URL = "https://gamedil.com"
    build.main()
    r401 = recent_row(detail(config.SITE_DIR, 401))
    check("상세 페이지: 부분 집계 게임은 최근 30일 행 없음(5개·100% 미표시)", r401 is None, str(r401)[:80])
    r402 = recent_row(detail(config.SITE_DIR, 402))
    check("상세 페이지: 기존 완전 집계는 그대로 90% · 500개", r402 is not None and "긍정 90% · 500개" in r402
          and "5개" not in r402.split("·")[-1].split("(")[0], str(r402)[:80])


def main():
    for fn in (fetch_tests, store_collect_tests, build_tests, repeat_cursor_integration):
        try:
            fn()
        except Exception as e:
            import traceback
            traceback.print_exc()
            check(f"{fn.__name__} 실행 중 예외 없음", False, repr(e)[:200])
    print(f"\n결과: FAIL {len(FAILS)}  (산출물: {TMP})")
    for f in FAILS:
        print("  - FAIL:", f)
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
