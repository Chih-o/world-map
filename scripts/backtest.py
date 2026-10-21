"""Backtest a contrarian use of the ten-indicator signal on MediaTek (2454.TW) over the last three months.

Each trading day the signal is computed from daily bars up to the previous close (no look-ahead).
At 10:00 the strategy trades one lot (1,000 shares) against the signal: 賣出 -> buy one lot,
買入 -> sell one lot if any is held (no short selling), 持有 -> nothing. Taiwan fees are included.
For comparison it also reports following the signal one lot at a time, and buying one lot and holding.
Writes data/backtest_2454.json.
"""
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_markets import chart
from fetch_tsmc import analyse, daily_bars

DATA = Path(__file__).resolve().parent.parent / "data"
SYMBOL, NAME = "2454.TW", "聯發科"
LOT = 1000
MONTHS = 3
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
    """signals: list of (date, advice, price at 10:00, close). One lot per trade."""
    shares = cost = cash = realized = fees = prev = max_cost = 0.0
    out = []
    for d, advice, price, close in signals:
        do, action, day_fee = rule.get(advice), "—", 0
        if do == "buy":
            day_fee = fee(price * LOT, sell=False)
            cash -= price * LOT + day_fee
            cost += price * LOT
            shares += LOT
            action = "買進 1 張"
        elif do == "sell" and shares >= LOT:
            avg = cost / shares
            day_fee = fee(price * LOT, sell=True)
            cash += price * LOT - day_fee
            realized += (price - avg) * LOT
            cost -= avg * LOT
            shares -= LOT
            action = "賣出 1 張"
        elif do == "sell":
            action = "無持股，不動作"
        fees += day_fee
        max_cost = max(max_cost, cost)
        equity = cash + shares * close
        out.append({"action": action, "lots": int(shares // LOT), "fee": day_fee,
                    "pnl": round(equity - prev), "cum": round(equity)})
        prev = equity
    last_close = signals[-1][3]
    summary = {
        "total": round(prev), "realized": round(realized), "unrealized": round(shares * last_close - cost),
        "fees": round(fees), "lots_held": int(shares // LOT),
        "avg_cost": round(cost / shares, 2) if shares else None,
        "buys": sum(x["action"].startswith("買進") for x in out),
        "sells": sum(x["action"].startswith("賣出") for x in out),
        "max_cost": round(max_cost),
    }
    return out, summary


def main():
    ts, closes, highs, lows, vols = daily_bars(chart(SYMBOL, "2y", "1d"))
    bars = [(datetime.fromtimestamp(t, TW).date(), c, h, l, v)
            for t, c, h, l, v in zip(ts, closes, highs, lows, vols)]

    hourly = chart(SYMBOL, "6mo", "60m")
    at10 = {}
    for t, o in zip(hourly["timestamp"], hourly["indicators"]["quote"][0]["open"]):
        dt = datetime.fromtimestamp(t, TW)
        if dt.hour == 10 and dt.minute == 0 and o is not None:
            at10[dt.date()] = o

    today = datetime.now(TW).date()
    m, y = today.month - MONTHS, today.year
    if m <= 0:
        m, y = m + 12, y - 1
    start = date(y, m, min(today.day, 28))

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
    buy_and_hold = (last_close - first) * LOT - fee(first * LOT, False) - fee(last_close * LOT, True)
    summary.update({
        "last_close": last_close,
        "trading_days": len(days),
        "signal_counts": {s: sum(x["signal"] == s for x in days) for s in ("買入", "持有", "賣出")},
        "buy_and_hold": round(buy_and_hold),
        "follow_total": follow["total"],
    })
    out = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "symbol": SYMBOL, "name": NAME, "months": MONTHS,
        "start": days[0]["date"], "end": days[-1]["date"],
        "rules": {"lot": LOT, "fee_rate": FEE_RATE, "fee_min": FEE_MIN, "tax_rate": TAX_RATE},
        "summary": summary,
        "days": days,
    }
    DATA.mkdir(exist_ok=True)
    (DATA / "backtest_2454.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), "utf-8")
    s = summary
    print(f"{out['start']} ~ {out['end']}  {s['trading_days']} days  signals {s['signal_counts']}")
    print(f"contrarian: buys {s['buys']} sells {s['sells']} held {s['lots_held']}  total {s['total']:+,} "
          f"(realized {s['realized']:+,}, unrealized {s['unrealized']:+,}, fees {s['fees']:,})")
    print(f"follow signal 1 lot: {s['follow_total']:+,}   buy&hold 1 lot: {s['buy_and_hold']:+,}")


if __name__ == "__main__":
    main()
