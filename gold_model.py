from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor, HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.metrics import accuracy_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import TimeSeriesSplit
from sklearn.preprocessing import StandardScaler


TICKERS = {
    "gold": "GC=F",
    "silver": "SI=F",
    "dollar": "DX-Y.NYB",
    "treasury": "TLT",
    "tips": "TIP",
    "oil": "CL=F",
    "stocks": "SPY",
    "vix": "^VIX",
}

HORIZONS = {"Next day": 1, "Next week": 5, "Next month": 21,
            "Next 3 months": 63, "Next 12 months": 252}


@dataclass
class ForecastResult:
    horizon: int
    as_of: pd.Timestamp
    spot: float
    probability_up: float
    median_return: float
    lower_return: float
    upper_return: float
    signal: str
    metrics: dict[str, float]
    predictions: pd.DataFrame
    importance: pd.Series
    features_used: list[str]


def download_market_data(start: str = "2007-01-01") -> pd.DataFrame:
    try:
        import yfinance as yf
    except ImportError as exc:
        raise RuntimeError("Install project packages with: pip install -r requirements.txt") from exc
    raw = yf.download(list(TICKERS.values()), start=start, auto_adjust=True,
                      progress=False, group_by="column", threads=True)
    if raw.empty:
        raise RuntimeError("No market data was downloaded. Check your internet connection.")
    close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
    if isinstance(close, pd.Series):
        close = close.to_frame(TICKERS["gold"])
    rename = {ticker: name for name, ticker in TICKERS.items()}
    close = close.rename(columns=rename).sort_index()
    if "gold" not in close or close["gold"].dropna().empty:
        raise RuntimeError(
            f"Gold symbol {TICKERS['gold']} was unavailable from the data provider."
        )
     
    close = close.reindex(close["gold"].dropna().index).ffill(limit=5)
    return close.dropna(axis=1, how="all")


def _rsi(price: pd.Series, window: int = 14) -> pd.Series:
    change = price.diff()
    gain = change.clip(lower=0).rolling(window).mean()
    loss = -change.clip(upper=0).rolling(window).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def make_features(prices: pd.DataFrame) -> pd.DataFrame:
    gold = prices["gold"]
    out = pd.DataFrame(index=prices.index)
    for n in (1, 5, 10, 21, 63, 126, 252):
        out[f"gold_ret_{n}"] = gold.pct_change(n)
    for n in (10, 21, 63, 126, 252):
        out[f"gold_ma_gap_{n}"] = gold / gold.rolling(n).mean() - 1
    daily = gold.pct_change()
    for n in (10, 21, 63):
        out[f"gold_vol_{n}"] = daily.rolling(n).std() * np.sqrt(252)
    out["rsi_14"] = _rsi(gold) / 100
    out["drawdown_252"] = gold / gold.rolling(252).max() - 1
    out["range_position_63"] = ((gold - gold.rolling(63).min()) /
                                (gold.rolling(63).max() - gold.rolling(63).min()))
    for name in prices.columns:
        if name == "gold":
            continue
        for n in (5, 21, 63):
            out[f"{name}_ret_{n}"] = prices[name].pct_change(n)
        out[f"{name}_vol_21"] = prices[name].pct_change().rolling(21).std() * np.sqrt(252)
    if {"gold", "silver"}.issubset(prices.columns):
        out["gold_silver_ratio_gap"] = ((prices.gold / prices.silver) /
                                         (prices.gold / prices.silver).rolling(126).mean() - 1)
    out = out.replace([np.inf, -np.inf], np.nan)
    return out


def _targets(prices: pd.DataFrame, horizon: int) -> tuple[pd.Series, pd.Series]:
    forward_return = prices["gold"].shift(-horizon) / prices["gold"] - 1
    direction = (forward_return > 0).astype(float)
    direction[forward_return.isna()] = np.nan
    return direction, forward_return


def _models(seed: int = 42):
    classifier = HistGradientBoostingClassifier(
        learning_rate=0.04, max_iter=180, max_leaf_nodes=15,
        min_samples_leaf=25, l2_regularization=1.0, random_state=seed)
    regressors = {
        "lower": GradientBoostingRegressor(loss="quantile", alpha=0.10, n_estimators=140,
            max_depth=2, learning_rate=0.035, min_samples_leaf=20, random_state=seed),
        "median": GradientBoostingRegressor(loss="quantile", alpha=0.50, n_estimators=140,
            max_depth=2, learning_rate=0.035, min_samples_leaf=20, random_state=seed),
        "upper": GradientBoostingRegressor(loss="quantile", alpha=0.90, n_estimators=140,
            max_depth=2, learning_rate=0.035, min_samples_leaf=20, random_state=seed),
    }
    return classifier, regressors


def _signal(probability: float, expected_return: float, cost_bps: float,
            threshold: float) -> str:
    cost = cost_bps / 10_000
    if probability >= threshold and expected_return > cost:
        return "BUY"
    if probability <= 1 - threshold and expected_return < -cost:
        return "SELL"
    return "NEUTRAL"


