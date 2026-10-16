"""Staging-only single-provider V9.5 PAPER dry-run on cached Twelve Data M1.

Runs the original V9.5 evaluate() entirely in memory. No state persistence,
Telegram, journal, order, or live monitor changes. No Biquote/Twelve mixing.
"""
import argparse
import datetime as dt
import json
import sqlite3
from pathlib import Path

from v95_paper_monitor import evaluate, aggregate
from v95_gap_aware_gate import check

UTC = dt.timezone.utc


def dry_run(path, now=None):
    now = now or dt.datetime.now(UTC)
    with sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True) as db:
        data = db.execute("SELECT minute_utc, open, high, low, close FROM twelve_m1 ORDER BY minute_utc").fetchall()
    rows = []
    for stamp, o, h, l, c in data:
        t = dt.datetime.fromisoformat(stamp)
        if t.tzinfo is None or t.utcoffset() != dt.timedelta(0):
            raise ValueError("non-UTC cached candle")
        if t + dt.timedelta(minutes=1) <= now - dt.timedelta(seconds=10):
            rows.append({"t": t, "o": o, "h": h, "l": l, "c": c})
    ready, reason, details = check(rows, aggregate, now=now)
    result = {"source": "TWELVE_DATA_ONLY", "gate_ready": ready,
              "gate_reason": reason, "paper_state_saved": False,
              "telegram_sent": False, "broker_order_sent": False}
    if not ready:
        return result
    # Fresh disposable state; no active positions are loaded or altered.
    state = {"last_bar": None, "paper_position": None, "last_event": None}
    updated, action, note = evaluate(rows, state, {"risk": "UNKNOWN"})
    result["dry_run_action"] = action
    result["dry_run_reason"] = note
    result["hypothetical_position_created_in_memory"] = bool(updated.get("paper_position"))
    result["m5_bars"] = len(aggregate(rows, 5))
    result["m15_bars"] = len(aggregate(rows, 15))
    result["h1_bars"] = len(aggregate(rows, 60))
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, default=Path("/home/ubuntu/v95-recovery-staging/twelve_m1_cache.sqlite3"))
    args = parser.parse_args()
    print(json.dumps(dry_run(args.cache), indent=2, default=str))


if __name__ == "__main__":
    main()
