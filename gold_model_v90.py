from __future__ import annotations

from dataclasses import dataclass
import math
import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesClassifier, HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, brier_score_loss, log_loss, roc_auc_score
from sklearn.preprocessing import StandardScaler

from gold_model import (
    ForecastResult, _download_symbol, _models, _signal, make_features,
    permutation_importance)
from gold_model_v82 import _wilson_lower
from institutional_features_v830 import (
    institutional_features, latest_institutional_audit)

MODEL_VERSION_V90 = "9.3-thirty-minute-six-venue-order-flow-research"
INTRADAY_INTERVAL = "15min"
INTRADAY_HORIZON_BARS = 2
INTRADAY_HORIZON_LABEL = "30 minutes (2 x 15-minute bars)"


def download_five_minute_gold(api_key, outputsize=5000):
    """Download a separate 5-minute XAU/USD series for reversal warnings."""
    frame = _download_symbol(
        api_key, "XAU/USD", outputsize, interval="5min")
    if len(frame) < 1200:
        raise RuntimeError(
            f"Only {len(frame)} five-minute candles were returned; 1,200 required.")
    return frame


def five_minute_reversal_states(gold_5m):
    """Causal exhaustion-and-break detector using completed five-minute bars."""
    close = gold_5m.close.astype(float)
    returns = close.pct_change()
    volatility = returns.rolling(96, min_periods=48).std().shift(1)
    scaled_one = returns / volatility.replace(0, np.nan)
    prior_low = gold_5m.low.shift(1)
    prior_high = gold_5m.high.shift(1)
    extension_up = (
        close.shift(1) / close.shift(1).rolling(12, min_periods=8).min() - 1
    ) / (volatility * np.sqrt(12)).replace(0, np.nan)
    extension_down = (
        close.shift(1) / close.shift(1).rolling(12, min_periods=8).max() - 1
    ) / (volatility * np.sqrt(12)).replace(0, np.nan)
    body = (gold_5m.close - gold_5m.open) / gold_5m.open
    candle_range = (gold_5m.high - gold_5m.low).replace(0, np.nan)
    close_location = (gold_5m.close - gold_5m.low) / candle_range
    normal_range = candle_range.rolling(48, min_periods=24).median().shift(1)
    expansion = candle_range / normal_range.replace(0, np.nan)
    sell = (
        (extension_up >= 1.25) & (close < prior_low) &
        (scaled_one <= -.65) & (body < 0) &
        (close_location <= .40) & (expansion >= 1.10))
    buy = (
        (extension_down <= -1.25) & (close > prior_high) &
        (scaled_one >= .65) & (body > 0) &
        (close_location >= .60) & (expansion >= 1.10))
    signal = pd.Series(0, index=gold_5m.index, dtype=int)
    signal.loc[buy.fillna(False)] = 1
    signal.loc[sell.fillna(False)] = -1
    return pd.DataFrame({
        "signal": signal,
        "extension_up": extension_up,
        "extension_down": extension_down,
        "scaled_return": scaled_one,
        "range_expansion": expansion,
        "close_location": close_location,
    }, index=gold_5m.index)


def _side_reversal_validation(sample, side, cost_bps, min_observations):
    selected = sample[sample.signal.eq(side)].copy()
    holdout_size = max(min_observations, int(math.ceil(len(selected) * .30)))
    holdout = selected.tail(min(len(selected), holdout_size))
    n = len(holdout)
    wins = int((side * holdout.future_return > 0).sum()) if n else 0
    accuracy = wins / n if n else np.nan
    lower = _wilson_lower(wins, n)
    net = side * holdout.future_return - cost_bps / 10_000
    gains = float(net[net > 0].sum())
    losses = float(-net[net < 0].sum())
    profit_factor = gains / losses if losses > 0 else (
        np.inf if gains > 0 else np.nan)
    qualified = bool(
        n >= min_observations and accuracy >= .55 and lower >= .50 and
        np.isfinite(profit_factor) and profit_factor >= 1.20)
    return {
        "qualified": qualified, "observations": n,
        "accuracy": accuracy, "lower_bound": lower,
        "profit_factor": profit_factor,
    }


def audit_five_minute_reversals(gold_5m, cost_bps=10,
                                min_observations=30):
    """Validate each reversal side on a newest, untouched chronological holdout."""
    states = five_minute_reversal_states(gold_5m)
    future = gold_5m.close.shift(-3) / gold_5m.close - 1
    sample = states[states.signal.ne(0)].copy()
    sample["future_return"] = future.reindex(sample.index)
    sample = sample.dropna(subset=["future_return"])
    buy = _side_reversal_validation(
        sample, 1, cost_bps, min_observations)
    sell = _side_reversal_validation(
        sample, -1, cost_bps, min_observations)
    current = int(states.signal.iloc[-1])
    side = buy if current > 0 else sell if current < 0 else None
    warning = "EARLY BUY WARNING" if current > 0 else (
        "EARLY SELL WARNING" if current < 0 else "NONE")
    released = bool(side and side["qualified"])
    return {
        "status": "PASS" if released else (
            "FAIL" if current else "MONITORING"),
        "warning": warning if released else "NONE",
        "raw_warning": warning,
        "current_signal": current,
        "buy": buy, "sell": sell,
        "latest": states.iloc[-1].to_dict(),
        "as_of": states.index[-1],
    }


