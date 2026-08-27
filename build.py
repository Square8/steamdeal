"""정적 사이트 생성. GitHub Actions 가 수집 직후 이 파일을 실행한다."""
import html
import json
import logging
import os
import sys
from datetime import datetime, timezone, timedelta

import config
import store
import theme

KST = timezone(timedelta(hours=9))


def won(v) -> str:
    return f"{v:,}원" if v else "—"


def esc(s) -> str:
    return html.escape(str(s or ""))


# ---------------------------------------------------------------- 차트


def nice_ticks(lo: float, hi: float, target: int = 4) -> list[int]:
    """1/2/2.5/5 x 10^n 계열의 '읽기 좋은' 눈금값을 고른다.
    68,688 같은 값이 축에 찍히지 않게 하고, 눈금 개수가 3~6개가 되도록 step 을 고른다."""
    import math
    span = max(hi - lo, 1e-9)
    mag = 10 ** math.floor(math.log10(span))
    best = None
    # 한 자릿수 위/아래까지 후보를 만들어 개수가 적당한 것을 고른다
    for exp in (mag * 10, mag, mag / 10, mag / 100):
        for m in (1, 2, 2.5, 5):
            step = m * exp
            if step <= 0:
                continue
            first = math.ceil(lo / step) * step
            vals = []
            v = first
            while v <= hi + step * 1e-9:
                vals.append(v)
                v += step
            n = len(vals)
            if n < 2:
                continue
            score = abs(n - target) + (0 if 3 <= n <= 6 else 10)
            ints = sorted(set(int(round(x)) for x in vals))
            if len(ints) < 2:
                continue          # 반올림 후 눈금이 겹치면 쓸 수 없다
            if best is None or score < best[0]:
                best = (score, ints)
    if best is None:
        a, b = int(round(lo)), int(round(hi))
        return [a, b] if a != b else [a]
    return best[1]


