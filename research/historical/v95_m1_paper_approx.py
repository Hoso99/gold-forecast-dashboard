"""V9.5 minute-by-minute historical technical PAPER approximation, research only.
Uses V9.5 technical SELL detectors, M1 signal close, M15/H1/M5 gates, 2% paper
risk and 3% UTC-day realized-loss lock, protective SL/TP and early-exit rules.
Historical news events and manual partial acknowledgements are NOT reproduced.
Censors positions on data gaps, no invented fills, no live-state changes.
"""
import collections
import datetime as dt
import json
import math
import sqlite3
from pathlib import Path
from urllib.parse import quote

ROOT = Path('/home/ubuntu/v95-historical-research')
NAMES = ['twelve_xauusd_m1.sqlite3',
         'twelve_xauusd_m1_2021_2022.sqlite3',
         'twelve_xauusd_m1_2022_2023.sqlite3',
         'twelve_xauusd_m1_2023_2024.sqlite3',
         'twelve_xauusd_m1_2024_2025.sqlite3',
         'twelve_xauusd_m1_2025_2026.sqlite3',
         'twelve_xauusd_m1_2026_partial.sqlite3']
UTC = dt.timezone.utc
ONE = dt.timedelta(minutes=1)
EQUITY = 10000.0
COST_BPS = 5.0
MAX_HOLD = 240

