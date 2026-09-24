import numpy as np
import pandas as pd

from forecast_ledger_v825 import ForecastLedger


class ForecastLedgerV83(ForecastLedger):
    def __init__(self, path="forecast_ledger_v83.sqlite"):
        super().__init__(path)

    def live_performance(self, cost_bps: float = 10,
                         min_forecasts: int = 30) -> dict:
        """Score genuinely recorded forecasts after their expiry.

        A greedy chronological sample removes overlapping one-hour forecasts
        from trading-return metrics. Calibration metrics may use every settled
        probability forecast because they do not pretend to be independent
        trades.
        """
        history = self.frame()
        settled = history[history.status.eq("SETTLED")].copy()
        if settled.empty:
            return {"status": "INSUFFICIENT", "settled": 0,
                    "scored_outlooks": 0, "executed": 0,
                    "direction_accuracy": np.nan, "decision_accuracy": np.nan,
                    "brier_score": np.nan, "interval_coverage": np.nan,
                    "median_absolute_error": np.nan,
                    "non_overlapping_trades": 0, "net_return": 0.0,
                    "profit_factor": np.nan}
        actual_up = (settled.actual_return > 0).astype(float)
        probability = settled.adjusted_probability_up.clip(1e-6, 1 - 1e-6)
        brier = float(np.mean((probability - actual_up) ** 2))
        outlook = settled[settled.outlook_result.isin(["CORRECT", "INCORRECT"])]
        executed = settled[settled.direction_result.isin(["CORRECT", "INCORRECT"])]
        coverage_rows = settled.dropna(subset=["actual_price", "lower_target", "upper_target"])
        coverage = float(((coverage_rows.actual_price >= coverage_rows.lower_target) &
                          (coverage_rows.actual_price <= coverage_rows.upper_target)).mean()
                         ) if len(coverage_rows) else np.nan
        error = settled.target_error.abs().dropna()
        chronological = executed.sort_values("data_timestamp_utc")
        selected = []
        next_allowed = None
        for row in chronological.itertuples():
            if next_allowed is None or row.data_timestamp_utc >= next_allowed:
                selected.append(row)
                next_allowed = row.forecast_timestamp_utc
        returns = []
        for row in selected:
            side = 1 if row.decision == "BUY" else -1
            returns.append(side * row.actual_return - cost_bps / 10_000)
        returns = pd.Series(returns, dtype=float)
        gains = float(returns[returns > 0].sum())
        losses = float(-returns[returns < 0].sum())
        profit_factor = gains / losses if losses > 0 else (
            np.inf if gains > 0 else np.nan)
        enough = len(outlook) >= min_forecasts
        direction_accuracy = float(outlook.outlook_result.eq("CORRECT").mean()) if len(outlook) else np.nan
        decision_accuracy = float(executed.direction_result.eq("CORRECT").mean()) if len(executed) else np.nan
        passed = bool(enough and direction_accuracy >= .55 and brier < .25 and
                      np.isfinite(coverage) and .70 <= coverage <= .90)
        return {
            "status": "PASS" if passed else "FAIL" if enough else "INSUFFICIENT",
            "settled": int(len(settled)), "scored_outlooks": int(len(outlook)),
            "executed": int(len(executed)),
            "direction_accuracy": direction_accuracy,
            "decision_accuracy": decision_accuracy, "brier_score": brier,
            "interval_coverage": coverage,
            "median_absolute_error": float(error.median()) if len(error) else np.nan,
            "non_overlapping_trades": int(len(returns)),
            "net_return": float((1 + returns).prod() - 1) if len(returns) else 0.0,
            "profit_factor": profit_factor,
        }

    def calibration_table(self) -> pd.DataFrame:
        settled = self.frame()
        settled = settled[settled.status.eq("SETTLED")].copy()
        columns = ["Probability band", "Forecasts", "Mean probability",
                   "Observed up frequency", "Calibration gap"]
        if settled.empty:
            return pd.DataFrame(columns=columns)
        settled["actual_up"] = (settled.actual_return > 0).astype(float)
        settled["band"] = pd.cut(
            settled.adjusted_probability_up, [0, .4, .5, .6, 1],
            labels=["0–40%", "40–50%", "50–60%", "60–100%"],
            include_lowest=True)
        rows = []
        for band, group in settled.groupby("band", observed=True):
            mean_probability = float(group.adjusted_probability_up.mean())
            observed = float(group.actual_up.mean())
            rows.append({"Probability band": str(band), "Forecasts": len(group),
                         "Mean probability": mean_probability,
                         "Observed up frequency": observed,
                         "Calibration gap": observed - mean_probability})
        return pd.DataFrame(rows, columns=columns)
