"""V9.4 validation utilities: divergence, untouched holdout, module dependence."""
from __future__ import annotations
import numpy as np
import pandas as pd
from candle_power_v94 import analyze_last_10_candles


def indicator_divergence(gold, lookback=10):
    """Return RSI/MACD divergence using only completed bars up to the last row."""
    if gold is None or len(gold) < 40:
        return {"signal":"NONE","score":0.0,"detail":"insufficient data"}
    c=gold.close.astype(float)
    delta=c.diff(); up=delta.clip(lower=0); dn=(-delta.clip(upper=0))
    rs=up.rolling(14).mean()/dn.rolling(14).mean().replace(0,np.nan)
    rsi=100-100/(1+rs)
    ema12=c.ewm(span=12,adjust=False).mean(); ema26=c.ewm(span=26,adjust=False).mean()
    macd=ema12-ema26; hist=macd-macd.ewm(span=9,adjust=False).mean()
    old=slice(-(lookback+1),-max(2,lookback//2)); new=slice(-max(2,lookback//2),None)
    p_old=float(c.iloc[old].max()); p_new=float(c.iloc[new].max())
    pl_old=float(c.iloc[old].min()); pl_new=float(c.iloc[new].min())
    r_old=float(rsi.iloc[old].mean()); r_new=float(rsi.iloc[new].mean())
    m_old=float(hist.iloc[old].mean()); m_new=float(hist.iloc[new].mean())
    bearish=(p_new>p_old and (r_new<r_old or m_new<m_old))
    bullish=(pl_new<pl_old and (r_new>r_old or m_new>m_old))
    if bearish and not bullish: return {"signal":"SELL","score":-1.0,"detail":"price high strengthened while RSI/MACD momentum weakened"}
    if bullish and not bearish: return {"signal":"BUY","score":1.0,"detail":"price low weakened while RSI/MACD momentum strengthened"}
    return {"signal":"NONE","score":0.0,"detail":"no confirmed RSI/MACD divergence"}


def untouched_holdout_report(gold, holdout_fraction=.20, horizon=2, cost_bps=10):
    """Evaluate frozen 10-candle rules only on the final untouched chronological block."""
    cols=["status","holdout_bars","signals","buy_signals","sell_signals","accuracy","expectancy","profit_factor","max_drawdown"]
    if gold is None or len(gold)<250:
        return {k:("INSUFFICIENT DATA" if k=="status" else np.nan) for k in cols}
    split=max(40,int(len(gold)*(1-holdout_fraction))); rows=[]
    for i in range(split, len(gold)-horizon):
        p=analyze_last_10_candles(gold.iloc[:i+1])
        if p.signal not in {"BUY","SELL"}: continue
        side=1 if p.signal=="BUY" else -1
        ret=float(gold.close.iloc[i+horizon]/gold.close.iloc[i]-1)
        net=side*ret-float(cost_bps)/10000
        rows.append((p.signal,net))
    if not rows:
        return {"status":"NO HOLDOUT SIGNALS","holdout_bars":len(gold)-split,"signals":0,"buy_signals":0,"sell_signals":0,"accuracy":np.nan,"expectancy":np.nan,"profit_factor":np.nan,"max_drawdown":np.nan}
    sides=[x[0] for x in rows]; rets=np.array([x[1] for x in rows],float)
    gains=rets[rets>0].sum(); losses=-rets[rets<0].sum(); pf=gains/losses if losses>0 else np.inf
    curve=np.cumsum(rets); peak=np.maximum.accumulate(np.r_[0,curve])[1:]; dd=curve-peak
    return {"status":"UNTOUCHED HOLDOUT","holdout_bars":len(gold)-split,"signals":len(rows),"buy_signals":sides.count("BUY"),"sell_signals":sides.count("SELL"),"accuracy":float((rets>0).mean()),"expectancy":float(rets.mean()),"profit_factor":float(pf),"max_drawdown":float(dd.min())}


def module_dependence(module_history):
    """Measure, never assume, pairwise signal correlation and directional overlap."""
    if module_history is None or len(module_history)<20:
        return pd.DataFrame(columns=["Module A","Module B","Correlation","Directional overlap"])
    f=pd.DataFrame(module_history).copy(); out=[]; names=list(f.columns)
    for i,a in enumerate(names):
        for b in names[i+1:]:
            x=pd.to_numeric(f[a],errors="coerce"); y=pd.to_numeric(f[b],errors="coerce")
            valid=x.notna()&y.notna(); corr=float(x[valid].corr(y[valid])) if valid.sum()>=3 else np.nan
            active=valid&(x!=0)&(y!=0); overlap=float((np.sign(x[active])==np.sign(y[active])).mean()) if active.any() else np.nan
            out.append({"Module A":a,"Module B":b,"Correlation":corr,"Directional overlap":overlap})
    return pd.DataFrame(out)