@dataclass
class V90Decision:
    action: str
    candidate: str
    macro_regime: str
    expected_move: float
    minimum_move: float
    reasons: list[str]
    evaluation: dict[str, float]


def shock_regime(gold, confirmations=None, window=96, z_threshold=6.0,
                 range_threshold=4.0, cooldown_bars=4):
    """Causally identify abnormal 15-minute jumps and their cooldown.

    Baselines are shifted by one bar, so the candle being assessed never
    contributes to its own volatility threshold.
    """
    if window < 32:
        raise ValueError("shock window must be at least 32 bars")
    log_return = np.log(gold.close.where(gold.close > 0)).diff()
    centre = log_return.rolling(window, min_periods=32).median().shift(1)
    mad = (log_return - centre).abs().rolling(
        window, min_periods=32).median().shift(1)
    robust_sigma = (1.4826 * mad).replace(0, np.nan)
    jump_z = ((log_return - centre).abs() / robust_sigma).clip(upper=50)
    previous = gold.close.shift(1)
    true_range = pd.concat([
        gold.high - gold.low,
        (gold.high - previous).abs(),
        (gold.low - previous).abs(),
    ], axis=1).max(axis=1) / previous
    normal_range = true_range.rolling(window, min_periods=32).median().shift(1)
    range_ratio = (true_range / normal_range.replace(0, np.nan)).clip(upper=50)
    # A local bipower proxy estimates continuous variation from adjacent
    # absolute returns; excess squared return is the jump contribution.
    bipower = (
        (np.pi / 2) * log_return.abs() * log_return.abs().shift(1)
    ).rolling(window, min_periods=32).mean().shift(1)
    jump_variance = (log_return.pow(2) - bipower).clip(lower=0)
    shock = (jump_z >= z_threshold) | (range_ratio >= range_threshold)
    severe = (jump_z >= z_threshold * 1.5) | (range_ratio >= range_threshold * 1.5)
    bars_since = pd.Series(np.nan, index=gold.index)
    last = None
    for i, flag in enumerate(shock.fillna(False).to_numpy()):
        if flag:
            last = i
        if last is not None:
            bars_since.iloc[i] = i - last
    cooldown = bars_since.notna() & (bars_since < cooldown_bars)
    out = pd.DataFrame({
        "shock_return": log_return, "shock_z": jump_z,
        "shock_range_ratio": range_ratio,
        "shock_jump_variance": jump_variance,
        "shock_detected": shock.fillna(False),
        "severe_shock": severe.fillna(False),
        "shock_cooldown": cooldown,
        "bars_since_shock": bars_since,
    }, index=gold.index)
    cross_count = pd.Series(0.0, index=gold.index)
    for frame in (confirmations or {}).values():
        aligned = frame.close.reindex(gold.index, method="ffill", limit=4)
        r = np.log(aligned.where(aligned > 0)).diff()
        med = r.rolling(window, min_periods=32).median().shift(1)
        scale = (1.4826 * (r - med).abs().rolling(
            window, min_periods=32).median().shift(1)).replace(0, np.nan)
        cross_count += (((r - med).abs() / scale) >= 4.0).fillna(False).astype(float)
    out["cross_asset_shocks"] = cross_count
    return out


def latest_shock_audit(gold, confirmations=None):
    history = shock_regime(gold, confirmations)
    row = history.iloc[-1]
    active = bool(row.shock_cooldown)
    return {
        "active": active,
        "detected_now": bool(row.shock_detected),
        "severe": bool(row.severe_shock),
        "z_score": float(row.shock_z) if np.isfinite(row.shock_z) else np.nan,
        "range_ratio": (
            float(row.shock_range_ratio)
            if np.isfinite(row.shock_range_ratio) else np.nan),
        "cross_asset_shocks": int(row.cross_asset_shocks),
        "bars_since_shock": (
            int(row.bars_since_shock)
            if np.isfinite(row.bars_since_shock) else None),
        "history": history,
    }


def technical_rejection_states(gold, confirmations=None, cooldown_bars=4):
    """Confirm spike rejection only after a full one-hour cooldown.

    An upward shock is a bearish rejection only when the close four bars later
    is below the shock candle midpoint; the inverse defines a bullish rejection.
    """
    shocks = shock_regime(
        gold, confirmations, cooldown_bars=cooldown_bars)
    states = pd.DataFrame(index=gold.index)
    states["rejection_signal"] = 0
    states["shock_direction"] = 0
    states["shock_midpoint"] = np.nan
    states["shock_timestamp"] = pd.Series(
        [None] * len(states), index=states.index, dtype="object")
    for i in np.flatnonzero(shocks.shock_detected.to_numpy()):
        j = i + cooldown_bars
        if j >= len(gold):
            continue
        direction = int(np.sign(
            np.log(gold.close.iloc[i] / gold.close.iloc[i - 1]))) if i else 0
        midpoint = float((gold.high.iloc[i] + gold.low.iloc[i]) / 2)
        confirmed = (
            -1 if direction > 0 and gold.close.iloc[j] < midpoint
            else 1 if direction < 0 and gold.close.iloc[j] > midpoint
            else 0)
        states.iloc[j, states.columns.get_loc("rejection_signal")] = confirmed
        states.iloc[j, states.columns.get_loc("shock_direction")] = direction
        states.iloc[j, states.columns.get_loc("shock_midpoint")] = midpoint
        states.iloc[j, states.columns.get_loc("shock_timestamp")] = gold.index[i]
    return states


