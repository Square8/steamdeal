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


def sparkline(hist: list[dict], w=88, h=40) -> str:
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
        f'<polygon points="{area}" fill="var(--brand-soft)"/>'
        f'<polyline points="{line}" fill="none" stroke="var(--brand)" stroke-width="2" '
        f'stroke-linejoin="round" stroke-linecap="round"/>'
        # 끝점(현재가)을 강조. 표면색 링으로 선과 분리한다.
        f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="3" fill="var(--brand)" '
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
  <polygon points="{area}" fill="var(--brand-soft)"/>
  <polyline points="{line}" fill="none" stroke="var(--brand)" stroke-width="2"
            stroke-linejoin="round" stroke-linecap="round"/>
  <circle cx="{ex:.1f}" cy="{ey:.1f}" r="4.5" fill="var(--brand)"
          stroke="var(--surface)" stroke-width="2"/>
  {xlabels}
  <line class="cross" x1="0" y1="{MT}" x2="0" y2="{MT+ih}" stroke="var(--ink-3)"
        stroke-width="1" opacity="0"/>
  <circle class="hoverdot" r="4.5" fill="var(--brand)" stroke="var(--surface)"
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


# ---------------------------------------------------------------- 페이지 골격

def page(title: str, body: str, updated: str, nav: bool = True) -> str:
    jump = ("""<nav class="jump">
    <a href="./index.html#pick">방송 후보</a>
    <a href="./index.html#demo">데모</a>
    <a href="./index.html#new">신작</a>
    <a href="./index.html#soon">출시예정</a>
    <a href="./index.html#sale">할인</a>
    <a href="./index.html#all">전체</a>
  </nav>""" if nav else "")
    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="한국어를 지원하는 스팀 신작·데모·출시예정 게임을 매일 자동으로 모아 보여줍니다. 원화 가격과 가격 추이를 함께 기록합니다.">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="한국어 지원 스팀 신작·데모·출시예정을 매일 자동으로.">
{theme.FONTS}
<style>{theme.CSS}</style>
</head>
<body>
<header class="top"><div class="topin">
  <a class="logo" href="./index.html">
    <b>스팀<i>딜</i> 레이더</b>
    <span>{esc(config.SITE_TAGLINE)}</span>
  </a>
  {jump}
  <div class="updated">{esc(updated)} KST 갱신</div>
</div></header>
<div class="wrap">
{body}
<footer>
  <p>가격은 스팀 공식 상점 API(한국 스토어·원화)에서 하루 두 번 자동 수집합니다. 표시 시점과 실제 가격이 다를 수 있으니 구매 전 스팀에서 확인하세요.</p>
  <p>'역대 최저'는 이 사이트가 추적을 시작한 뒤 기록한 최저값이며, 스팀의 전체 가격 역사와 다를 수 있습니다.</p>
  <p>성적 콘텐츠가 포함된 게임은 기본 화면에서 숨겨집니다.</p>
