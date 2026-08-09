"""
app.py
-------
AlphaQuant -- Premium Web Edition. Dark glassmorphic trading-terminal UI,
zero local installs. Once deployed, open a URL in any browser and the
entire agent pipeline runs server-side, now scanning the FULL NSE market
via NSE's own bhavcopy archive (see nse_bhavcopy.py) instead of a
hand-picked watchlist.
"""
from __future__ import annotations
import streamlit as st
import pandas as pd

import config
import orchestrator
import reporting
import upstox_auth
import gsheets_sync
import theme
import charts
import nse_bhavcopy
from backtest import backtest_engine

st.set_page_config(
    page_title=f"{config.APP_NAME} \u2014 Premium Research Terminal",
    page_icon="\U0001F4C8",
    layout="wide",
    initial_sidebar_state="expanded",
)
st.markdown(theme.inject_css(), unsafe_allow_html=True)

# --- Upstox OAuth callback handling -- must run before anything renders ---
query_params = st.query_params
if "code" in query_params and not upstox_auth.get_valid_token():
    try:
        token_response = upstox_auth.exchange_code_for_token(
            code=query_params["code"], redirect_uri=config.APP_BASE_URL
        )
        upstox_auth.store_token(token_response)
        st.query_params.clear()
        st.toast(f"Connected to Upstox as {token_response.get('user_name', 'user')}", icon="\u2705")
    except Exception as e:
        st.query_params.clear()
        st.sidebar.error(f"Upstox login failed: {e}")

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown(f"""
        <div class="aq-brand-wrap">
            <div class="aq-logo-mark">\U0001F4C8</div>
            <div>
                <div class="aq-brand-title">{config.APP_NAME}</div>
                <div class="aq-brand-tagline">{config.APP_TAGLINE}</div>
            </div>
        </div>
        <hr style="margin: 14px 0 18px 0;">
    """, unsafe_allow_html=True)

    st.markdown('<div style="font-size:12px; font-weight:700; letter-spacing:0.05em; '
                'color:#94A3B8; text-transform:uppercase; margin-bottom:8px;">Data Source</div>',
                unsafe_allow_html=True)
    status = upstox_auth.connection_status()
    if status["connected"]:
        st.markdown(theme.pill_html(f"\u25CF LIVE \u00b7 Upstox until {status['expires_at_ist']}", "approved"),
                    unsafe_allow_html=True)
        st.write("")
        if st.button("Disconnect Upstox", use_container_width=True):
            upstox_auth.clear_token()
            st.rerun()
    else:
        if status.get("expired"):
            st.markdown(theme.pill_html("\u23F0 Session expired \u2014 reconnect", "warning"), unsafe_allow_html=True)
        else:
            st.markdown(theme.pill_html("\u25CB Free tier \u00b7 yfinance", "neutral"), unsafe_allow_html=True)
        st.write("")
        if not upstox_auth.is_configured():
            st.caption("Add Upstox client_id/secret in Streamlit secrets for live data \u2014 see DEPLOY.md.")
        else:
            login_url = upstox_auth.get_login_url(redirect_uri=config.APP_BASE_URL)
            st.link_button("\U0001F517 Connect to Upstox", login_url, use_container_width=True)

    st.divider()

    st.markdown('<div style="font-size:12px; font-weight:700; letter-spacing:0.05em; '
                'color:#94A3B8; text-transform:uppercase; margin-bottom:8px;">Market Universe</div>',
                unsafe_allow_html=True)
    universe_mode_label = st.radio(
        "Universe source", ["Full market (NSE bhavcopy)", "Fallback watchlist (20 stocks)"],
        index=0 if config.UNIVERSE_MODE == "bhavcopy" else 1, label_visibility="collapsed",
    )
    config.UNIVERSE_MODE = "bhavcopy" if "bhavcopy" in universe_mode_label else "watchlist"

    scan_mode_label = st.radio(
        "Scan mode",
        ["\U0001F7E2 Live (during market hours)", "\U0001F319 End-of-day (uses latest bhavcopy, works anytime)"],
        index=0, label_visibility="collapsed",
        help="Live: bhavcopy discovers the liquid universe, then fetches LIVE quotes "
             "(bulk via Upstox, or a capped batch via yfinance). End-of-day: uses only "
             "cached bhavcopy history -- zero live API calls, covers the full universe "
             "uncapped, but reflects the last completed session, not right now.",
    )
    scan_mode = "live" if "Live" in scan_mode_label else "eod"

    st.divider()
    capital = st.number_input("Account capital (\u20b9)", min_value=10_000,
                               value=config.DEFAULT_CAPITAL, step=10_000)
    top_n = st.slider("Top N candidates", 1, 20, config.DEFAULT_TOP_N)
    use_pairs = st.checkbox("Include pairs trading scan", value=False)
    run_clicked = st.button("\u25B6\uFE0F  Run Full Pipeline", type="primary", use_container_width=True)

    st.divider()

    st.markdown('<div style="font-size:12px; font-weight:700; letter-spacing:0.05em; '
                'color:#94A3B8; text-transform:uppercase; margin-bottom:8px;">Backtest Validation</div>',
                unsafe_allow_html=True)
    bt_period = st.selectbox("History window", ["1y", "2y", "5y"], index=1)
    bt_horizon = st.slider("Forward horizon (days)", 2, 10, 5)
    bt_stride = st.slider("Stride (days)", 1, 10, 5)
    run_backtest_clicked = st.button("\U0001F52C  Run Backtest", use_container_width=True)

