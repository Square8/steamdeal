"""정적 사이트 생성. GitHub Actions 가 수집 직후 이 파일을 실행한다."""
import hashlib
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


# CSS 를 페이지마다 인라인하면 16.6KB 가 게임 수만큼 복제된다.
# 실측: 게임 8,965개에서 사이트 221MB 중 152MB 가 CSS 중복분이었다.
# 외부 파일 하나로 빼면 그게 사라지고, 방문자 브라우저도 한 번만 받는다.
CSS_HASH = hashlib.sha1(theme.CSS.encode()).hexdigest()[:8]


def abs_url(rel: str) -> str:
    """sitemap·canonical·og:url 은 절대 URL 이어야 한다.
    SITE_URL 이 없으면(로컬 테스트) 상대 경로를 그대로 둔다."""
    base = (config.SITE_URL or "").rstrip("/")
    return f"{base}/{rel.lstrip('./')}" if base else rel


def freshness_info(raw: str | None) -> dict:
    """마지막 수집 완료 시각을 사용자에게 정직한 상태로 바꾼다."""
    if not raw:
        return {"label": "상태 확인 필요", "class": "needs", "display": "시각 없음"}
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        age = (datetime.now(timezone.utc) - dt).total_seconds()
        display = dt.astimezone(KST).strftime("%m-%d %H:%M")
    except (ValueError, TypeError):
        return {"label": "상태 확인 필요", "class": "needs", "display": str(raw)[:16]}
    if age <= 18 * 3600:
        label, cls = "최신 가격", "ok"
    elif age <= 36 * 3600:
        label, cls = "업데이트 지연", "late"
    else:
        label, cls = "데이터 오래됨", "stale"
    return {"label": label, "class": cls, "display": display}


WISHLIST_JS = """<script>
(function(){
  var KEY='steamdeal-wishlist-v1';
  var TARGET_KEY='steamdeal-target-price-v1';
  function read(){
    try { return new Set(JSON.parse(localStorage.getItem(KEY)||'[]').map(String)); }
    catch(e) { return new Set(); }
  }
  function write(set){
    try { localStorage.setItem(KEY, JSON.stringify(Array.from(set))); } catch(e) {}
  }
  function readTargets(){
    try { var raw=JSON.parse(localStorage.getItem(TARGET_KEY)||'{}'); return raw&&typeof raw==='object'?raw:{}; }
    catch(e) { return {}; }
  }
  function writeTargets(targets){
    try { localStorage.setItem(TARGET_KEY, JSON.stringify(targets)); } catch(e) {}
  }
  function paint(){
    var saved=read();
    document.querySelectorAll('[data-wish-id]').forEach(function(btn){
      if(!btn.dataset.wishBound){
        btn.addEventListener('click',function(ev){ ev.preventDefault(); ev.stopPropagation(); toggle(btn); });
        btn.dataset.wishBound='1';
      }
      var on=saved.has(String(btn.dataset.wishId));
      btn.classList.toggle('on',on);
      btn.setAttribute('aria-pressed',String(on));
      btn.setAttribute('aria-label',on?'찜 목록에서 삭제':'찜 목록에 추가');
      btn.textContent=on?'♥':'♡';
    });
    document.querySelectorAll('.wish-count').forEach(function(el){ el.textContent=saved.size; });
    paintTargetHits();
    paintTargetPanels();
  }
  function toggle(btn){
    var saved=read(), id=String(btn.dataset.wishId);
    if(saved.has(id)) saved.delete(id); else saved.add(id);
    write(saved); paint();
  }
  function paintTargetHits(){
    var targets=readTargets();
    document.querySelectorAll('.card[data-wish]').forEach(function(card){
      var id=String(card.dataset.wish), target=+targets[id]||0, price=+card.dataset.price||0;
      var chips=card.querySelector('.chips'), flag=card.querySelector('.target-hit-tag');
      var hit=target>0 && price>0 && price<=target;
      card.classList.toggle('target-hit',hit);
      if(hit && !flag){
        if(!chips){
          chips=document.createElement('div'); chips.className='chips';
          var name=card.querySelector('.name'); if(name) name.after(chips);
        }
        flag=document.createElement('span'); flag.className='t target-hit-tag';
        flag.textContent='목표가 도달'; if(chips) chips.prepend(flag);
      } else if(!hit && flag) flag.remove();
    });
  }
  function paintTargetPanels(){
    var targets=readTargets();
    document.querySelectorAll('[data-target-appid]').forEach(function(panel){
      var id=String(panel.dataset.targetAppid), price=+panel.dataset.currentPrice||0;
      var input=panel.querySelector('.target-input'), save=panel.querySelector('.target-save');
      var del=panel.querySelector('.target-del'), result=panel.querySelector('.target-result');
      var target=+targets[id]||0;
      if(input && !input.dataset.formatBound){
        input.addEventListener('input', function(){
          var val = this.value.replace(/[^0-9]/g, '');
          this.value = val ? Number(val).toLocaleString('ko-KR') : '';
        });
        input.dataset.formatBound='1';
      }
      if(input && document.activeElement!==input) input.value=target?target.toLocaleString('ko-KR'):'';
      if(result){
        if(target){
          result.innerHTML = '<strong class="current-target">현재 목표가: ' + target.toLocaleString('ko-KR') + '원</strong><br>' +
            (price<=target ? '🎉 목표가에 도달했습니다. 지금 가격을 확인해보세요.' : '현재가 ' + price.toLocaleString('ko-KR') + '원 · 아직 도달하지 않았습니다.');
        } else {
          result.textContent = '아직 목표 가격을 저장하지 않았습니다.';
        }
        result.classList.toggle('hit',!!target && price<=target);
      }
      if(del){
        del.style.display = target ? 'inline-block' : 'none';
        if(!del.dataset.delBound){
          del.addEventListener('click', function(){
            var next=readTargets(); delete next[id]; writeTargets(next); paint();
          });
          del.dataset.delBound='1';
        }
      }
      if(save && !save.dataset.targetBound){
        save.addEventListener('click',function(){
          var n=Number(String(input.value||'').replace(/[^0-9]/g,''));
          var next=readTargets();
          if(n>0){
            next[id]=n;
            var saved=read(); saved.add(id); write(saved);
          } else delete next[id];
          writeTargets(next); paint();
        });
        save.dataset.targetBound='1';
      }
    });
  }
  window.steamWishlist={read:read,write:write,paint:paint,toggle:toggle,readTargets:readTargets,writeTargets:writeTargets};
  document.addEventListener('DOMContentLoaded',paint);
})();
</script>"""

COMPARE_JS = '''<script>
(function(){
  var C_KEY = 'gamedil-compare-v1';
  function readC() {
    try {
      var raw = localStorage.getItem(C_KEY);
      if (!raw) return [];
      var arr = JSON.parse(raw);
      if (!Array.isArray(arr)) return [];

      var dirty = false;
      if (arr.length > 0 && typeof arr[0] === 'string') {
        localStorage.removeItem(C_KEY);
        return [];
      }

      var map = {};
      var out = [];
      for (var i = 0; i < arr.length; i++) {
        var g = arr[i];
        if (!g || typeof g !== 'object') { dirty = true; continue; }

        var appid = Number(g.appid);
        if (isNaN(appid) || appid <= 0) { dirty = true; continue; }

        if (g.adult) { dirty = true; continue; }
        if (map[appid]) { dirty = true; continue; }
        if (out.length >= 3) { dirty = true; continue; }

        var snap = {
          appid: appid,
          name: typeof g.name === 'string' ? g.name : '',
          header_image: typeof g.header_image === 'string' ? g.header_image : '',
          price_final: Math.max(0, Number(g.price_final) || 0),
          discount_pct: Math.max(0, Number(g.discount_pct) || 0),
          lowest_seen: Math.max(0, Number(g.lowest_seen) || 0),
          recent_drop_amount: Math.max(0, Number(g.recent_drop_amount) || 0),
          korean: !!g.korean,
          has_demo: !!g.has_demo,
          review_label: typeof g.review_label === 'string' ? g.review_label : '',
          review_positive_pct: typeof g.review_positive_pct === 'number' || typeof g.review_positive_pct === 'string' ? g.review_positive_pct : '',
          players_current: Math.max(0, Number(g.players_current) || 0),
          release_text: typeof g.release_text === 'string' ? g.release_text : '',
          adult: false
        };

        if (JSON.stringify(g) !== JSON.stringify(snap)) dirty = true;

        map[appid] = true;
        out.push(snap);
      }

      if (dirty) {
        try { localStorage.setItem(C_KEY, JSON.stringify(out)); } catch(e) {}
      }
      return out;
    } catch(e) { return []; }
  }
  function writeC(arr) {
    try { localStorage.setItem(C_KEY, JSON.stringify(arr)); } catch(e) {}
  }
  function toggleC(btn) {
    var arr = readC();
    var id = Number(btn.dataset.compareId);
    var idx = -1;
    for (var i = 0; i < arr.length; i++) { if (arr[i].appid === id) idx = i; }
    if (idx > -1) {
      arr.splice(idx, 1);
    } else {
      if (arr.length >= 3) {
        alert('비교함은 최대 3개까지만 담을 수 있습니다.');
        return;
      }
      try {
        var snap = JSON.parse(btn.dataset.snapshot);
        arr.push(snap);
      } catch(e) {}
    }
    writeC(arr);
    paintC();
  }
  function paintC() {
    var arr = readC();
    var hasId = {};
    for (var i = 0; i < arr.length; i++) hasId[arr[i].appid] = true;

    document.querySelectorAll('[data-compare-id]').forEach(function(btn) {
      if (!btn.dataset.compareBound) {
        btn.addEventListener('click', function(ev) { ev.preventDefault(); toggleC(btn); });
        btn.dataset.compareBound = '1';
      }
      var on = !!hasId[btn.dataset.compareId];
      btn.textContent = on ? '비교함에서 제거' : '비교함에 담기';
      btn.classList.toggle('on', on);
      btn.setAttribute('aria-pressed', String(on));
    });
    document.querySelectorAll('.compare-count').forEach(function(el) { el.textContent = arr.length; });
  }
  document.addEventListener('DOMContentLoaded', paintC);
  window.steamCompare = {read: readC, paint: paintC, write: writeC};
})();
</script>'''


