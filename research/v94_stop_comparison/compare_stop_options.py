"""Offline V9.4 stop/entry options. Research only; no live execution."""
import argparse
from pathlib import Path
import numpy as np
import pandas as pd
from research_audit_v94 import load_m1,bars,m5_sell,simulate,BODY_THRESHOLD
from candle_power_v94 import analyze_last_10_candles,diagnose_sell_quality
from structure_risk_v94 import structure_atr_plan,_confirmed_swings,_atr14,_next_level

OPTIONS=('original_m15','atr_cap_m15','pullback_m15','m5_structure')

def m5_plan(m5_hist,entry,cost_bps):
    if len(m5_hist)<35:return None
    atr=_atr14(m5_hist)
    sh,_=_confirmed_swings(m5_hist,lookback=48,wing=2)
    if not sh or not np.isfinite(atr) or atr<=0:return None
    stop=max(sh[-1]+1.5*atr,entry*(1+3*cost_bps/10000))
    return float(stop) if stop>entry else None

def run(input_file,output,cap_atr=4.,pullback_atr=.5,wait_minutes=30,cost_bps=10.,max_minutes=120):
    m1=load_m1(input_file);m5=bars(m1,5);m15=bars(m1,15)
    decisions=[];trades=[]
    busy={k:pd.Timestamp.min.tz_localize('UTC') for k in OPTIONS}
    for ts in m15.index:
        hist=m15.loc[:ts]
        if len(hist)<35 or ts not in m5.index:continue
        power=analyze_last_10_candles(hist)
        quality=diagnose_sell_quality(power)
        sell5,body=m5_sell(m5.loc[ts])
        plan=structure_atr_plan('SELL',hist,atr_multiple=1.5,min_tp1_rr=2.,swing_lookback=48,cost_bps=cost_bps)
        atr=float(plan.get('atr',np.nan));entry=float(plan.get('entry',np.nan));stop=float(plan.get('stop',np.nan));target=float(plan.get('tp1',np.nan))
        distance=stop-entry; ratio=distance/atr if np.isfinite(distance) and np.isfinite(atr) and atr>0 else np.nan
        # Common directional gates; alternative structures must qualify independently.
        common_checks={'m15_sell':power.signal=='SELL',
                       'quality_8_of_9':quality['status']=='CONFIRMED',
                       'm5_sell_proxy':sell5,
                       'strong_m5_body':body>=BODY_THRESHOLD}
        signal_ok=all(common_checks.values())
        # Same pre-existing M15 structural target for fair stop comparison.
        _,m15_lows=_confirmed_swings(hist,lookback=48,wing=2)
        if not np.isfinite(target):
            target=_next_level(m15_lows,entry,'SELL')
        variants={}
        diagnostics={}
        option_metrics={}
        def assess(name, start, e, s, t, label, cap=False, needs_fill=False):
            # Save the independent proposal even if the option is rejected.
            risk=s-e if np.isfinite(s) and np.isfinite(e) else np.nan
            reward=e-t if np.isfinite(e) and np.isfinite(t) else np.nan
            rr=reward/risk if np.isfinite(reward) and np.isfinite(risk) and risk>0 else np.nan
            option_metrics[name]={'entry':e,'stop':s,'target':t,'risk':risk,
                                  'reward':reward,'rr':rr,
                                  'stop_atr':risk/atr if np.isfinite(risk) and np.isfinite(atr) and atr>0 else np.nan,
                                  'fill_time_utc':start.isoformat() if start is not None else ''}
            if not signal_ok:
                diagnostics[name]='signal_filters_failed'
            elif needs_fill and start is None:
                diagnostics[name]='pullback_not_filled'
            elif not all(np.isfinite(v) for v in (e,s,t)):
                diagnostics[name]='missing_entry_stop_or_structural_target'
            elif not (s>e>t):
                diagnostics[name]='invalid_stop_or_target_side'
            elif cap and (not np.isfinite(atr) or risk/atr>cap_atr):
                diagnostics[name]='stop_distance_cap_exceeded'
            elif rr<2.0:
                diagnostics[name]='structural_target_below_2R'
            elif start is None:
                diagnostics[name]='entry_not_available'
            else:
                variants[name]=(start,e,s,t,label)
                diagnostics[name]='eligible'
        assess('original_m15',ts,entry,stop,target,'original structure')
        assess('atr_cap_m15',ts,entry,stop,target,'ATR cap passed',cap=True)
        # A pullback improves entry price while retaining the original protective stop.
        # Use only M1 bars AFTER the decision; fill at limit after touch, next minute.
        pullback_start=None
        pullback_entry=np.nan
        if signal_ok and np.isfinite(atr) and np.isfinite(entry):
            desired=entry+pullback_atr*atr
            future=m1.loc[(m1.index>=ts)&(m1.index<ts+pd.Timedelta(minutes=wait_minutes))]
            hits=future.index[future.high>=desired]
            if len(hits):
                candidate_start=hits[0]+pd.Timedelta(minutes=1)
                if candidate_start in m1.index and candidate_start<ts+pd.Timedelta(minutes=wait_minutes):
                    pullback_start=candidate_start
                    # Conservative, observable market entry at the next M1 OPEN;
                    # never assume the previous limit price is still fillable.
                    pullback_entry=float(m1.loc[candidate_start,'open'])
            assess('pullback_m15',pullback_start,pullback_entry,stop,target,'next-minute market open after pullback touch',needs_fill=True)
        else:
            assess('pullback_m15',None,np.nan,stop,target,'pullback unavailable',needs_fill=True)
        m5_stop=m5_plan(m5.loc[:ts],entry,cost_bps) if signal_ok else None
        assess('m5_structure',ts,entry,float(m5_stop) if m5_stop is not None else np.nan,
               target,'M5 structural stop')
        decision={'time_utc':ts.isoformat(),'m15_signal':power.signal,
                  'quality_checks':quality['checks_passed'],'m5_sell_proxy':sell5,
                  'm5_body_ratio':body,'m15_stop_atr_ratio':ratio,
                  'base_candidate':signal_ok,'failed_checks':';'.join(k for k,v in common_checks.items() if not v),
                  'entry':entry,'m15_swing_high':plan.get('swing'),'m15_atr':atr,
                  'm15_stop':stop,'structural_target':target,
                  'original_rr':((entry-target)/(stop-entry) if np.isfinite(target) and np.isfinite(stop) and stop>entry else np.nan),
                  'original_structure_reason':plan.get('reason','')}
        for opt in OPTIONS:
            decision[opt+'_reason']=diagnostics.get(opt,'not_evaluated')
            for key,val in option_metrics.get(opt,{}).items():
                decision[opt+'_'+key]=val
        for opt in OPTIONS:decision[opt]='SELL' if opt in variants else 'WAIT'
        decisions.append(decision)
        for opt,(start,e,s,t,reason) in variants.items():
            if start<busy[opt]:continue
            outcome,r,exit_ts=simulate(m1,start,e,s,t,cost_bps,max_minutes)
            if outcome not in ('SL','TP','TIME'):continue
            trades.append({'option':opt,'signal_time_utc':ts.isoformat(),'entry_time_utc':start.isoformat(),'exit_time_utc':exit_ts.isoformat(),'entry':e,'stop':s,'target':t,'rr':(e-t)/(s-e),'stop_distance':s-e,'stop_atr_ratio':(s-e)/atr,'outcome':outcome,'net_r':r,'detail':reason})
            busy[opt]=exit_ts+pd.Timedelta(minutes=1)
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    pd.DataFrame(decisions,columns=['time_utc','m15_signal','quality_checks','m5_sell_proxy','m5_body_ratio','m15_stop_atr_ratio','base_candidate','failed_checks','entry','m15_swing_high','m15_atr','m15_stop','structural_target','original_rr','original_structure_reason',*[item for opt in OPTIONS for item in (opt,opt+'_reason',*[opt+'_'+metric for metric in ('entry','stop','target','risk','reward','rr','stop_atr','fill_time_utc')])]]).to_csv(output/'decisions.csv',index=False)
    t=pd.DataFrame(trades,columns=['option','signal_time_utc','entry_time_utc','exit_time_utc','entry','stop','target','rr','stop_distance','stop_atr_ratio','outcome','net_r','detail'])
    t.to_csv(output/'trades.csv',index=False)
    summary=[]
    for opt in OPTIONS:
        a=t[t.option==opt].sort_values('entry_time_utc');n=len(a)
        c=a.net_r.cumsum() if n else pd.Series(dtype=float)
        dd=(c-c.cummax().clip(lower=0)).min() if n else np.nan
        summary.append({'option':opt,'trades':n,'tp':int((a.outcome=='TP').sum()),'sl':int((a.outcome=='SL').sum()),'time':int((a.outcome=='TIME').sum()),'total_net_r':a.net_r.sum() if n else np.nan,'mean_net_r':a.net_r.mean() if n else np.nan,'max_drawdown_r':dd})
    pd.DataFrame(summary).to_csv(output/'summary.csv',index=False)
    print('M1:',len(m1),'M15:',len(m15),'decisions:',len(decisions));print(pd.DataFrame(summary).to_string(index=False))
    print('CAUTION: proxy M5 signal, reused historical research assumptions; not independent validation.')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--output',default='comparison_output');p.add_argument('--cap-atr',type=float,default=4.);p.add_argument('--pullback-atr',type=float,default=.5);p.add_argument('--wait-minutes',type=int,default=30);p.add_argument('--cost-bps',type=float,default=10.);p.add_argument('--max-minutes',type=int,default=120)
    a=p.parse_args();run(a.input,a.output,a.cap_atr,a.pullback_atr,a.wait_minutes,a.cost_bps,a.max_minutes)