def audit_technical_rejections(gold, confirmations=None, cost_bps=10,
                               min_observations=30):
    states = technical_rejection_states(gold, confirmations)
    future = gold.close.shift(-INTRADAY_HORIZON_BARS) / gold.close - 1
    sample = states[states.rejection_signal != 0].copy()
    sample["future_return"] = future.reindex(sample.index)
    sample = sample.dropna(subset=["future_return"])
    sample["success"] = sample.rejection_signal * sample.future_return > 0
    sample["net_return"] = (
        sample.rejection_signal * sample.future_return - cost_bps / 10_000)
    # Newest 30% is the untouched qualification holdout.
    holdout_size = max(
        min_observations, int(math.ceil(len(sample) * .30)))
    holdout = sample.tail(min(len(sample), holdout_size))
    n = len(holdout)
    wins = int(holdout.success.sum()) if n else 0
    accuracy = wins / n if n else np.nan
    lower = _wilson_lower(wins, n)
    gains = float(holdout.loc[
        holdout.net_return > 0, "net_return"].sum())
    losses = float(-holdout.loc[
        holdout.net_return < 0, "net_return"].sum())
    profit_factor = gains / losses if losses > 0 else (
        np.inf if gains > 0 else np.nan)
    qualified = bool(
        n >= min_observations and accuracy >= .55 and lower >= .50 and
        np.isfinite(profit_factor) and profit_factor >= 1.20)
    current_signal = int(states.rejection_signal.iloc[-1])
    return {
        "qualified": qualified, "observations": n, "accuracy": accuracy,
        "lower_bound": lower, "profit_factor": profit_factor,
        "current_signal": current_signal,
        "current_bias": (
            "BUY" if current_signal > 0 else
            "SELL" if current_signal < 0 else "NEUTRAL"),
        "history": sample,
    }


def _safe_auc(y, p):
    return float(roc_auc_score(y, p)) if pd.Series(y).nunique() > 1 else 0.5


def _v90_features(gold, confirmations):
    """Causal features available at the forecast timestamp."""
    out = make_features(gold, confirmations).copy()
    returns = gold.close.pct_change()
    for short, long in ((4, 32), (8, 64), (16, 96)):
        sv, lv = returns.rolling(short).std(), returns.rolling(long).std()
        out[f"vol_ratio_{short}_{long}"] = sv / lv.replace(0, np.nan)
        out[f"trend_vol_{short}_{long}"] = (
            gold.close.pct_change(short) / (lv * math.sqrt(short)).replace(0, np.nan))
    minute = out.index.hour * 60 + out.index.minute
    out["tod_sin"] = np.sin(2 * np.pi * minute / 1440)
    out["tod_cos"] = np.cos(2 * np.pi * minute / 1440)
    out["london_ny_overlap"] = ((out.index.hour >= 13) & (out.index.hour < 17)).astype(float)
    for name, frame in confirmations.items():
        aligned = frame.close.reindex(gold.index, method="ffill", limit=4)
        out[f"{name}_shock_4"] = (
            aligned.pct_change(4) /
            aligned.pct_change().rolling(64).std().replace(0, np.nan))
    shocks = shock_regime(gold, confirmations)
    out["jump_z"] = shocks.shock_z
    out["range_shock_ratio"] = shocks.shock_range_ratio
    out["jump_variance"] = shocks.shock_jump_variance
    out["cross_asset_shock_count"] = shocks.cross_asset_shocks
    out["post_shock_cooldown"] = shocks.shock_cooldown.astype(float)
    out = out.join(institutional_features(gold), how="left")
    return out.replace([np.inf, -np.inf], np.nan)


def _raw_models(seed):
    return [
        HistGradientBoostingClassifier(
            learning_rate=.035, max_iter=180, max_leaf_nodes=15,
            min_samples_leaf=35, l2_regularization=2.0, random_state=seed),
        ExtraTreesClassifier(
            n_estimators=180, max_depth=7, min_samples_leaf=20,
            max_features="sqrt", class_weight="balanced", n_jobs=-1,
            random_state=seed + 100),
        LogisticRegression(
            C=.20, max_iter=2000, class_weight="balanced", random_state=seed + 200),
    ]


def _component_probabilities(train_x, train_y, predict_x, seed):
    models, probabilities = _raw_models(seed), []
    for model in models:
        model.fit(train_x, train_y)
        probabilities.append(model.predict_proba(predict_x)[:, 1])
    return models, np.column_stack(probabilities)


