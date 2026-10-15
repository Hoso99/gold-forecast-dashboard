"""Read-only historical Biquote M1 continuity and completed M5 exit scan.

Reports aggregate diagnostics only. No execution, alerts, trade or state writes.
"""
import argparse
import json
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from research.active_position_monitor.v95_m5_exit_challenger import assess

def minute_epoch(value):
    if isinstance(value, (int, float)) or (isinstance(value, str) and value.strip().lstrip("-").isdigit()):
        v = int(value)
        if abs(v) >= 10**12:  # milliseconds
            v //= 1000
        if abs(v) >= 10**9:  # epoch seconds
            return v // 60
        return v  # epoch minutes
    s = str(value).strip().replace("Z", "+00:00")
    d = datetime.fromisoformat(s)
    if d.tzinfo is None:
        raise ValueError("Naive timestamp cannot be safely interpreted as UTC")
    return int(d.astimezone(timezone.utc).timestamp()) // 60

def scan(db_path):
    con = sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True)
    try:
        raw = con.execute(
            'SELECT minute, "open", high, low, "close" FROM candles ORDER BY minute'
        ).fetchall()
    finally:
        con.close()
    records = {}
    invalid = duplicates = 0
    for minute, o, h, l, c in raw:
        try:
            ts = minute_epoch(minute)
            b = {"o":float(o), "h":float(h), "l":float(l), "c":float(c)}
            if not b["l"] <= min(b["o"],b["c"]) <= max(b["o"],b["c"]) <= b["h"]:
                raise ValueError("bad OHLC")
            if ts in records:
                duplicates += 1
                continue
            records[ts] = b
        except (ValueError, TypeError, OverflowError):
            invalid += 1
    keys = sorted(records)
    gaps = sum(max(0, b-a-1) for a,b in zip(keys, keys[1:]))
    # Group only 5 exact, distinct UTC minutes in each aligned M5 interval.
    buckets = {}
    for ts in keys:
        buckets.setdefault(ts//5, []).append(ts)
    completed = []
    for bucket in sorted(buckets):
        times = buckets[bucket]
        if times != list(range(bucket*5, bucket*5+5)):
            continue
        bars = [records[t] for t in times]
        completed.append((bucket, {
            "o":bars[0]["o"], "h":max(b["h"] for b in bars),
            "l":min(b["l"] for b in bars), "c":bars[-1]["c"]
        }))
    counts = Counter()
    scanned = 0
    # Prevent a gap in completed M5 bars from being treated as continuous history.
    for i in range(15, len(completed)):
        window = completed[i-15:i+1]
        if any(window[j][0] != window[j-1][0]+1 for j in range(1,len(window))):
            continue
        result = assess([bar for _,bar in window])
        counts[result.action] += 1
        scanned += 1
    return {
        "raw_rows":len(raw), "valid_unique_m1":len(keys),
        "duplicate_minutes":duplicates, "invalid_rows":invalid,
        "first_minute_utc":datetime.fromtimestamp(keys[0]*60,timezone.utc).isoformat() if keys else None,
        "last_minute_utc":datetime.fromtimestamp(keys[-1]*60,timezone.utc).isoformat() if keys else None,
        "missing_m1_minutes_in_full_span_including_market_closures":gaps,
        "complete_m5_bars":len(completed),
        "contiguous_16_m5_windows_scanned":scanned,
        "exit_candidate_windows":counts["EXIT_CANDIDATE"],
        "warning_windows":counts["WARNING"],
        "hold_windows":counts["HOLD"],
        "note":"Research signal counts only; not trades, fills, realized returns or backtest performance."
    }

if __name__ == "__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--db", required=True)
    p.add_argument("--output", required=True)
    args=p.parse_args()
    report=scan(args.db)
    Path(args.output).write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,indent=2))
