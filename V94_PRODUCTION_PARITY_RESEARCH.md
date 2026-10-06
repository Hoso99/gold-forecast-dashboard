# V9.4 Production-Parity Historical Validation

Research only. Live V9.4 is unchanged.

This replay reproduces the uploaded live V9.4 candle-power SELL gate and the
9-check CONFIRMED quality gate using historical completed M15 OHLC data, with
footprint=None as in the live watcher.

It then compares the exact production SELL/CONFIRMED population with the
research Context Score >=2 layer (S/R + completed-H4 + 2-of-3 M15 timing).

Historical Biquote upcoming-event risk is NOT reconstructed and is excluded
rather than fabricated.

Outputs:
- candle_dynamics_production_parity_summary_v94.csv
- candle_dynamics_production_parity_detail_v94.csv
