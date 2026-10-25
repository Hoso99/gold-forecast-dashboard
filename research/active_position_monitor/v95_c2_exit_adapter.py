"""V9.5 PAPER-only C2 Raw adapter. No broker or live side effects."""
import datetime as dt
from collections import deque
from research.active_position_monitor.v95_hybrid_c_research import HybridC, Config, PaperSell

SIGNALS = {'ADAPTIVE_EXIT', 'EARLY_PROFIT_EXIT'}

def _bar(b):
    return {k: float(b[k]) for k in ('o','h','l','c')}

def _timestamp(s):
    return dt.datetime.fromisoformat(s)

def _pack(c, pid, last, pending_exit=None):
    return dict(position_id=pid, last_processed=last, bars=list(c.bars),
                pending=c.pending, reversal_anchor=c.reversal_anchor,
                reversal_peak_buy=c.reversal_peak_buy, reversal_age=c.reversal_age,
                peak_r=c.position.peak_r if c.position else 0.0,
                pending_exit=pending_exit)

def initialize(state, rows, cutoff=None):
    pos=state['paper_position']
    c=HybridC(cfg=Config(power_mode='raw', scenario_monitor_enabled=False))
    # Only historical completed bars at or before opening are eligible for warmup.
    opening=cutoff or _timestamp(pos['opened_at'])
    prior=[b for b in rows if b['t'] <= opening]
    for b in prior[-100:]:
        c.on_completed_m1(_bar(b), entry_allowed=False)
    c.open_initial(pos['entry'],pos['current_stop'],pos['target'])
    state['c2_raw']=_pack(c,pos['position_id'],opening.isoformat())

def advance(state, rows):
    """Return (action, note, fill) or None. Caller checks protective levels first.

    Requires contiguous completed M1 rows. Missing history freezes discretionary
    decisions rather than reconstructing confirmation state from partial data.
    """
    pos=state.get('paper_position')
    if not pos:
        state.pop('c2_raw',None)
        return None
    ctx=state.get('c2_raw')
    if not ctx or ctx.get('position_id')!=pos.get('position_id'):
        # For an already open legacy position, start forward-only, never backfill
        # decisions as though the adapter had been live since entry.
        initialize(state,rows)
        state['c2_raw']['initialized_forward_only']=True
        return None
    c=HybridC(cfg=Config(power_mode='raw', scenario_monitor_enabled=False))
    c.bars=deque(ctx['bars'],maxlen=100)
    c.pending=ctx['pending']
    c.reversal_anchor=ctx['reversal_anchor']
    c.reversal_peak_buy=ctx['reversal_peak_buy']
    c.reversal_age=ctx['reversal_age']
    c.position=PaperSell(pos['entry'],pos['current_stop'],pos['target'],ctx['peak_r'])
    previous=_timestamp(ctx['last_processed'])
    future=[b for b in rows if b['t']>previous]
    if not future:
        return None
    if future[0]['t'] != previous+dt.timedelta(minutes=1) or any(
        b['t'] != a['t']+dt.timedelta(minutes=1) for a,b in zip(future,future[1:])
    ):
        state['c2_raw_status']='WAIT_M1_GAP: confirmation frozen; no discretionary fill'
        return None
    pending=ctx.get('pending_exit')
    for b in future:
        ts=b['t'].isoformat()
        if pending is not None:
            # Protective full-window probe has already returned NO_PROTECTIVE_TOUCH.
            # Fill at next M1 open, not the signal candle close.
            fill=float(b['o'])
            state['c2_raw']=_pack(c,pos['position_id'],ts,None)
            state['c2_raw_last_signal']=pending
            return 'EXIT_SELL_NOW',f"C2 Raw {pending['action']} at next M1 open {ts}; hypothetical fill={fill:.2f}",fill
        result=c.on_completed_m1(_bar(b),entry_allowed=False)
        if result['action'] in SIGNALS:
            pending={'action':result['action'],'signal_bar':ts,'reason':result.get('reason','')}
    state['c2_raw']=_pack(c,pos['position_id'],future[-1]['t'].isoformat(),pending)
    state['c2_raw_status']='PENDING_NEXT_M1_OPEN' if pending else 'MONITORING'
    return None


def scan_chronologically(state, rows, previous_time):
    """Evaluate each unseen M1 open, then its protective range, then C2 close.

    Returns (action, detail, checked_time). Never examines a later candle
    before deciding a pending next-open exit. No missing M1 is fabricated.
    """
    from v95_protective_gap_probe import check_protective_levels
    pos=state['paper_position']
    unseen=[b for b in rows if b['t']>previous_time]
    if not unseen:
        return 'UNCHANGED', 'No new completed M1', previous_time
    cursor=previous_time
    ctx=state.get('c2_raw')
    if not ctx or ctx.get('position_id') != pos.get('position_id'):
        initialize(state, rows, previous_time)
        state['c2_raw']['initialized_forward_only'] = True
    for bar in unseen:
        # A pending discretionary exit is priced at this opening, not after
        # scanning this candle's intrabar high/low. Opening gaps are guarded.
        ctx=state.get('c2_raw') or {}
        pending=ctx.get('pending_exit') if ctx.get('position_id')==pos.get('position_id') else None
        if pending:
            open_price=float(bar['o'])
            stop=float(pos['current_stop'])
            target=float(pos['entry'])-2*(float(pos['initial_stop'])-float(pos['entry']))
            # Missing observations cannot establish which level was first.
            if bar['t']!=cursor+dt.timedelta(minutes=1):
                action,detail=check_protective_levels(pos,[bar],cursor)
                if action=='SL_TOUCHED':return action,detail,bar['t']
                return 'GAP_UNCERTAIN',{'reason':'M1 gap before pending C2 fill; no fill assumed'},cursor
            if open_price>=stop:
                return 'SL_TOUCHED',{'bar':bar['t'].isoformat(),'hypothetical_fill':open_price,'reason':'Stop breached at next M1 open'},bar['t']
            if open_price<=target:
                return 'GAP_UNCERTAIN',{'bar':bar['t'].isoformat(),'reason':'Open beyond TP; executable fill unverified'},cursor
            # C2 state is already pending from the preceding completed candle.
            state['c2_raw_last_signal']=pending
            return 'EXIT_SELL_NOW',{'hypothetical_fill':open_price,'signal':pending,'bar':bar['t'].isoformat()},bar['t']
        action,detail=check_protective_levels(pos,[bar],cursor)
        if action in ('SL_TOUCHED','TP_TOUCHED','GAP_UNCERTAIN','WAIT_DATA'):
            return action,detail,bar['t'] if action in ('SL_TOUCHED','TP_TOUCHED') else cursor
        # The candle's high/low has now been checked; C2 sees its close only.
        # On first use, initialization is forward-only (no retroactive exits).
        advance(state,[bar])
        cursor=bar['t']
    return 'NO_PROTECTIVE_TOUCH',{'checked_bars':len(unseen)},cursor