# ---------------------------------------------------------------------------
# State + pipeline execution
# ---------------------------------------------------------------------------
if "pipeline_result" not in st.session_state:
    st.session_state.pipeline_result = None
if "backtest_result" not in st.session_state:
    st.session_state.backtest_result = None

if run_clicked:
    progress_bar = st.sidebar.progress(0.0, text="Starting...")

    def _cb(frac, msg):
        progress_bar.progress(frac, text=msg)

    with st.spinner("Running full pipeline..."):
        st.session_state.pipeline_result = orchestrator.run_pipeline(
            capital=capital, top_n=top_n, use_pairs=use_pairs, scan_mode=scan_mode, progress_callback=_cb
        )
    progress_bar.empty()
    st.toast("Pipeline run complete", icon="\u2705")

if run_backtest_clicked:
    bt_progress = st.sidebar.progress(0.0, text="Starting backtest...")

    def _bt_cb(frac, msg):
        bt_progress.progress(frac, text=msg)

    with st.spinner("Running walk-forward backtest..."):
        st.session_state.backtest_result = backtest_engine.run_backtest(
            period=bt_period, horizon_days=bt_horizon, stride=bt_stride, progress_callback=_bt_cb
        )
    bt_progress.empty()
    st.toast("Backtest complete", icon="\U0001F52C")

result = st.session_state.pipeline_result
bt_result = st.session_state.backtest_result

# ---------------------------------------------------------------------------
# Top hero row
# ---------------------------------------------------------------------------
hero_cols = st.columns([2.4, 1, 1, 1, 1])
with hero_cols[0]:
    st.markdown(f"""
        <div style="padding-top:4px;">
            <div style="font-size:28px; font-weight:800; color:{theme.TEXT_PRIMARY}; letter-spacing:-0.02em;">
                Research Terminal
            </div>
            <div style="color:{theme.TEXT_SECONDARY}; font-size:14px; margin-top:2px;">
                Full NSE market coverage via bhavcopy \u00b7 6-agent decision pipeline
            </div>
        </div>
    """, unsafe_allow_html=True)

if result:
    rep = result["report"]
    n_approved = len(rep["approved"])
    n_rejected = len(rep["rejected"])
    n_new = len(rep["new_symbols"])
    avg_conf = round(sum(d["confidence_score"] for d in rep["approved"]) / n_approved, 1) if n_approved else 0.0
else:
    n_approved = n_rejected = n_new = 0
    avg_conf = 0.0

with hero_cols[1]:
    st.markdown(theme.kpi_html("Approved", str(n_approved),
                               f"\u2191 {n_new} new" if n_new else None, "pos" if n_new else "neu"),
                unsafe_allow_html=True)
with hero_cols[2]:
    st.markdown(theme.kpi_html("Rejected", str(n_rejected)), unsafe_allow_html=True)
with hero_cols[3]:
    st.markdown(theme.kpi_html("Avg Confidence", f"{avg_conf}"), unsafe_allow_html=True)
