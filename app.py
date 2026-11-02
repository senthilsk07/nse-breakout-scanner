import os
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from scanner import load_universe, fetch_candles_for_universe, scan_all
from strategy import SECTORS

IST = ZoneInfo("Asia/Kolkata")
st.set_page_config(page_title="NSE Breakout Scanner", page_icon="📈", layout="wide")

st.markdown("""
<style>
.block-container {padding-top: 1.3rem; padding-bottom: 2rem;}
[data-testid="stMetric"] {border: 1px solid rgba(128,128,128,.22); padding: 12px; border-radius: 12px;}
</style>
""", unsafe_allow_html=True)

st.title("📈 NSE Multi-Sector Breakout Scanner")
st.caption("Upstox candle-data prototype • T1 Sideways Hold • T2 Range Extension • NSE cash equities")

with st.sidebar:
    st.header("Scanner settings")
    sector = st.selectbox("Sector", ["All Sectors"] + SECTORS)
    selected_date = st.date_input("Trading date", value=date.today())
    refresh_seconds = st.select_slider("Refresh interval", options=[10, 20, 30], value=30)
    st.caption("Live refresh is intended for the current trading day. Historical dates use Upstox historical candles.")
    run_scan = st.button("Run scan now", type="primary", use_container_width=True)
    auto_refresh = st.toggle("Auto-refresh page", value=True)
    st.divider()
    st.markdown("**Credentials**")
    st.write("UPSTOX_ACCESS_TOKEN is read from the server environment. Never paste it into this page or source code.")
    st.markdown("[Upstox API docs](https://upstox.com/developer/api-documentation/)")

universe, universe_error = load_universe()
if universe_error:
    st.error(universe_error)
    st.stop()

if sector != "All Sectors":
    universe = universe[universe["sector"] == sector].copy()

if universe.empty:
    st.warning("No stocks are configured for this sector yet. Add stock rows to `universe.csv` (symbol, instrument_key, sector). See README.")
    st.stop()

today_ist = datetime.now(IST).date()
is_live_day = selected_date == today_ist

col1, col2, col3, col4 = st.columns(4)
col1.metric("Configured stocks", len(universe))
col2.metric("Sector view", sector)
col3.metric("Mode", "LIVE polling" if is_live_day else "HISTORICAL")
col4.metric("Refresh", f"{refresh_seconds}s" if is_live_day else "Manual")

status = st.empty()
if run_scan or (auto_refresh and is_live_day) or "scan_result" not in st.session_state or st.session_state.get("last_scan_date") != str(selected_date):
    try:
        with st.spinner("Fetching Upstox 5-minute candles and evaluating T1/T2 rules..."):
            candle_map, fetch_notes = fetch_candles_for_universe(universe, selected_date, is_live_day)
            results, diagnostics = scan_all(universe, candle_map, selected_date)
            st.session_state["scan_result"] = results
            st.session_state["scan_diagnostics"] = diagnostics
            st.session_state["fetch_notes"] = fetch_notes
            st.session_state["last_scan_date"] = str(selected_date)
            st.session_state["last_scan_at"] = datetime.now(IST).strftime("%H:%M:%S IST")
    except Exception as exc:
        st.error(f"Scan failed: {exc}")
        st.stop()

results = st.session_state.get("scan_result", pd.DataFrame())
diagnostics = st.session_state.get("scan_diagnostics", {})
notes = st.session_state.get("fetch_notes", [])
st.caption(f"Last scan: {st.session_state.get('last_scan_at', 'not run')}")

if notes:
    with st.expander(f"Data/API notes ({len(notes)})"):
        for note in notes[:100]:
            st.write(f"• {note}")

signals = results[results["signal"].isin(["T1 Bullish", "T1 Bearish", "T2 Bullish", "T2 Bearish"])] if not results.empty else pd.DataFrame()
a, b, c = st.columns(3)
a.metric("Triggered alerts", len(signals))
b.metric("T1 alerts", int(signals["signal"].str.startswith("T1").sum()) if not signals.empty else 0)
c.metric("T2 alerts", int(signals["signal"].str.startswith("T2").sum()) if not signals.empty else 0)

tab1, tab2, tab3 = st.tabs(["🚨 Alerts", "🔎 All stocks / diagnostics", "📘 Strategy rules"])
with tab1:
    if signals.empty:
        st.info("No confirmed T1/T2 signals for this scan. A signal is only counted after a completed 5-minute candle closes beyond the relevant range and the volume filters pass.")
    else:
        show_cols = ["symbol", "sector", "signal", "trigger_time", "close", "breakout_level",
                     "range_high", "range_low", "candle_volume", "range_avg_volume",
                     "range_volume_hike", "last_two_volume_hike", "volume_ratio"]
        st.dataframe(signals[show_cols], use_container_width=True, hide_index=True)
        st.download_button("Download alerts CSV", signals[show_cols].to_csv(index=False).encode("utf-8"),
                           file_name=f"nse_alerts_{selected_date}.csv", mime="text/csv")

with tab2:
    if not results.empty:
        st.dataframe(results, use_container_width=True, hide_index=True)
        st.download_button("Download full scan CSV", results.to_csv(index=False).encode("utf-8"),
                           file_name=f"nse_scan_{selected_date}.csv", mime="text/csv")
    st.markdown("#### Diagnostics")
    st.json(diagnostics)

with tab3:
    st.markdown("""
**Candle convention used by this code:** timestamps represent the *start* of a 5-minute candle. Therefore, the opening range 09:15–09:55 uses candles starting 09:15 through 09:50, which are complete at 09:55. The extended range 09:15–10:55 uses candles starting 09:15 through 10:50, complete at 10:55.

- **T1 range:** overall high and low of completed opening-range candles.
- **T1 eligibility:** every candle in the 09:55–10:25 watch window must stay strictly inside the opening range; touching either boundary invalidates T1.
- **T1 trigger:** from 10:30 through 14:45, a completed candle must close above the opening high or below the opening low.
- **T2 eligibility:** an opening-range boundary must be breached before 10:25.
- **T2 range:** after the 10:55 candle has completed, calculate the high/low from candles starting 09:15 through 10:50.
- **T2 trigger:** only a later completed candle, after 10:55, may close outside the extended range.
- **Volume check A — range volume hike:** trigger-candle volume must be strictly greater than the average 5-minute volume in the relevant range.
- **Volume check B — last-two-candle hike:** trigger-candle volume must be strictly greater than the volume of **each** of the two immediately preceding completed candles.
- Signals are generated once per symbol/strategy/direction per selected date; this is a scanner, not an order-execution system.
""")

if auto_refresh and is_live_day:
    st.caption(f"Auto-refresh enabled: page reruns every {refresh_seconds} seconds while this tab is open.")
    st_autorefresh(interval=refresh_seconds * 1000, key="live_auto_refresh")
