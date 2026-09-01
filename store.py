"""저장소. 게임 정보 + 일별 가격 이력."""
import os
import sqlite3
from datetime import date, datetime, timezone

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS games (
    appid         INTEGER PRIMARY KEY,
    name          TEXT NOT NULL,
    app_type      TEXT,
    tag           TEXT,            -- 신작 / 출시예정 / 할인 / 인기 / 고정
    header_image  TEXT,
    description   TEXT,
    genres        TEXT,
    korean        INTEGER DEFAULT 0,
    coming_soon   INTEGER DEFAULT 0,
    release_text  TEXT,
    release_date  TEXT,            -- YYYY-MM-DD (파싱 성공 시)
    has_demo      INTEGER DEFAULT 0,
    demo_appid    INTEGER,
    is_free       INTEGER DEFAULT 0,
    adult         INTEGER DEFAULT 0,   -- 성적 콘텐츠. 기본 화면에서 감춘다
    review_count  INTEGER DEFAULT 0,   -- 인지도 대리 지표
    review_score  INTEGER DEFAULT 0,
    review_desc   TEXT,
    review_positive INTEGER DEFAULT 0,
    review_negative INTEGER DEFAULT 0,
    reviews_checked_at TEXT,
    players_current INTEGER DEFAULT 0,
    players_previous INTEGER DEFAULT 0,
    players_checked_at TEXT,
    developer     TEXT,
    -- '이게 무슨 게임인가'에 답하는 것들. appdetails 응답에 이미 들어 있어
    -- 추가 호출 없이 얻는다. screenshots 는 줄바꿈으로 이어붙인 URL 목록.
    screenshots   TEXT,
    movie_mp4     TEXT,
    movie_webm    TEXT,
    movie_poster  TEXT,
    -- 가격을 '관측한' 첫/마지막 날. 가격 행은 변동 시에만 쌓기 때문에
    -- 관측 기간을 이력 행 개수로 셀 수 없다. 그래서 따로 기록한다.
    price_first   TEXT,
    price_last    TEXT,
    first_seen    TEXT NOT NULL,
    last_seen     TEXT NOT NULL,
    checked_at    TEXT NOT NULL    -- 마지막 상세조회 시각 (회전 갱신 기준)
);

CREATE TABLE IF NOT EXISTS prices (
    appid         INTEGER NOT NULL,
    on_date       TEXT NOT NULL,
    price_final   INTEGER NOT NULL,
    price_initial INTEGER NOT NULL,
    discount_pct  INTEGER NOT NULL,
    PRIMARY KEY (appid, on_date)
);
-- 한 번이라도 appdetails 를 부른 appid. 성공/실패 모두 남긴다.
-- 스팀 전체 25만 개 중 대부분은 DLC·사운드트랙·삭제된 것이라 실패하는데,
-- 그걸 기록하지 않으면 매 실행 같은 죽은 appid 를 다시 부르면서 예산을 태운다.
-- 호출이 유일한 희소 자원(1.5초에 하나)이므로 이 표가 개척의 핵심이다.
CREATE TABLE IF NOT EXISTS probed (
    appid   INTEGER PRIMARY KEY,
    ok      INTEGER NOT NULL DEFAULT 0,   -- 1 = 게임/데모로 저장됨
    on_date TEXT
);

