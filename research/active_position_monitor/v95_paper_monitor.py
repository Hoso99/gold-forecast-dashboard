"""V9.5 isolated XAU/USD SELL-only paper monitor. No broker or live orders.

REST M1 polling. Completed-candle signals only, conservative WAIT on stale/gaps.
Hypothetical fills use completed candle close; never represent executable quotes.
"""
import datetime as dt
import json
import logging
import math
import os
from pathlib import Path
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

UTC=dt.timezone.utc
ROOT=Path(__file__).resolve().parent
STATE=Path(os.getenv("V95_STATE_FILE",str(Path.home()/".local/state/v95-research/state.json")))
POLL=max(30,int(os.getenv("V95_POLL_SECONDS","60")))
ALERTS=os.getenv("V95_TELEGRAM_ENABLED","0")=="1"
KEY=os.getenv("TWELVE_DATA_API_KEY","").strip()
LOG=logging.getLogger("v95-paper")


def send(message):
    if not ALERTS:
        return
    token=os.getenv("TELEGRAM_BOT_TOKEN","").strip()
    chat=os.getenv("TELEGRAM_CHAT_ID","").strip()
    if not token or not chat:
        LOG.warning("Telegram enabled but credentials missing; no alert sent")
        return
    payload=urlencode({"chat_id":chat,"text":message}).encode()
    request=Request("https://api.telegram.org/bot"+token+"/sendMessage",
                    data=payload,method="POST")
    try:
        with urlopen(request,timeout=15) as response:
            data=json.load(response)
        if not data.get("ok"):
            LOG.warning("Telegram API rejected notification")
    except Exception as exc:
        LOG.warning("Telegram notification failed: %s",type(exc).__name__)


def load():
    try:
        return json.loads(STATE.read_text())
    except FileNotFoundError:
        return {"last_bar":None,"paper_position":None,"last_event":None}


def save(state):
    STATE.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    tmp=STATE.with_suffix(".tmp")
    with tmp.open("w") as f:
        json.dump(state,f,indent=2)
    os.chmod(tmp,0o600)
    tmp.replace(STATE)


