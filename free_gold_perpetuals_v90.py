"""Free cross-venue XAU perpetual microstructure audit.

This is deliberately labelled as a proxy: crypto-venue XAU-USDT perpetuals
are not COMEX GC. Public REST snapshots are used because a Streamlit rerun is
not a reliable home for permanent WebSocket connections. Binance and Bybit
remain preferred; BingX and Gate are transparent fallbacks when a hosting
region cannot reach them.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import json
import math
from typing import Any
from urllib.error import HTTPError
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
    pressure_score: float = 0.0
    buying_power: float = 0.5
    selling_power: float = 0.5
    order_flow_decision: str = "WAIT"
    pressure_bias: str = "WAIT"


def _get(url: str, timeout: float = 3.5) -> Any:
    request = Request(url, headers={"User-Agent": "Gold-Version-9.0/1.0"})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _level_size(level: Any) -> float:
    if isinstance(level, dict):
        return float(level.get("s", level.get("size", level.get("qty", 0))))
    return float(level[1]) if len(level) >= 2 else 0.0


def _imbalance(bids: list, asks: list) -> float:
    bid = sum(_level_size(level) for level in bids)
    ask = sum(_level_size(level) for level in asks)
    return (bid - ask) / (bid + ask) if bid + ask > 0 else np.nan


def _finish(venue: str, symbol: str, bids: list, asks: list,
            signed_sizes: list[tuple[float, float]], price: float) -> VenueAudit:
    if not bids or not asks or not signed_sizes:
        raise ValueError("order book or recent trades are empty")
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


def parse_bingx(book: dict, trades: dict) -> VenueAudit:
    snapshot = book.get("data") or {}
    rows = trades.get("data") or []
    if isinstance(rows, dict):
        rows = rows.get("trades", rows.get("list", []))
    signed = []
    for row in rows:
        size = float(row.get("qty", row.get("quantity", row.get("size", 0))))
        maker = row.get("buyerMaker", row.get("isBuyerMaker"))
        side = str(row.get("side", "")).lower()
        sign = -1.0 if maker is True or side == "sell" else 1.0
        signed.append((sign, size))
    price = float(rows[0].get("price", rows[0].get("p"))) if rows else np.nan
    return _finish("BingX (fallback)", "XAU-USDT", snapshot.get("bids", []),
                   snapshot.get("asks", []), signed, price)


def parse_gate(book: dict, trades: list[dict]) -> VenueAudit:
    signed = []
    for row in trades:
        raw_size = float(row.get("size", row.get("amount", 0)))
        side = str(row.get("side", "")).lower()
        sign = -1.0 if raw_size < 0 or side == "sell" else 1.0
        signed.append((sign, abs(raw_size)))
    price = float(trades[0].get("price")) if trades else np.nan
    return _finish("Gate (fallback)", "XAU_USDT", book.get("bids", []),
                   book.get("asks", []), signed, price)


def parse_mexc(book: dict, trades: dict, symbol: str = "GOLD_USDT") -> VenueAudit:
    depth = book.get("data", book)
    rows = trades.get("data", [])
    signed = [(1.0 if int(row.get("T", 0)) == 1 else -1.0,
               float(row["v"])) for row in rows if int(row.get("T", 0)) in (1, 2)]
    price = float(rows[0]["p"]) if rows else np.nan
    return _finish("MEXC", symbol, depth.get("bids", []), depth.get("asks", []),
                   signed, price)


def parse_bitget(book: dict, trades: dict, symbol: str = "XAUTUSDT") -> VenueAudit:
    depth = book.get("data", {})
    rows = trades.get("data", [])
    signed = [(1.0 if str(row.get("side", "")).lower() == "buy" else -1.0,
               float(row["size"])) for row in rows]
    price = float(rows[0]["price"]) if rows else np.nan
    return _finish("Bitget", symbol, depth.get("b", []), depth.get("a", []),
                   signed, price)


def parse_phemex(book: dict, trades: dict, symbol: str = "XAUUSDT") -> VenueAudit:
    depth = book.get("result", {}).get("book", {})
    rows = trades.get("result", {}).get("trades", [])
    signed = [(1.0 if str(row[1]).lower() == "buy" else -1.0, float(row[3]))
              for row in rows if len(row) >= 4]
    # Phemex legacy priceEp uses 1e-4 price units for most quoted contracts.
    price = float(rows[0][2]) / 10_000 if rows else np.nan
    return _finish("Phemex", symbol, depth.get("bids", []), depth.get("asks", []),
                   signed, price)


def parse_kraken(book: dict, trades: dict) -> VenueAudit:
    book_result = book.get("result", {})
    trade_result = trades.get("result", {})
    depth = next(iter(book_result.values()), {})
    rows = next((value for key, value in trade_result.items()
                 if key != "last" and isinstance(value, list)), [])
    signed = [(1.0 if str(row[3]).lower() == "b" else -1.0, float(row[1]))
              for row in rows if len(row) >= 4]
    price = float(rows[-1][0]) if rows else np.nan
    return _finish("Kraken (fallback)", "XAUT/USD", depth.get("bids", []),
                   depth.get("asks", []), signed, price)


def parse_coinbase(book: dict, trades: list[dict]) -> VenueAudit:
    # Coinbase reports the resting maker side, so aggressor direction is inverse.
    signed = [(1.0 if str(row.get("side", "")).lower() == "sell" else -1.0,
               float(row["size"])) for row in trades]
    price = float(trades[0]["price"]) if trades else np.nan
    return _finish("Coinbase PAXG (fallback)", "PAXG-USD",
                   book.get("bids", []), book.get("asks", []), signed, price)


def _error_detail(exc: Exception) -> str:
    if isinstance(exc, HTTPError):
        if exc.code in (403, 451):
            return f"HTTP {exc.code}: venue blocks this cloud region"
        return f"HTTP {exc.code}: {exc.reason}"
    return f"{type(exc).__name__}: {exc}"


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
        if venue == "OKX":
            book = _get("https://www.okx.com/api/v5/market/books?instId=XAU-USDT-SWAP&sz=50")
            trades = _get("https://www.okx.com/api/v5/market/trades?instId=XAU-USDT-SWAP&limit=100")
            return parse_okx(book, trades)
        if venue == "BingX":
            base = "https://open-api.bingx.com/openApi/swap/v2/quote"
            book = _get(base + "/depth?symbol=XAU-USDT&limit=50")
            trades = _get(base + "/trades?symbol=XAU-USDT&limit=100")
            return parse_bingx(book, trades)
        if venue == "MEXC":
            base = "https://contract.mexc.com/api/v1/contract"
            last_error = None
            for symbol in ("GOLD_USDT", "XAU_USDT"):
                try:
                    return parse_mexc(
                        _get(f"{base}/depth/{symbol}?limit=50"),
                        _get(f"{base}/deals/{symbol}?limit=100"), symbol)
                except Exception as exc:
                    last_error = exc
            raise last_error or ValueError("no supported gold contract")
        if venue == "Bitget":
            base = "https://api.bitget.com/api/v3/market"
            last_error = None
            for symbol in ("XAUUSDT", "GOLDUSDT", "XAUTUSDT"):
                try:
                    query = f"category=USDT-FUTURES&symbol={symbol}&limit="
                    return parse_bitget(
                        _get(f"{base}/orderbook?{query}50"),
                        _get(f"{base}/fills?{query}100"), symbol)
                except Exception as exc:
                    last_error = exc
            raise last_error or ValueError("no supported gold contract")
        if venue == "Phemex":
            last_error = None
            for symbol in ("XAUUSDT", "GOLDUSDT", "XAUUSD"):
                try:
                    return parse_phemex(
                        _get(f"https://api.phemex.com/md/orderbook?symbol={symbol}"),
                        _get(f"https://api.phemex.com/md/trade?symbol={symbol}"), symbol)
                except Exception as exc:
                    last_error = exc
            raise last_error or ValueError("no supported gold contract")
        if venue == "Kraken":
            base = "https://api.kraken.com/0/public"
            return parse_kraken(
                _get(base + "/Depth?pair=XAUTUSD&count=50"),
                _get(base + "/Trades?pair=XAUTUSD&count=100"))
        if venue == "Coinbase":
            base = "https://api.exchange.coinbase.com/products/PAXG-USD"
            return parse_coinbase(
                _get(base + "/book?level=2"),
                _get(base + "/trades?limit=100"))
        base = "https://api.gateio.ws/api/v4/futures/usdt"
        book = _get(base + "/order_book?contract=XAU_USDT&limit=50")
        trades = _get(base + "/trades?contract=XAU_USDT&limit=100")
        return parse_gate(book, trades)
    except Exception as exc:
        return VenueAudit(venue, "UNAVAILABLE", "", np.nan, np.nan, np.nan,
                          "UNKNOWN", 0, _error_detail(exc))


def _collect_slot(preferred: str, fallback: str | None = None) -> VenueAudit:
    primary = _collect_one(preferred)
    if primary.status == "LIVE" or fallback is None:
        return primary
    replacement = _collect_one(fallback)
    if replacement.status == "LIVE":
        replacement.detail = f"Used because {preferred} failed: {primary.detail}"
        return replacement
    primary.detail = (
        f"Primary failed: {primary.detail}; {fallback} fallback failed: "
        f"{replacement.detail}")
    return primary


def collect_free_perpetual_consensus() -> PerpetualConsensus:
    # Four XAU perpetual venues plus two tokenized-gold spot venues. The latter
    # are explicitly labelled and contribute only observable book/trade flow.
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = (
            pool.submit(_collect_slot, "Gate"),
            pool.submit(_collect_slot, "OKX"),
            pool.submit(_collect_slot, "MEXC"),
            pool.submit(_collect_slot, "Bitget"),
            pool.submit(_collect_slot, "Kraken"),
            pool.submit(_collect_slot, "Coinbase"),
        )
        venues = [future.result() for future in futures]
    live = [venue for venue in venues if venue.status == "LIVE"]
    buys = sum(venue.bias == "BUY PRESSURE" for venue in live)
    sells = sum(venue.bias == "SELL PRESSURE" for venue in live)
    agreement = max(buys, sells)
    required = 3
    direction = "BUY PRESSURE" if buys >= required and buys > sells else (
        "SELL PRESSURE" if sells >= required and sells > buys else "NO CONSENSUS")
    ratio = agreement / len(live) if live else 0.0
    confidence = "HIGH" if agreement >= 4 and ratio >= 2 / 3 else (
        "MODERATE" if agreement >= 3 else "LOW")
    status = "LIVE" if len(live) == 6 else ("PARTIAL" if live else "UNAVAILABLE")
    # Aggressive trades receive more weight than displayed book depth because
    # resting orders can be cancelled. Equal venue weighting prevents one
    # exchange from dominating solely because its contract is more active.
    venue_scores = []
    for venue in live:
        book = venue.book_imbalance if np.isfinite(venue.book_imbalance) else 0.0
        trades = venue.trade_imbalance if np.isfinite(venue.trade_imbalance) else 0.0
        venue_scores.append(.35 * book + .65 * trades)
    pressure = float(np.clip(np.median(venue_scores), -1, 1)) if venue_scores else 0.0
    buying = float((pressure + 1) / 2)
    selling = float(1 - buying)
    # A directional call needs two live venues, material pressure and at least
    # two venue labels agreeing. Otherwise the observable order flow is noise.
    order_flow_decision = "WAIT"
    confirmed_side = 1 if direction == "BUY PRESSURE" else (
        -1 if direction == "SELL PRESSURE" else 0)
    agreeing = [venue for venue in live if (
        venue.bias == ("BUY PRESSURE" if confirmed_side > 0 else "SELL PRESSURE"))]
    aggressive_confirmations = sum(
        np.isfinite(venue.trade_imbalance) and
        np.sign(venue.trade_imbalance) == confirmed_side and
        abs(venue.trade_imbalance) >= .15
        for venue in agreeing)
    if confirmed_side and len(agreeing) >= 3 and aggressive_confirmations >= 3:
        order_flow_decision = "BUY" if confirmed_side > 0 else "SELL"
    # Earlier directional information for the UI. This is deliberately easier
    # to trigger than the confirmed decision and is never an execution approval.
    pressure_bias = "WAIT"
    if len(live) >= 3 and abs(pressure) >= .10:
        pressure_bias = "BUY" if pressure > 0 else "SELL"
    return PerpetualConsensus(
        status, direction, agreement, len(live), confidence, venues,
        pressure, buying, selling, order_flow_decision, pressure_bias)


def display_frame(consensus: PerpetualConsensus) -> pd.DataFrame:
    return pd.DataFrame([{
        "Venue": v.venue, "Status": v.status, "Contract": v.symbol or "N/A",
        "Last": v.last_price, "Book imbalance": v.book_imbalance,
        "Trade imbalance": v.trade_imbalance, "Pressure": v.bias,
        "Recent trades": v.observations, "Connection detail": v.detail or "Direct",
    } for v in consensus.venues])
