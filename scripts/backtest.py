"""Backtest a contrarian use of the ten-indicator signal on several Taiwan listings over the last six months.

Each trading day the signal is computed from daily bars up to the previous close (no look-ahead).
At 10:00 the strategy trades against the signal: 賣出 -> buy BUY_QTY shares, 買入 -> sell SELL_QTY
shares if any are held (no short selling), 持有 -> nothing. Taiwan fees are included.
For comparison it also reports following the signal with the same sizes, and buying BUY_QTY shares and holding.
Writes data/backtest.json.
"""
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_markets import chart
from fetch_tsmc import analyse, daily_bars

DATA = Path(__file__).resolve().parent.parent / "data"
# code, Yahoo symbol, name
STOCKS = [
    ("2454", "2454.TW", "聯發科"),
    ("2330", "2330.TW", "台積電"),
    ("5274", "5274.TWO", "信驊"),
    ("0050", "0050.TW", "元大台灣50"),
]
BUY_QTY, SELL_QTY = 200, 100  # shares per trade (odd-lot trading)
MONTHS = 6
FEE_RATE, FEE_MIN, TAX_RATE = 0.001425, 20, 0.003
TW = timezone(timedelta(hours=8))
# signal -> what the strategy does
STRATEGIES = {
    "contrarian": {"賣出": "buy", "買入": "sell"},
    "follow": {"買入": "buy", "賣出": "sell"},
}


def fee(amount, sell):
    return max(round(amount * FEE_RATE), FEE_MIN) + (round(amount * TAX_RATE) if sell else 0)


def simulate(signals, rule):
    """signals: list of (date, advice, price at 10:00, close). BUY_QTY / SELL_QTY shares per trade."""
    shares = cost = cash = realized = fees = prev = max_cost = 0.0
    out = []
    for d, advice, price, close in signals:
        do, action, day_fee = rule.get(advice), "—", 0
        if do == "buy":
            day_fee = fee(price * BUY_QTY, sell=False)
            cash -= price * BUY_QTY + day_fee
            cost += price * BUY_QTY
            shares += BUY_QTY
            action = f"買進 {BUY_QTY} 股"
        elif do == "sell" and shares > 0:
            qty = min(SELL_QTY, shares)
            avg = cost / shares
            day_fee = fee(price * qty, sell=True)
            cash += price * qty - day_fee
            realized += (price - avg) * qty
            cost -= avg * qty
            shares -= qty
            action = f"賣出 {int(qty)} 股"
        elif do == "sell":
            action = "無持股，不動作"
        fees += day_fee
        max_cost = max(max_cost, cost)
        equity = cash + shares * close
        out.append({"action": action, "shares": int(shares), "fee": day_fee,
                    "pnl": round(equity - prev), "cum": round(equity)})
        prev = equity
    last_close = signals[-1][3]
    summary = {
        "total": round(prev), "realized": round(realized), "unrealized": round(shares * last_close - cost),
        "fees": round(fees), "shares_held": int(shares),
        "avg_cost": round(cost / shares, 2) if shares else None,
        "buys": sum(x["action"].startswith("買進") for x in out),
        "sells": sum(x["action"].startswith("賣出") for x in out),
        "max_cost": round(max_cost),
    }
    return out, summary


def backtest(symbol, name, start):
    ts, closes, highs, lows, vols = daily_bars(chart(symbol, "2y", "1d"))
    bars = [(datetime.fromtimestamp(t, TW).date(), c, h, l, v)
            for t, c, h, l, v in zip(ts, closes, highs, lows, vols)]

    hourly = chart(symbol, "1y", "60m")
    at10 = {}
    for t, o in zip(hourly["timestamp"], hourly["indicators"]["quote"][0]["open"]):
        dt = datetime.fromtimestamp(t, TW)
        if dt.hour == 10 and dt.minute == 0 and o is not None:
            at10[dt.date()] = o

    days, signals = [], []
    for i, (d, close, *_rest) in enumerate(bars):
        if d < start or d not in at10:
            continue
        hist = bars[:i]  # up to the previous close
        tools, bulls, advice, _ = analyse([b[1] for b in hist], [b[2] for b in hist],
                                          [b[3] for b in hist], [b[4] for b in hist])
        signals.append((d, advice, at10[d], close))
        days.append({"date": d.isoformat(), "bulls": bulls, "signal": advice, "price10": at10[d],
                     "close": close, "lights": [t["bull"] for t in tools]})

    trades, summary = simulate(signals, STRATEGIES["contrarian"])
    for day, t in zip(days, trades):
        day.update(t)
    _, follow = simulate(signals, STRATEGIES["follow"])

    first, last_close = days[0]["price10"], days[-1]["close"]
    buy_and_hold = ((last_close - first) * BUY_QTY - fee(first * BUY_QTY, False)
                    - fee(last_close * BUY_QTY, True))
    summary.update({
        "last_close": last_close,
        "trading_days": len(days),
        "signal_counts": {s: sum(x["signal"] == s for x in days) for s in ("買入", "持有", "賣出")},
        "buy_and_hold": round(buy_and_hold),
        "follow_total": follow["total"],
    })
    return {
        "symbol": symbol, "name": name,
        "start": days[0]["date"], "end": days[-1]["date"],
        "summary": summary,
        "days": days,
    }


def main():
    today = datetime.now(TW).date()
    m, y = today.month - MONTHS, today.year
    if m <= 0:
        m, y = m + 12, y - 1
    start = date(y, m, min(today.day, 28))

    stocks = {}
    for code, symbol, name in STOCKS:
        try:
            stocks[code] = backtest(symbol, name, start)
        except Exception as e:  # one failing stock should not hide the others
            print(f"{symbol}: {e}", file=sys.stderr)
            continue
        s = stocks[code]["summary"]
        print(f"{code} {name}: {stocks[code]['start']}~{stocks[code]['end']} signals {s['signal_counts']}  "
              f"contrarian {s['total']:+,} (buys {s['buys']} sells {s['sells']} held {s['shares_held']})  "
              f"follow {s['follow_total']:+,}  buy&hold {s['buy_and_hold']:+,}")
    if not stocks:
        sys.exit("no backtest could be run")
    out = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "months": MONTHS,
        "rules": {"buy_qty": BUY_QTY, "sell_qty": SELL_QTY, "fee_rate": FEE_RATE, "fee_min": FEE_MIN, "tax_rate": TAX_RATE},
        "order": list(stocks),
        "stocks": stocks,
    }
    DATA.mkdir(exist_ok=True)
    (DATA / "backtest.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), "utf-8")


if __name__ == "__main__":
    main()
