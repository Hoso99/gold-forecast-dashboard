"""Research-only parity test: C2 Raw with scenario labels OFF vs ON."""
import argparse,json
from pathlib import Path
from research.active_position_monitor.v95_c21_six_reject_audit import load_m1
from research.active_position_monitor.v95_hybrid_c_research import HybridC,Config

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--db",required=True)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    dest=Path(a.output)
    if dest.exists():p.error("Output exists")
    m1=load_m1(a.db)
    off=HybridC(cfg=Config(power_mode="raw",scenario_monitor_enabled=False))
    on=HybridC(cfg=Config(power_mode="raw",scenario_monitor_enabled=True))
    times=sorted(m1)
    # Each contiguous segment is independent; use identical synthetic protective
    # levels based on its FIRST candle, never future prices.
    checked=0;differences=[];states={};segment_count=0
    prev=None
    for t in times:
        if prev is None or t!=prev+1:
            off=HybridC(cfg=Config(power_mode="raw",scenario_monitor_enabled=False))
            on=HybridC(cfg=Config(power_mode="raw",scenario_monitor_enabled=True))
            entry=m1[t]["c"]
            off.open_initial(entry,entry+10000,entry-10000)
            on.open_initial(entry,entry+10000,entry-10000)
            segment_count+=1
        prev=t
        base=off.on_completed_m1(m1[t])
        enhanced=on.on_completed_m1(m1[t])
        label=enhanced.pop("scenario_monitor",None)
        checked+=1
        if base!=enhanced:
            differences.append({"minute":t,"off":base,"on":enhanced})
        if label:
            state=label["state"]
            states[state]=states.get(state,0)+1
    report={"study":"C2 Raw optional Scenario Monitor decision parity",
            "candles_checked":checked,"contiguous_segments":segment_count,
            "differences":len(differences),"first_differences":differences[:10],
            "scenario_counts":states,
            "pass":len(differences)==0,
            "note":"Compares identical raw decisions with scenario labels disabled/enabled; not strategy accuracy or real trade P&L"}
    with dest.open("x") as f:json.dump(report,f,indent=2);f.write("\n")
    print(json.dumps(report,indent=2))
    if differences:raise SystemExit(1)
if __name__=="__main__":main()
