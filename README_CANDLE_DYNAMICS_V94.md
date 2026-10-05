# V9.4 Persistence Optimization Research

Upload both files to the repository root, replacing the existing files when prompted.

This version keeps all previous candle-dynamics research and adds a separate persistence-focused out-of-sample study. It tests SEG3 and SEG2+SEG3 bearish persistence across several strength thresholds, ranks candidates on the discovery period, and evaluates the top rules on the untouched validation period.

It does **not** modify the live V9.4 entry watcher or live 10-candle SELL logic.

New CSV outputs:
- `candle_dynamics_persistence_search_v94.csv`
- `candle_dynamics_persistence_validation_v94.csv`
