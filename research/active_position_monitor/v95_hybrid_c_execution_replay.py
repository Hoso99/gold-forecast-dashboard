"""Isolated research-only Hybrid C1/C2 paper execution replay.

Completed M1 candles are evaluated at their CLOSE. Signal fills occur at
NEXT M1 OPEN. Protective touches use OHLC with conservative gap handling;
both SL/TP in one bar => AMBIGUOUS and stop scoring. No live integrations.
C2 delays first discretionary exit candidate by up to two further completed
M1 bars; rejection during that interval cancels it. A second candidate
confirms earlier. The next-open fill may differ from signal close.
"""
import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from research.active_position_monitor.v95_hybrid_c_research import HybridC

EXIT = {"ADAPTIVE_EXIT", "EARLY_PROFIT_EXIT"}
REJECT = "FALSE_REVERSAL_HOLD"

def load(db, start, end):
    path=Path(db).resolve()
    if not path.is_file(): raise ValueError("database missing")
    with sqlite3.connect(path.as_uri()+"?mode=ro",uri=True) as con:
        rows=con.execute("SELECT minute,open,high,low,close FROM candles WHERE minute>=? AND minute<? ORDER BY minute",(start,end)).fetchall()
    bars={}
    for stamp,o,h,l,c in rows:
        dt=datetime.fromisoformat(stamp.replace("Z","+00:00"))
        if dt.tzinfo is None or dt.second or dt.microsecond: raise ValueError("invalid timestamp")
        minute=int(dt.astimezone(timezone.utc).timestamp()//60)
        if minute in bars: raise ValueError("duplicate minute")
        bars[minute]={"o":float(o),"h":float(h),"l":float(l),"c":float(c)}
    start_min=int(datetime.fromisoformat(start.replace("Z","+00:00")).timestamp()//60)
    end_min=int(datetime.fromisoformat(end.replace("Z","+00:00")).timestamp()//60)
    missing=[m for m in range(start_min,end_min) if m not in bars]
    if missing: raise ValueError(f"{len(missing)} missing M1 candles; replay refused")
    return [(m,bars[m]) for m in range(start_min,end_min)]

def replay(rows,variant,entry=4144.57,stop=4174.64,target=4084.43,cost=0.0):
    model=HybridC()
    model.cfg.cost_per_oz=cost
    model.open_initial(entry,stop,target)
    trades=[]
    pending=None
    current_entry=entry
    current_stop=stop
    current_target=target
    last_exit=None
    events=[]
    for index,(minute,bar) in enumerate(rows):
        timestamp=datetime.fromtimestamp((minute+1)*60,timezone.utc).isoformat()
        # Pending discretionary orders fill at this M1 OPEN, before evaluating bar.
        if pending is not None and model.position is not None:
            price=bar["o"]
            r=(current_entry-price-cost)/(current_stop-current_entry)
            trades.append({"type":"EXIT","signal":pending["signal"],"fill_minute":minute,"price":round(price,5),"r":round(r,5),"variant":variant})
            model.confirm_paper_exit()
            last_exit=minute
            pending=None
        # Pending reentry at this bar OPEN: recompute SL/TP for actual fill,
        # preserving structural stop and min 2R. No fill if gap invalidates stop.
        elif pending is not None and model.position is None:
            price=bar["o"]
            stop_ref=pending["stop"]
            if price < stop_ref and model.reentry_left>0:
                target_ref=price-2*(stop_ref-price)
                model.confirm_paper_reentry(price,stop_ref,target_ref)
                current_entry,current_stop,current_target=price,stop_ref,target_ref
                trades.append({"type":"REENTRY","signal":pending["signal"],"fill_minute":minute,"price":round(price,5),"stop":round(stop_ref,5),"target":round(target_ref,5)})
            else:
                events.append({"time":timestamp,"action":"REENTRY_CANCELLED_GAP_OR_WINDOW"})
            pending=None
        # No trading during unknown initial position history: this is a scenario.
        decision=model.on_completed_m1(bar)
        action=decision["action"]
        if action in EXIT or action in (REJECT,"PROTECTIVE_SL","PROTECTIVE_TP","INCONCLUSIVE_SL_TP_ORDER","REENTRY_CANDIDATE"):
            events.append({"time":timestamp,"action":action,"r_reference":decision.get("r_reference")})
        if action.startswith("PROTECTIVE_") or action=="INCONCLUSIVE_SL_TP_ORDER":
            if action=="INCONCLUSIVE_SL_TP_ORDER":
                return {"variant":variant,"status":"AMBIGUOUS_PROTECTIVE_TOUCH","trades":trades,"events":events}
            level=current_stop if action=="PROTECTIVE_SL" else current_target
            # For a SELL stop, opening above stop means a worse fill.
            # For TP, opening below target may improve fill.
            price=max(level,bar["o"]) if action=="PROTECTIVE_SL" else min(level,bar["o"])
            r=(current_entry-price-cost)/(current_stop-current_entry)
            trades.append({"type":action,"fill_minute":minute,"price":round(price,5),"r":round(r,5)})
            return {"variant":variant,"status":"PROTECTIVE_EXIT","trades":trades,"events":events}
        if model.position is not None:
            if variant=="C1":
                if action in EXIT and index+1<len(rows):
                    pending={"kind":"exit","signal":timestamp}
            else:
                if action==REJECT:
                    candidate=None
                elif action in EXIT:
                    if 'candidate' not in locals() or candidate is None:
                        candidate={"minute":minute,"signal":timestamp,"count":1}
                    else:
                        candidate["count"]+=1
                if 'candidate' in locals() and candidate is not None:
                    if candidate["count"]>=2 or minute-candidate["minute"]>=2:
                        if action!=REJECT and index+1<len(rows):
                            pending={"kind":"exit","signal":timestamp}
                        candidate=None
        elif action=="REENTRY_CANDIDATE" and index+1<len(rows):
            pending={"kind":"reentry","signal":timestamp,"stop":decision["stop_reference"]}
    return {"variant":variant,"status":"END_OF_DATA","trades":trades,"events":events}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--db",required=True)
    parser.add_argument("--start",default="2026-10-15T15:00:00+00:00")
    parser.add_argument("--end",default="2026-10-15T17:55:00+00:00")
    parser.add_argument("--cost-per-oz",type=float,default=0.0)
    args=parser.parse_args()
    if args.cost_per_oz<0: parser.error("cost cannot be negative")
    rows=load(args.db,args.start,args.end)
    print("SCENARIO: SELL assumed open at start; original entry timestamp unverified.")
    print("No live orders; costs only if supplied; no economic-event feed.")
    for variant in ("C1","C2"):
        result=replay(rows,variant,cost=args.cost_per_oz)
        print("\n",variant,"status:",result["status"])
        for trade in result["trades"]: print("TRADE",trade)
        for event in result["events"]: print("EVENT",event)
if __name__=="__main__":
    main()
