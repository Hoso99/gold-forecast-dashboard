"""Offline, research-only V9.4 audit. Does not write entry watches or send alerts.

Input: CSV of timestamped M1 OHLC, e.g. v94_forward_m1.csv.
Timestamp denotes M1 bar OPEN. Only fully contiguous completed M5/M15 bars are used.
Baseline = M15 power SELL + 8/9 diagnostic + M5 power SELL proxy.
Candidate = baseline + M5 bearish candle body >= 0.6379.
These are research definitions, NOT an exact reproduction of the live watcher.
"""
import argparse
from pathlib import Path
import numpy as np
import pandas as pd
from candle_power_v94 import analyze_last_10_candles, diagnose_sell_quality
from structure_risk_v94 import structure_atr_plan

BODY_THRESHOLD = 0.6379

def load_m1(path):
    x = pd.read_csv(path)
    date_col = 'datetime' if 'datetime' in x else 'timestamp'
    x[date_col] = pd.to_datetime(x[date_col], utc=True, errors='coerce')
    x = x.dropna(subset=[date_col]).sort_values(date_col).drop_duplicates(date_col, keep='last')
    for col in ('open','high','low','close'):
        x[col] = pd.to_numeric(x[col], errors='coerce')
    x = x.dropna(subset=['open','high','low','close']).set_index(date_col)
    x = x[(x.high >= x[['open','close','low']].max(axis=1)) & (x.low <= x[['open','close','high']].min(axis=1))]
    return x[['open','high','low','close']]

def bars(m1, minutes):
    # label bars by the timestamp at which they become available (end-exclusive).
    # Require all expected constituent minutes; exclude partial/missing periods.
    grp = m1.resample(f'{minutes}min', label='right', closed='left')
    out = grp.agg({'open':'first','high':'max','low':'min','close':'last'})
    return out[grp['close'].count().eq(minutes)].dropna()

def m5_sell(bar):
    rng = float(bar.high-bar.low)
    body = float((bar.open-bar.close)/rng) if rng > 0 else 0.0
    # Explicit proxy: bearish M5 body and close in bottom half of candle.
    sell = bar.close < bar.open and (bar.close-bar.low)/rng <= .5 if rng > 0 else False
    return bool(sell), max(0.0, body)

def simulate(m1, start, entry, stop, target, cost_bps, max_minutes=120):
    # Enter at M15/M5 close; first next M1 bar onward. Both SL and TP hit => stop first.
    future = m1.loc[(m1.index >= start) & (m1.index < start + pd.Timedelta(minutes=max_minutes))]
    if len(future) < max_minutes: return 'UNRESOLVED', np.nan, pd.NaT
    risk = stop-entry
    if not (risk > 0 and target < entry): return 'INVALID', np.nan, pd.NaT
    cost_usd = entry * cost_bps / 10000
    for ts, b in future.iterrows():
        if b.high >= stop: return 'SL', -1 - cost_usd/risk, ts
        if b.low <= target: return 'TP', (entry-target)/risk - cost_usd/risk, ts
    return 'TIME', (entry-future.close.iloc[-1]-cost_usd)/risk, future.index[-1]

