"""가격 이력 저장. '역대 최저가'는 이 이력에서 계산된다."""
import os
import sqlite3
from datetime import date

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS games (
    appid        INTEGER PRIMARY KEY,
    name         TEXT NOT NULL,
    header_image TEXT,
    description  TEXT,
    first_seen   TEXT NOT NULL,
    last_seen    TEXT NOT NULL
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
CREATE INDEX IF NOT EXISTS idx_prices_date  ON prices(on_date);
"""


def connect() -> sqlite3.Connection:
    d = os.path.dirname(config.DB_PATH)
    if d:
        os.makedirs(d, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def save(conn: sqlite3.Connection, app: dict) -> None:
    today = date.today().isoformat()
    conn.execute(
        """INSERT INTO games (appid,name,header_image,description,first_seen,last_seen)
           VALUES (?,?,?,?,?,?)
           ON CONFLICT(appid) DO UPDATE SET
             name=excluded.name, header_image=excluded.header_image,
             description=excluded.description, last_seen=excluded.last_seen""",
        (app["appid"], app["name"], app["header_image"],
         app["short_description"], today, today),
    )
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


def all_games(conn) -> list[dict]:
    """게임별 현재가 + 역대최저가 + 이력을 한 번에."""
    rows = [dict(r) for r in conn.execute("SELECT * FROM games ORDER BY name")]
    out = []
    for g in rows:
        hist = [dict(r) for r in conn.execute(
            "SELECT on_date, price_final, discount_pct FROM prices "
            "WHERE appid=? ORDER BY on_date", (g["appid"],))]
        if not hist:
            continue
        cur = hist[-1]
        lows = [h["price_final"] for h in hist if h["price_final"] > 0]
        low = min(lows) if lows else 0
        g.update({
            "history": hist,
            "price_final": cur["price_final"],
            "discount_pct": cur["discount_pct"],
            "price_initial": max((h["price_final"] for h in hist), default=cur["price_final"]),
            "all_time_low": low,
            "is_all_time_low": bool(low and cur["price_final"] <= low),
            "days_tracked": len(hist),
        })
        out.append(g)
    return out
