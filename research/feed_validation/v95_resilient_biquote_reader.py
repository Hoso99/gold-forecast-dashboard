"""Research-only Biquote M1 reader tolerant of historical gaps.

Does not fill gaps, trade, modify databases, or bypass freshness validation.
The consumer must validate indicator-specific windows before creating entries.
"""
import datetime as dt
import math
import sqlite3
from pathlib import Path

UTC = dt.timezone.utc
DEFAULT_DB = Path("/home/ubuntu/v95-detector-dev/research/feed_validation/biquote_m1.sqlite3")


def read_candles(db_path=DEFAULT_DB, limit=2500, now=None, max_age_seconds=180):
    now = now or dt.datetime.now(UTC)
    if now.tzinfo is None or now.utcoffset() != dt.timedelta(0):
        raise ValueError("now must be UTC")
    with sqlite3.connect(f"file:{Path(db_path).resolve()}?mode=ro", uri=True) as db:
        records = db.execute(
            "SELECT minute, open, high, low, close FROM candles "
            "ORDER BY minute DESC LIMIT ?", (limit,)
        ).fetchall()
    rows = []
    for minute, o, h, l, c in records:
        try:
            t = dt.datetime.fromisoformat(minute)
            vals = (float(o), float(h), float(l), float(c))
        except (ValueError, TypeError, OverflowError) as exc:
            raise RuntimeError("WAIT_DATA: invalid Biquote M1 row") from exc
        if (t.tzinfo is None or t.utcoffset() != dt.timedelta(0)
                or t.second or t.microsecond
                or not all(math.isfinite(x) and x > 0 for x in vals)
                or not vals[2] <= min(vals[0], vals[3]) <= max(vals[0], vals[3]) <= vals[1]):
            raise RuntimeError("WAIT_DATA: invalid Biquote M1 OHLC/timestamp")
        # Incomplete candles are never eligible for evaluation.
        if t + dt.timedelta(minutes=1) > now - dt.timedelta(seconds=10):
            continue
        rows.append(dict(zip(("t", "o", "h", "l", "c"), (t, *vals))))
    rows.sort(key=lambda x: x["t"])
    if not rows:
        raise RuntimeError("WAIT_DATA: no completed Biquote M1")
    if any(b["t"] <= a["t"] for a, b in zip(rows, rows[1:])):
        raise RuntimeError("WAIT_DATA: duplicate or unsorted Biquote M1")
    age = (now - (rows[-1]["t"] + dt.timedelta(minutes=1))).total_seconds()
    if age < 0 or age > max_age_seconds:
        raise RuntimeError("WAIT_DATA: stale Biquote M1")
    return rows
