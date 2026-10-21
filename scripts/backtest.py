"""Backtest the ten-indicator signal on MediaTek (2454.TW) over the last two months.

Each trading day the signal is computed from daily bars up to the previous close (no look-ahead).
At 10:00 the strategy buys one lot (1,000 shares) on 買入, sells one lot on 賣出 if it holds any
(no short selling), and does nothing on 持有. Taiwan fees are included. Writes data/backtest_2454.json.
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
MONTHS = 2
FEE_RATE, FEE_MIN, TAX_RATE = 0.001425, 20, 0.003
TW = timezone(timedelta(hours=8))


def fee(amount, sell):
    return max(round(amount * FEE_RATE), FEE_MIN) + (round(amount * TAX_RATE) if sell else 0)


def main():
    ts, closes, highs, lows, vols = daily_bars(chart(SYMBOL, "2y", "1d"))
    bars = [(datetime.fromtimestamp(t, TW).date(), c, h, l, v)
            for t, c, h, l, v in zip(ts, closes, highs, lows, vols)]

    hourly = chart(SYMBOL, "3mo", "60m")
    hq = hourly["indicators"]["quote"][0]
    at10 = {}
    for t, o in zip(hourly["timestamp"], hq["open"]):
        dt = datetime.fromtimestamp(t, TW)
        if dt.hour == 10 and dt.minute == 0 and o is not None:
            at10[dt.date()] = o

    today = datetime.now(TW).date()
    m, y = today.month - MONTHS, today.year
    if m <= 0:
        m, y = m + 12, y - 1
    start = date(y, m, min(today.day, 28))

    shares = cost = cash = 0.0
    realized = fees_total = 0.0
    prev_equity = 0.0
    max_cost = 0.0
    days, trades = [], []
    for i, (d, close, *_rest) in enumerate(bars):
        if d < start or d not in at10:
            continue
        hist = bars[:i]  # up to the previous close
        tools, bulls, advice, _ = analyse([b[1] for b in hist], [b[2] for b in hist],
                                          [b[3] for b in hist], [b[4] for b in hist])
        price = at10[d]
        action, day_fee = "—", 0
        if advice == "買入":
            day_fee = fee(price * LOT, sell=False)
            cash -= price * LOT + day_fee
            cost += price * LOT
            shares += LOT
            action = "買進 1 張"
        elif advice == "賣出" and shares >= LOT:
            avg = cost / shares
            day_fee = fee(price * LOT, sell=True)
            cash += price * LOT - day_fee
            realized += (price - avg) * LOT
            cost -= avg * LOT
            shares -= LOT
            action = "賣出 1 張"
        elif advice == "賣出":
            action = "無持股，不動作"
        fees_total += day_fee
        max_cost = max(max_cost, cost)
        equity = cash + shares * close
        if action.startswith(("買進", "賣出")):
            trades.append({"date": d.isoformat(), "action": action, "price": price, "fee": day_fee})
        days.append({
            "date": d.isoformat(), "bulls": bulls, "signal": advice, "action": action,
            "price10": price, "close": close, "lots": int(shares // LOT),
            "fee": day_fee,
            "pnl": round(equity - prev_equity),
            "cum": round(equity),
            "lights": [t["bull"] for t in tools],
        })
        prev_equity = equity

    last_close = days[-1]["close"]
    unrealized = shares * last_close - cost
    first = days[0]
    bh_shares_cost = first["price10"] * LOT
    bh = (last_close - first["price10"]) * LOT - fee(bh_shares_cost, False) - fee(last_close * LOT, True)
    out = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "symbol": SYMBOL, "name": NAME, "start": first["date"], "end": days[-1]["date"],
        "rules": {"lot": LOT, "fee_rate": FEE_RATE, "fee_min": FEE_MIN, "tax_rate": TAX_RATE},
        "summary": {
            "total": round(prev_equity),
            "realized": round(realized),
            "unrealized": round(unrealized),
            "fees": round(fees_total),
            "lots_held": int(shares // LOT),
            "avg_cost": round(cost / shares, 2) if shares else None,
            "last_close": last_close,
            "buys": sum(t["action"].startswith("買進") for t in trades),
            "sells": sum(t["action"].startswith("賣出") for t in trades),
            "max_cost": round(max_cost),
            "trading_days": len(days),
            "signal_counts": {s: sum(x["signal"] == s for x in days) for s in ("買入", "持有", "賣出")},
            "buy_and_hold": round(bh),
        },
        "days": days,
        "trades": trades,
    }
    DATA.mkdir(exist_ok=True)
    (DATA / "backtest_2454.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), "utf-8")
    s = out["summary"]
    print(f"{out['start']} ~ {out['end']}  {s['trading_days']} days  signals {s['signal_counts']}")
    print(f"buys {s['buys']} sells {s['sells']} held {s['lots_held']}  total {s['total']:+,} "
          f"(realized {s['realized']:+,}, unrealized {s['unrealized']:+,}, fees {s['fees']:,})  "
          f"buy&hold {s['buy_and_hold']:+,}")


if __name__ == "__main__":
    main()
