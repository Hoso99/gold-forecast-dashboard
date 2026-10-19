# Oracle V9.5 PAPER runtime reconciliation — 2026-10-19

**Status:** local validation only; do not merge or deploy. The Oracle source ZIP was provided privately in the ChatGPT conversation and must **not** be committed to this public repository.

## Verified against actual Oracle source

- Monitor: `v95_paper_monitor.py` (615 lines).
- Session-aware cache reader: `v95_twelve_cache_reader_staging.py` (256 lines).
- Recovery worker: `v95_twelve_recovery_worker_staging.py` (73 lines).
- The monitor's `candles()` selects `read_candles_compatible()` when `V95_MARKET_DATA_SOURCE=TWELVE_DATA`.
- The Oracle reader raises the **exact** `RuntimeError("WAIT_DATA: stale in-session M1")` for out-of-range freshness. Its session-aware read path enforces the existing `max_age_seconds` (180 seconds in current runtime), plus other validation.
- The monitor calls `candles()` before `evaluate()`, so a stale exception blocks that cycle's paper-position protective evaluation. A retry adds up to 20 seconds latency to that same cycle; this is not a guaranteed improvement in protective evaluation. Do not enable without testing the open-position path.

## Locally checked

- A candidate patch gates the retry on `V95_MARKET_DATA_SOURCE=TWELVE_DATA` and otherwise preserves `candles()`.
- Six isolated local tests passed: transient recovery, persistent stale, unrelated error, immediate data, invalid arguments, and zero timeout.
- Python syntax compilation passed for candidate monitor/helper; all three original Oracle Python files parsed.
- **Not yet run:** the full V9.5 suite, live Oracle runtime, realistic collector timing tests, and paper-position SL/TP integration.

## Required next steps

1. Reconcile the candidate patch and helper against the isolated research branch, **without copying Oracle source files or configuration into this public repository**.
2. Add a deterministic integration test verifying that an already-open paper position cannot be delayed or bypassed by stale retries; quantify acceptable latency.
3. Test in Oracle staging with the existing session-aware reader, collect timestamps for collector refresh and monitor warnings, and verify persistent outages still produce WAIT_DATA.
4. Review and approve a V9.5 PAPER-only rollout and rollback plan. Do not alter V9.4 LIVE.

## Deployment boundaries

No changes to V9.4 LIVE, SELL-only gates, SL/TP, risk sizing, Telegram notifications, or data freshness threshold. No credentials, SSH keys, or server-specific configuration committed here.
