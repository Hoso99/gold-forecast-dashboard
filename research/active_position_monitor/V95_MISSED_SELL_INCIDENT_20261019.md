# V9.5 PAPER missed SELL incident triage — 2026-10-19

## Observed, not assumed
User screenshot shows a sharp downward gold move, a visible quote near 4153.10, a lower wick near 4143 and elevated volume. Screenshot does not establish the market-data provider, timeframe, exact timestamp, signal history, or whether a valid SELL was rejected. Do not label it a proven missed eligible trade.

## Critical split
1. Data failure: stale M1 cache, missing/invalid session candles, collector cadence, or stale-read exception before evaluation.
2. Decision failure: fresh data, but SELL power, trend, location, confirmation, macro, cost, or risk gates returned WAIT.
3. Notification failure: signal existed but alert was not sent or deduplicated.

## Evidence needed (read-only)
- UTC incident window and screenshot chart timeframe/timezone.
- Monitor journal around incident: WAIT_DATA, SELL, WAIT, ENTRY, rejection reason, alert queue, and exception count; redact credentials.
- Collector journal: request/refresh timestamps, errors, latency, latest complete candle minute.
- SQLite M1 cache: latest complete minute, age at monitor evaluations, missing minute gaps; do not assume retrospective backfills prove real-time availability.
- PAPER state: whether a SELL was already open; if so prioritize stop/target evaluation latency.
- Signal candidate chronology with each gate reason and price/SL/TP at decision time.

## Safety
Do not increase 180-second freshness tolerance, skip SL/TP, bypass SELL filters, chase an entry using a screenshot quote, or touch V9.4 LIVE. PR #8 is draft, not deployed; its retry helper alone cannot explain the incident. No broker execution.

## Immediate action
Collect timestamped read-only diagnostics first, then fix the proven bottleneck and test in isolated V9.5 PAPER staging. If collector is phase-lagged, evaluate safe scheduling adjustments; if signal gates rejected the move, study a separate research challenger without changing LIVE.
