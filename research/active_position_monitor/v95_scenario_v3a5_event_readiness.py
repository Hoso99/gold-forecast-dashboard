"""V3-A5 prospective episode readiness audit. Read-only; NO replay or trades.

Only records in the frozen-baseline append-only intake ledger are considered.
Readiness is NOT data-source parity, broker fill verification, or exit scoring.
"""
import argparse,json,sqlite3,math
from pathlib import Path
from datetime import datetime,timezone,timedelta
from collections import Counter

def dt(value):
 d=datetime.fromisoformat(str(value).replace("Z","+00:00"))
 if d.tzinfo is None:raise ValueError("naive timestamp")
 d=d.astimezone(timezone.utc)
 if d.second or d.microsecond:raise ValueError("not minute aligned")
 return d
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--db",default="/home/ubuntu/v95-detector-dev/research/feed_validation/biquote_m1.sqlite3")
 p.add_argument("--ledger",default="/home/ubuntu/v95-private-export/research/v3a5_forward/observations.jsonl")
 p.add_argument("--baseline",default="/tmp/v95_scenario_v3a5_baseline_oct16.json")
 p.add_argument("--output",required=True)
 p.add_argument("--warmup",type=int,default=100)
 p.add_argument("--max-confirmation-minutes",type=int,default=5)
 a=p.parse_args()
 if a.warmup<100 or a.max_confirmation_minutes!=5:p.error("frozen research parameters require warmup >=100 and five-minute bound")
 out=Path(a.output)
 if out.exists():p.error("output already exists")
 cutoff=datetime.fromisoformat(json.loads(Path(a.baseline).read_text())["created_at_utc"].replace("Z","+00:00")).astimezone(timezone.utc)
 ledger=Path(a.ledger)
 records=[json.loads(x) for x in ledger.read_text().splitlines() if x.strip()] if ledger.exists() else []
 con=sqlite3.connect("file:"+str(Path(a.db).resolve())+"?mode=ro",uri=True)
 try:rows=con.execute("SELECT minute,open,high,low,close FROM candles ORDER BY minute").fetchall()
 finally:con.close()
 bars={};bad=0;duplicates=0
 for time,o,h,l,c in rows:
  try:
   t=dt(time);v=tuple(float(x) for x in (o,h,l,c))
   if not all(math.isfinite(x) for x in v) or v[1]<max(v[0],v[3]) or v[2]>min(v[0],v[3]):raise ValueError("bad OHLC")
  except (ValueError,TypeError,OverflowError):bad+=1;continue
  if t in bars:duplicates+=1
  bars[t]=v
 latest=max(bars) if bars else None
 seen=set();episodes=[]
 for r in records:
  identity=r.get("identity")
  if identity in seen:continue
  seen.add(identity)
  if r.get("classification")!="PROSPECTIVE_CANDIDATE":continue
  row={"identity":identity,"model_time":r.get("model_time"),"first_seen_utc":r.get("first_seen_utc"),"status":None}
  try:
   t=dt(r["model_time"]);seen_at=datetime.fromisoformat(r["first_seen_utc"].replace("Z","+00:00")).astimezone(timezone.utc)
   entry,sl,tp=[float(r[k]) for k in ("entry","stop_loss","take_profit")]
   if not all(math.isfinite(x) for x in (entry,sl,tp)) or not tp<entry<sl or t<=cutoff:raise ValueError("invalid prospective SELL")
  except (ValueError,TypeError,KeyError,OverflowError) as exc:
   row.update(status="INVALID_EPISODE",reason=str(exc));episodes.append(row);continue
  lag=(seen_at-t).total_seconds()/60
  row["first_seen_delay_minutes"]=round(lag,2)
  # Late-discovered journal signals cannot be asserted as real-time observed.
  if lag>1:row.update(status="LATE_DISCOVERY",reason="first observed after signal-minute boundary; do not backdate")
  elif lag<0:row.update(status="TIMESTAMP_INCONSISTENCY",reason="first seen before model_time")
  else:row["status"]="TIMELY_CANDIDATE"
  missing=[(t-timedelta(minutes=i)).isoformat() for i in range(a.warmup,0,-1) if t-timedelta(minutes=i) not in bars]
  row["warmup_missing_count"]=len(missing)
  row["warmup_missing_examples"]=missing[:5]
  if row["status"]=="TIMELY_CANDIDATE":
   if missing:row.update(status="NO_CONTIGUOUS_WARMUP")
   elif latest is None or latest<t+timedelta(minutes=1):row.update(status="AWAITING_POST_ENTRY_M1")
   else:
    # Data availability is assessed through current observation, without
    # guessing when either frozen algorithm would request an exit.
    last=min(latest,t+timedelta(minutes=a.max_confirmation_minutes+2))
    missing_post=[(t+timedelta(minutes=i)).isoformat() for i in range(1,int((last-t).total_seconds()/60)+1) if t+timedelta(minutes=i) not in bars]
    row["post_entry_missing_count"]=len(missing_post)
    row["post_entry_missing_examples"]=missing_post[:5]
    row["next_open_available"]=t+timedelta(minutes=1) in bars
    if missing_post:row.update(status="POST_ENTRY_GAP")
    elif not row["next_open_available"]:row.update(status="NEXT_OPEN_MISSING")
    elif latest<t+timedelta(minutes=a.max_confirmation_minutes+2):row.update(status="OBSERVATION_INCOMPLETE")
    else:row.update(status="DATA_WINDOW_READY_UNSCORED")
  episodes.append(row)
 report={"study":"V3-A5 prospective event-level data readiness (no scoring)",
  "checked_at_utc":datetime.now(timezone.utc).isoformat(),"baseline_cutoff":cutoff.isoformat(),
  "ledger_records":len(records),"prospective_unique":len(episodes),
  "status_counts":dict(Counter(x["status"] for x in episodes)),
  "biquote_valid_rows":len(bars),"biquote_invalid_rows":bad,"biquote_duplicate_rows":duplicates,
  "latest_biquote_minute":latest.isoformat() if latest else None,
  "shadow_exit_engine":"NOT_ENABLED","episodes":episodes,
  "limitations":["No event-level C2 or V3-A2 replay; this is data readiness only",
   "No OHLC source parity due to zero overlapping historical minutes",
   "Data-window-ready is not proof of future exit-price availability at an unknown request time",
   "Strict first-seen timing is intentionally conservative; late signals remain excluded",
   "No broker fills, live-model modifications, scheduler, or collector changes"]}
 with out.open("x") as f:json.dump(report,f,indent=2);f.write("\n")
 print(json.dumps({k:v for k,v in report.items() if k not in ("episodes","limitations")},indent=2))
 print("REPORT",out)
if __name__=="__main__":main()
