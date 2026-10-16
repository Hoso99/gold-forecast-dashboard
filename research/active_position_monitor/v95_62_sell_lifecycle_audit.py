"""Research-only V9.4 SELL journal lifecycle audit. No live actions.

Reconstructs observable SL/TP first touches, data gaps, censoring and C2 Raw
first exit requests. Entry is a journal reference, NOT a verified broker fill.
"""
import argparse, csv, json
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter

ROOT = Path("/home/ubuntu/v95-detector-dev")
SOURCES = (ROOT/"candle_dynamics_m1_v94.csv", ROOT/"research/data/v94_forward_m1.csv")
JOURNAL = ROOT/"trade_journal_v94.json"

def minute(s):
    return int(datetime.fromisoformat(str(s).replace("Z","+00:00")).astimezone(timezone.utc).timestamp()//60)

def iso(m):
    return datetime.fromtimestamp(m*60,timezone.utc).isoformat()

def load():
    candles={}; duplicate=0
    for p in SOURCES:
        n=0
        with p.open(newline="",encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                t=minute(r["datetime"])
                b={k:float(r[v]) for k,v in (("o","open"),("h","high"),("l","low"),("c","close"))}
                if not b["l"]<=min(b["o"],b["c"])<=max(b["o"],b["c"])<=b["h"]:
                    raise ValueError(f"Bad OHLC {p}:{t}")
                if t in candles:
                    duplicate+=1
                    if candles[t]!=b: raise ValueError(f"Conflicting OHLC at {iso(t)}")
                else: candles[t]=b
                n+=1
        print("SOURCE",p.name,"rows",n)
    return candles,duplicate

def run_one(i,r,bars,last,days,warmup):
    row={"index":i,"journal_status":r.get("status"),"model_time":r.get("model_time")}
    try:
        t=minute(r["model_time"]);entry=float(r["entry"])
        sl=float(r["stop_loss"]);tp=float(r["take_profit"])
        if not tp<entry<sl: raise ValueError("Invalid SELL SL/TP geometry")
    except (KeyError,ValueError,TypeError) as e:
        return dict(row,classification="INVALID_RECORD",error=str(e))
    row.update(entry=entry,stop_loss=sl,take_profit=tp,risk_usd_per_oz=round(sl-entry,5))
    from research.active_position_monitor.v95_hybrid_c_research import HybridC,Config
    model=None;missing=sum(t-k not in bars for k in range(warmup,0,-1))
    row["warmup_missing"]=missing
    if not missing:
        model=HybridC(cfg=Config(power_mode="raw",scenario_monitor_enabled=True))
        for k in range(warmup,0,-1):
            model.on_completed_m1(bars[t-k])
        model.open_initial(entry,sl,tp)
    first_exit=None;first_warning=None;first_confirm=None
    end=min(t+days*1440,last)
    max_favorable=0.;max_adverse=0.;n=0
    classification=None;event_minute=None;first_gap=None
    for m in range(t+1,end+1):
        b=bars.get(m)
        if b is None:
            classification="CENSORED_DATA_GAP";first_gap=m;break
        n+=1
        max_favorable=max(max_favorable,entry-b["l"])
        max_adverse=max(max_adverse,b["h"]-entry)
        stop_hit=b["h"]>=sl;target_hit=b["l"]<=tp
        if stop_hit or target_hit:
            classification=("BOTH_SL_TP_SAME_M1" if stop_hit and target_hit else
                            "SL_FIRST" if stop_hit else "TP_FIRST")
            event_minute=m
            break
        if model is not None:
            outcome=model.on_completed_m1(b)
            state=outcome.get("scenario_monitor",{}).get("state")
            if state in ("REVERSAL_WARNING","CONFIRMED_REVERSAL_CANDIDATE") and first_warning is None:
                first_warning=m
            if state=="CONFIRMED_REVERSAL_CANDIDATE" and first_confirm is None:
                first_confirm=m
            if outcome["action"] in ("ADAPTIVE_EXIT","EARLY_PROFIT_EXIT") and first_exit is None:
                # C2 action is a request only; next candle OPEN is a hypothetical
                # fill reference, not an actual execution or trade result.
                nb=bars.get(m+1)
                first_exit={"signal_time":iso(m),"minutes_after_entry":m-t,
                            "action":outcome["action"],
                            "next_m1_open":None if nb is None else nb["o"],
                            "next_m1_open_r":None if nb is None else round((entry-nb["o"])/(sl-entry),5)}
    if classification is None:
        classification="CENSORED_DATA_END" if end==last else "CENSORED_TIME_LIMIT"
    row.update(classification=classification,observed_minutes=n,
               first_touch_time=iso(event_minute) if event_minute else None,
               first_touch_minutes_after_entry=event_minute-t if event_minute else None,
               first_gap_time=iso(first_gap) if first_gap else None,
               first_c2_exit_request=first_exit,
               first_reversal_warning_minute=first_warning-t if first_warning else None,
               first_confirmed_reversal_minute=first_confirm-t if first_confirm else None,
               max_favorable_usd_per_oz=round(max_favorable,5),
               max_adverse_usd_per_oz=round(max_adverse,5),
               touch_reference_r=(-1 if classification=="SL_FIRST" else 2 if classification=="TP_FIRST" else None))
    return row

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--output",required=True)
    p.add_argument("--max-days",type=int,default=14)
    p.add_argument("--warmup",type=int,default=100)
    a=p.parse_args()
    if a.max_days<1 or a.warmup<16: p.error("max-days>=1 and warmup>=16")
    dest=Path(a.output)
    if dest.exists():p.error("Output already exists; use a fresh filename")
    bars,duplicates=load()
    journal=json.loads(JOURNAL.read_text())
    sells=[(i,r) for i,r in enumerate(journal,1) if str(r.get("side","")).upper()=="SELL"]
    last=max(bars)
    rows=[run_one(i,r,bars,last,a.max_days,a.warmup) for i,r in sells]
    cross=Counter((r["journal_status"],r["classification"]) for r in rows)
    report={
        "study":"V9.4 SELL journal lifecycle audit, observational only",
        "signal_count":len(rows),"m1_candles":len(bars),
        "duplicate_identical_candles":duplicates,
        "first_m1":iso(min(bars)),"last_m1":iso(last),
        "max_days_per_signal":a.max_days,"warmup":a.warmup,
        "classification_counts":dict(Counter(r["classification"] for r in rows)),
        "warmup_complete":sum(r.get("warmup_missing")==0 for r in rows),
        "c2_exit_requests_before_protective_touch":sum(r.get("first_c2_exit_request") is not None for r in rows),
        "journal_vs_path":[{"journal_status":s,"path":c,"count":n} for (s,c),n in sorted(cross.items())],
        "limitations":[
            "Journal entry is a reference, not verified executed fill or broker position",
            "First-touch SL/TP is an OHLC reference outcome, not a realized execution",
            "Same M1 SL/TP touch order is unknown",
            "M1 missing minute terminates replay; no fabricated interpolation",
            "At most max-days observation; no claims beyond historical data end",
            "C2 Raw first exit request is not an executed exit; next-open R is hypothetical",
            "No costs, spread, slippage, commissions, funding or position sizing",
            "Signals can overlap; observations are not statistically independent",
            "Historical WIN/LOSS may use separate accounting and exit timestamps",
            "No modification to V9.4 LIVE, V9.5 PAPER, Telegram, or C2 Raw",
        ],"signals":rows}
    with dest.open("x",encoding="utf-8") as f:
        json.dump(report,f,indent=2);f.write("\n")
    print(json.dumps({k:v for k,v in report.items() if k!="signals"},indent=2))
    for r in rows:
        print("SIGNAL",r["index"],r["journal_status"],r["classification"],
              "MINUTES",r.get("observed_minutes"),"C2_EXIT",
              None if not r.get("first_c2_exit_request") else r["first_c2_exit_request"]["minutes_after_entry"])
if __name__=="__main__":main()
