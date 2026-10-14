# V9.5 M1 recovery research (not deployed)

This branch is isolated from the live V9.4 system and the running Oracle V9.5 monitor.

## Current scope

- `v95_candle_gap_audit.py`: read-only scan of the last N stored Biquote candle timestamps.
- `v95_recovery_dry_run.py`: read-only inspection of an absent candle and its adjacent genuine Biquote candles; optional **explicit** single Twelve Data historical request.
- Tests run offline using temporary SQLite databases. No secrets, live market feed, or Oracle access are required.

Example after copying the branch to a **separate working directory** (do not overwrite server files):

```bash
python3 research/feed_validation/v95_candle_gap_audit.py --limit 2500
python3 research/feed_validation/v95_recovery_dry_run.py --minute 2026-10-14T10:23:00+00:00
python3 -m unittest discover -s research/feed_validation -p 'test_v95_*.py' -v
```

Do not use `--fetch-once` until the provider quota and feed comparison are approved; it costs provider credits and requires an API key from the process environment.

## Explicit safety constraints

1. No code in this branch writes to the candle database, state, journal, paper positions or live model.
2. A Twelve Data candle is **not** a Biquote tick-derived candle. It is quarantined even when OHLC is valid; a price discontinuity can change indicators and trade outcomes.
3. These scripts do not repair the loader's 720-candle gap gate or make the monitor continuous; doing that requires a separately reviewed integration and deployment.
4. The standard New York weekly/daily schedule is an assumption, not a verified provider holiday calendar.
5. Oracle's deployed loader/monitor differ from GitHub versions. Obtain a safe diff and backup before any integration.
6. Never commit API keys, tokens, SSH keys, SQLite databases or state files.