-- 마지막으로 전체 가격 수집이 완료된 시각. 날짜만 담는 games.checked_at 과 달리
-- 예약 실행 지연을 화면에서 판별할 수 있도록 UTC 초 단위로 저장한다.
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_prices_appid ON prices(appid);
CREATE INDEX IF NOT EXISTS idx_games_checked ON games(checked_at);
"""


def connect() -> sqlite3.Connection:
    d = os.path.dirname(config.DB_PATH)
    if d:
        os.makedirs(d, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    _migrate(conn)
    return conn


def set_meta(conn, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta(key,value) VALUES(?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))


def get_meta(conn, key: str, default: str | None = None) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row[0] if row else default


def _migrate(conn) -> None:
    """예전 스키마로 만든 DB에 새 칼럼을 붙인다 (데이터 유지)."""
    have = {r["name"] for r in conn.execute("PRAGMA table_info(games)")}
    add = {
        "app_type": "TEXT", "tag": "TEXT", "genres": "TEXT",
        "korean": "INTEGER DEFAULT 0", "coming_soon": "INTEGER DEFAULT 0",
        "release_text": "TEXT", "release_date": "TEXT",
        "has_demo": "INTEGER DEFAULT 0", "demo_appid": "INTEGER",
        "is_free": "INTEGER DEFAULT 0", "checked_at": "TEXT",
        "adult": "INTEGER DEFAULT 0", "review_count": "INTEGER DEFAULT 0",
        "review_score": "INTEGER DEFAULT 0", "review_desc": "TEXT",
        "review_positive": "INTEGER DEFAULT 0",
        "review_negative": "INTEGER DEFAULT 0",
        "reviews_checked_at": "TEXT",
        "players_current": "INTEGER DEFAULT 0",
        "players_previous": "INTEGER DEFAULT 0",
        "players_checked_at": "TEXT",
        "developer": "TEXT", "price_first": "TEXT", "price_last": "TEXT",
        "screenshots": "TEXT", "movie_mp4": "TEXT", "movie_webm": "TEXT",
        "movie_poster": "TEXT",
    }
    for col, decl in add.items():
        if col not in have:
            conn.execute(f"ALTER TABLE games ADD COLUMN {col} {decl}")
    # 예전 방식(매일 1행)으로 쌓인 DB 에서 관측 구간을 복원한다.
    # 새 칼럼이 방금 추가됐다면 값이 NULL 이므로 기존 prices 에서 채워준다.
    conn.execute("""
        UPDATE games SET
          price_first = COALESCE(price_first,
            (SELECT MIN(on_date) FROM prices WHERE prices.appid = games.appid)),
          price_last  = COALESCE(price_last,
            (SELECT MAX(on_date) FROM prices WHERE prices.appid = games.appid))
        WHERE price_first IS NULL OR price_last IS NULL""")
    conn.commit()


def is_relevant(app: dict, tag: str | None) -> bool:
    """보관할 가치가 있는가. 개척은 넓게, 저장은 좁게 (config.KEEP_ONLY_RELEVANT).
    한국어 없고 데모도 없고 출시예정도 아니고 큐레이션에도 안 걸린 옛 게임은
    이 사이트 어느 화면에도 나가지 않으므로 보관하지 않는다."""
    if not config.KEEP_ONLY_RELEVANT:
        return True
    return bool(app.get("korean") or app.get("has_demo")
                or app.get("app_type") == "demo"
                or app.get("coming_soon") or tag)


def save(conn, app: dict, tag: str | None = None) -> bool:
    """저장했으면 True. 보관 대상이 아니면 아무것도 하지 않고 False.

    보관 필터는 '처음 들이는 게임'에만 건다. 이미 DB 에 있는 게임은 무조건 갱신한다 —
    갱신 대상에는 tag 가 None 으로 오기 때문에(태그는 최초 발견 때만 붙는다),
    필터를 그대로 걸면 예전에 '신작'으로 들어온 게임이 갱신 때마다 튕겨서
    사이트에는 계속 보이는데 가격만 영원히 멈춘다. 실제로 66개가 그 상태였다."""
    known = conn.execute("SELECT 1 FROM games WHERE appid=?",
                         (app["appid"],)).fetchone() is not None
    if not known and not is_relevant(app, tag):
        return False
    today = date.today().isoformat()
    conn.execute(
        """INSERT INTO games (appid,name,app_type,tag,header_image,description,genres,
                              korean,coming_soon,release_text,release_date,
                              has_demo,demo_appid,is_free,adult,review_count,developer,
                              screenshots,movie_mp4,movie_webm,movie_poster,
                              first_seen,last_seen,checked_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(appid) DO UPDATE SET
             name=excluded.name, app_type=excluded.app_type,
             header_image=excluded.header_image, description=excluded.description,
             genres=excluded.genres, korean=excluded.korean,
             coming_soon=excluded.coming_soon, release_text=excluded.release_text,
             release_date=excluded.release_date, has_demo=excluded.has_demo,
             demo_appid=excluded.demo_appid, is_free=excluded.is_free,
             adult=excluded.adult, review_count=excluded.review_count,
             developer=excluded.developer,
             screenshots=excluded.screenshots, movie_mp4=excluded.movie_mp4,
             movie_webm=excluded.movie_webm, movie_poster=excluded.movie_poster,
             last_seen=excluded.last_seen, checked_at=excluded.checked_at,
             -- 태그는 처음 발견된 것을 유지한다 (신작으로 잡힌 게 나중에 '할인'으로 덮이면
             -- 언제 새로 나왔는지 알 수 없게 되므로)
             tag=COALESCE(games.tag, excluded.tag)""",
        (app["appid"], app["name"], app["app_type"], tag, app["header_image"],
         app["short_description"], app["genres"], app["korean"], app["coming_soon"],
         app["release_text"], app["release_date"], app["has_demo"], app["demo_appid"],
         1 if app["is_free"] else 0, app.get("adult", 0), app.get("review_count", 0),
         app.get("developer", ""),
         app.get("screenshots", ""), app.get("movie_mp4", ""),
         app.get("movie_webm", ""), app.get("movie_poster", ""),
         today, today, today),
    )
    # 가격이 있는 것만 이력에 남긴다 (무료/출시예정은 가격이 없다)
    if app["price_final"] > 0:
        # 매 실행마다 한 행씩 쌓으면(200개 × 하루 2번) 2년에 14만 행 / 8.8MB 가 되고,
        # 이 파일을 하루 두 번 git 에 커밋하므로 저장소 이력이 계속 불어난다.
        # 그래서 '가격이 변했을 때만' 새 행을 남긴다. 관측 기간은 price_first/last 로 따로 센다.
        prev = conn.execute(
            "SELECT price_final, price_initial, discount_pct FROM prices "
            "WHERE appid=? ORDER BY on_date DESC LIMIT 1", (app["appid"],)).fetchone()
        cur = (app["price_final"], app["price_initial"], app["discount_pct"])
        changed = prev is None or tuple(prev) != cur
        if changed:
            conn.execute(
                """INSERT INTO prices (appid,on_date,price_final,price_initial,discount_pct)
                   VALUES (?,?,?,?,?)
                   ON CONFLICT(appid,on_date) DO UPDATE SET
                     price_final=excluded.price_final,
                     price_initial=excluded.price_initial,
                     discount_pct=excluded.discount_pct""",
                (app["appid"], today, *cur))
        # 변동이 없어도 '오늘 확인했다'는 사실은 기록해야 관측 기간이 늘어난다.
        conn.execute(
            "UPDATE games SET price_first=COALESCE(price_first,?), price_last=? "
            "WHERE appid=?", (today, today, app["appid"]))
    return True


def mark_probed(conn, appid: int, ok: bool) -> None:
    conn.execute(
        "INSERT INTO probed (appid, ok, on_date) VALUES (?,?,?) "
        "ON CONFLICT(appid) DO UPDATE SET ok=excluded.ok, on_date=excluded.on_date",
        (appid, 1 if ok else 0, date.today().isoformat()))


def probed_appids(conn) -> set[int]:
    """이미 확인해 본 appid. 여기 있는 것은 다시 부르지 않는다."""
    return {r[0] for r in conn.execute("SELECT appid FROM probed")}


def explore_stats(conn) -> tuple[int, int]:
    """(확인한 개수, 그중 게임/데모였던 개수). 개척 진행률 로그용."""
    r = conn.execute("SELECT COUNT(*), COALESCE(SUM(ok),0) FROM probed").fetchone()
    return int(r[0]), int(r[1])


def max_game_appid(conn) -> int:
    """실제로 존재가 확인된 앱 중 가장 큰 appid. 번호 훑기의 출발점이다.

    probed 는 보지 않는다 — 거기에는 존재하지 않는 번호까지 들어 있어서,
    그걸 천장으로 쓰면 훑기가 빈 구간에 머물며 제자리걸음을 한다(실제로 두 번 그랬다).
    큐레이션이 오늘 나온 신작을 물어다 주므로 이 값이 곧 '최신 경계'가 된다."""
    return int(conn.execute("SELECT COALESCE(MAX(appid),0) FROM games").fetchone()[0] or 0)


def stale_appids(conn, limit: int) -> list[int]:
    """가장 오래 갱신 안 된 게임부터. 신규 발견이 목록을 다 차지해서
    기존 게임 이력이 얼어붙는 문제를 막는다."""
    return [r["appid"] for r in conn.execute(
        "SELECT appid FROM games ORDER BY COALESCE(checked_at,'') ASC LIMIT ?", (limit,))]


def _current_price_join() -> str:
    """게임별 가장 최근 가격을 붙이는 공통 SQL 조각."""
    return """
      LEFT JOIN prices p ON p.appid=g.appid AND p.on_date=(
        SELECT MAX(p2.on_date) FROM prices p2 WHERE p2.appid=g.appid)
    """


def player_signal_appids(conn, limit: int) -> list[int]:
    """동접을 물어볼 후보. 한국어·비성인 정식 게임 중 검증된 인기작을 우선한다."""
    sql = ("SELECT g.appid FROM games g " + _current_price_join() + """
      WHERE g.korean=1 AND g.adult=0 AND g.coming_soon=0 AND g.app_type='game'
      ORDER BY CASE WHEN COALESCE(p.discount_pct,0)>0 THEN 0 ELSE 1 END,
               COALESCE(g.review_count,0) DESC, g.appid DESC
      LIMIT ?""")
    return [r[0] for r in conn.execute(sql, (limit,))]


def review_signal_appids(conn, limit: int) -> list[int]:
    """평가 등급 후보. 할인율 50% 이상인 한국어 게임을 오래된 측정부터 갱신한다."""
    sql = ("SELECT g.appid FROM games g " + _current_price_join() + """
      WHERE g.korean=1 AND g.adult=0 AND g.app_type='game'
        AND COALESCE(p.discount_pct,0)>=50 AND COALESCE(g.review_count,0)>=100
      ORDER BY COALESCE(g.reviews_checked_at,'') ASC,
               COALESCE(p.discount_pct,0) DESC, COALESCE(g.review_count,0) DESC
      LIMIT ?""")
    return [r[0] for r in conn.execute(sql, (limit,))]


def save_player_count(conn, appid: int, count: int) -> None:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn.execute(
        """UPDATE games SET
             players_previous=CASE WHEN players_checked_at IS NULL
                                   THEN ? ELSE COALESCE(players_current,0) END,
             players_current=?, players_checked_at=?
           WHERE appid=?""", (max(int(count), 0), max(int(count), 0), now, appid))


def save_review_summary(conn, appid: int, summary: dict) -> None:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn.execute(
        """UPDATE games SET review_score=?, review_desc=?,
             review_positive=?, review_negative=?, reviews_checked_at=?
           WHERE appid=?""",
        (summary.get("score", 0), summary.get("desc", ""),
         summary.get("positive", 0), summary.get("negative", 0), now, appid))


def observed_days(first: str | None, last: str | None) -> int:
    """가격을 지켜본 날짜 폭(양끝 포함). 가격 행 개수와 다르다."""
    if not first or not last:
        return 0
    try:
        f = date.fromisoformat(first)
        l = date.fromisoformat(last)
    except ValueError:
        return 0
    return max((l - f).days + 1, 1)


def all_games(conn) -> list[dict]:
    """게임별 현재 상태 + 가격 이력 + 최저가."""
    out = []
    for r in conn.execute("SELECT * FROM games ORDER BY name"):
        g = dict(r)
        hist = [dict(h) for h in conn.execute(
            "SELECT on_date, price_final, price_initial, discount_pct FROM prices "
            "WHERE appid=? ORDER BY on_date", (g["appid"],))]
        g["history"] = hist
        if hist:
            cur = hist[-1]
            lows = [h["price_final"] for h in hist if h["price_final"] > 0]
            low = min(lows) if lows else 0
            g["price_final"] = cur["price_final"]
            g["discount_pct"] = cur["discount_pct"]
            # 정가는 스팀이 준 실제 값을 쓴다 (관측 최고가로 추정하지 않는다)
            g["price_initial"] = cur["price_initial"] or cur["price_final"]
            g["lowest_seen"] = low
            # 관측 기간 = 실제로 지켜본 날짜 폭. 이력 '행 개수'가 아니다.
            # (가격 변동 시에만 행을 남기므로, 행 개수로 세면 1년 지켜봐도 3일로 나온다)
            #
            # 두 근거 중 넓은 쪽을 쓴다:
            #   price_first/last  = 변동이 없던 날까지 포함한 관측 구간 (더 정확)
            #   이력의 첫~마지막   = 그 날에 확실히 관측했다는 증거 (더 안전)
            # price_first/last 가 비어 있거나 낡은 DB(마이그레이션 직후, 외부에서
            # prices 만 채운 경우)에서 관측 기간이 1일로 축소되는 것을 막는다.
            g["days_tracked"] = max(
                observed_days(g.get("price_first"), g.get("price_last")),
                observed_days(hist[0]["on_date"], hist[-1]["on_date"]),
                1)
            # 관측 기간이 짧으면 '역대 최저'라고 말하지 않는다 (거짓이 될 수 있으므로)
            g["at_lowest"] = bool(low and cur["price_final"] <= low)
            g["atl_trustworthy"] = g["days_tracked"] >= config.MIN_DAYS_FOR_ATL
        else:
            g.update({"price_final": 0, "discount_pct": 0, "price_initial": 0,
                      "lowest_seen": 0, "days_tracked": 0,
                      "at_lowest": False, "atl_trustworthy": False})
        pos = g.get("review_positive") or 0
        neg = g.get("review_negative") or 0
        g["review_total"] = pos + neg
        g["review_positive_pct"] = round(pos * 100 / (pos + neg)) if pos + neg else 0
        g["player_delta"] = ((g.get("players_current") or 0)
                             - (g.get("players_previous") or 0))
        g["score"], g["why"] = score_broadcast(g)
        out.append(g)
    return out


def score_broadcast(g: dict) -> tuple[int, list[str]]:
    """추천 적합도 점수(0~100)와 그 근거.

    일부러 '역대 최저가와의 거리' 는 넣지 않았다. 그 지표는 수집 60일이 넘어야
    의미가 생기는데(MIN_DAYS_FOR_ATL) 지금은 이력이 며칠뿐이라, 넣으면 근거 없는
    숫자가 커 보이게 될 뿐이다. 아래 항목은 전부 수집 첫날부터 사실인 것들이다.

    가중치가 잘게 나뉘어 있는 이유: 만점이 흔하면 점수가 아무 정보도 주지 않는다.
    실제로 처음엔 항목이 굵어서 한국어 지원 데모 인디게임이면 전부 100점이 나왔다.
    """
    pts, why = 0, []
    if g.get("has_demo") or g.get("app_type") == "demo":
        pts += 28
        why.append("데모로 먼저 해볼 수 있음")
    if g.get("korean"):
        pts += 18
        why.append("한국어 지원")
    if g.get("coming_soon"):
        pts += 16
        why.append("아직 출시 전 — 선점 가능")
    elif g.get("tag") == "신작":
        pts += 12
        why.append("최근 출시된 신작")

    price = g.get("price_final") or 0
    if g.get("is_free"):
        pts += 14
        why.append("무료")
    elif not price:
        pass                                  # 가격 미정은 점수 없음
    elif price <= 10000:
        pts += 12
        why.append(f"{price:,}원 — 부담 없는 가격")
    elif price <= 20000:
        pts += 9
    elif price <= 40000:
        pts += 5

    off = g.get("discount_pct") or 0
    if off:
        pts += min(round(off * 0.14), 14)     # 50% → 7점, 90% → 13점
        why.append(f"{off}% 할인 중")

    # 리뷰가 없는 신작은 '정보가 없다'는 뜻이지 나쁘다는 뜻이 아니므로 감점하지 않는다.
    rc = g.get("review_count") or 0
    for need, add in ((10000, 10), (1000, 7), (100, 4)):
        if rc >= need:
            pts += add
            why.append(f"리뷰 {rc:,}개")
            break
    return min(pts, 100), why


def broadcast_candidates(games: list[dict], include_adult: bool = False) -> list[dict]:
    """추천 후보: 한국어 지원 + 가격 조건 + (데모 있음 또는 신작/출시예정).
    기준은 config 에서 조절한다. 점수 높은 순으로 돌려준다."""
    out = []
    for g in games:
        if not include_adult and g.get("adult"):
            continue
        if config.REQUIRE_KOREAN and not g.get("korean"):
            continue
        price = g.get("price_final") or 0
        if config.BROADCAST_MAX_PRICE and price > config.BROADCAST_MAX_PRICE:
            continue
        interesting = (g.get("has_demo") or g.get("app_type") == "demo"
                       or g.get("tag") in ("신작", "출시예정") or g.get("is_free"))
        if interesting:
            out.append(g)
    return sorted(out, key=lambda g: (-score_broadcast(g)[0], g.get("name") or ""))
