"""V3-A4 research-only actual-stop risk cost stress and episode sensitivity.
Reads immutable V3-A2 replay JSON and local V9.4 journal. No live writes.
"""
import argparse,json
from collections import defaultdict
from pathlib import Path
from statistics import mean,median
from research.active_position_monitor.v95_62_sell_phase2b_features import JOURNAL,minute

def stats(values):
    if not values:return {"n":0}
    return {"n":len(values),"mean_delta_r":round(mean(values),6),
            "sum_delta_r":round(sum(values),6),
            "median_delta_r":round(median(values),6),
            "better":sum(x>1e-8 for x in values),
            "worse":sum(x< -1e-8 for x in values),
            "ties":sum(abs(x)<=1e-8 for x in values),
            "min_delta_r":round(min(values),6),"max_delta_r":round(max(values),6)}
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",required=True)
    p.add_argument("--output",required=True)
    p.add_argument("--extra-slippage-per-oz",type=float,nargs="+",default=[0,0.05,0.1,0.25,0.5])
    a=p.parse_args()
    if any(v<0 for v in a.extra_slippage_per_oz):p.error("slippage cannot be negative")
    dest=Path(a.output)
    if dest.exists():p.error("output already exists")
    data=json.loads(Path(a.input).read_text())
    journal=json.loads(JOURNAL.read_text())
    sell_journal={i:r for i,r in enumerate(journal,1) if str(r.get("side","")).upper()=="SELL"}
    limits=[str(n) for n in data["parameters"]["limits"]]
    records=[];excluded=[]
    for s in data["signals"]:
        idx=s["index"];j=sell_journal.get(idx)
        if j is None:
            excluded.append({"index":idx,"reason":"missing_sell_journal"});continue
        try:
            start=minute(j["model_time"])
            entry=float(j["entry"]);stop=float(j["stop_loss"]);tp=float(j["take_profit"])
            risk=stop-entry
            if not tp<entry<stop or risk<=0:raise ValueError("invalid SELL geometry")
            raw=s["raw"];vv=s["v3a2"]
            if "net_r" not in raw or any("net_r" not in vv[k] for k in limits):
                excluded.append({"index":idx,"reason":"not_all_paired"});continue
            exits=[minute(raw["time"])]+[minute(vv[k]["time"]) for k in limits]
            end=max(exits)
        except (KeyError,TypeError,ValueError) as e:
            excluded.append({"index":idx,"reason":str(e)});continue
        records.append({"index":idx,"start":start,"end":end,"risk_per_oz":risk,
                        "raw_r":raw["net_r"],
                        "variants":{k:{"delta_r":vv[k]["net_r"]-raw["net_r"],
                                       "delay":vv[k].get("delay_minutes"),
                                       "reason":vv[k].get("reason")} for k in limits}})
    ordered=sorted(records,key=lambda r:(r["start"],r["index"]))
    groups=[];current=[];maxend=None
    for r in ordered:
        if current and r["start"]>maxend:
            groups.append(current);current=[];maxend=None
        current.append(r);maxend=max(r["end"],maxend if maxend is not None else r["end"])
    if current:groups.append(current)
    for gid,g in enumerate(groups):
        for r in g:r["episode"]=gid
    summary={"paired":len(records),"excluded":len(excluded),
             "risk_per_oz":{"min":round(min(r["risk_per_oz"] for r in records),4),
                            "median":round(median(r["risk_per_oz"] for r in records),4),
                            "max":round(max(r["risk_per_oz"] for r in records),4)},
             "overlap_episodes":len(groups),
             "episode_sizes":[len(g) for g in groups],"limits":{}}
    for k in limits:
        deltas=[r["variants"][k]["delta_r"] for r in ordered]
        episode_mean=[mean(r["variants"][k]["delta_r"] for r in g) for g in groups]
        episode_sum=[sum(r["variants"][k]["delta_r"] for r in g) for g in groups]
        results={"gross":stats(deltas),
                 "episode_equal_weight_mean":stats(episode_mean),
                 "episode_total_contribution":stats(episode_sum),
                 "leave_one_episode_out_mean_delta_r":[
                     round(mean([r["variants"][k]["delta_r"] for r in ordered if r["episode"]!=gid]),6)
                     for gid in range(len(groups)) if len(ordered)>len(groups[gid])],
                 "actual_stop_cost_sensitivity":{}}
        for slip in a.extra_slippage_per_oz:
            adjusted=[r["variants"][k]["delta_r"]-slip/r["risk_per_oz"] for r in ordered]
            episode_adj=[mean(r["variants"][k]["delta_r"]-slip/r["risk_per_oz"] for r in g) for g in groups]
            results["actual_stop_cost_sensitivity"][str(slip)]={
                "signal_weighted":stats(adjusted),"episode_equal_weight":stats(episode_adj)}
        results["leave_one_episode_out_range"]={
            "min":min(results["leave_one_episode_out_mean_delta_r"]),
            "max":max(results["leave_one_episode_out_mean_delta_r"])}
        results.pop("leave_one_episode_out_mean_delta_r")
        summary["limits"][k]=results
    report={"study":"V3-A4 actual-stop cost stress and overlap episode robustness",
            "source":a.input,"summary":summary,
            "excluded":excluded,
            "episodes":[{"id":gid,"indices":[r["index"] for r in g],
                         "start_minute_utc":g[0]["start"],
                         "end_minute_utc":max(r["end"] for r in g),
                         "variant_delta_sum_r":{k:round(sum(r["variants"][k]["delta_r"] for r in g),6) for k in limits}}
                        for gid,g in enumerate(groups)],
            "limitations":[
                "Historical replay results are in-sample; no independent forward validation",
                "Costs are extra adverse hypothetical per-ounce slippage ONLY on challenger versus Raw",
                "Uses original journal entry and stop; not independently verified broker fills",
                "Correlated signals grouped by overlapping modeled entry-to-latest-exit intervals",
                "Episode-equal weighting is descriptive, not a statistical independence guarantee",
                "Cost sensitivity assumes constant dollar slippage, not dynamic spreads",
                "No live V9.4, V9.5 PAPER, C2 Raw or original V3 research modified"]}
    with dest.open("x",encoding="utf-8") as f:json.dump(report,f,indent=2);f.write("\n")
    print("PAIRED",summary["paired"],"EPISODES",summary["overlap_episodes"],
          "RISK PER OZ",summary["risk_per_oz"])
    for k,rr in summary["limits"].items():
        print("\nWINDOW",k,"min")
        print("GROSS",rr["gross"])
        print("EQUAL EPISODE",rr["episode_equal_weight_mean"])
        print("LEAVE ONE EPISODE OUT RANGE",rr["leave_one_episode_out_range"])
        for slip in a.extra_slippage_per_oz:
            v=rr["actual_stop_cost_sensitivity"][str(slip)]
            print("EXTRA SLIPPAGE $"+str(slip)+"/oz",
                  "SIGNAL",v["signal_weighted"],"EPISODE",v["episode_equal_weight"])
    print("REPORT",dest)
if __name__=="__main__":main()
