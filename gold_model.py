from __future__ import annotations

from dataclasses import dataclass
import json
from urllib.parse import urlencode
from urllib.request import urlopen

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor, HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.metrics import accuracy_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import TimeSeriesSplit
from sklearn.preprocessing import StandardScaler

SYMBOL = "XAU/USD"
INTERVAL = "15min"
HORIZON_BARS = 16
HORIZON_LABEL = "4 hours (16 × 15-minute bars)"


@dataclass
class ForecastResult:
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
    observations: int


def download_market_data(api_key: str, outputsize: int = 5000) -> pd.DataFrame:
    if not api_key:
        raise ValueError("TWELVE_DATA_API_KEY is missing from Streamlit secrets.")
    query = urlencode({
        "symbol": SYMBOL, "interval": INTERVAL, "outputsize": outputsize,
        "timezone": "UTC", "format": "JSON", "apikey": api_key,
    })
    with urlopen(f"https://api.twelvedata.com/time_series?{query}", timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("status") == "error" or "values" not in payload:
        raise RuntimeError(f"Twelve Data error: {payload.get('message', 'No candle data returned.')}")
    frame = pd.DataFrame(payload["values"])
    required = ["datetime", "open", "high", "low", "close"]
    missing = [column for column in required if column not in frame]
    if missing:
        raise RuntimeError(f"Twelve Data response is missing: {', '.join(missing)}")
    frame["datetime"] = pd.to_datetime(frame["datetime"], utc=True, errors="coerce")
    for column in ["open", "high", "low", "close"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.set_index("datetime").sort_index()[["open", "high", "low", "close"]]
    frame = frame[~frame.index.duplicated(keep="last")].dropna()
    if len(frame) < 1200:
        raise RuntimeError(
            f"Only {len(frame)} complete 15-minute candles were returned; at least 1,200 are required.")
    return frame


def _rsi(price: pd.Series, window: int = 14) -> pd.Series:
    change = price.diff()
    gain = change.clip(lower=0).ewm(alpha=1 / window, adjust=False).mean()
    loss = -change.clip(upper=0).ewm(alpha=1 / window, adjust=False).mean()
    return 100 - 100 / (1 + gain / loss.replace(0, np.nan))


def make_features(prices: pd.DataFrame) -> pd.DataFrame:
    close = prices["close"]
    out = pd.DataFrame(index=prices.index)
    returns = close.pct_change()
    for bars in (1, 2, 4, 8, 16, 32, 64, 96):
        out[f"return_{bars}"] = close.pct_change(bars)
    for bars in (8, 16, 32, 64, 96):
        out[f"ema_gap_{bars}"] = close / close.ewm(span=bars, adjust=False).mean() - 1
    for bars in (8, 16, 32, 64):
        out[f"volatility_{bars}"] = returns.rolling(bars).std() * np.sqrt(bars)
    previous_close = close.shift(1)
    true_range = pd.concat([
        prices.high - prices.low,
        (prices.high - previous_close).abs(),
        (prices.low - previous_close).abs(),
    ], axis=1).max(axis=1)
    out["atr_14_pct"] = true_range.rolling(14).mean() / close
    out["rsi_14"] = _rsi(close) / 100
    out["candle_body"] = (prices.close - prices.open) / prices.open
    out["range_pct"] = (prices.high - prices.low) / prices.open
    out["range_position_32"] = (
        (close - prices.low.rolling(32).min()) /
        (prices.high.rolling(32).max() - prices.low.rolling(32).min()))
    out["hour_sin"] = np.sin(2 * np.pi * out.index.hour / 24)
    out["hour_cos"] = np.cos(2 * np.pi * out.index.hour / 24)
    out["weekday"] = out.index.dayofweek / 4
    return out.replace([np.inf, -np.inf], np.nan)


def _targets(prices: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    future_return = prices.close.shift(-HORIZON_BARS) / prices.close - 1
    direction = (future_return > 0).astype(float)
    direction[future_return.isna()] = np.nan
    return direction, future_return


def _models(seed: int):
    classifier = HistGradientBoostingClassifier(
        learning_rate=0.035, max_iter=160, max_leaf_nodes=15,
        min_samples_leaf=30, l2_regularization=1.5, random_state=seed)
    regressors = {
        name: GradientBoostingRegressor(
            loss="quantile", alpha=alpha, n_estimators=130, max_depth=2,
            learning_rate=0.035, min_samples_leaf=25, random_state=seed)
        for name, alpha in (("lower", 0.10), ("median", 0.50), ("upper", 0.90))
    }
    return classifier, regressors


def _signal(probability: float, expected_return: float, cost_bps: float,
            threshold: float) -> str:
    cost = cost_bps / 10_000
    if probability >= threshold and expected_return > cost:
        return "BUY"
    if probability <= 1 - threshold and expected_return < -cost:
        return "SELL"
    return "WAIT"


def fit_and_backtest(prices: pd.DataFrame, splits: int = 5,
                     cost_bps: float = 10, threshold: float = 0.65) -> ForecastResult:
    features = make_features(prices)
    y_cls, y_ret = _targets(prices)
    labelled = features.join(y_cls.rename("direction")).join(
        y_ret.rename("forward_return")).dropna()
    if len(labelled) < 1000:
        raise ValueError(f"Only {len(labelled)} labelled rows; at least 1,000 are required.")
    X = labelled[features.columns]
    y = labelled.direction.astype(int)
    returns = labelled.forward_return
    effective_splits = min(splits, max(3, len(X) // 500))
    cv = TimeSeriesSplit(n_splits=effective_splits, gap=HORIZON_BARS)
    rows = []
    for fold, (train_idx, test_idx) in enumerate(cv.split(X), 1):
        scaler = StandardScaler()
        train = scaler.fit_transform(X.iloc[train_idx])
        test = scaler.transform(X.iloc[test_idx])
        classifier, regressors = _models(40 + fold)
        classifier.fit(train, y.iloc[train_idx])
        pred = pd.DataFrame(index=X.iloc[test_idx].index)
        pred["actual_return"] = returns.iloc[test_idx]
        pred["actual_up"] = y.iloc[test_idx]
        pred["probability_up"] = classifier.predict_proba(test)[:, 1]
        for name, model in regressors.items():
            model.fit(train, returns.iloc[train_idx])
            pred[name] = model.predict(test)
        pred["fold"] = fold
        rows.append(pred)
    predictions = pd.concat(rows).sort_index()
    predictions["signal"] = [
        _signal(p, m, cost_bps, threshold)
        for p, m in zip(predictions.probability_up, predictions["median"])]
    predictions["position"] = predictions.signal.map({"BUY": 1, "SELL": -1, "WAIT": 0})
    events = predictions.iloc[::HORIZON_BARS].copy()
    turnover = events.position.diff().abs().fillna(events.position.abs())
    events["strategy_return"] = (
        events.position * events.actual_return - turnover * cost_bps / 10_000)
    events["strategy_equity"] = (1 + events.strategy_return).cumprod()
    events["gold_equity"] = (1 + events.actual_return).cumprod()
    predictions["strategy_equity"] = events.strategy_equity.reindex(predictions.index).ffill()
    predictions["gold_equity"] = events.gold_equity.reindex(predictions.index).ffill()
    peak = events.strategy_equity.cummax()
    metrics = {
        "ROC-AUC": roc_auc_score(predictions.actual_up, predictions.probability_up),
        "Brier score": brier_score_loss(predictions.actual_up, predictions.probability_up),
        "Direction accuracy": accuracy_score(
            predictions.actual_up, predictions.probability_up >= 0.5),
        "Always-up accuracy": predictions.actual_up.mean(),
        "80% interval coverage": ((predictions.actual_return >= predictions.lower) &
                                  (predictions.actual_return <= predictions.upper)).mean(),
        "Strategy total return": events.strategy_equity.iloc[-1] - 1,
        "Strategy max drawdown": (events.strategy_equity / peak - 1).min(),
        "Signal changes": float((events.position.diff().fillna(events.position) != 0).sum()),
    }
    full_features = features.dropna()
    latest_x = full_features.iloc[[-1]]
    scaler = StandardScaler()
    scaled = scaler.fit_transform(X)
    latest_scaled = scaler.transform(latest_x)
    classifier, regressors = _models(99)
    classifier.fit(scaled, y)
    probability = float(classifier.predict_proba(latest_scaled)[0, 1])
    forecast = {}
    for name, model in regressors.items():
        model.fit(scaled, returns)
        forecast[name] = float(model.predict(latest_scaled)[0])
    sample = min(500, len(X))
    perm = permutation_importance(
        classifier, scaled[-sample:], y.iloc[-sample:], n_repeats=3,
        random_state=42, scoring="neg_brier_score")
    importance = pd.Series(perm.importances_mean, index=X.columns).nlargest(15)
    as_of = latest_x.index[0]
    spot = float(prices.close.loc[:as_of].iloc[-1])
    return ForecastResult(
        as_of=as_of, spot=spot, probability_up=probability,
        median_return=forecast["median"], lower_return=forecast["lower"],
        upper_return=forecast["upper"],
        signal=_signal(probability, forecast["median"], cost_bps, threshold),
        metrics=metrics, predictions=predictions, importance=importance,
        features_used=list(X.columns), observations=len(prices))


def price_interval(result: ForecastResult) -> tuple[float, float, float]:
    return tuple(result.spot * (1 + value) for value in
                 (result.lower_return, result.median_return, result.upper_return))
