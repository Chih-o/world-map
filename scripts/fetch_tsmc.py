"""Fetch TSMC ADR (TSM), TSMC (2330.TW), MediaTek (2454.TW) and SpaceX (SPCX), compute five
technical indicators, and write data/tsmc.json for tsmc.html.

Each indicator gives a bullish (red) or bearish (green) signal, following the Taiwan convention;
the count of bullish signals becomes a buy / hold / sell suggestion. Rule-based, for reference only.
build() is also used by live_server.py to refresh the data every 30 seconds.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_markets import chart  # reuse the Yahoo fetch with retries

DATA = Path(__file__).resolve().parent.parent / "data"
ADR_RATIO = 5      # 1 TSM ADR = 5 shares of 2330
CHART_DAYS = 120   # days of history sent to the page

STOCKS = [
    ("adr", "TSM", "台積電 ADR", "紐約證交所 NYSE", "USD", "美股"),
    ("tw", "2330.TW", "台積電", "台灣證交所 TWSE", "TWD", "台股"),
    ("mtk", "2454.TW", "聯發科", "台灣證交所 TWSE", "TWD", "台股"),
    ("spcx", "SPCX", "SpaceX", "那斯達克 Nasdaq", "USD", "美股"),
]


def sma(xs, n):
    out = [None] * len(xs)
    for i in range(n - 1, len(xs)):
        out[i] = sum(xs[i - n + 1:i + 1]) / n
    return out


def ema(xs, n):
    out = [None] * len(xs)
    start = next(i for i, x in enumerate(xs) if x is not None)
    if len(xs) - start < n:
        return out
    k = 2 / (n + 1)
    out[start + n - 1] = sum(xs[start:start + n]) / n
    for i in range(start + n, len(xs)):
        out[i] = xs[i] * k + out[i - 1] * (1 - k)
    return out


def rsi(xs, n=14):
    """Wilder's RSI."""
    gains = [max(xs[i] - xs[i - 1], 0) for i in range(1, len(xs))]
    losses = [max(xs[i - 1] - xs[i], 0) for i in range(1, len(xs))]
    avg_g, avg_l = sum(gains[:n]) / n, sum(losses[:n]) / n
    for g, l in zip(gains[n:], losses[n:]):
        avg_g = (avg_g * (n - 1) + g) / n
        avg_l = (avg_l * (n - 1) + l) / n
    return 100.0 if avg_l == 0 else 100 - 100 / (1 + avg_g / avg_l)


def kd(highs, lows, closes, n=9):
    """Taiwan-style stochastic: K = 2/3 K' + 1/3 RSV, D = 2/3 D' + 1/3 K."""
    k = d = 50.0
    for i in range(n - 1, len(closes)):
        hi, lo = max(highs[i - n + 1:i + 1]), min(lows[i - n + 1:i + 1])
        rsv = 50.0 if hi == lo else (closes[i] - lo) / (hi - lo) * 100
        k = k * 2 / 3 + rsv / 3
        d = d * 2 / 3 + k / 3
    return k, d


def analyse(closes, highs, lows):
    price = closes[-1]
    ma5, ma20, ma60 = sma(closes, 5)[-1], sma(closes, 20)[-1], sma(closes, 60)[-1]

    e12, e26 = ema(closes, 12), ema(closes, 26)
    dif = [a - b if a is not None and b is not None else None for a, b in zip(e12, e26)]
    dea = ema(dif, 9)
    dif_v, dea_v = dif[-1], dea[-1]
    hist = dif_v - dea_v

    r = rsi(closes)
    k, d = kd(highs, lows, closes)

    window = closes[-20:]
    mid = sum(window) / 20
    sd = (sum((x - mid) ** 2 for x in window) / 20) ** 0.5
    upper, lower = mid + 2 * sd, mid - 2 * sd
    pct_b = (price - lower) / (upper - lower) if upper != lower else 0.5

    def fmt(x):
        return f"{x:,.2f}"

    rsi_note = "超買區，留意拉回" if r >= 70 else "超賣區，留意反彈" if r <= 30 else ""
    kd_note = "高檔鈍化區" if k >= 80 else "低檔區" if k <= 20 else ""
    bb_note = "觸及上軌，短線偏熱" if pct_b >= 1 else "跌破下軌，短線偏弱" if pct_b <= 0 else ""

    tools = [
        {
            "key": "ma", "name": "均線 MA", "full": "Moving Average（20 日 vs 60 日）",
            "bull": ma20 > ma60,
            "value": f"MA20 {fmt(ma20)}／MA60 {fmt(ma60)}",
            "reason": ("20 日均線在 60 日均線之上，中期趨勢向上" if ma20 > ma60
                       else "20 日均線在 60 日均線之下，中期趨勢向下"),
            "note": f"MA5 {fmt(ma5)}；股價{'高於' if price > ma5 else '低於'} 5 日線",
        },
        {
            "key": "macd", "name": "MACD", "full": "指數平滑異同移動平均（12, 26, 9）",
            "bull": hist > 0,
            "value": f"DIF {fmt(dif_v)}／DEA {fmt(dea_v)}",
            "reason": ("DIF 在訊號線之上（柱狀體為正），動能偏多" if hist > 0
                       else "DIF 在訊號線之下（柱狀體為負），動能偏空"),
            "note": f"柱狀體 {hist:+,.2f}",
        },
        {
            "key": "rsi", "name": "RSI", "full": "相對強弱指標（14 日）",
            "bull": r > 50,
            "value": f"{r:.1f}",
            "reason": "RSI 高於 50，買方力道較強" if r > 50 else "RSI 低於 50，賣方力道較強",
            "note": rsi_note,
        },
        {
            "key": "kd", "name": "KD", "full": "隨機指標（9 日）",
            "bull": k > d,
            "value": f"K {k:.1f}／D {d:.1f}",
            "reason": "K 值在 D 值之上，短線偏多" if k > d else "K 值在 D 值之下，短線偏空",
            "note": kd_note,
        },
        {
            "key": "bb", "name": "布林通道", "full": "Bollinger Bands（20 日, 2 倍標準差）",
            "bull": price > mid,
            "value": f"上 {fmt(upper)}／中 {fmt(mid)}／下 {fmt(lower)}",
            "reason": "股價在中軌之上，位於強勢區" if price > mid else "股價在中軌之下，位於弱勢區",
            "note": bb_note or f"通道位置 {pct_b * 100:.0f}%",
        },
    ]
    bulls = sum(t["bull"] for t in tools)
    advice = "買入" if bulls >= 4 else "持有" if bulls >= 2 else "賣出"
    series = {"ma20": sma(closes, 20)[-CHART_DAYS:], "ma60": sma(closes, 60)[-CHART_DAYS:]}
    return tools, bulls, advice, series


