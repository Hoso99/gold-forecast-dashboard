"""V9.4 XAU/USD candle-dynamics research (research only; live V9.4 unchanged)."""
from __future__ import annotations
import json, os, time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd

SYMBOL="XAU/USD"; M1_TARGET=int(os.getenv("DYNAMICS_M1_BARS","225000")); BATCH_SIZE=min(int(os.getenv("DYNAMICS_BATCH_SIZE","5000")),5000)
PAUSE=float(os.getenv("DYNAMICS_REQUEST_PAUSE","10")); CYPRUS=ZoneInfo("Europe/Nicosia"); FOLLOW=(15,30,60,120,240)
OUT=Path("candle_dynamics_m15_v94.csv")

def fetch(params):
    with urlopen("https://api.twelvedata.com/time_series?"+urlencode(params),timeout=30) as r: return json.loads(r.read().decode())

def download(api):
    batches=[]; remaining=M1_TARGET; end=None
    while remaining>0:
        size=min(BATCH_SIZE,remaining); p={"symbol":SYMBOL,"interval":"1min","outputsize":size,"timezone":"UTC","format":"JSON","apikey":api}
        if end is not None: p["end_date"]=end.strftime("%Y-%m-%d %H:%M:%S")
        x=fetch(p)
        if x.get("status")=="error": raise RuntimeError("Twelve Data: "+str(x.get("message")))
        if not x.get("values"): break
        d=pd.DataFrame(x["values"]); d["datetime"]=pd.to_datetime(d["datetime"],utc=True,errors="coerce")
        for c in ["open","high","low","close"]: d[c]=pd.to_numeric(d[c],errors="coerce")
        d=d.set_index("datetime").sort_index()[["open","high","low","close"]].dropna()
        if d.empty: break
        batches.append(d); end=d.index[0]-pd.Timedelta(minutes=1); remaining-=len(d)
        print(f"Downloaded {len(d)} M1; oldest={d.index[0]}; remaining={remaining}")
        if len(d)<size: break
        if remaining>0: time.sleep(PAUSE)
    if not batches: raise RuntimeError("No M1 data downloaded")
    z=pd.concat(batches); return z[~z.index.duplicated(keep="last")].sort_index().tail(M1_TARGET)

def session(h):
    return "ASIA_00_07" if h<7 else "EUROPE_07_12" if h<12 else "EU_US_12_17" if h<17 else "US_LATE_17_22" if h<22 else "LATE_22_24"

