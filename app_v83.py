import os
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from cme_microstructure_v830 import audit_microstructure, collect_cme_gc
from forecast_ledger_v83 import ForecastLedgerV83
from gold_model import price_interval, technical_snapshot
from gold_model_v82 import (
    INTRADAY_HORIZON_LABEL, INTRADAY_INTERVAL, apply_elliott_overlay,
    download_intraday_bundle, fit_intraday_system, validate_market_data,
)
from gold_model_v83 import MODEL_VERSION_V83, decide_v83, fit_v83_system
from institutional_features_v830 import catalyst_playbook
from macro_econometrics_v825 import combine_macro_sources, download_fred_macro, parse_slow_factor_csv
from official_event_calendar_v830 import (
    download_official_events, event_risk_notice, format_events_gmt,
    official_event_risk)

st.set_page_config(page_title="Gold Version 8.3", page_icon="🟡", layout="wide")
st.title("Gold Version 8.3.0")
st.caption("Shock-aware calibrated regime-ensemble · one-hour forecast · market-only research")

with st.sidebar:
    st.header("Version 8.3 settings")
    st.text_input("Candle interval", INTRADAY_INTERVAL, disabled=True)
    st.text_input("Forecast horizon", INTRADAY_HORIZON_LABEL, disabled=True)
    threshold = st.slider("Timing probability threshold", .55, .75, .60, .01)
    cost_bps = st.number_input("Estimated total cost (basis points)", 0, 100, 10, 5)
    splits = st.slider("Walk-forward folds", 4, 8, 5)
    major_event = st.checkbox(
        "Investing.com 3-star USD event within next hour",
        help="Check this after reviewing the embedded calendar. It blocks forecast release.")
    use_cme = st.checkbox(
        "Use licensed CME GC live feed",
        help="Requires CME_ACCESS_TOKEN. Uses real GC trades and one-deep top of book.")
    slow_file = st.file_uploader(
        "Optional official positioning CSV", type=["csv"],
        help=("Release-timestamped CFTC managed-money, central-bank demand or "
              "geopolitical-risk data. Future-dated observations are never used."))
    run = st.button("Run Version 8.3", type="primary", width="stretch")

with st.expander("Investing.com three-star economic calendar", expanded=False):
    calendar_url = (
        "https://sslecal2.investing.com?"
        "columns=exc_currency,exc_importance,exc_actual,exc_forecast,exc_previous"
        "&importance=3&features=datepicker,timezone,filters"
        "&calType=week&lang=1"
    )
    components.iframe(calendar_url, height=500, scrolling=True)
    st.caption(
        "Real-time economic calendar provided by Investing.com. "
        "Confirm the widget timezone and check the sidebar event box when a "
        "three-star USD event is within the next hour."
    )
    st.link_button(
        "Open full Investing.com calendar",
        "https://www.investing.com/economic-calendar/")

@st.cache_data(ttl=1800, show_spinner=False)
def official_calendar():
    return download_official_events()

official_events, official_audit = official_calendar()
automatic_event_lock, nearby_official_events = official_event_risk(
    official_events)
if automatic_event_lock:
    st.error(
        "Official calendar lockout is active: a high-impact event is within "
        "60 minutes before or 30 minutes after release.")
    st.dataframe(
        format_events_gmt(nearby_official_events),
        hide_index=True, width="stretch")
elif official_audit.Status.astype(str).str.startswith("unavailable").any():
    st.warning(
        "One or more official calendars are unavailable. Review Investing.com "
        "and use the manual three-star event checkbox.")

if not run:
    st.info("Run after a completed 15-minute candle. Version 8.2.5 remains unchanged on port 8502.")
    st.stop()

try:
    key = str(st.secrets["TWELVE_DATA_API_KEY"])
except (KeyError, FileNotFoundError):
    key = os.getenv("TWELVE_DATA_API_KEY", "")
if not key:
    st.error("Missing TWELVE_DATA_API_KEY in Streamlit secrets.")
    st.stop()

