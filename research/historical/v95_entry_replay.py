"""Isolated V9.5 technical SELL-entry replay. Research only; NOT a full paper-monitor replay.
Historical news events are unavailable; technical opportunities are evaluated without news
authorization. Exits: SL/TP or 240 M1 bars; no discretionary, partial or Telegram logic.
Uses next M1 open for entry and stop-first on ambiguous intrabar hits.
Never writes to source databases, running monitors, or production state.
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
    trades=[]; pending=None; active=None; last_t=None
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
                        active['outcome']='CENSORED_GAP';trades.append(active);stats['censored_gap']+=1;active=None
                    pending=None
                last_t=t
                row={'t':t,'o':o,'h':h,'l':l,'c':c}
                m1.append(row)
                completed=aggregate_update(aggs,t,o,h,l,c)
                if pending and t==pending['next_t']:
                    risk=pending['stop']-o
                    if risk>0 and ny_open(t):
                        active={**pending,'entry_utc':t.isoformat(),'entry':o,'risk':risk,
                                'target':o-2*risk,'elapsed':0,'year':t.year}
                        stats['entered']+=1
                    pending=None
                if active:
                    active['elapsed']+=1
                    stop=active['stop'];tp=active['target']
                    if h>=stop: outcome='SL';fill=max(stop,o)
                    elif l<=tp: outcome='TP';fill=tp
                    elif active['elapsed']>=MAX_HOLD: outcome='TIMEOUT';fill=c
                    else: outcome=None
                    if outcome:
                        active['exit_utc']=t.isoformat()
                        active['outcome']=outcome
                        active['gross_r']=(active['entry']-fill)/active['risk']
                        active['net_r']=active['gross_r']-active['entry']*(COST_BPS/10000)/active['risk']
                        trades.append(active);stats[outcome.lower()]+=1;active=None
                if 15 in completed and not active and not pending and ny_open(t):
                    # Only M15 boundary: closed M5/H1, and contiguous mandatory windows.
                    signal=technical_signal(m1,aggs)
                    if signal:
                        stats['technical_opportunities']+=1
                        pending={**signal,'next_t':t+ONE}
    if active:
        active['outcome']='CENSORED_END';trades.append(active);stats['censored_end']+=1
    completed=[x for x in trades if 'net_r' in x]
    by_year={}
    for year in sorted({x['year'] for x in completed}):
        v=[x['net_r'] for x in completed if x['year']==year]
        by_year[str(year)]={'trades':len(v),'mean_net_r':round(sum(v)/len(v),5),
                            'sum_net_r':round(sum(v),5),
                            'win_rate':round(sum(x>0 for x in v)/len(v),5)}
    report={'method':'V9.5 technical-entry research baseline, simplified SL/TP-only exits',
            'NOT_FULL_V95_PAPER_REPLAY':True,
            'news_gate':'NOT_TESTED: historical economic events unavailable',
            'paper_risk_daily_lock':'NOT_TESTED',
            'partial_exits_and_early_exits':'NOT_TESTED',
            'trade_overlap':'one at a time',
            'entry_fill':'next available contiguous M1 open',
            'exit_priority':'stop before target; conservative gap stop fill',
            'cost':'5 basis points of entry price per completed round trip',
            'hold_limit_m1':MAX_HOLD,'stats':dict(stats),'per_year':by_year,
            'completed_trades':len(completed),
            'overall_mean_net_r':round(sum(x['net_r'] for x in completed)/len(completed),5) if completed else None,
            'trades':trades}
    Path('v95-entry-replay-results.json').write_text(json.dumps(report,indent=2,default=str))
    print(json.dumps({k:v for k,v in report.items() if k!='trades'},indent=2))
    print('RESEARCH_ONLY_REPLAY_COMPLETE')

if __name__=='__main__':
    replay()
