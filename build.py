"""정적 사이트 생성. GitHub Actions 가 수집 직후 이 파일을 실행한다."""
import html
import json
import logging
import os
import sys
from datetime import date, datetime, timezone, timedelta

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


def _series(hist: list[dict], end_date: str | None):
    """이력을 (날짜서수, 가격) 목록으로. 가격 행은 '변동 시점'만 있으므로
    마지막 가격을 관측 마지막 날까지 수평으로 이어준다 (그게 실제로 유지된 가격이다)."""
    pts = []
    for h in hist:
        if h["price_final"] <= 0:
            continue
        try:
            pts.append((date.fromisoformat(h["on_date"]).toordinal(), h["price_final"]))
        except (ValueError, TypeError):
            continue
    if not pts:
        return []
    if end_date:
        try:
            eo = date.fromisoformat(end_date).toordinal()
            if eo > pts[-1][0]:
                pts.append((eo, pts[-1][1]))     # 마지막 가격이 오늘까지 유지됨
        except ValueError:
            pass
    return pts


def _step_path(pts, X, Y):
    """계단식 경로. 가격은 다음 변동까지 그대로 유지되므로
    점을 사선으로 잇는 것은 사실과 다르다 (서서히 내린 것처럼 보임)."""
    d = [f"{X(pts[0][0]):.1f},{Y(pts[0][1]):.1f}"]
    for i in range(1, len(pts)):
        d.append(f"{X(pts[i][0]):.1f},{Y(pts[i-1][1]):.1f}")   # 수평 유지
        d.append(f"{X(pts[i][0]):.1f},{Y(pts[i][1]):.1f}")     # 변동 순간 수직
    return " ".join(d)


def sparkline(hist: list[dict], end_date: str | None = None, w=88, h=40) -> str:
    """목록용 미니 추이. 형태만 보여주는 보조 표시이고, 수치는 옆에 숫자로 있다."""
    pts = _series(hist, end_date)
    if len(pts) < 2 or len({p[1] for p in pts}) < 2:
        # 변동이 없으면 '변동 없음'을 평선으로. 없는 기복을 그리지 않는다.
        return (f'<svg class="spark" viewBox="0 0 {w} {h}" aria-hidden="true">'
                f'<line x1="0" y1="{h/2}" x2="{w}" y2="{h/2}" stroke="var(--grid)" '
                f'stroke-width="2" stroke-linecap="round"/></svg>')
    t0, t1 = pts[0][0], pts[-1][0]
    tspan = (t1 - t0) or 1
    lo = min(p[1] for p in pts)
    hi = max(p[1] for p in pts)
    span = (hi - lo) or 1
    pad = 3

    def X(t):
        return (t - t0) / tspan * w

    def Y(v):
        return pad + (1 - (v - lo) / span) * (h - 2 * pad)

    line = _step_path(pts, X, Y)
    area = f"{line} {w:.1f},{h} 0,{h}"
    ex, ey = X(pts[-1][0]), Y(pts[-1][1])
    return (
        f'<svg class="spark" viewBox="0 0 {w} {h}" aria-hidden="true">'
        f'<polygon points="{area}" fill="var(--brand-soft)"/>'
        f'<polyline points="{line}" fill="none" stroke="var(--brand)" stroke-width="2" '
        f'stroke-linejoin="round" stroke-linecap="round"/>'
        f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="3" fill="var(--brand)" '
        f'stroke="var(--surface)" stroke-width="2"/>'
        f'</svg>'
    )


