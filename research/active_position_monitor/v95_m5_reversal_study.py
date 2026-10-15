"""Research-only V9.5 M5 reversal study on historical Biquote M1 candles.

Reports forward adverse price movement for a hypothetical SELL at each completed
M5 signal. Not a trade replay, fill simulation, or volume study.
No live service, trading, Telegram, or private paper journal access.
"""
import argparse
import json
import math
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from research.active_position_monitor.v95_m5_exit_challenger import assess
from research.active_position_monitor.v95_m5_history_scan import minute_epoch

HORIZONS = (5, 15, 30, 60)


def load_m5(db):
    con = sqlite3.connect(Path(db).resolve().as_uri() + "?mode=ro", uri=True)
    try:
        raw = con.execute('SELECT minute, "open", high, low, "close" FROM candles').fetchall()
    finally:
        con.close()
    m1 = {}
    for minute, o, h, l, c in raw:
        t = minute_epoch(minute)
        b = {"o": float(o), "h": float(h), "l": float(l), "c": float(c)}
        if not all(math.isfinite(x) for x in b.values()):
            raise ValueError("Nonfinite candle value")
        if not b["l"] <= min(b["o"], b["c"]) <= max(b["o"], b["c"]) <= b["h"]:
            raise ValueError("Invalid M1 OHLC")
        if t in m1:
            raise ValueError("Duplicate M1 timestamp")
        m1[t] = b
    complete = {}
    for bucket in sorted({t // 5 for t in m1}):
        rows = [m1.get(bucket * 5 + j) for j in range(5)]
        if any(row is None for row in rows):
            continue
        complete[bucket] = {
            "o": rows[0]["o"],
            "h": max(r["h"] for r in rows),
            "l": min(r["l"] for r in rows),
            "c": rows[-1]["c"],
        }
    return complete, len(m1)


def median(values):
    values = sorted(values)
    if not values:
        return None
    n = len(values)
    return (values[(n - 1) // 2] + values[n // 2]) / 2


def stats(values):
    if not values:
        return {"n": 0, "mean_bps": None, "median_bps": None, "rise_fraction": None}
    return {
        "n": len(values),
        "mean_bps": round(sum(values) / len(values), 3),
        "median_bps": round(median(values), 3),
        "rise_fraction": round(sum(v > 0 for v in values) / len(values), 4),
    }


def analyze(complete):
    buckets = sorted(complete)
    observations = []
    for b in buckets:
        if not all(t in complete for t in range(b - 15, b + 1)):
            continue
        window = [complete[t] for t in range(b - 15, b + 1)]
        result = assess(window)
        # At completed signal bar's close, future closes cannot be read until
        # the corresponding horizon has fully elapsed.
        forward = {}
        for horizon in HORIZONS:
            steps = horizon // 5
            if all(t in complete for t in range(b + 1, b + steps + 1)):
                initial = complete[b]["c"]
                final = complete[b + steps]["c"]
                forward[horizon] = (final - initial) / initial * 10000
            else:
                forward[horizon] = None
        observations.append({"bucket": b, "action": result.action, "forward": forward})

    # Group consecutive candidate windows into distinct episodes; this is
    # still not equivalent to counting independent market reversals or trades.
    candidate_buckets = [r["bucket"] for r in observations if r["action"] == "EXIT_CANDIDATE"]
    episodes = []
    for b in candidate_buckets:
        if not episodes or b != episodes[-1][-1] + 1:
            episodes.append([b])
        else:
            episodes[-1].append(b)
    first_of_episode = set(e[0] for e in episodes)

    # Fixed 60-minute embargo across *all* observations, chosen before
    # examining outcomes. Reduces, but does not eliminate, dependence.
    nonoverlap = []
    next_allowed = -10**30
    for r in observations:
        if r["bucket"] >= next_allowed:
            nonoverlap.append(r)
            next_allowed = r["bucket"] + 12

    def breakdown(rows):
        return {
            action: {
                str(h): stats([
                    r["forward"][h] for r in rows
                    if r["action"] == action and r["forward"][h] is not None
                ])
                for h in HORIZONS
            }
            for action in ("HOLD", "WARNING", "EXIT_CANDIDATE")
        }

    return {
        "eligible_m5_windows": len(observations),
        "action_counts": dict(Counter(r["action"] for r in observations)),
        "candidate_episode_count": len(episodes),
        "candidate_episode_lengths_in_windows": [len(e) for e in episodes],
        "nonoverlap_60m_windows": len(nonoverlap),
        "nonoverlap_action_counts": dict(Counter(r["action"] for r in nonoverlap)),
        "full_window_forward_return_bps": breakdown(observations),
        "episode_first_candidate_forward_return_bps": {
            str(h): stats([
                r["forward"][h] for r in observations
                if r["bucket"] in first_of_episode and r["forward"][h] is not None
            ]) for h in HORIZONS
        },
        "nonoverlap_forward_return_bps": breakdown(nonoverlap),
        "interpretation": "Positive forward bps means gold rose after the signal, adverse for an open SELL. Negative means gold fell.",
        "limitations": [
            "All-window forward observations overlap and are statistically dependent",
            "Episode grouping merges only immediately consecutive candidate windows",
            "Nonoverlap sample is chronological fixed-grid sampling, not balanced by action",
            "Price-body BUY power is not executed buy volume",
            "Close-to-close forward returns exclude spreads, slippage, SL/TP, and execution",
            "A useful reversal signal does not prove an improved hybrid trade exit",
        ],
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()
    m5, count = load_m5(args.db)
    report = analyze(m5)
    report["valid_m1_candles"] = count
    report["complete_m5_candles"] = len(m5)
    # Aggregate report only. Exclusive output creation avoids overwriting.
    dst = Path(args.output)
    if dst.exists():
        raise FileExistsError("Choose a new report path; will not overwrite")
    with dst.open("x", encoding="utf-8") as f:
        json.dump(report, f, indent=2, allow_nan=False)
        f.write("\n")
    print(json.dumps({
        "eligible_m5_windows": report["eligible_m5_windows"],
        "action_counts": report["action_counts"],
        "candidate_episode_count": report["candidate_episode_count"],
        "nonoverlap_60m_windows": report["nonoverlap_60m_windows"],
        "nonoverlap_action_counts": report["nonoverlap_action_counts"],
        "report_written": True,
    }))


if __name__ == "__main__":
    main()
