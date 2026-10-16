"""Hybrid C: isolated, causal SELL exit/re-entry research state machine.

No network, broker, Telegram, filesystem or running-service side effects.
Feed COMPLETED M1 candles chronologically. Thresholds are research hypotheses,
not validated signals. Price-body power is NOT traded buy/sell volume.
"""
from dataclasses import dataclass, field
from collections import deque
from statistics import mean

@dataclass
class Config:
    early_buy_power: float = 58.0
    strong_buy_power: float = 72.0
    min_accel_pp: float = 12.0
    strong_accel_pp: float = 30.0
    confirm_bars: int = 2
    false_buy_drop_pp: float = 15.0
    false_sell_power: float = 60.0
    false_sell_accel_pp: float = 10.0
    false_window_bars: int = 3
    profit_watch_r: float = 0.5
    profit_sensitive_r: float = 1.0
    high_profit_r: float = 1.5
    giveback_r: float = 0.4
    reentry_minutes: int = 15
    reentry_sell_power: float = 62.0
    reentry_accel_pp: float = 10.0
    min_rr: float = 2.0
    stop_buffer: float = 0.0
    cost_per_oz: float = 0.0
    max_reentries_per_window: int = 1

def power(bars):
    up = sum(max(x["c"]-x["o"], 0) for x in bars)
    down = sum(max(x["o"]-x["c"], 0) for x in bars)
    return 100*up/(up+down) if up+down else 50.

def check(bar):
    b = {k: float(bar[k]) for k in ("o","h","l","c")}
    if not b["l"] <= min(b["o"],b["c"]) <= max(b["o"],b["c"]) <= b["h"]:
        raise ValueError("Invalid OHLC")
    return b

@dataclass
class PaperSell:
    entry: float
    stop: float
    target: float
    peak_r: float = 0.0
    def __post_init__(self):
        if not self.target < self.entry < self.stop:
            raise ValueError("SELL requires TP < entry < SL")
    @property
    def risk(self):
        return self.stop-self.entry
    def r(self, price, cost=0.0):
        return (self.entry-price-cost)/self.risk

