# Gold Version 9.4 — Revised Four-Module Build

This build keeps Version 9.3 files intact and adds `app_v94.py` as the Version 9.4 Streamlit entry point.

## Decision architecture
1. SELL Power — last 10 completed 15-minute candles, explicitly SELL-sensitive.
2. BUY Power — independent bullish-strength reading from the same completed-candle window.
3. Breakout / Trend — mother-candle breakout plus short-term trend confirmation.
4. Reversal / Exhaustion — separate validated 5-minute reversal detector.

The last-10-candle BUY/SELL power pair carries 70% of the combined score. SELL has a lower release threshold than BUY by design, while mixed evidence returns WAIT. High-impact event locks and shock cooldowns block release. An opposed validated 5-minute reversal also blocks release.

The four modules are distinct by purpose, but this build does not claim they are statistically independent. Correlation and signal overlap must be measured out-of-sample before any such claim is made.

## Risk
Default maximum planned risk per qualified trade: **2.00%** of paper account equity. Hard stops remain mandatory. No martingale, grid, averaging down, or recovery sizing is introduced.

## Entry point
Use `app_v94.py` for Version 9.4.

## Verification
Packaged test suite: `56 passed`.


## Existing indicator integration
EMA 8/32, RSI 14, MACD histogram momentum and ATR 14 risk indicators were already present in the model stack. The revised dashboard surfaces these existing calculations without adding duplicate indicator engines. The calculated-risk validator now accepts the configured 2.00% maximum planned risk.

## V9.4 structure-based exits
- Stop: most recent confirmed M15 swing plus configurable ATR(14) buffer; default 1.5 ATR.
- TP1: next M15 structure level; signal is not position-sized unless TP1 offers at least the configured minimum R:R (default 1.5R).
- TP2: deeper H1/D1 level derived from completed M15 history when a valid deeper level exists; otherwise it is explicitly unavailable.
- Management: selectable 50% at +1R then stop to break-even, or M15 closed-candle trailing rule.
- Wider stops reduce position size; planned account risk remains capped at 2%.