with hero_cols[4]:
    upstox_live = status["connected"]
    st.markdown(theme.kpi_html("Data Feed", "LIVE" if upstox_live else "FREE",
                               "Upstox" if upstox_live else "yfinance",
                               "pos" if upstox_live else "neu"), unsafe_allow_html=True)

st.write("")

# ---------------------------------------------------------------------------
# Main tabs
# ---------------------------------------------------------------------------
tab_scan, tab_decisions, tab_news, tab_pairs, tab_backtest, tab_log = st.tabs([
    "\U0001F50E  Live Scan", "\u2705  Decisions", "\U0001F4F0  News & Regime",
    "\U0001F517  Pairs Trading", "\U0001F52C  Backtest Validation", "\U0001F4CB  Run Log"
])

# ============================ TAB: LIVE SCAN ================================
with tab_scan:
    st.markdown(theme.section_title_html("\U0001F50E", "Market Scanner"), unsafe_allow_html=True)
    st.caption("Relative volume \u2265 1.5\u00d7 avg, or price move \u2265 1% today qualifies for deeper analysis. "
               f"Universe: {config.UNIVERSE_MODE} \u00b7 Liquidity floor: Rs.{config.BHAVCOPY_MIN_AVG_DAILY_VALUE_CR}cr/day avg.")

    if result is None:
        st.markdown('<div class="aq-card" style="text-align:center; padding:48px 20px;">'
                    '<div style="font-size:40px; margin-bottom:12px;">\U0001F680</div>'
                    '<div style="color:#F1F5F9; font-weight:700; font-size:16px;">Ready to scan</div>'
                    '<div style="color:#94A3B8; font-size:13px; margin-top:6px;">'
                    'Click <b>Run Full Pipeline</b> in the sidebar to analyze the full market universe.</div>'
                    '</div>', unsafe_allow_html=True)
    else:
        scanned = result["scanned"]
        n_qualified = int(scanned["qualifies"].sum()) if not scanned.empty else 0
        st.markdown(
            f'<div class="aq-card" style="border-left: 3px solid {theme.ACCENT_SOLID};">'
            f'<span style="color:{theme.TEXT_PRIMARY};">Scanned <b>{len(scanned)}</b> stocks this run '
            f'({result["scan_mode"]} mode) \u2014 <b>{n_qualified}</b> qualified for deeper analysis.</span>'
            f'</div>', unsafe_allow_html=True)
        if not scanned.empty:
            col_chart, col_table = st.columns([1, 1.4])
            with col_chart:
                st.markdown('<div class="aq-card">', unsafe_allow_html=True)
                st.plotly_chart(charts.rel_volume_bar(scanned), use_container_width=True, config={"displayModeBar": False})
                st.caption("Showing up to 40 symbols for readability -- full results in the table.")
                st.markdown('</div>', unsafe_allow_html=True)
            with col_table:
                st.markdown('<div class="aq-card">', unsafe_allow_html=True)
                display_df = scanned.copy()
                display_df["qualifies"] = display_df["qualifies"].map({True: "\u2705", False: "\u2014"})
                st.dataframe(display_df, use_container_width=True, hide_index=True, height=400)
                st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.warning("No scan results -- bhavcopy may be unreachable right now (falls back to the "
                       "watchlist automatically on the next run) or no symbols cleared the liquidity floor.")

