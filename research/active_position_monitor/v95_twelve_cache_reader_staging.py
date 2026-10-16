"""V9.5 staging-only coherent Twelve Data M1 reader.

Drop-in candles() source for a separately approved PAPER deployment. Never
mixes Biquote and Twelve Data OHLC, and never falls back silently. Requires
fresh completed M1 and sufficient contiguous indicator windows.
"""
import datetime as dt
import math
import sqlite3
from pathlib import Path

UTC = dt.timezone.utc
DEFAULT_CACHE = Path("/home/ubuntu/v95-recovery-staging/twelve_m1_cache.sqlite3")


def read_candles(cache=DEFAULT_CACHE, now=None, limit=2500, max_age_seconds=180):
    now = now or dt.datetime.now(UTC)
    if now.tzinfo is None or now.utcoffset() != dt.timedelta(0):
        raise ValueError("now must be UTC")
    with sqlite3.connect(f"file:{Path(cache).resolve()}?mode=ro", uri=True) as db:
        records = db.execute(
            "SELECT minute_utc, open, high, low, close FROM twelve_m1 "
            "ORDER BY minute_utc DESC LIMIT ?", (limit,)
        ).fetchall()
    rows = []
    for stamp, o, h, l, c in reversed(records):
        t = dt.datetime.fromisoformat(stamp)
        vals = [float(x) for x in (o, h, l, c)]
        if (t.tzinfo is None or t.utcoffset() != dt.timedelta(0)
                or t.second or t.microsecond
                or not all(math.isfinite(x) and x > 0 for x in vals)
                or not vals[2] <= min(vals[0], vals[3]) <= max(vals[0], vals[3]) <= vals[1]):
            raise RuntimeError("WAIT_DATA: invalid Twelve Data cached M1")
        if t + dt.timedelta(minutes=1) > now - dt.timedelta(seconds=10):
            continue
        rows.append(dict(zip(("t", "o", "h", "l", "c"), (t, *vals))))
    if not rows:
        raise RuntimeError("WAIT_DATA: no completed Twelve Data M1")
    if any(b["t"] <= a["t"] for a, b in zip(rows, rows[1:])):
        raise RuntimeError("WAIT_DATA: duplicate or unsorted Twelve Data M1")
    age = (now - rows[-1]["t"] - dt.timedelta(minutes=1)).total_seconds()
    if age < 0 or age > max_age_seconds:
        raise RuntimeError("WAIT_DATA: stale Twelve Data M1 cache")
    return rows
