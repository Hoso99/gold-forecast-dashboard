"""Read-only 34-completed-M1-candle C2.3 research comparison."""
import argparse
import json
from pathlib import Path
from research.active_position_monitor.v95_c21_episode_comparison import load_m1,load_m5,episodes
from research.active_position_monitor.v95_c23_ablation import replay

def analyze(db,horizon=34):
    m5,_=load_m5(db)
    m1=load_m1(db)
    rows=[]
    for i,g in enumerate(episodes(m5),1):
        bucket=g[0]
        signal=bucket*5+4
        row={"episode":i,"variants":{}}
        for name in ("timer","veto","urgent"):
            r=replay(m1,bucket,horizon,name)
            if r["status"]=="EVALUATED":
                first=r["exit_first_min"]
                r["signal_at_or_before_30"]=first is not None and first<=30
                r["first_confirmation_after_30"]=first is not None and first>30
                if first is not None:
                    entry=m1[signal+first]["c"]
                    end=m1[signal+horizon]["c"]
                    r["post_confirmation_close_change"]=round(end-entry,5)
                    r["post_confirmation_sell_favorable"]=end<entry
            row["variants"][name]=r
        rows.append(row)
    summary={"episodes":len(rows),"horizon_completed_m1":horizon}
    for name in ("timer","veto","urgent"):
        valid=[r["variants"][name] for r in rows if r["variants"][name]["status"]=="EVALUATED"]
        summary[name]={"evaluated":len(valid),
                       "confirmed_episodes":sum(r["exit_first_min"] is not None for r in valid),
                       "first_confirmed_after_minute_30":sum(r["first_confirmation_after_30"] for r in valid),
                       "urgent_warning_episodes":sum(r["urgent_first_min"] is not None for r in valid),
                       "prevented_resets":sum(r["resets_prevented"] for r in valid),
                       "post_confirmation_sell_favorable":sum(r.get("post_confirmation_sell_favorable",False) for r in valid)}
    return {"study":"C2.3 34 M1 candle observation","summary":summary,"episodes":rows,
            "limitations":["34 completed M1 candles after the M5 episode anchor, including anchor at offset zero",
                           "M5 candidate episodes are not actual positions or verified reversals",
                           "Close-to-close after confirmation is descriptive, not execution P&L",
                           "No costs, fills, spread, slippage, or intrabar sequencing",
                           "Overlapping episodes are not independent",
                           "Unchanged C2.3 ablation variants; no live or paper integrations"]}
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db",required=True)
    p.add_argument("--output",required=True)
    p.add_argument("--horizon",type=int,default=34)
    a=p.parse_args()
    if not 1<=a.horizon<=120:p.error("horizon must be 1..120")
    result=analyze(a.db,a.horizon)
    with Path(a.output).open("x") as f:
        json.dump(result,f,indent=2)
        f.write("\n")
    print("SUMMARY",json.dumps(result["summary"]))
    for r in result["episodes"]:
        print("EPISODE",r["episode"],json.dumps({k:{"first":v.get("exit_first_min"),"urgent":v.get("urgent_first_min"),"resets":v.get("resets_prevented"),"post_sell_favorable":v.get("post_confirmation_sell_favorable")} for k,v in r["variants"].items()}))
if __name__=="__main__":main()
