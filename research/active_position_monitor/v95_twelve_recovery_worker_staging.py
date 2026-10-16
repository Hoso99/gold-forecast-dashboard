"""V9.5 staging: continuous, single-source Twelve Data M1 recovery worker.

Separate SQLite cache only. Never touches live V9.4, V9.5 state, Biquote
databases, or sends trades/alerts. Requests at most once per poll interval.
Backoff on provider errors; cache retains already validated candles.
"""
import argparse
import datetime as dt
import json
import logging
import os
import signal
import time
from pathlib import Path

from v95_twelve_m1_recovery_staging import fetch, parse_values, store, continuity

UTC = dt.timezone.utc
LOG = logging.getLogger("v95-twelve-recovery")
STOP = False


def stop_handler(signum, frame):
    global STOP
    STOP = True


def run_once(cache, outputsize, lookback):
    now = dt.datetime.now(UTC)
    rows = parse_values(fetch(os.getenv("TWELVE_DATA_API_KEY", ""), outputsize), now)
    if not rows:
        raise ValueError("provider returned no completed M1")
    total = store(cache, rows)
    report = continuity(cache, now, lookback)
    report.update({"fetched_completed": len(rows), "cached_total": total,
                   "observed_utc": now.isoformat()})
    return report


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--cache", type=Path, default=Path("/home/ubuntu/v95-recovery-staging/twelve_m1_cache.sqlite3"))
    p.add_argument("--poll-seconds", type=int, default=120)
    p.add_argument("--outputsize", type=int, default=600)
    p.add_argument("--lookback", type=int, default=270)
    p.add_argument("--once", action="store_true")
    args = p.parse_args()
    if args.poll_seconds < 60 or not 1 <= args.outputsize <= 5000 or not 1 <= args.lookback <= 2700:
        p.error("invalid polling or historical window")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    signal.signal(signal.SIGTERM, stop_handler)
    signal.signal(signal.SIGINT, stop_handler)
    failures = 0
    while not STOP:
        try:
            report = run_once(args.cache, args.outputsize, args.lookback)
            # Avoid logging any API keys or complete provider response.
            LOG.info("RECOVERY source=%s missing=%s cached=%s latest=%s",
                     report["source"], report["missing_count"],
                     report["cached_total"], report["latest_expected_utc"])
            failures = 0
        except Exception as exc:
            failures += 1
            LOG.warning("RECOVERY_RETRY error_type=%s consecutive_failures=%d",
                        type(exc).__name__, failures)
        if args.once:
            break
        delay = min(900, args.poll_seconds * (2 ** min(failures, 3)))
        time.sleep(delay)


if __name__ == "__main__":
    main()
