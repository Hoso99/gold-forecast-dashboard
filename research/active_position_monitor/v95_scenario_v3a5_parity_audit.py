"""V3-A5 research-only M1 parity audit: historical CSV versus Biquote SQLite.

No modifications to either source; no exits, scheduler, or trade signals.
The historical power metric is candle-body power, not traded volume.
"""
import argparse,csv,json,sqlite3,statistics
from datetime import datetime,timezone,timedelta
from pathlib import Path
def stamp(s):
 d=datetime.fromisoformat(str(s).replace("Z","+00:00"))
 if d.tzinfo is None:raise ValueError("naive time")
 d=d.astimezone(timezone.utc)
 if d.second or d.microsecond:raise ValueError("nonminute")
 return d
def bar(o,h,l,c):
 x=tuple(float(v) for v in (o,h,l,c))
 if not (all(v==v and abs(v)<1e10 for v in x) and x[1]>=max(x[0],x[3]) and x[2]<=min(x[0],x[3])):raise ValueError("bad OHLC")
 return x
def power(seq):
 up=sum(max(x[3]-x[0],0) for x in seq)
 down=sum(max(x[0]-x[3],0) for x in seq)
 return 100*up/(up+down) if up+down else 50.
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--db",default="/home/ubuntu/v95-detector-dev/research/feed_validation/biquote_m1.sqlite3")
 p.add_argument("--historical",nargs="+",default=["/home/ubuntu/v95-detector-dev/candle_dynamics_m1_v94.csv","/home/ubuntu/v95-detector-dev/research/data/v94_forward_m1.csv"])
 p.add_argument("--output",required=True)
 a=p.parse_args()
 out=Path(a.output)
 if out.exists():p.error("output exists")
 hist={};conflicts=[];invalid_hist=0
 for filename in a.historical:
  with open(filename,newline="",encoding="utf-8-sig") as f:
   for r in csv.DictReader(f):
    try:t=stamp(r["datetime"]);v=bar(r["open"],r["high"],r["low"],r["close"])
    except (KeyError,ValueError,TypeError,OverflowError):invalid_hist+=1;continue
    if t in hist and hist[t]!=v:conflicts.append(t.isoformat())
    else:hist[t]=v
 con=sqlite3.connect("file:"+str(Path(a.db).resolve())+"?mode=ro",uri=True)
 try:rows=con.execute("SELECT minute,open,high,low,close FROM candles ORDER BY minute").fetchall()
 finally:con.close()
 live={};invalid_live=0;duplicate_live=0
 for t,o,h,l,c in rows:
  try:key=stamp(t);v=bar(o,h,l,c)
  except (ValueError,TypeError,OverflowError):invalid_live+=1;continue
  if key in live:duplicate_live+=1
  live[key]=v
 overlap=sorted(set(hist)&set(live))
 diffs={k:[] for k in ("open","high","low","close")}
 exact=0;all_tol=0;examples=[]
 for t in overlap:
  a1=hist[t];b1=live[t];d=[abs(x-y) for x,y in zip(a1,b1)]
  if all(v==0 for v in d):exact+=1
  if all(v<=0.1 for v in d):all_tol+=1
  for key,val in zip(diffs,d):diffs[key].append(val)
  if len(examples)<8 and max(d)>0.1:examples.append({"minute":t.isoformat(),"historical":a1,"biquote":b1,"max_abs_delta":round(max(d),6)})
 power_pairs=[]
 for t in overlap:
  # Strict five consecutive M1 bars in BOTH sources; no gap-filling.
  keys=[t-timedelta(minutes=i) for i in range(4,-1,-1)]
  if all(k in hist and k in live for k in keys):
   power_pairs.append((t,power([hist[k] for k in keys]),power([live[k] for k in keys])))
 pd=[abs(a-b) for _,a,b in power_pairs]
 report={"study":"V3-A5 historical versus Biquote M1 parity","historical_rows_unique":len(hist),
  "biquote_rows_unique":len(live),"historical_invalid":invalid_hist,"biquote_invalid":invalid_live,
  "historical_conflicting_minutes":len(set(conflicts)),"historical_conflict_examples":conflicts[:8],
  "biquote_duplicate_minutes":duplicate_live,
  "historical_first":min(hist).isoformat() if hist else None,
  "historical_last":max(hist).isoformat() if hist else None,
  "biquote_first":min(live).isoformat() if live else None,
  "biquote_last":max(live).isoformat() if live else None,
  "overlapping_minutes":len(overlap),"exact_ohlc_matches":exact,
  "ohlc_all_fields_within_0_1_usd":all_tol,
  "price_absolute_differences":{k:{"mean":round(statistics.mean(v),6) if v else None,"max":round(max(v),6) if v else None} for k,v in diffs.items()},
  "five_minute_power_pairs":len(power_pairs),
  "five_minute_power_abs_pp":{"mean":round(statistics.mean(pd),5) if pd else None,"max":round(max(pd),5) if pd else None,
   "within_5pp":sum(x<=5 for x in pd),"within_10pp":sum(x<=10 for x in pd)},
  "sample_price_mismatches":examples,
  "parity_conclusion":"INSUFFICIENT_OVERLAP" if not overlap else "MEASURED_NOT_CERTIFIED",
  "limitations":["OHLC equivalence is not automatically established by small average errors",
   "No synthetic bars, future data, trading, or live service changes",
   "Price-body power is not volume-based order-flow pressure",
   "C2 state-dependent exit decisions require separate event-level replay parity checks",
   "Gaps and source-time differences can invalidate individual replay windows"]}
 with out.open("x") as f:json.dump(report,f,indent=2);f.write("\n")
 print(json.dumps({k:v for k,v in report.items() if k not in ("sample_price_mismatches","limitations","historical_conflict_examples")},indent=2))
 print("REPORT",out)
if __name__=="__main__":main()
