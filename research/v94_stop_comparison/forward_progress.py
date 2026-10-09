"""Research-only cumulative progress from the complete forward collector window."""
from pathlib import Path
import pandas as pd
import numpy as np

root = Path('comparison_output')
d = pd.read_csv(root / 'decisions.csv')
t = pd.read_csv(root / 'trades.csv')
if d['time_utc'].duplicated().any():
    raise SystemExit('Duplicate decision timestamps: forward accounting is unsafe')
if len(t) and t[['option','signal_time_utc']].duplicated().any():
    raise SystemExit('Duplicate option/signal trade pairs')
opts = ('original_m15','atr_cap_m15','pullback_m15','m5_structure')
rows = []
for option in opts:
    selected = t.loc[t['option'].eq(option)].copy() if len(t) else t.copy()
    n = len(selected)
    net = selected['net_r'].sum() if n else np.nan
    wins = int(selected['net_r'].gt(0).sum()) if n else 0
    equity = pd.concat([pd.Series([0.0]), selected['net_r'].cumsum().reset_index(drop=True)]) if n else pd.Series(dtype=float)
    drawdown = (equity - equity.cummax()).min() if n else np.nan
    rows.append({
        'option':option,
        'first_decision_utc':d['time_utc'].min() if len(d) else '',
        'last_decision_utc':d['time_utc'].max() if len(d) else '',
        'unique_decisions':len(d),
        'qualified_sell_setups':int(d['base_candidate'].astype(str).str.lower().eq('true').sum()),
        'eligible_setups':int(d[option].eq('SELL').sum()),
        'completed_trades':n,
        'winning_trades':wins,
        'win_rate':wins/n if n else np.nan,
        'total_net_r':net,
        'mean_net_r':selected['net_r'].mean() if n else np.nan,
        'max_drawdown_r':drawdown,
        'rejected_2r':int(d[option+'_reason'].eq('structural_target_below_2R').sum()),
        'unfilled_pullbacks':int(d[option+'_reason'].eq('pullback_not_filled').sum()),
    })
pd.DataFrame(rows).to_csv(root / 'forward_progress.csv',index=False)
print(pd.DataFrame(rows).to_string(index=False))
print('Cumulative over collector dataset only; zero trades implies unknown performance, not 0% win rate.')
