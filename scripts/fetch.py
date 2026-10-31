"""Fetch raw items from Treg catalog tools. Never logs secrets."""
import os, json, time, hashlib, re, urllib.request, urllib.parse
from datetime import datetime, timezone, timedelta

TREG = "https://treg.to/call/"
UA = "spain-unrest-board/1.0"

def _tok():
    t = os.environ.get("TREG_TOKEN", "").strip()
    if not t:
        raise SystemExit("TREG_TOKEN missing")
    return t

COST = {"micro": 0, "calls": 0, "errors": 0, "detail": []}

def treg(tool, method="GET", query=None, body=None, timeout=150):
    url = TREG + tool
    if query:
        url += "?" + urllib.parse.urlencode(query)
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "X-Treg-Token": _tok(), "Content-Type": "application/json",
        "X-Treg-Route-Max-Cost": "0.004", "User-Agent": UA})
    t0 = time.time()
    try:
        r = urllib.request.urlopen(req, timeout=timeout)
        st, h, txt = r.status, r.headers, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        st, h, txt = e.code, e.headers, e.read().decode("utf-8", "replace")
    except Exception as e:  # timeout etc.
        COST["errors"] += 1
        COST["detail"].append({"tool": tool, "status": "exc", "err": type(e).__name__})
        print(f"[treg] {tool} exception {type(e).__name__}")
        return None
    c = int(h.get("X-Treg-Cost-Micro") or 0) if h else 0
    COST["micro"] += c; COST["calls"] += 1
    COST["detail"].append({"tool": tool, "status": st, "cost_micro": c, "secs": round(time.time() - t0, 1)})
    print(f"[treg] {tool} -> {st} cost={c}µ$ {round(time.time()-t0,1)}s")
    if st != 200:
        COST["errors"] += 1
        return None
    try:
        return json.loads(txt)
    except Exception:
        return None

def iid(url):
    return hashlib.sha1(url.encode()).hexdigest()[:12]

def clean(s, n=400):
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = re.sub(r"\s+", " ", s).strip()
    return s[:n]

def parse_rfc(s):
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(s).astimezone(timezone.utc).isoformat()
    except Exception:
        return None

def parse_rel(s, now):
    """'20 hours ago' / 'hace 2 días' style -> iso."""
    if not s: return None
    m = re.search(r"(\d+)\s*(second|minute|hour|day|week|month|year)", s)
    if not m: return None
    n, u = int(m.group(1)), m.group(2)
    secs = {"second":1,"minute":60,"hour":3600,"day":86400,"week":604800,"month":2592000,"year":31536000}[u]
    return (now - timedelta(seconds=n*secs)).isoformat()

def mk(source, url, title, text, published, author="", embed=None, extra=None):
    d = {"id": iid(url), "source": source, "url": url, "title": clean(title, 220),
         "text": clean(text, 500), "published": published, "author": author, "embed": embed}
    if extra: d.update(extra)
    return d

# ---------------- sources ----------------
GNEWS = [
    ("huelga Madrid", "es-ES", "ES"),
    ("vaga Barcelona", "es-ES", "ES"),
    ("manifestación Madrid OR disturbios Barcelona OR incendio protesta", "es-ES", "ES"),
    ("huelga Renfe OR huelga aeropuerto OR huelga Iberia OR huelga Vueling OR huelga metro", "es-ES", "ES"),
    ("Spain general strike November Madrid Barcelona", "en-US", "US"),
]
TINYFISH = [
    ("huelga general 11 noviembre Madrid Barcelona", "es"),
    ("vaga general Barcelona novembre", "ca"),
    ("Spain strike protest travel disruption Barcelona Madrid", "en"),
]
X_QUERIES = [
    "(huelga OR vaga OR disturbios OR manifestación OR incendio OR Blocus) (Madrid OR Barcelona) -filter:replies",
]
YT_QUERIES = ["disturbios Barcelona", "huelga general Madrid", "huelga Renfe aeropuerto"]
TT_QUERIES = ["disturbios Barcelona", "huelga Madrid", "vaga general Barcelona"]
THREADS_QUERIES = ["huelga", "vaga", "Blocus"]
IG_TAGS = ["huelgageneral", "vagageneral", "barcelona protesta"]