</footer>
</div>
</body>
</html>"""


# ---------------------------------------------------------------- 카드 조각

def chips_for(g: dict, show_atl: bool = True) -> str:
    """게임 성격을 칩으로. 색만으로 뜻을 전하지 않도록 항상 글자를 쓴다."""
    out = []
    if g.get("app_type") == "demo" or g.get("has_demo"):
        out.append('<span class="t demo">데모</span>')
    if g.get("coming_soon"):
        out.append('<span class="t soon">출시예정</span>')
    elif g.get("tag") == "신작":
        out.append('<span class="t new">신작</span>')
    if g.get("is_free"):
        out.append('<span class="t free">무료</span>')
    if not g.get("korean"):
        out.append('<span class="t nokr">한국어 없음</span>')
    if g.get("adult"):
        out.append('<span class="t adult">성인</span>')
    if show_atl and atl_label(g):
        out.append(atl_label(g))
    return f'<div class="chips">{"".join(out)}</div>' if out else ""


def atl_label(g: dict) -> str:
    """최저가 표기. 관측 하루뿐이면 아무 말도 하지 않는다 —
    첫날엔 모든 게임이 자기 자신의 유일한 기록이라 전부 '최저'가 되어버린다."""
    if not (g.get("at_lowest") and g.get("days_tracked", 0) > 1):
        return ""
    if g.get("atl_trustworthy"):
        return theme.BADGE_ATL
    return f'<span class="t atl">{g["days_tracked"]}일 최저</span>'


def shot(g: dict, ribbon: bool = True) -> str:
    """표지 이미지. 없으면 검은 빈칸 대신 머리글자 자리표시를 쓴다."""
    rib = (f'<span class="ribbon">-{g["discount_pct"]}%</span>'
           if ribbon and g.get("discount_pct") else "")
    if g.get("header_image"):
        inner = (f'<img src="{esc(g["header_image"])}" alt="{esc(g["name"])} 표지" '
                 f'loading="lazy" decoding="async">')
    else:
        initial = esc((g.get("name") or "?").strip()[:2].upper())
        inner = f'<div class="ph" aria-hidden="true">{initial}</div>'
    return f'<div class="shot">{inner}{rib}</div>'


def price_html(g: dict) -> str:
    if g.get("is_free"):
        return '<div class="price"><span class="now">무료</span></div>'
    if not g.get("price_final"):
        label = "출시 전" if g.get("coming_soon") else "가격 미정"
        return f'<div class="price"><span class="now">{label}</span></div>'
    was = (f'<span class="strike">{g["price_initial"]:,}원</span>'
           if g.get("price_initial", 0) > g["price_final"] else "")
    return (f'<div class="price"><span class="now">{g["price_final"]:,}원</span>'
            f'{was}</div>')


def card(g: dict) -> str:
    """카드에는 고를 때 필요한 것만 남긴다: 표지 · 제목 · 성격 · 가격 · 점수."""
    score = g.get("score") or 0
    rc = (f'리뷰 {g["review_count"]:,}' if (g.get("review_count") or 0) >= 10
          else esc(g.get("developer") or g.get("genres") or ""))
    left = (f'<div class="score" title="방송 적합도 {score}점">'
            f'<span class="score-n">{score}</span>'
            f'<span class="bar" role="img" aria-label="방송 적합도 {score}점 중 100점">'
            f'<i style="width:{score}%"></i></span></div>'
            if score else sparkline(g.get("history") or []))
    return f"""<a class="card" href="./game/{g['appid']}.html"
   data-n="{esc(g['name']).lower()}" data-demo="{1 if (g.get('has_demo') or g.get('app_type')=='demo') else 0}"
   data-soon="{g.get('coming_soon') or 0}" data-new="{1 if g.get('tag')=='신작' else 0}"
   data-kr="{g.get('korean') or 0}" data-adult="{g.get('adult') or 0}"
   data-off="{g.get('discount_pct') or 0}" data-price="{g.get('price_final') or 0}"
   data-score="{score}" data-atl="{1 if atl_label(g) else 0}">
  {shot(g)}
  <div class="card-b">
    <div class="name">{esc(g['name'])}</div>
    {chips_for(g)}
    <div class="tagline">{rc}</div>
    <div class="card-f">{left}{price_html(g)}</div>
  </div>