try:
    with st.spinner("Running Version 8.3 calibrated walk-forward research…"):
        gold, confirmations, source_status = download_intraday_bundle(key)
        validate_market_data(gold, confirmations)
        result = fit_v83_system(gold, confirmations, splits, cost_bps, threshold)
        fred, macro_audit = download_fred_macro()
        slow = parse_slow_factor_csv(slow_file) if slow_file else None
        macro = combine_macro_sources(fred, slow)
        elliott = apply_elliott_overlay(result.probability_up, result.median_return,
                                        threshold, cost_bps, gold)
        cme_frame = pd.DataFrame()
        cme_error = ""
        if use_cme:
            try:
                cme_token = str(st.secrets["CME_ACCESS_TOKEN"])
            except (KeyError, FileNotFoundError):
                cme_token = os.getenv("CME_ACCESS_TOKEN", "")
            try:
                cme_frame = collect_cme_gc(cme_token, seconds=8)
            except Exception as cme_exc:
                cme_error = str(cme_exc)
        cme_audit = audit_microstructure(cme_frame)
        decision = decide_v83(
            result, macro, elliott, threshold, cost_bps,
            major_event=(major_event or automatic_event_lock))
        if (use_cme and cme_audit.status == "LIVE" and
                cme_audit.risk == "HIGH"):
            decision.action = "BLOCKED"
            decision.reasons.append(
                "live COMEX liquidity risk is high; spread/depth conditions are unsafe")
except Exception as exc:
    st.error(f"Version 8.3 could not run: {exc}")
    st.stop()

notice_state, notice_events = event_risk_notice(official_events)
if major_event and notice_state == "CLEAR":
    notice_state = "ELEVATED"
if notice_state == "LOCKOUT":
    st.error(
        "SPIKE RISK — EVENT LOCKOUT. A high-impact official release is "
        "imminent or has just occurred. Direction is unknown; expect possible "
        "spread widening, slippage and rapid price movement.")
    st.dataframe(
        format_events_gmt(notice_events), hide_index=True, width="stretch")
elif notice_state == "ELEVATED":
    st.warning(
        "ELEVATED SPIKE RISK — PREPARE. A high-impact event is approaching "
        "within four hours, or you manually flagged a three-star "
        "Investing.com event. This is a volatility warning, not a direction signal.")
    if not notice_events.empty:
        st.dataframe(
            format_events_gmt(notice_events), hide_index=True, width="stretch")
    if major_event and notice_events.empty:
        st.info(
            "Manual Investing.com flag is active. Confirm the event name, "
            "three-star importance and GMT time in the embedded calendar.")
else:
    st.success(
        "No scheduled high-impact BLS, BEA or Federal Reserve event was found "
        "in the next four hours. Unscheduled breaking-news spikes remain possible.")

st.subheader("COMEX institutional microstructure audit")
if not use_cme:
    st.info(
        "CME monitoring is off. Enable the licensed CME GC feed in the sidebar. "
        "No order-book inference is being fabricated from spot candles.")
elif cme_audit.status != "LIVE":
    st.warning(
        "CME feed is unavailable or stale. Its direction has zero weight. " +
        (f"Connection detail: {cme_error}" if cme_error else ""))
else:
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Feed", cme_audit.status)
    m2.metric("GC contract", cme_audit.symbol or "N/A")
    m3.metric("Spread", f"{cme_audit.spread_ticks:.1f} ticks")
    m4.metric("Top-book imbalance", f"{cme_audit.top_imbalance:+.1%}")
    m5.metric("Pressure", cme_audit.directional_bias)
    if cme_audit.risk == "HIGH":
        st.error("COMEX LIQUIDITY WARNING — execution is blocked while the live spread is abnormal.")
    elif cme_audit.risk == "ELEVATED":
        st.warning("COMEX liquidity is strongly one-sided. Treat a stop-run or rejection as possible.")
    else:
        st.success("COMEX top-of-book conditions are currently normal.")
