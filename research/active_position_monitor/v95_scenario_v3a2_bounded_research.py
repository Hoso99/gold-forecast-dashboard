"""V3-A2 bounded confirmation research. Does not modify original C2 or V3-A."""
import argparse,json
from collections import Counter,deque
from pathlib import Path
from statistics import mean
from research.active_position_monitor.v95_62_sell_phase2b_features import load,JOURNAL,minute,iso
from research.active_position_monitor.v95_hybrid_c_research import HybridC,Config,power
from research.active_position_monitor.v95_scenario_v3a_research import replay as replay_v3a,m5_signal,EXIT

def bounded(r,bars,threshold,limit,warmup,max_minutes,cost):
    try:
        t=minute(r["model_time"]);entry=float(r["entry"]);sl=float(r["stop_loss"]);tp=float(r["take_profit"])
        if not tp<entry<sl:raise ValueError("invalid SELL geometry")
    except (KeyError,ValueError,TypeError) as e:return {"status":"INVALID","reason":str(e)}
    if any(t-i not in bars for i in range(1,warmup+1)):return {"status":"NO_WARMUP"}
    risk=sl-entry
    model=HybridC(cfg=Config(power_mode="raw",scenario_monitor_enabled=False))
    hist=deque(maxlen=200)
    for k in range(warmup,0,-1):
        j=t-k;model.on_completed_m1(bars[j]);hist.append((j,bars[j]))
    model.open_initial(entry,sl,tp)
    first=None;deadline=None;pending=None;events=[]
    for m in range(t+1,t+max_minutes+1):
        b=bars.get(m)
        if b is None:return {"status":"CENSORED_GAP","first_request":iso(first) if first else None,"events":events}
        if pending:
            return {"status":"V3A2_EXIT","time":iso(m),"exit_price":b["o"],
                    "net_r":(entry-b["o"]-cost)/risk,
                    "first_request":iso(first),"delay_minutes":m-(first+1),
                    "reason":pending,"events":events}
        sl_hit=b["h"]>=sl;tp_hit=b["l"]<=tp
        if sl_hit and tp_hit:return {"status":"BOTH_TOUCH","first_request":iso(first) if first else None,"events":events}
        if sl_hit or tp_hit:
            price=max(sl,b["o"]) if sl_hit else tp
            return {"status":"PROTECTIVE_SL" if sl_hit else "PROTECTIVE_TP",
                    "time":iso(m),"exit_price":price,"net_r":(entry-price-cost)/risk,
                    "first_request":iso(first) if first else None,"events":events}
        hist.append((m,b))
        result=model.on_completed_m1(b)
        if first is None:
            if result["action"] not in EXIT:continue
            first=m;deadline=m+limit
        a=list(model.bars)
        buy=power(a[-5:]);accel=buy-power(a[-10:-5])
        prev_high=max(x["h"] for x in a[-6:-1])
        breakout=b["c"]>prev_high
        m5=m5_signal(hist,m)
        m5_ok=bool(m5 and m5["bullish"] and m5["close_above_prior_high"])
        persistent=sum(x["c"]>x["o"] for x in a[-3:])>=2 and b["c"]>=a[-3]["c"]
        strong=buy>=threshold
        # Two alternate causal confirmation paths: persistent M1 breakout, or
        # completed M5 bullish breakout with sustained buying power. Acceleration
        # is recorded but is not an unconditional gate.
        if strong and breakout and persistent:
            decision="EXIT";reason="m1_persistent_pressure_breakout"
        elif strong and m5_ok:
            decision="EXIT";reason="completed_m5_pressure_confirmation"
        elif m>=deadline:
            decision="EXIT";reason="hard_confirmation_deadline"
        else:
            decision="WATCH";reason="unconfirmed_within_bounded_window"
        events.append({"time":iso(m),"decision":decision,"reason":reason,
                       "buy_power_5":round(buy,3),"acceleration_pp":round(accel,3),
                       "breakout":breakout,"m5_confirmed":m5_ok,
                       "c2_action":result["action"]})
        if decision=="EXIT":pending=reason
    return {"status":"CENSORED_LIMIT","first_request":iso(first) if first else None,"events":events}

