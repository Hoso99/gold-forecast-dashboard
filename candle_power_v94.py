"""Version 9.4 last-10-candle buying/selling-power engine.

Primary direction comes from completed 15-minute XAU/USD candle structure.
Recent candles receive more weight. Optional executed-trade footprint pressure
confirms the candle signal but cannot create a signal by itself.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class CandlePowerV94:
    signal: str
    status: str
    buy_power: float
    sell_power: float
    net_score: float
    candle_score: float
    footprint_score: float
    footprint_used: bool
    bullish_candles: int
    bearish_candles: int
    neutral_candles: int
    recent_momentum: float
    pressure_acceleration: float
    bearish_evidence: float
    bullish_evidence: float
    rows: pd.DataFrame
    detail: str


def _clip(value):
    return float(np.clip(value, -1.0, 1.0))


def analyze_last_10_candles(gold, footprint=None, bars=10,
                            buy_threshold=.62, sell_threshold=.58,
                            buy_lead=.16, sell_lead=.12):
    """Measure completed-candle control; SELL is intentionally more sensitive.

    SELL has a slightly lower release threshold/lead than BUY. This is an
    explicit design preference, not evidence that SELL forecasts are inherently
    more accurate. WAIT remains the default when pressure is mixed.
    """
    required = {"open", "high", "low", "close"}
    if gold is None or len(gold) < bars + 20 or not required.issubset(gold.columns):
        return CandlePowerV94("WAIT", "INSUFFICIENT DATA", .5, .5, 0, 0, 0,
                              False, 0, 0, 0, 0, 0, 0, 0, pd.DataFrame(),
                              "At least 30 completed OHLC candles are required.")
    frame = gold.iloc[-bars:].copy()
    o = frame.open.astype(float); h = frame.high.astype(float)
    l = frame.low.astype(float); c = frame.close.astype(float)
    rng = (h - l).replace(0, np.nan)
    body = ((c - o) / rng).fillna(0).clip(-1, 1)
    close_location = (((c - l) / rng) * 2 - 1).fillna(0).clip(-1, 1)
    upper_wick = (h - np.maximum(o, c)) / rng
lower_wick = (np.minimum(o, c) - l) / rng

wick_pressure = (
    lower_wick - upper_wick
).fillna(0).clip(-1, 1)
prev = gold.close.astype(float).shift(1).reindex(frame.index)
tr = pd.concat([(h-l), (h-prev).abs(), (l-prev).abs()], axis=1).max(axis=1)
atr = pd.concat([
        gold.high.astype(float)-gold.low.astype(float),
        (gold.high.astype(float)-gold.close.astype(float).shift(1)).abs(),
        (gold.low.astype(float)-gold.close.astype(float).shift(1)).abs()
], axis=1).max(axis=1).rolling(14, min_periods=14).mean().reindex(frame.index)
impulse = ((c - prev) / atr.replace(0, np.nan)).fillna(0).clip(-1, 1)
    # Enhanced candle structure: body 40%, close 25%, wick rejection 20%, ATR impulse 15%.
raw = (
    .40 * body
    + .25 * close_location
    + .20 * wick_pressure
    + .15 * impulse
).clip(-1, 1)
    weights = np.arange(1, bars + 1, dtype=float)
    weights /= weights.sum()
    candle_score = _clip(np.dot(raw.to_numpy(), weights))

    fp_score = 0.0
    fp_used = False
    if footprint is not None:
        fp_signal = str(getattr(footprint, "ten_bar_signal", "NONE")).upper()
        candidate = float(getattr(footprint, "ten_bar_score", 0.0) or 0.0)
        if fp_signal in {"BUY", "SELL"} and np.isfinite(candidate):
            fp_score = _clip(candidate)
            fp_used = True
    # Candle power remains dominant. Footprint confirms at 30% when available.
    net = _clip(.70 * candle_score + .30 * fp_score) if fp_used else candle_score
    buy_power = float((net + 1) / 2)
    sell_power = float(1 - buy_power)
    buy_advantage = buy_power - sell_power
    sell_advantage = sell_power - buy_power
    pressure_acceleration = _clip(raw.iloc[-5:].mean() - raw.iloc[:5].mean())
    accel_boost = 0.10 * pressure_acceleration
    directional_net = _clip(net + accel_boost)
    directional_buy_power = float((directional_net + 1) / 2)
    directional_sell_power = float(1 - directional_buy_power)
    directional_buy_advantage = directional_buy_power - directional_sell_power
    directional_sell_advantage = directional_sell_power - directional_buy_power                            
    if directional_sell_power >= sell_threshold and directional_sell_advantage >= sell_lead:
        signal = "SELL"
    elif directional_buy_power >= buy_threshold and directional_buy_advantage >= buy_lead:
        signal = "BUY"
    else:
        signal = "WAIT"
    direction = np.where(raw > .10, "BUY", np.where(raw < -.10, "SELL", "NEUTRAL"))
    out = pd.DataFrame({
        "Candle": frame.index,
        "Open": o.values, "High": h.values, "Low": l.values, "Close": c.values,
        "Body pressure": body.values,
        "Close-location pressure": close_location.values,
        "ATR impulse": impulse.values,
        "Power score": raw.values,
        "Direction": direction,
        "Recency weight": weights,
    })
    bullish = int((raw > .10).sum()); bearish = int((raw < -.10).sum())
    neutral = bars - bullish - bearish
    recent_momentum = _clip(raw.iloc[-3:].mean() - raw.iloc[:3].mean())
    # Compare newer five candles with older five. Negative = selling accelerating.
    pressure_acceleration = _clip(raw.iloc[-5:].mean() - raw.iloc[:5].mean())
                              
    # Affirmative evidence only: neutral candles contribute to neither side.
    bearish_evidence = float(np.average(np.maximum(-raw.to_numpy(), 0), weights=weights))
    bullish_evidence = float(np.average(np.maximum(raw.to_numpy(), 0), weights=weights))
    detail = (
        f"Last {bars} completed candles: buying power {buy_power:.1%}, "
        f"selling power {sell_power:.1%}. Candle structure has priority"
        + (" with 30% footprint confirmation." if fp_used else ".")
        + " SELL uses the intentionally more sensitive threshold."
    )
    return CandlePowerV94(signal, "READY", buy_power, sell_power, net,
                          candle_score, fp_score, fp_used, bullish, bearish,
                          neutral, recent_momentum, pressure_acceleration, bearish_evidence, bullish_evidence, out, detail)


def validate_power_signal(power, *, event_lock=False, shock_active=False,
                          reversal_signal=0, validated_action="NO EDGE"):
    """Apply safety/confirmation gates without changing the primary direction."""
    signal = str(power.signal).upper()
    reasons = []
    if signal not in {"BUY", "SELL"}:
        reasons.append("10-candle buying/selling power is mixed")
    if event_lock:
        reasons.append("high-impact event lock is active")
    if shock_active:
        reasons.append("shock cooldown is active")
    rev = int(np.sign(reversal_signal or 0))
    if signal == "BUY" and rev < 0:
        reasons.append("5-minute validated reversal conflicts with BUY")
    if signal == "SELL" and rev > 0:
        reasons.append("5-minute validated reversal conflicts with SELL")
    action = str(validated_action).upper()
    confirmed = (signal in {"BUY", "SELL"} and not reasons and action == signal)
    if signal in {"BUY", "SELL"} and action not in {signal}:
        reasons.append(f"risk-controlled model action is {action}")
    return {
        "signal": signal,
        "status": "VALIDATED" if confirmed else ("WAIT" if signal == "WAIT" else "POWER SIGNAL ONLY"),
        "reasons": reasons,
        "validated": confirmed,
    }
