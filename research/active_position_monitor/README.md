# Stage 1: XAU/USD research-only cloud streaming monitor

This is a continuously running **worker**, not a GitHub Actions schedule. It uses Twelve Data WebSocket ticks and writes 10-second pressure snapshots to service logs. Price updates arrive only when the provider publishes them; no fixed 1–2 second feed is guaranteed. No trading, no Telegram, and no position integration.

## Deploy

Deploy this directory as a Docker **background worker** on an always-on cloud VM/container service with restart policy `unless-stopped` or equivalent. Build: `docker build -t v94-stage1 .`; run: `docker run -d --restart unless-stopped --name v94-stage1 -e TWELVE_DATA_API_KEY=YOUR_KEY v94-stage1` (prefer cloud secret injection, not a literal command in shell history). Set `TWELVE_DATA_API_KEY` as a secret. Inspect `docker logs -f v94-stage1`. Use one instance only to avoid redundant subscriptions.

## Data limits and caveats

- Requires Twelve Data WebSocket **XAU/USD entitlement**; Basic/trial may not permit this symbol. A successful REST M1 key does not imply WebSocket permission. No API key or cloud deployment is configured by this PR.
- Tick pressure is computed from the signed changes of the most recent 100 provider prices, not actual exchange order flow or volume. Neutral flat prices return 50/50. M1 REST snapshot script remains available for manual testing only.
- Each price event updates state immediately. Log snapshot interval defaults to 10 seconds (`SNAPSHOT_SECONDS`). If there are no ticks, no fresh snapshot is emitted. Reconnects on stale feeds after receiving prices, with capped backoff.
- Snapshots currently exist only in container logs; configure your cloud logging retention before relying on historical data.
- `position_state=UNKNOWN_NOT_CONNECTED` and `action=OBSERVE_ONLY`: no active trade can be identified and no CLOSE SELL alert is sent.
- Gold spot markets close during weekends/holidays; the worker may reconnect during closures. Monitor connection health and cloud spend.

The live V9.4 files, trading signals, Telegram alerts and SL/TP are untouched.
