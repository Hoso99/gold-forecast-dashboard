"""Read-only forward-outcome audit for optional C2 Raw M1 scenario labels.

Signal labels are causal, computed at completed M1 closes. Outcome reference
is NEXT M1 OPEN (hypothetical, no fills); future horizon closes and high/low
ranges are retrospective. Disjoint sample uses >=30-minute spacing globally
within each continuous segment, regardless of label.
"""
import argparse,json,statistics
from pathlib import Path
from collections import Counter,defaultdict
from research.active_position_monitor.v95_c21_six_reject_audit import load_m1
from research.active_position_monitor.v95_hybrid_c_research import HybridC,Config

HORIZONS=(5,10,15,30)
STATES=("SELL_CONTINUATION","NORMAL_PULLBACK_CANDIDATE",
        "REVERSAL_WARNING","CONFIRMED_REVERSAL_CANDIDATE",
        "HIGH_VOLATILITY_EVENT","SIDEWAYS_OR_UNCLEAR")

def describe(rows):
    out={"n":len(rows)}
    for h in HORIZONS:
        subset=[r["forward"][str(h)] for r in rows]
        deltas=[x["delta"] for x in subset]
        ranges=[x["range"] for x in subset]
        out[str(h)]={
            "n":len(subset),
            "up":sum(x>0 for x in deltas),
            "down":sum(x<0 for x in deltas),
            "flat":sum(x==0 for x in deltas),
            "mean_delta":round(statistics.mean(deltas),5) if deltas else None,
            "median_delta":round(statistics.median(deltas),5) if deltas else None,
            "median_range":round(statistics.median(ranges),5) if ranges else None}
    return out

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--db",required=True)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    dest=Path(a.output)
    if dest.exists():p.error("Output exists; use new filename")
    m1=load_m1(a.db)
    times=sorted(m1)
    labels=[]
    model=None;previous=None;segment=-1
    for t in times:
        if previous is None or t!=previous+1:
            model=HybridC(cfg=Config(power_mode="raw",scenario_monitor_enabled=True))
            entry=m1[t]["c"]
            model.open_initial(entry,entry+10000,entry-10000)
            segment+=1
        decision=model.on_completed_m1(m1[t])
        labels.append((t,segment,decision["scenario_monitor"]["state"]))
        previous=t
    # Use next M1 open as common post-signal price reference; horizon h
    # means close of minute t+h, so it spans approximately h minutes.
    # Require all intermediate M1 candles, including full 30-min horizon.
    eligible=[]
    skipped=Counter()
    for t,seg,state in labels:
        if state not in STATES:
            skipped["non_evaluable_state"]+=1
            continue
        if any((t+k not in m1) for k in range(1,31)):
            skipped["missing_forward_30m"]+=1
            continue
        ref=m1[t+1]["o"]
        forward={}
        for h in HORIZONS:
            bars=[m1[t+k] for k in range(1,h+1)]
            close=bars[-1]["c"]
            forward[str(h)]={
                "delta":round(close-ref,5),
                "range":round(max(b["h"] for b in bars)-min(b["l"] for b in bars),5),
                "max_up":round(max(b["h"] for b in bars)-ref,5),
                "max_down":round(ref-min(b["l"] for b in bars),5)}
        eligible.append({"minute":t,"segment":seg,"state":state,"forward":forward})
    # Time-based deterministic nonoverlap across ALL states, not per state.
    nonoverlap=[];last_by_segment={}
    for r in eligible:
        prev=last_by_segment.get(r["segment"])
        if prev is None or r["minute"]-prev>=30:
            nonoverlap.append(r)
            last_by_segment[r["segment"]]=r["minute"]
    def by_state(rows):
        return {s:describe([r for r in rows if r["state"]==s]) for s in STATES}
    report={
        "study":"C2 Raw Scenario Monitor forward-price outcome audit",
        "candles_total":len(times),
        "eligible_all":len(eligible),
        "eligible_nonoverlap_30m":len(nonoverlap),
        "skipped":dict(skipped),
        "horizons_minutes":list(HORIZONS),
        "all_observations":by_state(eligible),
        "nonoverlap_30m":by_state(nonoverlap),
        "nonoverlap_selection":"chronological greedy, minimum 30-minute spacing within contiguous M1 segment, independent of state",
        "outcome_definition":"next M1 open to close at signal minute + horizon; up is adverse to SELL, down favorable; range is max high minus min low over forward bars",
        "limitations":[
            "Not verified market reversals, just future price directions and ranges",
            "Labels selected using M1-only historical completed candles; no M5/M15/H1 or calendar input",
            "Hypothetical wide-stop SELL activates C2 Raw; not real V9.4 entries",
            "No actual fills, SL/TP, spread, slippage, fees or risk-normalized R",
            "All-observations sample strongly overlaps; nonoverlap sample is smaller and time-selected",
            "Nonoverlap uses one sample per 30m irrespective of label, potentially unbalanced states",
            "Forward outcomes used only for evaluation, never classification",
            "No out-of-sample holdout or significance test; do not infer accuracy or profitability",
            "V9.4 LIVE and V9.5 PAPER unchanged"]}
    with dest.open("x",encoding="utf-8") as f:json.dump(report,f,indent=2);f.write("\n")
    print(json.dumps(report,indent=2))
if __name__=="__main__":main()
