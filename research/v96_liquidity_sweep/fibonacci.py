"""Research-only Fibonacci retracement calculations."""
def premium_zone(high, low, lower=0.5, upper=0.786):
    if high <= low or not 0 <= lower < upper <= 1:
        raise ValueError("Invalid bearish impulse or retracement bounds")
    span = high - low
    return low + span * lower, low + span * upper

def in_zone(price, high, low, lower=0.5, upper=0.786):
    a, b = premium_zone(high, low, lower, upper)
    return a <= price <= b
