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
  --ink:#0b1220; --ink-2:#48546a; --ink-3:#66707f; --line:#dde4ef;
  --brand:#1b63c4; --brand-ink:#ffffff; --brand-soft:rgba(27,99,196,.10);
  --deal:#3f6212; --deal-mark:#4d7c0f; --deal-soft:rgba(101,163,13,.16);
  --warn:#9a3412; --warn-soft:rgba(234,88,12,.14);
  --amber:#b45309; --amber-soft:rgba(180,83,9,.14);
  --grid:#e6ebf3; --shadow:0 1px 2px rgba(11,18,32,.06),0 8px 24px rgba(11,18,32,.06);
}
/* ---- 다크(시스템 설정) ---- */
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --bg:#0b1220; --surface:#151e2e; --surface-2:#1a2436; --raised:#222e44;
    --ink:#eef2f8; --ink-2:#a8b4c8; --ink-3:#8b98ae; --line:#243044;
    --brand:#4da3ff; --brand-ink:#06101f; --brand-soft:rgba(77,163,255,.16);
    --deal:#a3e635; --deal-mark:#a3e635; --deal-soft:rgba(163,230,53,.16);
    --warn:#fb923c; --warn-soft:rgba(251,146,60,.16);
    --amber:#fbbf24; --amber-soft:rgba(251,191,36,.18);
    --grid:#1e2939; --shadow:0 1px 2px rgba(0,0,0,.4),0 10px 30px rgba(0,0,0,.35);
  }
}
/* ---- 다크(직접 지정) ---- */
:root[data-theme="dark"]{
  --bg:#0b1220; --surface:#151e2e; --surface-2:#1a2436; --raised:#222e44;
  --ink:#eef2f8; --ink-2:#a8b4c8; --ink-3:#8b98ae; --line:#243044;
  --brand:#4da3ff; --brand-ink:#06101f; --brand-soft:rgba(77,163,255,.16);
  --deal:#a3e635; --deal-mark:#a3e635; --deal-soft:rgba(163,230,53,.16);
  --warn:#fb923c; --warn-soft:rgba(251,146,60,.16);
  --amber:#fbbf24; --amber-soft:rgba(251,191,36,.18);
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
/* 한국어는 어절 중간에서 줄이 바뀌면 읽기가 나빠진다("데모/를"). 제목류에 keep-all. */
h1,h2,h3,.lead h1,.hero-body h2,.dhero h1,.card-b .name,.sec-head h2{word-break:keep-all}
img{max-width:100%}
.wrap{max-width:1180px; margin:0 auto; padding:0 18px 72px}

/* 숫자는 Inter 등폭 숫자로 — 가격이 줄줄이 흔들리지 않게 */
.num,.price,.big,.strike,.pct,.updated,.tile .v,td,.hsearch input{
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
.freshness{
  display:flex; align-items:center; gap:6px; white-space:nowrap;
  color:var(--ink-2); font-family:"Inter",sans-serif; font-size:11.5px; font-weight:700;
}
.freshness time{color:var(--ink-3); font-weight:500}
.freshness.f-late{color:var(--amber)}
.freshness.f-stale,.freshness.f-needs{color:var(--warn)}
.freshness.f-late .live-dot{background:var(--amber); box-shadow:0 0 0 4px var(--amber-soft)}
.freshness.f-stale .live-dot,.freshness.f-needs .live-dot{background:var(--warn); box-shadow:0 0 0 4px var(--warn-soft)}
.live-dot{
  width:7px; height:7px; border-radius:50%; flex:none; background:var(--deal);
  box-shadow:0 0 0 4px var(--deal-soft);
}
nav.jump{display:flex; gap:2px; flex-wrap:wrap}
nav.jump a{
  padding:6px 11px; border-radius:8px; font-size:13px; font-weight:500;
  color:var(--ink-2);
}
nav.jump a:hover{background:var(--raised); color:var(--ink)}
.updated{color:var(--ink-3); font-size:11.5px}

/* 헤더 검색: 처음 온 사람이 검색 기능의 존재를 알 수 있어야 한다.
   맨 아래에 있으면 아무도 못 찾는다. */
.hsearch{display:flex; align-items:center; gap:0; position:relative}
.hsearch input{
  width:190px; padding:7px 32px 7px 12px; border-radius:9px; font-size:13px;
  background:var(--surface); color:var(--ink); border:1px solid var(--line);
  font-family:inherit;
}
.hsearch input::placeholder{color:var(--ink-3)}
.hsearch input:focus-visible{outline:2px solid var(--brand); outline-offset:1px}
.hsearch button{
  position:absolute; right:0; top:0; bottom:0; width:30px; display:grid;
  place-items:center; background:none; border:0; cursor:pointer; color:var(--ink-3);
  border-radius:0 9px 9px 0;
}
.hsearch button:hover{color:var(--brand)}
.hsearch button:focus-visible{outline:2px solid var(--brand); outline-offset:-2px}
.hsearch svg{width:14px; height:14px}

/* ================= 히어로: 오늘 하나 ================= */
.hero-sec{margin:26px 0 8px}
.eyebrow{
  display:flex; align-items:center; gap:8px; margin-bottom:10px;
  font-family:"Inter",sans-serif; font-size:11px; font-weight:700;
  letter-spacing:.14em; text-transform:uppercase; color:var(--ink-3);
}
.eyebrow::after{content:""; flex:1; height:1px; background:var(--line)}

/* 첫 화면 한 줄 명제 + 숫자.
   처음 온 사람은 2초 안에 '여기가 뭐 하는 곳인지' 알아야 한다.
   숫자는 빌드 때 실제 값으로 채운다 (문구는 오해가 없게 명제와 숫자를 분리). */
.lead{margin:38px 0 8px}
.lead-kicker{
  margin:0 0 9px; color:var(--brand); font-family:"Inter",sans-serif;
  font-size:11px; font-weight:800; letter-spacing:.16em;
}
.lead h1{
  font-family:"Inter","Gothic A1",sans-serif; font-weight:800;
  font-size:clamp(1.85rem, 4.5vw, 3rem); letter-spacing:-.055em; line-height:1.14;
  margin:0 0 10px; text-wrap:balance;
}
.lead .facts{
  display:flex; flex-wrap:wrap; gap:8px 18px; margin:0;
  color:var(--ink-2); font-size:13.5px;
}
.lead .facts b{
  font-family:"Inter",sans-serif; font-variant-numeric:tabular-nums;
  color:var(--ink); font-weight:800;
}
.quick-actions{
  display:flex; gap:8px; flex-wrap:wrap; margin-top:18px;
}
.quick-actions button{
  appearance:none; padding:8px 13px; border:1px solid var(--line); border-radius:999px;
  background:var(--surface); color:var(--ink-2); cursor:pointer;
  font-family:inherit; font-size:12.5px; font-weight:700;
}
.quick-actions button:hover{border-color:var(--brand); color:var(--ink); background:var(--brand-soft)}
.quick-actions button:focus-visible{outline:2px solid var(--brand); outline-offset:2px}
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
.chip.reset-btn{background:transparent; border-style:dashed; color:var(--ink-3)}
.chip.reset-btn:hover{background:var(--surface-2); color:var(--ink)}

/* ================= 섹션 / 그리드 ================= */
/* 제목만 키우면 구획이 안 느껴진다. 섹션 사이 여백을 같이 넓힌다. */
section{margin-top:4rem; scroll-margin-top:76px}
.sec-head{display:flex; align-items:baseline; gap:10px; flex-wrap:wrap; margin-bottom:6px}
.sec-head h2{
  font-family:"Inter","Gothic A1",sans-serif; font-weight:800;
  font-size:clamp(1.3rem, 2vw, 1.5rem);
  margin:0; letter-spacing:-.03em;
}
.sec-head .cnt{
  font-family:"Inter",sans-serif; font-size:12px; font-weight:700; color:var(--ink-3);
}
.sec-head .more{margin-left:auto; font-size:12.5px; color:var(--brand); font-weight:600}
.sec-note{margin:2px 0 16px; color:var(--ink-3); font-size:13px}

.grid{display:grid; grid-template-columns:repeat(auto-fill,minmax(214px,1fr)); gap:14px}
/* 보조 섹션. 데스크톱에서는 그냥 그리드다 —
   가로 스크롤은 마우스 휠로 움직이지 않아서 잘린 카드가 그대로 안 보인 채 끝난다.
   손가락으로 밀 수 있는 좁은 화면에서만 레일이 된다. */
.rail{display:grid; grid-template-columns:repeat(auto-fill,minmax(214px,1fr)); gap:14px}

/* ================= 카드 ================= */
.card{
  position:relative; display:flex; flex-direction:column;
  background:var(--surface); border:1px solid var(--line); border-radius:12px;
  overflow:hidden; transition:transform .13s, border-color .13s, box-shadow .13s;
}
.card:hover{transform:translateY(-2px); border-color:var(--ink-3); box-shadow:var(--shadow)}
/* 눈이 멈출 곳을 하나 만든다. 모든 섹션에 쓰면 다시 균일해져서 의미가 없다. */
.card.big{grid-column:span 2; grid-row:span 1}
.card.big .name{font-size:19px}
.card.big .shot img,.card.big .ph{aspect-ratio:920/215}
@media (max-width:700px){ .card.big{grid-column:span 1}
  .card.big .name{font-size:15.5px}
  .card.big .shot img,.card.big .ph{aspect-ratio:460/215} }
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
.player-badge{
  position:absolute; top:8px; right:8px; max-width:calc(100% - 16px);
  padding:3px 7px; border-radius:7px; background:rgba(4,10,20,.78); color:#f3f7ff;
  backdrop-filter:blur(5px); font-family:"Inter",sans-serif; font-size:10.5px;
  font-weight:700; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;
  display:inline-flex; align-items:center; gap:4px;
}
.player-badge::before{
  content:"●"; color:var(--deal); font-size:9px; line-height:1;
  animation:playerPulse 2s ease-in-out infinite;
}
@keyframes playerPulse{
  0%,100%{opacity:1; transform:scale(1)}
  50%{opacity:.35; transform:scale(.82)}
}
.ribbon + .player-badge{max-width:calc(100% - 78px)}
.wish{
  position:absolute; top:44px; right:8px; z-index:3; width:30px; height:30px;
  display:grid; place-items:center; padding:0; border:1px solid rgba(255,255,255,.22);
  border-radius:50%; background:rgba(4,10,20,.72); color:#f3f7ff;
  backdrop-filter:blur(5px); cursor:pointer; font-family:Arial,sans-serif;
  font-size:21px; line-height:1; transition:transform .13s, background .13s, color .13s;
}
.wish:hover{transform:scale(1.08); background:var(--brand); color:#fff}
.wish.on{background:var(--warn); border-color:var(--warn); color:#fff}
.wish:focus-visible{outline:2px solid var(--brand); outline-offset:2px}
.card.target-hit{border-color:var(--deal)}
.t.target-hit-tag{background:var(--deal-soft); border-color:var(--deal); color:var(--deal)}
.card-b{padding:11px 13px 13px; display:flex; flex-direction:column; gap:7px; flex:1}
.card-b .name{
  font-weight:800; font-size:15.5px; line-height:1.3; letter-spacing:-.02em;
  display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical;
  overflow:hidden; word-break:break-word; overflow-wrap:anywhere;
}
.chips{display:flex; gap:4px; flex-wrap:wrap}
/* 리뷰수·개발사는 3순위다. 제목과 같은 무게로 두면 스캔이 느려진다. */
.tagline{
  color:var(--ink-3); font-size:11px; overflow:hidden; text-overflow:ellipsis;
  white-space:nowrap; opacity:.85;
}
.card-f{
  margin-top:auto; padding-top:9px; border-top:1px solid var(--line);
  display:flex; align-items:flex-end; justify-content:space-between; gap:8px;
  flex-wrap:wrap;
}
.price{text-align:right; white-space:nowrap; margin-left:auto}
.price .now{font-size:15px; font-weight:800; letter-spacing:-.03em; display:block}
.price .strike{
  color:var(--ink-3); font-size:11.5px; text-decoration:line-through; display:block;
}
.pct{color:var(--brand); font-weight:800; font-size:13px}

.spark{width:52px; height:22px; display:block; flex:none}

/* 할인율은 '세기'가 한눈에 보여야 한다. 전부 같은 파랑이면 -90% 와 -25% 가 똑같아 보인다.
   색만으로 전하지 않도록 숫자를 항상 같이 쓰고, 75% 이상만 굵게 키운다. */
.offtag{font-family:"Inter",sans-serif; font-size:12.5px; font-weight:800}
.off-lo{color:var(--ink-3)}                      /* 49% 이하 — 흔하다 */
.off-mid{color:var(--brand)}                     /* 50~74% */
.off-hi{color:var(--amber); font-size:13.5px}    /* 75% 이상 — 드물다 */
.off-free{color:var(--deal)}                     /* 무료 배포 */
/* 글자색은 테마별 대비를 맞춘 --brand-ink 를 쓴다 (고정 색이면 한쪽에서 미달) */
.ribbon.r-hi{background:var(--amber); color:var(--brand-ink)}
.ribbon.r-lo{background:var(--raised); color:var(--ink-2)}

/* 할인이 없으면 구분선도 취소선도 없앤다. 다만 가격은 바닥에 정렬해서
   정보가 적은 카드도 높이와 가격 위치가 어긋나지 않게 한다. */
.card-f.bare{border-top:0; padding-top:0}

/* ================= 상태 칩 (글자 필수) ================= */
.t{
  display:inline-block; padding:2.5px 7px; border-radius:6px;
  font-family:"Inter","Gothic A1",sans-serif; font-size:11.5px; font-weight:800;
  letter-spacing:.01em; white-space:nowrap;
  background:var(--raised); color:var(--ink-2);
}
.t.demo{background:var(--brand-soft); color:var(--brand)}
/* 출시예정은 경고가 아니라 상태다. 주황은 할인 강도 전용으로 비워둔다. */
.t.soon{background:var(--raised); color:var(--ink-2)}
.t.new{background:var(--deal-soft); color:var(--deal)}
.t.free{background:var(--deal-soft); color:var(--deal)}
.t.atl{background:var(--deal-soft); color:var(--deal)}
.t.review{background:var(--brand-soft); color:var(--brand)}
.t.nokr,.t.adult{background:var(--raised); color:var(--ink-2)}
.badge{
  display:inline-flex; align-items:center; gap:3px; padding:1.5px 6px;
  border-radius:6px; background:var(--deal-soft); color:var(--deal);
  font-family:"Inter",sans-serif; font-size:11.5px; font-weight:800;
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
/* 전체 목록은 처음에 일부만 그린다. 120개를 한 번에 세로로 쌓으면
   모바일에서 2만 픽셀이 되고 아무도 끝까지 내려가지 않는다. */
.morewrap{display:flex; justify-content:center; margin-top:18px}
.morebtn{
  padding:10px 22px; border-radius:10px; cursor:pointer; font-family:inherit;
  font-size:13.5px; font-weight:700;
  background:var(--surface); color:var(--ink-2); border:1px solid var(--line);
}
.morebtn:hover{border-color:var(--ink-3); color:var(--ink)}
.morebtn:focus-visible{outline:2px solid var(--brand); outline-offset:2px}

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

/* ================= 상세: '이게 무슨 게임인가'에 답하는 부분 ================= */
.dmedia{border-radius:12px; overflow:hidden; border:1px solid var(--line);
  background:var(--raised)}
.dmedia .shot{border:0; border-radius:0}
.dvid{display:block; width:100%; height:auto; aspect-ratio:16/9;
  background:#000; object-fit:cover}
/* 스크린샷 스트립. 좁은 화면에서는 손가락으로 밀 수 있게 가로 스크롤. */
.shots{display:grid; grid-template-columns:repeat(4,1fr); gap:9px}
.shots img{
  width:100%; aspect-ratio:16/9; object-fit:cover; display:block;
  border-radius:9px; border:1px solid var(--line); background:var(--raised);
}

/* ================= 상세 ================= */
.back{display:inline-block; margin:20px 0 14px; color:var(--ink-3); font-size:13px}
.back:hover{color:var(--ink)}
.dhero{
  display:grid; grid-template-columns:minmax(0,520px) minmax(0,1fr); gap:24px;
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
.target-row{display:flex; align-items:center; gap:8px; flex-wrap:wrap}
.target-input{
  flex:0 1 158px; min-width:0; padding:9px 10px; border-radius:9px;
  border:1px solid var(--line); background:var(--surface-2); color:var(--ink);
  font:700 14px "Inter","Gothic A1",sans-serif;
}
.target-input:focus-visible{outline:2px solid var(--brand); outline-offset:1px}
.target-row > span{color:var(--ink-2); font-size:13px}
.target-save{padding:9px 13px}
.target-del{padding:9px 13px}
.target-result{min-height:18px; margin:10px 0 0; color:var(--ink-3); font-size:12.5px; line-height:1.4}
.target-result.hit{color:var(--deal)}
.current-target{color:var(--ink); font-size:13.5px}
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
  width:1%;                      /* 이름 열은 내용 폭까지만. 값이 멀어지면 읽기 흐름이 끊긴다 */
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
  .dmedia{max-width:560px}
  .shots{grid-template-columns:repeat(2,1fr)}
}
@media (max-width:560px){
  .wrap{padding:0 13px 60px}
  .grid{grid-template-columns:repeat(auto-fill,minmax(158px,1fr)); gap:11px}
  .rail{
    grid-template-columns:none; grid-auto-flow:column; grid-auto-columns:204px;
    overflow-x:auto; padding-bottom:10px; scroll-snap-type:x proximity;
    scrollbar-width:none;
  }
  .rail::-webkit-scrollbar{display:none}
  .rail > *{scroll-snap-align:start}
  .rail .card-b{padding:10px 11px 11px; gap:6px}
  .rail .card-b .name{font-size:15px}
  .rail .tagline{font-size:10.5px}
  .rail .shot img,.rail .ph{aspect-ratio:16/9}
  .rail .wish{top:43px}
  section{margin-top:3.25rem}
  .lead{margin-top:28px}
  .lead h1{font-size:1.95rem}
  .lead .facts{gap:6px 13px; font-size:12.5px}
  .quick-actions{
    flex-wrap:nowrap; overflow-x:auto; white-space:nowrap; margin-left:-13px; margin-right:-13px;
    padding:0 13px 8px; scrollbar-width:none; scroll-snap-type:x mandatory;
  }
  .quick-actions::-webkit-scrollbar{display:none}
  .quick-actions button{flex:0 0 auto; white-space:nowrap; scroll-snap-align:start}
  .hero-body{padding:17px 17px 16px}
  .hero-body h2{font-size:1.3rem}
  .hero-price .big{font-size:1.75rem}
  nav.jump{
    order:3; width:100%; overflow-x:auto; padding-bottom:2px;
    flex-wrap:nowrap;                 /* 줄바꿈하면 헤더가 두 줄이 된다 */
    scrollbar-width:none;
  }
  nav.jump::-webkit-scrollbar{display:none}
  nav.jump a{white-space:nowrap}
  /* 모바일: [로고 | 갱신] / [검색] / [메뉴]. */
  .topin{padding:10px 13px; gap:10px}
  .logo span{display:none}
  .logo{margin-right:0; flex:none}
  .freshness{margin-left:auto}
  .freshness.f-ok .f-time{display:none}
  .hsearch{order:2; flex:1 1 100%; min-width:0}
  .hsearch input{width:100%}
}
@media (prefers-reduced-motion:reduce){
  *{transition:none !important; scroll-behavior:auto !important}
  .card:hover{transform:none}
  .player-badge::before{animation:none}
}
"""

BADGE_ATL = (
    '<span class="badge">'
    '<svg viewBox="0 0 10 10" aria-hidden="true" fill="currentColor">'
    '<path d="M5 9.5L.7 4h2.6V.5h3.4V4h2.6z"/></svg>역대최저</span>'
)
