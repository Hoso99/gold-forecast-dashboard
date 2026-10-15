"""Bounded, research-only independent Biquote M1 integration test.

Uses a second WebSocket session and a throwaway isolated SQLite file.
No live DB writes, no systemd installation, no price/tick payload logging.
"""
import json
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from v95_independent_candle_builder import validate_ticks
from v95_independent_sqlite_store import persist_validated_candle
from v95_secondary_connection_probe import URL, RS


def run(seconds=95):
    import websocket
    counters = dict(connected=False, subscription_acknowledged=False,
                    valid_ticks=0, complete_m1_candles=0, rejected_m1=0,
                    database_rows=0, primary_database_writes=False)
    with tempfile.TemporaryDirectory(prefix="v95-independent-proof-") as root:
        database = Path(root) / "isolated_independent_m1.sqlite3"
        ws = websocket.create_connection(URL, timeout=4, origin="https://biquote.io")
        counters["connected"] = True
        try:
            ws.send(json.dumps({"protocol": "json", "version": 1}) + RS)
            hello = ws.recv()
            if not any(isinstance(x, dict) and not x.get("error")
                       for x in (json.loads(part) for part in hello.split(RS) if part)):
                raise RuntimeError("SignalR handshake not accepted")
            ws.send(json.dumps({"type": 1, "target": "Subscribe",
                                "arguments": [["XAUUSD"]], "invocationId": "1"}) + RS)
            until = time.monotonic() + seconds
            current = None
            observations = []
            first_minute = True
            while time.monotonic() < until:
                try:
                    raw = ws.recv()
                except websocket.WebSocketTimeoutException:
                    continue
                for part in raw.split(RS):
                    if not part:
                        continue
                    try:
                        msg = json.loads(part)
                    except (ValueError, TypeError):
                        continue
                    if not isinstance(msg, dict):
                        continue
                    if msg.get("type") == 3 and msg.get("invocationId") == "1":
                        if msg.get("error"):
                            raise RuntimeError("Subscription rejected")
                        counters["subscription_acknowledged"] = True
                    if msg.get("target") != "ReceiveTick":
                        continue
                    args = msg.get("arguments")
                    if not isinstance(args, list) or not args or not isinstance(args[0], dict):
                        continue
                    tick = args[0]
                    if tick.get("symbol") != "XAUUSD":
                        continue
                    try:
                        timestamp = datetime.fromisoformat(str(tick["timestamp"]).replace("Z", "+00:00"))
                        bid = float(tick["bid"])
                        ask = float(tick["ask"])
                        age = (datetime.now(timezone.utc) - timestamp.astimezone(timezone.utc)).total_seconds()
                        if not (0 < bid <= ask and -2 <= age <= 10):
                            continue
                    except (KeyError, ValueError, TypeError, OverflowError):
                        continue
                    timestamp = timestamp.astimezone(timezone.utc)
                    counters["valid_ticks"] += 1
                    minute = timestamp.replace(second=0, microsecond=0)
                    if current is None:
                        current = minute
                        first_minute = True
                    if minute < current:
                        continue
                    if minute > current:
                        if not first_minute:
                            candle = validate_ticks(current, observations, timestamp)
                            if candle:
                                persist_validated_candle(database, candle)
                                counters["complete_m1_candles"] += 1
                            else:
                                counters["rejected_m1"] += 1
                        current = minute
                        observations = []
                        first_minute = False
                    observations.append((timestamp, bid))
            if database.exists():
                import sqlite3
                with sqlite3.connect(database) as conn:
                    counters["database_rows"] = conn.execute("SELECT COUNT(*) FROM independent_m1").fetchone()[0]
        finally:
            ws.close()
    print(json.dumps(counters, sort_keys=True))
    if not counters["subscription_acknowledged"] or counters["valid_ticks"] == 0:
        raise RuntimeError("Independent session did not deliver confirmed ticks")
    return counters


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__,
                          "primary_database_writes": False}))
        raise SystemExit(2)
