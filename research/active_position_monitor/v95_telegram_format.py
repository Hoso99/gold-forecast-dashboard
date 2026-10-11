"""Human-readable V9.5 paper Telegram research messages. No broker claims."""
import datetime as dt
from zoneinfo import ZoneInfo

EVENTS={"PAPER_SELL_ENTRY":"SELL ENTRY (hypothetical)",
"PARTIAL_EXIT_PROPOSED":"PARTIAL PROFIT OPPORTUNITY (not filled)",
"MOVE_SL":"STOP CHANGE (paper state only)",
"SL_TOUCHED":"STOP LOSS TOUCHED (paper estimate)",
"TP_TOUCHED":"TAKE PROFIT TOUCHED (paper estimate)",
"EXIT_SELL_NOW":"EARLY EXIT (paper estimate)"}

def money(value):
    return f"{value:.2f}" if isinstance(value,(int,float)) else "UNKNOWN"

def format_alert(action,note,state,now=None):
    now=now or dt.datetime.now(dt.timezone.utc)
    pos=state.get("paper_position") or state.get("last_closed_position") or {}
    d=state.get("diagnostics") or {}
    votes=state.get("research_votes") or {}
    ctx=state.get("biquote_context") or {}
    quote=ctx.get("quote") or {}
    entry=pos.get("entry")
    sl=pos.get("current_stop")
    tp=pos.get("target")
    risk=(pos.get("initial_stop",0)-entry) if isinstance(entry,(int,float)) else None
    rr=(entry-tp)/risk if risk and isinstance(tp,(int,float)) else None
    lines=["V9.5 PAPER RESEARCH — NO LIVE TRADE",
           "XAU/USD | "+EVENTS.get(action,action),
           "UTC: "+now.strftime("%Y-%m-%d %H:%M"),
           "Cyprus: "+now.astimezone(ZoneInfo("Asia/Nicosia")).strftime("%Y-%m-%d %H:%M %Z"),
           "Entry: "+money(entry)+" | SL: "+money(sl)+" | TP: "+money(tp),
           "Target R:R: "+(f"1:{rr:.2f}" if rr is not None else "UNKNOWN"),
           "Planned paper risk: "+money(pos.get("risk_budget")),
           "M1 SELL body proxy: "+money(d.get("m1_sell_pressure_10"))+"%",
           "M15 RSI14: "+money(d.get("m15_rsi14")),
           "M15 EMA9/EMA21: "+money(d.get("m15_ema9"))+" / "+money(d.get("m15_ema21")),
           "M5 momentum: "+money(d.get("m5_momentum_3")),
           "Previous H1 pivot: "+money(d.get("previous_h1_pivot")),
           "Four research votes: "+str(votes.get("agreement","UNKNOWN"))+"/4 (independence unverified)",
           "Macro risk: "+str(ctx.get("risk","UNKNOWN")),
           "Biquote bid/ask: "+money(quote.get("bid"))+" / "+money(quote.get("ask")),
           "Exit plan: structural SL; 2R TP; propose partial at 1R; early M15/M5-H1 reversal exit.",
           "No partial fill or break-even adjustment is assumed without acknowledgement.",
           "Event: "+note,
           "Paper fills, costs and profitability are not independently verified."]
    return "\n".join(lines)