def candles():
    if not KEY:
        raise RuntimeError("Missing TWELVE_DATA_API_KEY")
    query=urlencode({"symbol":"XAU/USD","interval":"1min","outputsize":500,
                     "timezone":"UTC","apikey":KEY,"format":"JSON"})
    with urlopen("https://api.twelvedata.com/time_series?"+query,timeout=30) as r:
        result=json.load(r)
    if not isinstance(result.get("values"),list):
        raise RuntimeError("Provider rejected XAU/USD M1 request")
    now=dt.datetime.now(UTC)
    rows=[]
    for v in result["values"]:
        t=dt.datetime.strptime(v["datetime"],"%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
        if t+dt.timedelta(minutes=1)>now-dt.timedelta(seconds=10):
            continue
        o,h,l,c=(float(v[k]) for k in ("open","high","low","close"))
        if not all(math.isfinite(x) and x>0 for x in (o,h,l,c)) or not l<=min(o,c)<=max(o,c)<=h:
            raise RuntimeError("Invalid OHLC")
        rows.append({"t":t,"o":o,"h":h,"l":l,"c":c})
    rows.sort(key=lambda x:x["t"])
    if len(rows)<240 or len({x["t"] for x in rows})!=len(rows):
        raise RuntimeError("Insufficient or duplicate M1 history")
    if (now-(rows[-1]["t"]+dt.timedelta(minutes=1))).total_seconds()>180:
        raise RuntimeError("Stale provider data; no signals")
    # Do not fill missing candles. A market closure is a legitimate reason to wait.
    tail=rows[-240:]
    if any(b["t"]-a["t"]!=dt.timedelta(minutes=1) for a,b in zip(tail,tail[1:])):
        raise RuntimeError("Gap in required M1 history; no signals")
    return rows


def aggregate(rows,minutes):
    out=[]
    chunk=[]
    for x in rows:
        if x["t"].minute%minutes==0 and (minutes!=60 or x["t"].minute==0):
            chunk=[]
        chunk.append(x)
        if len(chunk)==minutes:
            start=chunk[0]["t"]
            if (start.hour*60+start.minute)%minutes==0:
                out.append({"t":start,"o":chunk[0]["o"],"h":max(y["h"] for y in chunk),
                            "l":min(y["l"] for y in chunk),"c":chunk[-1]["c"]})
            chunk=[]
    return out


def atr(bars,n=14):
    tr=[]
    for a,b in zip(bars,bars[1:]):
        tr.append(max(b["h"]-b["l"],abs(b["h"]-a["c"]),abs(b["l"]-a["c"])))
    return sum(tr[-n:])/n if len(tr)>=n else None


def evaluate(rows,state):
    m5=aggregate(rows,5)
    m15=aggregate(rows,15)
    h1=aggregate(rows,60)
    if len(m15)<18 or len(m5)<6 or len(h1)<3:
        return state,"WAIT_DATA","Insufficient completed aligned bars"
    latest=rows[-1]
    last=latest["t"].isoformat()
    if state.get("last_bar")==last:
        return state,"UNCHANGED","No new completed M1 candle"
    state["last_bar"]=last
    price=latest["c"]
    sell_pressure=sum(max(x["o"]-x["c"],0) for x in rows[-10:])
    buy_pressure=sum(max(x["c"]-x["o"],0) for x in rows[-10:])
    total=buy_pressure+sell_pressure
    power=100*sell_pressure/total if total else 50
    m15atr=atr(m15)
    if m15atr is None or m15atr<=0:
        return state,"WAIT_DATA","Invalid M15 ATR"
    pos=state.get("paper_position")
    if pos:
        entry,initial_stop=pos["entry"],pos["initial_stop"]
        risk=initial_stop-entry
        if risk<=0:
            return state,"WAIT_DATA","Invalid paper position risk"
        r=(entry-price)/risk
        # Last completed M1 high/low may have touched a protective level;
        # conservative stop-first rule if both are crossed in the same bar.
        if latest["h"]>=pos["current_stop"]:
            action="SL_TOUCHED"
        elif latest["l"]<=entry-2*risk:
            action="TP_TOUCHED"
        elif m15[-1]["c"]>max(x["h"] for x in m15[-4:-1]):
            action="EXIT_SELL_NOW"
        elif (sum(m5[-i]["c"]>m5[-i-1]["c"] for i in range(1,5))>=3
              and m5[-1]["c"]>m5[-2]["c"] and h1[-1]["c"]>h1[-2]["c"]):
            action="EXIT_SELL_NOW"
        elif pos.get("partial") and pos["current_stop"]>entry:
            action="MOVE_SL"
            pos["current_stop"]=entry
        elif r>=1 and not pos.get("partial"):
            action="PARTIAL_EXIT"
            pos["partial"]=True
        else:
            action="HOLD_SELL"
        if action in ("SL_TOUCHED","TP_TOUCHED","EXIT_SELL_NOW"):
            state["paper_position"]=None
        note=f"paper entry={entry:.2f}, price={price:.2f}, R={r:.2f}, SL={pos['current_stop']:.2f}"
        return state,action,note
    # Research-only candidate: trend-aligned M15 downside breakout, pressure,
    # H1 bearish confirmation. No real position or broker execution is assumed.
    recent=m15[-1]
    breakout=recent["c"]<min(x["l"] for x in m15[-5:-1])
    trend=h1[-1]["c"]<h1[-2]["c"]
    if not (breakout and trend and power>=60):
        return state,"WAIT_SELL",f"SELL proxy={power:.1f}%, breakout={breakout}, H1 bearish={trend}"
    stop=max(x["h"] for x in m15[-5:])+1.5*m15atr
    if stop<=price:
        return state,"WAIT_DATA","Invalid structure/ATR stop"
    target=price-2*(stop-price)
    state["paper_position"]={"entry":price,"initial_stop":stop,"current_stop":stop,
                              "target":target,"partial":False,"opened_at":last}
    return state,"PAPER_SELL_ENTRY",f"entry={price:.2f}, SL={stop:.2f}, TP={target:.2f}, SELL proxy={power:.1f}%"


def main():
    logging.basicConfig(level=logging.INFO,format="%(asctime)s %(levelname)s %(message)s")
    LOG.info("V9.5 PAPER MONITOR ONLY; NO BROKER EXECUTION")
    while True:
        try:
            state=load()
            updated,action,note=evaluate(candles(),state)
            save(updated)
            LOG.info("%s %s",action,note)
            if action in {"PAPER_SELL_ENTRY","SL_TOUCHED","TP_TOUCHED",
                          "EXIT_SELL_NOW","PARTIAL_EXIT","MOVE_SL"}:
                message=f"[V9.5 PAPER RESEARCH — NOT A TRADE]\n{action}\n{note}"
                send(message)
        except Exception as exc:
            LOG.warning("WAIT_DATA: %s",type(exc).__name__+": "+str(exc).replace(KEY,"[REDACTED]"))
        time.sleep(POLL)


if __name__=="__main__":
    main()
