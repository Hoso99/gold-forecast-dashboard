"""CME GC real-time microstructure audit for Gold Version 8.3.0.

The CME WebSocket product supplies trades and a conflated one-deep book.  This
module deliberately calls that data *top of book*, never Level 2.  Deeper
features must be supplied by a separately entitled MDP/Pub/Sub feed.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import time
from typing import Any

import numpy as np
import pandas as pd


CME_WS_URL = "wss://markets.api.cmegroup.com/marketdatastream/v1"


@dataclass
class CMEAudit:
    status: str
    as_of: pd.Timestamp | None
    symbol: str
    observations: int
    spread_ticks: float
    top_imbalance: float
    signed_volume_delta: float
    trade_count: int
    risk: str
    directional_bias: str
    reasons: list[str]
    frame: pd.DataFrame


def subscription_message(product_code: str = "GC") -> dict[str, Any]:
    return {
        "header": {"messageType": "SUBSCRIBE", "version": "1.0",
                   "requestId": "gold-v830"},
        "payload": {
            "subscriptionMessageTypes": ["TRD", "TOB", "STAT"],
            "subscriptions": [{"productType": "FUT",
                               "productCode": product_code}],
        },
    }


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return np.nan


def _level(levels: Any) -> tuple[float, float]:
    if not levels:
        return np.nan, np.nan
    item = levels[0] if isinstance(levels, list) else levels
    if not isinstance(item, dict):
        return np.nan, np.nan
    price = next((_number(item.get(k)) for k in
                  ("price", "mdEntryPx", "entryPrice") if k in item), np.nan)
    size = next((_number(item.get(k)) for k in
                 ("quantity", "qty", "mdEntrySize", "size") if k in item), np.nan)
    return price, size


def normalize_messages(messages: list[dict[str, Any]]) -> pd.DataFrame:
    """Normalize CME JSON without assuming that every optional field exists."""
    rows: list[dict[str, Any]] = []
    for message in messages:
        header = message.get("header", {})
        kind = str(header.get("messageType", "")).upper()
        sent = pd.to_datetime(header.get("sentTime"), utc=True, errors="coerce")
        payload = message.get("payload", [])
        if isinstance(payload, dict):
            payload = [payload]
        for item in payload if isinstance(payload, list) else []:
            instrument = item.get("instrument", {})
            base = {"timestamp": pd.to_datetime(
                        item.get("lastUpdateTime", sent), utc=True,
                        errors="coerce"),
                    "message_type": kind,
                    "symbol": str(instrument.get("symbol", "")),
                    "bid_price": np.nan, "bid_size": np.nan,
                    "ask_price": np.nan, "ask_size": np.nan,
                    "trade_price": np.nan, "trade_size": np.nan,
                    "aggressor": ""}
            if kind == "TOB":
                base["bid_price"], base["bid_size"] = _level(item.get("bidLevel"))
                base["ask_price"], base["ask_size"] = _level(item.get("askLevel"))
            elif kind == "TRD":
                trade = item.get("tradeSummary", {})
                base["trade_price"] = _number(trade.get("tradePrice"))
                base["trade_size"] = _number(trade.get("tradeQty"))
                base["aggressor"] = str(trade.get("aggressorSide", "")).upper()
            rows.append(base)
    if not rows:
        return pd.DataFrame(columns=[
            "timestamp", "message_type", "symbol", "bid_price", "bid_size",
            "ask_price", "ask_size", "trade_price", "trade_size", "aggressor"])
    return pd.DataFrame(rows).sort_values("timestamp", na_position="first")


def collect_cme_gc(access_token: str, seconds: int = 8,
                   url: str = CME_WS_URL) -> pd.DataFrame:
    """Collect a short entitled CME GC sample; token is never persisted."""
    if not access_token:
        raise ValueError("CME access token is missing")
    try:
        import websocket
    except ImportError as exc:
        raise RuntimeError("websocket-client is not installed") from exc
    ws = websocket.create_connection(
        url, header=[f"Authorization: Bearer {access_token}"], timeout=3)
    messages: list[dict[str, Any]] = []
    try:
        login = json.loads(ws.recv())
        status = str(login.get("payload", {}).get("status", "")).lower()
        if status != "authenticated":
            raise RuntimeError(f"CME authentication failed: {status or 'unknown'}")
        ws.send(json.dumps(subscription_message()))
        deadline = time.monotonic() + max(3, min(int(seconds), 30))
        while time.monotonic() < deadline:
            try:
                messages.append(json.loads(ws.recv()))
            except TimeoutError:
                continue
    finally:
        ws.close()
    return normalize_messages(messages)


def audit_microstructure(frame: pd.DataFrame, tick_size: float = .10,
                         now: pd.Timestamp | None = None) -> CMEAudit:
    now = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    if now.tzinfo is None:
        now = now.tz_localize("UTC")
    if frame is None or frame.empty:
        return CMEAudit("UNAVAILABLE", None, "", 0, np.nan, np.nan, np.nan,
                        0, "UNKNOWN", "NEUTRAL",
                        ["no entitled CME observations received"],
                        pd.DataFrame() if frame is None else frame)
    data = frame.copy()
    data["timestamp"] = pd.to_datetime(data.timestamp, utc=True, errors="coerce")
    data = data.dropna(subset=["timestamp"]).sort_values("timestamp")
    if data.empty:
        return audit_microstructure(pd.DataFrame(), tick_size, now)
    latest_time = data.timestamp.iloc[-1]
    reasons: list[str] = []
    age = (now - latest_time).total_seconds()
    status = "LIVE" if -10 <= age <= 30 else "STALE"
    if status == "STALE":
        reasons.append(f"latest CME observation is {max(0, age):.0f}s old")
    books = data[data.message_type.eq("TOB")].dropna(
        subset=["bid_price", "ask_price", "bid_size", "ask_size"])
    spread_ticks = imbalance = np.nan
    if not books.empty:
        last = books.iloc[-1]
        spread_ticks = (last.ask_price - last.bid_price) / tick_size
        total = last.bid_size + last.ask_size
        imbalance = ((last.bid_size - last.ask_size) / total
                     if total > 0 else np.nan)
        if spread_ticks >= 3:
            reasons.append("COMEX top-of-book spread is abnormally wide")
        if abs(imbalance) >= .70:
            reasons.append("COMEX top-of-book liquidity is strongly imbalanced")
    else:
        reasons.append("no valid GC top-of-book update")
    trades = data[data.message_type.eq("TRD")].dropna(subset=["trade_size"])
    signs = trades.aggressor.map({"B": 1, "BUY": 1, "1": 1,
                                  "S": -1, "SELL": -1, "2": -1}).fillna(0)
    delta = float((signs * trades.trade_size).sum()) if len(trades) else np.nan
    bias_score = (0 if not np.isfinite(imbalance) else imbalance)
    if np.isfinite(delta) and trades.trade_size.sum() > 0:
        bias_score += float(delta / trades.trade_size.sum())
    bias = "BUY PRESSURE" if bias_score >= .75 else (
        "SELL PRESSURE" if bias_score <= -.75 else "NEUTRAL")
    risk = "HIGH" if status != "LIVE" or spread_ticks >= 3 else (
        "ELEVATED" if abs(imbalance) >= .70 else "NORMAL")
    # This is an audit/risk gate only. Direction must earn weight through a
    # historical walk-forward test before it may alter forecast probability.
    reasons.append("microstructure direction has zero forecast weight pending validation")
    return CMEAudit(status, latest_time, str(data.symbol.iloc[-1]), len(data),
                    float(spread_ticks), float(imbalance), delta, len(trades),
                    risk, bias, reasons, data)
