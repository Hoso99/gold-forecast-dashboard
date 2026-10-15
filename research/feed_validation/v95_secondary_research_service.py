"""Isolated Biquote secondary research collector. NOT installed or started.

Only genuine Biquote XAUUSD bid ticks. No access to primary DB or SELL logic.
"""
import json
import logging
import math
import os
import signal
import time
from datetime import datetime, timezone
from pathlib import Path

from v95_independent_candle_builder import validate_ticks
from v95_independent_sqlite_store import DEFAULT_BACKUP_DB, persist_validated_candle
from v95_secondary_connection_probe import RS, URL

LOG = logging.getLogger("v95_secondary")
STOP = False


def _stop(_signum, _frame):
    global STOP
    STOP = True


def _parse(raw):
    for part in raw.split(RS):
        if not part:
            continue
        try:
            msg = json.loads(part)
        except (ValueError, TypeError):
            continue
        if isinstance(msg, dict):
            yield msg


def _tick(msg):
    if msg.get("target") != "ReceiveTick":
        return None
    args = msg.get("arguments")
    if not isinstance(args, list) or not args or not isinstance(args[0], dict):
        return None
    data = args[0]
    if data.get("symbol") != "XAUUSD":
        return None
    try:
        dt = datetime.fromisoformat(str(data["timestamp"]).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return None
        dt = dt.astimezone(timezone.utc)
        bid, ask = float(data["bid"]), float(data["ask"])
        age = (datetime.now(timezone.utc) - dt).total_seconds()
        if not all(math.isfinite(x) for x in (bid, ask, age)):
            return None
        if not (0 < bid <= ask and -2 <= age <= 10):
            return None
        return dt, bid
    except (KeyError, ValueError, TypeError, OverflowError):
        return None


def collect_session(db_path, max_seconds=None):
    import websocket
    ws = websocket.create_connection(URL, timeout=5, origin="https://biquote.io")
    count = 0
    start = time.monotonic()
    current, observations, partial = None, [], True
    subscribed = False
    last_frame = time.monotonic()
    try:
        ws.send(json.dumps({"protocol": "json", "version": 1}) + RS)
        handshake = ws.recv()
        frames = list(_parse(handshake))
        if not frames or any(x.get("error") for x in frames):
            raise RuntimeError("SignalR handshake failed")
        ws.send(json.dumps({"type": 1, "target": "Subscribe",
                            "arguments": [["XAUUSD"]], "invocationId": "1"}) + RS)
        while not STOP and (max_seconds is None or time.monotonic() - start < max_seconds):
            try:
                raw = ws.recv()
            except websocket.WebSocketTimeoutException:
                if time.monotonic() - last_frame > 30:
                    raise RuntimeError("Feed silent over 30 seconds")
                continue
            if not raw:
                raise RuntimeError("WebSocket closed")
            last_frame = time.monotonic()
            for msg in _parse(raw):
                if msg.get("type") == 3 and msg.get("invocationId") == "1":
                    if msg.get("error"):
                        raise RuntimeError("Subscription rejected")
                    subscribed = True
                if not subscribed:
                    continue
                tick = _tick(msg)
                if tick is None:
                    continue
                timestamp, bid = tick
                minute = timestamp.replace(second=0, microsecond=0)
                if current is None:
                    current = minute
                if minute < current:
                    continue
                if minute > current:
                    # No fabricated empty minutes; skip partial first minute after connect.
                    if not partial and (minute - current).total_seconds() == 60:
                        candle = validate_ticks(current, observations, timestamp)
                        if candle is not None:
                            persist_validated_candle(db_path, candle)
                            count += 1
                    current, observations, partial = minute, [], False
                observations.append((timestamp, bid))
        return count
    finally:
        ws.close()


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    path = Path(os.environ.get("V95_SECONDARY_DB", str(DEFAULT_BACKUP_DB)))
    # Refuse any database except the dedicated isolated backup location.
    if path.resolve() != DEFAULT_BACKUP_DB.resolve():
        raise SystemExit("Unapproved secondary database path")
    backoff = 2
    while not STOP:
        try:
            count = collect_session(path)
            LOG.info("session ended validated_m1=%d", count)
            backoff = 2
        except Exception as exc:
            # Never log raw frames, tokens or prices.
            LOG.warning("secondary session reset reason=%s", type(exc).__name__)
        if not STOP:
            time.sleep(backoff)
            backoff = min(backoff * 2, 60)


if __name__ == "__main__":
    main()
