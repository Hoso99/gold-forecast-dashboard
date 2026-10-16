"""Read-only C2.2 reliability audit. No live/paper connections or trades."""
import argparse
import json
from pathlib import Path
from datetime import datetime, timezone
from research.active_position_monitor.v95_c21_episode_comparison import load_m1, load_m5, episodes, observe as baseline_observe, EXIT
from research.active_position_monitor.v95_hybrid_c_research import HybridC, Config
from research.active_position_monitor.v95_hybrid_c21 import C21Confirm
from research.active_position_monitor.v95_c22_episode_challenger import C22, atr, observe as c22_observe

def audit_episode(m1, bucket, horizon):
    signal=bucket*5+4
    begin=signal-99
    end=signal+horizon
    if any(t not in m1 for t in range(begin,end+1)):
        return {"status":"SKIP_MISSING_M1"}
    model=HybridC(cfg=Config(power_mode="raw"))
    prices=[m1[t]["c"] for t in range(begin,end+1)]
    model.open_initial(m1[begin]["c"],max(prices)+10000,min(prices)-10000)
    c22=C22()
    c21=C21Confirm()
    history=[]
    prev=None
    raw=[]
    confirms=[]
    c21_confirm=[]
    resets=[]
    warnings=[]
    for t in range(begin,end+1):
        b=m1[t]
        prior5=history[-5:]
        action=model.on_completed_m1(b)["action"]
        if t>=signal:
            israw=action in EXIT
            state21=c21.observe(t,b,prev,action,prior5)
            old_candidate=c22.candidate
            old_reference=c22.reference
            atr14=atr(history+[b])
            bullish=prev is not None and b["c"]>b["o"] and b["c"]>prev["c"]
            breakout=len(prior5)==5 and b["c"]>max(x["h"] for x in prior5)
            # The exact C22.observe logic evaluates structural confirmation
            # before ATR confirmation, after refreshing any Raw candidate.
            age=t-(t if israw else old_candidate) if (israw or old_candidate is not None) else None
            ref=b["c"] if israw else old_reference
            reason=None
            if age is not None and 0<age<=5 and bullish and breakout:
                reason="STRUCTURE"
            elif age is not None and 0<age<=5 and atr14 and atr14>0 and bullish and b["c"]-ref>=1.5*atr14:
                reason="ATR"
            state22=c22.observe(t,b,prev,prior5,atr14,israw)
            if israw:
                raw.append(t-signal)
                if old_candidate is not None:
                    resets.append({"minute":t-signal,"previous_candidate_minute":old_candidate-signal,"elapsed":t-old_candidate})
            if state22=="WARNING": warnings.append(t-signal)
            if state21=="CONFIRM": c21_confirm.append(t-signal)
            if state22=="EXIT_CANDIDATE":
                earlier=[r for r in raw if r<=t-signal]
                first_raw=earlier[0] if earlier else None
                max_adverse=None
                if first_raw is not None:
                    ref_close=m1[signal+first_raw]["c"]
                    max_adverse=max(m1[k]["h"]-ref_close for k in range(signal+first_raw+1,t+1)) if t>signal+first_raw else 0.0
                confirms.append({"minute":t-signal,"reason":reason or "UNCLASSIFIED",
                                 "first_raw_minute":first_raw,"max_adverse_before_confirmation":round(max_adverse,5) if max_adverse is not None else None})
        history.append(b)
        prev=b
    return {"status":"EVALUATED","raw_minutes":raw,"c21_confirm_minutes":c21_confirm,
            "c22_confirmations":confirms,"c22_warning_first_min":warnings[0] if warnings else None,
            "raw_resets":resets}

def analyze(db):
    m5,_=load_m5(db)
    m1=load_m1(db)
    rows=[]
    for i,g in enumerate(episodes(m5),1):
        a15=audit_episode(m1,g[0],15)
        a30=audit_episode(m1,g[0],30)
        base=baseline_observe(m1,g[0],15)
        challenger=c22_observe(m1,g[0],15)
        checks={}
        if a15["status"]=="EVALUATED":
            checks={"raw":(a15["raw_minutes"][0] if a15["raw_minutes"] else None)==base["raw_first_min"],
                    "c21":(a15["c21_confirm_minutes"][0] if a15["c21_confirm_minutes"] else None)==base["c21_first_min"],
                    "c22":(a15["c22_confirmations"][0]["minute"] if a15["c22_confirmations"] else None)==challenger["c22_first_min"]}
        rows.append({"episode":i,"m5_signal_utc":datetime.fromtimestamp((g[0]*5+5)*60,timezone.utc).isoformat(),
                     "horizon15":a15,"horizon30":a30,"replay_agreement":checks})
    evaluated=[r for r in rows if r["horizon15"]["status"]=="EVALUATED"]
    reasons={}
    for r in evaluated:
        for c in r["horizon15"]["c22_confirmations"]:
            reasons[c["reason"]]=reasons.get(c["reason"],0)+1
    summary={"episodes":len(rows),"evaluated15":len(evaluated),
             "evaluated30":sum(r["horizon30"]["status"]=="EVALUATED" for r in rows),
             "c22_15_confirmed_episodes":sum(bool(r["horizon15"]["c22_confirmations"]) for r in evaluated),
             "c22_30_confirmed_episodes":sum(r["horizon30"]["status"]=="EVALUATED" and bool(r["horizon30"]["c22_confirmations"]) for r in rows),
             "confirmation_reasons_15":reasons,
             "reset_events_15":sum(len(r["horizon15"]["raw_resets"]) for r in evaluated),
             "all_replay_checks_pass":all(all(r["replay_agreement"].values()) for r in evaluated)}
    return {"summary":summary,"episodes":rows,
            "limitations":["Preselected M5 candidates, no independently verified reversal labels",
                           "Synthetic SELL with distant SL/TP; no actual fills or trade profitability",
                           "Intrabar high/low sequence is unknown",
                           "30-minute study replays same algorithms with more future completed candles; no future data used in decisions",
                           "ATR/structure reason is a parallel diagnostic of unchanged C2.2 logic"]}
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db",required=True)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    report=analyze(a.db)
    with Path(a.output).open("x",encoding="utf-8") as f:
        json.dump(report,f,indent=2)
        f.write("\n")
    print("SUMMARY",json.dumps(report["summary"]))
    for r in report["episodes"]:
        print("EPISODE",r["episode"],json.dumps({"15":r["horizon15"],"30":r["horizon30"],"agreement":r["replay_agreement"]}))
if __name__=="__main__": main()