def bucket(t, n):
    return t.replace(hour=0, minute=0, second=0, microsecond=0) + dt.timedelta(minutes=((t.hour*60+t.minute)//n)*n)

def consecutive(bars, n, count):
    tail = list(bars)[-count:]
    return len(tail)==count and all(b['t']-a['t']==dt.timedelta(minutes=n) for a,b in zip(tail,tail[1:]))

def atr15(bars):
    b=list(bars)[-15:]
    if len(b)<15: return None
    return sum(max(y['h']-y['l'],abs(y['h']-x['c']),abs(y['l']-x['c'])) for x,y in zip(b,b[1:]))/14

def ny_open(t):
    from zoneinfo import ZoneInfo
    ny=t.astimezone(ZoneInfo('America/New_York'))
    if ny.weekday()==5 or (ny.weekday()==4 and ny.hour>=17) or (ny.weekday()==6 and ny.hour<17):
        return False
    if ny.weekday() in (0,1,2,3) and ny.hour==17: return False
    return True

def aggregate_update(aggs, t, o,h,l,c):
    completed=[]
    for n in (5,15,60,240):
        st=bucket(t,n)
        part=aggs[n]['part']
        if part is None or part['t']!=st:
            part={'t':st,'o':o,'h':h,'l':l,'c':c,'count':1,'last':t,'contig':True}
            aggs[n]['part']=part
        else:
            part['contig'] &= t-part['last']==ONE
            part['h']=max(part['h'],h);part['l']=min(part['l'],l)
            part['c']=c;part['last']=t;part['count']+=1
        if t==st+dt.timedelta(minutes=n-1):
            if part['count']==n and part['contig']:
                aggs[n]['bars'].append({k:part[k] for k in ('t','o','h','l','c')})
                completed.append(n)
            aggs[n]['part']=None
    return completed

def technical_signal(m1, aggs):
    m5=aggs[5]['bars'];m15=aggs[15]['bars'];h1=aggs[60]['bars']
    if not (consecutive(m1,1,10) and consecutive(m5,5,6)
            and consecutive(m15,15,18) and consecutive(h1,60,3)):
        return None
    b=list(m15); a=atr15(b)
    if a is None or not math.isfinite(a) or a<=0: return None
    tail=list(m1)[-10:]
    down=sum(max(x['o']-x['c'],0) for x in tail)
    up=sum(max(x['c']-x['o'],0) for x in tail)
    power=100*down/(down+up) if down+up else 50
    latest=b[-1]; prior=b[-5:-1]
    resistance=max(x['h'] for x in prior); support=min(x['l'] for x in prior)
    span=latest['h']-latest['l']
    if span<=0: return None
    wick=latest['h']-max(latest['o'],latest['c'])
    sweep=(latest['h']>resistance+0.10*a and latest['c']<resistance-0.05*a
           and wick/span>=0.40 and latest['c']<latest['o'] and power>=60)
    brk=(latest['c']<support-0.15*a and latest['c']<latest['o']
         and (latest['c']-latest['l'])/span<=0.30 and power>=60)
    m=list(m5); trend=h1[-1]['c']<h1[-2]['c']
    bearish=m[-1]['c']<m[-2]['c'] and sum(m[-i]['c']<m[-i-1]['c'] for i in range(1,5))>=3
    older_support=min(x['l'] for x in b[-17:-5])
    location=(tail[-1]['c']-older_support)>a
    if not ((sweep or brk) and trend and bearish and location and power>=60): return None
    price=tail[-1]['c'];stop=max(x['h'] for x in b[-5:])+1.5*a
    if stop<=price:return None
    return {'signal_utc':tail[-1]['t'].isoformat(),'signal_price':price,
            'stop':stop,'atr15':a,'power':round(power,2),
            'detector':'SWEEP' if sweep else 'SUPPORT_BREAK'}


def replay():
    aggs={n:{'part':None,'bars':collections.deque(maxlen=25)} for n in (5,15,60,240)}
    m1=collections.deque(maxlen=10)
    stats=collections.Counter()
    trades=[];active=None;last_t=None;realized_loss=0.0;loss_day=None
    for name in NAMES:
        uri='file:'+quote(str(ROOT/name),safe='/')+'?mode=ro&immutable=1'
        with sqlite3.connect(uri,uri=True) as con:
            con.execute('PRAGMA query_only=ON')
            for stamp,o,h,l,c in con.execute('SELECT minute_utc,open,high,low,close FROM candles ORDER BY minute_utc'):
                t=dt.datetime.fromisoformat(stamp).replace(tzinfo=UTC)
                stats['m1_rows']+=1
                if last_t is not None and t-last_t!=ONE:
                    stats['discontinuities']+=1
                    if active:
                        active['exit_utc']=last_t.isoformat()
                        active['outcome']='CENSORED_GAP'
                        trades.append(active);stats['censored_gap']+=1;active=None
                last_t=t
                if loss_day!=t.date():
                    loss_day=t.date();realized_loss=0.0
                row={'t':t,'o':o,'h':h,'l':l,'c':c}
                m1.append(row)
                aggregate_update(aggs,t,o,h,l,c)
                # A V9.5 entry gate must not silently reuse an old M5/M15/H1 bucket.
                fresh=all(aggs[n]['bars'] and aggs[n]['bars'][-1]['t']==
                    (bucket(t,n) if t.minute % n==n-1 and n<=60 else
                     bucket(t,n)-dt.timedelta(minutes=n))
                    for n in (5,15,60))
                contiguous=(consecutive(m1,1,10) and
                            consecutive(aggs[5]['bars'],5,6) and
                            consecutive(aggs[15]['bars'],15,18) and
                            consecutive(aggs[60]['bars'],60,3))
                ready=fresh and contiguous
                if active:
                    # Paper protective exits first, even when entry indicators are unavailable.
                    stop=active['stop'];tp=active['target']
                    if h>=stop:
                        outcome='SL';fill=max(stop,o)
                    elif l<=tp:
                        outcome='TP';fill=tp
                    elif ready and atr15(aggs[15]['bars']) is not None:
                        m15=list(aggs[15]['bars']);m5=list(aggs[5]['bars']);h1=list(aggs[60]['bars'])
                        if m15[-1]['c']>max(x['h'] for x in m15[-4:-1]):
                            outcome='EARLY_EXIT_STRUCTURE';fill=c
                        elif (sum(m5[-i]['c']>m5[-i-1]['c'] for i in range(1,5))>=3
                              and m5[-1]['c']>m5[-2]['c'] and h1[-1]['c']>h1[-2]['c']):
                            outcome='EARLY_EXIT_MOMENTUM';fill=c
                        else:outcome=None
                    else:outcome=None
                    if outcome:
                        active['exit_utc']=t.isoformat()
                        active['outcome']=outcome
                        active['gross_r']=(active['entry']-fill)/active['risk']
                        active['net_r']=active['gross_r']-active['entry']*(COST_BPS/10000)/active['risk']
                        pnl=(active['entry']-fill)*active['units']
                        if pnl<0:realized_loss+=-pnl
                        active['paper_pnl']=round(pnl,2)
                        trades.append(active);stats[outcome.lower()]+=1;active=None
                    continue
                if not ready or not ny_open(t):
                    stats['entry_not_ready_or_session']+=1
                    continue
                if realized_loss>=EQUITY*0.03:
                    stats['daily_lock_minutes']+=1;continue
                signal=technical_signal(m1,aggs)
                if not signal:continue
                stats['technical_opportunities']+=1
                risk=signal['stop']-c
                budget=min(EQUITY*0.02,max(0.0,EQUITY*0.03-realized_loss))
                if risk<=0 or budget<=0:continue
                active={**signal,'entry_utc':t.isoformat(),'entry':c,
                        'risk':risk,'target':c-2*risk,'units':budget/risk,
                        'risk_budget':budget,'year':t.year}
                stats['entered']+=1
    if active:
        active['outcome']='CENSORED_END';trades.append(active);stats['censored_end']+=1
    completed=[x for x in trades if 'net_r' in x]
    def summarize(v):
        if not v:return {'trades':0,'mean_net_r':None,'sum_net_r':0,'win_rate':None}
        return {'trades':len(v),'mean_net_r':round(sum(x['net_r'] for x in v)/len(v),5),
                'sum_net_r':round(sum(x['net_r'] for x in v),5),
                'win_rate':round(sum(x['net_r']>0 for x in v)/len(v),5)}
    per_year={str(year):summarize([x for x in completed if x['year']==year])
              for year in sorted({x['year'] for x in completed})}
    per_detector={name:summarize([x for x in completed if x['detector']==name])
                  for name in ('SWEEP','SUPPORT_BREAK')}
    report={'method':'V9.5 M1-close technical PAPER approximation v2',
            'NOT_FULL_V95_PAPER_REPLAY':True,
            'news_gate':'NOT_TESTED - no verified historical events; opportunities are hypothetical',
            'manual_partial_acknowledgements':'NOT_TESTED - no partial close or move-to-break-even',
            'paper_risk':'2 percent per position, 3 percent UTC-day realized loss lock',
            'entry':'M1 signal close (paper model reference; not executable fill guarantee)',
            'exits':'M1 protective stop-first, 2R TP, original indicator-based early exits',
            'gap_handling':'censor open positions on any M1 discontinuity',
            'cost':'5 bps of entry price per completed round trip',
            'stats':dict(stats),'per_year':per_year,'per_detector':per_detector,
            'completed_trades':len(completed),
            'overall':summarize(completed),
            'train_2020_2025':summarize([x for x in completed if x['year']<2026]),
            'seen_2026_diagnostic_only':summarize([x for x in completed if x['year']==2026]),
            'trades':trades}
    Path('v95-m1-paper-approx-results.json').write_text(json.dumps(report,indent=2,default=str))
    print(json.dumps({k:v for k,v in report.items() if k!='trades'},indent=2))
    print('RESEARCH_ONLY_M1_APPROX_COMPLETE')

if __name__=='__main__':
    replay()