st.caption(
    "CME WebSocket data is trades plus conflated one-deep top of book—not Level 2. "
    "Microstructure direction remains audit-only until historical CME data passes "
    "purged walk-forward accuracy, calibration and cost gates. Full depth/footprint "
    "requires a separately entitled CME MDP or Google Pub/Sub feed.")

st.subheader("Institutional liquidity and accumulation audit")
institutional = result.institutional_audit
i1, i2, i3, i4, i5 = st.columns(5)
i1.metric("Range state", institutional.accumulation_state)
i2.metric("Accumulation score", (
    f"{institutional.compression_percentile:.0%}"
    if pd.notna(institutional.compression_percentile) else "N/A"))
i3.metric("Nearest liquidity proxy", institutional.nearest_liquidity)
i4.metric("Distance", (
    f"{institutional.liquidity_distance_pct:.2%}"
    if pd.notna(institutional.liquidity_distance_pct) else "N/A"))
i5.metric("Volume profile", institutional.volume_status)
if institutional.volume_status == "AVAILABLE":
    st.caption(
        f"POC USD {institutional.poc:,.2f} | "
        f"Value area USD {institutional.value_area_low:,.2f}–"
        f"{institutional.value_area_high:,.2f}")
else:
    st.info(
        "POC/VAH/VAL are inactive because the current spot source does not "
        "supply verified traded volume. No synthetic volume was created.")
st.caption(" · ".join(institutional.reasons))

st.subheader("Historical catalyst playbook")
playbook = catalyst_playbook(gold, official_events)
if playbook.empty or not playbook.Qualified.any():
    st.info(
        "No event type has at least 20 aligned historical releases in the "
        "loaded official calendar. Event direction remains UNKNOWN; calendar "
        "timing still activates the volatility lockout.")
else:
    st.dataframe(playbook, hide_index=True, width="stretch")

lower, median, upper = price_interval(result)
forecast_time = result.as_of + pd.Timedelta(hours=1)
st.subheader("Version 8.3 decision")
c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Macro regime", decision.macro_regime)
c2.metric("Timing candidate", decision.candidate)
c3.metric("Risk-controlled action", decision.action)
c4.metric("Probability up", f"{elliott.probability_up:.1%}")
c5.metric("Predicted price in 1 hour", f"USD {median:,.2f}")
c6.metric("80% range", f"{lower:,.2f}–{upper:,.2f}")
st.caption(f"Data {result.as_of:%Y-%m-%d %H:%M UTC} | Expiry {forecast_time:%Y-%m-%d %H:%M UTC} | Spot USD {result.spot:,.2f}")
if decision.reasons:
    st.warning("Action withheld: " + "; ".join(decision.reasons) + ".")

st.subheader("Sudden-movement audit")
shock = result.shock_audit
s1, s2, s3, s4, s5 = st.columns(5)
s1.metric("Shock regime", "ACTIVE" if shock["active"] else "NORMAL")
s2.metric("Robust jump score", (
    f'{shock["z_score"]:.1f}σ' if pd.notna(shock["z_score"]) else "N/A"))
s3.metric("Range expansion", (
    f'{shock["range_ratio"]:.1f}×' if pd.notna(shock["range_ratio"]) else "N/A"))
s4.metric("Cross-asset shocks", shock["cross_asset_shocks"])
s5.metric("Bars since shock", (
    shock["bars_since_shock"] if shock["bars_since_shock"] is not None else "None"))
if shock["active"]:
    st.error("Forecast release is blocked during the four-candle post-shock cooldown. Run again after volatility normalizes.")
else:
    st.caption("Causal robust-volatility and range detector; thresholds use only candles completed before the candle being tested.")

