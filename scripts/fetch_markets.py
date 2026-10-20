"""Fetch major Asian and US stock indices from Yahoo Finance and write data/markets.json.

If a symbol cannot be fetched, the previous value from markets.json is kept.
"""
import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
HOSTS = ["query1.finance.yahoo.com", "query2.finance.yahoo.com"]

INDICES = [
    ("^TWII", "台灣", "加權指數"),
    ("^GSPC", "美國", "S&P 500"),
    ("^IXIC", "美國", "那斯達克"),
    ("^DJI", "美國", "道瓊工業"),
    ("^N225", "日本", "日經 225"),
    ("^KS11", "韓國", "KOSPI"),
    ("^STI", "新加坡", "海峽時報指數"),
]


def chart(symbol, range_, interval):
    path = f"/v8/finance/chart/{urllib.parse.quote(symbol)}?range={range_}&interval={interval}"
    err = None
    for attempt in range(3):
        host = HOSTS[attempt % len(HOSTS)]
        req = urllib.request.Request("https://" + host + path, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)["chart"]["result"][0]
        except Exception as e:
            err = e
            time.sleep(2)
    raise err


def closes(result):
    return [round(x, 2) for x in result["indicators"]["quote"][0]["close"] if x is not None]


def main():
    path = DATA / "markets.json"
    old = {m["symbol"]: m for m in json.loads(path.read_text("utf-8"))["markets"]} if path.exists() else {}
    now = time.time()
    out, failed = [], 0

    for symbol, region, name in INDICES:
        try:
            day = chart(symbol, "1d", "5m")
            month = chart(symbol, "1mo", "1d")
        except Exception as e:
            failed += 1
            print(f"{symbol}: {e}", file=sys.stderr)
            if symbol in old:
                out.append({**old[symbol], "stale": True})
            continue
        meta = day["meta"]
        price = meta["regularMarketPrice"]
        prev = meta.get("previousClose") or meta["chartPreviousClose"]
        month_closes = closes(month)
        period = meta.get("currentTradingPeriod", {}).get("regular", {})
        out.append({
            "symbol": symbol, "region": region, "name": name,
            "currency": meta.get("currency"),
            "price": round(price, 2),
            "prev_close": round(prev, 2),
            "change": round(price - prev, 2),
            "change_pct": round((price - prev) / prev * 100, 2),
            "month_change_pct": round((price - month_closes[0]) / month_closes[0] * 100, 2) if month_closes else None,
            "time": meta["regularMarketTime"],
            "timezone": meta.get("exchangeTimezoneName"),
            "open": period.get("start", 0) <= now <= period.get("end", 0),
            "intraday": closes(day),
            "month": month_closes,
            "stale": False,
        })

    if not out:
        sys.exit("no market data could be fetched")
    DATA.mkdir(exist_ok=True)
    path.write_text(json.dumps({
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "markets": out,
    }, ensure_ascii=False, separators=(",", ":")), "utf-8")
    print(f"{len(out) - failed} indices updated, {failed} failed")


if __name__ == "__main__":
    main()
