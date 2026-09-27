"""Version 9.4 four-module decision layer.

The four modules are intentionally distinct in purpose, but the code does not
claim statistical independence. Independence/correlation must be measured on
out-of-sample signals before being reported.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class ModuleReading:
    name: str
    score: float  # -1 SELL ... +1 BUY
    signal: str
    detail: str


@dataclass(frozen=True)
class FourModuleDecision:
    signal: str
    status: str
    score: float
    sell_strength: float
    buy_strength: float
    modules: tuple[ModuleReading, ...]
    reasons: tuple[str, ...]


def _clip(x):
    return float(np.clip(float(x), -1.0, 1.0))


def _side(score, neutral=.12):
    return "BUY" if score >= neutral else "SELL" if score <= -neutral else "WAIT"


def evaluate_four_modules(power, mother_breakout=None, short_trend="RANGE",
                          reversal=None, *, event_lock=False, shock_active=False,
                          sell_threshold=.16, buy_threshold=.24, divergence=None):
    """Combine four modules, with SELL intentionally more sensitive than BUY.

    1 SELL power and 2 BUY power come from the last-10-candle engine but are
    scored separately. 3 breakout/trend and 4 reversal/exhaustion are separate
    confirmations/vetoes. WAIT is the default for mixed evidence.
    """
    reversal = reversal or {}
    breakout = mother_breakout or {}
    divergence = divergence or {"signal":"NONE","score":0.0}
    sell = _clip(-max(0.0, (float(power.sell_power) - .5) * 2.0))
    buy = _clip(max(0.0, (float(power.buy_power) - .5) * 2.0))

    bsignal = str(breakout.get("signal", "NONE")).upper()
    trend = str(short_trend).upper()
    structure = (1.0 if bsignal == "BUY" else -1.0 if bsignal == "SELL" else 0.0)
    structure += (.35 if "UP" in trend or "BULL" in trend else
                  -.35 if "DOWN" in trend or "BEAR" in trend else 0.0)
    structure = _clip(structure)

    rev = int(np.sign(reversal.get("current_signal", 0) or 0))
    # A validated reversal is directional; absent reversal is neutral.
    reversal_score = float(rev)
    # Divergence is confirmation only and cannot create a trade by itself.
    div_signal = str(divergence.get("signal", "NONE")).upper()

    modules = (
        ModuleReading("SELL power", sell, "SELL" if sell < -.12 else "WAIT",
                      f"10-candle selling power {float(power.sell_power):.1%}"),
        ModuleReading("BUY power", buy, "BUY" if buy > .12 else "WAIT",
                      f"10-candle buying power {float(power.buy_power):.1%}"),
        ModuleReading("Breakout / trend", structure, _side(structure),
                      f"breakout={bsignal}; trend={trend}"),
        ModuleReading("Reversal / exhaustion", reversal_score, _side(reversal_score),
                      f"5-minute validated reversal={rev}"),
    )

    # Candle power is the priority (70% total); structure and reversal confirm.
    weights = (.35, .35, .18, .12)
    score = _clip(sum(m.score * w for m, w in zip(modules, weights)))
    reasons = []
    if event_lock:
        reasons.append("high-impact event lock")
    if shock_active:
        reasons.append("shock cooldown")

    # SELL threshold is lower by design; BUY requires stronger evidence.
    signal = "SELL" if score <= -sell_threshold else "BUY" if score >= buy_threshold else "WAIT"
    # Require affirmative multi-module confirmation: primary side plus at least
    # one independent structure/reversal/divergence confirmation.
    if signal in {"BUY", "SELL"}:
        side_score = 1 if signal == "BUY" else -1
        confirmations = int(np.sign(structure) == side_score) + int(rev == side_score) + int(div_signal == signal)
        if confirmations < 1:
            reasons.append("no independent module confirms the primary candle-power side")
    # Do not let a reversal directly opposed to the proposed trade through.
    if signal == "SELL" and rev > 0:
        reasons.append("validated 5-minute BUY reversal conflicts with SELL")
    if signal == "BUY" and rev < 0:
        reasons.append("validated 5-minute SELL reversal conflicts with BUY")
    if reasons:
        status = "BLOCKED"
    elif signal == "WAIT":
        status = "WAIT"
    else:
        status = "QUALIFIED POWER SIGNAL"
    return FourModuleDecision(
        signal=signal if not reasons else "WAIT", status=status, score=score,
        sell_strength=float((1-score)/2), buy_strength=float((1+score)/2),
        modules=modules, reasons=tuple(reasons))
