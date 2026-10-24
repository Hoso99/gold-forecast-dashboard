"""Causal, research-only M1 liquidity-sweep detection.

A sweep must exceed a previously confirmed five-bar swing high and close
back below that level. The current candle never helps define its own level.
"""
def latest_confirmed_swing_high(bars):
    for i in range(len(bars)-3,1,-1):
        high=bars[i]["h"]
        if all(high>bars[j]["h"] for j in (i-2,i-1,i+1,i+2)):
            return {"index":i,"confirmed_index":i+2,"price":high}
    return None

def bearish_sweep(completed_prior_bars, current_bar, min_excess=0.0):
    if min_excess < 0:
        raise ValueError("min_excess must be nonnegative")
    level=latest_confirmed_swing_high(completed_prior_bars)
    if level is None:
        return None
    price=level["price"]
    if current_bar["h"] > price+min_excess and current_bar["c"] < price:
        return {"swept_level":price,"sweep_high":current_bar["h"],
                "swing_index":level["index"]}
    return None
