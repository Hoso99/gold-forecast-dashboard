"""Research-only risk and UTC exit calculations (no orders)."""
from datetime import datetime, time, timedelta, timezone


def position_ounces(risk_dollars, entry, stop, estimated_stop_cost_per_oz=0.0):
    """SELL risk sizing. Costs include expected adverse stop execution per ounce."""
    if risk_dollars <= 0 or stop <= entry or estimated_stop_cost_per_oz < 0:
        raise ValueError("Invalid risk budget, SELL stop, or costs")
    return risk_dollars / (stop - entry + estimated_stop_cost_per_oz)


def exit_deadline(entry_utc):
    if entry_utc.tzinfo is None or entry_utc.utcoffset() != timedelta(0):
        raise ValueError("Entry must be timezone-aware UTC")
    cutoff = datetime.combine(entry_utc.date(), time(18, 30), tzinfo=timezone.utc)
    return min(entry_utc + timedelta(minutes=90), cutoff)
