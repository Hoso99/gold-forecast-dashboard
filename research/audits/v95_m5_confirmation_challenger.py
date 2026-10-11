"""Offline V9.5 M5 confirmation challenger; NEVER emits trading signals.

Assumption: M1 source timestamps denote candle OPEN; verify with provider before
using any result. Uses complete M5/M15 bars and next-minute entry. Directional
60/120m outcome only, NOT an SL/TP execution backtest.
"""
from __future__ import annotations
import importlib.util
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]


def completed_bars(m: pd.DataFrame, minutes: int) -> pd.DataFrame:
    """Open-stamped, 1-minute source assumed. Reject missing or repeated minutes."""
    freq = f"{minutes}min"
    x = m.sort_index()
    rows = []
    for start, g in x.groupby(x.index.floor(freq)):
        expected = pd.date_range(start, periods=minutes, freq="min", tz="UTC")
        if len(g) != minutes or not g.index.equals(expected):
            continue
        rows.append((start + pd.Timedelta(minutes=minutes),
                     g.open.iloc[0], g.high.max(), g.low.min(), g.close.iloc[-1]))
    if not rows:
        return pd.DataFrame(columns=["open","high","low","close"],
                            index=pd.DatetimeIndex([], tz="UTC", name="end"))
    out = pd.DataFrame(rows, columns=["end","open","high","low","close"]).set_index("end")
    return out


def run() -> dict:
    path = ROOT / "candle_dynamics_m1_v94.csv"
    m = pd.read_csv(path, usecols=["datetime","open","high","low","close"])
    m["datetime"] = pd.to_datetime(m.datetime, utc=True, errors="raise")
    if m.datetime.duplicated().any():
        raise ValueError("Duplicate M1 timestamps; review source instead of silently deduplicating")
    m = m.set_index("datetime").sort_index()
    if not ((m.index.second == 0) & (m.index.microsecond == 0)).all():
        raise ValueError("Non-minute timestamps")
    b15, b5 = completed_bars(m,15), completed_bars(m,5)
    spec = importlib.util.spec_from_file_location("v94_candle_power_research", ROOT/"candle_power_v94.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    rows = []
    for i in range(29,len(b15)-8):
        hist = b15.iloc[i-29:i+1]
        t = hist.index[-1]
        if hist.index[-1]-hist.index[0] != pd.Timedelta(minutes=29*15):
            continue
        p = mod.analyze_last_10_candles(hist)
        if p.signal != "SELL" or mod.diagnose_sell_quality(p)["status"] != "CONFIRMED":
            continue
        if t not in b5.index:
            continue
        j = b5.index.get_loc(t)
        if j < 29:
            continue
        hist5 = b5.iloc[j-29:j+1]
        if hist5.index[-1]-hist5.index[0] != pd.Timedelta(minutes=29*5):
            continue
        p5 = mod.analyze_last_10_candles(hist5)
        # Only future bars, with uninterrupted M15 continuity, are outcomes.
        future = b15.iloc[i+1:i+9]
        if len(future)!=8 or future.index[-1]-t!=pd.Timedelta(minutes=120):
            continue
        # Enter at next M1 OPEN only under the explicitly unverified open-stamp assumption.
        if t not in m.index:
            continue
        entry = float(m.loc[t,"open"])
        rows.append(dict(time=t, entry=entry, m5_confirmed=p5.signal=="SELL",
                         net_60=entry-float(future.iloc[3].close),
                         net_120=entry-float(future.iloc[7].close)))
    d = pd.DataFrame(rows)
    if d.empty:
        return {"status":"NO_ALIGNED_SIGNALS","m15_bars":len(b15),"m5_bars":len(b5)}
    # Purge at least 120 minutes around split to avoid overlapping outcome labels.
    split_time=b15.index[int(len(b15)*.70)]
    purge=pd.Timedelta(minutes=120)
    samples={"development":d[d.time < split_time-purge],
             "holdout":d[d.time >= split_time+purge]}
    result={"status":"EXPLORATORY_NOT_LIVE","timestamp_semantics":"UNVERIFIED_OPEN_STAMP_ASSUMPTION",
            "m15_complete_bars":len(b15),"m5_complete_bars":len(b5),
            "candidate_rows":len(d),"purge_minutes_each_side":120,
            "limitations":["M1 timestamp semantics not provider-verified",
                           "Directional forward close only; NOT stop-loss/take-profit fill modeling",
                           "Overlapping signals within each sample remain correlated",
                           "No live quote, broker fills, bid/ask or verified cost model",
                           "M5 SELL confirmation may miss profitable M15 SELLs"],
            "periods":{}}
    for label,frame in samples.items():
        summary={}
        for name,subset in (("M15",frame),("M15_plus_M5",frame[frame.m5_confirmed])):
            summary[name]={"n":len(subset),
                           "down_60_pct":round(float((subset.net_60>0).mean()*100),2) if len(subset) else None,
                           "mean_60_price_move":round(float(subset.net_60.mean()),4) if len(subset) else None,
                           "down_120_pct":round(float((subset.net_120>0).mean()*100),2) if len(subset) else None,
                           "mean_120_price_move":round(float(subset.net_120.mean()),4) if len(subset) else None}
        result["periods"][label]=summary
    return result


if __name__=="__main__":
    print(json.dumps(run(),indent=2))
