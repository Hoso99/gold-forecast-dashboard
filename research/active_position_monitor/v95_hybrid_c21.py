"""C2.1 isolated research-only confirmation logic; no live integrations.

Discretionary exits require a fresh completed bullish candle after a candidate.
Hard SL/TP handling belongs to the unchanged parent execution engine.
"""
from dataclasses import dataclass

@dataclass
class C21Confirm:
    candidate_minute: int | None = None
    max_wait: int = 2

    def observe(self, minute, bar, prior_bar, action, prior_five):
        """Return CONFIRM, WAIT or CANCEL; causal completed-bar inputs only."""
        if action == "FALSE_REVERSAL_HOLD":
            self.candidate_minute = None
            return "CANCEL"
        bearish_invalidation = (prior_bar is not None and
            bar["c"] < bar["o"] and bar["c"] < prior_bar["l"])
        if bearish_invalidation:
            self.candidate_minute = None
            return "CANCEL"
        candidate = action in ("ADAPTIVE_EXIT", "EARLY_PROFIT_EXIT")
        if self.candidate_minute is not None:
            elapsed = minute - self.candidate_minute
            if elapsed > self.max_wait:
                self.candidate_minute = None
            elif elapsed > 0:
                followthrough = (prior_bar is not None and
                    bar["c"] > bar["o"] and bar["c"] > prior_bar["c"])
                structure = (len(prior_five) == 5 and
                    bar["c"] > max(b["h"] for b in prior_five))
                if followthrough and (structure or candidate):
                    self.candidate_minute = None
                    return "CONFIRM"
        if candidate and self.candidate_minute is None:
            self.candidate_minute = minute
        return "WAIT"

def bearish_reentry_structure(bar, prior_five):
    """Reentry requires close below previous five completed M1 lows."""
    return (len(prior_five) == 5 and bar["c"] < bar["o"] and
            bar["c"] < min(b["l"] for b in prior_five))
