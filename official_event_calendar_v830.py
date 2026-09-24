from __future__ import annotations

from io import StringIO
import re
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
import pandas as pd

UTC = ZoneInfo("UTC")
ET = ZoneInfo("America/New_York")
USER_AGENT = "Gold-Version-8.3-Research/1.0"

BLS_RELEASES = {
    "BLS CPI": "https://www.bls.gov/schedule/news_release/cpi.htm",
    "BLS Employment Situation": "https://www.bls.gov/schedule/news_release/empsit.htm",
    "BLS PPI": "https://www.bls.gov/schedule/news_release/ppi.htm",
}
BEA_SCHEDULE = "https://www.bea.gov/news/schedule"
FED_MONTH = "https://www.federalreserve.gov/newsevents/{year}-{month}.htm"


def _download(url):
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=20) as response:
        return response.read().decode("utf-8", "replace")


def _et_timestamp(date_text, time_text):
    value = pd.to_datetime(
        f"{date_text} {time_text}", errors="coerce")
    if pd.isna(value):
        return pd.NaT
    return value.tz_localize(ET, ambiguous="NaT", nonexistent="shift_forward").tz_convert(UTC)


def _bls_events():
    rows, status = [], {}
    for event, url in BLS_RELEASES.items():
        try:
            tables = pd.read_html(StringIO(_download(url)))
            table = next(t for t in tables if {
                "Release Date", "Release Time"}.issubset(t.columns))
            for _, item in table.drop_duplicates(
                    ["Release Date", "Release Time"]).iterrows():
                timestamp = _et_timestamp(
                    item["Release Date"], item["Release Time"])
                if pd.notna(timestamp):
                    rows.append({
                        "timestamp": timestamp, "source": "BLS",
                        "event": event, "impact": 3})
            status[event] = "loaded"
        except Exception as exc:
            status[event] = f"unavailable: {exc}"
    return rows, status


def _bea_events():
    rows, status = [], {}
    try:
        table = pd.read_html(StringIO(_download(BEA_SCHEDULE)))[0]
        date_column, event_column = table.columns[0], table.columns[-1]
        year_match = re.search(r"(20\d{2})", str(date_column))
        year = int(year_match.group(1)) if year_match else pd.Timestamp.now().year
        important = re.compile(
            r"GDP|Personal Income and Outlays|International Trade", re.I)
        for _, item in table.iterrows():
            event = str(item[event_column])
            if not important.search(event):
                continue
            text = str(item[date_column])
            match = re.match(
                r"([A-Za-z]+\s+\d+)\s+(\d{1,2}:\d{2}\s+[AP]M)", text)
            if not match:
                continue
            timestamp = _et_timestamp(
                f"{match.group(1)}, {year}", match.group(2))
            if pd.notna(timestamp):
                rows.append({
                    "timestamp": timestamp, "source": "BEA",
                    "event": event, "impact": 3})
        status["BEA high-impact releases"] = "loaded"
    except Exception as exc:
        status["BEA high-impact releases"] = f"unavailable: {exc}"
    return rows, status


def _fed_events(now):
    rows, status = [], {}
    local = pd.Timestamp(now).tz_convert(ET)
    url = FED_MONTH.format(
        year=local.year, month=local.strftime("%B").lower())
    wanted = re.compile(
        r"FOMC|Beige Book|Minutes|Press Conference|Speech", re.I)
    try:
        soup = BeautifulSoup(_download(url), "html.parser")
        for panel in soup.select("div.panel-body"):
            row = panel.select_one("div.row")
            if row is None:
                continue
            time_box = row.select_one("div.col-xs-2")
            event_box = row.select_one("div.col-xs-7")
            day_box = row.select_one("div.col-xs-3")
            if not (time_box and event_box and day_box):
                continue
            event = " ".join(event_box.stripped_strings)
            if not wanted.search(event):
                continue
            time_text = " ".join(time_box.stripped_strings)
            for day in re.findall(r"\b([0-3]?\d)\b", " ".join(day_box.stripped_strings)):
                timestamp = _et_timestamp(
                    f"{local.strftime('%B')} {day}, {local.year}",
                    time_text)
                if pd.notna(timestamp):
                    rows.append({
                        "timestamp": timestamp, "source": "Federal Reserve",
                        "event": event, "impact": 3})
        status["Federal Reserve calendar"] = (
            "loaded" if rows else "unavailable: no high-impact rows parsed")
    except Exception as exc:
        status["Federal Reserve calendar"] = f"unavailable: {exc}"
    return rows, status


def download_official_events(now=None):
    now = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    now = now.tz_localize("UTC") if now.tzinfo is None else now.tz_convert("UTC")
    rows, status = [], {}
    for loader in (_bls_events, _bea_events):
        part, audit = loader()
        rows.extend(part)
        status.update(audit)
    part, audit = _fed_events(now)
    rows.extend(part)
    status.update(audit)
    events = pd.DataFrame(rows)
    if events.empty:
        events = pd.DataFrame(
            columns=["timestamp", "source", "event", "impact"])
    else:
        events = events.drop_duplicates(
            ["timestamp", "source", "event"]).sort_values("timestamp")
    audit = pd.DataFrame([
        {"Source": key, "Status": value} for key, value in status.items()])
    return events, audit


def official_event_risk(events, now=None, before_minutes=60,
                        after_minutes=30):
    now = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    now = now.tz_localize("UTC") if now.tzinfo is None else now.tz_convert("UTC")
    if events.empty:
        return False, events.copy()
    lower = now - pd.Timedelta(minutes=after_minutes)
    upper = now + pd.Timedelta(minutes=before_minutes)
    nearby = events[
        (events.timestamp >= lower) & (events.timestamp <= upper)].copy()
    return not nearby.empty, nearby


def event_risk_notice(events, now=None, watch_hours=4):
    """Return a non-directional spike-risk state and the relevant events."""
    now = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    now = now.tz_localize("UTC") if now.tzinfo is None else now.tz_convert("UTC")
    if events.empty:
        return "CLEAR", events.copy()
    lock_start = now - pd.Timedelta(minutes=30)
    lock_end = now + pd.Timedelta(minutes=60)
    lockout = events[
        (events.timestamp >= lock_start) &
        (events.timestamp <= lock_end)].copy()
    if not lockout.empty:
        return "LOCKOUT", lockout
    watch = events[
        (events.timestamp > lock_end) &
        (events.timestamp <= now + pd.Timedelta(hours=watch_hours))].copy()
    if not watch.empty:
        return "ELEVATED", watch
    return "CLEAR", events.iloc[0:0].copy()


def format_events_gmt(events):
    shown = events.copy()
    if shown.empty:
        return shown
    shown["Time (GMT)"] = shown.timestamp.map(
        lambda value: pd.Timestamp(value).tz_convert("UTC").strftime(
            "%Y-%m-%d %H:%M GMT"))
    return shown[["Time (GMT)", "source", "event", "impact"]].rename(
        columns={"source": "Source", "event": "Event", "impact": "Impact"})