def reconstruct(m1):
    w=m1.copy(); w["bucket"]=w.index.floor("15min"); rows=[]
    for t,g in w.groupby("bucket",sort=True):
        g=g.sort_index()
        if len(g)!=15: continue
        o=float(g.open.iloc[0]); h=float(g.high.max()); l=float(g.low.min()); c=float(g.close.iloc[-1]); body=c-o; rng=h-l
        mv=g.close.astype(float).diff().dropna(); signs=np.sign(mv.to_numpy()); nz=signs[signs!=0]; changes=int(np.sum(nz[1:]!=nz[:-1])) if len(nz)>1 else 0
        travel=float(mv.abs().sum()); seg=[]
        for s in (0,5,10):
            q=g.iloc[s:s+5]; m=q.close.astype(float).diff().dropna(); seg.append((float(q.close.iloc[-1]-q.open.iloc[0]),float(abs(m[m<0].sum())),float(m[m>0].sum()),float(m.abs().sum())))
        ht=g.high.idxmax(); lt=g.low.idxmin(); seq="HIGH_FIRST" if ht<lt else "LOW_FIRST" if lt<ht else "SAME_MINUTE_AMBIGUOUS"
        rev=[]; a=g.close.astype(float).to_numpy(); last=0; leg=a[0]; prev=a[0]
        for v in a[1:]:
            s=np.sign(v-prev)
            if s!=0:
                if last!=0 and s!=last: rev.append(abs(prev-leg)); leg=prev
                last=s
            prev=v
        cy=t.tz_convert(CYPRUS)
        rows.append(dict(model_time=t,cyprus_time=cy,utc_hour=t.hour,cyprus_hour=cy.hour,session_utc=session(t.hour),open=o,high=h,low=l,close=c,body=body,body_abs=abs(body),range=rng,upper_wick=h-max(o,c),lower_wick=min(o,c)-l,up_moves=int((mv>0).sum()),down_moves=int((mv<0).sum()),flat_moves=int((mv==0).sum()),direction_changes=changes,total_travel=travel,directional_efficiency=abs(body)/travel if travel else np.nan,early_net_1_5=seg[0][0],middle_net_6_10=seg[1][0],late_net_11_15=seg[2][0],early_sell=seg[0][1],middle_sell=seg[1][1],late_sell=seg[2][1],early_buy=seg[0][2],middle_buy=seg[1][2],late_buy=seg[2][2],early_travel=seg[0][3],middle_travel=seg[1][3],late_travel=seg[2][3],sell_acceleration_to_close=seg[2][1]-seg[0][1],buy_acceleration_to_close=seg[2][2]-seg[0][2],high_low_sequence=seq,high_minute=int((ht-t).total_seconds()//60)+1,low_minute=int((lt-t).total_seconds()//60)+1,avg_reversal_size=float(np.mean(rev)) if rev else 0,max_reversal_size=float(np.max(rev)) if rev else 0,travel=travel,reversal_count=changes,seg1_net=seg[0][0],seg2_net=seg[1][0],seg3_net=seg[2][0],event_regime="UNKNOWN"))
    if not rows: raise RuntimeError("No complete M15 groups reconstructed")
    return pd.DataFrame(rows).set_index("model_time").sort_index()

def enrich(d):
    d=d.copy(); pc=d.close.shift(1); tr=pd.concat([d.high-d.low,(d.high-pc).abs(),(d.low-pc).abs()],axis=1).max(axis=1); d["atr14"]=tr.rolling(14).mean(); d["range_atr_ratio"]=d.range/d.atr14
    q33=d.range_atr_ratio.rolling(200,min_periods=50).quantile(.33); q67=d.range_atr_ratio.rolling(200,min_periods=50).quantile(.67); d["volatility_regime"]=np.where(d.range_atr_ratio<=q33,"QUIET",np.where(d.range_atr_ratio>=q67,"HIGH","NORMAL"))
    ph=d.high.shift(1); pl=d.low.shift(1); d["break_prev_high"]=d.high>ph; d["break_prev_low"]=d.low<pl; d["high_break_continuation"]=d.close>ph; d["high_break_rejection"]=d.break_prev_high&(d.close<=ph); d["low_break_continuation"]=d.close<pl; d["low_break_rejection"]=d.break_prev_low&(d.close>=pl)
    d["resistance_48"]=d.high.shift(1).rolling(48).max(); d["support_48"]=d.low.shift(1).rolling(48).min(); d["distance_to_resistance_atr"]=(d.resistance_48-d.close)/d.atr14; d["distance_to_support_atr"]=(d.close-d.support_48)/d.atr14
    d["bearish_candidate"]=(d.body<0)&(d.late_sell>d.late_buy)&(d.sell_acceleration_to_close>0); d["bullish_candidate"]=(d.body>0)&(d.late_buy>d.late_sell)&(d.buy_acceleration_to_close>0)
    for mins in FOLLOW:
        n=mins//15; d[f"forward_{mins}m"]=d.close.shift(-n)-d.close; lows=pd.concat([d.low.shift(-k) for k in range(1,n+1)],axis=1).min(axis=1); highs=pd.concat([d.high.shift(-k) for k in range(1,n+1)],axis=1).max(axis=1); d[f"sell_mfe_{mins}m"]=d.close-lows; d[f"sell_mae_{mins}m"]=highs-d.close
    d["false_sell_60m"]=d.bearish_candidate&(d.forward_60m>0); return d

def summaries(d):
    t=d.assign(large_move=d.range_atr_ratio>=1.25).groupby(["utc_hour","session_utc"]).agg(candles=("close","size"),avg_range=("range","mean"),avg_range_atr=("range_atr_ratio","mean"),large_move_rate=("large_move","mean"),avg_sell_accel=("sell_acceleration_to_close","mean"),bearish_candidate_rate=("bearish_candidate","mean"),avg_forward_60m=("forward_60m","mean")).reset_index()
    rows=[]
    for reg in ["QUIET","NORMAL","HIGH"]:
        g=d[d.volatility_regime==reg]
        for name,mask in [("BEARISH_CANDIDATE",g.bearish_candidate),("BULLISH_CANDIDATE",g.bullish_candidate),("LOW_BREAK_REJECTION",g.low_break_rejection),("HIGH_BREAK_REJECTION",g.high_break_rejection)]:
            x=g[mask]; rows.append(dict(volatility_regime=reg,pattern=name,count=len(x),avg_efficiency=x.directional_efficiency.mean(),avg_forward_15m=x.forward_15m.mean(),avg_forward_30m=x.forward_30m.mean(),avg_forward_60m=x.forward_60m.mean(),avg_forward_120m=x.forward_120m.mean(),avg_sell_mfe_60m=x.sell_mfe_60m.mean(),avg_sell_mae_60m=x.sell_mae_60m.mean()))
    p=pd.DataFrame(rows); f=[]
    for name,mask in [("ALL",pd.Series(True,index=d.index)),("BEARISH_CANDIDATE",d.bearish_candidate),("FALSE_SELL_60M",d.false_sell_60m),("HIGH_FIRST",d.high_low_sequence.eq("HIGH_FIRST")),("LOW_FIRST",d.high_low_sequence.eq("LOW_FIRST"))]:
        g=d[mask]; row={"group":name,"count":len(g)}
        for mins in FOLLOW: row[f"avg_forward_{mins}m"]=g[f"forward_{mins}m"].mean(); row[f"avg_sell_mfe_{mins}m"]=g[f"sell_mfe_{mins}m"].mean(); row[f"avg_sell_mae_{mins}m"]=g[f"sell_mae_{mins}m"].mean()
        f.append(row)
    return t,p,pd.DataFrame(f)

def detailed_intracandle_analysis(d):
    """Compare early/middle/late M15 dynamics and false-SELL behaviour."""

    x = d.copy()

    # Direction of each 5-minute section
    x["phase_1_dir"] = np.sign(x["seg1_net"])
    x["phase_2_dir"] = np.sign(x["seg2_net"])
    x["phase_3_dir"] = np.sign(x["seg3_net"])

    # Absolute movement during each section
    x["phase_1_move"] = x["seg1_net"].abs()
    x["phase_2_move"] = x["seg2_net"].abs()
    x["phase_3_move"] = x["seg3_net"].abs()

    # Selling acceleration toward M15 close
    x["late_sell_acceleration"] = (
        (-x["seg3_net"]) - (-x["seg1_net"])
    )

    # Which third contained the largest net movement
    phase_moves = x[
        ["phase_1_move", "phase_2_move", "phase_3_move"]
    ]

    x["dominant_phase"] = (
        phase_moves.idxmax(axis=1)
        .str.replace("phase_", "", regex=False)
        .str.replace("_move", "", regex=False)
    )

    # Path classification
    x["path_type"] = "MIXED"

    x.loc[
        (x["seg1_net"] < 0)
        & (x["seg2_net"] < 0)
        & (x["seg3_net"] < 0),
        "path_type",
    ] = "SELL_ALL_3"

    x.loc[
        (x["seg1_net"] >= 0)
        & (x["seg2_net"] < 0)
        & (x["seg3_net"] < 0),
        "path_type",
    ] = "LATE_SELL"

    x.loc[
        (x["seg1_net"] < 0)
        & (x["seg2_net"] < 0)
        & (x["seg3_net"] >= 0),
        "path_type",
    ] = "SELL_THEN_RECOVERY"

    x.loc[
        (x["seg1_net"] > 0)
        & (x["seg2_net"] > 0)
        & (x["seg3_net"] < 0),
        "path_type",
    ] = "LATE_REVERSAL_SELL"

    # Successful bearish follow-through:
    # bearish candidate whose next 60-minute return is <= 0
    x["successful_sell_60m"] = (
        x["bearish_candidate"]
        & (x["forward_60m"] <= 0)
    )

    # Existing false SELL definition:
    # bearish candidate followed by positive 60-minute return
    x["false_sell_case"] = x["false_sell_60m"]

    groups = []

    for name, mask in [
        ("ALL", pd.Series(True, index=x.index)),
        ("SUCCESSFUL_SELL_60M", x["successful_sell_60m"]),
        ("FALSE_SELL_60M", x["false_sell_case"]),
    ]:
        g = x[mask].copy()

        if g.empty:
            continue

        groups.append({
            "group": name,
            "count": len(g),
            "avg_seg1_net": g["seg1_net"].mean(),
            "avg_seg2_net": g["seg2_net"].mean(),
            "avg_seg3_net": g["seg3_net"].mean(),
            "avg_late_sell_acceleration":
                g["late_sell_acceleration"].mean(),
            "avg_reversals": g["reversal_count"].mean(),
            "avg_travel": g["travel"].mean(),
            "avg_efficiency":
                g["directional_efficiency"].mean(),
            "high_first_rate":
                (g["high_low_sequence"] == "HIGH_FIRST").mean(),
            "low_first_rate":
                (g["high_low_sequence"] == "LOW_FIRST").mean(),
            "avg_forward_15m": g["forward_15m"].mean(),
            "avg_forward_30m": g["forward_30m"].mean(),
            "avg_forward_60m": g["forward_60m"].mean(),
            "avg_forward_120m": g["forward_120m"].mean(),
            "avg_sell_mfe_60m": g["sell_mfe_60m"].mean(),
            "avg_sell_mae_60m": g["sell_mae_60m"].mean(),
        })

    detail = pd.DataFrame(groups)

    path_summary = (
        x.groupby("path_type")
        .agg(
            count=("close", "size"),
            avg_body=("body", "mean"),
            avg_range=("range", "mean"),
            avg_travel=("travel", "mean"),
            avg_efficiency=("directional_efficiency", "mean"),
            avg_reversals=("reversal_count", "mean"),
            avg_forward_15m=("forward_15m", "mean"),
            avg_forward_30m=("forward_30m", "mean"),
            avg_forward_60m=("forward_60m", "mean"),
            avg_forward_120m=("forward_120m", "mean"),
            false_sell_rate=("false_sell_case", "mean"),
        )
        .reset_index()
    )

    return x, detail, path_summary

def analyze_sell_combinations(d):
    """Research combinations that separate successful from false SELL patterns."""

    x = d.copy()

    # Only bearish candidates are relevant to this SELL-only study.
    x = x[x["bearish_candidate"]].copy()

    # Outcome classification using the next 60 minutes.
    x["sell_outcome"] = np.where(
        x["forward_60m"] <= 0,
        "SUCCESSFUL_SELL_60M",
        "FALSE_SELL_60M",
    )

    # Efficiency buckets.
    x["efficiency_bucket"] = pd.cut(
        x["directional_efficiency"],
        bins=[-np.inf, 0.10, 0.20, 0.35, np.inf],
        labels=["VERY_LOW", "LOW", "MEDIUM", "HIGH"],
    )

    # Reversal buckets.
    x["reversal_bucket"] = pd.cut(
        x["reversal_count"],
        bins=[-1, 4, 7, 10, np.inf],
        labels=["LOW", "MEDIUM", "HIGH", "VERY_HIGH"],
    )

    # Late-selling strength.
    x["late_sell_strength"] = pd.cut(
        x["late_sell_acceleration"],
        bins=[-np.inf, 0, 1, 2, np.inf],
        labels=["NONE", "MILD", "STRONG", "VERY_STRONG"],
    )

    # High/low sequence.
    x["sequence_type"] = x["high_low_sequence"]

    group_cols = [
        "volatility_regime",
        "session_utc",
        "path_type",
        "efficiency_bucket",
        "reversal_bucket",
        "late_sell_strength",
        "sequence_type",
    ]

    rows = []

    for keys, g in x.groupby(
        group_cols,
        observed=True,
        dropna=False,
    ):
        if len(g) < 10:
            continue

        successful = (
            g["sell_outcome"] == "SUCCESSFUL_SELL_60M"
        ).sum()

        false = (
            g["sell_outcome"] == "FALSE_SELL_60M"
        ).sum()

        rows.append({
            "volatility_regime": keys[0],
            "session_utc": keys[1],
            "path_type": keys[2],
            "efficiency_bucket": keys[3],
            "reversal_bucket": keys[4],
            "late_sell_strength": keys[5],
            "sequence_type": keys[6],
            "samples": len(g),
            "successful_sell_60m": int(successful),
            "false_sell_60m": int(false),
            "success_rate_60m": successful / len(g),
            "avg_forward_15m": g["forward_15m"].mean(),
            "avg_forward_30m": g["forward_30m"].mean(),
            "avg_forward_60m": g["forward_60m"].mean(),
            "avg_forward_120m": g["forward_120m"].mean(),
            "avg_sell_mfe_60m": g["sell_mfe_60m"].mean(),
            "avg_sell_mae_60m": g["sell_mae_60m"].mean(),
            "avg_efficiency": g["directional_efficiency"].mean(),
            "avg_reversals": g["reversal_count"].mean(),
            "avg_late_sell_acceleration":
                g["late_sell_acceleration"].mean(),
        })

    result = pd.DataFrame(rows)

    if result.empty:
        return result

    return result.sort_values(
        ["success_rate_60m", "samples"],
        ascending=[False, False],
    ).reset_index(drop=True)

def compare_sell_filters(d):
    """Compare progressively stricter SELL filters on the same historical M15 data."""
    x = d.copy()
    x = x[x["bearish_candidate"]].copy()
    x["success"] = x["forward_60m"] <= 0
    x["BASE"] = True
    x["LATE_SELL"] = (
        (x["seg3_net"] < 0)
        & (x["late_sell_acceleration"] > 0)
    )
    x["LATE_SELL_EFFICIENT"] = (
        x["LATE_SELL"]
        & (x["directional_efficiency"] >= 0.20)
    )
    x["LATE_SELL_EFFICIENT_HIGH_FIRST"] = (
        x["LATE_SELL_EFFICIENT"]
        & (x["high_low_sequence"] == "HIGH_FIRST")
    )
    x["PERSISTENT_SELL"] = (
        (x["seg2_net"] < 0)
        & (x["seg3_net"] < 0)
        & (x["late_sell_acceleration"] > 0)
        & (x["directional_efficiency"] >= 0.20)
        & (x["high_low_sequence"] == "HIGH_FIRST")
    )

    filters = [
        "BASE",
        "LATE_SELL",
        "LATE_SELL_EFFICIENT",
        "LATE_SELL_EFFICIENT_HIGH_FIRST",
        "PERSISTENT_SELL",
    ]
    rows = []
    base_count = len(x)
    base_success = int(x["success"].sum())

    for name in filters:
        g = x[x[name]].copy()
        if g.empty:
            continue
        successful = int(g["success"].sum())
        false = len(g) - successful
        rows.append({
            "filter": name,
            "signals": len(g),
            "signals_kept_pct": 100.0 * len(g) / base_count if base_count else np.nan,
            "successful_sell_60m": successful,
            "false_sell_60m": false,
            "success_rate_60m": successful / len(g),
            "good_sells_kept_pct": 100.0 * successful / base_success if base_success else np.nan,
            "avg_forward_15m": g["forward_15m"].mean(),
            "avg_forward_30m": g["forward_30m"].mean(),
            "avg_forward_60m": g["forward_60m"].mean(),
            "avg_forward_120m": g["forward_120m"].mean(),
            "avg_sell_mfe_60m": g["sell_mfe_60m"].mean(),
            "avg_sell_mae_60m": g["sell_mae_60m"].mean(),
            "avg_efficiency": g["directional_efficiency"].mean(),
            "avg_reversals": g["reversal_count"].mean(),
            "avg_late_sell_acceleration": g["late_sell_acceleration"].mean(),
        })
    return pd.DataFrame(rows)


def compare_directional_efficiency_thresholds(d):
    """Research directional-efficiency thresholds without changing live V9.4."""
    x = d.copy()
    x = x[x["bearish_candidate"]].copy()
    x["success"] = x["forward_60m"] <= 0

    # Keep the same prerequisite used by the current best research filter.
    x = x[
        (x["seg3_net"] < 0)
        & (x["late_sell_acceleration"] > 0)
    ].copy()

    thresholds = [0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40]
    rows = []
    base_count = len(x)
    base_success = int(x["success"].sum())

    for threshold in thresholds:
        g = x[x["directional_efficiency"] >= threshold].copy()
        if g.empty:
            continue

        successful = int(g["success"].sum())
        false = len(g) - successful
        rows.append({
            "efficiency_threshold": threshold,
            "signals": len(g),
            "signals_kept_pct": 100.0 * len(g) / base_count if base_count else np.nan,
            "successful_sell_60m": successful,
            "false_sell_60m": false,
            "success_rate_60m": successful / len(g),
            "good_sells_kept_pct": 100.0 * successful / base_success if base_success else np.nan,
            "avg_forward_15m": g["forward_15m"].mean(),
            "avg_forward_30m": g["forward_30m"].mean(),
            "avg_forward_60m": g["forward_60m"].mean(),
            "avg_forward_120m": g["forward_120m"].mean(),
            "avg_sell_mfe_60m": g["sell_mfe_60m"].mean(),
            "avg_sell_mae_60m": g["sell_mae_60m"].mean(),
            "avg_efficiency": g["directional_efficiency"].mean(),
            "avg_reversals": g["reversal_count"].mean(),
            "avg_late_sell_acceleration": g["late_sell_acceleration"].mean(),
        })

    return pd.DataFrame(rows)


def multi_factor_sell_search(d):
    """Grid-search SELL confirmation combinations on historical M15 research data.

    Research only.  The live V9.4 decision engine is not modified.
    Negative forward returns are favourable for a SELL.
    """
    x = d.copy()
    x = x[x["bearish_candidate"]].copy()

    efficiency_thresholds = [0.10, 0.20, 0.30, 0.35, 0.40]
    reversal_limits = [4, 6, 8, 10, 12]
    acceleration_thresholds = [0.0, 1.0, 2.0, 3.0, 4.0]
    persistence_modes = ["SEG3", "SEG2_SEG3"]
    sequence_modes = ["ANY", "HIGH_FIRST"]
    regime_modes = ["ALL", "QUIET", "NORMAL", "HIGH"]

    rows = []
    base_count = len(x)

    for eff in efficiency_thresholds:
        for max_rev in reversal_limits:
            for accel in acceleration_thresholds:
                for persistence in persistence_modes:
                    for sequence in sequence_modes:
                        for regime in regime_modes:
                            mask = (
                                (x["directional_efficiency"] >= eff)
                                & (x["reversal_count"] <= max_rev)
                                & (x["late_sell_acceleration"] >= accel)
                                & (x["seg3_net"] < 0)
                            )
                            if persistence == "SEG2_SEG3":
                                mask &= x["seg2_net"] < 0
                            if sequence == "HIGH_FIRST":
                                mask &= x["high_low_sequence"] == "HIGH_FIRST"
                            if regime != "ALL":
                                mask &= x["volatility_regime"] == regime

                            g = x[mask].copy()
                            n = len(g)
                            if n < 50:
                                continue

                            row = {
                                "efficiency_min": eff,
                                "max_reversals": max_rev,
                                "late_sell_accel_min": accel,
                                "persistence": persistence,
                                "sequence": sequence,
                                "volatility_regime": regime,
                                "signals": n,
                                "signals_kept_pct": 100.0 * n / base_count if base_count else np.nan,
                                "avg_efficiency": g["directional_efficiency"].mean(),
                                "avg_reversals": g["reversal_count"].mean(),
                                "avg_late_sell_acceleration": g["late_sell_acceleration"].mean(),
                                "avg_sell_mfe_60m": g["sell_mfe_60m"].mean(),
                                "avg_sell_mae_60m": g["sell_mae_60m"].mean(),
                            }
                            for minutes in (15, 30, 60, 120):
                                col = f"forward_{minutes}m"
                                row[f"success_rate_{minutes}m"] = (g[col] <= 0).mean()
                                row[f"avg_forward_{minutes}m"] = g[col].mean()

                            # A ranking aid, not a trading rule: reward consistent SELL
                            # continuation at 30/60/120m while requiring a useful sample.
                            row["continuation_score"] = (
                                0.25 * row["success_rate_30m"]
                                + 0.50 * row["success_rate_60m"]
                                + 0.25 * row["success_rate_120m"]
                            )
                            rows.append(row)

    result = pd.DataFrame(rows)
    if result.empty:
        return result

    return result.sort_values(
        ["continuation_score", "signals"],
        ascending=[False, False],
    ).reset_index(drop=True)


def out_of_sample_multifactor_validation(d, train_fraction=0.70, top_n=20):
    """Chronological discovery/validation for the multi-factor SELL search.

    The first 70% is discovery data and the final 30% is unseen validation data.
    Eight M15 candles (120 minutes) are purged before the split so discovery
    outcomes cannot use prices from the validation period. Research only.
    """
    x = d.copy().sort_index()
    n = len(x)
    split_i = int(n * train_fraction)
    purge = 8  # 120m maximum forward horizon / 15m
    if split_i <= purge or split_i >= n:
        return pd.DataFrame(), pd.DataFrame()

    discovery = x.iloc[:split_i - purge].copy()
    validation = x.iloc[split_i:].copy()
    ranked = multi_factor_sell_search(discovery)
    if ranked.empty:
        return ranked, pd.DataFrame()

    selected = ranked.head(top_n).copy()
    rows = []
    base = validation[validation["bearish_candidate"]].copy()

    for rank, rule in selected.reset_index(drop=True).iterrows():
        mask = (
            (base["directional_efficiency"] >= rule["efficiency_min"])
            & (base["reversal_count"] <= rule["max_reversals"])
            & (base["late_sell_acceleration"] >= rule["late_sell_accel_min"])
            & (base["seg3_net"] < 0)
        )
        if rule["persistence"] == "SEG2_SEG3":
            mask &= base["seg2_net"] < 0
        if rule["sequence"] == "HIGH_FIRST":
            mask &= base["high_low_sequence"] == "HIGH_FIRST"
        if rule["volatility_regime"] != "ALL":
            mask &= base["volatility_regime"] == rule["volatility_regime"]

        g = base[mask].copy()
        row = {
            "discovery_rank": rank + 1,
            "efficiency_min": rule["efficiency_min"],
            "max_reversals": rule["max_reversals"],
            "late_sell_accel_min": rule["late_sell_accel_min"],
            "persistence": rule["persistence"],
            "sequence": rule["sequence"],
            "volatility_regime": rule["volatility_regime"],
            "discovery_signals": int(rule["signals"]),
            "discovery_score": rule["continuation_score"],
            "validation_signals": len(g),
        }
        for minutes in (15, 30, 60, 120):
            col = f"forward_{minutes}m"
            row[f"discovery_success_{minutes}m"] = rule[f"success_rate_{minutes}m"]
            row[f"validation_success_{minutes}m"] = (g[col] <= 0).mean() if len(g) else np.nan
            row[f"validation_avg_forward_{minutes}m"] = g[col].mean() if len(g) else np.nan
        row["validation_score"] = (
            0.25 * row["validation_success_30m"]
            + 0.50 * row["validation_success_60m"]
            + 0.25 * row["validation_success_120m"]
        ) if len(g) else np.nan
        row["score_change"] = row["validation_score"] - row["discovery_score"] if len(g) else np.nan
        row["validation_avg_sell_mfe_60m"] = g["sell_mfe_60m"].mean() if len(g) else np.nan
        row["validation_avg_sell_mae_60m"] = g["sell_mae_60m"].mean() if len(g) else np.nan
        rows.append(row)

    result = pd.DataFrame(rows)
    metadata = pd.DataFrame([{
        "total_complete_m15": n,
        "discovery_candles": len(discovery),
        "purged_candles": purge,
        "validation_candles": len(validation),
        "discovery_start": discovery.index.min(),
        "discovery_end": discovery.index.max(),
        "validation_start": validation.index.min(),
        "validation_end": validation.index.max(),
        "train_fraction": train_fraction,
        "top_rules_validated": min(top_n, len(ranked)),
    }])
    return metadata, result


def validate_simple_three_filter_rule(d, train_fraction=0.70):
    """Validate one simple, pre-specified 3-filter SELL confirmation rule.

    Filters derived from the robust region of the prior research, not from a new
    grid search:
      1) directional efficiency >= 0.10
      2) reversal count <= 4
      3) persistence: segment 2 and segment 3 net movement are both bearish

    The existing bearish_candidate definition remains the starting population.
    Results are reported for discovery, unseen validation, and all data.
    Research only; live V9.4 is not modified.
    """
    x = d.copy().sort_index()
    n = len(x)
    split_i = int(n * train_fraction)
    purge = 8
    if split_i <= purge or split_i >= n:
        return pd.DataFrame(), pd.DataFrame()

    discovery = x.iloc[:split_i - purge].copy()
    validation = x.iloc[split_i:].copy()

    def apply_rule(frame):
        base = frame[frame["bearish_candidate"]].copy()
        mask = (
            (base["directional_efficiency"] >= 0.10)
            & (base["reversal_count"] <= 4)
            & (base["seg2_net"] < 0)
            & (base["seg3_net"] < 0)
        )
        return base, base[mask].copy()

    rows = []
    for label, frame in (("DISCOVERY", discovery), ("VALIDATION", validation), ("ALL", x)):
        base, g = apply_rule(frame)
        row = {
            "sample": label,
            "complete_m15": len(frame),
            "bearish_candidates": len(base),
            "signals": len(g),
            "signals_kept_pct": 100.0 * len(g) / len(base) if len(base) else np.nan,
            "efficiency_min": 0.10,
            "max_reversals": 4,
            "persistence": "SEG2_SEG3",
            "avg_efficiency": g["directional_efficiency"].mean() if len(g) else np.nan,
            "avg_reversals": g["reversal_count"].mean() if len(g) else np.nan,
            "avg_late_sell_acceleration": g["late_sell_acceleration"].mean() if len(g) else np.nan,
            "avg_sell_mfe_60m": g["sell_mfe_60m"].mean() if len(g) else np.nan,
            "avg_sell_mae_60m": g["sell_mae_60m"].mean() if len(g) else np.nan,
        }
        for minutes in (15, 30, 60, 120):
            col = f"forward_{minutes}m"
            row[f"success_rate_{minutes}m"] = (g[col] <= 0).mean() if len(g) else np.nan
            row[f"false_sell_rate_{minutes}m"] = (g[col] > 0).mean() if len(g) else np.nan
            row[f"avg_forward_{minutes}m"] = g[col].mean() if len(g) else np.nan
        rows.append(row)

    metadata = pd.DataFrame([{
        "rule": "EFF>=0.10 + REV<=4 + SEG2&SEG3 bearish",
        "total_complete_m15": n,
        "discovery_candles": len(discovery),
        "purged_candles": purge,
        "validation_candles": len(validation),
        "discovery_start": discovery.index.min(),
        "discovery_end": discovery.index.max(),
        "validation_start": validation.index.min(),
        "validation_end": validation.index.max(),
        "train_fraction": train_fraction,
    }])
    return metadata, pd.DataFrame(rows)


def compare_three_filter_components(d, train_fraction=0.70):
    """Ablation test for the three fixed SELL filters on the same OOS split.

    This does not search new thresholds. It compares BASE, each single filter,
    each pair, and the original 3-filter rule on discovery and validation.
    Research only; live V9.4 is not modified.
    """
    x = d.copy().sort_index()
    n = len(x)
    split_i = int(n * train_fraction)
    purge = 8
    if split_i <= purge or split_i >= n:
        return pd.DataFrame()

    discovery = x.iloc[:split_i - purge].copy()
    validation = x.iloc[split_i:].copy()

    rules = {
        "BASE": lambda b: pd.Series(True, index=b.index),
        "EFF_ONLY": lambda b: b["directional_efficiency"] >= 0.10,
        "REV_ONLY": lambda b: b["reversal_count"] <= 4,
        "PERSIST_ONLY": lambda b: (b["seg2_net"] < 0) & (b["seg3_net"] < 0),
        "EFF_REV": lambda b: (b["directional_efficiency"] >= 0.10) & (b["reversal_count"] <= 4),
        "EFF_PERSIST": lambda b: (b["directional_efficiency"] >= 0.10) & (b["seg2_net"] < 0) & (b["seg3_net"] < 0),
        "REV_PERSIST": lambda b: (b["reversal_count"] <= 4) & (b["seg2_net"] < 0) & (b["seg3_net"] < 0),
        "ALL_3": lambda b: (b["directional_efficiency"] >= 0.10) & (b["reversal_count"] <= 4) & (b["seg2_net"] < 0) & (b["seg3_net"] < 0),
    }

    rows=[]
    for sample, frame in (("DISCOVERY", discovery), ("VALIDATION", validation)):
        base=frame[frame["bearish_candidate"]].copy()
        for rule_name, rule in rules.items():
            g=base[rule(base)].copy()
            row={
                "sample": sample, "rule": rule_name,
                "bearish_candidates": len(base), "signals": len(g),
                "signals_kept_pct": 100.0*len(g)/len(base) if len(base) else np.nan,
                "avg_efficiency": g["directional_efficiency"].mean() if len(g) else np.nan,
                "avg_reversals": g["reversal_count"].mean() if len(g) else np.nan,
                "avg_sell_mfe_60m": g["sell_mfe_60m"].mean() if len(g) else np.nan,
                "avg_sell_mae_60m": g["sell_mae_60m"].mean() if len(g) else np.nan,
            }
            for minutes in (15,30,60,120):
                col=f"forward_{minutes}m"
                row[f"success_rate_{minutes}m"]=(g[col] <= 0).mean() if len(g) else np.nan
                row[f"avg_forward_{minutes}m"]=g[col].mean() if len(g) else np.nan
            rows.append(row)
    return pd.DataFrame(rows)


def optimize_persistence_filter(d, train_fraction=0.70):
    """Out-of-sample research focused only on bearish persistence.

    Tests simple persistence definitions and strength thresholds on the same
    discovery/validation split. No live V9.4 files or thresholds are changed.
    """
    x = d.copy().sort_index()
    n = len(x)
    split_i = int(n * train_fraction)
    purge = 8
    if split_i <= purge or split_i >= n:
        return pd.DataFrame(), pd.DataFrame()

    discovery = x.iloc[:split_i - purge].copy()
    validation = x.iloc[split_i:].copy()

    # Persistence families.  SEG2_SEG3 is the current strongest component.
    # Strength uses the combined bearish net move of the late two segments.
    def add_features(frame):
        b = frame[frame["bearish_candidate"]].copy()
        b["late_two_net"] = b["seg2_net"] + b["seg3_net"]
        b["late_two_bearish_strength"] = -b["late_two_net"]
        return b

    disc = add_features(discovery)
    val = add_features(validation)

    # Fixed, interpretable candidate rules. Thresholds are learned/ranked only
    # on discovery; validation is reported separately.
    candidates = []
    for mode in ("SEG3", "SEG2_SEG3"):
        for strength_min in (0.0, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0):
            candidates.append((mode, strength_min))

    def mask_for(b, mode, strength_min):
        if mode == "SEG3":
            m = b["seg3_net"] < 0
        else:
            m = (b["seg2_net"] < 0) & (b["seg3_net"] < 0)
        if strength_min > 0:
            m &= b["late_two_bearish_strength"] >= strength_min
        return m

    discovery_rows=[]
    for mode, strength_min in candidates:
        g=disc[mask_for(disc, mode, strength_min)].copy()
        row={
            "persistence_mode": mode,
            "strength_min": strength_min,
            "bearish_candidates": len(disc),
            "signals": len(g),
            "signals_kept_pct": 100.0*len(g)/len(disc) if len(disc) else np.nan,
            "avg_late_two_bearish_strength": g["late_two_bearish_strength"].mean() if len(g) else np.nan,
            "avg_efficiency": g["directional_efficiency"].mean() if len(g) else np.nan,
            "avg_reversals": g["reversal_count"].mean() if len(g) else np.nan,
            "avg_sell_mfe_60m": g["sell_mfe_60m"].mean() if len(g) else np.nan,
            "avg_sell_mae_60m": g["sell_mae_60m"].mean() if len(g) else np.nan,
        }
        for minutes in (15,30,60,120):
            col=f"forward_{minutes}m"
            row[f"success_rate_{minutes}m"]=(g[col] <= 0).mean() if len(g) else np.nan
            row[f"avg_forward_{minutes}m"]=g[col].mean() if len(g) else np.nan
        # Balanced continuation score; 60m receives the largest weight.
        row["discovery_score"]=(
            0.20*row["success_rate_15m"] +
            0.25*row["success_rate_30m"] +
            0.40*row["success_rate_60m"] +
            0.15*row["success_rate_120m"]
        ) if len(g) else np.nan
        discovery_rows.append(row)

    ranked=pd.DataFrame(discovery_rows)
    # Avoid selecting tiny samples. Keep rules with >=5% of bearish candidates
    # and at least 50 discovery signals, then rank by discovery score.
    eligible=ranked[(ranked["signals"] >= 50) & (ranked["signals_kept_pct"] >= 5.0)].copy()
    eligible=eligible.sort_values(["discovery_score","signals"], ascending=[False,False])

    validation_rows=[]
    for rank, (_, rule) in enumerate(eligible.head(12).iterrows(), start=1):
        g=val[mask_for(val, rule["persistence_mode"], float(rule["strength_min"]))].copy()
        out={
            "discovery_rank": rank,
            "persistence_mode": rule["persistence_mode"],
            "strength_min": rule["strength_min"],
            "discovery_signals": int(rule["signals"]),
            "discovery_kept_pct": rule["signals_kept_pct"],
            "discovery_score": rule["discovery_score"],
            "validation_candidates": len(val),
            "validation_signals": len(g),
            "validation_kept_pct": 100.0*len(g)/len(val) if len(val) else np.nan,
            "validation_avg_late_two_bearish_strength": g["late_two_bearish_strength"].mean() if len(g) else np.nan,
            "validation_avg_sell_mfe_60m": g["sell_mfe_60m"].mean() if len(g) else np.nan,
            "validation_avg_sell_mae_60m": g["sell_mae_60m"].mean() if len(g) else np.nan,
        }
        for minutes in (15,30,60,120):
            col=f"forward_{minutes}m"
            out[f"discovery_success_{minutes}m"]=rule[f"success_rate_{minutes}m"]
            out[f"validation_success_{minutes}m"]=(g[col] <= 0).mean() if len(g) else np.nan
            out[f"validation_avg_forward_{minutes}m"]=g[col].mean() if len(g) else np.nan
        out["validation_score"]=(
            0.20*out["validation_success_15m"] +
            0.25*out["validation_success_30m"] +
            0.40*out["validation_success_60m"] +
            0.15*out["validation_success_120m"]
        ) if len(g) else np.nan
        out["score_change"]=out["validation_score"]-out["discovery_score"] if len(g) else np.nan
        validation_rows.append(out)

    return ranked, pd.DataFrame(validation_rows)


def research_structure_48_filter(d, train_fraction=0.70):
    """Research-only 48-M15 support/resistance/location filter.

    Tests whether a bearish candidate has enough room to prior 48-candle
    support and/or is located near prior 48-candle resistance. Uses only
    levels shifted by one candle, so the current candle is not used to build
    its own support/resistance level. Live V9.4 is unchanged.
    """
    x = d.copy().sort_index()
    n = len(x)
    split_i = int(n * train_fraction)
    purge = 8
    if split_i <= purge or split_i >= n:
        return pd.DataFrame(), pd.DataFrame()

    discovery = x.iloc[:split_i - purge].copy()
    validation = x.iloc[split_i:].copy()

    # Fixed research grid in ATR units. Selection/ranking happens on discovery.
    resistance_max = [0.5, 1.0, 1.5, 2.0]
    support_min = [0.5, 1.0, 1.5, 2.0, 3.0]

    def base_frame(frame):
        b = frame[frame["bearish_candidate"]].copy()
        return b[
            b["distance_to_resistance_atr"].notna()
            & b["distance_to_support_atr"].notna()
        ].copy()

    disc = base_frame(discovery)
    val = base_frame(validation)
    rows = []

    # Baseline plus individual and combined location rules.
    specs = [("BASE", None, None)]
    specs += [("NEAR_RESISTANCE", r, None) for r in resistance_max]
    specs += [("ROOM_TO_SUPPORT", None, s) for s in support_min]
    specs += [
        ("RESISTANCE_AND_ROOM", r, s)
        for r in resistance_max
        for s in support_min
    ]

    def apply_rule(b, kind, rmax, smin):
        m = pd.Series(True, index=b.index)
        if rmax is not None:
            m &= b["distance_to_resistance_atr"] <= rmax
        if smin is not None:
            m &= b["distance_to_support_atr"] >= smin
        return b[m].copy()

    for kind, rmax, smin in specs:
        g = apply_rule(disc, kind, rmax, smin)
        if len(g) < 50 and kind != "BASE":
            continue
        row = {
            "rule": kind,
            "resistance_max_atr": rmax,
            "support_min_atr": smin,
            "discovery_candidates": len(disc),
            "discovery_signals": len(g),
            "discovery_kept_pct": 100.0 * len(g) / len(disc) if len(disc) else np.nan,
            "discovery_avg_resistance_atr": g["distance_to_resistance_atr"].mean() if len(g) else np.nan,
            "discovery_avg_support_atr": g["distance_to_support_atr"].mean() if len(g) else np.nan,
        }
        for minutes in (15, 30, 60, 120):
            col = f"forward_{minutes}m"
            row[f"discovery_success_{minutes}m"] = (g[col] <= 0).mean() if len(g) else np.nan
            row[f"discovery_avg_forward_{minutes}m"] = g[col].mean() if len(g) else np.nan
        row["discovery_score"] = (
            0.20 * row["discovery_success_15m"]
            + 0.25 * row["discovery_success_30m"]
            + 0.40 * row["discovery_success_60m"]
            + 0.15 * row["discovery_success_120m"]
        ) if len(g) else np.nan
        rows.append(row)

    ranked = pd.DataFrame(rows)
    if ranked.empty:
        return ranked, pd.DataFrame()

    ranked = ranked.sort_values(
        ["discovery_score", "discovery_signals"],
        ascending=[False, False],
    ).reset_index(drop=True)

    validation_rows = []
    # Validate the discovery top 12 without re-ranking on validation.
    for rank, rule in ranked.head(12).iterrows():
        rmax = None if pd.isna(rule["resistance_max_atr"]) else float(rule["resistance_max_atr"])
        smin = None if pd.isna(rule["support_min_atr"]) else float(rule["support_min_atr"])
        g = apply_rule(val, rule["rule"], rmax, smin)
        out = {
            "discovery_rank": rank + 1,
            "rule": rule["rule"],
            "resistance_max_atr": rmax,
            "support_min_atr": smin,
            "discovery_signals": int(rule["discovery_signals"]),
            "discovery_score": rule["discovery_score"],
            "validation_candidates": len(val),
            "validation_signals": len(g),
            "validation_kept_pct": 100.0 * len(g) / len(val) if len(val) else np.nan,
            "validation_avg_resistance_atr": g["distance_to_resistance_atr"].mean() if len(g) else np.nan,
            "validation_avg_support_atr": g["distance_to_support_atr"].mean() if len(g) else np.nan,
        }
        for minutes in (15, 30, 60, 120):
            col = f"forward_{minutes}m"
            out[f"discovery_success_{minutes}m"] = rule[f"discovery_success_{minutes}m"]
            out[f"validation_success_{minutes}m"] = (g[col] <= 0).mean() if len(g) else np.nan
            out[f"validation_avg_forward_{minutes}m"] = g[col].mean() if len(g) else np.nan
        out["validation_score"] = (
            0.20 * out["validation_success_15m"]
            + 0.25 * out["validation_success_30m"]
            + 0.40 * out["validation_success_60m"]
            + 0.15 * out["validation_success_120m"]
        ) if len(g) else np.nan
        out["score_change"] = (
            out["validation_score"] - out["discovery_score"]
            if len(g) else np.nan
        )
        validation_rows.append(out)

    return ranked, pd.DataFrame(validation_rows)



def research_sell_continuation_score(d, train_fraction=0.70):
    """Research a compact SELL-continuation score with strict chronological OOS validation.

    The score combines six distinct ideas already measured by this research script:
    directional efficiency, late bearish persistence, reversal cleanliness, late sell
    acceleration, room to 48-candle support, and resistance/rejection location.
    All features use information available at the M15 close.  Threshold selection is
    performed on discovery only; validation is never used to choose a threshold.
    Research only; live V9.4 remains unchanged.
    """
    x=d.copy().sort_index()
    n=len(x); split_i=int(n*train_fraction); purge=8
    if split_i <= purge or split_i >= n:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    discovery=x.iloc[:split_i-purge].copy(); validation=x.iloc[split_i:].copy()

    def score_frame(frame, enabled=None):
        b=frame[frame["bearish_candidate"]].copy()
        if b.empty: return b
        enabled=set(enabled or ["EFF","PERSIST","CLEAN","ACCEL","ROOM","LOCATION"])
        atr=b["atr14"].replace(0,np.nan)
        # Each component is bounded 0..1 to stop one noisy feature dominating.
        comp={}
        comp["EFF"]=(b["directional_efficiency"]/0.50).clip(0,1)
        late_strength=(-(b["seg2_net"]+b["seg3_net"]))/atr
        comp["PERSIST"]=(late_strength/0.75).clip(0,1) * ((b["seg2_net"]<0)&(b["seg3_net"]<0)).astype(float)
        comp["CLEAN"]=(1.0-b["reversal_count"].clip(0,12)/12.0).clip(0,1)
        comp["ACCEL"]=(b["sell_acceleration_to_close"]/atr/0.50).clip(0,1)
        comp["ROOM"]=(b["distance_to_support_atr"]/3.0).clip(0,1).fillna(0)
        near=(1.0-b["distance_to_resistance_atr"]/2.0).clip(0,1).fillna(0)
        reject=b["high_break_rejection"].astype(float)
        comp["LOCATION"]=np.maximum(near, reject)
        weights={"EFF":20,"PERSIST":25,"CLEAN":15,"ACCEL":15,"ROOM":15,"LOCATION":10}
        denom=sum(weights[k] for k in enabled)
        b["continuation_score"]=sum(weights[k]*comp[k] for k in enabled)/denom*100.0
        for k in comp: b[f"score_{k.lower()}"]=comp[k]*100.0
        return b

    disc=score_frame(discovery); val=score_frame(validation)
    thresholds=[40,45,50,55,60,65,70,75]
    rows=[]
    for th in thresholds:
        g=disc[disc["continuation_score"]>=th].copy()
        if len(g)<50: continue
        row={"score_threshold":th,"discovery_candidates":len(disc),"discovery_signals":len(g),
             "discovery_kept_pct":100*len(g)/len(disc),"discovery_avg_score":g["continuation_score"].mean(),
             "discovery_avg_mfe_60m":g["sell_mfe_60m"].mean(),"discovery_avg_mae_60m":g["sell_mae_60m"].mean()}
        for m in (15,30,60,120):
            col=f"forward_{m}m"; row[f"discovery_success_{m}m"]=(g[col]<=0).mean(); row[f"discovery_avg_forward_{m}m"]=g[col].mean()
        row["discovery_score"]=(.20*row["discovery_success_15m"]+.25*row["discovery_success_30m"]+.40*row["discovery_success_60m"]+.15*row["discovery_success_120m"])
        rows.append(row)
    search=pd.DataFrame(rows)
    if search.empty: return search,pd.DataFrame(),pd.DataFrame()
    # Rank on discovery only, with a mild sample-size preference as tie-breaker.
    search=search.sort_values(["discovery_score","discovery_signals"],ascending=[False,False]).reset_index(drop=True)
    out=[]
    for rank,rule in search.iterrows():
        th=float(rule["score_threshold"]); g=val[val["continuation_score"]>=th].copy()
        r={"discovery_rank":rank+1,"score_threshold":th,"discovery_signals":int(rule["discovery_signals"]),
           "discovery_score":rule["discovery_score"],"validation_candidates":len(val),"validation_signals":len(g),
           "validation_kept_pct":100*len(g)/len(val) if len(val) else np.nan,
           "validation_avg_score":g["continuation_score"].mean() if len(g) else np.nan,
           "validation_avg_mfe_60m":g["sell_mfe_60m"].mean() if len(g) else np.nan,
           "validation_avg_mae_60m":g["sell_mae_60m"].mean() if len(g) else np.nan}
        for m in (15,30,60,120):
            col=f"forward_{m}m"; r[f"validation_success_{m}m"]=(g[col]<=0).mean() if len(g) else np.nan; r[f"validation_avg_forward_{m}m"]=g[col].mean() if len(g) else np.nan
        r["validation_score"]=(.20*r["validation_success_15m"]+.25*r["validation_success_30m"]+.40*r["validation_success_60m"]+.15*r["validation_success_120m"]) if len(g) else np.nan
        r["score_change"]=r["validation_score"]-r["discovery_score"] if len(g) else np.nan
        out.append(r)
    validation_table=pd.DataFrame(out)

    # Component ablation at the best discovery threshold. A component is useful only
    # if removing it hurts unseen validation, not merely discovery performance.
    best_th=float(search.iloc[0]["score_threshold"])
    all_components=["EFF","PERSIST","CLEAN","ACCEL","ROOM","LOCATION"]
    ab=[]
    for removed in ["NONE"]+all_components:
        enabled=all_components if removed=="NONE" else [k for k in all_components if k!=removed]
        for sample,frame in (("DISCOVERY",discovery),("VALIDATION",validation)):
            b=score_frame(frame,enabled); g=b[b["continuation_score"]>=best_th]
            rr={"sample":sample,"removed_component":removed,"threshold":best_th,"candidates":len(b),"signals":len(g),"kept_pct":100*len(g)/len(b) if len(b) else np.nan}
            for m in (15,30,60,120):
                col=f"forward_{m}m"; rr[f"success_{m}m"]=(g[col]<=0).mean() if len(g) else np.nan; rr[f"avg_forward_{m}m"]=g[col].mean() if len(g) else np.nan
            rr["continuation_metric"]=(.20*rr["success_15m"]+.25*rr["success_30m"]+.40*rr["success_60m"]+.15*rr["success_120m"]) if len(g) else np.nan
            ab.append(rr)
    return search,validation_table,pd.DataFrame(ab)



def research_sell_exhaustion_veto(d, train_fraction=0.70):
    """Test whether simple exhaustion/reversal vetoes improve high-score SELLs OOS.

    This deliberately uses a small, fixed family of interpretable vetoes rather than
    another large grid search. The goal is to identify false high-score SELLs caused
    by nearby support, lower-wick rejection, extreme candle expansion, or excessive
    intrabar reversals. Research only; live V9.4 remains unchanged.
    """
    x=d.copy().sort_index(); n=len(x); split_i=int(n*train_fraction); purge=8
    if split_i <= purge or split_i >= n: return pd.DataFrame(), pd.DataFrame()
    discovery=x.iloc[:split_i-purge].copy(); validation=x.iloc[split_i:].copy()

    def scored(frame):
        b=frame[frame["bearish_candidate"]].copy()
        if b.empty: return b
        atr=b["atr14"].replace(0,np.nan)
        eff=(b["directional_efficiency"]/0.50).clip(0,1)
        late_strength=(-(b["seg2_net"]+b["seg3_net"]))/atr
        persist=(late_strength/0.75).clip(0,1)*((b["seg2_net"]<0)&(b["seg3_net"]<0)).astype(float)
        clean=(1.0-b["reversal_count"].clip(0,12)/12.0).clip(0,1)
        accel=(b["sell_acceleration_to_close"]/atr/0.50).clip(0,1)
        room=(b["distance_to_support_atr"]/3.0).clip(0,1).fillna(0)
        near=(1.0-b["distance_to_resistance_atr"]/2.0).clip(0,1).fillna(0)
        location=np.maximum(near,b["high_break_rejection"].astype(float))
        b["continuation_score"]=(20*eff+25*persist+15*clean+15*accel+15*room+10*location)
        b["lower_wick_ratio"]=(b["lower_wick"]/b["range"].replace(0,np.nan)).fillna(0)
        b["veto_close_support"]=b["distance_to_support_atr"].fillna(np.inf)<1.0
        b["veto_lower_wick"]=b["lower_wick_ratio"]>=0.35
        b["veto_extreme_range"]=b["range_atr_ratio"]>=1.50
        b["veto_reversal_heavy"]=b["reversal_count"]>=8
        b["exhaustion_count"]=(b[["veto_close_support","veto_lower_wick","veto_extreme_range","veto_reversal_heavy"]].sum(axis=1))
        return b

    disc=scored(discovery); val=scored(validation)
    vetoes={
        "NONE": lambda b: pd.Series(False,index=b.index),
        "CLOSE_SUPPORT": lambda b: b["veto_close_support"],
        "LOWER_WICK_REJECTION": lambda b: b["veto_lower_wick"],
        "EXTREME_RANGE": lambda b: b["veto_extreme_range"],
        "REVERSAL_HEAVY": lambda b: b["veto_reversal_heavy"],
        "ANY_EXHAUSTION": lambda b: b["exhaustion_count"]>=1,
        "TWO_PLUS_EXHAUSTION": lambda b: b["exhaustion_count"]>=2,
    }
    rows=[]
    for threshold in (65,70,75):
        for name,fn in vetoes.items():
            for sample,b in (("DISCOVERY",disc),("VALIDATION",val)):
                base=b[b["continuation_score"]>=threshold].copy()
                g=base[~fn(base)].copy()
                r={"sample":sample,"score_threshold":threshold,"veto":name,"high_score_candidates":len(base),"signals_after_veto":len(g),"kept_pct":100*len(g)/len(base) if len(base) else np.nan,"avg_exhaustion_count":g["exhaustion_count"].mean() if len(g) else np.nan,"avg_mfe_60m":g["sell_mfe_60m"].mean() if len(g) else np.nan,"avg_mae_60m":g["sell_mae_60m"].mean() if len(g) else np.nan}
                for m in (15,30,60,120):
                    col=f"forward_{m}m"; r[f"success_{m}m"]=(g[col]<=0).mean() if len(g) else np.nan; r[f"avg_forward_{m}m"]=g[col].mean() if len(g) else np.nan
                r["continuation_metric"]=(.20*r["success_15m"]+.25*r["success_30m"]+.40*r["success_60m"]+.15*r["success_120m"]) if len(g) else np.nan
                rows.append(r)
    table=pd.DataFrame(rows)

    # Failure profile: compare successful vs false 60m outcomes at the promising
    # high-score thresholds so we can see which exhaustion features distinguish them.
    prof=[]
    for sample,b in (("DISCOVERY",disc),("VALIDATION",val)):
        for threshold in (65,70,75):
            q=b[b["continuation_score"]>=threshold].copy()
            for outcome,mask in (("SUCCESS_60M",q["forward_60m"]<=0),("FALSE_60M",q["forward_60m"]>0)):
                g=q[mask]
                prof.append({"sample":sample,"score_threshold":threshold,"outcome":outcome,"signals":len(g),"avg_score":g["continuation_score"].mean() if len(g) else np.nan,"close_support_rate":g["veto_close_support"].mean() if len(g) else np.nan,"lower_wick_rejection_rate":g["veto_lower_wick"].mean() if len(g) else np.nan,"extreme_range_rate":g["veto_extreme_range"].mean() if len(g) else np.nan,"reversal_heavy_rate":g["veto_reversal_heavy"].mean() if len(g) else np.nan,"avg_exhaustion_count":g["exhaustion_count"].mean() if len(g) else np.nan,"avg_distance_support_atr":g["distance_to_support_atr"].mean() if len(g) else np.nan,"avg_distance_resistance_atr":g["distance_to_resistance_atr"].mean() if len(g) else np.nan,"avg_range_atr_ratio":g["range_atr_ratio"].mean() if len(g) else np.nan,"avg_reversals":g["reversal_count"].mean() if len(g) else np.nan,"avg_lower_wick_ratio":g["lower_wick_ratio"].mean() if len(g) else np.nan})
    return table,pd.DataFrame(prof)


def research_continuation_time_stability(d, blocks=6):
    """Test fixed high continuation-score thresholds across chronological blocks.

    Each block is evaluated independently. The final 8 M15 candles of every block
    except the last are purged so 120-minute forward outcomes cannot cross into the
    next block. Thresholds are fixed in advance (60/65/70/75); no threshold is
    selected or re-fit on these blocks. Research only; live V9.4 remains unchanged.
    """
    x=d.copy().sort_index()
    if len(x) < blocks*100:
        return pd.DataFrame(), pd.DataFrame()

    def scored(frame):
        b=frame[frame["bearish_candidate"]].copy()
        if b.empty: return b
        atr=b["atr14"].replace(0,np.nan)
        eff=(b["directional_efficiency"]/0.50).clip(0,1)
        late_strength=(-(b["seg2_net"]+b["seg3_net"]))/atr
        persist=(late_strength/0.75).clip(0,1)*((b["seg2_net"]<0)&(b["seg3_net"]<0)).astype(float)
        clean=(1.0-b["reversal_count"].clip(0,12)/12.0).clip(0,1)
        accel=(b["sell_acceleration_to_close"]/atr/0.50).clip(0,1)
        room=(b["distance_to_support_atr"]/3.0).clip(0,1).fillna(0)
        near=(1.0-b["distance_to_resistance_atr"]/2.0).clip(0,1).fillna(0)
        location=np.maximum(near,b["high_break_rejection"].astype(float))
        b["continuation_score"]=(20*eff+25*persist+15*clean+15*accel+15*room+10*location)
        return b

    thresholds=(60,65,70,75)
    edges=np.linspace(0,len(x),blocks+1,dtype=int)
    rows=[]
    for bi in range(blocks):
        raw=x.iloc[edges[bi]:edges[bi+1]].copy()
        eval_frame=raw.iloc[:-8].copy() if bi < blocks-1 and len(raw)>8 else raw
        b=scored(eval_frame)
        for th in thresholds:
            g=b[b["continuation_score"]>=th].copy()
            r={
                "block":bi+1,"threshold":th,
                "start":eval_frame.index.min(),"end":eval_frame.index.max(),
                "complete_m15":len(eval_frame),"bearish_candidates":len(b),
                "signals":len(g),"kept_pct":100*len(g)/len(b) if len(b) else np.nan,
                "avg_score":g["continuation_score"].mean() if len(g) else np.nan,
                "avg_mfe_60m":g["sell_mfe_60m"].mean() if len(g) else np.nan,
                "avg_mae_60m":g["sell_mae_60m"].mean() if len(g) else np.nan,
            }
            for m in (15,30,60,120):
                col=f"forward_{m}m"
                r[f"success_{m}m"]=(g[col]<=0).mean() if len(g) else np.nan
                r[f"avg_forward_{m}m"]=g[col].mean() if len(g) else np.nan
            r["continuation_metric"]=(.20*r["success_15m"]+.25*r["success_30m"]+.40*r["success_60m"]+.15*r["success_120m"]) if len(g) else np.nan
            rows.append(r)
    detail=pd.DataFrame(rows)

    summary=[]
    for th in thresholds:
        q=detail[detail["threshold"]==th].copy()
        valid=q[q["signals"]>=20].copy()
        total=int(q["signals"].sum())
        rr={
            "threshold":th,"blocks":len(q),"blocks_with_20plus_signals":len(valid),
            "total_signals":total,"min_block_signals":int(q["signals"].min()) if len(q) else 0,
            "median_block_signals":q["signals"].median() if len(q) else np.nan,
            "mean_block_metric":valid["continuation_metric"].mean() if len(valid) else np.nan,
            "min_block_metric":valid["continuation_metric"].min() if len(valid) else np.nan,
            "max_block_metric":valid["continuation_metric"].max() if len(valid) else np.nan,
            "metric_std":valid["continuation_metric"].std(ddof=0) if len(valid) else np.nan,
            "blocks_metric_above_50pct":int((valid["continuation_metric"]>0.50).sum()) if len(valid) else 0,
            "blocks_60m_above_50pct":int((valid["success_60m"]>0.50).sum()) if len(valid) else 0,
            "mean_success_30m":valid["success_30m"].mean() if len(valid) else np.nan,
            "mean_success_60m":valid["success_60m"].mean() if len(valid) else np.nan,
            "mean_success_120m":valid["success_120m"].mean() if len(valid) else np.nan,
            "mean_forward_60m":valid["avg_forward_60m"].mean() if len(valid) else np.nan,
            "mean_forward_120m":valid["avg_forward_120m"].mean() if len(valid) else np.nan,
        }
        # Conservative robustness aid: reward average continuation, penalize instability.
        rr["robustness_score"]=(rr["mean_block_metric"]-0.50*rr["metric_std"]) if len(valid) else np.nan
        summary.append(rr)
    return detail,pd.DataFrame(summary).sort_values(["robustness_score","total_signals"],ascending=[False,False])


def research_h4_context(d, train_fraction=0.70):
    """Research-only H4 context; uses only fully completed H4 candles."""
    x=d.copy().sort_index()

    # Build H4 bars from completed M15 candles. Require all 16 constituent M15 bars.
    h4=x[["open","high","low","close"]].resample("4h",label="left",closed="left").agg(
        {"open":"first","high":"max","low":"min","close":"last"}).dropna()
    counts=x["close"].resample("4h",label="left",closed="left").count()
    h4=h4[counts.reindex(h4.index).eq(16)].copy()
    h4["h4_end"]=h4.index+pd.Timedelta(hours=4)

    # Slow enough to represent higher-timeframe direction, while remaining causal.
    h4["ema_fast"]=h4["close"].ewm(span=6,adjust=False).mean()
    h4["ema_slow"]=h4["close"].ewm(span=12,adjust=False).mean()
    bearish=(h4["close"]<h4["open"])&(h4["close"]<h4["ema_fast"])&(h4["ema_fast"]<=h4["ema_slow"])
    bullish=(h4["close"]>h4["open"])&(h4["close"]>h4["ema_fast"])&(h4["ema_fast"]>=h4["ema_slow"])
    h4["h4_context"]=np.where(bearish,"BEARISH",np.where(bullish,"BULLISH","NEUTRAL"))

    left=x.reset_index()
    left=left.rename(columns={left.columns[0]:"signal_time"}).sort_values("signal_time")
    right=h4.reset_index()
    right=right.rename(columns={right.columns[0]:"h4_start"}).sort_values("h4_end")

    # Only H4 bars whose end time is <= the M15 signal time are visible.
    merged=pd.merge_asof(
        left,right[["h4_start","h4_end","h4_context"]],
        left_on="signal_time",right_on="h4_end",direction="backward"
    ).set_index("signal_time")

    valid=merged["h4_end"].notna()
    if valid.any() and not (merged.loc[valid,"h4_end"]<=merged.loc[valid].index).all():
        raise AssertionError("H4 lookahead detected")

    n=len(merged); split_i=int(n*train_fraction); purge=8
    discovery=merged.iloc[:max(0,split_i-purge)].copy()
    validation=merged.iloc[split_i:].copy()

    rows=[]
    for sample,frame in (("DISCOVERY",discovery),("VALIDATION",validation),("ALL",merged)):
        base=frame[frame["bearish_candidate"]].copy()
        for ctx in ("ALL","BEARISH","NEUTRAL","BULLISH"):
            g=base if ctx=="ALL" else base[base["h4_context"]==ctx]
            row={"sample":sample,"h4_context":ctx,"bearish_candidates":len(base),
                 "signals":len(g),"kept_pct":100*len(g)/len(base) if len(base) else np.nan}
            for m in (15,30,60,120):
                col=f"forward_{m}m"
                row[f"success_{m}m"]=(g[col]<=0).mean() if len(g) else np.nan
                row[f"avg_forward_{m}m"]=g[col].mean() if len(g) else np.nan
            rows.append(row)

    detail=merged[["open","high","low","close","bearish_candidate","h4_start","h4_end","h4_context",
                   "forward_15m","forward_30m","forward_60m","forward_120m"]].copy()
    return pd.DataFrame(rows),detail


def research_combined_context_v94(d, train_fraction=0.70):
    """Research-only combined M15 + S/R + H1/H4 context validation.

    This deliberately avoids a threshold grid search. It compares fixed,
    interpretable combinations on the same chronological discovery/validation
    split. H1/H4 mappings use completed higher-timeframe candles only.
    """
    # Reuse the already-tested causal H1/H4 mappings.
    _, h1d = research_h1_context(d, train_fraction)
    _, h4d = research_h4_context(d, train_fraction)

    x = d.copy().sort_index()
    h1map = h1d[["h1_context"]].copy()
    h4map = h4d[["h4_context"]].copy()
    x = x.join(h1map, how="left").join(h4map, how="left")

    # Existing 48-M15 support/resistance is shifted one candle in enrich(),
    # so these location features are known at signal time.
    x["room_to_support_atr"] = (x["close"] - x["support_48"]) / x["atr14"]
    x["distance_from_resistance_atr"] = (x["resistance_48"] - x["close"]) / x["atr14"]

    # Previously identified fixed research location condition:
    # within 2 ATR of resistance AND at least 3 ATR room to support.
    x["sr_good_sell"] = (
        (x["distance_from_resistance_atr"] >= 0)
        & (x["distance_from_resistance_atr"] <= 2.0)
        & (x["room_to_support_atr"] >= 3.0)
    )

    n=len(x); split_i=int(n*train_fraction); purge=8
    discovery=x.iloc[:max(0,split_i-purge)].copy()
    validation=x.iloc[split_i:].copy()

    def summarize(sample, frame):
        b=frame[frame["bearish_candidate"]].copy()
        masks = {
            "M15_BASELINE": pd.Series(True,index=b.index),
            "M15_PLUS_SR_GOOD": b["sr_good_sell"],
            "M15_PLUS_H4_BEARISH": b["h4_context"].eq("BEARISH"),
            "M15_PLUS_H4_BEARISH_PLUS_SR_GOOD":
                b["h4_context"].eq("BEARISH") & b["sr_good_sell"],
            "M15_PLUS_H1_BEARISH_PLUS_H4_BEARISH":
                b["h1_context"].eq("BEARISH") & b["h4_context"].eq("BEARISH"),
            "M15_PLUS_H1_BEARISH_PLUS_H4_BEARISH_PLUS_SR_GOOD":
                b["h1_context"].eq("BEARISH") & b["h4_context"].eq("BEARISH") & b["sr_good_sell"],
        }
        rows=[]
        for name,mask in masks.items():
            g=b[mask.fillna(False)]
            row={"sample":sample,"combination":name,"baseline_candidates":len(b),
                 "signals":len(g),"kept_pct":100*len(g)/len(b) if len(b) else np.nan}
            for m in (15,30,60,120):
                col=f"forward_{m}m"
                row[f"success_{m}m"]=(g[col]<=0).mean() if len(g) else np.nan
                row[f"avg_forward_{m}m"]=g[col].mean() if len(g) else np.nan
            rows.append(row)
        return rows

    summary=pd.DataFrame(
        summarize("DISCOVERY",discovery)
        + summarize("VALIDATION",validation)
        + summarize("ALL",x)
    )

    detail_cols=[
        "open","high","low","close","atr14","bearish_candidate",
        "resistance_48","support_48","distance_from_resistance_atr",
        "room_to_support_atr","sr_good_sell","h1_context","h4_context",
        "forward_15m","forward_30m","forward_60m","forward_120m"
    ]
    detail=x[[c for c in detail_cols if c in x.columns]].copy()
    detail["sample"]="PURGED"
    detail.iloc[:max(0,split_i-purge),detail.columns.get_loc("sample")]="DISCOVERY"
    if split_i < len(detail):
        detail.iloc[split_i:,detail.columns.get_loc("sample")]="VALIDATION"
    return summary,detail

def main():
    api = os.getenv("TWELVE_DATA_API_KEY", "").strip()
    if not api:
        raise RuntimeError("TWELVE_DATA_API_KEY is missing")

    print("V9.4 CANDLE DYNAMICS RESEARCH")
    m1 = download(api)
    m1.to_csv("candle_dynamics_m1_v94.csv")
    d = enrich(reconstruct(m1))
    d.to_csv(OUT)

    t, p, f = summaries(d)
    t.to_csv("candle_dynamics_time_summary_v94.csv", index=False)
    p.to_csv("candle_dynamics_pattern_summary_v94.csv", index=False)
    f.to_csv("candle_dynamics_followthrough_summary_v94.csv", index=False)
    d[d.false_sell_60m].to_csv("candle_dynamics_false_sell_v94.csv")

    detailed, dynamics_summary, path_summary = detailed_intracandle_analysis(d)
    detailed.to_csv("candle_dynamics_detailed_v94.csv", index=False)
    dynamics_summary.to_csv("candle_dynamics_intracandle_summary_v94.csv", index=False)
    path_summary.to_csv("candle_dynamics_path_summary_v94.csv", index=False)

    sell_combinations = analyze_sell_combinations(detailed)
    sell_combinations.to_csv(
        "candle_dynamics_sell_combinations_v94.csv",
        index=False,
    )

    sell_filter_comparison = compare_sell_filters(detailed)
    sell_filter_comparison.to_csv(
        "candle_dynamics_sell_filter_comparison_v94.csv",
        index=False,
    )

    directional_efficiency_comparison = compare_directional_efficiency_thresholds(detailed)
    directional_efficiency_comparison.to_csv(
        "candle_dynamics_directional_efficiency_v94.csv",
        index=False,
    )

    multi_factor_comparison = multi_factor_sell_search(detailed)
    multi_factor_comparison.to_csv(
        "candle_dynamics_multifactor_search_v94.csv",
        index=False,
    )

    oos_metadata, oos_validation = out_of_sample_multifactor_validation(detailed)
    oos_metadata.to_csv(
        "candle_dynamics_oos_metadata_v94.csv",
        index=False,
    )
    oos_validation.to_csv(
        "candle_dynamics_oos_validation_v94.csv",
        index=False,
    )

    simple_rule_metadata, simple_rule_validation = validate_simple_three_filter_rule(detailed)
    simple_rule_metadata.to_csv(
        "candle_dynamics_three_filter_metadata_v94.csv",
        index=False,
    )
    simple_rule_validation.to_csv(
        "candle_dynamics_three_filter_validation_v94.csv",
        index=False,
    )

    component_comparison = compare_three_filter_components(detailed)
    component_comparison.to_csv(
        "candle_dynamics_three_filter_components_v94.csv",
        index=False,
    )

    persistence_search, persistence_validation = optimize_persistence_filter(detailed)
    persistence_search.to_csv(
        "candle_dynamics_persistence_search_v94.csv",
        index=False,
    )
    persistence_validation.to_csv(
        "candle_dynamics_persistence_validation_v94.csv",
        index=False,
    )

    structure48_search, structure48_validation = research_structure_48_filter(detailed)
    structure48_search.to_csv(
        "candle_dynamics_structure48_search_v94.csv",
        index=False,
    )
    structure48_validation.to_csv(
        "candle_dynamics_structure48_validation_v94.csv",
        index=False,
    )

    continuation_search, continuation_validation, continuation_ablation = research_sell_continuation_score(detailed)
    continuation_search.to_csv("candle_dynamics_continuation_score_search_v94.csv", index=False)
    continuation_validation.to_csv("candle_dynamics_continuation_score_validation_v94.csv", index=False)
    continuation_ablation.to_csv("candle_dynamics_continuation_score_ablation_v94.csv", index=False)

    exhaustion_veto, exhaustion_profile = research_sell_exhaustion_veto(detailed)
    exhaustion_veto.to_csv("candle_dynamics_exhaustion_veto_v94.csv", index=False)
    exhaustion_profile.to_csv("candle_dynamics_exhaustion_profile_v94.csv", index=False)

    h4_summary, h4_detail = research_h4_context(detailed)
    h4_summary.to_csv("candle_dynamics_h4_context_summary_v94.csv", index=False)
    h4_detail.to_csv("candle_dynamics_h4_context_detail_v94.csv")

    combined_summary, combined_detail = research_combined_context_v94(detailed)
    combined_summary.to_csv("candle_dynamics_combined_context_summary_v94.csv", index=False)
    combined_detail.to_csv("candle_dynamics_combined_context_detail_v94.csv")

    stability_detail, stability_summary = research_continuation_time_stability(detailed)
    stability_detail.to_csv("candle_dynamics_continuation_stability_blocks_v94.csv", index=False)
    stability_summary.to_csv("candle_dynamics_continuation_stability_summary_v94.csv", index=False)

    print("\nH4 CONTEXT — COMPLETED H4 CANDLES ONLY")
    print(h4_summary.to_string(index=False))

    print("\nCOMBINED M15 + S/R + H1/H4 VALIDATION")
    print(combined_summary.to_string(index=False))

    print("\nSELL FILTER COMPARISON")
    print(sell_filter_comparison.to_string(index=False))
    print("\nDIRECTIONAL EFFICIENCY THRESHOLD COMPARISON")
    print(directional_efficiency_comparison.to_string(index=False))
    print("\nMULTI-FACTOR SELL SEARCH — TOP 30")
    print(multi_factor_comparison.head(30).to_string(index=False))
    print("\nOUT-OF-SAMPLE SPLIT")
    print(oos_metadata.to_string(index=False))
    print("\nOUT-OF-SAMPLE VALIDATION — DISCOVERY TOP 20")
    print(oos_validation.to_string(index=False))
    print("\nSIMPLE 3-FILTER RULE — OUT-OF-SAMPLE VALIDATION")
    print(simple_rule_metadata.to_string(index=False))
    print(simple_rule_validation.to_string(index=False))
    print("\nTHREE-FILTER COMPONENT ABLATION — DISCOVERY VS VALIDATION")
    print(component_comparison.to_string(index=False))
    print("\nPERSISTENCE FILTER SEARCH — DISCOVERY")
    print(persistence_search.to_string(index=False))
    print("\nPERSISTENCE FILTER — OUT-OF-SAMPLE VALIDATION TOP 12")
    print(persistence_validation.to_string(index=False))
    print("\n48-CANDLE SUPPORT/RESISTANCE — DISCOVERY")
    print(structure48_search.head(30).to_string(index=False))
    print("\n48-CANDLE SUPPORT/RESISTANCE — OUT-OF-SAMPLE VALIDATION TOP 12")
    print(structure48_validation.to_string(index=False))
    print("\nSELL CONTINUATION SCORE — DISCOVERY")
    print(continuation_search.to_string(index=False))
    print("\nSELL CONTINUATION SCORE — OUT-OF-SAMPLE VALIDATION")
    print(continuation_validation.to_string(index=False))
    print("\nSELL CONTINUATION SCORE — COMPONENT ABLATION")
    print(continuation_ablation.to_string(index=False))
    print("\nHIGH-SCORE SELL EXHAUSTION VETO — DISCOVERY VS VALIDATION")
    print(exhaustion_veto.to_string(index=False))
    print("\nHIGH-SCORE SELL FAILURE PROFILE — SUCCESS VS FALSE SELL")
    print(exhaustion_profile.to_string(index=False))
    print("\nSELL CONTINUATION SCORE — CHRONOLOGICAL STABILITY BLOCKS")
    print(stability_detail.to_string(index=False))
    print("\nSELL CONTINUATION SCORE — STABILITY SUMMARY")
    print(stability_summary.to_string(index=False))
    print("\nSELL COMBINATION RESEARCH")
    print(sell_combinations.head(30).to_string(index=False))
    print("\nDETAILED INTRACANDLE SUMMARY")
    print(dynamics_summary.to_string(index=False))
    print("\nINTRACANDLE PATH SUMMARY")
    print(path_summary.to_string(index=False))
    print(f"Complete M15 candles reconstructed: {len(d)}")
    print("\nTIME SUMMARY")
    print(t.to_string(index=False))
    print("\nPATTERN SUMMARY")
    print(p.to_string(index=False))
    print("\nFOLLOW-THROUGH + MAE/MFE")
    print(f.to_string(index=False))


if __name__ == "__main__":
    main()
