"""V9.5 SELL-only structural detectors. Completed candles only.

Research/paper trading only. Thresholds are experimental, not validated.
"""
import math


def detect(m15, atr15, sell_power):
    """Evaluate two independent bearish structural setups."""
    if len(m15) < 18 or not math.isfinite(atr15) or atr15 <= 0:
        return {"status": "INSUFFICIENT_DATA"}

    latest = m15[-1]
    prior = m15[-5:-1]
    resistance = max(b["h"] for b in prior)
    support = min(b["l"] for b in prior)
    span = latest["h"] - latest["l"]

    if span <= 0:
        return {"status": "INVALID_CANDLE"}

    upper_wick = latest["h"] - max(latest["o"], latest["c"])
    close_from_low = (latest["c"] - latest["l"]) / span

    sweep = (
        latest["h"] > resistance + 0.10 * atr15
        and latest["c"] < resistance - 0.05 * atr15
        and upper_wick / span >= 0.40
        and latest["c"] < latest["o"]
        and sell_power >= 60
    )

    support_break = (
        latest["c"] < support - 0.15 * atr15
        and latest["c"] < latest["o"]
        and close_from_low <= 0.30
        and sell_power >= 60
    )

    return {
        "status": "OK",
        "bearish_liquidity_sweep": sweep,
        "enhanced_support_break": support_break,
        "structural_sell": sweep or support_break,
        "resistance": resistance,
        "support": support,
        "sweep_penetration_atr": round(
            (latest["h"] - resistance) / atr15, 3
        ),
        "support_break_distance_atr": round(
            (support - latest["c"]) / atr15, 3
        ),
        "upper_wick_ratio": round(upper_wick / span, 3),
        "close_from_low_ratio": round(close_from_low, 3),
    }
