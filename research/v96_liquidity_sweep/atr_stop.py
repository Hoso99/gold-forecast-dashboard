"""Research-only causal Wilder ATR for completed M5 candles.

Returns None until period+1 completed bars are available.
"""
def atr(completed_bars, period=14):
    if period < 1 or len(completed_bars) < period+1:
        return None
    trs=[]
    for previous,current in zip(completed_bars,completed_bars[1:]):
        high=float(current["h"]); low=float(current["l"])
        close=float(previous["c"])
        if not (high>=low>0 and close>0):
            raise ValueError("Invalid price")
        trs.append(max(high-low,abs(high-close),abs(low-close)))
    value=sum(trs[:period])/period
    for tr in trs[period:]:
        value=(value*(period-1)+tr)/period
    return value

def sell_stop(entry, sweep_high, m5_atr, atr_multiple=1.5, high_buffer=2.0, max_distance=None):
    """Stop at higher of sweep high + buffer or entry + ATR multiple.

    Returns None if the stop is too wide; never tightens the stop to fit cap.
    """
    if entry<=0 or sweep_high<=0 or m5_atr is None or m5_atr<=0:
        return None
    if atr_multiple<=0 or high_buffer<0:
        raise ValueError("Invalid stop parameters")
    stop=max(sweep_high+high_buffer,entry+atr_multiple*m5_atr)
    if max_distance is not None and stop-entry>max_distance:
        return None
    return stop
