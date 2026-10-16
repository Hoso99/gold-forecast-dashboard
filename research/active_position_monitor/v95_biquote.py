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

def event_context(events, now=None):
    """Classify the V9.4 upcoming-calendar format; fail closed on invalid data."""
    now = now or dt.datetime.now(UTC)
    if not isinstance(events, list):
        raise ValueError("Biquote calendar response is not a list")
    risk_rank = {"NORMAL": 0, "WATCH": 1, "HIGH": 2, "IMMINENT": 3}
    risk = "NORMAL"
    relevant = []
    valid = 0
    for event in events:
        if not isinstance(event, dict):
            raise ValueError("Malformed Biquote calendar event")
        name = event.get("name")
        time_text = event.get("time")
        if not isinstance(name, str) or not name.strip() or not isinstance(time_text, str):
            raise ValueError("Biquote calendar event missing name/time")
        when = parse_utc(time_text)
        valid += 1
        minutes = (when - now).total_seconds() / 60
        if minutes < 0:
            continue
        name_lower = name.lower()
        if any(term in name_lower for term in VERY_HIGH):
            relevance = "VERY HIGH"
            event_risk = "IMMINENT" if minutes <= 30 else "HIGH" if minutes <= 120 else "WATCH" if minutes <= 360 else "NORMAL"
        elif any(term in name_lower for term in HIGH_TERMS):
            relevance = "HIGH"
            event_risk = "IMMINENT" if minutes <= 15 else "HIGH" if minutes <= 60 else "WATCH" if minutes <= 180 else "NORMAL"
        else:
            relevance = "MODERATE"
            event_risk = "NORMAL"
        if risk_rank[event_risk] > risk_rank[risk]:
            risk = event_risk
        if relevance != "MODERATE":
            relevant.append({
                "name": name,
                "utc": when.isoformat(),
                "cyprus": when.astimezone(ZoneInfo("Asia/Nicosia")).isoformat(),
                "minutes_to_event": round(minutes, 1),
                "relevance": relevance,
                "risk": event_risk,
            })
    if not valid:
        raise ValueError("Biquote calendar returned no verifiable events")
    relevant.sort(key=lambda event: event["minutes_to_event"])
    return {"risk": risk, "events": relevant[:10], "source": "BIQUOTE_UPCOMING_US_HIGH", "event_count": valid}


def fetch_calendar_context(now=None):
    """V9.4-compatible high-importance US calendar; independent of quote feed."""
    now = now or dt.datetime.now(UTC)
    events = get_json(
        "https://biquote.io/api/calendar/upcoming"
        "?countries=US&importance=high&limit=20"
    )
    return event_context(events, now)

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
