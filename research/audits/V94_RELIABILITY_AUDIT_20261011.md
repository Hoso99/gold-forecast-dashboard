# V9.4 reliability audit — research-only, no deployment

This branch is a staging area for proposed fixes and regression tests. Do not merge or deploy without explicit approval.

## Evidence
- Journal: 62 SELL alerts; 13 WIN, 40 LOSS, 9 OPEN. Outcomes are candle-path simulations, **not** broker-confirmed positions.
- Legacy/no quality field: 1 WIN, 22 LOSS, 3 OPEN.
- Quality CONFIRMED: 12 WIN, 18 LOSS, 6 OPEN.
- Evidence journal: 206 evaluations, 24 SELL, 182 WAIT; 24 SELL records match trade journal timestamps.
- Latest GitHub Actions Entry Watch run 38129546005 failed on 2026-10-11 because the latest M15 candle was outside accepted market session.
- GitHub Actions cron: 2,17,32,47 minutes UTC. Cron does not guarantee exact timing.

## Proposed reliability changes (NOT APPLIED)
1. Closed-market runs should record a distinct SKIPPED_MARKET_CLOSED outcome and exit successfully without generating a SELL alert; genuine data failures should still fail.
2. Initialize `active` before conditional alert processing and add regression coverage for repeated same-candle evaluations.
3. Remove unconditional `reached=True`; verify actual entry threshold against a fresh quote and retain existing mandatory SL/TP checks.
4. Separate `SIGNAL_ALERTED`, `PAPER_POSITION`, and `MANUALLY_CONFIRMED_POSITION` records; do not treat Telegram delivery as a real position.
5. Verify chronological candle completion, freshness, stop/target ambiguity, bid/ask and slippage, overlapping alerts, and all WAIT outcomes.
6. Add tests for the dashboard-versus-entry-watcher SELL-only parity, risk sizing, event feed failures, and structural 2R feasibility.

## Isolation
- No changes to live V9.4 SELL-only direction, SL/TP, risk settings, Telegram, production workflow or Oracle.
- Existing draft PR #6 remains separate and unmerged.
- Next steps: create executable read-only tests and a proposed patch on this branch, then request review before any merge or deployment.
