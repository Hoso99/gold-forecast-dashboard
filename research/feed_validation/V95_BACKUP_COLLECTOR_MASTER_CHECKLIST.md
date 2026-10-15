# V9.5 Independent Biquote Backup Collector — Master Checklist

Last reviewed: 2026-10-15. Status: RESEARCH ONLY; SECOND LIVE COLLECTOR NOT STARTED.

## Objective
Run a second, genuinely independent Biquote XAU/USD WebSocket collector on Oracle Always Free, recording eligible M1 candles into its own SQLite database. Reduce avoidable missing candles without inventing data or changing live V9.4/V9.5 SELL decisions.

## Immutable safeguards
- [ ] Never modify or deploy to live V9.4, including SELL-only rules, SL/TP, risk, or Telegram.
- [ ] Never change V9.5 SELL calculations, thresholds, gating, SL/TP, 2% planned risk, or 3% daily loss lock.
- [ ] Do not modify the primary Biquote collector or primary SQLite database.
- [ ] Never synthesize, backfill, or mix provider prices; preserve genuine Biquote BID OHLC basis.
- [ ] Preserve strict M1 quality: first tick <=5s, last tick <=5s, >=2 ticks, no intertick gap >10s, next-minute confirmation; restart partial minute ineligible.
- [ ] Keep secondary collector database and service isolated. Fail closed on invalid ticks and gaps.
- [ ] Research changes stay on research branch/PR; no main branch changes.
- [ ] Never expose SSH keys, API tokens, secrets, private source literals, or tick payloads in public GitHub logs.
- [ ] Use Oracle Always Free only; obtain explicit approval before consequential live deployments/resource creation.
- [ ] Keep GitHub self-hosted runner least-privileged; avoid executing untrusted PR code.
- [ ] Do not reboot Oracle or interrupt primary services for backup work without explicit approval.

## Completed and verified
- [x] Oracle Ubuntu Always Free server provisioned.
- [x] GitHub self-hosted runner v94-research-monitor connected and executing research jobs on Oracle.
- [x] Narrow ACL read access to primary collector source granted to v95research; no sudo privileges granted.
- [x] Existing primary collector inspected with redacted AST metadata.
- [x] Primary WebSocket, SignalR handshake shape, reconnect loop and SQLite write structure identified.
- [x] Primary uses genuine Biquote BID prices for candles (not bid/ask midpoint).
- [x] October 14 missing M1 minute slots identified: 10:23, 11:51, 19:59 UTC. No historical backfill authorized.
- [x] Research-only archive of primary candles created and tested; cannot recover absent primary candles.
- [x] Hypothetical interruption/continuity simulation implemented; NOT historical replay.
- [x] Independent minute timing simulation and automated tests created.
- [x] Isolated candle-builder validator and tests created.
- [x] Isolated SignalR framing and bid tick parser and tests created.
- [x] GitHub Actions offline tests, Oracle read-only inspection, and Oracle isolated builder smoke tests passed (run 38703942041 per user screenshot).
- [x] Existing V9.4 and V9.5 services left unchanged by these research commits.

## Phase A — Genuine independent Biquote WebSocket transport
- [x] Confirm exact primary subscription fields and tick schema through privacy-safe local inspection; avoid logging secrets. SignalR Subscribe arguments must be nested: [['XAUUSD']].
- [ ] Implement isolated SignalR handshake, subscribe, heartbeat/timeout, reconnect/backoff, UTC source timestamps, XAUUSD filter and bid/ask validation.
- [ ] Add tests for malformed frames, wrong symbols, out-of-order/stale ticks, disconnects and reconnects.
- [x] Verify the provider permits a simultaneous second independent session; do not disrupt the primary. Oracle run 38707386525: connected and subscription acknowledged.
- [x] Run a short controlled research-only connection probe on Oracle with no database writes. 20 seconds, no DB writes.
- [x] Confirm authentic incoming Biquote ticks and correct bid basis; record only safe counts/status, never payloads. 40/40 valid XAUUSD ticks (run 38707386525).

## Phase B — Independent M1 storage
- [x] Implement separate SQLite database schema and validate in a disposable isolated Oracle directory; permanent research directory setup remains pending.
- [x] Validate candle provenance and strict first/last/gap/confirmation rules in bounded Oracle integration proof; first observed partial minute excluded.
- [x] Implement idempotent writes, conflict detection, SQLite busy timeout and safe database initialization; offline tests passed.
- [x] Test isolation: independent 95-second Oracle proof wrote only to disposable SQLite; primary_database_writes=false.
- [x] Verify first real independently captured M1 candle: run 38708290021, 131 valid ticks, 1 validated M1 stored, 0 rejected; sustained timestamp continuity remains Phase C.

## Phase C — Reliability and recovery
- [ ] Test primary interruption while independent connection stays up; use controlled simulation unless explicit permission to interrupt live primary.
- [ ] Test independent connection interruption and recovery, including mid-minute invalidation.
- [ ] Test shared outage: no fabricated or recovered candles.
- [ ] Compare coverage across both databases without changing SELL signal inputs.
- [ ] Evaluate the three October 14 slots hypothetically only; do not claim actual historical recovery.
- [ ] Document measured reconnect delays, missing-minute rates and coverage limitations.

## Phase D — Controlled Oracle deployment
- [ ] Seek explicit approval for enabling the independent always-on service.
- [ ] Install isolated backup code and SQLite path; no new paid Oracle resources.
- [ ] Add restricted systemd service, automatic restart and conservative backoff.
- [ ] Add health checks, disk retention/limits, log redaction and optional alerts.
- [ ] Verify both primary services remain healthy before and after deployment.
- [ ] Observe genuine continuous M1 collection over a monitored period.
- [ ] Record deployed code SHA, service name, DB path, rollback procedure and validation results.
- [ ] Only mark BACKUP LIVE when service active AND fresh genuine validated candles confirmed.

## Current gate
STOP before enabling a continuous service: Phase A verified; Phase B bounded isolated SQLite proof verified (131 ticks, 1 M1, 0 rejected, run 38708290021). Persistent independent service, long-running continuity/reconnection testing and explicit deployment approval remain pending.

## Working procedure for every future step
1. Read this checklist before changes.
2. Work only on research branch and isolated Oracle runner/workspace.
3. Implement one bounded step; add/execute tests and inspect logs.
4. Mark completed only with actual evidence (run link, commit, observed Oracle output).
5. Preserve all safeguards and report blockers honestly.
6. Never infer that green offline CI means live collection is active.
