"""Biquote XAUUSD quote and US macro context; research-only, fail closed."""
import datetime as dt
import json
from urllib.parse import urlencode
from urllib.request import urlopen
from zoneinfo import ZoneInfo

UTC=dt.timezone.utc
HIGH_TERMS=("cpi","consumer price","nonfarm","payroll","fomc","fed rate","interest rate","powell","pce","personal consumption","unemployment","gdp","retail sales","ism","pmi","jobless","crude oil","oil inventories","petroleum","eia")
VERY_HIGH=("cpi","consumer price","nonfarm","payroll","fomc","fed rate","interest rate","powell","pce","unemployment")

def get_json(url):
    with urlopen(url,timeout=12) as response:
        return json.load(response)

def parse_utc(value):
    return dt.datetime.fromisoformat(value.replace("Z","+00:00")).astimezone(UTC)

def event_context(events,now=None):
    now=now or dt.datetime.now(UTC)
    relevant=[]
    for event in events:
        name=str(event.get("name",""))
        if event.get("countryCode")!="US" or not any(x in name.lower() for x in HIGH_TERMS):
            continue
        if event.get("timeMode")!="exact" or not event.get("time"):
            continue
        try:
            when=parse_utc(event["time"])
        except (ValueError,TypeError):
            continue
        delta=(when-now).total_seconds()/60
        if -30<=delta<=240:
            relevant.append({"name":name,"utc":when.isoformat(),
                             "cyprus":when.astimezone(ZoneInfo("Asia/Nicosia")).isoformat(),
                             "minutes_to_event":round(delta,1),
                             "very_high":any(x in name.lower() for x in VERY_HIGH)})
    relevant.sort(key=lambda x:abs(x["minutes_to_event"]))
    imminent=any(-15<=x["minutes_to_event"]<=30 for x in relevant)
    buildup=any(0<=x["minutes_to_event"]<=120 for x in relevant)
    return {"events":relevant[:10],"risk":"IMMINENT" if imminent else "BUILDING" if buildup else "NORMAL"}

def fetch_calendar_context(now=None):
    """Fetch high-importance US events independently of XAUUSD quote availability."""
    now=now or dt.datetime.now(UTC)
    start=(now-dt.timedelta(hours=1)).isoformat().replace("+00:00","Z")
    end=(now+dt.timedelta(hours=5)).isoformat().replace("+00:00","Z")
    params=urlencode({"from":start,"to":end,"countries":"US","importance":"high","limit":200})
    events=get_json("https://biquote.io/api/calendar?"+params)
    if not isinstance(events,list):
        raise ValueError("Biquote calendar unexpected response")
    return event_context(events,now)


def fetch_context(now=None):
    """Optional quote + macro context; news gate uses fetch_calendar_context instead."""
    now=now or dt.datetime.now(UTC)
    result=fetch_calendar_context(now)
    quote=get_json("https://biquote.io/api/XAUUSD?allowStale=false")
    if not isinstance(quote,dict) or quote.get("stale") is not False or quote.get("marketState")!="open":
        raise ValueError("Biquote quote stale or market closed")
    bid=float(quote["bid"])
    ask=float(quote["ask"])
    if not (0<bid<=ask):
        raise ValueError("Biquote bid/ask invalid")
    result["quote"]={"bid":bid,"ask":ask,"spread":ask-bid,
                     "timestamp":quote.get("timestamp"),"source":quote.get("source")}
    result["source"]="BIQUOTE_CONTEXT_NOT_EXECUTION_FEED"
    return result