def page(title: str, body: str, updated: str, nav: bool = True,
         desc: str = "", canonical: str = "", og_image: str = "",
         depth: int = 0, freshness: dict | None = None,
         extra_head: str = "") -> str:
    """depth: 하위 폴더 깊이. game/xxx.html 은 1 이라 상위 경로가 '../' 가 된다."""
    up = "../" * depth
    freshness = freshness or {"label": "자동 갱신 정상", "class": "ok", "display": updated}
    # 홈에서 바로 비교할 수 있는 순서와 메뉴 순서를 맞춘다.
    jump = (f"""<nav class="jump">
    <a href="{up}index.html#popular">지금 인기</a>
    <a href="{up}recent-drops.html">최근 인하</a>
    <a href="{up}index.html#hot">핫딜</a>
    <a href="{up}index.html#soon">기대작</a>
    <a href="{up}index.html#demo">데모</a>
    <a href="{up}under-10000.html">1만원 이하</a>
    <a href="{up}compare.html">비교 <span class="compare-count">0</span></a>
    <a href="{up}my-games.html">내 찜 <span class="wish-count">0</span></a>
    <a href="{up}index.html#all">전체</a>
  </nav>""" if nav else "")
    search = (f"""<form class="hsearch" role="search" action="{up}index.html" method="GET">
    <input type="search" name="q" placeholder="게임 이름 검색" aria-label="게임 이름 검색">
    <button type="submit" aria-label="검색">
      <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2"
           aria-hidden="true"><circle cx="7" cy="7" r="4.5"/><path d="M10.5 10.5L15 15"/></svg>
    </button>
  </form>""" if nav else "")
    desc = desc or DEFAULT_DESC
    can = (f'<link rel="canonical" href="{esc(abs_url(canonical))}">'
           if canonical else "")
    og_img = (f'<meta property="og:image" content="{esc(og_image)}">'
              f'<meta name="twitter:card" content="summary_large_image">'
              if og_image else '<meta name="twitter:card" content="summary">')
    og_u = (f'<meta property="og:url" content="{esc(abs_url(canonical))}">'
            f'\n<meta name="twitter:url" content="{esc(abs_url(canonical))}">'
            if canonical else "")
    # 검색엔진 소유 확인 태그. 값이 없으면 태그 자체를 내보내지 않는다.
    verify = ""
    if config.GOOGLE_VERIFY:
        verify += f'<meta name="google-site-verification" content="{esc(config.GOOGLE_VERIFY)}">'
    if config.NAVER_VERIFY:
        verify += f'<meta name="naver-site-verification" content="{esc(config.NAVER_VERIFY)}">'
    return f"""<!doctype html>
<html lang="ko" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#0b1220">
<link rel="icon" type="image/svg+xml" href="{up}favicon.svg">
<link rel="apple-touch-icon" href="{up}favicon.svg">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
{extra_head}
{verify}
{can}
<meta property="og:type" content="website">
<meta property="og:site_name" content="GameDil">
<meta property="og:locale" content="ko_KR">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
{og_u}
{og_img}
{theme.FONTS}
<link rel="stylesheet" href="{up}style.css?v={CSS_HASH}">
{WISHLIST_JS}
{COMPARE_JS}
</head>
<body>
<header class="top"><div class="topin">
  <a class="logo" href="{up}index.html">
    <b>Game<i>Dil</i></b>
    <span>{esc(config.SITE_TAGLINE)}</span>
  </a>
  <div class="freshness f-{freshness['class']}" title="스팀 데이터 갱신 상태">
    <span class="live-dot" aria-hidden="true"></span>
    <span class="f-lbl">{esc(freshness['label'])}</span>
    <time class="f-time">({esc(freshness['display'])} 기준)</time>
  </div>
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

REVIEW_LABELS = {
    "overwhelmingly positive": "압도적 긍정",
    "very positive": "매우 긍정적",
    "positive": "긍정적",
    "mostly positive": "대체로 긍정적",
    "mixed": "복합적",
    "mostly negative": "대체로 부정적",
    "negative": "부정적",
    "very negative": "매우 부정적",
    "overwhelmingly negative": "압도적 부정",
}


def review_label(g: dict) -> str:
    raw = (g.get("review_desc") or "").strip()
    return REVIEW_LABELS.get(raw.lower(), raw)


def is_overwhelming(g: dict) -> bool:
    raw = (g.get("review_desc") or "").lower()
    return "overwhelmingly positive" in raw or "압도적으로 긍정" in raw


def compact_num(v: int) -> str:
    v = int(v or 0)
    if v >= 10_000:
        return f"{v / 10_000:.1f}만".replace(".0만", "만")
    return f"{v:,}"


def checked_time(games: list[dict]) -> str:
    values = [g.get("players_checked_at") for g in games if g.get("players_checked_at")]
    if not values:
        return ""
    raw = max(values)
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt.astimezone(KST).strftime("%m/%d %H:%M")
    except (ValueError, AttributeError):
        return raw[:16]

def chips_for(g: dict, show_atl: bool = True) -> str:
    """게임 성격을 칩으로. 색만으로 뜻을 전하지 않도록 항상 글자를 쓴다."""
    out = []
    if show_atl and atl_label(g):
        out.append(atl_label(g))
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
    if review_label(g):
        out.append(f'<span class="t review">{esc(review_label(g))}</span>')
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
    pct = g.get("discount_pct") or 0
    rib = (f'<span class="ribbon {"r-hi" if pct >= 75 else "r-lo"}">-{pct}%</span>'
           if ribbon and pct else "")
    players = g.get("players_current") or 0
    playing = (f'<span class="player-badge">● {compact_num(players)}명 플레이 중</span>'
               if players else "")
    if g.get("header_image"):
        inner = (f'<img src="{esc(g["header_image"])}" alt="{esc(g["name"])} 표지" '
                 f'loading="lazy" decoding="async">')
    else:
        initial = esc((g.get("name") or "?").strip()[:2].upper())
        inner = f'<div class="ph" aria-hidden="true">{initial}</div>'
    return f'<div class="shot">{inner}{rib}{playing}</div>'


def off_class(pct: int) -> str:
    """할인 '세기'를 세 단계로. 전부 같은 파랑이면 -90% 와 -25% 가 똑같아 보인다.
    색만으로 전하지 않도록 숫자를 항상 함께 쓴다."""
    if pct >= 75:
        return "off-hi"
    if pct >= 50:
        return "off-mid"
    return "off-lo"


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


def card(g: dict, big: bool = False, depth: int = 0) -> str:
    """카드에는 고를 때 필요한 것만 남긴다: 표지 · 제목 · 성격 · 가격.

    0~100 합성 점수는 뺐다. 이름을 뭘로 바꾸든 한눈에 뜻이 안 잡히고,
    할인 75%·리뷰 83만인 게임이 48점으로 나오면 고장난 숫자로 보인다.
    점수는 목록 정렬에만 내부적으로 쓰고, 근거는 상세에서 문장으로 보여준다.
    """
    score = g.get("score") or 0
    players = g.get("players_current") or 0
    delta = g.get("player_delta") or 0
    if review_label(g):
        total = g.get("review_total") or g.get("review_count") or 0
        positive = g.get("review_positive_pct")
        extra = f" · 긍정 {positive}%" if positive is not None else ""
        rc = f"{review_label(g)} · 리뷰 {total:,}{extra}"
    else:
        rc = (f'리뷰 {g["review_count"]:,}' if (g.get("review_count") or 0) >= 10
              else esc(g.get("developer") or g.get("genres") or ""))
    # 동접은 이미지 배지에서 이미 보여주므로 카드 본문에서 같은 숫자를 반복하지 않는다.
    # 두 번째 측정부터만 증감 화살표를 보조 정보로 붙인다.
    if players and delta:
        rc = f"{rc} · {'▲' if delta > 0 else '▼'} {abs(delta):,}" if rc else f"{'▲' if delta > 0 else '▼'} {abs(delta):,}"
    hist = g.get("history") or []
    # 가격이 실제로 변한 적이 있을 때만 추이를 그린다.
    # 2일치 데이터에서 전부 평선을 그리면 아무 정보도 없는 장식이 된다.
    off = g.get("discount_pct") or 0
    if g.get("recent_drop_amount"):
        left = f'<span class="offtag" style="background:var(--accent);">최근 {g["recent_drop_amount"]:,}원 인하</span>'
    elif len({h["price_final"] for h in hist if h["price_final"] > 0}) > 1:
        left = sparkline(hist, g.get("price_last"))
    elif g.get("is_free"):
        left = ""          # 가격 칸이 이미 '무료'다. 같은 말을 두 번 쓰지 않는다.
    elif off:
        left = f'<span class="offtag {off_class(off)}">-{off}%</span>'
    else:
        left = ""
    # 왼쪽이 비면 구분선도 없앤다. 빈 줄이 반복되면 그 자체가 잡음이 된다.
    fcls = "card-f" if left else "card-f bare"
    up = "../" * depth
    return f"""<a class="card{' big' if big else ''}" href="{up}game/{g['appid']}.html"
   data-n="{esc(g['name']).lower()}" data-demo="{1 if (g.get('has_demo') or g.get('app_type')=='demo') else 0}"
   data-soon="{g.get('coming_soon') or 0}" data-new="{1 if g.get('tag')=='신작' else 0}"
   data-kr="{g.get('korean') or 0}" data-adult="{g.get('adult') or 0}"
   data-off="{g.get('discount_pct') or 0}" data-price="{g.get('price_final') or 0}"
   data-score="{score}" data-atl="{1 if atl_label(g) else 0}" data-wish="{g['appid']}">
  {shot(g)}
  <button class="wish" type="button" data-wish-id="{g['appid']}" aria-pressed="false"
          aria-label="찜 목록에 추가">♡</button>
  <div class="card-b">
    <div class="name">{esc(g['name'])}</div>
    {chips_for(g)}
    <div class="tagline">{rc}</div>
    <div class="{fcls}">{left}{price_html(g)}</div>
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
            more_href: str = "#all", more_text: str = "전체에서 더 보기",
            feature: bool = False) -> str:
    """홈 섹션. 상한은 8개다 — 120개를 세로로 다 쌓으면 모바일에서 2만 픽셀이 되고,
    그러면 아래쪽 섹션은 아무도 못 본다. 나머지는 각자의 목록 페이지로 보낸다."""
    if not items:
        body = f'<div class="grid"><div class="none">{esc(empty)}</div></div>'
        cnt = ""
    else:
        cls = "rail" if rail else "grid"
        # feature: 첫 카드만 2칸으로. 모든 섹션에 쓰면 다시 균일해져서 의미가 없다.
        picked = items[:cap]
        cards = "".join(card(g, big=(feature and i == 0)) for i, g in enumerate(picked))
        body = f'<div class="{cls}">{cards}</div>'
        cnt = f'<span class="cnt">{len(items)}개</span>'
    note_html = f'<p class="sec-note">{esc(note)}</p>' if note else ""
    more = (f'<a class="more" href="{esc(more_href)}">{esc(more_text)} →</a>'
            if len(items) > cap else "")
    return f"""<section id="{sid}">
  <div class="sec-head"><h2>{esc(title)}</h2>{cnt}{more}</div>
  {note_html}
  {body}
</section>"""


