"""Private read-only M5 candidate + completed M1 confirmation trade comparison.

Predeclared M1 rule: after completed M5 EXIT_CANDIDATE, within the next
three completed M1 bars, require bullish M1 body and M1 close above the
candidate M5 close. Hypothetical fill is following M1 open. Original
observed V9.5 exit always wins at same/earlier time.
"""
import argparse
import json
from research.active_position_monitor.v95_m5_exit_challenger import assess
from research.active_position_monitor.v95_m5_trade_comparison import (
    load_trades, load_events, load_candles, m5_window, seconds, utc, write_private
)

MAX_CONFIRM_MINUTES = 3

def compare_one(trade, pair, candles):
    entry_event, exit_event = pair
    start = seconds(trade["opened_at"])
    end = seconds(exit_event["observed_at_utc"])
    if seconds(entry_event["m1_bar_start_utc"]) != start or end <= start:
        raise ValueError("Unmatched or invalid trade chronology")
    entry, stop, target, observed_fill = map(float, (
        trade["entry"], trade["initial_stop"], trade["target"],
        trade["hypothetical_fill"]))
    if not target < entry < stop:
        raise ValueError("Invalid SELL SL/TP")
    risk = stop - entry
    original_r = (entry - observed_fill) / risk
    result = dict(original_r=round(original_r,4), hybrid_r=None, delta_r=None,
                  original_exit_utc=utc(end), hybrid_exit_utc=None,
                  outcome=None, candidates=0, m1_confirmations=0,
                  expired_candidates=0, confirmation_delay_minutes=None)
    start_min, end_min = start//60, end//60
    warmup = (start//300)*5-80
    if any(m not in candles for m in range(warmup,end_min+1)):
        result["outcome"]="EXCLUDED_INCOMPLETE_M1"
        return result

    pending = None
    for minute in range(start_min,end_min+1):
        now = minute*60
        bar = candles[minute]
        # At this minute OPEN, only the preceding completed M1 is known.
        # Confirm before considering a newly completed M5 candidate.
        if pending is not None and now < end:
            elapsed = minute - pending["minute"]
            if 1 <= elapsed <= MAX_CONFIRM_MINUTES:
                prior = candles[minute-1]
                if prior["c"] > prior["o"] and prior["c"] > pending["close"]:
                    if bar["o"] >= stop or bar["o"] <= target:
                        result["outcome"]="INCONCLUSIVE_GAP_AT_M1_CONFIRMATION"
                        return result
                    hypothetical_r=(entry-bar["o"])/risk
                    result.update(hybrid_r=round(hypothetical_r,4),
                                  delta_r=round(hypothetical_r-original_r,4),
                                  hybrid_exit_utc=utc(now),
                                  outcome="EARLY_M1_CONFIRMED_EXIT",
                                  m1_confirmations=1,
                                  confirmation_delay_minutes=elapsed)
                    return result
            if elapsed >= MAX_CONFIRM_MINUTES:
                result["expired_candidates"] += 1
                pending = None

        if minute%5==0 and start < now < end and pending is None:
            completed=m5_window(candles,minute//5-1)
            if completed is None:
                result["outcome"]="EXCLUDED_INCOMPLETE_SIGNAL_CONTEXT"
                return result
            signal=assess(completed)
            if signal.action=="EXIT_CANDIDATE":
                pending={"minute":minute,"close":completed[-1]["c"]}
                result["candidates"] += 1

        # Conservative: an SL/TP touch in an M1 bar may occur before
        # the paper exit or a candidate; do not invent intraminute ordering.
        if bar["h"] >= stop or bar["l"] <= target:
            result["outcome"]="INCONCLUSIVE_PROTECTIVE_LEVEL_TOUCHED"
            return result

    result.update(hybrid_r=round(original_r,4),delta_r=0.0,
                  hybrid_exit_utc=utc(end),outcome="ORIGINAL_EXIT_RETAINED")
    return result

def compare(trades_path,journal_path,db_path):
    trades=load_trades(trades_path)
    pairs=load_events(journal_path)
    if len(trades)!=len(pairs):
        raise ValueError("Trade count and journal events differ")
    candles=load_candles(db_path)
    rows=[]
    for i,(trade,pair) in enumerate(zip(trades,pairs),1):
        row={"trade_number":i}
        row.update(compare_one(trade,pair,candles))
        rows.append(row)
    valid=[r for r in rows if r["delta_r"] is not None]
    return {
        "mode":"OFFLINE_M5_M1_HYBRID_RESEARCH_ONLY",
        "confirmation_window_minutes":MAX_CONFIRM_MINUTES,
        "trade_count":len(rows),
        "comparable_count":len(valid),
        "total_delta_r_comparable":round(sum(r["delta_r"] for r in valid),4),
        "results":rows,
        "limitations":[
            "Observed original V9.5 exits are not reimplemented",
            "Full M1 continuity required; no missing data inferred",
            "M1 OHLC cannot establish intraminute SL/TP sequence",
            "No spreads, slippage, commissions, or executable broker fills",
            "Trade sample is small and this is not out-of-sample validation",
            "Original exit always wins ties; original exit minute conservatively screened",
            "Comparison does not change any running service or risk controls"
        ]
    }

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--trades",required=True)
    p.add_argument("--journal",required=True)
    p.add_argument("--db",required=True)
    p.add_argument("--output",required=True)
    args=p.parse_args()
    report=compare(args.trades,args.journal,args.db)
    write_private(args.output,report)
    print(json.dumps({
        "trade_count":report["trade_count"],
        "comparable_count":report["comparable_count"],
        "outcomes":{str(r["trade_number"]):r["outcome"] for r in report["results"]},
        "confirmation_delays_minutes":{str(r["trade_number"]):r["confirmation_delay_minutes"] for r in report["results"] if r["confirmation_delay_minutes"] is not None},
        "total_delta_r_comparable":report["total_delta_r_comparable"],
        "report_written":True
    }))

if __name__=="__main__":
    main()
