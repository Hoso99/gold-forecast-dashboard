"""Research-only ETP-4 validity audit: causal trigger freshness, paired benchmark exits, episode clustering.
No service or trading side effects. Reads a pre-existing ETP report.
"""
import argparse,json
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path
from statistics import mean
from research.active_position_monitor.v95_62_sell_phase2b_features import load,JOURNAL,minute
from research.active_position_monitor.v95_scenario_v3a_research import replay as benchmark

def main():
 p=argparse.ArgumentParser()
 p.add_argument("--etp-report",required=True)
 p.add_argument("--output",required=True)
 p.add_argument("--cost-per-oz",type=float,default=0)
 p.add_argument("--episode-hours",type=int,default=4)
 a=p.parse_args()
 if a.cost_per_oz<0 or a.episode_hours<1:p.error("invalid settings")
 out=Path(a.output)
 if out.exists():p.error("output exists")
 source=json.loads(Path(a.etp_report).read_text())
 journal=json.loads(JOURNAL.read_text())
 bars=load()
 results=[]
 for record in source["signals"]:
  i=record["index"];r=journal[i-1];etp=record["outcomes"]
  raw=benchmark(r,bars,"raw",75,5,100,24*60,a.cost_per_oz)
  v3=benchmark(r,bars,"v3",75,5,100,24*60,a.cost_per_oz)
  hybrid=etp["hybrid_be"];partial=hybrid.get("partial")
  reasons=(partial or {}).get("reason","")
  risk=float(r["stop_loss"])-float(r["entry"])
  # Report was produced with cost=0. Subtract an estimated full round-trip
  # cost for comparable net-R, NOT a broker fill model.
  etp_net=(hybrid["net_r"]-a.cost_per_oz/risk) if "net_r" in hybrid else None
  results.append({"index":i,"time":r["model_time"],"minute":minute(r["model_time"]),
                  "etp_status":hybrid["status"],"etp_net_r_est":etp_net,
                  "partial":partial,"trigger_reasons":reasons,
                  "possible_stale_rsi":("confirmed_bullish_rsi_divergence" in reasons),
                  "raw_status":raw["status"],"raw_net_r":raw.get("net_r"),
                  "v3_status":v3["status"],"v3_net_r":v3.get("net_r")})
 results.sort(key=lambda x:x["minute"])
 episode=-1;last=None
 for r in results:
  if last is None or r["minute"]-last>a.episode_hours*60:episode+=1
  r["episode_id"]=episode;last=r["minute"]
 pairs={}
 for name,key in (("c2_raw","raw_net_r"),("v3a","v3_net_r")):
  valid=[r for r in results if r["etp_net_r_est"] is not None and r[key] is not None]
  diffs=[r["etp_net_r_est"]-r[key] for r in valid]
  by_episode=defaultdict(list)
  for r,d in zip(valid,diffs):by_episode[r["episode_id"]].append(d)
  episode_deltas=[mean(v) for v in by_episode.values()]
  pairs[name]={"paired_signals":len(valid),
               "mean_delta_r":round(mean(diffs),6) if diffs else None,
               "episodes":len(episode_deltas),
               "episode_equal_weight_mean_delta_r":round(mean(episode_deltas),6) if episode_deltas else None,
               "wins":sum(x>0 for x in diffs),"losses":sum(x<0 for x in diffs),
               "ties":sum(x==0 for x in diffs)}
 summary={"signals":len(results),"episodes_time_gap_heuristic":episode+1,
          "hybrid_partial_count":sum(r["partial"] is not None for r in results),
          "rsi_trigger_requires_freshness_audit":sum(r["possible_stale_rsi"] for r in results),
          "trigger_reasons":dict(Counter(r["trigger_reasons"] for r in results if r["partial"])),
          "paired_vs_exit_benchmarks":pairs}
 report={"study":"ETP-4 historical validity and paired benchmark audit (diagnostic, not a validated replay)",
         "parameters":{"episode_hours":a.episode_hours,"cost_per_oz":a.cost_per_oz},
         "summary":summary,"signals":results,
         "limitations":["Uses previous ETP-4 trigger report; stale RSI divergence has NOT been corrected",
         "Benchmark C2/V3A is whole-position exit; ETP remainder is protective-only, not C2/V3A managed",
         "Episode grouping is entry-time proximity heuristic, not verified overlapping exposure",
         "Cost estimate subtracts fixed full-position amount; not dynamic spread/slippage",
         "Benchmark replay requires 100 uninterrupted warmup M1 candles",
         "Censored/unpaired trades excluded; paired samples can be selected",
         "No live/paper/Telegram/timer changes"]}
 with out.open("x") as f:json.dump(report,f,indent=2);f.write("\n")
 print(json.dumps(summary,indent=2));print("REPORT",out)
if __name__=="__main__":main()
