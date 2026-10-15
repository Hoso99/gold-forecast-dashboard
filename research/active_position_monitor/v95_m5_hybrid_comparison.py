"""Offline V9.5 hybrid exit challenger: earlier confirmed M5 or original paper exit.

Research only. No order placement, service access beyond explicit read-only paths,
alerts, state modification, or GitHub artifact upload. Keep output private.
"""
import argparse
import json

from research.active_position_monitor.v95_m5_exit_challenger import assess
from research.active_position_monitor.v95_m5_trade_comparison import (
    load_trades, load_events, load_candles, m5_window, seconds, utc, write_private,
)


def hybrid_one(trade, pair, candles):
    entry_event, exit_event = pair
    start = seconds(trade["opened_at"])
    original_exit = seconds(exit_event["observed_at_utc"])
    if seconds(entry_event["m1_bar_start_utc"]) != start or original_exit <= start:
        raise ValueError("Unmatched or invalid trade chronology")
    entry = float(trade["entry"])
    stop = float(trade["initial_stop"])
    target = float(trade["target"])
    actual_fill = float(trade["hypothetical_fill"])
    if not target < entry < stop:
        raise ValueError("Invalid SELL protective levels")
    risk = stop - entry
    original_r = (entry - actual_fill) / risk
    result = {
        "original_r": round(original_r, 4),
        "hybrid_r": None,
        "delta_r": None,
        "hybrid_exit_utc": None,
        "original_exit_utc": utc(original_exit),
        "outcome": None,
        "warnings": 0,
        "candidates": 0,
    }
    first_minute = start // 60
    last_minute = original_exit // 60
    # Require complete M1 coverage throughout the original trade and the
    # 80-minute M5 context preceding entry; never treat missing data as HOLD.
    warmup_start = (start // 300) * 5 - 80
    if any(m not in candles for m in range(warmup_start, last_minute + 1)):
        result["outcome"] = "EXCLUDED_INCOMPLETE_M1"
        return result
    for minute in range(first_minute, last_minute + 1):
        bar = candles[minute]
        # Only completed M5 signals; next M1 candle OPEN is provisional fill.
        # Original exit always takes precedence at the same timestamp.
        signal_sec = minute * 60
        if minute % 5 == 0 and start < signal_sec < original_exit:
            window = m5_window(candles, minute // 5 - 1)
            if window is None:
                result["outcome"] = "EXCLUDED_INCOMPLETE_SIGNAL_CONTEXT"
                return result
            signal = assess(window)
            if signal.action == "WARNING":
                result["warnings"] += 1
            elif signal.action == "EXIT_CANDIDATE":
                result["candidates"] += 1
                if bar["o"] >= stop or bar["o"] <= target:
                    result["outcome"] = "INCONCLUSIVE_GAP_AT_CANDIDATE"
                    return result
                hybrid_r = (entry - bar["o"]) / risk
                result.update(
                    hybrid_r=round(hybrid_r, 4),
                    delta_r=round(hybrid_r - original_r, 4),
                    hybrid_exit_utc=utc(signal_sec),
                    outcome="EARLY_M5_EXIT",
                )
                return result
        # Prior protective-level touches invalidate an assumed clean M5 fill.
        # This check is conservative: even the entry/exit minute is checked in
        # full, although actual exposure may cover only part of that minute.
        sl = bar["h"] >= stop
        tp = bar["l"] <= target
        if sl or tp:
            result["outcome"] = "INCONCLUSIVE_PROTECTIVE_LEVEL_TOUCHED"
            return result
    # No earlier candidate: retain the observed original paper exit exactly.
    result.update(
        hybrid_r=round(original_r, 4),
        delta_r=0.0,
        hybrid_exit_utc=utc(original_exit),
        outcome="ORIGINAL_EXIT_RETAINED",
    )
    return result


def compare(trades_path, journal_path, db_path):
    trades = load_trades(trades_path)
    pairs = load_events(journal_path)
    if len(trades) != len(pairs):
        raise ValueError("Trade count and journal pairs differ")
    candles = load_candles(db_path)
    rows = []
    for i, (trade, pair) in enumerate(zip(trades, pairs), 1):
        row = {"trade_number": i}
        row.update(hybrid_one(trade, pair, candles))
        rows.append(row)
    comparable = [r for r in rows if r["delta_r"] is not None]
    return {
        "mode": "OFFLINE_HYBRID_RESEARCH_ONLY",
        "rule": "Earlier completed-M5 EXIT_CANDIDATE or observed original exit, whichever first",
        "trade_count": len(rows),
        "comparable_count": len(comparable),
        "total_delta_r_comparable": round(sum(r["delta_r"] for r in comparable), 4),
        "results": rows,
        "limitations": [
            "Original V9.5 exits are historical observations, not a reimplemented exit engine",
            "M1 OHLC cannot resolve intraminute protective-level ordering",
            "Spread, slippage, commission and executable fill prices are not modeled",
            "Missing candle history is excluded, not interpreted as a hold",
            "Trade sample is small; this is not a validated performance estimate",
        ],
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--trades", required=True)
    p.add_argument("--journal", required=True)
    p.add_argument("--db", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()
    report = compare(args.trades, args.journal, args.db)
    write_private(args.output, report)
    print(json.dumps({
        "trade_count": report["trade_count"],
        "comparable_count": report["comparable_count"],
        "outcomes": {str(r["trade_number"]): r["outcome"] for r in report["results"]},
        "total_delta_r_comparable": report["total_delta_r_comparable"],
        "report_written": True,
    }))


if __name__ == "__main__":
    main()
