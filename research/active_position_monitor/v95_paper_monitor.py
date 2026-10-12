"""V9.5 isolated XAU/USD SELL-only paper monitor. No broker or live orders.

REST M1 polling. Completed-candle signals only, conservative WAIT on stale/gaps.
Hypothetical fills use completed candle close; never represent executable quotes.
"""
import argparse
from urllib.error import HTTPError
import datetime as dt
import json
import logging
import math
import os
from pathlib import Path
from zoneinfo import ZoneInfo
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from v95_indicators import diagnostics
from v95_biquote import fetch_context, fetch_calendar_context
from v95_research_votes import votes
from v95_telegram_format import format_alert
from v95_entry_exit_shadow import entry_diagnostics, exit_diagnostics
from v95_core_sell_detectors import detect as detect_core_sell
from v95_trade_history import record_closed_trade

UTC=dt.timezone.utc
ROOT=Path(__file__).resolve().parent
STATE=Path(os.getenv("V95_STATE_FILE",str(Path.home()/".local/state/v95-research/state.json")))
POLL=max(150,int(os.getenv("V95_POLL_SECONDS","150")))
# Basic 800-credit daily plan: 150-second minimum is <=576 requests/day.
# Other clients using the same key may still exhaust the shared quota.
ALERTS=os.getenv("V95_TELEGRAM_ENABLED","0")=="1"
KEY=os.getenv("TWELVE_DATA_API_KEY","").strip()
LOG=logging.getLogger("v95-paper")
JOURNAL=Path(os.getenv("V95_JOURNAL_FILE",str(STATE.with_name("decisions.jsonl"))))
TRADE_HISTORY=Path(os.getenv("V95_TRADE_HISTORY_FILE",str(STATE.with_name("trade_history.jsonl"))))
CANDLE_CACHE=Path(os.getenv("V95_CANDLE_CACHE_FILE",str(STATE.with_name("m1_candle_cache.json"))))


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


def daily_quota_exhausted(exc):
    """Distinguish daily-credit exhaustion from a transient minute-level 429."""
    if not isinstance(exc, HTTPError) or exc.code != 429:
        return False
    try:
        payload=json.loads(exc.read(2048).decode("utf-8"))
    except (ValueError, UnicodeError, OSError):
        return False
    message=str(payload.get("message","")).lower()
    return "credits for the day" in message or "daily limit" in message


def seconds_until_utc_reset(now=None):
    now=now or dt.datetime.now(UTC)
    tomorrow=(now+dt.timedelta(days=1)).date()
    reset=dt.datetime.combine(tomorrow,dt.time.min,tzinfo=UTC)
    return max(1,math.ceil((reset-now).total_seconds())+5)


def _valid_bar(bar):
    try:
        t=dt.datetime.fromisoformat(bar["t"])
        o,h,l,c=(float(bar[k]) for k in ("o","h","l","c"))
        return (t.tzinfo is not None and t.utcoffset()==dt.timedelta(0)
                and t.second==0 and t.microsecond==0
                and all(math.isfinite(x) and x>0 for x in (o,h,l,c))
                and l<=min(o,c)<=max(o,c)<=h)
    except (KeyError, ValueError, TypeError, OverflowError):
        return False


def _load_candle_cache():
    """Only reuse candles previously retrieved from the same Twelve Data feed."""
    try:
        payload=json.loads(CANDLE_CACHE.read_text(encoding="utf-8"))
        if payload.get("source")!="TWELVE_DATA_XAUUSD_M1":
            return []
        raw=payload["bars"]
        if not isinstance(raw,list) or len(raw)>1500 or not all(_valid_bar(x) for x in raw):
            return []
        rows=[dict(x,t=dt.datetime.fromisoformat(x["t"]).astimezone(UTC)) for x in raw]
        rows.sort(key=lambda x:x["t"])
        if len({x["t"] for x in rows})!=len(rows):
            return []
        return rows
    except (OSError, ValueError, TypeError, KeyError):
        return []


