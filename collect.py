"""가격 수집. GitHub Actions 가 하루 2번 이 파일을 실행한다."""
import logging
import sys

import config
import steam
import store


def main() -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s")
    log = logging.getLogger("collect")

    conn = store.connect()

    # 기존에 추적하던 게임 + 스팀이 알려주는 신규
    known = [r["appid"] for r in conn.execute("SELECT appid FROM games")]
    discovered = steam.discover_appids()
    targets = list(dict.fromkeys(discovered + known))[:config.MAX_APPS_PER_RUN]
    log.info("이번 실행 대상 %d개 (기존 %d, 자동수집 %d)",
             len(targets), len(known), len(discovered))

    ok = skipped = failed = 0
    for i, appid in enumerate(targets, 1):
        app = steam.fetch_app(appid)
        if app is None:
            failed += 1
            continue
        if config.SKIP_FREE and (app["is_free"] or app["price_final"] <= 0):
            skipped += 1
            continue
        store.save(conn, app)
        ok += 1
        if i % 25 == 0:
            conn.commit()
            log.info("  진행 %d/%d (저장 %d, 무료/무가격 %d, 실패 %d)",
                     i, len(targets), ok, skipped, failed)
    conn.commit()

    total = conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]
    days = conn.execute("SELECT COUNT(DISTINCT on_date) FROM prices").fetchone()[0]
    log.info("완료 — 저장 %d, 무료/무가격 %d, 실패 %d | 누적 게임 %d개, 수집일수 %d일",
             ok, skipped, failed, total, days)
    conn.close()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