</a>"""


def hero(g: dict) -> str:
    why = "".join(f"<li>{esc(w)}</li>" for w in (g.get("why") or [])[:4])
    pct = (f'<span class="pct">-{g["discount_pct"]}%</span>'
           if g.get("discount_pct") else "")
    if g.get("is_free"):
        big = '<span class="big">무료</span>'
    elif g.get("price_final"):
        strike = (f'<span class="strike">{g["price_initial"]:,}원</span>'
                  if g.get("price_initial", 0) > g["price_final"] else "")
        big = f'<span class="big">{g["price_final"]:,}원</span>{strike}{pct}'
    else:
        big = f'<span class="big">{"출시 전" if g.get("coming_soon") else "가격 미정"}</span>'
    dev = f'<p class="dev">{esc(g["developer"])}</p>' if g.get("developer") else ""
    demo_id = g.get("demo_appid") or g["appid"]
    demo_btn = (f'<a class="btn btn-s" href="https://store.steampowered.com/app/{demo_id}/?cc=kr"'
                f' target="_blank" rel="noopener">데모 받기</a>'
                if (g.get("has_demo") or g.get("app_type") == "demo") else "")
    return f"""<section class="hero-sec" id="top">
  <div class="eyebrow">오늘 가장 방송할 만한 것</div>
  <div class="hero">
    <a class="hero-img" href="./game/{g['appid']}.html" aria-label="{esc(g['name'])} 상세">
      {shot(g, ribbon=True)}
    </a>
    <div class="hero-body">
      <h2>{esc(g['name'])}</h2>
      {dev}
      {chips_for(g)}
      <p class="desc">{esc((g.get('description') or '')[:150])}</p>
      <ul class="whylist">{why}</ul>
      <div class="hero-price">{big}</div>
      <div class="buyrow">
        <a class="btn btn-p" href="./game/{g['appid']}.html">가격 추이 보기</a>
        {demo_btn}
        <a class="btn btn-s" href="https://store.steampowered.com/app/{g['appid']}/?cc=kr"
           target="_blank" rel="noopener">스팀 상점</a>
      </div>
    </div>
  </div>
</section>"""


# ---------------------------------------------------------------- 홈

def section(sid: str, title: str, note: str, items: list[dict],
            empty: str, rail: bool = False, cap: int = 12) -> str:
    if not items:
        body = f'<div class="grid"><div class="none">{esc(empty)}</div></div>'
        cnt = ""
    else:
        cls = "rail" if rail else "grid"
        body = f'<div class="{cls}">' + "".join(card(g) for g in items[:cap]) + "</div>"
        cnt = f'<span class="cnt">{len(items)}개</span>'
    note_html = f'<p class="sec-note">{esc(note)}</p>' if note else ""
    more = ('<a class="more" href="#all">전체에서 더 보기 →</a>'
            if len(items) > cap else "")
    return f"""<section id="{sid}">
  <div class="sec-head"><h2>{esc(title)}</h2>{cnt}{more}</div>
  {note_html}
  {body}
</section>"""


def build_index(games: list[dict], updated: str) -> str:
    import store as _store
    # 기본 화면은 성적 콘텐츠를 제외한다. 전체 탐색기에서 토글로 켤 수 있다.
    safe = [g for g in games if not g.get("adult")]
    cands = _store.broadcast_candidates(games)          # 이미 점수순 정렬
    top = cands[0] if cands else (safe[0] if safe else games[0])

    # 히어로에 쓴 게임만 아래에서 뺀다.
    # 섹션끼리는 겹쳐도 된다 — '데모'를 보러 온 사람에게 데모 섹션이 비어 있으면 안 되니까.
    # 예전 문제는 겹침 자체가 아니라 모든 섹션이 '같은 정렬로 같은 목록'이었던 것이므로,
    # 섹션마다 정렬 기준을 다르게 줘서 실제로 다른 화면이 되게 한다.
    def rest(pool):
        return [g for g in pool if g["appid"] != top["appid"]]

    rest_cands = rest(cands)
    demos = sorted(rest([g for g in safe
                         if g.get("has_demo") or g.get("app_type") == "demo"]),
                   key=lambda g: -(g.get("review_count") or 0))   # 인기 있는 데모 먼저
    fresh = sorted(rest([g for g in safe if g.get("tag") == "신작"]),
                   key=lambda g: (g.get("release_date") or "", g.get("name") or ""),
                   reverse=True)                                   # 최근 출시 먼저
    soon = sorted(rest([g for g in safe if g.get("coming_soon")]),
                  key=lambda g: (g.get("release_date") or "9999", g.get("name") or ""))
    on_sale = sorted(rest([g for g in safe if g.get("discount_pct")]),
                     key=lambda g: -g["discount_pct"])

    days = max((g.get("days_tracked", 0) for g in games), default=0)
    n_demo = sum(1 for g in safe if g.get("has_demo") or g.get("app_type") == "demo")
    n_soon = sum(1 for g in safe if g.get("coming_soon"))
    tiles = "".join(
        f'<div class="tile"><div class="k">{k}</div><div class="v">{v}</div></div>'
        for k, v in [
            ("방송 후보", f'{len(cands):,}<small>개</small>'),
            ("데모 가능", f'{n_demo:,}<small>개</small>'),
            ("출시예정", f'{n_soon:,}<small>개</small>'),
            ("추적 게임", f"{len(games):,}"),
            ("수집 일수", f'{days:,}<small>일</small>'),
        ]
    )

    atl_note = ("" if days > config.MIN_DAYS_FOR_ATL else
                f'<p class="sec-note">가격 추적은 {days}일째입니다. '
                f'"역대 최저" 판정은 {config.MIN_DAYS_FOR_ATL}일 이상 모여야 표시됩니다.</p>')

    body = f"""
{hero(top)}