st.subheader("Technical-rejection audit")
rejection = result.rejection_audit
r1, r2, r3, r4, r5 = st.columns(5)
r1.metric("Current rejection", rejection["current_bias"])
r2.metric("Holdout cases", rejection["observations"])
r3.metric("Holdout accuracy", (
    f'{rejection["accuracy"]:.1%}'
    if pd.notna(rejection["accuracy"]) else "N/A"))
r4.metric("Profit factor", (
    f'{rejection["profit_factor"]:.2f}'
    if pd.notna(rejection["profit_factor"]) and
       rejection["profit_factor"] != float("inf") else
    "∞" if rejection["profit_factor"] == float("inf") else "N/A"))
r5.metric("Reliability gate", (
    "PASS" if rejection["qualified"] else "FAIL"))
st.caption(
    f'90% Wilson lower bound: '
    f'{rejection["lower_bound"]:.1%}' if
    pd.notna(rejection["lower_bound"]) else
    "90% Wilson lower bound: N/A")
if not rejection["qualified"]:
    st.info("Technical rejection has zero model weight until at least 30 holdout cases pass accuracy, confidence and cost-aware profit-factor gates.")
elif result.rejection_adjustment:
    st.success(
        f'Qualified rejection adjusted probability by '
        f'{result.rejection_adjustment:+.1%}.')

st.subheader("Elliott Wave audit")
e1, e2, e3, e4, e5 = st.columns(5)
e1.metric("Current bias", elliott.current_bias)
e2.metric("Current structure", elliott.current_structure)
e3.metric("Probability adjustment", f"{elliott.adjustment:+.1%}")
e4.metric("Holdout accuracy", f"{elliott.accuracy:.1%}")
e5.metric("Reliability gate", "PASS" if elliott.qualified else "FAIL")
st.caption(
    f"Causal confirmed-pivot evidence | Holdout observations: {elliott.observations:,} | "
    f"90% Wilson lower bound: {elliott.lower_bound:.1%}"
)
if elliott.reasons:
    st.info("Elliott evidence not applied: " + "; ".join(elliott.reasons) + ".")
elif elliott.adjustment:
    st.success(f"Qualified Elliott evidence adjusted probability by {elliott.adjustment:+.1%}.")
else:
    st.info("Qualified Elliott evidence is neutral; no probability adjustment was applied.")

ledger = ForecastLedgerV83()
settled = ledger.settle(gold)
ledger.record(
    model_version=MODEL_VERSION_V83, data_timestamp=result.as_of,
    forecast_timestamp=forecast_time, starting_price=result.spot,
    directional_outlook=decision.candidate, decision=decision.action,
    market_probability_up=result.probability_up,
    adjusted_probability_up=elliott.probability_up,
    lower_target=lower, median_target=median, upper_target=upper,
    release_gate="PASS" if decision.action in {"BUY", "SELL"} else decision.action,
    gate_reasons="; ".join(decision.reasons),
)
if settled:
    st.success(f"Settled {settled} previous Version 8.3 forecast(s).")

st.subheader("Live forecast settlement performance")
live = ledger.live_performance(cost_bps=cost_bps)
l1, l2, l3, l4, l5, l6 = st.columns(6)
l1.metric("Validation gate", live["status"])
l2.metric("Settled", live["settled"])
l3.metric("Direction accuracy", (
    f'{live["direction_accuracy"]:.1%}'
    if pd.notna(live["direction_accuracy"]) else "N/A"))
l4.metric("Live Brier score", (
    f'{live["brier_score"]:.3f}' if pd.notna(live["brier_score"]) else "N/A"))
l5.metric("80% range coverage", (
    f'{live["interval_coverage"]:.1%}'
    if pd.notna(live["interval_coverage"]) else "N/A"))
l6.metric("Median price error", (
    f'USD {live["median_absolute_error"]:,.2f}'
    if pd.notna(live["median_absolute_error"]) else "N/A"))
