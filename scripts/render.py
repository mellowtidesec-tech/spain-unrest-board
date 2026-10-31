"""Render static docs/index.html. No secrets ever reach the page."""
import json, html
from datetime import datetime, timezone, timedelta, date
from zoneinfo import ZoneInfo

TPE = ZoneInfo("Asia/Taipei")
E = lambda s: html.escape(str(s if s is not None else ""), quote=True)
CAT = {"strike": "罷工", "protest": "抗議/示威", "fire_violence": "縱火/暴力", "advisory": "官方警示"}
CITY = {"Madrid": "馬德里", "Barcelona": "巴塞隆納", "Spain": "全西班牙", "other": "其他"}
SRC = {"news": "新聞", "x": "X", "youtube": "YouTube", "tiktok": "TikTok", "instagram": "Instagram", "threads": "Threads"}
SEVC = {1: "#ffffff", 2: "#eeeeee", 3: "#ffe27a", 4: "#ff9a5c", 5: "#ff4b3a"}
LEVEL_WORD = {1: "平靜", 2: "留意", 3: "注意", 4: "警戒", 5: "嚴重"}

def tpe(iso):
    if not iso: return "時間不明"
    try:
        d = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if d.tzinfo is None: d = d.replace(tzinfo=timezone.utc)
        return d.astimezone(TPE).strftime("%m/%d %H:%M") + " 台北"
    except Exception:
        return E(iso)

def embed_html(it):
    e = it.get("embed") or {}
    t = e.get("type")
    if t == "youtube":
        return f'<div class="emb yt"><iframe loading="lazy" src="https://www.youtube.com/embed/{E(e["id"])}" title="YouTube" allow="accelerometer; encrypted-media; picture-in-picture" allowfullscreen></iframe></div>'
    if t == "x":
        return f'<div class="emb"><blockquote class="twitter-tweet" data-dnt="true" data-conversation="none"><a href="https://twitter.com/x/status/{E(e["id"])}">X 貼文</a></blockquote></div>'
    if t == "instagram":
        return f'<div class="emb"><blockquote class="instagram-media" data-instgrm-permalink="{E(e["url"])}" data-instgrm-version="14" style="max-width:100%;min-width:0;margin:0"><a href="{E(e["url"])}">Instagram</a></blockquote></div>'
    if t == "tiktok":
        return f'<div class="emb"><blockquote class="tiktok-embed" cite="{E(it["url"])}" data-video-id="{E(e["id"])}" style="max-width:100%;min-width:0;margin:0"><section><a href="{E(it["url"])}">TikTok</a></section></blockquote></div>'
    return ""

def gauge(level):
    cells = "".join(f'<span class="g{" on" if i <= level else ""}" style="background:{SEVC[i] if i <= level else "#fff"}"></span>' for i in range(1, 6))
    return f'<div class="gauge">{cells}</div>'

def spark(history):
    pts = history[-48:]
    if not pts: return ""
    w = 6
    bars = "".join(f'<rect x="{i*w}" y="{(5-p.get("level",1))*6}" width="{w-1}" height="{p.get("level",1)*6}" fill="{SEVC.get(p.get("level",1))}" stroke="#111" stroke-width="0.6"/>' for i, p in enumerate(pts))
    return f'<svg class="spark" viewBox="0 0 {len(pts)*w} 30" preserveAspectRatio="none" aria-label="近期嚴重度">{bars}</svg>'

