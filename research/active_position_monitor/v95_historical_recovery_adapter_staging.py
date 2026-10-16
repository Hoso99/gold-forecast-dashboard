"""Staging-only conservative historical M15 adapter.

Never splices Twelve Data and Biquote OHLC. No network access. Does not
alter the running paper monitor. Signals stay blocked on provider disagreement.
"""
import datetime as dt

from v95_historical_recovery_staging import (
    validate_indicator_window, compare_sources,
)

UTC = dt.timezone.utc


def assess_recovery(biquote_m1, biquote_m15, historical_m15, *,
                    now, max_close_diff=1.0):
    """Report readiness and research evidence, without authorizing an entry.

    Historical M15 may be useful as a self-consistent research indicator series
    but is not a replacement for the Biquote price/ATR used for paper SL/TP.
    """
    result = {"entry_authorized": False, "source": "TWELVE_DATA_M15_RESEARCH",
              "historical_ready": False, "biquote_recent_ready": False}
    if not biquote_m1 or len(biquote_m1) < 10:
        result["reason"] = "insufficient Biquote M1 SELL-pressure candles"
        return result
    tail = biquote_m1[-10:]
    if any(b["t"] - a["t"] != dt.timedelta(minutes=1)
           for a, b in zip(tail, tail[1:])):
        result["reason"] = "recent Biquote M1 gap"
        return result
    age = (now - (tail[-1]["t"] + dt.timedelta(minutes=1))).total_seconds()
    if age < 0 or age > 180:
        result["reason"] = "Biquote M1 stale or unfinished"
        return result
    result["biquote_recent_ready"] = True
    ready, reason = validate_indicator_window(historical_m15, now=now)
    if not ready:
        result["reason"] = reason
        return result
    result["historical_ready"] = True
    compatible, reason, comparisons = compare_sources(
        biquote_m15, historical_m15, max_close_diff=max_close_diff)
    result["provider_overlap_count"] = len(comparisons)
    result["provider_compatible"] = compatible
    result["reason"] = reason
    return result
