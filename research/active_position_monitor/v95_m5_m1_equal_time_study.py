"""Read-only equal-decision-time M5/M1 episode study.

At T=completed M5 candidate, compare an immediate hypothetical exit
at M1 open T with a predeclared 3-minute M1 confirmation rule.
At T+3, compare subsequent 5/15/30/60-minute price moves for ALL episodes,
not different starts for confirmed/rejected. Report delay and opportunity cost.
No private trade history, paper positions, execution or service writes.
"""
import argparse
import json
from pathlib import Path
from research.active_position_monitor.v95_m5_exit_challenger import assess
from research.active_position_monitor.v95_mtf_exit_study import load, aggregate, metrics

HORIZONS=(5,15,30,60)
WINDOW=3

def study(m1):
    m5=aggregate(m1,5)
    candidates=[]
    for b in sorted(m5):
        if all(i in m5 for i in range(b-15,b+1)):
            if assess([m5[i] for i in range(b-15,b+1)]).action=="EXIT_CANDIDATE":
                candidates.append(b)
    first=[b for i,b in enumerate(candidates) if i==0 or b!=candidates[i-1]+1]

    def continuous(t,n):
        return all(t+j in m1 for j in range(n))

    rows=[]
    for b in first:
        t=(b+1)*5
        if not continuous(t,WINDOW+1):
            rows.append(dict(status="EXCLUDED_CONFIRMATION_GAP",delay=None,post={},
                             confirmation_cost_bps=None,common_price_move_bps=None))
            continue
        immediate=m1[t]["o"]
        anchor=m5[b]["c"]
        delay=None
        for d in range(1,WINDOW+1):
            bar=m1[t+d-1]
            if bar["c"]>bar["o"] and bar["c"]>anchor:
                delay=d
                break
        # At t+d, next M1 open is earliest provisional confirmed fill.
        confirmed_fill=m1[t+delay]["o"] if delay is not None else None
        # All cohorts share the same T+3 starting price and future horizon.
        common_start=m1[t+WINDOW]["o"]
        post={}
        for h in HORIZONS:
            if continuous(t+WINDOW,h+1):
                end=m1[t+WINDOW+h]["o"]
                post[h]=(end-common_start)/common_start*10000
            else:
                post[h]=None
        rows.append(dict(
            status="CONFIRMED" if delay is not None else "REJECTED",
            delay=delay,
            confirmation_cost_bps=((confirmed_fill-immediate)/immediate*10000
                                   if confirmed_fill is not None else None),
            common_price_move_bps=(common_start-immediate)/immediate*10000,
            post=post
        ))
    usable=[r for r in rows if r["status"]!="EXCLUDED_CONFIRMATION_GAP"]
    yes=[r for r in usable if r["status"]=="CONFIRMED"]
    no=[r for r in usable if r["status"]=="REJECTED"]
    def summarize(group):
        return {str(h):metrics([r["post"][h] for r in group if r["post"][h] is not None])
                for h in HORIZONS}
    return dict(
        mode="OFFLINE_EQUAL_DECISION_TIME_M5_M1_RESEARCH",
        candidate_windows=len(candidates),
        episodes=len(first),
        eligible_episodes=len(usable),
        confirmed=len(yes),
        rejected=len(no),
        excluded_confirmation_gap=len(rows)-len(usable),
        confirmation_delay_counts={str(d):sum(r["delay"]==d for r in yes)
                                   for d in range(1,WINDOW+1)},
        confirmed_exit_delay_cost_bps=metrics([r["confirmation_cost_bps"] for r in yes]),
        confirmed_first_three_minute_move_bps=metrics([r["common_price_move_bps"] for r in yes]),
        rejected_first_three_minute_move_bps=metrics([r["common_price_move_bps"] for r in no]),
        forward_from_common_t_plus_3_bps=dict(
            all=summarize(usable),confirmed=summarize(yes),rejected=summarize(no)),
        limitations=[
            "First candidate of consecutive M5 EXIT_CANDIDATE windows defines each episode",
            "Confirmation must occur in first three completed M1 candles; no future candle leakage",
            "Equal follow-up starts at T+3 M1 open, independent of confirmation status",
            "Hypothetical immediate and confirmed fills use M1 opens; no execution costs",
            "Positive gold movement is adverse to a SELL held open, not realized trade R",
            "Rejected signals have no confirmation fill; comparison is descriptive not causal",
            "No SL/TP replay, paper trade data, or live V9.5 exit simulation",
            "Overlapping forward horizons and small sample undermine statistical independence",
            "In-sample study only; new future data needed for independent validation"
        ]
    )

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db",required=True)
    p.add_argument("--output",required=True)
    args=p.parse_args()
    report=study(load(args.db))
    dst=Path(args.output)
    if dst.exists() or dst.is_symlink():
        raise FileExistsError("Use a new report filename")
    # Aggregate-only report; preserve private destination if supplied.
    with dst.open("x",encoding="utf-8") as f:
        json.dump(report,f,indent=2,allow_nan=False)
        f.write("\n")
    print(json.dumps({k:report[k] for k in (
        "candidate_windows","episodes","eligible_episodes","confirmed",
        "rejected","excluded_confirmation_gap","confirmation_delay_counts",
        "confirmed_exit_delay_cost_bps","forward_from_common_t_plus_3_bps"
    )},indent=2))

if __name__=="__main__":
    main()
