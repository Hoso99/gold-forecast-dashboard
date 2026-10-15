"""Research-only independent M1 validation; no feed or database access."""
from datetime import timedelta
from math import isfinite


def validate_ticks(minute, observations, next_tick_time):
    """Return OHLC only when every strict tick-quality condition passes."""
    end = minute + timedelta(minutes=1)
    if len(observations) < 2 or next_tick_time is None:
        return None
    if not end <= next_tick_time <= end + timedelta(seconds=5):
        return None
    times = [item[0] for item in observations]
    if times != sorted(times):
        return None
    if times[0] < minute or times[-1] >= end:
        return None
    if (times[0] - minute).total_seconds() > 5:
        return None
    if (end - times[-1]).total_seconds() > 5:
        return None
    if any((b - a).total_seconds() > 10 for a, b in zip(times, times[1:])):
        return None
    prices = [float(item[1]) for item in observations]
    if not all(isfinite(p) and p > 0 for p in prices):
        return None
    return {'minute': minute.isoformat(), 'open': prices[0],
            'high': max(prices), 'low': min(prices), 'close': prices[-1],
            'ticks': len(prices), 'research_only': True}
