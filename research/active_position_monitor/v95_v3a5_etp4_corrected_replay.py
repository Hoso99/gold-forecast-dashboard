"""ETP-4 corrected historical partial-exit replay. Research-only, no side effects.

C2 Raw and V3-A benchmark exit times are replayed independently and treated
as hypothetical remaining-position exits. No execution or broker assertions.
"""
import argparse,json,math
from pathlib import Path
from collections import Counter,defaultdict
from statistics import mean
from research.active_position_monitor.v95_62_sell_phase2b_features import load,JOURNAL,minute
from research.active_position_monitor.v95_scenario_v3a_research import replay as benchmark
from research.active_position_monitor.v95_v3a5_etp4_freshness_audit import signals_at

def trigger(r,bars,limit):
 t=minute(r["model_time"]);e=float(r["entry"]);s=float(r["stop_loss"]);tp=float(r["take_profit"])
 if not tp<e<s:return None
 armed=None
 for m in range(t+1,t+limit+1):
  b=bars.get(m)
  if b is None:return None
  if b["h"]>=s or b["l"]<=tp:return None
  if armed is None and b["l"]<=e-(s-e):armed=m
  if armed is not None and m>armed:
   reasons=signals_at(bars,m)
   if reasons:return {"decision_minute":m,"fill_minute":m+1,"armed_minute":armed,"reasons":sorted(reasons)}
 return None

def simulate(r,bars,limit,base,signal,fraction,be,cost):
 t=minute(r["model_time"]);e=float(r["entry"]);s=float(r["stop_loss"]);tp=float(r["take_profit"])
 risk=s-e
 if not all(math.isfinite(x) for x in (e,s,tp)) or not tp<e<s:return {"status":"INVALID"}
 if base["status"] in ("INVALID","NO_WARMUP"):return {"status":"BENCHMARK_"+base["status"]}
 exit_m=minute(base["time"]) if "time" in base else None
 partial=None;stop=s
 for m in range(t+1,t+limit+1):
  b=bars.get(m)
  if b is None:return {"status":"CENSORED_GAP","partial":partial}
  # Benchmark's next-open decision has priority at that open.
  if exit_m==m:
   px=float(base["exit_price"])
   gross=(e-px)/risk
   total=gross if partial is None else fraction*partial["gross_r"]+(1-fraction)*gross
   return {"status":"BENCHMARK_"+base["status"],"partial":partial,"net_r":round(total-cost/risk,7)}
  if signal and partial is None and fraction>0 and m==signal["fill_minute"]:
   # An opening gap through the original stop precludes favorable partial execution.
   if b["o"]>=s:return {"status":"STOP_GAP","partial":None,"net_r":round((e-b["o"]-cost)/risk,7)}
   # A gap through the TP is an original protective exit, not a partial fill.
   if b["o"]<=tp:return {"status":"TP_GAP","partial":None,"net_r":round((e-b["o"]-cost)/risk,7)}
   candidate=(e-b["o"])/risk
   if candidate>0:
    partial={"minute":m,"price":b["o"],"gross_r":candidate,"fraction":fraction,
             "reasons":signal["reasons"]}
    stop=e if be else s
  hit_s=b["h"]>=stop;hit_t=b["l"]<=tp
  if hit_s and hit_t:return {"status":"AMBIGUOUS_BOTH_TOUCH","partial":partial}
  if hit_s or hit_t:
   px=max(stop,b["o"]) if hit_s else tp
   gross=(e-px)/risk
   total=gross if partial is None else fraction*partial["gross_r"]+(1-fraction)*gross
   return {"status":"STOP" if hit_s else "TP","partial":partial,
           "net_r":round(total-cost/risk,7)}
 return {"status":"CENSORED_LIMIT","partial":partial}

