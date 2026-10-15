"""Deterministic research-only Phase C outage tests.

No live services, sockets, DBs or market prices are modified. Tests demonstrate
what a secondary independent feed CAN and CANNOT cover during outages.
"""
from datetime import datetime, timedelta, timezone
from v95_independent_candle_builder import validate_ticks


def ticks(minute, offsets):
    return [(minute + timedelta(seconds=s), 4000 + s / 100) for s in offsets]


def assess_minute(minute, offsets, *, next_tick=True, secondary_connected=True,
                  first_minute_after_restart=False):
    """Fail closed on missing/partial sessions; no synthetic replacement ticks."""
    if not secondary_connected or first_minute_after_restart:
        return None
    observed = ticks(minute, offsets)
    confirmation = minute + timedelta(minutes=1, seconds=1) if next_tick else None
    return validate_ticks(minute, observed, confirmation)


def coverage(primary, secondary):
    """Independent coverage only; does not merge databases or change SELL inputs."""
    primary, secondary = set(primary), set(secondary)
    return dict(primary_only=sorted(primary - secondary),
                secondary_only=sorted(secondary - primary),
                shared=sorted(primary & secondary),
                unavailable=[])  # Unknown unless externally supplied expected slots.
