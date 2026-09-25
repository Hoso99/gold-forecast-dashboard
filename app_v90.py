import os
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from forecast_ledger_v90 import ForecastLedgerV90
from event_chart_v90 import (
    combine_chart_events, event_price_chart, manual_event_frame)
from free_gold_perpetuals_v90 import (
    collect_free_perpetual_consensus, display_frame as perpetual_display_frame)
from gold_model import price_interval, technical_snapshot
from gold_model_v82 import (
    apply_elliott_overlay,
    download_intraday_bundle, fit_intraday_system, validate_market_data,
)
from gold_model_v90 import (
    INTRADAY_HORIZON_BARS, INTRADAY_HORIZON_LABEL, INTRADAY_INTERVAL,
    MODEL_VERSION_V90, audit_five_minute_reversals,
    combined_directional_lean, decide_v90, download_five_minute_gold,
    fit_v90_system, short_term_technical_trend)
from institutional_features_v830 import catalyst_playbook
from macro_econometrics_v825 import combine_macro_sources, download_fred_macro, parse_slow_factor_csv
from official_event_calendar_v830 import (
    download_official_events, event_risk_notice, format_events_gmt,
    official_event_risk)

st.set_page_config(page_title="Gold Version 9.3", page_icon="🟡", layout="wide")
st.title("Gold Version 9.3")
st.caption("Shock-aware calibrated regime-ensemble · 30-minute forecast · market-only research")

with st.sidebar:
    st.header("Version 9.3 settings")
    st.text_input("Candle interval", INTRADAY_INTERVAL, disabled=True)
    st.text_input("Forecast horizon", INTRADAY_HORIZON_LABEL, disabled=True)
    threshold = st.slider("Timing probability threshold", .55, .75, .58, .01)
    cost_bps = st.number_input("Estimated total cost (basis points)", 0, 100, 10, 5)
    splits = st.slider("Walk-forward folds", 4, 8, 5)
    major_event = st.checkbox(
        "Investing.com 3-star USD event within next hour",
        help="Check this after reviewing the embedded calendar. It blocks forecast release.")
    manual_event_name = st.text_area(
        "Event names — one per line",
        "President Trump speech",
        help="Enter every simultaneous three-star event on a separate line.",
        disabled=not major_event)
    manual_event_date = st.date_input(
        "Event date (GMT)", value=pd.Timestamp.now(tz="UTC").date(),
        disabled=not major_event)
    manual_event_time = st.time_input(
        "Event time (GMT)", value=pd.Timestamp.now(tz="UTC").floor("15min").time(),
        disabled=not major_event)
    slow_file = st.file_uploader(
        "Optional official positioning CSV", type=["csv"],
        help=("Release-timestamped CFTC managed-money, central-bank demand or "
              "geopolitical-risk data. Future-dated observations are never used."))
    run = st.button("Run Version 9.3", type="primary", width="stretch")

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
manual_events = manual_event_frame(
    major_event, manual_event_date, manual_event_time, manual_event_name)
chart_events = combine_chart_events(official_events, manual_events)
automatic_event_lock, nearby_official_events = official_event_risk(
    chart_events)

@st.cache_data(ttl=15, show_spinner=False)
def free_perpetual_audit():
    return collect_free_perpetual_consensus()
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
    with st.spinner("Running Version 9.3 calibrated walk-forward research…"):
        gold, confirmations, source_status = download_intraday_bundle(key)
        validate_market_data(gold, confirmations)
        result = fit_v90_system(gold, confirmations, splits, cost_bps, threshold)
        fred, macro_audit = download_fred_macro()
        slow = parse_slow_factor_csv(slow_file) if slow_file else None
        macro = combine_macro_sources(fred, slow)
        elliott = apply_elliott_overlay(result.probability_up, result.median_return,
                                        threshold, cost_bps, gold,
                                        horizon_bars=INTRADAY_HORIZON_BARS)
        perpetual_consensus = free_perpetual_audit()
        try:
            gold_5m = download_five_minute_gold(key)
            reversal_5m = audit_five_minute_reversals(
                gold_5m, cost_bps=cost_bps)
        except Exception as reversal_error:
            reversal_5m = {
                "status": "UNAVAILABLE", "warning": "NONE",
                "raw_warning": "NONE", "current_signal": 0,
                "buy": {}, "sell": {}, "latest": {},
                "detail": str(reversal_error),
            }
        short_trend = short_term_technical_trend(gold)
        decision = decide_v90(
            result, macro, elliott, threshold, cost_bps,
            major_event=(major_event or automatic_event_lock),
            technical=short_trend,
            perpetual_consensus=perpetual_consensus)
        directional = combined_directional_lean(
            result, macro, short_trend, perpetual_consensus,
            institutional=result.institutional_audit,
            event_lock=(major_event or automatic_event_lock))
        directional["actionable"] = (
            decision.action in {"BUY", "SELL"} and
            directional["lean"].startswith(decision.action))