def lead(games: list[dict], safe: list[dict]) -> str:
    """첫 화면 명제 + 숫자.

    처음 온 사람은 2초 안에 '여기가 뭐 하는 곳인지' 알아야 한다.
    숫자를 문장 안에 넣으면 "스팀 게임이 78개뿐"으로 읽히므로 명제와 숫자를 분리한다.
    """
    n_kr = sum(1 for g in safe if g.get("korean"))
    n_demo = sum(1 for g in safe if g.get("korean")
                 and (g.get("has_demo") or g.get("app_type") == "demo"))
    n_sale = sum(1 for g in safe if g.get("korean") and (g.get("discount_pct") or 0) > 0)
    facts = [("한국어 게임", n_kr), ("무료 데모", n_demo), ("지금 할인", n_sale)]
    fh = "".join(f"<span>{esc(k)} <b>{v:,}</b></span>" for k, v in facts)
    return f"""<section class="lead" id="top">
  <p class="lead-kicker">STEAM DEAL RADAR</p>
  <h1>한국어로 할 수 있는 스팀 게임,<br>지금 살 만한 것부터.</h1>
  <p class="facts">{fh}</p>
  <div class="quick-actions" aria-label="빠른 조건">
    <button type="button" data-jump-filter="off50">🔥 50%+ 할인</button>
    <button type="button" data-jump-filter="cheap">💸 1만원 이하</button>
    <button type="button" data-jump-filter="demo">🎮 무료 데모</button>
    <button type="button" data-jump-filter="kr">🇰🇷 한국어</button>
    <button type="button" data-jump-filter="soon">🚀 출시예정</button>
    <button type="button" data-jump-filter="wish">♡ 찜 목록</button>
  </div>
</section>"""


def get_recent_drops(games: list[dict]) -> list[dict]:
    max_date = ""
    for g in games:
        for hist in g.get("history", []):
            if hist["on_date"] > max_date:
                max_date = hist["on_date"]

    if not max_date:
        return []

    from datetime import datetime, timedelta
    try:
        max_dt = datetime.strptime(max_date, "%Y-%m-%d")
        cutoff_dt = max_dt - timedelta(days=config.RECENT_DROP_DAYS)
        cutoff_str = cutoff_dt.strftime("%Y-%m-%d")
    except ValueError:
        return []

    drops = []
    for g in games:
        if g.get("adult") or not g.get("price_final") or g.get("is_free"):
            continue

        history = g.get("history", [])
        valid_hist = [h for h in history if h.get("price_final", 0) > 0]
        if len(valid_hist) < 2:
            continue

        last = valid_hist[-1]
        prev = valid_hist[-2]

        if last["on_date"] < cutoff_str:
            continue

        if prev["price_final"] > last["price_final"]:
            drop_amount = prev["price_final"] - last["price_final"]
            drop_rate = int(round((drop_amount / prev["price_final"]) * 100))

            game_copy = dict(g)
            game_copy["recent_drop_amount"] = drop_amount
            game_copy["recent_drop_rate"] = drop_rate
            game_copy["recent_drop_date"] = last["on_date"]
            drops.append(game_copy)

    drops.sort(key=lambda x: (
        not x.get("korean"),
        -x["recent_drop_amount"],
        -x["recent_drop_rate"],
        x.get("name") or ""
    ))
    return drops


