"""Research-only SignalR framing for an independent Biquote connection.

No connection is opened, no secrets are loaded, and no database is written.
The live adapter must supply the verified event schema before activation.
"""
import json
from datetime import datetime, timezone
from math import isfinite

RECORD_SEPARATOR = chr(30)


def decode_frames(raw):
    if not isinstance(raw, str):
        raise ValueError('Text WebSocket frame required')
    result = []
    for part in raw.split(RECORD_SEPARATOR):
        if part:
            message = json.loads(part)
            if not isinstance(message, dict):
                raise ValueError('SignalR object expected')
            result.append(message)
    return result


def parse_bid_tick(payload, *, symbol_key, time_key, bid_key, ask_key, expected_symbol):
    """Parse a verified schema supplied by the primary-collector audit."""
    if not isinstance(payload, dict) or payload.get(symbol_key) != expected_symbol:
        return None
    try:
        stamp = datetime.fromisoformat(str(payload[time_key]).replace('Z', '+00:00'))
        bid, ask = float(payload[bid_key]), float(payload[ask_key])
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    if stamp.tzinfo is None or not all(isfinite(x) for x in (bid, ask)):
        return None
    if not 0 < bid <= ask:
        return None
    return stamp.astimezone(timezone.utc), bid