except Exception as exc:
    st.error(f"Version 9.3 could not run: {exc}")
    st.stop()

decision_tab, events_tab, pressure_tab, validation_tab, ledger_tab = st.tabs([
    "Decision", "Events & Chart", "Market Pressure",
    "Validation", "Forecast Ledger",
])

with events_tab:
    if official_audit.Status.astype(str).str.startswith("unavailable").any():
        st.warning(
            "One or more official calendars are unavailable. Review "
            "Investing.com and use the manual three-star event control.")
    notice_state, notice_events = event_risk_notice(chart_events)
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
    
    st.subheader("Gold chart with high-impact event markers")
    st.plotly_chart(
        event_price_chart(gold, chart_events), width="stretch",
        config={"displaylogo": False})
    st.caption(
        "Yellow = manually confirmed Investing.com three-star event. "
        "Red dashed = official BLS, BEA or Federal Reserve event. All times are GMT/UTC.")
    
with pressure_tab:
    st.subheader("Free six-venue XAU perpetual consensus")
    p1, p2, p3, p4 = st.columns(4)
    p1.metric("Feed status", perpetual_consensus.status)
    p2.metric("Live venues", f"{perpetual_consensus.live_venues}/6")
    p3.metric("Consensus", perpetual_consensus.direction)
    p4.metric("Agreement", f"{perpetual_consensus.agreement}/{perpetual_consensus.live_venues} live · {perpetual_consensus.confidence}")
    q1, q2, q3 = st.columns(3)
    q1.metric("Purchasing power", f"{perpetual_consensus.buying_power:.1%}")
    q2.metric("Selling power", f"{perpetual_consensus.selling_power:.1%}")
    q3.metric("Order-flow decision", perpetual_consensus.order_flow_decision)
    perpetual_table = perpetual_display_frame(perpetual_consensus)
    st.dataframe(
        perpetual_table,
        column_config={
            "Last": st.column_config.NumberColumn(format="%.2f"),
            "Book imbalance": st.column_config.NumberColumn(format="%+.1%%"),
            "Trade imbalance": st.column_config.NumberColumn(format="%+.1%%"),
        }, hide_index=True, width="stretch")
    if perpetual_consensus.confidence == "HIGH":
        st.warning(
            f"HIGH-CONFIDENCE {perpetual_consensus.direction}: a strong majority "
            "of live venues agree. Treat this as order-flow confirmation, not a standalone trade.")
    elif perpetual_consensus.confidence == "MODERATE":
        st.info(
            f"MODERATE {perpetual_consensus.direction}: a live-venue majority agrees, "
            "but confirmation is incomplete.")
    else:
        st.info("No reliable cross-venue XAU perpetual pressure consensus is present.")
    st.caption(
        "Free public Binance, Bybit, OKX, MEXC, Bitget and Phemex gold-linked "
        "snapshots. These are synthetic perpetual proxies—not COMEX GC. Aggressive "
        "trades receive 65% and displayed depth 35% of the pressure score. The "
        "model uses at most 10% weight and requires cross-venue agreement; this "
        "cannot reveal hidden orders or guarantee the next move.")
    
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
    
