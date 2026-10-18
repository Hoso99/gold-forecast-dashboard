"""Read-only diagnostic of the previously completed V9.5 M1 research replay.
Fetches the known Actions artifact; no database reads, service access, or trading.
"""
import collections
import io
import json
import os
import statistics
import urllib.request
import zipfile
from pathlib import Path

# The prior workflow artifact is downloaded by actions/download-artifact into
# this job's isolated workspace; no token or network access in this script.
report=json.loads(Path('source-replay/v95-m1-paper-approx-results.json').read_text())
trades=report['trades']
completed=[x for x in trades if 'net_r' in x]
if len(completed)!=1196:raise RuntimeError('Unexpected replay artifact trade count')
def metrics(items):
    if not items:return {'count':0}
    values=[float(x['net_r']) for x in items]
    gross=[float(x['gross_r']) for x in items]
    cost=[g-n for g,n in zip(gross,values)]
    return {
      'count':len(items),
      'mean_net_r':round(statistics.mean(values),5),
      'median_net_r':round(statistics.median(values),5),
      'mean_gross_r':round(statistics.mean(gross),5),
      'mean_cost_r':round(statistics.mean(cost),5),
      'positive_net_fraction':round(sum(x>0 for x in values)/len(values),5),
      'mean_win_r':round(statistics.mean([x for x in values if x>0]),5) if any(x>0 for x in values) else None,
      'mean_loss_r':round(statistics.mean([x for x in values if x<=0]),5) if any(x<=0 for x in values) else None,
    }
def groups(key):
    return {str(k):metrics([x for x in completed if x.get(key)==k])
            for k in sorted({x.get(key) for x in completed})}
def split_year():
    return {str(y):metrics([x for x in completed if x.get('year')==y])
            for y in sorted({x.get('year') for x in completed})}
def drawdown_r(items):
    running=peak=dd=0.0
    for x in sorted(items,key=lambda x:x['exit_utc']):
        running+=float(x['net_r'])
        peak=max(peak,running)
        dd=max(dd,peak-running)
    return round(dd,4)
def quantiles(vals):
    if not vals:return None
    s=sorted(vals)
    return {str(q):round(s[round((len(s)-1)*q)],5) for q in (0.1,0.25,0.5,0.75,0.9)}
out={
 'source_run_id':39110369114,
 'source_artifact_id':ARTIFACT_ID,
 'source_model':'V9.5 technical M1 PAPER approximation (NOT full PAPER)',
 'all':metrics(completed),
 'by_exit':groups('outcome'),
 'by_detector':groups('detector'),
 'by_year':split_year(),
 'train_2020_2025':metrics([x for x in completed if x['year']<2026]),
 'seen_2026_diagnostic':metrics([x for x in completed if x['year']==2026]),
 'censored_by_gap':sum(x.get('outcome')=='CENSORED_GAP' for x in trades),
 'max_drawdown_sum_R_not_equity':drawdown_r(completed),
 'net_R_quantiles':quantiles([float(x['net_r']) for x in completed]),
 'stop_distance_price_quantiles':quantiles([float(x['risk']) for x in completed]),
 'scope':'Descriptive diagnostics only; not a counterfactual paired exit comparison',
 'known_limitations':['No historical news calendar','No partial acknowledgements',
    'Paper M1 close not executable fill','Historical gaps censored',
    'No original PAPER full parity','2026 already examined'],
}
Path('v95-exit-diagnostic-report.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out,indent=2))
print('READ_ONLY_EXIT_DIAGNOSTIC_COMPLETE')
