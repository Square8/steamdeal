"""
사이트 룩 — '가격 시세판' 컨셉.

이 사이트가 하는 일은 숫자를 계속 지켜보는 거다. 그래서 대시보드 카드가 아니라
시세 단말기처럼 만든다: 어두운 바탕, 등폭 숫자, 촘촘한 행, 상태는 왼쪽 띠로 표시.

색 역할 분리 (중요):
  --series  = 데이터(가격 추이). 파랑. 좋다/나쁘다 의미 없음
  --deal    = 상태색. '역대 최저' 전용. 라임. 다른 데 재사용 안 함
상태색은 색만으로 뜻을 전하지 않도록 항상 아이콘+글자와 함께 쓴다.
"""

FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
    'family=Archivo:wght@600;800&family=Gothic+A1:wght@400;500;700&'
    'family=JetBrains+Mono:wght@400;500;700&display=swap">'
)

CSS = """
/* 어두운 쪽이 기본 컨셉이고, 밝은 쪽은 같은 규칙을 뒤집어서 맞춘다 */
:root{
  --bg:#eef0ee; --surface:#ffffff; --surface-2:#f6f7f5; --raised:#e6e9e5;
  --ink:#10140f; --ink-2:#4d5349; --ink-3:#7c8377; --line:#d6dad3;
  --series:#2a78d6; --series-soft:rgba(42,120,214,.12);
  --deal:#3f6212; --deal-mark:#65a30d; --deal-soft:rgba(101,163,13,.14);
  --grid:#e2e5df;
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --bg:#0c100f; --surface:#151a18; --surface-2:#1b211e; --raised:#232a26;
    --ink:#eef2ee; --ink-2:#a9b3a7; --ink-3:#798477; --line:#262d29;
    --series:#5aa9e6; --series-soft:rgba(90,169,230,.16);
    --deal:#a3e635; --deal-mark:#a3e635; --deal-soft:rgba(163,230,53,.14);
    --grid:#202723;
  }
}
:root[data-theme="dark"]{
  --bg:#0c100f; --surface:#151a18; --surface-2:#1b211e; --raised:#232a26;
  --ink:#eef2ee; --ink-2:#a9b3a7; --ink-3:#798477; --line:#262d29;
  --series:#5aa9e6; --series-soft:rgba(90,169,230,.16);
  --deal:#a3e635; --deal-mark:#a3e635; --deal-soft:rgba(163,230,53,.14);
  --grid:#202723;
}

*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{
  margin:0; background:var(--bg); color:var(--ink);
  font-family:"Gothic A1","Apple SD Gothic Neo","Malgun Gothic",sans-serif;
  font-size:14.5px; line-height:1.5;
}
a{color:inherit}
.wrap{max-width:1000px; margin:0 auto; padding:26px 16px 64px}

/* 숫자는 전부 등폭 — 시세판의 핵심 */
.mono,.num,.tile .v,.price-now .big,.price-now .strike,.price-now .pct,
.updated,td,.row .off{
  font-family:"JetBrains Mono",ui-monospace,SFMono-Regular,Menlo,monospace;
  font-variant-numeric:tabular-nums;
}

/* ---- 헤더: 단말기 상단바 ---- */
header.top{
  display:flex; justify-content:space-between; align-items:flex-end; gap:14px;
  flex-wrap:wrap; padding-bottom:12px; margin-bottom:18px;
  border-bottom:2px solid var(--ink);
}
.brand h1{
  font-family:"Archivo",sans-serif; font-weight:800; font-size:1.32rem;
  margin:0; letter-spacing:-.03em; line-height:1;
}
.brand h1 a{text-decoration:none}
.brand .tag{display:block; color:var(--ink-3); font-size:12.5px; margin-top:5px}
.updated{color:var(--ink-3); font-size:11.5px; white-space:nowrap}

/* ---- 상단 수치 스트립 (카드 아님) ---- */
.tiles{
  display:flex; flex-wrap:wrap; background:var(--surface);
  border:1px solid var(--line); border-radius:2px; margin-bottom:8px;
}
.tile{flex:1 1 120px; padding:10px 14px; border-right:1px solid var(--line)}
.tile:last-child{border-right:0}
.tile .k{
  font-size:9.5px; letter-spacing:.16em; text-transform:uppercase;
  color:var(--ink-3); font-weight:700;
}
.tile .v{font-size:1.3rem; font-weight:700; margin-top:1px; letter-spacing:-.03em}
.tile .v small{font-size:.55em; font-weight:400; color:var(--ink-3); margin-left:2px}

/* ---- 섹션 제목: 얇은 라벨 ---- */
h2{
  font-family:"Archivo",sans-serif; font-weight:600; font-size:.78rem;
  letter-spacing:.13em; text-transform:uppercase;
  margin:30px 0 3px; padding-bottom:5px; border-bottom:1px solid var(--line);
}
h2 + .hint{margin:7px 0 9px; color:var(--ink-3); font-size:12.5px}

.controls{display:flex; gap:6px; flex-wrap:wrap; margin:12px 0 10px}
.controls input{
  flex:1 1 180px; min-width:140px; padding:7px 10px;
  font-family:inherit; font-size:13.5px;
  background:var(--surface); color:var(--ink);
  border:1px solid var(--line); border-radius:2px;
}
.controls input:focus-visible{outline:2px solid var(--series); outline-offset:1px}
.chip{
  padding:6px 11px; border-radius:2px; cursor:pointer;
  font-family:"JetBrains Mono",monospace; font-size:11.5px; font-weight:500;
  background:var(--surface); color:var(--ink-3);
  border:1px solid var(--line);
}
.chip:hover{color:var(--ink); border-color:var(--ink-3)}
.chip[aria-pressed="true"]{background:var(--ink); border-color:var(--ink); color:var(--bg)}
.chip:focus-visible{outline:2px solid var(--series); outline-offset:2px}

/* ---- 시세 행: 촘촘하게, 카드 느낌 없이 ---- */
.list{border:1px solid var(--line); border-radius:2px; background:var(--surface); overflow:hidden}
.row{
  position:relative; display:grid;
  grid-template-columns:1fr 88px 104px 62px; gap:10px; align-items:center;
  padding:9px 14px 9px 16px; text-decoration:none;
  border-bottom:1px solid var(--line);
}
.row:last-child{border-bottom:0}
.row:hover{background:var(--surface-2)}
.row:focus-visible{outline:2px solid var(--series); outline-offset:-2px}
/* 역대 최저 상태는 왼쪽 띠로도 표시 (색 하나에만 의존하지 않게 배지와 병행) */
.row[data-atl="1"]::before{
  content:""; position:absolute; left:0; top:0; bottom:0; width:3px;
  background:var(--deal-mark);
}
.row .name{
  font-weight:500; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;
  letter-spacing:-.01em;
}
.row .spark{width:88px; height:24px; display:block}
.row .num{text-align:right; white-space:nowrap; font-size:13.5px}
.row .now{font-weight:700}
.row .was{color:var(--ink-3); font-size:11.5px; text-decoration:line-through; margin-top:1px}
.row .off{text-align:right; font-size:12.5px; font-weight:700; color:var(--series)}
@media (max-width:640px){
  .row{grid-template-columns:1fr 80px; row-gap:4px; padding:10px 12px 10px 15px}
  .row .spark{grid-column:2; grid-row:1}
  .row .num,.row .off{grid-column:1/-1; text-align:left}
  .row .off{color:var(--ink-3)}
}

/* 아이콘 + 글자를 함께 쓰므로 색만으로 의미를 전달하지 않는다 */
.badge{
  display:inline-flex; align-items:center; gap:3px; vertical-align:2px;
  margin-left:7px; padding:1px 5px; border-radius:2px;
  background:var(--deal-soft); color:var(--deal);
  font-family:"JetBrains Mono",monospace; font-size:10px; font-weight:700;
  letter-spacing:.04em; white-space:nowrap;
}
.badge svg{width:9px; height:9px; flex:none}

.empty{padding:20px 16px; color:var(--ink-3); font-size:13px}
footer{
  margin-top:38px; padding-top:14px; border-top:1px solid var(--line);
  color:var(--ink-3); font-size:11.5px; line-height:1.7;
}
footer p{margin:0}

/* ---- 상세 ---- */
.back{
  display:inline-block; margin-bottom:16px; color:var(--ink-3);
  font-family:"JetBrains Mono",monospace; font-size:11.5px; text-decoration:none;
}
.back:hover{color:var(--ink)}
.hero{display:flex; gap:18px; flex-wrap:wrap; align-items:flex-start}
.hero img{width:264px; max-width:100%; border-radius:2px; border:1px solid var(--line)}
.hero .meta{flex:1 1 250px; min-width:210px}
.hero h1{
  font-family:"Archivo",sans-serif; font-weight:800; font-size:1.4rem;
  margin:0 0 6px; letter-spacing:-.03em; text-wrap:balance;
}
.hero .desc{color:var(--ink-2); font-size:13px; margin:0}
.price-now{display:flex; align-items:baseline; gap:9px; margin:14px 0 3px; flex-wrap:wrap}
.price-now .big{font-size:1.95rem; font-weight:700; letter-spacing:-.04em}
.price-now .strike{color:var(--ink-3); text-decoration:line-through; font-size:13px}
.price-now .pct{color:var(--series); font-weight:700; font-size:14px}

.chartbox{
  background:var(--surface); border:1px solid var(--line); border-radius:2px;
  padding:15px 15px 8px; margin-top:20px;
}
.chartbox h3{
  font-family:"Archivo",sans-serif; font-weight:600; font-size:.74rem;
  letter-spacing:.13em; text-transform:uppercase; margin:0 0 4px; color:var(--ink-2);
}
.chartbox .sub{margin:0 0 12px; color:var(--ink-3); font-size:12px}
.chartwrap{position:relative}
.chart{display:block; width:100%; height:auto; touch-action:pan-y}
.tip{
  position:absolute; pointer-events:none; opacity:0; transition:opacity .09s;
  background:var(--raised); border:1px solid var(--line); border-radius:2px;
  padding:5px 8px; z-index:2; white-space:nowrap;
  font-family:"JetBrains Mono",monospace; font-size:11.5px;
}
.tip.on{opacity:1}
.tip .d{color:var(--ink-3); font-size:10.5px}
.tip .p{font-weight:700}

table{width:100%; border-collapse:collapse; font-size:12.5px; margin-top:4px}
th{
  text-align:left; padding:7px 9px; border-bottom:1px solid var(--line);
  font-family:"Archivo",sans-serif; font-size:9.5px; letter-spacing:.14em;
  text-transform:uppercase; color:var(--ink-3); font-weight:600;
}
td{padding:5px 9px; border-bottom:1px solid var(--line)}
tr:last-child td{border-bottom:0}
.tablewrap{overflow-x:auto; margin-top:8px}
details{margin-top:12px}
summary{
  cursor:pointer; color:var(--ink-3); padding:3px 0;
  font-family:"JetBrains Mono",monospace; font-size:11.5px;
}
summary:hover{color:var(--ink)}
summary:focus-visible{outline:2px solid var(--series); outline-offset:2px}

/* ---- 성격 칩: 색이 아니라 글자가 뜻을 전달한다 ---- */
.chip-tag{
  display:inline-block; vertical-align:2px; margin-left:6px;
  padding:1px 5px; border-radius:2px; border:1px solid var(--line);
  font-family:"JetBrains Mono",monospace; font-size:10px; font-weight:700;
  letter-spacing:.02em; white-space:nowrap; color:var(--ink-2);
}
.chip-tag.demo{background:var(--series-soft); color:var(--series); border-color:transparent}
.chip-tag.soon{background:var(--raised); color:var(--ink-2); border-color:transparent}
.chip-tag.new{background:var(--deal-soft); color:var(--deal); border-color:transparent}
.chip-tag.free{background:var(--deal-soft); color:var(--deal); border-color:transparent}
.chip-tag.low{background:var(--raised); color:var(--ink-2); border-color:transparent}
.chip-tag.nokr{opacity:.7}
.sub-line{
  display:block; margin-top:2px; color:var(--ink-3);
  font-family:"JetBrains Mono",monospace; font-size:10.5px;
  overflow:hidden; text-overflow:ellipsis; white-space:nowrap;
}
h2 .side{
  font-family:"Gothic A1",sans-serif; font-size:11px; font-weight:400;
  letter-spacing:0; text-transform:none; color:var(--ink-3);
}
.row{align-items:start}
.row .spark,.row .num,.row .off{align-self:center}

@media (prefers-reduced-motion:reduce){*{transition:none !important}}
"""

BADGE_ATL = (
    '<span class="badge">'
    '<svg viewBox="0 0 10 10" aria-hidden="true" fill="currentColor">'
    '<path d="M5 9.5L.7 4h2.6V.5h3.4V4h2.6z"/></svg>역대최저</span>'
)
