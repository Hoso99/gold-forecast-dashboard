"""Research-only causal sweep-to-MSS orchestration.

The same completed M1 candle is used once. The signal is only available
at the close of its confirming candle; fills must occur on a later candle.
"""
from .mss import MSSDetector
from .sweep import bearish_sweep


class SweepMSS:
    def __init__(self, max_bars=10, min_excess=0.0):
        self.detector=MSSDetector(max_bars=max_bars)
        self.min_excess=min_excess

    def update(self, bar):
        prior=self.detector.bars
        sweep=bearish_sweep(prior, bar, self.min_excess)
        result=self.detector.update(bar, is_sweep=sweep is not None)
        if result=="MSS":
            return {"event":"SELL_CONFIRMED", "confirmation_close":bar["c"],
                    "confirmation_index":len(self.detector.bars)-1}
        if sweep is not None:
            return {"event":"SWEEP", **sweep}
        return {"event":result}