def build_index(games: list[dict], updated: str, freshness: dict | None = None, recent_drops: list[dict] | None = None) -> str:
    # 기본 화면은 성적 콘텐츠를 제외한다. 전체 탐색기에서 토글로 켤 수 있다.
    safe = [g for g in games if not g.get("adult")]
    korean = [g for g in safe if g.get("korean")]

    # 실시간 동접은 공식 Steam 현재 플레이어 수 신호가 있을 때만 주장한다.
    player_pool = [g for g in korean if (g.get("players_current") or 0) > 0
                   and not g.get("coming_soon")]
    if player_pool:
        popular = sorted(player_pool, key=lambda g: (-(g.get("players_current") or 0),
                                                      -(g.get("review_count") or 0)))
        popular_title = "🔥 지금 많이 하는 한국어 게임"
        stamp = checked_time(player_pool)
        popular_note = f"Steam 현재 플레이어 수 · {stamp} KST 기준" if stamp else "Steam 현재 플레이어 수 기준"
    else:
        popular = sorted([g for g in korean if not g.get("coming_soon")],
                         key=lambda g: -(g.get("review_count") or 0))
        popular_title = "🔥 지금 많이 찾는 한국어 게임"
        popular_note = "동접 신호를 처음 수집하기 전까지 Steam 리뷰 수를 기준으로 보여줍니다."

    strict_hot = [g for g in korean if (g.get("discount_pct") or 0) >= 70
                  and is_overwhelming(g)
                  and (g.get("review_total") or g.get("review_count") or 0) >= 500]
    if strict_hot:
        hot = sorted(strict_hot, key=lambda g: (-(g.get("discount_pct") or 0),
                                                -(g.get("review_total") or g.get("review_count") or 0)))
        hot_title = "💸 70%+ 할인 · 압도적 긍정"
        hot_note = "할인율만 세지 않습니다. Steam 전체 리뷰가 ‘압도적으로 긍정적’인 게임만 골랐습니다."
    else:
        reviewed_hot = [g for g in korean if (g.get("discount_pct") or 0) >= 70
                        and (g.get("review_score") or 0) >= 8
                        and (g.get("review_total") or 0) >= 500]
        if reviewed_hot:
            hot = sorted(reviewed_hot, key=lambda g: (-(g.get("discount_pct") or 0),
                                                       -(g.get("review_total") or 0)))
            hot_title = "💸 70%+ 할인 · 매우 긍정 이상"
            hot_note = "할인율과 Steam 전체 리뷰 평가를 함께 통과한 게임입니다."
        else:
            hot = sorted([g for g in korean if (g.get("discount_pct") or 0) >= 70
                          and (g.get("review_count") or 0) >= 500],
                         key=lambda g: (-(g.get("discount_pct") or 0),
                                        -(g.get("review_count") or 0)))
            hot_title = "💸 70%+ 검증된 핫딜"
            hot_note = "리뷰 요약을 처음 수집하기 전까지 할인율과 리뷰 수로 검증합니다."

    demos = sorted([g for g in korean
                    if g.get("has_demo") or g.get("app_type") == "demo"],
                   key=lambda g: -(g.get("review_count") or 0))
    fresh = sorted([g for g in korean if g.get("tag") == "신작"],
                   key=lambda g: (g.get("release_date") or "", g.get("name") or ""),
                   reverse=True)
    soon = sorted([g for g in korean if g.get("coming_soon")],
                  key=lambda g: (g.get("release_date") or "9999",
                                 -(g.get("review_count") or 0), g.get("name") or ""))
    top = (hot or popular or demos or fresh or soon or safe or games)[0]

    days = max((g.get("days_tracked", 0) for g in games), default=0)
    n_demo = sum(1 for g in korean if g.get("has_demo") or g.get("app_type") == "demo")
    n_soon = sum(1 for g in korean if g.get("coming_soon"))
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
    # 홈에 미리 그려두는 카드 수를 제한한다. 전량을 그리면 index.html 이
    # 게임 9천개에서 6.9MB 가 되고(실측) 모바일에서 열리지 않는다.
    # 상한을 넘으면 추천 점수 높은 순으로 자르고, 그 사실을 화면에 밝힌다.
    shown_games = sorted(safe, key=lambda g: -(g.get("score") or 0))[:24]
    all_note = ""

    atl_note = ("" if days >= config.MIN_DAYS_FOR_LOW else
                f'<p class="sec-note">가격 추적은 {days}일째입니다. '
                f'최저가 표시는 {config.MIN_DAYS_FOR_LOW}일, '
                f'"역대 최저"는 {config.MIN_DAYS_FOR_ATL}일이 모여야 나옵니다.</p>')

    body = f"""
{lead(games, safe)}

{section("popular", popular_title, popular_note, popular,
         "인기 신호를 수집하는 중입니다.", rail=True, cap=8,
         more_href="#all", more_text="전체에서 찾기")}

{(section("drop", "📉 최근 가격이 내려간 게임",
         f"최근 {config.RECENT_DROP_DAYS}일간 이 사이트가 관측한 가격 변동 기준입니다.", recent_drops,
         "", rail=True, cap=8, more_href="recent-drops.html", more_text="최근 인하 전체") if recent_drops else "")}

{section("hot", hot_title, hot_note, hot,
         "현재 조건에 맞는 70%+ 핫딜이 없습니다.", rail=True, cap=8,
         more_href="#all", more_text="할인 게임 찾기")}

{section("soon", "🚀 출시 임박 기대작",
         "Steam 상점 노출과 출시일 기준입니다. 공개되지 않은 위시리스트 순위는 사용하지 않습니다.",
         soon, "출시예정 목록이 아직 비어 있습니다.", rail=True,
         more_href="korean-soon.html", more_text="출시예정 전체")}

{section("demo", "🎮 사기 전에 해보는 무료 데모",
         "한국어로 먼저 플레이해보고 고를 수 있는 게임입니다.", demos,
         "한국어 데모가 아직 수집되지 않았습니다.", rail=True,
         more_href="korean-demo.html", more_text="무료 데모 전체")}

{section("new", "✨ 방금 나온 한국어 신작", "최근 출시일 순으로 보여줍니다.", fresh,
         "한국어 신작 목록이 아직 비어 있습니다.", rail=True,
         more_href="korean-new.html", more_text="신작 전체")}
{atl_note}

<section id="all">
  <div class="sec-head"><h2>전체 게임에서 찾기</h2>
    <span class="cnt" id="cnt">{len(games)}개</span></div>
  {all_note}
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
    <button class="chip" data-f="wish" aria-pressed="false">♡ 찜 목록 <span class="wish-count">0</span></button>
    <button class="chip reset-btn" id="resetBtn" style="display:none;" aria-label="필터 초기화">🔄 초기화</button>
  </div>
  <div class="grid" id="list">{"".join(card(g) for g in shown_games)}
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
  var list=document.getElementById('list'), q=document.getElementById('q'), hq=document.querySelector('.hsearch input[name="q"]');
  var sort=document.getElementById('sort'), adult=document.getElementById('adult');
  var msg=document.getElementById('noneMsg'), cnt=document.getElementById('cnt');
  var moreWrap=document.getElementById('moreWrap'), moreBtn=document.getElementById('moreBtn');
  var chips=document.querySelectorAll('.presets .chip');
  var f='all';

  var indexData = null;
  var fetchPromise = null;

  function createCard(g) {{
    var a = document.createElement('a');
    a.className = 'card';
    a.href = 'game/' + g.appid + '.html';

    a.dataset.n = g.n;
    a.dataset.demo = g.demo;
    a.dataset.soon = g.soon;
    a.dataset.new = g.new;
    a.dataset.kr = g.kr;
    a.dataset.adult = g.adult;
    a.dataset.off = g.off;
    a.dataset.price = g.price;
    a.dataset.score = g.score;
    a.dataset.atl = g.atl;
    a.dataset.wish = g.appid;

    var shot = document.createElement('div');
    shot.className = 'shot';

    if (g.img && (g.img.indexOf('http://') === 0 || g.img.indexOf('https://') === 0)) {{
      var img = document.createElement('img');
      img.src = g.img;
      img.alt = g.name + ' 표지';
      img.loading = 'lazy';
      img.decoding = 'async';
      shot.appendChild(img);
    }} else {{
      var ph = document.createElement('div');
      ph.className = 'ph';
      ph.setAttribute('aria-hidden', 'true');
      ph.textContent = (g.name || '?').trim().substring(0, 2).toUpperCase();
      shot.appendChild(ph);
    }}

    if (g.off) {{
      var rib = document.createElement('span');
      rib.className = 'ribbon ' + (g.off >= 75 ? 'r-hi' : 'r-lo');
      rib.textContent = '-' + g.off + '%';
      shot.appendChild(rib);
    }}

    if (g.players) {{
      var playing = document.createElement('span');
      playing.className = 'player-badge';
      var compact = g.players >= 10000 ? (g.players / 10000).toFixed(1).replace('.0', '') + '만' :
                    g.players >= 1000 ? (g.players / 1000).toFixed(1).replace('.0', '') + '천' : g.players;
      playing.textContent = '● ' + compact + '명 플레이 중';
      shot.appendChild(playing);
    }}
    a.appendChild(shot);

    var wishBtn = document.createElement('button');
    wishBtn.className = 'wish';
    wishBtn.type = 'button';
    wishBtn.dataset.wishId = g.appid;
    wishBtn.setAttribute('aria-pressed', 'false');
    wishBtn.setAttribute('aria-label', '찜 목록에 추가');
    wishBtn.textContent = '♡';
    a.appendChild(wishBtn);

    var cardB = document.createElement('div');
    cardB.className = 'card-b';

    var nameDiv = document.createElement('div');
    nameDiv.className = 'name';
    nameDiv.textContent = g.name;
    cardB.appendChild(nameDiv);

    var chips = [];
    if (g.atl && g.atl_txt) chips.push({{cls: 'atl', txt: g.atl_txt}});
    if (g.demo) chips.push({{cls: 'demo', txt: '데모'}});
    if (g.soon) chips.push({{cls: 'soon', txt: '출시예정'}});
    else if (g.new) chips.push({{cls: 'new', txt: '신작'}});
    if (g.kr_ov) chips.push({{cls: 'kr-ov', txt: '압도적 한국어'}});

    if (chips.length > 0) {{
      var cDiv = document.createElement('div');
      cDiv.className = 'chips';
      for (var i=0; i<chips.length; i++) {{
        var sp = document.createElement('span');
        sp.className = 't ' + chips[i].cls;
        sp.textContent = chips[i].txt;
        cDiv.appendChild(sp);
      }}
      cardB.appendChild(cDiv);
    }}

    var rc = '';
    if (g.r_lbl) {{
      rc = g.r_lbl + ' · 리뷰 ' + g.r_tot.toLocaleString('ko-KR');
      if (g.r_pct !== null && g.r_pct !== undefined) rc += ' · 긍정 ' + g.r_pct + '%';
    }} else {{
      if (g.r_tot >= 10) rc = '리뷰 ' + g.r_tot.toLocaleString('ko-KR');
      else rc = g.dev || '';
    }}
    if (g.players && g.p_delta) {{
      var arrow = g.p_delta > 0 ? '▲ ' : '▼ ';
      rc = (rc ? rc + ' · ' : '') + arrow + Math.abs(g.p_delta).toLocaleString('ko-KR');
    }}

    var tagline = document.createElement('div');
    tagline.className = 'tagline';
    tagline.textContent = rc;
    cardB.appendChild(tagline);

    var hasLeft = g.recent_drop || g.free || g.off;
    var fDiv = document.createElement('div');
    fDiv.className = hasLeft ? 'card-f' : 'card-f bare';

    if (g.recent_drop) {{
      var drp = document.createElement('span');
      drp.className = 'offtag';
      drp.style.background = 'var(--accent)';
      drp.textContent = '최근 ' + g.recent_drop.toLocaleString('ko-KR') + '원 인하';
      fDiv.appendChild(drp);
    }} else if (g.free) {{
      // nothing for left side when free
    }} else if (g.off) {{
      var offCls = g.off >= 75 ? 'off-hi' : (g.off >= 50 ? 'off-mid' : 'off-lo');
      var offTag = document.createElement('span');
      offTag.className = 'offtag ' + offCls;
      offTag.textContent = '-' + g.off + '%';
      fDiv.appendChild(offTag);
    }}

    var pDiv = document.createElement('div');
    pDiv.className = 'price';
    var nowSp = document.createElement('span');
    nowSp.className = 'now';

    if (g.free) {{
      nowSp.textContent = '무료';
      pDiv.appendChild(nowSp);
    }} else if (!g.price) {{
      nowSp.textContent = g.soon ? '출시 전' : '가격 미정';
      pDiv.appendChild(nowSp);
    }} else {{
      nowSp.textContent = g.price.toLocaleString('ko-KR') + '원';
      pDiv.appendChild(nowSp);
      if (g.p_init > g.price) {{
        var wasSp = document.createElement('span');
        wasSp.className = 'strike';
        wasSp.textContent = g.p_init.toLocaleString('ko-KR') + '원';
        pDiv.appendChild(wasSp);
      }}
    }}
    fDiv.appendChild(pDiv);

    cardB.appendChild(fDiv);
    a.appendChild(cardB);
    return a;
  }}

  function loadIndex() {{
    if (indexData) return Promise.resolve(indexData);
    if (fetchPromise) return fetchPromise;

    msg.textContent = '게임 목록 불러오는 중...';
    msg.hidden = false;

    fetchPromise = fetch('assets/game-search-index.json')
      .then(function(r) {{
        if (!r.ok) throw new Error('Network response was not ok');
        return r.json();
      }})
      .then(function(data) {{
        indexData = data;
        return data;
      }})
      .catch(function(e) {{
        msg.textContent = '목록을 불러오지 못했습니다. 새로고침 후 다시 시도해주세요.';
        msg.hidden = false;
        throw e;
      }});
    return fetchPromise;
  }}

  var observer = new IntersectionObserver(function(entries) {{
    if (entries[0].isIntersecting) {{
      loadIndex().then(render).catch(function(){{}});
      observer.disconnect();
    }}
  }});
  var allSec = document.getElementById('all');
  if (allSec) observer.observe(allSec);

  function keep(g){{
    if (g.adult===1 && !adult.checked) return false;
    var t=(q.value||'').trim().toLowerCase();
    if (t && g.n.indexOf(t)===-1) return false;
    if (f==='demo'  && g.demo!==1) return false;
    if (f==='soon'  && g.soon!==1) return false;
    if (f==='new'   && g.new!==1)  return false;
    if (f==='kr'    && g.kr!==1)   return false;
    if (f==='cheap' && !(g.price>0 && g.price<=10000)) return false;
    if (f==='off50' && g.off<50)    return false;
    if (f==='wish' && window.steamWishlist && !window.steamWishlist.read().has(String(g.appid))) return false;
    return true;
  }}
  function cmp(a,b){{
    var s=sort.value;
    if (s==='off')   return b.off - a.off;
    if (s==='name')  return a.n.localeCompare(b.n,'ko');
    if (s==='cheap'){{
      var pa=a.price||Infinity, pb=b.price||Infinity;
      return pa-pb;
    }}
    return b.score - a.score;
  }}
  function render(){{
    if (!indexData) return;
    var vis=indexData.filter(keep);
    vis.sort(cmp);

    list.innerHTML = '';
    for (var i = 0; i < Math.min(shown, vis.length); i++) {{
      list.appendChild(createCard(vis[i]));
    }}
    list.appendChild(msg);

    var hasFilter = f !== 'all' || (q.value||'').trim() !== '' || sort.value !== 'score' || adult.checked;
    var resetBtn = document.getElementById('resetBtn');
    if(resetBtn) resetBtn.style.display = hasFilter ? 'inline-block' : 'none';

    if(vis.length === 0){{
      if(f === 'wish' && (q.value||'').trim() === '') msg.textContent = '찜한 게임이 없습니다. 마음에 드는 게임을 찜해보세요.';
      else msg.textContent = '조건에 맞는 게임이 없습니다. 검색어나 필터를 넓혀보세요.';
      msg.hidden = false;
    }} else {{
      msg.hidden = true;
    }}
    cnt.textContent = vis.length+'개';
    moreWrap.hidden = vis.length<=shown;
    moreBtn.textContent = '더 보기 ('+Math.min(shown,vis.length)+' / '+vis.length+')';

    if (window.steamWishlist && window.steamWishlist.paint) window.steamWishlist.paint();
    if (window.steamCompare && window.steamCompare.paint) window.steamCompare.paint();
  }}

  function apply(){{
    if (!indexData) {{
      loadIndex().then(render).catch(function(){{}});
    }} else {{
      shown=PAGE;
      render();
    }}
  }}
  moreBtn.addEventListener('click',function(){{ shown+=PAGE; render(); }});

  function handleInput(v) {{
    if (q) q.value = v;
    if (hq) hq.value = v;
    var newUrl = location.pathname + (v ? '?q=' + encodeURIComponent(v) : '');
    history.replaceState(null, '', newUrl);
    apply();
  }}

  if (q) q.addEventListener('input', function() {{ handleInput(q.value); }});
  if (hq) hq.addEventListener('input', function() {{ handleInput(hq.value); }});

  sort.addEventListener('change',apply);
  adult.addEventListener('change',apply);
  chips.forEach(function(c){{
    c.addEventListener('click',function(){{
      chips.forEach(function(x){{ x.setAttribute('aria-pressed',String(x===c)); }});
      f=c.dataset.f; apply();
    }});
  }});
  document.querySelectorAll('[data-jump-filter]').forEach(function(b){{
    b.addEventListener('click',function(){{
      var target=document.querySelector('.presets .chip[data-f="'+b.dataset.jumpFilter+'"]');
      if(target) target.click();
      document.getElementById('all').scrollIntoView();
    }});
  }});
  var resetBtnNode = document.getElementById('resetBtn');
  if(resetBtnNode) {{
    resetBtnNode.addEventListener('click', function(){{
      if (q) q.value = '';
      if (hq) hq.value = '';
      sort.value = 'score';
      adult.checked = false;
      var allChip = document.querySelector('.presets .chip[data-f="all"]');
      if (allChip) allChip.click();
      history.replaceState(null, '', location.pathname);
      apply();
    }});
  }}

  window.syncURL=function(){{
    var params = new URLSearchParams(window.location.search);
    var searchStr = params.get('q');
    var h = location.hash||'';
    var v = '';

    if (searchStr !== null) {{
      v = searchStr;
    }} else if (h.indexOf('#q=') === 0) {{
      v = h.slice(3);
      try {{ v=decodeURIComponent(v); }} catch(e) {{}}
      history.replaceState(null, '', location.pathname + '?q=' + encodeURIComponent(v));
    }}

    if (q) q.value = v;
    if (hq) hq.value = v;

    if (searchStr !== null || h.indexOf('#q=') === 0) {{
      apply();
      document.getElementById('all').scrollIntoView();
    }}
  }};
  window.addEventListener('hashchange', window.syncURL);
  window.addEventListener('popstate', window.syncURL);
  window.syncURL();
}})();
</script>
"""
    schema = {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": "GameDil",
        "url": abs_url(""),
        "potentialAction": {
            "@type": "SearchAction",
            "target": abs_url("index.html") + "?q={search_term_string}",
            "query-input": "required name=search_term_string"
        }
    }
    extra_head = f'<script type="application/ld+json">\n{json.dumps(schema, ensure_ascii=False, indent=2).replace('<', '\\u003c').replace('>', '\\u003e')}\n</script>'
    return page("GameDil — 지금 많이 하는 한국어 게임과 검증된 핫딜",
                body, updated, canonical="index.html",
                og_image=(top.get("header_image") or ""),
                freshness=freshness,
                desc=(f"한국어 스팀 게임 {n_kr:,}개의 현재 인기와 원화 가격을 추적합니다. "
                      f"한국어 데모 {n_demo}개, 출시예정 {n_soon}개를 매일 두 번 자동 갱신."),
                extra_head=extra_head)


