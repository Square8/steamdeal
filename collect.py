"""
수집. GitHub Actions 가 하루 2번 실행한다.

목록 배분이 중요하다: 신규 발견이 전부 차지하면 기존 게임의 가격 이력이 얼어붙는다.
그래서 예산의 일부(REFRESH_QUOTA)를 '가장 오래 갱신 안 된 기존 게임'에 먼저 배정한다.
"""
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

    budget = config.MAX_APPS_PER_RUN
    refresh_n = int(budget * config.REFRESH_QUOTA)

    discovered = steam.discover()                      # {appid: 태그}
    stale = store.stale_appids(conn, refresh_n)        # 오래 갱신 안 된 기존 게임

    # 1) 기존 게임 갱신 몫을 먼저 확보 → 2) 남은 자리에 신규 발견
    targets: list[tuple[int, str | None]] = [(a, None) for a in stale]
    seen = set(stale)
    for appid, tag in discovered.items():
        if len(targets) >= budget:
            break
        if appid not in seen:
            targets.append((appid, tag))
            seen.add(appid)

    log.info("이번 실행 %d개 = 기존갱신 %d + 신규 %d (발견 %d)",
             len(targets), len(stale), len(targets) - len(stale), len(discovered))

    ok = failed = 0
    for i, (appid, tag) in enumerate(targets, 1):
        app = steam.fetch_app(appid)
        if app is None:
            failed += 1
            continue
        store.save(conn, app, tag or discovered.get(appid))
        ok += 1
        if i % 25 == 0:
            conn.commit()
            log.info("  진행 %d/%d (저장 %d, 실패 %d)", i, len(targets), ok, failed)
    conn.commit()

    total = conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]
    days = conn.execute("SELECT COUNT(DISTINCT on_date) FROM prices").fetchone()[0]
    ko = conn.execute("SELECT COUNT(*) FROM games WHERE korean=1").fetchone()[0]
    demo = conn.execute("SELECT COUNT(*) FROM games WHERE has_demo=1 OR app_type='demo'").fetchone()[0]
    log.info("완료 — 저장 %d, 실패 %d | 누적 %d개 (한국어 %d, 데모 %d), 수집일수 %d일",
             ok, failed, total, ko, demo, days)
    conn.close()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
