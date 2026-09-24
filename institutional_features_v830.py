"""Causal institutional-style features that are valid with available data.

Nothing in this module claims to reveal hidden OTC orders. Candle-derived
liquidity levels are labelled as proxies; traded-volume features activate only
when an actual volume column is present.
"""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np
import pandas as pd


@dataclass
class InstitutionalAudit:
    accumulation_state: str
    compression_percentile: float
    nearest_liquidity: str
    liquidity_distance_pct: float
    volume_status: str
    poc: float
    value_area_low: float
    value_area_high: float
    reasons: list[str]


def institutional_features(gold: pd.DataFrame) -> pd.DataFrame:
    """Build causal liquidity-map and accumulation features for each candle."""
    close, high, low = gold.close, gold.high, gold.low
    out = pd.DataFrame(index=gold.index)
    previous = close.shift(1)
    true_range = pd.concat([
        high - low, (high - previous).abs(), (low - previous).abs()], axis=1).max(axis=1)
    atr = true_range.rolling(64, min_periods=24).mean()
    prior_high = high.shift(1).rolling(96, min_periods=24).max()
    prior_low = low.shift(1).rolling(96, min_periods=24).min()
    out["liq_distance_prior_high"] = (prior_high - close) / close
    out["liq_distance_prior_low"] = (close - prior_low) / close
    out["liq_range_position"] = (
        (close - prior_low) / (prior_high - prior_low).replace(0, np.nan))
    # Repeated tests of nearby highs/lows are a stop-liquidity proxy, not an
    # observation of hidden orders. Threshold is based on lagged ATR.
    tolerance = atr.shift(1) * .15
    out["equal_high_tests_32"] = pd.Series(
        [np.nan] * len(gold), index=gold.index, dtype=float)
    out["equal_low_tests_32"] = out["equal_high_tests_32"].copy()
    for i in range(32, len(gold)):
        h = high.iloc[i-32:i]
        l = low.iloc[i-32:i]
        tol = tolerance.iloc[i]
        if np.isfinite(tol) and tol > 0:
            out.iloc[i, out.columns.get_loc("equal_high_tests_32")] = float(
                ((h.max() - h).abs() <= tol).sum())
            out.iloc[i, out.columns.get_loc("equal_low_tests_32")] = float(
                ((l - l.min()).abs() <= tol).sum())
    log_range = np.log(high / low.where(low > 0))
    compression = log_range.rolling(16, min_periods=8).mean()
    baseline = compression.rolling(384, min_periods=96)
    out["range_compression_z"] = (
        (compression - baseline.mean()) / baseline.std().replace(0, np.nan))
    out["trend_efficiency_32"] = (
        close.diff(32).abs() / close.diff().abs().rolling(32).sum().replace(0, np.nan))
    out["accumulation_score"] = (
        (-out.range_compression_z).clip(0, 3) / 3 *
        (1 - out.trend_efficiency_32.clip(0, 1)))
    day = pd.Series(gold.index.floor("D"), index=gold.index)
    typical = (high + low + close) / 3
    if "volume" in gold and pd.to_numeric(gold.volume, errors="coerce").notna().sum() > 20:
        volume = pd.to_numeric(gold.volume, errors="coerce").clip(lower=0)
        numerator = (typical * volume).groupby(day).cumsum()
        denominator = volume.groupby(day).cumsum().replace(0, np.nan)
        out["session_vwap_distance"] = (close - numerator / denominator) / close
        out["relative_volume_32"] = volume / volume.rolling(32).median().replace(0, np.nan)
    return out.replace([np.inf, -np.inf], np.nan)