def _calibration_weights(probabilities, actual):
    """Weight members using only a held-out calibration segment."""
    losses = np.array([
        brier_score_loss(actual, probabilities[:, i])
        for i in range(probabilities.shape[1])], dtype=float)
    inverse = 1.0 / np.clip(losses, 1e-4, None)
    weights = inverse / inverse.sum()
    equal = np.repeat(1.0 / probabilities.shape[1], probabilities.shape[1])
    weighted_loss = brier_score_loss(actual, probabilities @ weights)
    equal_loss = brier_score_loss(actual, probabilities @ equal)
    return weights if weighted_loss < equal_loss else equal


def _fit_weighted_ensemble(train_x, train_y, calibration_x, calibration_y,
                           predict_x, seed):
    models, calibration = _component_probabilities(
        train_x, train_y, calibration_x, seed)
    prediction = np.column_stack([
        model.predict_proba(predict_x)[:, 1] for model in models])
    weights = _calibration_weights(calibration, calibration_y)
    raw = prediction @ weights
    disagreement = prediction.std(axis=1)
    return models, raw, disagreement, weights, calibration @ weights


def _conformalize_quantiles(actual, lower, median, upper, test_lower,
                            test_median, test_upper, coverage=.80):
    """Split-conformal interval expansion and robust median-bias correction."""
    actual = np.asarray(actual, dtype=float)
    lower, median, upper = map(
        lambda value: np.asarray(value, dtype=float), (lower, median, upper))
    scores = np.maximum(lower - actual, actual - upper)
    scores = np.maximum(scores, 0.0)
    level = min(1.0, np.ceil((len(scores) + 1) * coverage) / len(scores))
    qhat = float(np.quantile(scores, level, method="higher"))
    bias = float(np.median(actual - median))
    return (np.asarray(test_lower) - qhat,
            np.asarray(test_median) + bias,
            np.asarray(test_upper) + qhat, qhat, bias)


def _sigmoid_calibrate(raw_cal, y_cal, raw_test):
    """Fold-local Platt calibration that never sees test outcomes."""
    raw_cal = np.clip(raw_cal, 1e-5, 1 - 1e-5)
    raw_test = np.clip(raw_test, 1e-5, 1 - 1e-5)
    if pd.Series(y_cal).nunique() < 2:
        return raw_test
    logit = lambda p: np.log(p / (1 - p)).reshape(-1, 1)
    calibrator = LogisticRegression(C=1.0, max_iter=1000)
    calibrator.fit(logit(raw_cal), y_cal)
    return calibrator.predict_proba(logit(raw_test))[:, 1]


def _folds(n, splits, gap):
    """Expanding chronological folds with a label purge."""
    test_size = n // (splits + 1)
    if test_size < 120:
        raise ValueError("Too little history for reliable Version 9.0 folds.")
    for fold in range(splits):
        test_start = n - (splits - fold) * test_size
        train_end = test_start - gap
        test_end = min(n, test_start + test_size)
        if train_end >= 600:
            yield np.arange(train_end), np.arange(test_start, test_end)


def selective_reliability(predictions, probability, threshold,
                          min_observations=30):
    """Measure side-specific out-of-sample reliability near an action."""
    side = "BUY" if probability >= threshold else (
        "SELL" if probability <= 1 - threshold else "NO EDGE")
    if side == "NO EDGE":
        return {"side": side, "qualified": False, "observations": 0,
                "accuracy": np.nan, "lower_bound": np.nan}
    sample = predictions[
        predictions.probability_up >= threshold
        if side == "BUY" else
        predictions.probability_up <= 1 - threshold].copy()
    correct = (sample.actual_up.eq(1) if side == "BUY"
               else sample.actual_up.eq(0))
    n, wins = len(sample), int(correct.sum())
    lower = _wilson_lower(wins, n)
    return {
        "side": side, "qualified": bool(
            n >= min_observations and lower >= .50),
        "observations": n,
        "accuracy": wins / n if n else np.nan,
        "lower_bound": lower,
    }


def balanced_release_reasons(result) -> list[str]:
    """Moderately lenient 30-minute gates; hard safety gates stay unchanged."""
    metrics = result.metrics
    reasons = []
    if metrics.get("ROC-AUC", 0) < .52:
        reasons.append("30-minute ROC-AUC is below 0.52")
    if metrics.get("Strategy total return", 0) <= 0:
        reasons.append("30-minute walk-forward strategy return is not positive")
    if metrics.get("Strategy max drawdown", -1) < -.12:
        reasons.append("30-minute walk-forward drawdown exceeds 12%")
    coverage = metrics.get("80% interval coverage", 0)
    if not .68 <= coverage <= .92:
        reasons.append("30-minute interval coverage is outside 68% to 92%")
    if metrics.get("Signal changes", 0) < 15:
        reasons.append("fewer than 15 non-overlapping signal changes")
    return reasons


