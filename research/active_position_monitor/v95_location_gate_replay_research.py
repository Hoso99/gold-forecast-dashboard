"""Research-only M1 candle replay: V9.5 location-gate counterfactual.

Reads an existing SQLite cache, writes JSON summary; no orders, alerts, or
changes to monitor state. Use only completed candles and prefix-only history.
"""
import argparse
import datetime as dt
import json
import sqlite3
from pathlib import Path

from v95_core_sell_detectors import detect as detect_core_sell
from v95_sell_gate_attribution_research import diagnose_sell_gate


def aggregate(rows, minutes):
    groups = {}
    for row in rows:
        t = row["t"]
        start = t.replace(hour=0, minute=0, second=0, microsecond=0)
        start += dt.timedelta(minutes=((t.hour * 60 + t.minute) // minutes) * minutes)
        groups.setdefault(start, []).append(row)
    result = []
    for start, chunk in sorted(groups.items()):
        expected = [start + dt.timedelta(minutes=i) for i in range(minutes)]
        if len(chunk) != minutes or [x["t"] for x in chunk] != expected:
            continue
        result.append({"t": start, "o": chunk[0]["o"],
                       "h": max(x["h"] for x in chunk),
                       "l": min(x["l"] for x in chunk), "c": chunk[-1]["c"]})
    return result


def atr(bars, n=14):
    tr = [max(b["h"] - b["l"], abs(b["h"] - a["c"]),
              abs(b["l"] - a["c"])) for a, b in zip(bars, bars[1:])]
    return sum(tr[-n:]) / n if len(tr) >= n else None


def load_rows(db):
    with sqlite3.connect(f"file:{Path(db).resolve()}?mode=ro", uri=True) as con:
        raw = con.execute(
            "SELECT minute_utc, open, high, low, close FROM twelve_m1 ORDER BY minute_utc"
        ).fetchall()
    rows = []
    for stamp, o, h, l, c in raw:
        t = dt.datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=dt.timezone.utc)
        rows.append({"t": t.astimezone(dt.timezone.utc),
                     "o": float(o), "h": float(h), "l": float(l), "c": float(c)})
    return rows


def replay(rows, start, end):
    results = []
    for i, latest in enumerate(rows):
        if latest["t"] < start or latest["t"] > end:
            continue
        # Prefix-only data prevents looking into future bars.
        history = rows[:i + 1]
        m5, m15, h1 = (aggregate(history, x) for x in (5, 15, 60))
        if len(m5) < 5 or len(m15) < 17 or len(h1) < 2:
            continue
        a = atr(m15)
        if a is None or a <= 0:
            continue
        tail = history[-10:]
        sell = sum(max(x["o"] - x["c"], 0) for x in tail)
        buy = sum(max(x["c"] - x["o"], 0) for x in tail)
        power = 100 * sell / (buy + sell) if buy + sell else 50
        detectors = detect_core_sell(m15, a, power)
        structural = detectors.get("structural_sell", False)
        h1_bearish = h1[-1]["c"] < h1[-2]["c"]
        m5_bearish = (m5[-1]["c"] < m5[-2]["c"] and
                      sum(m5[-j]["c"] < m5[-j - 1]["c"] for j in range(1, 5)) >= 3)
        support = min(x["l"] for x in m15[-17:-5])
        price = latest["c"]
        location = (price - support) > a
        item = diagnose_sell_gate(
            structural_sell=structural, h1_bearish=h1_bearish,
            m5_bearish=m5_bearish, support_buffer=location,
            sell_power=power, price=price, older_support=support, m15_atr=a)
        item["timestamp_utc"] = latest["t"].isoformat()
        results.append(item)
    return results


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--db", required=True)
    p.add_argument("--start", required=True, help="ISO UTC, e.g. 2026-10-19T12:00:00+00:00")
    p.add_argument("--end", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()
    start = dt.datetime.fromisoformat(args.start.replace("Z", "+00:00"))
    end = dt.datetime.fromisoformat(args.end.replace("Z", "+00:00"))
    if start.tzinfo is None or end.tzinfo is None:
        p.error("start/end must include UTC offset")
    results = replay(load_rows(args.db), start, end)
    summary = {
        "evaluated_completed_m1_prefixes": len(results),
        "original_technical_sell_count": sum(x["decision"] == "QUALIFIED_TECHNICAL_SELL" for x in results),
        "location_only_veto_count": sum(x["location_only_veto"] for x in results),
        "counterfactual_without_location_count": sum(x["counterfactual_without_location"] for x in results),
        "caveat": "Technical gate research only; excludes risk/news/position/SL-TP outcomes and session-aware cache acceptance. Counts are candle decisions, not independent trades.",
        "decisions": results,
    }
    Path(args.output).write_text(json.dumps(summary, indent=2))
    print(json.dumps({k: v for k, v in summary.items() if k != "decisions"}))


if __name__ == "__main__":
    main()
