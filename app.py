import os

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from gold_model import (
    HORIZON_LABEL, INTERVAL, SYMBOL, download_market_data,
    fit_and_backtest, price_interval,
)

st.set_page_config(page_title="XAU/USD 4-Hour Forecast", page_icon="🟡", layout="wide")
st.title("XAU/USD Four-Hour Forecast Lab")
st.caption("Twelve Data 15-minute spot candles · probabilistic research, not financial advice")

with st.sidebar:
    st.header("Model settings")
    st.text_input("Instrument", SYMBOL, disabled=True)
    st.text_input("Forecast horizon", HORIZON_LABEL, disabled=True)
    threshold = st.slider("Signal probability threshold", 0.55, 0.80, 0.65, 0.01)
    cost_bps = st.number_input("Estimated round-trip cost (basis points)", 0, 200, 10, 5)
    splits = st.slider("Walk-forward test folds", 3, 8, 5)
    st.header("Paper-trading risk")
    account_balance = st.number_input("Paper account balance (USD)", 100.0, 10_000_000.0, 10_000.0, 100.0)
    risk_pct = st.number_input("Risk per trade (%)", 0.05, 1.00, 0.25, 0.05)
    ounces_per_lot = st.number_input("Broker ounces per lot", 1.0, 1000.0, 100.0, 1.0)
    stop_atr = st.number_input("Stop distance (ATR multiple)", 0.5, 5.0, 1.5, 0.1)
    losses_today = st.number_input("Losing trades today", 0, 20, 0, 1)
    major_event = st.checkbox("Major US event within next 4 hours")
    run = st.button("Run four-hour forecast", type="primary", width="stretch")


def get_api_key() -> str:
    try:
        return str(st.secrets["TWELVE_DATA_API_KEY"])
    except (KeyError, FileNotFoundError):
        return os.getenv("TWELVE_DATA_API_KEY", "")


@st.cache_data(ttl=15 * 60, show_spinner=False)
def get_data(api_key: str):
    return download_market_data(api_key)


if not run:
    st.info("Add your Twelve Data API key to Streamlit secrets, then run the forecast.")
    st.stop()
api_key = get_api_key()
if not api_key:
    st.error("Missing TWELVE_DATA_API_KEY. Add it to .streamlit/secrets.toml locally or App settings → Secrets online.")
    st.code('TWELVE_DATA_API_KEY = "your-key-here"', language="toml")
    st.stop()

try:
    with st.spinner("Downloading XAU/USD candles and running walk-forward models…"):
        prices = get_data(api_key)
        result = fit_and_backtest(prices, splits, cost_bps, threshold)
except Exception as exc:
    st.error(f"Analysis could not run: {exc}")
    st.stop()

low, median, high = price_interval(result)
forecast_time = result.as_of + pd.Timedelta(hours=4)
now_utc = pd.Timestamp.now(tz="UTC")
data_age_minutes = max(0.0, (now_utc - result.as_of).total_seconds() / 60)
stale = data_age_minutes > 45
previous_close = prices.close.shift(1)
true_range = pd.concat([
    prices.high - prices.low,
    (prices.high - previous_close).abs(),
    (prices.low - previous_close).abs(),
], axis=1).max(axis=1)
atr = float(true_range.rolling(14).mean().iloc[-1])

gate_reasons = []
if stale:
    gate_reasons.append(f"latest candle is {data_age_minutes:.0f} minutes old")
if major_event:
    gate_reasons.append("major US event flagged within four hours")
if losses_today >= 2:
    gate_reasons.append("daily limit of two losing trades reached")
if result.metrics["ROC-AUC"] < 0.55:
    gate_reasons.append("walk-forward ROC-AUC is below 0.55")
if result.metrics["Direction accuracy"] <= result.metrics["Always-up accuracy"]:
    gate_reasons.append("direction accuracy does not beat the always-up baseline")
if result.signal == "WAIT":
    gate_reasons.append("model signal is WAIT")

decision = result.signal if not gate_reasons else "WAIT"
risk_amount = account_balance * risk_pct / 100
stop_distance = stop_atr * atr
ounces = risk_amount / stop_distance if stop_distance > 0 else 0.0
lots = ounces / ounces_per_lot if ounces_per_lot > 0 else 0.0
if decision == "BUY":
    stop_price = result.spot - stop_distance
    target_1 = median if median > result.spot else high
    target_2 = high
elif decision == "SELL":
    stop_price = result.spot + stop_distance
    target_1 = median if median < result.spot else low
    target_2 = low
else:
    stop_price = target_1 = target_2 = float("nan")

st.subheader("Latest pending four-hour forecast")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Paper-trade decision", decision)
c2.metric("Probability up", f"{result.probability_up:.1%}")
c3.metric("Median target", f"USD {median:,.2f}", f"{result.median_return:.2%}")
c4.metric("80% target range", f"USD {low:,.2f} – {high:,.2f}")
st.caption(
    f"Latest {INTERVAL} candle: {result.as_of:%Y-%m-%d %H:%M UTC} | "
    f"XAU/USD close: USD {result.spot:,.3f} | "
    f"Forecast time: {forecast_time:%Y-%m-%d %H:%M UTC} | "
    f"Candles loaded: {result.observations:,}")

