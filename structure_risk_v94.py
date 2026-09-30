from __future__ import annotations
import numpy as np
import pandas as pd


def _atr14(gold: pd.DataFrame) -> float:
    close = gold.close.astype(float)
    prev = close.shift(1)
    tr = pd.concat([(gold.high-gold.low).astype(float),
                    (gold.high.astype(float)-prev).abs(),
                    (gold.low.astype(float)-prev).abs()], axis=1).max(axis=1)
    return float(tr.rolling(14, min_periods=14).mean().iloc[-1])


def _confirmed_swings(gold: pd.DataFrame, lookback: int = 48, wing: int = 2):
    x = gold.tail(max(lookback, wing * 2 + 5)).copy()
    highs, lows = x.high.astype(float), x.low.astype(float)
    sh, sl = [], []
    for i in range(wing, len(x)-wing):
        if highs.iloc[i] >= highs.iloc[i-wing:i+wing+1].max():
            sh.append(float(highs.iloc[i]))
        if lows.iloc[i] <= lows.iloc[i-wing:i+wing+1].min():
            sl.append(float(lows.iloc[i]))
    return sh, sl


def _next_level(levels, entry, side):
    if side == "BUY":
        vals = sorted(v for v in levels if v > entry)
        return vals[0] if vals else np.nan
    vals = sorted((v for v in levels if v < entry), reverse=True)
    return vals[0] if vals else np.nan


def _higher_timeframe_target(gold, entry, side):
    # Uses only completed M15 data already available to the model; no extra feed.
    frame = gold.copy()
    if not isinstance(frame.index, pd.DatetimeIndex):
        return np.nan, "unavailable"
    candidates = []
    for rule, label in [("1h", "H1"), ("1D", "D1")]:
        agg = frame.resample(rule, label="right", closed="right").agg(
            {"open":"first", "high":"max", "low":"min", "close":"last"}).dropna()
        if len(agg) < 3:
            continue
        levels = list(agg.high.astype(float).iloc[:-1]) if side == "BUY" else list(agg.low.astype(float).iloc[:-1])
        nxt = _next_level(levels, entry, side)
        if np.isfinite(nxt):
            candidates.append((abs(nxt-entry), nxt, label))
    if not candidates:
        return np.nan, "unavailable"
    _, level, label = min(candidates)
    return float(level), label


def structure_atr_plan(side, gold, atr_multiple=1.5, min_tp1_rr=2.0,
                       swing_lookback=48, cost_bps=10, entry_price=None):
    """M15 structure + ATR stop with a minimum structural final target R:R gate."""
    side = str(side).upper()
    empty = {"status":"WAIT", "reason":"no qualified direction", "entry":np.nan,
             "atr":np.nan, "swing":np.nan, "stop":np.nan, "risk_distance":np.nan,
             "tp1":np.nan, "tp1_rr":np.nan, "tp2":np.nan, "tp2_rr":np.nan,
             "tp2_source":"unavailable", "atr_multiple":float(atr_multiple),
             "min_tp1_rr":float(min_tp1_rr)}
    if side not in {"BUY","SELL"} or gold is None or len(gold) < 30:
        return empty
    entry = float(entry_price) if entry_price is not None else float(gold.close.astype(float).iloc[-1])
    atr = _atr14(gold)
    if not np.isfinite(atr) or atr <= 0 or entry <= 0:
        return {**empty, "entry":entry, "reason":"invalid ATR or price"}
    sh, sl = _confirmed_swings(gold, swing_lookback)
    swings = sl if side == "BUY" else sh
    if not swings:
        return {**empty, "entry":entry, "atr":atr, "reason":"no confirmed M15 swing"}
    swing = float(swings[-1])
    raw_stop = swing - atr_multiple*atr if side == "BUY" else swing + atr_multiple*atr
    cost_floor = entry * max(float(cost_bps), 0.0) / 10000 * 3
    # Stop must be on the loss side and at least the cost floor away.
    if side == "BUY": stop = min(raw_stop, entry-cost_floor)
    else: stop = max(raw_stop, entry+cost_floor)
    risk = abs(entry-stop)
    if not np.isfinite(risk) or risk <= 0:
        return {**empty, "entry":entry, "atr":atr, "swing":swing, "reason":"invalid structure stop"}
    structure_levels = sh if side == "BUY" else sl
    tp1 = _next_level(structure_levels, entry, side)
    tp1_rr = abs(tp1-entry)/risk if np.isfinite(tp1) else np.nan
    if not np.isfinite(tp1) or tp1_rr < min_tp1_rr:
        return {**empty, "entry":entry, "atr":atr, "swing":swing, "stop":stop,
                "risk_distance":risk, "tp1":tp1, "tp1_rr":tp1_rr,
                "reason":f"next M15 structure does not provide {min_tp1_rr:.2f}R"}
    tp2, src = _higher_timeframe_target(gold, entry, side)
    tp2_rr = abs(tp2-entry)/risk if np.isfinite(tp2) else np.nan
    # TP2 must be deeper than TP1; otherwise leave it unavailable rather than inventing a target.
    if np.isfinite(tp2) and ((side=="BUY" and tp2 <= tp1) or (side=="SELL" and tp2 >= tp1)):
        tp2, tp2_rr, src = np.nan, np.nan, "unavailable"
    return {**empty, "status":"ACTIVE", "reason":"structure, ATR and TP1 R:R gates passed",
            "entry":entry, "atr":atr, "swing":swing, "stop":stop, "risk_distance":risk,
            "tp1":float(tp1), "tp1_rr":float(tp1_rr), "tp2":tp2,
            "tp2_rr":tp2_rr, "tp2_source":src}

def valid_entry_for_min_rr(plan, side, min_rr=2.0):
    """Price at which the current structure first provides the required R:R."""
    side = str(side).upper()

    if side not in {"BUY", "SELL"}:
        return np.nan

    stop = float(plan.get("stop", np.nan))
    target = float(plan.get("tp1", np.nan))

    if not np.isfinite(stop) or not np.isfinite(target):
        return np.nan

    r = max(float(min_rr), 0.01)

    if side == "BUY":
        # (target - entry) / (entry - stop) = r
        return float((target + r * stop) / (1.0 + r))

    # SELL:
    # (entry - target) / (stop - entry) = r
    return float((target + r * stop) / (1.0 + r))
def size_from_structure(plan, equity, risk_fraction, ounces_per_lot=100.0, max_notional_fraction=1.5):
    if plan.get("status") != "ACTIVE" or not (0 < risk_fraction <= .02) or equity <= 0:
        return {"risk_budget":0.0, "max_ounces":0.0, "estimated_lots":0.0}
    budget = float(equity)*float(risk_fraction)
    ounces_risk = budget/float(plan["risk_distance"])
    ounces_notional = float(equity)*float(max_notional_fraction)/float(plan["entry"])
    ounces = max(0.0, min(ounces_risk, ounces_notional))
    return {"risk_budget":budget, "max_ounces":ounces,
            "estimated_lots":ounces/float(ounces_per_lot)}


def protective_stop_update(side, original_stop, current_stop, proposed_stop):
    """Return a protective stop that can tighten or stay unchanged, never widen."""
    side = str(side).upper()
    vals = [float(original_stop), float(current_stop), float(proposed_stop)]
    if not all(np.isfinite(v) for v in vals) or side not in {"BUY", "SELL"}:
        raise ValueError("valid side and finite stop prices required")
    if side == "BUY":
        return max(vals)  # higher stop = less downside risk
    return min(vals)      # lower stop = less upside risk for a short
