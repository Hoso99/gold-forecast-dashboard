"""V9.5 staging-only historical M15 validation and source reconciliation.

No network calls, no broker orders, no changes to live monitor or SQLite.
Twelve Data M15 is kept separate from Biquote M1-derived M15.
"""
import datetime as dt
import math

UTC = dt.timezone.utc
REQUIRED_M15 = 18


def parse_twelve_data_m15(values, *, now):
    """Validate completed UTC 15m bars; reject duplicates, future/incomplete OHLC."""
    if now.tzinfo is None or now.utcoffset() != dt.timedelta(0):
        raise ValueError("now must be timezone-aware UTC")
    result = []
    for row in values:
        stamp = row.get("datetime")
        if not isinstance(stamp, str):
            raise ValueError("missing candle timestamp")
        t = dt.datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if t.tzinfo is None:
            # Twelve Data 'timezone=UTC' returns naive UTC datetime strings.
            t = t.replace(tzinfo=UTC)
        t = t.astimezone(UTC)
        if t.minute % 15 or t.second or t.microsecond:
            raise ValueError("misaligned M15 candle")
        if t + dt.timedelta(minutes=15) > now:
            continue  # never include an unfinished candle
        o, h, l, c = (float(row[k]) for k in ("open", "high", "low", "close"))
        if (not all(math.isfinite(x) and x > 0 for x in (o, h, l, c))
                or not l <= min(o, c) <= max(o, c) <= h):
            raise ValueError("invalid OHLC")
        result.append({"t": t, "o": o, "h": h, "l": l, "c": c})
    result.sort(key=lambda x: x["t"])
    if len({x["t"] for x in result}) != len(result):
        raise ValueError("duplicate historical candles")
    return result


def validate_indicator_window(bars, *, now, required=REQUIRED_M15):
    """Only a continuous, latest-closed M15 tail is usable for indicator research."""
    if len(bars) < required:
        return False, "insufficient M15 history"
    tail = bars[-required:]
    if any(b["t"] - a["t"] != dt.timedelta(minutes=15)
           for a, b in zip(tail, tail[1:])):
        return False, "gap in M15 history"
    expected = now.replace(minute=(now.minute // 15) * 15,
                           second=0, microsecond=0) - dt.timedelta(minutes=15)
    if tail[-1]["t"] != expected:
        return False, "latest completed M15 missing"
    return True, "READY"


def compare_sources(biquote_m15, twelve_m15, *, max_close_diff=1.0):
    """Fail closed on incompatible sources. Never splice the two OHLC histories."""
    by_time = {x["t"]: x for x in biquote_m15}
    comparisons = []
    for bar in twelve_m15:
        old = by_time.get(bar["t"])
        if old is None:
            continue
        delta = abs(old["c"] - bar["c"])
        comparisons.append({"t": bar["t"].isoformat(), "close_diff": delta})
    if not comparisons:
        return False, "no common completed M15 timestamps", comparisons
    largest = max(x["close_diff"] for x in comparisons)
    if largest > max_close_diff:
        return False, f"provider discrepancy exceeds threshold: {largest:.4f}", comparisons
    return True, "sources within close-difference threshold", comparisons
