# 全球時事熱度地圖

**網站：** https://chih-o.github.io/world-map/

用 [GDELT](https://www.gdeltproject.org/) 的全球新聞事件資料，顯示最近 6 小時各國的時事熱度和狀態；
左側顯示台灣、美國、日本、韓國、新加坡股市指數（Yahoo Finance，紅漲綠跌）。

## 運作方式

```
GDELT（每 15 分鐘更新）
   │  GitHub Actions 每 30 分鐘執行 scripts/fetch_gdelt.py、fetch_markets.py
   ▼
data/latest.json、data/history.json
   │  GitHub Pages
   ▼
index.html：世界地圖（Leaflet）
```

| 檔案 | 用途 |
|---|---|
| `index.html` | 地圖網頁 |
| `scripts/fetch_gdelt.py` | 下載 GDELT 資料，依國家統計 |
| `scripts/fetch_markets.py` | 下載股市指數 |
| `tsmc.html`、`scripts/fetch_tsmc.py` | 台積電 ADR、台積電、聯發科、SpaceX 四格技術分析（MA、MACD、RSI、KD、布林通道），網址 `/world-map/tsmc.html` |
| `backtest.html`、`scripts/backtest.py` | 聯發科、台積電、信驊、0050 近三個月十大指標反向操作回測（每天 10 點，建議賣出就買 100 股、建議買入就賣 100 股），網址 `/world-map/backtest.html` |
| `start-live.bat`、`scripts/live_server.py` | 在自己電腦上執行，個股分析頁每 30 秒即時更新 |

## 個股分析即時模式

線上版的資料由 GitHub Actions 每 30 分鐘更新（GitHub 無法更頻繁執行，報價網站也不允許網頁直接讀取）。
要每 30 秒更新：在電腦上點兩下 `start-live.bat`，會自動打開 http://localhost:8000/tsmc.html，關閉黑色視窗即停止。
| `.github/workflows/update.yml` | 每 30 分鐘自動執行並發布網站 |
| `data/` | 自動產生的資料（請勿手動修改） |

## 指標說明

- **熱度**：媒體提及次數
- **衝突比例**：言語衝突和實質衝突事件所佔比例（CAMEO QuadClass 3、4）
- **報導情緒**：GDELT AvgTone，負數代表報導偏負面
- **合作/衝突指數**：Goldstein Scale，範圍 -10 到 +10
- **狀態**：衝突比例 ≥ 45% 或指數 ≤ -3 為「緊張」；衝突比例 ≥ 30% 或情緒 ≤ -4 為「關注」；其餘為「平穩」

## 在自己電腦上執行

```
python scripts/fetch_gdelt.py
python scripts/fetch_markets.py
python -m http.server 8000
```
然後打開 http://localhost:8000

## 手動更新

GitHub → Actions → Update map data → Run workflow