def fit_v90_system(gold, confirmations, splits=5, cost_bps=10, threshold=.60):
    """Purged, calibrated 30-minute ensemble using completed 15-minute bars."""
    features = _v90_features(gold, confirmations)
    future = gold.close.shift(-INTRADAY_HORIZON_BARS) / gold.close - 1
    labelled = features.join(future.rename("future_return")).dropna()
    if len(labelled) < 1200:
        raise ValueError(f"Only {len(labelled)} labelled rows; Version 9.0 requires 1,200.")
    X, returns = labelled[features.columns], labelled.future_return
    y = (returns > 0).astype(int)
    rows = []
    for fold, (train_idx, test_idx) in enumerate(
            _folds(len(X), splits, INTRADAY_HORIZON_BARS), 1):
        cal_size = max(160, int(len(train_idx) * .20))
        fit_end = len(train_idx) - cal_size - INTRADAY_HORIZON_BARS
        fit_idx = train_idx[:fit_end]
        cal_idx = train_idx[fit_end + INTRADAY_HORIZON_BARS:]
        scaler = StandardScaler().fit(X.iloc[fit_idx])
        fit_x, cal_x = scaler.transform(X.iloc[fit_idx]), scaler.transform(X.iloc[cal_idx])
        test_x = scaler.transform(X.iloc[test_idx])
        _, raw_test, disagreement, weights, raw_cal = _fit_weighted_ensemble(
            fit_x, y.iloc[fit_idx], cal_x, y.iloc[cal_idx],
            test_x, 100 + fold)
        pred = pd.DataFrame(index=X.iloc[test_idx].index)
        pred["actual_return"], pred["actual_up"] = returns.iloc[test_idx], y.iloc[test_idx]
        pred["raw_probability_up"] = raw_test
        pred["probability_up"] = _sigmoid_calibrate(raw_cal, y.iloc[cal_idx], raw_test)
        pred["model_disagreement"] = disagreement
        _, regressors = _models(300 + fold)
        cal_forecast, test_forecast = {}, {}
        for name, model in regressors.items():
            model.fit(fit_x, returns.iloc[fit_idx])
            cal_forecast[name] = model.predict(cal_x)
            test_forecast[name] = model.predict(test_x)
        lower, median, upper, qhat, bias = _conformalize_quantiles(
            returns.iloc[cal_idx], cal_forecast["lower"],
            cal_forecast["median"], cal_forecast["upper"],
            test_forecast["lower"], test_forecast["median"],
            test_forecast["upper"])
        pred["lower"], pred["median"], pred["upper"] = lower, median, upper
        pred["conformal_adjustment"] = qhat
        pred["median_bias_adjustment"] = bias
        pred["fold"] = fold
        rows.append(pred)
    if not rows:
        raise ValueError("No valid Version 9.0 folds could be constructed.")
    predictions = pd.concat(rows).sort_index()
    predictions["signal"] = [
        _signal(p, m, cost_bps * 2, threshold)
        for p, m in zip(predictions.probability_up, predictions["median"])]
    predictions["position"] = predictions.signal.map({"BUY": 1, "SELL": -1, "WAIT": 0})
    events = predictions.iloc[::INTRADAY_HORIZON_BARS].copy()
    turnover = events.position.diff().abs().fillna(events.position.abs())
    events["strategy_return"] = (
        events.position * events.actual_return - turnover * cost_bps / 10_000)
    equity = (1 + events.strategy_return).cumprod()
    brier = float(brier_score_loss(predictions.actual_up, predictions.probability_up))
    raw_brier = float(brier_score_loss(
        predictions.actual_up, predictions.raw_probability_up))
    metrics = {
        "ROC-AUC": _safe_auc(predictions.actual_up, predictions.probability_up),
        "Raw ensemble ROC-AUC": _safe_auc(
            predictions.actual_up, predictions.raw_probability_up),
        "Brier score": brier,
        "Raw ensemble Brier score": raw_brier,
        "Log loss": float(log_loss(
            predictions.actual_up, predictions.probability_up)),
        "Direction accuracy": float(accuracy_score(
            predictions.actual_up, predictions.probability_up >= .5)),
        "Always-up accuracy": float(predictions.actual_up.mean()),
        "Calibration improvement": raw_brier - brier,
        "80% interval coverage": float((
            (predictions.actual_return >= predictions.lower) &
            (predictions.actual_return <= predictions.upper)).mean()),
        "Strategy total return": float(equity.iloc[-1] - 1),
        "Strategy max drawdown": float((equity / equity.cummax() - 1).min()),
        "Signal changes": float(
            (events.position.diff().fillna(events.position) != 0).sum()),
        "Mean model disagreement": float(predictions.model_disagreement.mean()),
    }
    # Version 8.2.5 predicts a different, one-hour target and therefore is not
    # a statistically valid champion comparison for this 30-minute model.
    baseline_metrics = {}

    clean, latest = features.dropna(), features.dropna().iloc[[-1]]
    cal_size = max(200, int(len(X) * .20))
    fit_end = len(X) - cal_size - INTRADAY_HORIZON_BARS
    fit_idx = np.arange(fit_end)
    cal_idx = np.arange(fit_end + INTRADAY_HORIZON_BARS, len(X))
    scaler = StandardScaler().fit(X.iloc[fit_idx])
    scaled, latest_scaled = scaler.transform(X), scaler.transform(latest)
    final_models, raw_latest, disagreement, weights, raw_cal = (
        _fit_weighted_ensemble(
            scaled[fit_idx], y.iloc[fit_idx], scaled[cal_idx],
            y.iloc[cal_idx], latest_scaled, 900))
    probability = float(_sigmoid_calibrate(
        raw_cal, y.iloc[cal_idx], raw_latest)[0])
    _, regressors = _models(999)
    forecast, calibration_forecast = {}, {}
    for name, model in regressors.items():
        model.fit(scaled[fit_idx], returns.iloc[fit_idx])
        forecast[name] = float(model.predict(latest_scaled)[0])
        calibration_forecast[name] = model.predict(scaled[cal_idx])
    calibrated = _conformalize_quantiles(
        returns.iloc[cal_idx], calibration_forecast["lower"],
        calibration_forecast["median"], calibration_forecast["upper"],
        [forecast["lower"]], [forecast["median"]], [forecast["upper"]])
    forecast["lower"], forecast["median"], forecast["upper"] = (
        float(calibrated[0][0]), float(calibrated[1][0]),
        float(calibrated[2][0]))
    sample = min(500, len(X))
    perm = permutation_importance(
        final_models[0], scaled[-sample:], y.iloc[-sample:], n_repeats=2,
        random_state=42, scoring="neg_brier_score")
    importance = pd.Series(
        perm.importances_mean, index=X.columns).nlargest(15)
    as_of = latest.index[0]
    spot = float(gold.close.loc[:as_of].iloc[-1])
    regime = (
        "HIGH VOLATILITY"
        if clean.vol_ratio_8_64.iloc[-1] > 1.35 else "NORMAL")
    result = ForecastResult(
        as_of, spot, probability, forecast["median"], forecast["lower"],
        forecast["upper"],
        _signal(probability, forecast["median"], cost_bps * 2, threshold),
        regime, metrics, baseline_metrics, predictions, importance,
        list(X.columns), len(gold))
    result.shock_audit = latest_shock_audit(gold, confirmations)
    result.rejection_audit = audit_technical_rejections(
        gold, confirmations, cost_bps)
    result.institutional_audit = latest_institutional_audit(gold)
    result.model_disagreement = float(disagreement[0])
    result.ensemble_weights = {
        name: float(weight) for name, weight in zip(
            ("Gradient boosting", "Extra trees", "Logistic"), weights)}
    result.conformal_adjustment = float(calibrated[3])
    result.median_bias_adjustment = float(calibrated[4])
    rejection = result.rejection_audit
    result.rejection_adjustment = 0.0
    if rejection["qualified"] and rejection["current_signal"]:
        strength = min(
            1.0, max(0.0, (rejection["lower_bound"] - .50) / .08))
        result.rejection_adjustment = float(
            rejection["current_signal"] * strength * .04)
        result.probability_up = float(np.clip(
            result.probability_up + result.rejection_adjustment, .01, .99))
        result.signal = _signal(
            result.probability_up, result.median_return,
            cost_bps * 2, threshold)
    return result


