"""Research-only C2.4 two-stage sustained bullish confirmation challenger.

Requires C2 Raw warning, then C2.3-style bullish five-bar breakout,
plus a second consecutive bullish close and positive 3-close momentum.
Uses completed M1 candles only. Never changes live/paper monitors.
"""
import argparse,json
from pathlib import Path
from datetime import datetime,timezone
from research.active_position_monitor.v95_c21_episode_comparison import load_m1,load_m5,episodes,EXIT
from research.active_position_monitor.v95_hybrid_c_research import HybridC,Config
from research.active_position_monitor.v95_c23_ablation import replay as replay23
from research.active_position_monitor.v95_c23_price_outcomes import path,HORIZONS

def replay24(m1,bucket,horizon=34):
    signal=bucket*5+4
    begin=signal-99
    end=signal+horizon
    if any(t not in m1 for t in range(begin,end+1)):
        return {"status":"SKIP_MISSING_M1"}
    model=HybridC(cfg=Config(power_mode="raw"))
    closes=[m1[t]["c"] for t in range(begin,end+1)]
    model.open_initial(m1[begin]["c"],max(closes)+10000,min(closes)-10000)
    active=None
    first=None
    warnings=[]
    confirmed=[]
    raw_times=[]
    # Same 5-minute window and no timer reset as C2.3 Timer.
    for t in range(begin,end+1):
        b=m1[t]
        action=model.on_completed_m1(b)["action"]
        if t<signal:continue
        raw=action in EXIT
        if raw:raw_times.append(t-signal)
        if active is None and raw:
            active=t
        if active is None:continue
        age=t-active
        if age>5:
            active=None
            continue
        prior=m1[t-1]
        # Existing C2.3 bearish invalidation; use only completed bars.
        if b["c"]<b["o"] and b["c"]<prior["l"]:
            active=None
            continue
        if age==0:continue
        prior5=[m1[k] for k in range(t-5,t)]
        breakout=b["c"]>max(x["h"] for x in prior5)
        bullish=b["c"]>b["o"] and b["c"]>prior["c"]
        if bullish and breakout:
            warnings.append(t-signal)
            # Distinguish a single bullish bounce from consecutive strength.
            previous_bullish=prior["c"]>prior["o"] and prior["c"]>m1[t-2]["c"]
            momentum_3=b["c"]>m1[t-3]["c"]
            if previous_bullish and momentum_3:
                confirmed.append(t-signal)
                active=None
    return {"status":"EVALUATED","raw_first_min":raw_times[0] if raw_times else None,
            "first_confirmation":confirmed[0] if confirmed else None,
            "first_breakout_warning":warnings[0] if warnings else None}

def analyze(db):
    m5,_=load_m5(db)
    m1=load_m1(db)
    rows=[]
    for i,g in enumerate(episodes(m5),1):
        bucket=g[0]
        signal=bucket*5+4
        c23=replay23(m1,bucket,34,"timer")
        c24=replay24(m1,bucket,34)
        a=c23.get("exit_first_min") if c23["status"]=="EVALUATED" else None
        b=c24.get("first_confirmation") if c24["status"]=="EVALUATED" else None
        row={"episode":i,"c23_first":a,"c24_first":b,
             "c24_breakout_warning":c24.get("first_breakout_warning"),
             "status_c23":c23["status"],"status_c24":c24["status"]}
        for name,offset in (("c23",a),("c24",b)):
            row[name+"_outcomes"]={str(h):path(m1,signal+offset,h) for h in HORIZONS} if offset is not None else {}
            row[name+"_timestamp_utc"]=datetime.fromtimestamp((signal+offset)*60,timezone.utc).isoformat() if offset is not None else None
        rows.append(row)
    summary={"episodes":len(rows)}
    for name in ("c23","c24"):
        key=name+"_first"
        valid=[r for r in rows if r["status_"+name]=="EVALUATED"]
        confirmed=[r for r in valid if r[key] is not None]
        unique={r[name+"_timestamp_utc"] for r in confirmed}
        summary[name]={"evaluated":len(valid),"confirmed_episodes":len(confirmed),
                       "unique_confirmation_timestamps":len(unique),
                       "horizons":{}}
        for h in HORIZONS:
            outcomes=[r[name+"_outcomes"][str(h)] for r in confirmed
                      if r[name+"_outcomes"][str(h)]["status"]=="EVALUATED"]
            summary[name]["horizons"][str(h)]={
                "evaluated":len(outcomes),
                "sell_continuation":sum(v["sell_continuation"] for v in outcomes),
                "sell_adverse":sum(v["sell_adverse"] for v in outcomes)}
    summary["c23_only"]=sum(r["c23_first"] is not None and r["c24_first"] is None for r in rows)
    summary["c24_only"]=sum(r["c24_first"] is not None and r["c23_first"] is None for r in rows)
    summary["both"]=sum(r["c23_first"] is not None and r["c24_first"] is not None for r in rows)
    return {"study":"C2.4 causal sustained bullish structure challenger",
            "summary":summary,"episodes":rows,
            "limitations":["Historical M5 candidate episodes are not actual SELL positions or verified reversals",
                           "Same sample used for development; no out-of-sample validation",
                           "Episode outcomes can overlap; unique timestamp count does not ensure independence",
                           "C2.4 conditions are exploratory, not calibrated or proven superior",
                           "M1 close reference is not executable; no spreads, stops, fees or fills",
                           "Fixed future horizons for research only; no lookahead in confirmation logic",
                           "No changes to V9.4 LIVE or V9.5 PAPER"]}
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
        print("EPISODE",r["episode"],json.dumps({
            "c23":r["c23_first"],"c24":r["c24_first"],
            "c24_warning":r["c24_breakout_warning"],
            "c23_30":r["c23_outcomes"].get("30",{}).get("final_change"),
            "c24_30":r["c24_outcomes"].get("30",{}).get("final_change")}))
if __name__=="__main__":main()
