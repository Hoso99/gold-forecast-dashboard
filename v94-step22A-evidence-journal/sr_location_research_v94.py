"""V9.4 historical 48-M15 support/resistance + location research.

Research-only companion module. It does not modify the live V9.4 signal engine.

Designed to be imported by candle_dynamics_v94.py (preferred), or run against
a CSV containing M15 OHLC columns: datetime/open/high/low/close (case-insensitive).

All features are causal: levels at candle i use only candles completed before i.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import numpy as np
import pandas as pd

LOOKBACK = 48
SWING = 2
ATR_PERIOD = 14
NEAR_ATR = 0.50
BREAK_ATR = 0.15
ROOM_ATR = (0.75, 1.0, 1.5, 2.0)


def _cols(df):
    m = {str(c).lower(): c for c in df.columns}
    need = ["open", "high", "low", "close"]
    missing = [x for x in need if x not in m]
    if missing:
        raise ValueError(f"Missing OHLC columns: {missing}")
    return m


def _atr(df, period=ATR_PERIOD):
    m = _cols(df)
    h = pd.to_numeric(df[m["high"]], errors="coerce")
    l = pd.to_numeric(df[m["low"]], errors="coerce")
    c = pd.to_numeric(df[m["close"]], errors="coerce")
    pc = c.shift(1)
    tr = pd.concat([(h-l).abs(), (h-pc).abs(), (l-pc).abs()], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=period).mean()


def _swings(hist, k=SWING):
    m = _cols(hist)
    h = pd.to_numeric(hist[m["high"]], errors="coerce").to_numpy(float)
    l = pd.to_numeric(hist[m["low"]], errors="coerce").to_numpy(float)
    highs, lows = [], []
    for j in range(k, len(hist)-k):
        if np.isfinite(h[j]) and h[j] >= np.nanmax(h[j-k:j+k+1]):
            highs.append(h[j])
        if np.isfinite(l[j]) and l[j] <= np.nanmin(l[j-k:j+k+1]):
            lows.append(l[j])
    return highs, lows


def add_sr_location_features(m15: pd.DataFrame, lookback=LOOKBACK) -> pd.DataFrame:
    """Return a copy with causal 48-candle S/R/location research features."""
    out = m15.copy()
    m = _cols(out)
    close = pd.to_numeric(out[m["close"]], errors="coerce")
    high = pd.to_numeric(out[m["high"]], errors="coerce")
    low = pd.to_numeric(out[m["low"]], errors="coerce")
    atr = _atr(out)

    rows = []
    for i in range(len(out)):
        rec = {
            "sr_resistance": np.nan, "sr_support": np.nan,
            "sr_dist_res_atr": np.nan, "sr_dist_sup_atr": np.nan,
            "sr_near_resistance": False, "sr_near_support": False,
            "sr_support_break": False, "sr_resistance_rejection": False,
            "sr_room_below_atr": np.nan, "sr_location_score": 0.0,
            "sr_location_class": "INSUFFICIENT_HISTORY",
        }
        if i < max(lookback, ATR_PERIOD + 1) or not np.isfinite(atr.iloc[i]):
            rows.append(rec); continue

        # IMPORTANT: history ends at i-1 -> no look-ahead.
        hist = out.iloc[i-lookback:i]
        sh, sl = _swings(hist)
        px = float(close.iloc[i])
        a = float(atr.iloc[i])
        if not np.isfinite(px) or not np.isfinite(a) or a <= 0:
            rows.append(rec); continue

        resistance_candidates = [x for x in sh if x >= px]
        support_candidates = [x for x in sl if x <= px]
        resistance = min(resistance_candidates) if resistance_candidates else (max(sh) if sh else float(hist[m["high"]].max()))
        support = max(support_candidates) if support_candidates else (min(sl) if sl else float(hist[m["low"]].min()))

        dres = (resistance - px) / a
        dsup = (px - support) / a

        prev_close = float(close.iloc[i-1])
        near_res = abs(resistance - px) <= NEAR_ATR * a
        near_sup = abs(px - support) <= NEAR_ATR * a
        support_break = (prev_close >= support) and (px < support - BREAK_ATR*a)
        rejection = (float(high.iloc[i]) >= resistance - NEAR_ATR*a and
                     px < resistance and float(high.iloc[i]) > px)

        # Positive = friendlier location for a SELL; negative = dangerous.
        score = 0.0
        if rejection: score += 2.0
        elif near_res: score += 1.0
        if support_break: score += 2.0
        if near_sup and not support_break: score -= 2.0
        if dsup >= 2.0: score += 1.0
        elif dsup < 1.0 and not support_break: score -= 1.0

        if score >= 2:
            cls = "FAVORABLE_SELL_LOCATION"
        elif score <= -1:
            cls = "POOR_SELL_LOCATION"
        else:
            cls = "NEUTRAL_LOCATION"

        rec.update({
            "sr_resistance": resistance, "sr_support": support,
            "sr_dist_res_atr": dres, "sr_dist_sup_atr": dsup,
            "sr_near_resistance": near_res, "sr_near_support": near_sup,
            "sr_support_break": support_break,
            "sr_resistance_rejection": rejection,
            "sr_room_below_atr": dsup,
            "sr_location_score": score, "sr_location_class": cls,
        })
        rows.append(rec)

    feat = pd.DataFrame(rows, index=out.index)
    return pd.concat([out, feat], axis=1)


def summarize_sr_location(df, bearish_col=None):
    """Print research tables. If bearish_col is supplied, restrict to candidates."""
    x = df.copy()
    if bearish_col and bearish_col in x.columns:
        x = x[x[bearish_col].astype(bool)]
    print("\n48-M15 SUPPORT / RESISTANCE LOCATION SUMMARY")
    if x.empty:
        print("No qualifying rows.")
        return

    future_cols = [c for c in ["forward_15m","forward_30m","forward_60m","forward_120m"] if c in x.columns]
    agg = {"sr_location_score":"mean", "sr_room_below_atr":"mean"}
    for c in future_cols:
        agg[c] = "mean"
    print(x.groupby("sr_location_class").agg(agg).to_string())

    print("\nSELL LOCATION COMPONENT ABLATION")
    tests = {
        "BASE": pd.Series(True, index=x.index),
        "NEAR_RESISTANCE": x["sr_near_resistance"],
        "RESISTANCE_REJECTION": x["sr_resistance_rejection"],
        "SUPPORT_BREAK": x["sr_support_break"],
        "NOT_NEAR_SUPPORT": ~x["sr_near_support"],
        "FAVORABLE_LOCATION": x["sr_location_class"].eq("FAVORABLE_SELL_LOCATION"),
    }
    records = []
    for name, mask in tests.items():
        z = x[mask.fillna(False)]
        r = {"filter": name, "signals": len(z), "kept_pct": 100*len(z)/max(len(x),1)}
        for c in future_cols:
            r[f"avg_{c}"] = z[c].mean() if len(z) else np.nan
            # For a SELL, negative forward return/change is directional success.
            r[f"success_{c}"] = (z[c] < 0).mean() if len(z) else np.nan
        records.append(r)
    print(pd.DataFrame(records).to_string(index=False))

    print("\nROOM BELOW SUPPORT — ATR THRESHOLD SEARCH")
    records = []
    for t in ROOM_ATR:
        z = x[x["sr_room_below_atr"] >= t]
        r = {"room_atr_min": t, "signals": len(z), "kept_pct": 100*len(z)/max(len(x),1)}
        for c in future_cols:
            r[f"avg_{c}"] = z[c].mean() if len(z) else np.nan
            r[f"success_{c}"] = (z[c] < 0).mean() if len(z) else np.nan
        records.append(r)
    print(pd.DataFrame(records).to_string(index=False))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", help="M15 CSV to analyze")
    ap.add_argument("--out", default="sr_location_research_v94.csv")
    ap.add_argument("--bearish-col", default=None)
    args = ap.parse_args()
    if not args.csv:
        print("Import add_sr_location_features() from candle_dynamics_v94.py research,")
        print("or run: python sr_location_research_v94.py --csv YOUR_M15.csv")
        return
    df = pd.read_csv(args.csv)
    out = add_sr_location_features(df)
    out.to_csv(args.out, index=False)
    summarize_sr_location(out, args.bearish_col)
    print(f"\nSaved: {args.out}")


if __name__ == "__main__":
    main()
