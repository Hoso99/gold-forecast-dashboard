"""Phase 2D: audit seven held C2 exits, costs and causal feature contrasts.

Research-only post-hoc diagnostics; no rule tuning, broker access or services.
"""
import argparse,json
from pathlib import Path
from statistics import median,mean

FEATURES=("buy_power_5","buy_acceleration_pp","bullish_breakout_atr",
"true_range_expansion","upper_wick_ratio","m1_close_change_3_atr",
"unrealized_r","peak_favorable_r","giveback_r","distance_to_stop_r",
"bullish_closes_last_3","up_close_count_last_3")
def summary(rows):
    if not rows:return None
    return {f:round(median(r["first_c2_request"]["features"][f] for r in rows),5) for f in FEATURES}
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--input",default="/tmp/v95_62_sell_phase2b_oct16.json")
    ap.add_argument("--output",required=True)
    ap.add_argument("--cost-per-oz",type=float,default=0)
    a=ap.parse_args()
    if a.cost_per_oz<0:ap.error("cost must be >=0")
    dest=Path(a.output)
    if dest.exists():ap.error("output already exists")
    raw=json.loads(Path(a.input).read_text())
    eligible=sorted((r for r in raw["signals"] if r.get("pair_valid")),key=lambda r:r["model_time"])
    # Recreate the original Phase 2C grouping/split exactly.
    components=[];current=[];end=None
    for r in eligible:
        if current and r["model_time"]>end:
            components.append(current);current=[];end=None
        current.append(r)
        if end is None or r["event_time"]>end:end=r["event_time"]
    if current:components.append(current)
    cutoff=max(1,round(len(components)*0.65))
    test=[r for group in components[cutoff:] for r in group]
    veto=[r for r in test if r["first_c2_request"]["features"]["buy_power_5"]<75]
    keep=[r for r in test if r not in veto]
    cases=[]
    for r in veto:
        f=r["first_c2_request"]["features"]
        # Extra exit-side costs can change the comparison. Baseline and exit
        # costs supplied by Phase 2B are shared; this sensitivity adds only
        # incremental C2 exit friction and leaves hold unchanged.
        baseline=r["baseline_net_r"]
        exit_r=r["exit_net_r"]
        cases.append({
            "signal_index":r["index"],"entry_time":r["model_time"],
            "exit_request_time":r["first_c2_request"]["time"],
            "protective_event_time":r["event_time"],"outcome":r["outcome"],
            "decision":"VETO_FIRST_C2_EXIT_HOLD_TO_PROTECTIVE",
            "minutes_to_first_request":r["first_c2_request"]["minutes_after_entry"],
            "entry":r["entry"],"stop":r["stop"],"target":r["target"],
            "risk_per_oz":r["risk"],"next_open":r["first_c2_request"]["next_open"],
            "gross_first_exit_r":exit_r,"protective_reference_r":baseline,
            "veto_benefit_r":round(baseline-exit_r,6),
            "incremental_exit_cost_per_oz":a.cost_per_oz,
            "veto_benefit_with_incremental_exit_cost_r":round(
                baseline-(exit_r-a.cost_per_oz/r["risk"]),6),
            "features_at_request":{key:f[key] for key in FEATURES},
        })
    wins=[r for r in veto if r["outcome"]=="TP_FIRST"]
    losses=[r for r in veto if r["outcome"]=="SL_FIRST"]
    report={
        "study":"Phase 2D fixed 75% first-C2-veto forensic audit",
        "total_paired":len(eligible),"components":len(components),
        "test_components":len(components[cutoff:]),"test_n":len(test),
        "test_accepted":len(keep),"test_vetoed":len(veto),
        "beneficial_veto_count":len(wins),"harmful_veto_count":len(losses),
        "veto_total_delta_vs_c2_r":round(sum(x["veto_benefit_r"] for x in cases),6),
        "veto_mean_delta_per_test_signal_r":round(
            sum(x["veto_benefit_r"] for x in cases)/len(test),6) if test else None,
        "veto_feature_medians":{"beneficial_tp_first":summary(wins),
                                "harmful_sl_first":summary(losses)},
        "incremental_exit_cost_per_oz":a.cost_per_oz,
        "cases":cases,
        "limitations":[
            "Future SL/TP outcome is used ONLY as post-hoc label, never input",
            "Seven vetoes are not seven independent market episodes",
            "Original 75% threshold and chronological grouping held fixed",
            "Only first C2 exit request compared, no later exits or reentries",
            "Protective SL/TP are OHLC first-touch reference, not broker fills",
            "Incremental exit cost is illustrative, not a complete spread model",
            "Cannot infer reliable filters from only two harmful cases",
            "V9.4 LIVE, V9.5 PAPER and C2 Raw remain unchanged"
        ]
    }
    with dest.open("x",encoding="utf-8") as f:json.dump(report,f,indent=2);f.write("\n")
    print(json.dumps({k:v for k,v in report.items() if k not in ("cases","limitations")},indent=2))
    for c in cases:
        print("CASE",c["signal_index"],c["outcome"],
              "buy",c["features_at_request"]["buy_power_5"],
              "accel",c["features_at_request"]["buy_acceleration_pp"],
              "velocity",c["features_at_request"]["m1_close_change_3_atr"],
              "breakout",c["features_at_request"]["bullish_breakout_atr"],
              "wick",c["features_at_request"]["upper_wick_ratio"],
              "veto_delta_R",c["veto_benefit_r"])
    print("REPORT",dest)
if __name__=="__main__":main()
