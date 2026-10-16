"""Research-only C2 first-exit challengers: exploratory train/test audit.

Uses ONLY timestamp-safe features from Phase 2B JSON. No live services.
A challenger either ACCEPTS first C2 exit at next M1 open or VETOES it and
HOLDS to first protective SL/TP. No reentry, costs as supplied in Phase 2B.
Chronological train/test is illustrative; overlapping signals are not independent.
"""
import argparse,json,math
from collections import Counter
from pathlib import Path
from statistics import mean,median

FAMILIES={
 "pressure":("buy_power_5","buy_acceleration_pp"),
 "velocity":("m1_close_change_3_atr","true_range_expansion"),
 "false_breakout":("upper_wick_ratio","bullish_breakout_atr"),
}
# Fixed small candidate grids, research hypotheses rather than fitted live rules.
RULES={
 "pressure":[("buy_power_5",">=",x) for x in (65,75,85,90,95)]
    +[("buy_acceleration_pp",">=",x) for x in (30,45,60,75)],
 "velocity":[("m1_close_change_3_atr",">=",x) for x in (0,0.5,1,1.5,2)]
    +[("true_range_expansion",">=",x) for x in (0.75,1,1.5,2)],
 "false_breakout":[("upper_wick_ratio","<=",x) for x in (0.05,0.10,0.15,0.25,0.4)]
    +[("bullish_breakout_atr",">=",x) for x in (0,0.1,0.25,0.5,1)],
}
def accept(f,rule):
    key,op,threshold=rule
    v=f[key]
    return v>=threshold if op==">=" else v<=threshold
def score(rows,rule=None):
    if not rows:return None
    diffs=[];exits=0
    for r in rows:
        # Baseline reference is hold-to-SL/TP. C2 first-exit strategy is
        # first next-open exit. Veto returns to protective reference.
        use_exit=(rule is None or accept(r["first_c2_request"]["features"],rule))
        exits+=use_exit
        diffs.append((r["exit_net_r"]-r["baseline_net_r"]) if use_exit else 0.0)
    return {"n":len(rows),"exit_requests_accepted":exits,
            "mean_delta_vs_protective_r":round(mean(diffs),6),
            "mean_delta_vs_c2_first_exit_r":round(
                mean(diffs)-mean(r["exit_net_r"]-r["baseline_net_r"] for r in rows),6),
            "sum_delta_vs_c2_first_exit_r":round(
                sum(diffs)-sum(r["exit_net_r"]-r["baseline_net_r"] for r in rows),6),
            "SL_first_accepted":sum(accept(r["first_c2_request"]["features"],rule) if rule else 1
                                     for r in rows if r["outcome"]=="SL_FIRST"),
            "TP_first_accepted":sum(accept(r["first_c2_request"]["features"],rule) if rule else 1
                                     for r in rows if r["outcome"]=="TP_FIRST")}
def overlap_components(rows):
    # Conservative: each record is considered potentially active from its
    # entry until protective touch. Shared active windows form one component.
    ordered=sorted(rows,key=lambda r:r["model_time"])
    components=[];current=[];end=None
    for r in ordered:
        start=r["model_time"];finish=r["event_time"]
        if current and start>end:
            components.append(current);current=[];end=None
        current.append(r)
        if end is None or finish>end:end=finish
    if current:components.append(current)
    return components
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--input",default="/tmp/v95_62_sell_phase2b_oct16.json")
    ap.add_argument("--output",required=True)
    ap.add_argument("--train-fraction",type=float,default=0.65)
    a=ap.parse_args()
    if not 0.4<=a.train_fraction<=0.8:ap.error("train fraction must be 0.4..0.8")
    out=Path(a.output)
    if out.exists():ap.error("output already exists")
    data=json.loads(Path(a.input).read_text())
    rows=[r for r in data["signals"] if r.get("pair_valid")]
    rows.sort(key=lambda r:r["model_time"])
    # Group by overlapping trade observation intervals, not just signal order.
    components=overlap_components(rows)
    cutoff=max(1,round(len(components)*a.train_fraction))
    train=[r for group in components[:cutoff] for r in group]
    test=[r for group in components[cutoff:] for r in group]
    # If no independent test component exists, do not report fake validation.
    result={"study":"Phase 2C three isolated research challengers",
            "total_paired":len(rows),"overlap_components":len(components),
            "train_components":len(components[:cutoff]),
            "test_components":len(components[cutoff:]),
            "train_n":len(train),"test_n":len(test),
            "train_last_event":max((r["event_time"] for r in train),default=None),
            "test_first_entry":min((r["model_time"] for r in test),default=None),
            "c2_train":score(train),"c2_test":score(test),
            "families":{},"limitations":[
                "This is an exploratory fixed-grid threshold test, not calibrated probabilities",
                "Chronological split grouped by overlapping protective-path windows",
                "Censored signals and missing warmup excluded; selection bias remains",
                "Hold is SL/TP first-touch reference, not actual execution",
                "C2 first exit uses next-M1 open and no reentries",
                "Only Phase 2B pre-exit features; no future data used in rules",
                "No claim of statistical independence or live trading edge",
                "No modification of V9.4 LIVE, V9.5 PAPER, or C2 Raw",
            ]}
    for family,rules in RULES.items():
        ranked=[]
        for rule in rules:
            train_score=score(train,rule)
            if train_score is None:continue
            # Avoid trivial always-exit/never-exit solutions; no feature selection
            # when a usable train/test partition cannot be constructed.
            accepted=train_score["exit_requests_accepted"]
            if accepted<max(2,round(0.1*len(train))) or accepted>len(train)-max(2,round(0.1*len(train))):
                continue
            ranked.append((train_score["mean_delta_vs_c2_first_exit_r"],rule,train_score))
        ranked.sort(key=lambda x:(-x[0],x[1][0],x[1][2]))
        selected=ranked[0] if ranked else None
        result["families"][family]={
            "feature_names":FAMILIES[family],
            "candidate_rules":len(rules),"eligible_rules":len(ranked),
            "selected_rule":None if selected is None else {"feature":selected[1][0],"operator":selected[1][1],"threshold":selected[1][2]},
            "train":selected[2] if selected else None,
            "untouched_test":score(test,selected[1]) if selected and test else None,
            "all_train_candidate_results":[{"rule":list(rule),"train":sc} for _,rule,sc in ranked],
        }
    with out.open("x",encoding="utf-8") as f:json.dump(result,f,indent=2);f.write("\n")
    print(json.dumps({k:v for k,v in result.items() if k not in ("families","limitations")},indent=2))
    for family,info in result["families"].items():
        print("FAMILY",family,"SELECTED",info["selected_rule"],
              "TRAIN",info["train"],"TEST",info["untouched_test"])
    print("REPORT",out)
if __name__=="__main__":main()