def sparkline(hist: list[dict], w=96, h=26) -> str:
    """목록용 미니 추이. 형태만 보여주는 보조 표시이고, 실제 수치는 옆 칼럼에 숫자로 있다."""
    pts = [p["price_final"] for p in hist if p["price_final"] > 0]
    if len(pts) < 2:
        return (f'<svg class="spark" viewBox="0 0 {w} {h}" aria-hidden="true">'
                f'<line x1="0" y1="{h/2}" x2="{w}" y2="{h/2}" stroke="var(--grid)" '
                f'stroke-width="2" stroke-linecap="round"/></svg>')
    lo, hi = min(pts), max(pts)
    span = (hi - lo) or 1
    pad = 3
    step = w / (len(pts) - 1)

    def xy(i, v):
        return i * step, pad + (1 - (v - lo) / span) * (h - 2 * pad)

    coords = [xy(i, v) for i, v in enumerate(pts)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
    area = f"{line} {w:.1f},{h} 0,{h}"
    ex, ey = coords[-1]
    return (
        f'<svg class="spark" viewBox="0 0 {w} {h}" aria-hidden="true">'
        f'<polygon points="{area}" fill="var(--series-soft)"/>'
        f'<polyline points="{line}" fill="none" stroke="var(--series)" stroke-width="2" '
        f'stroke-linejoin="round" stroke-linecap="round"/>'
        # 끝점(현재가)을 강조. 표면색 링으로 선과 분리한다.
        f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="3" fill="var(--series)" '
        f'stroke="var(--surface)" stroke-width="2"/>'
        f'</svg>'
    )


def detail_chart(hist: list[dict], atl: int) -> str:
    """상세 페이지 가격 추이. 단일 시리즈라 범례가 없고 제목이 시리즈를 지칭한다.
    역대 최저가는 기준선(점선, 저채도)으로 표시한다."""
    pts = [(p["on_date"], p["price_final"]) for p in hist if p["price_final"] > 0]
    if len(pts) < 2:
        return ('<p class="sub">가격 이력이 아직 하루치뿐이다. '
                '며칠 더 모이면 추이가 그려진다.</p>')

    W, H = 720, 240
    ML, MR, MT, MB = 58, 14, 14, 28
    iw, ih = W - ML - MR, H - MT - MB
    vals = [v for _, v in pts]
    lo, hi = min(vals), max(vals)
    if hi == lo:
        # 가격이 한 번도 변하지 않은 게임. 선이 정확히 가운데 오도록 위아래로 벌린다.
        pad_v = max(hi * 0.1, 1)
        lo_a, hi_a = max(0, lo - pad_v), hi + pad_v
    else:
        pad_v = (hi - lo) * 0.12
        lo_a, hi_a = max(0, lo - pad_v), hi + pad_v
    step = iw / (len(pts) - 1)

    def X(i):
        return ML + i * step

    def Y(v):
        return MT + (1 - (v - lo_a) / (hi_a - lo_a)) * ih

    line = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, (_, v) in enumerate(pts))
    area = f"{line} {X(len(pts)-1):.1f},{MT+ih:.1f} {ML:.1f},{MT+ih:.1f}"

    # y 눈금 (recessive grid, 읽기 좋은 값)
    ticks = []
    for v in nice_ticks(lo_a, hi_a):
        y = Y(v)
        ticks.append(
            f'<line x1="{ML}" y1="{y:.1f}" x2="{W-MR}" y2="{y:.1f}" '
            f'stroke="var(--grid)" stroke-width="1"/>'
            f'<text x="{ML-8}" y="{y+4:.1f}" text-anchor="end" font-size="11" '
            f'fill="var(--ink-3)">{v:,}</text>'
        )

    # 역대 최저가 기준선
    atl_line = ""
    if atl and lo_a <= atl <= hi_a:
        ay = Y(atl)
        atl_line = (
            f'<line x1="{ML}" y1="{ay:.1f}" x2="{W-MR}" y2="{ay:.1f}" '
            f'stroke="var(--ink-3)" stroke-width="1.5" stroke-dasharray="5 4" opacity=".8"/>'
            # 데이터 위에 겹쳐도 읽히도록 표면색 후광을 두른다
            f'<text x="{W-MR}" y="{ay-7:.1f}" text-anchor="end" font-size="11" '
            f'fill="var(--ink-3)" stroke="var(--surface)" stroke-width="3.5" '
            f'paint-order="stroke" stroke-linejoin="round">역대 최저 {atl:,}원</text>'
        )

    # x축 라벨: 처음/끝만 (모든 점에 숫자를 달지 않는다)
    xlabels = (
        f'<text x="{ML}" y="{H-8}" font-size="11" fill="var(--ink-3)">{pts[0][0][5:]}</text>'
        f'<text x="{W-MR}" y="{H-8}" text-anchor="end" font-size="11" '
        f'fill="var(--ink-3)">{pts[-1][0][5:]}</text>'
    )

    ex, ey = X(len(pts) - 1), Y(pts[-1][1])
    data = json.dumps([{"d": d, "v": v, "x": round(X(i), 1), "y": round(Y(v), 1)}
                       for i, (d, v) in enumerate(pts)], ensure_ascii=False)

    return f"""<div class="chartwrap">
<svg class="chart" viewBox="0 0 {W} {H}" role="img"
     aria-label="가격 추이 꺾은선 그래프. {pts[0][0]} {pts[0][1]:,}원부터 {pts[-1][0]} {pts[-1][1]:,}원까지.">
  {''.join(ticks)}
  {atl_line}
  <polygon points="{area}" fill="var(--series-soft)"/>
  <polyline points="{line}" fill="none" stroke="var(--series)" stroke-width="2"
            stroke-linejoin="round" stroke-linecap="round"/>
  <circle cx="{ex:.1f}" cy="{ey:.1f}" r="4.5" fill="var(--series)"
          stroke="var(--surface)" stroke-width="2"/>
  {xlabels}
  <line class="cross" x1="0" y1="{MT}" x2="0" y2="{MT+ih}" stroke="var(--ink-3)"
        stroke-width="1" opacity="0"/>
  <circle class="hoverdot" r="4.5" fill="var(--series)" stroke="var(--surface)"
          stroke-width="2" opacity="0"/>
</svg>
<div class="tip" role="status" aria-live="off"></div>
</div>
<script>
(function(){{
  var pts = {data};
  var svg = document.currentScript.parentNode.querySelector('.chart');
  var wrap = svg.parentNode, tip = wrap.querySelector('.tip');
  var cross = svg.querySelector('.cross'), dot = svg.querySelector('.hoverdot');
  var VB = {W};
  function move(ev){{
    var r = svg.getBoundingClientRect();
    var cx = (ev.touches ? ev.touches[0].clientX : ev.clientX) - r.left;
    var vx = cx / r.width * VB;
    var best = pts[0], bd = Infinity;
    for (var i=0;i<pts.length;i++){{
      var d = Math.abs(pts[i].x - vx);
      if (d < bd){{ bd = d; best = pts[i]; }}
    }}
    cross.setAttribute('x1', best.x); cross.setAttribute('x2', best.x);
    cross.setAttribute('opacity', '.45');
    dot.setAttribute('cx', best.x); dot.setAttribute('cy', best.y);
    dot.setAttribute('opacity', '1');
    tip.innerHTML = '<div class="d">'+best.d+'</div><div class="p">'+
                    best.v.toLocaleString('ko-KR')+'원</div>';
    tip.classList.add('on');
    var px = best.x / VB * r.width;
    tip.style.left = Math.min(Math.max(px - tip.offsetWidth/2, 0), r.width - tip.offsetWidth) + 'px';
    tip.style.top = '2px';
  }}
  function out(){{
    tip.classList.remove('on');
    cross.setAttribute('opacity','0'); dot.setAttribute('opacity','0');
  }}
  svg.addEventListener('mousemove', move);
  svg.addEventListener('mouseleave', out);
  svg.addEventListener('touchmove', move, {{passive:true}});
  svg.addEventListener('touchend', out);
}})();
</script>"""


