"""As-of safe external measurement inputs; no look-ahead or invented data."""
import csv
import datetime as dt
import math
from pathlib import Path

def timestamp(value):
    t=dt.datetime.fromisoformat(value.replace("Z","+00:00"))
    if t.tzinfo is None: raise ValueError("UTC offset required")
    return t.astimezone(dt.timezone.utc)

def read_csv(path,columns):
    if not path or not Path(path).exists(): return []
    with open(path,newline="") as f:
        reader=csv.DictReader(f)
        if not set(columns).issubset(reader.fieldnames or []):
            raise ValueError("Missing required external data columns: "+str(set(columns)-set(reader.fieldnames or [])))
        return list(reader)

def finite(value):
    v=float(value)
    if not math.isfinite(v): raise ValueError("Nonfinite external data")
    return v

def enrich(measurements,as_of,event_path=None,quotes_path=None,macro_path=None):
    """Inputs must be independently timestamped; only observations available as_of used."""
    as_of=timestamp(as_of)
    events=read_csv(event_path,("event_time_utc","available_at_utc","event","importance"))
    candidates=[]
    for row in events:
        available=timestamp(row["available_at_utc"])
        event_time=timestamp(row["event_time_utc"])
        if available<=as_of and event_time>=as_of and row["importance"].upper() in ("HIGH","VERY_HIGH"):
            candidates.append((event_time,row))
    if candidates:
        event_time,row=min(candidates,key=lambda x:x[0])
        measurements["07_economic_event_proximity"]={
            "status":"EXTERNAL_VERIFIED_INPUT","minutes_to_event":round((event_time-as_of).total_seconds()/60,2),
            "event":row["event"],"importance":row["importance"],"event_time_utc":event_time.isoformat(),
            "available_at_utc":timestamp(row["available_at_utc"]).isoformat()}
    quotes=read_csv(quotes_path,("observed_at_utc","bid","ask","source"))
    eligible=[]
    for row in quotes:
        observed=timestamp(row["observed_at_utc"])
        age=(as_of-observed).total_seconds()
        if 0<=age<=120:
            bid,ask=finite(row["bid"]),finite(row["ask"])
            if 0<bid<=ask: eligible.append((observed,bid,ask,row["source"]))
    if eligible:
        observed,bid,ask,source=max(eligible,key=lambda x:x[0])
        measurements["08_spread_execution"]={"status":"EXTERNAL_QUOTE_NOT_EXECUTION",
            "spread":round(ask-bid,6),"bid":bid,"ask":ask,"source":source,
            "observed_at_utc":observed.isoformat(),"slippage":None}
    macro=read_csv(macro_path,("available_at_utc","series","value","source"))
    series={}
    for row in macro:
        available=timestamp(row["available_at_utc"])
        if available>as_of: continue
        name=row["series"].upper()
        if name not in ("DXY","DGS10"): continue
        value=finite(row["value"])
        series.setdefault(name,[]).append((available,value,row["source"]))
    latest={}
    for name,observations in series.items():
        observations.sort()
        latest[name]=observations[-1]
    if latest:
        measurements["09_dxy_treasury_yields"]={
            "status":"EXTERNAL_PARTIAL" if len(latest)<2 else "EXTERNAL_DAILY_OR_DELAYED",
            "dxy":latest["DXY"][1] if "DXY" in latest else None,
            "dgs10_pct":latest["DGS10"][1] if "DGS10" in latest else None,
            "sources":{name:{"source":row[2],"available_at_utc":row[0].isoformat()} for name,row in latest.items()},
            "dxy_change":None,"yield_change":None,
            "note":"As-of observations only; DGS10 is daily, not a live trading trigger"}
    return measurements
