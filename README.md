# 全球時事熱度地圖

**網站：** https://chih-o.github.io/world-map/

用 [GDELT](https://www.gdeltproject.org/) 的全球新聞事件資料，顯示最近 6 小時各國的時事熱度和狀態。

## 運作方式

```
GDELT（每 15 分鐘更新）
   │  GitHub Actions 每小時執行 scripts/fetch_gdelt.py
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
| `.github/workflows/update.yml` | 每小時自動執行並發布網站 |
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
python -m http.server 8000
```
然後打開 http://localhost:8000

## 手動更新

GitHub → Actions → Update map data → Run workflow
