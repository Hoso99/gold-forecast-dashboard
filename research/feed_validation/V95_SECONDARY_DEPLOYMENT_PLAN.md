# V9.5 independent backup: pre-deployment gates and rollback

Status: PREPARED ONLY. Do not run deployment until explicit user approval.

## Isolation
- Existing Oracle Always Free instance only; no additional resources.
- Dedicated non-sudo user: v95research.
- Source directory: /home/v95research/v95-secondary-research
- Separate writable SQLite directory: /home/v95research/v95-backup-research
- Database: biquote_independent_m1.sqlite3; never point to primary biquote_m1.sqlite3.
- Service name: v95-secondary-research.service. Never restart/stop v95-biquote-collector.service or v95-research-monitor.service.
- No changes to V9.4, V9.5 SELL logic, risk, Telegram, or primary database.
- All code remains research-only until explicit authorization for integration (which is NOT part of this deployment).

## Required before enabling
1. Run offline unit tests, code audit, and syntax checks on research branch.
2. Confirm correct websocket-client library installed in an isolated venv; no shared Python packages modified.
3. Confirm database schema, disk space, restrictive file ownership, journald retention and backup storage capacity.
4. Confirm primary services active and fresh before deployment.
5. Obtain explicit user approval to install and start this service.
6. Deploy from pinned reviewed research commit, record SHA and timestamps.
7. Confirm new service active, independently received valid ticks, genuine M1 rows fresh and consecutive where eligible.
8. Confirm primary services remain active and fresh afterward.
9. Monitor for at least 24 hours, including reconnects, gap rate, disk usage, and SQLite consistency. Do not claim guaranteed zero gaps.
10. Do not merge backup DB into live trading inputs without a separate reviewed and explicitly approved change.

## Rollback (after approved installation only)
- Stop and disable ONLY v95-secondary-research.service.
- Preserve independent research SQLite for audit; do not delete primary files.
- Remove ONLY the secondary service unit and secondary isolated source directory if explicitly requested.
- Verify primary collector and monitor are healthy.
- Record rollback timestamp and reason.

## Safety caveat
This preparation does not authorize production deployment. A service being installed/active alone does not prove backup reliability; genuine validated M1 rows and monitoring are mandatory.
