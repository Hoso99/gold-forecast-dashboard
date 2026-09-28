"""V9.4 validation utilities: divergence, untouched holdout, module dependence."""
from __future__ import annotations
import numpy as np
import pandas as pd
from candle_power_v94 import analyze_last_10_candles


def indicator_divergence(gold, lookback=10):
    """Return RSI/MACD divergence using only completed bars up to the last row."""
    if gold is None or len(gold) < 40:
        return {"signal":"NONE","score":0.0,"detail":"insufficient data"}
    c=gold.close.astype(float)
    delta=c.diff(); up=delta.clip(lower=0); dn=(-delta.clip(upper=0))
    rs=up.rolling(14).mean()/dn.rolling(14).mean().replace(0,np.nan)
    rsi=100-100/(1+rs)
    ema12=c.ewm(span=12,adjust=False).mean(); ema26=c.ewm(span=26,adjust=False).mean()
    macd=ema12-ema26; hist=macd-macd.ewm(span=9,adjust=False).mean()
    old=slice(-(lookback+1),-max(2,lookback//2)); new=slice(-max(2,lookback//2),None)
    p_old=float(c.iloc[old].max()); p_new=float(c.iloc[new].max())
    pl_old=float(c.iloc[old].min()); pl_new=float(c.iloc[new].min())
    r_old=float(rsi.iloc[old].mean()); r_new=float(rsi.iloc[new].mean())
    m_old=float(hist.iloc[old].mean()); m_new=float(hist.iloc[new].mean())
    bearish=(p_new>p_old and (r_new<r_old or m_new<m_old))
    bullish=(pl_new<pl_old and (r_new>r_old or m_new>m_old))
    if bearish and not bullish: return {"signal":"SELL","score":-1.0,"detail":"price high strengthened while RSI/MACD momentum weakened"}
    if bullish and not bearish: return {"signal":"BUY","score":1.0,"detail":"price low weakened while RSI/MACD momentum strengthened"}
    return {"signal":"NONE","score":0.0,"detail":"no confirmed RSI/MACD divergence"}


def untouched_holdout_report(gold, holdout_fraction=.20, horizon=2, cost_bps=10):
    """Evaluate frozen 10-candle rules only on the final untouched chronological block."""
    cols=["status","holdout_bars","signals","buy_signals","sell_signals","accuracy","expectancy","profit_factor","max_drawdown"]
    if gold is None or len(gold)<250:
        return {k:("INSUFFICIENT DATA" if k=="status" else np.nan) for k in cols}
    split=max(40,int(len(gold)*(1-holdout_fraction))); rows=[]
    for i in range(split, len(gold)-horizon):
        p=analyze_last_10_candles(gold.iloc[:i+1])
        if p.signal not in {"BUY","SELL"}: continue
        side=1 if p.signal=="BUY" else -1
        ret=float(gold.close.iloc[i+horizon]/gold.close.iloc[i]-1)
        net=side*ret-float(cost_bps)/10000
        rows.append((p.signal,net))
    if not rows:
        return {"status":"NO HOLDOUT SIGNALS","holdout_bars":len(gold)-split,"signals":0,"buy_signals":0,"sell_signals":0,"accuracy":np.nan,"expectancy":np.nan,"profit_factor":np.nan,"max_drawdown":np.nan}
    sides=[x[0] for x in rows]; rets=np.array([x[1] for x in rows],float)
    gains=rets[rets>0].sum(); losses=-rets[rets<0].sum(); pf=gains/losses if losses>0 else np.inf
    curve=np.cumsum(rets); peak=np.maximum.accumulate(np.r_[0,curve])[1:]; dd=curve-peak
    return {"status":"UNTOUCHED HOLDOUT","holdout_bars":len(gold)-split,"signals":len(rows),"buy_signals":sides.count("BUY"),"sell_signals":sides.count("SELL"),"accuracy":float((rets>0).mean()),"expectancy":float(rets.mean()),"profit_factor":float(pf),"max_drawdown":float(dd.min())}


def module_dependence(module_history):
    """Measure, never assume, pairwise signal correlation and directional overlap."""
    if module_history is None or len(module_history)<20:
        return pd.DataFrame(columns=["Module A","Module B","Correlation","Directional overlap"])
    f=pd.DataFrame(module_history).copy(); out=[]; names=list(f.columns)
    for i,a in enumerate(names):
        for b in names[i+1:]:
            x=pd.to_numeric(f[a],errors="coerce"); y=pd.to_numeric(f[b],errors="coerce")
            valid=x.notna()&y.notna(); corr=float(x[valid].corr(y[valid])) if valid.sum()>=3 else np.nan
            active=valid&(x!=0)&(y!=0); overlap=float((np.sign(x[active])==np.sign(y[active])).mean()) if active.any() else np.nan
            out.append({"Module A":a,"Module B":b,"Correlation":corr,"Directional overlap":overlap})
    return pd.DataFrame(out)


def blocked_signal_audit(gold, holdout_fraction=.20, horizon=2, cost_bps=10,
                         atr_multiple=1.5, min_rr=2.0, swing_lookback=48):
    """Counterfactual audit of V9.4 gates on a chronological holdout block.

    A *candidate* is a BUY/SELL emitted by the frozen 10-candle power engine.
    For every candidate, this function records which reproducible V9.4 gates
    would have blocked it using information available at that timestamp, then
    settles the candidate two M15 bars later. Multiple gates may block the same
    candidate, so per-gate totals are descriptive. ``exclusive_*`` fields are
    the cleaner counterfactual: cases where that gate was the only blocker.

    Event-calendar and 5-minute reversal gates are deliberately not recreated
    from 15-minute OHLC; the coverage table marks them unavailable rather than
    fabricating historical inputs.
    """
    summary_cols = [
        "Gate", "Side", "Blocked cases", "Protected bad signals",
        "Missed good signals", "Ambiguous outcomes", "Good-signal rate",
        "Mean candidate net (bps)", "Exclusive blocks",
        "Exclusive missed good", "Exclusive protected bad",
        "Exclusive net effect if removed (bps)",
    ]
    coverage = pd.DataFrame([
        {"Gate":"Shock cooldown", "Historical audit":"YES", "Note":"Recomputed causally from M15 OHLC."},
        {"Gate":"Four-module threshold / confirmation", "Historical audit":"YES", "Note":"Uses candle power, M15 breakout/trend and RSI/MACD divergence; 5m reversal held neutral."},
        {"Gate":"Structure + ATR + minimum R:R", "Historical audit":"YES", "Note":"Recomputed from completed M15 structure with configured ATR and R:R."},
        {"Gate":"High-impact event lock", "Historical audit":"NO", "Note":"Historical event-state series is not present in the supplied M15 frame."},
        {"Gate":"5-minute reversal conflict", "Historical audit":"NO", "Note":"Aligned historical 5-minute reversal states are not present in the supplied M15 frame."},
        {"Gate":"Seven-venue / footprint context", "Historical audit":"NO", "Note":"Historical timestamp-aligned venue/footprint states are not present in the supplied M15 frame."},
    ])
    if gold is None or len(gold) < 250:
        return {
            "status":"INSUFFICIENT DATA", "candidates":0,
            "summary":pd.DataFrame(columns=summary_cols),
            "details":pd.DataFrame(), "coverage":coverage,
        }

    # Local imports avoid making validation_v94 a dependency hub at import time.
    from gold_model_v90 import shock_regime, mother_candle_breakout, short_term_technical_trend
    from four_module_v94 import evaluate_four_modules
    from structure_risk_v94 import structure_atr_plan

    frame = gold.copy()
    split = max(120, int(len(frame) * (1 - float(holdout_fraction))))
    shock_hist = shock_regime(frame)
    rows = []
    for i in range(split, len(frame) - int(horizon)):
        hist = frame.iloc[:i+1]
        power = analyze_last_10_candles(hist)
        candidate = str(power.signal).upper()
        if candidate not in {"BUY", "SELL"}:
            continue

        breakout = mother_candle_breakout(hist)
        trend = short_term_technical_trend(hist)
        divergence = indicator_divergence(hist)
        base_four = evaluate_four_modules(
            power, mother_breakout=breakout, short_trend=trend,
            reversal={"current_signal":0}, divergence=divergence,
            event_lock=False, shock_active=False)
        structure = structure_atr_plan(
            candidate, hist, atr_multiple=atr_multiple,
            min_tp1_rr=min_rr, swing_lookback=swing_lookback,
            cost_bps=cost_bps)

        blockers = []
        if bool(shock_hist.iloc[i].shock_cooldown):
            blockers.append("Shock cooldown")
        if base_four.signal != candidate or base_four.status != "QUALIFIED POWER SIGNAL":
            blockers.append("Four-module threshold / confirmation")
        if structure.get("status") != "ACTIVE":
            blockers.append("Structure + ATR + minimum R:R")

        entry = float(frame.close.iloc[i])
        future = frame.iloc[i+1:i+1+int(horizon)]
        side = 1.0 if candidate == "BUY" else -1.0
        raw_ret = side * (float(frame.close.iloc[i+int(horizon)]) / entry - 1.0)
        net_ret = raw_ret - float(cost_bps) / 10000.0
        net_bps = net_ret * 10000.0

        trade_outcome = "MARK-TO-MARKET"
        ambiguous = False
        if structure.get("status") == "ACTIVE":
            stop = float(structure["stop"]); target = float(structure["tp1"])
            for _, bar in future.iterrows():
                if candidate == "BUY":
                    stop_hit = float(bar.low) <= stop
                    target_hit = float(bar.high) >= target
                else:
                    stop_hit = float(bar.high) >= stop
                    target_hit = float(bar.low) <= target
                if stop_hit and target_hit:
                    trade_outcome = "AMBIGUOUS SAME BAR"
                    ambiguous = True
                    break
                if stop_hit:
                    trade_outcome = "STOP"
                    break
                if target_hit:
                    trade_outcome = "TARGET"
                    break
        good = (trade_outcome == "TARGET") or (trade_outcome == "MARK-TO-MARKET" and net_ret > 0)
        if trade_outcome == "STOP":
            good = False
        rows.append({
            "Timestamp": frame.index[i], "Side": candidate,
            "Entry": entry, "Buy power": float(power.buy_power),
            "Sell power": float(power.sell_power),
            "Blockers": tuple(blockers), "Blocker count": len(blockers),
            "30m net (bps)": float(net_bps), "Outcome": trade_outcome,
            "Good signal": bool(good), "Ambiguous": bool(ambiguous),
            "Shock active": bool(shock_hist.iloc[i].shock_cooldown),
            "Four-module signal": base_four.signal,
            "Structure status": structure.get("status"),
            "Structure reason": structure.get("reason"),
        })

    details = pd.DataFrame(rows)
    if details.empty:
        return {"status":"NO CANDIDATES", "candidates":0,
                "summary":pd.DataFrame(columns=summary_cols),
                "details":details, "coverage":coverage}

    out = []
    auditable_gates = [
        "Shock cooldown", "Four-module threshold / confirmation",
        "Structure + ATR + minimum R:R",
    ]
    for gate in auditable_gates:
        for side_name in ["ALL", "BUY", "SELL"]:
            mask = details["Blockers"].apply(lambda x: gate in x)
            if side_name != "ALL":
                mask &= details["Side"].eq(side_name)
            sub = details.loc[mask]
            exclusive = sub[sub["Blocker count"].eq(1)]
            nonamb = sub[~sub["Ambiguous"]]
            ex_nonamb = exclusive[~exclusive["Ambiguous"]]
            out.append({
                "Gate":gate, "Side":side_name,
                "Blocked cases":int(len(sub)),
                "Protected bad signals":int((~nonamb["Good signal"]).sum()),
                "Missed good signals":int(nonamb["Good signal"].sum()),
                "Ambiguous outcomes":int(sub["Ambiguous"].sum()),
                "Good-signal rate":float(nonamb["Good signal"].mean()) if len(nonamb) else np.nan,
                "Mean candidate net (bps)":float(nonamb["30m net (bps)"].mean()) if len(nonamb) else np.nan,
                "Exclusive blocks":int(len(exclusive)),
                "Exclusive missed good":int(ex_nonamb["Good signal"].sum()),
                "Exclusive protected bad":int((~ex_nonamb["Good signal"]).sum()),
                "Exclusive net effect if removed (bps)":float(ex_nonamb["30m net (bps)"].sum()) if len(ex_nonamb) else np.nan,
            })
    summary = pd.DataFrame(out, columns=summary_cols)
    return {
        "status":"HOLDOUT BLOCKED-SIGNAL AUDIT",
        "candidates":int(len(details)), "summary":summary,
        "details":details.sort_values("Timestamp", ascending=False),
        "coverage":coverage,
    }
