"""Phase 2E: research-only chronological execution replay for fixed C2 veto.

Compares original first C2 Raw exit with fixed 75% buy-body-power veto.
Following veto, model continues processing M1 bars, later C2 requests may
execute at next open. SL/TP remain active. No broker/live/paper side effects.
"""
import argparse,json
from pathlib import Path
from collections import Counter
from statistics import mean
from research.active_position_monitor.v95_62_sell_phase2b_features import load,JOURNAL,minute,iso
from research.active_position_monitor.v95_hybrid_c_research import HybridC,Config,power

EXIT_ACTIONS={"ADAPTIVE_EXIT","EARLY_PROFIT_EXIT"}

def replay(r,bars,threshold,max_minutes,warmup,cost,allow_veto):
    try:
        t=minute(r["model_time"]);entry=float(r["entry"]);stop=float(r["stop_loss"]);tp=float(r["take_profit"])
        if not tp<entry<stop:raise ValueError("invalid SELL levels")
    except (KeyError,ValueError,TypeError) as e:
        return {"status":"INVALID","reason":str(e)}
    risk=stop-entry
    if any(t-i not in bars for i in range(1,warmup+1)):
        return {"status":"NO_WARMUP"}
    model=HybridC(cfg=Config(power_mode="raw",scenario_monitor_enabled=False))
    for i in range(warmup,0,-1):model.on_completed_m1(bars[t-i])
    model.open_initial(entry,stop,tp)
    pending=None;requests=0;vetoes=0;first_request=None
    for m in range(t+1,t+max_minutes+1):
        b=bars.get(m)
        if b is None:
            return {"status":"CENSORED_GAP","minutes":m-t,"requests":requests,
                    "vetoes":vetoes,"first_request":first_request}
        # Pending C2 exit executes at the NEXT bar OPEN, before intrabar
        # SL/TP touches. Adverse opening gaps through stop are not filled
        # optimistically at stop; apply adverse opening price.
        if pending is not None:
            fill=b["o"]
            if fill>stop:fill=b["o"]  # gap past SL; worse-than-stop fill
            return {"status":"C2_EXIT","minutes":m-t,"time":iso(m),
                    "exit_price":fill,"net_r":(entry-fill-cost)/risk,
                    "requests":requests,"vetoes":vetoes,"first_request":first_request,
                    "exit_trigger":pending}
        sl=b["h"]>=stop;hit_tp=b["l"]<=tp
        if sl or hit_tp:
            if sl and hit_tp:
                return {"status":"BOTH_TOUCH","minutes":m-t,"requests":requests,
                        "vetoes":vetoes,"first_request":first_request}
            # Protective fills are reference levels. Gap through SL is worse;
            # favorable gaps through TP are not awarded as extra gains.
            fill=max(stop,b["o"]) if sl else tp
            return {"status":"PROTECTIVE_SL" if sl else "PROTECTIVE_TP",
                    "minutes":m-t,"time":iso(m),"exit_price":fill,
                    "net_r":(entry-fill-cost)/risk,"requests":requests,
                    "vetoes":vetoes,"first_request":first_request}
        result=model.on_completed_m1(b)
        if result["action"] not in EXIT_ACTIONS:continue
        requests+=1
        hist=list(model.bars)
        buy=power(hist[-5:])
        if first_request is None:
            first_request={"minute":m-t,"time":iso(m),"buy_power_5":round(buy,3)}
        if allow_veto and buy<threshold:
            vetoes+=1
            continue
        # Only schedule if next M1 exists; next iteration will either
        # execute at next open or censor on a missing next bar.
        pending={"minute":m-t,"time":iso(m),"buy_power_5":round(buy,3),
                 "action":result["action"]}
    return {"status":"CENSORED_LIMIT","minutes":max_minutes,"requests":requests,
            "vetoes":vetoes,"first_request":first_request}

