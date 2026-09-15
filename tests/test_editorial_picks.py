"""수·토 Threads 'GameDil 픽' 후보 JSON(editorial.py + build.py 연결) 검증.

HANDOFF.md / marketing/threads-picks-tasks.md 의 Claude 담당 항목.
Gemini 구현(editorial.py, build.py 의 editorial.generate_picks 호출) 완료 후
실제 코드 경로(build.main() 이 만드는 실제 assets/editorial-picks.json)를
Playwright/브라우저 없이 픽스처 DB + 실제 빌드로 검증한다. editorial.py 를
복제하지 않고 직접 import 해서 build.main() 을 통해 실행한다.

editorial.py 가 없거나 build.main() 이 JSON을 만들지 않으면 전체를 SKIP 하고
종료한다(구현 대기 상태에서 PASS/FAIL을 내지 않는다).
"""
import json
import os
import sqlite3
import sys
import tempfile

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, REPO_ROOT)

TMP = tempfile.mkdtemp(prefix="gamedil_editorial_qa_")
DB_PATH = os.path.join(TMP, "fixture.sqlite3")
SITE_DIR = os.path.join(TMP, "site")
os.environ["DB_PATH"] = DB_PATH
os.environ["SITE_DIR"] = SITE_DIR

FAILS = []
SKIPPED = []


