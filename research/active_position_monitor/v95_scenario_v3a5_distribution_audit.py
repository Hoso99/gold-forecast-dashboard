"""V3-A5 distribution diagnostic, research-only and read-only.

Non-overlapping historical V9.4 CSV and Biquote SQLite. Distribution
comparison does not establish data-source parity or causal equivalence.
"""
import argparse,csv,json,math,sqlite3,statistics
from collections import Counter
from datetime import datetime,timezone,timedelta
from pathlib import Path

def ts(s):
 d=datetime.fromisoformat(str(s).replace("Z","+00:00"))
 if d.tzinfo is None:raise ValueError("naive timestamp")
 d=d.astimezone(timezone.utc)
 if d.second or d.microsecond:raise ValueError("non-minute timestamp")
 return d
def candle(o,h,l,c):
 x=tuple(float(v) for v in (o,h,l,c))
 if not all(math.isfinite(v) for v in x) or x[1]<max(x[0],x[3]) or x[2]>min(x[0],x[3]):
  raise ValueError("invalid OHLC")
 return x
def quantile(values,q):
 if not values:return None
 v=sorted(values);idx=(len(v)-1)*q;lo=int(idx);hi=min(lo+1,len(v)-1)
 return round(v[lo]+(v[hi]-v[lo])*(idx-lo),6)
def stats(values):
 return {"n":len(values),"mean":round(statistics.mean(values),6) if values else None,
  "median":quantile(values,.5),"p10":quantile(values,.1),"p90":quantile(values,.9),
  "p99":quantile(values,.99),"max":round(max(values),6) if values else None}
def power(bars):
 up=sum(max(x[3]-x[0],0) for x in bars)
 down=sum(max(x[0]-x[3],0) for x in bars)
 return 100*up/(up+down) if up+down else 50
def load_csv(paths):
 bars={};invalid=0;conflicts=0
 for path in paths:
  with open(path,newline="",encoding="utf-8-sig") as f:
   for r in csv.DictReader(f):
    try:t=ts(r["datetime"]);b=candle(r["open"],r["high"],r["low"],r["close"])
    except (ValueError,KeyError,TypeError,OverflowError):invalid+=1;continue
    if t in bars and bars[t]!=b:conflicts+=1
    else:bars[t]=b
 return bars,invalid,conflicts
def load_db(path):
 con=sqlite3.connect("file:"+str(Path(path).resolve())+"?mode=ro",uri=True)
 try:rows=con.execute("SELECT minute,open,high,low,close FROM candles ORDER BY minute").fetchall()
 finally:con.close()
 bars={};invalid=0;duplicates=0
 for t,o,h,l,c in rows:
  try:t=ts(t);b=candle(o,h,l,c)
  except (ValueError,TypeError,OverflowError):invalid+=1;continue
  if t in bars:duplicates+=1
  bars[t]=b
 return bars,invalid,duplicates
def measure(bars):
 times=sorted(bars);gaps=[]
 for a,b in zip(times,times[1:]):
  missing=int((b-a).total_seconds()/60)-1
  if missing>0:gaps.append(missing)
 ranges=[b[1]-b[2] for b in bars.values()]
 bodies=[abs(b[3]-b[0]) for b in bars.values()]
 powers5=[];powers10=[];valid100=0
 # contiguous runs are evaluated without interpolating any missing minute
 run=[]
 prev=None
 for t in times:
  if prev is None or t-prev!=timedelta(minutes=1):run=[]
  run.append(bars[t])
  if len(run)>100:run.pop(0)
  if len(run)>=5:powers5.append(power(run[-5:]))
  if len(run)>=10:powers10.append(power(run[-10:]))
  if len(run)>=100:valid100+=1
  prev=t
 return {"candles":len(times),"first_utc":times[0].isoformat() if times else None,
  "last_utc":times[-1].isoformat() if times else None,
  "gaps":len(gaps),"missing_minutes":sum(gaps),"largest_gap_minutes":max(gaps,default=0),
  "complete_100_minute_warmup_endpoints":valid100,
  "range_usd":stats(ranges),"absolute_body_usd":stats(bodies),
  "body_buy_power_5_pct":stats(powers5),"body_buy_power_10_pct":stats(powers10),
  "power5_above_75_pct":round(100*sum(v>=75 for v in powers5)/len(powers5),3) if powers5 else None,
  "power5_window_count":len(powers5)}
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--db",default="/home/ubuntu/v95-detector-dev/research/feed_validation/biquote_m1.sqlite3")
 p.add_argument("--historical",nargs="+",default=["/home/ubuntu/v95-detector-dev/candle_dynamics_m1_v94.csv","/home/ubuntu/v95-detector-dev/research/data/v94_forward_m1.csv"])
 p.add_argument("--output",required=True)
 a=p.parse_args()
 output=Path(a.output)
 if output.exists():p.error("output exists; choose a fresh name")
 old,old_bad,old_conf=load_csv(a.historical)
 new,new_bad,new_dups=load_db(a.db)
 report={"study":"V3-A5 nonoverlapping M1 distribution diagnostic",
  "checked_at_utc":datetime.now(timezone.utc).isoformat(),
  "historical":measure(old),"biquote":measure(new),
  "integrity":{"historical_invalid":old_bad,"historical_conflicts":old_conf,
    "biquote_invalid":new_bad,"biquote_duplicate_minutes":new_dups},
  "overlapping_minutes":len(set(old)&set(new)),
  "comparison_status":"DISTRIBUTION_ONLY_NOT_PARITY",
  "limitations":["Different dates and market regimes confound distribution comparisons",
    "Body power is price-based, not traded order flow",
    "No claim of identical C2 or V3-A2 event decisions",
    "No price interpolation across missing M1 candles",
    "100-minute endpoints indicate coverage, not guaranteed signal-time eligibility",
    "No trading, broker, Telegram, collector, or live-model changes"]}
 with output.open("x") as f:json.dump(report,f,indent=2);f.write("\n")
 print(json.dumps({k:v for k,v in report.items() if k!="limitations"},indent=2))
 print("REPORT",output)
if __name__=="__main__":main()
