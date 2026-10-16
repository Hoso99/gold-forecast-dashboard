"""Scenario Monitor V3-A: causal reversal evidence and first-exit replay.

RESEARCH ONLY. Not a trading signal, not validated. No services or side effects.
Completed M1 only; M5 groups end on UTC multiples of five. Never use future
candles for decisions. Original C2 Raw state machine remains unchanged.
"""
import argparse,json
from collections import Counter,deque
from pathlib import Path
from statistics import mean
from research.active_position_monitor.v95_62_sell_phase2b_features import load,JOURNAL,minute,iso
from research.active_position_monitor.v95_hybrid_c_research import HybridC,Config,power

EXIT={"ADAPTIVE_EXIT","EARLY_PROFIT_EXIT"}
def m5_signal(history,t):
    # Only FULL completed UTC-aligned M5 intervals; timestamps are treated as
    # completed minute start timestamps and bar [t,t+1) becomes known at t+1.
    # At end of minute t, latest full block ends when (t+1)%5 == 0.
    end=t-((t+1)%5)
    if len(history)<15:return None
    lookup=dict(history)
    blocks=[]
    for finish in (end-10,end-5,end):
        seq=[lookup.get(k) for k in range(finish-4,finish+1)]
        if any(b is None for b in seq):return None
        blocks.append({"o":seq[0]["o"],"c":seq[-1]["c"],
                       "h":max(b["h"] for b in seq),"l":min(b["l"] for b in seq)})
    latest,previous=blocks[-1],blocks[-2]
    return {"bullish":latest["c"]>latest["o"],
            "close_above_prior_high":latest["c"]>previous["h"],
            "last_close":latest["c"],"last_high":latest["h"]}