def classify_macro_regime(macro, as_of):
    if macro is None or macro.empty:
        return "NEUTRAL", 0.0, ["no released macro history is available"]
    known = macro.loc[macro.index <= pd.Timestamp(as_of)].copy()
    directions = {
        "real_rate_pct": -1, "dollar_index": -1,
        "macro_uncertainty_index": 1, "market_volatility_vix": 1,
        "central_bank_demand_tonnes": 1, "gold_managed_money_net": 1,
        "geopolitical_risk_index": 1}
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
        z = (window.iloc[-1] - window.mean()) / deviation
        contributions.append(float(np.clip(direction * z, -2, 2)))
        used.append(name)
    if len(contributions) < 2:
        return "NEUTRAL", 0.0, ["fewer than two mature macro regime factors"]
    score = float(np.mean(contributions))
    regime = "BULLISH" if score >= .35 else "BEARISH" if score <= -.35 else "NEUTRAL"
    return regime, score, used


def short_term_technical_trend(gold):
    """Causal multi-speed trend state using completed 15-minute candles."""
    close = gold.close.astype(float)
    returns = close.pct_change()
    volatility = returns.rolling(64, min_periods=32).std().iloc[-1]
    volatility = float(volatility) if np.isfinite(volatility) and volatility > 0 else 1e-6
    ema_fast = close.ewm(span=8, adjust=False).mean()
    ema_slow = close.ewm(span=32, adjust=False).mean()
    previous = close.shift(1)
    true_range = pd.concat([
        gold.high - gold.low,
        (gold.high - previous).abs(),
        (gold.low - previous).abs(),
    ], axis=1).max(axis=1)
    atr = float(true_range.rolling(14, min_periods=8).mean().iloc[-1])
    atr = atr if np.isfinite(atr) and atr > 0 else float(close.iloc[-1] * volatility)
    components = {
        "one_hour_momentum": float(np.clip(
            close.pct_change(4).iloc[-1] / (volatility * 2), -2, 2)),
        "two_hour_momentum": float(np.clip(
            close.pct_change(8).iloc[-1] / (volatility * np.sqrt(8)), -2, 2)),
        "ema_alignment": float(np.clip(
            (ema_fast.iloc[-1] - ema_slow.iloc[-1]) / atr, -2, 2)),
        "candle_persistence": float(np.clip(
            (returns.tail(8).gt(0).mean() - .5) * 4, -2, 2)),
    }
    weights = {
        "one_hour_momentum": .35, "two_hour_momentum": .25,
        "ema_alignment": .25, "candle_persistence": .15}
    score = float(sum(components[name] * weights[name] for name in weights) / 2)
    score = float(np.clip(score, -1, 1))
    trend = "UPTREND" if score >= .20 else (
        "DOWNTREND" if score <= -.20 else "RANGE")
    return {
        "trend": trend, "score": score,
        "confidence": "HIGH" if abs(score) >= .60 else (
            "MODERATE" if abs(score) >= .35 else "LOW"),
        "components": components,
    }


