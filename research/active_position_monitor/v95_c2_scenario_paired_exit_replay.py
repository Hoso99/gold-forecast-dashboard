"""Research-only paired C2 Raw vs scenario-assisted SELL exit replay.

Uses identical hypothetical SELL entry, causal completed M1 signals, next-M1
open discretionary execution, and conservative stop-first protective handling.
Scenario-assisted challenger waits up to 2 completed bars after a Raw exit
request for a CONFIRMED_REVERSAL_CANDIDATE; otherwise executes the pending
Raw exit at expiry. No strategy/engine code modified.
"""
import argparse,json,statistics
from pathlib import Path
from research.active_position_monitor.v95_c21_six_reject_audit import load_m1,episodes,EXIT
from research.active_position_monitor.v95_m5_reversal_study import load_m5
from research.active_position_monitor.v95_hybrid_c_research import HybridC,Config

def replay(m1,group,cost_bps,stop_distance,hold_minutes):
    anchor=group[0]*5+4
    begin=anchor-99
    end=anchor+hold_minutes
    if any(t not in m1 for t in range(begin,end+1)):
        return {"status":"SKIP_GAP"}
    entry_t=anchor+1
    entry=m1[entry_t]["o"]
    stop=entry+stop_distance
    target=entry-2*stop_distance
    model=HybridC(cfg=Config(power_mode="raw",scenario_monitor_enabled=True))
    model.open_initial(m1[begin]["c"],m1[begin]["c"]+10000,m1[begin]["c"]-10000)
    decisions={}
    for t in range(begin,end):
        decisions[t]=model.on_completed_m1(m1[t])
    raw_signal=None
    for t in range(anchor,end):
        if decisions[t]["action"] in EXIT:
            raw_signal=t;break
    # Challenger uses only its own pending candidate; expiry prevents
    # indefinite deferral. It may act on confirmed scenario on the same bar
    # as Raw, or wait up to 2 further completed bars.
    def challenger():
        candidate=None
        pending=None
        for t in range(entry_t,end+1):
            b=m1[t]
            if pending is not None and pending<=t:
                return {"reason":"DISCRETIONARY_EXIT","exit_minute":t,"price":b["o"]}
            sl=b["h"]>=stop;tp=b["l"]<=target
            if sl or tp:
                return {"reason":"PROTECTIVE_SL" if sl else "PROTECTIVE_TP",
                        "both_touched":sl and tp,"exit_minute":t,
                        "price":stop if sl else target}
            if t>=end:return {"reason":"HORIZON","exit_minute":t,"price":b["c"]}
            d=decisions[t]
            if candidate is None and d["action"] in EXIT:candidate=t
            if candidate is not None:
                if d["scenario_monitor"]["state"]=="CONFIRMED_REVERSAL_CANDIDATE" or t-candidate>=2:
                    pending=t+1
        raise AssertionError("unreachable")
    def raw():
        pending=None
        for t in range(entry_t,end+1):
            b=m1[t]
            if pending is not None and pending<=t:
                return {"reason":"DISCRETIONARY_EXIT","exit_minute":t,"price":b["o"]}
            sl=b["h"]>=stop;tp=b["l"]<=target
            if sl or tp:
                return {"reason":"PROTECTIVE_SL" if sl else "PROTECTIVE_TP",
                        "both_touched":sl and tp,"exit_minute":t,
                        "price":stop if sl else target}
            if t>=end:return {"reason":"HORIZON","exit_minute":t,"price":b["c"]}
            if decisions[t]["action"] in EXIT:pending=t+1
        raise AssertionError("unreachable")
    def net(x):
        return round(entry-x["price"]-(entry+x["price"])*cost_bps/10000,5)
    a=raw();b=challenger()
    return {"status":"EVALUATED","anchor":anchor,"entry":entry,
            "stop":stop,"target":target,
            "raw":{**a,"net_usd_per_oz":net(a)},
            "scenario":{**b,"net_usd_per_oz":net(b)},
            "scenario_minus_raw":round(net(b)-net(a),5),
            "overlap_warning":"M5-selected episodes may overlap"}

def aggregate(rows):
    nums=[r["scenario_minus_raw"] for r in rows]
    return {"n":len(nums),"sum":round(sum(nums),5),
            "mean":round(statistics.mean(nums),5) if nums else None,
            "median":round(statistics.median(nums),5) if nums else None,
            "scenario_better":sum(x>0 for x in nums),
            "raw_better":sum(x<0 for x in nums),
            "tie":sum(x==0 for x in nums)}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--db",required=True)
    p.add_argument("--output",required=True)
    p.add_argument("--cost-bps",type=float,default=5.0)
    p.add_argument("--stop-distance",type=float,default=15.0)
    p.add_argument("--hold-minutes",type=int,default=45)
    args=p.parse_args()
    if not (0<=args.cost_bps<=100 and args.stop_distance>0 and 5<=args.hold_minutes<=120):
        p.error("Invalid cost/stop/hold parameters")
    dest=Path(args.output)
    if dest.exists():p.error("Output exists")
    m5,_=load_m5(args.db);m1=load_m1(args.db)
    groups=episodes(m5)
    rows=[]
    for i,g in enumerate(groups,1):
        result=replay(m1,g,args.cost_bps,args.stop_distance,args.hold_minutes)
        result["episode"]=i;rows.append(result)
    valid=[r for r in rows if r["status"]=="EVALUATED"]
    report={"study":"C2 Raw vs scenario-confirmed 2-bar-delay exit replay",
            "episode_count":len(groups),"evaluated":len(valid),
            "cost_bps_per_side":args.cost_bps,"stop_distance_usd_per_oz":args.stop_distance,
            "target_rr":2.0,"hold_minutes":args.hold_minutes,
            "paired_net_difference":aggregate(valid),
            "raw_exit_reasons":{x:sum(r["raw"]["reason"]==x for r in valid) for x in
                ("DISCRETIONARY_EXIT","PROTECTIVE_SL","PROTECTIVE_TP","HORIZON")},
            "scenario_exit_reasons":{x:sum(r["scenario"]["reason"]==x for r in valid) for x in
                ("DISCRETIONARY_EXIT","PROTECTIVE_SL","PROTECTIVE_TP","HORIZON")},
            "episodes":rows,
            "limitations":["Research-only hypothetical SELL entries at next M1 open after M5-selected anchor",
              "Fixed illustrative stop distance and 2R target, not actual V9.4 structure/ATR stops",
              "Both SL and TP within M1 treated conservatively as SL; no intrabar order data",
              "Gaps, spread, slippage, stop fill deviations and latency not modeled",
              "Entry and exit bps friction assumed; horizon exits at final M1 close",
              "M5-selected episodes may overlap; no portfolio P&L or independent win rate",
              "Scenario policy is an unvalidated challenger; no actual trade execution",
              "V9.4 LIVE and V9.5 PAPER unchanged"]}
    with dest.open("x",encoding="utf-8") as f:json.dump(report,f,indent=2);f.write("\n")
    print(json.dumps({k:v for k,v in report.items() if k!="episodes"},indent=2))
    for r in rows:
        if r["status"]=="EVALUATED":
            print("EPISODE",r["episode"],"difference",r["scenario_minus_raw"],
                  "raw",r["raw"]["reason"],"scenario",r["scenario"]["reason"])
if __name__=="__main__":main()
