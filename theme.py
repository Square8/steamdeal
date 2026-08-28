"""
사이트 룩 — '고를 수 있게 만드는 화면'.

이 사이트가 답해야 하는 질문은 하나다: "지금 방송할/살 만한 게임이 뭐냐".
그래서 데이터를 다 뿌리지 않고, 표지(이미지)·가격·이유를 크게 보여준다.

색 역할 분리 (지킬 것):
  --brand   = 브랜드/링크/데이터 시리즈. 파랑. 좋다/나쁘다 의미 없음
  --deal    = 상태색. '역대 최저' 전용. 라임. 다른 데 재사용 안 함
  --warn    = 상태색. '곧 끝남/주의' 전용. 주황
상태색은 색만으로 뜻을 전하지 않도록 항상 글자(또는 아이콘+글자)와 함께 쓴다.
라이트/다크 3중 스코프(:root / prefers-color-scheme / [data-theme])를 모두 정의한다.
"""

FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
    'family=Gothic+A1:wght@400;500;700;800&'
    'family=Inter:wght@400;500;600;700;800;900&display=swap">'
)

CSS = """
/* ---- 라이트(기본 정의) ---- */
:root{
  --bg:#f2f5fa; --surface:#ffffff; --surface-2:#f7f9fc; --raised:#e9eef6;
  --ink:#0b1220; --ink-2:#48546a; --ink-3:#78849a; --line:#dde4ef;
  --brand:#1b63c4; --brand-ink:#ffffff; --brand-soft:rgba(27,99,196,.10);
  --deal:#3f6212; --deal-mark:#4d7c0f; --deal-soft:rgba(101,163,13,.16);
  --warn:#9a3412; --warn-soft:rgba(234,88,12,.14);
  --grid:#e6ebf3; --shadow:0 1px 2px rgba(11,18,32,.06),0 8px 24px rgba(11,18,32,.06);
}
/* ---- 다크(시스템 설정) ---- */
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --bg:#0b1220; --surface:#151e2e; --surface-2:#1a2436; --raised:#222e44;
    --ink:#eef2f8; --ink-2:#a8b4c8; --ink-3:#76839a; --line:#243044;
    --brand:#4da3ff; --brand-ink:#06101f; --brand-soft:rgba(77,163,255,.16);
    --deal:#a3e635; --deal-mark:#a3e635; --deal-soft:rgba(163,230,53,.16);
    --warn:#fb923c; --warn-soft:rgba(251,146,60,.16);
    --grid:#1e2939; --shadow:0 1px 2px rgba(0,0,0,.4),0 10px 30px rgba(0,0,0,.35);
  }
}
/* ---- 다크(직접 지정) ---- */
:root[data-theme="dark"]{
  --bg:#0b1220; --surface:#151e2e; --surface-2:#1a2436; --raised:#222e44;
  --ink:#eef2f8; --ink-2:#a8b4c8; --ink-3:#76839a; --line:#243044;
  --brand:#4da3ff; --brand-ink:#06101f; --brand-soft:rgba(77,163,255,.16);
  --deal:#a3e635; --deal-mark:#a3e635; --deal-soft:rgba(163,230,53,.16);
  --warn:#fb923c; --warn-soft:rgba(251,146,60,.16);
  --grid:#1e2939; --shadow:0 1px 2px rgba(0,0,0,.4),0 10px 30px rgba(0,0,0,.35);
}

*{box-sizing:border-box}
/* hidden 속성이 실제로 먹게 한다.
   .card 는 display:flex 라서, 작성자 규칙이 UA 의 [hidden]{display:none} 을 이겨버린다.
   이 한 줄이 없으면 검색·필터가 아무것도 숨기지 못한다(눈으로 확인한 실제 버그). */
[hidden]{display:none !important}
html{-webkit-text-size-adjust:100%; scroll-behavior:smooth}
body{
  margin:0; background:var(--bg); color:var(--ink);
  font-family:"Gothic A1","Inter","Apple SD Gothic Neo","Malgun Gothic",sans-serif;
  font-size:15px; line-height:1.55;
}
a{color:inherit; text-decoration:none}
img{max-width:100%}
.wrap{max-width:1180px; margin:0 auto; padding:0 18px 72px}

/* 숫자는 Inter 등폭 숫자로 — 가격이 줄줄이 흔들리지 않게 */
.num,.price,.big,.strike,.pct,.updated,.tile .v,td,.score-n,.rc{
  font-family:"Inter",ui-sans-serif,system-ui,sans-serif;
  font-variant-numeric:tabular-nums;
}

/* ================= 헤더 ================= */
header.top{
  position:sticky; top:0; z-index:20;
  background:color-mix(in srgb, var(--bg) 88%, transparent);
  backdrop-filter:saturate(160%) blur(10px);
  border-bottom:1px solid var(--line);
}
.topin{
  max-width:1180px; margin:0 auto; padding:12px 18px;
  display:flex; align-items:center; gap:16px; flex-wrap:wrap;
}
.logo{display:flex; align-items:baseline; gap:9px; margin-right:auto}
.logo b{
  font-family:"Inter",sans-serif; font-weight:900; font-size:1.18rem;
  letter-spacing:-.035em;
}
.logo b i{color:var(--brand); font-style:normal}
.logo span{color:var(--ink-3); font-size:12px}
nav.jump{display:flex; gap:2px; flex-wrap:wrap}
nav.jump a{
  padding:6px 11px; border-radius:8px; font-size:13px; font-weight:500;
  color:var(--ink-2);
}
nav.jump a:hover{background:var(--raised); color:var(--ink)}
.updated{color:var(--ink-3); font-size:11.5px}

/* ================= 히어로: 오늘 하나 ================= */
.hero-sec{margin:26px 0 8px}
.eyebrow{
  display:flex; align-items:center; gap:8px; margin-bottom:10px;
  font-family:"Inter",sans-serif; font-size:11px; font-weight:700;
  letter-spacing:.14em; text-transform:uppercase; color:var(--ink-3);
}
.eyebrow::after{content:""; flex:1; height:1px; background:var(--line)}
.hero{
  display:grid; grid-template-columns:minmax(0,1.25fr) minmax(0,1fr); gap:0;
  background:var(--surface); border:1px solid var(--line); border-radius:14px;
  overflow:hidden; box-shadow:var(--shadow);
}
.hero-img{position:relative; background:var(--raised); min-height:210px}
/* 이미지가 칸을 꽉 채우게. 안 그러면 본문이 더 길 때 아래에 빈 띠가 남는다. */
.hero-img .shot{height:100%}
.hero-img .shot img,.hero-img .ph{
  width:100%; height:100%; aspect-ratio:auto; object-fit:cover; display:block;
}
.hero-body{padding:22px 24px 20px; display:flex; flex-direction:column; gap:10px}
.hero-body h2{
  font-family:"Inter","Gothic A1",sans-serif; font-weight:800; font-size:1.55rem;
  margin:0; letter-spacing:-.03em; line-height:1.2; text-wrap:balance;
}
.hero-body .dev{color:var(--ink-3); font-size:12.5px; margin:-4px 0 0}
.hero-body .desc{color:var(--ink-2); font-size:13.5px; margin:0}
.whylist{list-style:none; margin:2px 0 0; padding:0; display:flex;
  flex-direction:column; gap:4px}
.whylist li{
  font-size:13px; color:var(--ink-2); padding-left:18px; position:relative;
}
.whylist li::before{
  content:"✓"; position:absolute; left:0; top:0;
  color:var(--deal); font-weight:700; font-size:12px;
}
.hero-price{display:flex; align-items:baseline; gap:10px; flex-wrap:wrap; margin-top:auto}
.hero-price .big{font-size:2.1rem; font-weight:800; letter-spacing:-.04em; line-height:1}
.buyrow{display:flex; gap:8px; flex-wrap:wrap; margin-top:12px}
.btn{
  display:inline-flex; align-items:center; gap:6px; padding:9px 15px;
  border-radius:9px; font-size:13.5px; font-weight:700; border:1px solid transparent;
  cursor:pointer; font-family:inherit;
}
.btn-p{background:var(--brand); color:var(--brand-ink)}
.btn-p:hover{filter:brightness(1.08)}
.btn-s{background:transparent; color:var(--ink-2); border-color:var(--line)}
.btn-s:hover{border-color:var(--ink-3); color:var(--ink)}
.btn:focus-visible{outline:2px solid var(--brand); outline-offset:2px}

/* ================= 프리셋 필터 ================= */
.presets{display:flex; gap:7px; flex-wrap:wrap; margin:14px 0 4px}
.chip{
  padding:7px 13px; border-radius:999px; cursor:pointer;
  font-family:"Inter","Gothic A1",sans-serif; font-size:12.5px; font-weight:600;
  background:var(--surface); color:var(--ink-2); border:1px solid var(--line);
}
.chip:hover{color:var(--ink); border-color:var(--ink-3)}
.chip[aria-pressed="true"]{
  background:var(--brand); border-color:var(--brand); color:var(--brand-ink);
}
.chip:focus-visible{outline:2px solid var(--brand); outline-offset:2px}

/* ================= 섹션 / 그리드 ================= */
section{margin-top:34px; scroll-margin-top:76px}
.sec-head{display:flex; align-items:flex-end; gap:10px; flex-wrap:wrap; margin-bottom:4px}
.sec-head h2{
  font-family:"Inter","Gothic A1",sans-serif; font-weight:800; font-size:1.12rem;
  margin:0; letter-spacing:-.025em;
}
.sec-head .cnt{
  font-family:"Inter",sans-serif; font-size:12px; font-weight:700; color:var(--ink-3);
}
.sec-head .more{margin-left:auto; font-size:12.5px; color:var(--brand); font-weight:600}
.sec-note{margin:2px 0 12px; color:var(--ink-3); font-size:12.5px}

.grid{display:grid; grid-template-columns:repeat(auto-fill,minmax(214px,1fr)); gap:14px}
/* 가로 스크롤 레일: 보조 섹션은 세로로 길어지지 않게 */
.rail{
  display:grid; grid-auto-flow:column; grid-auto-columns:236px; gap:14px;
  overflow-x:auto; padding-bottom:10px; scroll-snap-type:x proximity;
}
.rail > *{scroll-snap-align:start}

/* ================= 카드 ================= */
.card{
  position:relative; display:flex; flex-direction:column;
  background:var(--surface); border:1px solid var(--line); border-radius:12px;
  overflow:hidden; transition:transform .13s, border-color .13s, box-shadow .13s;
}
.card:hover{transform:translateY(-2px); border-color:var(--ink-3); box-shadow:var(--shadow)}
.card:focus-visible{outline:2px solid var(--brand); outline-offset:2px}
.shot{position:relative; background:var(--raised)}
.shot img{width:100%; aspect-ratio:460/215; object-fit:cover; display:block}
/* 이미지가 없을 때: 검은 빈칸 대신 제목 머리글자를 쓴 자리표시 */
.ph{
  aspect-ratio:460/215; display:grid; place-items:center;
  background:linear-gradient(140deg,var(--raised),var(--surface-2));
  font-family:"Inter",sans-serif; font-weight:900; font-size:1.5rem;
  color:var(--ink-3); letter-spacing:-.04em;
}
.ribbon{
  position:absolute; top:8px; left:8px; padding:3px 8px; border-radius:7px;
  background:var(--brand); color:var(--brand-ink);
  font-family:"Inter",sans-serif; font-weight:800; font-size:12.5px;
  letter-spacing:-.02em;
}
.card-b{padding:11px 13px 13px; display:flex; flex-direction:column; gap:7px; flex:1}
.card-b .name{
  font-weight:700; font-size:14px; line-height:1.35; letter-spacing:-.015em;
  display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical;
  overflow:hidden;
}
.chips{display:flex; gap:4px; flex-wrap:wrap}
.tagline{
  color:var(--ink-3); font-size:11.5px; overflow:hidden; text-overflow:ellipsis;
  white-space:nowrap;
}
.card-f{
  margin-top:auto; padding-top:9px; border-top:1px solid var(--line);
  display:flex; align-items:flex-end; justify-content:space-between; gap:8px;
}
.price{text-align:right; white-space:nowrap; margin-left:auto}
.price .now{font-size:15px; font-weight:800; letter-spacing:-.03em; display:block}
.price .strike{
  color:var(--ink-3); font-size:11.5px; text-decoration:line-through; display:block;
}
.pct{color:var(--brand); font-weight:800; font-size:13px}

/* 점수 막대: 숫자와 막대를 같이 (색만으로 전달 안 함) */
.score{display:flex; align-items:center; gap:6px; min-width:0}
.score-n{
  font-size:12px; font-weight:800; color:var(--ink-2); letter-spacing:-.02em;
}
.bar{
  width:44px; height:4px; border-radius:99px; background:var(--grid);
  overflow:hidden; flex:none;
}
.bar i{display:block; height:100%; background:var(--brand); border-radius:99px}
.spark{width:44px; height:20px; display:block; flex:none}

/* ================= 상태 칩 (글자 필수) ================= */
.t{
  display:inline-block; padding:1.5px 6px; border-radius:6px;
  font-family:"Inter","Gothic A1",sans-serif; font-size:10.5px; font-weight:800;
  letter-spacing:.01em; white-space:nowrap;
  background:var(--raised); color:var(--ink-2);
}
.t.demo{background:var(--brand-soft); color:var(--brand)}
.t.soon{background:var(--warn-soft); color:var(--warn)}
.t.new{background:var(--deal-soft); color:var(--deal)}
.t.free{background:var(--deal-soft); color:var(--deal)}
.t.atl{background:var(--deal-soft); color:var(--deal)}
.t.nokr,.t.adult{background:var(--raised); color:var(--ink-3)}
.badge{
  display:inline-flex; align-items:center; gap:3px; padding:1.5px 6px;
  border-radius:6px; background:var(--deal-soft); color:var(--deal);
  font-family:"Inter",sans-serif; font-size:10.5px; font-weight:800;
  white-space:nowrap;
}
.badge svg{width:9px; height:9px; flex:none}

/* ================= 탐색기 ================= */
.tools{
  display:flex; gap:8px; flex-wrap:wrap; align-items:center; margin:12px 0 14px;
}
.tools input[type=search]{
  flex:1 1 220px; min-width:160px; padding:9px 13px; border-radius:9px;
  font-family:inherit; font-size:14px;
  background:var(--surface); color:var(--ink); border:1px solid var(--line);
}
.tools input[type=search]:focus-visible{outline:2px solid var(--brand); outline-offset:1px}
.tools select{
  padding:9px 11px; border-radius:9px; font-family:inherit; font-size:13px;
  background:var(--surface); color:var(--ink); border:1px solid var(--line);
}
.sw{
  display:inline-flex; align-items:center; gap:7px; font-size:12.5px;
  color:var(--ink-2); cursor:pointer; user-select:none;
}
.sw input{accent-color:var(--brand); width:15px; height:15px}
.none{
  grid-column:1/-1; padding:34px 16px; text-align:center;
  color:var(--ink-3); font-size:13.5px;
}

/* ================= 통계 스트립 ================= */
.tiles{
  display:grid; grid-template-columns:repeat(auto-fit,minmax(110px,1fr));
  background:var(--surface); border:1px solid var(--line); border-radius:12px;
  overflow:hidden; margin-top:16px;
}
.tile{padding:11px 15px; border-right:1px solid var(--line)}
.tile:last-child{border-right:0}
.tile .k{
  font-family:"Inter",sans-serif; font-size:9.5px; letter-spacing:.14em;
  text-transform:uppercase; color:var(--ink-3); font-weight:700;
}
.tile .v{font-size:1.28rem; font-weight:800; letter-spacing:-.035em; margin-top:1px}
.tile .v small{font-size:.55em; font-weight:500; color:var(--ink-3); margin-left:2px}

footer{
  margin-top:46px; padding-top:16px; border-top:1px solid var(--line);
  color:var(--ink-3); font-size:11.5px; line-height:1.75;
}
footer p{margin:0}

/* ================= 상세 ================= */
.back{display:inline-block; margin:20px 0 14px; color:var(--ink-3); font-size:13px}
.back:hover{color:var(--ink)}
.dhero{
  display:grid; grid-template-columns:minmax(0,320px) minmax(0,1fr); gap:22px;
  align-items:start;
}
.dhero .shot{border-radius:12px; overflow:hidden; border:1px solid var(--line)}
.dhero h1{
  font-family:"Inter","Gothic A1",sans-serif; font-weight:800; font-size:1.65rem;
  margin:0 0 4px; letter-spacing:-.035em; line-height:1.18; text-wrap:balance;
}
.dhero .desc{color:var(--ink-2); font-size:14px; margin:8px 0 0}
.price-now{display:flex; align-items:baseline; gap:11px; margin:16px 0 0; flex-wrap:wrap}
.price-now .big{font-size:2.15rem; font-weight:800; letter-spacing:-.045em}
.price-now .strike{color:var(--ink-3); text-decoration:line-through; font-size:14px}
.price-now .pct{font-size:15px}

.panel{
  background:var(--surface); border:1px solid var(--line); border-radius:12px;
  padding:17px 18px 12px; margin-top:20px;
}
.panel h3{
  font-family:"Inter","Gothic A1",sans-serif; font-weight:800; font-size:.82rem;
  letter-spacing:.1em; text-transform:uppercase; margin:0 0 4px; color:var(--ink-2);
}
.panel .sub{margin:0 0 13px; color:var(--ink-3); font-size:12.5px}
.chartwrap{position:relative}
.chart{display:block; width:100%; height:auto; touch-action:pan-y}
.tip{
  position:absolute; pointer-events:none; opacity:0; transition:opacity .09s;
  background:var(--raised); border:1px solid var(--line); border-radius:8px;
  padding:6px 9px; z-index:2; white-space:nowrap;
  font-family:"Inter",sans-serif; font-size:12px;
}
.tip.on{opacity:1}
.tip .d{color:var(--ink-3); font-size:10.5px}
.tip .p{font-weight:800}
.waiting{
  padding:26px 14px; text-align:center; color:var(--ink-3); font-size:13px;
  background:var(--surface-2); border-radius:9px; border:1px dashed var(--line);
}

table{width:100%; border-collapse:collapse; font-size:13px; margin-top:2px}
th{
  text-align:left; padding:8px 10px; border-bottom:1px solid var(--line);
  font-family:"Inter",sans-serif; font-size:9.5px; letter-spacing:.13em;
  text-transform:uppercase; color:var(--ink-3); font-weight:700; white-space:nowrap;
}
td{padding:7px 10px; border-bottom:1px solid var(--line)}
tr:last-child td{border-bottom:0}
.tablewrap{overflow-x:auto}
details{margin-top:12px}
summary{cursor:pointer; color:var(--ink-3); padding:4px 0; font-size:12.5px}
summary:hover{color:var(--ink)}
summary:focus-visible{outline:2px solid var(--brand); outline-offset:2px}

/* ================= 반응형 ================= */
@media (max-width:860px){
  .hero{grid-template-columns:1fr}
  .hero-img{aspect-ratio:460/215; min-height:0}
  .dhero{grid-template-columns:1fr}
  .dhero .shot{max-width:420px}
}
@media (max-width:560px){
  .wrap{padding:0 13px 60px}
  .grid{grid-template-columns:repeat(auto-fill,minmax(158px,1fr)); gap:11px}
  .rail{grid-auto-columns:186px}
  .hero-body{padding:17px 17px 16px}
  .hero-body h2{font-size:1.3rem}
  .hero-price .big{font-size:1.75rem}
  nav.jump{order:3; width:100%; overflow-x:auto; padding-bottom:2px}
}
@media (prefers-reduced-motion:reduce){
  *{transition:none !important; scroll-behavior:auto !important}
  .card:hover{transform:none}
}
"""

BADGE_ATL = (
    '<span class="badge">'
    '<svg viewBox="0 0 10 10" aria-hidden="true" fill="currentColor">'
    '<path d="M5 9.5L.7 4h2.6V.5h3.4V4h2.6z"/></svg>역대최저</span>'
)
