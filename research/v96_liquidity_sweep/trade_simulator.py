"""Offline SELL trade outcome simulator for V9.6 historical research.

Inputs are consecutive completed M1 bars, beginning with the NEXT bar
after a confirmed signal. No live feeds, orders, or account access.
Intrabar ordering is unknown: initial stop has priority over TP1;
after TP1, break-even stop has priority over TP2. TP2 cannot be
credited on the same bar as TP1 without tick-level ordering evidence.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from .risk_time import exit_deadline

@dataclass(frozen=True)
class TradeResult:
    gross_r: float
    net_r: float
    reason: str
    exit_utc: str
    entry: float
    initial_stop: float
    filled_tp1: bool

def simulate_sell(bars, stop, cost_per_oz=0.0):
    """Return completed outcome or None for empty, gapped, or unresolved input.

    The first bar's OPEN is the fill. 'stop' is an absolute SELL stop
    determined before entry. Cost is full-round-trip USD per ounce,
    including estimated spread, slippage and commission.
    """
    if not bars:
        return None
    if cost_per_oz < 0:
        raise ValueError("cost_per_oz must be nonnegative")
    entry = float(bars[0]["o"])
    if stop <= entry:
        return None
    risk = stop-entry
    tp1, tp2 = entry-risk, entry-2*risk
    entry_dt = datetime.fromisoformat(bars[0]["minute_utc"]).replace(tzinfo=timezone.utc)
    deadline = exit_deadline(entry_dt)
    previous = None
    first = False
    for bar in bars:
        ts = datetime.fromisoformat(bar["minute_utc"]).replace(tzinfo=timezone.utc)
        if previous is not None and (ts-previous).total_seconds()!=60:
            return None
        previous=ts
        o,h,l,c = (float(bar[k]) for k in ("o","h","l","c"))
        if not (0 < l <= min(o,c) <= max(o,c) <= h):
            raise ValueError("Invalid OHLC")
        if not first:
            if h >= stop:
                # Adverse opening gap is executed at the worse open.
                gross = (entry-max(stop,o))/risk
                return TradeResult(gross,gross-cost_per_oz/risk,"INITIAL_STOP",bar["minute_utc"],entry,stop,False)
            if l <= tp1:
                first = True
                # No TP2 or BE evaluation on the TP1 bar. Time exit still applies.
        elif first:
            if h >= entry:
                gross = .5 + .5*(entry-max(entry,o))/risk
                return TradeResult(gross,gross-cost_per_oz/risk,"BREAKEVEN",bar["minute_utc"],entry,stop,True)
            if l <= tp2:
                return TradeResult(1.5,1.5-cost_per_oz/risk,"TP2",bar["minute_utc"],entry,stop,True)
        if ts >= deadline:
            gross = (.5 + .5*(entry-c)/risk) if first else (entry-c)/risk
            return TradeResult(gross,gross-cost_per_oz/risk,"TIME",bar["minute_utc"],entry,stop,first)
    return None