# ============================ TAB: DECISIONS =================================
with tab_decisions:
    st.markdown(theme.section_title_html("\u2705", "Decision Agent \u2014 Approved & Rejected"), unsafe_allow_html=True)

    if result is None:
        st.markdown('<div class="aq-card" style="text-align:center; padding:48px 20px; color:#94A3B8;">'
                    'Run the pipeline first to see recommendations.</div>', unsafe_allow_html=True)
    else:
        rep = result["report"]

        if rep["new_symbols"]:
            st.markdown(
                f'<div class="aq-card" style="border-left: 3px solid {theme.ACCENT_SOLID};">'
                f'{theme.pill_html("\u2728 NEW THIS RUN", "new")} &nbsp; '
                f'<span style="color:{theme.TEXT_PRIMARY}; font-weight:600;">{", ".join(rep["new_symbols"])}</span>'
                f'</div>', unsafe_allow_html=True
            )

        st.write("")
        st.markdown("##### \u2705 Approved Candidates")

        if rep["approved"]:
            for d in rep["approved"]:
                is_new = d["symbol"] in rep["new_symbols"]
                conf = d["confidence_score"]
                badge = theme.pill_html("NEW", "new") if is_new else ""

                st.markdown('<div class="aq-card">', unsafe_allow_html=True)
                head_col1, head_col2, head_col3 = st.columns([2, 1, 1])
                with head_col1:
                    st.markdown(f'<span class="aq-symbol-chip">{d["symbol"]}</span> {badge}',
                                unsafe_allow_html=True)
                    st.markdown(theme.confidence_meter_html(conf), unsafe_allow_html=True)
                    st.caption(f"Confidence {conf}/100")
                with head_col2:
                    st.metric("Entry", f"\u20b9{d['entry']}")
                with head_col3:
                    stop_distance = d['stop'] - d['entry'] if d.get('entry') else None
                    st.metric("Stop", f"\u20b9{d['stop']}",
                              delta=f"{stop_distance:.2f}" if stop_distance is not None else None,
                              delta_color="inverse")

                with st.expander("View full analysis"):
                    chart_col, gauge_col = st.columns([2, 1])
                    with chart_col:
                        daily_df = d.get("daily_df")
                        if daily_df is not None and not daily_df.empty:
                            fig = charts.price_chart_with_levels(daily_df, d["entry"], d["stop"],
                                                                  d["targets"], d["symbol"])
                            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
                    with gauge_col:
                        st.plotly_chart(charts.confidence_gauge(conf), use_container_width=True,
                                         config={"displayModeBar": False})
                        st.plotly_chart(charts.component_radar(d["components"]), use_container_width=True,
                                         config={"displayModeBar": False})

                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("Shares", d["shares"])
                    m2.metric("Position Value", f"\u20b9{d['position_value']:,.0f}")
                    m3.metric("T2 Target", f"\u20b9{d['targets'].get('T2')}")
                    m4.metric("Targets", " / ".join(str(v) for v in d["targets"].values()))

                    st.markdown("**Reasoning**")
                    for r in d["reasoning"]:
                        st.markdown(f"- {r}")

                    if d.get("monte_carlo", {}).get("valid"):
                        mc = d["monte_carlo"]
                        st.markdown(f"**Monte Carlo Simulation** \u00b7 {mc['n_paths']} paths, "
                                    f"{mc['horizon_days']}-day horizon")
                        if mc.get("price_paths_sample"):
                            fan_fig = charts.monte_carlo_fan_chart(d["entry"], mc["price_paths_sample"],
                                                                    mc["horizon_days"])
                            st.plotly_chart(fan_fig, use_container_width=True, config={"displayModeBar": False})
                        prob_cols = st.columns(len(mc["targets"]) + 1)
                        prob_cols[0].metric("Stop hit prob.", f"{mc['stop_hit_probability_pct']}%")
                        for i, (label, t) in enumerate(mc["targets"].items(), start=1):
                            prob_cols[i].metric(f"{label} hit prob.", f"{t['hit_probability_pct']}%")

                    with st.popover("\u2139\ufe0f Assumptions & limitations"):
                        for a in d["assumptions"]:
                            st.caption(f"\u2022 {a}")
                st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="aq-card" style="text-align:center; color:#94A3B8; padding:24px;">'
                        'No candidates cleared every filter this run.</div>', unsafe_allow_html=True)

        st.write("")
        st.markdown("##### \u274C Rejected")
        if rep["rejected"]:
            rej_df = pd.DataFrame([{"Symbol": d["symbol"], "Reason": d.get("reject_reason")}
                                    for d in rep["rejected"]])
            st.markdown('<div class="aq-card">', unsafe_allow_html=True)
            st.dataframe(rej_df, use_container_width=True, hide_index=True)
            st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.caption("Nothing rejected this run.")