def volume_profile(gold: pd.DataFrame, bars: int = 384,
                   bins: int = 40) -> dict[str, float | str]:
    """Compute a close-at-volume profile only when real volume is available."""
    if "volume" not in gold:
        return {"status": "UNAVAILABLE", "poc": np.nan, "val": np.nan,
                "vah": np.nan, "reason": "source has no traded volume"}
    sample = gold.tail(bars).copy()
    volume = pd.to_numeric(sample.volume, errors="coerce")
    price = pd.to_numeric(sample.close, errors="coerce")
    valid = price.notna() & volume.notna() & (volume > 0)
    if valid.sum() < 40:
        return {"status": "UNAVAILABLE", "poc": np.nan, "val": np.nan,
                "vah": np.nan, "reason": "insufficient positive volume observations"}
    edges = np.linspace(price[valid].min(), price[valid].max(), bins + 1)
    bucket = np.clip(np.digitize(price[valid], edges) - 1, 0, bins - 1)
    profile = pd.Series(volume[valid].to_numpy()).groupby(bucket).sum()
    centers = (edges[:-1] + edges[1:]) / 2
    poc_bucket = int(profile.idxmax())
    ordered = profile.sort_values(ascending=False)
    selected = ordered.cumsum() <= ordered.sum() * .70
    chosen = list(ordered.index[selected])
    if not chosen:
        chosen = [poc_bucket]
    # Include the bucket that crosses 70%.
    if len(chosen) < len(ordered):
        chosen.append(int(ordered.index[len(chosen)]))
    return {"status": "AVAILABLE", "poc": float(centers[poc_bucket]),
            "val": float(centers[min(chosen)]),
            "vah": float(centers[max(chosen)]), "reason": ""}


def latest_institutional_audit(gold: pd.DataFrame) -> InstitutionalAudit:
    features = institutional_features(gold)
    row = features.iloc[-1]
    score = float(row.get("accumulation_score", np.nan))
    state = "ACCUMULATION RANGE" if np.isfinite(score) and score >= .55 else "NO CONFIRMED RANGE"
    distances = {
        "PRIOR HIGH": abs(float(row.get("liq_distance_prior_high", np.nan))),
        "PRIOR LOW": abs(float(row.get("liq_distance_prior_low", np.nan))),
    }
    finite = {k: v for k, v in distances.items() if np.isfinite(v)}
    nearest = min(finite, key=finite.get) if finite else "UNKNOWN"
    distance = finite.get(nearest, np.nan)
    profile = volume_profile(gold)
    reasons = [
        "prior highs/lows and equal tests are a liquidity proxy, not hidden orders",
        "dark-pool and liquidation inputs are disabled unless a licensed, gold-relevant source is supplied",
    ]
    if profile["status"] != "AVAILABLE":
        reasons.append(str(profile["reason"]))
    return InstitutionalAudit(
        state, score, nearest, distance, str(profile["status"]),
        float(profile["poc"]), float(profile["val"]), float(profile["vah"]), reasons)


def catalyst_playbook(gold: pd.DataFrame, events: pd.DataFrame,
                      horizon_bars: int = 4, min_events: int = 20) -> pd.DataFrame:
    """Historical post-event outcomes; never infer direction from future events."""
    columns = ["Event", "Cases", "Up frequency", "Median move",
               "Median absolute move", "Qualified"]
    if events is None or events.empty:
        return pd.DataFrame(columns=columns)
    rows = []
    for event_name, group in events.groupby("event"):
        outcomes = []
        for timestamp in pd.to_datetime(group.timestamp, utc=True, errors="coerce").dropna():
            location = gold.index.searchsorted(timestamp, side="left")
            if location < len(gold) and location + horizon_bars < len(gold):
                outcomes.append(gold.close.iloc[location + horizon_bars] /
                                gold.close.iloc[location] - 1)
        series = pd.Series(outcomes, dtype=float)
        rows.append({"Event": event_name, "Cases": len(series),
                     "Up frequency": float((series > 0).mean()) if len(series) else np.nan,
                     "Median move": float(series.median()) if len(series) else np.nan,
                     "Median absolute move": float(series.abs().median()) if len(series) else np.nan,
                     "Qualified": len(series) >= min_events})
    return pd.DataFrame(rows, columns=columns)
