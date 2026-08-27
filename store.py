"""저장소. 게임 정보 + 일별 가격 이력."""
import os
import sqlite3
from datetime import date

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


def _migrate(conn) -> None:
    """예전 스키마로 만든 DB에 새 칼럼을 붙인다 (데이터 유지)."""
    have = {r["name"] for r in conn.execute("PRAGMA table_info(games)")}
    add = {
        "app_type": "TEXT", "tag": "TEXT", "genres": "TEXT",
        "korean": "INTEGER DEFAULT 0", "coming_soon": "INTEGER DEFAULT 0",
        "release_text": "TEXT", "release_date": "TEXT",
        "has_demo": "INTEGER DEFAULT 0", "demo_appid": "INTEGER",
        "is_free": "INTEGER DEFAULT 0", "checked_at": "TEXT",
    }
    for col, decl in add.items():
        if col not in have:
            conn.execute(f"ALTER TABLE games ADD COLUMN {col} {decl}")
    conn.commit()


def save(conn, app: dict, tag: str | None = None) -> None:
    today = date.today().isoformat()
    conn.execute(
        """INSERT INTO games (appid,name,app_type,tag,header_image,description,genres,
                              korean,coming_soon,release_text,release_date,
                              has_demo,demo_appid,is_free,first_seen,last_seen,checked_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(appid) DO UPDATE SET
             name=excluded.name, app_type=excluded.app_type,
             header_image=excluded.header_image, description=excluded.description,
             genres=excluded.genres, korean=excluded.korean,
             coming_soon=excluded.coming_soon, release_text=excluded.release_text,
             release_date=excluded.release_date, has_demo=excluded.has_demo,
             demo_appid=excluded.demo_appid, is_free=excluded.is_free,
             last_seen=excluded.last_seen, checked_at=excluded.checked_at,
             -- 태그는 처음 발견된 것을 유지한다 (신작으로 잡힌 게 나중에 '할인'으로 덮이면
             -- 언제 새로 나왔는지 알 수 없게 되므로)
             tag=COALESCE(games.tag, excluded.tag)""",
        (app["appid"], app["name"], app["app_type"], tag, app["header_image"],
         app["short_description"], app["genres"], app["korean"], app["coming_soon"],
         app["release_text"], app["release_date"], app["has_demo"], app["demo_appid"],
         1 if app["is_free"] else 0, today, today, today),
    )
    # 가격이 있는 것만 이력에 남긴다 (무료/출시예정은 가격이 없다)
    if app["price_final"] > 0:
        conn.execute(
            """INSERT INTO prices (appid,on_date,price_final,price_initial,discount_pct)
               VALUES (?,?,?,?,?)
               ON CONFLICT(appid,on_date) DO UPDATE SET
                 price_final=excluded.price_final,
                 price_initial=excluded.price_initial,
                 discount_pct=excluded.discount_pct""",
            (app["appid"], today, app["price_final"],
             app["price_initial"], app["discount_pct"]),
        )


def stale_appids(conn, limit: int) -> list[int]:
    """가장 오래 갱신 안 된 게임부터. 신규 발견이 목록을 다 차지해서
    기존 게임 이력이 얼어붙는 문제를 막는다."""
    return [r["appid"] for r in conn.execute(
        "SELECT appid FROM games ORDER BY COALESCE(checked_at,'') ASC LIMIT ?", (limit,))]


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
            g["days_tracked"] = len(hist)
            # 관측 기간이 짧으면 '역대 최저'라고 말하지 않는다 (거짓이 될 수 있으므로)
            g["at_lowest"] = bool(low and cur["price_final"] <= low)
            g["atl_trustworthy"] = len(hist) >= config.MIN_DAYS_FOR_ATL
        else:
            g.update({"price_final": 0, "discount_pct": 0, "price_initial": 0,
                      "lowest_seen": 0, "days_tracked": 0,
                      "at_lowest": False, "atl_trustworthy": False})
        out.append(g)
    return out


def broadcast_candidates(games: list[dict]) -> list[dict]:
    """방송 후보: 한국어 지원 + 가격 조건 + (데모 있음 또는 신작/출시예정).
    기준은 config 에서 조절한다."""
    out = []
    for g in games:
        if config.REQUIRE_KOREAN and not g.get("korean"):
            continue
        price = g.get("price_final") or 0
        if config.BROADCAST_MAX_PRICE and price > config.BROADCAST_MAX_PRICE:
            continue
        interesting = (g.get("has_demo") or g.get("app_type") == "demo"
                       or g.get("tag") in ("신작", "출시예정") or g.get("is_free"))
        if interesting:
            out.append(g)
    # 데모 있는 것 → 출시예정 → 신작 순으로 위에 오게
    def rank(g):
        return (0 if (g.get("has_demo") or g.get("app_type") == "demo") else 1,
                0 if g.get("tag") == "출시예정" else 1,
                g.get("name") or "")
    return sorted(out, key=rank)
