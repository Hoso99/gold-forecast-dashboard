"""Research-only Trading Economics calendar adapter. Not enabled without verified credentials and UTC timestamps."""
import datetime as dt
import json
import os
from urllib.parse import quote, urlencode
from urllib.request import urlopen
from zoneinfo import ZoneInfo

UTC = dt.timezone.utc
TERMS = ("cpi", "consumer price", "nonfarm", "payroll", "fomc", "fed rate",
         "interest rate", "powell", "pce", "personal consumption", "unemployment",
         "gdp", "retail sales", "ism", "pmi", "jobless", "crude oil",
         "oil inventories", "petroleum", "eia")
VERY_HIGH = ("cpi", "consumer price", "nonfarm", "payroll", "fomc", "fed rate",
             "interest rate", "powell", "pce", "unemployment")

def parse_utc(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Missing event timestamp")
    parsed = dt.datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    # TE examples use naive timestamps. Do not silently guess their timezone.
    if parsed.tzinfo is None:
        if os.getenv("V95_TE_NAIVE_DATES_ARE_UTC") != "1":
            raise ValueError("TE timestamp has no timezone; UTC convention not verified")
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)

def classify(events, now=None):
    now = now or dt.datetime.now(UTC)
    if not isinstance(events, list) or not events:
        raise ValueError("Empty/unexpected economic calendar")
    relevant = []
    for e in events:
        if not isinstance(e, dict):
            raise ValueError("Unexpected calendar event")
        if str(e.get("Country", "")).lower() not in ("united states", "us", "usa"):
            continue
        name = str(e.get("Event") or e.get("Category") or "")
        lower = name.lower()
        if not any(term in lower for term in TERMS):
            continue
        # Estimated release times cannot clear a trading gate.
        if str(e.get("DateSpan", "0")) != "0":
            raise ValueError("Relevant event has estimated release time")
        when = parse_utc(e.get("Date"))
        delta = (when - now).total_seconds() / 60
        if -30 <= delta <= 240:
            relevant.append({"name": name, "utc": when.isoformat(),
                "cyprus": when.astimezone(ZoneInfo("Asia/Nicosia")).isoformat(),
                "minutes_to_event": round(delta, 1),
                "very_high": any(t in lower for t in VERY_HIGH)})
    relevant.sort(key=lambda e: abs(e["minutes_to_event"]))
    imminent = any(-15 <= e["minutes_to_event"] <= 30 for e in relevant)
    building = any(0 <= e["minutes_to_event"] <= 120 for e in relevant)
    return {"risk": "IMMINENT" if imminent else "BUILDING" if building else "NORMAL",
            "events": relevant[:10], "source": "TRADING_ECONOMICS_RESEARCH"}

def fetch_calendar_context(now=None):
    key = os.getenv("V95_TE_API_KEY")
    if not key:
        return {"risk": "UNKNOWN", "source": "TE_NOT_CONFIGURED"}
    now = now or dt.datetime.now(UTC)
    start = (now - dt.timedelta(days=1)).date().isoformat()
    end = (now + dt.timedelta(days=2)).date().isoformat()
    url = ("https://api.tradingeconomics.com/calendar/country/united%20states/"
           + start + "/" + end + "?" + urlencode({"c": key, "f": "json"}))
    try:
        with urlopen(url, timeout=12) as response:
            events = json.load(response)
        return classify(events, now)
    except Exception as exc:
        return {"risk": "UNKNOWN", "source": "TE_UNVERIFIED",
                "error_type": type(exc).__name__}
