"""Validation and features for locally collected synthetic gold footprints."""
from __future__ import annotations

from dataclasses import dataclass
import io
import os
import sqlite3

import numpy as np
import pandas as pd


REQUIRED_COLUMNS = {"timestamp", "venue", "symbol", "price", "size", "aggressor_side"}


@dataclass
class FootprintAudit:
    status: str = "UNAVAILABLE"
    signal: str = "NONE"
    score: float = 0.0
    buy_volume: float = 0.0
    sell_volume: float = 0.0
    delta: float = 0.0
    delta_pct: float = 0.0
    confirming_venues: int = 0
    live_venues: int = 0
    stacked_buy_levels: int = 0
    stacked_sell_levels: int = 0
    window_start: object = None
    window_end: object = None
    latest_trade: object = None
    detail: str = "No footprint source was supplied."
    venue_summary: object = None
    candle_summary: object = None
    ten_bar_buy_volume: float = 0.0
    ten_bar_sell_volume: float = 0.0
    ten_bar_delta: float = 0.0
    ten_bar_delta_pct: float = 0.0
    ten_bar_signal: str = "NONE"
    ten_bar_score: float = 0.0


def _read_source(source):
    if source is None:
        return pd.DataFrame()
    if isinstance(source, pd.DataFrame):
        return source.copy()
    if hasattr(source, "read"):
        raw = source.getvalue() if hasattr(source, "getvalue") else source.read()
        return pd.read_csv(io.BytesIO(raw) if isinstance(raw, bytes) else io.StringIO(raw))
    path = os.fspath(source)
    if not os.path.exists(path):
        return pd.DataFrame()
    if path.lower().endswith((".sqlite", ".db")):
        with sqlite3.connect(path) as connection:
            return pd.read_sql_query(
                "SELECT timestamp, venue, symbol, price, size, aggressor_side "
                "FROM trades ORDER BY timestamp DESC LIMIT 250000", connection)
    return pd.read_csv(path)


