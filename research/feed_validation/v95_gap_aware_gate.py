"""Research-only, gap-aware evaluation gate for V9.5.

Never fills candles or alters SELL calculations. Evaluates only when every
required recent input window is built from genuine contiguous M1 bars.
The caller must separately enforce completed-bar freshness and session status.
"""
import datetime as dt

UTC = dt.timezone.utc
REQUIREMENTS = {5: 6, 15: 18, 60: 3}
ADVISORY_REQUIREMENTS = {240: 2}


def _start(t, minutes):
    midnight = t.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight + dt.timedelta(minutes=(t.hour * 60 + t.minute) // minutes * minutes)


def _consecutive(bars, minutes):
    return all(b["t"] - a["t"] == dt.timedelta(minutes=minutes)
               for a, b in zip(bars, bars[1:]))


def check(rows, aggregate, now=None, max_age_seconds=180):
    """Return (allowed, reason, diagnostics); never mutate input or state."""
    if not rows:
        return False, "WAIT_DATA: no M1 candles", {}
    now = now or dt.datetime.now(UTC)
    times = [r["t"] for r in rows]
    if any(t.tzinfo is None or t.utcoffset() != dt.timedelta(0)
           or t.second or t.microsecond for t in times):
        return False, "WAIT_DATA: invalid UTC M1 timestamp", {}
    if times != sorted(set(times)):
        return False, "WAIT_DATA: M1 candles not strictly ordered", {}
    age = (now - (times[-1] + dt.timedelta(minutes=1))).total_seconds()
    if age < 0 or age > max_age_seconds:
        return False, "WAIT_DATA: stale or incomplete latest M1", {}
    if len(rows) < 10 or not _consecutive(rows[-10:], 1):
        return False, "WAIT_DATA: last 10 M1 SELL-pressure candles have a gap", {}

    detail = {}
    for minutes, required in REQUIREMENTS.items():
        bars = aggregate(rows, minutes)
        if len(bars) < required:
            return False, f"WAIT_DATA: need {required} complete M{minutes} bars", detail
        tail = bars[-required:]
        # Never silently skip a missing intermediate bar when calculating
        # indicator trends, ATR, pivots, or the 4h confirmation.
        if not _consecutive(tail, minutes):
            return False, f"WAIT_DATA: gap in M{minutes} indicator window", detail
        # Latest aggregate must be the most recently fully closed bucket.
        # Otherwise a missing newest bucket could masquerade as current.
        last_expected = _start(times[-1], minutes)
        if times[-1] < last_expected + dt.timedelta(minutes=minutes - 1):
            last_expected -= dt.timedelta(minutes=minutes)
        if tail[-1]["t"] != last_expected:
            return False, f"WAIT_DATA: latest M{minutes} bar missing", detail
        detail[f"M{minutes}"] = {"bars": required, "first": tail[0]["t"].isoformat(),
                                 "last": tail[-1]["t"].isoformat()}
    # H4 is advisory in V9.5, never a standalone SELL veto.
    for minutes, required in ADVISORY_REQUIREMENTS.items():
        bars = aggregate(rows, minutes)
        key = f"M{minutes}"
        if len(bars) < required:
            detail[key] = {"available": False, "reason": "insufficient completed bars"}
            continue
        tail = bars[-required:]
        last_expected = _start(times[-1], minutes)
        if times[-1] < last_expected + dt.timedelta(minutes=minutes - 1):
            last_expected -= dt.timedelta(minutes=minutes)
        if not _consecutive(tail, minutes) or tail[-1]["t"] != last_expected:
            detail[key] = {"available": False, "reason": "gap or latest bar unavailable"}
        else:
            detail[key] = {"available": True, "bars": required,
                           "first": tail[0]["t"].isoformat(),
                           "last": tail[-1]["t"].isoformat()}
    return True, "READY: mandatory M5/M15/H1 windows complete; H4 advisory", detail
