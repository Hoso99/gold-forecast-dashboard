"""V9.5 PAPER-only bounded recovery for a temporarily stale M1 cache.

Opt-in helper: no production monitor imports this module yet. Integration must
be reconciled against the current Oracle deployment and regression-tested.
"""
import time


STALE_MARKER = "WAIT_DATA: stale in-session M1"


def read_with_stale_retry(read_candles, *, timeout_seconds=25, interval_seconds=2,
                          monotonic=time.monotonic, sleep=time.sleep):
    """Retry ONLY the known transient stale-cache condition.

    All other errors propagate immediately. A real outage remains a WAIT_DATA
    failure. Freshness, completeness and continuity are enforced by read_candles.
    Caller must bound this delay against paper-position protective evaluation.
    """
    if not callable(read_candles):
        raise TypeError("read_candles must be callable")
    if timeout_seconds < 0 or interval_seconds <= 0:
        raise ValueError("invalid retry interval or timeout")
    deadline = monotonic() + timeout_seconds
    while True:
        try:
            return read_candles()
        except RuntimeError as exc:
            if str(exc) != STALE_MARKER:
                raise
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise
            sleep(min(interval_seconds, remaining))