def run(input_file, output, stop_cap_atr, cost_bps, max_minutes):
    m1=load_m1(input_file)
    m15=bars(m1,15); m5=bars(m1,5)
    decisions=[]; trades=[]
    busy_until={'baseline':pd.Timestamp.min.tz_localize('UTC'), 'candidate':pd.Timestamp.min.tz_localize('UTC')}
    for ts in m15.index:
        hist=m15.loc[:ts]
        if len(hist)<35: continue
        p=analyze_last_10_candles(hist)
        q=diagnose_sell_quality(p)
        if ts not in m5.index: continue
        sell5,body=m5_sell(m5.loc[ts])
        plan=structure_atr_plan('SELL',hist,atr_multiple=1.5,min_tp1_rr=2,swing_lookback=48,cost_bps=cost_bps)
        distance=float(plan.get('risk_distance',np.nan)); atr=float(plan.get('atr',np.nan))
        stop_ratio=distance/atr if np.isfinite(distance) and np.isfinite(atr) and atr>0 else np.nan
        checks={
            'm15_sell':p.signal=='SELL',
            'quality_8_of_9':q['status']=='CONFIRMED',
            'm5_sell_proxy':sell5,
            'structure_2r':plan['status']=='ACTIVE',
            'stop_distance_cap':np.isfinite(stop_ratio) and stop_ratio <= stop_cap_atr,
        }
        base=all(checks.values())
        cand=base and body>=BODY_THRESHOLD
        row={'time_utc':ts.isoformat(),'m15_signal':p.signal,'sell_power':p.sell_power,
             'quality_checks':q['checks_passed'],'m5_sell_proxy':sell5,'m5_bear_body_ratio':body,
             'stop_atr_ratio':stop_ratio,'entry':plan.get('entry'),'stop':plan.get('stop'),
             'target':plan.get('tp1'),'rr':plan.get('tp1_rr'),
             'baseline_decision':'SELL' if base else 'WAIT',
             'candidate_decision':'SELL' if cand else 'WAIT',
             'rejection_reasons':';'.join(k for k,v in checks.items() if not v) + (';weak_m5_body' if base and not cand else '')}
        decisions.append(row)
        for strategy,allowed in [('baseline',base),('candidate',cand)]:
            if not allowed or ts < busy_until[strategy]:continue
            entry=float(plan['entry']);stop=float(plan['stop']);target=float(plan['tp1'])
            outcome,net_r,exit_time=simulate(m1,ts,entry,stop,target,cost_bps,max_minutes)
            if outcome=='UNRESOLVED':continue
            trades.append({'strategy':strategy,'entry_time_utc':ts.isoformat(),'exit_time_utc':exit_time.isoformat(),
                           'entry':entry,'stop':stop,'target':target,'rr':float(plan['tp1_rr']),
                           'stop_atr_ratio':stop_ratio,'m5_body_ratio':body,'outcome':outcome,'net_r':net_r})
            busy_until[strategy]=exit_time+pd.Timedelta(minutes=1)
    output.mkdir(parents=True,exist_ok=True)
    pd.DataFrame(decisions).to_csv(output/'decisions.csv',index=False)
    cols=['strategy','entry_time_utc','exit_time_utc','entry','stop','target','rr','stop_atr_ratio','m5_body_ratio','outcome','net_r']
    td=pd.DataFrame(trades,columns=cols);td.to_csv(output/'trades.csv',index=False)
    summaries=[]
    for name in ['baseline','candidate']:
        t=td[td.strategy==name]; n=len(t)
        cumulative=t.net_r.cumsum() if n else pd.Series(dtype=float)
        summaries.append({'strategy':name,'trades':n,'tp':int((t.outcome=='TP').sum()),
                          'sl':int((t.outcome=='SL').sum()),'time_exits':int((t.outcome=='TIME').sum()),
                          'total_net_r':float(t.net_r.sum()) if n else np.nan,
                          'avg_net_r':float(t.net_r.mean()) if n else np.nan,
                          'max_drawdown_r':float((cumulative-cumulative.cummax().clip(lower=0)).min()) if n else np.nan})
    pd.DataFrame(summaries).to_csv(output/'summary.csv',index=False)
    print(f'M1 rows={len(m1)} M5 completed={len(m5)} M15 completed={len(m15)} decisions={len(decisions)}')
    print(pd.DataFrame(summaries).to_string(index=False))
    print('CAUTION: M5 confirmation is an explicit proxy, not verified live M5 algorithm parity.')
    print('CAUTION: historical event/shock locks, spreads, fills, and live watcher parity not modeled.')

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--input',required=True);a.add_argument('--output',default='research_audit_output')
    a.add_argument('--max-stop-atr',type=float,default=4.0,help='Research-only rejection cap, not optimized')
    a.add_argument('--cost-bps',type=float,default=10.0);a.add_argument('--max-minutes',type=int,default=120)
    args=a.parse_args();run(args.input,Path(args.output),args.max_stop_atr,args.cost_bps,args.max_minutes)
