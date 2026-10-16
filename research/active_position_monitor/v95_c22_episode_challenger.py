"""Research-only, causal C2.2 challenger compared with C2 Raw and C2.1.

Candidate is the original HybridC discretionary action. C2.2 preserves that
warning immediately, but only issues EXIT_CANDIDATE after independent completed
M1 bullish evidence. No trading, orders, or actual position state.
"""
import argparse
import json
from pathlib import Path
from statistics import median
from research.active_position_monitor.v95_c21_episode_comparison import load_m1, load_m5, episodes
from research.active_position_monitor.v95_hybrid_c_research import HybridC, Config
from research.active_position_monitor.v95_hybrid_c21 import C21Confirm
from research.active_position_monitor.v95_m5_history_scan import minute_epoch

EXIT={"ADAPTIVE_EXIT","EARLY_PROFIT_EXIT"}

def atr(bars, period=14):
    if len(bars)<period+1: return None
    trs=[]
    for i in range(len(bars)-period,len(bars)):
        b,p=bars[i],bars[i-1]
        trs.append(max(b["h"]-b["l"],abs(b["h"]-p["c"]),abs(b["l"]-p["c"])))
    return sum(trs)/period

class C22:
    def __init__(self):
        self.candidate=None
        self.reference=None
    def observe(self,t,b,prior,prior5,atr14,raw):
        if raw:
            self.candidate=t
            self.reference=b["c"]
        if self.candidate is None: return "HOLD"
        age=t-self.candidate
        if age>5:
            self.candidate=self.reference=None
            return "HOLD"
        bullish=(prior is not None and b["c"]>b["o"] and b["c"]>prior["c"])
        breakout=(len(prior5)==5 and b["c"]>max(x["h"] for x in prior5))
        if age>0 and bullish and breakout:
            self.candidate=self.reference=None
            return "EXIT_CANDIDATE"
        # Exploratory urgent path; no intrabar lookahead and no fitted dollar thresholds.
        if age>0 and atr14 and atr14>0 and bullish and b["c"]-self.reference>=1.5*atr14:
            self.candidate=self.reference=None
            return "EXIT_CANDIDATE"
        if age>0 and b["c"]<b["o"] and prior is not None and b["c"]<prior["l"]:
            self.candidate=self.reference=None
        return "WARNING" if raw or self.candidate is not None else "HOLD"

def observe(m1,bucket,lookahead):
    signal=bucket*5+4
    begin=signal-99
    end=signal+lookahead
    if any(t not in m1 for t in range(begin,end+1)):
        return {"status":"SKIP_MISSING_M1"}
    model=HybridC(cfg=Config(power_mode="raw"))
    prices=[m1[t]["c"] for t in range(begin,end+1)]
    model.open_initial(m1[begin]["c"],max(prices)+10000,min(prices)-10000)
    gate21=C21Confirm()
    gate22=C22()
    history=[]
    prev=None
    raw_times=[]
    c21_times=[]
    c22_times=[]
    warning_times=[]
    for t in range(begin,end+1):
        b=m1[t]
        prior5=history[-5:]
        decision=model.on_completed_m1(b)
        action=decision["action"]
        israw=action in EXIT
        state21=gate21.observe(t,b,prev,action,prior5) if t>=signal else None
        state22=gate22.observe(t,b,prev,prior5,atr(history+[b]),israw) if t>=signal else None
        if t>=signal:
            if israw: raw_times.append(t-signal)
            if state21=="CONFIRM": c21_times.append(t-signal)
            if state22=="EXIT_CANDIDATE": c22_times.append(t-signal)
            if state22=="WARNING": warning_times.append(t-signal)
        history.append(b)
        prev=b
    return {"status":"EVALUATED","raw_first_min":min(raw_times) if raw_times else None,
            "c21_first_min":min(c21_times) if c21_times else None,
            "c22_first_min":min(c22_times) if c22_times else None,
            "c22_warning_first_min":min(warning_times) if warning_times else None}

def analyze(db,lookahead=15):
    m5,_=load_m5(db)
    m1=load_m1(db)
    rows=[]
    for i,group in enumerate(episodes(m5),1):
        r=observe(m1,group[0],lookahead)
        r["episode"]=i
        rows.append(r)
    valid=[r for r in rows if r["status"]=="EVALUATED"]
    summary={"episodes":len(rows),"evaluated":len(valid),"raw_detected":sum(r["raw_first_min"] is not None for r in valid),
             "c21_detected":sum(r["c21_first_min"] is not None for r in valid),
             "c22_detected":sum(r["c22_first_min"] is not None for r in valid),
             "c22_warned":sum(r["c22_warning_first_min"] is not None for r in valid)}
    delays=[r["c22_first_min"]-r["raw_first_min"] for r in valid if r["c22_first_min"] is not None and r["raw_first_min"] is not None]
    summary["c22_median_delay_vs_raw"]=median(delays) if delays else None
    return {"study":"C2.2 causal M1 signal-only challenger","summary":summary,"episodes":rows,
            "limitations":["M5 episodes are selected candidates, not independently labeled reversals",
                           "Synthetic distant-stop SELL, no actual trade fills or returns",
                           "Exploratory rules are not validated; no live or paper integration",
                           "All decisions use completed current and earlier M1 candles"]}
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--db",required=True)
    p.add_argument("--output",required=True)
    p.add_argument("--lookahead",type=int,default=15)
    a=p.parse_args()
    if not 1<=a.lookahead<=60: p.error("lookahead must be 1..60")
    report=analyze(a.db,a.lookahead)
    with Path(a.output).open("x") as f: json.dump(report,f,indent=2)
    print("SUMMARY",json.dumps(report["summary"]))
    for row in report["episodes"]: print("EPISODE",json.dumps(row))
if __name__=="__main__": main()
