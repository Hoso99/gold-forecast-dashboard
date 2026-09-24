"""Free cross-venue XAU perpetual microstructure audit.

This is deliberately labelled as a proxy: Binance, Bybit and OKX XAU-USDT
perpetuals are not COMEX GC.  Public REST snapshots are used because a
Streamlit rerun is not a reliable home for permanent WebSocket connections.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import json
from typing import Any
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd


@dataclass
class VenueAudit:
    venue: str
    status: str
    symbol: str
    last_price: float
    book_imbalance: float
    trade_imbalance: float
    bias: str
    observations: int
    detail: str = ""


@dataclass
class PerpetualConsensus:
    status: str
    direction: str
    agreement: int
    live_venues: int
    confidence: str
    venues: list[VenueAudit]


def _get(url: str, timeout: float = 4.0) -> Any:
    request = Request(url, headers={"User-Agent": "Gold-Version-9.0/1.0"})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _imbalance(bids: list, asks: list) -> float:
    bid = sum(float(level[1]) for level in bids if len(level) >= 2)
    ask = sum(float(level[1]) for level in asks if len(level) >= 2)
    return (bid - ask) / (bid + ask) if bid + ask > 0 else np.nan


def _finish(venue: str, symbol: str, bids: list, asks: list,
            signed_sizes: list[tuple[float, float]], price: float) -> VenueAudit:
    book = _imbalance(bids, asks)
    bought = sum(size for sign, size in signed_sizes if sign > 0)
    sold = sum(size for sign, size in signed_sizes if sign < 0)
    trade = (bought - sold) / (bought + sold) if bought + sold > 0 else np.nan
    values = [x for x in (book, trade) if np.isfinite(x)]
    score = float(np.mean(values)) if values else 0.0
    bias = "BUY PRESSURE" if score >= .15 else (
        "SELL PRESSURE" if score <= -.15 else "NEUTRAL")
    return VenueAudit(venue, "LIVE", symbol, float(price), float(book),
                      float(trade), bias, len(signed_sizes))


def parse_binance(book: dict, trades: list[dict]) -> VenueAudit:
    signed = [(-1.0 if trade.get("m") else 1.0, float(trade["q"]))
              for trade in trades]
    price = float(trades[-1]["p"]) if trades else np.nan
    return _finish("Binance", "XAUUSDT", book.get("bids", []),
                   book.get("asks", []), signed, price)


def parse_bybit(book: dict, trades: dict) -> VenueAudit:
    result = book.get("result", {})
    rows = trades.get("result", {}).get("list", [])
    signed = [(1.0 if str(row.get("side", "")).lower() == "buy" else -1.0,
               float(row["size"])) for row in rows]
    price = float(rows[0]["price"]) if rows else np.nan
    return _finish("Bybit", "XAUUSDT", result.get("b", []),
                   result.get("a", []), signed, price)


def parse_okx(book: dict, trades: dict) -> VenueAudit:
    snapshot = (book.get("data") or [{}])[0]
    rows = trades.get("data", [])
    signed = [(1.0 if str(row.get("side", "")).lower() == "buy" else -1.0,
               float(row["sz"])) for row in rows]
    price = float(rows[0]["px"]) if rows else np.nan
    return _finish("OKX", "XAU-USDT-SWAP", snapshot.get("bids", []),
                   snapshot.get("asks", []), signed, price)


def _collect_one(venue: str) -> VenueAudit:
    try:
        if venue == "Binance":
            book = _get("https://fapi.binance.com/fapi/v1/depth?symbol=XAUUSDT&limit=50")
            trades = _get("https://fapi.binance.com/fapi/v1/aggTrades?symbol=XAUUSDT&limit=100")
            return parse_binance(book, trades)
        if venue == "Bybit":
            base = "https://api.bybit.com/v5/market"
            book = _get(base + "/orderbook?category=linear&symbol=XAUUSDT&limit=50")
            trades = _get(base + "/recent-trade?category=linear&symbol=XAUUSDT&limit=100")
            return parse_bybit(book, trades)
        book = _get("https://www.okx.com/api/v5/market/books?instId=XAU-USDT-SWAP&sz=50")
        trades = _get("https://www.okx.com/api/v5/market/trades?instId=XAU-USDT-SWAP&limit=100")
        return parse_okx(book, trades)
    except Exception as exc:
        return VenueAudit(venue, "UNAVAILABLE", "", np.nan, np.nan, np.nan,
                          "UNKNOWN", 0, str(exc))


def collect_free_perpetual_consensus() -> PerpetualConsensus:
    with ThreadPoolExecutor(max_workers=3) as pool:
        venues = list(pool.map(_collect_one, ("Binance", "Bybit", "OKX")))
    live = [venue for venue in venues if venue.status == "LIVE"]
    buys = sum(venue.bias == "BUY PRESSURE" for venue in live)
    sells = sum(venue.bias == "SELL PRESSURE" for venue in live)
    agreement = max(buys, sells)
    direction = "BUY PRESSURE" if buys >= 2 and buys > sells else (
        "SELL PRESSURE" if sells >= 2 and sells > buys else "NO CONSENSUS")
    confidence = "HIGH" if agreement == 3 else (
        "MODERATE" if agreement == 2 else "LOW")
    status = "LIVE" if len(live) == 3 else ("PARTIAL" if live else "UNAVAILABLE")
    return PerpetualConsensus(status, direction, agreement, len(live),
                              confidence, venues)


def display_frame(consensus: PerpetualConsensus) -> pd.DataFrame:
    return pd.DataFrame([{
        "Venue": v.venue, "Status": v.status, "Contract": v.symbol or "N/A",
        "Last": v.last_price, "Book imbalance": v.book_imbalance,
        "Trade imbalance": v.trade_imbalance, "Pressure": v.bias,
        "Recent trades": v.observations,
    } for v in consensus.venues])
