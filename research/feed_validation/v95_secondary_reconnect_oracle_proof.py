"""Bounded real reconnection proof, isolated to SECONDARY research WebSocket.

Never stops primary collector, writes primary DB, or creates a service.
Only complete post-reconnect minutes may enter disposable SQLite.
"""
import json
import sqlite3
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from v95_independent_candle_builder import validate_ticks
from v95_independent_sqlite_store import persist_validated_candle
from v95_secondary_connection_probe import URL, RS


def connect():
    import websocket
    ws = websocket.create_connection(URL, timeout=4, origin="https://biquote.io")
    ws.send(json.dumps({"protocol": "json", "version": 1}) + RS)
    hello = ws.recv()
    if not any(isinstance(x, dict) and not x.get("error")
               for x in (json.loads(p) for p in hello.split(RS) if p)):
        ws.close()
        raise RuntimeError("SignalR handshake rejected")
    ws.send(json.dumps({"type": 1, "target": "Subscribe",
                        "arguments": [["XAUUSD"]], "invocationId": "1"}) + RS)
    return ws


def read_events(ws):
    import websocket
    try:
        raw = ws.recv()
    except websocket.WebSocketTimeoutException:
        return []
    result = []
    for part in raw.split(RS):
        if not part:
            continue
        try:
            msg = json.loads(part)
        except (ValueError, TypeError):
            continue
        if isinstance(msg, dict):
            result.append(msg)
    return result


def tick_from(msg):
    if msg.get("target") != "ReceiveTick":
        return None
    args = msg.get("arguments")
    if not isinstance(args, list) or not args or not isinstance(args[0], dict):
        return None
    tick = args[0]
    if tick.get("symbol") != "XAUUSD":
        return None
    try:
        timestamp = datetime.fromisoformat(str(tick["timestamp"]).replace("Z", "+00:00"))
        timestamp = timestamp.astimezone(timezone.utc)
        bid, ask = float(tick["bid"]), float(tick["ask"])
        age = (datetime.now(timezone.utc) - timestamp).total_seconds()
        if not (0 < bid <= ask and -2 <= age <= 10):
            return None
    except (ValueError, TypeError, KeyError, OverflowError):
        return None
    return timestamp, bid


def run():
    counters = dict(primary_database_writes=False, first_session_ticks=0,
                    reconnect_success=False, second_session_ticks=0,
                    discarded_partial_minutes=0, validated_post_reconnect_m1=0,
                    rejected_post_reconnect_m1=0, sqlite_rows=0)
    with tempfile.TemporaryDirectory(prefix="v95-reconnect-proof-") as root:
        db = Path(root) / "secondary_only.sqlite3"
        ws = connect()
        try:
            deadline = time.monotonic() + 18
            while time.monotonic() < deadline:
                for event in read_events(ws):
                    if tick_from(event):
                        counters["first_session_ticks"] += 1
        finally:
            ws.close()  # Intentionally interrupt SECONDARY only.
        if not counters["first_session_ticks"]:
            raise RuntimeError("No first-session ticks to prove interruption")
        time.sleep(2)
        ws = connect()
        counters["reconnect_success"] = True
        minute = None
        observations = []
        partial = True
        ack = False
        try:
            deadline = time.monotonic() + 205
            while time.monotonic() < deadline:
                for event in read_events(ws):
                    if event.get("type") == 3 and event.get("invocationId") == "1":
                        if event.get("error"):
                            raise RuntimeError("Reconnected subscription rejected")
                        ack = True
                    parsed = tick_from(event)
                    if parsed is None:
                        continue
                    timestamp, bid = parsed
                    counters["second_session_ticks"] += 1
                    bucket = timestamp.replace(second=0, microsecond=0)
                    if minute is None:
                        minute = bucket
                    if bucket < minute:
                        continue
                    if bucket > minute:
                        if partial:
                            counters["discarded_partial_minutes"] += 1
                        else:
                            candle = validate_ticks(minute, observations, timestamp)
                            if candle is None:
                                counters["rejected_post_reconnect_m1"] += 1
                            else:
                                persist_validated_candle(db, candle)
                                counters["validated_post_reconnect_m1"] += 1
                        minute, observations, partial = bucket, [], False
                    observations.append((timestamp, bid))
        finally:
            ws.close()
        if db.exists():
            with sqlite3.connect(db) as connection:
                counters["sqlite_rows"] = connection.execute(
                    "SELECT COUNT(*) FROM independent_m1").fetchone()[0]
        counters["reconnect_subscription_acknowledged"] = ack
    print(json.dumps(counters, sort_keys=True))
    if not (counters["reconnect_success"] and ack
            and counters["second_session_ticks"] > 0
            and counters["discarded_partial_minutes"] >= 1
            and counters["validated_post_reconnect_m1"] >= 1
            and counters["sqlite_rows"] == counters["validated_post_reconnect_m1"]):
        raise RuntimeError("Secondary reconnect acceptance criteria not met")


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        print(json.dumps({"status": "FAILED", "error_type": type(exc).__name__,
                          "primary_database_writes": False}))
        raise SystemExit(2)