# ---------------------------------------------------------------- 페이지

def page(title: str, body: str, updated: str) -> str:
    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="스팀 게임 가격을 원화로 추적해 지금 할인가가 역대 최저인지 알려준다.">
{theme.FONTS}
<style>{theme.CSS}</style>
</head>
<body>
<div class="wrap">
<header class="top">
  <div class="brand">
    <h1><a href="./index.html">{esc(config.SITE_NAME)}</a></h1>
    <span class="tag">{esc(config.SITE_TAGLINE)}</span>
  </div>
  <div class="updated">UPDATED {esc(updated)} KST</div>
</header>
{body}
<footer>
  <p>가격 정보는 스팀 공식 상점 API(한국 스토어, 원화)에서 자동 수집됩니다.</p>
  <p>역대 최저가는 이 사이트가 추적을 시작한 이후 기록된 최저값이며, 스팀의 전체 역사와 다를 수 있습니다.</p>
  <p>가격은 수집 시점 기준이므로 실제 구매 전 스팀 상점에서 확인하세요.</p>
</footer>
</div>
</body>
</html>"""


def row_html(g: dict) -> str:
    badge = theme.BADGE_ATL if g["is_all_time_low"] else ""
    off = f'-{g["discount_pct"]}%' if g["discount_pct"] else ""
    was = (f'<div class="was">{g["price_initial"]:,}원</div>'
           if g["price_initial"] > g["price_final"] else "")
    return f"""<a class="row" href="./game/{g['appid']}.html"
   data-name="{esc(g['name']).lower()}" data-atl="{1 if g['is_all_time_low'] else 0}"
   data-off="{g['discount_pct']}">
  <div class="name">{esc(g['name'])}{badge}</div>
  {sparkline(g['history'])}
  <div class="num"><div class="now">{won(g['price_final'])}</div>{was}</div>
  <div class="off">{off}</div>
</a>"""


def build_index(games: list[dict], updated: str) -> str:
    atl = [g for g in games if g["is_all_time_low"]]
    on_sale = sorted([g for g in games if g["discount_pct"] > 0],
                     key=lambda g: -g["discount_pct"])
    days = max((g["days_tracked"] for g in games), default=0)

    tiles = "".join(
        f'<div class="tile"><div class="k">{k}</div><div class="v">{v}</div></div>'
        for k, v in [
            ("추적 게임", f"{len(games):,}"),
            ("역대 최저가", f'{len(atl):,}<small>개</small>'),
            ("할인 중", f'{len(on_sale):,}<small>개</small>'),
            ("수집 일수", f'{days:,}<small>일</small>'),
        ]
    )

    atl_list = ("".join(row_html(g) for g in
                sorted(atl, key=lambda g: -g["discount_pct"])[:30])
                or '<div class="empty">지금 역대 최저가인 게임이 없다. 할인 시즌을 기다리자.</div>')

    sale_list = ("".join(row_html(g) for g in on_sale[:40])
                 or '<div class="empty">할인 중인 게임이 아직 수집되지 않았다.</div>')

    all_list = "".join(row_html(g) for g in sorted(games, key=lambda g: g["name"]))

    body = f"""
<div class="tiles">{tiles}</div>

<h2>지금 역대 최저가</h2>
<p class="hint">추적 시작 이후 기록된 가장 낮은 가격에 도달한 게임. 여기 있으면 지금이 사기 좋은 때다.</p>
<div class="list">{atl_list}</div>

<h2>할인율 순</h2>
<p class="hint">할인율이 크다고 역대 최저는 아니다. 위 목록과 겹치는지 확인하자.</p>
<div class="list">{sale_list}</div>

