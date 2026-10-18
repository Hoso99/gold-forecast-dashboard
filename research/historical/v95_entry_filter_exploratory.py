"""Frozen V9.5 entry-filter exploratory audit. No price database or model changes.
Selection only on recorded entry-time features; 2026 diagnostic, NOT pristine holdout.
"""
import collections,json,math
from pathlib import Path

src=json.loads(Path('source-replay/v95-m1-paper-approx-results.json').read_text())
trades=src['trades']
assert len(trades)==1296
costs=(0,2,5,10)
train=[t for t in trades if t['year']<=2025]
seen=[t for t in trades if t['year']==2026]
def report(items):
    done=[t for t in items if 'gross_r' in t]
    def vals(bps):
        return [t['gross_r']-t['entry']*(bps/10000)/t['risk'] for t in done]
    out={'entries':len(items),'completed':len(done),
         'censored':len(items)-len(done),
         'coverage':round(len(items)/len(trades),5)}
    for b in costs:
        v=vals(b)
        out[f'net_{b}bps']={'mean_r':round(sum(v)/len(v),5) if v else None,
                           'positive_fraction':round(sum(x>0 for x in v)/len(v),5) if v else None}
    return out
# Fixed, explicitly exploratory thresholds, no optimization against 2026.
def specs():
    yield 'BASELINE',lambda t:True
    for det in ('SWEEP','SUPPORT_BREAK'):
        yield det,lambda t,d=det:t['detector']==d
        for p in (60,65,70,75):
            yield f'{det}_power_ge_{p}',lambda t,d=det,p=p:t['detector']==d and t['power']>=p
    for p in (65,70,75):
        yield f'ALL_power_ge_{p}',lambda t,p=p:t['power']>=p
    for bound in (1.5,2.0,3.0):
        yield f'ALL_stop_ATR_le_{bound}',lambda t,b=bound:t['risk']/t['atr15']<=b
        yield f'SWEEP_stop_ATR_le_{bound}',lambda t,b=bound:t['detector']=='SWEEP' and t['risk']/t['atr15']<=b
    for bound in (1.5,2.0):
        yield f'ALL_stop_ATR_ge_{bound}',lambda t,b=bound:t['risk']/t['atr15']>=b

rows=[]
for name,fn in specs():
    selected=[t for t in trades if fn(t)]
    rows.append({'filter':name,'all':report(selected),
                 'train_2020_2025':report([t for t in train if fn(t)]),
                 'seen_2026_diagnostic':report([t for t in seen if fn(t)]),
                 'train_by_year':{str(y):report([t for t in train if t['year']==y and fn(t)])
                                  for y in range(2020,2026)}})
out={'source_run_id':39110369114,'exploratory_only':True,
     'NOT_FULL_V95_PAPER_REPLAY':True,'not_deployable':True,
     'entry_cohort':len(trades),
     'method':'Frozen entry-cohort subgroup analysis; does not regenerate entries or account for freed capacity',
     'censoring':'Exclude censored outcomes from mean R; always report counts',
     'no_lookahead_features':['detector','power','risk/atr15'],
     'limitations':['Historical news gate absent','Original H1/H4/SR values absent',
                    'No dynamic portfolio resimulation after filtering',
                    'Selection bias from excluded censored trades',
                    '2026 previously examined; not pristine out-of-sample',
                    'M1 close paper reference; not guaranteed executable fill'],
     'candidates':rows}
Path('v95-entry-filter-exploratory.json').write_text(json.dumps(out,indent=2)+'\n')
print('ENTRY_FILTER_EXPLORATORY_SUMMARY')
for row in rows:
    x=row['train_2020_2025']
    print(row['filter'],'train_entries',x['entries'],'completed',x['completed'],
          'censored',x['censored'],'train_mean_net_5bps',x['net_5bps']['mean_r'],
          'seen_2026_mean_net_5bps',row['seen_2026_diagnostic']['net_5bps']['mean_r'])
print('REPORT_WRITTEN v95-entry-filter-exploratory.json')
