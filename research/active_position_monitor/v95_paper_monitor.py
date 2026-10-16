"""V9.5 isolated XAU/USD SELL-only paper monitor. No broker or live orders.

REST M1 polling. Completed-candle signals only, conservative WAIT on stale/gaps.
Hypothetical fills use completed candle close; never represent executable quotes.
"""
import argparse
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
from v95_research_votes import votes
from v95_telegram_format import format_alert
from v95_entry_exit_shadow import entry_diagnostics, exit_diagnostics
from v95_core_sell_detectors import detect as detect_core_sell
from v95_trade_history import record_closed_trade

UTC=dt.timezone.utc
ROOT=Path(__file__).resolve().parent
STATE=Path(os.getenv("V95_STATE_FILE",str(Path.home()/".local/state/v95-research/state.json")))
POLL=max(30,int(os.getenv("V95_POLL_SECONDS","60")))
ALERTS=os.getenv("V95_TELEGRAM_ENABLED","0")=="1"
KEY=os.getenv("TWELVE_DATA_API_KEY","").strip()
LOG=logging.getLogger("v95-paper")
JOURNAL=Path(os.getenv("V95_JOURNAL_FILE",str(STATE.with_name("decisions.jsonl"))))
TRADE_HISTORY=Path(os.getenv("V95_TRADE_HISTORY_FILE",str(STATE.with_name("trade_history.jsonl"))))


def send(message):
    """Return True only when Telegram confirms successful delivery."""
    if not ALERTS:
        return False

    token=os.getenv("TELEGRAM_BOT_TOKEN","").strip()
    chat=os.getenv("TELEGRAM_CHAT_ID","").strip()

    if not token or not chat:
        LOG.warning("Telegram enabled but credentials missing")
        return False

    payload=urlencode({"chat_id":chat,"text":message}).encode()
    request=Request(
        "https://api.telegram.org/bot"+token+"/sendMessage",
        data=payload,
        method="POST"
    )

    try:
        with urlopen(request,timeout=15) as response:
            data=json.load(response)

        if data.get("ok") is True:
            return True

        LOG.warning("Telegram API rejected notification")
        return False

    except Exception as exc:
        LOG.warning(
            "Telegram notification failed: %s",
            type(exc).__name__
        )
        return False

def retry_pending_alerts():
    """Retry previously queued V9.5 research notifications."""
    from v95_telegram_outbox import pending, mark_sent, mark_failed

    if not ALERTS:
        return

    outbox = STATE.with_name("telegram_outbox.sqlite3")

    committed = load()
    committed_ids = set(committed.get("committed_alert_ids", []))

    # Cleanup uses the persisted commitment record, never an assumed event.
    from v95_telegram_outbox import cleanup
    cleanup_result = cleanup(outbox, committed_ids)
    if cleanup_result["cancelled_orphans"] or cleanup_result["removed_sent"]:
        LOG.info(
            "V9.5 outbox cleanup: %s orphan(s) cancelled, %s sent record(s) removed",
            cleanup_result["cancelled_orphans"],
            cleanup_result["removed_sent"],
        )

    # Keep every pending commitment and the latest 1000 historical IDs.
    # Never discard an ID while its notification is awaiting delivery.
    history = committed.get("committed_alert_ids", [])
    if len(history) > 1000:
        pending_ids = {
            event_id for event_id, _, _ in pending(outbox, limit=100000)
        }
        retained = set(history[-1000:]) | pending_ids
        pruned = [event_id for event_id in history if event_id in retained]
        if len(pruned) < len(history):
            committed["committed_alert_ids"] = pruned
            save(committed)
            committed_ids = set(pruned)

    for event_id, message, attempts in pending(outbox, limit=100000):
        if event_id not in committed_ids:
            LOG.warning(
                "V9.5 alert not verified against committed state; "
                "delivery deferred"
            )
            continue

        if send(message):
            mark_sent(outbox, event_id)
        else:
            mark_failed(outbox, event_id, "Delivery not confirmed")


