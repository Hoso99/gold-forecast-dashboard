import json
import urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

URL = (
    "https://biquote.io/api/calendar/upcoming"
    "?countries=US"
    "&importance=high"
    "&limit=20"
)

CYPRUS_TZ = ZoneInfo("Europe/Nicosia")

VERY_HIGH_GOLD_EVENTS = [
    "cpi",
    "core cpi",
    "nonfarm payroll",
    "unemployment rate",
    "fomc",
    "federal reserve",
    "fed interest rate",
    "interest rate decision",
    "powell",
    "pce",
]

HIGH_GOLD_EVENTS = [
    "initial jobless claims",
    "ism manufacturing",
    "ism non-manufacturing",
    "services pmi",
    "manufacturing pmi",
    "crude oil stocks",
    "retail sales",
    "gdp",
]


def parse_event_time(value):
    return datetime.fromisoformat(
        value.replace("Z", "+00:00")
    )


def gold_relevance(name):
    text = name.lower()

    if any(
        keyword in text
        for keyword in VERY_HIGH_GOLD_EVENTS
    ):
        return "VERY HIGH"

    if any(
        keyword in text
        for keyword in HIGH_GOLD_EVENTS
    ):
        return "HIGH"

    return "MODERATE"


def format_countdown(minutes):
    if minutes < 0:
        return "EVENT PASSED"

    total_minutes = int(minutes)
    days, remainder = divmod(total_minutes, 1440)
    hours, mins = divmod(remainder, 60)

    if days:
        return f"{days}d {hours}h {mins}m"

    if hours:
        return f"{hours}h {mins}m"

    return f"{mins}m"


print("Biquote — Gold Event Risk Detector\n")

with urllib.request.urlopen(URL, timeout=15) as response:
    events = json.loads(
        response.read().decode("utf-8")
    )

now_utc = datetime.now(timezone.utc)

future_events = []

for event in events:

    event_time_text = event.get("time")

    if not event_time_text:
        continue

    event_time = parse_event_time(event_time_text)

    minutes_until = (
        event_time - now_utc
    ).total_seconds() / 60

    if minutes_until < 0:
        continue

    relevance = gold_relevance(
        event.get("name", "")
    )

    future_events.append({
        "name": event.get("name", "Unknown"),
        "time": event_time,
        "minutes": minutes_until,
        "relevance": relevance,
        "forecast": event.get("forecast"),
        "previous": event.get("previous"),
    })


future_events.sort(
    key=lambda item: item["time"]
)


def event_risk(event):
    minutes = event["minutes"]
    relevance = event["relevance"]

    if relevance == "VERY HIGH":

        if minutes <= 30:
            return "IMMINENT EVENT RISK"

        if minutes <= 120:
            return "HIGH EVENT RISK"

        if minutes <= 360:
            return "EVENT WATCH"

    if relevance == "HIGH":

        if minutes <= 15:
            return "IMMINENT EVENT RISK"

        if minutes <= 60:
            return "HIGH EVENT RISK"

        if minutes <= 180:
            return "EVENT WATCH"

    return "NORMAL"


print(
    "Current UTC:    "
    f"{now_utc.strftime('%Y-%m-%d %H:%M:%S')}"
)

print(
    "Current Cyprus: "
    f"{now_utc.astimezone(CYPRUS_TZ).strftime('%Y-%m-%d %H:%M:%S %Z')}"
)

print("\n========== UPCOMING EVENTS ==========")


overall_risk = "NORMAL"

risk_rank = {
    "NORMAL": 0,
    "EVENT WATCH": 1,
    "HIGH EVENT RISK": 2,
    "IMMINENT EVENT RISK": 3,
}


for event in future_events:

    risk = event_risk(event)

    if risk_rank[risk] > risk_rank[overall_risk]:
        overall_risk = risk

    cyprus_time = event["time"].astimezone(
        CYPRUS_TZ
    )

    print("\n--------------------------------")

    print(f"Event: {event['name']}")

    print(
        "UTC: "
        f"{event['time'].strftime('%Y-%m-%d %H:%M')}"
    )

    print(
        "Cyprus: "
        f"{cyprus_time.strftime('%Y-%m-%d %H:%M %Z')}"
    )

    print(
        "Time left: "
        f"{format_countdown(event['minutes'])}"
    )

    print(
        f"Gold impact: {event['relevance']}"
    )

    print(
        f"Event risk: {risk}"
    )

    print(
        f"Forecast: {event['forecast']}"
    )

    print(
        f"Previous: {event['previous']}"
    )


print("\n================================")
print(f"OVERALL GOLD EVENT RISK: {overall_risk}")
print("================================")