def stats(rows,key,base):
    paired=[x for x in rows if "net_r" in x[key] and "net_r" in x[base]]
    d=[x[key]["net_r"]-x[base]["net_r"] for x in paired]
    return {"paired":len(d),"better":sum(v>1e-8 for v in d),
            "worse":sum(v< -1e-8 for v in d),"ties":sum(abs(v)<=1e-8 for v in d),
            "mean_delta_r":round(mean(d),6) if d else None,
            "sum_delta_r":round(sum(d),6),
            "worst_delta_r":round(min(d),6) if d else None,
            "best_delta_r":round(max(d),6) if d else None}
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--output",required=True)
    p.add_argument("--threshold",type=float,default=75)
    p.add_argument("--limits",type=int,nargs="+",default=[3,5,10])
    p.add_argument("--cost-per-oz",type=float,default=0)
    p.add_argument("--warmup",type=int,default=100)
    p.add_argument("--max-days",type=int,default=14)
    a=p.parse_args()
    if not 0<=a.threshold<=100 or not a.limits or any(n<1 or n>30 for n in a.limits) or a.cost_per_oz<0:p.error("invalid parameters")
    output=Path(a.output)
    if output.exists():p.error("output already exists")
    bars=load();journal=json.loads(JOURNAL.read_text())
    rows=[]
    for i,r in enumerate(journal,1):
        if str(r.get("side","")).upper()!="SELL":continue
        raw=replay_v3a(r,bars,"raw",a.threshold,5,a.warmup,a.max_days*1440,a.cost_per_oz)
        old=replay_v3a(r,bars,"v3",a.threshold,5,a.warmup,a.max_days*1440,a.cost_per_oz)
        v={str(n):bounded(r,bars,a.threshold,n,a.warmup,a.max_days*1440,a.cost_per_oz) for n in sorted(set(a.limits))}
        rows.append({"index":i,"model_time":r.get("model_time"),"raw":raw,"v3a":old,"v3a2":v})
    summary={"signals":len(rows),"v3a_vs_raw":stats(rows,"v3a","raw"),"limits":{}}
    for n in sorted(set(a.limits)):
        temp=[{"raw":x["raw"],"v3a":x["v3a"],"new":x["v3a2"][str(n)]} for x in rows]
        summary["limits"][str(n)]={
            "vs_raw":stats(temp,"new","raw"),"vs_v3a":stats(temp,"new","v3a"),
            "statuses":dict(Counter(x["new"]["status"] for x in temp)),
            "deadline_exits":sum(x["new"].get("reason")=="hard_confirmation_deadline" for x in temp),
            "m5_exits":sum(x["new"].get("reason")=="completed_m5_pressure_confirmation" for x in temp),
            "m1_exits":sum(x["new"].get("reason")=="m1_persistent_pressure_breakout" for x in temp),
            "max_delay_minutes":max((x["new"].get("delay_minutes",0) for x in temp),default=0)}
    report={"study":"V3-A2 bounded causal confirmation research",
            "parameters":{"threshold":a.threshold,"limits":sorted(set(a.limits)),
                          "cost_per_oz":a.cost_per_oz},
            "summary":summary,"signals":rows,
            "limitations":["Hypothetical next M1 open fills; no real execution",
                           "Hard confirmation deadline is relative to first C2 request and cannot reset",
                           "Overlapping SELL signals are correlated",
                           "No independent holdout; all thresholds provisional",
                           "Protective SL/TP tested on each completed M1 bar before signal decisions",
                           "Cost is a flat per-ounce deduction; does not model dynamic spread or slippage",
                           "No changes to original C2, V3-A, V9.4 LIVE or V9.5 PAPER"]}
    with output.open("x") as f:json.dump(report,f,indent=2);f.write("\n")
    print(json.dumps(summary,indent=2));print("REPORT",output)
if __name__=="__main__":main()
