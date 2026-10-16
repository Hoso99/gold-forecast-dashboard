"""Research-only feature audit of original 8/10 C2 reversal sample.

Extracts only causal signal-time M1 features; evaluates next-open to t+30
close. Compares global chronological 30m selection vs target-first 30m.
No training, optimization, or exit-rule changes.
"""
import argparse,json,statistics
from pathlib import Path
from collections import Counter
from research.active_position_monitor.v95_c21_six_reject_audit import load_m1
from research.active_position_monitor.v95_hybrid_c_research import HybridC,Config

TARGET="CONFIRMED_REVERSAL_CANDIDATE"

def features(bars,decision):
    recent=bars[-5:]
    prev=bars[-6:-1]
    up=sum(max(x["c"]-x["o"],0) for x in recent)
    down=sum(max(x["o"]-x["c"],0) for x in recent)
    buy=100*up/(up+down) if up+down else 50
    last=bars[-1]
    previous_high=max(x["h"] for x in prev)
    range10=max(x["h"] for x in bars[-11:-1])-min(x["l"] for x in bars[-11:-1])
    return {"buy_power":round(buy,3),
            "breakout_margin":round(last["c"]-previous_high,5),
            "breakout_normalized":round((last["c"]-previous_high)/max(range10,1e-8),5),
            "last_body":round(last["c"]-last["o"],5),
            "last_range":round(last["h"]-last["l"],5),
            "five_close_change":round(last["c"]-bars[-6]["c"],5),
            "ten_close_change":round(last["c"]-bars[-11]["c"],5),
            "range10":round(range10,5),
            "tr_expansion":decision["scenario_monitor"].get("m1_true_range_expansion"),
            "raw_action":decision["action"]}

def spaced(rows):
    out=[];last={}
    for r in rows:
        s=r["segment"]
        if s not in last or r["minute"]-last[s]>=30:
            out.append(r);last[s]=r["minute"]
    return out

def stats(rows):
    result={"n":len(rows),"up30":sum(r["delta30"]>0 for r in rows),
            "down30":sum(r["delta30"]<0 for r in rows),
            "mean_delta30":round(statistics.mean(r["delta30"] for r in rows),5) if rows else None,
            "raw_actions":dict(Counter(r["features"]["raw_action"] for r in rows))}
    for key in ("buy_power","breakout_margin","breakout_normalized","last_body",
                "last_range","five_close_change","ten_close_change","range10","tr_expansion"):
        nums=[r["features"][key] for r in rows if r["features"][key] is not None]
        result[key+"_median"]=round(statistics.median(nums),5) if nums else None
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--db",required=True)
    p.add_argument("--output",required=True)
    args=p.parse_args()
    dest=Path(args.output)
    if dest.exists():p.error("Output exists")
    m1=load_m1(args.db)
    model=None;segment=-1;previous=None;history=[];rows=[]
    for t in sorted(m1):
        if previous is None or t!=previous+1:
            model=HybridC(cfg=Config(power_mode="raw",scenario_monitor_enabled=True))
            price=m1[t]["c"];model.open_initial(price,price+10000,price-10000)
            segment+=1;history=[]
        history.append(m1[t])
        decision=model.on_completed_m1(m1[t])
        previous=t
        state=decision["scenario_monitor"]["state"]
        if state not in ("SELL_CONTINUATION","NORMAL_PULLBACK_CANDIDATE","REVERSAL_WARNING",
                         TARGET,"HIGH_VOLATILITY_EVENT","SIDEWAYS_OR_UNCLEAR"):continue
        if len(history)<16 or any(t+k not in m1 for k in range(1,31)):continue
        if state!=TARGET:
            rows.append({"minute":t,"segment":segment,"state":state})
            continue
        ref=m1[t+1]["o"]
        rows.append({"minute":t,"segment":segment,"state":state,
                     "delta30":round(m1[t+30]["c"]-ref,5),
                     "features":features(history,decision)})
    all_target=[r for r in rows if r["state"]==TARGET]
    global_target=[r for r in spaced(rows) if r["state"]==TARGET]
    target_first=spaced(all_target)
    # Freeze original selected minutes from prior published audit to verify
    # that the same exact 10 observations are being inspected.
    expected=[29865243,29865864,29866387,29866567,29866687,
              29867056,29867206,29867836,29868076,29868614]
    actual=[r["minute"] for r in global_target]
    if actual[:len(expected)]!=expected:
        raise RuntimeError("Original ten changed; do not compare until resolved: "+str(actual))
    original=[r for r in global_target if r["minute"] in set(expected)]
    additional=[r for r in global_target if r["minute"] not in set(expected)]
    report={"study":"Original 8/10 C2 confirmed reversal feature audit",
      "global_sample_reproduced":True,
      "original_sample_size":len(original),
      "additional_global_sample": [{"minute":r["minute"],"delta30":r["delta30"]} for r in additional],
      "original_global_30m":{"all":stats(original),
                             "successful_up":stats([r for r in original if r["delta30"]>0]),
                             "failed_down":stats([r for r in original if r["delta30"]<=0])},
      "target_first_30m":{"all":stats(target_first),
                          "successful_up":stats([r for r in target_first if r["delta30"]>0]),
                          "failed_down":stats([r for r in target_first if r["delta30"]<=0])},
      "all_confirmed":{"all":stats(all_target),
                       "successful_up":stats([r for r in all_target if r["delta30"]>0]),
                       "failed_down":stats([r for r in all_target if r["delta30"]<=0])},
      "original_ten":[{"minute":r["minute"],"delta30":r["delta30"],
                       "outcome":"UP" if r["delta30"]>0 else "DOWN_OR_FLAT",
                       **r["features"]} for r in original],
      "notes":["Only completed M1 bars used for features; forward prices used for outcome labels only",
               "Feature differences are exploratory, not trained or validated filters",
               "Original 10 observations were selected by chronological phase, not by features",
               "Sample size 8 successful/2 failed is too small for robust filter discovery",
               "Original 80% must not be interpreted as out-of-sample accuracy",
               "No actual V9.4 positions or execution; V9.4 LIVE and V9.5 PAPER unchanged"]}
    with dest.open("x",encoding="utf-8") as f:
        json.dump(report,f,indent=2);f.write("\n")
    print(json.dumps({k:v for k,v in report.items() if k!="original_ten"},indent=2))
    print("ORIGINAL_TEN",json.dumps(report["original_ten"]))
if __name__=="__main__":main()
