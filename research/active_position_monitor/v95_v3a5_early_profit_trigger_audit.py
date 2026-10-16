"""Offline V3-A5 early-profit trigger study; no orders, alerts or services."""
import argparse,json,math
from pathlib import Path
from collections import Counter
from research.active_position_monitor.v95_62_sell_phase2b_features import load,JOURNAL,minute

def rsi(closes,n=14):
 if len(closes)<n+1:return None
 changes=[closes[i]-closes[i-1] for i in range(len(closes)-n,len(closes))]
 gain=sum(max(x,0) for x in changes)/n
 loss=sum(max(-x,0) for x in changes)/n
 return 100 if loss==0 else 100-100/(1+gain/loss)

def ema(values,n=20):
 if len(values)<n:return None
 result=sum(values[:n])/n
 for x in values[n:]:result=(2*x+(n-1)*result)/(n+1)
 return result

def study(signal,bars,max_minutes):
 try:
  t=minute(signal["model_time"])
  entry,sl,tp=[float(signal[k]) for k in ("entry","stop_loss","take_profit")]
  if not all(math.isfinite(v) for v in (entry,sl,tp)) or not tp<entry<sl:raise ValueError()
 except (ValueError,KeyError,TypeError):return {"status":"INVALID"}
 risk=sl-entry
 if any(t-i not in bars for i in range(100,0,-1)):return {"status":"NO_WARMUP"}
 hist=[bars[t-i] for i in range(100,0,-1)]
 events={k:None for k in ("fixed_1r","fixed_1_5r","hybrid")}
 # This scan observes completed M1 bars only; signals act no earlier than next M1 open.
 for step in range(1,max_minutes+1):
  b=bars.get(t+step)
  if b is None:return {"status":"CENSORED_GAP","events":events}
  if b["h"]>=sl and b["l"]<=tp:return {"status":"AMBIGUOUS_PROTECTIVE","events":events}
  if b["h"]>=sl:return {"status":"PROTECTIVE_SL","events":events}
  if b["l"]<=tp:return {"status":"PROTECTIVE_TP","events":events}
  hist.append(b)
  for label,threshold in (("fixed_1r",1),("fixed_1_5r",1.5)):
   if events[label] is None and b["l"]<=entry-threshold*risk:
    events[label]={"signal_minute":t+step,"target":entry-threshold*risk,"fill":"UNDETERMINED_INTRABAR"}
  # Completed M5 bars are formed from consecutive completed M1 bars.
  # EMA20 M5 close reversal is evaluated only on the M5 boundary.
  if events["hybrid"] is None and b["c"]<=entry-risk and (t+step+1)%5==0:
   end=t+step
   closes=[]
   for j in range(20):
    group=[bars.get(end-5*j-k) for k in range(4,-1,-1)]
    if any(x is None for x in group):break
    closes.append(group[-1]["c"])
   if len(closes)==20:
    avg=ema(list(reversed(closes)))
    if b["c"]>avg:
     events["hybrid"]={"signal_minute":end,"reason":"completed_m5_ema20_reclaim",
                       "fill":"NEXT_M1_OPEN_REQUIRED"}
  if all(v is not None for v in events.values()):return {"status":"TRIGGERS_OBSERVED","events":events}
 return {"status":"CENSORED_HORIZON","events":events}

def main():
 p=argparse.ArgumentParser()
 p.add_argument("--output",required=True)
 p.add_argument("--max-minutes",type=int,default=240)
 a=p.parse_args()
 if not 1<=a.max_minutes<=1440:p.error("max-minutes outside 1..1440")
 out=Path(a.output)
 if out.exists():p.error("output exists")
 bars=load()
 rows=json.loads(JOURNAL.read_text())
 result=[{"index":i,"study":study(r,bars,a.max_minutes)} for i,r in enumerate(rows,1) if r.get("side")=="SELL"]
 report={"mode":"OFFLINE_RESEARCH_ONLY","partial_fraction_proposed":0.5,
         "signals":len(result),"statuses":dict(Counter(x["study"]["status"] for x in result)),
         "results":result,
         "limitations":["Trigger audit only: no fills, net R, remainder PnL or strategy ranking",
         "RSI divergence requires separate causal swing-pivot implementation",
         "No changes to V9.4 LIVE, V9.5 PAPER, C2 Raw, V3-A2, timer or Telegram"]}
 with out.open("x") as f:json.dump(report,f,indent=2);f.write("\n")
 print(json.dumps({k:v for k,v in report.items() if k!="results"},indent=2))
if __name__=="__main__":main()
