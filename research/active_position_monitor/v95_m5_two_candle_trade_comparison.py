"""Offline two-candle V9.5 SELL-exit hybrid vs recorded original exits.

Research-only. Read protected history as ubuntu; output private 0600.
No live service writes, trade execution, Telegram, or workflow artifacts.
"""
import argparse
import json
from research.active_position_monitor.v95_m5_exit_challenger import assess
from research.active_position_monitor.v95_m5_trade_comparison import (
    load_trades, load_events, load_candles, m5_window, seconds, utc, write_private
)


def compare_one(trade, pair, candles):
    entry_event, exit_event = pair
    start = seconds(trade["opened_at"])
    original_exit = seconds(exit_event["observed_at_utc"])
    if seconds(entry_event["m1_bar_start_utc"]) != start or original_exit <= start:
        raise ValueError("Invalid or mismatched trade chronology")
    entry, stop, target, original_fill = map(float, (
        trade["entry"], trade["initial_stop"], trade["target"], trade["hypothetical_fill"]
    ))
    if not target < entry < stop:
        raise ValueError("Invalid SELL protection levels")
    risk = stop - entry
    original_r = (entry - original_fill) / risk
    result = dict(original_r=round(original_r, 4), hybrid_r=None, delta_r=None,
                  original_exit_utc=utc(original_exit), hybrid_exit_utc=None,
                  outcome=None, candidates=0, confirmations=0, rejections=0)
    start_min = start // 60
    last_min = original_exit // 60
    warmup = (start // 300) * 5 - 80
    if any(m not in candles for m in range(warmup, last_min + 1)):
        result["outcome"] = "EXCLUDED_INCOMPLETE_M1"
        return result

    pending = None
    for minute in range(start_min, last_min + 1):
        bar = candles[minute]
        now = minute * 60
        # Original observed exit wins ties; never simulate a candidate at/after it.
        if minute % 5 == 0 and start < now < original_exit:
            last_completed_bucket = minute // 5 - 1
            completed = m5_window(candles, last_completed_bucket)
            if completed is None:
                result["outcome"] = "EXCLUDED_INCOMPLETE_SIGNAL_CONTEXT"
                return result
            last = completed[-1]
            if pending is not None:
                # Confirm on exactly the next completed M5 candle, not later.
                if minute == pending["minute"] + 5:
                    confirmed = last["c"] > last["o"] and last["c"] > pending["close"]
                    if confirmed:
                        result["confirmations"] += 1
                        if bar["o"] >= stop or bar["o"] <= target:
                            result["outcome"] = "INCONCLUSIVE_GAP_AT_CONFIRMED_EXIT"
                            return result
                        hybrid_r = (entry - bar["o"]) / risk
                        result.update(hybrid_r=round(hybrid_r, 4),
                                      delta_r=round(hybrid_r-original_r, 4),
                                      hybrid_exit_utc=utc(now),
                                      outcome="EARLY_TWO_CANDLE_EXIT")
                        return result
                    result["rejections"] += 1
                pending = None
            # New candidate only when no pending; no forward candles consulted.
            if pending is None:
                signal = assess(completed)
                if signal.action == "EXIT_CANDIDATE":
                    result["candidates"] += 1
                    pending = {"minute":minute,"close":last["c"]}
        # If protective levels were touched in a full M1 candle while trade
        # may have been active, reject clean-fill comparison. Intraminute
        # order and original-exit-minute exposure cannot be resolved.
        if bar["h"] >= stop or bar["l"] <= target:
            result["outcome"] = "INCONCLUSIVE_PROTECTIVE_LEVEL_TOUCHED"
            return result

    result.update(hybrid_r=round(original_r, 4), delta_r=0.0,
                  hybrid_exit_utc=utc(original_exit),
                  outcome="ORIGINAL_EXIT_RETAINED")
    return result


def compare(trades_path, journal_path, db_path):
    trades = load_trades(trades_path)
    events = load_events(journal_path)
    if len(trades) != len(events):
        raise ValueError("Trade count differs from journal event pairs")
    candles = load_candles(db_path)
    results=[]
    for index, (trade, pair) in enumerate(zip(trades, events), 1):
        row={"trade_number":index}
        row.update(compare_one(trade, pair, candles))
        results.append(row)
    valid=[r for r in results if r["delta_r"] is not None]
    return {
        "mode":"OFFLINE_TWO_CANDLE_HYBRID_RESEARCH_ONLY",
        "rule":"Candidate on completed M5 then next completed bullish M5 closes above candidate; exit at following M1 open only if before observed original exit",
        "trade_count":len(results),
        "comparable_count":len(valid),
        "total_delta_r_comparable":round(sum(r["delta_r"] for r in valid),4),
        "results":results,
        "limitations":[
            "Original exits are observed, not a reimplemented exit engine",
            "Requires complete M1 candles through original exit; gaps excluded",
            "M1 OHLC cannot resolve intraminute SL/TP ordering or partial exposure",
            "No executable spread, slippage, commission, or broker fills",
            "Paper trade sample is very small; results do not prove an edge",
            "No early exit can occur at or after the observed original exit",
            "Comparison does not change the running V9.5 service"
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
        "total_delta_r_comparable":report["total_delta_r_comparable"],
        "report_written":True,
        "note":"Private trade-level report stays on Oracle; do not upload"
    }))


if __name__=="__main__":
    main()