# ============================ TAB: NEWS & REGIME ==============================
with tab_news:
    st.markdown(theme.section_title_html("\U0001F4F0", "News & Macro Sentiment"), unsafe_allow_html=True)

    if result is None:
        st.markdown('<div class="aq-card" style="text-align:center; color:#94A3B8; padding:48px;">'
                    'Run the pipeline first.</div>', unsafe_allow_html=True)
    else:
        macro = result["macro_summary"]
        headlines = result["headlines"]

        c1, c2 = st.columns([1, 1.6])
        with c1:
            st.markdown('<div class="aq-card">', unsafe_allow_html=True)
            st.markdown("**Sentiment Mix**")
            st.plotly_chart(charts.sentiment_donut(headlines), use_container_width=True,
                             config={"displayModeBar": False})
            st.markdown('</div>', unsafe_allow_html=True)
        with c2:
            k1, k2, k3 = st.columns(3)
            with k1:
                st.markdown(theme.kpi_html("Headlines (24h)", str(macro["headline_count"])), unsafe_allow_html=True)
            with k2:
                sent_val = macro["avg_sentiment"] if macro["avg_sentiment"] is not None else "n/a"
                st.markdown(theme.kpi_html("Avg Sentiment", str(sent_val),
                                           macro["overall_label"].title(),
                                           "pos" if macro["overall_label"] == "positive" else
                                           "neg" if macro["overall_label"] == "negative" else "neu"),
                            unsafe_allow_html=True)
            with k3:
                st.markdown(theme.kpi_html("High Impact", str(macro["high_impact_count"])), unsafe_allow_html=True)
            st.write("")
            st.caption("Sentiment scored with VADER (rule-based, offline) \u2014 layered on top of "
                       "keyword-based High/Medium/Low impact tagging.")

        st.write("")
        if not headlines.empty:
            st.markdown('<div class="aq-card">', unsafe_allow_html=True)
            st.dataframe(headlines[["headline", "published", "impact", "sentiment_label", "sentiment_compound"]],
                         use_container_width=True, hide_index=True)
            st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.caption("No headlines fetched this run (feeds may be rate-limited or unreachable).")

# ============================ TAB: PAIRS TRADING ==============================
with tab_pairs:
    st.markdown(theme.section_title_html("\U0001F517", "Pairs Trading \u2014 Semi-Automatic"), unsafe_allow_html=True)
    st.caption(f"Manual candidates + auto-discovered pairs (correlation \u2265 {config.PAIRS_MIN_CORRELATION}).")

    if result is None:
        st.markdown('<div class="aq-card" style="text-align:center; color:#94A3B8; padding:48px;">'
                    'Run the pipeline with "Include pairs trading scan" checked.</div>', unsafe_allow_html=True)
    elif result["pairs"].empty:
        st.markdown('<div class="aq-card" style="text-align:center; color:#94A3B8; padding:24px;">'
                    'No pairs scanned this run \u2014 check the sidebar box and re-run.</div>', unsafe_allow_html=True)
    else:
        pairs_df = result["pairs"]
        signal_count = pairs_df["signal"].notna().sum() if "signal" in pairs_df.columns else 0
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(theme.kpi_html("Pairs Scanned", str(len(pairs_df))), unsafe_allow_html=True)
        with c2:
            st.markdown(theme.kpi_html("Active Signals", str(signal_count),
                                       "divergence detected" if signal_count else None,
                                       "pos" if signal_count else "neu"), unsafe_allow_html=True)
        st.write("")
        st.markdown('<div class="aq-card">', unsafe_allow_html=True)
        st.dataframe(pairs_df, use_container_width=True, hide_index=True)
        st.markdown('</div>', unsafe_allow_html=True)

