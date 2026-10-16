"""Read-only XOOMAR US calendar freshness and coverage probe. No live/PAPER integration."""
import datetime as dt
import json
from urllib.request import Request, urlopen

UTC = dt.timezone.utc
URL = "https://xoomar.com/api/markets/calendar?importance=high"
CRITICAL = {"CPI": ("cpi",), "NFP": ("nonfarm", "payroll"),
            "FOMC": ("fomc",), "PCE": ("pce", "personal income"),
            "GDP": ("gdp",), "ISM": ("ism",), "OIL_INVENTORIES": ("crude oil", "petroleum", "oil inventories", "eia")}
def parse(value):
    if not isinstance(value, str):
        raise ValueError("missing timestamp")
    d = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if d.tzinfo is None:
        raise ValueError("timestamp lacks timezone")
    return d.astimezone(UTC)

def probe(now=None):
    now = now or dt.datetime.now(UTC)
    with urlopen(Request(URL, headers={"User-Agent":"V95-research-calendar-probe/1.0"}), timeout=15) as resp:
        payload = json.load(resp)
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise ValueError("invalid response structure")
    updated = parse(payload.get("updatedAt"))
    age_hours = (now-updated).total_seconds()/3600
    events = payload["data"]
    names = [str(e.get("eventName", "")).lower() for e in events if isinstance(e, dict)]
    coverage = {label: any(any(term in name for term in terms) for name in names) for label,terms in CRITICAL.items()}
    bad_dates = sum(1 for e in events if not isinstance(e,dict) or not isinstance(e.get("scheduledAt"),str) or not e["scheduledAt"].endswith("Z"))
    next_at = payload.get("nextReleaseAt")
    next_past = next_at is not None and parse(next_at) < now
    # Stale schedule, invalid UTC, or missing categories -> NEVER clear news gate.
    validated = bool(events) and 0 <= age_hours <= 24 and bad_dates == 0 and not next_past and all(coverage.values())
    return {"source":"XOOMAR_READ_ONLY_PROBE", "events":len(events),
            "updated_at":updated.isoformat(), "age_hours":round(age_hours,2),
            "next_release_in_past":next_past,"non_utc_or_invalid_dates":bad_dates,
            "category_coverage_in_returned_window":coverage,
            "safe_to_activate":validated}

if __name__ == "__main__":
    try:
        print(json.dumps(probe(), indent=2, sort_keys=True))
    except Exception as exc:
        print(json.dumps({"safe_to_activate":False,"error_type":type(exc).__name__}))
