import pandas as pd, numpy as np, importlib.util
from pathlib import Path
P=Path(__file__).parent
spec=importlib.util.spec_from_file_location('power',str(P/'candle_power_v94.py')); mod=importlib.util.module_from_spec(spec)
import sys;sys.modules['power']=mod;spec.loader.exec_module(mod)
m=pd.read_csv(P/'candle_dynamics_m1_v94.csv',parse_dates=['datetime']).set_index('datetime').sort_index()
m=m[~m.index.duplicated(keep='last')]
def candles(freq, n):
 g=m.groupby(m.index.floor(freq)).agg(open=('open','first'),high=('high','max'),low=('low','min'),close=('close','last'),count=('close','size'))
 g=g[g['count']==n].drop(columns='count');g.index=g.index+pd.Timedelta(freq)
 return g
m15=candles('15min',15);m5=candles('5min',5)
# Explicitly reject windows containing incomplete or missing bars.
def is_contiguous(idx, n, minutes):
 return len(idx)>=n and (idx[-1]-idx[-n]==pd.Timedelta(minutes=(n-1)*minutes))
records=[];count=0
for i in range(30,len(m15)-16):
 t=m15.index[i]; hist=m15.iloc[i-29:i+1]
 if not is_contiguous(hist.index,30,15):continue
 p=mod.analyze_last_10_candles(hist)
 if p.signal!='SELL':continue
 q=mod.diagnose_sell_quality(p)
 if q['status']!='CONFIRMED':continue
 j=m5.index.searchsorted(t,side='right')-1
 if j<29 or m5.index[j]!=t:continue
 h5=m5.iloc[j-29:j+1]
 if not is_contiguous(h5.index,30,5):continue
 p5=mod.analyze_last_10_candles(h5)
 entry=float(m.loc[m.index>=t].iloc[0].open) if len(m.loc[m.index>=t]) else np.nan
 # 60/120 minute forward close changes, research-only, not SLTP fills
 future=m15.loc[m15.index>t].head(8)
 if len(future)<8 or not is_contiguous(pd.DatetimeIndex([t]+list(future.index)),9,15):continue
 records.append(dict(time=t,m15_sell_power=p.sell_power,m15_quality=q['checks_passed'],m5_sell_power=p5.sell_power,m5_signal=p5.signal,entry=entry,forward_60=entry-float(future.iloc[3].close),forward_120=entry-float(future.iloc[7].close)))
 count+=1
r=pd.DataFrame(records);r.to_csv(P/'full_history_m15_m5.csv',index=False)
if r.empty:raise ValueError('No aligned setups')
cut=int(len(m15)*.70);cut_time=m15.index[cut]
print('M1 rows',len(m),'M15',len(m15),'M5',len(m5),'candidate setups',len(r),'split',cut_time)
for period,a in [('train',r[r.time<cut_time]),('test',r[r.time>=cut_time])]:
 for label,b in [('M15',a),('M15+M5',a[a.m5_signal=='SELL'])]:
  print(period,label,'n',len(b),'60m down%',round(100*(b.forward_60>0).mean(),2) if len(b) else None,'120m down%',round(100*(b.forward_120>0).mean(),2) if len(b) else None,'avg 60m move',round(b.forward_60.mean(),2) if len(b) else None,'avg 120m move',round(b.forward_120.mean(),2) if len(b) else None)
