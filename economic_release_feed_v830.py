"""Licensed machine-readable economic releases for Gold Version 8.3.0."""
from __future__ import annotations

from dataclasses import dataclass
import json
from urllib.parse import quote, urlencode
from urllib.request import urlopen

import numpy as np
import pandas as pd


TE_API = "https://api.tradingeconomics.com/calendar/country/united%20states"


@dataclass
class ReleaseSignal:
    state: str
    direction: str
    event: str
    timestamp: pd.Timestamp | None
    actual: str
    forecast: str
    previous: str
    surprise: float
    confirmations: int
    explanation: str


def download_us_high_impact(api_key: str, now=None,
                            days_back: int = 2,
                            days_forward: int = 7) -> pd.DataFrame:
    if not api_key:
        return pd.DataFrame()
    now = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    if now.tzinfo is None:
        now = now.tz_localize("UTC")
    start = (now - pd.Timedelta(days=days_back)).strftime("%Y-%m-%d")
    end = (now + pd.Timedelta(days=days_forward)).strftime("%Y-%m-%d")
    query = urlencode({"c": api_key, "importance": 3,
                       "values": "true", "f": "json"})
    url = f"{TE_API}/{start}/{end}?{query}"
    with urlopen(url, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if isinstance(payload, dict) and payload.get("error"):
        raise RuntimeError(str(payload.get("error")))
    return normalize_te_calendar(payload)


def normalize_te_calendar(payload) -> pd.DataFrame:
    rows = []
    for item in payload if isinstance(payload, list) else []:
        rows.append({
            "calendar_id": str(item.get("CalendarId", "")),
            "timestamp": pd.to_datetime(item.get("Date"), utc=True,
                                        errors="coerce"),
            "event": str(item.get("Event") or item.get("Category") or ""),
            "category": str(item.get("Category", "")),
            "importance": pd.to_numeric(item.get("Importance"), errors="coerce"),
            "actual": str(item.get("Actual") or ""),
            "previous": str(item.get("Previous") or ""),
            "forecast": str(item.get("Forecast") or ""),
            "revised": str(item.get("Revised") or ""),
            "actual_value": pd.to_numeric(item.get("ActualValue"), errors="coerce"),
            "previous_value": pd.to_numeric(item.get("PreviousValue"), errors="coerce"),
            "forecast_value": pd.to_numeric(item.get("ForecastValue"), errors="coerce"),
            "unit": str(item.get("Unit") or ""),
            "source": str(item.get("Source") or ""),
            "date_exact": str(item.get("DateSpan", "0")) == "0",
        })
    if not rows:
        return pd.DataFrame(columns=["timestamp", "event", "importance"])
    return (pd.DataFrame(rows).dropna(subset=["timestamp"])
            .drop_duplicates(["calendar_id", "timestamp"], keep="last")
            .sort_values("timestamp"))


def release_lock(events: pd.DataFrame, now=None,
                 before_minutes: int = 60,
                 after_minutes: int = 30):
    now = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    if now.tzinfo is None:
        now = now.tz_localize("UTC")
    if events is None or events.empty:
        return False, pd.DataFrame() if events is None else events.iloc[0:0]
    nearby = events[(events.timestamp >= now - pd.Timedelta(minutes=after_minutes)) &
                    (events.timestamp <= now + pd.Timedelta(minutes=before_minutes))]
    return not nearby.empty, nearby.copy()


def _gold_response_sign(event: str) -> int:
    """+1 means a positive data surprise is commonly gold-positive."""
    name = event.lower()
    positive_for_gold = ("unemployment rate", "jobless claims", "layoff")
    negative_for_gold = (
        "non farm", "nonfarm", "payroll", "cpi", "inflation", "pce",
        "producer price", "ppi", "wage", "earnings", "gdp", "retail sales",
        "ism", "pmi", "industrial production", "interest rate")
    if any(term in name for term in positive_for_gold):
        return 1
    if any(term in name for term in negative_for_gold):
        return -1
    return 0


def _confirmation_count(confirmations, direction: str) -> int:
    count = 0
    frames = confirmations or {}
    dollar = frames.get("dollar_uup")
    treasury = frames.get("treasury_tlt")
    if dollar is not None and len(dollar) >= 2:
        move = dollar.close.pct_change().iloc[-1]
        count += int(move < 0) if direction == "GOLD UP" else int(move > 0)
    if treasury is not None and len(treasury) >= 2:
        move = treasury.close.pct_change().iloc[-1]
        count += int(move > 0) if direction == "GOLD UP" else int(move < 0)
    return count


def latest_release_signal(events: pd.DataFrame, confirmations=None, now=None,
                          post_release_minutes: int = 30) -> ReleaseSignal:
    now = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    if now.tzinfo is None:
        now = now.tz_localize("UTC")
    if events is None or events.empty:
        return ReleaseSignal("UNAVAILABLE", "UNKNOWN", "", None, "", "", "",
                             np.nan, 0, "licensed economic feed is unavailable")
    recent = events[(events.timestamp <= now) &
                    (events.timestamp >= now - pd.Timedelta(minutes=post_release_minutes))]
    if recent.empty:
        future = events[events.timestamp > now].head(1)
        if future.empty:
            return ReleaseSignal("CLEAR", "UNKNOWN", "", None, "", "", "",
                                 np.nan, 0, "no nearby high-impact US release")
        row = future.iloc[0]
        return ReleaseSignal("UPCOMING", "UNKNOWN", row.event, row.timestamp,
                             row.actual, row.forecast, row.previous, np.nan, 0,
                             "actual value has not been released; direction cannot be known")
    row = recent.iloc[-1]
    actual, forecast = row.actual_value, row.forecast_value
    if not np.isfinite(actual) or not np.isfinite(forecast):
        return ReleaseSignal("AWAITING ACTUAL", "UNKNOWN", row.event, row.timestamp,
                             row.actual, row.forecast, row.previous, np.nan, 0,
                             "release occurred but numeric actual/forecast is incomplete")
    scale = max(abs(forecast), abs(row.previous_value)
                if np.isfinite(row.previous_value) else 0, 1e-9)
    surprise = float((actual - forecast) / scale)
    response_sign = _gold_response_sign(f"{row.event} {row.category}")
    if response_sign == 0 or abs(surprise) < .002:
        direction = "UNKNOWN"
    else:
        direction = "GOLD UP" if response_sign * surprise > 0 else "GOLD DOWN"
    confirms = _confirmation_count(confirmations, direction) if direction != "UNKNOWN" else 0
    state = "CONFIRMED" if confirms >= 2 else "PRELIMINARY" if direction != "UNKNOWN" else "AMBIGUOUS"
    explanation = (
        "surprise implication confirmed by dollar and Treasury proxies"
        if state == "CONFIRMED" else
        "initial surprise implication; wait for dollar/yield confirmation"
        if state == "PRELIMINARY" else
        "event mapping or surprise is not sufficiently directional")
    return ReleaseSignal(state, direction, row.event, row.timestamp,
                         row.actual, row.forecast, row.previous,
                         surprise, confirms, explanation)


def display_events(events: pd.DataFrame) -> pd.DataFrame:
    if events is None or events.empty:
        return pd.DataFrame(columns=["Time (GMT)", "Event", "Actual", "Forecast",
                                     "Previous", "Importance", "Source"])
    shown = events.copy()
    shown["Time (GMT)"] = shown.timestamp.dt.strftime("%Y-%m-%d %H:%M GMT")
    return shown.rename(columns={"event": "Event", "actual": "Actual",
                                 "forecast": "Forecast", "previous": "Previous",
                                 "importance": "Importance", "source": "Source"})[
        ["Time (GMT)", "Event", "Actual", "Forecast", "Previous", "Importance", "Source"]]
