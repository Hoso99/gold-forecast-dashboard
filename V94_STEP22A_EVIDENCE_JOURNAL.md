# V9.4 Step 22A — Automated Evidence Journal

This step adds `evidence_journal_v94.json` without changing the live SELL decision, threshold, SL, TP, or Telegram gating.

Every completed-M15 evaluation is recorded, including SELL, WAIT, and event-blocked decisions. Re-running the same completed M15 candle replaces that evaluation rather than duplicating it.

Recorded evidence includes 10-candle BUY/SELL power, pressure acceleration, all nine SELL-quality checks and failed checks, recent body/close/wick/ATR/power diagnostics, Biquote market/event context, 48-M15 support/resistance and location diagnostics, and structure/SL/TP fields when an actionable SELL exists.

`trade_journal_v94.json` remains the outcome journal for actual active alerts. `evidence_journal_v94.json` is the complete decision-evidence journal used for later V9.4 analysis and V9.5 comparison.
