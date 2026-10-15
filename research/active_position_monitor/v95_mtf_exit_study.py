"""Offline M5/M15/H1 exit confirmation research, no live trading side effects.

Predeclared filters (not tuned on outcomes):
M15: last completed close > preceding completed close and bullish body.
H1: last completed close > preceding completed close and bullish body.
Only completed candles at signal time are available; no forward leakage.
"""
import argparse
import json
import sqlite3
import math
from collections import Counter
from pathlib import Path
from datetime import datetime, timezone
from research.active_position_monitor.v95_m5_history_scan import minute_epoch
from research.active_position_monitor.v95_m5_exit_challenger import assess

HORIZONS=(5,15,30,60)

def load(db):
    con=sqlite3.connect(Path(db).resolve().as_uri()+"?mode=ro",uri=True)
    try:
        rows=con.execute('SELECT minute, "open", high, low, "close" FROM candles').fetchall()
    finally:
        con.close()
    m1={}
    for t,o,h,l,c in rows:
        t=minute_epoch(t)
        b=dict(o=float(o),h=float(h),l=float(l),c=float(c))
        if t in m1 or not all(math.isfinite(v) for v in b.values()) or not b["l"]<=min(b["o"],b["c"])<=max(b["o"],b["c"])<=b["h"]:
            raise ValueError("Duplicate or invalid M1 candle")
        m1[t]=b
    return m1

def aggregate(m1, width):
    out={}
    for bucket in sorted({t//width for t in m1}):
        bars=[m1.get(bucket*width+i) for i in range(width)]
        if any(x is None for x in bars):
            continue
        out[bucket]=dict(o=bars[0]["o"],h=max(x["h"] for x in bars),
                         l=min(x["l"] for x in bars),c=bars[-1]["c"])
    return out

def bullish_confirmation(bars, signal_close_minute, width):
    # Signal at minute t means M5 bar [t-5,t) is completed.
    # Last completed higher-timeframe bar ends at floor(t/width)*width.
    last_bucket=signal_close_minute//width-1
    last=bars.get(last_bucket)
    prev=bars.get(last_bucket-1)
    if last is None or prev is None:
        return None
    return last["c"]>last["o"] and last["c"]>prev["c"]

def metrics(values):
    if not values:
        return dict(n=0,mean_bps=None,rise_fraction=None)
    return dict(n=len(values),mean_bps=round(sum(values)/len(values),3),
                rise_fraction=round(sum(x>0 for x in values)/len(values),4))

def study(m1):
    m5=aggregate(m1,5)
    m15=aggregate(m1,15)
    h1=aggregate(m1,60)
    observations=[]
    for b in sorted(m5):
        if any(x not in m5 for x in range(b-15,b+1)):
            continue
        a=assess([m5[x] for x in range(b-15,b+1)])
        if a.action!="EXIT_CANDIDATE":
            continue
        t=(b+1)*5
        m15_ok=bullish_confirmation(m15,t,15)
        h1_ok=bullish_confirmation(h1,t,60)
        forward={}
        for h in HORIZONS:
            n=h//5
            forward[h]=((m5[b+n]["c"]-m5[b]["c"])/m5[b]["c"]*10000
                        if all(x in m5 for x in range(b+1,b+n+1)) else None)
        observations.append(dict(bucket=b,m15=m15_ok,h1=h1_ok,forward=forward))
    # A consecutive run of M5 candidates is one episode; use its FIRST
    # candidate only for an additional, less-dependent descriptive sample.
    episodes=[]
    for row in observations:
        if not episodes or row["bucket"]!=episodes[-1][-1]["bucket"]+1:
            episodes.append([row])
        else:
            episodes[-1].append(row)
    def summarize(rows):
        groups={
            "m5_only":rows,
            "m5_m15":[r for r in rows if r["m15"] is True],
            "m5_m15_h1":[r for r in rows if r["m15"] is True and r["h1"] is True],
        }
        return {name:dict(count=len(group),forward_bps={
            str(h):metrics([r["forward"][h] for r in group if r["forward"][h] is not None])
            for h in HORIZONS}) for name,group in groups.items()}
    return {
        "mode":"OFFLINE_MTF_RESEARCH_ONLY",
        "complete_m5":len(m5),"complete_m15":len(m15),"complete_h1":len(h1),
        "m5_candidate_windows":len(observations),
        "consecutive_candidate_episodes":len(episodes),
        "confirmation_availability":{
            "m15_unavailable":sum(r["m15"] is None for r in observations),
            "h1_unavailable":sum(r["h1"] is None for r in observations),
        },
        "all_candidate_windows":summarize(observations),
        "first_candidate_per_episode":summarize([e[0] for e in episodes]),
        "limitations":[
            "M15/H1 confirmation is a predefined simple bullish close rule, not an optimized exit rule",
            "Signals within and across episodes can remain statistically dependent",
            "First-of-episode filters do not allow a later confirmation in the same episode",
            "Forward returns are close-to-close, not executable trades or realized R",
            "No spreads, slippage, commissions, or original V9.5 exit replay",
            "Higher-timeframe history may be unavailable near dataset start or gaps",
            "Small sample and overlapping forward horizons preclude profitability claims"
        ],
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--db",required=True)
    p.add_argument("--output",required=True)
    args=p.parse_args()
    report=study(load(args.db))
    dst=Path(args.output)
    if dst.exists() or dst.is_symlink():
        raise FileExistsError("Use a new output path")
    with dst.open("x",encoding="utf-8") as f:
        json.dump(report,f,indent=2,allow_nan=False)
        f.write("\n")
    print(json.dumps({
        "m5_candidate_windows":report["m5_candidate_windows"],
        "episodes":report["consecutive_candidate_episodes"],
        "all_counts":{k:v["count"] for k,v in report["all_candidate_windows"].items()},
        "episode_counts":{k:v["count"] for k,v in report["first_candidate_per_episode"].items()},
        "report_written":True
    }))

if __name__=="__main__":
    main()
