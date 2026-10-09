"""Research-only, reproducible SELL opportunity ledger. No alerts or orders."""
from pathlib import Path
import pandas as pd

root = Path(__file__).resolve().parent / 'comparison_output'
decisions = pd.read_csv(root / 'decisions.csv', keep_default_na=False)
trades = pd.read_csv(root / 'trades.csv', keep_default_na=False)
options = ('original_m15', 'atr_cap_m15', 'pullback_m15', 'm5_structure')
required = {'time_utc', 'base_candidate', 'quality_checks', 'm5_body_ratio', 'entry',
            'm15_atr', 'structural_target', 'failed_checks'}
for option in options:
    required.update((option, option+'_reason', option+'_entry', option+'_stop',
                     option+'_target', option+'_rr', option+'_fill_time_utc'))
missing = required - set(decisions.columns)
if missing:
    raise SystemExit(f'Missing decision columns: {sorted(missing)}')
if decisions['time_utc'].duplicated().any():
    raise SystemExit('Duplicate signal timestamps; refusing ambiguous ledger')
if len(trades) and trades[['option','signal_time_utc']].duplicated().any():
    raise SystemExit('Duplicate trade results per option and signal')
trade_index = {(str(r.option), str(r.signal_time_utc)): r
               for r in trades.itertuples(index=False)}
ledger = []
for r in decisions.itertuples(index=False):
    if str(r.base_candidate).lower() != 'true':
        continue
    for option in options:
        state = getattr(r, option)
        reason = getattr(r, option+'_reason')
        outcome = trade_index.get((option, str(r.time_utc)))
        # Eligible is a setup classification, not a completed trade.
        status = ('COMPLETED' if outcome is not None else
                  'ELIGIBLE_NO_COMPLETED_OUTCOME' if state == 'SELL' else
                  'REJECTED')
        ledger.append({
            'opportunity_id':str(r.time_utc)+'|'+option,
            'signal_time_utc':r.time_utc,
            'direction':'SELL', 'strategy':option,
            'status':status, 'rejection_reason':reason if status == 'REJECTED' else '',
            'quality_checks':r.quality_checks, 'm5_body_ratio':r.m5_body_ratio,
            'm15_atr':r.m15_atr,
            'entry':getattr(r,option+'_entry'),
            'stop_loss':getattr(r,option+'_stop'),
            'take_profit':getattr(r,option+'_target'),
            'reward_risk':getattr(r,option+'_rr'),
            'fill_time_utc':getattr(r,option+'_fill_time_utc'),
            'exit_time_utc':outcome.exit_time_utc if outcome is not None else '',
            'outcome':outcome.outcome if outcome is not None else '',
            'net_r':outcome.net_r if outcome is not None else ''
        })
columns = ['opportunity_id','signal_time_utc','direction','strategy','status',
           'rejection_reason','quality_checks','m5_body_ratio','m15_atr',
           'entry','stop_loss','take_profit','reward_risk','fill_time_utc',
           'exit_time_utc','outcome','net_r']
result = pd.DataFrame(ledger,columns=columns)
result.to_csv(root/'sell_opportunities.csv',index=False)
print(f'SELL opportunity tracker: {len(result)} strategy evaluations across '
      f'{result.signal_time_utc.nunique() if len(result) else 0} distinct SELL signals')
print(result.groupby(['strategy','status']).size().to_string() if len(result) else 'No qualified SELL signals')
print('Full collector history regenerated each run; IDs stable by signal time and strategy.')
print('No real-time alert, live trading decision, or broker execution.')
