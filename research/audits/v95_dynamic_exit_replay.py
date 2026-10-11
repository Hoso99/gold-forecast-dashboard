"""V9.5 causal SELL exit challenger vs fixed-2R baseline, OFFLINE ONLY.

Uses historical M15 candle-power SELL confirmation, fixed structural/ATR
research assumptions, and completed M5/M15/H1 reversal proxies. This is
NOT a faithful live V9.4 replay or evidence of profitability.
"""
from __future__ import annotations
import importlib.util
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from v95_m5_confirmation_challenger import completed_bars

ROOT=Path(__file__).resolve().parents[2]
COST=0.30
HORIZON=120


def run():
    m=pd.read_csv(ROOT/"candle_dynamics_m1_v94.csv",
                  usecols=["datetime","open","high","low","close"])
    m["datetime"]=pd.to_datetime(m.datetime,utc=True)
    if m.datetime.duplicated().any():raise ValueError("Duplicate M1 times")
    m=m.set_index("datetime").sort_index()
    b15=completed_bars(m,15)
    b5=completed_bars(m,5)
    h1=completed_bars(m,60)
    spec=importlib.util.spec_from_file_location("v94_exit_power",ROOT/"candle_power_v94.py")
    power=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=power
    spec.loader.exec_module(power)
    # Precompute completed-bar features; observations at t use bars ending <=t.
    rev5=(b5.close.diff().gt(0).rolling(4,min_periods=4).sum().ge(3)
          & b5.close.gt(b5.close.shift(1)))
    inv15=b15.close.gt(b15.high.shift(1).rolling(3,min_periods=3).max())
    bull1=h1.close.gt(h1.close.shift(1))
    # At t, all indicators are known from bars completed at or before t.
    def flags(t):
        def last(s):
            p=s.index.searchsorted(t,side="right")-1
            return bool(s.iloc[p]) if p>=0 and pd.notna(s.iloc[p]) else False
        return last(rev5),last(inv15),last(bull1)

    def simulate(entry,stop,future,dynamic):
        risk=stop-entry
        qty=1.0
        pnl=0.0
        partial=False
        active_stop=stop
        pending=None
        outcome="TIMEOUT"
        for k,(t,b) in enumerate(future.iterrows()):
            # Pending close/partial decided at prior completed candle boundary
            # executes at NEXT M1 open; never at the signal's own close.
            if pending:
                if pending=="EXIT":
                    pnl+=qty*(entry-float(b.open));qty=0;outcome="EARLY_EXIT";break
                if pending=="PARTIAL" and not partial:
                    pnl+=0.5*(entry-float(b.open));qty=0.5;partial=True
                    # Breakeven protective stop becomes effective this bar.
                    active_stop=min(active_stop,entry)
                pending=None
            if float(b.open)>=active_stop or float(b.high)>=active_stop:
                pnl+=qty*(entry-max(active_stop,float(b.open)))
                qty=0;outcome="STOP";break
            if float(b.low)<=entry-2*risk:
                pnl+=qty*2*risk;qty=0;outcome="TARGET";break
            if dynamic:
                # The completed minute becomes observable only at t+1 minute.
                obs=t+pd.Timedelta(minutes=1)
                m5,m15,h1bull=flags(obs)
                if m15 or (m5 and h1bull):
                    pending="EXIT"
                elif not partial and float(b.close)<=entry-risk:
                    pending="PARTIAL"
        if qty:
            pnl+=qty*(entry-float(future.iloc[-1].close))
        return {"net_r":round((pnl-COST)/risk,5),"outcome":outcome,
                "partial":partial}

    trades=[]
    last_exit=None
    for i in range(29,len(b15)-9):
        hist=b15.iloc[i-29:i+1]
        t=hist.index[-1]
        if t-hist.index[0]!=pd.Timedelta(minutes=435):continue
        if last_exit is not None and t<last_exit:continue
        p=power.analyze_last_10_candles(hist)
        if p.signal!="SELL" or power.diagnose_sell_quality(p)["status"]!="CONFIRMED":
            continue
        if t not in m.index:continue
        future=m.loc[t:t+pd.Timedelta(minutes=HORIZON-1)]
        expected=pd.date_range(t,periods=HORIZON,freq="min",tz="UTC")
        if not future.index.equals(expected):continue
        prev=hist.close.shift(1)
        tr=pd.concat([hist.high-hist.low,(hist.high-prev).abs(),
                      (hist.low-prev).abs()],axis=1).max(axis=1)
        atr=float(tr.rolling(14,min_periods=14).mean().iloc[-1])
        entry=float(future.iloc[0].open)
        if not np.isfinite(atr) or atr<=0:continue
        stop=max(float(hist.high.iloc[-10:].max()),entry)+1.5*atr
        base=simulate(entry,stop,future,False)
        challenger=simulate(entry,stop,future,True)
        trades.append({"t":t,"baseline":base,"challenger":challenger})
        # Both strategies use same fixed 120m entry spacing, not independent
        # overlapping hypothetical positions.
        last_exit=t+pd.Timedelta(minutes=HORIZON)
    if not trades:return {"status":"NO_VALID_NONOVERLAPPING_TRADES"}
    split=b15.index[int(len(b15)*0.7)]
    purge=pd.Timedelta(minutes=HORIZON)
    def summarize(group,key):
        vals=[r[key]["net_r"] for r in group]
        return {"n":len(vals),"mean_net_r":round(float(np.mean(vals)),5) if vals else None,
                "median_net_r":round(float(np.median(vals)),5) if vals else None,
                "stops":sum(r[key]["outcome"]=="STOP" for r in group),
                "targets":sum(r[key]["outcome"]=="TARGET" for r in group),
                "early_exits":sum(r[key]["outcome"]=="EARLY_EXIT" for r in group),
                "timeouts":sum(r[key]["outcome"]=="TIMEOUT" for r in group)}
    periods={}
    for name,g in (("development",[x for x in trades if x["t"]<split-purge]),
                   ("holdout",[x for x in trades if x["t"]>=split+purge])):
        periods[name]={"fixed_2r":summarize(g,"baseline"),
                       "dynamic_reversal_partial":summarize(g,"challenger")}
    return {"status":"EXPLORATORY_NOT_LIVE","nonoverlapping_trades":len(trades),
            "horizon_minutes":HORIZON,"cost_points":COST,"periods":periods,
            "limitations":["M1 timestamps assumed open-stamped; unverified",
            "Historical adaptive ATR and Biquote event state unavailable",
            "Fixed 1.5 ATR is a research proxy, not actual live V9.4 risk",
            "No bid/ask or fills; 0.30 points illustrative roundtrip cost",
            "Completed-bar reversal rules are hypotheses, not validated signals",
            "M1 stop-first approximation; broker gap/slippage may differ",
            "Holdout must not be used for parameter tuning"]}


if __name__=="__main__":
    print(json.dumps(run(),indent=2))
