"""V9.5 SELL-only exit variants. Offline research, no live execution.

M1 open-stamp assumption remains UNVERIFIED. Input bars are sequential completed
one-minute bars after entry. M5 ATR is computed only from completed 5-minute bars
and trailing updates become effective on the NEXT minute, not retrospectively.
"""
from __future__ import annotations
import math


def simulate_sell(bars, entry, initial_stop, atr_m5, mode="baseline",
                  target_r=2.0, horizon=120, chandelier_k=2.5,
                  cost_points=0.30):
    """Return net R, status and path metrics for a hypothetical SELL.

    bars: sequence of dicts with open/high/low/close and optional
    atr_m5_closed, m5_close_completed. An ATR update on a bar is
    only allowed to modify the stop for the NEXT bar.
    """
    if not (initial_stop>entry>0 and horizon>0 and cost_points>=0):
        raise ValueError("Invalid SELL parameters")
    if mode not in {"baseline","fixed","partial_fixed","partial_chandelier","chandelier"}:
        raise ValueError("Unsupported variant")
    risk=initial_stop-entry
    stop=initial_stop
    lowest=entry
    qty=1.0
    realized=0.0
    partial=False
    target=entry-target_r*risk
    max_favorable=0.0
    max_adverse=0.0
    duration=0
    outcome="TIMEOUT"
    for duration,bar in enumerate(bars[:horizon],start=1):
        o,h,l,c=[float(bar[k]) for k in ("open","high","low","close")]
        if not all(math.isfinite(x) for x in (o,h,l,c)):
            raise ValueError("Nonfinite candle")
        # A gap above protective stop fills at the worse opening price.
        max_favorable=max(max_favorable,entry-l)
        max_adverse=max(max_adverse,h-entry)
        if o>=stop or h>=stop:
            exit_price=max(stop,o)
            realized+=qty*(entry-exit_price)
            outcome="STOP"
            qty=0.0
            break
        # Stop-first applies even if low also crosses a profit target.
        if mode in {"baseline","fixed"}:
            if l<=target:
                realized+=qty*(entry-target)
                qty=0.0
                outcome="TARGET"
                break
        else:
            first_target=entry-risk
            if not partial and l<=first_target:
                if mode in {"partial_fixed","partial_chandelier"}:
                    realized+=0.5*(entry-first_target)
                    qty=0.5
                partial=True
                # Break-even stop applies on the next bar, not the current one.
                new_stop=min(stop,entry)
            else:
                new_stop=stop
            if mode=="partial_fixed" and partial and l<=entry-2*risk:
                realized+=qty*2*risk
                qty=0.0
                outcome="TARGET"
                break
            if mode=="chandelier" and partial:
                # full position trails; no fixed target
                pass
            if mode=="partial_chandelier" and partial:
                pass
            # Update trailing stop using only completed M5 ATR and past low.
            # Effective NEXT bar; stop never moves up for a SELL.
            if mode in {"chandelier","partial_chandelier"} and partial:
                a=float(bar.get("atr_m5_closed",atr_m5))
                if math.isfinite(a) and a>0 and bool(bar.get("m5_close_completed",False)):
                    lowest=min(lowest,l)
                    new_stop=min(new_stop,lowest+chandelier_k*a)
            stop=min(stop,new_stop)
        # Keep the minimum low observed, for trailing activation.
        lowest=min(lowest,l)
    if qty:
        if duration==0:
            raise ValueError("No bars supplied")
        realized+=qty*(entry-float(bars[duration-1]["close"]))
    return {"outcome":outcome,"net_r":round((realized-cost_points)/risk,5),
            "partial":partial,"duration_minutes":duration,
            "mfe_r":round(max_favorable/risk,4),
            "mae_r":round(max_adverse/risk,4)}


def variants():
    return (
        [{"name":"A_baseline","mode":"baseline","target_r":2.0,"horizon":120}]
        +[{"name":f"B_fixed_{r}R_{h}m","mode":"fixed","target_r":r,"horizon":h}
          for r in (1.0,1.5,2.0) for h in (120,240,360)]
        +[{"name":f"C_partial_fixed_{h}m","mode":"partial_fixed","horizon":h}
          for h in (120,240,360)]
        +[{"name":f"D_partial_chandelier_{k}_{h}m","mode":"partial_chandelier",
           "chandelier_k":k,"horizon":h}
          for k in (2.0,2.5,3.0) for h in (120,240,360)]
        +[{"name":f"E_full_chandelier_{k}_{h}m","mode":"chandelier",
           "chandelier_k":k,"horizon":h}
          for k in (2.0,2.5,3.0) for h in (120,240,360)]
    )
