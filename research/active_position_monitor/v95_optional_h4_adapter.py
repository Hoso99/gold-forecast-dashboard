"""Optional H4 research diagnostics; never used to authorize SELL entries."""
from v95_indicators import diagnostics, rsi, pivot, pressure
from v95_research_votes import votes

def evaluate_optional_h4(m1, m5, m15, h1, h4):
    info = diagnostics(m1, m5, m15, h1, h4)
    if len(h4) >= 2:
        return info, votes(m1, m5, m15, h1, h4)
    info["h4_bearish"] = None
    if min(len(m1), len(m5), len(m15), len(h1)) < 2:
        return info, {"status": "INSUFFICIENT_DATA", "votes": {}, "independence_verified": False}
    strength = rsi([bar["c"] for bar in m15], 14)
    structure = len(m15) >= 6 and m15[-1]["c"] < min(bar["l"] for bar in m15[-5:-1]) and m15[-1]["c"] < pivot(h1[-2])
    momentum = len(m5) >= 5 and sum(m5[-i]["c"] < m5[-i-1]["c"] for i in range(1,5)) >= 3 and strength is not None and strength < 50
    flow = pressure(m1,10) >= 60 and pressure(m15,10) >= 55
    return info, {"status": "PARTIAL_RESEARCH_ONLY_UNVALIDATED",
                  "votes": {"trend": None, "structure": bool(structure),
                            "momentum": bool(momentum), "candle_flow_proxy": bool(flow)},
                  "agreement_available_votes": sum((structure, momentum, flow)),
                  "independence_verified": False}
