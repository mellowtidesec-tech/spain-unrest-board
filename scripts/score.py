"""Gemini scoring. Key only read from env inside CI; never logged."""
import os, json, re, time, urllib.request

MODELS = ["gemini-flash-latest", "gemini-3.8-flash", "gemini-3.5-flash", "gemini-2.5-flash"]

PROMPT = """你是西班牙社會動態與旅遊安全分析師。讀者是台灣旅客（繁體中文），將於 2026-11-05 至 2026-11-15 在馬德里與巴塞隆納旅遊。
現在時間（UTC）：{now}

任務：
A. 檢視 NEW_ITEMS（新抓到的貼文/新聞，西班牙文/加泰隆尼亞文/英文）。逐筆判斷：
   - keep：凡是與「馬德里/巴塞隆納（或全西班牙層級、會影響這兩城）的罷工、抗議/示威、縱火/火災/暴力衝突/騷亂、警方部署、官方警示或交通中斷」相關，且為近 14 天內發生或已宣布的未來事件，都應 keep=true（寧可保留，讓讀者看到事態全貌）。只有明顯無關（廣告、觀光、足球、他國、與本主題無關）或舊聞（14 天以前且無後續）才 keep=false。
   - dup_of：若與其他項目（含 KEPT_ITEMS）講同一事件且資訊沒更多，填被重複的 id，並 keep=false。
   - category：strike / protest / fire_violence / advisory
   - city：Madrid / Barcelona / Spain（全國）/ other
   - event_date：事件發生或預定日期 YYYY-MM-DD（不確定填 null）
   - severity 1-5（對旅客影響）：1=輕微/零星；2=局部小規模；3=明顯交通或市區中斷；4=大範圍罷工或暴力衝突、需改行程；5=嚴重暴亂/全面癱瘓/官方警告避免前往
   - title_zh：繁中一句話標題（≤40字），note_zh：繁中一句話說明對旅客的意義（≤60字）
B. 綜合 KEPT_ITEMS + 保留的 NEW_ITEMS + PREVIOUS（上一輪結論），寫整體判斷：
   - level 1-5 與 level_label（繁中短語），trend：up/down/flat（與 PREVIOUS.level 及事態相比），trend_note_zh
   - summary_zh：3-5 句整體摘要；madrid_zh、barcelona_zh：各 2-3 句
   - upcoming：所有已宣布、落在 2026-11-01 到 2026-11-20 的罷工/抗議/示威日期（特別是 11/5-11/15），每筆 {{date, city, type, title_zh, impact_zh, severity, confidence: high/medium/low}}。PREVIOUS.upcoming 中仍有效的請保留；未經來源支持的不要捏造。
   - travel_impact_zh：3-6 條實用旅遊建議（交通：Renfe/Rodalies/Cercanías、地鐵、機場/Iberia/Vueling/Aena、計程車；應避開的地點/時段）
嚴守事實：只根據項目內容判斷，不誇大、不臆測規模或封路範圍；來源未說明的影響請寫「可能」或「待確認」。每一筆 NEW_ITEMS 都要回傳一個物件。
只輸出 JSON，格式：
{{"items":[{{"id":"...","keep":true,"dup_of":null,"category":"strike","city":"Madrid","event_date":"2026-11-11","severity":3,"title_zh":"...","note_zh":"..."}}],
 "summary":{{"level":3,"level_label":"...","trend":"flat","trend_note_zh":"...","summary_zh":"...","madrid_zh":"...","barcelona_zh":"...","upcoming":[...],"travel_impact_zh":["..."]}}}}

PREVIOUS:
{prev}

KEPT_ITEMS（已分類，供去重與綜合）：
{kept}

NEW_ITEMS：
{new}
"""

def call_gemini(prompt):
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise SystemExit("GEMINI_API_KEY missing")
    body = json.dumps({"contents": [{"parts": [{"text": prompt}]}],
                       "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2}}).encode()
    last = None
    for m in MODELS:
        for attempt in range(2):
            req = urllib.request.Request(
                f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent",
                data=body, method="POST", headers={"Content-Type": "application/json", "x-goog-api-key": key})
            try:
                r = urllib.request.urlopen(req, timeout=240)
                d = json.loads(r.read())
                txt = "".join(p.get("text", "") for p in d["candidates"][0]["content"]["parts"] if not p.get("thought"))
                usage = d.get("usageMetadata", {})
                print(f"[gemini] model={m} in={usage.get('promptTokenCount')} out={usage.get('candidatesTokenCount')}")
                txt = txt.strip()
                txt = re.sub(r"^```(json)?|```$", "", txt).strip()
                return json.loads(txt), m, usage
            except urllib.error.HTTPError as e:
                last = f"{m} HTTP {e.code}"
                print(f"[gemini] {last}")
                if e.code in (404, 400, 403): break
                time.sleep(5)
            except Exception as e:
                last = f"{m} {type(e).__name__}"
                print(f"[gemini] {last}")
                time.sleep(3)
    raise RuntimeError(f"gemini failed: {last}")

def score(new_items, kept_items, prev, now_iso):
    def slim_new(i):
        return {"id": i["id"], "source": i["source"], "author": i.get("author"), "published": i.get("published"),
                "title": i["title"], "text": i["text"][:350]}
    def slim_kept(i):
        return {"id": i["id"], "category": i.get("category"), "city": i.get("city"), "event_date": i.get("event_date"),
                "severity": i.get("severity"), "title_zh": i.get("title_zh"), "published": i.get("published")}
    prev_slim = {k: prev.get(k) for k in ("level", "level_label", "trend", "summary_zh", "upcoming", "generated_at")} if prev else {}
    prompt = PROMPT.format(now=now_iso, prev=json.dumps(prev_slim, ensure_ascii=False),
                           kept=json.dumps([slim_kept(i) for i in kept_items], ensure_ascii=False),
                           new=json.dumps([slim_new(i) for i in new_items], ensure_ascii=False))
    return call_gemini(prompt)
