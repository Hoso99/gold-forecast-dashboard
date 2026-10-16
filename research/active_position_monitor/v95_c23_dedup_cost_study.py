"""Deduplicated research-only C2.3 Timer exit-vs-hold price comparison.

One observation per exact completed M1 confirmation timestamp.
Cost assumptions are hypothetical, not observed spread/fill data.
"""
import argparse
import json
from pathlib import Path
from statistics import median
from datetime import datetime,timezone
from research.active_position_monitor.v95_c21_episode_comparison import load_m1,load_m5,episodes
from research.active_position_monitor.v95_c23_ablation import replay
from research.active_position_monitor.v95_c23_price_outcomes import path,HORIZONS

def analyze(db,cost_bps):
    m5,_=load_m5(db)
    m1=load_m1(db)
    events={}
    skipped=[]
    for i,g in enumerate(episodes(m5),1):
        signal=g[0]*5+4
        r=replay(m1,g[0],34,"timer")
        if r["status"]!="EVALUATED":
            skipped.append({"episode":i,"reason":r["status"]})
            continue
        offset=r["exit_first_min"]
        if offset is None:continue
        t=signal+offset
        if t not in events:
            events[t]={"confirmation_utc":datetime.fromtimestamp(t*60,timezone.utc).isoformat(),
                       "minute_epoch":t,"episodes":[],"reference_close":m1[t]["c"]}
        events[t]["episodes"].append(i)
    rows=[]
    for t,e in sorted(events.items()):
        horizons={}
        for h in HORIZONS:
            r=path(m1,t,h)
            if r["status"]=="EVALUATED":
                # For a SELL held through horizon, price-only gross benefit
                # compared to closing at the confirmation close is close_now-close_later.
                gross_sell_hold_advantage=-r["final_change"]
                # Explicit illustrative additional round-trip-equivalent friction
                # charged to a hypothetical delayed close; not a broker quote.
                assumed_cost=e["reference_close"]*cost_bps/10000
                net_hold_advantage=gross_sell_hold_advantage-assumed_cost
                r["gross_hold_advantage_vs_exit"]=round(gross_sell_hold_advantage,5)
                r["assumed_extra_hold_cost"]=round(assumed_cost,5)
                r["net_hold_advantage_vs_exit"]=round(net_hold_advantage,5)
                r["hold_better_after_assumed_extra_cost"]=net_hold_advantage>0
            horizons[str(h)]=r
        rows.append({**e,"horizons":horizons})
    summary={"episode_count":len(episodes(m5)),"episode_confirmations":sum(len(e["episodes"]) for e in rows),
             "unique_confirmation_events":len(rows),
             "duplicates_removed":sum(len(e["episodes"])-1 for e in rows),
             "cost_bps_assumed_extra_to_hold":cost_bps,
             "horizons":{},"skipped_episodes":skipped}
    for h in HORIZONS:
        valid=[e["horizons"][str(h)] for e in rows if e["horizons"][str(h)]["status"]=="EVALUATED"]
        summary["horizons"][str(h)]={
            "evaluated":len(valid),"missing":len(rows)-len(valid),
            "sell_continuation":sum(r["sell_continuation"] for r in valid),
            "sell_adverse":sum(r["sell_adverse"] for r in valid),
            "hold_better_after_assumed_extra_cost":sum(r["hold_better_after_assumed_extra_cost"] for r in valid),
            "median_gross_hold_advantage":round(median(r["gross_hold_advantage_vs_exit"] for r in valid),5) if valid else None,
            "median_net_hold_advantage":round(median(r["net_hold_advantage_vs_exit"] for r in valid),5) if valid else None}
    return {"study":"C2.3 Timer unique timestamp hypothetical exit-versus-hold",
            "summary":summary,"events":rows,
            "limitations":["Not verified open SELL positions, actual exit fills or profitability",
                           "Timestamp deduplication removes exact duplicates only; nearby overlapping events remain dependent",
                           "Holding for fixed horizon ignores SL/TP and any intermediate liquidation or stop",
                           "Assumed cost_bps is illustrative incremental friction applied only to delayed hold exit",
                           "Actual exit and hold costs, spread, slippage and position sizing are unknown",
                           "M1 close reference is not an executable price",
                           "No lookahead in signal replay; subsequent prices used only for retrospective evaluation",
                           "No changes to V9.4 LIVE or V9.5 PAPER"]}
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db",required=True)
    p.add_argument("--output",required=True)
    p.add_argument("--cost-bps",type=float,default=5.0)
    a=p.parse_args()
    if not 0<=a.cost_bps<=100:p.error("cost-bps must be 0..100")
    result=analyze(a.db,a.cost_bps)
    with Path(a.output).open("x",encoding="utf-8") as f:
        json.dump(result,f,indent=2)
        f.write("\n")
    print("SUMMARY",json.dumps(result["summary"]))
    for e in result["events"]:
        print("EVENT",json.dumps({"utc":e["confirmation_utc"],"episodes":e["episodes"],
            "outcomes":{h:{"status":r["status"],
                           "gross_hold_advantage":r.get("gross_hold_advantage_vs_exit"),
                           "net_hold_advantage":r.get("net_hold_advantage_vs_exit")}
                        for h,r in e["horizons"].items()}}))
if __name__=="__main__":main()
