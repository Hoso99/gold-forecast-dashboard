# V9.5 Oracle integration contract — review before deployment

## Goal
Continue the process and collector during open XAU/USD sessions regardless of the number of missing historical M1 candles. Never fabricate OHLC, alter the SELL formula, or touch V9.4.

## Verified research
- Offline recovery suite: GitHub Actions run #8 passed.
- Read-only Oracle probe: 2,442 M1 records; M5 valid; M15 indicator window blocked at 2026-10-14 13:18 UTC.
- Oracle monitor (deployed, not the older GitHub copy): `candles()` line 73, `aggregate()` line 88, `evaluate()` line 113, `cycle()` line 285.
- Deployed monitor SHA256: `7c4be5242e092376185d45c918b7123dd79b63e0e3f39c97b91414832384e231`; **do not overwrite with the GitHub version**.
- Deployed loader SHA256: `c92452b40566b7b58a1af7453d8752be8de5c5b25f85a629f0d41bd22bc4618d`.

## Proposed integration (not deployed)
1. Keep the original Oracle loader and monitor untouched during shadow testing. Import `v95_resilient_biquote_reader.read_candles` into an isolated runner.
2. Use the existing Oracle `aggregate` algorithm; it discards incomplete higher-timeframe bars.
3. Validate actual windows required by `diagnostics`, `votes`, `entry_diagnostics`, `exit_diagnostics`, `detect_core_sell`, ATR(14), and the position-exit logic. Current `v95_gap_aware_gate.REQUIREMENTS` are **provisional minimums**, not proven sufficient for all modules.
4. Separate data availability for *new entries* from protection of an *already-open paper position*. Never allow a gap in M15/H4 to suppress stop/target checks based on a fresh genuine M1 OHLC. Do not use stale or invented fills.
5. During normal weekday maintenance and weekends, remain healthy but do not evaluate new trades. Handle provider holidays conservatively.
6. On every minute: report collector freshness, missing minute count, last 10 M1 integrity, and availability of M5/M15/H1/H4 indicator windows. Missing candles are **diagnostics**, not process-fatal errors.
7. Never advance `state["last_bar"]` merely because data failed eligibility checks; preserve exactly-once paper-position accounting and journaling.
8. Test: 0, 1, 10, 100 missing historical M1; missing newest M1; stale collector; gap in M15 ATR; H4 session boundary; restart mid-position; both SL/TP touched; market closed; weekend reopen.
9. Only after independent tests and Oracle file backups, deploy with a reversible, explicit approval step. Keep live V9.4 untouched.

## Safety note
Continuous *service operation* is achievable as a design target; continuous reliable SELL *signals* cannot be guaranteed during unavailable or incomplete market data.
