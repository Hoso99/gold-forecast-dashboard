"""Standalone V9.5 M5 exit research challenger. No trading or alert side effects.

Input: completed M5 OHLC bars, oldest first. Signal is evaluated at the final
bar's close; previous confirmed lower highs are determined using past bars only.
This is a candidate, NOT a validated trading rule.
"""
from dataclasses import dataclass
from typing import Optional, Sequence, Mapping

@dataclass(frozen=True)
class ExitAssessment:
    action: str
    buy_power_5: float
    buy_power_10: float
    previous_buy_power_5: float
    acceleration_pp: float
    reference_lower_high: Optional[float]
    body_close_break: bool
    warning: bool
    reason: str

def buy_power(bars: Sequence[Mapping[str, float]]) -> float:
    """Price-body proxy, not executed buy/sell volume."""
    up = sum(max(float(b["c"]) - float(b["o"]), 0.0) for b in bars)
    down = sum(max(float(b["o"]) - float(b["c"]), 0.0) for b in bars)
    return 100.0 * up / (up + down) if up + down else 50.0

def confirmed_lower_high(bars: Sequence[Mapping[str, float]], left: int = 2,
                         right: int = 2) -> Optional[float]:
    """Most recent causally confirmed swing high lower than preceding swing high.

    The current signal candle is excluded. A pivot needs 'right' completed
    bars AFTER the pivot, so a future pivot is never read early.
    """
    history = bars[:-1]
    pivots = []
    for i in range(left, len(history) - right):
        high = float(history[i]["h"])
        if (all(high > float(history[j]["h"]) for j in range(i-left, i))
                and all(high > float(history[j]["h"]) for j in range(i+1, i+right+1))):
            pivots.append(high)
    for i in range(len(pivots)-1, 0, -1):
        if pivots[i] < pivots[i-1]:
            return pivots[i]
    return None

def assess(m5: Sequence[Mapping[str, float]]) -> ExitAssessment:
    """Research-only: HOLD / WARNING / EXIT_CANDIDATE. Never close positions."""
    if len(m5) < 16:
        raise ValueError("At least 16 completed M5 bars required")
    for b in m5:
        if not all(k in b for k in ("o", "h", "l", "c")):
            raise ValueError("Missing OHLC field")
        o,h,l,c = (float(b[k]) for k in ("o","h","l","c"))
        if not l <= min(o,c) <= max(o,c) <= h:
            raise ValueError("Invalid OHLC candle")
    current = buy_power(m5[-5:])
    ten = buy_power(m5[-10:])
    previous = buy_power(m5[-10:-5])
    accel = current - previous
    level = confirmed_lower_high(m5)
    # Only the COMPLETED M5 close counts; high/wick never confirms a break.
    break_confirmed = level is not None and float(m5[-1]["c"]) > level
    warning = current > 55.0 and accel >= 10.0
    candidate = current > 60.0 and accel >= 10.0 and break_confirmed
    action = "EXIT_CANDIDATE" if candidate else ("WARNING" if warning else "HOLD")
    reason = ("M5 body-close above confirmed lower high with strong accelerating BUY proxy"
              if candidate else
              "BUY proxy rising; await completed M5 body-close structure confirmation"
              if warning else "Insufficient confirmed bullish reversal evidence")
    return ExitAssessment(action, round(current,2), round(ten,2),
                          round(previous,2), round(accel,2), level,
                          break_confirmed, warning, reason)
