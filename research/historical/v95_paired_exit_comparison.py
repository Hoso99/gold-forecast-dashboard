"""Paired exit counterfactual on frozen V9.5 M1 technical-paper entry cohort.
NOT a portfolio backtest. No entries are generated or changed here.
Original exits vs stop/2R/240-minute hold from identical recorded entry.
Historical gap -> censored; no fabricated candles; stop-first on same-bar ambiguity.
"""
import collections
import datetime as dt
import json
import sqlite3
from pathlib import Path
from urllib.parse import quote

ROOT=Path('/home/ubuntu/v95-historical-research')
NAMES=['twelve_xauusd_m1.sqlite3','twelve_xauusd_m1_2021_2022.sqlite3',
       'twelve_xauusd_m1_2022_2023.sqlite3','twelve_xauusd_m1_2023_2024.sqlite3',
       'twelve_xauusd_m1_2024_2025.sqlite3','twelve_xauusd_m1_2025_2026.sqlite3',
       'twelve_xauusd_m1_2026_partial.sqlite3']
COSTS=[0,2,5,10]
MAX_HOLD=240
ONE=dt.timedelta(minutes=1)

def metrics(rows,mode,cost):
    values=[]
    for r in rows:
        x=r[mode]
        if x['outcome'].startswith('CENSORED'):continue
        values.append(x['gross_r']-r['entry']*(cost/10000)/r['risk'])
    if not values:return {'n':0,'mean_net_r':None}
    return {'n':len(values),'mean_net_r':round(sum(values)/len(values),5),
            'positive_fraction':round(sum(v>0 for v in values)/len(values),5),
            'sum_net_r':round(sum(values),4)}

def run():
    src=json.loads(Path('source-replay/v95-m1-paper-approx-results.json').read_text())
    original=src['trades']
    # Research replay is a fixed cohort, not an independently tradable portfolio.
    rows=[x for x in original if 'entry_utc' in x and 'risk' in x]
    rows.sort(key=lambda x:x['entry_utc'])
    if len(rows)!=1296:raise RuntimeError(f'Unexpected entry cohort size {len(rows)}')
    pairs=[]
    censored=collections.Counter()
    conns=[]
    try:
        for name in NAMES:
            p=ROOT/name
            uri='file:'+quote(str(p),safe='/')+'?mode=ro&immutable=1'
            con=sqlite3.connect(uri,uri=True)
            con.execute('PRAGMA query_only=ON')
            start,end=con.execute('SELECT MIN(minute_utc),MAX(minute_utc) FROM candles').fetchone()
            conns.append((start,end,con))
        for trade in rows:
            entry_t=dt.datetime.fromisoformat(trade['entry_utc']).replace(tzinfo=None)
            # Source timestamps are naive ISO UTC, preserving source lexical format.
            start=(entry_t+ONE).isoformat()
            end=(entry_t+dt.timedelta(minutes=MAX_HOLD)).isoformat()
            entry=float(trade['entry']);risk=float(trade['risk'])
            stop=float(trade['stop']);target=float(trade['target'])
            path=[]
            for lo,hi,conn in conns:
                if hi<start or lo>end:continue
                path.extend(conn.execute(
                    'SELECT minute_utc,open,high,low,close FROM candles WHERE minute_utc>=? AND minute_utc<=? ORDER BY minute_utc',
                    (start,end)).fetchall())
            path.sort(key=lambda x:x[0])
            # Candle timestamps are UTC ISO strings; SQLite stores naive UTC.
            # Normalize both sides to minute-resolution datetimes before comparing.
            outcome='CENSORED_END';gross=None;prev=entry_t
            for index,(stamp,o,h,l,c) in enumerate(path):
                t=dt.datetime.fromisoformat(stamp).replace(tzinfo=None)
                if t-prev!=ONE:
                    outcome='CENSORED_GAP';break
                prev=t
                if h>=stop:
                    outcome='SL';fill=max(stop,o)
                elif l<=target:
                    outcome='TP';fill=target
                elif (t-entry_t)>=dt.timedelta(minutes=MAX_HOLD):
                    outcome='TIMEOUT';fill=c
                else:continue
                gross=(entry-fill)/risk
                break
            if gross is None:
                censored[outcome]+=1
            recorded={'outcome':trade['outcome'],
                      'gross_r':float(trade['gross_r']) if 'gross_r' in trade else None}
            alt={'outcome':outcome,'gross_r':gross}
            pairs.append({'entry_utc':trade['entry_utc'],'year':trade['year'],
                          'detector':trade['detector'],'entry':entry,'risk':risk,
                          'recorded':recorded,'hold':alt})
    finally:
        for _,_,con in conns:con.close()
    # Fail loudly if the research produces no comparable outcomes.
    # A successful job with zero pairs is not a valid experiment.
    comparable=[r for r in pairs if r['recorded']['gross_r'] is not None and r['hold']['gross_r'] is not None]
    if not comparable:
        raise RuntimeError('ZERO_COMPARABLE_PAIRS: inspect timestamp format and OHLC coverage before analysis')
    def summary(items):
        v=[r['hold']['gross_r']-r['recorded']['gross_r'] for r in items]
        return {'paired_n':len(items),
                'mean_gross_delta_hold_minus_recorded_r':round(sum(v)/len(v),5) if v else None,
                'hold_better_fraction':round(sum(x>0 for x in v)/len(v),5) if v else None,
                'same_outcome_fraction':round(sum(r['hold']['outcome']==r['recorded']['outcome'] for r in items)/len(items),5) if items else None,
                'recorded':{str(bps):metrics(items,'recorded',bps) for bps in COSTS},
                'hold':{str(bps):metrics(items,'hold',bps) for bps in COSTS}}
    report={
      'source_run_id':39110369114,
      'method':'fixed-cohort paired V9.5 early-exit versus SL/TP/240min',
      'not_portfolio_replay':True,
      'not_full_v95_parity':True,
      'not_live_approved':True,
      'price_execution':'M1 entry close paper reference; future M1 OHLC, stop-first',
      'gap_rule':'Both arms must have completed observed outcome for pair',
      'same_entries':len(pairs),
      'comparable_pairs':len(comparable),
      'excluded_noncomparable':len(pairs)-len(comparable),
      'hold_censor_reasons':dict(censored),
      'overall':summary(comparable),
      'by_detector':{d:summary([r for r in comparable if r['detector']==d]) for d in ('SWEEP','SUPPORT_BREAK')},
      'by_recorded_exit':{e:summary([r for r in comparable if r['recorded']['outcome']==e])
                           for e in sorted({r['recorded']['outcome'] for r in comparable})},
      'by_year':{str(y):summary([r for r in comparable if r['year']==y])
                 for y in sorted({r['year'] for r in comparable})},
      'limitations':['No economic calendar or partial-exit parity',
                     'Fixed entries ignore opportunity cost and concurrent positions',
                     '240-minute alternative is a research assumption, not the original V9.5',
                     'Censored trades excluded, potentially selection-biased',
                     '2026 is previously seen and not an untouched holdout']}
    Path('v95-paired-exits-report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    print('READ_ONLY_PAIRED_EXIT_COMPARISON_COMPLETE')

if __name__=='__main__':run()