{section("pick", "이번 주 방송 후보", "한국어를 지원하고, 데모가 있거나 새로 나왔거나 곧 나오는 게임을 방송 적합도 순으로.", rest_cands, "아직 후보가 없습니다. 다음 수집에서 채워집니다.")}

{section("demo", "데모로 먼저 해볼 수 있는 게임", "사기 전에, 방송으로 먼저.", demos, "데모가 있는 게임이 아직 수집되지 않았습니다.", rail=True)}

{section("new", "새로 나온 게임", "", fresh, "신작 목록이 아직 비어 있습니다.", rail=True)}

{section("soon", "곧 나오는 게임", "출시 전에 미리 찜해두면 좋은 것들.", soon, "출시예정 목록이 아직 비어 있습니다.", rail=True)}

{section("sale", "할인 중", "가격은 매일 기록됩니다.", on_sale, "할인 중인 게임이 아직 없습니다.")}
{atl_note}

<section id="all">
  <div class="sec-head"><h2>전체 게임에서 찾기</h2>
    <span class="cnt" id="cnt">{len(games)}개</span></div>
  <div class="tools">
    <input type="search" id="q" placeholder="게임 이름 검색" aria-label="게임 이름 검색">
    <select id="sort" aria-label="정렬 기준">
      <option value="score">방송 적합도순</option>
      <option value="off">할인율순</option>
      <option value="cheap">낮은 가격순</option>
      <option value="name">이름순</option>
    </select>
    <label class="sw"><input type="checkbox" id="adult"> 성인 게임 포함</label>
  </div>
  <div class="presets">
    <button class="chip" data-f="all" aria-pressed="true">전체</button>
    <button class="chip" data-f="demo" aria-pressed="false">데모 있음</button>
    <button class="chip" data-f="soon" aria-pressed="false">출시예정</button>
    <button class="chip" data-f="new" aria-pressed="false">신작</button>
    <button class="chip" data-f="kr" aria-pressed="false">한국어</button>
    <button class="chip" data-f="cheap" aria-pressed="false">1만원 이하</button>
    <button class="chip" data-f="off50" aria-pressed="false">50% 이상 할인</button>
  </div>
  <div class="grid" id="list">{"".join(card(g) for g in games)}
    <div class="none" id="noneMsg" hidden>조건에 맞는 게임이 없습니다.</div>
  </div>
</section>

<div class="tiles">{tiles}</div>