if gate_reasons:
    st.error("NO PAPER TRADE: " + "; ".join(gate_reasons) + ".")
else:
    st.success(
        f"PAPER {decision} | Entry USD {result.spot:,.3f} | "
        f"Stop USD {stop_price:,.3f} | Target 1 USD {target_1:,.3f} | "
        f"Target 2 USD {target_2:,.3f} | Risk USD {risk_amount:,.2f} | "
        f"Size {ounces:,.2f} oz ({lots:,.3f} lots, if contract size is correct)"
    )

latest = pd.DataFrame([{
    "Instrument": SYMBOL,
    "Data timestamp UTC": result.as_of.strftime("%Y-%m-%d %H:%M"),
    "Forecast timestamp UTC": forecast_time.strftime("%Y-%m-%d %H:%M"),
    "Starting price": result.spot,
    "Raw model signal": result.signal,
    "Paper-trade decision": decision,
    "Probability up": result.probability_up,
    "Median target": median,
    "80% lower target": low,
    "80% upper target": high,
    "Data age minutes": data_age_minutes,
    "ATR 14": atr,
    "Stop": stop_price,
    "Target 1": target_1,
    "Target 2": target_2,
    "Risk amount": risk_amount,
    "Position ounces": ounces if decision != "WAIT" else 0.0,
    "Estimated lots": lots if decision != "WAIT" else 0.0,
    "Gate reasons": "; ".join(gate_reasons),
    "Outcome": "PENDING",
}])
st.dataframe(latest, hide_index=True, width="stretch")
st.download_button(
    "Download latest four-hour forecast (CSV)",
    latest.to_csv(index=False).encode("utf-8"),
    f"xauusd_4h_forecast_{forecast_time:%Y%m%d_%H%M}.csv", "text/csv")
st.warning(
    "Paper trading only. Verify your broker's contract size independently. "
    "A probability and target range are uncertain estimates, not a guarantee or executable quote.")

st.subheader("Walk-forward validation")
metric_frame = pd.DataFrame({"Metric": result.metrics.keys(), "Value": result.metrics.values()})
formats = {
    "ROC-AUC": "{:.3f}", "Brier score": "{:.3f}", "Direction accuracy": "{:.1%}",
    "Always-up accuracy": "{:.1%}", "80% interval coverage": "{:.1%}",
    "Strategy total return": "{:.1%}", "Strategy max drawdown": "{:.1%}",
    "Signal changes": "{:.0f}",
}
metric_frame["Result"] = [formats[k].format(v) for k, v in result.metrics.items()]
st.dataframe(metric_frame[["Metric", "Result"]], hide_index=True, width="stretch")

left, right = st.columns(2)
with left:
    equity = result.predictions[["strategy_equity", "gold_equity"]].dropna()
    fig = px.line(
        equity,
        labels={"value": "Growth of USD 1", "index": "UTC time", "variable": "Series"},
        title="Non-overlapping four-hour walk-forward equity")
    st.plotly_chart(fig, width="stretch")
with right:
    calibration = result.predictions.copy()
    calibration["Probability bucket"] = pd.cut(
        calibration.probability_up, bins=[0, .4, .5, .6, 1], include_lowest=True)
    cal = calibration.groupby("Probability bucket", observed=True).agg(
        predicted=("probability_up", "mean"), observed=("actual_up", "mean"),
        count=("actual_up", "size"))
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=cal.predicted, y=cal.observed, mode="markers+lines", name="Model"))
    fig.add_trace(go.Scatter(
        x=[0, 1], y=[0, 1], mode="lines", name="Perfect calibration",
        line=dict(dash="dash")))
    fig.update_layout(
        title="Probability calibration",
        xaxis_title="Predicted", yaxis_title="Observed")
    st.plotly_chart(fig, width="stretch")

st.subheader("Most influential features")
importance = (
    result.importance.sort_values()
    .rename_axis("feature")
    .reset_index(name="importance")
)
st.plotly_chart(
    px.bar(importance, x="importance", y="feature", orientation="h"),
    width="stretch")

with st.expander("Method and limitations"):
    st.markdown(f"""
    - Uses `{len(result.features_used)}` price, momentum, volatility, candle and time-of-day features.
    - Predicts the return over the next {HORIZON_LABEL.lower()}.
    - Walk-forward splits contain a 16-bar gap to reduce future-data leakage.
    - Quantile models estimate the 10th, 50th and 90th percentiles of future return.
    - Validation uses non-overlapping four-hour decisions and {cost_bps} bps estimated cost.
    - Twelve Data and broker prices can differ. Results exclude financing and variable slippage.
    - Short intraday histories and regime changes can make apparent relationships disappear.
    """)

history_csv = result.predictions.to_csv().encode("utf-8")
st.download_button(
    "Download historical walk-forward predictions (CSV)", history_csv,
    "xauusd_4h_walk_forward_predictions.csv", "text/csv")
