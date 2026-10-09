"""Stage 1 XAU/USD spot pressure snapshot. Research only; no trade actions."""
import csv
import datetime as dt
import json
import math
import os
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

UTC = dt.timezone.utc
key = os.environ.get("TWELVE_DATA_API_KEY", "").strip()
if not key:
    raise SystemExit("Missing TWELVE_DATA_API_KEY")
params = urlencode({"symbol":"XAU/USD","interval":"1min","outputsize":30,
                    "timezone":"UTC","apikey":key,"format":"JSON"})
with urlopen("https://api.twelvedata.com/time_series?"+params,timeout=35) as response:
    payload=json.load(response)
if payload.get("status")=="error" or not isinstance(payload.get("values"),list):
    raise SystemExit("Market-data provider did not return M1 candles: "+str(payload.get("message","unknown error")))
now=dt.datetime.now(UTC)
bars=[]
for item in payload["values"]:
    ts=dt.datetime.strptime(item["datetime"],"%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    if ts+dt.timedelta(minutes=1)>now-dt.timedelta(seconds=10):
        continue
    o,h,l,c=(float(item[k]) for k in ("open","high","low","close"))
    if not all(math.isfinite(v) for v in (o,h,l,c)) or not (l<=min(o,c)<=max(o,c)<=h):
        raise SystemExit("Invalid OHLC data")
    bars.append((ts,o,h,l,c))
bars.sort()
if len(bars)<10:
    raise SystemExit("Insufficient completed M1 candles (need 10)")
latest=bars[-1][0]
age=(now-(latest+dt.timedelta(minutes=1))).total_seconds()/60
if age<0 or age>5:
    raise SystemExit(f"Stale or future M1 candle: {age:.1f} minutes since close")
window=bars[-10:]
if any((b[0]-a[0])!=dt.timedelta(minutes=1) for a,b in zip(window,window[1:])):
    raise SystemExit("Gap within the latest 10 M1 candles")
# Candle-derived pressure proxy, not actual order flow or exchange volume.
# Allocate each bar's range using close location; neutral doji/zero range => 50/50.
buy=sell=0.
for _,o,h,l,c in window:
    if h==l:
        b=.5
    else:
        b=max(0.,min(1.,(c-l)/(h-l)))
    weight=max(h-l,1e-8)
    buy+=weight*b
    sell+=weight*(1-b)
total=buy+sell
buy_pct=100*buy/total
sell_pct=100*sell/total
status="BUY_DOMINANT" if buy_pct>sell_pct else "SELL_DOMINANT" if sell_pct>buy_pct else "BALANCED"
row={"observed_at_utc":now.isoformat(),"latest_m1_start_utc":latest.isoformat(),
     "spot_close":window[-1][4],"buy_power_proxy_pct":round(buy_pct,2),
     "sell_power_proxy_pct":round(sell_pct,2),"pressure_state":status,
     "window_candles":10,"data_age_minutes":round(age,2),
     "position_state":"UNKNOWN_NOT_CONNECTED","action":"OBSERVE_ONLY"}
out=Path("research/active_position_monitor/pressure_snapshot.csv")
out.parent.mkdir(parents=True,exist_ok=True)
with out.open("w",newline="") as f:
    w=csv.DictWriter(f,fieldnames=list(row));w.writeheader();w.writerow(row)
print(json.dumps(row,indent=2))
print("Research-only candle pressure proxy; no open-position tracking, alert, or order.")
