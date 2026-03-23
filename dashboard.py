#!/usr/bin/env python3
"""Trading Analysis Dashboard — Streamlit UI.

Run: streamlit run dashboard.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import json
from datetime import datetime
from decimal import Decimal

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.utils.db import (
    init_db, get_reports, get_watchlist, get_alerts,
    add_watchlist_item, remove_watchlist_item,
)

init_db()

# --- Page config ---
st.set_page_config(
    page_title="Trading Analysis Platform",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Sidebar navigation ---
st.sidebar.title("📊 Trading Platform")
page = st.sidebar.radio(
    "Navigate",
    ["🔍 Analyze", "📋 Reports", "👁 Watchlist", "🔔 Alerts", "🌍 Macro"],
    label_visibility="collapsed",
)


# ═══════════════════════════════════════════════════════════════
# Page: Analyze
# ═══════════════════════════════════════════════════════════════
if page == "🔍 Analyze":
    st.title("🔍 Stock Analysis")

    col1, col2 = st.columns([3, 1])
    with col1:
        symbol = st.text_input("Enter ticker symbol", value="AAPL", max_chars=10).upper()
    with col2:
        generate_pdf = st.checkbox("PDF export", value=False)

    if st.button("Run Analysis", type="primary", use_container_width=True):
        with st.spinner(f"Analyzing {symbol}..."):
            try:
                from src.orchestrator import analyze_stock
                report = analyze_stock(symbol, export=True, pdf=generate_pdf)

                # Verdict banner
                verdict_colors = {
                    "Strong Buy": "#16a34a", "Buy": "#22c55e",
                    "Hold": "#ca8a04",
                    "Sell": "#ef4444", "Strong Sell": "#dc2626",
                }
                color = verdict_colors.get(report.verdict.value, "#6b7280")

                st.markdown(f"""
                <div style="background: {color}15; border: 2px solid {color};
                    border-radius: 12px; padding: 20px; text-align: center; margin: 16px 0;">
                    <h1 style="color: {color}; margin: 0;">{report.verdict.value}</h1>
                    <p style="margin: 8px 0 0;">
                        Confidence: <strong>{report.confidence}</strong> &nbsp;|&nbsp;
                        Risk: <strong>{report.risk_rating.value}/5</strong> &nbsp;|&nbsp;
                        Price: <strong>${report.current_price}</strong>
                    </p>
                </div>
                """, unsafe_allow_html=True)

                # Metrics row
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Price", f"${report.current_price}")
                c2.metric("Sentiment", f"{report.sentiment_score}")
                c3.metric("Risk", f"{report.risk_rating.value}/5")
                c4.metric("Confidence", report.confidence)

                # Reasoning
                with st.expander("📝 Analysis Reasoning", expanded=True):
                    for r in report.reasoning:
                        st.markdown(f"- {r}")

                # Sections
                for section in report.sections:
                    with st.expander(f"📌 {section.title}", expanded=False):
                        st.write(section.content)
                        if section.data:
                            data_df = pd.DataFrame([
                                {"Metric": k.replace("_", " ").title(), "Value": _fmt(v)}
                                for k, v in section.data.items()
                            ])
                            st.dataframe(data_df, use_container_width=True, hide_index=True)

                # Risks
                if report.risks:
                    st.warning("**Identified Risks:**\n" + "\n".join(f"- {r}" for r in report.risks))

                # Price chart
                _render_price_chart(symbol)

                st.info(report.DISCLAIMER)

            except Exception as e:
                st.error(f"Analysis failed: {e}")


# ═══════════════════════════════════════════════════════════════
# Page: Reports
# ═══════════════════════════════════════════════════════════════
elif page == "📋 Reports":
    st.title("📋 Saved Reports")

    col1, col2 = st.columns(2)
    with col1:
        filter_symbol = st.text_input("Filter by symbol", value="").upper()
    with col2:
        limit = st.selectbox("Show", [10, 25, 50, 100], index=0)

    reports = get_reports(
        symbol=filter_symbol if filter_symbol else None,
        limit=limit,
    )

    if not reports:
        st.info("No reports yet. Run an analysis first.")
    else:
        for r in reports:
            verdict = r.get("verdict", "N/A")
            risk = r.get("risk_rating", "N/A")
            date = r.get("created_at", "")[:16]

            verdict_emoji = {"Strong Buy": "🟢", "Buy": "🟢", "Hold": "🟡", "Sell": "🔴", "Strong Sell": "🔴"}
            emoji = verdict_emoji.get(verdict, "⚪")

            with st.expander(f"{emoji} **{r['symbol']}** — {verdict} (Risk {risk}/5) — {date}"):
                try:
                    content = json.loads(r["content"])
                    if "reasoning" in content:
                        st.markdown("**Reasoning:**")
                        for reason in content["reasoning"]:
                            st.markdown(f"- {reason}")
                    if "sections" in content:
                        for sec in content["sections"]:
                            st.markdown(f"**{sec['title']}:** {sec['content']}")
                except (json.JSONDecodeError, KeyError):
                    st.text(r.get("content", "")[:500])


# ═══════════════════════════════════════════════════════════════
# Page: Watchlist
# ═══════════════════════════════════════════════════════════════
elif page == "👁 Watchlist":
    st.title("👁 Watchlist")

    # Add stock
    col1, col2 = st.columns([3, 1])
    with col1:
        new_symbol = st.text_input("Add ticker", placeholder="MSFT").upper()
    with col2:
        st.write("")
        st.write("")
        if st.button("Add", use_container_width=True) and new_symbol:
            add_watchlist_item(new_symbol)
            st.rerun()

    # Scan button
    watchlist = get_watchlist()

    if watchlist:
        if st.button("🔄 Scan All Stocks", type="primary", use_container_width=True):
            with st.spinner(f"Scanning {len(watchlist)} stocks..."):
                from src.scheduler import run_watchlist_scan
                result = run_watchlist_scan()
                st.success(f"Scanned {result['scanned']} stocks. {len(result.get('alerts', []))} alerts.")
                st.rerun()

        st.divider()

        # Show watchlist with latest verdicts
        for item in watchlist:
            sym = item["symbol"]
            latest = get_reports(symbol=sym, limit=1)

            col1, col2, col3, col4 = st.columns([2, 2, 2, 1])
            with col1:
                st.markdown(f"### {sym}")
            with col2:
                if latest:
                    verdict = latest[0].get("verdict", "—")
                    verdict_emoji = {"Strong Buy": "🟢", "Buy": "🟢", "Hold": "🟡", "Sell": "🔴", "Strong Sell": "🔴"}
                    st.markdown(f"{verdict_emoji.get(verdict, '⚪')} **{verdict}**")
                else:
                    st.markdown("⚪ **No report yet**")
            with col3:
                if latest:
                    risk = latest[0].get("risk_rating", "—")
                    st.markdown(f"Risk: **{risk}/5**")
                else:
                    st.markdown("—")
            with col4:
                if st.button("✕", key=f"rm_{sym}"):
                    remove_watchlist_item(sym)
                    st.rerun()
    else:
        st.info("Watchlist is empty. Add tickers above.")


# ═══════════════════════════════════════════════════════════════
# Page: Alerts
# ═══════════════════════════════════════════════════════════════
elif page == "🔔 Alerts":
    st.title("🔔 Alerts")

    alerts = get_alerts(limit=50)

    if not alerts:
        st.info("No alerts yet. Alerts are generated when watchlist scans detect signal changes.")
    else:
        # Summary
        critical = sum(1 for a in alerts if a["severity"] == "critical")
        warning = sum(1 for a in alerts if a["severity"] == "warning")
        info = sum(1 for a in alerts if a["severity"] == "info")

        c1, c2, c3 = st.columns(3)
        c1.metric("Critical", critical)
        c2.metric("Warnings", warning)
        c3.metric("Info", info)

        st.divider()

        for a in alerts:
            severity_icon = {"critical": "🔴", "warning": "🟡", "info": "🔵"}
            icon = severity_icon.get(a["severity"], "⚪")
            date = a["created_at"][:16]

            st.markdown(
                f"{icon} **{a['symbol']}** — `{a['alert_type']}` — {a['message']}  \n"
                f"<small style='color: #888;'>{date}</small>",
                unsafe_allow_html=True,
            )


# ═══════════════════════════════════════════════════════════════
# Page: Macro
# ═══════════════════════════════════════════════════════════════
elif page == "🌍 Macro":
    st.title("🌍 Macro Environment")

    with st.spinner("Fetching macro data..."):
        try:
            from src.data.gateway import DataGateway
            gw = DataGateway()
            snapshot = gw.get_macro_snapshot()

            if snapshot:
                # Regime banner
                regime_colors = {
                    "normal": "#22c55e", "strong_labor": "#3b82f6",
                    "high_volatility": "#f59e0b", "tight_monetary": "#f97316",
                    "recession_warning": "#dc2626",
                }
                color = regime_colors.get(snapshot.regime, "#6b7280")
                st.markdown(f"""
                <div style="background: {color}15; border: 2px solid {color};
                    border-radius: 12px; padding: 16px; text-align: center; margin-bottom: 16px;">
                    <h2 style="color: {color}; margin: 0;">Regime: {snapshot.regime.replace('_', ' ').title()}</h2>
                    <p>{"⚠️ Yield curve inverted — recession signal" if snapshot.yield_curve_inverted else "✅ Yield curve normal"}</p>
                </div>
                """, unsafe_allow_html=True)

                # Key metrics
                c1, c2, c3, c4, c5 = st.columns(5)
                c1.metric("Fed Funds Rate", f"{snapshot.fed_funds_rate}%" if snapshot.fed_funds_rate else "—")
                c2.metric("10Y Treasury", f"{snapshot.treasury_10y}%" if snapshot.treasury_10y else "—")
                c3.metric("VIX", f"{snapshot.vix}" if snapshot.vix else "—")
                c4.metric("Unemployment", f"{snapshot.unemployment_rate}%" if snapshot.unemployment_rate else "—")
                c5.metric("GDP Growth", f"{snapshot.gdp_growth}%" if snapshot.gdp_growth else "—")

                st.divider()

                c1, c2 = st.columns(2)
                with c1:
                    st.metric("2Y Treasury", f"{snapshot.treasury_2y}%" if snapshot.treasury_2y else "—")
                    st.metric("CPI (YoY)", f"{snapshot.cpi_yoy}%" if snapshot.cpi_yoy else "—")
                with c2:
                    spread = snapshot.yield_spread_10y2y
                    st.metric("10Y-2Y Spread", f"{spread}%" if spread else "—",
                              delta="Inverted" if snapshot.yield_curve_inverted else "Normal")
                    st.metric("Dollar Index", f"{snapshot.dollar_index}" if snapshot.dollar_index else "—")
            else:
                st.warning("Could not load macro data. Check Alpha Vantage API key.")
        except Exception as e:
            st.error(f"Error loading macro data: {e}")


# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════

def _fmt(val) -> str:
    if isinstance(val, list):
        return ", ".join(str(v) for v in val) if val else "—"
    if isinstance(val, bool):
        return "Yes" if val else "No"
    if val is None or str(val) == "None":
        return "—"
    return str(val)


def _render_price_chart(symbol: str) -> None:
    try:
        from src.data.gateway import DataGateway
        gw = DataGateway()
        df = gw.get_historical(symbol, period_days=180)
        if df is None or df.empty:
            return

        fig = go.Figure()
        fig.add_trace(go.Candlestick(
            x=df["date"], open=df["open"], high=df["high"],
            low=df["low"], close=df["close"], name="Price",
        ))

        # Add SMA lines if enough data
        if len(df) >= 20:
            df["sma20"] = df["close"].rolling(20).mean()
            fig.add_trace(go.Scatter(
                x=df["date"], y=df["sma20"], mode="lines",
                name="SMA(20)", line=dict(color="#3b82f6", width=1),
            ))
        if len(df) >= 50:
            df["sma50"] = df["close"].rolling(50).mean()
            fig.add_trace(go.Scatter(
                x=df["date"], y=df["sma50"], mode="lines",
                name="SMA(50)", line=dict(color="#f59e0b", width=1),
            ))

        fig.update_layout(
            title=f"{symbol} Price Chart (6 months)",
            xaxis_title="Date", yaxis_title="Price ($)",
            template="plotly_white", height=450,
            xaxis_rangeslider_visible=False,
        )
        st.plotly_chart(fig, use_container_width=True)
    except Exception:
        pass
