"""V9.4 ten-measurement research diagnostics from completed M1 candles.

Does not change live entry/exit decisions, send alerts, or execute trades.
Missing external feeds remain null, never inferred from OHLC.
"""
import argparse
import csv
import datetime as dt
import json
import math
from pathlib import Path
from external_inputs import enrich

def mean(xs):
    return sum(xs)/len(xs) if xs else None

def bars_from_csv(path):
    rows=[]
    with open(path,newline="") as f:
        for row in csv.DictReader(f):
            ts=dt.datetime.fromisoformat(row["datetime"].replace("Z","+00:00"))
            if ts.tzinfo is None: raise ValueError("Timestamps must have timezone")
            o,h,l,c=(float(row[k]) for k in ("open","high","low","close"))
            if not all(map(math.isfinite,(o,h,l,c))) or not l<=min(o,c)<=max(o,c)<=h:
                raise ValueError("Invalid OHLC")
            rows.append((ts,o,h,l,c))
    rows.sort()
    if len({r[0] for r in rows})!=len(rows): raise ValueError("Duplicate candle timestamp")
    return rows

def power(rows):
    buy=sell=0.
    for _,o,h,l,c in rows:
        rng=h-l
        weight=max(rng,1e-8)
        fraction=(c-l)/rng if rng else .5
        buy+=weight*fraction
        sell+=weight*(1-fraction)
    return round(100*sell/(buy+sell),2) if buy+sell else None

def atr(rows,period=14):
    if len(rows)<period+1: return None
    tr=[]
    for previous,current in zip(rows,rows[1:]):
        _,_,ph,pl,pc=previous
        _,_,h,l,_=current
        tr.append(max(h-l,abs(h-pc),abs(l-pc)))
    return mean(tr[-period:])

def frame_closes(rows,minutes):
    # Include only fully populated, time-contiguous UTC buckets.
    buckets={}
    for r in rows:
        ts=r[0]
        start=ts.replace(minute=(ts.minute//minutes)*minutes,second=0,microsecond=0)
        if minutes>60:
            start=ts.replace(hour=(ts.hour//(minutes//60))*(minutes//60),minute=0,second=0,microsecond=0)
        buckets.setdefault(start,[]).append(r)
    closes=[]
    for start,group in sorted(buckets.items()):
        if len(group)==minutes and all(group[i][0]==start+dt.timedelta(minutes=i) for i in range(minutes)):
            closes.append((start,group[-1][4],group[0][1],max(x[2] for x in group),min(x[3] for x in group)))
    return closes

def calculate(rows):
    if len(rows)<45: raise ValueError("Need at least 45 completed M1 candles")
    recent=rows[-10:]
    if any(b[0]-a[0]!=dt.timedelta(minutes=1) for a,b in zip(recent,recent[1:])):
        raise ValueError("Latest ten candles contain gaps")
    close=rows[-1][4]
    sell_now=power(recent)
    sell_before=power(rows[-20:-10])
    previous=rows[-21:-1]
    support=min(r[3] for r in previous)
    resistance=max(r[2] for r in previous)
    a=atr(rows)
    older=atr(rows[:-10])
    m5=frame_closes(rows,5)
    m15=frame_closes(rows,15)
    h1=frame_closes(rows,60)
    h4=frame_closes(rows,240)
    def trend(frame):
        if len(frame)<4: return None
        return "DOWN" if frame[-1][1]<frame[-4][1] else "UP" if frame[-1][1]>frame[-4][1] else "FLAT"
    # A sweep requires previous-bar reference and a return through that level.
    previous_high=max(r[2] for r in rows[-21:-1])
    bearish_sweep=rows[-1][2]>previous_high and close<previous_high
    m1_bullish=rows[-1][4]>rows[-1][1]
    m5_bullish=(m5[-1][1]>m5[-1][2]) if m5 else None
    # These are indicators/proxies, not validated trading rules.
    measurements={
      "01_selling_pressure_acceleration":{"status":"PROXY","sell_power_10m_pct":sell_now,
           "previous_10m_pct":sell_before,"change_percentage_points":round(sell_now-sell_before,2)},
      "02_support_resistance":{"status":"OHLC_DERIVED","support_20m":support,
           "resistance_20m":resistance,"distance_to_support":round(close-support,5),
           "distance_to_resistance":round(resistance-close,5)},
      "03_liquidity_sweep":{"status":"PRICE_PATTERN_PROXY","bearish_resistance_sweep":bearish_sweep,
           "note":"Price pattern only; no order book or liquidity confirmation"},
      "04_m1_m5_reversal":{"status":"OHLC_DERIVED","m1_bullish":m1_bullish,
           "m5_bullish":m5_bullish,"m5_complete_bars":len(m5)},
      "05_higher_timeframe_alignment":{"status":"OHLC_DERIVED_PARTIAL","m15":trend(m15),
           "h1":trend(h1),"h4":trend(h4)},
      "06_volatility_atr":{"status":"OHLC_DERIVED","atr14_m1":round(a,5) if a is not None else None,
           "atr_change_pct":round(100*(a/older-1),2) if a and older else None},
      "07_economic_event_proximity":{"status":"UNAVAILABLE","minutes_to_event":None,
           "reason":"Requires timestamped verified economic calendar"},
      "08_spread_execution":{"status":"UNAVAILABLE","spread":None,"slippage":None,
           "reason":"Mid-price OHLC cannot reveal executable bid/ask or slippage"},
      "09_dxy_treasury_yields":{"status":"UNAVAILABLE","dxy_change":None,"yield_change":None,
           "reason":"Requires timestamp-aligned independent DXY and Treasury-yield feeds"},
      "10_active_trade_deterioration":{"status":"PROXY_NO_POSITION","buy_power_10m_pct":round(100-sell_now,2),
           "sell_power_delta_pp":round(sell_now-sell_before,2),
           "active_position_known":False,"early_exit_signal":None}
    }
    return {"as_of_m1_start_utc":rows[-1][0].isoformat(),"spot_close":close,
            "research_only":True,"measurements":measurements}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",default="research/data/v94_forward_m1.csv")
    p.add_argument("--output",default="research/ten_measurements/latest.json")
    p.add_argument("--events",default=None)
    p.add_argument("--quotes",default=None)
    p.add_argument("--macro",default=None)
    args=p.parse_args()
    result=calculate(bars_from_csv(args.input))
    enrich(result["measurements"],result["as_of_m1_start_utc"],args.events,args.quotes,args.macro)
    out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({"as_of":result["as_of_m1_start_utc"],
          "available":sum(m["status"]!="UNAVAILABLE" for m in result["measurements"].values()),
          "unavailable":sum(m["status"]=="UNAVAILABLE" for m in result["measurements"].values()),
          "output":str(out)}))
if __name__=="__main__": main()