def stock(symbol, name, exchange, currency, market):
    res = chart(symbol, "1y", "1d")
    meta, q = res["meta"], res["indicators"]["quote"][0]
    rows = [(t, c, h, l, v) for t, c, h, l, v in
            zip(res["timestamp"], q["close"], q["high"], q["low"], q["volume"])
            if None not in (c, h, l)]
    ts, closes, highs, lows, vols = (list(x) for x in zip(*rows))
    # During trading the last daily bar can lag the live quote; use the live price
    live = meta.get("regularMarketPrice")
    if live and meta.get("regularMarketTime", 0) >= ts[-1]:
        closes[-1] = live
        highs[-1], lows[-1] = max(highs[-1], live), min(lows[-1], live)
    tools, bulls, advice, series = analyse(closes, highs, lows)
    prev = closes[-2]
    period = meta.get("currentTradingPeriod", {}).get("regular", {})
    now = datetime.now(timezone.utc).timestamp()
    return {
        "symbol": symbol, "name": name, "exchange": exchange, "currency": currency, "market": market,
        "price": round(closes[-1], 2),
        "change": round(closes[-1] - prev, 2),
        "change_pct": round((closes[-1] - prev) / prev * 100, 2),
        "volume": vols[-1] or 0,
        "time": meta["regularMarketTime"],
        "timezone": meta.get("exchangeTimezoneName"),
        "open": period.get("start", 0) <= now <= period.get("end", 0),
        "range_label": "52 週" if len(closes) >= 240 else "上市以來",
        "high_52w": round(max(highs), 2), "low_52w": round(min(lows), 2),
        "tools": tools, "bulls": bulls, "advice": advice,
        "chart": {
            "t": ts[-CHART_DAYS:],
            "close": [round(c, 2) for c in closes[-CHART_DAYS:]],
            "ma20": [round(x, 2) if x else None for x in series["ma20"]],
            "ma60": [round(x, 2) if x else None for x in series["ma60"]],
        },
    }


def build():
    out = {"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "stocks": {}}
    fx = chart("TWD=X", "5d", "1d")["meta"]["regularMarketPrice"]
    out["usdtwd"] = round(fx, 3)
    for key, *info in STOCKS:
        try:
            out["stocks"][key] = stock(*info)
        except Exception as e:  # one failing symbol should not hide the others
            print(f"{info[0]}: {e}", file=sys.stderr)
    adr, tw = out["stocks"].get("adr"), out["stocks"].get("tw")
    if adr and tw:
        fair = tw["price"] * ADR_RATIO / fx
        out["premium"] = {"ratio": ADR_RATIO, "fair_usd": round(fair, 2),
                          "pct": round((adr["price"] / fair - 1) * 100, 2)}
    return out


def main():
    out = build()
    if not out["stocks"]:
        sys.exit("no stock data could be fetched")
    DATA.mkdir(exist_ok=True)
    (DATA / "tsmc.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), "utf-8")
    for s in out["stocks"].values():
        print(f"{s['symbol']}: {s['price']:.2f}  bullish {s['bulls']}/5 -> {s['advice']}")
    if "premium" in out:
        print(f"ADR premium {out['premium']['pct']:+.2f}% (USD/TWD {out['usdtwd']:.3f})")


if __name__ == "__main__":
    main()
