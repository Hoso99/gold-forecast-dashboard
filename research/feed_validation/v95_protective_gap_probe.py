"""Research-only pure protective checks for an existing V9.5 paper SELL.

This module does not open positions, change risk/SELL logic, write state or
assume that absent candles prove a stop/target was not hit.
"""
import datetime as dt
import math


def check_protective_levels(position, rows, last_checked_bar=None):
    """Return (action, detail). Caller must journal/commit at most once.

    When M1 coverage is discontinuous since the last check, an observed SL
    touch remains actionable, but an apparent TP touch is *uncertain*:
    an unobserved prior SL could have occurred first. No invented fill.
    """
    if not rows:
        return "WAIT_DATA", "No completed genuine M1 candle"
    entry = float(position["entry"])
    stop = float(position["current_stop"])
    initial = float(position["initial_stop"])
    if not all(math.isfinite(x) and x > 0 for x in (entry, stop, initial)):
        return "WAIT_DATA", "Invalid paper position prices"
    risk = initial - entry
    if risk <= 0:
        return "WAIT_DATA", "Invalid paper position risk"
    target = entry - 2 * risk
    if target <= 0:
        return "WAIT_DATA", "Invalid paper target"
    times = [x["t"] for x in rows]
    if times != sorted(set(times)):
        return "WAIT_DATA", "M1 timestamps not strictly ordered"
    if last_checked_bar is not None:
        if last_checked_bar.tzinfo is None or last_checked_bar.utcoffset() != dt.timedelta(0):
            return "WAIT_DATA", "Invalid last-checked timestamp"
        unseen = [x for x in rows if x["t"] > last_checked_bar]
        if not unseen:
            return "UNCHANGED", "No new completed M1"
        expected = last_checked_bar + dt.timedelta(minutes=1)
    else:
        unseen = [rows[-1]]
        expected = unseen[0]["t"]
    coverage_gap = False
    for bar in unseen:
        if bar["t"] != expected:
            coverage_gap = True
        expected = bar["t"] + dt.timedelta(minutes=1)
        if bar["h"] >= stop:
            return "SL_TOUCHED", {"bar": bar["t"].isoformat(), "gap_before": coverage_gap,
                                   "hypothetical_fill": max(stop, bar["o"])}
        if bar["l"] <= target:
            if coverage_gap:
                return "GAP_UNCERTAIN", {"bar": bar["t"].isoformat(),
                                          "reason": "Earlier unobserved SL/TP ordering unknown"}
            return "TP_TOUCHED", {"bar": bar["t"].isoformat(),
                                   "hypothetical_fill": target}
    if coverage_gap:
        return "GAP_UNCERTAIN", {"reason": "Unobserved M1 period; cannot establish complete position path"}
    return "NO_PROTECTIVE_TOUCH", {"checked_bars": len(unseen)}
