"""Build point-in-time historical exit evidence from completed M1-derived bars.

RESEARCH ONLY. Assumes provider M1 timestamps mark OPEN (unverified).
Never interpolates missing candles, reads future data, sends orders or alerts.
"""
from __future__ import annotations
import pandas as pd
from v95_m5_confirmation_challenger import completed_bars
from v95_dynamic_sell_exit_research import SellExitEvidence, decide_sell_exit


def evidence_at(m1: pd.DataFrame, observation_time, *, entry: float,
                initial_stop: float, current_stop: float,
                partial_already_taken: bool = False) -> dict:
    """Observe at minute boundary t; price is last COMPLETED M1 close.

    M5 reversal: 3 of last 4 completed M5 closes rise and latest close
    exceeds previous M5 close. M15 invalidation: last completed M15 close
    above high of preceding 3 completed M15 bars. H1 bullish: two
    consecutive completed H1 closes rising. These are predeclared
    exploratory proxies, NOT validated V9.4 indicators.
    """
    t = pd.Timestamp(observation_time)
    if t.tzinfo is None:
        raise ValueError("Observation time must have timezone")
    t = t.tz_convert("UTC")
    if t.second or t.microsecond:
        raise ValueError("Observation must be on minute boundary")
    if m1.index.has_duplicates:
        raise ValueError("Duplicate M1 timestamps")
    # M1 rows are OPEN-stamped; the row at t is not yet completed.
    past = m1.loc[m1.index < t].sort_index()
    if len(past) < 60 or past.index[-1] != t-pd.Timedelta(minutes=1):
        return {"action":"WAIT_DATA","reason":"Missing latest completed M1 bar"}
    tail = past.tail(60)
    expected = pd.date_range(t-pd.Timedelta(minutes=60), periods=60, freq="min", tz="UTC")
    if not tail.index.equals(expected):
        return {"action":"WAIT_DATA","reason":"Incomplete previous 60 M1 bars"}
    m5 = completed_bars(past, 5).loc[:t]
    m15 = completed_bars(past, 15).loc[:t]
    h1 = completed_bars(past, 60).loc[:t]
    if len(m5) < 5 or len(m15) < 4 or len(h1) < 2:
        return {"action":"WAIT_DATA","reason":"Insufficient completed higher-timeframe bars"}
    # Require consecutive completed windows; gaps invalidate evidence.
    for bars, count, minutes in ((m5,5,5),(m15,4,15),(h1,2,60)):
        segment=bars.tail(count)
        if segment.index[-1] != t.floor(f"{minutes}min") or not (
            segment.index.to_series().diff().iloc[1:] == pd.Timedelta(minutes=minutes)
        ).all():
            return {"action":"WAIT_DATA","reason":"Incomplete aligned indicator history"}
    rising = int((m5.close.diff().tail(4)>0).sum())
    m5_reversal = rising>=3 and m5.close.iloc[-1]>m5.close.iloc[-2]
    m15_invalid = bool(m15.close.iloc[-1] > m15.high.iloc[-4:-1].max())
    h1_bullish = bool(h1.close.iloc[-1] > h1.close.iloc[-2])
    e = SellExitEvidence(entry=entry, initial_stop=initial_stop,
                         current_stop=current_stop, price=float(past.close.iloc[-1]),
                         completed_m5_reversal=m5_reversal,
                         completed_m15_bullish_invalidation=m15_invalid,
                         h1_bullish_confirmation=h1_bullish,
                         partial_already_taken=partial_already_taken)
    return {**decide_sell_exit(e), "observed_utc":t.isoformat(),
            "evidence":{"m5_reversal":bool(m5_reversal),
                        "m15_bullish_invalidation":bool(m15_invalid),
                        "h1_bullish_confirmation":bool(h1_bullish)},
            "timestamp_semantics":"UNVERIFIED_OPEN_STAMP_ASSUMPTION",
            "data_scope":"COMPLETED_BARS_ONLY_RESEARCH"}
