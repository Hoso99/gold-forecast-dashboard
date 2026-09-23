from __future__ import annotations

from dataclasses import dataclass
import numpy as np
import pandas as pd

from gold_model_v82 import INTRADAY_HORIZON_BARS, intraday_release_reasons

MODEL_VERSION_V83 = "8.3-two-horizon-cost-aware-research"


@dataclass
class V83Decision:
    action: str
    candidate: str
    macro_regime: str
    expected_move: float
    minimum_move: float
    reasons: list[str]
    evaluation: dict[str, float]


def classify_macro_regime(macro: pd.DataFrame, as_of) -> tuple[str, float, list[str]]:
    if macro is None or macro.empty:
        return "NEUTRAL", 0.0, ["no released macro history is available"]
    known = macro.loc[macro.index <= pd.Timestamp(as_of)].copy()
    directions = {
        "real_rate_pct": -1,
        "dollar_index": -1,
        "macro_uncertainty_index": 1,
        "market_volatility_vix": 1,
        "central_bank_demand_tonnes": 1,
        "gold_managed_money_net": 1,
        "geopolitical_risk_index": 1,
    }
    contributions, used = [], []
    for name, direction in directions.items():
        if name not in known:
            continue
        values = pd.to_numeric(known[name], errors="coerce").dropna()
        if len(values) < 20:
            continue
        window = values.tail(min(252, len(values)))
        deviation = window.std()
        if not np.isfinite(deviation) or deviation == 0:
            continue
        z_score = float((window.iloc[-1] - window.mean()) / deviation)
        contributions.append(float(np.clip(direction * z_score, -2, 2)))
        used.append(name)
    if len(contributions) < 2:
        return "NEUTRAL", 0.0, ["fewer than two mature macro regime factors"]
    score = float(np.mean(contributions))
    regime = "BULLISH" if score >= 0.35 else "BEARISH" if score <= -0.35 else "NEUTRAL"
    return regime, score, used


def non_overlapping_evaluation(result, threshold: float, cost_bps: float) -> dict[str, float]:
    sample = result.predictions.iloc[::INTRADAY_HORIZON_BARS].copy()
    cost = cost_bps / 10_000
    minimum = 2 * cost
    sample["position"] = 0
    sample.loc[(sample.probability_up >= threshold) & (sample["median"] > minimum), "position"] = 1
    sample.loc[(sample.probability_up <= 1 - threshold) & (sample["median"] < -minimum), "position"] = -1
    traded = sample[sample.position != 0].copy()
    if traded.empty:
        return {"Observations": float(len(sample)), "Trades": 0.0, "Win rate": np.nan,
                "Profit factor": np.nan, "Net return": 0.0, "Max drawdown": 0.0}
    traded["net_return"] = traded.position * traded.actual_return - cost
    equity = (1 + traded.net_return).cumprod()
    gains = float(traded.loc[traded.net_return > 0, "net_return"].sum())
    losses = float(-traded.loc[traded.net_return < 0, "net_return"].sum())
    return {
        "Observations": float(len(sample)),
        "Trades": float(len(traded)),
        "Win rate": float((traded.net_return > 0).mean()),
        "Profit factor": gains / losses if losses > 0 else np.inf,
        "Net return": float(equity.iloc[-1] - 1),
        "Max drawdown": float((equity / equity.cummax() - 1).min()),
    }


def decide_v83(
    result,
    macro: pd.DataFrame,
    elliott,
    threshold: float,
    cost_bps: float,
    major_event: bool = False,
) -> V83Decision:
    regime, _, regime_evidence = classify_macro_regime(macro, result.as_of)
    evaluation = non_overlapping_evaluation(result, threshold, cost_bps)
    minimum_move = 2 * cost_bps / 10_000
    probability = float(elliott.probability_up)
    if probability >= threshold and result.median_return > minimum_move:
        candidate = "BUY"
    elif probability <= 1 - threshold and result.median_return < -minimum_move:
        candidate = "SELL"
    else:
        candidate = "NO EDGE"
    reasons = intraday_release_reasons(result)
    if evaluation["Trades"] < 20:
        reasons.append("fewer than 20 non-overlapping cost-aware trades")
    if evaluation["Net return"] <= 0:
        reasons.append("non-overlapping cost-aware return is not positive")
    if np.isfinite(evaluation["Profit factor"]) and evaluation["Profit factor"] < 1.20:
        reasons.append("cost-aware profit factor is below 1.20")
    if candidate == "BUY" and regime == "BEARISH":
        reasons.append("BUY candidate conflicts with bearish macro regime")
    if candidate == "SELL" and regime == "BULLISH":
        reasons.append("SELL candidate conflicts with bullish macro regime")
    if elliott.qualified and elliott.current_bias not in {candidate, "NEUTRAL"} and candidate != "NO EDGE":
        reasons.append("qualified Elliott structure contradicts the candidate")
    if major_event:
        action = "BLOCKED"
        reasons.append("major US event flagged within the next hour")
    elif candidate == "NO EDGE" or reasons:
        action = "NO EDGE"
    else:
        action = candidate
    if not regime_evidence:
        reasons.append("macro regime evidence is unavailable")
    return V83Decision(action, candidate, regime, float(result.median_return),
                       minimum_move, list(dict.fromkeys(reasons)), evaluation)

