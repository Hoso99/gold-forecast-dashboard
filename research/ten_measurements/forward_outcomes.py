"""Research-only forward outcomes for M15 decisions, never modifies live signals."""
import argparse,csv,datetime as dt,json,statistics
from collections import defaultdict
from pathlib import Path
from evaluate import bars_from_csv
from external_inputs import timestamp

def evaluate(m1_path,snapshots_path,output_dir,horizons=(15,30,60)):
    bars=bars_from_csv(m1_path)
    lookup={r[0]:r for r in bars}
    snapshots=[json.loads(line) for line in Path(snapshots_path).read_text().splitlines() if line.strip()]
    out=Path(output_dir);out.mkdir(parents=True,exist_ok=True)
    observations=[]
    for d in snapshots:
        t=timestamp(d["decision_time_utc"])
        if d.get("status")!="OK":continue
        baseline=lookup.get(t)
        if baseline is None:continue
        entry=baseline[1] # next M1 open at decision timestamp; not an executable fill claim
        m=d["measurements"]
        sell=m["01_selling_pressure_acceleration"]
        location=m["02_support_resistance"]
        trend=m["05_higher_timeframe_alignment"]
        reversal=m["04_m1_m5_reversal"]
        atr=m["06_volatility_atr"]["atr14_m1"]
        for horizon in horizons:
            future=[lookup.get(t+dt.timedelta(minutes=k)) for k in range(horizon)]
            if any(b is None for b in future):continue
            last=future[-1]
            high=max(b[2] for b in future);low=min(b[3] for b in future)
            observations.append({
                "decision_time_utc":t.isoformat(),"m15_signal":d["m15_signal"],
                "base_candidate":d["base_candidate"],"original_m15":d["original_m15"],
                "horizon_minutes":horizon,"entry_reference_next_m1_open":entry,
                "forward_close_change":round(last[4]-entry,6),
                "sell_favorable_move":round(entry-low,6),
                "sell_adverse_move":round(high-entry,6),
                "sell_power_10m_pct":sell["sell_power_10m_pct"],
                "sell_power_acceleration_pp":sell["change_percentage_points"],
                "distance_to_support":location["distance_to_support"],
                "h1_trend":trend["h1"],"m5_bullish":reversal["m5_bullish"],
                "atr14_m1":atr,"research_only":True})
    keys=list(observations[0]) if observations else ["decision_time_utc","horizon_minutes"]
    with (out/"forward_outcomes.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(observations)
    summary=[]
    for (signal,horizon),group in sorted(_groups(observations).items()):
        summary.append({"m15_signal":signal,"horizon_minutes":horizon,"n":len(group),
            "mean_forward_close_change":round(statistics.mean(x["forward_close_change"] for x in group),5),
            "mean_sell_favorable_move":round(statistics.mean(x["sell_favorable_move"] for x in group),5),
            "mean_sell_adverse_move":round(statistics.mean(x["sell_adverse_move"] for x in group),5),
            "sell_favorable_close_fraction":round(sum(x["forward_close_change"]<0 for x in group)/len(group),4)})
    with (out/"forward_summary.csv").open("w",newline="") as f:
        keys=list(summary[0]) if summary else ["m15_signal","horizon_minutes","n"]
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(summary)
    return {"observations":len(observations),"summary_groups":len(summary),"output":str(out)}

def _groups(rows):
    groups=defaultdict(list)
    for row in rows:groups[(row["m15_signal"],row["horizon_minutes"])].append(row)
    return groups

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--m1",required=True);p.add_argument("--snapshots",required=True)
    p.add_argument("--output",default="research/ten_measurements/forward_analysis")
    a=p.parse_args();print(json.dumps(evaluate(a.m1,a.snapshots,a.output)))
