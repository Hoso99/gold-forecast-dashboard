"""Observation-only Twelve Data vs completed Biquote M1 candle comparison.

Research-only. No broker actions, Telegram alerts, or writes to the candle DB.
Twelve Data WS quotes are sampled at most once every five seconds.
"""
import asyncio
import datetime as dt
import json
import math
import sqlite3
import time
from pathlib import Path
from urllib.parse import quote

import websockets

SYMBOL = "XAU/USD"
ENV = Path.home() / ".config/v95-research/monitor.env"
DB = Path(__file__).with_name("biquote_m1.sqlite3")
OBSERVE_SECONDS = 90
FINALIZE_SECONDS = 70
SAMPLE_SECONDS = 5


def load_key():
    for line in ENV.read_text(encoding="utf-8").splitlines():
        if line.startswith("TWELVE_DATA_API_KEY="):
            key = line.split("=", 1)[1].strip().strip('"').strip("'")
            if key:
                return key
    raise RuntimeError("Twelve Data API key is missing")


def utc_minute(timestamp):
    return dt.datetime.fromtimestamp(timestamp, dt.timezone.utc).replace(
        second=0, microsecond=0
    ).isoformat()


def read_candle(connection, minute):
    return connection.execute(
        "SELECT high, low, close, ticks FROM candles WHERE minute = ?",
        (minute,),
    ).fetchone()


def compare_samples(samples):
    """Read only completed Biquote candles; one DB lookup per unique minute."""
    matched = missing = invalid = outside = 0
    max_difference = 0.0
    with sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=5) as db:
        cache = {}
        for minute, price, timestamp in samples:
            if minute not in cache:
                cache[minute] = read_candle(db, minute)
            candle = cache[minute]
            if candle is None:
                missing += 1
                print(f"MISSING_CANDLE UTC={minute} TwelveData={price:.3f}")
                continue
            high, low, close, ticks = candle
            if not all(isinstance(v, (int, float)) and math.isfinite(v)
                       for v in (high, low, close, ticks)) or not (
                       0 < low <= high and low <= close <= high and ticks > 0):
                invalid += 1
                print(f"INVALID_CANDLE UTC={minute}")
                continue
            difference = max(low - price, 0.0, price - high)
            matched += 1
            outside += difference > 0
            max_difference = max(max_difference, difference)
            print(
                f"UTC={minute} TwelveData={price:.3f} "
                f"BiquoteLow={low:.3f} BiquoteHigh={high:.3f} "
                f"Difference={difference:.3f} Ticks={ticks}"
            )
    print(
        f"SUMMARY sampled={len(samples)} matched={matched} "
        f"missing={missing} invalid={invalid} outside_range={outside} "
        f"max_difference={max_difference:.3f}"
    )


async def collect():
    key = load_key()
    url = "wss://ws.twelvedata.com/v1/quotes/price?apikey=" + quote(key, safe="")
    samples = []
    last_sample_monotonic = float("-inf")
    deadline = time.monotonic() + OBSERVE_SECONDS
    print("Research-only XAU/USD quote observation starting", flush=True)
    try:
        async with websockets.connect(url, open_timeout=15) as ws:
            await ws.send(json.dumps({
                "action": "subscribe", "params": {"symbols": SYMBOL}
            }))
            while time.monotonic() < deadline:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=min(1, remaining))
                    event = json.loads(raw)
                except asyncio.TimeoutError:
                    continue
                except (json.JSONDecodeError, TypeError):
                    continue
                if not isinstance(event, dict):
                    continue
                if event.get("event") == "subscribe-status":
                    if event.get("status") in ("error", "failed") or event.get("fails"):
                        print("SUBSCRIPTION_FAILED")
                        break
                    continue
                if event.get("event") != "price" or event.get("symbol") != SYMBOL:
                    continue
                try:
                    price = float(event["price"])
                    timestamp = float(event["timestamp"])
                    age = time.time() - timestamp
                    if not (math.isfinite(price) and price > 0
                            and math.isfinite(timestamp) and -10 <= age <= 15):
                        continue
                    minute = utc_minute(timestamp)
                except (KeyError, ValueError, TypeError, OverflowError, OSError):
                    continue
                now = time.monotonic()
                if now - last_sample_monotonic < SAMPLE_SECONDS:
                    continue
                samples.append((minute, price, timestamp))
                last_sample_monotonic = now
    except Exception as exc:
        # Never print the connection URL: it contains the API key.
        print(f"WEBSOCKET_ERROR type={type(exc).__name__}")
    return samples


async def main():
    samples = await collect()
    if samples:
        # A final quote near the end of observation can belong to a minute
        # that has not completed yet; allow collector time to persist it.
        last_minute_end = max(t for _, _, t in samples)
        last_minute_end = (int(last_minute_end) // 60 + 1) * 60
        wait = max(0.0, last_minute_end + FINALIZE_SECONDS - time.time())
        if wait:
            print(f"Waiting {wait:.0f}s for final M1 candle", flush=True)
            await asyncio.sleep(wait)
    compare_samples(samples)


if __name__ == "__main__":
    asyncio.run(main())