def stats(pairs,key):
    values=[p[key]["net_r"] for p in pairs]
    return {"n":len(values),"mean_net_r":round(mean(values),6),
            "sum_net_r":round(sum(values),6),
            "statuses":dict(Counter(p[key]["status"] for p in pairs))}
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--output",required=True)
    ap.add_argument("--threshold",type=float,default=75)
    ap.add_argument("--cost-per-oz",type=float,default=0)
    ap.add_argument("--warmup",type=int,default=100)
    ap.add_argument("--max-days",type=int,default=14)
    a=ap.parse_args()
    if not 0<=a.threshold<=100 or a.cost_per_oz<0 or a.warmup<20 or a.max_days<1:
        ap.error("invalid parameters")
    path=Path(a.output)
    if path.exists():ap.error("output already exists")
    bars=load();journal=json.loads(JOURNAL.read_text())
    signals=[(i,r) for i,r in enumerate(journal,1) if str(r.get("side","")).upper()=="SELL"]
    records=[]
    for i,r in signals:
        raw=replay(r,bars,a.threshold,a.max_days*1440,a.warmup,a.cost_per_oz,False)
        challenger=replay(r,bars,a.threshold,a.max_days*1440,a.warmup,a.cost_per_oz,True)
        record={"signal_index":i,"model_time":r.get("model_time"),
                "c2_raw":raw,"challenger":challenger}
        if raw.get("net_r") is not None and challenger.get("net_r") is not None:
            record["delta_r"]=round(challenger["net_r"]-raw["net_r"],8)
        records.append(record)
    paired=[r for r in records if "delta_r" in r]
    summary={"signals":len(records),"paired_executable_reference":len(paired),
             "raw_statuses":dict(Counter(r["c2_raw"]["status"] for r in records)),
             "challenger_statuses":dict(Counter(r["challenger"]["status"] for r in records)),
             "raw":stats(paired,"c2_raw") if paired else None,
             "challenger":stats(paired,"challenger") if paired else None,
             "mean_delta_r":round(mean(r["delta_r"] for r in paired),6) if paired else None,
             "sum_delta_r":round(sum(r["delta_r"] for r in paired),6),
             "challenger_better":sum(r["delta_r"]>1e-8 for r in paired),
             "raw_better":sum(r["delta_r"]< -1e-8 for r in paired),
             "ties":sum(abs(r["delta_r"])<=1e-8 for r in paired),
             "vetoed_signals":sum(r["challenger"].get("vetoes",0)>0 for r in records),
             "later_exit_after_veto":sum(r["challenger"].get("vetoes",0)>0 and
                                         r["challenger"]["status"]=="C2_EXIT" for r in records)}
    report={"study":"Phase 2E fixed threshold chronological M1 execution replay",
            "threshold":a.threshold,"cost_per_oz":a.cost_per_oz,"summary":summary,
            "limitations":[
                "Only the first initial SELL position; no reentry",
                "C2 Raw requests are recomputed on every completed M1",
                "C2 exit fills at next M1 open, never at signal close",
                "Protective SL/TP OHLC first touches; same-bar ambiguity censored",
                "SL opening gaps use adverse opening price; TP fills capped at target",
                "Spread, market impact and latency not modeled beyond flat cost",
                "Historical signals overlap and are not independent",
                "No new threshold optimization; threshold fixed at 75%",
                "Censored signals excluded from paired mean; survivorship bias possible",
                "No modifications to live V9.4, paper V9.5, original C2 Raw",
            ],"signals":records}
    with path.open("x",encoding="utf-8") as f:json.dump(report,f,indent=2);f.write("\n")
    print(json.dumps(summary,indent=2))
    print("VETO CASES")
    for r in records:
        if r["challenger"].get("vetoes",0):
            print(r["signal_index"],"raw",r["c2_raw"]["status"],r["c2_raw"].get("net_r"),
                  "challenger",r["challenger"]["status"],r["challenger"].get("net_r"),
                  "vetoes",r["challenger"]["vetoes"],"delta",r.get("delta_r"))
    print("REPORT",path)
if __name__=="__main__":main()
