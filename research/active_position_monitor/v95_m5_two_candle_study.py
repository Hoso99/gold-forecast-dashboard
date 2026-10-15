"""Read-only two-candle M5 exit timing experiment.

First candidate of each consecutive EXIT_CANDIDATE episode is the anchor.
B confirms at next completed M5 close only if candle is bullish and closes
above candidate close. A triggers at candidate close. Both use only information
known at their respective signal times. No live trading or paper state access.
"""
import argparse
import json
from pathlib import Path
from research.active_position_monitor.v95_mtf_exit_study import load, aggregate, metrics
from research.active_position_monitor.v95_m5_exit_challenger import assess

HORIZONS=(5,15,30,60)

def study(m1):
    m5=aggregate(m1,5)
    candidates=[]
    for b in sorted(m5):
        if all(x in m5 for x in range(b-15,b+1)):
            a=assess([m5[x] for x in range(b-15,b+1)])
            if a.action=="EXIT_CANDIDATE":
                candidates.append(b)
    episodes=[]
    for b in candidates:
        if not episodes or b!=episodes[-1][-1]+1:
            episodes.append([b])
        else:
            episodes[-1].append(b)
    first=[e[0] for e in episodes]
    def future(b,h):
        n=h//5
        if not all(x in m5 for x in range(b+1,b+n+1)):
            return None
        return (m5[b+n]["c"]-m5[b]["c"])/m5[b]["c"]*10000

    rows=[]
    for b in first:
        next_bar=m5.get(b+1)
        contiguous=next_bar is not None
        confirmed=(contiguous and next_bar["c"]>next_bar["o"]
                   and next_bar["c"]>m5[b]["c"])
        rows.append({
            "b":b,"next_available":contiguous,"confirmed":confirmed,
            "a":{h:future(b,h) for h in HORIZONS},
            "b_forward":{h:future(b+1,h) if confirmed else None for h in HORIZONS},
            "delay_price_bps":((m5[b+1]["c"]-m5[b]["c"])/m5[b]["c"]*10000)
                              if contiguous else None,
        })
    confirmed=[r for r in rows if r["confirmed"]]
    def summary(items,key):
        return {str(h):metrics([r[key][h] for r in items if r[key][h] is not None])
                for h in HORIZONS}
    return {
        "mode":"RESEARCH_ONLY_NO_TRADE_REPLAY",
        "complete_m5":len(m5),
        "candidate_windows":len(candidates),
        "first_candidate_episodes":len(rows),
        "second_bar_available":sum(r["next_available"] for r in rows),
        "second_bar_confirmed":len(confirmed),
        "second_bar_rejected":sum(r["next_available"] and not r["confirmed"] for r in rows),
        "second_bar_unavailable":sum(not r["next_available"] for r in rows),
        "confirmation_delay_minutes":5,
        "a_first_candidate_all_episodes_forward_bps":summary(rows,"a"),
        "a_first_candidate_confirmed_subset_forward_bps":summary(confirmed,"a"),
        "b_after_second_candle_confirmed_subset_forward_bps":summary(confirmed,"b_forward"),
        "delay_price_move_confirmed_bps":metrics([r["delay_price_bps"] for r in confirmed]),
        "unconfirmed_a_forward_bps":summary([r for r in rows if r["next_available"] and not r["confirmed"]],"a"),
        "limitations":[
            "No trade PnL, original V9.5 exit replay, spread, slippage or stop/target handling",
            "A and B have different decision times; same-horizon forward returns are not directly interchangeable",
            "B excludes unconfirmed episodes, causing selection differences",
            "A second candle may be too late for a profitable exit",
            "Episodes can overlap forward horizons and are not independent trades",
            "Predeclared confirmation rule has not been validated out of sample",
            "Original V9.5 exit fallback is not simulated in this candle-only study",
        ],
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--db",required=True)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    result=study(load(a.db))
    dst=Path(a.output)
    if dst.exists() or dst.is_symlink():
        raise FileExistsError("Use a new report filename")
    with dst.open("x",encoding="utf-8") as f:
        json.dump(result,f,indent=2,allow_nan=False)
        f.write("\n")
    print(json.dumps({k:result[k] for k in (
        "candidate_windows","first_candidate_episodes","second_bar_available",
        "second_bar_confirmed","second_bar_rejected","second_bar_unavailable")}))
    print("Aggregate report written.")

if __name__=="__main__":
    main()
