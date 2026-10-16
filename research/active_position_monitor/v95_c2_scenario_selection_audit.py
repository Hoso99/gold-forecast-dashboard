"""Research-only C2 Raw scenario selection-bias and exit-signal comparison.

No change to HybridC. Full 30-minute forward paths required. Synthetic distant
SL/TP merely keep the research state machine open; NOT actual trades.
"""
import argparse,json,statistics
from collections import Counter,defaultdict
from pathlib import Path
from research.active_position_monitor.v95_c21_six_reject_audit import load_m1
from research.active_position_monitor.v95_hybrid_c_research import HybridC,Config

EXIT={"ADAPTIVE_EXIT","EARLY_PROFIT_EXIT"}
TARGET="CONFIRMED_REVERSAL_CANDIDATE"

def summarize(rows):
    d=[r["delta30"] for r in rows]
    return {"n":len(d),"up":sum(v>0 for v in d),
            "down":sum(v<0 for v in d),"flat":sum(v==0 for v in d),
            "up_fraction":round(sum(v>0 for v in d)/len(d),4) if d else None,
            "mean_delta":round(statistics.mean(d),4) if d else None,
            "median_delta":round(statistics.median(d),4) if d else None}

def spaced(rows,spacing=30):
    chosen=[];last={}
    for r in rows:
        s=r["segment"]
        if s not in last or r["minute"]-last[s]>=spacing:
            chosen.append(r);last[s]=r["minute"]
    return chosen

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--db",required=True)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    dest=Path(a.output)
    if dest.exists():p.error("Output already exists")
    m1=load_m1(a.db)
    model=None;last=None;segment=-1
    records=[]
    for t in sorted(m1):
        if last is None or t!=last+1:
            model=HybridC(cfg=Config(power_mode="raw",scenario_monitor_enabled=True))
            price=m1[t]["c"]
            model.open_initial(price,price+10000,price-10000)
            segment+=1
        last=t
        result=model.on_completed_m1(m1[t])
        state=result["scenario_monitor"]["state"]
        if any(t+i not in m1 for i in range(1,31)):continue
        ref=m1[t+1]["o"]
        records.append({"minute":t,"segment":segment,"state":state,
                        "action":result["action"],
                        "delta30":round(m1[t+30]["c"]-ref,5)})
    all_confirmed=[r for r in records if r["state"]==TARGET]
    global_spaced=spaced([r for r in records if r["state"] not in ("INSUFFICIENT_HISTORY","NO_OPEN_SELL")])
    target_first=spaced(all_confirmed)
    # First signal in each uninterrupted run of confirmed labels.
    onset=[];prev=None
    for r in all_confirmed:
        if prev is None or r["segment"]!=prev["segment"] or r["minute"]!=prev["minute"]+1:
            onset.append(r)
        prev=r
    raw_exit=[r for r in records if r["action"] in EXIT]
    # Disjoint forward windows selected independently per cohort; cohorts
    # may overlap each other and are NOT paired exit comparisons.
    summary={
      "study":"C2 Raw confirmed reversal selection sensitivity and raw exit association",
      "total_evaluable":len(records),
      "confirmed_all":summarize(all_confirmed),
      "confirmed_global_30m":summarize([r for r in global_spaced if r["state"]==TARGET]),
      "confirmed_target_first_30m":summarize(target_first),
      "confirmed_onset_all":summarize(onset),
      "confirmed_onset_30m":summarize(spaced(onset)),
      "raw_exit_all":summarize(raw_exit),
      "raw_exit_first_30m":summarize(spaced(raw_exit)),
      "confirmed_and_raw_exit":summarize([r for r in all_confirmed if r["action"] in EXIT]),
      "confirmed_without_raw_exit":summarize([r for r in all_confirmed if r["action"] not in EXIT]),
      "confirmed_action_counts":dict(Counter(r["action"] for r in all_confirmed)),
      "raw_exit_scenario_counts":dict(Counter(r["state"] for r in raw_exit)),
      "sample_confirmed_global_30m_minutes":[r["minute"] for r in global_spaced if r["state"]==TARGET],
      "sample_confirmed_target_first_30m_minutes":[r["minute"] for r in target_first],
      "interpretation":"Positive delta is adverse to SELL; selection sensitivity is not an exit P&L or incremental-value proof.",
      "limitations":["No real entries, fills, costs, SL/TP or position-level returns",
        "Global 30m selection preferentially samples whichever state happens to occur at the fixed sampling phase",
        "Target-first selection conditions on observing a confirmed label; not a fair prospective sampling policy",
        "Onset episodes can overlap and are not independent until spaced",
        "Cohorts are not matched on time or market regime; comparisons descriptive only",
        "No out-of-sample data or confidence interval; M1-only scenario monitor",
        "V9.4 LIVE and V9.5 PAPER unchanged"]}
    with dest.open("x",encoding="utf-8") as f:
        json.dump(summary,f,indent=2);f.write("\n")
    print(json.dumps(summary,indent=2))
if __name__=="__main__":main()
