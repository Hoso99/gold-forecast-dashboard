"""Research-only exit-policy sensitivity study on the frozen V9.5 M1 approximation.
No live imports, historical DB writes, production or paper state changes.
"""
import importlib.util
import json
from pathlib import Path

SRC=Path('research/historical/v95_m1_paper_approx.py')
ORIGINAL=SRC.read_text()
OUT=Path('v95-exit-confirmation-research.json')
NEEDLE="""if m15[-1]['c']>max(x['h'] for x in m15[-4:-1]):"""
MOMENTUM="""elif (sum(m5[-i]['c']>m5[-i-1]['c'] for i in range(1,5))>=3
                              and m5[-1]['c']>m5[-2]['c'] and h1[-1]['c']>h1[-2]['c']):"""
assert ORIGINAL.count(NEEDLE)==1 and ORIGINAL.count(MOMENTUM)==1, 'Frozen code mismatch'
variants={
 'original':(NEEDLE,MOMENTUM),
 'confirmed_early_exit':(
  """if (m15[-1]['c']>max(x['h'] for x in m15[-4:-1])
                                +0.25*atr15(aggs[15]['bars'])
                                and m5[-1]['c']>m5[-2]['c']):""",
  """elif (sum(m5[-i]['c']>m5[-i-1]['c'] for i in range(1,5))>=4
                              and m5[-1]['c']>m5[-2]['c']
                              and h1[-1]['c']>h1[-2]['c']
                              and c>active['entry']+0.25*atr15(aggs[15]['bars'])):"""),
 'protective_only':('if False:', 'elif False:'),
}
def summarize(trades):
    done=[t for t in trades if 'net_r' in t]
    s=0.;peak=0.;dd=0.
    for t in done:
        s+=t['net_r'];peak=max(peak,s);dd=max(dd,peak-s)
    return {'entered':len(trades),'completed':len(done),
            'censored':len(trades)-len(done),
            'mean_net_r':round(s/len(done),5) if done else None,
            'sum_net_r':round(s,5),
            'win_rate':round(sum(t['net_r']>0 for t in done)/len(done),5) if done else None,
            'max_cumulative_r_drawdown':round(dd,5)}
results={}
for name,(structure,momentum) in variants.items():
    src=ORIGINAL.replace(NEEDLE,structure).replace(MOMENTUM,momentum)
    spec=importlib.util.spec_from_loader('v95_exit_'+name,loader=None)
    mod=importlib.util.module_from_spec(spec)
    exec(compile(src,str(SRC),'exec'),mod.__dict__)
    mod.technical_signal_original=mod.technical_signal
    def sweep75(m1,aggs,_fn=mod.technical_signal_original):
        s=_fn(m1,aggs)
        return s if s and s['detector']=='SWEEP' and s['power']>=75 else None
    mod.technical_signal=sweep75
    mod.replay()
    report=json.loads(Path('v95-m1-paper-approx-results.json').read_text())
    trades=report['trades']
    results[name]={
      'overall':summarize(trades),
      'years':{str(y):summarize([t for t in trades if t['year']==y]) for y in range(2020,2027)},
      'outcomes':{k:v for k,v in report['stats'].items() if k in ('sl','tp','early_exit_momentum','early_exit_structure','censored_gap','censored_end')},
      'entry_timestamps':[t['entry_utc'] for t in trades]
    }
    print('ARM',name,json.dumps(results[name]['overall'],sort_keys=True))
    print('OUTCOMES',name,json.dumps(results[name]['outcomes'],sort_keys=True))
    print('YEARS',name,json.dumps(results[name]['years'],sort_keys=True))
base=set(results['original']['entry_timestamps'])
for name in ('confirmed_early_exit','protective_only'):
    other=set(results[name]['entry_timestamps'])
    results[name]['entry_overlap_with_original']={
      'same_entries':len(base&other),'original_only':len(base-other),
      'challenger_only':len(other-base)}
    print('ENTRY_OVERLAP',name,json.dumps(results[name]['entry_overlap_with_original']))
for v in results.values():del v['entry_timestamps']
out={'research_only':True,'not_full_v95_paper':True,'method':'Independent chronological exit-policy replays; not paired trades',
     'entry':'Sweep75, frozen M1-close paper proxy',
     'exit_variants':{'original':'Frozen original early exits',
       'confirmed_early_exit':'Structure break > 0.25 ATR with M5 uptick; momentum stronger and adverse >0.25 ATR',
       'protective_only':'Only mandatory stop-loss and 2R take-profit; gap censoring retained'},
     'limitations':['Changing exits changes subsequent entry availability',
       'No verified historical news calendar','No manual partial acknowledgement',
       '2026 previously examined, not untouched out-of-sample',
       'No guaranteed executable M1 close fills','Censored trades excluded from mean R'],
     'results':results}
OUT.write_text(json.dumps(out,indent=2)+'\n')
print('EXIT_POLICY_RESEARCH_COMPLETE')
