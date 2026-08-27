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


def chips_for(g: dict) -> str:
    """게임의 성격을 작은 칩으로. 색만으로 뜻을 전하지 않도록 항상 글자를 쓴다."""
    out = []
    if g.get("app_type") == "demo" or g.get("has_demo"):
        out.append('<span class="chip-tag demo">데모</span>')
    if g.get("coming_soon"):
        out.append('<span class="chip-tag soon">출시예정</span>')
    elif g.get("tag") == "신작":
        out.append('<span class="chip-tag new">신작</span>')
    if g.get("is_free"):
        out.append('<span class="chip-tag free">무료</span>')
    if not g.get("korean"):
        out.append('<span class="chip-tag nokr">한국어X</span>')
    return "".join(out)


def price_cell(g: dict) -> str:
    if g.get("is_free"):
        return '<div class="num"><div class="now">무료</div></div>'
    if not g.get("price_final"):
        return '<div class="num"><div class="now">—</div></div>'
    was = (f'<div class="was">{g["price_initial"]:,}원</div>'
           if g.get("price_initial", 0) > g["price_final"] else "")
    return f'<div class="num"><div class="now">{g["price_final"]:,}원</div>{was}</div>'


def row_html(g: dict) -> str:
    off = f'-{g["discount_pct"]}%' if g.get("discount_pct") else ""
    # 관측 기간이 충분할 때만 '역대최저'라고 말한다. 짧으면 일수를 밝힌다.
    # (수집 1일차엔 모든 게임이 자기 자신의 유일한 기록이라 '최저'가 되어버리므로
    #  days_tracked>1 을 반드시 같이 확인한다 — 배지 텍스트와 카드 강조 색을 항상 같은 조건으로 묶는다)
    show_low = bool(g.get("at_lowest") and g.get("days_tracked", 0) > 1)
    low_mark = ""
    if show_low:
        low_mark = (theme.BADGE_ATL if g.get("atl_trustworthy")
                    else f'<span class="chip-tag low">{g["days_tracked"]}일 최저</span>')
    rel = esc(g.get("release_text") or "")
    thumb = (f'<img class="thumb" src="{esc(g["header_image"])}" alt="" loading="lazy">'
             if g.get("header_image") else '<div class="thumb thumb-empty"></div>')
    desc = esc(g.get("description") or "")
    desc_html = f'<p class="card-desc">{desc}</p>' if desc else ""
    return f"""<a class="row" href="./game/{g['appid']}.html"
   data-name="{esc(g['name']).lower()}" data-demo="{1 if (g.get('has_demo') or g.get('app_type')=='demo') else 0}"
   data-soon="{g.get('coming_soon') or 0}" data-kr="{g.get('korean') or 0}"
   data-off="{g.get('discount_pct') or 0}" data-atl="{1 if show_low else 0}">
  {thumb}
  <div class="card-body">
    <div class="name">{esc(g['name'])}{chips_for(g)}{low_mark}
      <span class="sub-line">{rel}{(' · ' + esc(g['genres'])) if g.get('genres') else ''}</span>
    </div>
    {desc_html}
    <div class="card-foot">
      {sparkline(g['history'])}
      {price_cell(g)}
      <div class="off">{off}</div>
    </div>
  </div>
</a>"""


def build_index(games: list[dict], updated: str) -> str:
    import store as _store
    cands = _store.broadcast_candidates(games)
    demos = [g for g in cands if g.get("has_demo") or g.get("app_type") == "demo"]
    soon = [g for g in games if g.get("coming_soon")]
    fresh = [g for g in games if g.get("tag") == "신작"]
    on_sale = sorted([g for g in games if g.get("discount_pct")],
                     key=lambda g: -g["discount_pct"])
    days = max((g.get("days_tracked", 0) for g in games), default=0)

    tiles = "".join(
        f'<div class="tile"><div class="k">{k}</div><div class="v">{v}</div></div>'
        for k, v in [
            ("방송 후보", f'{len(cands):,}<small>개</small>'),
            ("데모 가능", f'{len(demos):,}<small>개</small>'),
            ("출시예정", f'{len(soon):,}<small>개</small>'),
            ("추적 게임", f"{len(games):,}"),
            ("수집 일수", f'{days:,}<small>일</small>'),
        ]
    )

    def block(items, empty):
        return ('<div class="list">' + "".join(row_html(g) for g in items) + '</div>'
                if items else f'<div class="list"><div class="empty">{empty}</div></div>')

    body = f"""
<div class="tiles">{tiles}</div>

<h2>이번 주 방송 후보</h2>
<p class="hint">한국어를 지원하고, 데모가 있거나 새로 나왔거나 곧 나오는 게임. 기준은 config.py 에서 바꿀 수 있다.</p>
{block(cands[:40], "아직 후보가 없다. collect.py 를 한 번 더 돌리면 채워진다.")}

<h2>데모 플레이 가능</h2>
<p class="hint">사기 전에 방송으로 먼저 해볼 수 있는 것들.</p>
{block(demos[:30], "데모가 있는 게임이 아직 수집되지 않았다.")}

<h2>곧 나옴</h2>
{block(soon[:30], "출시예정 목록이 아직 비어 있다.")}

<h2>새로 나옴</h2>
{block(fresh[:30], "신작 목록이 아직 비어 있다.")}

<h2>할인 중 <span class="side">(부수 기능)</span></h2>
<p class="hint">가격은 매일 같이 기록된다. 최저가 판단은 관측 {config.MIN_DAYS_FOR_ATL}일이 넘어야 신뢰할 수 있다.</p>
{block(on_sale[:30], "할인 중인 게임이 아직 없다.")}

<h2>전체</h2>
<div class="controls">
  <input type="search" id="q" placeholder="게임 이름 검색" aria-label="게임 이름 검색">
  <button class="chip" data-f="all" aria-pressed="true">전체</button>
  <button class="chip" data-f="demo" aria-pressed="false">데모</button>
  <button class="chip" data-f="soon" aria-pressed="false">출시예정</button>
  <button class="chip" data-f="kr" aria-pressed="false">한국어</button>
  <button class="chip" data-f="sale" aria-pressed="false">할인</button>
</div>
<div class="list" id="all">{"".join(row_html(g) for g in games)}</div>

<script>
(function(){{
  var q=document.getElementById('q'), chips=document.querySelectorAll('.chip');
  var rows=Array.prototype.slice.call(document.querySelectorAll('#all .row'));
  var f='all';
  function apply(){{
    var t=(q.value||'').trim().toLowerCase();
    rows.forEach(function(r){{
      var okName=!t||r.dataset.name.indexOf(t)!==-1;
      var okF = f==='all'
        || (f==='demo' && r.dataset.demo==='1')
        || (f==='soon' && r.dataset.soon==='1')
        || (f==='kr'   && r.dataset.kr==='1')
        || (f==='sale' && parseInt(r.dataset.off,10)>0);
      r.hidden=!(okName&&okF);
    }});
  }}
  q.addEventListener('input',apply);
  chips.forEach(function(c){{
    c.addEventListener('click',function(){{
      chips.forEach(function(x){{x.setAttribute('aria-pressed',String(x===c));}});
      f=c.dataset.f; apply();
    }});
  }});
}})();
</script>
"""
    return page(config.SITE_NAME, body, updated)


