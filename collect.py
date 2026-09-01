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
from datetime import datetime, timezone

import config
import steam
import store


def _collect_signals(conn, log) -> tuple[int, int]:
    """홈 트렌드용 리뷰 등급·현재 동접을 제한된 후보에만 붙인다."""
    review_ok = player_ok = 0
    review_ids = store.review_signal_appids(conn, config.REVIEW_SIGNAL_LIMIT)
    player_ids = store.player_signal_appids(conn, config.PLAYER_SIGNAL_LIMIT)
    log.info("트렌드 신호 — 리뷰 후보 %d / 동접 후보 %d",
             len(review_ids), len(player_ids))

    for i, appid in enumerate(review_ids, 1):
        summary = steam.fetch_review_summary(appid)
        if summary is not None:
            store.save_review_summary(conn, appid, summary)
            review_ok += 1
        if i % 20 == 0:
            conn.commit()

    for i, appid in enumerate(player_ids, 1):
        count = steam.fetch_current_players(appid)
        if count is not None:
            store.save_player_count(conn, appid, count)
            player_ok += 1
        if i % 20 == 0:
            conn.commit()
    conn.commit()
    log.info("트렌드 신호 완료 — 리뷰 %d/%d, 동접 %d/%d",
             review_ok, len(review_ids), player_ok, len(player_ids))
    return review_ok, player_ok


def _plan(conn, log) -> tuple[list[tuple[int, str | None]], set[int]]:
    """(부를 목록, 그중 개척분 appid). 개척 적중률을 따로 재려면 구분이 필요하다 —
    첫 배포에서 개척 440개 중 8개만 건진 걸 진행 로그로 역산해서야 알았다."""
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
        done = store.probed_appids(conn)
        pool = steam.all_appids()
        if pool:
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
            # 전체 목록을 못 받아도 개척을 멈추지 않는다.
            # appid 는 10 단위로 순차 배정되므로 '큰 번호 = 최근'이고, 10 의 배수만
            # 실재한다. 존재가 확인된 최대 appid 에서 10 씩 내려간다.
            # (1 씩 훑던 때는 호출의 90% 가 존재할 수 없는 번호로 갔다 — 적중률 1.8%)
            step = max(config.EXPLORE_STEP, 1)
            top = store.max_game_appid(conn) + config.EXPLORE_NUMERIC_MARGIN
            ceiling = top - (top % step)
            if ceiling <= step:
                log.warning("아직 아는 게임이 없어 개척을 건너뛴다")
            else:
                log.warning("전체 목록을 못 받아 번호 훑기로 개척한다 "
                            "(%d 부터 %d 씩 내려감)", ceiling, step)
                appid = ceiling
                while n_explore < room and appid > step:
                    if appid not in done and take(appid, None):
                        n_explore += 1
                    appid -= step

    explore_ids = {a for a, _ in targets[len(targets) - n_explore:]} if n_explore else set()
    log.info("이번 실행 %d개 = 기존갱신 %d + 큐레이션 %d + 신규개척 %d",
             len(targets), n_refresh, n_featured, n_explore)
    return targets, explore_ids


def main() -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s")
    log = logging.getLogger("collect")
    conn = store.connect()

    if "--signals-only" in sys.argv:
        review_ok, player_ok = _collect_signals(conn, log)
        if review_ok or player_ok:
            store.set_meta(conn, "last_signal_at", datetime.now(timezone.utc).isoformat(timespec="seconds"))
            conn.commit()
        conn.close()
        return 0 if review_ok or player_ok else 1

    targets, explore_ids = _plan(conn, log)
    if not targets:
        log.error("부를 대상이 없다. 스팀 API 응답을 확인할 것.")
        conn.close()
        return 1

    ok = failed = dropped = 0
    ex_ok = ex_seen = 0          # 개척분만 따로. 적중률이 나쁘면 훑는 위치가 틀린 것이다
    for i, (appid, tag) in enumerate(targets, 1):
        app = steam.fetch_app(appid)
        # 실패도 기록한다 — 안 하면 다음 실행에서 같은 죽은 appid 를 또 부른다.
        store.mark_probed(conn, appid, app is not None)
        is_ex = appid in explore_ids
        ex_seen += is_ex
        if app is None:
            failed += 1
        elif store.save(conn, app, tag):
            ok += 1
            ex_ok += is_ex
        else:
            dropped += 1        # 게임이지만 보관 대상 아님 (한국어X·데모X·구작)
        if i % 50 == 0:
            conn.commit()
            log.info("  진행 %d/%d (저장 %d, 무관 %d, 제외 %d)",
                     i, len(targets), ok, dropped, failed)
    conn.commit()

    # appdetails 전체 수집과 분리된 작은 후보군만 확인한다. 이 단계가 실패해도
    # 가격 수집 결과는 유지되고, 홈은 기존 리뷰 수 기반으로 안전하게 폴백한다.
    _collect_signals(conn, log)
    store.set_meta(conn, "last_collection_at", datetime.now(timezone.utc).isoformat(timespec="seconds"))
    conn.commit()

    if ex_seen:
        log.info("개척 적중률 %d/%d (%.1f%%) — 낮으면 훑는 위치가 틀린 것이다",
                 ex_ok, ex_seen, 100 * ex_ok / ex_seen)
    # 응답에 미디어가 실제로 오는지. 트레일러가 0 이면 여기서 원인이 드러난다.
    ms = steam.MEDIA_STATS
    if ms["apps"]:
        log.info("미디어 — 앱 %d개 중 스크린샷 %d / movies 키 있음 %d / 항목 있음 %d / 영상URL %d",
                 ms["apps"], ms["screenshots"], ms["movies_key"],
                 ms["movies_items"], ms["got_mp4"])
        if ms["sample_movie_keys"]:
            log.info("  movies[0] 키: %s", ms["sample_movie_keys"])
            log.info("  mp4/webm 키: %s", ms["sample_src_keys"] or "(사전 아님)")
        elif ms["movies_key"] == 0:
            log.warning("  appdetails 응답에 movies 필드 자체가 없다 "
                        "— 스팀이 더 이상 주지 않는 것으로 보인다. 스크린샷만 쓴다.")
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
