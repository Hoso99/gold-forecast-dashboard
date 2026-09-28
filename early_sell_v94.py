"""Causal early-SELL detector for Version 9.4.

This is a directional warning layer, not an execution override.  It uses only
completed M15 OHLC bars available at each timestamp.  Event, shock, structure,
reward:risk and position-sizing gates remain separate.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class EarlySellV94:
    signal: str
    score: float
    status: str
    checks_passed: int
    checks_total: int
    components: dict
    detail: str


def _series(gold):
    c = gold.close.astype(float); o = gold.open.astype(float)
    h = gold.high.astype(float); l = gold.low.astype(float)
    prev = c.shift(1)
    tr = pd.concat([(h-l), (h-prev).abs(), (l-prev).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14, min_periods=14).mean()
    rng = (h-l).replace(0, np.nan)
    body = ((c-o)/rng).fillna(0).clip(-1, 1)
    close_loc = (((c-l)/rng)*2-1).fillna(0).clip(-1, 1)
    impulse = ((c-prev)/atr.replace(0, np.nan)).fillna(0).clip(-2, 2)
    raw = (.50*body + .30*close_loc + .20*impulse.clip(-1,1)).clip(-1,1)
    ema8 = c.ewm(span=8, adjust=False).mean()
    ema21 = c.ewm(span=21, adjust=False).mean()
    recent_low = l.shift(1).rolling(6, min_periods=4).min()
    return c, h, l, atr, raw, ema8, ema21, recent_low


def detect_early_sell(gold, *, threshold=.62):
    """Detect bearish acceleration before the 10-candle aggregate fully turns.

    Five causal components are deliberately simple and inspectable:
    recent bearish pressure, pressure acceleration, downside structure break,
    EMA deterioration, and downside range/ATR impulse.  A SELL warning requires
    a weighted score >= threshold and at least three affirmative components.
    """
    if gold is None or len(gold) < 35 or not {"open","high","low","close"}.issubset(gold.columns):
        return EarlySellV94("WAIT", 0.0, "INSUFFICIENT DATA", 0, 5, {},
                            "At least 35 completed M15 OHLC candles are required.")
    c,h,l,atr,raw,ema8,ema21,recent_low = _series(gold)
    recent3 = float(raw.iloc[-3:].mean())
    prior5 = float(raw.iloc[-8:-3].mean())
    acceleration = float(np.clip(prior5 - recent3, 0, 1))  # positive = selling accelerated
    bearish_pressure = float(np.clip(-recent3, 0, 1))
    structure_break = float(c.iloc[-1] < recent_low.iloc[-1])
    ema_deterioration = float((ema8.iloc[-1] < ema21.iloc[-1]) and (ema8.iloc[-1] < ema8.iloc[-2]))
    downside_impulse = float(np.clip((c.iloc[-2] - c.iloc[-1]) / max(float(atr.iloc[-1]), 1e-9), 0, 1))
    comps = {
        "recent bearish pressure": bearish_pressure,
        "selling acceleration": acceleration,
        "downside structure break": structure_break,
        "EMA deterioration": ema_deterioration,
        "downside ATR impulse": downside_impulse,
    }
    weights = {"recent bearish pressure":.28, "selling acceleration":.22,
               "downside structure break":.22, "EMA deterioration":.14,
               "downside ATR impulse":.14}
    score = float(sum(comps[k]*weights[k] for k in comps))
    passed = sum([bearish_pressure >= .30, acceleration >= .20,
                  structure_break >= 1, ema_deterioration >= 1,
                  downside_impulse >= .35])
    signal = "SELL" if score >= threshold and passed >= 3 else "WAIT"
    detail = (f"Early-SELL score {score:.2f}; {passed}/5 checks. Uses completed M15 bars only; "
              "directional warning does not bypass shock/event/risk gates.")
    return EarlySellV94(signal, score, "EARLY SELL" if signal == "SELL" else "MONITORING",
                        int(passed), 5, comps, detail)


def early_sell_holdout(gold, *, cost_bps=10.0, threshold=.62, horizon=2, min_train=80):
    """Chronological diagnostic of the fixed early-SELL rule; no tuning occurs here."""
    if gold is None or len(gold) < min_train + horizon + 35:
        return {"status":"INSUFFICIENT", "signals":0, "accuracy":np.nan,
                "mean_net_bps":np.nan, "profit_factor":np.nan}
    rows=[]
    for i in range(min_train, len(gold)-horizon):
        d=detect_early_sell(gold.iloc[:i+1], threshold=threshold)
        if d.signal != "SELL":
            continue
        entry=float(gold.close.iloc[i]); exit_=float(gold.close.iloc[i+horizon])
        net_bps=((entry-exit_)/entry)*10000.0-float(cost_bps)
        rows.append(net_bps)
    if not rows:
        return {"status":"NO SIGNALS", "signals":0, "accuracy":np.nan,
                "mean_net_bps":np.nan, "profit_factor":np.nan}
    a=np.asarray(rows,float); wins=a[a>0].sum(); losses=-a[a<0].sum()
    return {"status":"FIXED-RULE HOLDOUT", "signals":int(len(a)),
            "accuracy":float((a>0).mean()), "mean_net_bps":float(a.mean()),
            "profit_factor":float(wins/losses) if losses>0 else np.inf}