<script>
(function(){{
  var list=document.getElementById('list'), q=document.getElementById('q');
  var sort=document.getElementById('sort'), adult=document.getElementById('adult');
  var msg=document.getElementById('noneMsg'), cnt=document.getElementById('cnt');
  var chips=document.querySelectorAll('.presets .chip');
  var cards=Array.prototype.slice.call(list.querySelectorAll('.card'));
  var f='all';

  function keep(c){{
    var d=c.dataset;
    if (d.adult==='1' && !adult.checked) return false;
    var t=(q.value||'').trim().toLowerCase();
    if (t && d.n.indexOf(t)===-1) return false;
    if (f==='demo'  && d.demo!=='1') return false;
    if (f==='soon'  && d.soon!=='1') return false;
    if (f==='new'   && d.new!=='1')  return false;
    if (f==='kr'    && d.kr!=='1')   return false;
    if (f==='cheap' && !(+d.price>0 && +d.price<=10000)) return false;
    if (f==='off50' && +d.off<50)    return false;
    return true;
  }}
  function cmp(a,b){{
    var s=sort.value;
    if (s==='off')   return (+b.dataset.off)-(+a.dataset.off);
    if (s==='name')  return a.dataset.n.localeCompare(b.dataset.n,'ko');
    if (s==='cheap'){{
      // 가격 미정(0)은 '싼 것'이 아니므로 뒤로 보낸다
      var pa=+a.dataset.price||Infinity, pb=+b.dataset.price||Infinity;
      return pa-pb;
    }}
    return (+b.dataset.score)-(+a.dataset.score);
  }}
  function apply(){{
    var vis=cards.filter(keep);
    cards.forEach(function(c){{ c.hidden=true; }});
    vis.sort(cmp).forEach(function(c){{ c.hidden=false; list.appendChild(c); }});
    list.appendChild(msg);
    msg.hidden = vis.length>0;
    cnt.textContent = vis.length+'개';
  }}
  q.addEventListener('input',apply);
  sort.addEventListener('change',apply);
  adult.addEventListener('change',apply);
  chips.forEach(function(c){{
    c.addEventListener('click',function(){{
      chips.forEach(function(x){{ x.setAttribute('aria-pressed',String(x===c)); }});
      f=c.dataset.f; apply();
    }});
  }});
  apply();
}})();
</script>
"""
    return page("스팀딜 레이더 — 한국어 지원 스팀 신작·데모·할인", body, updated)


# ---------------------------------------------------------------- 상세

def build_detail(g: dict, updated: str) -> str:
    if g.get("is_free"):
        price_block = '<span class="big">무료</span>'
    elif g.get("price_final"):
        strike = (f'<span class="strike">{g["price_initial"]:,}원</span>'
                  if g.get("price_initial", 0) > g["price_final"] else "")
        pct = f'<span class="pct">-{g["discount_pct"]}%</span>' if g.get("discount_pct") else ""
        price_block = f'<span class="big">{g["price_final"]:,}원</span>{strike}{pct}'
    else:
        price_block = (f'<span class="big">'
                       f'{"출시 전" if g.get("coming_soon") else "가격 미정"}</span>')

    facts = []
    if g.get("developer"):
        facts.append(("개발사", esc(g["developer"])))
    if g.get("release_text"):
        facts.append(("출시", esc(g["release_text"]) +
                      (" (출시예정)" if g.get("coming_soon") else "")))
    if g.get("genres"):
        facts.append(("장르", esc(g["genres"])))
    facts.append(("한국어", "지원" if g.get("korean") else "미지원"))
    if (g.get("review_count") or 0) > 0:
        facts.append(("스팀 리뷰 수", f'{g["review_count"]:,}개'))
    if g.get("has_demo") or g.get("app_type") == "demo":
        demo_id = g.get("demo_appid") or g["appid"]
        facts.append(("데모", f'<a href="https://store.steampowered.com/app/{demo_id}/?cc=kr" '
                              f'target="_blank" rel="noopener" style="color:var(--brand)">'
                              f'스팀에서 데모 받기 →</a>'))
    if g.get("days_tracked"):
        low = f'{g["lowest_seen"]:,}원' if g.get("lowest_seen") else "—"
        label = "역대 최저" if g.get("atl_trustworthy") else f'추적 {g["days_tracked"]}일 최저'
        facts.append((label, low))
    fact_rows = "".join(f'<tr><th>{esc(k)}</th><td>{v}</td></tr>' for k, v in facts)

    why = "".join(f"<li>{esc(w)}</li>" for w in (g.get("why") or []))
    why_panel = (f"""<div class="panel">
  <h3>방송 적합도 {g.get('score', 0)}점</h3>
  <p class="sub">데모 여부·한국어 지원·신작 여부·가격만으로 계산합니다.
     '역대 최저가와의 차이'는 데이터가 충분히 쌓인 뒤에 반영합니다.</p>
  <ul class="whylist">{why}</ul>
