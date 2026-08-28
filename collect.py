"""
수집. GitHub Actions 가 하루 2번 실행한다.

예산(MAX_APPS_PER_RUN) 배분이 이 파일의 전부다. 세 가지가 서로 자리를 다툰다:

  ① 기존 갱신 (REFRESH_QUOTA)  — 안 하면 이미 아는 게임의 가격 이력이 얼어붙는다
  ② 큐레이션 발견              — featuredcategories. 오늘 뭐가 새로 나왔는지
  ③ 신규 개척 (EXPLORE_QUOTA)  — GetAppList 의 미탐색 appid

②만 쓰면 '알게 되는' 게임이 150~250개에서 영구히 멈춘다
(실측: 1일차 61개 → 2일차 120개. 예산이 남아서가 아니라 목록을 다 훑어서 멈춤).
그래서 ③이 있다. 스팀 전체는 25만 개고 appdetails 는 1.5초에 하나라 한 번에는
104일이 걸리지만, DB 는 지워지지 않는 누적 자산이라 매 실행 조금씩 파면 된다.
"""
import logging
import sys

import config
import steam
import store


def _plan(conn, log) -> list[tuple[int, str | None]]:
    """이번 실행에 부를 (appid, 태그) 목록. 위 세 몫을 순서대로 채운다."""
    budget = config.MAX_APPS_PER_RUN
    targets: list[tuple[int, str | None]] = []
    seen: set[int] = set()

    def take(appid: int, tag: str | None) -> bool:
        if appid in seen or len(targets) >= budget:
            return False
        targets.append((appid, tag))
        seen.add(appid)
        return True

    # ① 기존 갱신 몫을 먼저 확보한다. 이걸 뒤로 미루면 개척이 예산을 다 먹고
    #    아는 게임의 가격이 며칠씩 갱신되지 않는다.
    stale = store.stale_appids(conn, int(budget * config.REFRESH_QUOTA))
    for appid in stale:
        take(appid, None)
    n_refresh = len(targets)

    # ② 오늘 상점 첫 화면에 걸린 것 — 신작/할인 태그를 얻을 수 있는 유일한 경로
    discovered = steam.discover()
    for appid, tag in discovered.items():
        take(appid, tag)
    n_featured = len(targets) - n_refresh

    # ③ 남은 자리를 미탐색 appid 로 채운다
    room = min(budget - len(targets), int(budget * config.EXPLORE_QUOTA))
    n_explore = 0
    if room > 0:
        pool = steam.all_appids()
        if pool:
            done = store.probed_appids(conn)
            for appid, _name in pool:
                if appid in done:
                    continue
                if not take(appid, None):
                    break
                n_explore += 1
                if n_explore >= room:
                    break
            checked, hit = store.explore_stats(conn)
            log.info("개척 풀 %d개 중 %d개 확인 완료 (%.1f%%), 그중 게임/데모 %d개",
                     len(pool), checked, 100 * checked / max(len(pool), 1), hit)
        else:
            log.warning("전체 목록을 못 받아 개척을 건너뛴다 (큐레이션 발견만 진행)")

    log.info("이번 실행 %d개 = 기존갱신 %d + 큐레이션 %d + 신규개척 %d",
             len(targets), n_refresh, n_featured, n_explore)
    return targets


def main() -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s")
    log = logging.getLogger("collect")
    conn = store.connect()

    targets = _plan(conn, log)
    if not targets:
        log.error("부를 대상이 없다. 스팀 API 응답을 확인할 것.")
        conn.close()
        return 1

    ok = failed = dropped = 0
    for i, (appid, tag) in enumerate(targets, 1):
        app = steam.fetch_app(appid)
        # 실패도 기록한다 — 안 하면 다음 실행에서 같은 죽은 appid 를 또 부른다.
        store.mark_probed(conn, appid, app is not None)
        if app is None:
            failed += 1
        elif store.save(conn, app, tag):
            ok += 1
        else:
            dropped += 1        # 게임이지만 보관 대상 아님 (한국어X·데모X·구작)
        if i % 50 == 0:
            conn.commit()
            log.info("  진행 %d/%d (저장 %d, 무관 %d, 제외 %d)",
                     i, len(targets), ok, dropped, failed)
    conn.commit()

    q = lambda s: conn.execute(s).fetchone()[0]
    log.info("완료 — 저장 %d, 무관 %d, 제외 %d | 누적 %d개 (한국어 %d, 데모 %d), 수집일수 %d일",
             ok, dropped, failed,
             q("SELECT COUNT(*) FROM games"),
             q("SELECT COUNT(*) FROM games WHERE korean=1"),
             q("SELECT COUNT(*) FROM games WHERE has_demo=1 OR app_type='demo'"),
             q("SELECT COUNT(DISTINCT on_date) FROM prices"))
    conn.close()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