def detail_chart(hist: list[dict], atl: int, end_date: str | None = None) -> str:
    """상세 가격 추이. x축은 날짜에 비례한다 —
    점을 균등 간격으로 놓으면 '6개월 공백'과 '하루 간격'이 똑같이 보여서 거짓이 된다."""
    pts = _series(hist, end_date)
    if len(pts) < 2:
        return ('<div class="waiting">가격 추적을 시작했습니다.<br>'
                '가격이 한 번이라도 바뀌면 이 자리에 추이가 그려집니다.</div>')

    W, H = 720, 240
    ML, MR, MT, MB = 58, 14, 16, 30
    iw, ih = W - ML - MR, H - MT - MB
    t0, t1 = pts[0][0], pts[-1][0]
    tspan = (t1 - t0) or 1
    vals = [v for _, v in pts]
    lo, hi = min(vals), max(vals)
    if hi == lo:
        pad_v = max(hi * 0.1, 1)
    else:
        pad_v = (hi - lo) * 0.12
    lo_a, hi_a = max(0, lo - pad_v), hi + pad_v

    def X(t):
        return ML + (t - t0) / tspan * iw

    def Y(v):
        return MT + (1 - (v - lo_a) / (hi_a - lo_a)) * ih

    line = _step_path(pts, X, Y)
    area = f"{line} {X(t1):.1f},{MT+ih:.1f} {ML:.1f},{MT+ih:.1f}"

    ticks = []
    for v in nice_ticks(lo_a, hi_a):
        y = Y(v)
        ticks.append(
            f'<line x1="{ML}" y1="{y:.1f}" x2="{W-MR}" y2="{y:.1f}" '
            f'stroke="var(--grid)" stroke-width="1"/>'
            f'<text x="{ML-8}" y="{y+4:.1f}" text-anchor="end" font-size="11" '
            f'fill="var(--ink-3)">{v:,}</text>')

    atl_line = ""
    if atl and lo_a <= atl <= hi_a:
        ay = Y(atl)
        atl_line = (
            f'<line x1="{ML}" y1="{ay:.1f}" x2="{W-MR}" y2="{ay:.1f}" '
            f'stroke="var(--ink-3)" stroke-width="1.5" stroke-dasharray="5 4" opacity=".8"/>'
            # 데이터 위에 겹쳐도 읽히도록 표면색 후광을 두른다
            f'<text x="{W-MR}" y="{ay-7:.1f}" text-anchor="end" font-size="11" '
            f'fill="var(--ink-3)" stroke="var(--surface)" stroke-width="3.5" '
            f'paint-order="stroke" stroke-linejoin="round">추적 중 최저 {atl:,}원</text>')

    d0 = date.fromordinal(t0).isoformat()
    d1 = date.fromordinal(t1).isoformat()
    xlabels = (
        f'<text x="{ML}" y="{H-9}" font-size="11" fill="var(--ink-3)">{d0[2:]}</text>'
        f'<text x="{W-MR}" y="{H-9}" text-anchor="end" font-size="11" '
        f'fill="var(--ink-3)">{d1[2:]}</text>')

    ex, ey = X(t1), Y(pts[-1][1])
    data = json.dumps([{"d": date.fromordinal(t).isoformat(), "v": v,
                        "x": round(X(t), 1), "y": round(Y(v), 1)}
                       for t, v in pts], ensure_ascii=False)

    return f"""<div class="chartwrap">
<svg class="chart" viewBox="0 0 {W} {H}" role="img"
     aria-label="가격 추이 계단 그래프. {d0} {pts[0][1]:,}원부터 {d1} {pts[-1][1]:,}원까지, 변동 {len(pts)-1}회.">
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

DEFAULT_DESC = ("한국어로 할 수 있는 스팀 신작·데모·출시예정 게임을 매일 두 번 자동으로 모읍니다. "
                "원화 가격과 변동 이력도 함께 기록합니다.")


def abs_url(rel: str) -> str:
    """sitemap·canonical·og:url 은 절대 URL 이어야 한다.
    SITE_URL 이 없으면(로컬 테스트) 상대 경로를 그대로 둔다."""
    base = (config.SITE_URL or "").rstrip("/")
    return f"{base}/{rel.lstrip('./')}" if base else rel


def page(title: str, body: str, updated: str, nav: bool = True,
         desc: str = "", canonical: str = "", og_image: str = "",
         depth: int = 0) -> str:
    """depth: 하위 폴더 깊이. game/xxx.html 은 1 이라 상위 경로가 '../' 가 된다."""
    up = "../" * depth
    # 메뉴는 사이트가 실제로 잘하는 축(한국어 · 데모 · 신작 · 출시예정)을 먼저 둔다.
    # 가격은 2일치뿐이라 앞세우면 가장 약한 데이터로 첫인상을 만들게 된다.
    jump = (f"""<nav class="jump">
    <a href="{up}korean-demo.html">데모</a>
    <a href="{up}korean-new.html">신작</a>
    <a href="{up}korean-soon.html">출시예정</a>
    <a href="{up}under-10000.html">1만원 이하</a>
    <a href="{up}index.html#sale">할인 중</a>
    <a href="{up}index.html#all">전체</a>
  </nav>""" if nav else "")
    search = (f"""<form class="hsearch" role="search" onsubmit="return sq(this)">
    <input type="search" name="q" placeholder="게임 이름 검색" aria-label="게임 이름 검색">
    <button type="submit" aria-label="검색">
      <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2"
           aria-hidden="true"><circle cx="7" cy="7" r="4.5"/><path d="M10.5 10.5L15 15"/></svg>
    </button>
  </form>
  <script>function sq(f){{var v=(f.q.value||'').trim();
    location.href='{up}index.html'+(v?'#q='+encodeURIComponent(v):'#all');
    if(window.applyHash)window.applyHash();return false;}}</script>""" if nav else "")
    desc = desc or DEFAULT_DESC
    can = (f'<link rel="canonical" href="{esc(abs_url(canonical))}">'
           if canonical else "")
    og_img = (f'<meta property="og:image" content="{esc(og_image)}">'
              f'<meta name="twitter:card" content="summary_large_image">'
              if og_image else '<meta name="twitter:card" content="summary">')
    og_u = (f'<meta property="og:url" content="{esc(abs_url(canonical))}">'
            if canonical else "")
    # 검색엔진 소유 확인 태그. 값이 없으면 태그 자체를 내보내지 않는다.
    verify = ""
    if config.GOOGLE_VERIFY:
        verify += f'<meta name="google-site-verification" content="{esc(config.GOOGLE_VERIFY)}">'
    if config.NAVER_VERIFY:
        verify += f'<meta name="naver-site-verification" content="{esc(config.NAVER_VERIFY)}">'
    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
{verify}
{can}
<meta property="og:type" content="website">
<meta property="og:site_name" content="스팀딜 레이더">
<meta property="og:locale" content="ko_KR">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
{og_u}
{og_img}
{theme.FONTS}
<style>{theme.CSS}</style>
</head>
<body>
<header class="top"><div class="topin">
  <a class="logo" href="{up}index.html">
    <b>스팀<i>딜</i> 레이더</b>
    <span>{esc(config.SITE_TAGLINE)}</span>
  </a>
  {search}
  {jump}
</div></header>
<div class="wrap">
{body}
<footer>
  <p class="updated">가격 기준 시각: {esc(updated)} KST</p>
  <p>가격은 스팀 공식 상점 API(한국 스토어·원화)에서 하루 두 번 자동 수집합니다. 표시 시점과 실제 가격이 다를 수 있으니 구매 전 스팀에서 확인하세요.</p>
  <p>최저가 표시는 가격을 {config.MIN_DAYS_FOR_LOW}일 이상 지켜본 게임에만 답니다. '역대 최저'는 {config.MIN_DAYS_FOR_ATL}일 이상 관측한 경우이며, 이 사이트가 추적을 시작한 뒤의 최저값이라 스팀의 전체 가격 역사와는 다를 수 있습니다.</p>
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
    """최저가 표기.

    관측 2일차의 "2일 최저"는 사실상 '수집한 뒤 가격이 안 바뀌었다'는 뜻인데,
    초록 배지로 달면 진짜 역대최저처럼 읽힌다. 그래서 아예 달지 않는다.
      30일 미만  → 배지 없음
      30~59일    → "N일 최저" (기간을 밝힌 제한적 주장)
      60일 이상  → "역대최저" (MIN_DAYS_FOR_ATL)
    """
    days = g.get("days_tracked", 0)
    if not (g.get("at_lowest") and days >= config.MIN_DAYS_FOR_LOW):
        return ""
    if g.get("atl_trustworthy"):
        return theme.BADGE_ATL
    return f'<span class="t atl">{days}일 최저</span>'


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
    """카드에는 고를 때 필요한 것만 남긴다: 표지 · 제목 · 성격 · 가격.

    0~100 합성 점수는 뺐다. 이름을 뭘로 바꾸든 한눈에 뜻이 안 잡히고,
    할인 75%·리뷰 83만인 게임이 48점으로 나오면 고장난 숫자로 보인다.
    점수는 목록 정렬에만 내부적으로 쓰고, 근거는 상세에서 문장으로 보여준다.
    """
    score = g.get("score") or 0
    rc = (f'리뷰 {g["review_count"]:,}' if (g.get("review_count") or 0) >= 10
          else esc(g.get("developer") or g.get("genres") or ""))
    hist = g.get("history") or []
    # 가격이 실제로 변한 적이 있을 때만 추이를 그린다.
    # 2일치 데이터에서 전부 평선을 그리면 아무 정보도 없는 장식이 된다.
    left = (sparkline(hist, g.get("price_last"))
            if len({h["price_final"] for h in hist if h["price_final"] > 0}) > 1
            else (f'<span class="offtag">-{g["discount_pct"]}%</span>'
                  if g.get("discount_pct") else ""))
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
  <div class="eyebrow">오늘의 한 편</div>
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
        <a class="btn btn-p" href="./game/{g['appid']}.html">자세히 보기</a>
        {demo_btn}
        <a class="btn btn-s" href="https://store.steampowered.com/app/{g['appid']}/?cc=kr"
           target="_blank" rel="noopener">스팀 상점</a>
      </div>
    </div>
  </div>
</section>"""


