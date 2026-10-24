"""Historical M1 continuity safeguards for offline V9.6 research.

Never forward-fill missing prices. UTC timestamps must be sorted.
"""
from datetime import datetime, timedelta

def classify_transition(previous_utc, current_utc):
    """Return CONTIGUOUS, DUPLICATE, OUT_OF_ORDER, or GAP."""
    prev = datetime.fromisoformat(previous_utc)
    curr = datetime.fromisoformat(current_utc)
    delta = curr - prev
    if delta == timedelta(minutes=1):
        return "CONTIGUOUS"
    if delta == timedelta(0):
        return "DUPLICATE"
    if delta < timedelta(0):
        return "OUT_OF_ORDER"
    return "GAP"

def continuous_segments(rows):
    """Yield contiguous groups of M1 OHLC rows, splitting at every gap.

    No synthetic candles are inserted. Caller must reset indicator state
    and close or mark unresolved any open simulated position at a boundary.
    """
    segment = []
    for row in rows:
        if segment and classify_transition(segment[-1]["minute_utc"], row["minute_utc"]) != "CONTIGUOUS":
            yield segment
            segment = []
        segment.append(row)
    if segment:
        yield segment