def main():
 p=argparse.ArgumentParser()
 p.add_argument("--output",required=True)
 p.add_argument("--hours",type=int,default=24)
 p.add_argument("--cost-per-oz",type=float,default=0)
 p.add_argument("--episode-hours",type=int,default=4)
 a=p.parse_args()
 if not 1<=a.hours<=336 or a.cost_per_oz<0 or a.episode_hours<1:p.error("invalid settings")
 output=Path(a.output)
 if output.exists():p.error("output exists")
 bars=load();journal=json.loads(JOURNAL.read_text())
 rows=[]
 for i,r in enumerate(journal,1):
  if str(r.get("side","")).upper()!="SELL":continue
  try:
   e=float(r["entry"]);s=float(r["stop_loss"]);tp=float(r["take_profit"]);t=minute(r["model_time"])
   if not tp<e<s:raise ValueError()
  except (ValueError,KeyError,TypeError):continue
  fresh=trigger(r,bars,a.hours*60)
  outcomes={}
  for name,mode in (("c2","raw"),("v3a","v3")):
   base=benchmark(r,bars,mode,75,5,100,a.hours*60,0)
   outcomes[name+"_baseline"]=simulate(r,bars,a.hours*60,base,None,0,False,a.cost_per_oz)
   for fraction in (.25,.5):
    for be in (False,True):
     key=f"{name}_etp_{int(fraction*100)}_{'be' if be else 'original'}"
     outcomes[key]=simulate(r,bars,a.hours*60,base,fresh,fraction,be,a.cost_per_oz)
  rows.append({"index":i,"minute":t,"fresh_trigger":fresh,"outcomes":outcomes})
 rows.sort(key=lambda x:x["minute"])
 episode=-1;last=None
 for row in rows:
  if last is None or row["minute"]-last>a.episode_hours*60:episode+=1
  row["episode_id"]=episode;last=row["minute"]
 summary={"signals":len(rows),"episodes_heuristic":episode+1,
          "fresh_triggers":sum(x["fresh_trigger"] is not None for x in rows),
          "strategies":{}}
 for name in rows[0]["outcomes"] if rows else []:
  entries=[x["outcomes"][name] for x in rows]
  paired=[];groups=defaultdict(list)
  base_name="c2_baseline" if name.startswith("c2") else "v3a_baseline"
  for row in rows:
   value=row["outcomes"][name].get("net_r")
   baseline=row["outcomes"][base_name].get("net_r")
   if value is None or baseline is None:continue
   delta=value-baseline
   paired.append(delta);groups[row["episode_id"]].append(delta)
  summary["strategies"][name]={
   "completed":sum("net_r" in x for x in entries),
   "partials":sum(x.get("partial") is not None for x in entries),
   "status_counts":dict(Counter(x["status"] for x in entries)),
   "paired":len(paired),
   "mean_delta_vs_matching_benchmark":round(mean(paired),7) if paired else None,
   "episode_groups_paired":len(groups),
   "episode_equal_weight_delta":round(mean(mean(v) for v in groups.values()),7) if groups else None}
 report={"study":"ETP-4 corrected freshness partial replay vs C2 and V3A",
         "parameters":{"hours":a.hours,"cost_per_oz":a.cost_per_oz,"episode_hours":a.episode_hours},
         "summary":summary,"signals":rows,
         "limitations":["Only completed M5 confirmations strictly after +1R activation",
         "C2/V3A benchmark replay is independent; remainder uses benchmark exit timestamp, not a reinitialized half-size model",
         "If benchmark exits before ETP trigger, partial is suppressed",
         "No broker fills; partial assumed at next M1 open; gap and ambiguous touches flagged",
         "Protective stop is applied before newly completed bar signals",
         "Flat cost-per-oz applied once to full notional; does not model spread/slippage at each fill",
         "Incomplete histories censored; episode grouping is a time-gap heuristic",
         "No prospective validation; overlapping signals not independent",
         "Research only; no live, paper, Telegram or timer changes"]}
 with output.open("x") as f:json.dump(report,f,indent=2);f.write("\n")
 print(json.dumps(summary,indent=2));print("REPORT",output)
if __name__=="__main__":main()