# ============================ TAB: BACKTEST VALIDATION ========================
with tab_backtest:
    st.markdown(theme.section_title_html("\U0001F52C", "Decision Agent Backtesting Harness"), unsafe_allow_html=True)
    st.caption("Validates whether the COMBINED weighted score beats any single signal alone \u2014 "
               "walk-forward, no lookahead.")

    if bt_result is None:
        st.markdown('<div class="aq-card" style="text-align:center; padding:48px; color:#94A3B8;">'
                    'Click <b>Run Backtest</b> in the sidebar. Fetches ~2 years of history per '
                    'watchlist stock \u2014 can take 30-90 seconds.</div>', unsafe_allow_html=True)
    elif not bt_result.get("valid"):
        st.error(bt_result.get("reason"))
    else:
        st.markdown(f'<div class="aq-card" style="border-left: 3px solid {theme.ACCENT_SOLID};">'
                    f'<span style="color:{theme.TEXT_PRIMARY}; font-weight:600;">'
                    f'{backtest_engine.verdict(bt_result["summary"])}</span></div>', unsafe_allow_html=True)
        st.caption(f"{bt_result['n_observations']} observations \u00b7 {bt_result['symbols_covered']} symbols \u00b7 "
                   f"{bt_result['horizon_days']}-day horizon \u00b7 {bt_result['period']} window")

        score_labels = {"combined": "Combined", "technical": "Technical",
                        "quant": "Quant", "regime": "Regime", "risk_quality": "Risk Quality"}
        cols = st.columns(len(score_labels))
        for col, (key, label) in zip(cols, score_labels.items()):
            s = bt_result["summary"].get(key, {})
            with col:
                if s.get("valid"):
                    sig = "\u2713 significant" if s["ic_significant"] else "not significant"
                    st.markdown(theme.kpi_html(label, f"IC {s['information_coefficient']}", sig,
                                               "pos" if s["ic_significant"] else "neu"), unsafe_allow_html=True)
                else:
                    st.markdown(theme.kpi_html(label, "n/a"), unsafe_allow_html=True)

        st.write("")
        for key, label in score_labels.items():
            s = bt_result["summary"].get(key, {})
            if s.get("valid"):
                with st.expander(f"{label} \u2014 quartile breakdown"):
                    st.dataframe(pd.DataFrame(s["quartile_breakdown"]), use_container_width=True, hide_index=True)
                    st.caption(f"Top-quartile minus bottom-quartile return spread: "
                              f"{s['top_minus_bottom_quartile_spread_pct']}%")

        with st.expander("Raw observation-level data"):
            st.dataframe(bt_result["raw_data"], use_container_width=True, hide_index=True)
            st.download_button("Download as CSV", bt_result["raw_data"].to_csv(index=False),
                               file_name="alphaquant_backtest_raw.csv")

# ============================ TAB: RUN LOG ====================================
with tab_log:
    st.markdown(theme.section_title_html("\U0001F4CB", "Run History"), unsafe_allow_html=True)

    sheets_status = gsheets_sync.connection_status()
    if config.RUN_LOG_BACKEND == "gsheets":
        if sheets_status["connected"]:
            st.markdown(
                f'<div class="aq-card" style="border-left: 3px solid {theme.POSITIVE};">'
                f'{theme.pill_html("\U0001F4C4 PERSISTED", "approved")} &nbsp;'
                f'<span style="color:{theme.TEXT_PRIMARY};">Google Sheets: '
                f'<b>{sheets_status["sheet_name"]}</b> / {sheets_status["worksheet"]} '
                f'({sheets_status["row_count"]} rows) \u2014 survives redeploys.</span></div>',
                unsafe_allow_html=True)
        else:
            st.markdown(
                f'<div class="aq-card" style="border-left: 3px solid {theme.WARNING};">'
                f'{theme.pill_html("LOCAL ONLY", "warning")} &nbsp;'
                f'<span style="color:{theme.TEXT_SECONDARY};">Google Sheets not connected '
                f'({sheets_status["reason"]}). Resets on redeploy \u2014 see DEPLOY.md.</span></div>',
                unsafe_allow_html=True)
    st.write("")

    log_df = reporting.read_log()
    if log_df.empty:
        st.markdown('<div class="aq-card" style="text-align:center; color:#94A3B8; padding:32px;">'
                    'No runs logged yet.</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="aq-card">', unsafe_allow_html=True)
        st.dataframe(log_df.sort_values("run_timestamp", ascending=False),
                     use_container_width=True, hide_index=True)
        st.markdown('</div>', unsafe_allow_html=True)
        st.download_button("Download full run log as CSV", log_df.to_csv(index=False),
                           file_name="run_log_export.csv")

st.divider()
st.caption(
    f"{config.APP_NAME} is a personal, non-professional research tool \u2014 <b>not investment advice</b>. "
    "Every score here is a transparent, rules-based signal with stated assumptions. "
    "Hard-coded risk limits (1% max risk/trade, RR\u22651.5) keep being wrong survivable."
)
