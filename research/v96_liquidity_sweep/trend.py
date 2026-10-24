"""Research-only completed-candle higher-timeframe trend filter.

Input bars must be chronological, completed H1 or H4 candles.
Never supply the still-forming higher-timeframe candle.
"""
def ema(values, period):
    if period < 1 or len(values) < period:
        return None
    alpha = 2.0 / (period + 1)
    value = sum(values[:period]) / period
    for price in values[period:]:
        value = alpha * price + (1.0 - alpha) * value
    return value

def bearish_trend(completed_bars):
    if len(completed_bars) < 22:
        return False
    closes = [float(bar["c"]) for bar in completed_bars]
    return (ema(closes, 9) < ema(closes, 21)
            and closes[-1] < closes[-2])

def h1_h4_bearish(completed_h1, completed_h4):
    return bearish_trend(completed_h1) and bearish_trend(completed_h4)