def institutional_liquidity_score(audit) -> float:
    """Small directional proxy toward nearby prior liquidity; never an order."""
    if audit is None or not np.isfinite(audit.liquidity_distance_pct):
        return 0.0
    proximity = float(np.clip(1 - audit.liquidity_distance_pct / .01, 0, 1))
    direction = 1.0 if audit.nearest_liquidity == "PRIOR HIGH" else (
        -1.0 if audit.nearest_liquidity == "PRIOR LOW" else 0.0)
    # Compression increases breakout risk but does not reveal breakout side.
    # It scales an already directional nearby-liquidity observation only.
    compression = audit.compression_percentile
    range_scale = (
        .75 + .25 * float(np.clip(compression, 0, 1))
        if np.isfinite(compression) else .75)
    return float(direction * proximity * range_scale)


def combined_directional_lean(result, macro, technical,
                              perpetual_consensus=None, institutional=None,
                              event_lock=False):
    """Transparent directional synthesis; never bypasses the action gates."""
    _, macro_score, _ = classify_macro_regime(macro, result.as_of)
    statistical = float(np.clip((result.probability_up - .5) / .15, -1, 1))
    expected = float(np.clip(
        result.median_return / max(abs(result.median_return), .0015), -1, 1))
    microstructure = 0.0
    micro_weight = 0.0
    pressure_indication = "WAIT"
    if perpetual_consensus is not None and perpetual_consensus.agreement >= 2:
        microstructure = float(getattr(
            perpetual_consensus, "pressure_score",
            1.0 if perpetual_consensus.direction == "BUY PRESSURE" else
            -1.0 if perpetual_consensus.direction == "SELL PRESSURE" else 0.0))
        pressure_indication = getattr(
            perpetual_consensus, "order_flow_decision", "WAIT")
        # Cross-venue executed flow is the priority timing input when the feed
        # passes its coverage/agreement gate. It remains a proxy, not COMEX GC.
        pressure_confidence = getattr(perpetual_consensus, "confidence", "LOW")
        micro_weight = (
            .50 if pressure_confidence == "HIGH"
            else .35 if pressure_confidence == "MODERATE"
            else .10)
    values = {
        "Statistical forecast": statistical,
        "Short-term technical": float(technical["score"]),
        "Expected price move": expected,
        "Slow macro background": float(np.clip(macro_score / 1.5, -1, 1)),
        "Perpetual pressure proxy": microstructure,
        "Institutional liquidity proxy": institutional_liquidity_score(institutional),
    }
    weights = {
        "Statistical forecast": .25,
        "Short-term technical": .15,
        "Expected price move": .10,
        "Slow macro background": .05,
        "Perpetual pressure proxy": micro_weight,
        "Institutional liquidity proxy": .05,
    }
    denominator = sum(weights.values())
    score = float(sum(values[name] * weights[name] for name in values) / denominator)
    lean = "BUY LEAN" if score >= 0 else "SELL LEAN"
    confidence = "HIGH" if abs(score) >= .55 else (
        "MODERATE" if abs(score) >= .30 else "LOW")
    if event_lock:
        confidence = "EVENT RISK"
    aligned = sum(np.sign(value) == np.sign(score) for value in values.values()
                  if abs(value) >= .10)
    active = sum(abs(value) >= .10 for value in values.values())
    return {
        "lean": lean, "score": score, "confidence": confidence,
        "aligned": aligned, "active": active,
        "components": values, "weights": weights,
        "pressure_indication": pressure_indication,
        "pressure_priority": pressure_indication in {"BUY", "SELL"},
        "actionable": False,
    }


def non_overlapping_evaluation(result, threshold, cost_bps):
    sample = result.predictions.iloc[::INTRADAY_HORIZON_BARS].copy()
    minimum = 2 * cost_bps / 10_000
    sample["position"] = 0
    sample.loc[
        (sample.probability_up >= threshold) &
        (sample["median"] > minimum), "position"] = 1
    sample.loc[
        (sample.probability_up <= 1 - threshold) &
        (sample["median"] < -minimum), "position"] = -1
    traded = sample[sample.position != 0].copy()
    if traded.empty:
        return {"Observations": float(len(sample)), "Trades": 0.0,
                "Win rate": np.nan, "Profit factor": np.nan,
                "Net return": 0.0, "Max drawdown": 0.0}
    traded["net_return"] = (
        traded.position * traded.actual_return - cost_bps / 10_000)
    equity = (1 + traded.net_return).cumprod()
    gains = float(traded.loc[traded.net_return > 0, "net_return"].sum())
    losses = float(-traded.loc[traded.net_return < 0, "net_return"].sum())
    return {"Observations": float(len(sample)), "Trades": float(len(traded)),
            "Win rate": float((traded.net_return > 0).mean()),
            "Profit factor": gains / losses if losses > 0 else np.inf,
            "Net return": float(equity.iloc[-1] - 1),
            "Max drawdown": float((equity / equity.cummax() - 1).min())}