st.caption(
    f'Executed decisions: {live["executed"]} | Non-overlapping trades: '
    f'{live["non_overlapping_trades"]} | Cost-aware net return: '
    f'{live["net_return"]:.1%} | Profit factor: '
    f'{live["profit_factor"]:.2f}' if pd.notna(live["profit_factor"]) else
    f'Executed decisions: {live["executed"]} | Non-overlapping trades: '
    f'{live["non_overlapping_trades"]} | Cost-aware net return: '
    f'{live["net_return"]:.1%} | Profit factor: N/A')
if live["status"] == "INSUFFICIENT":
    st.info("Live validation needs at least 30 settled directional forecasts. It is not replaced by backtest performance.")
elif live["status"] == "FAIL":
    st.warning("Live forecasts have not passed the accuracy, calibration and interval-coverage gate.")
else:
    st.success("Live forecasts passed the minimum settlement validation gate; continue monitoring for stability.")
calibration = ledger.calibration_table()
if not calibration.empty:
    calibration_display = calibration.copy()
    for column in ("Mean probability", "Observed up frequency"):
        calibration_display[column] = calibration_display[column].map(
            lambda value: f"{value:.1%}")
    calibration_display["Calibration gap"] = calibration_display[
        "Calibration gap"].map(lambda value: f"{value:+.1%}")
    st.dataframe(calibration_display, hide_index=True, width="stretch")

st.subheader("Non-overlapping cost-aware evaluation")
rows = []
for name, value in decision.evaluation.items():
    if name in {"Win rate", "Net return", "Max drawdown"} and pd.notna(value):
        shown = f"{value:.1%}"
    elif pd.isna(value):
        shown = "N/A"
    elif value == float("inf"):
        shown = "∞"
    else:
        shown = f"{value:.3f}"
    rows.append({"Metric": name, "Result": shown})
st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

st.subheader("Walk-forward out-of-sample performance")
st.dataframe(pd.DataFrame([
    {"Model": "Version 8.3", "ROC-AUC": result.metrics.get("ROC-AUC"),
     "Brier score": result.metrics.get("Brier score")},
    {"Model": "Version 8.2.5 champion",
     "ROC-AUC": result.baseline_metrics.get("Champion ROC-AUC"),
     "Brier score": result.baseline_metrics.get("Champion Brier score")},
]), hide_index=True, width="stretch")
st.caption("Higher ROC-AUC and lower Brier score are better. Version 8.3 abstains unless it beats 8.2.5 on both.")
st.caption("This section uses historical purged walk-forward folds. It is separate from the live settlement results above.")

st.subheader("Version 8.3 forecast ledger")
history = ledger.frame()
st.dataframe(history, hide_index=True, width="stretch")
st.download_button("Download Version 8.3 ledger (CSV)", history.to_csv(index=False).encode(),
                   "gold_v83_forecast_ledger.csv", "text/csv")

st.subheader("Technical indicators and previous-session pivots")
technical = technical_snapshot(gold)
st.dataframe(pd.DataFrame([{"Measure": key, "Value": value} for key, value in technical.items()]),
             hide_index=True, width="stretch")

st.subheader("Macro release audit")
st.dataframe(macro_audit, hide_index=True, width="stretch")
st.caption("Slow factors classify regime at their true release frequency; they do not create synthetic 15-minute releases.")
st.caption(
    "Investing.com calendar values are displayed through its official widget "
    "and are not scraped, copied or stored by Version 8.3.0.")

st.subheader("Official event-calendar audit")
st.dataframe(official_audit, hide_index=True, width="stretch")
upcoming = official_events[
    official_events.timestamp >= pd.Timestamp.now(tz="UTC")].head(10)
st.dataframe(format_events_gmt(upcoming), hide_index=True, width="stretch")
st.caption(
    "Authoritative times: BLS CPI/payrolls/PPI; BEA GDP/PCE/trade; "
    "Federal Reserve FOMC, minutes, speeches, press conferences and Beige Book. "
    "All displayed times are GMT. Lockout: 60 minutes before through "
    "30 minutes after; elevated preparation window: four hours.")