# ---------------------------------------------------------------- 상세

def media_main(g: dict) -> str:
    """상세 페이지 대표 미디어. 트레일러가 있으면 영상, 없으면 표지.

    표지(460x215 배너)는 대부분 로고와 제목뿐이라 '이게 무슨 게임인가'에 답하지 못한다.
    영상·스크린샷이 그 답을 한다. 다만 스팀 CDN 이 외부 재생을 막을 수도 있으므로
    poster 를 항상 깔아두고, 영상이 없거나 못 틀면 표지가 그대로 보이게 한다."""
    poster = g.get("movie_poster") or g.get("header_image") or ""
    mp4, webm = g.get("movie_mp4") or "", g.get("movie_webm") or ""
    if not (mp4 or webm):
        return f'<div class="dmedia">{shot(g, ribbon=False)}</div>'
    src = ""
    if webm:
        src += f'<source src="{esc(webm)}" type="video/webm">'
    if mp4:
        src += f'<source src="{esc(mp4)}" type="video/mp4">'
    alt = (f'<img src="{esc(g["header_image"])}" alt="{esc(g["name"])} 표지">'
           if g.get("header_image") else "")
    return f"""<div class="dmedia">
  <div class="dmedia-title">Steam 트레일러</div>
  <video class="dvid" playsinline muted loop controls preload="none"
         poster="{esc(poster)}" aria-label="{esc(g['name'])} 트레일러">
    {src}{alt}
  </video>
</div>"""


def shots_strip(g: dict) -> str:
    """스크린샷 스트립. 실제 게임 화면이라 한 줄 설명보다 빠르게 이해된다."""
    urls = [u for u in (g.get("screenshots") or "").split("\n") if u.strip()]
    if not urls:
        return ""
    imgs = "".join(
        f'<img src="{esc(u)}" alt="{esc(g["name"])} 스크린샷 {i}" '
        f'loading="lazy" decoding="async">'
        for i, u in enumerate(urls, 1))
    return f'<div class="panel"><h3>게임 화면</h3><div class="shots">{imgs}</div></div>'


def build_related(g: dict, all_games: list[dict]) -> str:
    """현재 게임과 속성이 겹치는 추천 게임을 찾는다."""
    g_kr = bool(g.get("korean"))
    g_genres = set(x.strip() for x in (g.get("genres") or "").split(",") if x.strip())
    g_demo = bool(g.get("has_demo") or g.get("app_type") == "demo")
    g_disc = bool(g.get("discount_pct"))

    scored = []
    for o in all_games:
        if o["appid"] == g["appid"]:
            continue
        # 상세페이지의 관련 추천도 기본 공개 목록과 같은 성인 제외 정책을 따른다.
        if o.get("adult"):
            continue

        score = 0
        if bool(o.get("korean")) == g_kr: score += 1

        o_genres = set(x.strip() for x in (o.get("genres") or "").split(",") if x.strip())
        overlap = len(g_genres & o_genres)
        score += overlap * 2

        if bool(o.get("has_demo") or o.get("app_type") == "demo") == g_demo: score += 1
        if bool(o.get("discount_pct")) == g_disc: score += 1

        if score > 0:
            scored.append((score, o.get("release_date") or "", o["appid"], o))

    if not scored:
        return ""

    scored.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)
    picked = [x[3] for x in scored[:4]]

    cards = "".join(card(o, depth=1) for o in picked)
    return f"""
<div class="panel">
  <h3>같이 볼 만한 게임</h3>
  <div class="grid" style="margin-top:12px">
    {cards}
  </div>
</div>
"""


