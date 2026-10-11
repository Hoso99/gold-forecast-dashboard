"""Four interpretable research votes; not statistically independent until tested.

All inputs must be fully closed bars. These votes are NOT executable signals.
"""
from v95_indicators import ema,rsi,pressure,pivot

def votes(m1,m5,m15,h1,h4):
    if min(len(m1),len(m5),len(m15),len(h1),len(h4))<2:
        return {"status":"INSUFFICIENT_DATA","votes":{}}
    closes=[b["c"] for b in m15]
    fast,slow=ema(closes,9),ema(closes,21)
    strength=rsi(closes,14)
    # Trend, structure, momentum and candle pressure overlap in market data;
    # they are separate logical modules, not independent alpha sources.
    trend=fast is not None and slow is not None and fast<slow and h1[-1]["c"]<h1[-2]["c"] and h4[-1]["c"]<h4[-2]["c"]
    structure=len(m15)>=6 and m15[-1]["c"]<min(x["l"] for x in m15[-5:-1]) and m15[-1]["c"]<pivot(h1[-2])
    momentum=len(m5)>=5 and sum(m5[-i]["c"]<m5[-i-1]["c"] for i in range(1,5))>=3 and strength is not None and strength<50
    flow=pressure(m1,10)>=60 and pressure(m15,10)>=55
    return {"status":"RESEARCH_ONLY_UNVALIDATED","votes":{"trend":bool(trend),"structure":bool(structure),"momentum":bool(momentum),"candle_flow_proxy":bool(flow)},"agreement":sum((trend,structure,momentum,flow)),
            "independence_verified":False}