<h2>전체 추적 목록</h2>
<div class="controls">
  <input type="search" id="q" placeholder="게임 이름 검색" aria-label="게임 이름 검색">
  <button class="chip" data-f="all" aria-pressed="true">전체</button>
  <button class="chip" data-f="atl" aria-pressed="false">역대 최저만</button>
  <button class="chip" data-f="sale" aria-pressed="false">할인 중만</button>
</div>
<div class="list" id="all">{all_list}</div>

<script>
(function(){{
  var q = document.getElementById('q');
  var chips = document.querySelectorAll('.chip');
  var rows = Array.prototype.slice.call(document.querySelectorAll('#all .row'));
  var filter = 'all';
  function apply(){{
    var term = (q.value || '').trim().toLowerCase();
    rows.forEach(function(r){{
      var okName = !term || r.dataset.name.indexOf(term) !== -1;
      var okF = filter === 'all'
        || (filter === 'atl' && r.dataset.atl === '1')
        || (filter === 'sale' && parseInt(r.dataset.off,10) > 0);
      r.hidden = !(okName && okF);
    }});
  }}
  q.addEventListener('input', apply);
  chips.forEach(function(c){{
    c.addEventListener('click', function(){{
      chips.forEach(function(x){{ x.setAttribute('aria-pressed', String(x === c)); }});
      filter = c.dataset.f; apply();
    }});
  }});
}})();
</script>
"""
    return page(f"{config.SITE_NAME}", body, updated)


def build_detail(g: dict, updated: str) -> str:
    badge = theme.BADGE_ATL if g["is_all_time_low"] else ""
    img = (f'<img src="{esc(g["header_image"])}" alt="" loading="lazy">'
           if g["header_image"] else "")
    strike = (f'<span class="strike">{g["price_initial"]:,}원</span>'
              if g["price_initial"] > g["price_final"] else "")
    pct = f'<span class="pct">-{g["discount_pct"]}%</span>' if g["discount_pct"] else ""

    rows = "".join(
        f'<tr><td>{esc(h["on_date"])}</td><td>{h["price_final"]:,}원</td>'
        f'<td>{("-" + str(h["discount_pct"]) + "%") if h["discount_pct"] else "—"}</td></tr>'
        for h in reversed(g["history"])
    )

    body = f"""
<a class="back" href="./../index.html">← 전체 목록</a>
<div class="hero">
  {img}
  <div class="meta">
    <h1>{esc(g['name'])}{badge}</h1>
    <p class="desc">{esc(g['description'])}</p>
    <div class="price-now">
      <span class="big">{won(g['price_final'])}</span>{strike}{pct}
    </div>
    <div class="updated">역대 최저 {won(g['all_time_low'])} · {g['days_tracked']}일 추적</div>
  </div>
</div>

<div class="chartbox">
  <h3>{esc(g['name'])} 원화 가격 추이</h3>
  <p class="sub">점선은 추적 시작 이후 역대 최저가. 그래프에 마우스를 올리면 날짜별 가격이 나온다.</p>
  {detail_chart(g['history'], g['all_time_low'])}
  <details>
    <summary>표로 보기</summary>
    <div class="tablewrap">
      <table><thead><tr><th>날짜</th><th>가격</th><th>할인</th></tr></thead>
      <tbody>{rows}</tbody></table>
    </div>
  </details>
</div>

<p class="updated" style="margin-top:18px">
  <a href="https://store.steampowered.com/app/{g['appid']}/?cc=kr" target="_blank"
     rel="noopener">스팀 상점에서 보기 →</a>
</p>
"""
    return page(f"{g['name']} 가격 추이", body, updated)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")
    log = logging.getLogger("build")

    conn = store.connect()
    games = store.all_games(conn)
    conn.close()

    if not games:
        log.error("DB에 게임이 없다. 먼저 collect.py 를 실행할 것.")
        return 1

    updated = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    os.makedirs(os.path.join(config.SITE_DIR, "game"), exist_ok=True)

    with open(os.path.join(config.SITE_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(build_index(games, updated))
    for g in games:
        p = os.path.join(config.SITE_DIR, "game", f"{g['appid']}.html")
        with open(p, "w", encoding="utf-8") as f:
            f.write(build_detail(g, updated))
    # GitHub Pages 가 _ 로 시작하는 경로를 Jekyll 로 처리하지 않게
    open(os.path.join(config.SITE_DIR, ".nojekyll"), "w").close()

    atl = sum(1 for g in games if g["is_all_time_low"])
    log.info("생성 완료 — 게임 %d개, 역대최저 %d개 → %s", len(games), atl, config.SITE_DIR)
    return 0


if __name__ == "__main__":
    sys.exit(main())
