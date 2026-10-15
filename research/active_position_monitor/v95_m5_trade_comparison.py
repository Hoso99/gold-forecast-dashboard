"""Offline, read-only V9.5 paper exit comparison. Run locally as authorized ubuntu user.
No live services, alerts, order execution, or production state writes.
Report contains trade-level price-derived R values: keep output private.
"""
import argparse
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from research.active_position_monitor.v95_m5_exit_challenger import assess
from research.active_position_monitor.v95_m5_history_scan import minute_epoch


def seconds(value):
    d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if d.tzinfo is None:
        raise ValueError("Naive timestamps not supported")
    return int(d.astimezone(timezone.utc).timestamp())


def utc(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat()


def load_events(path):
    events = []
    with Path(path).open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                r = json.loads(line)
                if r.get("decision") in ("PAPER_SELL_ENTRY", "EXIT_SELL_NOW"):
                    events.append(r)
    events.sort(key=lambda r: seconds(r["observed_at_utc"]))
    if len(events) % 2 or any(
        events[i]["decision"] != "PAPER_SELL_ENTRY"
        or events[i+1]["decision"] != "EXIT_SELL_NOW"
        for i in range(0, len(events), 2)
    ):
        raise ValueError("Journal entry/exit sequence is not unambiguous")
    return [(events[i], events[i+1]) for i in range(0, len(events), 2)]


def load_trades(path):
    with Path(path).open(encoding="utf-8") as f:
        trades = [json.loads(line) for line in f if line.strip()]
    return sorted(trades, key=lambda r: seconds(r["opened_at"]))


def load_candles(path):
    con = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
    try:
        raw = con.execute(
            'SELECT minute, "open", high, low, "close" FROM candles ORDER BY minute'
        ).fetchall()
    finally:
        con.close()
    candles = {}
    for minute, o, h, l, c in raw:
        t = minute_epoch(minute)
        b = {"o": float(o), "h": float(h), "l": float(l), "c": float(c)}
        if not b["l"] <= min(b["o"], b["c"]) <= max(b["o"], b["c"]) <= b["h"]:
            raise ValueError("Invalid OHLC in database")
        if t in candles:
            raise ValueError("Duplicate M1 timestamp")
        candles[t] = b
    return candles


def m5_window(candles, bucket):
    result = []
    for b in range(bucket - 15, bucket + 1):
        rows = [candles.get(b * 5 + j) for j in range(5)]
        if any(x is None for x in rows):
            return None
        result.append({
            "o": rows[0]["o"], "h": max(x["h"] for x in rows),
            "l": min(x["l"] for x in rows), "c": rows[-1]["c"]
        })
    return result


def simulate(trade, pair, candles, last_minute, max_minutes):
    entry_event, exit_event = pair
    entry_sec = seconds(trade["opened_at"])
    if entry_sec != seconds(entry_event["m1_bar_start_utc"]):
        raise ValueError("Trade opening does not match journal candle timestamp")
    actual_exit_sec = seconds(exit_event["observed_at_utc"])
    if not entry_sec < actual_exit_sec:
        raise ValueError("Nonpositive paper trade duration")
    entry = float(trade["entry"])
    stop = float(trade["initial_stop"])
    target = float(trade["target"])
    actual_fill = float(trade["hypothetical_fill"])
    if not target < entry < stop:
        raise ValueError("Invalid SELL SL/TP")
    risk = stop - entry
    actual_r = (entry - actual_fill) / risk
    start_min = entry_sec // 60
    last_observed_min = actual_exit_sec // 60
    result = {
        "original_exit_utc": utc(actual_exit_sec),
        "original_r": round(actual_r, 4),
        "challenger_exit_utc": None,
        "challenger_r": None,
        "delta_r": None,
        "warnings": 0,
        "candidates": 0,
        "outcome": None,
    }
    # Require contiguous M1 bars from 80 minutes before the entry through the
    # original exit, plus all M1 bars needed to establish M5 signal context.
    warmup_min = (entry_sec // 300) * 5 - 80
    if any(m not in candles for m in range(warmup_min, last_observed_min + 1)):
        result["outcome"] = "EXCLUDED_MISSING_PRE_EXIT_CANDLES"
        return result
    # Never invent a future horizon or a fill after the database ends.
    horizon_min = min(last_minute, last_observed_min + max_minutes)
    # Track original protective levels from entry; one M1 candle may touch both.
    for minute in range(start_min, horizon_min + 1):
        bar = candles.get(minute)
        if bar is None:
            result["outcome"] = "INCONCLUSIVE_DATA_GAP"
            return result
        # At minute opening, execute prior completed-M5 candidate at M1 open.
        # Signal candle must have closed before this minute.
        if minute % 5 == 0 and minute * 60 > entry_sec:
            window = m5_window(candles, minute // 5 - 1)
            if window is not None:
                signal = assess(window)
                if signal.action == "WARNING":
                    result["warnings"] += 1
                elif signal.action == "EXIT_CANDIDATE":
                    result["candidates"] += 1
                    # Price at next M1 open; gap-through SL/TP is not treated as a clean fill.
                    if bar["o"] >= stop or bar["o"] <= target:
                        result["outcome"] = "INCONCLUSIVE_OPEN_BEYOND_PROTECTIVE_LEVEL"
                        return result
                    fill = bar["o"]
                    result["challenger_exit_utc"] = utc(minute * 60)
                    result["challenger_r"] = round((entry - fill) / risk, 4)
                    result["delta_r"] = round(result["challenger_r"] - actual_r, 4)
                    result["outcome"] = "M5_EXIT_CANDIDATE"
                    return result
        # SL and TP can occur within the M1 candle; when both touched,
        # ordering is unknown and must not be guessed.
        sl = bar["h"] >= stop
        tp = bar["l"] <= target
        if sl and tp:
            result["outcome"] = "INCONCLUSIVE_SL_TP_SAME_MINUTE"
            return result
        if sl or tp:
            # Opening beyond the protective level implies gap risk, not exact SL/TP fill.
            if (sl and bar["o"] > stop) or (tp and bar["o"] < target):
                result["outcome"] = "INCONCLUSIVE_PROTECTIVE_GAP"
                return result
            fill = stop if sl else target
            result["challenger_exit_utc"] = utc(minute * 60)
            result["challenger_r"] = round((entry - fill) / risk, 4)
            result["delta_r"] = round(result["challenger_r"] - actual_r, 4)
            result["outcome"] = "STOP_LOSS" if sl else "TAKE_PROFIT"
            return result
    result["outcome"] = "INCONCLUSIVE_HORIZON_OR_DATABASE_END"
    return result


def compare(trades_path, journal_path, db_path, max_minutes):
    trades = load_trades(trades_path)
    pairs = load_events(journal_path)
    if len(trades) != len(pairs):
        raise ValueError("Trade count does not match journal pairs")
    candles = load_candles(db_path)
    if not candles:
        raise ValueError("Empty candle database")
    last_minute = max(candles)
    results = []
    for idx, (trade, pair) in enumerate(zip(trades, pairs), 1):
        row = {"trade_number": idx}
        row.update(simulate(trade, pair, candles, last_minute, max_minutes))
        results.append(row)
    comparable = [r for r in results if r["delta_r"] is not None]
    return {
        "mode": "OFFLINE_RESEARCH_ONLY",
        "max_post_original_exit_minutes": max_minutes,
        "trade_count": len(results),
        "comparable_count": len(comparable),
        "total_delta_r_comparable": round(sum(r["delta_r"] for r in comparable), 4),
        "results": results,
        "limitations": [
            "Candle-body buy pressure is not executed market volume",
            "M1 OHLC cannot establish intraminute ordering; ambiguous bars are inconclusive",
            "No spread, slippage, commissions, or broker fill simulation",
            "Post-original-exit outcomes are hypothetical, not observed paper trades",
            "No conclusion about strategy profitability from a small sample",
        ],
    }


def write_private(path, report):
    dst = Path(path)
    if dst.is_symlink() or not dst.parent.is_dir() or dst.parent.stat().st_mode & 0o077:
        raise PermissionError("Output must be new file in private 0700 directory")
    fd = os.open(dst, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, allow_nan=False)
        f.write("\n")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--trades", required=True)
    p.add_argument("--journal", required=True)
    p.add_argument("--db", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--max-post-exit-minutes", type=int, default=240)
    args = p.parse_args()
    if not 1 <= args.max_post_exit_minutes <= 1440:
        p.error("max-post-exit-minutes must be 1..1440")
    report = compare(args.trades, args.journal, args.db, args.max_post_exit_minutes)
    write_private(args.output, report)
    print(json.dumps({
        "trade_count": report["trade_count"],
        "comparable_count": report["comparable_count"],
        "outcomes": {str(r["trade_number"]): r["outcome"] for r in report["results"]},
        "report_written": True,
        "note": "Detailed R results kept in private output; do not upload to public GitHub."
    }))


if __name__ == "__main__":
    main()
