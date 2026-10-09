"""Research-only 24/7 Twelve Data WebSocket spot monitor. No orders or alerts."""
import asyncio
import collections
import datetime as dt
import json
import logging
import math
import os
import time
from urllib.parse import quote
import websockets

SYMBOL="XAU/USD"
KEY=os.environ.get("TWELVE_DATA_API_KEY","").strip()
WINDOW=int(os.environ.get("PRESSURE_TICKS","100"))
MAX_AGE=float(os.environ.get("MAX_QUOTE_AGE_SECONDS","15"))
LOG_EVERY=float(os.environ.get("SNAPSHOT_SECONDS","10"))
if not KEY: raise SystemExit("TWELVE_DATA_API_KEY is required")
if WINDOW<10 or WINDOW>10000 or LOG_EVERY<1: raise SystemExit("Invalid configuration")
logging.basicConfig(level=logging.INFO,format="%(asctime)s %(levelname)s %(message)s")
log=logging.getLogger("v94-stage1")
# Tick-to-tick signed price movement is a *proxy*, not actual buying/selling volume.
def pressure(ticks):
    moves=[b-a for a,b in zip(ticks,ticks[1:])]
    up=sum(max(x,0.) for x in moves)
    down=sum(max(-x,0.) for x in moves)
    if up+down==0: return 50.,50.
    return 100*up/(up+down),100*down/(up+down)

async def session():
    prices=collections.deque(maxlen=WINDOW)
    uri="wss://ws.twelvedata.com/v1/quotes/price?apikey="+quote(KEY,safe="")
    async with websockets.connect(uri,ping_interval=20,ping_timeout=20,open_timeout=20,max_size=2**20) as ws:
        await ws.send(json.dumps({"action":"subscribe","params":{"symbols":SYMBOL}}))
        log.info("Connected; subscription requested for %s",SYMBOL)
        last_received=0.
        connected_since=time.monotonic()
        last_log=0.
        last_heartbeat=time.monotonic()
        subscribed=False
        while True:
            now=time.monotonic()
            if now-last_heartbeat>=10:
                await ws.send(json.dumps({"action":"heartbeat"}))
                last_heartbeat=now
            try:
                message=await asyncio.wait_for(ws.recv(),timeout=2)
            except asyncio.TimeoutError:
                if last_received and now-last_received>MAX_AGE:
                    raise ConnectionError("No fresh price events; reconnecting")
                if not last_received and now-connected_since>60:
                    raise ConnectionError("No price events after subscription")
                continue
            event=json.loads(message)
            kind=event.get("event")
            if kind=="subscribe-status":
                log.info("Subscription response: %s",json.dumps(event))
                if event.get("status") in ("error","failed") or event.get("fails"):
                    raise RuntimeError("Symbol subscription failed; verify WebSocket entitlement")
                subscribed=True
                continue
            if kind!="price" or event.get("symbol")!=SYMBOL:
                continue
            price=float(event["price"])
            if not math.isfinite(price) or price<=0: continue
            received=time.monotonic()
            timestamp=event.get("timestamp")
            if timestamp is not None:
                try:
                    quote_age=time.time()-float(timestamp)
                    if quote_age>MAX_AGE or quote_age < -10:
                        log.warning("Skipping stale/future provider quote: age=%.1fs",quote_age)
                        continue
                except (ValueError,TypeError):
                    continue
            last_received=received
            prices.append(price)
            if received-last_log>=LOG_EVERY:
                buy,sell=pressure(prices)
                row={"observed_at_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
                     "provider_quote_timestamp":timestamp,"symbol":SYMBOL,
                     "spot_price":price,"tick_count":len(prices),
                     "buy_power_proxy_pct":round(buy,2),"sell_power_proxy_pct":round(sell,2),
                     "pressure_state":"BUY_DOMINANT" if buy>sell else "SELL_DOMINANT" if sell>buy else "BALANCED",
                     "position_state":"UNKNOWN_NOT_CONNECTED","action":"OBSERVE_ONLY"}
                log.info("SNAPSHOT %s",json.dumps(row,separators=(",",":")))
                last_log=received

async def main():
    backoff=2
    while True:
        try:
            await session()
            backoff=2
        except (KeyboardInterrupt,asyncio.CancelledError):
            raise
        except Exception as exc:
            log.error("WebSocket monitor disconnected: %s",str(exc).replace(KEY,"[REDACTED]"))
            await asyncio.sleep(backoff)
            backoff=min(backoff*2,60)

if __name__=="__main__":
    asyncio.run(main())
