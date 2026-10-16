"""Optional causal scenario annotation for Hybrid C2 Raw research.

Observational only: does not authorize exits, entries, SL/TP edits or alerts.
Completed M1 bars only; higher timeframe and calendar data NOT inferred.
"""
from dataclasses import dataclass
from statistics import mean

@dataclass
class RawScenarioMonitor:
    def classify(self,bars,position,action,*,high_risk_event=False):
        if not position:
            return {"state":"NO_OPEN_SELL","confidence":"NOT_ESTIMATED","data":"M1_ONLY"}
        if len(bars)<16:
            return {"state":"INSUFFICIENT_HISTORY","confidence":"NOT_ESTIMATED","data":"M1_ONLY"}
        recent=bars[-5:];previous=bars[-10:-5]
        up=sum(max(b["c"]-b["o"],0) for b in recent)
        down=sum(max(b["o"]-b["c"],0) for b in recent)
        buy=100*up/(up+down) if up+down else 50.0
        closes=[b["c"] for b in bars[-16:]]
        last=bars[-1]
        prev_high=max(b["h"] for b in bars[-6:-1])
        prev_low=min(b["l"] for b in bars[-6:-1])
        bullish_break=last["c"]>prev_high
        bearish_break=last["c"]<prev_low
        # M1 true-range expansion relative to preceding 10 completed bars
        def tr(i):
            b=bars[i];pc=bars[i-1]["c"]
            return max(b["h"]-b["l"],abs(b["h"]-pc),abs(b["l"]-pc))
        prior_tr=mean(tr(i) for i in range(len(bars)-11,len(bars)-1))
        current_tr=tr(len(bars)-1)
        expanding=current_tr>=2*max(prior_tr,1e-8)
        if high_risk_event or expanding:
            state="HIGH_VOLATILITY_EVENT"
        elif action in ("PROTECTIVE_SL","PROTECTIVE_TP","INCONCLUSIVE_SL_TP_ORDER"):
            state="PROTECTIVE_LEVEL_EVENT"
        elif bullish_break and buy>=72:
            state="CONFIRMED_REVERSAL_CANDIDATE"
        elif action in ("ADAPTIVE_EXIT","EARLY_PROFIT_EXIT","REVERSAL_WARNING","PROFIT_PROTECTION_WATCH") or (buy>=58 and last["c"]>closes[-6]):
            state="REVERSAL_WARNING"
        elif bearish_break or (buy<=40 and last["c"]<closes[-6]):
            state="SELL_CONTINUATION"
        elif last["c"]>closes[-6]:
            state="NORMAL_PULLBACK_CANDIDATE"
        else:
            state="SIDEWAYS_OR_UNCLEAR"
        return {"state":state,"confidence":"NOT_ESTIMATED","data":"M1_ONLY",
                "buy_body_power_5":round(buy,2),
                "m1_true_range_expansion":round(current_tr/max(prior_tr,1e-8),2),
                "unrealized_r_reference":round(position.r(last["c"]),4),
                "distance_to_stop":round(position.stop-last["c"],5),
                "distance_to_target":round(last["c"]-position.target,5),
                "note":"Observational research label; not a validated prediction or trade instruction"}