with decision_tab:
    lower, median, upper = price_interval(result)
    forecast_time = result.as_of + pd.Timedelta(minutes=30)
    st.subheader("Version 9.3 decision")
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Slow macro background", decision.macro_regime)
    c2.metric("Timing candidate", decision.candidate)
    c3.metric("Risk-controlled action", decision.action)
    c4.metric("Probability up", f"{elliott.probability_up:.1%}")
    c5.metric("Predicted price in 30 minutes", f"USD {median:,.2f}")
    c6.metric("80% range", f"{lower:,.2f}–{upper:,.2f}")
    d1, d2, d3, d4, d5 = st.columns(5)
    d1.metric("Short-term technical trend", short_trend["trend"])
    d2.metric("Priority market-pressure indication", directional["pressure_indication"])
    d3.metric("All-source directional lean", directional["lean"])
    d4.metric("Evidence alignment", f'{directional["aligned"]}/{directional["active"]}')
    d5.metric("Lean confidence", directional["confidence"])
    st.progress((directional["score"] + 1) / 2,
                text=f'Directional score {directional["score"]:+.2f} '
                     '(left = SELL lean, right = BUY lean)')
    evidence_rows = []
    for source, score in directional["components"].items():
        evidence_rows.append({
            "Evidence": source,
            "Direction": "BUY" if score > .10 else "SELL" if score < -.10 else "NEUTRAL",
            "Score": score,
            "Weight": directional["weights"][source],
        })
    st.dataframe(pd.DataFrame(evidence_rows), hide_index=True, width="stretch",
                 column_config={
                     "Score": st.column_config.NumberColumn(format="%+.2f"),
                     "Weight": st.column_config.NumberColumn(format="%.0%%")})
    if directional["pressure_priority"]:
        st.warning(
            f'PRIORITY PRESSURE INDICATION: {directional["pressure_indication"]}. '
            'This is the highest-weight timing input, but it becomes an actionable '
            'trade only when the risk-controlled action confirms the same side.')
    if directional["actionable"]:
        st.success(
            f'CONFIRMED {decision.action}: the validated action and all-source '
            'directional lean agree. This remains probabilistic, not guaranteed.')
    else:
        st.info(
            f'{directional["lean"]} is context only. The executable research '
            f'action remains {decision.action}; a lean never overrides failed '
            'validation, cost or event gates.')
    st.subheader("Validated 5-minute early-reversal warning")
    active_side = (
        reversal_5m.get("buy", {}) if reversal_5m["current_signal"] > 0 else
        reversal_5m.get("sell", {}) if reversal_5m["current_signal"] < 0 else {})
    v1, v2, v3, v4, v5 = st.columns(5)
    v1.metric("Released warning", reversal_5m["warning"])
    v2.metric("Raw detector", reversal_5m["raw_warning"])
    v3.metric("Validation gate", reversal_5m["status"])
    v4.metric("Holdout accuracy", (
        f'{active_side.get("accuracy"):.1%}'
        if pd.notna(active_side.get("accuracy", pd.NA)) else "N/A"))
    v5.metric("Profit factor", (
        f'{active_side.get("profit_factor"):.2f}'
        if pd.notna(active_side.get("profit_factor", pd.NA)) else "N/A"))
    reversal_rows = []
    for label, values in (("BUY reversal", reversal_5m.get("buy", {})),
                          ("SELL reversal", reversal_5m.get("sell", {}))):
        reversal_rows.append({
            "Side": label, "Holdout cases": values.get("observations", 0),
            "Accuracy": values.get("accuracy"),
            "90% Wilson lower": values.get("lower_bound"),
            "Profit factor": values.get("profit_factor"),
            "Gate": "PASS" if values.get("qualified", False) else "FAIL",
        })
    st.dataframe(pd.DataFrame(reversal_rows), hide_index=True, width="stretch",
                 column_config={
                     "Accuracy": st.column_config.NumberColumn(format="%.1%%"),
                     "90% Wilson lower": st.column_config.NumberColumn(format="%.1%%"),
                     "Profit factor": st.column_config.NumberColumn(format="%.2f")})
    if reversal_5m["warning"] != "NONE":
        st.error(
            f'{reversal_5m["warning"]}: a completed five-minute candle '
            'confirmed exhaustion and a reversal break, and that side passed '
            'its separate historical validation gate. Treat this as an early '
            'warning—not an automatic order.')
    elif reversal_5m["raw_warning"] != "NONE":
        st.warning(
            f'{reversal_5m["raw_warning"]} was detected but suppressed because '
            'its side-specific validation gate failed.')
    elif reversal_5m["status"] == "UNAVAILABLE":
        st.info("Five-minute reversal feed unavailable: " + reversal_5m["detail"])
    else:
        st.info("No completed five-minute exhaustion-and-break reversal is active.")
    st.caption(
        "A side passes only with at least 30 newest holdout cases, accuracy "
        "of at least 55%, a 90% Wilson lower bound of at least 50%, and "
        "profit factor of at least 1.20 after configured costs.")
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
    