# ---------------------------------------------------------------- 홈

def section(sid: str, title: str, note: str, items: list[dict],
            empty: str, rail: bool = False, cap: int = 8,
            more_href: str = "#all", more_text: str = "전체에서 더 보기") -> str:
    """홈 섹션. 상한은 8개다 — 120개를 세로로 다 쌓으면 모바일에서 2만 픽셀이 되고,
    그러면 아래쪽 섹션은 아무도 못 본다. 나머지는 각자의 목록 페이지로 보낸다."""
    if not items:
        body = f'<div class="grid"><div class="none">{esc(empty)}</div></div>'
        cnt = ""
    else:
        cls = "rail" if rail else "grid"
        body = f'<div class="{cls}">' + "".join(card(g) for g in items[:cap]) + "</div>"
        cnt = f'<span class="cnt">{len(items)}개</span>'
    note_html = f'<p class="sec-note">{esc(note)}</p>' if note else ""
    more = (f'<a class="more" href="{esc(more_href)}">{esc(more_text)} →</a>'
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
    n_kr = sum(1 for g in safe if g.get("korean"))
    tiles = "".join(
        f'<div class="tile"><div class="k">{k}</div><div class="v">{v}</div></div>'
        for k, v in [
            ("한국어 지원", f'{n_kr:,}<small>개</small>'),
            ("데모 가능", f'{n_demo:,}<small>개</small>'),
            ("출시예정", f'{n_soon:,}<small>개</small>'),
            ("추적 게임", f'{len(games):,}<small>개</small>'),
            ("수집 일수", f'{days:,}<small>일</small>'),
        ]
    )

    # 최저가 판정은 관측 30일부터 배지로 나가고 60일부터 '역대최저'가 된다.
    # 그 전까지는 왜 최저가 표시가 없는지 밝혀두는 편이 낫다.
    atl_note = ("" if days >= config.MIN_DAYS_FOR_LOW else
                f'<p class="sec-note">가격 추적은 {days}일째입니다. '
                f'최저가 표시는 {config.MIN_DAYS_FOR_LOW}일, '
                f'"역대 최저"는 {config.MIN_DAYS_FOR_ATL}일이 모여야 나옵니다.</p>')

    body = f"""
{hero(top)}

{section("pick", "오늘의 추천", "한국어를 지원하고, 데모가 있거나 새로 나왔거나 곧 나오는 게임.", rest_cands, "아직 후보가 없습니다. 다음 수집에서 채워집니다.", more_href="#all", more_text="전체 보기")}

{section("demo", "데모로 먼저 해볼 수 있는 게임", "사기 전에 무료로 해볼 수 있는 것들.", demos, "데모가 있는 게임이 아직 수집되지 않았습니다.", rail=True, more_href="korean-demo.html", more_text="한국어 데모 전체")}

{section("new", "새로 나온 게임", "", fresh, "신작 목록이 아직 비어 있습니다.", rail=True, more_href="korean-new.html", more_text="한국어 신작 전체")}

{section("soon", "곧 나오는 게임", "출시 전에 미리 찜해두면 좋은 것들.", soon, "출시예정 목록이 아직 비어 있습니다.", rail=True, more_href="korean-soon.html", more_text="출시예정 전체")}

{section("sale", "할인 중", "원화 가격을 하루 두 번 기록합니다.", on_sale, "할인 중인 게임이 아직 없습니다.", rail=True, more_href="#all", more_text="전체에서 더 보기")}
{atl_note}

<section id="all">
  <div class="sec-head"><h2>전체 게임에서 찾기</h2>
    <span class="cnt" id="cnt">{len(games)}개</span></div>
  <div class="tools">
    <input type="search" id="q" placeholder="게임 이름 검색" aria-label="게임 이름 검색">
    <select id="sort" aria-label="정렬 기준">
      <option value="score">추천순</option>
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
  <div class="morewrap" id="moreWrap" hidden>
    <button class="morebtn" id="moreBtn" type="button">더 보기</button>
  </div>
</section>

<div class="tiles">{tiles}</div>

<script>
(function(){{
  var PAGE=24, shown=PAGE;
  var list=document.getElementById('list'), q=document.getElementById('q');
  var sort=document.getElementById('sort'), adult=document.getElementById('adult');
  var msg=document.getElementById('noneMsg'), cnt=document.getElementById('cnt');
  var moreWrap=document.getElementById('moreWrap'), moreBtn=document.getElementById('moreBtn');
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
  function render(){{
    var vis=cards.filter(keep);
    cards.forEach(function(c){{ c.hidden=true; }});
    vis.sort(cmp).forEach(function(c,i){{ if(i<shown) c.hidden=false; list.appendChild(c); }});
    list.appendChild(msg);
    msg.hidden = vis.length>0;
    cnt.textContent = vis.length+'개';
    // 전부 그리지 않고 24개씩 늘린다. 검색은 숨은 카드까지 전부 대상으로 한다.
    moreWrap.hidden = vis.length<=shown;
    moreBtn.textContent = '더 보기 ('+Math.min(shown,vis.length)+' / '+vis.length+')';
  }}
  function apply(){{ shown=PAGE; render(); }}
  moreBtn.addEventListener('click',function(){{ shown+=PAGE; render(); }});
  q.addEventListener('input',apply);
  sort.addEventListener('change',apply);
  adult.addEventListener('change',apply);
  chips.forEach(function(c){{
    c.addEventListener('click',function(){{
      chips.forEach(function(x){{ x.setAttribute('aria-pressed',String(x===c)); }});
      f=c.dataset.f; apply();
    }});
  }});

  // 헤더 검색창이 넘겨준 #q=... 을 받아 목록에 반영하고 그 자리로 데려간다.
  window.applyHash=function(){{
    var h=location.hash||'';
    if (h.indexOf('#q=')!==0) return;
    try {{ q.value=decodeURIComponent(h.slice(3)); }} catch(e) {{ q.value=h.slice(3); }}
    apply();
    document.getElementById('all').scrollIntoView();
  }};
  window.addEventListener('hashchange', window.applyHash);
  apply();
  window.applyHash();
}})();
</script>
"""
    return page("스팀딜 레이더 — 한국어 지원 스팀 신작 · 데모 · 출시예정",
                body, updated, canonical="index.html",
                og_image=(top.get("header_image") or ""),
                desc=(f"스팀 게임 {len(games):,}개의 한국어 지원 여부와 원화 가격을 추적합니다. "
                      f"한국어 데모 {n_demo}개, 출시예정 {n_soon}개를 매일 두 번 자동 갱신."))


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
        d = g["days_tracked"]
        if d < config.MIN_DAYS_FOR_LOW:
            # 2일 관측으로 '2일 최저'라고 적으면 최저가 정보처럼 읽힌다.
            # 이 단계에서 정직하게 말할 수 있는 사실은 '언제부터 봤는가' 뿐이다.
            facts.append(("가격 추적 시작", f'{esc(g.get("price_first") or "—")} ({d}일째)'))
        else:
            low = f'{g["lowest_seen"]:,}원' if g.get("lowest_seen") else "—"
            label = "역대 최저" if g.get("atl_trustworthy") else f"추적 {d}일 최저"
            facts.append((label, low))
    fact_rows = "".join(f'<tr><th>{esc(k)}</th><td>{v}</td></tr>' for k, v in facts)

    why = "".join(f"<li>{esc(w)}</li>" for w in (g.get("why") or []))
    # 합성 점수 대신 근거를 문장으로. 숫자 하나보다 이쪽이 검증 가능하다.
    why_panel = (f"""<div class="panel">
  <h3>이 게임을 고른 이유</h3>
  <p class="sub">아래 항목은 스팀 상점 정보에서 그대로 확인한 사실입니다.
     '역대 최저가와의 차이'는 가격 이력이 충분히 쌓인 뒤에 반영합니다.</p>
  <ul class="whylist">{why}</ul>
</div>""" if why else "")

    hist = g.get("history") or []
    days = g.get("days_tracked") or 0
    if len(hist) >= 2:
        # 이력은 '가격이 바뀐 날'만 담긴다. 표에도 그렇게 적어야 오해가 없다.
        rows = "".join(
            f'<tr><td>{esc(h["on_date"])}</td><td>{h["price_final"]:,}원</td>'
            f'<td>{("-" + str(h["discount_pct"]) + "%") if h["discount_pct"] else "—"}</td></tr>'
            for h in reversed(hist))
        chart_inner = (detail_chart(hist, g.get("lowest_seen") or 0, g.get("price_last")) +
                       f"""<details><summary>가격이 바뀐 날 {len(hist)}건 보기</summary>
    <div class="tablewrap"><table><thead>
    <tr><th>바뀐 날</th><th>가격</th><th>할인</th></tr></thead>
    <tbody>{rows}</tbody></table></div></details>""")
        sub = (f"{days}일 지켜보는 동안 {len(hist) - 1}번 바뀌었습니다. "
               f"가격은 다음 변동까지 유지되므로 계단으로 그립니다.")
    else:
        # 빈 그래프를 보여주는 대신 왜 비었는지 말한다
        chart_inner = ('<div class="waiting">가격 추적을 시작했습니다.<br>'
                       '가격이 한 번이라도 바뀌면 이 자리에 추이가 그려집니다.</div>')
        sub = (f"{days}일째 지켜보는 중이고, 아직 가격이 바뀌지 않았습니다."
               if days > 1 else "하루 두 번 자동으로 확인합니다.")
    if len(hist) >= 2:
        chart = f"""<div class="panel">
  <h3>원화 가격 추이</h3>
  <p class="sub">{sub}</p>
  {chart_inner}
</div>"""
    else:
        # 아직 보여줄 추이가 없다. 접어두고, 열면 왜 비었는지 설명한다.
        chart = f"""<div class="panel">
  <details><summary>원화 가격 추이 — {esc(sub)}</summary>
  {chart_inner}
  </details>
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
    # 제목에 가격을 넣으면 검색결과에서 클릭할 이유가 생긴다.
    if g.get("is_free"):
        pt = f'{g["name"]} — 무료'
    elif g.get("price_final"):
        pt = f'{g["name"]} — {g["price_final"]:,}원'
        if g.get("discount_pct"):
            pt += f' ({g["discount_pct"]}% 할인)'
    else:
        pt = f'{g["name"]} — 출시예정' if g.get("coming_soon") else g["name"]

    bits = []
    if g.get("korean"):
        bits.append("한국어 지원")
    if g.get("has_demo") or g.get("app_type") == "demo":
        bits.append("데모 있음")
    if g.get("release_text"):
        bits.append(f'{g["release_text"]} 출시')
    d = f'{g["name"]} 스팀 원화 가격과 변동 이력.' + (" " + " · ".join(bits) if bits else "")

    return page(pt, body, updated, canonical=f"game/{g['appid']}.html",
                og_image=(g.get("header_image") or ""), desc=d, depth=1)


# ---------------------------------------------------------------- 랜딩(검색 유입용)

# 우리 데이터만 정직하게 답할 수 있는 질문들.
# '스팀 최저가' 같은 거대 키워드는 선행 6개를 이길 수 없어서 쓰지 않는다.
LANDINGS = [
    dict(slug="korean-demo",
         title="스팀 한국어 데모 — 지금 무료로 해볼 수 있는 게임",
         h1="한국어 지원 데모",
         desc="한국어를 지원하고 데모를 무료로 받을 수 있는 스팀 게임 목록. 매일 두 번 자동 갱신.",
         note="사기 전에 무료로 먼저 해볼 수 있고, 한국어까지 되는 게임만 모았습니다.",
         pick=lambda g: g.get("korean") and (g.get("has_demo") or g.get("app_type") == "demo"),
         sort=lambda g: -(g.get("review_count") or 0)),
    dict(slug="korean-new",
         title="스팀 한국어 지원 신작 — 최근 나온 게임",
         h1="한국어 지원 신작",
         desc="최근 스팀에 출시된 게임 중 한국어를 지원하는 것만 골라 매일 갱신합니다.",
         note="최근 출시 순입니다.",
         pick=lambda g: g.get("korean") and g.get("tag") == "신작" and not g.get("coming_soon"),
         sort=lambda g: (g.get("release_date") or "", g.get("name") or ""), rev=True),
    dict(slug="korean-soon",
         title="스팀 출시예정 한국어 게임 — 곧 나오는 것",
         h1="곧 나오는 한국어 게임",
         desc="아직 출시되지 않았지만 한국어를 지원할 예정인 스팀 게임 목록.",
         note="출시일이 가까운 순입니다. 출시 전에 찜해두면 좋습니다.",
         pick=lambda g: g.get("korean") and g.get("coming_soon"),
         sort=lambda g: (g.get("release_date") or "9999", g.get("name") or "")),
    dict(slug="under-10000",
         title="스팀 1만원 이하 한국어 게임",
         h1="1만원 이하 한국어 게임",
         desc="현재 스팀 원화 가격이 1만원 이하이고 한국어를 지원하는 게임 목록.",
         note="현재 판매가 기준입니다. 낮은 가격 순.",
         pick=lambda g: (g.get("korean") and 0 < (g.get("price_final") or 0) <= 10000),
         sort=lambda g: g.get("price_final") or 0),
]


def build_landing(spec: dict, games: list[dict], updated: str) -> str:
    items = sorted([g for g in games if not g.get("adult") and spec["pick"](g)],
                   key=spec["sort"], reverse=spec.get("rev", False))
    grid = ('<div class="grid">' + "".join(card(g) for g in items) + "</div>"
            if items else
            '<div class="grid"><div class="none">'
            '아직 조건에 맞는 게임이 수집되지 않았습니다. 다음 갱신에서 채워집니다.'
            '</div></div>')
    body = f"""
<section id="top">
  <div class="sec-head"><h2>{esc(spec['h1'])}</h2>
    <span class="cnt">{len(items)}개</span>
    <a class="more" href="./index.html">전체 보기 →</a></div>
  <p class="sec-note">{esc(spec['note'])}</p>
  {grid}
</section>
"""
    return page(spec["title"], body, updated,
                canonical=f"{spec['slug']}.html", desc=spec["desc"],
                og_image=(items[0].get("header_image") if items else ""))


def build_sitemap(paths: list[str], updated: str) -> str:
    if not config.SITE_URL:
        # 절대 URL 없이는 유효한 사이트맵을 만들 수 없다. 빈 파일보다 낫게 표시만 남긴다.
        return '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"></urlset>\n'
    day = updated[:10]
    urls = "".join(
        f"  <url><loc>{esc(abs_url(p))}</loc><lastmod>{day}</lastmod>"
        f"<changefreq>daily</changefreq>"
        f"<priority>{'1.0' if p == 'index.html' else ('0.8' if '/' not in p else '0.6')}</priority>"
        f"</url>\n" for p in paths)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            f"{urls}</urlset>\n")


def build_robots() -> str:
    sm = f"\nSitemap: {abs_url('sitemap.xml')}" if config.SITE_URL else ""
    return f"User-agent: *\nAllow: /\n{sm}\n"


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

    def write(rel: str, text: str) -> None:
        with open(os.path.join(config.SITE_DIR, rel), "w", encoding="utf-8") as f:
            f.write(text)

    write("index.html", build_index(games, updated))
    paths = ["index.html"]

    for spec in LANDINGS:
        write(f"{spec['slug']}.html", build_landing(spec, games, updated))
        paths.append(f"{spec['slug']}.html")

    # 성인 게임 상세는 만들되 사이트맵에 넣지 않는다 (검색에 내보내지 않음)
    for g in games:
        write(os.path.join("game", f"{g['appid']}.html"), build_detail(g, updated))
        if not g.get("adult"):
            paths.append(f"game/{g['appid']}.html")

    write("sitemap.xml", build_sitemap(paths, updated))
    write("robots.txt", build_robots())
    # GitHub Pages 가 _ 로 시작하는 경로를 Jekyll 로 처리하지 않게
    open(os.path.join(config.SITE_DIR, ".nojekyll"), "w").close()

    cands = len(store.broadcast_candidates(games))
    demos = sum(1 for g in games if g.get("has_demo") or g.get("app_type") == "demo")
    adult = sum(1 for g in games if g.get("adult"))
    if not config.SITE_URL:
        log.warning("SITE_URL 이 비어 있어 사이트맵/canonical 이 절대 URL 이 아니다 "
                    "(로컬 테스트면 정상, Actions 면 환경변수 확인)")
    log.info("생성 완료 — 게임 %d개(성인 %d 숨김), 방송후보 %d, 데모 %d, "
             "랜딩 %d, 사이트맵 %d개 URL → %s",
             len(games), adult, cands, demos, len(LANDINGS), len(paths), config.SITE_DIR)
    return 0


if __name__ == "__main__":
    sys.exit(main())
