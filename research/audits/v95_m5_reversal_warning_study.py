"""Research-only M5 warning study. No orders, live alerts or production writes.

The warning is evaluated only after the M15 SELL signal and after a completed
M5 bar; future outcomes are used for evaluation, never for warning decisions.
M1 candle timestamps are assumed OPEN-stamped (NOT independently verified).
"""
from __future__ import annotations
import importlib.util
import json
import sys
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(Path(__file__).resolve().parent))
from v95_m5_confirmation_challenger import completed_bars


def study():
    m=pd.read_csv(ROOT/"candle_dynamics_m1_v94.csv",usecols=["datetime","open","high","low","close"])
    m["datetime"]=pd.to_datetime(m.datetime,utc=True,errors="raise")
    if m.datetime.duplicated().any(): raise ValueError("Duplicate M1 times")
    m=m.set_index("datetime").sort_index()
    b15=completed_bars(m,15)
    b5=completed_bars(m,5)
    spec=importlib.util.spec_from_file_location("v94_warning_power",ROOT/"candle_power_v94.py")
    mod=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=mod
    spec.loader.exec_module(mod)
    records=[]
    for i in range(29,len(b15)-5):
        h=b15.iloc[i-29:i+1];t=h.index[-1]
        if t-h.index[0]!=pd.Timedelta(minutes=435):continue
        p=mod.analyze_last_10_candles(h)
        if p.signal!="SELL" or mod.diagnose_sell_quality(p)["status"]!="CONFIRMED":continue
        # Warning is available 15 minutes AFTER the M15 signal, never at entry.
        warning_time=t+pd.Timedelta(minutes=15)
        if warning_time not in b5.index:continue
        j=b5.index.get_loc(warning_time)
        if j<10:continue
        h5=b5.iloc[j-9:j+1]
        if h5.index[-1]-h5.index[0]!=pd.Timedelta(minutes=45):continue
        # An interpretable M5 reversal proxy: >=3 rising closes among last 4
        # and M5 close above the close of the preceding M15 signal.
        rising=int((h5.close.diff().iloc[-4:]>0).sum())
        warning=bool(rising>=3 and h5.close.iloc[-1]>float(h.close.iloc[-1]))
        # Evaluate only AFTER warning is observable; do not pretend an exit
        # could occur at the earlier M15 entry.
        end=warning_time+pd.Timedelta(minutes=60)
        if end not in b5.index:continue
        f=b5.loc[warning_time:end]
        if len(f)!=13 or f.index[-1]-f.index[0]!=pd.Timedelta(minutes=60):continue
        # Future SELL-direction movement measured from warning-time close.
        movement=float(b5.loc[warning_time,"close"]-b5.loc[end,"close"])
        records.append(dict(t=t,warning=warning,forward_sell_move=movement))
    if not records:return {"status":"NO_VALID_OBSERVATIONS"}
    d=pd.DataFrame(records)
    split=b15.index[int(len(b15)*.7)]
    result={"status":"EXPLORATORY_NOT_LIVE","warning_delay_minutes":15,
            "timestamp_semantics":"UNVERIFIED_OPEN_STAMP_ASSUMPTION",
            "warning_rule":"At least 3 rising M5 closes in 4 completed M5 bars, and close above previous M15 signal close",
            "outcome":"Next 60m price movement from warning observation, not trade PnL",
            "limitations":["Warning occurs 15 minutes after signal; not usable at original entry",
                           "No SL/TP, bid/ask, spread, slippage or broker execution",
                           "Signals may overlap and be correlated",
                           "No proof of optimal threshold or out-of-sample robustness"],
            "periods":{}}
    for name,s in (("development",d[d.t<split-pd.Timedelta(minutes=60)]),
                   ("holdout",d[d.t>=split+pd.Timedelta(minutes=60)])):
        result["periods"][name]={}
        for label,g in (("warning",s[s.warning]),("no_warning",s[~s.warning])):
            result["periods"][name][label]={
                "n":len(g),
                "future_60m_sell_favorable_pct":round(100*float((g.forward_sell_move>0).mean()),2) if len(g) else None,
                "mean_future_60m_sell_price_move":round(float(g.forward_sell_move.mean()),4) if len(g) else None}
    return result

if __name__=="__main__":
    print(json.dumps(study(),indent=2))
