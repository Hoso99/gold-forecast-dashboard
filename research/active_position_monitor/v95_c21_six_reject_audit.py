"""Read-only C2 Raw vs C2.1 rejected-episode price-path diagnostic.

Uses same Biquote M1/M5 episode selection and hypothetical wide-stop SELL as
v95_c21_episode_comparison. This is NOT a trade replay or a fill simulation.
Completed-bar decisions only; forward price outcomes are diagnostic labels.
"""
import argparse
import json
from pathlib import Path
from datetime import datetime,timezone
from research.active_position_monitor.v95_c21_episode_comparison import load_m1,episodes,EXIT
from research.active_position_monitor.v95_m5_reversal_study import load_m5
from research.active_position_monitor.v95_hybrid_c_research import HybridC,Config
from research.active_position_monitor.v95_hybrid_c21 import C21Confirm

HORIZONS=(5,10,15,30)
def study(m1,group):
    anchor=group[0]*5+4
    begin=anchor-99
    end=anchor+45
    if any(t not in m1 for t in range(begin,end+1)):
        return {"status":"SKIP_GAP"}
    prices=[m1[t]["c"] for t in range(begin,anchor+1)]
    model=HybridC(cfg=Config(power_mode="raw"))
    model.open_initial(m1[begin]["c"],max(prices)+10000,min(prices)-10000)
    gate=C21Confirm()
    history=[];prior=None;raw=None;c21=None
    for t in range(begin,anchor+16):
        b=m1[t];history.append(b)
        action=model.on_completed_m1(b)["action"]
        if t>=anchor and action in EXIT and raw is None:raw=t
        if t>=anchor and gate.observe(t,b,prior,action,history[-6:-1])=="CONFIRM" and c21 is None:c21=t
        prior=b
    result={"status":"EVALUATED","anchor_utc":datetime.fromtimestamp((anchor+1)*60,timezone.utc).isoformat(),
            "raw_offset":None if raw is None else raw-anchor,
            "c21_offset":None if c21 is None else c21-anchor,
            "classification":("RAW_REJECTED_BY_C21" if raw is not None and c21 is None
                              else "BOTH" if raw is not None and c21 is not None
                              else "NEITHER" if raw is None and c21 is None else "C21_ONLY")}
    if raw is not None:
        ref=m1[raw]["c"]
        result["raw_reference_close"]=ref
        result["future"]={}
        for h in HORIZONS:
            seq=[m1[t] for t in range(raw+1,raw+h+1)]
            close=seq[-1]["c"]
            result["future"][str(h)]={
                "price_change":round(close-ref,5),
                "sell_continuation":close<ref,
                "max_adverse_rise":round(max(b["h"] for b in seq)-ref,5),
                "max_favorable_drop":round(ref-min(b["l"] for b in seq),5)}
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--db",required=True)
    p.add_argument("--output",required=True)
    args=p.parse_args()
    dest=Path(args.output)
    if dest.exists():p.error("Output already exists; choose new path")
    m5,_=load_m5(args.db)
    m1=load_m1(args.db)
    groups=episodes(m5)
    records=[]
    for idx,g in enumerate(groups,1):
        row=study(m1,g);row["episode"]=idx;records.append(row)
    rejected=[r for r in records if r.get("classification")=="RAW_REJECTED_BY_C21"]
    both=[r for r in records if r.get("classification")=="BOTH"]
    def aggregate(items):
        out={"count":len(items)}
        for h in HORIZONS:
            key=str(h)
            paths=[r["future"][key] for r in items if "future" in r]
            out[key]={"n":len(paths),
                      "sell_continuation":sum(p["sell_continuation"] for p in paths),
                      "sell_adverse":sum(p["price_change"]>0 for p in paths),
                      "flat":sum(p["price_change"]==0 for p in paths)}
        return out
    report={"study":"C2 Raw rejected by C2.1: signal-close future price paths",
            "episodes_total":len(groups),
            "raw_rejected":aggregate(rejected),"both_detected":aggregate(both),
            "episodes":records,
            "limitations":["M5-selected episodes are not independent reversal labels",
                           "Synthetic wide-stop SELL, not actual positions or exit fills",
                           "C2.1 confirmation window matches 15-minute prior diagnostic",
                           "Price at completed M1 signal close is not executable; next-bar fills not modeled",
                           "No spread, slippage, fees, protective SL/TP, or position sizing",
                           "Future prices used only for retrospective outcome labels",
                           "Episodes may overlap; no independent win rate or strategy superiority claim",
                           "No changes to V9.4 LIVE or V9.5 PAPER"]}
    with dest.open("x",encoding="utf-8") as f:
        json.dump(report,f,indent=2);f.write("\n")
    print(json.dumps({k:v for k,v in report.items() if k!="episodes"},indent=2))
    for r in records:
        if r.get("classification")=="RAW_REJECTED_BY_C21":
            print("REJECTED_EPISODE",json.dumps(r,sort_keys=True))
if __name__=="__main__":main()
