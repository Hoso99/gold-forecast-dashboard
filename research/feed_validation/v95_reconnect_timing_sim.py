"""Offline research only. No prices, no network and no database writes."""
from datetime import timedelta


def timing_eligible(minute, ticks, interruptions=()):
    """Necessary timing conditions only, never a valid OHLC candle."""
    end = minute + timedelta(minutes=1)
    if any(start < end and stop > minute for start, stop in interruptions):
        return False
    inside = sorted(t for t in ticks if minute <= t < end)
    if len(inside) < 2:
        return False
    if (inside[0] - minute).total_seconds() > 5:
        return False
    if (end - inside[-1]).total_seconds() > 5:
        return False
    if any((b - a).total_seconds() > 10 for a, b in zip(inside, inside[1:])):
        return False
    return any(end <= t <= end + timedelta(seconds=5) for t in ticks)


def assess(minute, primary_ticks, independent_ticks, primary_outages=(), independent_outages=()):
    p = timing_eligible(minute, primary_ticks, primary_outages)
    b = timing_eligible(minute, independent_ticks, independent_outages)
    return {"minute_utc": minute.isoformat(), "primary_timing_eligible": p,
            "independent_timing_eligible": b, "continuity_possible": p or b,
            "actual_candle_validated": False, "historical_replay": False}