ledger = ForecastLedgerV90()
settled = ledger.settle(gold)
ledger.record(
    model_version=MODEL_VERSION_V90, data_timestamp=result.as_of,
    forecast_timestamp=forecast_time, starting_price=result.spot,
    directional_outlook=decision.candidate, decision=decision.action,
    market_probability_up=result.probability_up,
    adjusted_probability_up=elliott.probability_up,
    lower_target=lower, median_target=median, upper_target=upper,
    release_gate="PASS" if decision.action in {"BUY", "SELL"} else decision.action,
    gate_reasons="; ".join(decision.reasons),
)
if settled:
    st.success(f"Settled {settled} previous Version 9.3 forecast(s).")

with validation_tab:
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
        {"Model": "Version 9.3", "ROC-AUC": result.metrics.get("ROC-AUC"),
         "Brier score": result.metrics.get("Brier score")},
    ]), hide_index=True, width="stretch")
    st.caption("Higher ROC-AUC and lower Brier score are better. Version 8.2.5 is not compared because it predicts a different one-hour target.")
    st.caption("This section uses historical purged walk-forward folds. It is separate from the live settlement results above.")

    st.subheader("Selective-signal reliability")
    selective = result.selective_reliability
    q1, q2, q3, q4 = st.columns(4)
    q1.metric("Candidate side", selective["side"])
    q2.metric("Comparable OOS signals", selective["observations"])
    q3.metric("OOS side accuracy", (
        f'{selective["accuracy"]:.1%}'
        if pd.notna(selective["accuracy"]) else "N/A"))
    q4.metric("90% Wilson lower bound", (
        f'{selective["lower_bound"]:.1%}'
        if pd.notna(selective["lower_bound"]) else "N/A"))
    st.caption(
        "BUY/SELL is released only when the current side has at least 30 "
        "purged out-of-sample examples and its conservative accuracy lower "
        "bound is at least 50%.")
    st.dataframe(pd.DataFrame([
        {"Ensemble member": name, "Calibration weight": weight}
        for name, weight in result.ensemble_weights.items()
    ]), hide_index=True, width="stretch",
        column_config={"Calibration weight": st.column_config.NumberColumn(
            format="%.1%%")})
    st.caption(
        f'Current ensemble disagreement: {result.model_disagreement:.1%} · '
        f'Conformal interval adjustment: {result.conformal_adjustment:.3%} return · '
        f'Median bias adjustment: {result.median_bias_adjustment:+.3%} return.')
    
with ledger_tab:
    st.subheader("Version 9.3 forecast ledger")
    history = ledger.frame()
    st.dataframe(history, hide_index=True, width="stretch")
    st.download_button("Download Version 9.3 ledger (CSV)", history.to_csv(index=False).encode(),
                       "gold_v90_forecast_ledger.csv", "text/csv")
    
    st.subheader("Technical indicators and previous-session pivots")
    technical = technical_snapshot(gold)
    st.dataframe(pd.DataFrame([{"Measure": key, "Value": value} for key, value in technical.items()]),
                 hide_index=True, width="stretch")
    
    st.subheader("Macro release audit")
    st.dataframe(macro_audit, hide_index=True, width="stretch")
    st.caption("Slow factors classify regime at their true release frequency; they do not create synthetic 15-minute releases.")
    st.caption(
        "Investing.com calendar values are displayed through its official widget "
        "and are not scraped, copied or stored by Version 9.3.")
    
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
