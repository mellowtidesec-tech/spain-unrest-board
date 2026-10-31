"""Hourly pipeline: fetch (Treg) -> score (Gemini) -> history -> render docs/index.html."""
import json, os, sys
from datetime import datetime, timezone, timedelta
sys.path.insert(0, os.path.dirname(__file__))
import fetch, score, render

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = lambda n: os.path.join(ROOT, "data", n)

def load(n, default):
    try:
        with open(D(n), encoding="utf-8") as f: return json.load(f)
    except Exception: return default

def save(n, obj):
    with open(D(n), "w", encoding="utf-8") as f: json.dump(obj, f, ensure_ascii=False, indent=1)

def age_days(iso, now):
    try:
        d = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if d.tzinfo is None: d = d.replace(tzinfo=timezone.utc)
        return (now - d).total_seconds() / 86400
    except Exception:
        return None

def main():
    now = datetime.now(timezone.utc)
    force = os.environ.get("FORCE_ALL") == "1"
    items = load("items.json", [])
    seen = load("seen.json", [])
    state = load("state.json", {})
    history = load("history.json", [])
    seen_set = set(seen) | {i["id"] for i in items}

    raw, cost = fetch.run(now, force_all=force)
    new = []
    for it in raw:
        if it["id"] in seen_set: continue
        a = age_days(it.get("published") or "", now)
        if a is not None and a > 12: 
            seen.append(it["id"]); continue
        new.append(it)
    # balanced pick across sources so social items are not crowded out by news
    new.sort(key=lambda i: i.get("published") or "", reverse=True)
    buckets = {}
    for it in new: buckets.setdefault(it["source"], []).append(it)
    picked = []
    while len(picked) < 130 and any(buckets.values()):
        for k in list(buckets):
            if buckets[k]: picked.append(buckets[k].pop(0))
    new = picked[:130]
    # retain kept items: published within 10 days, or event date in the future window
    def keep_old(i):
        a = age_days(i.get("published") or "", now)
        ev = i.get("event_date") or ""
        return (a is None or a <= 10) or ev >= now.date().isoformat()
    items = [i for i in items if keep_old(i)]
    print(f"raw={len(raw)} new={len(new)} kept_before={len(items)}")

    model = None
    if new or not state:
        res, model, usage = score.score(new, items, state, now.isoformat())
        byid = {i["id"]: i for i in new}
        for r in res.get("items", []):
            src = byid.get(r.get("id"))
            if not src: continue
            if r.get("keep") and not r.get("dup_of"):
                src.update({k: r.get(k) for k in ("category", "city", "event_date", "severity", "title_zh", "note_zh")})
                try: src["severity"] = max(1, min(5, int(src.get("severity") or 1)))
                except Exception: src["severity"] = 1
                items.append(src)
        seen.extend(byid.keys())
        summ = res.get("summary") or {}
        if summ:
            prev_level = state.get("level")
            state = summ
            try: state["level"] = max(1, min(5, int(state.get("level") or 1)))
            except Exception: state["level"] = 1
            state["prev_level"] = prev_level
    state["generated_at"] = now.isoformat()
    state["model"] = model or state.get("model")

    # cost history
    history.append({"generated_at": now.isoformat(), "level": state.get("level"), "trend": state.get("trend"),
                    "kept": len(items), "new_raw": len(new), "treg_cost_micro": cost["micro"],
                    "treg_calls": cost["calls"], "treg_errors": cost["errors"], "model": model,
                    "tools": [{"tool": d["tool"], "status": d.get("status"), "cost_micro": d.get("cost_micro", 0)} for d in cost["detail"]]})
    history = history[-1000:]
    last = history[-24:]
    avg = sum(h["treg_cost_micro"] for h in last) / max(1, len(last))
    print(f"treg cost this run: {cost['micro']} micro-USD over {cost['calls']} calls; avg(last {len(last)})={avg:.0f}")

    save("items.json", items); save("seen.json", seen[-4000:]); save("state.json", state); save("history.json", history)
    os.makedirs(os.path.join(ROOT, "docs"), exist_ok=True)
    with open(os.path.join(ROOT, "docs", "index.html"), "w", encoding="utf-8") as f:
        f.write(render.render(state, items, history, {"avg_micro": avg}))
    with open(os.path.join(ROOT, "docs", "data.json"), "w", encoding="utf-8") as f:
        json.dump({"state": state, "items": items}, f, ensure_ascii=False)
    print("rendered docs/index.html")

if __name__ == "__main__":
    main()
