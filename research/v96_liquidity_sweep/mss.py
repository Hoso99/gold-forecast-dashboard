"""Isolated V9.6 research-only M1 sweep/MSS state machine.

All bars passed to update() must be completed and chronological. No live orders.
"""
from dataclasses import dataclass
from typing import Optional


def latest_confirmed_swing_low(bars):
    """Most recent 5-bar fractal low known at end of supplied completed bars."""
    for i in range(len(bars) - 3, 1, -1):
        low = bars[i]["l"]
        if all(low < bars[j]["l"] for j in (i - 2, i - 1, i + 1, i + 2)):
            return {"index": i, "confirmed_index": i + 2, "price": low}
    return None


@dataclass
class SweepState:
    high: float
    mss_level: float
    sweep_index: int
    sweep_count: int = 1


class MSSDetector:
    """Sweep events supplied by a separate detector; MSS only after sweep bar.

    On a secondary sweep, re-anchor to latest *already confirmed* fractal low.
    If no confirmed low exists, cancel the pending setup.
    """
    def __init__(self, max_bars=10):
        if max_bars < 1:
            raise ValueError("max_bars must be positive")
        self.max_bars = max_bars
        self.bars = []
        self.pending: Optional[SweepState] = None

    def update(self, bar, is_sweep=False):
        """Return 'WAIT', 'MSS', 'EXPIRED', or 'INVALIDATED'."""
        idx = len(self.bars)
        # The current bar cannot confirm its own swing low or serve as MSS
        # confirmation for a sweep occurring on the same bar.
        previous_swing = latest_confirmed_swing_low(self.bars)
        if is_sweep:
            count = self.pending.sweep_count + 1 if self.pending else 1
            self.pending = (SweepState(
                high=max(bar["h"], self.pending.high) if self.pending else bar["h"],
                mss_level=previous_swing["price"],
                sweep_index=idx,
                sweep_count=count,
            ) if previous_swing is not None else None)
            result = "WAIT"
        elif self.pending is None:
            result = "WAIT"
        elif idx - self.pending.sweep_index > self.max_bars:
            self.pending = None
            result = "EXPIRED"
        elif bar["h"] > self.pending.high:
            self.pending = None
            result = "INVALIDATED"
        elif bar["c"] < self.pending.mss_level:
            self.pending = None
            result = "MSS"
        else:
            result = "WAIT"
        self.bars.append(dict(bar))
        return result
