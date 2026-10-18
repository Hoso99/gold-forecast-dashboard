"""Isolated chronological H4 confirmation experiment for V9.5 M1 proxy.
Uses only fully completed H4 candles at each signal, with a freshness guard.
Never modifies historical SQLite databases, live or paper deployment.
"""
import importlib.util
import json
from pathlib import Path

SRC=Path('research/historical/v95_m1_paper_approx.py')
FROZEN=Path('source-replay/v95-m1-paper-approx-results.json')
spec=importlib.util.spec_from_file_location('frozen_v95_m1',SRC)
model=importlib.util.module_from_spec(spec)
spec.loader.exec_module(model)
original=json.loads(FROZEN.read_text())
assert original['completed_trades']>=1000
original_signal=model.technical_signal

def h4_confirmed(m1,aggs):
    signal=original_signal(m1,aggs)
    if not signal or signal['detector']!='SWEEP' or signal['power']<75:
        return None
    bars=list(aggs[240]['bars'])
    if len(bars)<3 or not model.consecutive(bars,240,3):
        return None
    # Aggregate stores bar START time. The latest fully closed H4 bar
    # must end no more than 4h before the current signal minute.
    now=m1[-1]['t']
    latest_end=bars[-1]['t']+model.dt.timedelta(minutes=239)
    if latest_end>now or now-latest_end>model.dt.timedelta(minutes=240):
        return None
    # Bearish H4 close-to-close momentum and price below previous H4 close.
    if not (bars[-1]['c']<bars[-2]['c'] and m1[-1]['c']<bars[-2]['c']):
        return None
    return signal

def summary(trades):
    done=[t for t in trades if 'net_r' in t]
    total=0.0; peak=0.0; dd=0.0
    for t in done:
        total+=t['net_r'];peak=max(peak,total);dd=max(dd,peak-total)
    return {'entered':len(trades),'completed':len(done),'censored':len(trades)-len(done),
            'mean_net_r':round(total/len(done),5) if done else None,
            'sum_net_r':round(total,5),
            'win_rate':round(sum(t['net_r']>0 for t in done)/len(done),5) if done else None,
            'max_cumulative_r_drawdown':round(dd,5)}
arms={}
for name,signal in [('sweep75',lambda m,a: (lambda s:s if s and s['detector']=='SWEEP' and s['power']>=75 else None)(original_signal(m,a))),
                    ('sweep75_h4_bearish',h4_confirmed)]:
    model.technical_signal=signal
    model.replay()
    data=json.loads(Path('v95-m1-paper-approx-results.json').read_text())
    trades=data['trades']
    arms[name]={'overall':summary(trades),
                'years':{str(y):summary([t for t in trades if t['year']==y])
                         for y in range(2020,2027)},
                'stats':data['stats']}
    print('ARM',name,json.dumps(arms[name]['overall'],sort_keys=True))
    print('YEARLY',name,json.dumps(arms[name]['years'],sort_keys=True))
model.technical_signal=original_signal
report={'research_only':True,'source_run_id':39110369114,
        'not_full_v95_paper':True,
        'frozen_baseline_reference':{'overall':original['overall'],'per_year':original['per_year']},
        'challenger':'Sweep75 + fully completed bearish H4 close-to-close and below prior H4 close',
        'unchanged':'Original M1 approximation risk, exits, costs and gap rules',
        'known_limitations':['Historical economic news not reconstructed',
                             'H4 is a new research gate, not original live parity',
                             '2026 already examined, not pristine holdout',
                             'No next-bar executable fill or portfolio equity drawdown',
                             'Censored outcomes excluded from average R'],
        'arms':arms}
Path('v95-sweep75-h4-report.json').write_text(json.dumps(report,indent=2)+'\n')
print('H4_RESEARCH_COMPLETE')
