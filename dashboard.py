#!/usr/bin/env python3
"""Trading Analysis Dashboard — MoneyFlow-Inspired Dark UI.

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

# ═══════════════════════════════════════════════════════════════
# Page Config + Global CSS
# ═══════════════════════════════════════════════════════════════

st.set_page_config(page_title="Trading Platform", page_icon="📊", layout="wide")

st.markdown("""
<style>
    /* Global dark card style */
    .dark-card {
        background: #1a1a1a; border: 1px solid #2a2a2a; border-radius: 12px;
        padding: 20px; margin-bottom: 16px;
    }
    .dark-card h3 { margin-top: 0; color: #e5e5e5; }

    /* Net flow badges */
    .badge-inflow { background: #16a34a22; color: #22c55e; padding: 4px 12px;
        border-radius: 20px; font-weight: 700; font-size: 13px; }
    .badge-outflow { background: #dc262622; color: #ef4444; padding: 4px 12px;
        border-radius: 20px; font-weight: 700; font-size: 13px; }

    /* Status labels (economic page) */
    .status-green { color: #22c55e; font-weight: 700; }
    .status-orange { color: #f59e0b; font-weight: 700; }
    .status-red { color: #ef4444; font-weight: 700; }
    .status-gray { color: #9ca3af; font-weight: 700; }

    /* Opportunity score badge */
    .score-badge {
        display: inline-block; padding: 6px 14px; border-radius: 8px;
        font-weight: 800; font-size: 18px;
    }
    .score-excellent { background: #22c55e33; color: #22c55e; border: 1px solid #22c55e; }
    .score-good { background: #f59e0b33; color: #f59e0b; border: 1px solid #f59e0b; }
    .score-fair { background: #6b728033; color: #9ca3af; border: 1px solid #6b7280; }
    .score-poor { background: #ef444433; color: #ef4444; border: 1px solid #ef4444; }

    /* Signal card (gold border for top) */
    .signal-card {
        background: #1a1a1a; border: 1px solid #2a2a2a; border-radius: 12px;
        padding: 16px; margin-bottom: 12px;
    }
    .signal-card-top { border-color: #f59e0b; }

    /* Verdict banners */
    .verdict-buy { background: #16a34a18; border: 2px solid #22c55e; }
    .verdict-sell { background: #dc262618; border: 2px solid #ef4444; }
    .verdict-hold { background: #ca8a0418; border: 2px solid #f59e0b; }

    /* Smaller text */
    .text-sm { font-size: 13px; color: #9ca3af; }
    .text-lg { font-size: 20px; font-weight: 700; }
    .text-green { color: #22c55e; }
    .text-red { color: #ef4444; }
    .text-orange { color: #f59e0b; }

    /* Hide streamlit branding */
    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }

    /* Disclaimer */
    .disclaimer { text-align: center; font-size: 11px; color: #6b7280; padding: 12px; }

    /* Eco indicator card */
    .eco-card {
        background: #1a1a1a; border: 1px solid #2a2a2a; border-radius: 12px;
        padding: 16px; text-align: center;
    }
    .eco-card .value { font-size: 24px; font-weight: 800; color: #e5e5e5; }
    .eco-card .label { font-size: 12px; color: #9ca3af; margin-top: 4px; }
    .eco-card .change { font-size: 13px; margin-top: 4px; }

    /* Category badge */
    .cat-badge {
        display: inline-block; padding: 2px 8px; border-radius: 6px;
        font-size: 11px; font-weight: 600; margin-bottom: 6px;
    }
</style>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════
# Helpers (must be defined before page logic)
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
        if len(df) >= 20:
            df["sma20"] = df["close"].rolling(20).mean()
            fig.add_trace(go.Scatter(x=df["date"], y=df["sma20"], mode="lines",
                                     name="SMA(20)", line=dict(color="#3b82f6", width=1)))
        if len(df) >= 50:
            df["sma50"] = df["close"].rolling(50).mean()
            fig.add_trace(go.Scatter(x=df["date"], y=df["sma50"], mode="lines",
                                     name="SMA(50)", line=dict(color="#f59e0b", width=1)))

        fig.update_layout(
            title=f"{symbol} — 6 Month Price",
            template="plotly_dark", height=400,
            plot_bgcolor="#0a0a0a", paper_bgcolor="#0a0a0a",
            xaxis_rangeslider_visible=False,
        )
        st.plotly_chart(fig, use_container_width=True)
    except Exception:
        pass


def _compute_opportunity_for(symbol: str):
    try:
        from src.data.gateway import DataGateway
        from src.analysis import technical
        from src.analysis.opportunity import compute_opportunity

        gw = DataGateway()
        hist = gw.get_historical(symbol, period_days=60)
        tech = None
        if hist is not None and not hist.empty:
            tech = technical.analyze(symbol, hist)

        options = gw.get_options_summary(symbol)
        pcr = options.put_call_ratio if options else None

        insider = gw.get_insider_summary(symbol)
        net_buy = None
        if insider and insider.total_buys > insider.total_sells:
            net_buy = True
        elif insider and insider.total_sells > insider.total_buys:
            net_buy = False

        return compute_opportunity(symbol, tech, pcr, net_buy)
    except Exception:
        return None


def _macro_status(indicator: str, value) -> tuple[str, str]:
    if value is None:
        return "—", "status-gray"
    v = float(value)
    if indicator == "inflation":
        if v > 4: return "Elevated", "status-red"
        if v > 2.5: return "Moderate", "status-orange"
        return "Low", "status-green"
    if indicator == "employment":
        if v < 4: return "Strong", "status-green"
        if v < 6: return "Moderate", "status-orange"
        return "Weak", "status-red"
    if indicator == "fed":
        if v > 5: return "Tightening", "status-red"
        if v > 3: return "Hold Steady", "status-orange"
        return "Easing", "status-green"
    if indicator == "sentiment":
        if v < 15: return "Bullish", "status-green"
        if v < 25: return "Neutral", "status-orange"
        return "Bearish", "status-red"
    return "—", "status-gray"


# ═══════════════════════════════════════════════════════════════
# Navigation
# ═══════════════════════════════════════════════════════════════

page = st.sidebar.radio(
    "Navigation",
    ["🏠 Home", "📊 Markets", "⚡ Signals", "📈 Economic", "🔬 Backtest", "💼 Portfolio", "📓 Journal", "📋 Reports", "🔔 Alerts"],
    label_visibility="collapsed",
)

st.sidebar.markdown("---")
st.sidebar.markdown('<p class="text-sm">ℹ For informational purposes only.<br>Not financial advice.</p>', unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════
# HOME — Analyze + Watchlist
# ═══════════════════════════════════════════════════════════════
if page == "🏠 Home":
    st.title("🏠 Home")

    # Analyze section
    col1, col2, col3 = st.columns([4, 1, 1])
    with col1:
        symbol = st.text_input("Ticker", value="AAPL", max_chars=10, label_visibility="collapsed",
                               placeholder="Enter ticker (e.g. AAPL)").upper()
    with col2:
        pdf_opt = st.checkbox("PDF", value=False)
    with col3:
        run_btn = st.button("Analyze", type="primary", use_container_width=True)

    if run_btn and symbol:
        with st.spinner(f"Analyzing {symbol}..."):
            try:
                from src.orchestrator import analyze_stock
                report = analyze_stock(symbol, export=True, pdf=pdf_opt)

                # Verdict banner
                v = report.verdict.value.lower()
                cls = "verdict-buy" if "buy" in v else "verdict-sell" if "sell" in v else "verdict-hold"
                color = "#22c55e" if "buy" in v else "#ef4444" if "sell" in v else "#f59e0b"

                st.markdown(f"""
                <div class="dark-card {cls}" style="text-align:center;">
                    <div style="font-size:36px; font-weight:800; color:{color};">{report.verdict.value}</div>
                    <div style="display:flex; justify-content:center; gap:32px; margin-top:12px;">
                        <div><span class="text-sm">Price</span><br><span class="text-lg">${report.current_price}</span></div>
                        <div><span class="text-sm">Confidence</span><br><span class="text-lg">{report.confidence}</span></div>
                        <div><span class="text-sm">Risk</span><br><span class="text-lg">{report.risk_rating.value}/5</span></div>
                        <div><span class="text-sm">Sentiment</span><br><span class="text-lg">{report.sentiment_score}</span></div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                # Reasoning
                with st.expander("📝 Reasoning", expanded=True):
                    for r in report.reasoning:
                        st.markdown(f"- {r}")

                # Price chart
                _render_price_chart(symbol)

                # Sections
                for section in report.sections:
                    with st.expander(f"📌 {section.title}"):
                        st.write(section.content)
                        if section.data:
                            df = pd.DataFrame([
                                {"Metric": k.replace("_", " ").title(), "Value": _fmt(v)}
                                for k, v in section.data.items()
                            ])
                            st.dataframe(df, use_container_width=True, hide_index=True)

                if report.risks:
                    st.markdown(f"""<div class="dark-card" style="border-left:4px solid #ef4444;">
                        <h3>⚠ Risks</h3>{''.join(f'<p class="text-red">• {r}</p>' for r in report.risks)}
                    </div>""", unsafe_allow_html=True)

                st.markdown(f'<p class="disclaimer">{report.DISCLAIMER}</p>', unsafe_allow_html=True)
            except Exception as e:
                st.error(f"Analysis failed: {e}")

    # Watchlist section
    st.markdown("---")
    st.subheader("👁 Watchlist")

    col1, col2 = st.columns([4, 1])
    with col1:
        new_sym = st.text_input("Add to watchlist", placeholder="MSFT", label_visibility="collapsed").upper()
    with col2:
        if st.button("Add", use_container_width=True) and new_sym:
            add_watchlist_item(new_sym)
            st.rerun()

    watchlist = get_watchlist()
    if watchlist:
        cols = st.columns(min(len(watchlist), 4))
        for i, item in enumerate(watchlist):
            sym = item["symbol"]
            latest = get_reports(symbol=sym, limit=1)
            verdict = latest[0]["verdict"] if latest else "—"
            v_color = "#22c55e" if "Buy" in str(verdict) else "#ef4444" if "Sell" in str(verdict) else "#f59e0b"

            with cols[i % 4]:
                st.markdown(f"""<div class="dark-card" style="text-align:center;">
                    <div style="font-size:18px; font-weight:700;">{sym}</div>
                    <div style="color:{v_color}; font-weight:700; font-size:14px;">{verdict}</div>
                </div>""", unsafe_allow_html=True)
                if st.button("✕", key=f"rm_{sym}"):
                    remove_watchlist_item(sym)
                    st.rerun()
    else:
        st.info("Watchlist empty. Add tickers above.")


# ═══════════════════════════════════════════════════════════════
# MARKETS — Sector Flows
# ═══════════════════════════════════════════════════════════════
elif page == "📊 Markets":
    st.title("📊 Markets")

    tab_movers, tab_sectors = st.tabs(["Movers", "Sectors"])

    with tab_sectors:
        period_map = {"1W": "5d", "1M": "1mo", "3M": "3mo", "6M": "6mo", "1Y": "1y"}
        period_tabs = st.tabs(list(period_map.keys()))

        for i, (label, yf_period) in enumerate(period_map.items()):
            with period_tabs[i]:
                with st.spinner(f"Loading sector flows ({label})..."):
                    from src.data.gateway import DataGateway
                    gw = DataGateway()
                    flows = gw.get_sector_flows(period=yf_period)

                if not flows:
                    st.warning("Could not load sector data.")
                    continue

                # Total market flow summary
                inflows = [f for f in flows if f["change_pct"] > 0]
                outflows = [f for f in flows if f["change_pct"] < 0]
                net = sum(f["change_pct"] for f in flows)
                net_label = "NET INFLOW" if net > 0 else "NET OUTFLOW"
                net_badge = "badge-inflow" if net > 0 else "badge-outflow"
                net_color = "text-green" if net > 0 else "text-red"

                st.markdown(f"""<div class="dark-card">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <h3 style="margin:0;">Total Market Flow</h3>
                        <span class="{net_badge}">{'↑' if net > 0 else '↓'} {net_label}</span>
                    </div>
                    <div style="display:flex; gap:40px; margin-top:12px;">
                        <div><span class="text-sm">Net Change</span><br>
                            <span class="text-lg {net_color}">{net:+.1f}%</span></div>
                        <div><span class="text-sm">Inflows</span><br>
                            <span class="text-lg text-green">{len(inflows)} sectors</span></div>
                        <div><span class="text-sm">Outflows</span><br>
                            <span class="text-lg text-red">{len(outflows)} sectors</span></div>
                    </div>
                </div>""", unsafe_allow_html=True)

                # Horizontal bar chart
                df = pd.DataFrame(flows)
                colors = ["#22c55e" if x > 0 else "#ef4444" for x in df["change_pct"]]

                fig = go.Figure(go.Bar(
                    y=df["sector"], x=df["change_pct"],
                    orientation="h", marker_color=colors,
                    text=[f"{x:+.1f}%" for x in df["change_pct"]],
                    textposition="outside",
                ))
                fig.update_layout(
                    title="Flow Distribution by Sector",
                    template="plotly_dark", height=450,
                    plot_bgcolor="#0a0a0a", paper_bgcolor="#0a0a0a",
                    yaxis=dict(autorange="reversed"),
                    xaxis=dict(title="Change %", zeroline=True, zerolinecolor="#333"),
                    margin=dict(l=180),
                )
                st.plotly_chart(fig, use_container_width=True)

    with tab_movers:
        st.markdown('<p class="text-sm">Top movers from your watchlist</p>', unsafe_allow_html=True)
        watchlist = get_watchlist()
        if not watchlist:
            st.info("Add stocks to your watchlist to see movers.")
        else:
            movers = []
            for item in watchlist:
                try:
                    import yfinance as yf
                    t = yf.Ticker(item["symbol"])
                    info = t.info
                    change = info.get("regularMarketChangePercent", 0) or 0
                    movers.append({
                        "symbol": item["symbol"],
                        "price": info.get("regularMarketPrice", 0),
                        "change_pct": round(change, 2),
                        "volume": info.get("regularMarketVolume", 0),
                    })
                except Exception:
                    continue

            if movers:
                movers.sort(key=lambda x: abs(x["change_pct"]), reverse=True)
                for m in movers:
                    color = "text-green" if m["change_pct"] > 0 else "text-red"
                    arrow = "↑" if m["change_pct"] > 0 else "↓"
                    st.markdown(f"""<div class="dark-card" style="display:flex; justify-content:space-between; align-items:center;">
                        <div><span style="font-size:18px; font-weight:700;">{m['symbol']}</span>
                            <span class="text-sm" style="margin-left:12px;">${m['price']}</span></div>
                        <span class="{color}" style="font-size:18px; font-weight:700;">{arrow} {m['change_pct']:+.2f}%</span>
                    </div>""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════
# SIGNALS — Opportunity Scores + Unusual Activity
# ═══════════════════════════════════════════════════════════════
elif page == "⚡ Signals":
    st.title("⚡ Signals")

    tab_signals, tab_opps = st.tabs(["Signals", "Opportunities"])

    with tab_opps:
        # Opportunity score explanation
        with st.expander("ℹ How Opportunity Scores Work"):
            st.markdown("""
            Opportunity scores combine four factors:
            - 📊 **Volume Score (25%)** — Recent volume vs average
            - 📈 **Price Score (25%)** — Price momentum and patterns
            - 💰 **Flow Score (25%)** — Money flow trends (options + insiders)
            - ⚖️ **Risk/Reward (25%)** — Distance to support/resistance
            """)
            st.markdown('<p class="text-sm">Scores are estimates for informational purposes only. Not financial advice.</p>', unsafe_allow_html=True)

        watchlist = get_watchlist()
        if not watchlist:
            st.info("Add stocks to watchlist to see opportunity scores.")
        else:
            st.markdown("**Unusual Activity** — Ranked by opportunity score")
            scores = []
            for item in watchlist:
                sym = item["symbol"]
                with st.spinner(f"Scoring {sym}..."):
                    score = _compute_opportunity_for(sym)
                    if score:
                        scores.append(score)

            scores.sort(key=lambda s: s.total_score, reverse=True)

            for rank, s in enumerate(scores, 1):
                score_cls = ("score-excellent" if s.label == "Excellent"
                             else "score-good" if s.label == "Good"
                             else "score-poor" if s.label == "Poor"
                             else "score-fair")
                card_cls = "signal-card signal-card-top" if rank == 1 else "signal-card"

                st.markdown(f"""<div class="{card_cls}">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <div>
                            <span style="color:#9ca3af;">#{rank}</span>
                            <span style="font-size:18px; font-weight:700; margin-left:8px;">{s.symbol}</span>
                        </div>
                        <span class="score-badge {score_cls}">★ {s.total_score}</span>
                    </div>
                    <div style="color:#9ca3af; font-size:12px; margin-top:2px;">{s.label}</div>
                    <div style="display:flex; gap:24px; margin-top:12px;">
                        <div><span class="text-sm">Strategy</span><br>
                            <span class="text-orange" style="font-weight:600;">{s.strategy}</span></div>
                        <div><span class="text-sm">Risk/Reward</span><br>
                            <span style="font-weight:600;">{s.risk_reward_ratio}</span></div>
                    </div>
                    <div style="display:flex; gap:24px; margin-top:8px;">
                        <div><span class="text-sm">Vol</span> <b>{s.volume_score}/25</b></div>
                        <div><span class="text-sm">Price</span> <b>{s.price_score}/25</b></div>
                        <div><span class="text-sm">Flow</span> <b>{s.flow_score}/25</b></div>
                        <div><span class="text-sm">R/R</span> <b>{s.risk_reward_score}/25</b></div>
                    </div>
                </div>""", unsafe_allow_html=True)

    with tab_signals:
        st.markdown("**Latest Signals** from watchlist analysis")
        watchlist = get_watchlist()
        if not watchlist:
            st.info("Add stocks to watchlist to see signals.")
        else:
            for item in watchlist:
                sym = item["symbol"]
                latest = get_reports(symbol=sym, limit=1)
                if not latest:
                    continue
                try:
                    content = json.loads(latest[0]["content"])
                    verdict = latest[0].get("verdict", "—")
                    risk = latest[0].get("risk_rating", "—")
                    v_color = "#22c55e" if "Buy" in str(verdict) else "#ef4444" if "Sell" in str(verdict) else "#f59e0b"

                    reasoning = content.get("reasoning", [])
                    st.markdown(f"""<div class="dark-card">
                        <div style="display:flex; justify-content:space-between;">
                            <span style="font-size:18px; font-weight:700;">{sym}</span>
                            <span style="color:{v_color}; font-weight:700;">{verdict} | Risk {risk}/5</span>
                        </div>
                        <div class="text-sm" style="margin-top:8px;">
                            {'<br>'.join(f'• {r}' for r in reasoning[:4])}
                        </div>
                    </div>""", unsafe_allow_html=True)
                except (json.JSONDecodeError, KeyError):
                    continue


# ═══════════════════════════════════════════════════════════════
# ECONOMIC — Macro Dashboard
# ═══════════════════════════════════════════════════════════════
elif page == "📈 Economic":
    st.title("📈 Economic Data")

    with st.spinner("Loading economic data..."):
        try:
            from src.data.gateway import DataGateway
            gw = DataGateway()
            snapshot = gw.get_macro_snapshot()
        except Exception:
            snapshot = None

    if not snapshot:
        st.warning("Could not load macro data.")
    else:
        # Economic Overview card
        inflation_status = _macro_status("inflation", snapshot.cpi_yoy)
        employment_status = _macro_status("employment", snapshot.unemployment_rate)
        fed_status = _macro_status("fed", snapshot.fed_funds_rate)
        sentiment_status = _macro_status("sentiment", snapshot.vix)

        st.markdown(f"""<div class="dark-card">
            <div style="display:flex; align-items:center; gap:12px; margin-bottom:16px;">
                <span style="font-size:24px;">📈</span>
                <div><b style="font-size:18px;">Economic Overview</b><br>
                    <span class="text-sm">Based on latest indicators</span></div>
            </div>
            <hr style="border-color:#2a2a2a;">
            <table style="width:100%;">
                <tr><td style="padding:10px 0;">📊 Inflation</td>
                    <td style="text-align:right;"><span class="{inflation_status[1]}">{inflation_status[0]}</span></td></tr>
                <tr><td style="padding:10px 0;">👥 Employment</td>
                    <td style="text-align:right;"><span class="{employment_status[1]}">{employment_status[0]}</span></td></tr>
                <tr><td style="padding:10px 0;">% Fed Policy</td>
                    <td style="text-align:right;"><span class="{fed_status[1]}">{fed_status[0]}</span></td></tr>
                <tr><td style="padding:10px 0;">🌐 Sentiment</td>
                    <td style="text-align:right;"><span class="{sentiment_status[1]}">{sentiment_status[0]}</span></td></tr>
            </table>
        </div>""", unsafe_allow_html=True)

        # Key metrics grid
        st.markdown("### Key Indicators")
        indicators = [
            ("Fed Funds Rate", f"{snapshot.fed_funds_rate}%" if snapshot.fed_funds_rate else "—", "Rates", "#3b82f6"),
            ("10Y Treasury", f"{snapshot.treasury_10y}%" if snapshot.treasury_10y else "—", "Rates", "#3b82f6"),
            ("2Y Treasury", f"{snapshot.treasury_2y}%" if snapshot.treasury_2y else "—", "Rates", "#3b82f6"),
            ("VIX", f"{snapshot.vix}" if snapshot.vix else "—", "Sentiment", "#f59e0b"),
            ("Unemployment", f"{snapshot.unemployment_rate}%" if snapshot.unemployment_rate else "—", "Employment", "#22c55e"),
            ("GDP Growth", f"{snapshot.gdp_growth}%" if snapshot.gdp_growth else "—", "Growth", "#a855f7"),
            ("CPI (YoY)", f"{snapshot.cpi_yoy}%" if snapshot.cpi_yoy else "—", "Inflation", "#ef4444"),
            ("Dollar Index", f"{snapshot.dollar_index}" if snapshot.dollar_index else "—", "Currency", "#06b6d4"),
        ]

        cat_colors = {
            "Rates": "#3b82f6", "Sentiment": "#f59e0b", "Employment": "#22c55e",
            "Growth": "#a855f7", "Inflation": "#ef4444", "Currency": "#06b6d4",
        }

        cols = st.columns(4)
        for i, (name, value, cat, color) in enumerate(indicators):
            with cols[i % 4]:
                st.markdown(f"""<div class="eco-card">
                    <span class="cat-badge" style="background:{color}22; color:{color};">{cat}</span>
                    <div style="font-weight:600; font-size:14px; color:#e5e5e5;">{name}</div>
                    <div class="value">{value}</div>
                </div>""", unsafe_allow_html=True)

        # Yield curve status
        spread = snapshot.yield_spread_10y2y
        inverted = snapshot.yield_curve_inverted
        spread_color = "text-red" if inverted else "text-green"
        spread_icon = "⚠️" if inverted else "✅"

        st.markdown(f"""<div class="dark-card">
            <h3>{spread_icon} Yield Curve</h3>
            <div style="display:flex; gap:32px;">
                <div><span class="text-sm">10Y-2Y Spread</span><br>
                    <span class="text-lg {spread_color}">{spread}%</span></div>
                <div><span class="text-sm">Status</span><br>
                    <span class="text-lg {spread_color}">{'INVERTED' if inverted else 'NORMAL'}</span></div>
            </div>
        </div>""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════
# REPORTS
# ═══════════════════════════════════════════════════════════════
elif page == "📋 Reports":
    st.title("📋 Reports")

    col1, col2 = st.columns([3, 1])
    with col1:
        filter_sym = st.text_input("Filter by symbol", value="").upper()
    with col2:
        limit = st.selectbox("Show", [10, 25, 50], index=0)

    reports = get_reports(symbol=filter_sym if filter_sym else None, limit=limit)
    if not reports:
        st.info("No reports yet.")
    else:
        for r in reports:
            verdict = r.get("verdict", "—")
            v_color = "#22c55e" if "Buy" in str(verdict) else "#ef4444" if "Sell" in str(verdict) else "#f59e0b"
            date = r.get("created_at", "")[:16]

            with st.expander(f"**{r['symbol']}** — {verdict} — {date}"):
                try:
                    content = json.loads(r["content"])
                    for reason in content.get("reasoning", []):
                        st.markdown(f"- {reason}")
                except (json.JSONDecodeError, KeyError):
                    st.text(str(r.get("content", ""))[:500])


# ═══════════════════════════════════════════════════════════════
# ALERTS
# ═══════════════════════════════════════════════════════════════
elif page == "🔔 Alerts":
    st.title("🔔 Alerts")

    alerts = get_alerts(limit=50)
    if not alerts:
        st.info("No alerts yet. Alerts appear after watchlist scans detect signal changes.")
    else:
        critical = sum(1 for a in alerts if a["severity"] == "critical")
        warning = sum(1 for a in alerts if a["severity"] == "warning")

        c1, c2, c3 = st.columns(3)
        c1.metric("Critical", critical)
        c2.metric("Warnings", warning)
        c3.metric("Total", len(alerts))

        for a in alerts:
            sev_color = "#ef4444" if a["severity"] == "critical" else "#f59e0b" if a["severity"] == "warning" else "#3b82f6"
            st.markdown(f"""<div class="dark-card" style="border-left:4px solid {sev_color};">
                <div style="display:flex; justify-content:space-between;">
                    <b>{a['symbol']}</b>
                    <span class="text-sm">{a['created_at'][:16]}</span>
                </div>
                <div style="margin-top:4px;">{a['message']}</div>
                <span class="text-sm">{a['alert_type']}</span>
            </div>""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════
# BACKTEST — Signal Explorer + Signal Accuracy
# ═══════════════════════════════════════════════════════════════
elif page == "🔬 Backtest":
    st.title("🔬 Signal Backtester")

    tab_explorer, tab_accuracy = st.tabs(["Signal Explorer", "Signal Accuracy"])

    with tab_explorer:
        col1, col2, col3 = st.columns([2, 2, 1])
        with col1:
            bt_symbol = st.text_input("Ticker", value="AAPL", key="bt_sym").upper()
        with col2:
            from src.analysis.backtester import SIGNALS
            bt_signal = st.selectbox("Signal", list(SIGNALS.keys()),
                                      format_func=lambda x: f"{x} — {SIGNALS[x]['description']}")
        with col3:
            bt_hold = st.selectbox("Hold days", [7, 14, 30, 60, 90], index=2)

        if st.button("Run Backtest", type="primary", use_container_width=True):
            with st.spinner(f"Backtesting {bt_signal} on {bt_symbol}..."):
                from src.data.gateway import DataGateway
                from src.analysis.backtester import backtest_signal

                gw = DataGateway()
                hist = gw.get_historical(bt_symbol, period_days=365)
                if hist is None or hist.empty:
                    st.error("No historical data available.")
                else:
                    result = backtest_signal(bt_symbol, hist, bt_signal, bt_hold)

                    # Stats
                    c1, c2, c3, c4, c5 = st.columns(5)
                    c1.metric("Trades", result.total_trades)
                    c2.metric("Win Rate", f"{result.win_rate:.0%}")
                    c3.metric("Avg Return", f"{result.avg_return:+.2f}%")
                    c4.metric("Sharpe", f"{result.sharpe_ratio:.2f}")
                    c5.metric("Grade", result.grade)

                    # Chart with signal markers
                    fig = go.Figure()
                    fig.add_trace(go.Candlestick(
                        x=hist["date"], open=hist["open"], high=hist["high"],
                        low=hist["low"], close=hist["close"], name="Price",
                    ))

                    # Add signal markers
                    for t in result.trades:
                        color = "#22c55e" if t.outcome == "win" else "#ef4444"
                        marker = "triangle-up" if t.direction == "buy" else "triangle-down"
                        fig.add_trace(go.Scatter(
                            x=[t.entry_date], y=[t.entry_price],
                            mode="markers", name=f"{t.outcome} ({t.pnl_percent:+.1f}%)",
                            marker=dict(size=14, color=color, symbol=marker, line=dict(width=1, color="white")),
                            showlegend=False,
                        ))

                    fig.update_layout(
                        title=f"{bt_symbol} — {bt_signal} signals (hold {bt_hold}d)",
                        template="plotly_dark", height=450,
                        plot_bgcolor="#0a0a0a", paper_bgcolor="#0a0a0a",
                        xaxis_rangeslider_visible=False,
                    )
                    st.plotly_chart(fig, use_container_width=True)

                    # Trade log
                    if result.trades:
                        st.markdown("### Trade Log")
                        trade_data = [{
                            "Date": t.entry_date, "Entry": f"${t.entry_price}",
                            "Exit": f"${t.exit_price}", "P/L": f"{t.pnl_percent:+.2f}%",
                            "Days": t.hold_days, "Result": t.outcome.upper(),
                        } for t in result.trades]
                        st.dataframe(pd.DataFrame(trade_data), use_container_width=True, hide_index=True)

    with tab_accuracy:
        acc_symbol = st.text_input("Ticker", value="AAPL", key="acc_sym").upper()
        acc_hold = st.selectbox("Hold period", [7, 14, 30, 60], index=2, key="acc_hold")

        if st.button("Rank All Signals", type="primary", use_container_width=True):
            with st.spinner(f"Testing all 14 signals on {acc_symbol}..."):
                from src.data.gateway import DataGateway
                from src.analysis.backtester import backtest_all_signals

                gw = DataGateway()
                hist = gw.get_historical(acc_symbol, period_days=365)
                if hist is None or hist.empty:
                    st.error("No historical data.")
                else:
                    results = backtest_all_signals(acc_symbol, hist, acc_hold)

                    st.markdown(f"### Signal Leaderboard — {acc_symbol} (hold {acc_hold} days)")

                    for rank, r in enumerate(results, 1):
                        ev = r.win_rate * r.avg_return
                        grade_color = "#22c55e" if r.grade.startswith("A") else "#f59e0b" if r.grade.startswith("B") else "#ef4444"

                        st.markdown(f"""<div class="dark-card" style="display:flex; justify-content:space-between; align-items:center;">
                            <div>
                                <span class="text-sm">#{rank}</span>
                                <span style="font-weight:700; margin-left:8px;">{r.signal_name}</span>
                                <span class="text-sm" style="margin-left:8px;">{SIGNALS[r.signal_name]['description']}</span>
                            </div>
                            <div style="display:flex; gap:16px; align-items:center;">
                                <span>{r.win_rate:.0%} win</span>
                                <span>{r.avg_return:+.2f}% avg</span>
                                <span>{r.total_trades} trades</span>
                                <span style="color:{grade_color}; font-weight:800; font-size:18px;">{r.grade}</span>
                            </div>
                        </div>""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════
# PORTFOLIO — Simulator
# ═══════════════════════════════════════════════════════════════
elif page == "💼 Portfolio":
    st.title("💼 Portfolio Simulator")

    watchlist = get_watchlist()
    wl_symbols = [w["symbol"] for w in watchlist]

    if not wl_symbols:
        st.info("Add stocks to watchlist first.")
    else:
        col1, col2, col3 = st.columns(3)
        with col1:
            sim_symbols = st.multiselect("Stocks", wl_symbols, default=wl_symbols[:3])
        with col2:
            sim_strategy = st.selectbox("Strategy", list(SIGNALS.keys()) if 'SIGNALS' in dir() else ["rsi_oversold", "macd_bullish", "sma50_cross_up", "volume_spike"])
        with col3:
            sim_capital = st.number_input("Starting Capital ($)", value=100000, step=10000)

        if st.button("Run Simulation", type="primary", use_container_width=True) and sim_symbols:
            with st.spinner("Simulating portfolio..."):
                try:
                    from src.data.gateway import DataGateway
                    from src.analysis.portfolio_sim import simulate_portfolio

                    gw = DataGateway()
                    hist_data = {}
                    for sym in sim_symbols:
                        df = gw.get_historical(sym, period_days=365)
                        if df is not None and not df.empty:
                            hist_data[sym] = df

                    # SPY benchmark
                    import yfinance as yf
                    spy = yf.download("SPY", period="1y", progress=False, auto_adjust=True).reset_index()
                    spy.columns = [c if isinstance(c, str) else c[0] for c in spy.columns]
                    spy = spy.rename(columns={"Date": "date", "Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"})
                    spy["date"] = spy["date"].dt.strftime("%Y-%m-%d")

                    result = simulate_portfolio(
                        symbols=list(hist_data.keys()),
                        historical_data=hist_data,
                        benchmark_data=spy,
                        strategy=sim_strategy,
                        initial_capital=float(sim_capital),
                    )

                    # Stats
                    c1, c2, c3, c4, c5 = st.columns(5)
                    ret_color = "normal" if result.total_return > 0 else "inverse"
                    c1.metric("Total Return", f"{result.total_return:+.1f}%")
                    c2.metric("Alpha vs SPY", f"{result.alpha:+.1f}%")
                    c3.metric("Sharpe", f"{result.sharpe_ratio:.2f}")
                    c4.metric("Max Drawdown", f"{result.max_drawdown:.1f}%")
                    c5.metric("Win Rate", f"{result.win_rate:.0%}")

                    # Equity curve
                    if result.equity_curve:
                        eq_df = pd.DataFrame([{
                            "Date": s.date,
                            "Portfolio": s.cumulative_return,
                            "S&P 500": s.benchmark_return,
                        } for s in result.equity_curve])

                        fig = go.Figure()
                        fig.add_trace(go.Scatter(x=eq_df["Date"], y=eq_df["Portfolio"],
                                                  name="Your Portfolio", line=dict(color="#22c55e", width=2)))
                        fig.add_trace(go.Scatter(x=eq_df["Date"], y=eq_df["S&P 500"],
                                                  name="S&P 500", line=dict(color="#6b7280", width=1, dash="dot")))
                        fig.update_layout(
                            title="Equity Curve — Portfolio vs Benchmark",
                            template="plotly_dark", height=400,
                            plot_bgcolor="#0a0a0a", paper_bgcolor="#0a0a0a",
                            yaxis_title="Cumulative Return %",
                        )
                        st.plotly_chart(fig, use_container_width=True)

                    # Trades
                    if result.closed_trades:
                        st.markdown("### Closed Trades")
                        t_data = [{
                            "Symbol": t.symbol, "Entry": t.entry_date,
                            "Exit": t.exit_date, "P/L": f"{t.pnl_percent:+.2f}%",
                            "Result": t.outcome.upper(),
                        } for t in result.closed_trades]
                        st.dataframe(pd.DataFrame(t_data), use_container_width=True, hide_index=True)

                except Exception as e:
                    st.error(f"Simulation failed: {e}")


# ═══════════════════════════════════════════════════════════════
# JOURNAL — Trade Journal
# ═══════════════════════════════════════════════════════════════
elif page == "📓 Journal":
    st.title("📓 Trade Journal")

    tab_log, tab_history, tab_stats = st.tabs(["Log Trade", "History", "Performance"])

    with tab_log:
        st.markdown("### New Trade")
        col1, col2 = st.columns(2)
        with col1:
            j_symbol = st.text_input("Ticker", key="j_sym").upper()
            j_direction = st.selectbox("Direction", ["long", "short"])
            j_entry = st.number_input("Entry Price ($)", min_value=0.01, value=100.0, step=0.01)
        with col2:
            j_shares = st.number_input("Shares", min_value=1, value=100, step=1)
            j_verdict = st.selectbox("Report Said", ["Strong Buy", "Buy", "Hold", "Sell", "Strong Sell", "N/A"])
            j_thesis = st.text_area("Thesis / Reason", height=80)

        if st.button("Log Trade", type="primary") and j_symbol:
            from src.journal import log_trade
            trade_id = log_trade(j_symbol, j_direction, j_entry, j_shares, j_thesis, j_verdict)
            st.success(f"Trade #{trade_id} logged: {j_direction.upper()} {j_shares} {j_symbol} @ ${j_entry}")

        # Open positions
        st.markdown("---")
        st.markdown("### Open Positions")
        from src.journal import get_open_trades, close_trade
        open_trades = get_open_trades()
        if not open_trades:
            st.info("No open trades.")
        else:
            for t in open_trades:
                col1, col2, col3 = st.columns([3, 2, 1])
                with col1:
                    st.markdown(f"**{t.symbol}** — {t.direction.upper()} {t.shares} shares @ ${t.entry_price}")
                with col2:
                    close_price = st.number_input(f"Exit price", min_value=0.01, value=float(t.entry_price), step=0.01, key=f"close_{t.id}")
                with col3:
                    st.write("")
                    st.write("")
                    if st.button("Close", key=f"closebtn_{t.id}"):
                        close_trade(t.id, close_price)
                        st.rerun()

    with tab_history:
        from src.journal import get_trade_history
        trades = get_trade_history()
        if not trades:
            st.info("No closed trades yet.")
        else:
            t_data = [{
                "Symbol": t.symbol, "Direction": t.direction.upper(),
                "Entry": f"${t.entry_price}", "Exit": f"${t.exit_price}",
                "Shares": t.shares, "P/L": f"${t.pnl:.2f}" if t.pnl else "—",
                "P/L %": f"{t.pnl_percent:+.2f}%" if t.pnl_percent else "—",
                "Verdict": t.report_verdict, "Date": t.entry_date,
            } for t in trades]
            st.dataframe(pd.DataFrame(t_data), use_container_width=True, hide_index=True)

    with tab_stats:
        from src.journal import get_performance_stats, get_report_accuracy
        stats = get_performance_stats()

        if stats.closed_trades == 0:
            st.info("Close some trades to see performance stats.")
        else:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Win Rate", f"{stats.win_rate:.0%}")
            c2.metric("Total P/L", f"${stats.total_pnl:,.2f}")
            c3.metric("Expectancy", f"{stats.expectancy:+.2f}%")
            c4.metric("Trades", stats.closed_trades)

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Avg Win", f"${stats.avg_win:,.2f}")
            c2.metric("Avg Loss", f"${stats.avg_loss:,.2f}")
            c3.metric("Best", f"${stats.best_trade:,.2f}")
            c4.metric("Worst", f"${stats.worst_trade:,.2f}")

            # Report accuracy
            st.markdown("### Report Accuracy")
            accuracy = get_report_accuracy()
            if accuracy:
                for verdict, data in accuracy.items():
                    if data["trades"] > 0:
                        color = "#22c55e" if data["win_rate"] > 0.6 else "#ef4444" if data["win_rate"] < 0.4 else "#f59e0b"
                        st.markdown(f"""<div class="dark-card" style="display:flex; justify-content:space-between;">
                            <span style="font-weight:700;">{verdict}</span>
                            <span>{data['trades']} trades | <span style="color:{color}; font-weight:700;">{data['win_rate']:.0%} win rate</span></span>
                        </div>""", unsafe_allow_html=True)
            else:
                st.info("Log trades with report verdicts to see accuracy.")
