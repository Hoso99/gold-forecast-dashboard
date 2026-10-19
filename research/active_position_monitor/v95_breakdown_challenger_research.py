"""Research-only XAU/USD breakdown SELL challenger. Never places orders or alters monitor state.
Uses complete M1->M5/M15/H1 bars, next-M1-open fills, conservative SL-first replay.
Results are hypothetical, exclude spread/slippage/news and cannot establish profitability.
"""
import argparse
import datetime as dt
import json
from pathlib import Path
from v95_location_gate_replay_research import load_rows, aggregate, atr

UTC = dt.timezone.utc

def replay(rows, start, end, hold_minutes=240):
    events = []
    last_episode_end = None
    by_time = {r["t"]: i for i, r in enumerate(rows)}
    for i, row in enumerate(rows[:-1]):
        t = row["t"]
        if t < start or t > end or t.minute % 5 != 4:
            continue
        if last_episode_end is not None and t <= last_episode_end:
            continue
        history = rows[:i+1]
        m5, m15, h1 = (aggregate(history, n) for n in (5, 15, 60))
        if len(m5) < 20 or len(m15) < 20 or len(h1) < 2:
            continue
        a5, a15 = atr(m5), atr(m15)
        if a5 is None or a15 is None or a5 <= 0 or a15 <= 0:
            continue
        # Latest M5 is complete at t+1 minute; M15 and H1 bars are complete too.
        prev_support = min(x["l"] for x in m15[-5:-1])
        price = m5[-1]["c"]
        breakdown = price < prev_support - 0.15*a15
        bearish = m5[-1]["c"] < m5[-1]["o"] and m5[-1]["c"] < m5[-2]["c"]
        h1_down = h1[-1]["c"] < h1[-2]["c"]
        tail = history[-10:]
        down = sum(max(x["o"]-x["c"],0) for x in tail)
        up = sum(max(x["c"]-x["o"],0) for x in tail)
        power = 100*down/(down+up) if down+up else 50
        if not (breakdown and bearish and h1_down and power >= 60):
            continue
        # Entry at NEXT M1 open; reject gaps and nonconsecutive candles.
        nxt = rows[i+1]
        if nxt["t"] != t + dt.timedelta(minutes=1):
            continue
        entry = nxt["o"]
        # Fixed ex-ante rule: highest high of previous 3 completed M5 bars + 0.5 ATR.
        sl = max(x["h"] for x in m5[-3:]) + 0.5*a5
        risk = sl-entry
        if not (0 < risk <= 2*a5):
            continue
        tp = entry-2*risk
        # Require room below entry: previous 20 completed M15 lows excluding recent 4
        older_lows = [x["l"] for x in m15[-20:-4]]
        if not older_lows or min(older_lows) > tp:
            continue
        outcome, exit_at, exit_price = "UNRESOLVED", None, None
        last_seen = None
        observed = 0
        for future in rows[i+1:]:
            if future["t"] >= nxt["t"] + dt.timedelta(minutes=hold_minutes):
                break
            if last_seen is not None and future["t"] != last_seen + dt.timedelta(minutes=1):
                outcome = "DATA_GAP"
                break
            last_seen = future["t"]
            observed += 1
            # Conservative when both barriers touched in the same M1 candle.
            if future["h"] >= sl:
                outcome, exit_at, exit_price = "STOP", future["t"], sl
                break
            if future["l"] <= tp:
                outcome, exit_at, exit_price = "TARGET", future["t"], tp
                break
        if outcome == "UNRESOLVED" and observed < hold_minutes:
            outcome = "INCOMPLETE_HORIZON"
        events.append(dict(signal_utc=t.isoformat(), entry_utc=nxt["t"].isoformat(),
            entry=round(entry,5), sl=round(sl,5), tp=round(tp,5),
            risk_per_oz=round(risk,5), sell_proxy=round(power,2),
            atr5=round(a5,5), atr15=round(a15,5),
            outcome=outcome, exit_utc=exit_at.isoformat() if exit_at else None,
            observed_m1=observed))
        last_episode_end = t + dt.timedelta(minutes=hold_minutes)
    return events

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--db",required=True)
    p.add_argument("--start",required=True)
    p.add_argument("--end",required=True)
    p.add_argument("--output",required=True)
    args=p.parse_args()
    start=dt.datetime.fromisoformat(args.start.replace("Z","+00:00"))
    end=dt.datetime.fromisoformat(args.end.replace("Z","+00:00"))
    if start.tzinfo is None or end.tzinfo is None or end<start:
        p.error("Use offset-aware timestamps with end >= start")
    rows=load_rows(args.db)
    events=replay(rows,start.astimezone(UTC),end.astimezone(UTC))
    counts={k:sum(e["outcome"]==k for e in events) for k in
            ("TARGET","STOP","UNRESOLVED","DATA_GAP","INCOMPLETE_HORIZON")}
    summary=dict(mode="RESEARCH_ONLY",episodes=len(events),outcomes=counts,
        note="Hypothetical 2R, no spread/slippage/news/position management; not a live or paper signal.",
        events=events)
    Path(args.output).write_text(json.dumps(summary,indent=2))
    print(json.dumps({k:v for k,v in summary.items() if k!="events"}))
if __name__=="__main__":
    main()