@dataclass
class HybridC:
    cfg: Config = field(default_factory=Config)
    position: PaperSell | None = None
    bars: deque = field(default_factory=lambda: deque(maxlen=100))
    pending: int = 0
    reentry_left: int = 0
    reentries: int = 0
    events: list = field(default_factory=list)
    last_close: float | None = None
    reversal_anchor: float | None = None
    reversal_peak_buy: float | None = None
    reversal_age: int = 0

    def open_initial(self, entry, stop, target):
        if self.position is not None:
            raise ValueError("Already in position")
        self.position = PaperSell(entry, stop, target)

    def on_completed_m1(self, raw, *, high_risk_event=False, entry_allowed=True):
        """Return paper decision after a COMPLETED M1 bar. All exits at NEXT M1 open
        must be simulated by caller; emitted prices are signal references only.
        OHLC SL/TP ambiguity is explicitly flagged; never invent touch order.
        """
        b = check(raw)
        self.bars.append(b)
        a = list(self.bars)
        result = {"action":"WAIT", "reference_close":b["c"], "reason":"insufficient history"}
        if len(a) < 11:
            return result
        buy = power(a[-5:])
        prior = power(a[-10:-5])
        accel = buy-prior
        sell = 100-buy
        sell_accel = prior-buy
        bullish_break = b["c"] > max(x["h"] for x in a[-6:-1])
        bearish_break = b["c"] < min(x["l"] for x in a[-6:-1])
        bullish_body = b["c"] > b["o"]
        bearish_body = b["c"] < b["o"]
        if self.position:
            p = self.position
            sl_touch = b["h"] >= p.stop
            tp_touch = b["l"] <= p.target
            if sl_touch or tp_touch:
                self.pending = 0
                if sl_touch and tp_touch:
                    result = {"action":"INCONCLUSIVE_SL_TP_ORDER", "reason":"both touched in one M1 bar"}
                else:
                    result = {"action":"PROTECTIVE_SL" if sl_touch else "PROTECTIVE_TP",
                              "reason":"hard protective level touched; fill/order requires replay"}
                self.events.append(result)
                # Do not invent fill or reopen automatically.
                return result
            unrealized = p.r(b["c"], self.cfg.cost_per_oz)
            p.peak_r = max(p.peak_r, p.r(b["l"], self.cfg.cost_per_oz))
            giveback = p.peak_r-unrealized
            warning = buy >= self.cfg.early_buy_power and accel >= self.cfg.min_accel_pp
            strong = (buy >= self.cfg.strong_buy_power and
                      accel >= self.cfg.strong_accel_pp and bullish_break)
            # False-reversal detector: causal, time-limited, two-of-three vote.
            # Anchor is the resistance broken by a bullish close, fixed at the
            # moment of that break; never updated with later price information.
            if bullish_break and self.reversal_anchor is None:
                self.reversal_anchor = max(x["h"] for x in a[-6:-1])
                self.reversal_peak_buy = buy
                self.reversal_age = 0
            if self.reversal_anchor is not None:
                self.reversal_age += 1
                self.reversal_peak_buy = max(self.reversal_peak_buy, buy)
            buy_collapse = (self.reversal_peak_buy is not None and
                            self.reversal_peak_buy - buy >= self.cfg.false_buy_drop_pp)
            lost_structure = (self.reversal_anchor is not None and
                              b["c"] < self.reversal_anchor)
            sell_recovery = (sell >= self.cfg.false_sell_power and
                             sell_accel >= self.cfg.false_sell_accel_pp and bearish_body)
            false_votes = sum((buy_collapse, lost_structure, sell_recovery))
            rejected = self.reversal_anchor is not None and false_votes >= 2
            if rejected or self.reversal_age > self.cfg.false_window_bars:
                self.reversal_anchor = None
                self.reversal_peak_buy = None
                self.reversal_age = 0
            profit_watch = unrealized >= self.cfg.profit_watch_r and (warning or giveback >= self.cfg.giveback_r)
            profit_exit = (unrealized > 0 and p.peak_r >= self.cfg.profit_watch_r
                           and giveback >= self.cfg.giveback_r
                           and (warning or bullish_break))
            if rejected:
                self.pending = 0
            elif warning:
                self.pending += 1
            else:
                self.pending = 0
            sensitive = unrealized >= self.cfg.profit_sensitive_r or p.peak_r >= self.cfg.high_profit_r
            confirmed = self.pending >= (1 if sensitive else self.cfg.confirm_bars) and bullish_body
            if (strong or profit_exit or confirmed) and not rejected:
                self.pending = 0
                result = {"action":"EARLY_PROFIT_EXIT" if unrealized > 0 else "ADAPTIVE_EXIT",
                          "reason":"strong reversal" if strong else "profit giveback + reversal" if profit_exit else "adaptive M1 confirmation",
                          "r_reference":round(unrealized,4),
                          "peak_r":round(p.peak_r,4),
                          "giveback_r":round(giveback,4),
                          "execution":"next M1 open; not executed here"}
                # State transition is a paper exit REQUEST; caller must confirm fill.
            elif rejected:
                result = {"action":"FALSE_REVERSAL_HOLD",
                          "reason":"at least two causal false-reversal checks",
                          "votes":false_votes,
                          "buy_power_drop":buy_collapse,
                          "lost_bullish_structure":lost_structure,
                          "renewed_sell_pressure":sell_recovery,
                          "r_reference":round(unrealized,4)}
            elif profit_watch:
                result = {"action":"PROFIT_PROTECTION_WATCH", "r_reference":round(unrealized,4),
                          "giveback_r":round(giveback,4)}
            elif warning:
                result = {"action":"REVERSAL_WARNING", "buy_power":round(buy,2),
                          "acceleration_pp":round(accel,2)}
            else:
                result = {"action":"HOLD", "r_reference":round(unrealized,4)}
        elif self.reentry_left > 0:
            self.reentry_left -= 1
            phase = "FAST_0_5" if self.reentry_left >= self.cfg.reentry_minutes-5 else "STRUCTURE_5_15"
            qualifies = (sell >= self.cfg.reentry_sell_power and
                         sell_accel >= self.cfg.reentry_accel_pp and bearish_body and
                         (phase == "FAST_0_5" or bearish_break))
            if qualifies and not high_risk_event and entry_allowed and self.reentries < self.cfg.max_reentries_per_window:
                # Structure-derived stop, TP at 2R. Caller must validate account
                # exposure, daily loss, spread, volatility and next-open fill.
                proposed_stop = max(x["h"] for x in a[-5:]) + self.cfg.stop_buffer
                risk = proposed_stop-b["c"]
                if risk > 0:
                    result = {"action":"REENTRY_CANDIDATE", "entry_reference":b["c"],
                              "stop_reference":proposed_stop,
                              "target_reference":b["c"]-self.cfg.min_rr*risk,
                              "phase":phase, "execution":"next M1 open, approval required"}
                else:
                    result = {"action":"WAIT_REENTRY", "reason":"invalid stop distance"}
            else:
                result = {"action":"WAIT_REENTRY" if self.reentry_left else "NORMAL_SELL_SCAN",
                          "phase":phase, "reason":"no qualified SELL or blocked"}
        else:
            result = {"action":"NORMAL_SELL_SCAN", "reason":"outside reentry window"}
        self.events.append(result)
        return result

    def confirm_paper_exit(self):
        """Call only AFTER external replay establishes valid hypothetical exit fill."""
        if self.position is None:
            raise ValueError("No open position")
        self.position = None
        self.pending = 0
        self.reversal_anchor = None
        self.reversal_peak_buy = None
        self.reversal_age = 0
        self.reentry_left = self.cfg.reentry_minutes
        self.reentries = 0

    def confirm_paper_reentry(self, entry, stop, target):
        """Caller validates next-open fill, event restrictions and risk limits."""
        if self.position is not None or self.reentry_left <= 0:
            raise ValueError("No reentry authorization")
        if self.reentries >= self.cfg.max_reentries_per_window:
            raise ValueError("Reentry limit")
        if (entry-target)/(stop-entry) < self.cfg.min_rr-1e-9:
            raise ValueError("R:R below minimum")
        self.position = PaperSell(entry, stop, target)
        self.reentries += 1
        self.reentry_left = 0
