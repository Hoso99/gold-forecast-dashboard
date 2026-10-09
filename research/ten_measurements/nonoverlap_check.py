"""Sensitivity check: non-overlapping SELL decision windows, no parameter tuning."""
import argparse,csv,json
from collections import defaultdict
from datetime import datetime,timedelta
from pathlib import Path

def run(source,target):
    with open(source,newline="") as f: rows=list(csv.DictReader(f))
    groups=defaultdict(list)
    for r in rows:
        if r["m15_signal"]!="SELL":continue
        groups[int(r["horizon_minutes"])].append(r)
    out=[]
    for horizon,items in sorted(groups.items()):
        items.sort(key=lambda r:r["decision_time_utc"])
        selected=[];last_end=None
        for r in items:
            t=datetime.fromisoformat(r["decision_time_utc"])
            if last_end is None or t>=last_end:
                selected.append(r);last_end=t+timedelta(minutes=horizon)
        for name,subset in [
            ("all",selected),
            ("near_support_1atr",[r for r in selected if r.get("distance_to_support") and r.get("atr14_m1") and float(r["atr14_m1"])>0 and float(r["distance_to_support"])/float(r["atr14_m1"])<=1]),
            ("far_support_1atr",[r for r in selected if r.get("distance_to_support") and r.get("atr14_m1") and float(r["atr14_m1"])>0 and float(r["distance_to_support"])/float(r["atr14_m1"])>1])]:
            changes=[float(r["forward_close_change"]) for r in subset]
            out.append({"horizon_minutes":horizon,"group":name,"n":len(changes),
                "mean_change":round(sum(changes)/len(changes),5) if changes else "",
                "sell_favorable_fraction":round(sum(c<0 for c in changes)/len(changes),4) if changes else "",
                "note":"NON_OVERLAPPING_DESCRIPTIVE_ONLY"})
    target=Path(target);target.parent.mkdir(parents=True,exist_ok=True)
    with target.open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=["horizon_minutes","group","n","mean_change","sell_favorable_fraction","note"]);w.writeheader();w.writerows(out)
    return {"groups":len(out),"output":str(target)}
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--input",required=True);p.add_argument("--output",required=True)
    a=p.parse_args();print(json.dumps(run(a.input,a.output)))