def run(now=None, force_all=False):
    now = now or datetime.now(timezone.utc)
    h = now.hour
    items = []
    # Google News (crawl4ai, $0.00015 each) – every run
    for q, lang, cc in GNEWS:
        d = treg("crawl4ai.google.serp.news", "POST", body={"query": q, "lang": lang, "country": cc, "limit": 15})
        for r in (d or {}).get("rows", []):
            if r.get("url"):
                items.append(mk("news", r["url"], r.get("title"), r.get("summary"), parse_rfc(r.get("published","")), r.get("source","")))
    # TinyFish news (free) – every run
    for q, lang in TINYFISH:
        d = treg("tinyfish.web.search.news", "GET", query={"query": q, "domain_type": "news", "language": lang, "recency_minutes": 60*24*10})
        for r in (d or {}).get("results", []):
            if r.get("url"):
                items.append(mk("news", r["url"], r.get("title"), r.get("snippet"), parse_rfc(r.get("date","")) or parse_rel(r.get("date",""), now), r.get("publisher") or r.get("site_name","")))
    # X (anyapi, ~$0.00054) – every run
    for q in X_QUERIES:
        d = treg("anyapi.x.search.posts", "POST", body={"query": q, "queryType": "Latest", "limit": 20})
        for t in ((d or {}).get("output") or {}).get("data", {}).get("items", []) or []:
            if not t.get("id"): continue
            url = f"https://x.com/{t.get('authorUsername','i')}/status/{t['id']}"
            pub = datetime.fromtimestamp(t["createdUtc"], timezone.utc).isoformat() if t.get("createdUtc") else None
            items.append(mk("x", url, t.get("text","")[:120], t.get("text"), pub, "@"+(t.get("authorUsername") or ""),
                            {"type": "x", "id": t["id"]}, {"engagement": (t.get("likeCount") or 0)+(t.get("retweetCount") or 0), "views": t.get("viewCount")}))
    # YouTube + TikTok every 3h
    if force_all or h % 3 == 0:
        q = YT_QUERIES[(h // 3) % len(YT_QUERIES)]
        d = treg("crawl4ai.youtube.search.videos", "POST", body={"query": q, "limit": 12})
        for v in (d or {}).get("rows", []):
            if v.get("video_id"):
                items.append(mk("youtube", f"https://www.youtube.com/watch?v={v['video_id']}", v.get("title"), v.get("description"),
                                parse_rel(v.get("published",""), now), v.get("channel",""), {"type": "youtube", "id": v["video_id"]}, {"views": v.get("views")}))
        q = TT_QUERIES[(h // 3) % len(TT_QUERIES)]
        d = treg("crawl4ai.tiktok.search.videos", "POST", body={"query": q, "limit": 10}, timeout=200)
        for v in (d or {}).get("rows", []):
            if v.get("post_id") and v.get("url"):
                items.append(mk("tiktok", v["url"], v.get("description","")[:120], v.get("description"), v.get("created_at"),
                                "@"+((v.get("author") or {}).get("username") or ""), {"type": "tiktok", "id": v["post_id"]},
                                {"views": (v.get("stats") or {}).get("plays")}))
    # Threads + Instagram every 6h
    if force_all or h % 6 == 0:
        q = THREADS_QUERIES[(h // 6) % len(THREADS_QUERIES)]
        d = treg("scrapecreators.x.v1-threads-search", "GET", query={"query": q})
        for p in (d or {}).get("posts", []) or []:
            user = (p.get("user") or {}).get("username", "")
            code = p.get("code")
            if not code: continue
            url = p.get("url") or f"https://www.threads.com/@{user}/post/{code}"
            cap = (p.get("caption") or {}).get("text", "") if isinstance(p.get("caption"), dict) else (p.get("caption") or "")
            pub = datetime.fromtimestamp(p["taken_at"], timezone.utc).isoformat() if isinstance(p.get("taken_at"), (int, float)) else None
            items.append(mk("threads", url, cap[:120], cap, pub, "@"+user, None, {"engagement": p.get("like_count")}))
        tag = IG_TAGS[(h // 6) % len(IG_TAGS)]
        d = treg("scrapecreators.x.v1-instagram-search-hashtag", "GET", query={"hashtag": tag, "date_posted": "last-week"})
        for p in (d or {}).get("posts", []) or []:
            sc = p.get("shortcode")
            if not sc: continue
            url = p.get("url") or f"https://www.instagram.com/p/{sc}/"
            items.append(mk("instagram", url, (p.get("caption") or "")[:120], p.get("caption"), p.get("taken_at"),
                            "@"+((p.get("owner") or {}).get("username") or ""), {"type": "instagram", "id": sc, "url": url},
                            {"views": p.get("video_view_count")}))
    # dedupe by id
    seen, out = set(), []
    for it in items:
        if it["id"] in seen: continue
        seen.add(it["id"]); out.append(it)
    return out, COST
