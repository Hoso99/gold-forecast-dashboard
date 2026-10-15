"""One-shot research probe. No database writes, secrets, or price logging."""
import json
import time
from datetime import datetime, timezone

URL = 'wss://biquote.io/hubs/tick'
RS = chr(30)


def probe(duration=20):
    import websocket
    seen = 0
    valid = 0
    message_types = {}
    handshake_ok = False
    subscription_result = 'not_seen'
    connected = False
    ws = None
    try:
        ws = websocket.create_connection(URL, timeout=4, origin='https://biquote.io')
        connected = True
        ws.send(json.dumps({'protocol': 'json', 'version': 1}) + RS)
        handshake_raw = ws.recv()
        handshake_parts = [json.loads(x) for x in handshake_raw.split(RS) if x]
        handshake_ok = any(isinstance(x, dict) and not x.get('error') for x in handshake_parts)
        ws.send(json.dumps({'type': 1, 'target': 'Subscribe', 'arguments': [['XAUUSD']], 'invocationId': '1'}) + RS)
        until = time.monotonic() + duration
        while time.monotonic() < until:
            try:
                raw = ws.recv()
            except websocket.WebSocketTimeoutException:
                continue
            for chunk in raw.split(RS):
                if not chunk:
                    continue
                try:
                    event = json.loads(chunk)
                except (ValueError, TypeError):
                    continue
                if not isinstance(event, dict):
                    continue
                kind = str(event.get('type', 'unspecified'))
                message_types[kind] = message_types.get(kind, 0) + 1
                if event.get('invocationId') == '1' and event.get('type') == 3:
                    subscription_result = 'error' if event.get('error') else 'acknowledged'
                if event.get('target') != 'ReceiveTick':
                    continue
                seen += 1
                args = event.get('arguments')
                if not isinstance(args, list) or not args or not isinstance(args[0], dict):
                    continue
                tick = args[0]
                if tick.get('symbol') != 'XAUUSD':
                    continue
                try:
                    timestamp = datetime.fromisoformat(str(tick['timestamp']).replace('Z', '+00:00'))
                    bid, ask = float(tick['bid']), float(tick['ask'])
                    age = (datetime.now(timezone.utc) - timestamp.astimezone(timezone.utc)).total_seconds()
                    if 0 < bid <= ask and -2 <= age <= 10:
                        valid += 1
                except (ValueError, TypeError, KeyError, OverflowError):
                    pass
        return {'second_session_connected': connected, 'receive_tick_events': seen,
                'valid_xauusd_ticks': valid, 'duration_seconds': duration,
                'handshake_ok': handshake_ok, 'subscription_result': subscription_result,
                'message_types': message_types,
                'research_only': True, 'database_writes': False}
    finally:
        if ws is not None:
            ws.close()


if __name__ == '__main__':
    try:
        print(json.dumps(probe(), sort_keys=True))
    except Exception as exc:
        print(json.dumps({'probe_status': 'FAILED', 'error_type': type(exc).__name__,
                          'database_writes': False}))
        raise SystemExit(2)
