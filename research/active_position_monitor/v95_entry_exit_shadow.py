"""V9.5 research-only entry/exit diagnostics; no execution or live-model hooks.

All inputs are completed OHLC candles, oldest to newest. These are hypotheses
for comparison against the existing V9.5 baseline, not validated trade signals.
"""
def body_sell_power(bars):
    if not bars:
        return None
    sell = sum(max(b["o"] - b["c"], 0.0) for b in bars)
    buy = sum(max(b["c"] - b["o"], 0.0) for b in bars)
    return round(100.0 * sell / (sell + buy), 2) if sell + buy else 50.0


def entry_diagnostics(m1, m5, m15):
    """Non-gating SELL evidence. Never read an unfinished candle."""
    if len(m1) < 20 or len(m5) < 4 or len(m15) < 6:
        return {"status": "INSUFFICIENT_DATA"}
    recent = body_sell_power(m1[-10:])
    previous = body_sell_power(m1[-20:-10])
    latest = m15[-1]
    preceding = m15[-5:-1]
    prior_high = max(b["h"] for b in preceding)
    prior_low = min(b["l"] for b in preceding)
    span = latest["h"] - latest["l"]
    # Bearish rejection of prior highs, closing back below prior high.
    sweep_rejection = (latest["h"] > prior_high and latest["c"] < prior_high
                       and latest["c"] < latest["o"]
                       and span > 0 and (latest["h"] - latest["c"]) / span >= 0.5)
    # Downside breakout is distinct from a high-side liquidity sweep.
    downside_breakout = latest["c"] < prior_low
    m5_weakening = (m5[-1]["c"] > m5[-2]["c"] > m5[-3]["c"])
    return {
        "status": "OK",
        "sell_power_10": recent,
        "sell_power_previous_10": previous,
        "sell_power_acceleration_pp": round(recent - previous, 2),
        "bearish_high_sweep_rejection": sweep_rejection,
        "m15_downside_breakout": downside_breakout,
        "m5_bearish_momentum_weakening": m5_weakening,
        "candidate_sell_evidence": (recent >= 60 and
                                    (sweep_rejection or downside_breakout)),
    }


def exit_diagnostics(m1, m5, position):
    """Research-only early-exit warning; never mutate paper position."""
    if not position or len(m1) < 20 or len(m5) < 4:
        return {"status": "INSUFFICIENT_DATA"}
    now = body_sell_power(m1[-10:])
    before = body_sell_power(m1[-20:-10])
    higher_lows = m5[-1]["l"] > m5[-2]["l"] > m5[-3]["l"]
    rising_closes = m5[-1]["c"] > m5[-2]["c"] > m5[-3]["c"]
    fading = now < before - 10
    return {
        "status": "OK",
        "sell_power_acceleration_pp": round(now - before, 2),
        "bearish_pressure_fading": fading,
        "m5_reversal_structure": higher_lows and rising_closes,
        "early_exit_warning": fading and higher_lows and rising_closes,
        "action": "REVIEW_EXIT" if fading and higher_lows and rising_closes else "NO_CHANGE",
    }