def decide_v90(result, macro, elliott, threshold, cost_bps, major_event=False,
               technical=None, perpetual_consensus=None):
    regime, _, evidence = classify_macro_regime(macro, result.as_of)
    evaluation = non_overlapping_evaluation(result, threshold, cost_bps)
    minimum = 2 * cost_bps / 10_000
    probability = float(elliott.probability_up)
    pressure_side = getattr(perpetual_consensus, "order_flow_decision", "WAIT")
    pressure_confidence = getattr(perpetual_consensus, "confidence", "LOW")
    pressure_threshold = max(.55, threshold - .03)
    buy_threshold = (
        pressure_threshold if pressure_side == "BUY" and pressure_confidence == "HIGH"
        else threshold)
    sell_threshold = (
        1 - pressure_threshold if pressure_side == "SELL" and pressure_confidence == "HIGH"
        else 1 - threshold)
    candidate = (
        "BUY" if probability >= buy_threshold and result.median_return > minimum
        else "SELL" if probability <= sell_threshold and result.median_return < -minimum
        else "NO EDGE")
    reliability_threshold = pressure_threshold if (
        candidate == pressure_side and pressure_confidence == "HIGH") else threshold
    reasons = balanced_release_reasons(result)
    reliability = selective_reliability(
        result.predictions, probability, reliability_threshold)
    result.selective_reliability = reliability
    if candidate != "NO EDGE" and not reliability["qualified"]:
        reasons.append(
            "current side lacks 30 out-of-sample signals with a Wilson "
            "accuracy lower bound of at least 50%")
    if getattr(result, "model_disagreement", 1.0) > .15:
        reasons.append("ensemble members disagree too strongly")
    champion_auc = result.baseline_metrics.get("Champion ROC-AUC")
    champion_brier = result.baseline_metrics.get("Champion Brier score")
    if champion_auc is not None and result.metrics.get("ROC-AUC", 0) <= champion_auc:
        reasons.append("Version 9.0 did not beat Version 8.2.5 ROC-AUC")
    if champion_brier is not None and result.metrics.get("Brier score", 1) >= champion_brier:
        reasons.append("Version 9.0 did not beat Version 8.2.5 calibration")
    if result.metrics.get("Calibration improvement", 0) < 0:
        reasons.append("fold-local calibration did not improve Brier score")
    if evaluation["Trades"] < 15:
        reasons.append("fewer than 15 non-overlapping cost-aware trades")
    if evaluation["Net return"] <= 0:
        reasons.append("non-overlapping cost-aware return is not positive")
    if np.isfinite(evaluation["Profit factor"]) and evaluation["Profit factor"] < 1.15:
        reasons.append("cost-aware profit factor is below 1.15")
    if candidate == "BUY" and regime == "BEARISH":
        reasons.append("BUY candidate conflicts with bearish macro regime")
    if candidate == "SELL" and regime == "BULLISH":
        reasons.append("SELL candidate conflicts with bullish macro regime")
    if technical is not None:
        if candidate == "BUY" and technical["trend"] == "DOWNTREND":
            reasons.append("BUY candidate conflicts with the short-term downtrend")
        if candidate == "SELL" and technical["trend"] == "UPTREND":
            reasons.append("SELL candidate conflicts with the short-term uptrend")
    if (perpetual_consensus is not None and
            perpetual_consensus.confidence == "HIGH" and candidate != "NO EDGE"):
        proxy_side = getattr(perpetual_consensus, "order_flow_decision", None)
        if proxy_side == "WAIT":
            proxy_side = None
        if proxy_side is not None and proxy_side != candidate:
            reasons.append("three-venue pressure conflicts with the candidate")
    if (elliott.qualified and candidate != "NO EDGE" and
            elliott.current_bias not in {candidate, "NEUTRAL"}):
        reasons.append("qualified Elliott structure contradicts the candidate")
    if evidence and evidence[0].startswith("fewer"):
        reasons.append(evidence[0])
    shock = getattr(result, "shock_audit", {"active": False})
    if shock.get("active"):
        reasons.append(
            "abnormal price shock detected; pre-shock relationships are in cooldown")
        action = "BLOCKED"
    elif major_event:
        reasons.append("major US event flagged within the next hour")
        action = "BLOCKED"
    elif candidate == "NO EDGE" or reasons:
        action = "NO EDGE"
    else:
        action = candidate
    return V90Decision(
        action, candidate, regime, float(result.median_return), minimum,
        list(dict.fromkeys(reasons)), evaluation)
