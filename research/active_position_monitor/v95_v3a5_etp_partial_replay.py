"""Research-only ETP replay. No service, broker, or Telegram integration.

Historical signal-level partial exit versus protective SL/TP. All triggers
use completed bars; partial fills at following M1 open. No live execution.
"""
import argparse,json,math
from collections import Counter
from statistics import mean
from pathlib import Path
from research.active_position_monitor.v95_62_sell_phase2b_features import load,JOURNAL,minute,iso

def ema(vals,n=20):
 if len(vals)<n:return None
 e=sum(vals[:n])/n
 for v in vals[n:]:e+=(v-e)*2/(n+1)
 return e

def rsi(vals,n=14):
 if len(vals)<n+1:return None
 dif=[vals[i]-vals[i-1] for i in range(len(vals)-n,len(vals))]
 up=sum(max(0,x) for x in dif)/n;down=sum(max(0,-x) for x in dif)/n
 return 100 if down==0 else 100-100/(1+up/down)

def m5_reversal(bars,end):
 # Last M5 candle is fully completed only when (end+1)%5==0.
 if (end+1)%5:return []
 blocks=[]
 for finish in range(end-5*27,end+1,5):
  seq=[bars.get(j) for j in range(finish-4,finish+1)]
  if any(x is None for x in seq):return []
  blocks.append({"l":min(x["l"] for x in seq),"c":seq[-1]["c"]})
 closes=[b["c"] for b in blocks]
 reasons=[]
 e=ema(closes,20)
 if e is not None and closes[-2]<=ema(closes[:-1],20) and closes[-1]>e:
  reasons.append("m5_ema20_cross_up")
 # Confirmed swing lows: center pivot needs 2 M5 bars to the right.
 pivots=[i for i in range(2,len(blocks)-2) if
         all(blocks[i]["l"]<blocks[j]["l"] for j in (i-2,i-1,i+1,i+2))]
 if len(pivots)>=2:
  a,b=pivots[-2:]
  ra=rsi(closes[:a+1]);rb=rsi(closes[:b+1])
  if ra is not None and rb is not None and blocks[b]["l"]<blocks[a]["l"] and rb>ra:
   reasons.append("confirmed_bullish_rsi_divergence")
 return reasons

def replay(r,bars,limit,threshold,kind,breakeven,cost):
 try:
  t=minute(r["model_time"]);entry=float(r["entry"]);sl=float(r["stop_loss"]);tp=float(r["take_profit"])
  if not all(map(math.isfinite,(entry,sl,tp))) or not tp<entry<sl:raise ValueError()
 except (ValueError,KeyError,TypeError):return {"status":"INVALID"}
 risk=sl-entry;early=entry-threshold*risk
 armed=False;pending=None;partial=None;remaining_sl=sl;reason=None
 for step in range(1,limit+1):
  m=t+step;b=bars.get(m)
  if b is None:return {"status":"CENSORED_GAP","partial":partial}
  if pending is not None:
   # next-open execution; if already beyond stop, no favorable early fill
   if b["o"]>=sl:return {"status":"STOP_AT_PARTIAL_OPEN","partial":None,
                        "net_r":(entry-b["o"]-cost)/risk}
   partial={"minute":m,"price":b["o"],"reason":reason,
            "gross_r":(entry-b["o"])/risk}
   if partial["gross_r"]<=0:return {"status":"PARTIAL_NONPROFITABLE","partial":partial}
   remaining_sl=entry if breakeven else sl
   pending=None
  # Stop or TP inside same M1: do not invent path order.
  stop_hit=b["h"]>=remaining_sl;tp_hit=b["l"]<=tp
  if stop_hit and tp_hit:return {"status":"AMBIGUOUS_PROTECTIVE","partial":partial}
  if stop_hit or tp_hit:
   price=max(remaining_sl,b["o"]) if stop_hit else tp
   gross=(entry-price)/risk
   total=(gross if partial is None else 0.5*partial["gross_r"]+0.5*gross)
   # cost-per-oz is a full-position roundtrip approximation, not dynamic spread.
   return {"status":"STOP" if stop_hit else "TP","partial":partial,
           "net_r":round(total-cost/risk,6),"minutes":step}
  if partial is not None:continue
  if b["l"]<=entry-risk:armed=True
  if not armed:continue
  if kind=="fixed":
   if b["l"]<=early:
    # A target touch is not an executable next-open fill.
    pending="next_open";reason="fixed_target_touch"
  elif kind=="hybrid":
   if m5_reversal(bars,m):
    pending="next_open";reason=",".join(m5_reversal(bars,m))
 return {"status":"CENSORED_LIMIT","partial":partial}

def main():
 p=argparse.ArgumentParser()
 p.add_argument("--output",required=True)
 p.add_argument("--hours",type=int,default=24)
 p.add_argument("--cost-per-oz",type=float,default=0)
 a=p.parse_args()
 if not 1<=a.hours<=336 or a.cost_per_oz<0:p.error("invalid settings")
 out=Path(a.output)
 if out.exists():p.error("output exists")
 bars=load();journal=json.loads(JOURNAL.read_text())
 plans={"hold":("fixed",999,False),"fixed_1r_original":("fixed",1,False),
        "fixed_1r_be":("fixed",1,True),"fixed_1_5r_original":("fixed",1.5,False),
        "fixed_1_5r_be":("fixed",1.5,True),"hybrid_original":("hybrid",1,False),
        "hybrid_be":("hybrid",1,True)}
 results=[]
 for i,r in enumerate(journal,1):
  if str(r.get("side","")).upper()!="SELL":continue
  outcomes={k:replay(r,bars,a.hours*60,target,kind,be,a.cost_per_oz)
            for k,(kind,target,be) in plans.items()}
  results.append({"index":i,"model_time":r.get("model_time"),"outcomes":outcomes})
 summary={}
 for name in plans:
  completed=[x["outcomes"][name]["net_r"] for x in results if "net_r" in x["outcomes"][name]]
  paired=[(x["outcomes"][name]["net_r"],x["outcomes"]["hold"]["net_r"])
          for x in results if "net_r" in x["outcomes"][name] and "net_r" in x["outcomes"]["hold"]]
  summary[name]={"statuses":dict(Counter(x["outcomes"][name]["status"] for x in results)),
                 "partials":sum(x["outcomes"][name].get("partial") is not None for x in results),
                 "completed":len(completed),"mean_net_r_completed":round(mean(completed),6) if completed else None,
                 "paired_vs_hold":len(paired),
                 "mean_delta_r_vs_hold":round(mean(x-y for x,y in paired),6) if paired else None}
 report={"study":"ETP partial profit historical exploratory replay",
         "hours":a.hours,"cost_per_oz":a.cost_per_oz,"summary":summary,"signals":results,
         "limitations":["No C2 Raw or V3-A2 remainder integration yet; HOLD means protective SL/TP only",
         "No independent episode grouping or prospective validation",
         "No intra-minute path resolution; ambiguous SL/TP bars censored",
         "Next-open fill approximation, not broker execution",
         "No partial fills at same-bar target touch; costs are simplified",
         "Break-even stop is hypothetical, never applied to V9.4",
         "No live, paper, Telegram or intake changes"]}
 with out.open("x") as f:json.dump(report,f,indent=2);f.write("\n")
 print(json.dumps(summary,indent=2));print("REPORT",out)
if __name__=="__main__":main()