def fit_and_backtest(prices: pd.DataFrame, horizon: int, splits: int = 6,
                     cost_bps: float = 10, threshold: float = 0.58) -> ForecastResult:
    features = make_features(prices)
    y_cls, y_ret = _targets(prices, horizon)
    combined = features.join(y_cls.rename("direction")).join(y_ret.rename("forward_return")).dropna()
    if len(combined) < 700:
        raise ValueError(f"Only {len(combined)} complete rows; at least 700 are required.")

    X = combined[features.columns]
    y = combined.direction.astype(int)
    r = combined.forward_return
    effective_splits = min(splits, max(2, len(X) // 300))
    cv = TimeSeriesSplit(n_splits=effective_splits, gap=horizon)
    rows: list[pd.DataFrame] = []

    for fold, (train_idx, test_idx) in enumerate(cv.split(X), 1):
        scaler = StandardScaler()
        X_train = scaler.fit_transform(X.iloc[train_idx])
        X_test = scaler.transform(X.iloc[test_idx])
        classifier, regressors = _models(42 + fold)
        classifier.fit(X_train, y.iloc[train_idx])
        pred = pd.DataFrame(index=X.iloc[test_idx].index)
        pred["actual_return"] = r.iloc[test_idx]
        pred["actual_up"] = y.iloc[test_idx]
        pred["probability_up"] = classifier.predict_proba(X_test)[:, 1]
        for key, model in regressors.items():
            model.fit(X_train, r.iloc[train_idx])
            pred[key] = model.predict(X_test)
        pred["fold"] = fold
        rows.append(pred)

    predictions = pd.concat(rows).sort_index()
    predictions["signal"] = [
        _signal(p, m, cost_bps, threshold)
        for p, m in zip(predictions.probability_up, predictions["median"])
    ]
    predictions["position"] = predictions.signal.map({"BUY": 1, "SELL": -1, "NEUTRAL": 0})
    # Sample non-overlapping decisions; this avoids pretending overlapping h-day trades are independent.
    event = predictions.iloc[::horizon].copy()
    turnover = event.position.diff().abs().fillna(event.position.abs())
    event["strategy_return"] = event.position * event.actual_return - turnover * cost_bps / 10_000
    event["strategy_equity"] = (1 + event.strategy_return).cumprod()
    event["gold_equity"] = (1 + event.actual_return).cumprod()
    predictions["strategy_equity"] = event.strategy_equity.reindex(predictions.index).ffill()
    predictions["gold_equity"] = event.gold_equity.reindex(predictions.index).ffill()

    auc = roc_auc_score(predictions.actual_up, predictions.probability_up)
    coverage = ((predictions.actual_return >= predictions.lower) &
                (predictions.actual_return <= predictions.upper)).mean()
    years = max((event.index[-1] - event.index[0]).days / 365.25, 0.25)
    strategy_cagr = event.strategy_equity.iloc[-1] ** (1 / years) - 1
    peak = event.strategy_equity.cummax()
    max_dd = (event.strategy_equity / peak - 1).min()
    metrics = {
        "ROC-AUC": auc,
        "Brier score": brier_score_loss(predictions.actual_up, predictions.probability_up),
        "Direction accuracy": accuracy_score(predictions.actual_up, predictions.probability_up >= 0.5),
        "Always-up accuracy": predictions.actual_up.mean(),
        "80% interval coverage": coverage,
        "Strategy CAGR": strategy_cagr,
        "Strategy max drawdown": max_dd,
        "Trades": float((event.position.diff().fillna(event.position) != 0).sum()),
    }

    full = features.dropna()
    latest_x = full.iloc[[-1]]
    train_mask = X.index <= full.index[-1]
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X.loc[train_mask])
    latest_scaled = scaler.transform(latest_x)
    classifier, regressors = _models(99)
    classifier.fit(X_scaled, y.loc[train_mask])
    probability = float(classifier.predict_proba(latest_scaled)[0, 1])
    forecasts: dict[str, float] = {}
    for key, model in regressors.items():
        model.fit(X_scaled, r.loc[train_mask])
        forecasts[key] = float(model.predict(latest_scaled)[0])
    perm = permutation_importance(classifier, X_scaled[-min(500, len(X_scaled)):],
                                  y.loc[train_mask].iloc[-min(500, len(X_scaled)):],
                                  n_repeats=3, random_state=42, scoring="neg_brier_score")
    importance = pd.Series(perm.importances_mean, index=X.columns).sort_values(ascending=False).head(15)
    spot = float(prices.gold.loc[:latest_x.index[0]].iloc[-1])
    return ForecastResult(
        horizon=horizon, as_of=latest_x.index[0], spot=spot,
        probability_up=probability, median_return=forecasts["median"],
        lower_return=forecasts["lower"], upper_return=forecasts["upper"],
        signal=_signal(probability, forecasts["median"], cost_bps, threshold),
        metrics=metrics, predictions=predictions, importance=importance,
        features_used=list(X.columns))


def price_interval(result: ForecastResult) -> tuple[float, float, float]:
    return tuple(result.spot * (1 + value) for value in
                 (result.lower_return, result.median_return, result.upper_return))