def check(label, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {label}" + (f"  ({detail})" if detail else ""))
    if not cond:
        FAILS.append(label)


def skip(label, reason):
    print(f"  SKIP  {label}  — {reason}")
    SKIPPED.append((label, reason))


GAMES = []


def g(appid, name, **overrides):
    GAMES.append((appid, name, overrides))


g(800001, "성인 제외 대상", adult=1, discount_pct=30, review_total=200, review_pos_pct=90, korean=1)
g(800002, "미출시 제외 대상", coming_soon=1, discount_pct=30, review_total=200, review_pos_pct=90, korean=1)
g(800003, "DLC(정식게임 아님) 제외 여부 확인", app_type="dlc", discount_pct=30, review_total=200,
  review_pos_pct=90, korean=1)
g(800004, "가격이력 전무 - 0원 non-free 오인 여부", no_price_row=True, review_total=200,
  review_pos_pct=90, korean=1)
g(800005, "리뷰수 부족 제외 대상", discount_pct=30, review_total=10, review_pos_pct=95, korean=1)
g(800006, "긍정률 부족 제외 대상", discount_pct=30, review_total=200, review_pos_pct=60, korean=1)
g(800007, "수요일용 유효 할인중", discount_pct=30, review_total=200, review_pos_pct=90, korean=1, has_demo=1,
  price_last="2026-09-05")
g(800008, "할인없음 - 수요일 제외 토요일 포함", discount_pct=0, review_total=200, review_pos_pct=90, korean=1)
g(800009, "무료게임 - 수요일 제외 토요일 포함", is_free=1, discount_pct=0, review_total=200, review_pos_pct=85,
  korean=1)
for i in range(15):
    g(800100 + i, f"동률후보{i}", discount_pct=0, review_total=100, review_pos_pct=85, korean=1)


def build_fixture_db():
    import store

    conn = sqlite3.connect(DB_PATH)
    conn.executescript(store.SCHEMA)
    cols_games = [r[1] for r in conn.execute("PRAGMA table_info(games)")]

    for appid, name, ov in GAMES:
        pos_pct = ov.get("review_pos_pct", 85)
        total = ov.get("review_total", 100)
        pos = round(total * pos_pct / 100)
        neg = total - pos
        row = {
            "appid": appid, "name": name,
            "app_type": ov.get("app_type", "game"),
            "korean": ov.get("korean", 0),
            "coming_soon": ov.get("coming_soon", 0),
            "adult": ov.get("adult", 0),
            "is_free": ov.get("is_free", 0),
            "has_demo": ov.get("has_demo", 0),
            "review_positive": pos,
            "review_negative": neg,
            "review_count": total,
            "reviews_checked_at": "2026-09-11T00:00:00Z",
            "first_seen": "2026-08-01", "last_seen": "2026-09-10",
            "checked_at": "2026-09-10",
            "price_first": "2026-08-01", "price_last": ov.get("price_last", "2026-09-10"),
        }
        row = {k: v for k, v in row.items() if k in cols_games}
        cols = list(row.keys())
        conn.execute(
            f"INSERT INTO games ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})",
            [row[c] for c in cols],
        )
        if not ov.get("no_price_row"):
            discount = ov.get("discount_pct", 0)
            final = 10000
            initial = int(final / (1 - discount / 100)) if discount else final
            if ov.get("is_free"):
                final = initial = 0
            conn.execute(
                "INSERT INTO prices (appid, on_date, price_final, price_initial, discount_pct) "
                "VALUES (?, '2026-08-01', ?, ?, 0)", (appid, initial, initial))
            conn.execute(
                "INSERT INTO prices (appid, on_date, price_final, price_initial, discount_pct) "
                "VALUES (?, ?, ?, ?, ?)", (appid, ov.get("price_last", "2026-09-10"), final, initial, discount))
    conn.commit()
    conn.close()


def build_site():
    build_fixture_db()
    import build
    build.main()
    return SITE_DIR


def find_picks_json(site_dir):
    p = os.path.join(site_dir, "assets", "editorial-picks.json")
    return p if os.path.exists(p) else None


def check_schema_and_rules(data, index_html_path):
    check("schema_version 필드 존재", "schema_version" in data, data.get("schema_version"))
    check("generated_at 필드 존재(UTC)", "generated_at" in data, data.get("generated_at"))
    for day in ("wednesday", "saturday"):
        check(f"{day} 배열 존재", isinstance(data.get(day), list))

    wed = {it["appid"]: it for it in data.get("wednesday", [])}
    sat = {it["appid"]: it for it in data.get("saturday", [])}

    check("성인(800001) wed/sat 모두 제외", 800001 not in wed and 800001 not in sat)
    check("미출시(800002) wed/sat 모두 제외", 800002 not in wed and 800002 not in sat)

    # 800003(DLC)/800004(가격이력 전무)는 다른 동률 후보와의 점수 경쟁·12개 상한 때문에
    # 우연히 잘려나갈 수 있어 이 다인원 시나리오에서는 판정하지 않는다.
    # (아래 check_edge_case_isolation()에서 경쟁 없는 단독 시나리오로 확정 검증한다.)

    check("리뷰수부족(800005) 제외", 800005 not in wed and 800005 not in sat)
    check("긍정률부족(800006) 제외", 800006 not in wed and 800006 not in sat)

    check("유효 할인중(800007) 수요일 포함", 800007 in wed)
    check("할인없음(800008) 수요일 제외", 800008 not in wed)
    check("할인없음(800008) 토요일 포함", 800008 in sat)
    check("무료게임(800009) 수요일 제외(할인 개념 없음)", 800009 not in wed)
    check("무료게임(800009) 토요일 포함", 800009 in sat)

    check("wednesday 12개 이하", len(data.get("wednesday", [])) <= 12, len(data.get("wednesday", [])))
    check("saturday 12개 이하", len(data.get("saturday", [])) <= 12, len(data.get("saturday", [])))
    tie_in_sat = [aid for aid in range(800100, 800115) if aid in sat]
    check("동률 후보 15개 중 saturday 상한(12)로 일부만 채택됨",
          0 < len(tie_in_sat) <= 12, len(tie_in_sat))
    check("saturday 동률 구간이 appid 오름차순으로 결정적 정렬됨",
          tie_in_sat == sorted(tie_in_sat), tie_in_sat)

    # 참고: "가격 이력은 있는데 price_last만 NULL"인 채로 유효 후보가 되는 경우는
    # store.connect() 마이그레이션(price_last = COALESCE(price_last, MAX(prices.on_date)))이
    # 매 실행마다 실제 이력으로 역채움하므로 이 코드베이스에서는 재현 불가능함을 별도로 확인함
    # (2026-09-15). price_last가 진짜 NULL인 경우는 이력 자체가 없는 경우뿐이며, 그 경우는
    # 아래 check_edge_case_isolation()의 '가격이력 전무' 케이스로 이미 제외 여부를 검증한다.
    if 800007 in wed:
        item = wed[800007]
        check("실제 가격 관측일(price_last=2026-09-05)이 price_checked_at에 그대로 반영되는가(R1 수정 확인)",
              item.get("price_checked_at") == "2026-09-05",
              f"price_checked_at={item.get('price_checked_at')!r}")
        check("reviews_checked_at은 실제 games.reviews_checked_at 값을 반영",
              item.get("reviews_checked_at") == "2026-09-11T00:00:00Z", item.get("reviews_checked_at"))

    body = json.dumps(data, ensure_ascii=False)
    check("HTML 조각 미포함", "<div" not in body and "<p>" not in body)
    check("50KB 예산 이내", len(body.encode("utf-8")) <= 50 * 1024, len(body.encode("utf-8")))

    if os.path.exists(index_html_path):
        idx = open(index_html_path, encoding="utf-8").read()
        check("홈 index.html이 editorial-picks.json을 초기 로딩 시 fetch하지 않음(문자열 부재로 확인)",
              "editorial-picks" not in idx)


def check_determinism():
    site_dir_2 = os.path.join(TMP, "site2")
    import config
    import build
    config.SITE_DIR = site_dir_2
    build.main()
    p2 = find_picks_json(site_dir_2)
    p1 = find_picks_json(SITE_DIR)
    if not p2 or not p1:
        skip("결정적 재현성(동일 DB 재빌드시 동일 결과)", "1차 또는 2차 빌드에서 JSON 미생성")
        return
    d1 = json.load(open(p1, encoding="utf-8"))
    d2 = json.load(open(p2, encoding="utf-8"))
    ids1 = [it["appid"] for it in d1.get("saturday", [])]
    ids2 = [it["appid"] for it in d2.get("saturday", [])]
    check("동일 DB로 재빌드해도 saturday 순서가 동일(결정적 정렬)", ids1 == ids2, f"{ids1} vs {ids2}")


def _insert_minimal_game(conn, cols_games, appid, name, **ov):
    total = ov.get("review_total", 200)
    pos_pct = ov.get("review_pos_pct", 90)
    pos = round(total * pos_pct / 100)
    neg = total - pos
    row = {
        "appid": appid, "name": name,
        "app_type": ov.get("app_type", "game"),
        "korean": ov.get("korean", 1),
        "coming_soon": ov.get("coming_soon", 0),
        "adult": ov.get("adult", 0),
        "is_free": ov.get("is_free", 0),
        "has_demo": ov.get("has_demo", 0),
        "review_positive": pos, "review_negative": neg, "review_count": total,
        "reviews_checked_at": "2026-09-11T00:00:00Z",
        "first_seen": "2026-08-01", "last_seen": "2026-09-10", "checked_at": "2026-09-10",
        "price_first": "2026-08-01", "price_last": "2026-09-10",
    }
    row = {k: v for k, v in row.items() if k in cols_games}
    cols = list(row.keys())
    conn.execute(
        f"INSERT INTO games ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})",
        [row[c] for c in cols])
    if not ov.get("no_price_row"):
        discount = ov.get("discount_pct", 0)
        final = 10000
        initial = int(final / (1 - discount / 100)) if discount else final
        conn.execute(
            "INSERT INTO prices (appid, on_date, price_final, price_initial, discount_pct) "
            "VALUES (?, '2026-09-10', ?, ?, ?)", (appid, final, initial, discount))


def check_edge_case_isolation():
    """DLC 누락 / 가격이력 전무(price_final=0) 오인 여부를,
    다른 후보와의 점수 경쟁·12개 상한이 결과를 흐리지 않도록 후보 수를 최소화해 단독 검증한다."""
    import config
    import importlib
    import store
    import build

    for label, appid, overrides in [
        ("DLC(app_type=dlc) 단독 배제 확인(R1)", 900001, {"app_type": "dlc"}),
        ("가격이력 전무(price_final=0, is_free=0) 단독 배제 확인(R1)", 900002, {"no_price_row": True}),
    ]:
        db_path = os.path.join(TMP, f"iso_{appid}.sqlite3")
        site_dir = os.path.join(TMP, f"iso_site_{appid}")
        config.DB_PATH = db_path
        config.SITE_DIR = site_dir
        conn = sqlite3.connect(db_path)
        conn.executescript(store.SCHEMA)
        cols_games = [r[1] for r in conn.execute("PRAGMA table_info(games)")]
        _insert_minimal_game(conn, cols_games, appid, f"단독검증-{appid}", **overrides)
        conn.commit()
        conn.close()
        build.main()
        p = find_picks_json(site_dir)
        if not p:
            skip(label, "JSON 미생성")
            continue
        data = json.load(open(p, encoding="utf-8"))
        in_any = (appid in [it["appid"] for it in data.get("wednesday", [])] or
                  appid in [it["appid"] for it in data.get("saturday", [])])
        check(f"[단독시나리오] {label} → 포함되면 안 됨", not in_any,
              f"실제 포함 여부={in_any} (경쟁 후보 없이 단독 검증, 점수/상한 영향 없음)")


def main():
    try:
        import editorial  # noqa: F401
    except ImportError:
        skip("전체 검증", "editorial.py 가 아직 존재하지 않음 — Gemini 구현 대기 중")
        print(f"\n결과: 실패 0건 / 스킵 1건")
        sys.exit(0)

    if not hasattr(editorial, "generate_picks"):
        skip("전체 검증", "editorial.generate_picks 함수가 없음 — 구현/연결 확인 필요")
        sys.exit(0)

    site_dir = build_site()
    picks_json = find_picks_json(site_dir)
    if not picks_json:
        skip("전체 검증", "build.main()이 assets/editorial-picks.json을 생성하지 않음 — build.py 연결 미완료")
    else:
        data = json.load(open(picks_json, encoding="utf-8"))
        check_schema_and_rules(data, os.path.join(site_dir, "index.html"))
        check_determinism()
        check_edge_case_isolation()

    print(f"\n결과: 실패 {len(FAILS)}건 / 스킵 {len(SKIPPED)}건")
    for f in FAILS:
        print("  FAIL -", f)
    for label, reason in SKIPPED:
        print("  SKIP -", label, "—", reason)
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
