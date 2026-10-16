"""V3-A3: chronological robustness and differential execution stress.
Research only. Reads the completed V3-A2 JSON; never touches trading systems.
"""
import argparse,json,math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean,median

def stamp(s):
    return datetime.fromisoformat(s).timestamp()/60 if s else None

def summarize(rows):
    if not rows:return {"n":0}
    d=[x["delta_r"] for x in rows]
    return {"n":len(d),"mean_delta_r":round(mean(d),6),
            "sum_delta_r":round(sum(d),6),
            "median_delta_r":round(median(d),6),
            "better":sum(x>1e-8 for x in d),
            "worse":sum(x< -1e-8 for x in d),
            "ties":sum(abs(x)<=1e-8 for x in d),
            "worst_delta_r":round(min(d),6),
            "best_delta_r":round(max(d),6)}
def components(rows):
    # Group overlapping observation intervals using earliest model timestamp
    # through latest available exit time across ALL tested variants.
    ordered=sorted(rows,key=lambda x:x["start"])
    groups=[];group=[];end=None
    for r in ordered:
        if group and r["start"]>end:
            groups.append(group);group=[];end=None
        group.append(r);end=max(end or r["end"],r["end"])
    if group:groups.append(group)
    return groups
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",required=True)
    p.add_argument("--output",required=True)
    p.add_argument("--extra-slippage-per-oz",type=float,nargs="+",default=[0,0.1,0.25,0.5,1])
    a=p.parse_args()
    if any(v<0 for v in a.extra_slippage_per_oz):p.error("slippage must be nonnegative")
    dst=Path(a.output)
    if dst.exists():p.error("output exists")
    data=json.loads(Path(a.input).read_text())
    limits=[str(v) for v in data["parameters"]["limits"]]
    rows=[]
    for s in data["signals"]:
        raw=s["raw"];variants=s["v3a2"]
        if "net_r" not in raw or any("net_r" not in variants[k] for k in limits):continue
        start=stamp(s["model_time"])
        end=max(stamp(raw.get("time")) or start,
                *(stamp(variants[k].get("time")) or start for k in limits))
        # Infer risk per ounce from the provided price and R, where possible.
        # Original replay stores net R and fill, but no entry or stop here.
        # Risk cannot be reconstructed reliably from those two values alone;
        # require journal metadata only if supplied by the source report.
        rows.append({"index":s["index"],"start":start,"end":end,
                     "raw":raw,"v3a":s["v3a"],"variants":variants})
    groups=components(rows)
    group_ids={r["index"]:i for i,g in enumerate(groups) for r in g}
    chronological=sorted(rows,key=lambda r:(r["start"],r["index"]))
    n=len(chronological)
    thirds=[chronological[:n//3],chronological[n//3:2*n//3],chronological[2*n//3:]]
    results={}
    for k in limits:
        observations=[]
        for r in chronological:
            v=r["variants"][k];raw=r["raw"]
            observations.append({"index":r["index"],"component":group_ids[r["index"]],
                                 "delta_r":v["net_r"]-raw["net_r"],
                                 "raw_r":raw["net_r"],"challenger_r":v["net_r"],
                                 "exit_delay_minutes":v.get("delay_minutes"),
                                 "exit_reason":v.get("reason")})
        total=summarize(observations)
        ranked=sorted(observations,key=lambda x:x["delta_r"],reverse=True)
        positive=sum(max(0,x["delta_r"]) for x in observations)
        top3=sum(max(0,x["delta_r"]) for x in ranked[:3])
        group_rows=[[x for x in observations if x["component"]==i] for i in range(len(groups))]
        group_stats=[summarize(g) for g in group_rows]
        by_id={x["index"]:x for x in observations}
        third_stats=[summarize([by_id[r["index"]] for r in g]) for g in thirds]
        # Stress as extra *R* charged only to challenger, with explicit
        # illustrative stop distances. Not market spread observations.
        stress={}
        for risk_usd in (5,10,20):
            stress[str(risk_usd)]={}
            for slip in a.extra_slippage_per_oz:
                ds=[dict(x,delta_r=x["delta_r"]-slip/risk_usd) for x in observations]
                stress[str(risk_usd)][str(slip)]=summarize(ds)
        results[k]={"vs_raw":total,"chronological_thirds":third_stats,
                    "overlap_component_count":len(groups),
                    "overlap_component_sizes":[len(g) for g in groups],
                    "overlap_component_results":group_stats,
                    "top_three_positive_contribution_r":round(top3,6),
                    "total_positive_contribution_r":round(positive,6),
                    "sum_without_top_three":round(sum(x["delta_r"] for x in ranked[3:]),6),
                    "worst_five":[{"index":x["index"],"delta_r":round(x["delta_r"],6)} for x in ranked[-5:]],
                    "best_five":[{"index":x["index"],"delta_r":round(x["delta_r"],6)} for x in ranked[:5]],
                    "hypothetical_extra_challenger_slippage":stress}
    report={"study":"V3-A3 chronological robustness and hypothetical differential slippage",
            "input":a.input,"paired_all_variants":len(rows),
            "components":[{"id":i,"n":len(g),"first_signal":g[0]["index"],
                           "last_signal":g[-1]["index"]} for i,g in enumerate(groups)],
            "results":results,
            "limitations":[
                "Historical data reused for design and evaluation; not independent validation",
                "Chronological thirds are descriptive, not independent held-out tests",
                "Overlap components represent correlated observations; no independent trade count inferred",
                "Hypothetical differential slippage assumes stop distances of $5/$10/$20 per ounce; not observed market spreads",
                "Stress subtracts extra adverse slippage only from challenger; symmetric costs cancel in paired R",
                "Input replay uses hypothetical next-minute open fills; no real broker fills",
                "No original research or live systems modified"]}
    with dst.open("x") as f:json.dump(report,f,indent=2);f.write("\n")
    print("PAIRED",len(rows),"OVERLAP COMPONENTS",len(groups),
          "SIZES",[len(g) for g in groups])
    for k in limits:
        r=results[k]
        print("\nWINDOW",k,"minutes")
        print("OVERALL",json.dumps(r["vs_raw"]))
        print("CHRONOLOGICAL THIRDS",json.dumps(r["chronological_thirds"]))
        print("COMPONENTS",json.dumps(r["overlap_component_results"]))
        print("TOP 3 POSITIVE",r["top_three_positive_contribution_r"],
              "SUM WITHOUT TOP 3",r["sum_without_top_three"])
        print("BEST FIVE",r["best_five"],"WORST FIVE",r["worst_five"])
        for risk in ("5","10","20"):
            print("HYPOTHETICAL RISK $"+risk+"/oz; EXTRA SLIPPAGE $0.25/oz",
                  r["hypothetical_extra_challenger_slippage"][risk].get("0.25"))
    print("REPORT",dst)
if __name__=="__main__":main()
