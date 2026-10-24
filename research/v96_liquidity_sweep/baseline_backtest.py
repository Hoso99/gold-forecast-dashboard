"""Isolated V9.6 baseline historical sweep+MSS evaluation.

This is a BASELINE ONLY, not full strategy A/B/C: no Fibonacci,
H1/H4, support, economic calendar or ATR-based stop. Never use these
baseline results to claim validated V9.6 strategy profitability.
Run: python3 -m research.v96_liquidity_sweep.baseline_backtest
"""
from collections import Counter
from datetime import datetime, timedelta
from .archive_reader import iter_candles
from .signal_pipeline import SweepMSS
from .trade_simulator import simulate_sell

def evaluate(rows, max_rows=None):
    counts=Counter()
    outcomes=[]
    signal=SweepMSS()
    previous=None
    pending=None
    trade_bars=[]
    sweep_high=None
    for i,bar in enumerate(rows):
        if max_rows is not None and i>=max_rows:
            break
        ts=datetime.fromisoformat(bar["minute_utc"])
        if previous is not None and ts-previous!=timedelta(minutes=1):
            counts["gaps"]+=1
            if pending is not None:
                counts["unresolved_at_gap"]+=1
            pending=None
            trade_bars=[]
            signal=SweepMSS()
            sweep_high=None
        previous=ts
        if pending is not None:
            if not trade_bars:
                # Entry must be the candle AFTER MSS, never the signal close.
                if bar["o"]>=pending["stop"]:
                    counts["invalid_next_open"]+=1
                    pending=None
                    continue
            trade_bars.append(bar)
            result=simulate_sell(trade_bars,pending["stop"],cost_per_oz=0.5)
            if result is not None:
                outcomes.append(result.net_r)
                counts[result.reason]+=1
                pending=None
                trade_bars=[]
            continue
        event=signal.update(bar)
        if event["event"]=="SWEEP":
            counts["sweeps"]+=1
            sweep_high=max(sweep_high or event["sweep_high"],event["sweep_high"])
        if event["event"]=="SELL_CONFIRMED":
            counts["mss"]+=1
            # Baseline only: $2 above retained sweep high; M5 ATR still pending.
            if sweep_high is None or not (13 <= ts.hour < 17):
                counts["out_of_session_or_missing_sweep"]+=1
                continue
            pending={"stop":max(sweep_high,bar["h"])+2.0}
            sweep_high=None
    if pending is not None:
        counts["unresolved_at_end"]+=1
    return {
        "warning":"UNFILTERED BASELINE ONLY; not validated V9.6 strategy",
        "counts":dict(counts),
        "closed_trades":len(outcomes),
        "net_r":round(sum(outcomes),4),
        "mean_net_r":round(sum(outcomes)/len(outcomes),4) if outcomes else None,
    }

if __name__=="__main__":
    import json
    print(json.dumps(evaluate(iter_candles()),indent=2))