def analyze_footprint(source, as_of=None, interval="15min", min_venues=3,
                      imbalance_threshold=.15, level_ratio=3.0,
                      history_bars=10):
    """Analyze the latest completed interval of tick-by-tick aggressor trades."""
    try:
        trades = _read_source(source)
    except Exception as exc:
        return FootprintAudit(detail=f"Could not read footprint source: {exc}")
    if trades.empty:
        return FootprintAudit()
    missing = REQUIRED_COLUMNS.difference(trades.columns)
    if missing:
        return FootprintAudit(
            status="INVALID", detail=f"Missing columns: {', '.join(sorted(missing))}")
    trades = trades.copy()
    trades["timestamp"] = pd.to_datetime(trades.timestamp, utc=True, errors="coerce")
    trades["price"] = pd.to_numeric(trades.price, errors="coerce")
    trades["size"] = pd.to_numeric(trades["size"], errors="coerce").abs()
    trades["aggressor_side"] = trades.aggressor_side.astype(str).str.upper()
    trades = trades.dropna(subset=["timestamp", "price", "size"])
    trades = trades[
        trades.aggressor_side.isin(["BUY", "SELL"]) & trades["size"].gt(0)]
    if trades.empty:
        return FootprintAudit(status="INVALID", detail="No valid BUY/SELL trades were found.")
    now = pd.Timestamp(as_of) if as_of is not None else pd.Timestamp.now(tz="UTC")
    now = now.tz_localize("UTC") if now.tzinfo is None else now.tz_convert("UTC")
    end = now.floor(interval)
    start = end - pd.Timedelta(interval)
    history_start = end - pd.Timedelta(interval) * int(history_bars)
    history = trades[(trades.timestamp >= history_start) &
                     (trades.timestamp < end)].copy()
    if not history.empty:
        history["buy_size"] = history["size"].where(
            history.aggressor_side.eq("BUY"), 0.0)
        history["sell_size"] = history["size"].where(
            history.aggressor_side.eq("SELL"), 0.0)
        history["candle"] = history.timestamp.dt.floor(interval)
        venue_candles = history.groupby(
            ["candle", "venue"], as_index=False).agg(
                buy_volume=("buy_size", "sum"),
                sell_volume=("sell_size", "sum"), trades=("size", "size"))
        venue_candles["total"] = (
            venue_candles.buy_volume + venue_candles.sell_volume)
        venue_candles["delta_pct"] = np.where(
            venue_candles.total > 0,
            (venue_candles.buy_volume - venue_candles.sell_volume) /
            venue_candles.total, 0.0)
        candle_summary = venue_candles.groupby("candle", as_index=False).agg(
            buy_volume=("buy_volume", "sum"),
            sell_volume=("sell_volume", "sum"),
            normalized_delta=("delta_pct", "median"),
            live_venues=("venue", "nunique"), trades=("trades", "sum"))
        candle_summary["delta"] = (
            candle_summary.buy_volume - candle_summary.sell_volume)
        candle_summary["delta_pct"] = np.where(
            candle_summary.buy_volume + candle_summary.sell_volume > 0,
            candle_summary.delta /
            (candle_summary.buy_volume + candle_summary.sell_volume), 0.0)
        candle_summary["direction"] = np.where(
            candle_summary.normalized_delta >= .10, "BUY",
            np.where(candle_summary.normalized_delta <= -.10, "SELL", "NEUTRAL"))
        candle_summary = candle_summary.sort_values("candle")
        ten_buy = float(history.buy_size.sum())
        ten_sell = float(history.sell_size.sum())
        ten_delta = ten_buy - ten_sell
        ten_delta_pct = ten_delta / (ten_buy + ten_sell) if ten_buy + ten_sell else 0.0
        venue_history = history.groupby("venue", as_index=False).agg(
            buy_volume=("buy_size", "sum"), sell_volume=("sell_size", "sum"))
        venue_history["total"] = venue_history.buy_volume + venue_history.sell_volume
        venue_history["delta_pct"] = np.where(
            venue_history.total > 0,
            (venue_history.buy_volume - venue_history.sell_volume) /
            venue_history.total, 0.0)
        ten_score = float(np.clip(np.median(venue_history.delta_pct), -1, 1))
        ten_signal = "BUY" if ten_score >= .10 else (
            "SELL" if ten_score <= -.10 else "NONE")
    else:
        candle_summary = pd.DataFrame()
        ten_buy = ten_sell = ten_delta = ten_delta_pct = ten_score = 0.0
        ten_signal = "NONE"
    sample = trades[(trades.timestamp >= start) & (trades.timestamp < end)].copy()
    latest = trades.timestamp.max()
    if sample.empty:
        return FootprintAudit(
            status="STALE", window_start=start, window_end=end, latest_trade=latest,
            detail="No trades exist for the latest completed 15-minute interval.",
            candle_summary=candle_summary, ten_bar_buy_volume=ten_buy,
            ten_bar_sell_volume=ten_sell, ten_bar_delta=ten_delta,
            ten_bar_delta_pct=float(ten_delta_pct), ten_bar_signal=ten_signal,
            ten_bar_score=ten_score)
    sample["buy_size"] = sample["size"].where(sample.aggressor_side.eq("BUY"), 0.0)
    sample["sell_size"] = sample["size"].where(sample.aggressor_side.eq("SELL"), 0.0)
    venues = sample.groupby("venue", as_index=False).agg(
        buy_volume=("buy_size", "sum"), sell_volume=("sell_size", "sum"),
        trades=("size", "size"), latest=("timestamp", "max"))
    venues["total"] = venues.buy_volume + venues.sell_volume
    venues["delta_pct"] = np.where(
        venues.total > 0, (venues.buy_volume - venues.sell_volume) / venues.total, 0.0)
    venues["direction"] = np.where(
        venues.delta_pct >= imbalance_threshold, "BUY",
        np.where(venues.delta_pct <= -imbalance_threshold, "SELL", "NEUTRAL"))
    buy_confirm = int(venues.direction.eq("BUY").sum())
    sell_confirm = int(venues.direction.eq("SELL").sum())
    preliminary_required = max(2, int(np.ceil(len(venues) * 2 / 3)))
    if buy_confirm >= min_venues and buy_confirm > sell_confirm:
        signal, confirmations, status = "BUY", buy_confirm, "CONFIRMED"
    elif sell_confirm >= min_venues and sell_confirm > buy_confirm:
        signal, confirmations, status = "SELL", sell_confirm, "CONFIRMED"
    elif buy_confirm >= preliminary_required and buy_confirm > sell_confirm:
        signal, confirmations, status = "BUY", buy_confirm, "PRELIMINARY"
    elif sell_confirm >= preliminary_required and sell_confirm > buy_confirm:
        signal, confirmations, status = "SELL", sell_confirm, "PRELIMINARY"
    else:
        signal, confirmations, status = (
            "NONE", max(buy_confirm, sell_confirm), "MONITORING")
    buy = float(sample.buy_size.sum())
    sell = float(sample.sell_size.sum())
    delta = buy - sell
    delta_pct = delta / (buy + sell) if buy + sell else 0.0
    # Price-level imbalance is calculated per venue to avoid mixing different
    # contract sizes and slightly different tokenized-gold prices.
    levels = sample.groupby(["venue", "price"], as_index=False).agg(
        bid_volume=("sell_size", "sum"), ask_volume=("buy_size", "sum"))
    levels["buy_ratio"] = levels.ask_volume / levels.bid_volume.replace(0, np.nan)
    levels["sell_ratio"] = levels.bid_volume / levels.ask_volume.replace(0, np.nan)
    stacked_buy = int(levels.buy_ratio.ge(level_ratio).sum())
    stacked_sell = int(levels.sell_ratio.ge(level_ratio).sum())
    score = float(np.clip(np.median(venues.delta_pct), -1, 1))
    if signal == "NONE":
        score = 0.0
    elif status == "PRELIMINARY":
        score *= .5
    return FootprintAudit(
        status=status,
        signal=signal, score=score, buy_volume=buy, sell_volume=sell,
        delta=delta, delta_pct=float(delta_pct), confirming_venues=confirmations,
        live_venues=int(len(venues)), stacked_buy_levels=stacked_buy,
        stacked_sell_levels=stacked_sell, window_start=start, window_end=end,
        latest_trade=latest,
        detail=(
            "Three-venue footprint confirmation passed."
            if status == "CONFIRMED" else
            "Two of three venues agree; preliminary indication contributes at half strength."
            if status == "PRELIMINARY" else
            "Fewer than two-thirds of live venues have material same-side delta."),
        venue_summary=venues,
        candle_summary=candle_summary,
        ten_bar_buy_volume=ten_buy, ten_bar_sell_volume=ten_sell,
        ten_bar_delta=ten_delta, ten_bar_delta_pct=float(ten_delta_pct),
        ten_bar_signal=ten_signal, ten_bar_score=ten_score,
    )
