import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from gold_model import HORIZONS, download_market_data, fit_and_backtest, price_interval


st.set_page_config(page_title="Gold Forecast Lab", page_icon="🟡", layout="wide")
st.title("XAU/USD Multi-Horizon Forecast Lab")
st.caption("Leakage-aware research forecasts—not financial advice or an execution system.")

with st.sidebar:
    st.header("Model settings")
    horizon_name = st.selectbox("Forecast horizon", list(HORIZONS))
    start = st.text_input("History start", "2007-01-01")
    threshold = st.slider("Signal probability threshold", 0.51, 0.75, 0.58, 0.01)
    cost_bps = st.number_input("Round-trip cost (basis points)", 0, 200, 10, 5)
    splits = st.slider("Walk-forward test folds", 3, 10, 6)
    run = st.button("Run analysis", type="primary", use_container_width=True)


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def get_data(start_date: str):
    return download_market_data(start_date)


@st.cache_resource(show_spinner=False)
def run_model(prices, horizon, folds, cost, probability_threshold):
    return fit_and_backtest(prices, horizon, folds, cost, probability_threshold)


if not run:
    st.info("Choose settings and click **Run analysis**. Defaults are a sensible first pass.")
    st.stop()

try:
    with st.spinner("Downloading data and running walk-forward models…"):
        prices = get_data(start)
        result = run_model(prices, HORIZONS[horizon_name], splits, cost_bps, threshold)
except Exception as exc:
    st.error(f"Analysis could not run: {exc}")
    st.stop()

low, median, high = price_interval(result)
c1, c2, c3, c4 = st.columns(4)
c1.metric("Research signal", result.signal)
c2.metric("Probability up", f"{result.probability_up:.1%}")
c3.metric("Median target", f"${median:,.2f}", f"{result.median_return:.1%}")
c4.metric("80% price range", f"${low:,.0f} – ${high:,.0f}")
st.caption(f"As of {result.as_of:%Y-%m-%d} | Gold proxy close ${result.spot:,.2f} | "
           f"Forecast horizon {result.horizon} trading days")

st.subheader("Out-of-sample validation")
metric_frame = pd.DataFrame({"Metric": result.metrics.keys(), "Value": result.metrics.values()})
formats = {
    "ROC-AUC": "{:.3f}", "Brier score": "{:.3f}", "Direction accuracy": "{:.1%}",
    "Always-up accuracy": "{:.1%}", "80% interval coverage": "{:.1%}",
    "Strategy CAGR": "{:.1%}", "Strategy max drawdown": "{:.1%}", "Trades": "{:.0f}",
}
metric_frame["Result"] = [formats[k].format(v) for k, v in result.metrics.items()]
st.dataframe(metric_frame[["Metric", "Result"]], hide_index=True, use_container_width=True)

left, right = st.columns(2)
with left:
    equity = result.predictions[["strategy_equity", "gold_equity"]].dropna()
    fig = px.line(equity, labels={"value": "Growth of $1", "index": "Date", "variable": "Series"},
                  title="Non-overlapping walk-forward equity")
    st.plotly_chart(fig, use_container_width=True)
with right:
    calibration = result.predictions.copy()
    calibration["Probability bucket"] = pd.cut(calibration.probability_up,
        bins=[0, .4, .5, .6, 1], include_lowest=True)
    cal = calibration.groupby("Probability bucket", observed=True).agg(
        predicted=("probability_up", "mean"), observed=("actual_up", "mean"), count=("actual_up", "size"))
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=cal.predicted, y=cal.observed, mode="markers+lines",
                             marker=dict(size=(cal["count"] ** .5) * 2), name="Model"))
    fig.add_trace(go.Scatter(x=[0, 1], y=[0, 1], mode="lines", name="Perfect calibration",
                             line=dict(dash="dash")))
    fig.update_layout(title="Probability calibration", xaxis_title="Predicted", yaxis_title="Observed")
    st.plotly_chart(fig, use_container_width=True)

st.subheader("Most influential features")
importance = (
    result.importance.sort_values()
    .rename("importance")
    .reset_index()
    .rename(columns={"index": "feature"})
)
st.plotly_chart(px.bar(importance, x="importance", y="feature", orientation="h"),
                use_container_width=True)

with st.expander("Method and limitations"):
    st.markdown(f"""
    - Uses `{len(result.features_used)}` technical and cross-market features from the available series.
    - Walk-forward splits include a `{result.horizon}`-day gap between training and test observations.
    - Quantile regressors estimate the 10th, 50th, and 90th percentiles of future return.
    - Strategy results use non-overlapping decisions and {cost_bps} bps estimated round-trip cost.
    - Results exclude taxes, financing, spreads that vary through time, and live execution latency.
    - Regime changes can make historical relationships fail abruptly. Paper-test before any real use.
    """)

csv = result.predictions.to_csv().encode("utf-8")
st.download_button("Download walk-forward predictions (CSV)", csv,
                   f"gold_predictions_{result.horizon}d.csv", "text/csv")

