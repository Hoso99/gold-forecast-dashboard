"""Research-only C2.3 Timer post-confirmation price paths.

First confirmation only per M5 episode. Fixed 5/10/15/30 completed M1
horizons after confirmation, with strictly contiguous M1 data.
No real trade, execution, or P&L claims.
"""
import argparse
import json
from pathlib import Path
from statistics import median
from research.active_position_monitor.v95_c21_episode_comparison import load_m1,load_m5,episodes
from research.active_position_monitor.v95_c23_ablation import replay

HORIZONS=(5,10,15,30)

def path(m1,t,h):
    if any(k not in m1 for k in range(t,t+h+1)):
        return {"status":"SKIP_MISSING_M1"}
    reference=m1[t]["c"]
    bars=[m1[k] for k in range(t+1,t+h+1)]
    final=m1[t+h]["c"]-reference
    max_up=max(b["h"] for b in bars)-reference
    max_down=reference-min(b["l"] for b in bars)
    return {"status":"EVALUATED","reference_close":round(reference,5),
            "final_change":round(final,5),
            "max_adverse_rise_for_sell":round(max_up,5),
            "max_favorable_drop_for_sell":round(max_down,5),
            "sell_continuation":final<0,
            "sell_adverse":final>0,
            "flat":final==0}

def analyze(db):
    m5,_=load_m5(db)
    m1=load_m1(db)
    rows=[]
    for i,g in enumerate(episodes(m5),1):
        bucket=g[0]
        signal=bucket*5+4
        # Fixed 34-minute candidate search, matching prior comparison.
        result=replay(m1,bucket,34,"timer")
        first=result.get("exit_first_min") if result["status"]=="EVALUATED" else None
        horizons={}
        if first is not None:
            t=signal+first
            horizons={str(h):path(m1,t,h) for h in HORIZONS}
        rows.append({"episode":i,"first_confirmation_offset":first,
                     "confirmation_status":result["status"],
                     "horizons":horizons})
    summary={"episodes":len(rows),"confirmed_episodes":sum(r["first_confirmation_offset"] is not None for r in rows),
             "unconfirmed_episodes":sum(r["first_confirmation_offset"] is None for r in rows),
             "outcomes":{}}
    for h in HORIZONS:
        evaluated=[r["horizons"][str(h)] for r in rows
                   if str(h) in r["horizons"] and r["horizons"][str(h)]["status"]=="EVALUATED"]
        missing=sum(str(h) in r["horizons"] and r["horizons"][str(h)]["status"]!="EVALUATED" for r in rows)
        summary["outcomes"][str(h)]={
            "evaluated":len(evaluated),"missing":missing,
            "sell_continuation":sum(r["sell_continuation"] for r in evaluated),
            "sell_adverse":sum(r["sell_adverse"] for r in evaluated),
            "flat":sum(r["flat"] for r in evaluated),
            "median_final_change":round(median(r["final_change"] for r in evaluated),5) if evaluated else None,
            "median_max_adverse_rise":round(median(r["max_adverse_rise_for_sell"] for r in evaluated),5) if evaluated else None,
            "median_max_favorable_drop":round(median(r["max_favorable_drop_for_sell"] for r in evaluated),5) if evaluated else None}
    return {"study":"C2.3 Timer first-confirmation fixed-horizon M1 price outcome",
            "summary":summary,"episodes":rows,
            "limitations":["Historical episodes are M5-selected, not independent reversal ground truth",
                           "Reference price is completed signal M1 close, not executable fill",
                           "Price movement after confirmation does not measure realized trading returns",
                           "No fees, spreads, slippage, SL/TP touches or intrabar ordering",
                           "Episodes may overlap; observations not independent",
                           "First confirmation only; no live or paper monitor changes"]}
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db",required=True)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    report=analyze(a.db)
    with Path(a.output).open("x",encoding="utf-8") as f:
        json.dump(report,f,indent=2)
        f.write("\n")
    print("SUMMARY",json.dumps(report["summary"]))
    for r in report["episodes"]:
        print("EPISODE",r["episode"],json.dumps({"first":r["first_confirmation_offset"],
             "outcomes":{k:{"status":v["status"],"final":v.get("final_change"),
                              "adverse":v.get("max_adverse_rise_for_sell"),
                              "favorable":v.get("max_favorable_drop_for_sell")}
                         for k,v in r["horizons"].items()}}))
if __name__=="__main__":main()
