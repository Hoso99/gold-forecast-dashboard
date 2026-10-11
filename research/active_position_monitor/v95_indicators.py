"""V9.5 research-only indicator diagnostics. No trading execution or hidden feeds."""
import math

def ema(values, period):
    if len(values)<period:
        return None
    value=sum(values[:period])/period
    k=2/(period+1)
    for x in values[period:]:
        value=x*k+value*(1-k)
    return value

def rsi(values, period=14):
    if len(values)<period+1:
        return None
    changes=[b-a for a,b in zip(values,values[1:])][-period:]
    gain=sum(max(d,0) for d in changes)/period
    loss=sum(max(-d,0) for d in changes)/period
    return 100 if loss==0 else 100-100/(1+gain/loss)

def pivot(previous):
    return (previous["h"]+previous["l"]+previous["c"])/3

def pressure(bars, window=10):
    tail=bars[-window:]
    sell=sum(max(b["o"]-b["c"],0) for b in tail)
    buy=sum(max(b["c"]-b["o"],0) for b in tail)
    return 100*sell/(sell+buy) if sell+buy else 50.

def diagnostics(m1,m5,m15,h1,h4):
    """Only supplied completed candles. Diagnostics are not independent alpha."""
    close=[x["c"] for x in m15]
    ema9=ema(close,9)
    ema21=ema(close,21)
    rsi14=rsi(close,14)
    m5close=[x["c"] for x in m5]
    m5momentum=(m5close[-1]-m5close[-4]) if len(m5close)>=4 else None
    prev=h1[-2] if len(h1)>=2 else None
    p=pivot(prev) if prev else None
    return {"m1_sell_pressure_10":round(pressure(m1),2),
            "m15_ema9":ema9,"m15_ema21":ema21,"m15_rsi14":rsi14,
            "m5_momentum_3":m5momentum,"previous_h1_pivot":p,
            "h4_bearish":len(h4)>=2 and h4[-1]["c"]<h4[-2]["c"],
            "bearish_ema_alignment":ema9 is not None and ema21 is not None and ema9<ema21,
            "below_previous_h1_pivot":p is not None and close[-1]<p}