</div>""" if why else "")

    hist = g.get("history") or []
    if len(hist) >= 2:
        rows = "".join(
            f'<tr><td>{esc(h["on_date"])}</td><td>{h["price_final"]:,}원</td>'
            f'<td>{("-" + str(h["discount_pct"]) + "%") if h["discount_pct"] else "—"}</td></tr>'
            for h in reversed(hist))
        chart_inner = (detail_chart(hist, g.get("lowest_seen") or 0) +
                       f"""<details><summary>표로 보기</summary>
    <div class="tablewrap"><table><thead>
    <tr><th>날짜</th><th>가격</th><th>할인</th></tr></thead>
    <tbody>{rows}</tbody></table></div></details>""")
        sub = "점선은 추적 기간 중 최저가입니다. 그래프에 마우스를 올리면 날짜별 가격이 나옵니다."
    else:
        # 빈 그래프를 보여주는 대신 왜 비었는지 말한다
        chart_inner = ('<div class="waiting">가격 추적을 시작했습니다.<br>'
                       '며칠 더 모이면 이 자리에 추이 그래프가 그려집니다.</div>')
        sub = "하루 두 번 자동으로 기록됩니다."
    chart = f"""<div class="panel">
  <h3>원화 가격 추이</h3>
  <p class="sub">{sub}</p>
  {chart_inner}
</div>"""

    demo_id = g.get("demo_appid") or g["appid"]
    demo_btn = (f'<a class="btn btn-s" href="https://store.steampowered.com/app/{demo_id}/?cc=kr"'
                f' target="_blank" rel="noopener">데모 받기</a>'
                if (g.get("has_demo") or g.get("app_type") == "demo") else "")

    body = f"""
<a class="back" href="./../index.html">← 목록으로</a>
<div class="dhero">
  {shot(g)}
  <div>
    <h1>{esc(g['name'])}</h1>
    {chips_for(g)}
    <p class="desc">{esc(g.get('description'))}</p>
    <div class="price-now">{price_block}</div>
    <div class="buyrow">
      <a class="btn btn-p" href="https://store.steampowered.com/app/{g['appid']}/?cc=kr"
         target="_blank" rel="noopener">스팀 상점에서 보기</a>
      {demo_btn}
    </div>
  </div>
</div>

{why_panel}

<div class="panel">
  <h3>정보</h3>
  <div class="tablewrap"><table>{fact_rows}</table></div>
</div>

{chart}
"""
    return page(g["name"], body, updated)


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

    cands = len(store.broadcast_candidates(games))
    demos = sum(1 for g in games if g.get("has_demo") or g.get("app_type") == "demo")
    adult = sum(1 for g in games if g.get("adult"))
    log.info("생성 완료 — 게임 %d개, 방송후보 %d개, 데모 %d개, 성인 %d개(기본 숨김) → %s",
             len(games), cands, demos, adult, config.SITE_DIR)
    return 0


if __name__ == "__main__":
    sys.exit(main())