def build_detail(g: dict, all_games: list[dict], updated: str, freshness: dict | None = None, recent_drop: dict | None = None) -> str:
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
    if g.get("players_current"):
        facts.append(("현재 플레이 중", f'{g["players_current"]:,}명'))
    if review_label(g):
        total = g.get("review_total") or g.get("review_count") or 0
        positive = g.get("review_positive_pct")
        value = review_label(g)
        if positive is not None:
            value += f" · 긍정 {positive}%"
        if total:
            value += f" ({total:,}개)"
        facts.append(("Steam 평가", esc(value)))
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

    # 알림 서버 없이도 바로 쓸 수 있는 1단계: 목표가는 이 브라우저에만 저장한다.
    # 저장할 때 찜에도 넣어두므로 다음 방문에서 찜 필터로 바로 찾을 수 있다.
    judge_panel = ""
    if g.get("price_final") and not g.get("is_free"):
        d = g.get("days_tracked", 0)
        curr = g.get("price_final", 0)
        low = g.get("lowest_seen", 0)
        if d < config.MIN_DAYS_FOR_LOW:
            j_txt = f"추적 {d}일째 · 아직 가격 판단을 보류합니다."
        elif curr <= low and low > 0:
            if g.get("atl_trustworthy"):
                j_txt = f"<b>역대 최저가</b>입니다. (관측 {d}일 기준)"
            else:
                j_txt = f"<b>추적 {d}일 기준 최저가</b>입니다."
        elif low > 0:
            diff = curr - low
            j_txt = f"관측 최저가({low:,}원)보다 <b>{diff:,}원</b> 더 비쌉니다. (추적 {d}일 기준)"
        else:
            j_txt = f"추적 {d}일째 · 아직 가격 판단을 보류합니다."
        judge_panel = f"""<div class="panel">
  <h3>지금 사도 될까요?</h3>
  <p style="font-size:13.5px; margin:0; color:var(--ink-2); line-height:1.5;">{j_txt}</p>
</div>"""

    target_panel = ""
    if g.get("price_final") and not g.get("is_free"):
        target_panel = f"""<div class="panel target-panel" data-target-appid="{g['appid']}"
  data-current-price="{g['price_final']}">
  <h3>내 목표 가격</h3>
  <p class="sub">실제 푸시 알림이 아니라 다음 방문 시 사이트에 표시됩니다. (현재 기기 브라우저에만 저장)</p>
  <div class="target-row">
    <input class="target-input" type="text" inputmode="numeric"
           placeholder="예: 15,000" aria-label="{esc(g['name'])} 목표 가격">
    <span>원</span>
    <button class="btn btn-p target-save" type="button">저장</button>
    <button class="btn target-del" type="button" style="display:none;" aria-label="목표가 삭제">삭제</button>
  </div>
  <p class="target-result" role="status"></p>
</div>"""

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

    recent_drop_html = ""
    if recent_drop:
        amt = recent_drop["recent_drop_amount"]
        dt = recent_drop["recent_drop_date"]
        recent_drop_html = f'<p style="color:var(--accent); font-weight:bold; margin-bottom:0.5rem; font-size:14px;">최근 {amt:,}원 인하 · {esc(dt)} 관측</p>'

    if len(hist) >= 2:
        chart = f"""<div class="panel">
  {recent_drop_html}
  <h3>원화 가격 추이</h3>
  <p class="sub">{sub}</p>
  {chart_inner}
</div>"""
    else:
        # 아직 보여줄 추이가 없다. 접어두고, 열면 왜 비었는지 설명한다.
        chart = f"""<div class="panel">
  {recent_drop_html}
  <details><summary>원화 가격 추이 — {esc(sub)}</summary>
  {chart_inner}
  </details>
</div>"""

    demo_id = g.get("demo_appid") or g["appid"]
    demo_btn = (f'<a class="btn btn-s" href="https://store.steampowered.com/app/{demo_id}/?cc=kr"'
                f' target="_blank" rel="noopener">데모 받기</a>'
                if (g.get("has_demo") or g.get("app_type") == "demo") else "")

    share_title_js = json.dumps(g['name'], ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e')
    share_text = g['name']
    if g.get('is_free'):
        share_text += " — 무료"
    elif g.get('price_final'):
        share_text += f" — {g['price_final']:,}원"
        if g.get('discount_pct'):
            share_text += f" ({g['discount_pct']}% 할인)"
    if g.get('price_final') and not g.get('is_free'):
        curr = g.get("price_final", 0)
        low = g.get("lowest_seen", 0)
        if curr <= low and low > 0 and g.get("atl_trustworthy"):
            share_text += " [스팀 역대 최저가]"
    share_text_js = json.dumps(share_text, ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e')

    compare_btn = ""
    if not g.get("adult"):
        snap = {
            "appid": g["appid"],
            "name": g["name"],
            "header_image": g.get("header_image") or "",
            "price_final": g.get("price_final") or 0,
            "discount_pct": g.get("discount_pct") or 0,
            "lowest_seen": g.get("lowest_seen") or 0,
            "recent_drop_amount": recent_drop["recent_drop_amount"] if recent_drop else 0,
            "korean": bool(g.get("korean")),
            "has_demo": bool(g.get("has_demo") or g.get("demo_appid")),
            "review_label": review_label(g),
            "review_positive_pct": g.get("review_positive_pct"),
            "players_current": g.get("players_current") or 0,
            "release_text": g.get("release_text") or "",
            "adult": bool(g.get("adult"))
        }
        snap_json = json.dumps(snap, ensure_ascii=False)
        compare_btn = f'<button class="btn btn-s compare-btn" data-compare-id="{g["appid"]}" data-snapshot="{esc(snap_json)}" type="button">비교함에 담기</button>'


    share_js = f"""<script>
(function(){{
  var btn = document.getElementById('shareBtn');
  if(!btn) return;
  function copyToClipboard() {{
    var og = btn.textContent;
    var fullText = {share_text_js} + "\\n" + location.href;
    if (!navigator.clipboard || !navigator.clipboard.writeText) {{
      btn.textContent = "복사 실패";
      setTimeout(function(){{ btn.textContent = og; }}, 2000);
      return;
    }}
    navigator.clipboard.writeText(fullText).then(function(){{
      btn.textContent = "복사 완료!";
      setTimeout(function(){{ btn.textContent = og; }}, 2000);
    }}).catch(function(){{
      btn.textContent = "복사 실패";
      setTimeout(function(){{ btn.textContent = og; }}, 2000);
    }});
  }}
  btn.addEventListener('click', function(){{
    if(navigator.share) {{
      navigator.share({{title: {share_title_js}, text: {share_text_js}, url: location.href}})
        .catch(function(err){{
          if (err.name !== 'AbortError') copyToClipboard();
        }});
    }} else {{
      copyToClipboard();
    }}
  }});
}})();
</script>"""

    body = f"""
<a class="back" href="./../index.html">← 목록으로</a>
<div class="dhero">
  {media_main(g)}
  <div>
    <h1>{esc(g['name'])}</h1>
    {chips_for(g)}
    <p class="desc">{esc(g.get('description'))}</p>
    <div class="price-now">{price_block}</div>
    <div class="buyrow">
      <a class="btn btn-p" href="https://store.steampowered.com/app/{g['appid']}/?cc=kr"
         target="_blank" rel="noopener">스팀 상점에서 보기</a>
      {demo_btn}
      <button class="btn btn-s share-btn" id="shareBtn" type="button" aria-label="공유">공유</button>
      {compare_btn}
    </div>
  </div>
</div>
{share_js}

{shots_strip(g)}

{why_panel}
{judge_panel}

<div class="panel">
  <h3>정보</h3>
  <div class="tablewrap"><table>{fact_rows}</table></div>
</div>

{target_panel}

{chart}

{build_related(g, all_games)}
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

    schema = {
        "@context": "https://schema.org",
        "@type": "VideoGame",
        "name": g["name"],
        "url": f"https://store.steampowered.com/app/{g['appid']}/"
    }
    if g.get("header_image"):
        schema["image"] = g["header_image"]

    if g.get("is_free"):
        schema["offers"] = {
            "@type": "Offer",
            "priceCurrency": "KRW",
            "price": 0
        }
    elif g.get("price_final") is not None:
        schema["offers"] = {
            "@type": "Offer",
            "priceCurrency": "KRW",
            "price": g["price_final"]
        }
        if g.get("discount_pct"):
            schema["offers"]["discount"] = g["discount_pct"]

    r_total = g.get("review_total") or g.get("review_count") or 0
    r_pos = g.get("review_positive_pct")
    if r_total > 0 and r_pos is not None:
        schema["aggregateRating"] = {
            "@type": "AggregateRating",
            "ratingValue": r_pos,
            "bestRating": 100,
            "ratingCount": r_total
        }

    extra_head = f'<script type="application/ld+json">\n{json.dumps(schema, ensure_ascii=False, indent=2).replace('<', '\\u003c').replace('>', '\\u003e')}\n</script>'

    return page(pt, body, updated, canonical=f"game/{g['appid']}.html",
                og_image=(g.get("header_image") or ""), desc=d, depth=1,
                freshness=freshness, extra_head=extra_head)


# ---------------------------------------------------------------- 랜딩(검색 유입용)

# 우리 데이터만 정직하게 답할 수 있는 질문들.
# '스팀 최저가' 같은 거대 키워드는 선행 6개를 이길 수 없어서 쓰지 않는다.
LANDINGS = [
    # 제목·설명은 '자동완성이 실제로 제안하는 표현'만 쓴다 (2026-08-29 실측).
    #   수요 있음: 스팀 한국어 게임 / 스팀 한국어 지원 / 스팀 신작(추천) /
    #             스팀 출시예정(게임) / 스팀 데모 추천 / 스팀 무료 데모 / 스팀 1만원 이하 게임
    #   수요 없음: "스팀 한국어 데모"  ← 두 수식어를 겹친 조합만 죽었다.
    #             사람들은 속성을 하나씩 검색한다.
    # 그래서 제목은 단일 축 표현을 앞세우고, '한국어'는 부제·본문에서 말한다.
    #
    # slug 는 절대 바꾸지 않는다 — 바꾸면 쌓인 링크와 검색 순위가 날아간다.
    # (그래서 korean-demo 라는 이름은 유지하되 제목만 고친다)
    dict(slug="korean-games",
         title="스팀 한국어 지원 게임 — 한국어로 할 수 있는 것 모음",
         h1="한국어 지원 게임",
         desc="한국어를 지원하는 스팀 게임을 매일 두 번 자동으로 모읍니다. "
              "원화 가격과 데모 여부를 함께 봅니다.",
         note="이 사이트가 추적 중인 게임 중 한국어를 지원하는 것 전부입니다. "
              "리뷰가 많은 순.",
         pick=lambda g: g.get("korean"),
         sort=lambda g: -(g.get("review_count") or 0)),
    dict(slug="korean-demo",
         title="스팀 무료 데모 추천 — 지금 받아서 해볼 수 있는 게임",
         h1="무료 데모 추천",
         desc="사기 전에 무료로 해볼 수 있는 스팀 데모 목록. 한국어를 지원하는 것만 골랐습니다.",
         note="전부 한국어를 지원합니다. 리뷰가 많은 순.",
         pick=lambda g: g.get("korean") and (g.get("has_demo") or g.get("app_type") == "demo"),
         sort=lambda g: -(g.get("review_count") or 0)),
    dict(slug="korean-new",
         title="스팀 신작 추천 — 최근 나온 게임",
         h1="새로 나온 게임",
         desc="최근 스팀에 출시된 게임을 매일 갱신합니다. 한국어를 지원하는 것만 골랐습니다.",
         note="최근 출시 순입니다. 전부 한국어를 지원합니다.",
         pick=lambda g: g.get("korean") and g.get("tag") == "신작" and not g.get("coming_soon"),
         sort=lambda g: (g.get("release_date") or "", g.get("name") or ""), rev=True),
    dict(slug="korean-soon",
         title="스팀 출시예정 게임 — 곧 나오는 것",
         h1="곧 나오는 게임",
         desc="아직 나오지 않은 스팀 게임 목록. 한국어를 지원할 예정인 것만 골랐습니다.",
         note="출시일이 가까운 순입니다. 출시 전에 찜해두면 좋습니다.",
         pick=lambda g: g.get("korean") and g.get("coming_soon"),
         sort=lambda g: (g.get("release_date") or "9999", g.get("name") or "")),
    dict(slug="under-10000",
         title="스팀 1만원 이하 게임",
         h1="1만원 이하 게임",
         desc="현재 스팀 원화 가격이 1만원 이하인 게임 목록. 한국어를 지원하는 것만 골랐습니다.",
         note="현재 판매가 기준, 낮은 가격 순입니다. 전부 한국어를 지원합니다.",
         pick=lambda g: (g.get("korean") and 0 < (g.get("price_final") or 0) <= 10000),
         sort=lambda g: g.get("price_final") or 0),
    dict(slug="recent-drops",
         title="스팀 최근 가격 인하 게임 — 최근 7일 가격이 내려간 것",
         h1="최근 가격 인하 게임",
         desc="최근 7일간 이 사이트가 관측한 가격 변동 기준입니다. 최대 120개까지만 보여줍니다.",
         note="가격 인하폭 및 할인율이 큰 순서입니다. (데이터가 많으면 최대 120개 표시)",
         pick=lambda g: True,
         sort=lambda g: 0),
]


def build_landing(spec: dict, games: list[dict], updated: str,
                  freshness: dict | None = None) -> str:
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
    schema = {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": "GameDil",
        "url": abs_url(""),
        "potentialAction": {
            "@type": "SearchAction",
            "target": abs_url("index.html") + "?q={search_term_string}",
            "query-input": "required name=search_term_string"
        }
    }
    extra_head = f'<script type="application/ld+json">\n{json.dumps(schema, ensure_ascii=False, indent=2).replace('<', '\\u003c').replace('>', '\\u003e')}\n</script>'
    return page(spec["title"], body, updated,
                canonical=f"{spec['slug']}.html", desc=spec["desc"],
                og_image=(items[0].get("header_image") if items else ""),
                freshness=freshness,
                extra_head=extra_head)


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



def build_compare(games: list[dict], updated: str, freshness: dict, recent_drops_map: dict) -> str:
    html = '''
<div class="dhero" style="text-align:center; padding: 2rem 1rem;">
  <h1>게임 비교</h1>
  <p class="sub">비교함 데이터는 이 브라우저에만 임시로 저장됩니다.</p>
</div>

<div id="compareApp"></div>

<script>
(function(){
  function el(tag, text, cls) {
    var e = document.createElement(tag);
    if(text) e.textContent = text;
    if(cls) e.className = cls;
    return e;
  }

  function render() {
    var app = document.getElementById('compareApp');
    app.innerHTML = '';
    var arr = window.steamCompare ? window.steamCompare.read() : [];

    if (arr.length === 0) {
      var empty = el('div', '', 'empty-state');
      empty.textContent = '비교함이 비었습니다.';
      var br = document.createElement('br');
      var br2 = document.createElement('br');
      var a = el('a', '홈으로 돌아가기', 'btn btn-p');
      a.href = 'index.html';
      empty.appendChild(br);
      empty.appendChild(br2);
      empty.appendChild(a);
      app.appendChild(empty);
      return;
    }

    var container = el('div', '', 'compare-container');
    var hint = el('div', '← 표를 좌우로 스크롤하여 비교하세요 →', 'scroll-hint');
    container.appendChild(hint);
    var table = el('table', '', 'compare-table');
    var tbody = document.createElement('tbody');

    var rows = [
      { key: '게임', render: function(g, td) {
          var a = el('a');
          a.href = 'game/' + g.appid + '.html';
          if (g.header_image && (g.header_image.indexOf('http://') === 0 || g.header_image.indexOf('https://') === 0)) {
            var img = el('img');
            img.src = g.header_image;
            img.alt = g.name + ' 표지';
            a.appendChild(img);
          }
          var b = el('b', g.name);
          a.appendChild(b);
          td.appendChild(a);
      } },
      { key: '현재 가격', render: function(g, td) {
          if (!g.price_final) { td.textContent = '정보 없음'; return; }
          var b = el('b', g.price_final.toLocaleString('ko-KR') + '원');
          td.appendChild(b);
          if (g.discount_pct) {
            td.appendChild(document.createElement('br'));
            var sp = el('span', '-' + g.discount_pct + '%');
            sp.style.color = 'var(--accent)';
            td.appendChild(sp);
          }
      } },
      { key: '관측 최저가', render: function(g, td) {
          td.textContent = g.lowest_seen ? g.lowest_seen.toLocaleString('ko-KR') + '원' : '정보 없음';
      } },
      { key: '최근 인하', render: function(g, td) {
          if (g.recent_drop_amount) {
            var sp = el('span', '최근 ' + g.recent_drop_amount.toLocaleString('ko-KR') + '원 인하');
            sp.style.color = 'var(--accent)';
            td.appendChild(sp);
          } else {
            td.textContent = '해당 없음';
          }
      } },
      { key: '한국어', render: function(g, td) { td.textContent = g.korean ? '지원' : '미지원'; } },
      { key: '데모', render: function(g, td) { td.textContent = g.has_demo ? '있음' : '없음'; } },
      { key: 'Steam 리뷰', render: function(g, td) {
          if (!g.review_label) { td.textContent = '정보 없음'; return; }
          var text = g.review_label;
          if (g.review_positive_pct) text += ' (' + g.review_positive_pct + '%)';
          td.textContent = text;
      } },
      { key: '현재 플레이어', render: function(g, td) { td.textContent = g.players_current ? g.players_current.toLocaleString('ko-KR') + '명' : '정보 없음'; } },
      { key: '출시', render: function(g, td) { td.textContent = g.release_text || '정보 없음'; } },
      { key: '관리', render: function(g, td) {
          var btn = el('button', '제거', 'btn btn-s del-btn');
          btn.dataset.remove = g.appid;
          btn.setAttribute('aria-label', g.name + ' 비교함에서 제거');
          td.appendChild(btn);
      } }
    ];

    rows.forEach(function(r) {
      var tr = document.createElement('tr');
      var th = el('th', r.key);
      th.setAttribute('scope', 'row');
      tr.appendChild(th);

      arr.forEach(function(g) {
        var td = document.createElement('td');
        if (g) r.render(g, td);
        tr.appendChild(td);
      });

      for (var i = arr.length; i < 3; i++) {
        var td = document.createElement('td');
        var sp = el('span', '비어 있음');
        sp.style.color = 'var(--ink-3)';
        td.appendChild(sp);
        tr.appendChild(td);
      }
      tbody.appendChild(tr);
    });

    table.appendChild(tbody);
    container.appendChild(table);
    app.appendChild(container);

    var divClear = el('div');
    divClear.style.textAlign = 'center';
    divClear.style.padding = '2rem';
    var clearBtn = el('button', '비교함 비우기', 'btn clear-btn');
    divClear.appendChild(clearBtn);
    app.appendChild(divClear);

    app.querySelectorAll('.del-btn').forEach(function(btn) {
      btn.addEventListener('click', function() {
        var id = Number(this.dataset.remove);
        var cur = window.steamCompare.read();
        var idx = -1;
        for (var i=0; i<cur.length; i++) if(cur[i].appid === id) idx = i;
        if (idx > -1) cur.splice(idx, 1);
        window.steamCompare.write(cur);
        if (window.steamCompare.paint) window.steamCompare.paint();
        render();
      });
    });

    if (clearBtn) {
      clearBtn.addEventListener('click', function() {
        window.steamCompare.write([]);
        if (window.steamCompare.paint) window.steamCompare.paint();
        render();
      });
    }
  }

  document.addEventListener('DOMContentLoaded', render);
})();
</script>
'''
    return page("게임 비교 - GameDil", html, updated, depth=0, freshness=freshness, desc="최대 3개의 게임을 한눈에 비교합니다.", extra_head='<meta name="robots" content="noindex,follow">')


def build_my_games(updated: str, freshness: dict) -> str:
    html = '''
<div class="dhero" style="text-align:center; padding: 2rem 1rem 1rem;">
  <h1>내 찜 목록</h1>
  <p class="sub">브라우저에 저장된 찜 게임과 목표 가격을 확인합니다.</p>
</div>

<div class="sec-wrap" style="max-width: 1040px; margin: 0 auto; padding: 0 1rem 3rem;">
  <div class="tools" id="myTools" style="display:none; justify-content: space-between; margin-bottom: 14px;">
    <div style="display:flex; align-items:center; gap:8px;">
      <span class="cnt" id="myCnt" style="font-weight:700; color:var(--ink-2);">0개</span>
      <select id="mySort" aria-label="정렬 기준">
        <option value="default">목표가 도달순</option>
        <option value="off">할인 큰 순</option>
        <option value="cheap">낮은 가격순</option>
        <option value="name">이름순</option>
      </select>
    </div>
    <label class="sw"><input type="checkbox" id="myAdult"> 성인 게임 포함</label>
  </div>

  <div id="myApp"></div>
</div>

<script>
(function(){
  var WISH_KEY = 'steamdeal-wishlist-v1';
  var TARGET_KEY = 'steamdeal-target-price-v1';

  function readWish() {
    try {
      return new Set(JSON.parse(localStorage.getItem(WISH_KEY) || '[]').map(String));
    } catch(e) {
      return new Set();
    }
  }

  function writeWish(set) {
    try {
      localStorage.setItem(WISH_KEY, JSON.stringify(Array.from(set)));
    } catch(e) {}
  }

  function readTargets() {
    try {
      var raw = JSON.parse(localStorage.getItem(TARGET_KEY) || '{}');
      return raw && typeof raw === 'object' ? raw : {};
    } catch(e) {
      return {};
    }
  }

  function writeTargets(targets) {
    try {
      localStorage.setItem(TARGET_KEY, JSON.stringify(targets));
    } catch(e) {}
  }

  function el(tag, text, cls) {
    var e = document.createElement(tag);
    if (text) e.textContent = text;
    if (cls) e.className = cls;
    return e;
  }

  var allGames = null;
  var isLoading = false;
  var isError = false;

  var app = document.getElementById('myApp');
  var tools = document.getElementById('myTools');
  var sortSelect = document.getElementById('mySort');
  var adultCheck = document.getElementById('myAdult');
  var cntSpan = document.getElementById('myCnt');

  function renderStatus() {
    app.innerHTML = '';
    if (isLoading) {
      var loading = el('div', '불러오는 중...', 'empty-state');
      app.appendChild(loading);
      return;
    }
    if (isError) {
      var err = el('div', '데이터를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.', 'empty-state');
      app.appendChild(err);
      return;
    }
  }

  function render() {
    if (isLoading || isError) {
      renderStatus();
      return;
    }

    var saved = readWish();
    var wishCount = saved.size;
    document.querySelectorAll('.wish-count').forEach(function(el){ el.textContent = wishCount; });

    if (wishCount === 0) {
      if (tools) tools.style.display = 'none';
      app.innerHTML = '';
      var empty = el('div', '', 'empty-state');
      var p = el('p', '아직 찜한 게임이 없습니다.');
      var br = document.createElement('br');
      var a = el('a', '홈으로 돌아가기', 'btn btn-p');
      a.href = 'index.html';
      empty.appendChild(p);
      empty.appendChild(br);
      empty.appendChild(a);
      app.appendChild(empty);
      return;
    }

    if (!allGames) {
      isLoading = true;
      renderStatus();
      fetch('assets/game-search-index.json')
        .then(function(res) {
          if (!res.ok) throw new Error('Network error');
          return res.json();
        })
        .then(function(data) {
          isLoading = false;
          allGames = Array.isArray(data) ? data : [];
          render();
        })
        .catch(function() {
          isLoading = false;
          isError = true;
          renderStatus();
        });
      return;
    }

    var targets = readTargets();
    var myGames = allGames.filter(function(g) {
      return saved.has(String(g.appid));
    });

    var showAdult = adultCheck && adultCheck.checked;
    if (!showAdult) {
      myGames = myGames.filter(function(g) {
        return !g.adult;
      });
    }

    if (tools) tools.style.display = 'flex';
    if (cntSpan) cntSpan.textContent = myGames.length + '개';

    var sortMode = sortSelect ? sortSelect.value : 'default';
    function isHit(g) {
      var t = +targets[String(g.appid)] || 0;
      var p = +g.price || 0;
      return t > 0 && p > 0 && p <= t;
    }

    myGames.sort(function(a, b) {
      if (sortMode === 'default') {
        var hitA = isHit(a) ? 1 : 0;
        var hitB = isHit(b) ? 1 : 0;
        if (hitA !== hitB) return hitB - hitA;
        var offA = a.off || 0;
        var offB = b.off || 0;
        if (offA !== offB) return offB - offA;
        return (a.name || '').localeCompare(b.name || '');
      } else if (sortMode === 'off') {
        var offA = a.off || 0;
        var offB = b.off || 0;
        if (offA !== offB) return offB - offA;
        return (+a.price || 0) - (+b.price || 0);
      } else if (sortMode === 'cheap') {
        if ((+a.price || 0) !== (+b.price || 0)) return (+a.price || 0) - (+b.price || 0);
        return (a.name || '').localeCompare(b.name || '');
      } else if (sortMode === 'name') {
        return (a.name || '').localeCompare(b.name || '');
      }
      return 0;
    });

    app.innerHTML = '';
    if (myGames.length === 0) {
      var noMsg = el('div', '', 'empty-state');
      noMsg.appendChild(el('p', '조건에 맞는 찜 게임이 없습니다.'));
      app.appendChild(noMsg);
      return;
    }

    var grid = el('div', '', 'grid');

    myGames.forEach(function(g) {
      var appidStr = String(g.appid);
      var currentTarget = +targets[appidStr] || 0;
      var currentPrice = +g.price || 0;
      var targetHit = currentTarget > 0 && currentPrice > 0 && currentPrice <= currentTarget;

      var card = el('div', '', 'my-card');
      if (targetHit) card.classList.add('target-hit');

      var head = el('div', '', 'my-card-head');
      var imgLink = el('a');
      imgLink.href = 'game/' + g.appid + '.html';

      if (g.img && (g.img.indexOf('http://') === 0 || g.img.indexOf('https://') === 0)) {
        var img = document.createElement('img');
        img.src = g.img;
        img.alt = g.name + ' 표지';
        img.loading = 'lazy';
        img.decoding = 'async';
        imgLink.appendChild(img);
      } else {
        var ph = el('div', (g.name || '?').trim().substring(0, 2).toUpperCase(), 'ph');
        imgLink.appendChild(ph);
      }
      head.appendChild(imgLink);

      if (g.off) {
        var rib = el('span', '-' + g.off + '%', 'ribbon ' + (g.off >= 75 ? 'r-hi' : 'r-lo'));
        head.appendChild(rib);
      }

      if (targetHit) {
        var hitBadge = el('span', '🎉 목표가 도달', 'my-hit-badge');
        head.appendChild(hitBadge);
      }
      card.appendChild(head);

      var body = el('div', '', 'my-card-body');
      var title = el('a', g.name, 'my-card-title');
      title.href = 'game/' + g.appid + '.html';
      body.appendChild(title);

      var chipsDiv = el('div', '', 'chips');
      if (g.atl && g.atl_txt) chipsDiv.appendChild(el('span', g.atl_txt, 't atl'));
      if (g.demo) chipsDiv.appendChild(el('span', '데모', 't demo'));
      if (g.soon) chipsDiv.appendChild(el('span', '출시예정', 't soon'));
      else if (g.new) chipsDiv.appendChild(el('span', '신작', 't new'));
      if (g.kr_ov) chipsDiv.appendChild(el('span', '압도적 한국어', 't kr-ov'));
      else if (g.kr) chipsDiv.appendChild(el('span', '한국어', 't kr'));
      if (chipsDiv.childNodes.length > 0) body.appendChild(chipsDiv);

      var rc = '';
      if (g.r_lbl) {
        rc = g.r_lbl + ' · 리뷰 ' + g.r_tot.toLocaleString('ko-KR');
        if (g.r_pct !== null && g.r_pct !== undefined) rc += ' · 긍정 ' + g.r_pct + '%';
      } else if (g.r_tot >= 10) {
        rc = '리뷰 ' + g.r_tot.toLocaleString('ko-KR');
      }
      if (rc) {
        body.appendChild(el('div', rc, 'tagline'));
      }

      var priceRow = el('div', '', 'my-price-row');
      var priceBox = el('div', '', 'price');
      if (g.free) {
        priceBox.appendChild(el('span', '무료', 'now'));
      } else if (!currentPrice) {
        priceBox.appendChild(el('span', g.soon ? '출시 전' : '가격 미정', 'now'));
      } else {
        priceBox.appendChild(el('span', currentPrice.toLocaleString('ko-KR') + '원', 'now'));
        if (g.p_init && g.p_init > currentPrice) {
          priceBox.appendChild(el('span', g.p_init.toLocaleString('ko-KR') + '원', 'init'));
        }
      }
      priceRow.appendChild(priceBox);
      body.appendChild(priceRow);

      var targetPanel = el('div', '', 'my-target-panel');
      var targetView = el('div', '', 'my-target-view');
      var targetStatus = el('div', '', 'my-target-status' + (targetHit ? ' hit' : ''));

      if (currentTarget > 0) {
        var tText = el('span', '목표가: ' + currentTarget.toLocaleString('ko-KR') + '원', 'current-target');
        targetStatus.appendChild(tText);
        if (targetHit) {
          targetStatus.appendChild(el('span', '🎉 목표가 도달', 'target-hit-text'));
        }
        targetView.appendChild(targetStatus);

        var actions = el('div', '', 'my-target-actions');
        var editBtn = el('button', '수정', 'btn btn-s');
        editBtn.type = 'button';
        var delBtn = el('button', '목표가 삭제', 'btn btn-s');
        delBtn.type = 'button';
        actions.appendChild(editBtn);
        actions.appendChild(delBtn);
        targetView.appendChild(actions);
      } else {
        targetStatus.appendChild(el('span', '목표 가격 미설정', 'current-target'));
        targetView.appendChild(targetStatus);

        var actions = el('div', '', 'my-target-actions');
        var setBtn = el('button', '+ 목표가 설정', 'btn btn-s');
        setBtn.type = 'button';
        actions.appendChild(setBtn);
        targetView.appendChild(actions);
      }
      targetPanel.appendChild(targetView);

      var targetEdit = el('div', '', 'my-target-edit');
      targetEdit.style.display = 'none';
      var editRow = el('div', '', 'target-row');
      var input = el('input', '', 'target-input');
      input.type = 'text';
      input.placeholder = '목표 가격 입력';
      if (currentTarget > 0) input.value = currentTarget.toLocaleString('ko-KR');

      input.addEventListener('input', function() {
        var val = this.value.replace(/[^0-9]/g, '');
        this.value = val ? Number(val).toLocaleString('ko-KR') : '';
      });

      var wonSpan = el('span', '원');
      var saveBtn = el('button', '저장', 'btn btn-s btn-p target-save');
      saveBtn.type = 'button';
      var cancelBtn = el('button', '취소', 'btn btn-s target-del');
      cancelBtn.type = 'button';

      editRow.appendChild(input);
      editRow.appendChild(wonSpan);
      editRow.appendChild(saveBtn);
      editRow.appendChild(cancelBtn);
      targetEdit.appendChild(editRow);
      targetPanel.appendChild(targetEdit);

      var showEdit = function() {
        targetView.style.display = 'none';
        targetEdit.style.display = 'block';
        input.focus();
      };
      var hideEdit = function() {
        targetEdit.style.display = 'none';
        targetView.style.display = 'block';
      };

      if (targetView.querySelector('button')) {
        targetView.querySelectorAll('button').forEach(function(b) {
          if (b.textContent === '수정' || b.textContent === '+ 목표가 설정') {
            b.addEventListener('click', showEdit);
          } else if (b.textContent === '목표가 삭제') {
            b.addEventListener('click', function() {
              var curT = readTargets();
              delete curT[appidStr];
              writeTargets(curT);
              if (window.steamWishlist && window.steamWishlist.paint) window.steamWishlist.paint();
              render();
            });
          }
        });
      }

      saveBtn.addEventListener('click', function() {
        var n = Number(input.value.replace(/[^0-9]/g, ''));
        var curT = readTargets();
        if (n > 0) {
          curT[appidStr] = n;
        } else {
          delete curT[appidStr];
        }
        writeTargets(curT);
        if (window.steamWishlist && window.steamWishlist.paint) window.steamWishlist.paint();
        render();
      });

      cancelBtn.addEventListener('click', hideEdit);

      body.appendChild(targetPanel);
      card.appendChild(body);

      var foot = el('div', '', 'my-card-foot');
      var detailBtn = el('a', '상세보기', 'btn btn-s');
      detailBtn.href = 'game/' + g.appid + '.html';

      var removeBtn = el('button', '찜 삭제', 'btn btn-s');
      removeBtn.type = 'button';
      removeBtn.setAttribute('aria-label', g.name + ' 찜 목록에서 삭제');
      removeBtn.addEventListener('click', function() {
        var curWish = readWish();
        curWish.delete(appidStr);
        writeWish(curWish);
        document.querySelectorAll('.wish-count').forEach(function(el){ el.textContent = curWish.size; });
        if (window.steamWishlist && window.steamWishlist.paint) window.steamWishlist.paint();
        render();
      });

      foot.appendChild(detailBtn);
      foot.appendChild(removeBtn);
      card.appendChild(foot);

      grid.appendChild(card);
    });

    app.appendChild(grid);
  }

  if (sortSelect) sortSelect.addEventListener('change', render);
  if (adultCheck) adultCheck.addEventListener('change', render);

  document.addEventListener('DOMContentLoaded', render);
})();
</script>
'''
    return page("내 찜 목록 — GameDil", html, updated, depth=0, freshness=freshness, desc="브라우저에 저장된 찜 게임과 목표 가격을 확인합니다.", extra_head='<meta name="robots" content="noindex,follow">')


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")
    log = logging.getLogger("build")

    conn = store.connect()
    games = store.all_games(conn)
    last_collection = store.get_meta(conn, "last_collection_at")
    if not last_collection:
        # 메타 기록이 생기기 전 DB도 현재 동접/리뷰 수집 시각으로 최대한 정확히 표시한다.
        stamps = [g.get("players_checked_at") for g in games if g.get("players_checked_at")]
        stamps += [g.get("reviews_checked_at") for g in games if g.get("reviews_checked_at")]
        last_collection = max(stamps) if stamps else None
    conn.close()

    if not games:
        log.error("DB에 게임이 없다. 먼저 collect.py 를 실행할 것.")
        return 1

    freshness = freshness_info(last_collection)
    updated = freshness["display"] if last_collection else datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    os.makedirs(os.path.join(config.SITE_DIR, "game"), exist_ok=True)

    recent_drops = get_recent_drops(games)
    recent_drops_map = {g['appid']: g for g in recent_drops}

    os.makedirs(os.path.join(config.SITE_DIR, "assets"), exist_ok=True)
    index_data = []
    for g in games:
        g_copy = dict(g)
        if g['appid'] in recent_drops_map:
            g_copy['recent_drop_amount'] = recent_drops_map[g['appid']]['recent_drop_amount']

        index_data.append({
            "appid": g_copy["appid"],
            "name": g_copy["name"],
            "n": g_copy["name"].lower(),
            "demo": 1 if (g_copy.get('has_demo') or g_copy.get('app_type')=='demo') else 0,
            "soon": 1 if g_copy.get('coming_soon') else 0,
            "new": 1 if g_copy.get('tag')=='신작' else 0,
            "kr": 1 if g_copy.get('korean') else 0,
            "adult": 1 if g_copy.get('adult') else 0,
            "off": g_copy.get('discount_pct') or 0,
            "price": g_copy.get('price_final') or 0,
            "p_init": g_copy.get('price_initial') or 0,
            "free": 1 if g_copy.get('is_free') else 0,
            "score": g_copy.get('score') or 0,
            "atl": 1 if atl_label(g_copy) else 0,
            "atl_txt": atl_label(g_copy).replace('<span class="t atl">', "").replace("</span>", "") if atl_label(g_copy) else "",
            "img": g_copy.get("header_image") or "",
            "recent_drop": g_copy.get("recent_drop_amount") or 0,
            "players": g_copy.get("players_current") or 0,
            "p_delta": g_copy.get("player_delta") or 0,
            "r_lbl": review_label(g_copy) or "",
            "r_tot": g_copy.get("review_total") or g_copy.get("review_count") or 0,
            "r_pct": g_copy.get("review_positive_pct"), # can be None
            "dev": g_copy.get("developer") or g_copy.get("genres") or "",
            "kr_ov": 1 if g_copy.get("korean") and g_copy.get("developer") and is_overwhelming(g_copy) else 0
        })

    import json
    with open(os.path.join(config.SITE_DIR, "assets", "game-search-index.json"), "w", encoding="utf-8") as f:
        json.dump(index_data, f, ensure_ascii=False, separators=(',', ':'))

    def write(rel: str, text: str) -> None:
        with open(os.path.join(config.SITE_DIR, rel), "w", encoding="utf-8") as f:
            f.write(text)

    write("style.css", theme.CSS)
    if os.path.exists(os.path.join(config.ROOT, "favicon.svg")):
        write("favicon.svg", open(os.path.join(config.ROOT, "favicon.svg"), encoding="utf-8").read())
    write("index.html", build_index(games, updated, freshness, recent_drops=recent_drops))
    write("compare.html", build_compare(games, updated, freshness, recent_drops_map))
    write("my-games.html", build_my_games(updated, freshness))
    paths = ["index.html"]

    for spec in LANDINGS:
        if spec["slug"] == "recent-drops":
            write(f"{spec['slug']}.html", build_landing(spec, recent_drops[:120], updated, freshness))
        else:
            write(f"{spec['slug']}.html", build_landing(spec, games, updated, freshness))
        paths.append(f"{spec['slug']}.html")

    # 성인 게임 상세는 만들되 사이트맵에 넣지 않는다 (검색에 내보내지 않음)
    for g in games:
        rd = recent_drops_map.get(g["appid"])
        write(os.path.join("game", f"{g['appid']}.html"), build_detail(g, games, updated, freshness, recent_drop=rd))
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
    log.info("생성 완료 — 게임 %d개(성인 %d 숨김), 추천후보 %d, 데모 %d, "
             "랜딩 %d, 사이트맵 %d개 URL → %s",
             len(games), adult, cands, demos, len(LANDINGS), len(paths), config.SITE_DIR)
    return 0


if __name__ == "__main__":
    sys.exit(main())
