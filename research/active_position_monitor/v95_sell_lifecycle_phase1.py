"""V9.5 research-only SELL lifecycle replay: baseline vs 33% at +1R.

Requires an independently recorded CSV of actual or explicitly simulated SELL
entries. Never derives entries from exit-candidate episodes. Does not trade.
Conservative OHLC sequencing: when SL and TP touch same M1 candle, SL wins.
"""
import argparse,csv,json,math
from pathlib import Path
from datetime import datetime,timezone
from statistics import mean
from research.active_position_monitor.v95_c21_episode_comparison import load_m1
from research.active_position_monitor.v95_m5_history_scan import minute_epoch

def entries_csv(path):
    with open(path,newline="",encoding="utf-8") as f:
        reader=csv.DictReader(f)
        required={"entry_minute","entry_price","stop_loss"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError("CSV requires entry_minute,entry_price,stop_loss columns")
        entries=[]
        for line,row in enumerate(reader,2):
            t=minute_epoch(row["entry_minute"])
            e=float(row["entry_price"]);sl=float(row["stop_loss"])
            tp=float(row["take_profit"]) if row.get("take_profit") else e-2*(sl-e)
            if not all(math.isfinite(x) for x in (e,sl,tp)) or not (sl>e>tp>0):
                raise ValueError(f"Line {line}: require stop_loss > entry_price > take_profit > 0")
            entries.append({"line":line,"minute":t,"entry":e,"sl":sl,"tp":tp,
                            "id":row.get("id") or f"line_{line}"})
    if len({x["id"] for x in entries})!=len(entries):
        raise ValueError("Duplicate entry IDs")
    return entries

def simulate(m1,trade,partial_fraction,max_minutes):
    e,sl,tp=trade["entry"],trade["sl"],trade["tp"]
    risk=sl-e
    first_target=e-risk
    start=trade["minute"]+1
    # Entry is assumed filled at specified price at end of entry_minute.
    # All subsequent bars must be contiguous; no retroactive intrabar fill.
    if trade["minute"] not in m1:return {"status":"SKIP_ENTRY_MINUTE_MISSING"}
    for t in range(start,start+max_minutes):
        if t not in m1:return {"status":"SKIP_MISSING_M1","missing_minute":t}
    realized=0.0
    remaining=1.0
    partial_done=False
    actions=[]
    for t in range(start,start+max_minutes):
        b=m1[t]
        # If SL and profit levels touched in same candle, stop-first.
        if b["h"]>=sl:
            realized+=remaining*(e-sl)/risk
            actions.append({"minute":t,"type":"STOP","fraction":round(remaining,4),"price":sl})
            return {"status":"CLOSED","reason":"SL","gross_R":round(realized,5),"actions":actions}
        if partial_fraction and not partial_done and b["l"]<=first_target:
            realized+=partial_fraction*(e-first_target)/risk
            remaining-=partial_fraction
            partial_done=True
            actions.append({"minute":t,"type":"PARTIAL_TP","fraction":partial_fraction,"price":first_target})
        if b["l"]<=tp:
            realized+=remaining*(e-tp)/risk
            actions.append({"minute":t,"type":"FINAL_TP","fraction":round(remaining,4),"price":tp})
            return {"status":"CLOSED","reason":"TP","gross_R":round(realized,5),"actions":actions}
    # End-of-window close, not an executable guaranteed fill.
    t=start+max_minutes-1
    realized+=remaining*(e-m1[t]["c"])/risk
    actions.append({"minute":t,"type":"HORIZON_CLOSE","fraction":round(remaining,4),"price":m1[t]["c"]})
    return {"status":"CLOSED","reason":"HORIZON","gross_R":round(realized,5),"actions":actions}

def analyze(db,entries,max_minutes):
    m1=load_m1(db)
    rows=[]
    for trade in entries_csv(entries):
        baseline=simulate(m1,trade,0,max_minutes)
        partial=simulate(m1,trade,0.33,max_minutes)
        rows.append({"id":trade["id"],"entry_minute":trade["minute"],
                     "entry_utc":datetime.fromtimestamp(trade["minute"]*60,timezone.utc).isoformat(),
                     "entry":trade["entry"],"sl":trade["sl"],"tp":trade["tp"],
                     "A_baseline":baseline,"B_partial_33pct_1R":partial})
    valid=[r for r in rows if r["A_baseline"]["status"]=="CLOSED" and r["B_partial_33pct_1R"]["status"]=="CLOSED"]
    summary={"submitted_entries":len(rows),"evaluated_entries":len(valid),
             "skipped_entries":len(rows)-len(valid),"max_holding_minutes":max_minutes}
    for name in ("A_baseline","B_partial_33pct_1R"):
        vals=[r[name]["gross_R"] for r in valid]
        summary[name]={"trades":len(vals),"mean_gross_R":round(mean(vals),5) if vals else None,
                       "total_gross_R":round(sum(vals),5) if vals else None,
                       "stop_count":sum(r[name]["reason"]=="SL" for r in valid),
                       "tp_count":sum(r[name]["reason"]=="TP" for r in valid),
                       "horizon_count":sum(r[name]["reason"]=="HORIZON" for r in valid)}
    return {"study":"V9.5 SELL lifecycle Phase 1: complete-path A/B gross-R research",
            "summary":summary,"trades":rows,
            "limitations":["Input entries must be independently recorded; C2 M5 exit episodes are not entries",
                           "OHLC bar sequencing unknown; stop-first on collisions",
                           "Entry assumed filled at end of entry minute at provided price",
                           "SL and TP filled exactly at specified prices; real gaps and slippage can worsen fills",
                           "No spread, commissions, financing, or liquidity costs",
                           "No break-even stop movement, trailing, structural exits, or re-entry in Phase 1",
                           "Horizon-close uses bar close proxy, not guaranteed executable price",
                           "No overlap-aware portfolio risk accounting or position sizing",
                           "Research-only: no live or paper trading modifications"]}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db",required=True)
    p.add_argument("--entries",required=True,help="CSV: id,entry_minute,entry_price,stop_loss,take_profit(optional)")
    p.add_argument("--output",required=True)
    p.add_argument("--max-minutes",type=int,default=240)
    a=p.parse_args()
    if not 1<=a.max_minutes<=1440:p.error("max-minutes must be 1..1440")
    result=analyze(a.db,a.entries,a.max_minutes)
    with Path(a.output).open("x",encoding="utf-8") as f:
        json.dump(result,f,indent=2);f.write("\n")
    print("SUMMARY",json.dumps(result["summary"]))
    for row in result["trades"]:
        print("TRADE",json.dumps({"id":row["id"],
              "A":{k:row["A_baseline"].get(k) for k in ("status","reason","gross_R")},
              "B":{k:row["B_partial_33pct_1R"].get(k) for k in ("status","reason","gross_R")}}))
if __name__=="__main__":main()
