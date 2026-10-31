# 西班牙動態看板｜馬德里・巴塞隆納

每小時（GitHub Actions cron `0 * * * *`）抓取罷工、抗議、縱火/暴力、官方警示相關的新聞與社群貼文（Google News、TinyFish、X、YouTube、TikTok、Instagram、Threads，經 [Treg.to](https://treg.to)），以 Gemini 篩選、去重、分類並評分 1–5，產生繁中摘要、趨勢與 11/5–11/15 日期時間軸，部署到 GitHub Pages。

- `scripts/fetch.py` Treg HTTP 呼叫（`X-Treg-Token` 取自 secret `TREG_TOKEN`）
- `scripts/score.py` Gemini（secret `GEMINI_API_KEY`，只在 Action 內使用）
- `scripts/render.py` 靜態頁 `docs/index.html`
- `data/history.json` 每次執行的等級、趨勢與 Treg 花費（micro-USD）

成本控制：新聞與 X 每小時；YouTube/TikTok 每 3 小時；Threads/Instagram 每 6 小時。手動執行時可帶 `force_all=1` 抓全部來源。
