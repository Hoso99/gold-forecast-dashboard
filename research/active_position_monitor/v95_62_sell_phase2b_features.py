"""Research-only Phase 2B: timestamp-safe first-exit feature audit.

Paired initial SELL: (A) hold to first SL/TP, (B) first C2 Raw exit at
next M1 open, with identical protective levels. Both paths are hypothetical.
No broker, Telegram, or live-model side effects.
"""
import argparse,csv,json
from pathlib import Path
from datetime import datetime,timezone
from collections import Counter,defaultdict
from statistics import mean,median
from research.active_position_monitor.v95_hybrid_c_research import HybridC,Config,power

ROOT=Path("/home/ubuntu/v95-detector-dev")
SOURCES=[ROOT/"candle_dynamics_m1_v94.csv",ROOT/"research/data/v94_forward_m1.csv"]
JOURNAL=ROOT/"trade_journal_v94.json"

def minute(v):
    return int(datetime.fromisoformat(str(v).replace("Z","+00:00")).astimezone(timezone.utc).timestamp()//60)
def iso(t):
    return datetime.fromtimestamp(t*60,timezone.utc).isoformat()
def load():
    bars={}
    for path in SOURCES:
        with path.open(newline="",encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                t=minute(row["datetime"])
                b={k:float(row[v]) for k,v in (("o","open"),("h","high"),("l","low"),("c","close"))}
                if t in bars and bars[t]!=b:raise ValueError("Conflicting M1 at "+iso(t))
                bars[t]=b
    return bars
def tr(a):
    return max(a[-1]["h"]-a[-1]["l"],abs(a[-1]["h"]-a[-2]["c"]),abs(a[-1]["l"]-a[-2]["c"]))
def features(history,entry,stop,peak,t):
    a=history
    buy5=power(a[-5:]);buyprev=power(a[-10:-5])
    atr14=mean(max(a[j]["h"]-a[j]["l"],abs(a[j]["h"]-a[j-1]["c"]),abs(a[j]["l"]-a[j-1]["c"])) for j in range(len(a)-14,len(a)))
    recent=a[-1]; prior_hi=max(b["h"] for b in a[-6:-1])
    risk=stop-entry
    return {
        "buy_power_5":round(buy5,3),
        "buy_acceleration_pp":round(buy5-buyprev,3),
        "atr14_m1":round(atr14,5),
        "true_range_expansion":round(tr(a)/max(atr14,1e-8),4),
        "bullish_breakout_atr":round((recent["c"]-prior_hi)/max(atr14,1e-8),4),
        "bullish_closes_last_3":sum(b["c"]>b["o"] for b in a[-3:]),
        "up_close_count_last_3":sum(a[j]["c"]>a[j-1]["c"] for j in range(len(a)-3,len(a))),
        "upper_wick_ratio":round((recent["h"]-max(recent["o"],recent["c"]))/max(recent["h"]-recent["l"],1e-8),4),
        "m1_close_change_3_atr":round((recent["c"]-a[-4]["c"])/max(atr14,1e-8),4),
        "unrealized_r":round((entry-recent["c"])/risk,5),
        "peak_favorable_r":round(peak/risk,5),
        "giveback_r":round((peak-(entry-recent["c"]))/risk,5),
        "distance_to_stop_r":round((stop-recent["c"])/risk,5),
        "utc_hour":datetime.fromtimestamp(t*60,timezone.utc).hour,
    }
def one(index,r,bars,max_m,warmup,cost):
    row={"index":index,"journal_status":r.get("status"),"model_time":r.get("model_time")}
    try:
        t=minute(r["model_time"]);entry=float(r["entry"]);stop=float(r["stop_loss"]);tp=float(r["take_profit"])
        if not tp<entry<stop:raise ValueError("Invalid SELL geometry")
    except (ValueError,TypeError,KeyError) as e:return dict(row,outcome="INVALID_JOURNAL",error=str(e))
    risk=stop-entry
    row.update(entry=entry,stop=stop,target=tp,risk=risk)
    missing=sum(t-k not in bars for k in range(warmup,0,-1))
    row["warmup_missing"]=missing
    model=None;history=[]
    if not missing:
        model=HybridC(cfg=Config(power_mode="raw",scenario_monitor_enabled=True))
        for k in range(warmup,0,-1):
            b=bars[t-k];history.append(b);model.on_completed_m1(b)
        model.open_initial(entry,stop,tp)
    first=None;outcome=None;event_time=None;observed=0;peak=0
    for m in range(t+1,t+max_m+1):
        b=bars.get(m)
        if b is None:
            outcome="CENSORED_GAP";event_time=m;break
        observed+=1
        sl=b["h"]>=stop;target=b["l"]<=tp
        if sl or target:
            outcome="BOTH_TOUCH" if sl and target else "SL_FIRST" if sl else "TP_FIRST"
            event_time=m;break
        peak=max(peak,entry-b["l"])
        if model is not None:
            history.append(b)
            result=model.on_completed_m1(b)
            if first is None and result["action"] in ("ADAPTIVE_EXIT","EARLY_PROFIT_EXIT"):
                next_bar=bars.get(m+1)
                # Next bar may itself hit SL/TP; first-touch order within that
                # minute cannot be inferred from OHLC. Flag such requests.
                next_touch=(next_bar is not None and (next_bar["h"]>=stop or next_bar["l"]<=tp))
                first={"minute":m,"time":iso(m),"minutes_after_entry":m-t,
                       "action":result["action"],"features":features(history,entry,stop,peak,m),
                       "next_open":None if next_bar is None else next_bar["o"],
                       "next_bar_protective_touch":next_touch,
                       "next_open_r_gross":None if next_bar is None else (entry-next_bar["o"])/risk,
                       "next_open_r_net":None if next_bar is None else (entry-next_bar["o"]-cost)/risk}
        # When no warmup, only reconstruct protective path.
    if outcome is None:outcome="CENSORED_LIMIT";event_time=t+max_m
    baseline=None
    if outcome=="SL_FIRST":baseline=-1-cost/risk
    elif outcome=="TP_FIRST":baseline=(entry-tp-cost)/risk
    exit_net=first["next_open_r_net"] if first else None
    valid_pair=bool(first and exit_net is not None and baseline is not None
                    and not first["next_bar_protective_touch"])
    row.update(outcome=outcome,event_time=iso(event_time),observed_minutes=observed,
               first_c2_request=first,baseline_net_r=baseline,
               exit_net_r=exit_net,
               pair_valid=valid_pair,
               delta_r=exit_net-baseline if valid_pair else None)
    return row
def summarize(rows):
    pairs=[r for r in rows if r.get("pair_valid")]
    out={"signals":len(rows),"outcomes":dict(Counter(r["outcome"] for r in rows)),
         "complete_warmup":sum(r.get("warmup_missing")==0 for r in rows),
         "first_c2_requests":sum(r.get("first_c2_request") is not None for r in rows),
         "valid_paired_comparisons":len(pairs),
         "next_bar_protective_touch_flags":sum(bool((r.get("first_c2_request") or {}).get("next_bar_protective_touch")) for r in rows)}
    if pairs:
        out["paired_mean_delta_r"]=round(mean(r["delta_r"] for r in pairs),5)
        out["exit_better"]=sum(r["delta_r"]>0 for r in pairs)
        out["hold_better"]=sum(r["delta_r"]<0 for r in pairs)
        out["by_outcome"]={}
        for label in ("SL_FIRST","TP_FIRST"):
            part=[r for r in pairs if r["outcome"]==label]
            if part:out["by_outcome"][label]={"n":len(part),"mean_exit_net_r":round(mean(r["exit_net_r"] for r in part),5),
                    "mean_delta_r":round(mean(r["delta_r"] for r in part),5)}
    return out
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--output",required=True)
    ap.add_argument("--max-days",type=int,default=14)
    ap.add_argument("--warmup",type=int,default=100)
    ap.add_argument("--cost-per-oz",type=float,default=0.0)
    args=ap.parse_args()
    if args.max_days<1 or args.warmup<20 or args.cost_per_oz<0:ap.error("invalid parameters")
    output=Path(args.output)
    if output.exists():ap.error("Output already exists")
    bars=load();journal=json.loads(JOURNAL.read_text())
    sells=[(i,r) for i,r in enumerate(journal,1) if str(r.get("side","")).upper()=="SELL"]
    rows=[one(i,r,bars,args.max_days*1440,args.warmup,args.cost_per_oz) for i,r in sells]
    report={"study":"Phase 2B timestamp-safe first C2 exit feature audit",
            "cost_per_oz":args.cost_per_oz,"summary":summarize(rows),
            "limitations":[
                "First C2 request only; no simulated reentries",
                "Entry timestamp treated as reference boundary, not broker fill",
                "Next M1 open exit is hypothetical, not executable proof",
                "OHLC does not resolve within-minute stop/target sequencing",
                "Pairs with next-bar protective touches excluded as ambiguous",
                "Incomplete data censored; no fabricated prices",
                "C2 requests do not establish independent scenario predictive value",
                "SL/TP reference is not verified broker execution",
                "No spread/slippage unless represented in user-supplied cost_per_oz",
                "Overlapping trades may not be independent; no model fit or optimization",
                "Features use only bars completed at C2 request time",
                "No modifications to live V9.4 or paper V9.5"
            ],"signals":rows}
    with output.open("x",encoding="utf-8") as f:json.dump(report,f,indent=2);f.write("\n")
    print(json.dumps(report["summary"],indent=2))
    print("REPORT",output)
if __name__=="__main__":main()
