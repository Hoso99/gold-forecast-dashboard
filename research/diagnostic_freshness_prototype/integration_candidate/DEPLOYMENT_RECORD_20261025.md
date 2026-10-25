# V9.5 Freshness Integration Deployment Record

Date: 2026-10-25
Scope: V9.5 PAPER research monitor only.

## Source and reproducibility

The freshness candidate is maintained separately from the live monitor.
The deployed monitor was reproduced byte-for-byte from the candidate after
exactly two import rewrites:

- journal_freshness_adapter -> v95_journal_freshness_adapter
- freshness_evidence -> v95_freshness_evidence

Installed monitor SHA-256:
fc57f68f7b3e47cd800736f6ec06483b71b5ff42ad29967e45973658348c4a16

Pre-deployment monitor SHA-256:
40ed132f52569ea108febd686c38ccf782be349efe16b31f5deed7809721af2a

## Verification completed

- Candidate syntax and imports checked.
- Isolated freshness journal smoke test passed.
- Four freshness components reported RECALCULATED in the isolated test.
- Six targeted protective regression tests passed.
- Seven freshness/import tests passed.
- Existing monitor regression suite: 25 tests passed.
- Both V9.5 production services reported active after deployment.

## Boundaries

- V9.4 LIVE was not modified.
- No broker execution was enabled.
- F0.50 testing remains separate.
- A genuine market-open runtime cycle still needs verification.
- This record documents the checks performed; it does not claim
  validation of a real market-open cycle.
