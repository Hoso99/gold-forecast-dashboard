"""C2.3 isolated research challenger: causal ablation, no trading integrations.

Compares unchanged C2.1/C2.2 against three C2.3 variants:
timer-only; timer + bearish-continuation veto; timer + veto + urgent warning.
ATR urgent warnings NEVER constitute automatic exit confirmations.
"""
import argparse
import json
from pathlib import Path
from datetime import datetime, timezone
from research.active_position_monitor.v95_c21_episode_comparison import (
    load_m1, load_m5, episodes, observe as observe_c21, EXIT)
from research.active_position_monitor.v95_c22_episode_challenger import (
    observe as observe_c22, atr)
from research.active_position_monitor.v95_hybrid_c_research import HybridC, Config

class C23:
    def __init__(self, veto=False, urgent=False):
        self.start=None
        self.reference=None
        self.veto=veto
        self.urgent=urgent
        self.resets_prevented=0
    def observe(self,t,b,prior,prior5,atr14,raw):
        if self.start is None and raw:
            self.start=t
            self.reference=b["c"]
        elif self.start is not None and raw:
            self.resets_prevented+=1
        if self.start is None:
            return "HOLD",None
        age=t-self.start
        if age>5:
            self.start=self.reference=None
            return "HOLD",None
        bearish=(prior is not None and b["c"]<b["o"] and b["c"]<prior["l"])
        # Causal cancellation: the same bearish invalidation as C2.1.
        if bearish:
            self.start=self.reference=None
            return "HOLD","BEARISH_INVALIDATION"
        bullish=prior is not None and b["c"]>b["o"] and b["c"]>prior["c"]
        breakout=len(prior5)==5 and b["c"]>max(x["h"] for x in prior5)
        # Exploratory SELL-continuation veto: two completed bearish candles,
        # and the latest close is below its predecessor's close.
        continuation=(self.veto and prior is not None and
                      b["c"]<b["o"] and prior["c"]<prior["o"] and
                      b["c"]<prior["c"])
        if age>0 and bullish and breakout and not continuation:
            self.start=self.reference=None
            return "EXIT_CANDIDATE","STRUCTURE"
        if self.urgent and age>0 and atr14 and atr14>0 and bullish and (
            b["c"]-self.reference>=1.5*atr14):
            return "URGENT_WARNING","ATR_1_5"
        return "WARNING",None

def replay(m1,bucket,horizon,variant):
    signal=bucket*5+4
    begin=signal-99
    end=signal+horizon
    if any(t not in m1 for t in range(begin,end+1)):
        return {"status":"SKIP_MISSING_M1"}
    model=HybridC(cfg=Config(power_mode="raw"))
    closes=[m1[t]["c"] for t in range(begin,end+1)]
    model.open_initial(m1[begin]["c"],max(closes)+10000,min(closes)-10000)
    gate=C23(veto=variant in ("veto","urgent"),urgent=variant=="urgent")
    history=[]
    prev=None
    exits=[]
    warnings=[]
    urgent=[]
    raw_times=[]
    for t in range(begin,end+1):
        b=m1[t]
        action=model.on_completed_m1(b)["action"]
        if t>=signal:
            raw=action in EXIT
            if raw: raw_times.append(t-signal)
            state,reason=gate.observe(t,b,prev,history[-5:],atr(history+[b]),raw)
            if state=="EXIT_CANDIDATE":
                exits.append({"minute":t-signal,"reason":reason})
            elif state=="URGENT_WARNING":
                urgent.append({"minute":t-signal,"reason":reason})
            elif state=="WARNING":
                warnings.append(t-signal)
        history.append(b)
        prev=b
    return {"status":"EVALUATED","raw_first_min":raw_times[0] if raw_times else None,
            "exit_first_min":exits[0]["minute"] if exits else None,
            "exits":exits,"warning_first_min":warnings[0] if warnings else None,
            "urgent_first_min":urgent[0]["minute"] if urgent else None,
            "urgent_events":urgent,"resets_prevented":gate.resets_prevented}

def analyze(db):
    m5,_=load_m5(db)
    m1=load_m1(db)
    rows=[]
    for i,group in enumerate(episodes(m5),1):
        bucket=group[0]
        base=observe_c21(m1,bucket,15)
        c22=observe_c22(m1,bucket,15)
        variants={}
        for name in ("timer","veto","urgent"):
            variants[name]={"15":replay(m1,bucket,15,name),
                            "30":replay(m1,bucket,30,name)}
        rows.append({"episode":i,
                     "first_m5_signal_utc":datetime.fromtimestamp(
                         (bucket*5+5)*60,timezone.utc).isoformat(),
                     "raw_first_min":base["raw_first_min"],
                     "c21_first_min":base["c21_first_min"],
                     "c22_first_min":c22["c22_first_min"],
                     "variants":variants})
    summary={"episodes":len(rows)}
    for name in ("timer","veto","urgent"):
        for horizon in ("15","30"):
            valid=[r["variants"][name][horizon] for r in rows
                   if r["variants"][name][horizon]["status"]=="EVALUATED"]
            summary[name+"_"+horizon]={
                "evaluated":len(valid),
                "confirmed_episodes":sum(v["exit_first_min"] is not None for v in valid),
                "urgent_warning_episodes":sum(v["urgent_first_min"] is not None for v in valid),
                "prevented_resets":sum(v["resets_prevented"] for v in valid)}
    return {"study":"C2.3 causal ablation (research only)","summary":summary,
            "episodes":rows,
            "limitations":["No independently labeled reversals or actual positions",
                           "M5-selected episodes; no profitability inference",
                           "No execution, spread, slippage or intrabar sequencing",
                           "Veto and ATR warning are exploratory; not validated",
                           "30-minute windows can overlap other episodes",
                           "Completed candles only; C2.1/C2.2 unchanged"]}
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db",required=True)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    report=analyze(a.db)
    with Path(a.output).open("x") as f:
        json.dump(report,f,indent=2)
        f.write("\n")
    print("SUMMARY",json.dumps(report["summary"]))
    for r in report["episodes"]:
        print("EPISODE",r["episode"],json.dumps({
            "raw":r["raw_first_min"],"c21":r["c21_first_min"],"c22":r["c22_first_min"],
            "variants":{k:{"15":v["15"]["exit_first_min"],
                            "30":v["30"]["exit_first_min"],
                            "urgent30":v["30"]["urgent_first_min"],
                            "resets30":v["30"]["resets_prevented"]}
                        for k,v in r["variants"].items()}}))
if __name__=="__main__":
    main()
