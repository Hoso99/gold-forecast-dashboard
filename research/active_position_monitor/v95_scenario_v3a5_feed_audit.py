"""V3-A5 Biquote M1 coverage audit. Read-only; does not score trades.

Reports timestamp integrity, completed UTC minute bars, gap counts, and
coverage for new prospective intake records. Does not treat Biquote OHLC
as the original historical candle-dynamics pressure source.
"""
import argparse,json,sqlite3
from collections import Counter
from datetime import datetime,timezone,timedelta
from pathlib import Path

def parse(t):
 d=datetime.fromisoformat(str(t).replace("Z","+00:00"))
 if d.tzinfo is None:raise ValueError("naive timestamp")
 return d.astimezone(timezone.utc)
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--db",default="/home/ubuntu/v95-detector-dev/research/feed_validation/biquote_m1.sqlite3")
 p.add_argument("--ledger",default="/home/ubuntu/v95-private-export/research/v3a5_forward/observations.jsonl")
 p.add_argument("--warmup",type=int,default=100)
 p.add_argument("--forward-minutes",type=int,default=15)
 p.add_argument("--output",default="/tmp/v95_v3a5_biquote_coverage.json")
 a=p.parse_args()
 if a.warmup<1 or a.forward_minutes<1:p.error("positive windows required")
 out=Path(a.output)
 if out.exists():p.error("output already exists; choose a new filename")
 uri="file:"+str(Path(a.db).resolve())+"?mode=ro"
 con=sqlite3.connect(uri,uri=True)
 try:
  schema=con.execute("PRAGMA table_info(candles)").fetchall()
  fields={r[1] for r in schema}
  required={"minute","open","high","low","close"}
  if not required<=fields:raise RuntimeError("missing columns: "+str(required-fields))
  rows=con.execute("SELECT minute,open,high,low,close FROM candles ORDER BY minute").fetchall()
 finally:con.close()
 now=datetime.now(timezone.utc)
 times=[];bad=0;nonminute=0;future=0;invalid_ohlc=0
 for minute,o,h,l,c in rows:
  try:
   t=parse(minute)
   if t.second or t.microsecond:nonminute+=1;continue
   vals=[float(v) for v in (o,h,l,c)]
   if not (all(v==v and abs(v)<1e10 for v in vals) and vals[2]>=max(vals[0],vals[3]) and vals[1]<=min(vals[0],vals[3]) and vals[2]>=vals[1]):invalid_ohlc+=1;continue
   if t>now:future+=1;continue
   times.append(t)
  except (ValueError,TypeError,OverflowError):bad+=1
 counts=Counter(times);unique=sorted(counts)
 gaps=[]
 for prev,curr in zip(unique,unique[1:]):
  missing=int((curr-prev).total_seconds()/60)-1
  if missing>0:gaps.append({"after":prev.isoformat(),"before":curr.isoformat(),"missing":missing})
 latest=unique[-1] if unique else None
 # A candle at minute T is complete only after T+1 minute UTC.
 complete={t for t in unique if t+timedelta(minutes=1)<=now and counts[t]==1}
 ledger=Path(a.ledger);observations=[]
 if ledger.exists():
  for line in ledger.read_text().splitlines():
   if line.strip():
    rec=json.loads(line)
    if rec.get("classification")=="PROSPECTIVE_CANDIDATE":
     t=parse(rec["model_time"])
     needed=[t+timedelta(minutes=i) for i in range(-a.warmup,0)]
     forward=[t+timedelta(minutes=i) for i in range(1,a.forward_minutes+1)]
     observations.append({"identity":rec["identity"],"model_time":rec["model_time"],
       "first_seen_utc":rec["first_seen_utc"],
       "discovery_delay_minutes":round((parse(rec["first_seen_utc"])-t).total_seconds()/60,2),
       "warmup_complete":all(x in complete for x in needed),
       "forward_window_complete":all(x in complete for x in forward),
       "missing_warmup_minutes":sum(x not in complete for x in needed),
       "missing_forward_minutes":sum(x not in complete for x in forward),
       "eligible_for_shadow_scoring":False,
       "reason":"Biquote candle completeness alone does not establish equivalence to historical pressure inputs or timely execution"})
 report={"study":"V3-A5 Biquote M1 read-only coverage audit","checked_at_utc":now.isoformat(),
  "db":str(Path(a.db)),"total_rows":len(rows),"valid_unique_minute_rows":len(unique),
  "completed_unique_minute_rows":len(complete),
  "first_minute_utc":unique[0].isoformat() if unique else None,
  "latest_minute_utc":latest.isoformat() if latest else None,
  "latest_age_minutes":round((now-latest).total_seconds()/60,2) if latest else None,
  "duplicate_minutes":sum(n-1 for n in counts.values() if n>1),
  "bad_timestamps":bad,"nonminute_timestamps":nonminute,
  "invalid_ohlc":invalid_ohlc,"future_rows":future,
  "gaps_over_one_minute":len(gaps),"missing_minutes_across_gaps":sum(x["missing"] for x in gaps),
  "largest_gap_minutes":max((x["missing"] for x in gaps),default=0),
  "recent_gaps":gaps[-8:],
  "prospective_candidates":len(observations),"candidate_coverage":observations,
  "shadow_exit_engine":"NOT_ENABLED",
  "limitations":["Market closure gaps are included; gaps are not automatically feed outages",
    "M1 bar close is available only after its minute ends",
    "No original historical candle-dynamics pressure parity test",
    "No hypothetical fills or trading orders generated",
    "Historical C2/V3-A2 replay remains frozen"]}
 with out.open("x") as f:json.dump(report,f,indent=2);f.write("\n")
 print(json.dumps({k:v for k,v in report.items() if k not in ("recent_gaps","candidate_coverage","limitations")},indent=2))
 print("REPORT",out)
if __name__=="__main__":main()
