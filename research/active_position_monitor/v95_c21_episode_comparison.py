"""Research-only episode-aligned M5 vs M1 C2/C2.1 diagnostic.

No trades, fills, SL/TP performance, or claimed reversal ground truth.
M5 candidates define episodes; M1 detectors are evaluated independently
with an explicitly hypothetical distant-stop SELL to activate exit logic.
"""
import argparse
import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from research.active_position_monitor.v95_m5_reversal_study import load_m5
from research.active_position_monitor.v95_m5_exit_challenger import assess
from research.active_position_monitor.v95_m5_history_scan import minute_epoch
from research.active_position_monitor.v95_hybrid_c_research import HybridC,Config
from research.active_position_monitor.v95_hybrid_c21 import C21Confirm

EXIT={"ADAPTIVE_EXIT","EARLY_PROFIT_EXIT"}

def load_m1(path):
    with sqlite3.connect(Path(path).resolve().as_uri()+"?mode=ro",uri=True) as con:
        rows=con.execute('SELECT minute,"open",high,low,"close" FROM candles ORDER BY minute').fetchall()
    result={}
    for t,o,h,l,c in rows:
        m=minute_epoch(t)
        if m in result: raise ValueError("Duplicate M1")
        b={"o":float(o),"h":float(h),"l":float(l),"c":float(c)}
        if not b["l"]<=min(b["o"],b["c"])<=max(b["o"],b["c"])<=b["h"]:
            raise ValueError("Invalid OHLC")
        result[m]=b
    return result

def episodes(m5):
    candidates=[]
    for bucket in sorted(m5):
        if all(t in m5 for t in range(bucket-15,bucket+1)):
            if assess([m5[t] for t in range(bucket-15,bucket+1)]).action=="EXIT_CANDIDATE":
                candidates.append(bucket)
    grouped=[]
    for bucket in candidates:
        if not grouped or bucket!=grouped[-1][-1]+1:
            grouped.append([bucket])
        else:
            grouped[-1].append(bucket)
    return grouped

def observe(m1,first_bucket,lookahead=15):
    # M5 bucket covers [5*b,5*b+4]; signal is at end of final M1.
    signal_minute=first_bucket*5+4
    begin=signal_minute-99
    end=signal_minute+lookahead
    if any(m not in m1 for m in range(begin,end+1)):
        return {"status":"SKIP_MISSING_M1"}
    model=HybridC(cfg=Config(power_mode="raw"))
    # Distant protective levels are synthetic, not a historical SELL.
    # Avoid actual SL/TP touches; only compare discretionary exit timing.
    prices=[m1[m]["c"] for m in range(begin,end+1)]
    low=min(prices)-10000
    high=max(prices)+10000
    model.open_initial(m1[begin]["c"],high,low)
    gate=C21Confirm()
    prev=None
    history=[]
    raw=[]
    c21=[]
    for minute in range(begin,end+1):
        bar=m1[minute]
        history.append(bar)
        decision=model.on_completed_m1(bar)
        action=decision["action"]
        if minute>=signal_minute and action in EXIT:
            raw.append(minute-signal_minute)
        if minute>=signal_minute:
            state=gate.observe(minute,bar,prev,action,history[-6:-1])
            if state=="CONFIRM":
                c21.append(minute-signal_minute)
        prev=bar
    return {"status":"EVALUATED","raw_first_min":min(raw) if raw else None,
            "c21_first_min":min(c21) if c21 else None,
            "raw_exit_actions":len(raw),"c21_confirmations":len(c21)}

def analyze(db,lookahead=15):
    m5,n=load_m5(db)
    m1=load_m1(db)
    groups=episodes(m5)
    results=[]
    for i,group in enumerate(groups,1):
        r=observe(m1,group[0],lookahead)
        r.update({"episode":i,"m5_windows":len(group),
                  "first_m5_signal_utc":datetime.fromtimestamp(
                      (group[0]*5+5)*60,timezone.utc).isoformat()})
        results.append(r)
    evaluated=[r for r in results if r["status"]=="EVALUATED"]
    raw=[r for r in evaluated if r["raw_first_min"] is not None]
    c21=[r for r in evaluated if r["c21_first_min"] is not None]
    return {"study":"M5 episode-aligned M1 discretionary signal diagnostic",
            "m1_candles":n,"m5_episodes":len(groups),
            "m5_exit_candidate_windows":sum(map(len,groups)),
            "evaluated":len(evaluated),"skipped_missing_m1":len(groups)-len(evaluated),
            "raw_detected":len(raw),"c21_detected":len(c21),
            "both_detected":sum(r["raw_first_min"] is not None and
                                r["c21_first_min"] is not None for r in evaluated),
            "lookahead_minutes":lookahead,"episodes":results,
            "limitations":[
                "M5 candidate episodes are NOT verified bullish reversals",
                "Hypothetical wide-stop SELL activates M1 exit logic; not actual trades",
                "C2 Raw detection is M1 discretionary action, not C2 filled exit",
                "C2.1 detection is post-candidate bullish followthrough, not a fill",
                "Signals overlap; no independent win-rate or profitability claim",
                "M1 history must be contiguous; incomplete episodes are skipped",
                "No fees, spread, slippage, event risk, or verified open positions"]}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db",required=True)
    p.add_argument("--output",required=True)
    p.add_argument("--lookahead",type=int,default=15)
    a=p.parse_args()
    if a.lookahead<1 or a.lookahead>60: p.error("lookahead must be 1..60")
    report=analyze(a.db,a.lookahead)
    path=Path(a.output)
    with path.open("x") as f:
        json.dump(report,f,indent=2)
        f.write("\n")
    print(json.dumps({k:v for k,v in report.items() if k not in ("episodes","limitations")},indent=2))
    for r in report["episodes"]: print("EPISODE",json.dumps(r))

if __name__=="__main__": main()
