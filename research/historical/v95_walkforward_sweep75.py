"""Research-only chronological comparison using frozen V9.5 M1 approximation.
Replays both arms independently over the same immutable SQLite candles.
No production imports, no DB writes, no live deployment.
"""
import importlib.util
import json
from pathlib import Path

SOURCE=Path('research/historical/v95_m1_paper_approx.py')
OUT=Path('v95-walkforward-sweep75-report.json')
ORIGINAL=Path('source-replay/v95-m1-paper-approx-results.json')
spec=importlib.util.spec_from_file_location('v95_frozen_m1_replay',SOURCE)
model=importlib.util.module_from_spec(spec)
spec.loader.exec_module(model)
frozen=json.loads(ORIGINAL.read_text())
assert frozen['completed_trades']>=1000, 'Original reference unexpectedly small'
results={}
for arm in ('baseline','sweep75'):
    original_signal=model.technical_signal
    if arm=='sweep75':
        def challenger(m1,aggs,_orig=original_signal):
            signal=_orig(m1,aggs)
            return signal if signal and signal['detector']=='SWEEP' and signal['power']>=75 else None
        model.technical_signal=challenger
    else:
        model.technical_signal=original_signal
    model.replay()
    current=json.loads(Path('v95-m1-paper-approx-results.json').read_text())
    if arm=='baseline':
        # Require parity with original frozen research before trusting comparison.
        for key in ('completed_trades','overall','per_year','per_detector','stats'):
            assert current[key]==frozen[key], f'BASELINE_PARITY_FAILURE: {key}'
    results[arm]={k:v for k,v in current.items() if k!='trades'}
    trades=current['trades']
    completed=[t for t in trades if 'net_r' in t]
    total=0.0;peak=0.0;max_dd=0.0
    for t in completed:
        total+=t['net_r']
        peak=max(peak,total)
        max_dd=max(max_dd,peak-total)
    results[arm]['cumulative_r_max_drawdown']=round(max_dd,5)
    results[arm]['censored_trades']=len(trades)-len(completed)
    model.technical_signal=original_signal
report={'research_only':True,'full_live_parity':False,
        'source_run_id':39110369114,
        'baseline_parity_verified':True,
        'challenger':'Liquidity sweep and M1 10-candle SELL power >=75; other frozen replay logic unchanged',
        'execution':'Existing M1 signal-close paper assumption; no executable fills guaranteed',
        'news_gate':'Not tested; verified historical calendar absent',
        'h4':'Original M1 approximation does not require H4 gate',
        'year_2026':'Previously examined, not untouched out-of-sample',
        'baseline':results['baseline'],'challenger':results['sweep75']}
OUT.write_text(json.dumps(report,indent=2)+'\n')
for arm in ('baseline','sweep75'):
    x=results[arm]
    print('ARM',arm,'entered',x['stats'].get('entered'),'completed',x['completed_trades'],
          'net_R',x['overall']['mean_net_r'],'win_rate',x['overall']['win_rate'],
          'max_dd_R',x['cumulative_r_max_drawdown'],'censored',x['censored_trades'])
    print('YEARS',arm,json.dumps(x['per_year'],sort_keys=True))
print('BASELINE_PARITY_VERIFIED')
print('REPORT_WRITTEN',OUT)
