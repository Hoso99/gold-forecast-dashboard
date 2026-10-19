# V9.5 PAPER — stale-data recovery plan (isolated)

Status: **research-only; NOT DEPLOYED**.

This branch was created from `research/v95-gap-recovery-staging-20261016`. **Its cache reader differs from the newer version currently running on Oracle.** Do not deploy this branch wholesale or overwrite Oracle's session-aware reader.

## Baseline observations (2026-10-19 UTC)

- 22 `WAIT_DATA: stale in-session M1` warnings between 10:00 and 12:40.
- The SQLite archive was subsequently continuous; retrospective reconstruction showed eligible completed candles younger than 180 seconds, but backfilled data cannot establish the exact cache state at each warning.
- Oracle collector service executes `v95_twelve_recovery_worker_staging.py --poll-seconds 120` in a recovery-staging working directory.
- Oracle monitor runs from `/home/ubuntu/v95-research`, evaluates independently with `POLL=max(30,int(V95_POLL_SECONDS or 60))` and uses a newer `read_candles_session_aware` implementation with a 70-second eligibility cutoff.
- GitHub's old staging cache reader does **not** contain Oracle's session-aware implementation.

## Proposed safe change — requires Oracle version reconciliation

1. Obtain a sanitized, exact snapshot or commit of the *currently running* Oracle monitor, session-aware cache reader, and collector worker. Compare SHAs and preserve existing C2 Raw/protective-exit behavior.
2. Write unit tests for late collector refresh, cache updated during retry, persistent provider outage, weekend/session boundary, complete-candle cutoff, sequential timestamps, open paper-position protective SL/TP checks, and interrupt responsiveness.
3. Make the collector poll every 60 seconds after confirming one-request-per-cycle usage and backup of the unit. Keep backoff on errors.
4. Implement a **bounded stale-only cache reload** *before evaluation*; never change the 180-second freshness threshold or turn a genuine stale state into an entry. A retry may wait up to 20–30 seconds for the collector, requerying the cache in read-only mode. If it stays stale, preserve `WAIT_DATA`.
5. Prevent the retry from starving protective SL/TP monitoring: validate gap-aware chronological M1 checks and document bounded delay/recovery behavior under an open position.
6. Deploy **only** to isolated V9.5 PAPER services with explicit verification and rollback; do not touch V9.4 LIVE or merge to `main`.
7. Compare warnings per monitor evaluation, completed-M1 age at decision time, provider errors, continuity, and defensive behavior before/after, including real provider outage scenarios.

## Safety

- No removal of SL/TP, no changed SELL gates or position sizing.
- No Telegram token, SSH secret, API key, or environment file committed.
- No setting `max_age_seconds` higher merely to hide warnings.
- A true provider outage MUST still produce `WAIT_DATA`.
- Never auto-merge or auto-deploy this planning branch.
