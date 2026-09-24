"""Event-aware gold chart for Version 9.0."""

from __future__ import annotations

from datetime import date, time

import pandas as pd
import plotly.graph_objects as go


def manual_event_frame(enabled: bool, event_date: date, event_time: time,
                       name: str) -> pd.DataFrame:
    columns = ["timestamp", "source", "event", "impact"]
    if not enabled:
        return pd.DataFrame(columns=columns)
    timestamp = pd.Timestamp.combine(event_date, event_time)
    timestamp = timestamp.tz_localize("UTC")
    names = [item.strip() for item in name.splitlines() if item.strip()]
    if not names:
        names = ["Three-star USD event"]
    return pd.DataFrame([{
        "timestamp": timestamp,
        "source": "Investing.com (manual)",
        "event": item,
        "impact": 3,
    } for item in names], columns=columns)


def combine_chart_events(official: pd.DataFrame,
                         manual: pd.DataFrame) -> pd.DataFrame:
    frames = [frame for frame in (official, manual) if not frame.empty]
    if not frames:
        return pd.DataFrame(
            columns=["timestamp", "source", "event", "impact"])
    events = pd.concat(frames, ignore_index=True)
    events["timestamp"] = pd.to_datetime(events["timestamp"], utc=True)
    return events.drop_duplicates(
        ["timestamp", "source", "event"]).sort_values("timestamp")


def event_price_chart(gold: pd.DataFrame, events: pd.DataFrame,
                      bars: int = 192) -> go.Figure:
    prices = gold.tail(bars).copy()
    fig = go.Figure(go.Candlestick(
        x=prices.index,
        open=prices["open"], high=prices["high"],
        low=prices["low"], close=prices["close"],
        name="XAU/USD",
        increasing_line_color="#18a558",
        decreasing_line_color="#e53935",
    ))
    start = pd.Timestamp(prices.index.min())
    end = pd.Timestamp(prices.index.max())
    start = start.tz_localize("UTC") if start.tzinfo is None else start.tz_convert("UTC")
    end = end.tz_localize("UTC") if end.tzinfo is None else end.tz_convert("UTC")
    visible_end = end
    if not events.empty:
        selected = events[
            (events.timestamp >= start) &
            (events.timestamp <= end + pd.Timedelta(hours=4))].tail(20)
        for timestamp, simultaneous in selected.groupby("timestamp", sort=True):
            manual = simultaneous.source.astype(str).str.startswith(
                "Investing.com").any()
            color = "#ffd600" if manual else "#e53935"
            width = 3 if manual else 2
            names = " / ".join(dict.fromkeys(
                simultaneous.event.astype(str).tolist()))
            label = f"{'★ ★ ★ ' if manual else ''}{names} · {timestamp:%H:%M GMT}"
            fig.add_vline(
                x=timestamp.to_pydatetime(), line_color=color,
                line_width=width, line_dash="solid" if manual else "dash")
            fig.add_annotation(
                x=timestamp.to_pydatetime(), y=1, yref="paper",
                text=label, showarrow=True, arrowhead=2,
                bgcolor=color, font={"color": "#111", "size": 10},
                textangle=-90, yanchor="top")
            visible_end = max(visible_end, timestamp)
    fig.update_layout(
        height=570, margin={"l": 20, "r": 20, "t": 35, "b": 20},
        xaxis_title="Time (GMT/UTC)", yaxis_title="Gold price (USD)",
        xaxis_rangeslider_visible=False, template="plotly_white",
        hovermode="x unified", showlegend=False,
    )
    fig.update_xaxes(range=[start, visible_end + pd.Timedelta(minutes=30)])
    return fig
