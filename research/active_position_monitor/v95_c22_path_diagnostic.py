"""Read-only M1 path diagnostic for C2 Raw-only M5 episodes. Research only."""
import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path
from research.active_position_monitor.v95_c21_episode_comparison import load_m1
from research.active_position_monitor.v95_m5_history_scan import minute_epoch

def analyze(db, report_path, horizons=(5,15,30)):
    m1=load_m1(db)
    report=json.loads(Path(report_path).read_text())
    results=[]
    for ep in report["episodes"]:
        if ep["raw_first_min"] is None or ep["c21_first_min"] is not None:
            continue
        # first_m5_signal_utc is the end of the M5 bucket; the corresponding
        # final M1 candle is stamped one minute earlier.
        t=minute_epoch(ep["first_m5_signal_utc"])-1+ep["raw_first_min"]
        if t not in m1:
            results.append({"episode":ep["episode"],"status":"MISSING_REFERENCE"})
            continue
        reference=m1[t]["c"]
        row={"episode":ep["episode"],"status":"OK","raw_signal_utc":datetime.fromtimestamp((t+1)*60,__import__("datetime").timezone.utc).isoformat(),"reference_close":reference,"horizons":{}}
        for horizon in horizons:
            future=[m1.get(t+i) for i in range(1,horizon+1)]
            if any(b is None for b in future):
                row["horizons"][str(horizon)]={"status":"INCOMPLETE"}
                continue
            rise=max(b["h"]-reference for b in future)
            drop=max(reference-b["l"] for b in future)
            row["horizons"][str(horizon)]={"status":"OK","max_adverse_rise":round(rise,5),"max_favorable_drop":round(drop,5),"final_change":round(future[-1]["c"]-reference,5),"first_adverse_peak_min":next(i for i,b in enumerate(future,1) if b["h"]-reference==rise),"first_favorable_trough_min":next(i for i,b in enumerate(future,1) if reference-b["l"]==drop)}
        results.append(row)
    return {"study":"C2.2 predevelopment path diagnostic; no exits or trade fills","episodes":results,"limitations":["M1 OHLC cannot establish intrabar high/low order","M5 candidates are not verified reversals","No actual position, spreads, costs or event feed"]}
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--db",required=True)
    p.add_argument("--comparison",required=True)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    result=analyze(a.db,a.comparison)
    with open(a.output,"x") as f: json.dump(result,f,indent=2)
    for row in result["episodes"]: print("EPISODE",json.dumps(row))
if __name__=="__main__": main()