def render(state, items, history, cost_info):
    s = state or {}
    lvl = int(s.get("level") or 1)
    trend = s.get("trend", "flat")
    arrow = {"up": "▲ 升溫", "down": "▼ 降溫", "flat": "■ 持平"}.get(trend, "■ 持平")
    gen = s.get("generated_at")
    # timeline Nov 5-15
    ups = s.get("upcoming") or []
    days = [date(2026, 11, d) for d in range(5, 16)]
    wk = "一二三四五六日"
    cols = []
    for d in days:
        evs = [u for u in ups if str(u.get("date", ""))[:10] == d.isoformat()]
        evh = "".join(
            f'<div class="ev" style="background:{SEVC.get(int(u.get("severity") or 2), "#fff")}"><b>{E(CITY.get(u.get("city"), u.get("city")))}</b> {E(u.get("title_zh"))}'
            f'<small>{E(u.get("impact_zh"))}{" ・可信度:"+E(u.get("confidence")) if u.get("confidence") else ""}</small></div>' for u in evs)
        mx = max([int(u.get("severity") or 1) for u in evs] or [0])
        cols.append(f'<div class="day{" hot" if mx >= 4 else ""}"><div class="dh"><span>11/{d.day}</span><span>週{wk[d.weekday()]}</span></div>{evh or "<div class=none>—</div>"}</div>')
    other = [u for u in ups if not ("2026-11-05" <= str(u.get("date", ""))[:10] <= "2026-11-15")]
    other_h = "".join(f'<li><b>{E(u.get("date"))}</b> {E(CITY.get(u.get("city"), u.get("city")))}｜{E(u.get("title_zh"))}</li>' for u in other)
    impacts = "".join(f"<li>{E(x)}</li>" for x in (s.get("travel_impact_zh") or []))
    # counts
    def cnt(city):
        c = {k: 0 for k in CAT}
        for i in items:
            if i.get("city") == city and i.get("category") in c: c[i["category"]] += 1
        return " ".join(f'<span class="tag">{CAT[k]} {v}</span>' for k, v in c.items())
    # cards
    items = sorted(items, key=lambda i: (-(i.get("severity") or 0), i.get("published") or ""), reverse=False)
    items = sorted(items, key=lambda i: (i.get("severity") or 0, i.get("published") or ""), reverse=True)
    quota = {"youtube": 8, "x": 10, "instagram": 4, "tiktok": 4}
    cards = []
    for it in items[:90]:
        emb = ""
        t = (it.get("embed") or {}).get("type")
        if t and quota.get(t, 0) > 0 and (it.get("severity") or 0) >= 2:
            quota[t] -= 1; emb = embed_html(it)
        sev = int(it.get("severity") or 1)
        cards.append(f'''<article class="card" data-city="{E(it.get("city"))}" data-cat="{E(it.get("category"))}" data-sev="{sev}">
<header><span class="sev" style="background:{SEVC[sev]}">{sev}</span><span class="tag">{E(SRC.get(it["source"], it["source"]))}</span><span class="tag">{E(CITY.get(it.get("city"), it.get("city")))}</span><span class="tag">{E(CAT.get(it.get("category"), it.get("category")))}</span></header>
<h3>{E(it.get("title_zh") or it.get("title"))}</h3>
<p class="note">{E(it.get("note_zh"))}</p>
<p class="orig">{E(it.get("title"))}</p>
{emb}
<footer><span>{E(it.get("author"))}</span><span>發布 {tpe(it.get("published"))}{" ・事件日 "+E(it.get("event_date")) if it.get("event_date") else ""}</span><a href="{E(it["url"])}" target="_blank" rel="noopener">原文 ↗</a></footer>
</article>''')
    per_run = cost_info.get("avg_micro", 0) / 1e6
    hist_rows = "".join(f'<tr><td>{tpe(h.get("generated_at"))}</td><td>{h.get("level")}</td><td>{E({"up":"▲","down":"▼"}.get(h.get("trend"),"■"))}</td><td>{h.get("kept")}</td><td>${h.get("treg_cost_micro",0)/1e6:.4f}</td></tr>' for h in reversed(history[-12:]))
    return f'''<!doctype html><html lang="zh-Hant-TW"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>西班牙動態看板｜馬德里・巴塞隆納 罷工・抗議・縱火</title>
<meta http-equiv="refresh" content="1800">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Funnel+Display:wght@400;600;800&family=Inter:wght@400;500;700&display=swap" rel="stylesheet">
<style>
:root{{--ink:#111;--b:1.5px solid #111}}
*{{box-sizing:border-box}}
body{{margin:0;background:#fff;color:var(--ink);font:15px/1.55 Inter,"Noto Sans TC","PingFang TC","Microsoft JhengHei",sans-serif;
background-image:linear-gradient(#f2f2f2 1px,transparent 1px),linear-gradient(90deg,#f2f2f2 1px,transparent 1px);background-size:24px 24px}}
h1,h2,h3,.big{{font-family:"Funnel Display",Inter,"Noto Sans TC",sans-serif;margin:0}}
.wrap{{max-width:1240px;margin:0 auto;padding:20px}}
.box{{border:var(--b);background:#fff;padding:16px}}
.top{{display:flex;justify-content:space-between;align-items:flex-end;gap:12px;flex-wrap:wrap;border:var(--b);background:#fff;padding:16px;margin-bottom:-1.5px}}
.top h1{{font-size:30px;font-weight:800;letter-spacing:-.5px}}
.meta{{font-size:13px}}
.grid{{display:grid;gap:0}}
.hero{{grid-template-columns:320px 1fr}}
.hero>.box,.cities>.box{{margin:0 -1.5px -1.5px 0}}
.big{{font-size:72px;font-weight:800;line-height:1}}
.gauge{{display:flex;gap:6px;margin:10px 0}}
.gauge .g{{width:40px;height:22px;border:var(--b)}}
.trend{{font-weight:700;font-size:18px;border:var(--b);display:inline-block;padding:2px 8px;margin-top:6px}}
.spark{{width:100%;height:36px;margin-top:10px;border:var(--b)}}
.cities{{grid-template-columns:1fr 1fr}}
h2{{font-size:20px;margin-bottom:8px}}
.tag{{display:inline-block;border:var(--b);padding:0 6px;font-size:12px;margin:2px 4px 2px 0;background:#fff}}
.timeline{{display:grid;grid-template-columns:repeat(11,1fr);border-left:var(--b);border-top:var(--b);margin-top:8px}}
.day{{border-right:var(--b);border-bottom:var(--b);min-height:120px;padding:6px;background:#fff;font-size:12px}}
.day.hot{{outline:3px solid #ff4b3a;outline-offset:-4px}}
.dh{{display:flex;justify-content:space-between;font-family:"Funnel Display";font-weight:800;font-size:15px;border-bottom:var(--b);margin-bottom:6px}}
.ev{{border:var(--b);padding:4px;margin-bottom:4px}}
.ev small{{display:block;color:#333}}
.none{{color:#999;text-align:center;padding-top:20px}}
.section{{margin-top:18px}}
.filters{{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:10px 0}}
select,button{{font:inherit;border:var(--b);background:#fff;padding:4px 8px;border-radius:0}}
.cards{{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:14px}}
.card{{border:var(--b);background:#fff;padding:12px;display:flex;flex-direction:column;gap:6px}}
.card header{{display:flex;align-items:center;flex-wrap:wrap}}
.sev{{display:inline-grid;place-items:center;width:26px;height:26px;border:var(--b);font-weight:800;margin-right:6px;font-family:"Funnel Display"}}
.card h3{{font-size:17px;line-height:1.35}}
.note{{margin:0}}
.orig{{margin:0;font-size:12px;color:#555}}
.card footer{{display:flex;justify-content:space-between;gap:6px;flex-wrap:wrap;font-size:12px;border-top:var(--b);padding-top:6px;margin-top:auto}}
a{{color:#111}}
.emb{{border:var(--b);overflow:hidden}}
.emb.yt{{aspect-ratio:16/9}} .emb iframe{{width:100%;height:100%;border:0;display:block}}
.emb blockquote{{margin:0}}
ul{{margin:6px 0 0 18px;padding:0}}
table{{border-collapse:collapse;font-size:12px;width:100%}} td,th{{border:var(--b);padding:3px 6px;text-align:left}}
.legend span{{display:inline-block;border:var(--b);padding:0 6px;margin-right:4px;font-size:12px}}
@media(max-width:900px){{.hero,.cities{{grid-template-columns:1fr}}.timeline{{grid-template-columns:repeat(2,1fr)}}}}
</style></head><body><div class="wrap">
<div class="top"><div><h1>西班牙動態看板｜馬德里・巴塞隆納</h1><div class="meta">罷工・抗議・縱火/暴力衝突・官方警示｜旅程 11/5–11/15｜每小時自動更新</div></div>
<div class="meta">最後更新：<b>{tpe(gen)}</b><br>本頁資料：{len(items)} 則有效項目</div></div>
<div class="grid hero">
<div class="box"><div class="meta">整體嚴重度（對旅客）</div><div class="big">{lvl}<span style="font-size:28px">/5</span></div>{gauge(lvl)}
<div style="font-weight:700;font-size:18px">{E(s.get("level_label") or LEVEL_WORD.get(lvl))}</div>
<div class="trend">{arrow}</div><div class="meta" style="margin-top:6px">{E(s.get("trend_note_zh"))}</div>
{spark(history)}<div class="meta">近 48 次更新的嚴重度走勢</div></div>
<div class="box"><h2>目前情勢摘要</h2><p style="margin:0;font-size:16px">{E(s.get("summary_zh"))}</p>
<h2 style="margin-top:14px">旅遊實際影響與建議</h2><ul>{impacts}</ul></div>
</div>
<div class="grid cities">
<div class="box"><h2>馬德里 Madrid</h2><p style="margin:0 0 6px">{E(s.get("madrid_zh"))}</p>{cnt("Madrid")}</div>
<div class="box"><h2>巴塞隆納 Barcelona</h2><p style="margin:0 0 6px">{E(s.get("barcelona_zh"))}</p>{cnt("Barcelona")}</div>
</div>
<div class="section box"><h2>11/5–11/15 已宣布的罷工・抗議日期</h2>
<div class="legend">嚴重度：<span style="background:{SEVC[2]}">2 局部</span><span style="background:{SEVC[3]}">3 明顯中斷</span><span style="background:{SEVC[4]}">4 需改行程</span><span style="background:{SEVC[5]}">5 嚴重</span></div>
<div class="timeline">{"".join(cols)}</div>
{f"<div style='margin-top:8px'><b>旅程前後其他日期：</b><ul>{other_h}</ul></div>" if other_h else ""}</div>
<div class="section"><div class="box" style="margin-bottom:-1.5px"><h2>即時項目</h2>
<div class="filters">城市 <select id="fc"><option value="">全部</option><option value="Madrid">馬德里</option><option value="Barcelona">巴塞隆納</option><option value="Spain">全西班牙</option></select>
類型 <select id="ft"><option value="">全部</option><option value="strike">罷工</option><option value="protest">抗議/示威</option><option value="fire_violence">縱火/暴力</option><option value="advisory">官方警示</option></select>
最低嚴重度 <select id="fs"><option value="1">1+</option><option value="2">2+</option><option value="3">3+</option><option value="4">4+</option></select></div></div>
<div class="box"><div class="cards" id="cards">{"".join(cards)}</div></div></div>
<div class="section grid cities">
<div class="box"><h2>官方資訊（出發前請再確認）</h2><ul>
<li><a href="https://www.boca.gov.tw/sp-trwa-content-219-1.html" target="_blank" rel="noopener">外交部領事事務局｜西班牙旅遊警示</a></li>
<li><a href="https://www.roc-taiwan.org/es/" target="_blank" rel="noopener">駐西班牙台北經濟文化辦事處</a>（急難救助）</li>
<li><a href="https://www.renfe.com/es/es/grupo-renfe/comunicacion/renfe-al-dia/avisos" target="_blank" rel="noopener">Renfe 公告／最低服務</a>・<a href="https://rodalies.gencat.cat/es/informacio_del_servei/" target="_blank" rel="noopener">Rodalies 服務狀態</a></li>
<li><a href="https://www.metromadrid.es/es" target="_blank" rel="noopener">Metro de Madrid</a>・<a href="https://www.tmb.cat/es/" target="_blank" rel="noopener">TMB Barcelona</a></li>
<li><a href="https://www.aena.es/es/infovuelos.html" target="_blank" rel="noopener">Aena 航班資訊</a>・<a href="https://www.iberia.com/" target="_blank" rel="noopener">Iberia</a>・<a href="https://www.vueling.com/" target="_blank" rel="noopener">Vueling</a></li>
<li><a href="https://x.com/112cat" target="_blank" rel="noopener">@112cat</a>・<a href="https://x.com/mossos" target="_blank" rel="noopener">@mossos</a>・<a href="https://x.com/EmergenciasMad" target="_blank" rel="noopener">@EmergenciasMad</a>・<a href="https://x.com/policia" target="_blank" rel="noopener">@policia</a></li>
</ul></div>
<div class="box"><h2>更新紀錄</h2><table><tr><th>時間</th><th>等級</th><th>趨勢</th><th>項目</th><th>Treg 花費</th></tr>{hist_rows}</table>
<p class="meta">平均每次抓取成本約 ${per_run:.4f}（Treg）；Gemini 只在 GitHub Actions 內執行。資料來源：Google News、TinyFish 新聞、X、YouTube、TikTok、Instagram、Threads（經 Treg.to）。AI 分類可能有誤，請點原文確認。</p></div>
</div></div>
<script>
const fc=document.getElementById('fc'),ft=document.getElementById('ft'),fs=document.getElementById('fs');
function f(){{document.querySelectorAll('.card').forEach(c=>{{const ok=(!fc.value||c.dataset.city===fc.value)&&(!ft.value||c.dataset.cat===ft.value)&&(+c.dataset.sev>=+fs.value);c.style.display=ok?'':'none'}})}}
[fc,ft,fs].forEach(e=>e.addEventListener('change',f));
</script>
<script async src="https://platform.twitter.com/widgets.js" charset="utf-8"></script>
<script async src="https://www.instagram.com/embed.js"></script>
<script async src="https://www.tiktok.com/embed.js"></script>
</body></html>'''