def build_detail(g: dict, updated: str) -> str:
    low_mark = ""
    if g.get("at_lowest") and g.get("days_tracked", 0) > 1:
        low_mark = (theme.BADGE_ATL if g.get("atl_trustworthy")
                    else f'<span class="chip-tag low">{g["days_tracked"]}일 최저</span>')
    img = (f'<img src="{esc(g["header_image"])}" alt="" loading="lazy">'
           if g.get("header_image") else "")

    if g.get("is_free"):
        price_block = '<span class="big">무료</span>'
    elif g.get("price_final"):
        strike = (f'<span class="strike">{g["price_initial"]:,}원</span>'
                  if g.get("price_initial", 0) > g["price_final"] else "")
        pct = f'<span class="pct">-{g["discount_pct"]}%</span>' if g.get("discount_pct") else ""
        price_block = f'<span class="big">{g["price_final"]:,}원</span>{strike}{pct}'
    else:
        price_block = '<span class="big">가격 미정</span>'

    facts = []
    if g.get("release_text"):
        facts.append(("출시", esc(g["release_text"]) +
                      (" (출시예정)" if g.get("coming_soon") else "")))
    if g.get("genres"):
        facts.append(("장르", esc(g["genres"])))
    facts.append(("한국어", "지원" if g.get("korean") else "미지원"))
    if g.get("has_demo") or g.get("app_type") == "demo":
        demo_id = g.get("demo_appid") or g["appid"]
        facts.append(("데모", f'<a href="https://store.steampowered.com/app/{demo_id}/?cc=kr" '
                              f'target="_blank" rel="noopener">스팀에서 데모 받기 →</a>'))
    if g.get("days_tracked"):
        low = f'{g["lowest_seen"]:,}원' if g.get("lowest_seen") else "—"
        label = "역대 최저" if g.get("atl_trustworthy") else f'추적 {g["days_tracked"]}일 최저'
        facts.append((label, low))
    fact_rows = "".join(
        f'<tr><th>{esc(k)}</th><td>{v}</td></tr>' for k, v in facts)

    hist_rows = "".join(
        f'<tr><td>{esc(h["on_date"])}</td><td>{h["price_final"]:,}원</td>'
        f'<td>{("-" + str(h["discount_pct"]) + "%") if h["discount_pct"] else "—"}</td></tr>'
        for h in reversed(g["history"])
    )
    chart = (f"""<div class="chartbox">
  <h3>원화 가격 추이</h3>
  <p class="sub">점선은 추적 기간 중 최저가. 그래프에 마우스를 올리면 날짜별 가격이 나온다.</p>
  {detail_chart(g['history'], g.get('lowest_seen') or 0)}
  <details><summary>표로 보기</summary>
    <div class="tablewrap"><table><thead><tr><th>날짜</th><th>가격</th><th>할인</th></tr></thead>
    <tbody>{hist_rows}</tbody></table></div>
  </details>
</div>""" if g["history"] else "")

    body = f"""
<a class="back" href="./../index.html">← 목록으로</a>
<div class="hero">
  {img}
  <div class="meta">
    <h1>{esc(g['name'])}{chips_for(g)}{low_mark}</h1>
    <p class="desc">{esc(g.get('description'))}</p>
    <div class="price-now">{price_block}</div>
  </div>
</div>

<div class="chartbox">
  <h3>정보</h3>
  <div class="tablewrap"><table>{fact_rows}</table></div>
</div>

{chart}

<p class="updated" style="margin-top:16px">
  <a href="https://store.steampowered.com/app/{g['appid']}/?cc=kr" target="_blank"
     rel="noopener">스팀 상점에서 보기 →</a>
</p>
"""
    return page(f"{g['name']}", body, updated)


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

    import store as _store
    cands = len(_store.broadcast_candidates(games))
    demos = sum(1 for g in games if g.get("has_demo") or g.get("app_type") == "demo")
    log.info("생성 완료 — 게임 %d개, 방송후보 %d개, 데모 %d개 → %s",
             len(games), cands, demos, config.SITE_DIR)
    return 0


if __name__ == "__main__":
    sys.exit(main())
