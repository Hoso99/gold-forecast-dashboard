# V9.5 adaptive exit: matched historical audit (2026-10-18)

Source: GitHub Actions run 39128223687, artifact `v95-adaptive-exit-challenger-39128223687` (145 fixed SELL entry timestamps). This is a research-only M1-close technical approximation, **not** a full PAPER replay. Historical news gate, manual partials, portfolio occupancy, and realized daily loss-lock parity are unverified.

## Completed-only comparison (all years)

| Arm | Entries | Completed | Censored | Mean net R | Sum net R | Win rate | Profit factor |
|---|---:|---:|---:|---:|---:|---:|---:|
| Original | 145 | 138 | 7 | -0.045033 | -6.214502 | 30.43% | 0.856241 |
| Strict | 145 | 127 | 18 | -0.002342 | -0.297397 | 30.71% | 0.994312 |
| Adaptive | 145 | 135 | 10 | -0.050936 | -6.876412 | 34.81% | 0.869775 |

These totals have **different denominators**. They must not be interpreted as matched-strategy profitability.

## Development window (2020–2025)

- Original: 105 completed of 112, sum -5.213126R.
- Strict: 94 completed of 112, sum +2.248903R; **18 unresolved**.
- Adaptive: 102 completed of 112, sum -5.963213R; **10 unresolved**.
- Strict matched to original: 94 jointly completed; sum delta **+5.875214R**. Eleven trades originally completed but were censored by strict; original net R on those eleven was **-1.586816R**.
- Adaptive matched to original: 102 jointly completed; sum delta **-1.447482R**. Three trades originally completed but were censored by adaptive; original net R on those three was **-0.697396R**.

## 2026 diagnostic (previously viewed; not clean untouched holdout)

- Original 33 completed, -1.001375R.
- Strict 33 completed, -2.546300R.
- Adaptive 33 completed, -0.913200R.

## Unresolved trade classifications

- Strict: 18 `CENSORED_GAP`, including 7 originally censored and **11 originally completed** (7 original momentum exits, 4 original structure exits).
- Adaptive: 6 `CENSORED_GAP` and 4 `CENSORED_END`. Four originally censored by gap were reclassified to `CENSORED_END` for three cases; one originally completed momentum exit became `CENSORED_END`. This discrepancy needs timestamp/session-boundary inspection, not a guessed fill.

## Required next experiment before optimization

1. Audit original vs challenger candle availability and each censored episode, including last available minute, missing minute, session boundary, and whether the 240-minute timeout was reachable.
2. Enforce identical timestamp coverage, bar-close semantics, cost assumptions, stop-first precedence and terminal outcome policy. Never replace a gap with a fabricated exit.
3. Report paired-completed deltas **and** unresolved-case sensitivity ranges; also count trades where either arm lacks an outcome.
4. Confirm whether adaptive M15/H1 aggregates use only fully closed candles. Audit lookahead and entry-bar treatment.
5. Keep parameter choices fixed using development data. 2026 has already been inspected; designate a genuinely later unseen sample for final validation.
6. Only after the audit, test one targeted challenger against frozen original and evaluate drawdown, per-year consistency, slippage sensitivity, and cost robustness.

**Decision:** No evidence yet justifies promoting strict or adaptive exits to V9.5 PAPER. Do not modify V9.4 LIVE, V9.5 PAPER, C2 Raw, collectors, Telegram or historical source databases.
