"""Read-only ETP-4 trigger freshness audit.

Checks whether prior ETP partials were based on newly completed M5
EMA/RSI evidence AFTER +1R arming. Does not claim broker fills.
"""
import argparse,json
from pathlib import Path
from collections import Counter
from research.active_position_monitor.v95_62_sell_phase2b_features import load,JOURNAL,minute,iso
from research.active_position_monitor.v95_v3a5_etp_partial_replay import ema,rsi

def signals_at(bars,end):
 if (end+1)%5:return set()
 blocks=[]
 for finish in range(end-5*27,end+1,5):
  seq=[bars.get(j) for j in range(finish-4,finish+1)]
  if any(x is None for x in seq):return set()
  blocks.append({"l":min(x["l"] for x in seq),"c":seq[-1]["c"]})
 closes=[x["c"] for x in blocks]
 signals=set()
 prev=ema(closes[:-1],20);cur=ema(closes,20)
 if prev is not None and cur is not None and closes[-2]<=prev and closes[-1]>cur:
  signals.add("m5_ema20_cross_up")
 pivots=[i for i in range(2,len(blocks)-2) if
         all(blocks[i]["l"]<blocks[j]["l"] for j in (i-2,i-1,i+1,i+2))]
 if len(pivots)>=2:
  a,b=pivots[-2:]
  ra=rsi(closes[:a+1]);rb=rsi(closes[:b+1])
  if ra is not None and rb is not None and blocks[b]["l"]<blocks[a]["l"] and rb>ra:
   # A newly confirmed pivot at index len(blocks)-3; do not re-fire older divergence.
   if b==len(blocks)-3:signals.add("fresh_bullish_rsi_divergence")
 return signals

def audit(r,bars,max_minutes):
 t=minute(r["model_time"]);entry=float(r["entry"]);sl=float(r["stop_loss"]);tp=float(r["take_profit"])
 if not tp<entry<sl:return {"status":"INVALID"}
 armed_at=None;first=None
 for m in range(t+1,t+max_minutes+1):
  b=bars.get(m)
  if b is None:return {"status":"GAP","armed_at":iso(armed_at) if armed_at else None,"first":first}
  if b["h"]>=sl or b["l"]<=tp:
   return {"status":"PROTECTIVE_EXIT","armed_at":iso(armed_at) if armed_at else None,"first":first}
  if armed_at is None and b["l"]<=entry-(sl-entry):armed_at=m
  if armed_at is not None and m>armed_at:
   s=signals_at(bars,m)
   if s:
    first={"decision_minute":iso(m),"next_open_minute":iso(m+1),
           "reasons":sorted(s),"minutes_after_arm":m-armed_at}
    return {"status":"FRESH_CONFIRMATION","armed_at":iso(armed_at),"first":first}
 return {"status":"HORIZON","armed_at":iso(armed_at) if armed_at else None,"first":first}

def main():
 p=argparse.ArgumentParser()
 p.add_argument("--prior-report",required=True)
 p.add_argument("--output",required=True)
 p.add_argument("--hours",type=int,default=24)
 a=p.parse_args()
 if a.hours<1 or a.hours>336:p.error("invalid hours")
 output=Path(a.output)
 if output.exists():p.error("output exists")
 old=json.loads(Path(a.prior_report).read_text())
 rows=json.loads(JOURNAL.read_text());bars=load()
 details=[]
 for item in old["signals"]:
  i=item["index"];previous=item["outcomes"]["hybrid_be"]
  now=audit(rows[i-1],bars,a.hours*60)
  details.append({"index":i,"previous_partial":previous.get("partial"),
                  "previous_status":previous["status"],"fresh_audit":now})
 summary={"signals":len(details),
          "previous_partials":sum(bool(x["previous_partial"]) for x in details),
          "fresh_confirmation_candidates":sum(x["fresh_audit"]["status"]=="FRESH_CONFIRMATION" for x in details),
          "fresh_reason_counts":dict(Counter(reason for x in details for reason in
             (x["fresh_audit"].get("first") or {}).get("reasons",[]))),
          "previous_partials_without_fresh_confirmation":sum(bool(x["previous_partial"]) and
             x["fresh_audit"]["status"]!="FRESH_CONFIRMATION" for x in details),
          "previous_partials_with_different_trigger_time":sum(
             bool(x["previous_partial"]) and x["fresh_audit"]["first"] is not None and
             x["previous_partial"]["minute"]!=minute(x["fresh_audit"]["first"]["next_open_minute"])
             for x in details)}
 report={"study":"ETP-4 freshness-only audit","summary":summary,"signals":details,
         "limitations":["Fresh confirmation is a candidate only, not a simulated fill or PnL",
         "Requires completed M5 evidence strictly after +1R arming",
         "RSI pivot confirmed by two subsequent completed M5 candles",
         "M1 OHLC cannot resolve intrabar sequence; stop/TP checked first",
         "M5 EMA and RSI research definitions are exploratory, not tuned",
         "No service, Telegram, V9.4, V9.5 or timer modifications"]}
 with output.open("x") as f:json.dump(report,f,indent=2);f.write("\n")
 print(json.dumps(summary,indent=2));print("REPORT",output)
if __name__=="__main__":main()