def replay(r,bars,mode,threshold,watch_bars,warmup,max_minutes,cost):
    try:
        t=minute(r["model_time"]);entry=float(r["entry"]);stop=float(r["stop_loss"]);tp=float(r["take_profit"])
        if not tp<entry<stop:raise ValueError("invalid SELL geometry")
    except (ValueError,KeyError,TypeError) as e:return {"status":"INVALID","reason":str(e)}
    if any(t-i not in bars for i in range(1,warmup+1)):
        return {"status":"NO_WARMUP"}
    risk=stop-entry
    model=HybridC(cfg=Config(power_mode="raw",scenario_monitor_enabled=False))
    history=deque(maxlen=200)
    for k in range(warmup,0,-1):
        m=t-k;b=bars[m];model.on_completed_m1(b);history.append((m,b))
    model.open_initial(entry,stop,tp)
    pending=None;watch_until=None;watch_anchor=None;watch_peak=0
    decisions=[];vetoes=0
    for m in range(t+1,t+max_minutes+1):
        b=bars.get(m)
        if b is None:return {"status":"CENSORED_GAP","decisions":decisions,"vetoes":vetoes}
        if pending is not None:
            return {"status":"C2_EXIT" if mode=="raw" else "V3_EXIT",
                    "time":iso(m),"exit_price":b["o"],
                    "net_r":(entry-b["o"]-cost)/risk,
                    "decisions":decisions,"vetoes":vetoes}
        sl=b["h"]>=stop;hit_tp=b["l"]<=tp
        if sl or hit_tp:
            if sl and hit_tp:return {"status":"BOTH_TOUCH","decisions":decisions,"vetoes":vetoes}
            price=max(stop,b["o"]) if sl else tp
            return {"status":"PROTECTIVE_SL" if sl else "PROTECTIVE_TP",
                    "time":iso(m),"exit_price":price,
                    "net_r":(entry-price-cost)/risk,"decisions":decisions,"vetoes":vetoes}
        history.append((m,b))
        result=model.on_completed_m1(b)
        if mode=="raw":
            if result["action"] in EXIT:pending={"reason":"original_c2_request"}
            continue
        if result["action"] not in EXIT and watch_until is None:continue
        a=list(model.bars)
        buy=power(a[-5:]);prior=power(a[-10:-5]);accel=buy-prior
        prior_high=max(x["h"] for x in a[-6:-1])
        breakout=b["c"]>prior_high
        m5=m5_signal(history,m)
        # Fixed, interpretable hypotheses; no training/threshold fitting.
        strong=buy>=threshold and accel>=45 and breakout
        m5_confirmed=bool(m5 and m5["bullish"] and m5["close_above_prior_high"])
        if watch_until is None:
            if strong and m5_confirmed:
                decision="EXIT";reason="strong_pressure_breakout_and_completed_m5"
            else:
                decision="WATCH";reason="C2_exit_unconfirmed"
                watch_until=m+watch_bars;watch_anchor=prior_high
                watch_peak=b["c"];vetoes+=1
        else:
            watch_peak=max(watch_peak,b["c"])
            # A failed breakout is a closed M1 below the fixed anchor.
            failed=bool(watch_anchor is not None and b["c"]<watch_anchor)
            persistent=(sum(x["c"]>x["o"] for x in a[-3:])>=2 and
                        b["c"]>=a[-3]["c"])
            if strong and (persistent or m5_confirmed):
                decision="EXIT";reason="later_persistent_reversal"
            elif m>=watch_until:
                decision="HOLD";reason="confirmation_window_expired"
                watch_until=None;watch_anchor=None;watch_peak=0
            elif failed and buy<50:
                decision="HOLD";reason="failed_breakout_and_buy_power_faded"
                watch_until=None;watch_anchor=None;watch_peak=0
            else:
                decision="WATCH";reason="awaiting_confirmation"
        if len(decisions)<50:
            decisions.append({"time":iso(m),"decision":decision,"reason":reason,
                              "c2_action":result["action"],"buy_power_5":round(buy,2),
                              "acceleration_pp":round(accel,2),
                              "bullish_breakout":breakout,
                              "m5_confirmed":m5_confirmed})
        if decision=="EXIT":pending={"reason":reason}
    return {"status":"CENSORED_LIMIT","decisions":decisions,"vetoes":vetoes}
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--output",required=True)
    p.add_argument("--threshold",type=float,default=75)
    p.add_argument("--watch-bars",type=int,default=5)
    p.add_argument("--cost-per-oz",type=float,default=0)
    p.add_argument("--warmup",type=int,default=100)
    p.add_argument("--max-days",type=int,default=14)
    args=p.parse_args()
    if not 0<=args.threshold<=100 or not 1<=args.watch_bars<=30 or args.cost_per_oz<0:
        p.error("invalid parameter")
    output=Path(args.output)
    if output.exists():p.error("output already exists")
    bars=load();journal=json.loads(JOURNAL.read_text())
    signals=[(i,r) for i,r in enumerate(journal,1) if str(r.get("side","")).upper()=="SELL"]
    records=[]
    for i,r in signals:
        raw=replay(r,bars,"raw",args.threshold,args.watch_bars,args.warmup,args.max_days*1440,args.cost_per_oz)
        v3=replay(r,bars,"v3",args.threshold,args.watch_bars,args.warmup,args.max_days*1440,args.cost_per_oz)
        row={"index":i,"model_time":r.get("model_time"),"raw":raw,"v3a":v3}
        if "net_r" in raw and "net_r" in v3:row["delta_r"]=round(v3["net_r"]-raw["net_r"],8)
        records.append(row)
    paired=[r for r in records if "delta_r" in r]
    changes=[r for r in paired if abs(r["delta_r"])>1e-8]
    summary={"signals":len(records),"paired":len(paired),
             "raw_statuses":dict(Counter(r["raw"]["status"] for r in records)),
             "v3_statuses":dict(Counter(r["v3a"]["status"] for r in records)),
             "v3_watch_signals":sum(r["v3a"].get("vetoes",0)>0 for r in records),
             "v3_better":sum(r["delta_r"]>1e-8 for r in paired),
             "raw_better":sum(r["delta_r"]< -1e-8 for r in paired),
             "ties":len(paired)-len(changes),
             "mean_delta_r":round(mean(r["delta_r"] for r in paired),6) if paired else None,
             "sum_delta_r":round(sum(r["delta_r"] for r in paired),6)}
    report={"study":"Scenario Monitor V3-A causal M1 and completed M5 research",
            "parameters":{"threshold":args.threshold,"watch_bars":args.watch_bars,
                          "cost_per_oz":args.cost_per_oz},
            "summary":summary,"signals":records,
            "limitations":[
                "Fixed research hypotheses, no calibration or independent validation",
                "M5 blocks use UTC minute boundaries and complete five M1 bars",
                "WATCH timeout is not a permanent trade exit; C2 may request again",
                "No reentry; execution at next M1 open, protective reference touch",
                "Intrabar SL/TP ambiguity flagged; adverse SL opening gap applied",
                "Overlapping trades are correlated, not independent observations",
                "Censored records excluded from paired comparison",
                "No broker execution, latency or spread model beyond flat cost",
                "No changes to live V9.4, paper V9.5 or C2 Raw"
            ]}
    with output.open("x",encoding="utf-8") as f:json.dump(report,f,indent=2);f.write("\n")
    print(json.dumps(summary,indent=2))
    print("CHANGED CASES")
    for r in changes:print(r["index"],"delta_r",r["delta_r"],"raw",r["raw"]["status"],
                            "v3",r["v3a"]["status"],"watch",r["v3a"]["vetoes"])
    print("REPORT",output)
if __name__=="__main__":main()
