"""Causal UTC M1-to-higher-timeframe OHLC aggregation for V9.6 research.

Only fully observed, contiguous UTC buckets are emitted. Partial and
gap-containing buckets are discarded, never forward-filled.
"""
from datetime import datetime, timedelta, timezone

def aggregate_complete_m1(rows, minutes):
    if minutes not in (5, 15, 60, 240):
        raise ValueError("Unsupported timeframe")
    bucket = []
    start = None
    previous = None
    for row in rows:
        ts = datetime.fromisoformat(row["minute_utc"])
        if ts.tzinfo is not None:
            if ts.utcoffset() != timedelta(0):
                raise ValueError("Timestamps must be UTC")
            ts = ts.replace(tzinfo=None)
        minute_index = (ts.hour * 60 + ts.minute) // minutes * minutes
        aligned = ts.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(minutes=minute_index)
        if start != aligned or (previous is not None and ts - previous != timedelta(minutes=1)):
            bucket = []
            start = aligned
        if ts != start + timedelta(minutes=len(bucket)):
            bucket = []
            start = aligned
        bucket.append(row)
        previous = ts
        if len(bucket) == minutes:
            yield {
                "minute_utc": start.strftime("%Y-%m-%d %H:%M:%S"),
                "end_utc": ts.strftime("%Y-%m-%d %H:%M:%S"),
                "o": bucket[0]["o"],
                "h": max(b["h"] for b in bucket),
                "l": min(b["l"] for b in bucket),
                "c": bucket[-1]["c"],
            }
            bucket = []
            start = None