def queue_research_alert(action, note, state):
    """Persist a research notification before attempting delivery."""
    from v95_telegram_outbox import enqueue

    if not ALERTS:
        return

    event_bar = state.get("last_bar")
    if not event_bar:
        raise ValueError("Cannot queue alert without a candle timestamp")

    pos = state.get("paper_position") or state.get("last_closed_position") or {}
    position_id = pos.get("position_id")
    if not position_id:
        import hashlib
        legacy_key = json.dumps(
            {k: pos.get(k) for k in ("opened_at", "entry", "initial_stop", "target")},
            sort_keys=True,
        )
        position_id = "legacy-" + hashlib.sha256(
            legacy_key.encode("utf-8")
        ).hexdigest()[:24]
    event_id = "V95:" + position_id + ":" + action + ":" + event_bar
    message = format_alert(action, note, state)

    outbox = STATE.with_name("telegram_outbox.sqlite3")
    enqueue(outbox, event_id, message)


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
    """Read coherent Twelve Data M1 only when explicitly configured for PAPER."""
    if os.getenv("V95_MARKET_DATA_SOURCE", "BIQUOTE").upper() == "TWELVE_DATA":
        from v95_twelve_cache_reader_staging import read_candles
        return read_candles()
    from v95_resilient_biquote_reader import read_candles
    return read_candles()


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
    # Protect existing paper positions before applying new-entry requirements.
    pos = state.get("paper_position")
    if pos:
        from v95_protective_gap_probe import check_protective_levels
        # Track protective coverage independently of entry evaluations.
        previous = state.get("last_protective_bar")
        if not previous:
            previous = pos.get("opened_at")

        if not previous:
            return state, "WAIT_DATA", "Missing paper-position opening timestamp"

        try:
            previous_time = dt.datetime.fromisoformat(previous)
        except (TypeError, ValueError):
            return state, "WAIT_DATA", "Invalid protective checkpoint timestamp"

        protective_action, protective_detail = check_protective_levels(
            pos, rows, previous_time
        )

        if protective_action == "NO_PROTECTIVE_TOUCH":
            state["last_protective_bar"] = rows[-1]["t"].isoformat()
        state["protective_gap_check"] = {
            "action": protective_action,
            "detail": protective_detail,
        }
        if protective_action in ("SL_TOUCHED", "TP_TOUCHED"):
            fill = protective_detail["hypothetical_fill"]
            entry = pos["entry"]
            paper_pnl = (entry - fill) * pos.get("paper_units", 0.0)

            today = rows[-1]["t"].date().isoformat()
            if state.get("loss_day_utc") != today:
                state["loss_day_utc"] = today
                state["realized_paper_loss"] = 0.0

            if paper_pnl < 0:
                state["realized_paper_loss"] += -paper_pnl

            state["last_closed_position"] = dict(
                pos,
                exit_action=protective_action,
                hypothetical_fill=fill,
                paper_pnl=paper_pnl,
            )
            state["paper_position"] = None
            state["last_bar"] = rows[-1]["t"].isoformat()

            note = (
                f"paper entry={entry:.2f}, "
                f"hypothetical fill={fill:.2f}, "
                f"paper PnL={paper_pnl:.2f}"
            )
            return state, protective_action, note
        if protective_action == "GAP_UNCERTAIN":
            return state, "GAP_UNCERTAIN", str(protective_detail)
        if protective_action == "WAIT_DATA":
            return state, "WAIT_DATA", str(protective_detail)
    from v95_gap_aware_gate import check as check_entry_data
    eligible, data_reason, data_details = check_entry_data(rows, aggregate)
    state["entry_data_gate"] = {
        "eligible": eligible,
        "reason": data_reason,
        "details": data_details,
    }
    if not eligible and not state.get("paper_position"):
        return state,"WAIT_DATA",data_reason
    if not eligible and state.get("paper_position"):
        state["entry_data_blocked"] = data_reason
        state["last_bar"] = rows[-1]["t"].isoformat()
        return state, "HOLD_SELL", (
            "Existing paper SELL: protective M1 checks completed; "
            "indicator-based exits deferred: " + data_reason
        )
    state.pop("entry_data_blocked", None)
    latest=rows[-1]
    last=latest["t"].isoformat()
    if state.get("last_bar")==last:
        return state,"UNCHANGED","No new completed M1 candle"
    state["last_bar"]=last
    price=latest["c"]
    # Research diagnostics must never interrupt protective monitoring.
    from v95_optional_h4_adapter import evaluate_optional_h4
    try:
        state["diagnostics"], state["research_votes"] = evaluate_optional_h4(
            rows, m5, m15, h1, h4
        )
    except (ValueError, IndexError, KeyError, TypeError, ZeroDivisionError) as exc:
        state["diagnostics"] = {"status": "UNAVAILABLE", "reason": str(exc)}
        state["research_votes"] = {"status": "UNAVAILABLE", "reason": str(exc)}

    try:
        state["shadow_entry"] = entry_diagnostics(rows, m5, m15)
    except (ValueError, IndexError, KeyError, TypeError, ZeroDivisionError) as exc:
        state["shadow_entry"] = {"status": "UNAVAILABLE", "reason": str(exc)}
    sell_pressure=sum(max(x["o"]-x["c"],0) for x in rows[-10:])
    buy_pressure=sum(max(x["c"]-x["o"],0) for x in rows[-10:])
    total=buy_pressure+sell_pressure
    power=100*sell_pressure/total if total else 50
    # ATR is mandatory for new entries and indicator-based position exits,
    # but must not prevent protective M1 monitoring of an existing position.
    m15atr=atr(m15) if len(m15)>=15 else None
    atr_valid = (
        m15atr is not None
        and math.isfinite(m15atr)
        and m15atr > 0
    )
    if not atr_valid and state.get("paper_position"):
        return state, "HOLD_SELL", (
            "Existing paper SELL: protective M1 checks completed; "
            "indicator-based exits unavailable because M15 ATR is invalid"
        )
    if not atr_valid:
        return state, "WAIT_DATA", "Invalid M15 ATR"
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
    h4_bearish=(h4[-1]["c"]<h4[-2]["c"]) if len(h4)>=2 else None
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
    # Preserve a qualifying technical SELL independently of news authorization.
    # This is research metadata only, never a position or broker order.
    state["last_technical_sell_opportunity"] = {
        "bar": rows[-1]["t"].isoformat(),
        "price": price,
        "sell_power": round(power, 2),
        "news_risk": (news_context or {}).get("risk", "UNKNOWN"),
        "paper_entry_authorized_by_news": (
            os.getenv("V95_NEWS_GATE_ENABLED", "1") != "1"
            or (news_context or {}).get("risk") == "NORMAL"
        ),
    }
    # Only new paper entries are subject to the USD calendar gate. Existing
    # positions have already returned above, so protective exits never depend
    # on calendar availability. Missing or unverified context fails closed.
    if os.getenv("V95_NEWS_GATE_ENABLED","1")=="1":
        news_risk=(news_context or {}).get("risk","UNKNOWN")
        if news_risk != "NORMAL":
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
    # A new paper position must never inherit the previous trade's cursor.
    state["last_protective_bar"] = last
    state.pop("protective_gap_check", None)
    from uuid import uuid4
    state["paper_position"]={"position_id":uuid4().hex,
                              "entry":price,"initial_stop":stop,"current_stop":stop,
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
         "reason":note,"source":("TWELVE_DATA_XAUUSD_M1" if os.getenv("V95_MARKET_DATA_SOURCE", "BIQUOTE").upper()=="TWELVE_DATA" else "BIQUOTE_XAUUSD_M1"),
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
    # Standard Monday–Thursday XAU/USD maintenance window.
    if weekday in (0, 1, 2, 3) and ny.hour == 17:
        return False
    return True


def cycle():
    # Retry queued research alerts independently of market data.
    try:
        retry_pending_alerts()
    except Exception as exc:
        LOG.warning(
            "V9.5 pending alert retry failed: %s",
            type(exc).__name__
        )
    state=load()
    # Migrate legacy paper positions without changing trading parameters.
    pos = state.get("paper_position")
    if pos and not pos.get("position_id"):
        from uuid import uuid4
        pos["position_id"] = uuid4().hex
        save(state)
        LOG.info("V9.5 legacy paper position assigned research ID")
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
            # Calendar source is independent of Twelve Data market candles.
            from v95_biquote import fetch_calendar_context
            news_context=fetch_calendar_context()
        except Exception as exc:
            news_context={"risk":"UNKNOWN","error_type":type(exc).__name__}
    else:
        news_context={"risk":"DISABLED"}
    if os.getenv("V95_MARKET_DATA_SOURCE", "BIQUOTE").upper()=="TWELVE_DATA":
        state.pop("biquote_context", None)
    state["news_context"]=news_context
    updated,action,note=evaluate(rows,state,news_context)
    updated["last_event"]=action
    # Context is logged independently. No assumed Biquote pressure or fabricated data.
    # An unavailable optional context feed is explicitly recorded as UNKNOWN.
    if os.getenv("V95_MARKET_DATA_SOURCE", "BIQUOTE").upper() != "TWELVE_DATA" and os.getenv("V95_BIQUOTE_ENABLED","0")=="1":
        try:
            from v95_biquote import fetch_context
            updated["biquote_context"]=fetch_context()
        except Exception as exc:
            updated["biquote_context"]={"risk":"UNKNOWN","error_type":type(exc).__name__}
    # Queue alerts before state persistence to prevent silent alert loss.
    # Telegram delivery remains after the state has been saved.
    if action in {"PAPER_SELL_ENTRY","SL_TOUCHED","TP_TOUCHED",
                  "EXIT_SELL_NOW","PARTIAL_EXIT_PROPOSED","MOVE_SL"}:
        queue_research_alert(action,note,updated)
    if action in {"PAPER_SELL_ENTRY","SL_TOUCHED","TP_TOUCHED",
                  "EXIT_SELL_NOW","PARTIAL_EXIT_PROPOSED","MOVE_SL"} and ALERTS:
        pos = updated.get("paper_position") or updated.get("last_closed_position") or {}
        position_id = pos.get("position_id")
        if not position_id:
            import hashlib
            legacy_key = json.dumps(
                {k: pos.get(k) for k in ("opened_at", "entry", "initial_stop", "target")},
                sort_keys=True,
            )
            position_id = "legacy-" + hashlib.sha256(
                legacy_key.encode("utf-8")
            ).hexdigest()[:24]
        event_id = "V95:" + position_id + ":" + action + ":" + str(updated.get("last_bar"))
        committed_ids = updated.setdefault("committed_alert_ids", [])
        if event_id not in committed_ids:
            committed_ids.append(event_id)
    journal_decision(action,note,updated)
    save(updated)
    try:
        record_closed_trade(updated, TRADE_HISTORY)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        LOG.error("V9.5 trade history recording failed; retry on next cycle: %s", type(exc).__name__)
    LOG.info("%s %s",action,note)
    retry_pending_alerts()
    return action

def main():
    logging.basicConfig(level=logging.INFO,format="%(asctime)s %(levelname)s %(message)s")
    LOG.info("V9.5 PAPER MONITOR ONLY; NO BROKER EXECUTION")
    parser=argparse.ArgumentParser()
    parser.add_argument("--once",action="store_true")
    args=parser.parse_args()
    while True:
        try:
            cycle()
        except Exception as exc:
            safe=str(exc).replace(KEY,"[REDACTED]") if KEY else str(exc)
            LOG.warning("WAIT_DATA: %s",type(exc).__name__+": "+safe)
            if args.once:
                raise SystemExit(1)
        if args.once:
            break
        time.sleep(POLL)

if __name__=="__main__":
    main()
