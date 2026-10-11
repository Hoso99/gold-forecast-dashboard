"""V9.5 offline hypothetical SELL SL/TP replay; research branch ONLY.

Not a reproduction of live V9.4: historical adaptive ATR, Biquote state,
actual bid/ask, and executions are unavailable. M1 is assumed open-stamped.
Conservative rule: if SL and TP touch in one M1 candle, count STOP first.
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


def resolve_sell(entry, stop, target, future, cost_points=0.30):
    """One hypothetical SELL; entry/SL/TP are mid-price levels, costs in gold points."""
    if not (np.isfinite(entry) and np.isfinite(stop) and np.isfinite(target)
            and stop>entry>target and cost_points>=0):
        raise ValueError("Invalid SELL setup")
    risk=stop-entry
    for _,bar in future.iterrows():
        hit_stop=float(bar.high)>=stop
        hit_target=float(bar.low)<=target
        if hit_stop:  # deliberately stop first when same minute ambiguous
            return {"outcome":"STOP","net_r":round((-risk-cost_points)/risk,5)}
        if hit_target:
            return {"outcome":"TARGET","net_r":round(((entry-target)-cost_points)/risk,5)}
    exit_price=float(future.iloc[-1].close)
    return {"outcome":"TIMEOUT","net_r":round((entry-exit_price-cost_points)/risk,5)}


def replay():
    m=pd.read_csv(ROOT/"candle_dynamics_m1_v94.csv",
                  usecols=["datetime","open","high","low","close"])
    m["datetime"]=pd.to_datetime(m.datetime,utc=True,errors="raise")
    if m.datetime.duplicated().any():raise ValueError("Duplicate M1 timestamps")
    m=m.set_index("datetime").sort_index()
    b15=completed_bars(m,15)
    b5=completed_bars(m,5)
    spec=importlib.util.spec_from_file_location("v94_trade_replay_power",ROOT/"candle_power_v94.py")
    mod=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=mod
    spec.loader.exec_module(mod)
    rows=[]
    horizon=120
    for i in range(30,len(b15)-9):
        hist=b15.iloc[i-29:i+1]
        t=hist.index[-1]
        if t-hist.index[0]!=pd.Timedelta(minutes=29*15):continue
        power=mod.analyze_last_10_candles(hist)
        if power.signal!="SELL" or mod.diagnose_sell_quality(power)["status"]!="CONFIRMED":continue
        if t not in m.index or t not in b5.index:continue
        j=b5.index.get_loc(t)
        if j<29 or b5.index[j]-b5.index[j-29]!=pd.Timedelta(minutes=145):continue
        m5=mod.analyze_last_10_candles(b5.iloc[j-29:j+1])
        future=m.loc[t:t+pd.Timedelta(minutes=horizon-1)]
        expected=pd.date_range(t,periods=horizon,freq="min",tz="UTC")
        if not future.index.equals(expected):continue
        prev=hist.close.shift(1)
        tr=pd.concat([(hist.high-hist.low),
                      (hist.high-prev).abs(),(hist.low-prev).abs()],axis=1).max(axis=1)
        atr=float(tr.rolling(14,min_periods=14).mean().iloc[-1])
        if not np.isfinite(atr) or atr<=0:continue
        entry=float(m.loc[t,"open"])
        swing_high=float(hist.high.iloc[-10:].max())
        # Fixed 1.5 ATR is a research assumption, NOT recorded V9.4 adaptive risk.
        stop=max(swing_high,entry)+1.5*atr
        risk=stop-entry
        if risk<=0:continue
        target=entry-2*risk
        outcome=resolve_sell(entry,stop,target,future)
        rows.append({"time":t,"m5_confirmed":m5.signal=="SELL",
                     "risk_points":risk,**outcome})
    if not rows:return {"status":"NO_VALID_TRADES"}
    d=pd.DataFrame(rows)
    split=b15.index[int(len(b15)*.70)]
    purge=pd.Timedelta(minutes=horizon)
    result={"status":"EXPLORATORY_NOT_LIVE","timestamp_semantics":"UNVERIFIED_OPEN_STAMP_ASSUMPTION",
            "risk_assumption":"Last 10 M15 highs + 1.5 ATR14; 2R target; fixed 120m timeout",
            "cost_assumption":"0.30 XAUUSD price points per round trip (illustrative, NOT sourced)",
            "same_bar_resolution":"STOP_FIRST","horizon_minutes":horizon,
            "limitations":["Not faithful V9.4 historical replay: adaptive ATR multiple and Biquote state absent",
                           "Illustrative constant cost, not bid/ask quotes or broker fills",
                           "M1 timestamp semantics unverified",
                           "Overlapping trades treated independently; portfolio drawdown not valid",
                           "Signals use historical candle power, not full production execution gates"],
            "periods":{}}
    for name,s in (("development",d[d.time<split-purge]),
                   ("holdout",d[d.time>=split+purge])):
        result["periods"][name]={}
        for label,g in (("M15",s),("M15_plus_M5",s[s.m5_confirmed])):
            result["periods"][name][label]={
                "n":len(g),"targets":int((g.outcome=="TARGET").sum()),
                "stops":int((g.outcome=="STOP").sum()),
                "timeouts":int((g.outcome=="TIMEOUT").sum()),
                "mean_net_r":round(float(g.net_r.mean()),4) if len(g) else None,
                "median_net_r":round(float(g.net_r.median()),4) if len(g) else None}
    return result


if __name__=="__main__":
    print(json.dumps(replay(),indent=2))
