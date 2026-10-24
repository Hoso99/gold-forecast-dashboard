"""Research-only support-location alternatives.

The breakdown override is intentionally a callback: it must be supplied by
the validated V9.5 definition before historical comparison is claimed.
"""
def normal_location(price, older_support, m15_atr):
    if m15_atr <= 0:
        return False
    return price - older_support > m15_atr


def lenient_location(price, older_support, m15_atr, confirmed_breakdown):
    return normal_location(price, older_support, m15_atr) or bool(confirmed_breakdown)
