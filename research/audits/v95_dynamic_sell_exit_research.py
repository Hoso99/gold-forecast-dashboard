"""V9.5 SELL-only exit decision state machine, OFFLINE RESEARCH ONLY.

Consumes point-in-time observations from a separate evidence builder. It does
not obtain live data, send alerts, execute orders or alter protective orders.
Prices and indicators must be independently validated before any deployment.
"""
from __future__ import annotations
from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class SellExitEvidence:
    entry: float
    initial_stop: float
    current_stop: float
    price: float
    completed_m5_reversal: bool = False
    completed_m15_bullish_invalidation: bool = False
    h1_bullish_confirmation: bool = False
    volatility_high: bool = False
    event_imminent: bool = False
    partial_already_taken: bool = False
    quote_fresh: bool = True


def decide_sell_exit(e: SellExitEvidence) -> dict:
    """Propose a *hypothetical* action; never claim a broker fill.

    Ordering: invalid/stale -> protective SL -> 2R TP -> confirmed structure
    invalidation -> M5 warning with H1 corroboration -> partial at +1R ->
    HOLD. Moving SL is proposed only after a previously acknowledged partial;
    no retroactive intrabar move. High volatility/events do not alone exit.
    """
    values = (e.entry, e.initial_stop, e.current_stop, e.price)
    if not all(isfinite(v) and v > 0 for v in values):
        return {"action": "WAIT_DATA", "reason": "Invalid or nonfinite quote"}
    if not e.initial_stop > e.entry or not e.current_stop <= e.initial_stop:
        return {"action": "WAIT_DATA", "reason": "Invalid or widened protective stop"}
    if not e.quote_fresh:
        return {"action": "WAIT_DATA", "reason": "Stale quote; no exit inference"}
    risk = e.initial_stop - e.entry
    r = (e.entry - e.price) / risk
    base = {"hypothetical_unrealized_r": round(r, 4),
            "research_only": True, "broker_fill_confirmed": False}
    if e.price >= e.current_stop:
        return {**base, "action": "SL_TOUCHED", "reason": "Quote at/above stop; actual fill unknown"}
    if e.price <= e.entry - 2 * risk:
        return {**base, "action": "TP_TOUCHED", "reason": "Quote at/below baseline 2R target; actual fill unknown"}
    if e.completed_m15_bullish_invalidation:
        return {**base, "action": "EXIT_SELL_NOW", "reason": "Completed M15 bullish structure invalidation"}
    if e.completed_m5_reversal and e.h1_bullish_confirmation:
        return {**base, "action": "EXIT_SELL_NOW", "reason": "Completed M5 reversal corroborated by H1 bullish confirmation"}
    if e.partial_already_taken and e.current_stop > e.entry:
        return {**base, "action": "MOVE_SL", "proposed_stop": e.entry,
                "reason": "Previously acknowledged partial; propose break-even stop, never widen"}
    if r >= 1 and not e.partial_already_taken:
        return {**base, "action": "PARTIAL_EXIT", "proposed_fraction": 0.5,
                "reason": "Hypothetical +1R reached; partial requires execution acknowledgment"}
    warning = bool(e.completed_m5_reversal or e.volatility_high or e.event_imminent)
    return {**base, "action": "HOLD_SELL",
            "reason": "No confirmed exit trigger",
            "risk_warning": warning}
