"""Research-only M5-to-M1 confirmation episode study.

First candidate of each consecutive M5 EXIT_CANDIDATE run anchors an episode.
Confirmation is checked at the next 1, 2 or 3 *completed* M1 closes:
bullish M1 body and M1 close > anchor M5 close.
Forward outcomes use closes at fixed times after the anchor and after confirmation.
No private trade data, execution, or live service changes.
"""
import argparse
import json
from pathlib import Path
from research.active_position_monitor.v95_m5_exit_challenger import assess
from research.active_position_monitor.v95_m5_history_scan import minute_epoch
from research.active_position_monitor.v95_mtf_exit_study import load, aggregate, metrics

HORIZONS=(5,15,30,60)
CONFIRM_WINDOW=3

def analyze(m1):
    m5=aggregate(m1,5)
    candidates=[]
    for b in sorted(m5):
        if all(i in m5 for i in range(b-15,b+1)):
            if assess([m5[i] for i in range(b-15,b+1)]).action=="EXIT_CANDIDATE":
                candidates.append(b)
    episodes=[]
    for b in candidates:
        if not episodes or b!=episodes[-1][-1]+1:
            episodes.append([b])
        else:
            episodes[-1].append(b)

    def forward_close(anchor_minute,h):
        start=m1.get(anchor_minute-1)
        end=m1.get(anchor_minute+h-1)
        if start is None or end is None or any(
            minute not in m1 for minute in range(anchor_minute,anchor_minute+h)):
            return None
        return (end["c"]-start["c"])/start["c"]*10000

    rows=[]
    for episode in episodes:
        b=episode[0]
        t=(b+1)*5 # First minute after completed candidate M5
        anchor=m5[b]["c"]
        status="UNCONFIRMED"
        delay=None
        # For delay d, M1 candle [t+d-1, t+d) has just completed.
        # Do not inspect candle at or after a confirmation fill.
        for d in range(1,CONFIRM_WINDOW+1):
            candle=m1.get(t+d-1)
            if candle is None:
                status="INCOMPLETE_M1_CONFIRMATION_WINDOW"
                break
            if candle["c"]>candle["o"] and candle["c"]>anchor:
                status="CONFIRMED"
                delay=d
                break
        rows.append({
            "anchor_minute":t,
            "status":status,
            "delay":delay,
            "anchor_forward":{h:forward_close(t,h) for h in HORIZONS},
            "confirmed_forward":({h:forward_close(t+delay,h) for h in HORIZONS}
                                 if delay is not None else None),
            "delay_bps":((m1[t+delay-1]["c"]-anchor)/anchor*10000
                         if delay is not None else None),
        })

    confirmed=[r for r in rows if r["status"]=="CONFIRMED"]
    rejected=[r for r in rows if r["status"]=="UNCONFIRMED"]
    incomplete=[r for r in rows if r["status"]=="INCOMPLETE_M1_CONFIRMATION_WINDOW"]
    def summarize(items,key):
        return {str(h):metrics([r[key][h] for r in items
                                if r[key] is not None and r[key][h] is not None])
                for h in HORIZONS}
    return {
        "mode":"OFFLINE_M5_M1_EPISODE_RESEARCH_ONLY",
        "m5_candidate_windows":len(candidates),
        "candidate_episodes":len(rows),
        "confirmation_window_minutes":CONFIRM_WINDOW,
        "confirmed_episodes":len(confirmed),
        "unconfirmed_episodes":len(rejected),
        "incomplete_confirmation_windows":len(incomplete),
        "confirmation_delay_counts":{str(d):sum(r["delay"]==d for r in confirmed)
                                     for d in range(1,CONFIRM_WINDOW+1)},
        "all_anchor_forward_bps":summarize(rows,"anchor_forward"),
        "confirmed_anchor_forward_bps":summarize(confirmed,"anchor_forward"),
        "unconfirmed_anchor_forward_bps":summarize(rejected,"anchor_forward"),
        "confirmed_after_confirmation_forward_bps":summarize(confirmed,"confirmed_forward"),
        "confirmation_price_move_bps":metrics([r["delay_bps"] for r in confirmed]),
        "limitations":[
            "Consecutive M5 candidate windows grouped by first candidate only",
            "M1 confirmation is bullish candle closing above candidate M5 close",
            "Confirmed episodes are selected using subsequent 1-3 minutes; compare at equal decision times for causality",
            "Overlapping 5-60 minute outcomes are not statistically independent",
            "Positive gold returns are adverse to holding a SELL, not realized profit",
            "No trade positions, original V9.5 exit replay, SL/TP, spreads, commissions or slippage",
            "Small historical sample, not out-of-sample proof of exit improvement",
        ],
    }

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db",required=True)
    p.add_argument("--output",required=True)
    args=p.parse_args()
    report=analyze(load(args.db))
    dst=Path(args.output)
    if dst.exists() or dst.is_symlink():
        raise FileExistsError("Choose a new output path")
    with dst.open("x",encoding="utf-8") as f:
        json.dump(report,f,indent=2,allow_nan=False)
        f.write("\n")
    print(json.dumps({k:report[k] for k in (
        "m5_candidate_windows","candidate_episodes","confirmed_episodes",
        "unconfirmed_episodes","incomplete_confirmation_windows",
        "confirmation_delay_counts")}))
    print("Aggregate research report written.")

if __name__=="__main__":
    main()