def _save_candle_cache(rows):
    CANDLE_CACHE.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    tmp=CANDLE_CACHE.with_suffix(".tmp")
    payload={"source":"TWELVE_DATA_XAUUSD_M1",
             "bars":[dict(x,t=x["t"].isoformat()) for x in rows[-1000:]]}
    with tmp.open("w",encoding="utf-8") as f:
        json.dump(payload,f)
    os.chmod(tmp,0o600)
    tmp.replace(CANDLE_CACHE)


def candles():
    if not KEY:
        raise RuntimeError("Missing TWELVE_DATA_API_KEY")
    cached=_load_candle_cache()
    # The initial request establishes a provider-consistent 720-bar baseline.
    # Subsequent requests overlap the cache to catch missing minutes/revisions.
    size=20 if len(cached)>=720 else 1000
    query=urlencode({"symbol":"XAU/USD","interval":"1min","outputsize":size,
                     "timezone":"UTC","apikey":KEY,"format":"JSON"})
    with urlopen("https://api.twelvedata.com/time_series?"+query,timeout=30) as r:
        result=json.load(r)
    if not isinstance(result.get("values"),list):
        raise RuntimeError("Provider rejected XAU/USD M1 request")
    now=dt.datetime.now(UTC)
    fresh=[]
    for v in result["values"]:
        t=dt.datetime.strptime(v["datetime"],"%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
        if t+dt.timedelta(minutes=1)>now-dt.timedelta(seconds=10):
            continue
        o,h,l,c=(float(v[k]) for k in ("open","high","low","close"))
        if not all(math.isfinite(x) and x>0 for x in (o,h,l,c)) or not l<=min(o,c)<=max(o,c)<=h:
            raise RuntimeError("Invalid OHLC")
        fresh.append({"t":t,"o":o,"h":h,"l":l,"c":c})
    if len({x["t"] for x in fresh})!=len(fresh):
        raise RuntimeError("Duplicate provider M1 timestamps")
    fresh.sort(key=lambda x:x["t"])
    if not fresh:
        raise RuntimeError("No completed provider M1 candles")
    # Refuse silently combining inconsistent sources or provider revisions.
    existing={x["t"]:x for x in cached}
    for x in fresh:
        previous=existing.get(x["t"])
        if previous and any(abs(previous[k]-x[k])>0.00001 for k in ("o","h","l","c")):
            raise RuntimeError("Provider M1 candle revision; no signals")
    merged={x["t"]:x for x in cached}
    merged.update({x["t"]:x for x in fresh})
    rows=sorted(merged.values(),key=lambda x:x["t"])[-1000:]
    # A cache must never bypass the same completed-candle safety checks.
    if len(rows)<720:
        raise RuntimeError("Insufficient M1 history")
    if (now-(rows[-1]["t"]+dt.timedelta(minutes=1))).total_seconds()>180:
        raise RuntimeError("Stale provider data; no signals")
    tail=rows[-720:]
    if any(b["t"]-a["t"]!=dt.timedelta(minutes=1) for a,b in zip(tail,tail[1:])):
        raise RuntimeError("Gap in required M1 history; no signals")
    _save_candle_cache(rows)
    return rows


def aggregate(rows,minutes):
    """Aggregate only fully completed, correctly aligned, contiguous M1 bars."""
    out=[]
    groups={}
    for x in rows:
        midnight=x["t"].replace(hour=0,minute=0,second=0,microsecond=0)
        minute_of_day=x["t"].hour*60+x["t"].minute
        start=midnight+dt.timedelta(minutes=(minute_of_day//minutes)*minutes)
        groups.setdefault(start,[]).append(x)
    for start,chunk in sorted(groups.items()):
        expected=[start+dt.timedelta(minutes=i) for i in range(minutes)]
        if len(chunk)!=minutes or [x["t"] for x in chunk]!=expected:
            continue
        out.append({"t":start,"o":chunk[0]["o"],"h":max(y["h"] for y in chunk),
                    "l":min(y["l"] for y in chunk),"c":chunk[-1]["c"]})
    return out


def atr(bars,n=14):
    tr=[]
    for a,b in zip(bars,bars[1:]):
        tr.append(max(b["h"]-b["l"],abs(b["h"]-a["c"]),abs(b["l"]-a["c"])))
    return sum(tr[-n:])/n if len(tr)>=n else None


def evaluate(rows,state,news_context=None):
    m5=aggregate(rows,5)
    m15=aggregate(rows,15)
    h1=aggregate(rows,60)
    h4=aggregate(rows,240)
    if len(m15)<18 or len(m5)<6 or len(h1)<3 or len(h4)<2:
        return state,"WAIT_DATA","Insufficient completed aligned bars"
    latest=rows[-1]
    last=latest["t"].isoformat()
    if state.get("last_bar")==last:
        return state,"UNCHANGED","No new completed M1 candle"
    state["last_bar"]=last
    price=latest["c"]
    state["diagnostics"]=diagnostics(rows,m5,m15,h1,h4)
    state["research_votes"]=votes(rows,m5,m15,h1,h4)
    state["shadow_entry"]=entry_diagnostics(rows,m5,m15)
    sell_pressure=sum(max(x["o"]-x["c"],0) for x in rows[-10:])
    buy_pressure=sum(max(x["c"]-x["o"],0) for x in rows[-10:])
    total=buy_pressure+sell_pressure
    power=100*sell_pressure/total if total else 50
    m15atr=atr(m15)
    if m15atr is None or m15atr<=0:
        return state,"WAIT_DATA","Invalid M15 ATR"
    today=latest["t"].date().isoformat()
    if state.get("loss_day_utc")!=today:
        state["loss_day_utc"]=today
        state["realized_paper_loss"]=0.0
    pos=state.get("paper_position")
    state["shadow_exit"]=exit_diagnostics(rows,m5,pos) if pos else {"status":"NO_POSITION"}
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
        elif pos.get("partial_acknowledged") and pos["current_stop"]>entry:
            action="MOVE_SL"
            pos["current_stop"]=entry
        elif (latest["l"]<=entry-risk and not pos.get("partial_acknowledged")
              and not pos.get("partial_proposed")):
            action="PARTIAL_EXIT_PROPOSED"
            pos["partial_proposed"]=True
        else:
            action="HOLD_SELL"
        if action in ("SL_TOUCHED","TP_TOUCHED","EXIT_SELL_NOW"):
            # Conservative paper-only PnL; adverse stop gaps use worse M1 open.
            if action=="SL_TOUCHED":
                hypothetical_fill=max(pos["current_stop"],latest["o"])
            elif action=="TP_TOUCHED":
                hypothetical_fill=entry-2*risk
            else:
                hypothetical_fill=price
            paper_pnl=(entry-hypothetical_fill)*pos.get("paper_units",0.0)
            if paper_pnl<0:
                state["realized_paper_loss"]+=-paper_pnl
            state["last_closed_position"]=dict(pos, exit_action=action, hypothetical_fill=hypothetical_fill, paper_pnl=paper_pnl)
            state["paper_position"]=None
        note=f"paper entry={entry:.2f}, price={price:.2f}, R={r:.2f}, SL={pos['current_stop']:.2f}"
        return state,action,note
    # Daily paper realized-loss lock (3% of configured starting paper equity).
    paper_equity=float(os.getenv("V95_PAPER_EQUITY","0"))
    if not math.isfinite(paper_equity) or paper_equity<=0:
        return state,"WAIT_RISK","Set positive V95_PAPER_EQUITY before opening any paper position"
    if state["realized_paper_loss"]>=paper_equity*0.03:
        return state,"DAILY_PAPER_LOCK","3% UTC-day realized paper loss threshold reached"
    # Research-only candidate. Require M5 momentum and H1 trend; H4 advisory.
    # No real position or broker execution is assumed.
    core_detectors=detect_core_sell(m15,m15atr,power)
    state["core_sell_detectors"]=core_detectors
    structural_sell=core_detectors.get("structural_sell",False)
    trend=h1[-1]["c"]<h1[-2]["c"]
    # H4 is advisory context only; it must never veto an otherwise valid SELL.
    h4_bearish=h4[-1]["c"]<h4[-2]["c"]
    m5_bearish=m5[-1]["c"]<m5[-2]["c"] and sum(
        m5[-i]["c"]<m5[-i-1]["c"] for i in range(1,5))>=3
    # Check remaining downside room against older support, not the breakout level.
    # Never veto a breakout solely for crossing the support it just broke.
    older_support=min(x["l"] for x in m15[-17:-5])
    location=(price-older_support)>1.0*m15atr
    if not (structural_sell and trend and m5_bearish and location and power>=60):
        return state,"WAIT_SELL",(
            f"SELL proxy={power:.1f}%, M5 bearish={m5_bearish}, "
            f"enhanced support break={core_detectors.get('enhanced_support_break')}, "
            f"bearish liquidity sweep={core_detectors.get('bearish_liquidity_sweep')}, "
            f"H1 bearish={trend}, H4 advisory bearish={h4_bearish}, "
            f"support buffer={location}")
    # Only new paper entries are subject to the USD calendar gate. Existing
    # positions have already returned above, so protective exits never depend
    # on calendar availability. Missing or unverified context fails closed.
    if os.getenv("V95_NEWS_GATE_ENABLED","1")=="1":
        news_risk=(news_context or {}).get("risk","UNKNOWN")
        if news_risk not in ("NORMAL","BUILDING"):
            events=(news_context or {}).get("events",[])
            event_name=next((x.get("name","USD event") for x in events
                             if -15<=x.get("minutes_to_event",999)<=30),"")
            return state,"NEWS_BLOCKED",(
                f"New paper SELL entry blocked: USD calendar risk={news_risk}"
                + (f", event={event_name}" if event_name else "")
            )
    stop=max(x["h"] for x in m15[-5:])+1.5*m15atr
    if stop<=price:
        return state,"WAIT_DATA","Invalid structure/ATR stop"
    target=price-2*(stop-price)
    # Position sizing requires a verified paper equity amount. Never invent 2% risk.
    risk_budget=min(paper_equity*0.02,max(0.0,paper_equity*0.03-state["realized_paper_loss"]))
    units=risk_budget/(stop-price)
    if not math.isfinite(units) or units<=0:
        return state,"WAIT_RISK","Invalid hypothetical position sizing"
    triggered_detectors=[
        name for name in ("enhanced_support_break", "bearish_liquidity_sweep")
        if core_detectors.get(name,False)
    ]
    state["paper_position"]={"entry":price,"initial_stop":stop,"current_stop":stop,
                              "target":target,"paper_units":units,"risk_budget":risk_budget,
                              "partial_proposed":False,
                              "partial_acknowledged":False,"opened_at":last,
                              "entry_detectors":triggered_detectors}
    return state,"PAPER_SELL_ENTRY",f"entry={price:.2f}, SL={stop:.2f}, TP={target:.2f}, paper units={units:.4f}, max planned paper risk={risk_budget:.2f}, SELL proxy={power:.1f}%, detectors={triggered_detectors}, H4 advisory bearish={h4_bearish}"


def journal_decision(action,note,state):
    """Append V9.5 decisions to its own research journal, never V9.4."""
    if action=="UNCHANGED":
        return
    JOURNAL.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    row={"version":"V9.5_RESEARCH","observed_at_utc":dt.datetime.now(UTC).isoformat(),
         "m1_bar_start_utc":state.get("last_bar"),"decision":action,
         "reason":note,"source":"TWELVE_DATA_XAUUSD_M1_PROXY",
         "paper_position_open":bool(state.get("paper_position")),"broker_execution":False,
         "diagnostics":state.get("diagnostics",{}),
         "research_votes":state.get("research_votes",{}),
         "core_sell_detectors":state.get("core_sell_detectors",{}),
         "shadow_entry":state.get("shadow_entry",{}),
         "shadow_exit":state.get("shadow_exit",{}),
         "biquote_context":state.get("biquote_context",{"risk":"NOT_ENABLED"}),
         "news_context":state.get("news_context",{"risk":"UNKNOWN"})}
    with JOURNAL.open("a",encoding="utf-8") as out:
        out.write(json.dumps(row,sort_keys=True)+"\n")
    os.chmod(JOURNAL,0o600)

def market_session_open(now=None):
    """Conservative indicative XAU/USD weekly session; freshness checks still required.

    New York Friday 17:00 through Sunday 17:00 is closed. Provider holidays
    and maintenance are not inferred; candles() rejects stale and gapped bars.
    """
    now = now or dt.datetime.now(UTC)
    ny = now.astimezone(ZoneInfo("America/New_York"))
    weekday = ny.weekday()
    if weekday == 5:
        return False
    if weekday == 4 and ny.hour >= 17:
        return False
    if weekday == 6 and ny.hour < 17:
        return False
    return True


def cycle():
    state=load()
    if not market_session_open():
        action="WAIT_MARKET_CLOSED"
        note="Indicative XAU/USD weekend closure; no paper entries or exits evaluated"
        if state.get("last_event") != action:
            journal_decision(action,note,state)
        state["last_event"]=action
        save(state)
        try:
            record_closed_trade(state, TRADE_HISTORY)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            LOG.error("V9.5 trade history recording failed; retry on next cycle: %s", type(exc).__name__)
        LOG.info("%s %s",action,note)
        return action
    rows=candles()
    # Calendar check happens before any new paper SELL entry is authorized.
    # A calendar failure must not prevent SL/TP and early-exit evaluation.
    if os.getenv("V95_NEWS_GATE_ENABLED","1")=="1":
        try:
            news_context=fetch_calendar_context()
        except Exception as exc:
            news_context={"risk":"UNKNOWN","error_type":type(exc).__name__}
    else:
        news_context={"risk":"DISABLED"}
    state["news_context"]=news_context
    updated,action,note=evaluate(rows,state,news_context)
    updated["last_event"]=action
    # Context is logged independently. No assumed Biquote pressure or fabricated data.
    # An unavailable optional context feed is explicitly recorded as UNKNOWN.
    if os.getenv("V95_BIQUOTE_ENABLED","0")=="1":
        try:
            updated["biquote_context"]=fetch_context()
        except Exception as exc:
            updated["biquote_context"]={"risk":"UNKNOWN","error_type":type(exc).__name__}
    journal_decision(action,note,updated)
    save(updated)
    try:
        record_closed_trade(updated, TRADE_HISTORY)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        LOG.error("V9.5 trade history recording failed; retry on next cycle: %s", type(exc).__name__)
    LOG.info("%s %s",action,note)
    if action in {"PAPER_SELL_ENTRY","SL_TOUCHED","TP_TOUCHED",
                  "EXIT_SELL_NOW","PARTIAL_EXIT_PROPOSED","MOVE_SL"}:
        send(format_alert(action,note,updated))
    return action

def main():
    logging.basicConfig(level=logging.INFO,format="%(asctime)s %(levelname)s %(message)s")
    LOG.info("V9.5 PAPER MONITOR ONLY; NO BROKER EXECUTION")
    parser=argparse.ArgumentParser()
    parser.add_argument("--once",action="store_true")
    args=parser.parse_args()
    while True:
        delay=POLL
        try:
            cycle()
        except Exception as exc:
            if daily_quota_exhausted(exc):
                delay=seconds_until_utc_reset()
                LOG.warning("WAIT_DATA: Twelve Data daily quota exhausted; next request after UTC reset (%s seconds)",delay)
                if args.once:
                    raise SystemExit(1)
                time.sleep(delay)
                continue
            safe=str(exc).replace(KEY,"[REDACTED]") if KEY else str(exc)
            LOG.warning("WAIT_DATA: %s",type(exc).__name__+": "+safe)
            if args.once:
                raise SystemExit(1)
        if args.once:
            break
        time.sleep(delay)

if __name__=="__main__":
    main()
