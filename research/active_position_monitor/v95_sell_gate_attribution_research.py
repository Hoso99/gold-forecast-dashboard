"""Research-only V9.5 SELL entry gate attribution; never places orders.

Consumes already-computed V9.5 indicator values. Does not alter monitor,
entry authorization, protective SL/TP, data feeds, or Telegram.
"""


def diagnose_sell_gate(*, structural_sell, h1_bearish, m5_bearish,
                       support_buffer, sell_power, threshold=60.0,
                       price=None, older_support=None, m15_atr=None):
    gates = {
        "structural_sell": bool(structural_sell),
        "h1_bearish": bool(h1_bearish),
        "m5_bearish": bool(m5_bearish),
        "support_buffer": bool(support_buffer),
        "sell_power": float(sell_power) >= float(threshold),
    }
    original = all(gates.values())
    without_location = all(value for name, value in gates.items()
                           if name != "support_buffer")
    return {
        "decision": "QUALIFIED_TECHNICAL_SELL" if original else "WAIT_SELL",
        "gates": gates,
        "failed_gates": [name for name, value in gates.items() if not value],
        "location_only_veto": not gates["support_buffer"] and without_location,
        "counterfactual_without_location": without_location,
        "sell_power": float(sell_power),
        "threshold": float(threshold),
        "price": price,
        "older_support": older_support,
        "m15_atr": m15_atr,
        "distance_above_support_atr": (
            (price - older_support) / m15_atr
            if price is not None and older_support is not None
            and m15_atr is not None and m15_atr > 0 else None
        ),
    }
