"""Research-only paired proxy SELL exit replay on M5-selected Biquote episodes.

Causal C2 Raw/C2.1 signals; hypothetical SELL already open at anchor.
Exit at NEXT M1 OPEN after completed signal; baseline holds to anchor+45
next M1 open. Fixed 45-minute comparison, not verified V9.4 trades.
"""
import argparse,json,statistics
from pathlib import Path
from research.active_position_monitor.v95_c21_six_reject_audit import load_m1,episodes,EXIT
from research.active_position_monitor.v95_m5_reversal_study import load_m5
from research.active_position_monitor.v95_hybrid_c_research import HybridC,Config
from research.active_position_monitor.v95_hybrid_c21 import C21Confirm

def replay(m1,group,cost_bps):
    anchor=group[0]*5+4
    begin=anchor-99
    last=anchor+46
    if any(t not in m1 for t in range(begin,last+1)):
        return {"status":"SKIP_GAP"}
    prior_closes=[m1[t]["c"] for t in range(begin,anchor+1)]
    model=HybridC(cfg=Config(power_mode="raw"))
    model.open_initial(m1[begin]["c"],max(prior_closes)+10000,min(prior_closes)-10000)
    gate=C21Confirm()
    history=[];previous=None;raw=None;c21=None
    for t in range(begin,anchor+46):
        b=m1[t];history.append(b)
        action=model.on_completed_m1(b)["action"]
        if t>=anchor:
            if action in EXIT and raw is None:raw=t
            if gate.observe(t,b,previous,action,history[-6:-1])=="CONFIRM" and c21 is None:c21=t
        previous=b
    entry=m1[anchor+1]["o"]
    terminal=anchor+45
    paths={}
    for name,signal in (("HOLD",None),("RAW",raw),("C21",c21)):
        exit_bar=min(signal+1,terminal) if signal is not None else terminal
        price=m1[exit_bar]["o"]
        gross=entry-price
        # Same entry cost for all strategies cancels in paired differences;
        # still report 2-sided assumed friction for each hypothetical path.
        costs=(entry+price)*cost_bps/10000
        paths[name]={"signal_offset":None if signal is None else signal-anchor,
                     "exit_offset":exit_bar-anchor,
                     "exit_open":round(price,5),
                     "gross_usd_per_oz":round(gross,5),
                     "net_usd_per_oz":round(gross-costs,5)}
    return {"status":"EVALUATED","entry_open":entry,"paths":paths,
            "raw_minus_hold_net":round(paths["RAW"]["net_usd_per_oz"]-paths["HOLD"]["net_usd_per_oz"],5),
            "c21_minus_hold_net":round(paths["C21"]["net_usd_per_oz"]-paths["HOLD"]["net_usd_per_oz"],5),
            "raw_minus_c21_net":round(paths["RAW"]["net_usd_per_oz"]-paths["C21"]["net_usd_per_oz"],5)}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--db",required=True)
    p.add_argument("--output",required=True)
    p.add_argument("--cost-bps",type=float,default=5.0)
    a=p.parse_args()
    if a.cost_bps<0 or a.cost_bps>100:p.error("cost-bps must be 0..100")
    dest=Path(a.output)
    if dest.exists():p.error("Output exists; choose a new output path")
    m5,_=load_m5(a.db);m1=load_m1(a.db);groups=episodes(m5)
    rows=[]
    for i,g in enumerate(groups,1):
        r=replay(m1,g,a.cost_bps);r["episode"]=i;rows.append(r)
    valid=[r for r in rows if r["status"]=="EVALUATED"]
    def aggregate(key):
        nums=[r[key] for r in valid]
        return {"n":len(nums),"sum":round(sum(nums),5),
                "mean":round(statistics.mean(nums),5) if nums else None,
                "median":round(statistics.median(nums),5) if nums else None,
                "positive":sum(x>0 for x in nums),"negative":sum(x<0 for x in nums),
                "zero":sum(x==0 for x in nums)}
    report={"study":"M5-selected hypothetical SELL paired exit proxy",
            "episode_count":len(groups),"evaluated":len(valid),
            "cost_bps_per_side":a.cost_bps,
            "paired_net_differences_usd_per_oz":{
                "RAW_minus_HOLD":aggregate("raw_minus_hold_net"),
                "C21_minus_HOLD":aggregate("c21_minus_hold_net"),
                "RAW_minus_C21":aggregate("raw_minus_c21_net")},
            "episodes":rows,
            "limitations":[
                "Hypothetical SELL entry at first M1 open after M5 episode anchor, not actual V9.4 trades",
                "Original Hybrid C uses synthetic distant stops/targets; no realistic SL/TP touch replay",
                "Exit signals assessed on completed candles, hypothetical execution at next M1 open",
                "HOLD exits at M1 open 45 minutes after anchor; signals after that do not affect result",
                "Assumed symmetrical bps friction on entry and exit, no spread/latency model",
                "M5 episodes selected for exit candidates, not independent verified reversals",
                "Episodes may overlap; summed results are NOT independent portfolio P&L",
                "Not risk-normalized R, no sizing, no out-of-sample evidence",
                "No changes to V9.4 LIVE or V9.5 PAPER"]}
    with dest.open("x",encoding="utf-8") as f:json.dump(report,f,indent=2);f.write("\n")
    print(json.dumps({k:v for k,v in report.items() if k!="episodes"},indent=2))
    for r in rows:
        if r["status"]=="EVALUATED":
            print("EPISODE",r["episode"],json.dumps({k:r[k] for k in
                ("raw_minus_hold_net","c21_minus_hold_net","raw_minus_c21_net")}))
if __name__=="__main__":main()
