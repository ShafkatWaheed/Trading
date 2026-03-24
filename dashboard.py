#!/usr/bin/env python3
"""Trading Analysis Dashboard — 5-Step Trading Journey.

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
# Page Config + CSS
# ═══════════════════════════════════════════════════════════════

st.set_page_config(page_title="Trading Platform", page_icon="📊", layout="wide")

st.markdown("""
<style>
    .dark-card { background: #1a1a1a; border: 1px solid #2a2a2a; border-radius: 12px; padding: 20px; margin-bottom: 16px; }
    .dark-card h3 { margin-top: 0; color: #e5e5e5; }
    .badge-inflow { background: #16a34a22; color: #22c55e; padding: 4px 12px; border-radius: 20px; font-weight: 700; font-size: 13px; }
    .badge-outflow { background: #dc262622; color: #ef4444; padding: 4px 12px; border-radius: 20px; font-weight: 700; font-size: 13px; }
    .status-green { color: #22c55e; font-weight: 700; }
    .status-orange { color: #f59e0b; font-weight: 700; }
    .status-red { color: #ef4444; font-weight: 700; }
    .status-gray { color: #9ca3af; font-weight: 700; }
    .score-badge { display: inline-block; padding: 6px 14px; border-radius: 8px; font-weight: 800; font-size: 18px; }
    .score-excellent { background: #22c55e33; color: #22c55e; border: 1px solid #22c55e; }
    .score-good { background: #f59e0b33; color: #f59e0b; border: 1px solid #f59e0b; }
    .score-fair { background: #6b728033; color: #9ca3af; border: 1px solid #6b7280; }
    .score-poor { background: #ef444433; color: #ef4444; border: 1px solid #ef4444; }
    .signal-card { background: #1a1a1a; border: 1px solid #2a2a2a; border-radius: 12px; padding: 16px; margin-bottom: 12px; }
    .signal-card-top { border-color: #f59e0b; }
    .verdict-buy { background: #16a34a18; border: 2px solid #22c55e; }
    .verdict-sell { background: #dc262618; border: 2px solid #ef4444; }
    .verdict-hold { background: #ca8a0418; border: 2px solid #f59e0b; }
    .text-sm { font-size: 13px; color: #9ca3af; }
    .text-lg { font-size: 20px; font-weight: 700; }
    .text-green { color: #22c55e; }
    .text-red { color: #ef4444; }
    .text-orange { color: #f59e0b; }
    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }
    .disclaimer { text-align: center; font-size: 11px; color: #6b7280; padding: 12px; }
    .eco-card { background: #1a1a1a; border: 1px solid #2a2a2a; border-radius: 12px; padding: 16px; text-align: center; }
    .eco-card .value { font-size: 24px; font-weight: 800; color: #e5e5e5; }
    .eco-card .label { font-size: 12px; color: #9ca3af; margin-top: 4px; }
    .why-box { background: #111; border-left: 3px solid #3b82f6; padding: 12px 16px; margin: 8px 0; border-radius: 0 8px 8px 0; font-size: 14px; color: #d1d5db; line-height: 1.6; }
    .signal-bar-container { margin-bottom: 16px; }
    .signal-bar-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }
    .signal-bar-track { height: 8px; background: #2a2a2a; border-radius: 4px; overflow: hidden; }
    .signal-bar-fill { height: 100%; border-radius: 4px; }
    .step-active { border-bottom: 3px solid #22c55e !important; }
    .cta-box { text-align: center; padding: 20px 0; }
</style>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════
# Session State
# ═══════════════════════════════════════════════════════════════

if "current_step" not in st.session_state:
    st.session_state.current_step = 1
if "selected_stock" not in st.session_state:
    st.session_state.selected_stock = None
if "cached_report" not in st.session_state:
    st.session_state.cached_report = None
if "cached_report_symbol" not in st.session_state:
    st.session_state.cached_report_symbol = None
if "comparison_stocks" not in st.session_state:
    st.session_state.comparison_stocks = []


def navigate_to(step: int, stock: str | None = None):
    st.session_state.current_step = step
    if stock:
        st.session_state.selected_stock = stock
    st.rerun()


# ═══════════════════════════════════════════════════════════════
# Navigation Bar
# ═══════════════════════════════════════════════════════════════

def render_navigation():
    steps = [
        (1, "🌍 Market Pulse"),
        (2, "🔍 Discover"),
        (3, "📊 Deep Dive"),
        (4, "🔬 Prove It"),
        (5, "💼 Portfolio"),
    ]
    cols = st.columns(5)
    for col, (num, label) in zip(cols, steps):
        with col:
            active = st.session_state.current_step == num
            completed = st.session_state.current_step > num
            btn_type = "primary" if active else "secondary"
            prefix = "●" if active or completed else "○"
            if st.button(f"{prefix} {label}", key=f"nav_{num}", use_container_width=True, type=btn_type):
                navigate_to(num)
    st.divider()


# ═══════════════════════════════════════════════════════════════
# Existing Helpers (preserved from previous dashboard)
# ═══════════════════════════════════════════════════════════════

def _fmt(val) -> str:
    if isinstance(val, list):
        return ", ".join(str(v) for v in val) if val else "—"
    if isinstance(val, bool):
        return "Yes" if val else "No"
    if val is None or str(val) == "None":
        return "—"
    return str(val)


def _render_price_chart(symbol: str, period: str = "6mo", period_days: int = 180) -> None:
    try:
        import yfinance as yf
        df = yf.download(symbol, period=period, progress=False, auto_adjust=True)
        if df.empty:
            return
        if hasattr(df.columns, 'levels') and df.columns.nlevels > 1:
            df.columns = df.columns.get_level_values(0)
        df = df.reset_index()
        df = df.rename(columns={"Date": "date", "Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"})
        df["date"] = df["date"].dt.strftime("%Y-%m-%d")

        fig = go.Figure()
        fig.add_trace(go.Candlestick(
            x=df["date"], open=df["open"], high=df["high"],
            low=df["low"], close=df["close"], name="Price",
        ))
        if len(df) >= 20:
            df["sma20"] = df["close"].rolling(20).mean()
            fig.add_trace(go.Scatter(x=df["date"], y=df["sma20"], mode="lines", name="SMA(20)", line=dict(color="#3b82f6", width=1)))
        if len(df) >= 50:
            df["sma50"] = df["close"].rolling(50).mean()
            fig.add_trace(go.Scatter(x=df["date"], y=df["sma50"], mode="lines", name="SMA(50)", line=dict(color="#f59e0b", width=1)))

        fig.update_layout(title=f"{symbol} — {period}", template="plotly_dark", height=400,
                          plot_bgcolor="#0a0a0a", paper_bgcolor="#0a0a0a", xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True)
    except Exception:
        pass


def _render_multi_timeframe_chart(symbol: str) -> None:
    periods = {"1W": "5d", "1M": "1mo", "3M": "3mo", "6M": "6mo", "1Y": "1y"}
    tabs = st.tabs(list(periods.keys()))
    for tab, (label, period) in zip(tabs, periods.items()):
        with tab:
            _render_price_chart(symbol, period=period)


def _render_earnings_calendar(symbol: str) -> None:
    try:
        from src.data.gateway import DataGateway
        gw = DataGateway()
        earnings = gw.get_earnings_calendar(symbol)
        if not earnings:
            return
        st.markdown("### 📅 Earnings Calendar")
        today = datetime.utcnow().strftime("%Y-%m-%d")
        future = [e for e in earnings if e["date"] >= today]
        past = [e for e in earnings if e["date"] < today]
        if future:
            next_e = future[0]
            st.markdown(f"""<div class="dark-card" style="border-left:4px solid #f59e0b;">
                <b>Next Earnings:</b> {next_e['date']}
                {f" | EPS Estimate: ${next_e['eps_estimate']:.2f}" if next_e.get('eps_estimate') else ""}
            </div>""", unsafe_allow_html=True)
        if past:
            rows = []
            for e in past[:8]:
                surprise_str = f"{e['surprise_pct']:+.1f}%" if e.get('surprise_pct') else "—"
                rows.append({"Date": e["date"], "EPS Est": f"${e['eps_estimate']:.2f}" if e.get('eps_estimate') else "—",
                             "EPS Actual": f"${e['eps_actual']:.2f}" if e.get('eps_actual') else "—", "Surprise": surprise_str})
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    except Exception:
        pass


def _render_watchlist_heatmap() -> None:
    watchlist = get_watchlist()
    if not watchlist or len(watchlist) < 2:
        return
    labels, colors, values, texts = [], [], [], []
    for item in watchlist:
        sym = item["symbol"]
        latest = get_reports(symbol=sym, limit=1)
        verdict = latest[0]["verdict"] if latest else "Hold"
        risk = latest[0].get("risk_rating", 3) if latest else 3
        color_map = {"Strong Buy": "#16a34a", "Buy": "#22c55e", "Hold": "#ca8a04", "Sell": "#ef4444", "Strong Sell": "#dc2626"}
        labels.append(sym)
        colors.append(color_map.get(verdict, "#6b7280"))
        values.append(1)
        texts.append(f"{verdict}<br>Risk {risk}/5")
    fig = go.Figure(go.Treemap(labels=labels, parents=["" for _ in labels], values=values, text=texts,
                                marker=dict(colors=colors), textinfo="label+text", textfont=dict(size=16)))
    fig.update_layout(template="plotly_dark", height=300, margin=dict(t=10, b=10, l=10, r=10), paper_bgcolor="#0a0a0a")
    st.plotly_chart(fig, use_container_width=True)


def _render_volume_profile(symbol: str) -> None:
    try:
        from src.data.gateway import DataGateway
        gw = DataGateway()
        hist = gw.get_historical(symbol, period_days=60)
        if hist is None or hist.empty:
            return
        close = hist["close"].astype(float)
        volume = hist["volume"].astype(float)
        price_min, price_max = close.min(), close.max()
        n_bins = 30
        bin_size = (price_max - price_min) / n_bins
        if bin_size == 0:
            return
        bins = {}
        for i in range(len(close)):
            bucket = round(price_min + int((close.iloc[i] - price_min) / bin_size) * bin_size, 2)
            bins[bucket] = bins.get(bucket, 0) + volume.iloc[i]
        prices = sorted(bins.keys())
        volumes = [bins[p] for p in prices]
        poc = prices[volumes.index(max(volumes))]
        fig = go.Figure(go.Bar(y=[f"${p:.0f}" for p in prices], x=volumes, orientation="h",
                                marker_color=["#f59e0b" if p == poc else "#3b82f644" for p in prices]))
        fig.update_layout(title=f"Volume Profile (60d) — POC: ${poc:.2f}", template="plotly_dark", height=350,
                          plot_bgcolor="#0a0a0a", paper_bgcolor="#0a0a0a", xaxis_title="Volume", yaxis_title="Price")
        st.plotly_chart(fig, use_container_width=True)
    except Exception:
        pass


_shared_gw = None

def _get_gateway():
    global _shared_gw
    if _shared_gw is None:
        from src.data.gateway import DataGateway
        _shared_gw = DataGateway()
    return _shared_gw


@st.cache_data(ttl=900, show_spinner=False)  # Cache 15 min
def _compute_opportunity_for(symbol: str):
    try:
        from src.analysis import technical
        from src.analysis.opportunity import compute_opportunity

        gw = _get_gateway()

        # Only fetch historical prices (fast, cached in SQLite)
        # Skip options + insider for scoring — too slow for watchlist scan
        hist = gw.get_historical(symbol, period_days=60)
        tech = None
        if hist is not None and not hist.empty:
            tech = technical.analyze(symbol, hist)

        # Use cached options/insider if available, don't block on API
        pcr = None
        net_buy = None
        try:
            from src.utils.db import cache_get
            cached_opts = cache_get(f"polygon:optsummary:{symbol}")
            if cached_opts:
                from decimal import Decimal
                pcr = Decimal(cached_opts.get("put_call_ratio", "0"))
            cached_insider = cache_get(f"sec:insider:{symbol}:90")
            if cached_insider and isinstance(cached_insider, list):
                buys = sum(1 for t in cached_insider if t.get("transaction_type") == "buy")
                sells = sum(1 for t in cached_insider if t.get("transaction_type") == "sell")
                if buys > sells:
                    net_buy = True
                elif sells > buys:
                    net_buy = False
        except Exception:
            pass

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
# New Helpers (WHY explanations)
# ═══════════════════════════════════════════════════════════════

def _regime_explanation(snapshot) -> str:
    if snapshot is None:
        return "Unable to load macro data."
    parts = []
    if snapshot.vix:
        v = float(snapshot.vix)
        if v < 15: parts.append(f"Low VIX ({v:.1f}) signals calm markets — favorable for risk-on trades")
        elif v < 25: parts.append(f"Moderate VIX ({v:.1f}) — normal volatility")
        else: parts.append(f"High VIX ({v:.1f}) signals fear — consider defensive positions")
    if snapshot.fed_funds_rate:
        r = float(snapshot.fed_funds_rate)
        if r > 5: parts.append(f"tight monetary policy (Fed at {r:.2f}%) pressures growth stocks")
        elif r < 2: parts.append(f"easy monetary policy (Fed at {r:.2f}%) supports equities")
        else: parts.append(f"Fed rate at {r:.2f}% — balanced policy")
    if snapshot.yield_curve_inverted:
        parts.append("⚠ yield curve inverted — historically signals recession within 12-18 months")
    elif snapshot.yield_spread_10y2y:
        parts.append(f"yield curve normal (spread {float(snapshot.yield_spread_10y2y):.2f}%)")
    if snapshot.unemployment_rate:
        u = float(snapshot.unemployment_rate)
        if u < 4: parts.append(f"strong labor market ({u:.1f}% unemployment)")
        elif u > 6: parts.append(f"weakening labor ({u:.1f}% unemployment) — risk of slowdown")
    return ". ".join(parts) + "." if parts else "Market conditions are within normal ranges."


def _market_summary(snapshot, flows: list[dict]) -> str:
    regime = snapshot.regime if snapshot else "unknown"
    regime_map = {"normal": "stable", "high_volatility": "volatile", "recession_warning": "showing recession signals",
                  "tight_monetary": "under tight monetary pressure", "strong_labor": "supported by strong employment"}
    summary = f"Markets are {regime_map.get(regime, regime)}. "
    if flows:
        top = sorted(flows, key=lambda f: f.get("change_pct", 0), reverse=True)
        if len(top) >= 2:
            summary += f"Money is flowing into {top[0]['sector']} ({top[0]['change_pct']:+.1f}%) and {top[1]['sector']} ({top[1]['change_pct']:+.1f}%). "
            bottom = sorted(flows, key=lambda f: f.get("change_pct", 0))
            if bottom[0]['change_pct'] < 0:
                summary += f"Weakness in {bottom[0]['sector']} ({bottom[0]['change_pct']:+.1f}%)."
    return summary


def _opportunity_why(score) -> str:
    parts = []
    if score.volume_score >= 20: parts.append(f"Strong volume activity ({score.volume_score}/25)")
    elif score.volume_score <= 8: parts.append(f"Weak volume ({score.volume_score}/25)")
    if score.price_score >= 18: parts.append(f"bullish price momentum ({score.price_score}/25)")
    elif score.price_score <= 8: parts.append(f"bearish price action ({score.price_score}/25)")
    if score.flow_score >= 18: parts.append(f"options/insider flow is bullish ({score.flow_score}/25)")
    elif score.flow_score <= 8: parts.append(f"negative flow signals ({score.flow_score}/25)")
    parts.append(f"Risk/reward ratio {score.risk_reward_ratio}")
    return ". ".join(parts) + f". Strategy: {score.strategy}."


def _render_signal_bars(report) -> None:
    signal_sections = {
        "Technical Analysis": {"color": "#3b82f6", "max": 2},
        "Fundamental Analysis": {"color": "#8b5cf6", "max": 2},
        "News Sentiment": {"color": "#06b6d4", "max": 1},
        "Macro Environment": {"color": "#f59e0b", "max": 2},
        "Options Flow": {"color": "#ec4899", "max": 2},
        "Smart Money": {"color": "#10b981", "max": 2},
        "Congressional Trades": {"color": "#6366f1", "max": 1},
    }
    for section in report.sections:
        config = None
        for key, cfg in signal_sections.items():
            if key.lower() in section.title.lower():
                config = cfg
                break
        if not config:
            continue

        data = section.data
        # Determine score direction from content
        content_lower = section.content.lower()
        if "buy" in content_lower or "bullish" in content_lower or "positive" in content_lower:
            direction = "bullish"
            fill_color = "#22c55e"
        elif "sell" in content_lower or "bearish" in content_lower or "negative" in content_lower:
            direction = "bearish"
            fill_color = "#ef4444"
        else:
            direction = "neutral"
            fill_color = "#f59e0b"

        # Score percentage for bar
        score_val = data.get("score", data.get("overall", data.get("valuation", 0)))
        try:
            score_num = float(score_val) if score_val else 0
        except (ValueError, TypeError):
            score_num = 0
        bar_pct = min(max((score_num + config["max"]) / (2 * config["max"]) * 100, 5), 95)

        st.markdown(f"""
        <div class="signal-bar-container">
            <div class="signal-bar-header">
                <span style="color:{config['color']}; font-weight:700;">{section.title}</span>
                <span class="{'text-green' if direction == 'bullish' else 'text-red' if direction == 'bearish' else 'text-orange'}"
                      style="font-weight:700;">{direction.upper()}</span>
            </div>
            <div class="signal-bar-track">
                <div class="signal-bar-fill" style="width:{bar_pct}%; background:{fill_color};"></div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # WHY explanation
        why_parts = []
        if section.content and section.content != "—":
            why_parts.append(section.content)

        # Extract factors/strengths/weaknesses from data
        for key in ("factors", "strengths", "weaknesses", "agreements", "divergences", "warnings"):
            items = data.get(key, [])
            if isinstance(items, list) and items:
                why_parts.extend(items)

        if why_parts:
            bullets = "".join(f"• {p}<br>" for p in why_parts[:5])
            st.markdown(f'<div class="why-box">{bullets}</div>', unsafe_allow_html=True)


def _classify_sector(sector_name: str) -> str:
    growth = {"Technology", "Communication Services", "Consumer Discretionary"}
    defensive = {"Utilities", "Healthcare", "Consumer Staples", "Real Estate"}
    cyclical = {"Industrials", "Materials", "Energy", "Financials"}
    if sector_name in growth: return "growth"
    if sector_name in defensive: return "defensive"
    if sector_name in cyclical: return "cyclical"
    return "other"


def _render_step_cta(label: str, next_step: int, stock: str | None = None) -> None:
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button(f"➡ {label}", type="primary", use_container_width=True, key=f"cta_{next_step}"):
        navigate_to(next_step, stock)


def _build_equity_curve_from_journal() -> go.Figure | None:
    try:
        from src.journal import get_trade_history
        trades = get_trade_history()
        closed = [t for t in trades if t.status == "closed" and t.pnl is not None]
        if not closed:
            return None
        closed.sort(key=lambda t: t.exit_date or t.entry_date)
        dates, cumulative = [], []
        running = 0.0
        for t in closed:
            running += t.pnl
            dates.append(t.exit_date or t.entry_date)
            cumulative.append(running)
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=dates, y=cumulative, mode="lines+markers", name="Cumulative P/L",
                                  line=dict(color="#22c55e" if cumulative[-1] >= 0 else "#ef4444", width=2)))
        fig.add_hline(y=0, line_dash="dash", line_color="#6b7280")
        fig.update_layout(title="Equity Curve (Real Trades)", template="plotly_dark", height=350,
                          plot_bgcolor="#0a0a0a", paper_bgcolor="#0a0a0a", yaxis_title="Cumulative P/L ($)")
        return fig
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════
# STEP 1: MARKET PULSE
# ═══════════════════════════════════════════════════════════════

def _kpi_card(icon: str, label: str, value: str, status: str, status_class: str, explanation: str) -> str:
    return f"""<div class="dark-card" style="padding:16px;">
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <div style="display:flex; align-items:center; gap:10px;">
                <span style="font-size:22px;">{icon}</span>
                <span style="color:#9ca3af; font-size:14px;">{label}</span>
            </div>
            <span class="{status_class}" style="font-size:14px;">{status}</span>
        </div>
        <div style="font-size:28px; font-weight:800; color:#e5e5e5; margin:8px 0 4px;">{value}</div>
        <div style="font-size:12px; color:#6b7280; line-height:1.4;">{explanation}</div>
    </div>"""


def _yield_curve_card(snapshot) -> str:
    """Returns HTML for the yield curve card. The educational section is rendered separately via Streamlit expander."""
    if snapshot is None or snapshot.yield_spread_10y2y is None:
        return ""
    spread = float(snapshot.yield_spread_10y2y)
    t10 = f"{float(snapshot.treasury_10y):.2f}%" if snapshot.treasury_10y else "—"
    t2 = f"{float(snapshot.treasury_2y):.2f}%" if snapshot.treasury_2y else "—"
    inverted = spread < 0
    flattening = 0 <= spread < 0.3

    color = "#ef4444" if inverted else "#f59e0b" if flattening else "#22c55e"
    status = "INVERTED" if inverted else "FLATTENING" if flattening else "NORMAL"
    icon = "⚠" if inverted else "⚡" if flattening else "✅"

    bar_pct = max(min((spread + 1.5) / 3.0 * 100, 100), 0)

    if inverted:
        explanation = f"Short-term rates ({t2}) exceed long-term ({t10}) by {abs(spread):.2f}%. This is abnormal — investors expect the economy to weaken so badly that the Fed will cut rates in the future. Historically predicted the last 8 recessions."
        action = "Risk-off positioning: rotate to defensive sectors (utilities, healthcare, staples). Raise cash allocation. Avoid cyclicals and high-beta names."
    elif flattening:
        explanation = f"Spread narrowing to just {spread:+.2f}%. Approaching inversion territory — the bond market is getting nervous about economic growth ahead."
        action = "Start building defensive positions. Don't go all-in on growth. Watch for further flattening as an early warning."
    else:
        explanation = f"Healthy {spread:+.2f}% spread between 10Y ({t10}) and 2Y ({t2}). Lenders demand more interest for locking money longer — this is normal. Economy is functioning as expected."
        action = "No recession signal from bonds. Broad market exposure is reasonable. Both growth and value strategies can work."

    return f"""<div class="dark-card" style="padding:20px; border-left:3px solid {color};">
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <div style="display:flex; align-items:center; gap:10px;">
                <span style="font-size:22px;">📐</span>
                <span style="color:#e5e5e5; font-size:16px; font-weight:700;">Yield Curve</span>
            </div>
            <span style="background:{color}22; color:{color}; font-weight:700; font-size:13px; padding:4px 12px; border-radius:20px; border:1px solid {color};">{icon} {status}</span>
        </div>

        <div style="display:flex; gap:32px; margin:16px 0;">
            <div style="text-align:center;">
                <div style="color:#6b7280; font-size:11px; text-transform:uppercase; letter-spacing:0.5px;">10-Year</div>
                <div style="font-size:24px; font-weight:800; color:#e5e5e5; margin-top:2px;">{t10}</div>
                <div style="color:#6b7280; font-size:11px;">Long-term rate</div>
            </div>
            <div style="text-align:center; font-size:24px; color:#6b7280; padding-top:16px;">vs</div>
            <div style="text-align:center;">
                <div style="color:#6b7280; font-size:11px; text-transform:uppercase; letter-spacing:0.5px;">2-Year</div>
                <div style="font-size:24px; font-weight:800; color:#e5e5e5; margin-top:2px;">{t2}</div>
                <div style="color:#6b7280; font-size:11px;">Short-term rate</div>
            </div>
            <div style="text-align:center; font-size:24px; color:#6b7280; padding-top:16px;">=</div>
            <div style="text-align:center;">
                <div style="color:#6b7280; font-size:11px; text-transform:uppercase; letter-spacing:0.5px;">Spread</div>
                <div style="font-size:24px; font-weight:800; color:{color}; margin-top:2px;">{spread:+.2f}%</div>
                <div style="color:#6b7280; font-size:11px;">{"Danger zone" if inverted else "Watch zone" if flattening else "Healthy"}</div>
            </div>
        </div>

        <div style="height:8px; background:#2a2a2a; border-radius:4px; margin:12px 0; position:relative;">
            <div style="height:100%; width:{bar_pct}%; background:linear-gradient(to right, #ef4444, #f59e0b, #22c55e); border-radius:4px;"></div>
            <div style="position:absolute; top:-4px; left:{bar_pct}%; width:16px; height:16px; background:{color}; border:2px solid #e5e5e5; border-radius:50%; transform:translateX(-50%); box-shadow:0 1px 4px rgba(0,0,0,0.5);"></div>
        </div>
        <div style="display:flex; justify-content:space-between; font-size:10px; color:#6b7280; margin-bottom:12px;">
            <span>🔴 Inverted (-1.5%)</span><span>Flat (0%)</span><span>🟢 Steep (+1.5%)</span>
        </div>

        <div style="font-size:13px; color:#d1d5db; line-height:1.6; margin-bottom:8px;">{explanation}</div>
        <div style="font-size:13px; color:{color}; line-height:1.6; font-weight:600;">→ {action}</div>
    </div>"""


def _render_yield_curve_section(snapshot) -> None:
    """Render yield curve card using Streamlit-native components + educational expander."""
    if snapshot is None or snapshot.yield_spread_10y2y is None:
        return

    spread = float(snapshot.yield_spread_10y2y)
    t10 = float(snapshot.treasury_10y) if snapshot.treasury_10y else None
    t2 = float(snapshot.treasury_2y) if snapshot.treasury_2y else None
    inverted = spread < 0
    flattening = 0 <= spread < 0.3

    color = "#ef4444" if inverted else "#f59e0b" if flattening else "#22c55e"
    status = "INVERTED" if inverted else "FLATTENING" if flattening else "NORMAL"
    icon = "⚠️" if inverted else "⚡" if flattening else "✅"

    if inverted:
        explanation = f"Short-term rates ({t2:.2f}%) exceed long-term ({t10:.2f}%) by {abs(spread):.2f}%. This is abnormal — investors expect the economy to weaken. Historically predicted the last 8 recessions."
        action = "Rotate to defensive sectors (utilities, healthcare, staples). Raise cash allocation. Avoid cyclicals."
    elif flattening:
        explanation = f"Spread narrowing to just {spread:+.2f}%. Approaching inversion territory — the bond market is getting nervous about growth."
        action = "Start building defensive positions. Don't go all-in on growth. Watch for further flattening."
    else:
        explanation = f"Healthy {spread:+.2f}% spread between 10Y ({t10:.2f}%) and 2Y ({t2:.2f}%). Lenders demand more for longer lockup — normal. Economy functioning as expected."
        action = "No recession signal. Broad market exposure is reasonable. Both growth and value strategies work."

    # Header
    st.markdown(f"""<div class="dark-card" style="border-left:3px solid {color}; padding:20px;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
            <span style="color:#e5e5e5; font-size:16px; font-weight:700;">📐 Yield Curve</span>
            <span style="background:{color}22; color:{color}; font-weight:700; font-size:13px; padding:4px 12px; border-radius:20px; border:1px solid {color};">{icon} {status}</span>
        </div>
    </div>""", unsafe_allow_html=True)

    # Metrics row
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("10-Year (Long)", f"{t10:.2f}%" if t10 else "—")
    c2.metric("2-Year (Short)", f"{t2:.2f}%" if t2 else "—")
    c3.metric("Spread", f"{spread:+.2f}%", delta=f"{'Healthy' if spread > 0.3 else 'Watch' if spread >= 0 else 'DANGER'}")
    c4.metric("Signal", status)

    # Progress bar via Streamlit
    bar_val = max(min((spread + 1.5) / 3.0, 1.0), 0.0)
    st.progress(bar_val)
    cols = st.columns(3)
    cols[0].caption("🔴 Inverted (-1.5%)")
    cols[1].caption("&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Flat (0%)")
    cols[2].caption("&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;🟢 Steep (+1.5%)")

    # Explanation + action
    st.markdown(f"""<div class="why-box">
        {explanation}<br><br>
        <span style="color:{color}; font-weight:600;">→ {action}</span>
    </div>""", unsafe_allow_html=True)

    with st.expander("📚 What is the Yield Curve and why should traders care?"):
        st.markdown("""
**The yield curve** shows the relationship between short-term and long-term government bond interest rates.

**Normal (spread > 0):** Lenders demand **more** interest for locking money up longer — this makes sense. The economy is healthy.

**Inverted (spread < 0):** Short-term rates **exceed** long-term. Investors expect the economy to weaken so badly that the Fed will **cut rates**. They lock in today's long-term rates before they fall.

| Yield Curve | What It Signals | Track Record | Trading Action |
|-------------|----------------|--------------|----------------|
| **Normal** (> +0.5%) | Economy expanding | Stocks go up | Full exposure, growth + value |
| **Flattening** (0 to +0.3%) | Slowdown approaching | Early warning | Build defensive positions |
| **Inverted** (< 0%) | Recession 12-18 months | Predicted last 8 recessions | Rotate to defensives, raise cash |
| **Steepening** (after inversion) | Recovery beginning | Buy signal | Accumulate beaten-down sectors |

**Why it's the #1 recession indicator:** Banks borrow short-term and lend long-term. When short rates exceed long rates, banks can't profit from lending. Credit tightens → businesses can't expand → layoffs → recession.
        """)


def page_market_pulse():
    st.title("🌍 Market Pulse")
    st.caption("Understand the market before picking stocks")

    from src.data.gateway import DataGateway
    gw = DataGateway()

    with st.spinner("Loading macro data..."):
        snapshot = gw.get_macro_snapshot()

    # ── Regime Banner ──────────────────────────────────────────
    regime = snapshot.regime if snapshot else "unknown"
    regime_colors = {"normal": "#22c55e", "strong_labor": "#22c55e", "high_volatility": "#f59e0b",
                     "tight_monetary": "#ef4444", "recession_warning": "#dc2626"}
    regime_labels_map = {"normal": "Normal Market Conditions", "strong_labor": "Strong Labor Market",
                         "high_volatility": "High Volatility", "tight_monetary": "Tight Monetary Policy",
                         "recession_warning": "⚠ Recession Warning"}
    color = regime_colors.get(regime, "#6b7280")
    st.markdown(f"""<div class="dark-card" style="border-left: 4px solid {color}; padding: 24px;">
        <h2 style="color:{color}; margin:0;">{regime_labels_map.get(regime, regime.replace('_', ' ').title())}</h2>
        <p style="color:#d1d5db; margin-top:8px; font-size:15px;">{_regime_explanation(snapshot)}</p>
    </div>""", unsafe_allow_html=True)

    # ── KPI Cards Row 1: Primary Indicators ────────────────────
    if snapshot:
        st.markdown("### Key Economic Indicators")

        col1, col2, col3 = st.columns(3)

        # Fed Rate
        with col1:
            fed = float(snapshot.fed_funds_rate) if snapshot.fed_funds_rate else None
            if fed is not None:
                fed_status, fed_class = _macro_status("fed", fed)
                fed_explain = (
                    "Rates above 5% squeeze corporate borrowing and slow growth. High-debt companies suffer most. Favor cash-rich value stocks."
                    if fed > 5 else
                    "Moderate rates — balanced policy. Both growth and value stocks can perform. Watch for next Fed meeting signals."
                    if fed > 3 else
                    "Low rates fuel borrowing and expansion. Growth stocks and real estate typically outperform. Risk appetite is high."
                )
                st.markdown(_kpi_card("🏦", "Fed Funds Rate", f"{fed:.2f}%", fed_status, fed_class, fed_explain), unsafe_allow_html=True)

        # VIX
        with col2:
            vix = float(snapshot.vix) if snapshot.vix else None
            if vix is not None:
                vix_status, vix_class = _macro_status("sentiment", vix)
                vix_explain = (
                    "Extreme fear in markets — large price swings expected. Options are expensive. Consider hedging or waiting for volatility to settle."
                    if vix > 30 else
                    "Elevated uncertainty — markets pricing in risk events. Tighten stop losses and reduce position sizes."
                    if vix > 20 else
                    "Calm markets — low implied volatility. Good environment for trend-following strategies. Options are cheap for protection."
                )
                st.markdown(_kpi_card("📊", "VIX (Fear Index)", f"{vix:.1f}", vix_status, vix_class, vix_explain), unsafe_allow_html=True)

        # Unemployment
        with col3:
            unemp = float(snapshot.unemployment_rate) if snapshot.unemployment_rate else None
            if unemp is not None:
                emp_status, emp_class = _macro_status("employment", unemp)
                emp_explain = (
                    "Labor market weakening — consumers cut spending, earnings forecasts drop. Defensive sectors (utilities, healthcare, staples) tend to outperform."
                    if unemp > 6 else
                    "Healthy job market — consumer spending supports corporate earnings. Broad market exposure is reasonable."
                    if unemp < 4.5 else
                    "Mixed signals — employment softening but not alarming. Watch for acceleration in claims data."
                )
                st.markdown(_kpi_card("👥", "Unemployment Rate", f"{unemp:.1f}%", emp_status, emp_class, emp_explain), unsafe_allow_html=True)

        # ── KPI Cards Row 2: Rates + Growth ────────────────────
        col4, col5, col6 = st.columns(3)

        # 10Y Treasury
        with col4:
            t10y = float(snapshot.treasury_10y) if snapshot.treasury_10y else None
            if t10y is not None:
                t10_status = "Rising" if t10y > 4.5 else "Moderate" if t10y > 3 else "Low"
                t10_class = "status-red" if t10y > 4.5 else "status-orange" if t10y > 3 else "status-green"
                t10_explain = (
                    "High yields compete with stocks for capital. Growth stocks with high P/E ratios are most vulnerable. Bonds become attractive alternative."
                    if t10y > 4.5 else
                    "Moderate yields — stocks still competitive but high-valuation names face pressure. Balance between growth and value."
                    if t10y > 3 else
                    "Low yields push investors into stocks for returns. Risk assets rally. Growth stocks benefit most."
                )
                st.markdown(_kpi_card("📈", "10-Year Treasury", f"{t10y:.2f}%", t10_status, t10_class, t10_explain), unsafe_allow_html=True)

        # GDP Growth
        with col5:
            gdp = float(snapshot.gdp_growth) if snapshot.gdp_growth else None
            if gdp is not None:
                gdp_status = "Expanding" if gdp > 2 else "Slowing" if gdp > 0 else "Contracting"
                gdp_class = "status-green" if gdp > 2 else "status-orange" if gdp > 0 else "status-red"
                gdp_explain = (
                    "Strong economic expansion — corporate revenues growing. Cyclical stocks (industrials, consumer discretionary, tech) typically lead."
                    if gdp > 2 else
                    "Growth slowing but still positive. Late-cycle dynamics — focus on quality and profitability over pure growth."
                    if gdp > 0 else
                    "Economy shrinking — earnings under pressure across sectors. Cash, treasuries, and defensive stocks are safer. Avoid high-beta names."
                )
                st.markdown(_kpi_card("🏭", "GDP Growth", f"{gdp:.1f}%", gdp_status, gdp_class, gdp_explain), unsafe_allow_html=True)

        # CPI / Inflation
        with col6:
            cpi = float(snapshot.cpi_yoy) if snapshot.cpi_yoy else None
            if cpi is not None:
                inf_status, inf_class = _macro_status("inflation", cpi)
                inf_explain = (
                    "High inflation erodes purchasing power and forces the Fed to raise rates. Commodities and real assets outperform. Avoid long-duration bonds and high-P/E stocks."
                    if cpi > 4 else
                    "Moderate inflation — the Fed is watching closely. Companies with pricing power (strong brands, monopolies) handle this best."
                    if cpi > 2.5 else
                    "Low inflation — Goldilocks zone for stocks. The Fed may ease policy, supporting equity valuations across the board."
                )
                st.markdown(_kpi_card("💰", "Inflation (CPI YoY)", f"{cpi:.1f}%", inf_status, inf_class, inf_explain), unsafe_allow_html=True)

    # ── Yield Curve Card ───────────────────────────────────────
    _render_yield_curve_section(snapshot)

    # ── Sector Flows ───────────────────────────────────────────
    period_labels = {"1D": "1d", "1W": "5d", "1M": "1mo", "3M": "3mo", "6M": "6mo", "1Y": "1y"}
    period_display = {"1D": "1 Day", "1W": "1 Week", "1M": "1 Month", "3M": "3 Months", "6M": "6 Months", "1Y": "1 Year"}

    # Header + filter in one row
    hdr_col, filter_col = st.columns([1, 2])
    with hdr_col:
        st.markdown("### Sector Money Flow")
    with filter_col:
        st.markdown("""<style>
            /* Style the segmented filter pills */
            div[data-testid="stColumns"] div[data-baseweb="tab-list"] {
                gap: 0px !important;
            }
            div[data-testid="stColumns"] div[data-baseweb="tab-list"] button {
                font-size: 13px !important;
                font-weight: 600 !important;
                padding: 4px 14px !important;
                border-radius: 8px !important;
            }
            div[data-testid="stColumns"] div[data-baseweb="tab-list"] button[aria-selected="true"] {
                background-color: #22c55e !important;
                color: #0a0a0a !important;
            }
        </style>""", unsafe_allow_html=True)
        selected_period = st.segmented_control(
            "Period", list(period_labels.keys()), default="1M",
            key="flow_period_seg", label_visibility="collapsed",
        )
        if selected_period is None:
            selected_period = "1M"
    yf_period = period_labels[selected_period]

    with st.spinner(f"Loading {period_display[selected_period]} sector data..."):
        flows = gw.get_sector_flows(yf_period)

    if flows:
        # Net flow summary
        total_positive = sum(f.get("change_pct", 0) for f in flows if f.get("change_pct", 0) > 0)
        total_negative = sum(f.get("change_pct", 0) for f in flows if f.get("change_pct", 0) < 0)
        net = total_positive + total_negative
        net_label = "NET INFLOW" if net > 0 else "NET OUTFLOW"
        net_class = "badge-inflow" if net > 0 else "badge-outflow"

        st.markdown(f"""<div class="dark-card" style="padding:16px;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
                <span style="color:#9ca3af; font-size:13px;">Sector flows over {period_display[selected_period]} &nbsp;&bull;&nbsp; 11 sectors
                    &nbsp;&bull;&nbsp; Data as of: {datetime.utcnow().strftime('%b %d, %Y')}</span>
                <span class="{net_class}">{net_label}</span>
            </div>
            <div style="display:flex; justify-content:space-around; text-align:center;">
                <div><span style="color:#9ca3af; font-size:12px;">Net Flow</span><br>
                    <span style="font-size:22px; font-weight:800; color:{'#22c55e' if net > 0 else '#ef4444'};">{net:+.1f}%</span></div>
                <div><span style="color:#9ca3af; font-size:12px;">Inflows</span><br>
                    <span style="font-size:22px; font-weight:800; color:#22c55e;">+{total_positive:.1f}%</span></div>
                <div><span style="color:#9ca3af; font-size:12px;">Outflows</span><br>
                    <span style="font-size:22px; font-weight:800; color:#ef4444;">{total_negative:.1f}%</span></div>
            </div>
        </div>""", unsafe_allow_html=True)

        sorted_flows = sorted(flows, key=lambda f: f.get("change_pct", 0))
        sectors = [f["sector"] for f in sorted_flows]
        changes = [f.get("change_pct", 0) for f in sorted_flows]
        bar_colors = ["#22c55e" if c > 0 else "#ef4444" for c in changes]

        fig = go.Figure(go.Bar(y=sectors, x=changes, orientation="h", marker_color=bar_colors,
                                text=[f"{c:+.1f}%" for c in changes], textposition="outside"))
        fig.update_layout(template="plotly_dark", height=max(350, len(sectors) * 35),
                          plot_bgcolor="#0a0a0a", paper_bgcolor="#0a0a0a",
                          xaxis_title="Change %", margin=dict(l=150))
        st.plotly_chart(fig, use_container_width=True)

    # ── Trading Implications ───────────────────────────────────
    period_name = period_display[selected_period]
    advice_parts = []

    # ── Macro-driven advice (always shown) ─────────────────────
    if snapshot:
        # VIX
        vix_val = float(snapshot.vix) if snapshot.vix else None
        if vix_val is not None:
            if vix_val > 30:
                advice_parts.append(f"🔴 **VIX at {vix_val:.1f} (extreme fear)** — reduce position sizes to 50% of normal, use tight stops. Options are expensive — selling premium strategies (covered calls, credit spreads) have an edge.")
            elif vix_val > 25:
                advice_parts.append(f"🟠 **VIX at {vix_val:.1f} (elevated)** — markets are nervous. Tighten stop losses, avoid overleveraging. Consider hedging open positions with protective puts.")
            elif vix_val > 20:
                advice_parts.append(f"🟡 **VIX at {vix_val:.1f} (cautious)** — moderate uncertainty. Normal position sizing but be selective. Favor stocks with clear catalysts over speculative plays.")
            else:
                advice_parts.append(f"🟢 **VIX at {vix_val:.1f} (calm)** — low volatility favors trend-following and breakout strategies. Options are cheap — good time to buy protective puts or call spreads.")

        # Fed Rate
        fed_val = float(snapshot.fed_funds_rate) if snapshot.fed_funds_rate else None
        if fed_val is not None:
            if fed_val > 5:
                advice_parts.append(f"🔴 **Fed Rate at {fed_val:.2f}% (restrictive)** — borrowing costs squeeze margins. Avoid high-debt companies (check D/E ratio). Value stocks with strong free cash flow outperform. Tech/growth stocks with no profits are highest risk.")
            elif fed_val > 3.5:
                advice_parts.append(f"🟡 **Fed Rate at {fed_val:.2f}% (moderate)** — rates are manageable but watch the direction. If the Fed signals more hikes, rotate to value. If pausing, growth stocks recover first.")
            else:
                advice_parts.append(f"🟢 **Fed Rate at {fed_val:.2f}% (accommodative)** — cheap money fuels expansion. Growth stocks, real estate (REITs), and high-P/E names benefit most. Risk appetite is high across the board.")

        # Yield Curve
        if snapshot.yield_curve_inverted:
            spread = float(snapshot.yield_spread_10y2y) if snapshot.yield_spread_10y2y else 0
            advice_parts.append(f"🔴 **Yield curve inverted ({spread:+.2f}%)** — the bond market is pricing in recession. Historically, stocks decline 15-20% within 12-18 months of inversion. Action: rotate to defensive sectors (utilities, healthcare, consumer staples), raise cash allocation, avoid cyclicals.")
        elif snapshot.yield_spread_10y2y:
            spread = float(snapshot.yield_spread_10y2y)
            if spread < 0.3:
                advice_parts.append(f"🟠 **Yield curve flattening ({spread:+.2f}% spread)** — approaching inversion territory. Start building defensive positions. Don't go all-in on growth.")
            else:
                advice_parts.append(f"🟢 **Yield curve normal ({spread:+.2f}% spread)** — no recession signal from bonds. Economy functioning as expected. Broad market exposure is reasonable.")

        # GDP
        gdp_val = float(snapshot.gdp_growth) if snapshot.gdp_growth else None
        if gdp_val is not None:
            if gdp_val > 3:
                advice_parts.append(f"🟢 **GDP growing at {gdp_val:.1f}%** — strong expansion. Cyclical stocks (industrials, consumer discretionary, materials) have earnings tailwinds. Small-caps historically outperform in high-growth periods.")
            elif gdp_val > 0:
                advice_parts.append(f"🟡 **GDP growing at {gdp_val:.1f}% (slowing)** — late-cycle dynamics. Favor quality over quantity — look for companies with consistent earnings, strong balance sheets, and pricing power. Avoid speculative names.")
            else:
                advice_parts.append(f"🔴 **GDP contracting at {gdp_val:.1f}%** — economic recession. Raise cash to 30-50% of portfolio. Focus on: dividend aristocrats, utilities, healthcare, consumer staples. Avoid: cyclicals, high-beta, unprofitable growth.")

        # Unemployment
        unemp_val = float(snapshot.unemployment_rate) if snapshot.unemployment_rate else None
        if unemp_val is not None:
            if unemp_val > 6:
                advice_parts.append(f"🔴 **Unemployment at {unemp_val:.1f}% (weakening)** — consumer spending will decline, hitting retail and discretionary sectors hardest. Companies reporting earnings misses likely to increase. Favor essentials over luxuries.")
            elif unemp_val < 4:
                advice_parts.append(f"🟢 **Unemployment at {unemp_val:.1f}% (strong labor)** — consumers are spending, supporting corporate revenues. Retail, restaurants, and discretionary sectors benefit. But watch for wage inflation pressuring margins.")

        # CPI
        cpi_val = float(snapshot.cpi_yoy) if snapshot.cpi_yoy else None
        if cpi_val is not None:
            if cpi_val > 5:
                advice_parts.append(f"🔴 **Inflation at {cpi_val:.1f}% (hot)** — the Fed will likely keep rates high or raise them. Commodities, energy, and companies with pricing power outperform. Avoid long-duration bonds and unprofitable growth stocks.")
            elif cpi_val > 3:
                advice_parts.append(f"🟠 **Inflation at {cpi_val:.1f}% (sticky)** — above the Fed's 2% target. Companies that can pass costs to customers (strong brands, monopolies) handle this best. Monitor Fed meeting dates for policy signals.")
            elif cpi_val is not None:
                advice_parts.append(f"🟢 **Inflation at {cpi_val:.1f}% (controlled)** — in the Goldilocks zone. The Fed may cut rates, which supports equity valuations. Broadest opportunity set for both growth and value.")

    # ── Sector-driven advice (changes with filter) ─────────────
    if flows:
        sorted_by_flow = sorted(flows, key=lambda f: f.get("change_pct", 0), reverse=True)
        top_2 = sorted_by_flow[:2]
        bottom_2 = sorted_by_flow[-2:]
        gaining = [f for f in flows if f.get("change_pct", 0) > 0]
        losing = [f for f in flows if f.get("change_pct", 0) < 0]

        if top_2 and top_2[0].get("change_pct", 0) > 0:
            advice_parts.append(
                f"📈 **Over the past {period_name}**, money is flowing into "
                f"**{top_2[0]['sector']}** ({top_2[0]['change_pct']:+.1f}%) and "
                f"**{top_2[1]['sector']}** ({top_2[1]['change_pct']:+.1f}%). "
                f"Look for leading stocks in these sectors — they have institutional momentum behind them."
            )

        if bottom_2 and bottom_2[-1].get("change_pct", 0) < 0:
            advice_parts.append(
                f"📉 **Capital rotating out of** "
                f"**{bottom_2[-1]['sector']}** ({bottom_2[-1]['change_pct']:+.1f}%) and "
                f"**{bottom_2[-2]['sector']}** ({bottom_2[-2]['change_pct']:+.1f}%). "
                f"Avoid new positions here unless you see a clear reversal signal. Existing positions — tighten stops."
            )

        if len(gaining) >= 8:
            advice_parts.append(f"🟢 **Broad strength** — {len(gaining)}/11 sectors positive over {period_name}. Market is in a risk-on mode. Trend-following strategies favored.")
        elif len(losing) >= 8:
            advice_parts.append(f"🔴 **Broad weakness** — {len(losing)}/11 sectors negative over {period_name}. Defensive posture recommended. Raise cash, tighten stops, reduce position count.")
        elif abs(len(gaining) - len(losing)) <= 2:
            advice_parts.append(f"🟡 **Mixed rotation** — {len(gaining)} sectors up, {len(losing)} down over {period_name}. Market is sector-selective, not directional. Stock picking matters more than market direction.")

        # Rotation narrative
        if len(flows) >= 4:
            top_sector_type = _classify_sector(top_2[0]["sector"]) if top_2 else ""
            bottom_sector_type = _classify_sector(bottom_2[-1]["sector"]) if bottom_2 else ""
            if top_sector_type == "growth" and bottom_sector_type == "defensive":
                advice_parts.append("🔄 **Risk-on rotation**: money moving from defensive to growth sectors. Market is optimistic. Favor tech, consumer discretionary, communications.")
            elif top_sector_type == "defensive" and bottom_sector_type == "growth":
                advice_parts.append("🔄 **Risk-off rotation**: money moving from growth to defensive sectors. Market is cautious. Favor utilities, healthcare, staples. Reduce tech exposure.")
            elif top_sector_type == "cyclical" and bottom_sector_type == "growth":
                advice_parts.append("🔄 **Value rotation**: money moving from growth to cyclicals. Investors expect economic strength. Favor industrials, materials, energy over tech.")

    # Build HTML
    if not advice_parts:
        advice_parts.append("🟡 No strong directional signals across indicators. Market is balanced — focus on individual stock catalysts rather than macro themes.")

    advice_html = "".join(f"""<div style="padding:10px 0; border-bottom:1px solid #222; line-height:1.7; font-size:14px; color:#d1d5db;">
        {a}
    </div>""" for a in advice_parts)

    st.markdown(f"""<div class="dark-card" style="border-left:3px solid #3b82f6; padding:24px;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:16px;">
            <h3 style="color:#3b82f6; margin:0;">What This Means For Your Trading</h3>
            <span style="color:#6b7280; font-size:12px;">Based on current indicators + {period_name} sector flows</span>
        </div>
        {advice_html}
    </div>""", unsafe_allow_html=True)

    _render_step_cta("Find Stocks to Trade", 2)


# ═══════════════════════════════════════════════════════════════
# STEP 2: DISCOVER
# ═══════════════════════════════════════════════════════════════

POPULAR_STOCKS = [
    "AAPL", "MSFT", "GOOG", "AMZN", "NVDA", "META", "TSLA", "BRK-B", "JPM", "V",
    "JNJ", "WMT", "PG", "MA", "UNH", "HD", "DIS", "BAC", "XOM", "KO",
    "PFE", "ABBV", "CSCO", "MRK", "PEP", "AMD", "INTC", "NFLX", "CRM", "ORCL",
    "COST", "ADBE", "NKE", "T", "VZ", "BA", "GS", "MS", "QCOM", "SBUX",
    "PYPL", "SQ", "SHOP", "SNAP", "UBER", "ABNB", "COIN", "RIVN", "PLTR", "SOFI",
]


def page_discover():
    st.title("🔍 Discover Opportunities")
    st.caption("Find and rank stocks worth trading")

    # Searchable stock selector
    watchlist = get_watchlist()
    existing = {w["symbol"] for w in watchlist} if watchlist else set()

    col_search, col_add = st.columns([4, 1])
    with col_search:
        selected = st.selectbox(
            "Search stocks",
            options=[""] + [s for s in POPULAR_STOCKS if s not in existing],
            index=0,
            placeholder="Search by ticker (e.g. AAPL, TSLA, NVDA)...",
            label_visibility="collapsed",
        )
    with col_add:
        custom = st.text_input("or type", placeholder="Custom ticker", max_chars=10, label_visibility="collapsed")

    add_col1, add_col2, _ = st.columns([1, 1, 3])
    with add_col1:
        if st.button("➕ Add to Watchlist", use_container_width=True, type="primary"):
            sym = (selected or custom or "").strip().upper()
            if sym:
                add_watchlist_item(sym)
                st.rerun()
    with add_col2:
        if st.button("➕ Add Top 5", use_container_width=True):
            for s in ["AAPL", "MSFT", "NVDA", "TSLA", "AMZN"]:
                if s not in existing:
                    add_watchlist_item(s)
            st.rerun()

    watchlist = get_watchlist()

    if not watchlist:
        st.info("Your watchlist is empty. Search for stocks above or click 'Add Top 5' to get started.")
        return

    # Opportunity scores with time filter
    disc_periods = {"1D": 2, "1W": 5, "1M": 21, "3M": 63, "6M": 126, "1Y": 252}
    disc_labels = {"1D": "1 Day", "1W": "1 Week", "1M": "1 Month", "3M": "3 Months", "6M": "6 Months", "1Y": "1 Year"}

    hdr_col, filter_col = st.columns([1, 2])
    with hdr_col:
        st.markdown("### Opportunity Ranking")
    with filter_col:
        disc_period = st.segmented_control(
            "Period", list(disc_periods.keys()), default="1M",
            key="disc_period_seg", label_visibility="collapsed",
        )
        if disc_period is None:
            disc_period = "1M"
    lookback_days = disc_periods[disc_period]

    scores = []
    prices = {}
    sparklines = {}
    symbols = [item["symbol"] for item in watchlist]

    with st.spinner("Scoring watchlist stocks..."):
        from concurrent.futures import ThreadPoolExecutor

        # 1. Score all stocks in parallel (uses @st.cache_data — instant on repeat)
        with ThreadPoolExecutor(max_workers=min(len(symbols), 5)) as executor:
            results = list(executor.map(_compute_opportunity_for, symbols))
        scores = [s for s in results if s is not None]

        # 2. Fetch historical data once per stock (cached in SQLite after first call)
        gw = _get_gateway()
        hist_cache = {}
        def _fetch_hist(sym):
            try:
                return sym, gw.get_historical(sym, period_days=max(lookback_days + 5, 60))
            except Exception:
                return sym, None

        with ThreadPoolExecutor(max_workers=min(len(symbols), 5)) as executor:
            for sym, hist in executor.map(lambda s: _fetch_hist(s), symbols):
                if hist is not None and not hist.empty:
                    hist_cache[sym] = hist

        # 3. Extract prices + sparklines from the same data (no extra API calls)
        for sym, hist in hist_cache.items():
            closes = hist["close"].astype(float)
            dates = hist["date"].tolist()

            last_close = float(closes.iloc[-1])
            offset = min(lookback_days, len(closes) - 1)
            period_close = float(closes.iloc[-1 - offset]) if offset > 0 else last_close
            change_pct = ((last_close - period_close) / period_close) * 100 if period_close else 0
            prices[sym] = {"price": last_close, "change": change_pct}

            trim = min(lookback_days, len(closes))
            sparklines[sym] = {"closes": closes.tolist()[-trim:], "dates": dates[-trim:]}

    scores.sort(key=lambda s: s.total_score, reverse=True)

    # Explain the scoring system once
    with st.expander("📚 How Opportunity Scores Work", expanded=False):
        st.markdown("""
Opportunity scores combine **four factors** (25 points each, 100 total):

| Factor | Weight | What It Measures | High Score Means |
|--------|--------|-----------------|-----------------|
| **Volume** | 25% | Recent volume vs 20-day average | Unusual activity — institutions may be accumulating |
| **Price** | 25% | RSI momentum + trend + MACD direction | Strong momentum in a clear trend |
| **Flow** | 25% | Options put/call ratio + insider buying | Smart money is positioning bullishly |
| **Risk/Reward** | 25% | Distance to support vs resistance | More upside potential than downside risk |

| Score Range | Label | Meaning |
|------------|-------|---------|
| **80-100** | Excellent | Multiple signals aligned — strong opportunity |
| **60-79** | Good | Favorable setup with some confirmation |
| **40-59** | Fair | Mixed signals — proceed with caution |
| **0-39** | Poor | Weak setup — wait for better entry |
        """)

    # Strategy info lookup (defined once)
    strategy_info = {
        "Volume Spike": {"color": "#3b82f6", "icon": "📊", "short": "Unusual volume detected"},
        "Momentum": {"color": "#22c55e", "icon": "🚀", "short": "Strong price momentum"},
        "Breakout": {"color": "#f59e0b", "icon": "💥", "short": "Near resistance breakout"},
        "Oversold Bounce": {"color": "#06b6d4", "icon": "🔄", "short": "Oversold — potential reversal"},
        "Mean Reversion": {"color": "#8b5cf6", "icon": "📉", "short": "Below average — may revert"},
        "Golden Cross": {"color": "#fbbf24", "icon": "✨", "short": "SMA50 crossing above SMA200"},
        "Death Cross": {"color": "#dc2626", "icon": "💀", "short": "SMA50 crossing below SMA200"},
        "Insider Accumulation": {"color": "#10b981", "icon": "🏦", "short": "Multiple insiders buying"},
        "Congress Buying": {"color": "#6366f1", "icon": "🏛️", "short": "Bipartisan congressional buying"},
        "Earnings Catalyst": {"color": "#f97316", "icon": "📅", "short": "Earnings within 14 days"},
        "Dividend Play": {"color": "#14b8a6", "icon": "💵", "short": "High dividend yield"},
        "Bollinger Squeeze": {"color": "#a855f7", "icon": "🔧", "short": "Volatility squeeze — breakout coming"},
        "Support Bounce": {"color": "#0ea5e9", "icon": "🛡️", "short": "Price at support level"},
        "Gap Fill": {"color": "#78716c", "icon": "📐", "short": "Price filling a gap"},
        "Sector Leader": {"color": "#eab308", "icon": "👑", "short": "Top in strongest sector"},
        "Neutral": {"color": "#6b7280", "icon": "⏸️", "short": "No clear setup"},
    }

    # 2-column card grid
    for row_start in range(0, len(scores), 2):
        cols = st.columns(2)
        for col_idx in range(2):
            i = row_start + col_idx
            if i >= len(scores):
                break
            score = scores[i]
            with cols[col_idx]:
                css_class = "score-excellent" if score.total_score >= 80 else "score-good" if score.total_score >= 60 else "score-fair" if score.total_score >= 40 else "score-poor"
                border_style = "border-color: #f59e0b;" if i == 0 else ""

                p = prices.get(score.symbol, {})
                price_str = f"${p['price']:.2f}" if p.get("price") else "—"
                chg = p.get("change", 0)
                chg_color = "#22c55e" if chg > 0 else "#ef4444" if chg < 0 else "#9ca3af"
                chg_arrow = "↑" if chg > 0 else "↓" if chg < 0 else ""
                chg_str = f"{chg_arrow} {chg:+.2f}%" if p.get("price") else ""

                strat = strategy_info.get(score.strategy, strategy_info["Neutral"])
                secondaries = getattr(score, "secondary_strategies", [])

                # Card header
                st.markdown(f"""<div class="signal-card" style="{border_style} padding:16px;">
                    <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                        <div>
                            <div style="display:flex; align-items:center; gap:8px;">
                                <span style="color:#6b7280; font-size:13px;">#{i+1}</span>
                                <span style="font-size:20px; font-weight:800; color:#e5e5e5;">{score.symbol}</span>
                                <span class="score-badge {css_class}" style="font-size:14px; padding:3px 10px;">{score.total_score}</span>
                            </div>
                            <div style="margin-top:4px;">
                                <span style="font-size:18px; font-weight:700; color:#e5e5e5;">{price_str}</span>
                                <span style="font-size:14px; font-weight:600; color:{chg_color}; margin-left:8px;">{chg_str}</span>
                                <span style="font-size:12px; color:#6b7280; margin-left:4px;">{disc_period}</span>
                            </div>
                        </div>
                        <div style="text-align:right;">
                            <div style="padding:4px 10px; background:{strat['color']}15; border:1px solid {strat['color']}44; border-radius:8px;">
                                <span style="font-size:14px;">{strat['icon']}</span>
                                <span style="font-size:12px; font-weight:700; color:{strat['color']};">{score.strategy}</span>
                            </div>
                            <div style="font-size:11px; color:#6b7280; margin-top:2px;">{strat['short']}</div>
                        </div>
                    </div>
                </div>""", unsafe_allow_html=True)

                # Sparkline chart
                spark = sparklines.get(score.symbol)
                if spark and len(spark["closes"]) > 2:
                    spark_color = "#22c55e" if spark["closes"][-1] >= spark["closes"][0] else "#ef4444"
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(
                        x=spark["dates"], y=spark["closes"], mode="lines",
                        line=dict(color=spark_color, width=2),
                        fill="tozeroy", fillcolor=f"rgba({','.join(str(int(spark_color[i:i+2], 16)) for i in (1,3,5))},0.06)",
                    ))
                    fig.update_layout(
                        template="plotly_dark", height=120, margin=dict(l=0, r=0, t=0, b=0),
                        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                        xaxis=dict(visible=False), yaxis=dict(visible=False),
                        showlegend=False,
                    )
                    st.plotly_chart(fig, use_container_width=True, key=f"spark_{score.symbol}")

                # 4 sub-scores as compact bars
                sub_scores = [
                    ("Vol", score.volume_score, 25),
                    ("Price", score.price_score, 25),
                    ("Flow", score.flow_score, 25),
                    ("R/R", score.risk_reward_score, 25),
                ]
                bar_html = ""
                for name, val, mx in sub_scores:
                    pct = max(min(val / mx * 100, 100), 3)
                    c = "#22c55e" if val >= 18 else "#ef4444" if val <= 8 else "#f59e0b"
                    bar_html += f"""<div style="flex:1;">
                        <div style="font-size:10px; color:#6b7280; margin-bottom:2px;">{name} <span style="color:{c}; font-weight:600;">{val}</span></div>
                        <div style="height:4px; background:#2a2a2a; border-radius:2px;">
                            <div style="height:100%; width:{pct}%; background:{c}; border-radius:2px;"></div>
                        </div>
                    </div>"""
                st.markdown(f'<div style="display:flex; gap:8px; margin:4px 0 8px;">{bar_html}</div>', unsafe_allow_html=True)

                # Secondary strategy pills
                if secondaries:
                    pills = "".join(
                        f'<span style="display:inline-block; margin:0 4px 4px 0; padding:2px 8px; background:{strategy_info.get(s, strategy_info["Neutral"])["color"]}11; border:1px solid {strategy_info.get(s, strategy_info["Neutral"])["color"]}44; border-radius:12px; font-size:10px; color:{strategy_info.get(s, strategy_info["Neutral"])["color"]};">{strategy_info.get(s, strategy_info["Neutral"])["icon"]} {s}</span>'
                        for s in secondaries[:4]
                    )
                    st.markdown(pills, unsafe_allow_html=True)

                # Action buttons
                btn_col1, btn_col2 = st.columns([3, 1])
                with btn_col1:
                    if st.button(f"Deep Dive →", key=f"dive_{score.symbol}", use_container_width=True):
                        navigate_to(3, score.symbol)
                with btn_col2:
                    if st.button("🗑", key=f"rm_{score.symbol}"):
                        remove_watchlist_item(score.symbol)
                        st.rerun()


# ═══════════════════════════════════════════════════════════════
# STEP 3: DEEP DIVE
# ═══════════════════════════════════════════════════════════════

def page_deep_dive():
    st.title("📊 Deep Dive")

    symbol = st.session_state.selected_stock
    if not symbol:
        symbol = st.text_input("Enter ticker to analyze", placeholder="AAPL", max_chars=10)
        if not symbol:
            st.info("Select a stock from Discover, or enter a ticker above.")
            return
        symbol = symbol.upper()
        st.session_state.selected_stock = symbol

    st.caption(f"Full signal breakdown for **{symbol}**")

    # Run analysis (cached)
    if st.session_state.cached_report_symbol != symbol:
        with st.spinner(f"Analyzing {symbol}..."):
            from src.orchestrator import analyze_stock
            report = analyze_stock(symbol, export=True)
            st.session_state.cached_report = report
            st.session_state.cached_report_symbol = symbol
    report = st.session_state.cached_report

    if not report:
        st.error("Analysis failed.")
        return

    # Verdict banner
    v = report.verdict.value
    v_class = "verdict-buy" if "Buy" in v else "verdict-sell" if "Sell" in v else "verdict-hold"
    v_color = "#22c55e" if "Buy" in v else "#ef4444" if "Sell" in v else "#f59e0b"

    st.markdown(f"""<div class="dark-card {v_class}" style="text-align:center; padding:24px;">
        <div style="font-size:36px; font-weight:800; color:{v_color};">{v}</div>
        <div style="display:flex; justify-content:center; gap:40px; margin-top:12px;">
            <div><span class="text-sm">Price</span><br><span class="text-lg">${report.current_price}</span></div>
            <div><span class="text-sm">Confidence</span><br><span class="text-lg">{report.confidence}</span></div>
            <div><span class="text-sm">Risk</span><br><span class="text-lg">{report.risk_rating.value}/5</span></div>
            <div><span class="text-sm">Sentiment</span><br><span class="text-lg">{report.sentiment_score}</span></div>
        </div>
    </div>""", unsafe_allow_html=True)

    # Reasoning
    st.markdown("### Analysis Reasoning")
    for r in report.reasoning:
        st.markdown(f"- {r}")

    # Signal bars with WHY
    st.markdown("### Signal Breakdown")
    _render_signal_bars(report)

    # Charts and extras in tabs
    tab_chart, tab_earnings, tab_volume = st.tabs(["📈 Price Chart", "📅 Earnings", "📊 Volume Profile"])
    with tab_chart:
        _render_multi_timeframe_chart(symbol)
    with tab_earnings:
        _render_earnings_calendar(symbol)
    with tab_volume:
        _render_volume_profile(symbol)

    # Risks
    if report.risks:
        st.markdown("### ⚠ Risks")
        for r in report.risks:
            st.markdown(f"- 🔴 {r}")

    _render_step_cta("Prove It — Test These Signals", 4, symbol)


# ═══════════════════════════════════════════════════════════════
# STEP 4: PROVE IT
# ═══════════════════════════════════════════════════════════════

def page_prove_it():
    st.title("🔬 Prove It")

    symbol = st.session_state.selected_stock
    if not symbol:
        symbol = st.text_input("Enter ticker to backtest", placeholder="AAPL", max_chars=10)
        if not symbol:
            st.info("Select a stock from Deep Dive, or enter a ticker above.")
            return
        symbol = symbol.upper()

    st.caption(f"Historical signal validation for **{symbol}**")

    from src.data.gateway import DataGateway
    from src.analysis.backtester import backtest_all_signals, backtest_signal, SIGNALS

    gw = DataGateway()
    hold_days = st.selectbox("Hold period (days)", [7, 14, 30, 60], index=2)

    with st.spinner(f"Backtesting {symbol} with {hold_days}-day hold..."):
        hist = gw.get_historical(symbol, period_days=365)

    if hist is None or hist.empty or len(hist) < 60:
        st.warning("Not enough historical data for backtesting.")
        return

    # Signal accuracy ranking
    tab_accuracy, tab_explorer, tab_portfolio = st.tabs(["📊 Signal Accuracy", "🔍 Signal Explorer", "💼 Multi-Stock Sim"])

    with tab_accuracy:
        st.markdown("### Signal Accuracy Ranking")
        st.markdown('<p class="text-sm">Which signals actually made money historically?</p>', unsafe_allow_html=True)

        results = backtest_all_signals(symbol, hist, hold_days)
        results = [r for r in results if r.total_trades > 0]
        results.sort(key=lambda r: r.win_rate * 100 + r.avg_return, reverse=True)

        for i, r in enumerate(results[:10]):
            grade_colors = {"A+": "#22c55e", "A": "#22c55e", "B+": "#86efac", "B": "#f59e0b", "C": "#9ca3af", "D": "#ef4444"}
            gc = grade_colors.get(r.grade, "#6b7280")
            st.markdown(f"""<div class="signal-card">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <div>
                        <span style="color:#6b7280;">#{i+1}</span>
                        <span style="font-weight:700; color:#e5e5e5; margin-left:8px;">{r.signal_name.replace('_', ' ').title()}</span>
                        <span class="text-sm" style="margin-left:8px;">{SIGNALS.get(r.signal_name, {}).get('description', '')}</span>
                    </div>
                    <span class="score-badge" style="background:{gc}33; color:{gc}; border:1px solid {gc};">{r.grade}</span>
                </div>
                <div style="display:flex; gap:20px; margin-top:8px;">
                    <span>Win Rate: <b class="{'text-green' if r.win_rate >= 0.6 else 'text-red' if r.win_rate < 0.4 else 'text-orange'}">{r.win_rate*100:.0f}%</b></span>
                    <span>Avg Return: <b class="{'text-green' if r.avg_return > 0 else 'text-red'}">{r.avg_return:+.1f}%</b></span>
                    <span>Trades: <b>{r.total_trades}</b></span>
                    <span>Best: <b class="text-green">{r.max_gain:+.1f}%</b></span>
                    <span>Worst: <b class="text-red">{r.max_loss:+.1f}%</b></span>
                </div>
            </div>""", unsafe_allow_html=True)

        if results:
            best = results[0]
            st.markdown(f"""<div class="why-box">
                <b>Best Strategy:</b> {best.signal_name.replace('_', ' ').title()} — {best.win_rate*100:.0f}% win rate
                with {best.avg_return:+.1f}% avg return over {hold_days} days. Grade: {best.grade}.
            </div>""", unsafe_allow_html=True)

    with tab_explorer:
        st.markdown("### Signal Explorer")
        signal_name = st.selectbox("Select signal", list(SIGNALS.keys()),
                                    format_func=lambda s: f"{s.replace('_', ' ').title()} — {SIGNALS[s]['description']}")

        result = backtest_signal(symbol, hist, signal_name, hold_days)

        if result and result.trades:
            # Chart with markers
            fig = go.Figure()
            fig.add_trace(go.Candlestick(x=hist["date"], open=hist["open"], high=hist["high"],
                                          low=hist["low"], close=hist["close"], name="Price"))

            wins = [t for t in result.trades if t.outcome == "win"]
            losses = [t for t in result.trades if t.outcome == "loss"]

            if wins:
                fig.add_trace(go.Scatter(
                    x=[t.entry_date for t in wins], y=[t.entry_price for t in wins],
                    mode="markers", name="Win", marker=dict(color="#22c55e", size=12, symbol="triangle-up"),
                    text=[f"{t.signal_name}: {t.pnl_percent:+.1f}%" for t in wins], hovertemplate="%{text}",
                ))
            if losses:
                fig.add_trace(go.Scatter(
                    x=[t.entry_date for t in losses], y=[t.entry_price for t in losses],
                    mode="markers", name="Loss", marker=dict(color="#ef4444", size=12, symbol="triangle-down"),
                    text=[f"{t.signal_name}: {t.pnl_percent:+.1f}%" for t in losses], hovertemplate="%{text}",
                ))

            fig.update_layout(template="plotly_dark", height=450, plot_bgcolor="#0a0a0a", paper_bgcolor="#0a0a0a",
                              xaxis_rangeslider_visible=False, title=f"{signal_name.replace('_', ' ').title()} — {symbol}")
            st.plotly_chart(fig, use_container_width=True)

            # Trade log
            trades_df = pd.DataFrame([{
                "Entry": t.entry_date, "Exit": t.exit_date,
                "Entry $": f"${t.entry_price:.2f}", "Exit $": f"${t.exit_price:.2f}",
                "P/L %": f"{t.pnl_percent:+.1f}%", "Outcome": "✅" if t.outcome == "win" else "❌",
                "Days": t.hold_days,
            } for t in result.trades])
            st.dataframe(trades_df, use_container_width=True, hide_index=True)
        else:
            st.info(f"No trades triggered for {signal_name} in the last year.")

    with tab_portfolio:
        st.markdown("### Multi-Stock Portfolio Simulation")

        watchlist = get_watchlist()
        available = [w["symbol"] for w in watchlist] if watchlist else []
        if symbol not in available:
            available.insert(0, symbol)

        selected = st.multiselect("Select stocks for simulation", available, default=[symbol])
        strategy = st.selectbox("Strategy signal", list(SIGNALS.keys()), key="port_strategy",
                                 format_func=lambda s: f"{s.replace('_', ' ').title()}")
        capital = st.number_input("Starting capital ($)", value=100000, step=10000)

        if selected and st.button("Run Simulation", type="primary"):
            from src.analysis.portfolio_sim import simulate_portfolio
            import yfinance as yf

            with st.spinner("Simulating portfolio..."):
                hist_data = {}
                for s in selected:
                    h = gw.get_historical(s, period_days=365)
                    if h is not None and not h.empty:
                        hist_data[s] = h

                spy = yf.download("SPY", period="1y", progress=False, auto_adjust=True)
                if hasattr(spy.columns, 'levels') and spy.columns.nlevels > 1:
                    spy.columns = spy.columns.get_level_values(0)
                spy = spy.reset_index().rename(columns={"Date": "date", "Open": "open", "High": "high",
                                                          "Low": "low", "Close": "close", "Volume": "volume"})
                spy["date"] = spy["date"].dt.strftime("%Y-%m-%d")

                result = simulate_portfolio(list(hist_data.keys()), hist_data, spy, strategy, capital)

            if result and result.equity_curve:
                # Equity curve chart
                dates = [s.date for s in result.equity_curve]
                values = [s.cumulative_return * 100 for s in result.equity_curve]
                bench = [s.benchmark_return * 100 for s in result.equity_curve]

                fig = go.Figure()
                fig.add_trace(go.Scatter(x=dates, y=values, name="Portfolio", line=dict(color="#22c55e", width=2)))
                fig.add_trace(go.Scatter(x=dates, y=bench, name="S&P 500", line=dict(color="#6b7280", width=1, dash="dash")))
                fig.update_layout(template="plotly_dark", height=400, plot_bgcolor="#0a0a0a", paper_bgcolor="#0a0a0a",
                                  title="Portfolio vs S&P 500", yaxis_title="Return %")
                st.plotly_chart(fig, use_container_width=True)

                # Stats
                cols = st.columns(5)
                cols[0].metric("Total Return", f"{result.total_return*100:+.1f}%")
                cols[1].metric("Alpha", f"{result.alpha*100:+.1f}%")
                cols[2].metric("Sharpe", f"{result.sharpe_ratio:.2f}")
                cols[3].metric("Max Drawdown", f"{result.max_drawdown*100:.1f}%")
                cols[4].metric("Win Rate", f"{result.win_rate*100:.0f}%")

                st.markdown(f"""<div class="why-box">
                    <b>Result:</b> ${capital:,.0f} → ${result.final_value:,.0f}
                    ({result.total_return*100:+.1f}%) using {strategy.replace('_', ' ')} strategy.
                    {"Beating" if result.alpha > 0 else "Underperforming"} S&P 500 by {abs(result.alpha)*100:.1f}%.
                </div>""", unsafe_allow_html=True)

    _render_step_cta("Track My Real Trades", 5)


# ═══════════════════════════════════════════════════════════════
# STEP 5: MY PORTFOLIO
# ═══════════════════════════════════════════════════════════════

def page_portfolio():
    st.title("💼 My Portfolio")
    st.caption("Log trades, track P/L, measure which signals make you money")

    from src.journal import log_trade, close_trade, get_open_trades, get_trade_history, get_performance_stats

    tab_overview, tab_log, tab_history = st.tabs(["📊 Overview", "📝 Log Trade", "📋 History"])

    with tab_overview:
        stats = get_performance_stats()

        cols = st.columns(4)
        pnl_color = "normal" if stats.total_pnl == 0 else ("off" if stats.total_pnl < 0 else "normal")
        cols[0].metric("Total P/L", f"${stats.total_pnl:+,.2f}")
        cols[1].metric("Win Rate", f"{stats.win_rate*100:.0f}%" if stats.closed_trades > 0 else "—")
        cols[2].metric("Trades", f"{stats.closed_trades} ({stats.wins}W / {stats.losses}L)")
        cols[3].metric("Expectancy", f"${stats.expectancy:+,.2f}" if stats.closed_trades > 0 else "—")

        # Equity curve
        eq_fig = _build_equity_curve_from_journal()
        if eq_fig:
            st.plotly_chart(eq_fig, use_container_width=True)

        # Report accuracy
        if stats.report_accuracy:
            st.markdown("### Report Accuracy")
            st.markdown('<p class="text-sm">How accurate are the app\'s verdicts when you trade on them?</p>', unsafe_allow_html=True)
            rows = []
            for verdict, data in stats.report_accuracy.items():
                rows.append({"Verdict": verdict, "Trades": data["trades"], "Wins": data["wins"],
                             "Win Rate": f"{data['win_rate']*100:.0f}%"})
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

            best_verdict = max(stats.report_accuracy.items(), key=lambda x: x[1]["win_rate"])[0] if stats.report_accuracy else None
            if best_verdict:
                st.markdown(f"""<div class="why-box">
                    <b>Insight:</b> Your best results come from <b>{best_verdict}</b> verdicts.
                    Consider focusing on these signals for higher win rates.
                </div>""", unsafe_allow_html=True)

        # Open positions
        open_trades = get_open_trades()
        if open_trades:
            st.markdown("### Open Positions")
            for t in open_trades:
                col1, col2, col3 = st.columns([3, 2, 1])
                with col1:
                    st.markdown(f"**{t.symbol}** — {t.direction.upper()} | {t.shares} shares @ ${t.entry_price:.2f}")
                with col2:
                    exit_price = st.number_input("Exit $", min_value=0.01, step=0.01, key=f"exit_{t.id}")
                with col3:
                    if st.button("Close", key=f"close_{t.id}"):
                        close_trade(t.id, exit_price)
                        st.rerun()

    with tab_log:
        st.markdown("### Log New Trade")
        with st.form("log_trade_form"):
            c1, c2 = st.columns(2)
            with c1:
                sym = st.text_input("Symbol", placeholder="AAPL", max_chars=10)
                direction = st.selectbox("Direction", ["long", "short"])
                entry_price = st.number_input("Entry Price ($)", min_value=0.01, step=0.01)
            with c2:
                shares = st.number_input("Shares", min_value=1, step=1, value=100)
                verdict = st.selectbox("Report Verdict", ["Strong Buy", "Buy", "Hold", "Sell", "Strong Sell", ""])
                thesis = st.text_area("Thesis / Notes", placeholder="Why are you taking this trade?")

            if st.form_submit_button("Log Trade", type="primary"):
                if sym and entry_price > 0:
                    trade_id = log_trade(sym.upper(), direction, entry_price, shares, thesis, verdict)
                    st.success(f"Trade #{trade_id} logged for {sym.upper()}")
                    st.rerun()

    with tab_history:
        st.markdown("### Trade History")
        trades = get_trade_history()
        if trades:
            rows = []
            for t in trades:
                rows.append({
                    "Symbol": t.symbol, "Dir": t.direction, "Entry": f"${t.entry_price:.2f}",
                    "Exit": f"${t.exit_price:.2f}" if t.exit_price else "Open",
                    "Shares": t.shares,
                    "P/L": f"${t.pnl:+,.2f}" if t.pnl is not None else "—",
                    "P/L %": f"{t.pnl_percent:+.1f}%" if t.pnl_percent is not None else "—",
                    "Verdict": t.report_verdict or "—",
                    "Date": t.entry_date,
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.info("No trades logged yet. Use the 'Log Trade' tab to record your first trade.")


# ═══════════════════════════════════════════════════════════════
# Page Router
# ═══════════════════════════════════════════════════════════════

render_navigation()

step = st.session_state.current_step
if step == 1:
    page_market_pulse()
elif step == 2:
    page_discover()
elif step == 3:
    page_deep_dive()
elif step == 4:
    page_prove_it()
elif step == 5:
    page_portfolio()

st.markdown('<div class="disclaimer">This is AI-generated analysis for informational purposes only. Not financial advice.</div>', unsafe_allow_html=True)
