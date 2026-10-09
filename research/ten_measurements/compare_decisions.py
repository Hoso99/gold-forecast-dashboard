"""Join historical V9.4 decisions to strictly past completed-M1 measurements."""
import argparse
import csv
import datetime as dt
import json
from pathlib import Path
from evaluate import bars_from_csv, calculate
from external_inputs import enrich, timestamp

def build(m1_path,decisions_path,out_path,events=None,quotes=None,macro=None):
    rows=bars_from_csv(m1_path)
    with open(decisions_path,newline="") as f:
        decisions=list(csv.DictReader(f))
    output=[]
    for decision in decisions:
        decision_at=timestamp(decision["time_utc"])
        # Decision times in the stop comparison represent M15 bucket starts.
        # Therefore do not use candles beginning at/after that time.
        past=[r for r in rows if r[0]+dt.timedelta(minutes=1)<=decision_at]
        record={"decision_time_utc":decision_at.isoformat(),
                "m15_signal":decision.get("m15_signal",""),
                "base_candidate":decision.get("base_candidate",""),
                "original_m15":decision.get("original_m15",""),
                "original_m15_reason":decision.get("original_m15_reason",""),
                "research_only":True}
        if len(past)<45:
            record.update({"status":"INSUFFICIENT_HISTORY","measurements":None})
        else:
            try:
                snapshot=calculate(past)
                enrich(snapshot["measurements"],decision_at,events,quotes,macro)
                record.update({"status":"OK","as_of_m1_close_utc":snapshot["as_of_m1_close_utc"],
                               "measurements":snapshot["measurements"]})
            except ValueError as e:
                record.update({"status":"DATA_QUALITY_BLOCK","reason":str(e),"measurements":None})
        output.append(record)
    out=Path(out_path);out.parent.mkdir(parents=True,exist_ok=True)
    with out.open("w") as f:
        for record in output:f.write(json.dumps(record,allow_nan=False)+"\n")
    counts={}
    for record in output:counts[record["status"]]=counts.get(record["status"],0)+1
    return {"decisions":len(output),"status_counts":counts,"output":str(out)}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--m1",default="research/data/v94_forward_m1.csv")
    p.add_argument("--decisions",default="research/results/v94_stop_comparison/decisions.csv")
    p.add_argument("--output",default="research/ten_measurements/decision_snapshots.jsonl")
    p.add_argument("--events");p.add_argument("--quotes");p.add_argument("--macro")
    a=p.parse_args()
    print(json.dumps(build(a.m1,a.decisions,a.output,a.events,a.quotes,a.macro)))
if __name__=="__main__":main()
