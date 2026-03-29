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
    /* ── Global ───────────────────────────────────────── */
    .stApp { background: #0a0a0a; }
    section[data-testid="stSidebar"] { background: #0d0d0d; }
    #MainMenu, footer, header { visibility: hidden; }
    .stDeployButton { display: none; }
    h1, h2, h3 { color: #e5e5e5 !important; letter-spacing: -0.3px; }
    p, li, span { color: #d1d5db; }
    .stTabs [data-baseweb="tab-list"] { gap: 4px; }
    .stTabs [data-baseweb="tab"] { background: #111; border: 1px solid #222; border-radius: 8px 8px 0 0; padding: 8px 16px; color: #9ca3af; font-weight: 600; }
    .stTabs [aria-selected="true"] { background: #1a1a1a; border-color: #333; color: #e5e5e5; }
    .stExpander { border: 1px solid #1a1a1a; border-radius: 10px; background: #0d0d0d; }
    .stDataFrame { border: 1px solid #1a1a1a; border-radius: 10px; }
    .stMetric { background: #111; border: 1px solid #1a1a1a; border-radius: 10px; padding: 12px; }
    .stMetric label { color: #6b7280 !important; font-size: 11px !important; text-transform: uppercase; letter-spacing: 0.5px; }
    .stMetric [data-testid="stMetricValue"] { color: #e5e5e5 !important; font-weight: 800; }
    div[data-testid="stForm"] { background: #111; border: 1px solid #1a1a1a; border-radius: 12px; padding: 20px; }
    .stSelectbox, .stMultiSelect, .stTextInput, .stNumberInput { border-radius: 8px; }
    ::-webkit-scrollbar { width: 6px; height: 6px; }
    ::-webkit-scrollbar-track { background: #0a0a0a; }
    ::-webkit-scrollbar-thumb { background: #333; border-radius: 3px; }
    ::-webkit-scrollbar-thumb:hover { background: #555; }

    /* ── Cards ─────────────────────────────────────────── */
    .dark-card { background: #111; border: 1px solid #1a1a1a; border-radius: 12px; padding: 20px; margin-bottom: 16px; }
    .dark-card h3 { margin-top: 0; color: #e5e5e5; }
    .signal-card { background: #111; border: 1px solid #1a1a1a; border-radius: 12px; padding: 16px; margin-bottom: 12px; }
    .signal-card-top { border-color: #f59e0b; }

    /* ── Badges ────────────────────────────────────────── */
    .badge-inflow { background: rgba(34,197,94,0.12); color: #22c55e; padding: 4px 12px; border-radius: 20px; font-weight: 700; font-size: 13px; }
    .badge-outflow { background: rgba(239,68,68,0.12); color: #ef4444; padding: 4px 12px; border-radius: 20px; font-weight: 700; font-size: 13px; }
    .score-badge { display: inline-block; padding: 6px 14px; border-radius: 8px; font-weight: 800; font-size: 18px; }
    .score-excellent { background: rgba(34,197,94,0.15); color: #22c55e; border: 1px solid #22c55e; }
    .score-good { background: rgba(245,158,11,0.15); color: #f59e0b; border: 1px solid #f59e0b; }
    .score-fair { background: rgba(107,114,128,0.15); color: #9ca3af; border: 1px solid #6b7280; }
    .score-poor { background: rgba(239,68,68,0.15); color: #ef4444; border: 1px solid #ef4444; }

    /* ── Verdict ───────────────────────────────────────── */
    .verdict-buy { background: rgba(34,197,94,0.08); border: 2px solid #22c55e; }
    .verdict-sell { background: rgba(239,68,68,0.08); border: 2px solid #ef4444; }
    .verdict-hold { background: rgba(245,158,11,0.08); border: 2px solid #f59e0b; }

    /* ── Text ──────────────────────────────────────────── */
    .status-green { color: #22c55e; font-weight: 700; }
    .status-orange { color: #f59e0b; font-weight: 700; }
    .status-red { color: #ef4444; font-weight: 700; }
    .status-gray { color: #9ca3af; font-weight: 700; }
    .text-sm { font-size: 13px; color: #9ca3af; }
    .text-lg { font-size: 20px; font-weight: 700; }
    .text-green { color: #22c55e; }
    .text-red { color: #ef4444; }
    .text-orange { color: #f59e0b; }

    /* ── Misc ──────────────────────────────────────────── */
    .disclaimer { text-align: center; font-size: 11px; color: #4b5563; padding: 16px; border-top: 1px solid #1a1a1a; margin-top: 24px; }
    .eco-card { background: #111; border: 1px solid #1a1a1a; border-radius: 12px; padding: 16px; text-align: center; }
    .eco-card .value { font-size: 24px; font-weight: 800; color: #e5e5e5; }
    .eco-card .label { font-size: 12px; color: #9ca3af; margin-top: 4px; }
    .why-box { background: #0d0d0d; border-left: 3px solid #3b82f6; padding: 12px 16px; margin: 8px 0; border-radius: 0 8px 8px 0; font-size: 14px; color: #d1d5db; line-height: 1.6; }
    .signal-bar-container { margin-bottom: 16px; }
    .signal-bar-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }
    .signal-bar-track { height: 8px; background: #1a1a1a; border-radius: 4px; overflow: hidden; }
    .signal-bar-fill { height: 100%; border-radius: 4px; }
    .step-active { border-bottom: 3px solid #22c55e !important; }
    .cta-box { text-align: center; padding: 20px 0; }

    /* ── Navigation ────────────────────────────────────── */
    div[data-testid="stHorizontalBlock"] > div:first-child { }
    .stButton button { border-radius: 8px; font-weight: 600; }
    .stButton button[kind="primary"] { background: linear-gradient(135deg, #22c55e, #16a34a); border: none; }
    .stButton button[kind="primary"]:hover { background: linear-gradient(135deg, #16a34a, #15803d); }
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
if "dd_multi_stocks" not in st.session_state:
    st.session_state.dd_multi_stocks = []


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
        (1, "Market Pulse", "Understand the market"),
        (2, "Discover", "Find opportunities"),
        (3, "Deep Dive", "Analyze signals"),
        (4, "Prove It", "Backtest & validate"),
        (5, "Portfolio", "Track your trades"),
        (6, "AI Agent", "Autonomous trading"),
    ]
    current = st.session_state.current_step

    # Progress bar
    progress_pct = (current - 1) / (len(steps) - 1) * 100
    st.markdown(
        f'<div style="height:3px; background:#1a1a1a; border-radius:2px; margin-bottom:8px;">'
        f'<div style="height:100%; width:{progress_pct}%; background:linear-gradient(to right, #22c55e, #3b82f6); border-radius:2px; transition:width 0.3s;"></div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    cols = st.columns(6)
    for col, (num, label, desc) in zip(cols, steps):
        with col:
            active = current == num
            completed = current > num
            if active:
                color = "#22c55e"
                icon = "●"
            elif completed:
                color = "#3b82f6"
                icon = "✓"
            else:
                color = "#333"
                icon = str(num)

            st.markdown(
                f'<div style="text-align:center; margin-bottom:4px;">'
                f'<div style="width:24px; height:24px; border-radius:50%; background:{color}; color:#fff; font-size:11px; font-weight:700; display:inline-flex; align-items:center; justify-content:center;">{icon}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
            btn_type = "primary" if active else "secondary"
            if st.button(label, key=f"nav_{num}", use_container_width=True, type=btn_type):
                navigate_to(num)
            st.markdown(f'<div style="text-align:center; font-size:10px; color:#6b7280; margin-top:-8px;">{desc}</div>', unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════
# Existing Helpers (preserved from previous dashboard)
# ═══════════════════════════════════════════════════════════════

def _freshness_badge(cache_key: str) -> str:
    """Return HTML badge showing how fresh the cached data is."""
    from src.utils.db import get_connection
    try:
        conn = get_connection()
        row = conn.execute("SELECT created_at FROM cache WHERE key = ?", (cache_key,)).fetchone()
        conn.close()
        if not row:
            return '<span style="font-size:10px; color:#ef4444;">No data</span>'
        from datetime import datetime
        created = datetime.fromisoformat(row["created_at"])
        age = datetime.utcnow() - created
        minutes = int(age.total_seconds() / 60)
        if minutes < 1:
            return '<span style="font-size:10px; color:#22c55e;">Just now</span>'
        elif minutes < 15:
            return f'<span style="font-size:10px; color:#22c55e;">{minutes}m ago</span>'
        elif minutes < 60:
            return f'<span style="font-size:10px; color:#f59e0b;">{minutes}m ago</span>'
        elif minutes < 1440:
            hours = minutes // 60
            return f'<span style="font-size:10px; color:#f59e0b;">{hours}h ago</span>'
        else:
            days = minutes // 1440
            return f'<span style="font-size:10px; color:#ef4444;">{days}d ago</span>'
    except Exception:
        return ""


def _section_header(title: str, cache_key: str = "", refresh_hint: str = "") -> None:
    """Render a section header with optional freshness badge."""
    freshness = _freshness_badge(cache_key) if cache_key else ""
    st.markdown(
        f'<div style="display:flex; align-items:center; justify-content:space-between; margin:20px 0 12px;">'
        f'<div style="display:flex; align-items:center; gap:8px;">'
        f'<div style="height:2px; width:30px; background:#333;"></div>'
        f'<span style="font-size:15px; font-weight:700; color:#e5e5e5;">{title}</span>'
        f'</div>'
        f'<div>{freshness}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


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
                                marker_color=["#f59e0b" if p == poc else "rgba(59,130,246,0.27)" for p in prices]))
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


def _score_single_stock_fresh(symbol: str) -> dict | None:
    """Score a single stock from scratch — called by background job."""
    from src.analysis import technical
    from src.analysis.opportunity import compute_opportunity
    from src.data.gateway import DataGateway
    from src.utils.db import save_precomputed_score

    try:
        gw = DataGateway()
        hist = gw.get_historical(symbol, period_days=252)
        tech_result = None
        if hist is not None and not hist.empty:
            tech_result = technical.analyze(symbol, hist)
        score = compute_opportunity(symbol, tech_result)
        try:
            gw.get_fundamentals(symbol)
        except Exception:
            pass

        # Save to DB for instant access
        score_dict = {
            "total_score": score.total_score,
            "volume_score": score.volume_score,
            "price_score": score.price_score,
            "flow_score": score.flow_score,
            "risk_reward_score": score.risk_reward_score,
            "risk_reward_ratio": score.risk_reward_ratio,
            "strategy": score.strategy,
            "secondary_strategies": score.secondary_strategies,
            "label": score.label,
        }
        save_precomputed_score(symbol, score_dict)

        return {"score": score, "tech": tech_result, "hist": hist}
    except Exception:
        return None


def _batch_score_watchlist(symbols: tuple[str, ...]) -> dict:
    """Score watchlist stocks. Uses pre-computed DB scores if fresh, computes missing ones."""
    from src.utils.db import get_all_precomputed_scores, get_precomputed_score
    from src.analysis.opportunity import OpportunityScore
    import threading, time

    results = {}

    # Step 1: Check DB for pre-computed scores (instant)
    precomputed = get_all_precomputed_scores(max_age_minutes=60)
    symbols_needing_compute = []

    for sym in symbols:
        if sym in precomputed:
            # Reconstruct OpportunityScore from DB
            d = precomputed[sym]
            score = OpportunityScore(
                symbol=sym,
                total_score=d["total_score"],
                volume_score=d["volume_score"],
                price_score=d["price_score"],
                flow_score=d["flow_score"],
                risk_reward_score=d["risk_reward_score"],
                risk_reward_ratio=d["risk_reward_ratio"],
                strategy=d["strategy"],
                secondary_strategies=d.get("secondary_strategies", []),
                label=d["label"],
            )
            # Still need hist for charts — fetch from cache (should be instant)
            try:
                gw = _get_gateway()
                hist = gw.get_historical(sym, period_days=252)
                from src.analysis import technical
                tech = technical.analyze(sym, hist) if hist is not None and not hist.empty else None
                results[sym] = {"score": score, "tech": tech, "hist": hist}
            except Exception:
                results[sym] = {"score": score, "tech": None, "hist": None}
        else:
            symbols_needing_compute.append(sym)

    # Step 2: Compute missing ones in background threads
    if symbols_needing_compute:
        lock = threading.Lock()

        def _do_score(sym):
            data = _score_single_stock_fresh(sym)
            if data:
                with lock:
                    results[sym] = data

        threads = []
        for sym in symbols_needing_compute:
            t = threading.Thread(target=_do_score, args=(sym,))
            threads.append(t)
            t.start()
            time.sleep(0.3)

        for t in threads:
            t.join(timeout=30)

    return results


def _precompute_watchlist_scores_background():
    """Run in background thread on app startup — pre-computes all watchlist scores."""
    import threading

    def _worker():
        try:
            watchlist = get_watchlist()
            if not watchlist:
                return
            for item in watchlist:
                sym = item["symbol"]
                _score_single_stock_fresh(sym)
                import time
                time.sleep(0.5)
        except Exception:
            pass

    t = threading.Thread(target=_worker, daemon=True)
    t.start()


# Start pre-computing on app load
_precompute_watchlist_scores_background()

# Start agent background scheduler (if frequency is set)
if "agent_scheduler_started" not in st.session_state:
    try:
        from src.scheduler import start_agent_scheduler
        start_agent_scheduler()
        st.session_state.agent_scheduler_started = True
    except Exception:
        st.session_state.agent_scheduler_started = False


def _detect_signals_on_history(hist_df, symbol: str) -> list[dict]:
    """Walk historical prices, detect signals at each point, return markers."""
    if hist_df is None or hist_df.empty or len(hist_df) < 30:
        return []

    import ta as ta_lib
    closes = hist_df["close"].astype(float)
    highs = hist_df["high"].astype(float) if "high" in hist_df else closes
    lows = hist_df["low"].astype(float) if "low" in hist_df else closes
    dates = hist_df["date"].tolist()

    rsi = ta_lib.momentum.RSIIndicator(closes, window=14).rsi()
    macd_ind = ta_lib.trend.MACD(closes)
    macd_line = macd_ind.macd()
    macd_signal = macd_ind.macd_signal()
    sma50 = closes.rolling(50).mean()
    sma200 = closes.rolling(200).mean()

    signals = []
    for i in range(1, len(closes)):
        date = dates[i]
        price = float(closes.iloc[i])
        detected = []

        # RSI oversold
        if rsi.iloc[i] is not None and rsi.iloc[i] < 30:
            detected.append(("RSI Oversold", "buy", f"RSI {rsi.iloc[i]:.0f}"))
        # RSI overbought
        elif rsi.iloc[i] is not None and rsi.iloc[i] > 70:
            detected.append(("RSI Overbought", "sell", f"RSI {rsi.iloc[i]:.0f}"))

        # MACD crossover
        if i > 0 and macd_line.iloc[i] is not None and macd_signal.iloc[i] is not None:
            if macd_line.iloc[i] > macd_signal.iloc[i] and macd_line.iloc[i-1] <= macd_signal.iloc[i-1]:
                detected.append(("MACD Bullish Cross", "buy", "MACD crossed above signal"))
            elif macd_line.iloc[i] < macd_signal.iloc[i] and macd_line.iloc[i-1] >= macd_signal.iloc[i-1]:
                detected.append(("MACD Bearish Cross", "sell", "MACD crossed below signal"))

        # Golden/Death cross
        if i > 0 and not pd.isna(sma50.iloc[i]) and not pd.isna(sma200.iloc[i]):
            if sma50.iloc[i] > sma200.iloc[i] and sma50.iloc[i-1] <= sma200.iloc[i-1]:
                detected.append(("Golden Cross", "buy", "SMA50 crossed above SMA200"))
            elif sma50.iloc[i] < sma200.iloc[i] and sma50.iloc[i-1] >= sma200.iloc[i-1]:
                detected.append(("Death Cross", "sell", "SMA50 crossed below SMA200"))

        # Add signals with 30-day outcome if data exists
        for name, direction, detail in detected:
            outcome_idx = min(i + 30, len(closes) - 1)
            future_price = float(closes.iloc[outcome_idx])
            pnl_pct = ((future_price - price) / price) * 100
            if direction == "sell":
                pnl_pct = -pnl_pct
            signals.append({
                "date": date, "price": price, "signal": name,
                "direction": direction, "detail": detail,
                "outcome_price": future_price,
                "outcome_pct": round(pnl_pct, 1),
                "outcome_days": outcome_idx - i,
                "win": pnl_pct > 0,
            })

    return signals


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
    st.title("Market Pulse")
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

    # ── Economic Calendar ───────────────────────────────────────
    _render_economic_calendar()

    # ── Yield Curve Card ───────────────────────────────────────
    _section_header("Yield Curve", "macro:snapshot")
    _render_yield_curve_section(snapshot)

    # ── Geopolitical & Event Risk ─────────────────────────────
    _render_geopolitical_risks()

    # ── Disruptive Technology ──────────────────────────────────
    _render_disruption_section()

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

# Searchable stock database: ticker → (name, sector, keywords)
STOCK_DB = {
    # Mega cap tech
    "AAPL": ("Apple Inc", "Technology", "iphone mac consumer electronics"),
    "MSFT": ("Microsoft Corp", "Technology", "cloud azure ai software enterprise"),
    "GOOG": ("Alphabet Inc", "Technology", "google search ads ai cloud youtube"),
    "AMZN": ("Amazon.com Inc", "Consumer Discretionary", "ecommerce cloud aws retail"),
    "NVDA": ("NVIDIA Corp", "Technology", "gpu ai chips semiconductors gaming data center"),
    "META": ("Meta Platforms", "Technology", "facebook instagram social media metaverse ads"),
    "TSLA": ("Tesla Inc", "Consumer Discretionary", "ev electric vehicle auto energy battery"),
    "BRK-B": ("Berkshire Hathaway", "Financials", "buffett insurance conglomerate value"),
    # Finance
    "JPM": ("JPMorgan Chase", "Financials", "bank investment banking finance"),
    "V": ("Visa Inc", "Financials", "payments credit card fintech"),
    "MA": ("Mastercard Inc", "Financials", "payments credit card fintech"),
    "BAC": ("Bank of America", "Financials", "bank consumer finance"),
    "GS": ("Goldman Sachs", "Financials", "investment bank wall street trading"),
    "MS": ("Morgan Stanley", "Financials", "investment bank wealth management"),
    # Healthcare / Pharma
    "JNJ": ("Johnson & Johnson", "Healthcare", "pharma medical devices consumer health"),
    "UNH": ("UnitedHealth Group", "Healthcare", "health insurance managed care"),
    "PFE": ("Pfizer Inc", "Healthcare", "pharma drugs vaccine biotech"),
    "ABBV": ("AbbVie Inc", "Healthcare", "pharma biotech immunology"),
    "MRK": ("Merck & Co", "Healthcare", "pharma oncology vaccine"),
    "LLY": ("Eli Lilly", "Healthcare", "pharma glp-1 ozempic weight loss diabetes"),
    "NVO": ("Novo Nordisk", "Healthcare", "pharma glp-1 wegovy obesity diabetes"),
    "ISRG": ("Intuitive Surgical", "Healthcare", "robotics surgical robots medical devices"),
    # Consumer
    "WMT": ("Walmart Inc", "Consumer Staples", "retail grocery discount"),
    "PG": ("Procter & Gamble", "Consumer Staples", "consumer goods household"),
    "KO": ("Coca-Cola Co", "Consumer Staples", "beverages drinks"),
    "PEP": ("PepsiCo Inc", "Consumer Staples", "beverages snacks frito lay"),
    "COST": ("Costco Wholesale", "Consumer Staples", "retail warehouse membership"),
    "MCD": ("McDonald's Corp", "Consumer Discretionary", "fast food restaurant"),
    "SBUX": ("Starbucks Corp", "Consumer Discretionary", "coffee restaurant"),
    "NKE": ("Nike Inc", "Consumer Discretionary", "shoes apparel sports"),
    "HD": ("Home Depot", "Consumer Discretionary", "home improvement retail construction"),
    "DIS": ("Walt Disney Co", "Communication Services", "entertainment streaming theme parks"),
    # Tech / Software
    "CRM": ("Salesforce Inc", "Technology", "crm cloud saas enterprise software"),
    "ORCL": ("Oracle Corp", "Technology", "database cloud enterprise software"),
    "ADBE": ("Adobe Inc", "Technology", "creative cloud design software saas"),
    "NFLX": ("Netflix Inc", "Communication Services", "streaming entertainment content"),
    "AMD": ("Advanced Micro Devices", "Technology", "semiconductors cpu gpu chips ai"),
    "INTC": ("Intel Corp", "Technology", "semiconductors cpu chips manufacturing"),
    "CSCO": ("Cisco Systems", "Technology", "networking infrastructure enterprise"),
    "QCOM": ("Qualcomm Inc", "Technology", "semiconductors mobile 5g wireless chips"),
    "AVGO": ("Broadcom Inc", "Technology", "semiconductors networking infrastructure"),
    # Energy
    "XOM": ("Exxon Mobil", "Energy", "oil gas petroleum refining"),
    "CVX": ("Chevron Corp", "Energy", "oil gas petroleum energy"),
    "OXY": ("Occidental Petroleum", "Energy", "oil gas carbon capture"),
    # Telecom
    "T": ("AT&T Inc", "Communication Services", "telecom wireless 5g"),
    "VZ": ("Verizon Communications", "Communication Services", "telecom wireless 5g"),
    # Industrial / Aerospace
    "BA": ("Boeing Co", "Industrials", "aerospace defense aircraft"),
    "LMT": ("Lockheed Martin", "Industrials", "defense aerospace military"),
    "RTX": ("RTX Corp", "Industrials", "defense aerospace missiles"),
    "CAT": ("Caterpillar Inc", "Industrials", "construction mining heavy equipment"),
    # Fintech / Growth
    "PYPL": ("PayPal Holdings", "Financials", "payments fintech digital wallet"),
    "SQ": ("Block Inc", "Financials", "payments fintech square cash app bitcoin"),
    "SHOP": ("Shopify Inc", "Technology", "ecommerce platform saas"),
    "COIN": ("Coinbase Global", "Financials", "crypto exchange bitcoin ethereum"),
    "SOFI": ("SoFi Technologies", "Financials", "fintech banking lending neobank"),
    # Mobility / Travel
    "UBER": ("Uber Technologies", "Industrials", "rideshare delivery transportation"),
    "ABNB": ("Airbnb Inc", "Consumer Discretionary", "travel vacation rental lodging"),
    "SNAP": ("Snap Inc", "Communication Services", "social media messaging ar"),
    # EV / Clean energy
    "RIVN": ("Rivian Automotive", "Consumer Discretionary", "ev electric vehicle truck"),
    "LCID": ("Lucid Group", "Consumer Discretionary", "ev electric vehicle luxury"),
    "ENPH": ("Enphase Energy", "Technology", "solar energy inverters clean"),
    # AI / Data
    "PLTR": ("Palantir Technologies", "Technology", "ai data analytics government defense"),
    "SNOW": ("Snowflake Inc", "Technology", "cloud data warehouse analytics"),
    "DDOG": ("Datadog Inc", "Technology", "cloud monitoring observability devops"),
    # Quantum / Nuclear
    "IONQ": ("IonQ Inc", "Technology", "quantum computing"),
    "RGTI": ("Rigetti Computing", "Technology", "quantum computing"),
    "SMR": ("NuScale Power", "Utilities", "nuclear smr energy"),
    "OKLO": ("Oklo Inc", "Utilities", "nuclear fission energy"),
    "CCJ": ("Cameco Corp", "Energy", "uranium nuclear mining"),
}

# Build display options: "AAPL — Apple Inc (Technology)"
STOCK_OPTIONS = {f"{ticker} — {name} ({sector})": ticker for ticker, (name, sector, _) in STOCK_DB.items()}
POPULAR_STOCKS = list(STOCK_DB.keys())


@st.cache_data(ttl=86400, show_spinner=False)  # Cache 24 hours — a ticker either exists or doesn't
def _validate_ticker(symbol: str) -> tuple[bool, str]:
    """Check if a ticker exists on Yahoo Finance. Returns (valid, name)."""
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        info = ticker.info
        name = info.get("shortName") or info.get("longName") or ""
        # Yahoo returns info for invalid tickers too, but with no price
        if not name and not info.get("regularMarketPrice"):
            return False, ""
        return True, name
    except Exception:
        return False, ""


def _search_stocks(query: str) -> list[str]:
    """Search stocks by ticker, name, sector, or keyword."""
    if not query:
        return POPULAR_STOCKS[:20]
    q = query.lower()
    results = []
    for ticker, (name, sector, keywords) in STOCK_DB.items():
        searchable = f"{ticker} {name} {sector} {keywords}".lower()
        if q in searchable:
            # Exact ticker match first
            score = 3 if q == ticker.lower() else 2 if q in name.lower() else 1
            results.append((score, ticker))
    results.sort(key=lambda x: (-x[0], x[1]))
    return [r[1] for r in results]


def _render_discover_card(sym: str, data: dict, lookback_days: int, disc_period: str, rank: int, strategy_info: dict):
    """Render a single stock card. Used by both cached and streaming paths."""
    from src.analysis.opportunity import explain_strategy

    score = data["score"]
    tech = data.get("tech")
    hist = data.get("hist")

    if not strategy_info:
        strategy_info = {
            "Volume Spike": {"color": "#3b82f6", "icon": "📊"}, "Momentum": {"color": "#22c55e", "icon": "🚀"},
            "Breakout": {"color": "#f59e0b", "icon": "💥"}, "Oversold Bounce": {"color": "#06b6d4", "icon": "🔄"},
            "Mean Reversion": {"color": "#8b5cf6", "icon": "📉"}, "Golden Cross": {"color": "#fbbf24", "icon": "✨"},
            "Death Cross": {"color": "#dc2626", "icon": "💀"}, "Insider Accumulation": {"color": "#10b981", "icon": "🏦"},
            "Congress Buying": {"color": "#6366f1", "icon": "🏛"}, "Earnings Catalyst": {"color": "#f97316", "icon": "📅"},
            "Dividend Play": {"color": "#14b8a6", "icon": "💵"}, "Bollinger Squeeze": {"color": "#a855f7", "icon": "🔧"},
            "Support Bounce": {"color": "#0ea5e9", "icon": "🛡"}, "Gap Fill": {"color": "#78716c", "icon": "📐"},
            "Sector Leader": {"color": "#eab308", "icon": "👑"}, "Neutral": {"color": "#6b7280", "icon": "⏸"},
        }

    # Price + change
    last_price = None
    chg_pct = 0.0
    if hist is not None and not hist.empty:
        closes = hist["close"].astype(float)
        last_price = float(closes.iloc[-1])
        offset = min(lookback_days, len(closes) - 1)
        if offset > 0:
            period_close = float(closes.iloc[-1 - offset])
            chg_pct = ((last_price - period_close) / period_close) * 100 if period_close else 0

    price_str = f"${last_price:.2f}" if last_price else "—"
    chg_color = "#22c55e" if chg_pct > 0 else "#ef4444" if chg_pct < 0 else "#9ca3af"
    chg_arrow = "↑" if chg_pct > 0 else "↓" if chg_pct < 0 else ""

    css_class = "score-excellent" if score.total_score >= 80 else "score-good" if score.total_score >= 60 else "score-fair" if score.total_score >= 40 else "score-poor"
    strat = strategy_info.get(score.strategy, strategy_info["Neutral"])
    border = "border-color: #f59e0b;" if rank == 0 else ""

    # Extra context: sector, market cap, 52-week range, earnings
    sector_str = ""
    mcap_str = ""
    w52_html = ""
    earnings_str = ""

    # Try to get fundamentals from gateway cache
    try:
        from src.utils.db import cache_get
        fund_cache = cache_get(f"market:fundamentals:{sym}")
        if fund_cache:
            sector = fund_cache.get("sector", "")
            industry = fund_cache.get("industry", "")
            if sector:
                sector_str = f"{sector}"
                if industry:
                    sector_str += f" · {industry}"

            mcap_raw = fund_cache.get("market_cap")
            if mcap_raw:
                mcap_val = float(mcap_raw)
                if mcap_val >= 1e12:
                    mcap_str = f"${mcap_val/1e12:.1f}T"
                elif mcap_val >= 1e9:
                    mcap_str = f"${mcap_val/1e9:.0f}B"
                elif mcap_val >= 1e6:
                    mcap_str = f"${mcap_val/1e6:.0f}M"

            w52_high = fund_cache.get("week_52_high")
            w52_low = fund_cache.get("week_52_low")
            if w52_high and w52_low and last_price:
                high = float(w52_high)
                low = float(w52_low)
                if high > low:
                    pct_pos = ((last_price - low) / (high - low)) * 100
                    pct_pos = max(0, min(100, pct_pos))
                    pos_color = "#22c55e" if pct_pos < 40 else "#ef4444" if pct_pos > 80 else "#f59e0b"
                    w52_html = f"""<div style="margin-top:6px;">
                        <div style="display:flex; justify-content:space-between; font-size:10px; color:#6b7280;">
                            <span>${low:.0f}</span><span style="color:{pos_color}; font-weight:600;">52W Range</span><span>${high:.0f}</span>
                        </div>
                        <div style="height:4px; background:#2a2a2a; border-radius:2px; position:relative; margin-top:2px;">
                            <div style="height:100%; width:{pct_pos}%; background:linear-gradient(to right, #22c55e, #f59e0b, #ef4444); border-radius:2px;"></div>
                            <div style="position:absolute; top:-3px; left:{pct_pos}%; width:10px; height:10px; background:{pos_color}; border:2px solid #e5e5e5; border-radius:50%; transform:translateX(-50%);"></div>
                        </div>
                    </div>"""
    except Exception:
        pass

    # Try to get earnings date
    try:
        fund_cache2 = cache_get(f"market:fundamentals:{sym}")
        if fund_cache2:
            earnings_date = fund_cache2.get("next_earnings_date")
            if earnings_date:
                earnings_str = f"Earnings: {earnings_date}"
    except Exception:
        pass

    # Build context line
    context_parts = []
    if sector_str:
        context_parts.append(sector_str)
    if mcap_str:
        context_parts.append(mcap_str)
    if earnings_str:
        context_parts.append(earnings_str)
    context_line = " · ".join(context_parts)

    # Card header — build as parts to avoid f-string issues
    import html as html_mod
    context_html = f'<div style="font-size:12px; color:#6b7280; margin-top:2px; margin-left:32px;">{html_mod.escape(context_line)}</div>' if context_line else ""

    card_header = (
        f'<div class="signal-card" style="{border}">'
        f'<div style="display:flex; justify-content:space-between; align-items:center;">'
        f'<div>'
        f'<div style="display:flex; align-items:center; gap:10px;">'
        f'<span style="color:#6b7280; font-size:14px; font-weight:700;">#{rank+1}</span>'
        f'<span style="font-size:22px; font-weight:800; color:#e5e5e5;">{sym}</span>'
        f'<span class="score-badge {css_class}" style="font-size:15px; padding:4px 12px;">{score.total_score} {score.label}</span>'
        f'</div>'
        f'{context_html}'
        f'</div>'
        f'<div style="text-align:right;">'
        f'<span style="font-size:20px; font-weight:700; color:#e5e5e5;">{price_str}</span>'
        f'<span style="font-size:14px; font-weight:600; color:{chg_color}; margin-left:8px;">{chg_arrow} {chg_pct:+.1f}%</span>'
        f'<span style="font-size:11px; color:#6b7280; margin-left:4px;">({disc_period})</span>'
        f'</div>'
        f'</div>'
        f'{w52_html}'
        f'</div>'
    )
    st.markdown(card_header, unsafe_allow_html=True)

    # Interactive chart with signal markers
    if hist is not None and not hist.empty:
        closes = hist["close"].astype(float)
        dates = hist["date"].tolist()
        trim = min(lookback_days, len(closes))
        chart_closes = closes.tolist()[-trim:]
        chart_dates = dates[-trim:]

        chart_hist = hist.tail(trim).reset_index(drop=True)
        signals = _detect_signals_on_history(chart_hist, sym) if len(chart_hist) >= 30 else []

        spark_color = "#22c55e" if chart_closes[-1] >= chart_closes[0] else "#ef4444"
        r, g, b = int(spark_color[1:3], 16), int(spark_color[3:5], 16), int(spark_color[5:7], 16)

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=chart_dates, y=chart_closes, mode="lines", name="Price",
            line=dict(color=spark_color, width=2),
            fill="tozeroy", fillcolor=f"rgba({r},{g},{b},0.06)",
            hovertemplate="$%{y:.2f}<br>%{x}<extra></extra>",
        ))

        if signals:
            buy_sigs = [s for s in signals if s["direction"] == "buy"]
            sell_sigs = [s for s in signals if s["direction"] == "sell"]
            if buy_sigs:
                fig.add_trace(go.Scatter(
                    x=[s["date"] for s in buy_sigs], y=[s["price"] for s in buy_sigs],
                    mode="markers", name="Buy Signal",
                    marker=dict(color="#22c55e", size=10, symbol="triangle-up", line=dict(color="#fff", width=1)),
                    hovertemplate="<b>%{customdata[0]}</b><br>$%{y:.2f}<br>%{customdata[1]}<br>30d: %{customdata[2]}%<extra></extra>",
                    customdata=[[s["signal"], s["detail"], f"{s['outcome_pct']:+.1f}"] for s in buy_sigs],
                ))
            if sell_sigs:
                fig.add_trace(go.Scatter(
                    x=[s["date"] for s in sell_sigs], y=[s["price"] for s in sell_sigs],
                    mode="markers", name="Sell Signal",
                    marker=dict(color="#ef4444", size=10, symbol="triangle-down", line=dict(color="#fff", width=1)),
                    hovertemplate="<b>%{customdata[0]}</b><br>$%{y:.2f}<br>%{customdata[1]}<br>30d: %{customdata[2]}%<extra></extra>",
                    customdata=[[s["signal"], s["detail"], f"{s['outcome_pct']:+.1f}"] for s in sell_sigs],
                ))

        fig.update_layout(
            template="plotly_dark", height=200, margin=dict(l=0, r=0, t=0, b=0),
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(showgrid=False, showticklabels=True, tickfont=dict(size=10, color="#6b7280")),
            yaxis=dict(showgrid=False, showticklabels=True, tickfont=dict(size=10, color="#6b7280"), tickprefix="$"),
            showlegend=False, hovermode="x unified",
        )
        st.plotly_chart(fig, use_container_width=True, key=f"chart_{sym}_{disc_period}")

    # Strategy explanation — primary + secondaries with detail
    import html as html_mod
    from src.analysis.opportunity import explain_strategy, OpportunityScore

    explanation = html_mod.escape(explain_strategy(score, tech))
    strat_color = strat["color"]
    secondaries = getattr(score, "secondary_strategies", [])

    # Strategy short descriptions for secondaries
    strat_short_desc = {
        "Volume Spike": "Trading volume is significantly above the 20-day average, indicating unusual institutional interest or a catalyst-driven move.",
        "Momentum": "Price is trending upward with RSI in the healthy 50-70 zone and MACD confirming the direction.",
        "Breakout": "Price is approaching or breaking through a key resistance level. A confirmed breakout with volume often leads to a sustained move.",
        "Oversold Bounce": "RSI has dropped below 30 (extreme oversold). Statistically, stocks tend to bounce from these levels within days.",
        "Mean Reversion": "Price has moved far from its average. Mean reversion trades bet on a return to the norm — counter-trend, higher risk.",
        "Golden Cross": "The 50-day MA crossed above the 200-day MA — one of the most reliable long-term bullish signals used by institutional investors.",
        "Death Cross": "The 50-day MA crossed below the 200-day MA — a bearish signal that often precedes extended downtrends. Defensive posture recommended.",
        "Insider Accumulation": "Multiple corporate insiders bought shares within 7 days (cluster buy). Insiders have material non-public information advantage.",
        "Congress Buying": "Members of Congress from both parties are buying this stock. Bipartisan buying may indicate upcoming favorable policy or sector tailwinds.",
        "Earnings Catalyst": "Earnings report within 14 days. The stock has a favorable technical setup going in, which can amplify a beat reaction.",
        "Dividend Play": "Dividend yield above 3% with stable fundamentals. Provides income while you hold. Check ex-date timing.",
        "Bollinger Squeeze": "Bollinger Bands are narrowing — volatility compression. This typically precedes a large directional breakout. Direction unknown until it happens.",
        "Support Bounce": "Price is testing a proven support level. Risk is well-defined (stop below support) with clear upside to resistance.",
        "Gap Fill": "A price gap is being filled as the stock reverts toward the pre-gap level. About 70% of gaps fill within a few weeks.",
        "Sector Leader": "This stock is the top performer in the strongest sector. Leading stocks in leading sectors tend to outperform the broader market.",
        "Neutral": "No clear pattern detected. Multiple signals are conflicting or absent.",
    }

    # Build primary strategy block
    primary_html = (
        f'<div style="background:#111111; border:1px solid {strat_color}; border-radius:8px; padding:14px; margin:-8px 0 8px;">'
        f'<div style="display:flex; align-items:center; gap:8px; margin-bottom:8px;">'
        f'<span style="font-size:20px;">{strat["icon"]}</span>'
        f'<span style="font-size:16px; font-weight:800; color:{strat_color};">Primary: {score.strategy}</span>'
        f'<span style="font-size:12px; color:#6b7280; margin-left:auto;">R/R {score.risk_reward_ratio}</span>'
        f'</div>'
        f'<div style="font-size:13px; color:#d1d5db; line-height:1.6; margin-bottom:4px;">{explanation}</div>'
        f'</div>'
    )
    st.markdown(primary_html, unsafe_allow_html=True)

    # Build secondary strategy details — horizontal scrollable carousel
    if secondaries:
        sec_cards = ""
        for s in secondaries:
            si = strategy_info.get(s, strategy_info["Neutral"])
            sc = si["color"]
            desc = html_mod.escape(strat_short_desc.get(s, ""))
            sec_cards += (
                f'<div style="flex:0 0 220px; background:#0d0d0d; border:1px solid {sc}55; border-radius:8px; padding:12px; scroll-snap-align:start;">'
                f'<div style="display:flex; align-items:center; gap:6px; margin-bottom:6px;">'
                f'<span style="font-size:16px;">{si["icon"]}</span>'
                f'<span style="font-size:13px; font-weight:700; color:{sc};">{s}</span>'
                f'</div>'
                f'<div style="font-size:11px; color:#9ca3af; line-height:1.5;">{desc}</div>'
                f'</div>'
            )

        st.markdown(
            f'<div style="font-size:11px; color:#6b7280; margin-bottom:4px;">Also detected ({len(secondaries)} signals) — scroll →</div>'
            f'<div style="display:flex; gap:10px; overflow-x:auto; padding:4px 0 8px; scroll-snap-type:x mandatory; '
            f'-webkit-overflow-scrolling:touch; scrollbar-width:thin; scrollbar-color:#333 transparent;">'
            f'{sec_cards}</div>',
            unsafe_allow_html=True,
        )

    # Sub-score bars
    sub_scores = [
        ("Volume", score.volume_score, 25, "Recent volume vs 20-day avg"),
        ("Price", score.price_score, 25, "RSI + trend + MACD momentum"),
        ("Flow", score.flow_score, 25, "Options P/C ratio + insider buying"),
        ("Risk/Reward", score.risk_reward_score, 25, "Upside vs downside distance"),
    ]
    bar_html = ""
    for name, val, mx, desc in sub_scores:
        pct = max(min(val / mx * 100, 100), 3)
        c = "#22c55e" if val >= 18 else "#ef4444" if val <= 8 else "#f59e0b"
        bar_html += f"""<div style="flex:1;">
            <div style="font-size:10px; color:#6b7280; margin-bottom:2px;" title="{desc}">{name} <span style="color:{c}; font-weight:700;">{val}/25</span></div>
            <div style="height:5px; background:#2a2a2a; border-radius:3px;">
                <div style="height:100%; width:{pct}%; background:{c}; border-radius:3px;"></div>
            </div>
        </div>"""
    st.markdown(f'<div style="display:flex; gap:12px; margin:4px 0 12px;">{bar_html}</div>', unsafe_allow_html=True)

    # Action buttons
    b1, b2, _ = st.columns([2, 1, 5])
    with b1:
        if st.button("Deep Dive →", key=f"dive_{sym}", use_container_width=True):
            navigate_to(3, sym)
    with b2:
        if st.button("Remove", key=f"rm_{sym}"):
            remove_watchlist_item(sym)
            st.rerun()

    st.divider()


def page_discover():
    st.title("Discover Opportunities")
    st.caption("Find and rank stocks worth trading")

    # ── Stock selector ─────────────────────────────────────
    watchlist = get_watchlist()
    existing = {w["symbol"] for w in watchlist} if watchlist else set()

    sel_col, inp_col, btn_col, btn2_col = st.columns([3, 2, 1, 1])
    with sel_col:
        selected = st.selectbox(
            "Search", options=[""] + [s for s in POPULAR_STOCKS if s not in existing],
            format_func=lambda s: f"{s} — {STOCK_DB[s][0]} ({STOCK_DB[s][1]})" if s and s in STOCK_DB else f"{s} (custom)" if s else "Search by name, ticker, or sector...",
            index=0, placeholder="Search by name, ticker, or sector...", label_visibility="collapsed",
        )
    with inp_col:
        custom = st.text_input("Custom", placeholder="Any ticker (e.g. CRWD)", max_chars=10, label_visibility="collapsed")
    with btn_col:
        if st.button("Add", use_container_width=True, type="primary"):
            sym = (selected or custom or "").strip().upper()
            if sym:
                if sym in STOCK_DB:
                    add_watchlist_item(sym)
                    st.rerun()
                else:
                    with st.spinner(f"Validating {sym}..."):
                        valid, name = _validate_ticker(sym)
                    if valid:
                        add_watchlist_item(sym)
                        # Add to STOCK_DB for this session
                        STOCK_DB[sym] = (name or sym, "Unknown", "custom")
                        st.rerun()
                    else:
                        st.error(f"Ticker '{sym}' not found. Check the symbol and try again.")
    with btn2_col:
        if st.button("Add Top 5", use_container_width=True):
            for s in ["AAPL", "MSFT", "NVDA", "TSLA", "AMZN"]:
                if s not in existing:
                    add_watchlist_item(s)
            st.rerun()

    watchlist = get_watchlist()
    if not watchlist:
        st.info("Your watchlist is empty. Search for stocks above or click 'Add Top 5' to get started.")
        return

    symbols = tuple(item["symbol"] for item in watchlist)

    # ── Period filter ──────────────────────────────────────
    disc_periods = {"1D": 1, "1W": 5, "1M": 21, "3M": 63, "6M": 126, "1Y": 252}

    disc_period = st.segmented_control(
        "Period", list(disc_periods.keys()), default="1M",
        key="disc_period_seg", label_visibility="collapsed",
    )
    if disc_period is None:
        disc_period = "1M"
    lookback_days = disc_periods[disc_period]

    # ── Load scores (DB pre-computed → instant, else compute) ──
    from src.utils.db import get_all_precomputed_scores

    precomputed = get_all_precomputed_scores(max_age_minutes=60)
    has_precomputed = any(sym in precomputed for sym in symbols)

    if has_precomputed:
        # Most/all stocks are pre-computed — instant render
        batch = _batch_score_watchlist(symbols)
    else:
        # First visit — compute with progress bar
        with st.spinner(f"Scoring {len(symbols)} stocks (first time only — will be instant next time)..."):
            batch = _batch_score_watchlist(symbols)

    if not batch:
        st.warning("Could not score any stocks. Check API connectivity.")
        return

    scored_syms = sorted(batch.keys(), key=lambda s: batch[s]["score"].total_score if batch[s]["score"] else 0, reverse=True)
    scored_syms = list(scored_syms)

    # Scoring explainer
    with st.expander("How Opportunity Scores Work", expanded=False):
        st.markdown("""
| Factor | Weight | What It Measures |
|--------|--------|-----------------|
| **Volume** | 25% | Recent volume vs 20-day average |
| **Price** | 25% | RSI momentum + trend + MACD direction |
| **Flow** | 25% | Options put/call ratio + insider buying |
| **Risk/Reward** | 25% | Distance to support vs resistance |

**80-100** Excellent | **60-79** Good | **40-59** Fair | **0-39** Poor
        """)

    # ── Strategy info ──────────────────────────────────────
    strategy_info = {
        "Volume Spike": {"color": "#3b82f6", "icon": "📊"}, "Momentum": {"color": "#22c55e", "icon": "🚀"},
        "Breakout": {"color": "#f59e0b", "icon": "💥"}, "Oversold Bounce": {"color": "#06b6d4", "icon": "🔄"},
        "Mean Reversion": {"color": "#8b5cf6", "icon": "📉"}, "Golden Cross": {"color": "#fbbf24", "icon": "✨"},
        "Death Cross": {"color": "#dc2626", "icon": "💀"}, "Insider Accumulation": {"color": "#10b981", "icon": "🏦"},
        "Congress Buying": {"color": "#6366f1", "icon": "🏛"}, "Earnings Catalyst": {"color": "#f97316", "icon": "📅"},
        "Dividend Play": {"color": "#14b8a6", "icon": "💵"}, "Bollinger Squeeze": {"color": "#a855f7", "icon": "🔧"},
        "Support Bounce": {"color": "#0ea5e9", "icon": "🛡"}, "Gap Fill": {"color": "#78716c", "icon": "📐"},
        "Sector Leader": {"color": "#eab308", "icon": "👑"}, "Neutral": {"color": "#6b7280", "icon": "⏸"},
    }

    # ── Deep Dive All button ──────────────────────────────
    if scored_syms and len(scored_syms) > 1:
        if st.button(f"Deep Dive All {len(scored_syms)} Stocks →", use_container_width=True, type="primary"):
            st.session_state.selected_stock = scored_syms[0]
            st.session_state.dd_multi_stocks = list(scored_syms)
            st.session_state.current_step = 3
            st.rerun()

    # ── Render cards (sorted by score) ────────────────────
    from src.analysis.opportunity import explain_strategy

    for rank, sym in enumerate(scored_syms):
        data = batch[sym]
        if data and data.get("score"):
            _render_discover_card(sym, data, lookback_days, disc_period, rank, strategy_info)


# ═══════════════════════════════════════════════════════════════
# STEP 3: DEEP DIVE
# ═══════════════════════════════════════════════════════════════

def page_deep_dive():
    st.title("Deep Dive")

    # ── Multi-stock selector ───────────────────────────────
    watchlist = get_watchlist()
    wl_syms = [w["symbol"] for w in watchlist] if watchlist else []

    # Check if coming from "Deep Dive All" button
    dd_multi = st.session_state.get("dd_multi_stocks", [])
    if dd_multi:
        preselected = dd_multi
        st.session_state.dd_multi_stocks = []  # Clear after use
    elif st.session_state.selected_stock:
        preselected = [st.session_state.selected_stock]
    else:
        preselected = []

    sel_col, add_col = st.columns([4, 1])
    with sel_col:
        selected_stocks = st.multiselect(
            "Select stocks to compare",
            options=wl_syms + [s for s in POPULAR_STOCKS if s not in wl_syms],
            format_func=lambda s: f"{s} — {STOCK_DB[s][0]} ({STOCK_DB[s][1]})" if s in STOCK_DB else f"{s} (custom)",
            default=[s for s in preselected if s],
            placeholder="Pick one or more stocks...",
        )
    with add_col:
        custom_sym = st.text_input("Add custom", placeholder="Any ticker", max_chars=10, label_visibility="collapsed")
        if custom_sym:
            cs = custom_sym.upper()
            if cs not in selected_stocks:
                if cs in STOCK_DB:
                    selected_stocks.append(cs)
                else:
                    valid, name = _validate_ticker(cs)
                    if valid:
                        STOCK_DB[cs] = (name or cs, "Unknown", "custom")
                        selected_stocks.append(cs)
                    else:
                        st.error(f"'{cs}' not found.")

    if not selected_stocks:
        st.info("Select stocks from the dropdown above, or come here from Discover.")
        return

    # ── Filters row ────────────────────────────────────────
    f1, f2, f3 = st.columns([2, 2, 2])
    with f1:
        dd_period = st.segmented_control("Timeframe", ["1D", "1W", "1M", "3M", "6M", "1Y"], default="3M", key="dd_tf", label_visibility="collapsed")
        if dd_period is None:
            dd_period = "3M"
    with f2:
        signal_filter = st.selectbox("Signal filter", ["All Signals", "Buy Only", "Sell Only", "Strong Only"], index=0, label_visibility="collapsed")
    with f3:
        view_mode = st.segmented_control("View", ["Full", "Compare"], default="Full", key="dd_view", label_visibility="collapsed")
        if view_mode is None:
            view_mode = "Full"

    period_map = {"1D": 1, "1W": 5, "1M": 21, "3M": 63, "6M": 126, "1Y": 252}
    lookback = period_map[dd_period]

    # ── Analyze all stocks for this timeframe (cached per sym+period) ──
    @st.cache_data(ttl=900, show_spinner=False)
    def _analyze_for_deep_dive(sym: str, period_days: int):
        """Run full analysis using only the last `period_days` of data."""
        from src.data.gateway import DataGateway
        from src.analysis import technical, fundamental
        from src.analysis import macro as macro_analysis
        from src.analysis import options_flow, smart_money, congress_signal, confluence
        from src.analysis.confluence import SignalInput
        from src.sentiment.analyzer import SentimentResult, NewsArticle, score_headline
        from src.reports.builder import build_report
        from src.models.stock import Stock
        from decimal import Decimal

        local_gw = DataGateway()

        # Fetch data — historical limited to the selected period
        stock = local_gw.get_stock(sym)
        # Use max(period_days, 60) so we have enough data for indicators like SMA50
        hist = local_gw.get_historical(sym, period_days=max(period_days + 30, 60))
        macro_snapshot = local_gw.get_macro_snapshot()
        options_summary = local_gw.get_options_summary(sym)
        insider_summary = local_gw.get_insider_summary(sym)
        institutional_summary = local_gw.get_institutional_summary(sym)
        congress_summary = local_gw.get_congress_summary(sym)
        news_articles = local_gw.get_stock_news(sym)

        # Technical — trim to period window AFTER computing (needs lookback for SMA)
        tech_result = None
        if hist is not None and not hist.empty:
            tech_result = technical.analyze(sym, hist)
            # Override trend based on the selected period
            if len(hist) > period_days:
                period_closes = hist["close"].astype(float).tail(period_days)
                if len(period_closes) >= 2:
                    period_change = (float(period_closes.iloc[-1]) - float(period_closes.iloc[0])) / float(period_closes.iloc[0])
                    if period_change > 0.03:
                        tech_result.trend = "uptrend"
                    elif period_change < -0.03:
                        tech_result.trend = "downtrend"
                    else:
                        tech_result.trend = "sideways"

        # Fundamental
        fund_result = None
        if stock.fundamentals:
            try:
                fund_result = fundamental.analyze(stock.fundamentals)
            except Exception:
                pass

        # Sentiment
        from src.orchestrator import _build_sentiment
        sentiment_result = _build_sentiment(sym, news_articles)

        # Macro
        macro_result = None
        if macro_snapshot:
            try:
                macro_result = macro_analysis.analyze(macro_snapshot)
            except Exception:
                pass

        # Options
        options_result = None
        if options_summary:
            try:
                options_result = options_flow.analyze(options_summary)
            except Exception:
                pass

        # Smart money
        try:
            smart_money_result = smart_money.analyze(insider_summary, institutional_summary)
        except Exception:
            smart_money_result = None

        # Congress
        congress_result = None
        if congress_summary:
            try:
                congress_result = congress_signal.analyze(congress_summary)
            except Exception:
                pass

        # Confluence
        signals = []
        if tech_result and tech_result.overall_signal != "Neutral":
            score_map = {"Strong Buy": 2, "Buy": 1, "Sell": -1, "Strong Sell": -2}
            signals.append(SignalInput(name="technical", score=score_map.get(tech_result.overall_signal, 0), max_score=2, label=tech_result.overall_signal))
        if fund_result:
            s = 2 if fund_result.overall_score >= 4 else 1 if fund_result.overall_score >= 3 else -1 if fund_result.overall_score <= 2 else 0
            signals.append(SignalInput(name="fundamental", score=s, max_score=2, label=f"Score {fund_result.overall_score}/5"))
        if sentiment_result and sentiment_result.overall_score != Decimal("0"):
            s = 1 if sentiment_result.overall_score > Decimal("0.3") else -1 if sentiment_result.overall_score < Decimal("-0.3") else 0
            signals.append(SignalInput(name="sentiment", score=s, max_score=1, label=sentiment_result.overall_sentiment))

        confluence_result = confluence.analyze(signals) if signals else None

        # Defaults for missing
        if tech_result is None:
            from src.models.indicator import TechnicalIndicators
            tech_result = TechnicalIndicators(symbol=sym, timestamp=datetime.utcnow())
        if fund_result is None:
            from src.analysis.fundamental import FundamentalScore
            fund_result = FundamentalScore(symbol=sym, valuation_score=3, growth_score=3, profitability_score=3, health_score=3, overall_score=3, strengths=[], weaknesses=["Insufficient data"])

        # Geopolitical risk
        from src.orchestrator import _fetch_geopolitical_for_stock
        geo_data = None
        try:
            geo_data = _fetch_geopolitical_for_stock(sym, stock)
        except Exception:
            pass

        analyst_data = None
        try:
            from src.orchestrator import _fetch_analyst_data
            analyst_data = _fetch_analyst_data(sym)
        except Exception:
            pass

        holders_data = None
        try:
            from src.orchestrator import _fetch_holders_data
            holders_data = _fetch_holders_data(sym)
        except Exception:
            pass

        buzz_data = None
        try:
            from src.orchestrator import _fetch_community_buzz
            buzz_data = _fetch_community_buzz(sym)
        except Exception:
            pass

        report = build_report(
            stock=stock, technicals=tech_result, fundamentals_score=fund_result,
            sentiment=sentiment_result, macro_score=macro_result, options_score=options_result,
            smart_money_score=smart_money_result, congress_score=congress_result,
            relative_value_score=None, confluence=confluence_result,
            geopolitical_data=geo_data, analyst_data=analyst_data,
            holders_data=holders_data, community_buzz=buzz_data,
        )

        # Adjust confidence based on timeframe — shorter = less certain
        timeframe_confidence_penalty = {5: -1, 21: 0, 63: 0, 126: 0, 252: 1}
        penalty = timeframe_confidence_penalty.get(period_days, 0)
        levels = ["Low", "Medium", "High"]
        try:
            idx = levels.index(report.confidence)
            report.confidence = levels[max(0, min(2, idx + penalty))]
        except ValueError:
            pass

        # Count non-neutral signals — fewer signals = lower confidence
        non_neutral = sum(1 for s in report.sections if s.data and s.content
                         and any(w in s.content.lower() for w in ("buy", "sell", "bullish", "bearish", "positive", "negative")))
        if non_neutral <= 1:
            report.confidence = "Low"
        elif non_neutral <= 2 and report.confidence == "High":
            report.confidence = "Medium"

        # Add period price change to report for display
        if hist is not None and not hist.empty:
            closes = hist["close"].astype(float)
            trimmed = closes.tail(period_days)
            if len(trimmed) >= 2:
                period_start = float(trimmed.iloc[0])
                period_end = float(trimmed.iloc[-1])
                pct_change = ((period_end - period_start) / period_start) * 100 if period_start else 0
                report._period_change_pct = pct_change
                report._period_start_price = period_start
            else:
                report._period_change_pct = 0
                report._period_start_price = None
        else:
            report._period_change_pct = 0
            report._period_start_price = None

        return report

    reports = {}
    import threading, time

    def _do_analyze(sym):
        try:
            reports[sym] = _analyze_for_deep_dive(sym, lookback)
        except Exception:
            pass

    with st.spinner(f"Analyzing {len(selected_stocks)} stock{'s' if len(selected_stocks) > 1 else ''} ({dd_period} window)..."):
        threads = []
        for sym in selected_stocks:
            t = threading.Thread(target=_do_analyze, args=(sym,))
            threads.append(t)
            t.start()
            time.sleep(0.3)
        for t in threads:
            t.join(timeout=45)

    if not reports:
        st.error("Analysis failed for all selected stocks.")
        return

    # ── COMPARE VIEW: side-by-side verdict cards ───────────
    if view_mode == "Compare" and len(reports) > 1:
        _render_compare_view(reports, selected_stocks, lookback, dd_period)
        _render_step_cta("Prove It — Test These Signals", 4, selected_stocks[0])
        return

    # ── FULL VIEW: detailed cards per stock ────────────────
    for sym in selected_stocks:
        report = reports.get(sym)
        if not report:
            st.warning(f"Could not analyze {sym}")
            continue

        _render_deep_dive_card(sym, report, lookback, dd_period, signal_filter)

    _render_step_cta("Prove It — Test These Signals", 4, selected_stocks[0])


def _render_compare_view(reports: dict, symbols: list[str], lookback: int, period: str):
    """Side-by-side comparison of multiple stocks."""
    import html as html_mod

    # ── Verdict comparison row ─────────────────────────────
    cols = st.columns(len(symbols))
    for col, sym in zip(cols, symbols):
        report = reports.get(sym)
        if not report:
            continue
        with col:
            v = report.verdict.value
            v_color = "#22c55e" if "Buy" in v else "#ef4444" if "Sell" in v else "#f59e0b"
            conf = report.confidence
            conf_color = "#22c55e" if conf == "High" else "#f59e0b" if conf == "Medium" else "#ef4444"
            pct_chg = getattr(report, "_period_change_pct", 0)
            chg_color = "#22c55e" if pct_chg > 0 else "#ef4444" if pct_chg < 0 else "#9ca3af"
            chg_arrow = "↑" if pct_chg > 0 else "↓" if pct_chg < 0 else ""
            st.markdown(
                f'<div class="dark-card" style="text-align:center; border-top:3px solid {v_color}; padding:16px;">'
                f'<div style="font-size:20px; font-weight:800; color:#e5e5e5;">{sym}</div>'
                f'<div style="font-size:28px; font-weight:800; color:{v_color}; margin:8px 0;">{v}</div>'
                f'<div style="font-size:12px; color:{chg_color}; font-weight:600; margin-bottom:8px;">{chg_arrow} {pct_chg:+.1f}% ({period})</div>'
                f'<div style="display:flex; justify-content:center; gap:16px; font-size:12px;">'
                f'<div><span style="color:#6b7280;">Price</span><br><span style="color:#e5e5e5; font-weight:700;">${report.current_price}</span></div>'
                f'<div><span style="color:#6b7280;">Risk</span><br><span style="color:#e5e5e5; font-weight:700;">{report.risk_rating.value}/5</span></div>'
                f'<div><span style="color:#6b7280;">Conf</span><br><span style="color:{conf_color}; font-weight:700;">{conf}</span></div>'
                f'</div></div>',
                unsafe_allow_html=True,
            )

    # ── Overlaid price chart ───────────────────────────────
    st.markdown("### Price Comparison")
    fig = go.Figure()
    colors = ["#3b82f6", "#22c55e", "#f59e0b", "#ef4444", "#a855f7", "#06b6d4"]
    gw = _get_gateway()

    for i, sym in enumerate(symbols):
        try:
            hist = gw.get_historical(sym, period_days=lookback + 5)
            if hist is not None and not hist.empty:
                closes = hist["close"].astype(float)
                dates = hist["date"].tolist()
                trim = min(lookback, len(closes))
                trimmed = closes.tolist()[-trim:]
                # Normalize to % change from first day
                base = trimmed[0] if trimmed[0] != 0 else 1
                normalized = [(c / base - 1) * 100 for c in trimmed]
                fig.add_trace(go.Scatter(
                    x=dates[-trim:], y=normalized, mode="lines",
                    name=sym, line=dict(color=colors[i % len(colors)], width=2),
                    hovertemplate=f"{sym}: %{{y:+.1f}}%<br>%{{x}}<extra></extra>",
                ))
        except Exception:
            continue

    fig.update_layout(
        template="plotly_dark", height=350, margin=dict(l=0, r=0, t=10, b=0),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        yaxis=dict(title="% Change", ticksuffix="%", showgrid=True, gridcolor="#1a1a1a"),
        xaxis=dict(showgrid=False), legend=dict(orientation="h", y=1.1),
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)

    # ── Signal comparison matrix ───────────────────────────
    st.markdown("### Signal Comparison")
    signal_names = ["Technical", "Fundamental", "Sentiment", "Macro", "Options", "Smart Money", "Congress", "Geopolitical", "Disruptive Technology", "Analyst", "Institutional Holders", "Community Buzz"]

    header = "| Signal |" + "|".join(f" **{s}** " for s in symbols) + "|"
    sep = "|--------|" + "|".join("--------" for _ in symbols) + "|"
    rows = []

    for sig_name in signal_names:
        row = f"| {sig_name} |"
        for sym in symbols:
            report = reports.get(sym)
            if not report:
                row += " — |"
                continue
            found = False
            for section in report.sections:
                if sig_name.lower() in section.title.lower():
                    content = section.content.lower()
                    if "buy" in content or "bullish" in content or "positive" in content:
                        row += " 🟢 Bullish |"
                    elif "sell" in content or "bearish" in content or "negative" in content:
                        row += " 🔴 Bearish |"
                    else:
                        row += " 🟡 Neutral |"
                    found = True
                    break
            if not found:
                row += " — |"
        rows.append(row)

    st.markdown("\n".join([header, sep] + rows))

    # ── Key metrics table ──────────────────────────────────
    st.markdown("### Key Metrics")
    metrics_data = []
    for sym in symbols:
        report = reports.get(sym)
        if not report:
            continue
        overview = next((s for s in report.sections if "overview" in s.title.lower()), None)
        d = overview.data if overview else {}
        metrics_data.append({
            "Stock": sym,
            "Price": f"${report.current_price}",
            "Verdict": report.verdict.value,
            "Risk": f"{report.risk_rating.value}/5",
            "Sentiment": f"{float(report.sentiment_score):.5f}",
            "Market Cap": d.get("market_cap", "—"),
            "Sector": d.get("sector", "—"),
            "52W High": d.get("52w_high", "—"),
            "52W Low": d.get("52w_low", "—"),
        })
    if metrics_data:
        st.dataframe(pd.DataFrame(metrics_data), use_container_width=True, hide_index=True)


@st.cache_data(ttl=900, show_spinner=False)
def _get_signal_track_record(symbol: str, section_type: str, direction: str, hold_days: int = 30) -> dict | None:
    """Compute backtest track record for a Deep Dive signal section. Cached 15 min."""
    from src.analysis.backtester import backtest_section_signals
    from src.data.gateway import DataGateway

    try:
        gw = DataGateway()
        # Fetch enough history — need at least 2x the hold period for meaningful results
        hist_days = max(365, hold_days * 5)
        hist = gw.get_historical(symbol, period_days=hist_days)
        if hist is None or hist.empty or len(hist) < 60:
            return None
        return backtest_section_signals(symbol, hist, section_type, direction, hold_days=hold_days)
    except Exception:
        return None


def _render_track_record(record: dict, section_color: str) -> None:
    """Render signal track record as visual dots + stats."""
    import html as html_mod

    total = record["total"]
    wins = record["wins"]
    win_rate = record["win_rate"]
    avg_ret = record["avg_return"]
    best = record["best"]
    worst = record["worst"]
    hold = record["hold_days"]
    signals_used = record.get("signals_used", [])

    # Win rate color
    wr_color = "#22c55e" if win_rate >= 65 else "#f59e0b" if win_rate >= 50 else "#ef4444"

    # Dot visualization
    dots = ""
    for t in record["trades"][:20]:  # Max 20 dots
        if t.outcome == "win":
            dots += '<span style="color:#22c55e; font-size:16px; margin:0 2px;" title="Win: +{:.1f}%">●</span>'.format(t.pnl_percent)
        else:
            dots += '<span style="color:#ef4444; font-size:16px; margin:0 2px;" title="Loss: {:.1f}%">○</span>'.format(t.pnl_percent)

    # Signal names
    sig_pills = " ".join(
        f'<span style="font-size:10px; color:#6b7280; background:#1a1a1a; padding:2px 6px; border-radius:4px;">{s.replace("_", " ").title()}</span>'
        for s in signals_used
    )

    # Hold period label
    hold_label = {5: "1 week", 21: "1 month", 63: "3 months", 126: "6 months", 252: "1 year"}.get(hold, f"{hold} days")

    # Insight based on win rate
    if win_rate >= 70:
        insight = f"Strong signal — {win_rate}% win rate over {hold_label} hold periods. High probability setup."
    elif win_rate >= 55:
        insight = f"Moderate signal — wins more than it loses over {hold_label}. Use with other confirming signals."
    elif win_rate >= 40:
        insight = f"Weak signal — near coin-flip odds over {hold_label}. Don't trade this alone."
    else:
        insight = f"Unreliable signal — lost money more often than not over {hold_label}. Consider contrarian approach."

    st.markdown(
        f'<div style="background:#0a0a0a; border:1px solid {section_color}33; border-radius:8px; padding:14px;">'
        # Header stats
        f'<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">'
        f'<div style="font-size:13px; color:#e5e5e5;">Fired <b>{total}</b> times in past year ({hold_label} hold)</div>'
        f'<div style="font-size:18px; font-weight:800; color:{wr_color};">{win_rate}% win rate</div>'
        f'</div>'
        # Dots
        f'<div style="margin-bottom:10px;">{dots}</div>'
        # Stats grid
        f'<div style="display:grid; grid-template-columns:1fr 1fr 1fr 1fr; gap:8px;">'
        f'<div><div style="font-size:10px; color:#6b7280;">Won</div><div style="font-size:14px; font-weight:700; color:#22c55e;">{wins}</div></div>'
        f'<div><div style="font-size:10px; color:#6b7280;">Lost</div><div style="font-size:14px; font-weight:700; color:#ef4444;">{total - wins}</div></div>'
        f'<div><div style="font-size:10px; color:#6b7280;">Avg Return</div><div style="font-size:14px; font-weight:700; color:{"#22c55e" if avg_ret > 0 else "#ef4444"};">{avg_ret:+.1f}%</div></div>'
        f'<div><div style="font-size:10px; color:#6b7280;">Best / Worst</div><div style="font-size:12px; color:#9ca3af;">{best:+.1f}% / {worst:+.1f}%</div></div>'
        f'</div>'
        # Insight
        f'<div style="margin-top:10px; padding:8px; background:#111; border-radius:6px; font-size:12px; color:#d1d5db; line-height:1.5;">{html_mod.escape(insight)}</div>'
        # Signals used
        f'<div style="margin-top:8px; padding-top:8px; border-top:1px solid #1a1a1a; font-size:11px; color:#6b7280;">Signals tested: {sig_pills}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


@st.cache_data(ttl=3600, show_spinner=False)  # Cache 1 hour — events don't change every minute
def _fetch_geopolitical_events() -> list[dict]:
    """Fetch current geopolitical events from Tavily and categorize them."""
    import httpx
    from src.utils.config import TAVILY_API_KEY

    if not TAVILY_API_KEY:
        return []

    # Event categories with search queries and industry impact mappings
    categories = [
        {
            "type": "tariff",
            "icon": "🏷",
            "query": "US tariffs trade war 2026 impact industries sectors",
            "severity_keywords": ["200%", "new tariff", "trade war escalat", "retaliat"],
        },
        {
            "type": "war",
            "icon": "⚔",
            "query": "war conflict military impact US stock market 2026",
            "severity_keywords": ["escalat", "invasion", "missile", "nuclear", "sanction"],
        },
        {
            "type": "natural_disaster",
            "icon": "🌊",
            "query": "flood hurricane earthquake wildfire disaster US economic impact 2026",
            "severity_keywords": ["billion damage", "emergency", "catastroph", "devastat"],
        },
        {
            "type": "supply_chain",
            "icon": "🚢",
            "query": "supply chain disruption shortage US industry impact 2026",
            "severity_keywords": ["shortage", "disruption", "backlog", "shut down"],
        },
    ]

    # Industry impact mapping per event type
    impact_map = {
        "tariff": {
            "negative": ["Technology", "Consumer Discretionary", "Industrials", "Materials", "Automotive"],
            "positive": ["Domestic Manufacturing", "Utilities", "Healthcare (domestic)"],
            "explanation": "Tariffs raise input costs for importers and manufacturers. Tech and consumer goods face higher component costs. Domestic producers may benefit from reduced foreign competition.",
        },
        "war": {
            "negative": ["Airlines", "Tourism", "Consumer Discretionary", "Financials (global banks)"],
            "positive": ["Defense & Aerospace", "Energy (oil/gas)", "Cybersecurity", "Gold miners"],
            "explanation": "Military conflicts drive defense spending, spike oil prices, and create risk-off sentiment. Defense stocks surge while travel and consumer spending pull back.",
        },
        "natural_disaster": {
            "negative": ["Insurance", "Real Estate", "Agriculture", "Regional banks"],
            "positive": ["Construction", "Home improvement (HD, LOW)", "Infrastructure", "Utilities rebuild"],
            "explanation": "Disasters destroy physical assets but create rebuilding demand. Insurance companies face claims, while construction and materials companies see revenue spikes.",
        },
        "supply_chain": {
            "negative": ["Automotive", "Electronics", "Retail", "Restaurants"],
            "positive": ["Shipping & Logistics", "Warehousing", "Domestic alternatives"],
            "explanation": "Supply disruptions cause shortages and cost inflation. Companies with domestic supply chains or inventory buffers outperform. Logistics companies benefit from rerouting.",
        },
    }

    events = []
    try:
        for cat in categories:
            try:
                resp = httpx.post(
                    "https://api.tavily.com/search",
                    json={"query": cat["query"], "api_key": TAVILY_API_KEY, "max_results": 3, "search_depth": "basic"},
                    timeout=15,
                )
                results = resp.json().get("results", [])

                for r in results[:2]:
                    title = r.get("title", "")
                    content = r.get("content", "")[:200]
                    url = r.get("url", "")

                    # Determine severity
                    combined = (title + " " + content).lower()
                    high_severity = any(kw in combined for kw in cat["severity_keywords"])

                    impact = impact_map.get(cat["type"], {})
                    events.append({
                        "type": cat["type"],
                        "icon": cat["icon"],
                        "title": title[:100],
                        "snippet": content,
                        "url": url,
                        "severity": "high" if high_severity else "moderate",
                        "negative_sectors": impact.get("negative", []),
                        "positive_sectors": impact.get("positive", []),
                        "explanation": impact.get("explanation", ""),
                    })
            except Exception:
                continue
    except Exception:
        pass

    return events


def _render_economic_calendar():
    """Render upcoming economic events that affect trading."""
    from datetime import datetime as dt, timedelta
    import html as html_mod

    _section_header("Economic Calendar")

    # Known recurring events with approximate dates
    now = dt.utcnow()
    year = now.year
    month = now.month

    # Build events list — combination of known schedule + earnings from watchlist
    events = []

    # Fed meetings (2026 FOMC schedule — approximate)
    fomc_dates = [
        f"{year}-01-29", f"{year}-03-19", f"{year}-05-07", f"{year}-06-18",
        f"{year}-07-29", f"{year}-09-17", f"{year}-11-05", f"{year}-12-17",
    ]
    for d in fomc_dates:
        event_dt = dt.strptime(d, "%Y-%m-%d")
        if event_dt >= now - timedelta(days=1):
            days_away = (event_dt - now).days
            events.append({
                "date": d, "name": "FOMC Rate Decision", "icon": "%",
                "impact": "high", "days_away": days_away,
                "warning": "Expect volatility. Consider reducing position sizes day before." if days_away <= 3 else "",
            })

    # CPI releases (usually 2nd week of month)
    for m_offset in range(0, 3):
        cpi_month = month + m_offset
        cpi_year = year
        if cpi_month > 12:
            cpi_month -= 12
            cpi_year += 1
        cpi_date = f"{cpi_year}-{cpi_month:02d}-10"
        try:
            event_dt = dt.strptime(cpi_date, "%Y-%m-%d")
            if event_dt >= now - timedelta(days=1):
                days_away = (event_dt - now).days
                events.append({
                    "date": cpi_date, "name": "CPI Inflation Data", "icon": "📊",
                    "impact": "high", "days_away": days_away,
                    "warning": "Inflation surprise can move all stocks. Watch bond yields." if days_away <= 3 else "",
                })
        except Exception:
            pass

    # Jobs report (usually first Friday of month)
    for m_offset in range(0, 3):
        jobs_month = month + m_offset
        jobs_year = year
        if jobs_month > 12:
            jobs_month -= 12
            jobs_year += 1
        # First Friday approximation
        jobs_date = f"{jobs_year}-{jobs_month:02d}-07"
        try:
            event_dt = dt.strptime(jobs_date, "%Y-%m-%d")
            if event_dt >= now - timedelta(days=1):
                days_away = (event_dt - now).days
                events.append({
                    "date": jobs_date, "name": "Jobs Report (NFP)", "icon": "👥",
                    "impact": "high", "days_away": days_away,
                    "warning": "Strong jobs = rates stay high (bearish for growth). Weak jobs = rate cut hopes (bullish)." if days_away <= 3 else "",
                })
        except Exception:
            pass

    # GDP (quarterly — end of Jan, Apr, Jul, Oct)
    gdp_dates = [f"{year}-01-30", f"{year}-04-30", f"{year}-07-30", f"{year}-10-30"]
    for d in gdp_dates:
        try:
            event_dt = dt.strptime(d, "%Y-%m-%d")
            if event_dt >= now - timedelta(days=1):
                days_away = (event_dt - now).days
                events.append({
                    "date": d, "name": "GDP Report", "icon": "🏭",
                    "impact": "medium", "days_away": days_away, "warning": "",
                })
        except Exception:
            pass

    # Watchlist earnings dates
    try:
        watchlist = get_watchlist()
        if watchlist:
            from src.data.gateway import DataGateway
            gw = DataGateway()
            for w in watchlist[:10]:
                try:
                    earnings = gw.get_earnings_calendar(w["symbol"])
                    if earnings:
                        for e in earnings[:1]:
                            e_date = e.get("date", "")
                            if e_date:
                                event_dt = dt.strptime(e_date[:10], "%Y-%m-%d")
                                if event_dt >= now - timedelta(days=1):
                                    days_away = (event_dt - now).days
                                    events.append({
                                        "date": e_date[:10], "name": f"{w['symbol']} Earnings", "icon": "💰",
                                        "impact": "high" if days_away <= 7 else "medium",
                                        "days_away": days_away,
                                        "warning": f"Expect 5-15% move. Consider options or reduced size." if days_away <= 5 else "",
                                    })
                except Exception:
                    continue
    except Exception:
        pass

    events.sort(key=lambda x: x["days_away"])
    upcoming = [e for e in events if e["days_away"] <= 60][:8]

    if not upcoming:
        st.caption("No major economic events in the next 60 days.")
        return

    # Render events
    for e in upcoming:
        impact_color = "#ef4444" if e["impact"] == "high" else "#f59e0b"
        urgency = ""
        if e["days_away"] <= 2:
            urgency = "background:rgba(239,68,68,0.08); border:1px solid rgba(239,68,68,0.3);"
        elif e["days_away"] <= 7:
            urgency = "background:rgba(245,158,11,0.08); border:1px solid rgba(245,158,11,0.3);"
        else:
            urgency = "background:#111; border:1px solid #1a1a1a;"

        days_label = "TODAY" if e["days_away"] == 0 else "TOMORROW" if e["days_away"] == 1 else f"in {e['days_away']} days"
        days_color = "#ef4444" if e["days_away"] <= 2 else "#f59e0b" if e["days_away"] <= 7 else "#6b7280"

        st.markdown(
            f'<div style="{urgency} border-radius:8px; padding:12px; margin-bottom:6px; display:flex; justify-content:space-between; align-items:center;">'
            f'<div style="display:flex; align-items:center; gap:10px;">'
            f'<span style="font-size:18px;">{e["icon"]}</span>'
            f'<div>'
            f'<div style="font-size:13px; font-weight:700; color:#e5e5e5;">{html_mod.escape(e["name"])}</div>'
            f'<div style="font-size:11px; color:#6b7280;">{e["date"]}</div>'
            f'</div>'
            f'</div>'
            f'<div style="text-align:right;">'
            f'<div style="font-size:12px; font-weight:700; color:{days_color};">{days_label}</div>'
            f'<div style="font-size:10px; color:{impact_color}; text-transform:uppercase;">{e["impact"]} impact</div>'
            f'</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        if e.get("warning"):
            st.markdown(
                f'<div style="font-size:11px; color:#f59e0b; margin:-4px 0 8px 36px;">⚠ {html_mod.escape(e["warning"])}</div>',
                unsafe_allow_html=True,
            )


def _render_geopolitical_risks():
    """Render geopolitical and event risk section in Market Pulse."""
    import html as html_mod

    # Section header
    st.markdown(
        '<div style="display:flex; align-items:center; gap:10px; margin:24px 0 16px;">'
        '<span style="font-size:22px;">🌐</span>'
        '<div>'
        '<div style="font-size:18px; font-weight:800; color:#e5e5e5;">Geopolitical &amp; Event Risk</div>'
        '<div style="font-size:12px; color:#6b7280;">Real-time events affecting markets and sectors</div>'
        '</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    events = _fetch_geopolitical_events()

    if not events:
        st.markdown(
            '<div style="background:#0d0d0d; border:1px solid #22c55e44; border-radius:12px; padding:20px; text-align:center;">'
            '<div style="font-size:16px; color:#22c55e; font-weight:600;">All Clear</div>'
            '<div style="font-size:13px; color:#6b7280; margin-top:4px;">No major geopolitical risks detected. Markets operating in a low-threat environment.</div>'
            '</div>',
            unsafe_allow_html=True,
        )
        return

    # Overall threat level
    high_count = sum(1 for e in events if e["severity"] == "high")
    if high_count >= 3:
        threat_level, threat_color, threat_label = "ELEVATED", "#ef4444", "Multiple high-impact events active"
    elif high_count >= 1:
        threat_level, threat_color, threat_label = "HEIGHTENED", "#f59e0b", "Some high-impact events detected"
    else:
        threat_level, threat_color, threat_label = "NORMAL", "#22c55e", "No critical events — monitoring ongoing"

    st.markdown(
        f'<div style="background:#0d0d0d; border:1px solid {threat_color}; border-radius:12px; padding:16px; margin-bottom:16px; display:flex; justify-content:space-between; align-items:center;">'
        f'<div>'
        f'<div style="font-size:10px; color:#6b7280; text-transform:uppercase; letter-spacing:1px;">Threat Level</div>'
        f'<div style="font-size:20px; font-weight:800; color:{threat_color}; margin-top:2px;">{threat_level}</div>'
        f'</div>'
        f'<div style="text-align:right;">'
        f'<div style="font-size:13px; color:#d1d5db;">{threat_label}</div>'
        f'<div style="font-size:11px; color:#6b7280; margin-top:2px;">{len(events)} events tracked across 4 categories</div>'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # Group by type
    by_type: dict[str, list[dict]] = {}
    for e in events:
        by_type.setdefault(e["type"], []).append(e)

    type_labels = {
        "tariff": "Tariffs & Trade Policy",
        "war": "Conflicts & Sanctions",
        "natural_disaster": "Natural Disasters",
        "supply_chain": "Supply Chain Disruptions",
    }

    # Render as 2-column grid
    types_list = list(by_type.items())
    for row_start in range(0, len(types_list), 2):
        cols = st.columns(2)
        for col_idx in range(2):
            idx = row_start + col_idx
            if idx >= len(types_list):
                break
            event_type, type_events = types_list[idx]

            with cols[col_idx]:
                label = type_labels.get(event_type, event_type.title())
                icon = type_events[0]["icon"]
                has_high = any(e["severity"] == "high" for e in type_events)
                sev_color = "#ef4444" if has_high else "#f59e0b"
                sev_label = "HIGH" if has_high else "MODERATE"
                sev_bg = "rgba(239,68,68,0.08)" if has_high else "rgba(245,158,11,0.08)"

                neg_sectors = type_events[0].get("negative_sectors", [])
                pos_sectors = type_events[0].get("positive_sectors", [])
                explanation = type_events[0].get("explanation", "")

                # Sector pills
                neg_html = "".join(
                    f'<span style="display:inline-block; margin:2px; padding:3px 10px; background:rgba(239,68,68,0.1); border:1px solid rgba(239,68,68,0.3); border-radius:20px; font-size:11px; font-weight:600; color:#f87171;">{html_mod.escape(s)}</span>'
                    for s in neg_sectors[:4]
                )
                pos_html = "".join(
                    f'<span style="display:inline-block; margin:2px; padding:3px 10px; background:rgba(34,197,94,0.1); border:1px solid rgba(34,197,94,0.3); border-radius:20px; font-size:11px; font-weight:600; color:#4ade80;">{html_mod.escape(s)}</span>'
                    for s in pos_sectors[:4]
                )

                # Headlines
                headlines = ""
                for e in type_events[:2]:
                    headlines += f'<div style="font-size:12px; color:#d1d5db; margin:4px 0; line-height:1.4;">• {html_mod.escape(e["title"][:90])}</div>'

                st.markdown(
                    f'<div style="background:#111; border:1px solid #222; border-radius:12px; padding:18px; height:100%;">'
                    # Header
                    f'<div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:12px;">'
                    f'<div style="display:flex; align-items:center; gap:8px;">'
                    f'<span style="font-size:24px;">{icon}</span>'
                    f'<span style="font-size:14px; font-weight:700; color:#e5e5e5;">{label}</span>'
                    f'</div>'
                    f'<span style="font-size:10px; font-weight:800; letter-spacing:0.5px; color:{sev_color}; background:{sev_bg}; padding:4px 10px; border-radius:20px;">{sev_label}</span>'
                    f'</div>'
                    # Headlines
                    f'<div style="margin-bottom:10px;">{headlines}</div>'
                    # Explanation
                    f'<div style="font-size:11px; color:#9ca3af; line-height:1.5; padding:10px; background:#0a0a0a; border-radius:8px; margin-bottom:12px;">{html_mod.escape(explanation)}</div>'
                    # Sectors at risk
                    f'<div style="margin-bottom:8px;">'
                    f'<div style="font-size:9px; color:#6b7280; text-transform:uppercase; letter-spacing:1px; font-weight:700; margin-bottom:4px;">Sectors at risk</div>'
                    f'<div style="display:flex; flex-wrap:wrap; gap:2px;">{neg_html}</div>'
                    f'</div>'
                    # Sectors that benefit
                    f'<div>'
                    f'<div style="font-size:9px; color:#6b7280; text-transform:uppercase; letter-spacing:1px; font-weight:700; margin-bottom:4px;">May benefit</div>'
                    f'<div style="display:flex; flex-wrap:wrap; gap:2px;">{pos_html}</div>'
                    f'</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

    with st.expander("How to use this for trading", expanded=False):
        st.markdown(
            '<div style="font-size:13px; color:#d1d5db; line-height:1.7;">'
            '<b style="color:#e5e5e5;">Why this matters:</b><br>'
            'Geopolitical events are the #1 cause of sudden market moves. A tariff announcement can crash tech stocks 5% in a day. '
            'A war escalation can spike defense stocks 10% overnight. Knowing which sectors are exposed <i>before</i> the market reacts is your edge.<br><br>'
            '<b style="color:#e5e5e5;">How to act:</b><br>'
            '• <b style="color:#ef4444;">HIGH IMPACT</b> — Check if your watchlist stocks are in the "at risk" sectors. Consider reducing exposure or adding hedges.<br>'
            '• <b style="color:#f59e0b;">MODERATE</b> — Monitor the situation. Don\'t panic, but factor it into your analysis.<br>'
            '• Look at "May benefit" sectors for opportunity trades — these are often overlooked while everyone focuses on the damage.<br>'
            '• Disaster-hit sectors typically overcorrect by 10-20%, creating buying opportunities 2-4 weeks after the event.<br><br>'
            '<span style="color:#6b7280; font-size:11px;">Events refresh hourly from Tavily news search.</span>'
            '</div>',
            unsafe_allow_html=True,
        )


@st.cache_data(ttl=3600, show_spinner=False)
def _fetch_disruption_themes() -> list[dict]:
    """Fetch current tech disruption themes using Claude AI to identify and analyze them."""
    import httpx
    import subprocess
    import os
    from src.utils.config import TAVILY_API_KEY

    if not TAVILY_API_KEY:
        return []

    # Step 1: Fetch broad disruption news from Tavily
    all_articles = []
    queries = [
        "technology disruption stocks industry impact 2026",
        "emerging technology reshaping industries stocks winners losers 2026",
        "AI biotech energy innovation disrupt market 2026",
    ]
    for q in queries:
        try:
            resp = httpx.post(
                "https://api.tavily.com/search",
                json={"query": q, "api_key": TAVILY_API_KEY, "max_results": 5, "search_depth": "basic"},
                timeout=15,
            )
            for r in resp.json().get("results", [])[:5]:
                all_articles.append({
                    "title": r.get("title", "")[:100],
                    "content": r.get("content", "")[:150],
                })
        except Exception:
            continue

    if not all_articles:
        return []

    # Step 2: Ask Claude to identify disruption themes from the articles
    articles_text = "\n".join(f"- {a['title']}: {a['content'][:80]}" for a in all_articles[:12])

    try:
        prompt = f"""Analyze these recent articles and identify the top 6 technology disruption themes currently impacting the US stock market.

ARTICLES:
{articles_text}

For each theme, determine:
1. Name and emoji icon
2. Current intensity: HIGH (actively moving stocks NOW), MEDIUM (growing, being priced in), EMERGING (early stage)
3. Which specific US stock tickers BENEFIT (up to 5)
4. Which sectors benefit
5. Which specific tickers are AT RISK (up to 4)
6. Which sectors are at risk
7. Two recent headline examples

Include BOTH well-known themes (AI, EVs) AND any NEW disruptions you see emerging from the articles that most investors might miss.

Respond with ONLY a JSON array:
[
  {{
    "name": "AI & Large Language Models",
    "icon": "🤖",
    "level": "HIGH",
    "intensity": 4,
    "beneficiaries": ["NVDA", "MSFT", "GOOG"],
    "beneficiary_sectors": ["Semiconductors", "Cloud Computing"],
    "at_risk": ["INFY", "WIT"],
    "at_risk_sectors": ["IT Services", "Call Centers"],
    "headlines": ["Article headline 1", "Article headline 2"]
  }}
]"""

        env = dict(os.environ)
        env.pop("CLAUDECODE", None)

        proc = subprocess.run(
            ["claude", "-p", prompt, "--model", "haiku"],
            capture_output=True, text=True, timeout=30, env=env,
        )
        response = proc.stdout.strip()

        start = response.find("[")
        end = response.rfind("]") + 1
        if start >= 0 and end > start:
            import json
            results = json.loads(response[start:end])

            # Normalize and sort
            for r in results:
                r.setdefault("icon", "🔬")
                r.setdefault("level", "EMERGING")
                r.setdefault("intensity", 1 if r["level"] == "EMERGING" else 3 if r["level"] == "MEDIUM" else 5)
                r.setdefault("beneficiaries", [])
                r.setdefault("beneficiary_sectors", [])
                r.setdefault("at_risk", [])
                r.setdefault("at_risk_sectors", [])
                r.setdefault("headlines", [])
                # Add query field for compatibility
                r["query"] = r["name"]

            results.sort(key=lambda x: x.get("intensity", 0), reverse=True)

            # Cache for orchestrator
            try:
                from src.utils.db import cache_set as db_cache_set
                db_cache_set("geo:disruption_themes", results, ttl_minutes=60)
            except Exception:
                pass

            return results

    except Exception:
        pass

    return []


def _render_disruption_section():
    """Render disruptive technology section in Market Pulse."""
    import html as html_mod

    st.markdown(
        '<div style="display:flex; align-items:center; gap:10px; margin:24px 0 16px;">'
        '<span style="font-size:22px;">🚀</span>'
        '<div>'
        '<div style="font-size:18px; font-weight:800; color:#e5e5e5;">Disruptive Technology Tracker</div>'
        '<div style="font-size:12px; color:#6b7280;">How emerging technologies are reshaping industries and stock winners/losers</div>'
        '</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    themes = _fetch_disruption_themes()

    if not themes:
        st.caption("Unable to fetch disruption data.")
        return

    # Render as cards
    for row_start in range(0, len(themes), 2):
        cols = st.columns(2)
        for col_idx in range(2):
            idx = row_start + col_idx
            if idx >= len(themes):
                break
            theme = themes[idx]

            with cols[col_idx]:
                level = theme["level"]
                lev_color = "#ef4444" if level == "HIGH" else "#f59e0b" if level == "MEDIUM" else "#6b7280"
                lev_bg = "rgba(239,68,68,0.08)" if level == "HIGH" else "rgba(245,158,11,0.08)" if level == "MEDIUM" else "rgba(107,114,128,0.08)"

                # Intensity bar
                bar_pct = min(theme["intensity"] / 5 * 100, 100)

                # Beneficiary pills
                ben_pills = "".join(
                    f'<span style="display:inline-block; margin:2px; padding:2px 8px; background:rgba(34,197,94,0.1); border:1px solid rgba(34,197,94,0.3); border-radius:16px; font-size:10px; font-weight:600; color:#4ade80;">{html_mod.escape(s)}</span>'
                    for s in theme.get("beneficiaries", [])[:4]
                )
                ben_sectors = ", ".join(theme.get("beneficiary_sectors", [])[:3])

                # At risk pills
                risk_pills = "".join(
                    f'<span style="display:inline-block; margin:2px; padding:2px 8px; background:rgba(239,68,68,0.1); border:1px solid rgba(239,68,68,0.3); border-radius:16px; font-size:10px; font-weight:600; color:#f87171;">{html_mod.escape(s)}</span>'
                    for s in theme.get("at_risk", [])[:4]
                )
                risk_sectors = ", ".join(theme.get("at_risk_sectors", [])[:3])

                # Headlines
                headlines_html = ""
                for h in theme.get("headlines", [])[:2]:
                    headlines_html += f'<div style="font-size:11px; color:#d1d5db; margin:3px 0; line-height:1.4;">• {html_mod.escape(h)}</div>'

                st.markdown(
                    f'<div style="background:#111; border:1px solid #222; border-radius:12px; padding:18px; height:100%;">'
                    # Header
                    f'<div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:10px;">'
                    f'<div style="display:flex; align-items:center; gap:8px;">'
                    f'<span style="font-size:24px;">{theme["icon"]}</span>'
                    f'<span style="font-size:14px; font-weight:700; color:#e5e5e5;">{html_mod.escape(theme["name"])}</span>'
                    f'</div>'
                    f'<span style="font-size:10px; font-weight:800; letter-spacing:0.5px; color:{lev_color}; background:{lev_bg}; padding:4px 10px; border-radius:20px;">{level}</span>'
                    f'</div>'
                    # Intensity bar
                    f'<div style="height:3px; background:#1a1a1a; border-radius:2px; margin-bottom:10px;">'
                    f'<div style="height:100%; width:{bar_pct}%; background:linear-gradient(to right, {lev_color}, {lev_color}88); border-radius:2px;"></div>'
                    f'</div>'
                    # Headlines
                    f'{headlines_html}'
                    # Winners
                    f'<div style="margin-top:10px;">'
                    f'<div style="font-size:9px; color:#6b7280; text-transform:uppercase; letter-spacing:1px; font-weight:700; margin-bottom:4px;">Winners</div>'
                    f'<div style="display:flex; flex-wrap:wrap; gap:2px; margin-bottom:2px;">{ben_pills}</div>'
                    f'<div style="font-size:10px; color:#6b7280;">{html_mod.escape(ben_sectors)}</div>'
                    f'</div>'
                    # Losers
                    + (
                        f'<div style="margin-top:8px;">'
                        f'<div style="font-size:9px; color:#6b7280; text-transform:uppercase; letter-spacing:1px; font-weight:700; margin-bottom:4px;">At Risk</div>'
                        f'<div style="display:flex; flex-wrap:wrap; gap:2px; margin-bottom:2px;">{risk_pills}</div>'
                        f'<div style="font-size:10px; color:#6b7280;">{html_mod.escape(risk_sectors)}</div>'
                        f'</div>'
                        if theme.get("at_risk") else ""
                    )
                    + f'</div>',
                    unsafe_allow_html=True,
                )

    with st.expander("How disruption affects your trades", expanded=False):
        st.markdown(
            '<div style="font-size:13px; color:#d1d5db; line-height:1.7;">'
            '<b style="color:#e5e5e5;">Why track disruption?</b><br>'
            'Disruptive technologies create the biggest stock winners AND losers over 1-5 year periods. '
            'NVDA went from $15 to $175 on AI. Legacy auto stocks flatlined while TSLA surged. '
            'GLP-1 drugs are quietly destroying fast food and medical device revenue forecasts.<br><br>'
            '<b style="color:#e5e5e5;">How to use this:</b><br>'
            '• <b style="color:#22c55e;">HIGH intensity</b> — This disruption is actively moving stocks NOW. Check if your watchlist is exposed.<br>'
            '• <b style="color:#f59e0b;">MEDIUM</b> — Disruption is real but still being priced in. Early positioning opportunity.<br>'
            '• <b style="color:#6b7280;">EMERGING</b> — Early stage. Watch for acceleration signals.<br>'
            '• Winners tend to keep winning until the disruption matures (3-5 years).<br>'
            '• "At Risk" stocks may not crash immediately, but their growth ceiling is now lower.<br><br>'
            '<span style="color:#6b7280; font-size:11px;">Themes updated hourly from news + research sources.</span>'
            '</div>',
            unsafe_allow_html=True,
        )


def _explain_signal_section(signal_type: str, direction: str, data: dict, content: str, symbol: str) -> tuple[str, str, str]:
    """Generate 3-part educational explanation: what the data says, why it matters, what to do."""

    def _val(key, fmt=None):
        v = data.get(key)
        if v is None or str(v) in ("None", ""):
            return None
        if fmt:
            try:
                return fmt.format(float(v))
            except (ValueError, TypeError):
                return str(v)
        return str(v)

    if signal_type == "Technical Analysis":
        rsi = _val("rsi", "{:.0f}")
        macd = _val("macd")
        trend = _val("trend") or "unclear"
        sma50 = _val("sma_50", "${:.2f}")
        sma200 = _val("sma_200", "${:.2f}")
        support = _val("support", "${:.2f}")
        resistance = _val("resistance", "${:.2f}")
        signal = _val("signal") or direction

        parts = []
        if rsi:
            if float(data.get("rsi", 50)) > 70:
                parts.append(f"RSI is at {rsi} — in overbought territory (above 70)")
            elif float(data.get("rsi", 50)) < 30:
                parts.append(f"RSI is at {rsi} — in oversold territory (below 30)")
            elif float(data.get("rsi", 50)) > 50:
                parts.append(f"RSI is at {rsi} — in the healthy momentum zone (50-70)")
            else:
                parts.append(f"RSI is at {rsi} — below the midpoint, showing weak momentum")
        if trend != "unclear":
            parts.append(f"The trend is {trend}")
        if sma50 and sma200:
            parts.append(f"50-day MA is {sma50}, 200-day MA is {sma200}")
        what = ". ".join(parts) + "." if parts else content

        if direction == "bullish":
            why = "Buyers are in control. When momentum indicators align with an uptrend, it means the stock has institutional support and is likely to continue higher. This is the kind of setup professional traders look for."
            todo = f"Favorable entry point. Consider buying with a stop loss below the 50-day MA{' at ' + sma50 if sma50 else ''}."
            if support:
                todo += f" Support at {support} — if it breaks below, exit."
            if resistance:
                todo += f" First target: resistance at {resistance}."
        elif direction == "bearish":
            why = "Sellers are dominating. Downtrending price with weak momentum means institutions are distributing shares. Fighting a downtrend is one of the most common mistakes traders make."
            todo = "Avoid buying. If you hold this stock, consider tightening your stop loss or reducing position size. Wait for trend reversal signals before entering."
        else:
            why = "No clear direction. The stock is consolidating — indicators are mixed. This is a wait-and-see situation. Most profitable trades come from clear setups, not ambiguous ones."
            todo = "Wait for a clearer signal. Set an alert for RSI crossing below 30 (oversold bounce) or price breaking above resistance."

        return what, why, todo

    elif signal_type == "Fundamental Analysis":
        overall = _val("overall")
        valuation = _val("valuation")
        growth = _val("growth")
        profitability = _val("profitability")
        strengths = data.get("strengths", [])
        weaknesses = data.get("weaknesses", [])

        parts = [f"Overall fundamental score: {overall}/5" if overall else ""]
        if strengths:
            parts.append("Strengths: " + ", ".join(str(s) for s in strengths[:3]))
        if weaknesses:
            parts.append("Weaknesses: " + ", ".join(str(w) for w in weaknesses[:3]))
        what = ". ".join(p for p in parts if p) + "."

        if direction == "bullish":
            why = "Strong fundamentals mean the company is financially healthy — it earns money, grows revenue, and manages debt well. Stocks with strong fundamentals tend to recover faster from dips and outperform over the long term."
            todo = "Fundamentals support a buy. This stock has a financial moat. Even if the price dips short-term, the underlying business justifies holding. Good for swing trades and longer holds."
        elif direction == "bearish":
            why = "Weak fundamentals signal financial stress — the company may be overvalued, losing money, or carrying too much debt. These stocks are higher risk because bad earnings can cause sharp drops."
            todo = "Proceed with caution. If trading this, use smaller position sizes and tighter stop losses. The fundamentals don't support holding through a downturn."
        else:
            why = "Fundamentals are average — not a red flag, but not a standout either. The stock will likely be driven more by market sentiment and technicals than by its financial strength."
            todo = "Neutral — fundamentals neither help nor hurt. Focus on technical signals and momentum for timing."

        return what, why, todo

    elif signal_type == "News Sentiment":
        score = _val("score")
        sentiment = _val("sentiment") or direction
        count = data.get("article_count", 0)

        what = f"{count} recent news articles analyzed. Overall sentiment: {sentiment}"
        if score:
            what += f" (score: {score})"
        what += "."

        if direction == "bullish":
            why = "Positive news drives buying pressure. When multiple sources report good news (earnings beats, upgrades, new products), it creates a feedback loop — more buyers push the price up, which generates more positive coverage."
            todo = "News supports a buy. But be aware — if the good news is already widely known, it may be 'priced in'. Check if the stock has already jumped. Best entries come when good news hasn't fully reflected in the price yet."
        elif direction == "bearish":
            why = "Negative news creates selling pressure and fear. Bad headlines (lawsuits, missed earnings, downgrades) can cause sharp drops as institutional investors exit. The first drop is rarely the last."
            todo = "Avoid buying into negative headlines. Wait for the news cycle to settle (usually 3-5 days). The best dip-buying opportunities come after the panic fades, not during it."
        else:
            why = "No strong news sentiment either way. The stock is flying under the radar, which can be good — it means price is driven by fundamentals and technicals rather than hype or fear."
            todo = "Neutral news — other signals matter more. Check technical and fundamental analysis for direction."

        return what, why, todo

    elif signal_type == "Macro Environment":
        regime = _val("regime") or "normal"
        factors = data.get("factors", [])

        what = f"Current economic regime: {regime}."
        if factors:
            what += " Key factors: " + ", ".join(str(f) for f in factors[:3]) + "."
        else:
            what += " No extreme macro conditions detected."

        if direction == "bullish":
            why = "The broader economy supports stock gains. Low interest rates, strong employment, or accommodative Fed policy creates a 'risk-on' environment where stocks generally rise. A rising tide lifts all boats."
            todo = "Macro tailwind — the economy is helping, not hurting. This is a good time for growth stocks and higher-risk trades. Ride the momentum."
        elif direction == "bearish":
            why = "Economic headwinds hurt all stocks. High interest rates, recession signals, or elevated inflation create a 'risk-off' environment. Even good companies see their stock prices fall when the economy weakens."
            todo = "Macro headwind — consider reducing overall exposure. Favor defensive sectors (utilities, healthcare, staples) and companies with strong cash flow. Avoid high-debt, high-growth names."
        else:
            why = "The economy is neither helping nor hurting. In a neutral macro environment, stock-picking matters more than market direction. Focus on individual company quality."
            todo = "Normal conditions — macro won't save a bad stock or sink a good one. Focus on the other signals."

        return what, why, todo

    elif signal_type == "Options Flow":
        pc_ratio = data.get("put_call_ratio")
        iv_rank = data.get("iv_rank")

        parts = []
        if pc_ratio:
            pcr = float(pc_ratio) if pc_ratio else None
            if pcr and pcr < 0.7:
                parts.append(f"Put/Call ratio is {pcr:.2f} (bullish — more calls than puts being bought)")
            elif pcr and pcr > 1.0:
                parts.append(f"Put/Call ratio is {pcr:.2f} (bearish — more puts than calls)")
            elif pcr:
                parts.append(f"Put/Call ratio is {pcr:.2f} (neutral)")
        if iv_rank:
            parts.append(f"Implied volatility rank: {iv_rank}%")
        what = ". ".join(parts) + "." if parts else "Options data: " + content

        if direction == "bullish":
            why = "Options traders are betting on the stock going up. The options market is often called 'smart money' because it's dominated by institutional traders. When they buy calls aggressively, it's a bullish signal."
            todo = "Options flow confirms bullish bias. Consider buying stock or call options. If IV is low, options are cheap — good time for directional bets."
        elif direction == "bearish":
            why = "Options traders are buying protection (puts) or betting on a decline. Heavy put buying often precedes bad news — options traders frequently have information advantages."
            todo = "Options flow is warning of downside. If you hold this stock, consider buying protective puts or tightening stops. Don't ignore this signal."
        else:
            why = "Options activity is balanced — no strong directional bet from institutional traders. This means the 'smart money' isn't positioned for a big move in either direction."
            todo = "Neutral options flow — no edge here. Focus on other signals for direction."

        return what, why, todo

    elif signal_type == "Smart Money":
        insider_sig = data.get("insider_signal", "neutral")
        inst_sig = data.get("institutional_signal", "neutral")
        cluster = data.get("cluster_buy", False)
        factors = data.get("factors", [])

        parts = [f"Insider activity: {insider_sig}", f"Institutional flow: {inst_sig}"]
        if cluster:
            parts.append("CLUSTER BUY DETECTED — multiple insiders bought within 7 days")
        if factors:
            parts.extend(str(f) for f in factors[:2])
        what = ". ".join(parts) + "."

        if direction == "bullish":
            why = "Corporate insiders and large institutions are buying. Insiders know their company best — when CEOs and CFOs buy with their own money, it's one of the strongest bullish signals. Institutional accumulation means the 'big money' is building positions."
            if cluster:
                why += " A CLUSTER BUY (multiple insiders buying within 7 days) is historically the single most reliable bullish signal for retail traders."
            todo = "Smart money is on your side. This is a high-confidence buy signal. Insiders risk their own money — they don't do it casually. Consider a larger position size than normal."
        elif direction == "bearish":
            why = "Insiders are selling or institutions are reducing positions. While insider selling alone isn't always bearish (they sell for personal reasons too), heavy institutional selling means professional money managers are exiting."
            todo = "Smart money is leaving. Don't fight it. If you hold, consider reducing your position. If you don't hold, wait for insider selling to slow before entering."
        else:
            why = "No significant insider or institutional activity. This is common — most stocks see little insider trading most of the time. It's a neutral signal, not a negative one."
            todo = "No smart money signal — look at other indicators for direction."

        return what, why, todo

    elif signal_type == "Congressional Trades":
        factors = data.get("factors", [])
        what = content if content and content != "—" else "Congressional trading activity for this stock."
        if factors:
            what += " " + ". ".join(str(f) for f in factors[:2]) + "."

        if direction == "bullish":
            why = "Members of Congress are buying this stock. While controversial, congressional trades have historically outperformed the market. They have access to policy decisions, regulatory changes, and economic briefings before the public. Bipartisan buying is especially significant."
            todo = "Congress is buying — consider following. Note: trades are disclosed with up to 45-day delay, so the price may have already moved. Check if the stock has already rallied since the trade date."
        elif direction == "bearish":
            why = "Congressional members are selling this stock. This could signal upcoming regulation, policy changes, or sector headwinds that aren't public yet."
            todo = "Congress is selling — a cautionary signal. Don't panic, but factor this into your overall assessment. Check if there's pending legislation that could affect this stock's sector."
        else:
            why = "No significant congressional trading activity for this stock. Most stocks don't see congressional trades — it's only notable when it happens."
            todo = "No congressional signal — not unusual. Check the other signals."

        return what, why, todo

    elif signal_type == "Geopolitical & Event Risk":
        threat_level = data.get("threat_level", "normal")
        sector = data.get("sector", "unknown")
        at_risk = data.get("sector_at_risk", False)
        benefits = data.get("sector_benefits", False)
        events = data.get("events", [])
        risk_events = data.get("risk_events", [])
        benefit_events = data.get("benefit_events", [])

        event_summary = ", ".join(e.get("type", "").replace("_", " ").title() for e in events[:3]) if events else "none detected"
        what = f"Geopolitical threat level: {threat_level.upper()}. Active events: {event_summary}. {symbol}'s sector ({sector}) is {'directly exposed to risk' if at_risk else 'positioned to benefit' if benefits else 'not directly affected'}."

        if at_risk and risk_events:
            what += " Risk headlines: " + "; ".join(risk_events[:2]) + "."

        if direction == "bearish":
            why = (
                f"Your stock's sector ({sector}) is in the crosshairs of active geopolitical events. "
                "Tariffs raise costs, conflicts disrupt supply chains, and sanctions block revenue streams. "
                "Stocks in affected sectors typically drop 5-15% during escalation phases before stabilizing."
            )
            todo = (
                "Reduce exposure or hedge. Consider: (1) Tightening stop losses on this position, "
                "(2) Adding positions in sectors that benefit from the same event, "
                "(3) Waiting for the event to de-escalate before adding more."
            )
        elif direction == "bullish":
            why = (
                f"Your stock's sector ({sector}) actually benefits from current geopolitical dynamics. "
                "Defense stocks surge during conflicts, domestic manufacturers gain from tariffs, "
                "and construction companies profit from disaster rebuilding. This is a tailwind."
            )
            todo = (
                "Geopolitical tailwind supports your position. This stock may see increased demand or pricing power "
                "due to current events. Consider holding or adding on dips."
            )
        else:
            why = (
                f"Current geopolitical events have minimal direct impact on {symbol}'s sector ({sector}). "
                "The stock should trade primarily on its own fundamentals and technicals rather than macro events."
            )
            todo = (
                "Low geopolitical exposure — focus on the other signals above. "
                "Monitor if events escalate to sectors that affect your stock's supply chain or customer base."
            )

        return what, why, todo

    elif signal_type == "Analyst Ratings":
        consensus = data.get("consensus", "hold")
        num = data.get("num_analysts", 0)
        target_mean = data.get("target_mean")
        current = data.get("current_price")
        upside = data.get("upside_pct")
        sb = data.get("strong_buy", 0)
        b = data.get("buy", 0)
        h = data.get("hold", 0)
        s = data.get("sell", 0)
        ss = data.get("strong_sell", 0)

        parts = [f"Wall Street consensus: {consensus.replace('_', ' ').title()} from {num} analysts"]
        if sb or b:
            parts.append(f"{sb} Strong Buy, {b} Buy, {h} Hold, {s} Sell, {ss} Strong Sell")
        if target_mean and current:
            parts.append(f"Average price target: ${target_mean:.2f} (current: ${current:.2f})")
        if upside is not None:
            parts.append(f"Implied {'upside' if upside > 0 else 'downside'}: {upside:+.1f}%")
        what = ". ".join(parts) + "."

        if direction == "bullish":
            why = (
                f"The majority of Wall Street analysts rate {symbol} as a Buy or Strong Buy. "
                f"With {num} analysts covering this stock, the consensus represents significant institutional research. "
                "Analyst upgrades often precede institutional buying — fund managers follow their own firm's recommendations."
            )
            if upside and upside > 20:
                why += f" The {upside:.0f}% upside to target suggests analysts see significant room to run."
            todo = (
                "Analyst consensus supports buying. However, remember analysts are often late to downgrade — "
                "they maintained Buy ratings on many stocks through 2008 and 2022 crashes. Use as confirmation, not as your only signal."
            )
        elif direction == "bearish":
            why = (
                f"Analysts are cautious on {symbol} — the consensus is Sell or Hold with downside to price targets. "
                "When analysts turn bearish, it often means the problems are severe enough that even their inherent bullish bias can't hide them."
            )
            todo = "Analysts are negative — a rare and significant signal. Avoid buying. If you hold, consider reducing position size."
        else:
            why = (
                f"Analyst consensus is Hold — the default 'we don't know' rating. "
                "Most analysts are reluctant to issue Sell ratings (it hurts their firm's banking relationships). "
                "A Hold often means 'we'd sell if we could say so.' Dig deeper into the other signals."
            )
            todo = "Hold consensus — not helpful on its own. Focus on technical and smart money signals for direction."

        return what, why, todo

    elif signal_type == "Community Buzz":
        total = data.get("total_mentions", 0)
        bullish_pct = data.get("bullish_pct", 0)
        bearish_pct = data.get("bearish_pct", 0)
        buzz_level = data.get("buzz_level", "low")
        sources = data.get("sources", [])
        top_posts = data.get("top_posts", [])

        parts = [f"{buzz_level.title()} buzz — {total} mentions across {', '.join(sources) if sources else 'web'}"]
        parts.append(f"Community sentiment: {bullish_pct}% bullish, {bearish_pct}% bearish")
        if top_posts:
            top = top_posts[0]
            parts.append(f"Top discussion: \"{top.get('title', '')[:60]}\" ({top.get('source', '')})")
        what = ". ".join(parts) + "."

        if direction == "bullish":
            why = (
                f"The retail trading community is overwhelmingly bullish on {symbol}. "
                f"{bullish_pct}% of discussions are positive. High retail conviction can create short-term buying pressure "
                "as traders pile in. Reddit and StockTwits sentiment preceded several major moves in 2024-2025."
            )
            if buzz_level in ("high", "very high"):
                why += " However, extreme retail bullishness can also signal a near-term top — 'when everyone is bullish, who is left to buy?'"
            todo = (
                "Community supports the trade. Use this as confirmation alongside institutional and technical signals. "
                "If buzz is at peak AND price is extended, consider waiting for a pullback. "
                "Best entry: when buzz is RISING, not already at maximum."
            )
        elif direction == "bearish":
            why = (
                f"Retail traders are pessimistic about {symbol}. {bearish_pct}% of discussions are negative. "
                "When the crowd turns bearish, it often accelerates selling as retail panic sells. "
                "However, extreme bearishness can also create contrarian buying opportunities."
            )
            todo = (
                "Community sentiment is negative. If other signals are also bearish, avoid. "
                "But if fundamentals and institutions are bullish while retail is bearish, this could be a contrarian buy — "
                "retail traders often sell at the bottom."
            )
        else:
            why = (
                f"Community discussion about {symbol} is mixed — no strong consensus. "
                "This is actually normal for most stocks. Extreme sentiment (very bullish or very bearish) is what matters. "
                "Mixed sentiment means the crowd doesn't have a strong opinion."
            )
            todo = "Neutral buzz — no crowd signal. This is fine. Focus on the institutional and technical signals above."

        return what, why, todo

    elif signal_type == "Institutional Holders":
        inst_pct = data.get("institutional_pct", 0)
        insider_pct = data.get("insider_pct", 0)
        inst_count = data.get("institutional_count", 0)
        buyers = data.get("buyers", 0)
        sellers = data.get("sellers", 0)
        net_dir = data.get("net_direction", "stable")
        notable = data.get("notable", [])
        top_holders = data.get("top_holders", [])

        parts = [f"{inst_pct:.1f}% owned by {inst_count} institutions. Insiders hold {insider_pct:.1f}%"]
        parts.append(f"Among top 10 holders: {buyers} increasing positions, {sellers} decreasing. Net: {net_dir}")
        if top_holders:
            parts.append("Top holders: " + ", ".join(top_holders[:3]))
        if notable:
            parts.append("Notable: " + "; ".join(notable))
        what = ". ".join(parts) + "."

        # Add Claude's AI interpretation if available
        ai_interp = data.get("ai_interpretation", "")
        if ai_interp:
            what += " AI Analysis: " + ai_interp

        if direction == "bullish":
            why = (
                f"Major institutions are accumulating {symbol}. When Vanguard, BlackRock, and other trillion-dollar managers "
                "increase positions simultaneously, it signals deep fundamental conviction. These firms have armies of analysts — "
                "they don't increase positions casually. Institutional accumulation often precedes sustained price appreciation."
            )
            todo = (
                "Institutional backing is strong. This is a high-conviction long-term signal. "
                "Big money moves slowly — they'll continue buying over quarters, providing a floor for the stock price. "
                "Dips are likely to be bought by these same institutions."
            )
        elif direction == "bearish":
            why = (
                f"Institutions are reducing {symbol} positions. When the biggest holders start selling, it removes a key source of demand. "
                "Institutional selling is methodical — they sell over weeks/months to avoid moving the price. "
                "By the time it shows up in quarterly filings, they may be further along than the data suggests."
            )
            todo = (
                "Smart money is exiting. This is a significant warning. Institutions sell for fundamental reasons — "
                "deteriorating earnings, management concerns, or sector rotation. Consider reducing exposure and tightening stops."
            )
        else:
            why = (
                f"Institutional ownership is stable at {inst_pct:.0f}%. No major accumulation or distribution by top holders. "
                "The stock is in a holding pattern from the institutional perspective — no strong conviction either way."
            )
            todo = "Institutional flow is neutral. Focus on the other signals — technicals, sentiment, and analyst ratings — for direction."

        return what, why, todo

    elif signal_type == "Disruptive Technology":
        beneficiary_of = data.get("beneficiary_of", [])
        at_risk_from = data.get("at_risk_from", [])
        themes = data.get("themes", [])
        sector = data.get("sector", "")

        theme_list = ", ".join(t.get("name", "") for t in themes[:3]) if themes else "none tracked"
        what = f"Active disruption themes: {theme_list}. "

        if beneficiary_of:
            what += f"{symbol} is a direct beneficiary of: {', '.join(beneficiary_of)}."
        elif at_risk_from:
            what += f"{symbol}'s sector ({sector}) is being disrupted by: {', '.join(at_risk_from)}."
        else:
            what += f"{symbol}'s sector ({sector}) has no direct exposure to current disruption themes."

        if direction == "bullish":
            why = (
                f"{symbol} is riding a technology wave. Companies at the center of disruptive shifts often see "
                "exponential revenue growth as adoption accelerates. Early winners in disruption tend to keep winning — "
                "think NVDA in AI, TSLA in EVs. The market often underestimates how fast adoption curves move."
            )
            todo = (
                "Disruption tailwind supports a higher valuation than traditional metrics suggest. "
                "P/E ratios may look expensive but are justified by above-market growth rates. "
                "Hold through dips — disruption leaders recover faster than the market."
            )
        elif direction == "bearish":
            why = (
                f"{symbol}'s sector is facing structural disruption. Unlike a temporary downturn, disruption permanently "
                "shrinks the addressable market. Companies in disrupted sectors see revenue estimates consistently revised down. "
                "The market is slow to price this in — earnings misses compound over quarters."
            )
            todo = (
                "Structural headwind — this isn't a dip to buy. The company needs to adapt or its growth ceiling "
                "is permanently lower. If trading, use shorter hold periods and tighter stops. "
                "Consider pairing with a long position in the disruptor for a hedge."
            )
        else:
            why = (
                f"No major disruption is currently targeting {symbol}'s sector. The stock should trade on its own "
                "fundamentals and market dynamics rather than technology shifts."
            )
            todo = "No disruption signal — neutral. Focus on the other indicators for trading direction."

        return what, why, todo

    # Fallback
    return content, "This signal provides additional context for your trading decision.", "Consider this alongside the other signals above."


def _render_trade_plan(sym: str, report, period: str):
    """Render actionable trade plan card with entry, exit, sizing, and risk."""
    import html as html_mod

    v = report.verdict.value
    v_color = "#22c55e" if "Buy" in v else "#ef4444" if "Sell" in v else "#f59e0b"
    conf = report.confidence

    # Extract price data from report sections
    price = float(report.current_price) if report.current_price else None
    support = None
    resistance = None
    sma50 = None
    w52_high = None
    w52_low = None
    earnings_date = None
    pe_ratio = None

    for section in report.sections:
        d = section.data
        if "technical" in section.title.lower():
            support = float(d["support"]) if d.get("support") and str(d["support"]) != "None" else None
            resistance = float(d["resistance"]) if d.get("resistance") and str(d["resistance"]) != "None" else None
            sma50 = float(d["sma_50"]) if d.get("sma_50") and str(d["sma_50"]) != "None" else None
        if "overview" in section.title.lower():
            w52_high = float(d["52w_high"]) if d.get("52w_high") and str(d["52w_high"]) != "None" else None
            w52_low = float(d["52w_low"]) if d.get("52w_low") and str(d["52w_low"]) != "None" else None

    if not price:
        return

    # ── Calculate trade levels ─────────────────────────
    # Stop loss: below support or SMA50, whichever is tighter
    stop_candidates = [s for s in [support, sma50] if s and s < price]
    stop_loss = max(stop_candidates) if stop_candidates else round(price * 0.92, 2)

    # Targets
    target1 = resistance if resistance and resistance > price else round(price * 1.06, 2)
    target2 = w52_high if w52_high and w52_high > target1 else round(price * 1.12, 2)

    # Risk/Reward
    risk_per_share = round(price - stop_loss, 2)
    reward1 = round(target1 - price, 2)
    reward2 = round(target2 - price, 2)
    rr_ratio = round(reward1 / risk_per_share, 1) if risk_per_share > 0 else 0

    stop_pct = round((risk_per_share / price) * 100, 1)
    target1_pct = round((reward1 / price) * 100, 1)
    target2_pct = round((reward2 / price) * 100, 1)

    # ── Position sizing ────────────────────────────────
    account_size = 10000  # Default — user can change
    risk_pct = 2  # 2% risk per trade
    risk_amount = account_size * (risk_pct / 100)
    shares = int(risk_amount / risk_per_share) if risk_per_share > 0 else 0
    position_value = round(shares * price, 2)
    profit_t1 = round(shares * reward1, 2)
    loss_at_stop = round(shares * risk_per_share, 2)

    # ── Signal agreement (matches Signal Alignment card logic) ──
    bullish_words = ("buy", "bullish", "positive", "tailwind", "accumulating", "upgrade", "strong buy", "beneficiary")
    bearish_words = ("sell", "bearish", "negative", "risk", "distributing", "headwind", "downgrade", "at risk", "high risk")

    # Skip non-signal sections (Overview, Confluence)
    skip_sections = ("overview", "confluence")

    total_signals = 0
    bull_count = 0
    bear_count = 0
    neutral_count = 0
    for section in report.sections:
        if any(s in section.title.lower() for s in skip_sections):
            continue
        total_signals += 1
        cl = section.content.lower()
        is_bullish = any(w in cl for w in bullish_words)
        is_bearish = any(w in cl for w in bearish_words)
        if is_bullish and not is_bearish:
            bull_count += 1
        elif is_bearish and not is_bullish:
            bear_count += 1
        else:
            neutral_count += 1

    # Agreement = how many signals agree with the DOMINANT direction
    agree_signals = max(bull_count, bear_count)
    dominant = "bullish" if bull_count >= bear_count else "bearish"
    alignment_pct = round((agree_signals / total_signals) * 100) if total_signals > 0 else 0

    # ── Risks ──────────────────────────────────────────
    risk_items = []
    if report.risks:
        risk_items = [html_mod.escape(str(r)) for r in report.risks[:3]]

    # ── Timing ─────────────────────────────────────────
    timing_good = []
    timing_warn = []
    regime = "normal"
    for section in report.sections:
        if "macro" in section.title.lower():
            regime = section.data.get("regime", "normal")

    if regime == "normal":
        timing_good.append("Market regime: Normal (no macro headwinds)")
    elif "recession" in regime:
        timing_warn.append("Recession warning — reduce position sizes")

    if support and abs(price - support) / price < 0.03:
        timing_good.append(f"Price near support (${support:.2f}) — good entry zone")
    elif resistance and abs(price - resistance) / price < 0.02:
        timing_warn.append(f"Price near resistance (${resistance:.2f}) — may reject here, wait for breakout")

    # ── For sell verdicts, flip the framing ────────────
    is_buy = "Buy" in v
    is_sell = "Sell" in v
    action_word = "buying" if is_buy else "selling/avoiding" if is_sell else "monitoring"

    # ── Build HTML ─────────────────────────────────────
    # Entry/Exit/Target table
    levels_html = (
        f'<div style="display:grid; grid-template-columns:1fr 1fr 1fr; gap:12px; margin:12px 0;">'
        # Entry
        f'<div style="background:#0d0d0d; border:1px solid #2a2a2a; border-radius:8px; padding:12px; text-align:center;">'
        f'<div style="font-size:10px; color:#6b7280; text-transform:uppercase; letter-spacing:0.5px;">Entry Zone</div>'
        f'<div style="font-size:20px; font-weight:800; color:#e5e5e5; margin:4px 0;">${price:.2f}</div>'
        f'<div style="font-size:11px; color:#6b7280;">Current price</div>'
        f'</div>'
        # Stop Loss
        f'<div style="background:#0d0d0d; border:1px solid #ef444444; border-radius:8px; padding:12px; text-align:center;">'
        f'<div style="font-size:10px; color:#ef4444; text-transform:uppercase; letter-spacing:0.5px;">Stop Loss</div>'
        f'<div style="font-size:20px; font-weight:800; color:#ef4444; margin:4px 0;">${stop_loss:.2f}</div>'
        f'<div style="font-size:11px; color:#ef4444;">-{stop_pct}% max loss</div>'
        f'</div>'
        # Target
        f'<div style="background:#0d0d0d; border:1px solid #22c55e44; border-radius:8px; padding:12px; text-align:center;">'
        f'<div style="font-size:10px; color:#22c55e; text-transform:uppercase; letter-spacing:0.5px;">Target 1</div>'
        f'<div style="font-size:20px; font-weight:800; color:#22c55e; margin:4px 0;">${target1:.2f}</div>'
        f'<div style="font-size:11px; color:#22c55e;">+{target1_pct}% gain</div>'
        f'</div>'
        f'</div>'
    )

    # Target 2
    target2_html = (
        f'<div style="background:#0d0d0d; border:1px solid #22c55e22; border-radius:8px; padding:8px 12px; margin-bottom:12px; display:flex; justify-content:space-between; align-items:center;">'
        f'<span style="font-size:12px; color:#6b7280;">Target 2 (extended)</span>'
        f'<span style="font-size:14px; font-weight:700; color:#22c55e;">${target2:.2f} (+{target2_pct}%)</span>'
        f'</div>'
    )

    # Position sizing
    sizing_html = (
        f'<div style="background:#0d0d0d; border:1px solid #2a2a2a; border-radius:8px; padding:14px; margin-bottom:12px;">'
        f'<div style="font-size:12px; color:#3b82f6; font-weight:700; text-transform:uppercase; letter-spacing:0.5px; margin-bottom:8px;">Position Sizing</div>'
        f'<div style="display:grid; grid-template-columns:1fr 1fr 1fr; gap:8px;">'
        f'<div><div style="font-size:10px; color:#6b7280;">Account</div><div style="font-size:14px; font-weight:700; color:#e5e5e5;">${account_size:,}</div></div>'
        f'<div><div style="font-size:10px; color:#6b7280;">Risk ({risk_pct}%)</div><div style="font-size:14px; font-weight:700; color:#f59e0b;">${risk_amount:.0f}</div></div>'
        f'<div><div style="font-size:10px; color:#6b7280;">Shares</div><div style="font-size:14px; font-weight:700; color:#e5e5e5;">{shares}</div></div>'
        f'</div>'
        f'<div style="display:grid; grid-template-columns:1fr 1fr 1fr; gap:8px; margin-top:8px; padding-top:8px; border-top:1px solid #1a1a1a;">'
        f'<div><div style="font-size:10px; color:#6b7280;">Position</div><div style="font-size:14px; font-weight:700; color:#e5e5e5;">${position_value:,.0f}</div></div>'
        f'<div><div style="font-size:10px; color:#6b7280;">If Target 1</div><div style="font-size:14px; font-weight:700; color:#22c55e;">+${profit_t1:.0f}</div></div>'
        f'<div><div style="font-size:10px; color:#6b7280;">If Stopped</div><div style="font-size:14px; font-weight:700; color:#ef4444;">-${loss_at_stop:.0f}</div></div>'
        f'</div>'
        f'<div style="font-size:11px; color:#6b7280; margin-top:8px;">Risk/Reward: 1:{rr_ratio} — {"favorable" if rr_ratio >= 2 else "acceptable" if rr_ratio >= 1 else "unfavorable"}</div>'
        f'</div>'
    )

    # Signal confidence — with full breakdown
    conf_color = "#22c55e" if conf == "High" else "#f59e0b" if conf == "Medium" else "#ef4444"
    dom_color = "#22c55e" if dominant == "bullish" else "#ef4444"

    # Build dots
    dots = ('🟢 ' * bull_count + '🔴 ' * bear_count + '🟡 ' * neutral_count).strip()

    # Stacked bar percentages
    bull_pct = round(bull_count / total_signals * 100) if total_signals > 0 else 0
    bear_pct = round(bear_count / total_signals * 100) if total_signals > 0 else 0
    neut_pct = 100 - bull_pct - bear_pct

    # Insight text
    if alignment_pct >= 70:
        insight = f"Strong conviction — {bull_count if dominant == 'bullish' else bear_count} of {total_signals} signals point {dominant}. High probability setup."
    elif alignment_pct >= 45:
        insight = f"Moderate conviction — signals are leaning {dominant} but not unanimous. Use additional confirmation before trading."
    else:
        insight = "Weak conviction — signals are split. Consider waiting for clearer alignment or reducing position size."

    # What's driving it
    bull_names = []
    bear_names = []
    for section in report.sections:
        if any(s in section.title.lower() for s in ("overview", "confluence")):
            continue
        cl = section.content.lower()
        is_b = any(w in cl for w in bullish_words)
        is_s = any(w in cl for w in bearish_words)
        if is_b and not is_s:
            bull_names.append(section.title)
        elif is_s and not is_b:
            bear_names.append(section.title)

    confidence_html = (
        f'<div style="background:#0d0d0d; border:1px solid {conf_color}44; border-radius:12px; padding:18px; margin-bottom:12px;">'
        f'<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">'
        f'<div style="font-size:13px; color:#3b82f6; font-weight:700; text-transform:uppercase; letter-spacing:0.5px;">Signal Confidence</div>'
        f'<div style="font-size:24px; font-weight:900; color:{conf_color};">{alignment_pct}%</div>'
        f'</div>'
        # Dots
        f'<div style="font-size:16px; margin-bottom:10px; letter-spacing:2px;">{dots}</div>'
        # Stacked bar
        f'<div style="display:flex; height:8px; border-radius:4px; overflow:hidden; margin-bottom:10px;">'
        f'<div style="width:{bull_pct}%; background:#22c55e;"></div>'
        f'<div style="width:{bear_pct}%; background:#ef4444;"></div>'
        f'<div style="width:{neut_pct}%; background:#f59e0b;"></div>'
        f'</div>'
        # Counts
        f'<div style="display:flex; gap:16px; margin-bottom:12px; font-size:12px;">'
        f'<span style="color:#22c55e; font-weight:700;">{bull_count} Bullish</span>'
        f'<span style="color:#ef4444; font-weight:700;">{bear_count} Bearish</span>'
        f'<span style="color:#f59e0b; font-weight:700;">{neutral_count} Neutral</span>'
        f'<span style="color:#6b7280;">of {total_signals} signals</span>'
        f'</div>'
        # Insight
        f'<div style="font-size:13px; color:#d1d5db; line-height:1.6; margin-bottom:8px;">{html_mod.escape(insight)}</div>'
        # What's bullish
        + (f'<div style="font-size:11px; color:#22c55e; margin-bottom:4px;">Bullish: {html_mod.escape(", ".join(bull_names[:4]))}</div>' if bull_names else "")
        # What's bearish
        + (f'<div style="font-size:11px; color:#ef4444;">{html_mod.escape("Bearish: " + ", ".join(bear_names[:4]))}</div>' if bear_names else "")
        + f'</div>'
    )

    # Risks
    risks_html = ""
    if risk_items:
        risk_bullets = "".join(f'<div style="margin:4px 0; font-size:12px; color:#f87171;">⚠ {r}</div>' for r in risk_items)
        risks_html = (
            f'<div style="background:#0d0d0d; border:1px solid #ef444422; border-radius:8px; padding:14px; margin-bottom:12px;">'
            f'<div style="font-size:12px; color:#ef4444; font-weight:700; text-transform:uppercase; letter-spacing:0.5px; margin-bottom:6px;">Key Risks</div>'
            f'{risk_bullets}</div>'
        )

    # Timing
    timing_html = ""
    timing_items = []
    for t in timing_good:
        timing_items.append(f'<div style="margin:3px 0; font-size:12px; color:#22c55e;">✓ {html_mod.escape(t)}</div>')
    for t in timing_warn:
        timing_items.append(f'<div style="margin:3px 0; font-size:12px; color:#f59e0b;">⚠ {html_mod.escape(t)}</div>')
    if timing_items:
        timing_html = (
            f'<div style="background:#0d0d0d; border:1px solid #2a2a2a; border-radius:8px; padding:14px; margin-bottom:12px;">'
            f'<div style="font-size:12px; color:#3b82f6; font-weight:700; text-transform:uppercase; letter-spacing:0.5px; margin-bottom:6px;">Timing</div>'
            f'{"".join(timing_items)}</div>'
        )

    # Assemble full trade plan
    st.markdown(
        f'<div style="background:#0a0a0a; border:2px solid {v_color}; border-radius:12px; padding:20px; margin:16px 0;">'
        f'<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:16px;">'
        f'<div style="display:flex; align-items:center; gap:10px;">'
        f'<span style="font-size:20px;">💡</span>'
        f'<span style="font-size:18px; font-weight:800; color:#e5e5e5;">TRADE PLAN — {sym}</span>'
        f'</div>'
        f'<div style="display:flex; align-items:center; gap:12px;">'
        f'<span style="font-size:20px; font-weight:800; color:{v_color};">{v}</span>'
        f'<span style="font-size:13px; color:{conf_color}; font-weight:600;">{conf} Conf</span>'
        f'</div>'
        f'</div>'
        f'{levels_html}'
        f'{target2_html}'
        f'{sizing_html}'
        f'{confidence_html}'
        f'{risks_html}'
        f'{timing_html}'
        f'<div style="font-size:10px; color:#4b5563; text-align:center; margin-top:8px;">Position sizing based on ${account_size:,} account with {risk_pct}% risk per trade. Adjust in settings. Not financial advice.</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # Action buttons
    b1, b2, _ = st.columns([2, 2, 4])
    with b1:
        if st.button(f"Backtest {sym} →", key=f"bt_{sym}", use_container_width=True):
            navigate_to(4, sym)
    with b2:
        if st.button(f"Log Trade {sym}", key=f"log_{sym}", use_container_width=True):
            navigate_to(5, sym)


def _render_deep_dive_card(sym: str, report, lookback: int, period: str, signal_filter: str):
    """Render a full deep dive card for one stock."""
    import html as html_mod

    v = report.verdict.value
    v_color = "#22c55e" if "Buy" in v else "#ef4444" if "Sell" in v else "#f59e0b"

    # Period price change
    pct_chg = getattr(report, "_period_change_pct", 0)
    start_price = getattr(report, "_period_start_price", None)
    chg_color = "#22c55e" if pct_chg > 0 else "#ef4444" if pct_chg < 0 else "#9ca3af"
    chg_arrow = "↑" if pct_chg > 0 else "↓" if pct_chg < 0 else ""
    period_price_html = (
        f'<div style="font-size:12px; color:{chg_color}; font-weight:600; margin-top:2px;">'
        f'{chg_arrow} {pct_chg:+.1f}% over {period}'
        f'</div>'
    ) if pct_chg != 0 else ""

    # Confidence color
    conf = report.confidence
    conf_color = "#22c55e" if conf == "High" else "#f59e0b" if conf == "Medium" else "#ef4444"

    # Risk color
    risk_val = report.risk_rating.value
    risk_color = "#22c55e" if risk_val <= 2 else "#ef4444" if risk_val >= 4 else "#f59e0b"

    # Sentiment color
    try:
        sent_val = float(report.sentiment_score)
        sent_color = "#22c55e" if sent_val > 0.3 else "#ef4444" if sent_val < -0.3 else "#f59e0b"
    except (ValueError, TypeError):
        sent_color = "#6b7280"

    # Count bullish/bearish signals for quick summary
    bull_count = sum(1 for s in report.sections if any(w in s.content.lower() for w in ("buy", "bullish", "positive")))
    bear_count = sum(1 for s in report.sections if any(w in s.content.lower() for w in ("sell", "bearish", "negative")))
    total_sigs = bull_count + bear_count
    signal_summary = f"{bull_count} bullish, {bear_count} bearish" if total_sigs > 0 else "analyzing..."

    # ── Verdict banner ─────────────────────────────────
    st.markdown(
        # Outer container
        f'<div style="background:linear-gradient(135deg, #0d0d0d 0%, #111 100%); border:1px solid {v_color}; border-radius:16px; padding:24px; margin-bottom:20px;">'
        # Top row: symbol + verdict
        f'<div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:20px;">'
        f'<div>'
        f'<div style="display:flex; align-items:center; gap:12px;">'
        f'<span style="font-size:28px; font-weight:900; color:#e5e5e5; letter-spacing:-0.5px;">{sym}</span>'
        f'<span style="font-size:11px; color:#6b7280; background:#1a1a1a; padding:4px 10px; border-radius:20px;">{period} analysis</span>'
        f'</div>'
        f'<div style="font-size:13px; color:#6b7280; margin-top:4px;">{signal_summary} out of {total_sigs} signal{"s" if total_sigs != 1 else ""}</div>'
        f'</div>'
        f'<div style="text-align:center;">'
        f'<div style="font-size:36px; font-weight:900; color:{v_color}; letter-spacing:-1px; line-height:1;">{v}</div>'
        f'<div style="font-size:12px; color:{conf_color}; font-weight:700; margin-top:4px;">{conf} Confidence</div>'
        f'</div>'
        f'</div>'
        # KPI row
        f'<div style="display:grid; grid-template-columns:repeat(4, 1fr); gap:12px;">'
        # Price
        f'<div style="background:#0a0a0a; border:1px solid #1a1a1a; border-radius:10px; padding:14px; text-align:center;">'
        f'<div style="font-size:10px; color:#6b7280; text-transform:uppercase; letter-spacing:0.8px;">Price</div>'
        f'<div style="font-size:22px; font-weight:800; color:#e5e5e5; margin:4px 0;">${report.current_price}</div>'
        f'{period_price_html}'
        f'</div>'
        # Confidence
        f'<div style="background:#0a0a0a; border:1px solid #1a1a1a; border-radius:10px; padding:14px; text-align:center;">'
        f'<div style="font-size:10px; color:#6b7280; text-transform:uppercase; letter-spacing:0.8px;">Confidence</div>'
        f'<div style="font-size:22px; font-weight:800; color:{conf_color}; margin:4px 0;">{conf}</div>'
        f'<div style="font-size:11px; color:#6b7280;">Signal alignment</div>'
        f'</div>'
        # Risk
        f'<div style="background:#0a0a0a; border:1px solid #1a1a1a; border-radius:10px; padding:14px; text-align:center;">'
        f'<div style="font-size:10px; color:#6b7280; text-transform:uppercase; letter-spacing:0.8px;">Risk Level</div>'
        f'<div style="font-size:22px; font-weight:800; color:{risk_color}; margin:4px 0;">{risk_val}/5</div>'
        f'<div style="font-size:11px; color:#6b7280;">{"Low" if risk_val <= 2 else "High" if risk_val >= 4 else "Moderate"} risk</div>'
        f'</div>'
        # Sentiment
        f'<div style="background:#0a0a0a; border:1px solid #1a1a1a; border-radius:10px; padding:14px; text-align:center;">'
        f'<div style="font-size:10px; color:#6b7280; text-transform:uppercase; letter-spacing:0.8px;">Sentiment</div>'
        f'<div style="font-size:22px; font-weight:800; color:{sent_color}; margin:4px 0;">{float(report.sentiment_score):.5f}</div>'
        f'<div style="font-size:11px; color:#6b7280;">News mood</div>'
        f'</div>'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # Section header
    st.markdown(
        '<div style="display:flex; align-items:center; gap:8px; margin:20px 0 12px;">'
        '<div style="height:2px; flex:1; background:linear-gradient(to right, #333, transparent);"></div>'
        '<span style="font-size:13px; font-weight:700; color:#6b7280; text-transform:uppercase; letter-spacing:1px;">Signal Breakdown</span>'
        '<div style="height:2px; flex:1; background:linear-gradient(to left, #333, transparent);"></div>'
        '</div>',
        unsafe_allow_html=True,
    )

    # ── Signal breakdown with educational explanations ──
    signal_sections = {
        "Technical Analysis": {"color": "#3b82f6", "max": 2, "icon": "📈"},
        "Fundamental Analysis": {"color": "#8b5cf6", "max": 2, "icon": "📊"},
        "News Sentiment": {"color": "#06b6d4", "max": 1, "icon": "📰"},
        "Macro Environment": {"color": "#f59e0b", "max": 2, "icon": "🌍"},
        "Options Flow": {"color": "#ec4899", "max": 2, "icon": "⚡"},
        "Smart Money": {"color": "#10b981", "max": 2, "icon": "🏦"},
        "Congressional Trades": {"color": "#6366f1", "max": 1, "icon": "🏛"},
        "Geopolitical & Event Risk": {"color": "#f97316", "max": 1, "icon": "🌐"},
        "Disruptive Technology": {"color": "#a855f7", "max": 1, "icon": "🚀"},
        "Analyst Ratings": {"color": "#0ea5e9", "max": 1, "icon": "🎯"},
        "Institutional Holders": {"color": "#14b8a6", "max": 1, "icon": "🏛"},
        "Community Buzz": {"color": "#e879f9", "max": 1, "icon": "🗣"},
    }

    for section in report.sections:
        config = None
        matched_key = None
        for key, cfg in signal_sections.items():
            if key.lower() in section.title.lower():
                config = cfg
                matched_key = key
                break
        if not config:
            continue

        content_lower = section.content.lower()
        data_score = section.data.get("score", section.data.get("overall", None))

        # Use numeric score if available (more reliable than keyword matching)
        # Threshold: scores between -0.1 and +0.1 are neutral (too weak to be directional)
        if data_score is not None:
            try:
                score_numeric = float(data_score)
                if score_numeric > 0.1:
                    direction = "bullish"
                    fill_color = "#22c55e"
                    dir_icon = "🟢"
                elif score_numeric < -0.1:
                    direction = "bearish"
                    fill_color = "#ef4444"
                    dir_icon = "🔴"
                else:
                    direction = "neutral"
                    fill_color = "#f59e0b"
                    dir_icon = "🟡"
            except (ValueError, TypeError):
                direction = "neutral"
                fill_color = "#f59e0b"
                dir_icon = "🟡"
        # Fallback to keyword matching for sections without numeric scores
        elif any(w in content_lower for w in ("buy", "bullish", "tailwind", "accumulating", "strong buy")):
            direction = "bullish"
            fill_color = "#22c55e"
            dir_icon = "🟢"
        elif any(w in content_lower for w in ("sell", "bearish", "headwind", "distributing", "high risk")):
            direction = "bearish"
            fill_color = "#ef4444"
            dir_icon = "🔴"
        else:
            direction = "neutral"
            fill_color = "#f59e0b"
            dir_icon = "🟡"

        # Apply signal filter
        if signal_filter == "Buy Only" and direction != "bullish":
            continue
        if signal_filter == "Sell Only" and direction != "bearish":
            continue
        if signal_filter == "Strong Only" and direction == "neutral":
            continue

        data = section.data
        score_val = data.get("score", data.get("overall", data.get("valuation", 0)))
        try:
            score_num = float(score_val) if score_val else 0
        except (ValueError, TypeError):
            score_num = 0
        bar_pct = min(max((score_num + config["max"]) / (2 * config["max"]) * 100, 5), 95)

        # Build 3-part educational explanation
        what_says, why_matters, what_todo = _explain_signal_section(
            matched_key, direction, data, section.content, sym
        )

        # (Pro detail removed — signal cards provide full explanation)

        # Direction badge bg
        dir_bg = "rgba(34,197,94,0.1)" if direction == "bullish" else "rgba(239,68,68,0.1)" if direction == "bearish" else "rgba(245,158,11,0.1)"

        # Render card
        st.markdown(
            # Card container
            f'<div style="background:linear-gradient(135deg, #0d0d0d, #111); border:1px solid #1a1a1a; border-left:4px solid {config["color"]}; border-radius:12px; padding:20px; margin-bottom:16px;">'
            # Header row
            f'<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">'
            f'<div style="display:flex; align-items:center; gap:10px;">'
            f'<div style="width:36px; height:36px; background:{config["color"]}15; border-radius:10px; display:flex; align-items:center; justify-content:center; font-size:20px;">{config["icon"]}</div>'
            f'<span style="color:#e5e5e5; font-weight:800; font-size:16px;">{section.title}</span>'
            f'</div>'
            f'<div style="display:flex; align-items:center; gap:6px; padding:6px 14px; background:{dir_bg}; border:1px solid {fill_color}44; border-radius:20px;">'
            f'<span style="font-size:12px;">{dir_icon}</span>'
            f'<span style="font-weight:700; font-size:12px; color:{fill_color}; letter-spacing:0.3px;">{direction.upper()}</span>'
            f'</div>'
            f'</div>'
            # Progress bar
            f'<div style="height:4px; background:#1a1a1a; border-radius:2px; margin-bottom:16px; overflow:hidden;">'
            f'<div style="height:100%; width:{bar_pct}%; background:linear-gradient(to right, {config["color"]}, {fill_color}); border-radius:2px; transition:width 0.5s;"></div>'
            f'</div>'
            # 3-section grid
            f'<div style="display:grid; grid-template-columns:1fr; gap:12px;">'
            # What the data says
            f'<div style="background:#0a0a0a; border-radius:8px; padding:14px;">'
            f'<div style="display:flex; align-items:center; gap:6px; margin-bottom:6px;">'
            f'<div style="width:4px; height:14px; background:{config["color"]}; border-radius:2px;"></div>'
            f'<span style="font-size:10px; color:{config["color"]}; font-weight:700; text-transform:uppercase; letter-spacing:0.8px;">What the data says</span>'
            f'</div>'
            f'<div style="font-size:13px; color:#e5e5e5; line-height:1.7;">{html_mod.escape(what_says)}</div>'
            f'</div>'
            # Why this matters
            f'<div style="background:#0a0a0a; border-radius:8px; padding:14px;">'
            f'<div style="display:flex; align-items:center; gap:6px; margin-bottom:6px;">'
            f'<div style="width:4px; height:14px; background:{config["color"]}; border-radius:2px;"></div>'
            f'<span style="font-size:10px; color:{config["color"]}; font-weight:700; text-transform:uppercase; letter-spacing:0.8px;">Why this matters</span>'
            f'</div>'
            f'<div style="font-size:13px; color:#d1d5db; line-height:1.7;">{html_mod.escape(why_matters)}</div>'
            f'</div>'
            # What to do
            f'<div style="background:#0a0a0a; border-radius:8px; padding:14px; border:1px solid {fill_color}22;">'
            f'<div style="display:flex; align-items:center; gap:6px; margin-bottom:6px;">'
            f'<div style="width:4px; height:14px; background:{fill_color}; border-radius:2px;"></div>'
            f'<span style="font-size:10px; color:{fill_color}; font-weight:700; text-transform:uppercase; letter-spacing:0.8px;">What to do</span>'
            f'</div>'
            f'<div style="font-size:13px; color:#d1d5db; line-height:1.7;">{html_mod.escape(what_todo)}</div>'
            f'</div>'
            f'</div>'
            + f'</div>',
            unsafe_allow_html=True,
        )

        # Build raw data line for pro detail (shown inside expander)
        pro_parts = []
        for k, v_raw in data.items():
            if k in ("factors", "strengths", "weaknesses", "agreements", "divergences", "warnings", "events", "risk_events", "benefit_events", "top_posts", "top_holders", "notable", "themes"):
                continue
            if isinstance(v_raw, (list, dict)):
                continue
            if v_raw is not None and str(v_raw) not in ("", "None", "0", "[]", "False"):
                pro_parts.append(f"{k}: {v_raw}")
        pro_line = html_mod.escape(" | ".join(pro_parts[:10])) if pro_parts else ""

        # Track record expander (computed on click, uses timeframe filter as hold period)
        from src.analysis.backtester import NON_BACKTESTABLE
        hold_label = {"5": "5 days", "21": "21 days", "63": "63 days", "126": "6 months", "252": "1 year"}.get(str(lookback), f"{lookback} days")

        if matched_key not in NON_BACKTESTABLE:
            with st.expander(f"Signal Track Record — {matched_key} ({hold_label} hold)", expanded=False):
                record = _get_signal_track_record(sym, matched_key, direction, hold_days=lookback)
                if record and record["total"] > 0:
                    _render_track_record(record, config["color"])
                else:
                    st.caption(f"No signal triggers found with a {hold_label} hold period.")
                if pro_line:
                    st.markdown(f'<div style="font-size:10px; color:#4b5563; margin-top:10px; padding-top:8px; border-top:1px solid #1a1a1a; font-family:monospace;">{pro_line}</div>', unsafe_allow_html=True)
        else:
            with st.expander(f"Signal Track Record — {matched_key} ({hold_label} hold)", expanded=False):
                st.caption(f"Track record not available for {matched_key.lower()} — these signals require qualitative judgment rather than historical price validation.")
                if pro_line:
                    st.markdown(f'<div style="font-size:10px; color:#4b5563; margin-top:10px; padding-top:8px; border-top:1px solid #1a1a1a; font-family:monospace;">{pro_line}</div>', unsafe_allow_html=True)

    # ── Trade Plan section divider ──────────────────────
    st.markdown(
        '<div style="display:flex; align-items:center; gap:8px; margin:24px 0 12px;">'
        '<div style="height:2px; flex:1; background:linear-gradient(to right, #333, transparent);"></div>'
        '<span style="font-size:13px; font-weight:700; color:#6b7280; text-transform:uppercase; letter-spacing:1px;">Trade Plan</span>'
        '<div style="height:2px; flex:1; background:linear-gradient(to left, #333, transparent);"></div>'
        '</div>',
        unsafe_allow_html=True,
    )
    _render_trade_plan(sym, report, period)

    # ── Chart + Earnings + Volume in tabs ──────────────
    tab_chart, tab_earnings, tab_volume = st.tabs(["Price Chart", "Earnings", "Volume Profile"])
    with tab_chart:
        _render_multi_timeframe_chart(sym)
    with tab_earnings:
        _render_earnings_calendar(sym)
    with tab_volume:
        _render_volume_profile(sym)

    st.divider()


# ═══════════════════════════════════════════════════════════════
# STEP 4: PROVE IT
# ═══════════════════════════════════════════════════════════════

def page_prove_it():
    st.title("Prove It")
    st.caption("Backtest signals on historical data — did they actually make money?")

    from src.data.gateway import DataGateway
    from src.analysis.backtester import backtest_all_signals, backtest_signal, SIGNALS

    # ── Multi-stock selector (same pattern as Deep Dive) ──
    watchlist = get_watchlist()
    wl_syms = [w["symbol"] for w in watchlist] if watchlist else []
    preselected = [st.session_state.selected_stock] if st.session_state.selected_stock else []

    sel_col, add_col = st.columns([4, 1])
    with sel_col:
        selected_stocks = st.multiselect(
            "Select stocks to backtest",
            options=wl_syms + [s for s in POPULAR_STOCKS if s not in wl_syms],
            format_func=lambda s: f"{s} — {STOCK_DB[s][0]} ({STOCK_DB[s][1]})" if s in STOCK_DB else f"{s} (custom)",
            default=[s for s in preselected if s],
            placeholder="Pick one or more stocks...",
            key="bt_stocks",
        )
    with add_col:
        custom_bt = st.text_input("Custom", placeholder="Any ticker", max_chars=10, label_visibility="collapsed", key="bt_custom")
        if custom_bt:
            cb = custom_bt.upper()
            if cb not in selected_stocks:
                if cb in STOCK_DB:
                    selected_stocks.append(cb)
                else:
                    valid, name = _validate_ticker(cb)
                    if valid:
                        STOCK_DB[cb] = (name or cb, "Unknown", "custom")
                        selected_stocks.append(cb)
                    else:
                        st.error(f"'{cb}' not found.")

    if not selected_stocks:
        st.info("Select stocks from the dropdown above, or come here from Deep Dive.")
        return

    # ── Filter bar (same timeframe as Discover/Deep Dive) ──
    f1, f2, f3 = st.columns([2, 2, 2])
    with f1:
        bt_period = st.segmented_control("Hold period", ["1D", "1W", "1M", "3M", "6M", "1Y"], default="1M", key="bt_tf", label_visibility="collapsed")
        if bt_period is None:
            bt_period = "1M"
    with f2:
        from src.analysis.backtester import SIGNAL_CATEGORIES
        signal_category = st.selectbox("Signal category",
            list(SIGNAL_CATEGORIES.keys()),
            index=0, label_visibility="collapsed", key="bt_cat")
    with f3:
        sort_by = st.selectbox("Sort by", ["Win Rate", "Avg Return", "Total Trades", "Expected Value"], index=0, label_visibility="collapsed", key="bt_sort")

    period_map = {"1D": 1, "1W": 5, "1M": 21, "3M": 63, "6M": 126, "1Y": 252}
    hold_days = period_map[bt_period]
    hold_label = {"1D": "1 day", "1W": "1 week", "1M": "1 month", "3M": "3 months", "6M": "6 months", "1Y": "1 year"}.get(bt_period, f"{hold_days} days")

    # ── Tabs ──────────────────────────────────────────────
    tab_accuracy, tab_explorer, tab_ai, tab_multi, tab_portfolio = st.tabs([
        "Signal Accuracy", "Signal Explorer", "AI Analyst", "Multi-Stock Compare", "Portfolio Simulation",
    ])

    gw = DataGateway()

    # ── Tab 1: Signal Accuracy ────────────────────────────
    with tab_accuracy:
        symbol = selected_stocks[0]

        st.markdown(
            '<div style="display:flex; align-items:center; gap:8px; margin-bottom:12px;">'
            f'<span style="font-size:18px; font-weight:800; color:#e5e5e5;">{symbol}</span>'
            f'<span style="font-size:12px; color:#6b7280;">— {hold_label} hold period</span>'
            '</div>',
            unsafe_allow_html=True,
        )

        with st.spinner(f"Backtesting {symbol}..."):
            hist = gw.get_historical(symbol, period_days=max(365, hold_days * 5))

        if hist is None or hist.empty or len(hist) < 60:
            st.warning("Not enough historical data.")
        else:
            results = backtest_all_signals(symbol, hist, hold_days)
            results = [r for r in results if r.total_trades > 0]

            # Sort
            if sort_by == "Win Rate":
                results.sort(key=lambda r: r.win_rate, reverse=True)
            elif sort_by == "Avg Return":
                results.sort(key=lambda r: r.avg_return, reverse=True)
            elif sort_by == "Total Trades":
                results.sort(key=lambda r: r.total_trades, reverse=True)
            else:
                results.sort(key=lambda r: r.win_rate * r.avg_return, reverse=True)

            # Filter by category
            if signal_category != "All Signals":
                allowed = set(SIGNAL_CATEGORIES.get(signal_category, []))
                results = [r for r in results if r.signal_name in allowed]

            if not results:
                st.info("No signal triggers found for the selected category and hold period.")
            else:
                for i, r in enumerate(results):
                    wr_color = "#22c55e" if r.win_rate >= 0.65 else "#ef4444" if r.win_rate < 0.45 else "#f59e0b"
                    ret_color = "#22c55e" if r.avg_return > 0 else "#ef4444"
                    grade_colors = {"A+": "#22c55e", "A": "#22c55e", "B+": "#86efac", "B": "#f59e0b", "C": "#9ca3af", "D": "#ef4444"}
                    gc = grade_colors.get(r.grade, "#6b7280")

                    # Win/loss dots
                    dots = ""
                    for t in r.trades[:15]:
                        dots += f'<span style="color:{"#22c55e" if t.outcome == "win" else "#ef4444"}; font-size:14px;">{"●" if t.outcome == "win" else "○"}</span>'

                    desc = SIGNALS.get(r.signal_name, {}).get("description", "")

                    st.markdown(
                        f'<div style="background:linear-gradient(135deg, #0d0d0d, #111); border:1px solid #1a1a1a; border-radius:12px; padding:16px; margin-bottom:10px;">'
                        f'<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">'
                        f'<div>'
                        f'<span style="color:#6b7280; font-size:13px;">#{i+1}</span>'
                        f'<span style="font-weight:800; color:#e5e5e5; font-size:15px; margin-left:8px;">{r.signal_name.replace("_", " ").title()}</span>'
                        f'<span style="font-size:12px; color:#6b7280; margin-left:8px;">{desc}</span>'
                        f'</div>'
                        f'<span style="padding:4px 12px; background:{gc}22; color:{gc}; border:1px solid {gc}; border-radius:20px; font-weight:800; font-size:13px;">{r.grade}</span>'
                        f'</div>'
                        # Dots
                        f'<div style="margin-bottom:8px;">{dots}</div>'
                        # Stats row
                        f'<div style="display:grid; grid-template-columns:repeat(5, 1fr); gap:8px;">'
                        f'<div style="background:#0a0a0a; border-radius:6px; padding:8px; text-align:center;">'
                        f'<div style="font-size:9px; color:#6b7280; text-transform:uppercase;">Win Rate</div>'
                        f'<div style="font-size:16px; font-weight:800; color:{wr_color};">{r.win_rate*100:.0f}%</div></div>'
                        f'<div style="background:#0a0a0a; border-radius:6px; padding:8px; text-align:center;">'
                        f'<div style="font-size:9px; color:#6b7280; text-transform:uppercase;">Avg Return</div>'
                        f'<div style="font-size:16px; font-weight:800; color:{ret_color};">{r.avg_return:+.1f}%</div></div>'
                        f'<div style="background:#0a0a0a; border-radius:6px; padding:8px; text-align:center;">'
                        f'<div style="font-size:9px; color:#6b7280; text-transform:uppercase;">Trades</div>'
                        f'<div style="font-size:16px; font-weight:800; color:#e5e5e5;">{r.total_trades}</div></div>'
                        f'<div style="background:#0a0a0a; border-radius:6px; padding:8px; text-align:center;">'
                        f'<div style="font-size:9px; color:#6b7280; text-transform:uppercase;">Best</div>'
                        f'<div style="font-size:16px; font-weight:800; color:#22c55e;">{r.max_gain:+.1f}%</div></div>'
                        f'<div style="background:#0a0a0a; border-radius:6px; padding:8px; text-align:center;">'
                        f'<div style="font-size:9px; color:#6b7280; text-transform:uppercase;">Worst</div>'
                        f'<div style="font-size:16px; font-weight:800; color:#ef4444;">{r.max_loss:+.1f}%</div></div>'
                        f'</div></div>',
                        unsafe_allow_html=True,
                    )

                if results:
                    best = results[0]
                    st.markdown(
                        f'<div style="background:#0d0d0d; border:1px solid #22c55e44; border-radius:10px; padding:14px; margin-top:8px;">'
                        f'<div style="font-size:13px; color:#22c55e; font-weight:700;">Best Signal: {best.signal_name.replace("_", " ").title()}</div>'
                        f'<div style="font-size:12px; color:#d1d5db; margin-top:4px;">'
                        f'{best.win_rate*100:.0f}% win rate with {best.avg_return:+.1f}% avg return over {hold_label}. '
                        f'Triggered {best.total_trades} times in the past year.</div></div>',
                        unsafe_allow_html=True,
                    )

    # ── Tab 2: Signal Explorer ────────────────────────────
    with tab_explorer:
        symbol = selected_stocks[0]
        signal_name = st.selectbox("Select signal to explore", list(SIGNALS.keys()),
                                    format_func=lambda s: f"{s.replace('_', ' ').title()} — {SIGNALS[s]['description']}",
                                    key="bt_explore_sig")

        hist = gw.get_historical(symbol, period_days=max(365, hold_days * 5))
        if hist is None or hist.empty or len(hist) < 60:
            st.warning("Not enough data.")
        else:
            result = backtest_signal(symbol, hist, signal_name, hold_days)
            if result and result.trades:
                fig = go.Figure()
                fig.add_trace(go.Candlestick(x=hist["date"], open=hist["open"], high=hist["high"],
                                              low=hist["low"], close=hist["close"], name="Price"))
                wins = [t for t in result.trades if t.outcome == "win"]
                losses = [t for t in result.trades if t.outcome == "loss"]
                if wins:
                    fig.add_trace(go.Scatter(
                        x=[t.entry_date for t in wins], y=[t.entry_price for t in wins],
                        mode="markers", name="Win",
                        marker=dict(color="#22c55e", size=12, symbol="triangle-up", line=dict(color="#fff", width=1)),
                        hovertemplate="<b>%{text}</b><extra></extra>",
                        text=[f"WIN: {t.pnl_percent:+.1f}% in {t.hold_days}d" for t in wins],
                    ))
                if losses:
                    fig.add_trace(go.Scatter(
                        x=[t.entry_date for t in losses], y=[t.entry_price for t in losses],
                        mode="markers", name="Loss",
                        marker=dict(color="#ef4444", size=12, symbol="triangle-down", line=dict(color="#fff", width=1)),
                        hovertemplate="<b>%{text}</b><extra></extra>",
                        text=[f"LOSS: {t.pnl_percent:+.1f}% in {t.hold_days}d" for t in losses],
                    ))
                fig.update_layout(template="plotly_dark", height=450, plot_bgcolor="#0a0a0a", paper_bgcolor="#0a0a0a",
                                  xaxis_rangeslider_visible=False,
                                  title=f"{signal_name.replace('_', ' ').title()} — {symbol} ({hold_label} hold)")
                st.plotly_chart(fig, use_container_width=True)

                # Summary stats
                total_trades = len(result.trades)
                win_count = len(wins)
                loss_count = len(losses)
                win_rate = (win_count / total_trades * 100) if total_trades > 0 else 0
                total_pnl = sum(t.pnl_percent for t in result.trades)
                avg_pnl = total_pnl / total_trades if total_trades > 0 else 0
                best_trade = max(t.pnl_percent for t in result.trades) if result.trades else 0
                worst_trade = min(t.pnl_percent for t in result.trades) if result.trades else 0

                # Cumulative P/L (compounded)
                cumulative = 1.0
                for t in result.trades:
                    cumulative *= (1 + t.pnl_percent / 100)
                cumulative_pnl = (cumulative - 1) * 100

                pnl_color = "#22c55e" if cumulative_pnl > 0 else "#ef4444"
                wr_color = "#22c55e" if win_rate >= 60 else "#ef4444" if win_rate < 40 else "#f59e0b"

                st.markdown(
                    f'<div style="display:grid; grid-template-columns:repeat(6, 1fr); gap:10px; margin:12px 0;">'
                    f'<div style="background:#111; border:1px solid #1a1a1a; border-radius:10px; padding:12px; text-align:center;">'
                    f'<div style="font-size:10px; color:#6b7280; text-transform:uppercase;">Total P/L</div>'
                    f'<div style="font-size:20px; font-weight:800; color:{pnl_color};">{cumulative_pnl:+.1f}%</div>'
                    f'</div>'
                    f'<div style="background:#111; border:1px solid #1a1a1a; border-radius:10px; padding:12px; text-align:center;">'
                    f'<div style="font-size:10px; color:#6b7280; text-transform:uppercase;">Win Rate</div>'
                    f'<div style="font-size:20px; font-weight:800; color:{wr_color};">{win_rate:.0f}%</div>'
                    f'</div>'
                    f'<div style="background:#111; border:1px solid #1a1a1a; border-radius:10px; padding:12px; text-align:center;">'
                    f'<div style="font-size:10px; color:#6b7280; text-transform:uppercase;">Trades</div>'
                    f'<div style="font-size:20px; font-weight:800; color:#e5e5e5;">{total_trades}</div>'
                    f'</div>'
                    f'<div style="background:#111; border:1px solid #1a1a1a; border-radius:10px; padding:12px; text-align:center;">'
                    f'<div style="font-size:10px; color:#6b7280; text-transform:uppercase;">Avg P/L</div>'
                    f'<div style="font-size:20px; font-weight:800; color:{"#22c55e" if avg_pnl > 0 else "#ef4444"};">{avg_pnl:+.1f}%</div>'
                    f'</div>'
                    f'<div style="background:#111; border:1px solid #1a1a1a; border-radius:10px; padding:12px; text-align:center;">'
                    f'<div style="font-size:10px; color:#6b7280; text-transform:uppercase;">Best</div>'
                    f'<div style="font-size:20px; font-weight:800; color:#22c55e;">{best_trade:+.1f}%</div>'
                    f'</div>'
                    f'<div style="background:#111; border:1px solid #1a1a1a; border-radius:10px; padding:12px; text-align:center;">'
                    f'<div style="font-size:10px; color:#6b7280; text-transform:uppercase;">Worst</div>'
                    f'<div style="font-size:20px; font-weight:800; color:#ef4444;">{worst_trade:+.1f}%</div>'
                    f'</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

                # Verdict
                if cumulative_pnl > 10:
                    verdict_text = f"This signal made money. {cumulative_pnl:+.1f}% total return across {total_trades} trades with {win_rate:.0f}% win rate. Worth trading."
                    verdict_color = "#22c55e"
                elif cumulative_pnl > 0:
                    verdict_text = f"Marginally profitable. {cumulative_pnl:+.1f}% total but slim edge. Consider combining with other confirming signals."
                    verdict_color = "#f59e0b"
                else:
                    verdict_text = f"This signal lost money. {cumulative_pnl:+.1f}% total. Do NOT trade this signal alone on {symbol}. Consider the opposite direction or different hold period."
                    verdict_color = "#ef4444"

                st.markdown(
                    f'<div style="background:#0d0d0d; border:1px solid {verdict_color}44; border-radius:10px; padding:14px; margin-bottom:12px;">'
                    f'<div style="font-size:13px; color:{verdict_color}; font-weight:700;">Bottom Line</div>'
                    f'<div style="font-size:13px; color:#d1d5db; margin-top:4px; line-height:1.5;">{verdict_text}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

                # Trade log
                trades_df = pd.DataFrame([{
                    "Entry": t.entry_date, "Exit": t.exit_date,
                    "Entry $": f"${t.entry_price:.2f}", "Exit $": f"${t.exit_price:.2f}",
                    "P/L %": f"{t.pnl_percent:+.1f}%", "Result": "Win" if t.outcome == "win" else "Loss",
                    "Days": t.hold_days,
                } for t in result.trades])
                st.dataframe(trades_df, use_container_width=True, hide_index=True)
            else:
                st.info(f"No trades triggered for {signal_name} in the historical data.")

    # ── Tab: AI Analyst ─────────────────────────────────
    with tab_ai:
        ai_symbol = selected_stocks[0]
        st.markdown(
            f'<div style="display:flex; align-items:center; gap:10px; margin-bottom:16px;">'
            f'<span style="font-size:22px;">🤖</span>'
            f'<div>'
            f'<div style="font-size:16px; font-weight:800; color:#e5e5e5;">AI Analyst — {ai_symbol}</div>'
            f'<div style="font-size:12px; color:#6b7280;">Claude analyzes all 12 signals together and makes trading decisions ({hold_label} hold)</div>'
            f'</div></div>',
            unsafe_allow_html=True,
        )

        if st.button("Run AI Backtest", type="primary", key="run_ai_bt", use_container_width=True):
            ai_hist = gw.get_historical(ai_symbol, period_days=max(365, hold_days * 5))
            if ai_hist is None or ai_hist.empty or len(ai_hist) < 60:
                st.warning("Not enough historical data.")
            else:
                from src.analysis import technical as tech_mod
                from src.analysis.opportunity import compute_opportunity

                closes = ai_hist["close"].astype(float)
                dates = ai_hist["date"].tolist()

                # Sample monthly — one AI decision per month
                import subprocess
                sample_indices = list(range(30, len(ai_hist) - hold_days, 21))  # Every ~month

                ai_trades = []
                ai_decisions = []
                progress = st.progress(0, text="AI analyzing signals...")

                for step, idx in enumerate(sample_indices):
                    progress.progress((step + 1) / len(sample_indices), text=f"AI analyzing {step + 1}/{len(sample_indices)} time points...")

                    # Compute signals at this point in time
                    hist_slice = ai_hist.iloc[:idx + 1].copy()
                    try:
                        tech = tech_mod.analyze(ai_symbol, hist_slice)
                    except Exception:
                        tech = None

                    price = float(closes.iloc[idx])
                    date = dates[idx]

                    # Build signal summary for Claude
                    signal_summary = f"Stock: {ai_symbol}, Date: {date}, Price: ${price:.2f}\n"
                    if tech:
                        signal_summary += f"RSI: {float(tech.rsi_14):.0f}, " if tech.rsi_14 else ""
                        signal_summary += f"MACD: {'positive' if tech.macd_histogram and tech.macd_histogram > 0 else 'negative'}, "
                        signal_summary += f"Trend: {tech.trend}, "
                        if tech.sma_50:
                            signal_summary += f"Price vs SMA50: {'above' if price > float(tech.sma_50) else 'below'}, "
                        if tech.support:
                            signal_summary += f"Support: ${float(tech.support):.2f}, "
                        if tech.resistance:
                            signal_summary += f"Resistance: ${float(tech.resistance):.2f}, "

                    # 20-day price change for context
                    if idx >= 20:
                        price_20d_ago = float(closes.iloc[idx - 20])
                        recent_change = ((price - price_20d_ago) / price_20d_ago) * 100
                        signal_summary += f"\n20-day price change: {recent_change:+.1f}%"

                    # Volume trend
                    if idx >= 20:
                        recent_vol = float(ai_hist["volume"].iloc[idx])
                        avg_vol = float(ai_hist["volume"].iloc[idx - 20:idx].mean())
                        if avg_vol > 0:
                            vol_ratio = recent_vol / avg_vol
                            signal_summary += f"\nVolume: {vol_ratio:.1f}x average"

                    try:
                        prompt = f"""You are a professional stock trader. Based on these signals, make a trading decision.

{signal_summary}

Respond in EXACTLY this format (no other text):
DECISION: BUY or SELL or HOLD
REASON: One sentence explaining why."""

                        env = dict(__import__("os").environ)
                        env.pop("CLAUDECODE", None)

                        proc = subprocess.run(
                            ["claude", "-p", prompt, "--model", "haiku"],
                            capture_output=True, text=True, timeout=30, env=env,
                        )
                        ai_text = proc.stdout.strip()

                        # Parse decision
                        decision = "HOLD"
                        reason = ""
                        for line in ai_text.split("\n"):
                            if line.startswith("DECISION:"):
                                d = line.replace("DECISION:", "").strip().upper()
                                if "BUY" in d:
                                    decision = "BUY"
                                elif "SELL" in d:
                                    decision = "SELL"
                                else:
                                    decision = "HOLD"
                            elif line.startswith("REASON:"):
                                reason = line.replace("REASON:", "").strip()

                    except Exception as e:
                        decision = "HOLD"
                        reason = f"AI unavailable: {str(e)[:50]}"

                    # Calculate outcome
                    exit_idx = min(idx + hold_days, len(closes) - 1)
                    exit_price = float(closes.iloc[exit_idx])

                    if decision == "BUY":
                        pnl_pct = ((exit_price - price) / price) * 100
                    elif decision == "SELL":
                        pnl_pct = ((price - exit_price) / price) * 100
                    else:
                        pnl_pct = 0  # Hold = no trade

                    ai_decisions.append({
                        "date": date,
                        "price": price,
                        "decision": decision,
                        "reason": reason,
                        "exit_date": dates[exit_idx],
                        "exit_price": exit_price,
                        "pnl_pct": round(pnl_pct, 2),
                        "outcome": "win" if pnl_pct > 0 else "loss" if pnl_pct < 0 else "skip",
                    })

                progress.empty()

                # Filter to actual trades (not HOLDs)
                actual_trades = [d for d in ai_decisions if d["decision"] != "HOLD"]
                wins = [d for d in actual_trades if d["outcome"] == "win"]
                losses = [d for d in actual_trades if d["outcome"] == "loss"]
                holds = [d for d in ai_decisions if d["decision"] == "HOLD"]

                # Stats
                total_ai = len(actual_trades)
                win_count = len(wins)
                win_rate = (win_count / total_ai * 100) if total_ai > 0 else 0

                cumulative = 1.0
                for t in actual_trades:
                    cumulative *= (1 + t["pnl_pct"] / 100)
                total_pnl = (cumulative - 1) * 100
                avg_pnl = sum(t["pnl_pct"] for t in actual_trades) / total_ai if total_ai > 0 else 0

                pnl_color = "#22c55e" if total_pnl > 0 else "#ef4444"
                wr_color = "#22c55e" if win_rate >= 60 else "#ef4444" if win_rate < 40 else "#f59e0b"

                # Chart with AI decision markers
                fig = go.Figure()
                fig.add_trace(go.Candlestick(x=ai_hist["date"], open=ai_hist["open"], high=ai_hist["high"],
                                              low=ai_hist["low"], close=ai_hist["close"], name="Price"))

                buy_decisions = [d for d in ai_decisions if d["decision"] == "BUY"]
                sell_decisions = [d for d in ai_decisions if d["decision"] == "SELL"]
                hold_decisions = [d for d in ai_decisions if d["decision"] == "HOLD"]

                if buy_decisions:
                    fig.add_trace(go.Scatter(
                        x=[d["date"] for d in buy_decisions],
                        y=[d["price"] for d in buy_decisions],
                        mode="markers", name="AI: BUY",
                        marker=dict(color="#22c55e", size=14, symbol="triangle-up", line=dict(color="#fff", width=1)),
                        hovertemplate="<b>AI: BUY</b><br>$%{y:.2f}<br>%{customdata}<extra></extra>",
                        customdata=[f"{d['reason'][:60]}... → {d['pnl_pct']:+.1f}%" for d in buy_decisions],
                    ))
                if sell_decisions:
                    fig.add_trace(go.Scatter(
                        x=[d["date"] for d in sell_decisions],
                        y=[d["price"] for d in sell_decisions],
                        mode="markers", name="AI: SELL",
                        marker=dict(color="#ef4444", size=14, symbol="triangle-down", line=dict(color="#fff", width=1)),
                        hovertemplate="<b>AI: SELL</b><br>$%{y:.2f}<br>%{customdata}<extra></extra>",
                        customdata=[f"{d['reason'][:60]}... → {d['pnl_pct']:+.1f}%" for d in sell_decisions],
                    ))
                if hold_decisions:
                    fig.add_trace(go.Scatter(
                        x=[d["date"] for d in hold_decisions],
                        y=[d["price"] for d in hold_decisions],
                        mode="markers", name="AI: HOLD",
                        marker=dict(color="#f59e0b", size=10, symbol="diamond", line=dict(color="#fff", width=1)),
                        hovertemplate="<b>AI: HOLD</b><br>$%{y:.2f}<br>%{customdata}<extra></extra>",
                        customdata=[d["reason"][:60] for d in hold_decisions],
                    ))

                fig.update_layout(template="plotly_dark", height=450, plot_bgcolor="#0a0a0a", paper_bgcolor="#0a0a0a",
                                  xaxis_rangeslider_visible=False,
                                  title=f"AI Analyst Decisions — {ai_symbol} ({hold_label} hold)")
                st.plotly_chart(fig, use_container_width=True)

                # KPI cards
                st.markdown(
                    f'<div style="display:grid; grid-template-columns:repeat(5, 1fr); gap:10px; margin:12px 0;">'
                    f'<div style="background:#111; border:1px solid #1a1a1a; border-radius:10px; padding:12px; text-align:center;">'
                    f'<div style="font-size:10px; color:#6b7280; text-transform:uppercase;">Total P/L</div>'
                    f'<div style="font-size:22px; font-weight:800; color:{pnl_color};">{total_pnl:+.1f}%</div></div>'
                    f'<div style="background:#111; border:1px solid #1a1a1a; border-radius:10px; padding:12px; text-align:center;">'
                    f'<div style="font-size:10px; color:#6b7280; text-transform:uppercase;">Win Rate</div>'
                    f'<div style="font-size:22px; font-weight:800; color:{wr_color};">{win_rate:.0f}%</div></div>'
                    f'<div style="background:#111; border:1px solid #1a1a1a; border-radius:10px; padding:12px; text-align:center;">'
                    f'<div style="font-size:10px; color:#6b7280; text-transform:uppercase;">Trades</div>'
                    f'<div style="font-size:22px; font-weight:800; color:#e5e5e5;">{total_ai}</div>'
                    f'<div style="font-size:10px; color:#6b7280;">{len(holds)} skipped</div></div>'
                    f'<div style="background:#111; border:1px solid #1a1a1a; border-radius:10px; padding:12px; text-align:center;">'
                    f'<div style="font-size:10px; color:#6b7280; text-transform:uppercase;">Avg P/L</div>'
                    f'<div style="font-size:22px; font-weight:800; color:{"#22c55e" if avg_pnl > 0 else "#ef4444"};">{avg_pnl:+.1f}%</div></div>'
                    f'<div style="background:#111; border:1px solid #1a1a1a; border-radius:10px; padding:12px; text-align:center;">'
                    f'<div style="font-size:10px; color:#6b7280; text-transform:uppercase;">Decisions</div>'
                    f'<div style="font-size:22px; font-weight:800; color:#e5e5e5;">{len(ai_decisions)}</div></div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

                # Bottom line
                if total_pnl > 10:
                    verdict_text = f"AI Analyst made money. {total_pnl:+.1f}% total return with {win_rate:.0f}% win rate. The AI skipped {len(holds)} uncertain moments — knowing when NOT to trade is as important as knowing when to trade."
                    verdict_color = "#22c55e"
                elif total_pnl > 0:
                    verdict_text = f"AI Analyst was marginally profitable. {total_pnl:+.1f}% total. The AI was cautious, skipping {len(holds)} uncertain signals. Consider combining with your own judgment."
                    verdict_color = "#f59e0b"
                else:
                    verdict_text = f"AI Analyst lost money on this stock. {total_pnl:+.1f}% total. Even AI can't predict every market move. Consider different hold periods or combining with fundamental analysis."
                    verdict_color = "#ef4444"

                st.markdown(
                    f'<div style="background:#0d0d0d; border:1px solid {verdict_color}44; border-radius:10px; padding:14px; margin-bottom:16px;">'
                    f'<div style="font-size:13px; color:{verdict_color}; font-weight:700;">AI Bottom Line</div>'
                    f'<div style="font-size:13px; color:#d1d5db; margin-top:4px; line-height:1.5;">{verdict_text}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

                # AI Decision Log
                st.markdown("### AI Decision Log")
                for d in ai_decisions:
                    dec_color = "#22c55e" if d["decision"] == "BUY" else "#ef4444" if d["decision"] == "SELL" else "#f59e0b"
                    outcome_icon = "✅" if d["outcome"] == "win" else "❌" if d["outcome"] == "loss" else "⏸"
                    pnl_display = f'{d["pnl_pct"]:+.1f}%' if d["decision"] != "HOLD" else "—"
                    pnl_c = "#22c55e" if d["pnl_pct"] > 0 else "#ef4444" if d["pnl_pct"] < 0 else "#6b7280"

                    st.markdown(
                        f'<div style="background:#111; border:1px solid #1a1a1a; border-radius:8px; padding:12px; margin-bottom:6px; display:flex; justify-content:space-between; align-items:center;">'
                        f'<div style="flex:1;">'
                        f'<span style="color:#6b7280; font-size:12px;">{d["date"]}</span>'
                        f'<span style="color:{dec_color}; font-weight:800; font-size:14px; margin-left:12px;">{d["decision"]}</span>'
                        f'<span style="color:#6b7280; font-size:12px; margin-left:8px;">@ ${d["price"]:.2f}</span>'
                        f'</div>'
                        f'<div style="flex:2; font-size:12px; color:#9ca3af; padding:0 12px;">{d["reason"][:80]}</div>'
                        f'<div style="text-align:right; min-width:80px;">'
                        f'<span style="font-size:14px;">{outcome_icon}</span>'
                        f'<span style="color:{pnl_c}; font-weight:700; font-size:13px; margin-left:6px;">{pnl_display}</span>'
                        f'</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

        else:
            st.markdown(
                '<div style="background:#111; border:1px solid #1a1a1a; border-radius:12px; padding:40px; text-align:center;">'
                '<div style="font-size:32px; margin-bottom:12px;">🤖</div>'
                '<div style="font-size:16px; font-weight:700; color:#e5e5e5;">AI-Powered Signal Analysis</div>'
                '<div style="font-size:13px; color:#6b7280; margin-top:8px; max-width:500px; margin-left:auto; margin-right:auto; line-height:1.6;">'
                'Claude will analyze all technical indicators at monthly intervals over the past year, '
                'make BUY/SELL/HOLD decisions with reasoning, and show you the results on a candlestick chart. '
                'Unlike fixed-rule signals, AI can weigh conflicting indicators and decide when to sit out.'
                '</div>'
                '</div>',
                unsafe_allow_html=True,
            )

    # ── Tab 3: Multi-Stock Compare ────────────────────────
    with tab_multi:
        if len(selected_stocks) < 2:
            st.info("Select 2+ stocks in the dropdown above to compare backtests across stocks.")
        else:
            st.markdown(
                f'<div style="font-size:14px; color:#e5e5e5; margin-bottom:12px;">Comparing <b>{len(selected_stocks)} stocks</b> across all signals ({hold_label} hold)</div>',
                unsafe_allow_html=True,
            )

            compare_signal = st.selectbox("Compare signal", list(SIGNALS.keys()),
                                           format_func=lambda s: f"{s.replace('_', ' ').title()} — {SIGNALS[s]['description']}",
                                           key="bt_compare_sig")

            # Run backtest for each stock
            compare_results = {}
            with st.spinner(f"Backtesting {len(selected_stocks)} stocks..."):
                for sym in selected_stocks:
                    try:
                        h = gw.get_historical(sym, period_days=max(365, hold_days * 5))
                        if h is not None and not h.empty and len(h) >= 60:
                            r = backtest_signal(sym, h, compare_signal, hold_days)
                            if r and r.total_trades > 0:
                                compare_results[sym] = r
                    except Exception:
                        continue

            if compare_results:
                # Comparison table
                rows = []
                grade_colors = {"A+": "#22c55e", "A": "#22c55e", "B+": "#86efac", "B": "#f59e0b", "C": "#9ca3af", "D": "#ef4444"}
                for sym, r in sorted(compare_results.items(), key=lambda x: x[1].win_rate, reverse=True):
                    wr_color = "#22c55e" if r.win_rate >= 0.65 else "#ef4444" if r.win_rate < 0.45 else "#f59e0b"
                    ret_color = "#22c55e" if r.avg_return > 0 else "#ef4444"
                    gc = grade_colors.get(r.grade, "#6b7280")
                    rows.append(
                        f'<tr>'
                        f'<td style="font-weight:700; color:#e5e5e5;">{sym}</td>'
                        f'<td style="color:{wr_color}; font-weight:700;">{r.win_rate*100:.0f}%</td>'
                        f'<td style="color:{ret_color};">{r.avg_return:+.1f}%</td>'
                        f'<td style="color:#e5e5e5;">{r.total_trades}</td>'
                        f'<td style="color:#22c55e;">{r.max_gain:+.1f}%</td>'
                        f'<td style="color:#ef4444;">{r.max_loss:+.1f}%</td>'
                        f'<td style="color:{gc}; font-weight:700;">{r.grade}</td>'
                        f'</tr>'
                    )

                st.markdown(
                    f'<div style="background:#111; border-radius:12px; padding:16px; overflow-x:auto;">'
                    f'<table style="width:100%; border-collapse:collapse; font-size:13px;">'
                    f'<thead><tr style="border-bottom:1px solid #333;">'
                    f'<th style="text-align:left; padding:8px; color:#6b7280;">Stock</th>'
                    f'<th style="text-align:left; padding:8px; color:#6b7280;">Win Rate</th>'
                    f'<th style="text-align:left; padding:8px; color:#6b7280;">Avg Return</th>'
                    f'<th style="text-align:left; padding:8px; color:#6b7280;">Trades</th>'
                    f'<th style="text-align:left; padding:8px; color:#6b7280;">Best</th>'
                    f'<th style="text-align:left; padding:8px; color:#6b7280;">Worst</th>'
                    f'<th style="text-align:left; padding:8px; color:#6b7280;">Grade</th>'
                    f'</tr></thead>'
                    f'<tbody>{"".join(rows)}</tbody>'
                    f'</table></div>',
                    unsafe_allow_html=True,
                )

                # Best stock for this signal
                best_sym = max(compare_results.items(), key=lambda x: x[1].win_rate * x[1].avg_return)
                st.markdown(
                    f'<div style="background:#0d0d0d; border:1px solid #22c55e44; border-radius:10px; padding:14px; margin-top:12px;">'
                    f'<div style="font-size:13px; color:#22c55e; font-weight:700;">Best Stock for {compare_signal.replace("_", " ").title()}: {best_sym[0]}</div>'
                    f'<div style="font-size:12px; color:#d1d5db; margin-top:4px;">'
                    f'{best_sym[1].win_rate*100:.0f}% win rate, {best_sym[1].avg_return:+.1f}% avg return over {hold_label}.</div></div>',
                    unsafe_allow_html=True,
                )
            else:
                st.warning("No backtest results. Stocks may not have enough historical data.")

    # ── Tab 4: Portfolio Simulation ───────────────────────
    with tab_portfolio:
        available = list(set(wl_syms + selected_stocks))
        sim_stocks = st.multiselect("Stocks for simulation", available, default=selected_stocks, key="sim_stocks")
        strategy = st.selectbox("Strategy signal", list(SIGNALS.keys()), key="port_strategy",
                                 format_func=lambda s: f"{s.replace('_', ' ').title()}")

        c1, c2 = st.columns(2)
        with c1:
            capital = st.number_input("Starting capital ($)", value=100000, step=10000, key="sim_capital")
        with c2:
            st.markdown(f"**Hold period:** {hold_label} (set in filter bar above)")

        if sim_stocks and st.button("Run Simulation", type="primary", key="run_sim"):
            from src.analysis.portfolio_sim import simulate_portfolio
            import yfinance as yf

            with st.spinner("Simulating portfolio..."):
                hist_data = {}
                for s in sim_stocks:
                    h = gw.get_historical(s, period_days=max(365, hold_days * 5))
                    if h is not None and not h.empty:
                        hist_data[s] = h

                spy = yf.download("SPY", period="2y", progress=False, auto_adjust=True)
                if hasattr(spy.columns, 'levels') and spy.columns.nlevels > 1:
                    spy.columns = spy.columns.get_level_values(0)
                spy = spy.reset_index().rename(columns={"Date": "date", "Open": "open", "High": "high",
                                                          "Low": "low", "Close": "close", "Volume": "volume"})
                spy["date"] = spy["date"].dt.strftime("%Y-%m-%d")

                result = simulate_portfolio(list(hist_data.keys()), hist_data, spy, strategy, capital)

            if result and result.equity_curve:
                dates = [s.date for s in result.equity_curve]
                values = [s.cumulative_return * 100 for s in result.equity_curve]
                bench = [s.benchmark_return * 100 for s in result.equity_curve]

                fig = go.Figure()
                fig.add_trace(go.Scatter(x=dates, y=values, name="Portfolio",
                                          line=dict(color="#22c55e", width=2),
                                          fill="tozeroy", fillcolor="rgba(34,197,94,0.06)"))
                fig.add_trace(go.Scatter(x=dates, y=bench, name="S&P 500",
                                          line=dict(color="#6b7280", width=1, dash="dash")))
                fig.update_layout(template="plotly_dark", height=400, plot_bgcolor="#0a0a0a", paper_bgcolor="#0a0a0a",
                                  yaxis_title="Return %", hovermode="x unified",
                                  legend=dict(orientation="h", y=1.1))
                st.plotly_chart(fig, use_container_width=True)

                # Stats
                cols = st.columns(5)
                cols[0].metric("Total Return", f"{result.total_return*100:+.1f}%")
                cols[1].metric("Alpha", f"{result.alpha*100:+.1f}%")
                cols[2].metric("Sharpe", f"{result.sharpe_ratio:.2f}")
                cols[3].metric("Max Drawdown", f"{result.max_drawdown*100:.1f}%")
                cols[4].metric("Win Rate", f"{result.win_rate*100:.0f}%")

                alpha_color = "#22c55e" if result.alpha > 0 else "#ef4444"
                st.markdown(
                    f'<div style="background:#0d0d0d; border:1px solid {alpha_color}44; border-radius:10px; padding:14px; margin-top:8px;">'
                    f'<div style="font-size:14px; color:#e5e5e5;">'
                    f'${capital:,.0f} → <b style="color:{alpha_color};">${result.final_value:,.0f}</b> '
                    f'({result.total_return*100:+.1f}%) using {strategy.replace("_", " ")} strategy over {hold_label}. '
                    f'{"Beating" if result.alpha > 0 else "Underperforming"} S&P 500 by <b style="color:{alpha_color};">{abs(result.alpha)*100:.1f}%</b>.'
                    f'</div></div>',
                    unsafe_allow_html=True,
                )

    _render_step_cta("Track My Real Trades", 5)


# ═══════════════════════════════════════════════════════════════
# STEP 5: MY PORTFOLIO
# ═══════════════════════════════════════════════════════════════

def page_portfolio():
    st.title("My Portfolio")
    st.caption("Log trades, track P/L, and measure which signals make you money")

    from src.journal import log_trade, close_trade, get_open_trades, get_trade_history, get_performance_stats

    tab_overview, tab_log, tab_history = st.tabs(["Overview", "Log Trade", "History"])

    with tab_overview:
        stats = get_performance_stats()

        # KPI cards
        pnl_color = "#22c55e" if stats.total_pnl > 0 else "#ef4444" if stats.total_pnl < 0 else "#6b7280"
        wr_color = "#22c55e" if stats.win_rate >= 0.6 else "#ef4444" if stats.win_rate < 0.4 else "#f59e0b"
        exp_color = "#22c55e" if stats.expectancy > 0 else "#ef4444" if stats.expectancy < 0 else "#6b7280"

        st.markdown(
            f'<div style="display:grid; grid-template-columns:repeat(4, 1fr); gap:12px; margin-bottom:20px;">'
            # Total P/L
            f'<div style="background:#111; border:1px solid #1a1a1a; border-radius:12px; padding:16px; text-align:center;">'
            f'<div style="font-size:10px; color:#6b7280; text-transform:uppercase; letter-spacing:0.8px;">Total P/L</div>'
            f'<div style="font-size:24px; font-weight:800; color:{pnl_color}; margin:6px 0;">${stats.total_pnl:+,.2f}</div>'
            f'</div>'
            # Win Rate
            f'<div style="background:#111; border:1px solid #1a1a1a; border-radius:12px; padding:16px; text-align:center;">'
            f'<div style="font-size:10px; color:#6b7280; text-transform:uppercase; letter-spacing:0.8px;">Win Rate</div>'
            f'<div style="font-size:24px; font-weight:800; color:{wr_color}; margin:6px 0;">{stats.win_rate*100:.0f}%</div>'
            f'<div style="font-size:11px; color:#6b7280;">{stats.wins}W / {stats.losses}L</div>'
            f'</div>'
            # Trades
            f'<div style="background:#111; border:1px solid #1a1a1a; border-radius:12px; padding:16px; text-align:center;">'
            f'<div style="font-size:10px; color:#6b7280; text-transform:uppercase; letter-spacing:0.8px;">Total Trades</div>'
            f'<div style="font-size:24px; font-weight:800; color:#e5e5e5; margin:6px 0;">{stats.closed_trades}</div>'
            f'<div style="font-size:11px; color:#6b7280;">{stats.open_trades if hasattr(stats, "open_trades") else 0} open</div>'
            f'</div>'
            # Expectancy
            f'<div style="background:#111; border:1px solid #1a1a1a; border-radius:12px; padding:16px; text-align:center;">'
            f'<div style="font-size:10px; color:#6b7280; text-transform:uppercase; letter-spacing:0.8px;">Expectancy</div>'
            f'<div style="font-size:24px; font-weight:800; color:{exp_color}; margin:6px 0;">${stats.expectancy:+,.2f}</div>'
            f'<div style="font-size:11px; color:#6b7280;">Avg $ per trade</div>'
            f'</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        # Equity curve
        eq_fig = _build_equity_curve_from_journal()
        if eq_fig:
            st.plotly_chart(eq_fig, use_container_width=True)

        # ── Portfolio Risk View ─────────────────────────
        open_trades = get_open_trades()
        if open_trades and len(open_trades) >= 2:
            _section_header("Portfolio Risk")

            # Get sector for each position
            sector_exposure: dict[str, float] = {}
            total_invested = 0
            for t in open_trades:
                value = t.entry_price * t.shares
                total_invested += value
                # Look up sector
                sector = "Unknown"
                if t.symbol in STOCK_DB:
                    sector = STOCK_DB[t.symbol][1]
                else:
                    try:
                        from src.utils.db import cache_get
                        fund = cache_get(f"market:fundamentals:{t.symbol}")
                        if fund:
                            sector = fund.get("sector", "Unknown")
                    except Exception:
                        pass
                sector_exposure[sector] = sector_exposure.get(sector, 0) + value

            if total_invested > 0 and sector_exposure:
                # Sector pie chart
                sectors = list(sector_exposure.keys())
                values = list(sector_exposure.values())
                pcts = [v / total_invested * 100 for v in values]
                colors = ["#3b82f6", "#22c55e", "#f59e0b", "#ef4444", "#a855f7", "#06b6d4", "#ec4899", "#14b8a6"]

                c1, c2 = st.columns([1, 1])
                with c1:
                    fig = go.Figure(go.Pie(
                        labels=sectors, values=values,
                        hole=0.55, textinfo="label+percent",
                        marker=dict(colors=colors[:len(sectors)]),
                        textfont=dict(size=11, color="#e5e5e5"),
                    ))
                    fig.update_layout(
                        template="plotly_dark", height=250,
                        margin=dict(l=0, r=0, t=10, b=10),
                        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                        showlegend=False,
                    )
                    st.plotly_chart(fig, use_container_width=True)

                with c2:
                    # Concentration warnings
                    warnings = []
                    for sector, pct in zip(sectors, pcts):
                        if pct > 50:
                            warnings.append(f'<div style="color:#ef4444; font-size:12px; margin:4px 0;">⚠ {sector}: {pct:.0f}% — dangerously concentrated. One bad sector day could wipe gains.</div>')
                        elif pct > 30:
                            warnings.append(f'<div style="color:#f59e0b; font-size:12px; margin:4px 0;">⚠ {sector}: {pct:.0f}% — consider diversifying.</div>')

                    if len(sectors) == 1:
                        warnings.append('<div style="color:#ef4444; font-size:12px; margin:4px 0;">⚠ All positions in one sector — zero diversification.</div>')

                    if warnings:
                        st.markdown(
                            '<div style="background:#0d0d0d; border:1px solid #ef444444; border-radius:10px; padding:14px;">'
                            '<div style="font-size:11px; color:#ef4444; font-weight:700; text-transform:uppercase; margin-bottom:8px;">Concentration Risk</div>'
                            + "".join(warnings) +
                            '</div>',
                            unsafe_allow_html=True,
                        )
                    else:
                        st.markdown(
                            '<div style="background:#0d0d0d; border:1px solid #22c55e44; border-radius:10px; padding:14px;">'
                            '<div style="font-size:12px; color:#22c55e;">Well diversified — no sector exceeds 30%.</div>'
                            '</div>',
                            unsafe_allow_html=True,
                        )

        # ── Daily P/L Heatmap ──────────────────────────
        closed_trades_all = get_trade_history()
        daily_pnl: dict[str, float] = {}
        for t in closed_trades_all:
            if t.pnl is not None and t.exit_date:
                d = t.exit_date[:10]
                daily_pnl[d] = daily_pnl.get(d, 0) + t.pnl

        if daily_pnl and len(daily_pnl) >= 3:
            _section_header("Daily P/L Calendar")

            from datetime import datetime as dt_mod, timedelta
            # Build calendar for last 90 days
            today = dt_mod.utcnow()
            calendar_html = '<div style="display:flex; flex-wrap:wrap; gap:2px;">'
            for day_offset in range(89, -1, -1):
                d = (today - timedelta(days=day_offset)).strftime("%Y-%m-%d")
                pnl = daily_pnl.get(d, 0)
                if pnl > 0:
                    bg = f"rgba(34,197,94,{min(abs(pnl) / 500, 1) * 0.8 + 0.2})"
                elif pnl < 0:
                    bg = f"rgba(239,68,68,{min(abs(pnl) / 500, 1) * 0.8 + 0.2})"
                else:
                    bg = "#1a1a1a"
                day_num = d[-2:]
                tooltip = f"${pnl:+,.0f}" if pnl != 0 else "No trades"
                calendar_html += (
                    f'<div title="{d}: {tooltip}" style="width:14px; height:14px; background:{bg}; border-radius:2px; cursor:default;"></div>'
                )
            calendar_html += '</div>'

            # Legend
            calendar_html += (
                '<div style="display:flex; gap:12px; margin-top:6px; font-size:10px; color:#6b7280;">'
                '<span>Less</span>'
                '<div style="display:flex; gap:2px;">'
                '<div style="width:12px; height:12px; background:#1a1a1a; border-radius:2px;"></div>'
                '<div style="width:12px; height:12px; background:rgba(34,197,94,0.3); border-radius:2px;"></div>'
                '<div style="width:12px; height:12px; background:rgba(34,197,94,0.6); border-radius:2px;"></div>'
                '<div style="width:12px; height:12px; background:rgba(34,197,94,1); border-radius:2px;"></div>'
                '</div>'
                '<span>More profit</span>'
                '<span style="margin-left:12px;">Loss:</span>'
                '<div style="display:flex; gap:2px;">'
                '<div style="width:12px; height:12px; background:rgba(239,68,68,0.3); border-radius:2px;"></div>'
                '<div style="width:12px; height:12px; background:rgba(239,68,68,0.6); border-radius:2px;"></div>'
                '<div style="width:12px; height:12px; background:rgba(239,68,68,1); border-radius:2px;"></div>'
                '</div>'
                '</div>'
            )

            st.markdown(
                f'<div style="background:#111; border:1px solid #1a1a1a; border-radius:12px; padding:16px;">{calendar_html}</div>',
                unsafe_allow_html=True,
            )

            # Summary stats
            green_days = sum(1 for v in daily_pnl.values() if v > 0)
            red_days = sum(1 for v in daily_pnl.values() if v < 0)
            best_day = max(daily_pnl.values()) if daily_pnl else 0
            worst_day = min(daily_pnl.values()) if daily_pnl else 0
            st.markdown(
                f'<div style="display:flex; gap:16px; margin-top:8px; font-size:12px;">'
                f'<span style="color:#22c55e;">{green_days} green days</span>'
                f'<span style="color:#ef4444;">{red_days} red days</span>'
                f'<span style="color:#22c55e;">Best: ${best_day:+,.0f}</span>'
                f'<span style="color:#ef4444;">Worst: ${worst_day:+,.0f}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

        # Report accuracy
        if stats.report_accuracy:
            st.markdown(
                '<div style="display:flex; align-items:center; gap:8px; margin:20px 0 12px;">'
                '<div style="height:2px; flex:1; background:linear-gradient(to right, #333, transparent);"></div>'
                '<span style="font-size:13px; font-weight:700; color:#6b7280; text-transform:uppercase; letter-spacing:1px;">Report Accuracy</span>'
                '<div style="height:2px; flex:1; background:linear-gradient(to left, #333, transparent);"></div>'
                '</div>',
                unsafe_allow_html=True,
            )
            st.caption("How accurate are the app's verdicts when you trade on them?")

            acc_rows = ""
            for verdict, data in stats.report_accuracy.items():
                wr = data["win_rate"]
                wr_c = "#22c55e" if wr >= 0.65 else "#ef4444" if wr < 0.45 else "#f59e0b"
                acc_rows += (
                    f'<tr>'
                    f'<td style="padding:8px; font-weight:700; color:#e5e5e5;">{verdict}</td>'
                    f'<td style="padding:8px; color:#e5e5e5;">{data["trades"]}</td>'
                    f'<td style="padding:8px; color:#22c55e;">{data["wins"]}</td>'
                    f'<td style="padding:8px; color:{wr_c}; font-weight:700;">{wr*100:.0f}%</td>'
                    f'</tr>'
                )

            st.markdown(
                f'<div style="background:#111; border:1px solid #1a1a1a; border-radius:12px; padding:16px; overflow-x:auto;">'
                f'<table style="width:100%; border-collapse:collapse; font-size:13px;">'
                f'<thead><tr style="border-bottom:1px solid #222;">'
                f'<th style="text-align:left; padding:8px; color:#6b7280;">Verdict</th>'
                f'<th style="text-align:left; padding:8px; color:#6b7280;">Trades</th>'
                f'<th style="text-align:left; padding:8px; color:#6b7280;">Wins</th>'
                f'<th style="text-align:left; padding:8px; color:#6b7280;">Win Rate</th>'
                f'</tr></thead>'
                f'<tbody>{acc_rows}</tbody>'
                f'</table></div>',
                unsafe_allow_html=True,
            )

            best_verdict = max(stats.report_accuracy.items(), key=lambda x: x[1]["win_rate"])[0] if stats.report_accuracy else None
            if best_verdict:
                st.markdown(
                    f'<div style="background:#0d0d0d; border:1px solid #22c55e44; border-radius:10px; padding:14px; margin-top:12px;">'
                    f'<div style="font-size:13px; color:#22c55e; font-weight:700;">Your best results come from "{best_verdict}" verdicts.</div>'
                    f'<div style="font-size:12px; color:#9ca3af; margin-top:4px;">Consider focusing on these signals for higher win rates.</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

        # Open positions
        open_trades = get_open_trades()
        if open_trades:
            st.markdown(
                '<div style="display:flex; align-items:center; gap:8px; margin:20px 0 12px;">'
                '<div style="height:2px; flex:1; background:linear-gradient(to right, #333, transparent);"></div>'
                '<span style="font-size:13px; font-weight:700; color:#6b7280; text-transform:uppercase; letter-spacing:1px;">Open Positions</span>'
                '<div style="height:2px; flex:1; background:linear-gradient(to left, #333, transparent);"></div>'
                '</div>',
                unsafe_allow_html=True,
            )
            for t in open_trades:
                st.markdown(
                    f'<div style="background:#111; border:1px solid #1a1a1a; border-radius:10px; padding:14px; margin-bottom:8px; display:flex; justify-content:space-between; align-items:center;">'
                    f'<div>'
                    f'<span style="font-size:16px; font-weight:800; color:#e5e5e5;">{t.symbol}</span>'
                    f'<span style="font-size:12px; color:#6b7280; margin-left:8px;">{t.direction.upper()} | {t.shares} shares @ ${t.entry_price:.2f}</span>'
                    f'</div>'
                    f'<span style="font-size:12px; color:#6b7280;">{t.entry_date}</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                c1, c2 = st.columns([3, 1])
                with c1:
                    exit_price = st.number_input("Exit price", min_value=0.01, step=0.01, key=f"exit_{t.id}", label_visibility="collapsed", placeholder="Exit price")
                with c2:
                    if st.button("Close Position", key=f"close_{t.id}", use_container_width=True):
                        close_trade(t.id, exit_price)
                        st.rerun()

    with tab_log:
        st.markdown(
            '<div style="font-size:16px; font-weight:700; color:#e5e5e5; margin-bottom:12px;">Log New Trade</div>',
            unsafe_allow_html=True,
        )
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

            if st.form_submit_button("Log Trade", type="primary", use_container_width=True):
                if sym and entry_price > 0:
                    trade_id = log_trade(sym.upper(), direction, entry_price, shares, thesis, verdict)
                    st.success(f"Trade #{trade_id} logged for {sym.upper()}")
                    st.rerun()

    with tab_history:
        trades = get_trade_history()
        if trades:
            hist_rows = ""
            for t in trades:
                pnl_c = "#22c55e" if t.pnl and t.pnl > 0 else "#ef4444" if t.pnl and t.pnl < 0 else "#6b7280"
                hist_rows += (
                    f'<tr style="border-bottom:1px solid #1a1a1a;">'
                    f'<td style="padding:10px; font-weight:700; color:#e5e5e5;">{t.symbol}</td>'
                    f'<td style="padding:10px; color:#9ca3af;">{t.direction.upper()}</td>'
                    f'<td style="padding:10px; color:#e5e5e5;">${t.entry_price:.2f}</td>'
                    f'<td style="padding:10px; color:#e5e5e5;">{f"${t.exit_price:.2f}" if t.exit_price else "Open"}</td>'
                    f'<td style="padding:10px; color:#e5e5e5;">{t.shares}</td>'
                    f'<td style="padding:10px; color:{pnl_c}; font-weight:700;">{f"${t.pnl:+,.2f}" if t.pnl is not None else "—"}</td>'
                    f'<td style="padding:10px; color:{pnl_c};">{f"{t.pnl_percent:+.1f}%" if t.pnl_percent is not None else "—"}</td>'
                    f'<td style="padding:10px; color:#6b7280;">{t.report_verdict or "—"}</td>'
                    f'<td style="padding:10px; color:#6b7280;">{t.entry_date}</td>'
                    f'</tr>'
                )

            st.markdown(
                f'<div style="background:#111; border:1px solid #1a1a1a; border-radius:12px; padding:16px; overflow-x:auto;">'
                f'<table style="width:100%; border-collapse:collapse; font-size:13px;">'
                f'<thead><tr style="border-bottom:1px solid #333;">'
                f'<th style="text-align:left; padding:10px; color:#6b7280;">Symbol</th>'
                f'<th style="text-align:left; padding:10px; color:#6b7280;">Dir</th>'
                f'<th style="text-align:left; padding:10px; color:#6b7280;">Entry</th>'
                f'<th style="text-align:left; padding:10px; color:#6b7280;">Exit</th>'
                f'<th style="text-align:left; padding:10px; color:#6b7280;">Shares</th>'
                f'<th style="text-align:left; padding:10px; color:#6b7280;">P/L</th>'
                f'<th style="text-align:left; padding:10px; color:#6b7280;">P/L %</th>'
                f'<th style="text-align:left; padding:10px; color:#6b7280;">Verdict</th>'
                f'<th style="text-align:left; padding:10px; color:#6b7280;">Date</th>'
                f'</tr></thead>'
                f'<tbody>{hist_rows}</tbody>'
                f'</table></div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div style="background:#111; border:1px solid #1a1a1a; border-radius:12px; padding:40px; text-align:center;">'
                '<div style="font-size:32px; margin-bottom:12px;">📋</div>'
                '<div style="font-size:16px; font-weight:700; color:#e5e5e5;">No trades logged yet</div>'
                '<div style="font-size:13px; color:#6b7280; margin-top:4px;">Use the "Log Trade" tab to record your first trade.</div>'
                '</div>',
                unsafe_allow_html=True,
            )


# ═══════════════════════════════════════════════════════════════
# STEP 6: AI AGENT
# ═══════════════════════════════════════════════════════════════

def page_ai_agent():
    st.title("AI Agent")
    st.caption("Autonomous paper trading — Claude analyzes markets, picks stocks, and tracks P/L")

    from src.agent import TradingAgent, get_agent_config, get_agent_positions, get_agent_decisions, get_agent_equity, reset_agent, add_human_trade

    config = get_agent_config()

    # ── Controls ───────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        capital = st.number_input("Starting Capital ($)", value=int(config.get("starting_capital", 100000)), step=10000, key="agent_cap")
    with c2:
        risk = st.selectbox("Risk per Trade", ["1%", "2%", "3%", "5%"], index=1, key="agent_risk")
        risk_pct = float(risk.replace("%", "")) / 100
    with c3:
        max_pos = st.selectbox("Max Positions", [3, 5, 8, 10], index=1, key="agent_maxpos")
    with c4:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Reset Agent", use_container_width=True):
            reset_agent(capital, risk_pct, max_pos)
            st.rerun()

    # ── Frequency + Run controls ─────────────────────────
    freq_col, run_col, status_col = st.columns([2, 2, 1])
    with freq_col:
        freq_options = {"Manual Only": "manual", "Daily": "daily", "Weekly": "weekly", "Monthly": "monthly"}
        freq_label = st.selectbox("Run Frequency", list(freq_options.keys()),
                                   index=list(freq_options.values()).index(config.get("rebalance_frequency", "weekly")) if config.get("rebalance_frequency", "weekly") in freq_options.values() else 0,
                                   key="agent_freq", label_visibility="collapsed")
        freq = freq_options[freq_label]

        # Show next scheduled run
        last_run = config.get("last_run")
        if freq != "manual" and last_run:
            from datetime import datetime as dt, timedelta
            try:
                last_dt = dt.strptime(last_run[:16], "%Y-%m-%d %H:%M")
                interval = {"daily": timedelta(days=1), "weekly": timedelta(weeks=1), "monthly": timedelta(days=30)}.get(freq, timedelta(weeks=1))
                next_run = last_dt + interval
                now = dt.utcnow()
                overdue = now > next_run
                next_str = next_run.strftime("%Y-%m-%d %H:%M")
                st.markdown(
                    f'<div style="font-size:11px; color:{"#ef4444" if overdue else "#6b7280"};">'
                    f'{"⚠ OVERDUE — " if overdue else ""}Next run: {next_str}</div>',
                    unsafe_allow_html=True,
                )
            except Exception:
                pass

    with run_col:
        run_clicked = st.button("Run AI Agent Cycle Now", type="primary", use_container_width=True, key="run_agent")

    with status_col:
        st.markdown(
            f'<div style="text-align:center; padding:4px;">'
            f'<div style="font-size:10px; color:#6b7280;">Last Run</div>'
            f'<div style="font-size:11px; color:#e5e5e5;">{last_run[:16] if last_run else "Never"}</div>'
            f'<div style="font-size:10px; color:#6b7280; margin-top:2px;">{freq_label}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # Save frequency if changed
    if freq != config.get("rebalance_frequency"):
        conn = __import__("src.utils.db", fromlist=["get_connection"]).get_connection()
        conn.execute("UPDATE agent_config SET rebalance_frequency=? WHERE id=1", (freq,))
        conn.commit()
        conn.close()

    # Auto-run check: if frequency is set and overdue, offer to run
    if freq != "manual" and last_run:
        try:
            from datetime import datetime as dt, timedelta
            last_dt = dt.strptime(last_run[:16], "%Y-%m-%d %H:%M")
            interval = {"daily": timedelta(days=1), "weekly": timedelta(weeks=1), "monthly": timedelta(days=30)}.get(freq, timedelta(weeks=1))
            if dt.utcnow() > last_dt + interval and not run_clicked:
                st.warning(f"Agent is overdue for a {freq} cycle. Last run: {last_run[:16]}.")
                if st.button("Auto-Run Overdue Cycle", key="auto_run"):
                    run_clicked = True
        except Exception:
            pass

    # ── AI Trading Rules (visible + expandable) ──────────
    with st.expander("AI Trading Rules", expanded=False):
        st.markdown(
            '<div style="background:#0d0d0d; border-radius:10px; padding:16px;">'
            '<div style="font-size:13px; color:#d1d5db; line-height:1.8;">'
            '<div style="font-size:11px; color:#3b82f6; font-weight:700; text-transform:uppercase; letter-spacing:0.5px; margin-bottom:8px;">Entry Rules</div>'
            '• Only trade when 7+ of 12 signals agree on direction<br>'
            '• Prioritize signals with 70%+ historical win rate on this stock<br>'
            '• Discount signals with &lt;40% backtest win rate<br>'
            '• If insider cluster buy detected AND backtest confirms, increase position size<br>'
            '• If analyst consensus is Strong Buy with 20%+ upside, strong confirming signal<br>'
            '• Follow the money — favor sectors with positive money flow, avoid sectors with outflows<br>'
            '• If sector flow is negative for a stock&#39;s sector, reduce conviction even if other signals are bullish<br>'
            '<br>'
            '<div style="font-size:11px; color:#ef4444; font-weight:700; text-transform:uppercase; letter-spacing:0.5px; margin-bottom:8px;">Risk Rules</div>'
            f'• Max risk per trade: {risk_pct*100:.0f}% of portfolio (${capital*risk_pct:,.0f})<br>'
            f'• Max {max_pos} open positions at once<br>'
            '• Keep at least 20% in cash at all times<br>'
            '• Set stop loss on every trade (below support or -8% max)<br>'
            '• Set target on every trade (at resistance or +15% max)<br>'
            '<br>'
            '<div style="font-size:11px; color:#f59e0b; font-weight:700; text-transform:uppercase; letter-spacing:0.5px; margin-bottom:8px;">Market Regime Rules</div>'
            '• Normal: trade all sectors, standard position sizes<br>'
            '• High volatility (VIX &gt; 30): defensive only, reduce position sizes, raise min score to 60<br>'
            '• Recession warning (inverted yield curve): favor healthcare, staples, utilities. Avoid cyclicals<br>'
            '<br>'
            '<div style="font-size:11px; color:#a855f7; font-weight:700; text-transform:uppercase; letter-spacing:0.5px; margin-bottom:8px;">Exit Rules</div>'
            '• Close when stop loss hit (automatic)<br>'
            '• Close when target reached (take profit)<br>'
            '• Close when signal alignment flips bearish (7+ signals flip)<br>'
            '• Close when AI detects macro regime change affecting the position<br>'
            '<br>'
            '<div style="font-size:11px; color:#06b6d4; font-weight:700; text-transform:uppercase; letter-spacing:0.5px; margin-bottom:8px;">AI Decision Process</div>'
            '• Step 1: Read macro environment (VIX, rates, geopolitical, disruption, sector money flow)<br>'
            '• Step 2: AI picks sectors + stocks based on market context<br>'
            '• Step 3: Deep dive each pick — analyze all 12 indicators with raw data<br>'
            '• Step 4: Check backtest track record — which signals historically worked on this stock<br>'
            '• Step 5: Claude makes BUY/SELL/HOLD decision with reasoning<br>'
            '• Step 6: Execute paper trades with calculated position sizing<br>'
            '</div></div>',
            unsafe_allow_html=True,
        )

    if run_clicked:
        agent = TradingAgent()
        try:
            progress = st.progress(0, text="Step 1/6: Reading market conditions...")
            result = agent.run_cycle()
            progress.empty()

            steps = result.get("steps", {})

            # ── Step 1: Market Analysis ────────────────────
            market = steps.get("market", {})
            st.markdown(
                f'<div style="background:#111; border-left:3px solid #3b82f6; border-radius:8px; padding:14px; margin-bottom:8px;">'
                f'<div style="font-size:12px; color:#3b82f6; font-weight:700; text-transform:uppercase;">Step 1: Market Analysis</div>'
                f'<div style="font-size:14px; color:#e5e5e5; margin-top:6px;">Regime: <b>{market.get("regime", "normal").title()}</b> | {market.get("summary", "")}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

            # ── Step 2: AI Discovery ───────────────────────
            candidates = steps.get("candidates", [])
            disc_reasoning = steps.get("discovery_reasoning", "")
            disc_focus = steps.get("discovery_focus", "")
            cand_pills = " ".join(
                f'<span style="display:inline-block; margin:2px; padding:3px 10px; background:rgba(34,197,94,0.1); border:1px solid rgba(34,197,94,0.3); border-radius:20px; font-size:12px; color:#4ade80; font-weight:600;">{c["symbol"]} ({c["score"]})</span>'
                for c in candidates[:5]
            )
            st.markdown(
                f'<div style="background:#111; border-left:3px solid #f59e0b; border-radius:8px; padding:14px; margin-bottom:8px;">'
                f'<div style="font-size:12px; color:#f59e0b; font-weight:700; text-transform:uppercase;">Step 2: AI Discovery</div>'
                f'<div style="font-size:13px; color:#d1d5db; margin-top:6px;">{disc_focus}</div>'
                f'<div style="font-size:12px; color:#9ca3af; margin-top:4px; font-style:italic;">{disc_reasoning[:150]}</div>'
                f'<div style="margin-top:8px;">{cand_pills}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

            # ── Step 3: Deep Dive Results ──────────────────
            analyses = steps.get("analyses", {})
            if analyses:
                dive_rows = ""
                for sym, data in analyses.items():
                    v = data.get("verdict", "Hold")
                    vc = "#22c55e" if "Buy" in v else "#ef4444" if "Sell" in v else "#f59e0b"
                    dive_rows += (
                        f'<div style="display:flex; justify-content:space-between; padding:4px 0; border-bottom:1px solid #1a1a1a;">'
                        f'<span style="font-weight:700; color:#e5e5e5;">{sym}</span>'
                        f'<span style="color:{vc}; font-weight:700;">{v}</span>'
                        f'<span style="color:#6b7280;">{data.get("bullish_signals", 0)}/{data.get("total_signals", 0)} bullish</span>'
                        f'<span style="color:#6b7280;">Risk {data.get("risk", 3)}/5</span>'
                        f'</div>'
                    )
                st.markdown(
                    f'<div style="background:#111; border-left:3px solid #8b5cf6; border-radius:8px; padding:14px; margin-bottom:8px;">'
                    f'<div style="font-size:12px; color:#8b5cf6; font-weight:700; text-transform:uppercase;">Step 3: Deep Dive Analysis</div>'
                    f'<div style="margin-top:8px; font-size:13px;">{dive_rows}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

            # ── Step 4+5: AI Trade Decisions + Execution ───
            trade_decisions = steps.get("trade_decisions", [])
            executed = steps.get("executed", [])
            if trade_decisions:
                trade_rows = ""
                for t in trade_decisions:
                    ac = "#22c55e" if t.get("action") == "BUY" else "#ef4444" if t.get("action") == "SELL" else "#f59e0b"
                    trade_rows += (
                        f'<div style="display:flex; justify-content:space-between; align-items:center; padding:6px 0; border-bottom:1px solid #1a1a1a;">'
                        f'<span style="font-weight:700; color:#e5e5e5;">{t.get("symbol", "")}</span>'
                        f'<span style="color:{ac}; font-weight:800;">{t.get("action", "HOLD")}</span>'
                        f'<span style="color:#6b7280;">{t.get("shares", "")} shares</span>'
                        f'<span style="color:#9ca3af; font-size:12px; max-width:300px; overflow:hidden; text-overflow:ellipsis;">{t.get("reason", "")[:80]}</span>'
                        f'</div>'
                    )
                st.markdown(
                    f'<div style="background:#111; border-left:3px solid #22c55e; border-radius:8px; padding:14px; margin-bottom:8px;">'
                    f'<div style="font-size:12px; color:#22c55e; font-weight:700; text-transform:uppercase;">Step 4-5: AI Decisions &amp; Execution</div>'
                    f'<div style="font-size:12px; color:#6b7280; margin-top:4px;">{len(executed)} of {len(trade_decisions)} trades executed</div>'
                    f'<div style="margin-top:8px; font-size:13px;">{trade_rows}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f'<div style="background:#111; border-left:3px solid #6b7280; border-radius:8px; padding:14px; margin-bottom:8px;">'
                    f'<div style="font-size:12px; color:#6b7280; font-weight:700; text-transform:uppercase;">Step 4-5: AI Decisions</div>'
                    f'<div style="font-size:13px; color:#9ca3af; margin-top:6px;">No trades recommended this cycle. AI is waiting for better setups.</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

            # ── Pre-Trade Checklists ───────────────────────
            checklists = steps.get("checklists", {})
            if checklists:
                checklist_html = ""
                for sym_ck, ck_data in checklists.items():
                    passed = ck_data.get("passed", True)
                    checks = ck_data.get("checks", [])
                    ck_border = "#22c55e" if passed else "#ef4444"
                    ck_label = "PASSED" if passed else "BLOCKED"

                    items_html = ""
                    for check_line in checks:
                        if "PASS" in check_line:
                            items_html += f'<div style="font-size:11px; color:#22c55e; margin:2px 0;">✅ {check_line.replace("PASS: ", "")}</div>'
                        elif "FAIL" in check_line:
                            items_html += f'<div style="font-size:11px; color:#ef4444; margin:2px 0;">❌ {check_line.replace("FAIL: ", "")}</div>'
                        elif "WARN" in check_line:
                            items_html += f'<div style="font-size:11px; color:#f59e0b; margin:2px 0;">⚠️ {check_line.replace("WARN: ", "")}</div>'

                    checklist_html += (
                        f'<div style="background:#0d0d0d; border:1px solid {ck_border}44; border-radius:8px; padding:10px; margin-bottom:6px;">'
                        f'<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">'
                        f'<span style="font-size:13px; font-weight:700; color:#e5e5e5;">{sym_ck}</span>'
                        f'<span style="font-size:11px; font-weight:700; color:{ck_border};">{ck_label}</span>'
                        f'</div>'
                        f'{items_html}'
                        f'</div>'
                    )

                st.markdown(
                    f'<div style="background:#111; border-left:3px solid #06b6d4; border-radius:8px; padding:14px; margin-bottom:8px;">'
                    f'<div style="font-size:12px; color:#06b6d4; font-weight:700; text-transform:uppercase; margin-bottom:8px;">Pre-Trade Checklist</div>'
                    f'{checklist_html}'
                    f'</div>',
                    unsafe_allow_html=True,
                )

            # ── Step 6: Closed Positions ───────────────────
            closed = steps.get("closed_positions", [])
            if closed:
                close_rows = ""
                for c in closed:
                    pc = "#22c55e" if c.get("pnl_pct", 0) and c["pnl_pct"] > 0 else "#ef4444"
                    close_rows += f'<div style="color:{pc}; font-size:13px;">Closed {c["symbol"]} — {c["reason"]} ({c.get("pnl_pct", 0):+.1f}%)</div>'
                st.markdown(
                    f'<div style="background:#111; border-left:3px solid #ef4444; border-radius:8px; padding:14px; margin-bottom:8px;">'
                    f'<div style="font-size:12px; color:#ef4444; font-weight:700; text-transform:uppercase;">Positions Closed</div>'
                    f'<div style="margin-top:6px;">{close_rows}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

            # ── Step 7: Portfolio Snapshot ──────────────────
            equity = steps.get("equity", {})
            pnl_c = "#22c55e" if equity.get("cumulative_return", 0) > 0 else "#ef4444"
            st.markdown(
                f'<div style="background:#111; border-left:3px solid #06b6d4; border-radius:8px; padding:14px; margin-bottom:16px;">'
                f'<div style="font-size:12px; color:#06b6d4; font-weight:700; text-transform:uppercase;">Step 6: Portfolio Snapshot</div>'
                f'<div style="display:flex; gap:24px; margin-top:8px; font-size:14px;">'
                f'<span style="color:#e5e5e5;">Total: <b>${equity.get("total_value", 0):,.0f}</b></span>'
                f'<span style="color:#e5e5e5;">Cash: <b>${equity.get("cash", 0):,.0f}</b></span>'
                f'<span style="color:{pnl_c};">Return: <b>{equity.get("cumulative_return", 0):+.1f}%</b></span>'
                f'</div></div>',
                unsafe_allow_html=True,
            )

            st.success(f"Cycle complete — {result['trades_executed']} trades executed")

        except Exception as e:
            st.error(f"Agent error: {str(e)[:200]}")

    # ── Delta from last run (always show if decisions exist) ──
    all_decisions = get_agent_decisions(limit=50)
    if all_decisions:
        # Group decisions by run_date
        runs: dict[str, list[dict]] = {}
        for d in all_decisions:
            rd = d.get("run_date", "")
            runs.setdefault(rd, []).append(d)

        run_dates = sorted(runs.keys(), reverse=True)

        if len(run_dates) >= 1:
            st.markdown(
                '<div style="display:flex; align-items:center; gap:8px; margin:20px 0 12px;">'
                '<div style="height:2px; flex:1; background:linear-gradient(to right, #333, transparent);"></div>'
                '<span style="font-size:13px; font-weight:700; color:#6b7280; text-transform:uppercase; letter-spacing:1px;">AI Decision Delta</span>'
                '<div style="height:2px; flex:1; background:linear-gradient(to left, #333, transparent);"></div>'
                '</div>',
                unsafe_allow_html=True,
            )

            if len(run_dates) >= 2:
                latest_run = run_dates[0]
                prev_run = run_dates[1]
                latest_decisions = runs[latest_run]
                prev_decisions = runs[prev_run]

                # Extract key changes
                latest_trades = {d["symbol"]: d for d in latest_decisions if d.get("symbol") and d["step"] in ("ai_trade", "close_position", "human_trade")}
                prev_trades = {d["symbol"]: d for d in prev_decisions if d.get("symbol") and d["step"] in ("ai_trade", "close_position", "human_trade")}

                # New positions this cycle
                new_syms = set(latest_trades.keys()) - set(prev_trades.keys())
                # Closed positions
                closed_syms = {d["symbol"] for d in latest_decisions if d["step"] == "close_position" and d.get("symbol")}
                # Held (in both)
                held_syms = set(latest_trades.keys()) & set(prev_trades.keys()) - closed_syms

                # Discovery focus change
                latest_disc = next((d for d in latest_decisions if d["step"] == "ai_discovery"), None)
                prev_disc = next((d for d in prev_decisions if d["step"] == "ai_discovery"), None)

                delta_html = '<div style="background:#111; border:1px solid #1a1a1a; border-radius:12px; padding:18px;">'

                # Timing
                delta_html += (
                    f'<div style="display:flex; justify-content:space-between; font-size:12px; color:#6b7280; margin-bottom:12px;">'
                    f'<span>Current run: {latest_run}</span>'
                    f'<span>Previous run: {prev_run}</span>'
                    f'</div>'
                )

                # Strategy shift
                if latest_disc and prev_disc:
                    latest_focus = latest_disc.get("decision", "")
                    prev_focus = prev_disc.get("decision", "")
                    if latest_focus != prev_focus:
                        delta_html += (
                            f'<div style="background:#0d0d0d; border-radius:8px; padding:12px; margin-bottom:10px;">'
                            f'<div style="font-size:11px; color:#f59e0b; font-weight:700; text-transform:uppercase; margin-bottom:4px;">Strategy Shift</div>'
                            f'<div style="font-size:12px; color:#ef4444; margin-bottom:4px;">Before: {prev_focus[:80]}</div>'
                            f'<div style="font-size:12px; color:#22c55e;">Now: {latest_focus[:80]}</div>'
                            f'<div style="font-size:11px; color:#9ca3af; margin-top:4px;">Reasoning: {latest_disc.get("reasoning", "")[:120]}</div>'
                            f'</div>'
                        )
                    else:
                        delta_html += (
                            f'<div style="background:#0d0d0d; border-radius:8px; padding:12px; margin-bottom:10px;">'
                            f'<div style="font-size:11px; color:#22c55e; font-weight:700;">Strategy Unchanged: {latest_focus[:80]}</div>'
                            f'</div>'
                        )

                # New entries
                if new_syms:
                    new_pills = " ".join(
                        f'<span style="display:inline-block; margin:2px; padding:3px 10px; background:rgba(34,197,94,0.1); border:1px solid rgba(34,197,94,0.3); border-radius:20px; font-size:12px; font-weight:600; color:#4ade80;">{s}</span>'
                        for s in new_syms
                    )
                    delta_html += (
                        f'<div style="margin-bottom:8px;">'
                        f'<span style="font-size:11px; color:#22c55e; font-weight:700; text-transform:uppercase;">New Positions: </span>'
                        f'{new_pills}'
                        f'</div>'
                    )

                # Closed
                if closed_syms:
                    closed_pills = " ".join(
                        f'<span style="display:inline-block; margin:2px; padding:3px 10px; background:rgba(239,68,68,0.1); border:1px solid rgba(239,68,68,0.3); border-radius:20px; font-size:12px; font-weight:600; color:#f87171;">{s}</span>'
                        for s in closed_syms
                    )
                    delta_html += (
                        f'<div style="margin-bottom:8px;">'
                        f'<span style="font-size:11px; color:#ef4444; font-weight:700; text-transform:uppercase;">Closed: </span>'
                        f'{closed_pills}'
                        f'</div>'
                    )

                # Held
                if held_syms:
                    held_pills = " ".join(
                        f'<span style="display:inline-block; margin:2px; padding:3px 10px; background:rgba(245,158,11,0.1); border:1px solid rgba(245,158,11,0.3); border-radius:20px; font-size:12px; font-weight:600; color:#fbbf24;">{s}</span>'
                        for s in held_syms
                    )
                    delta_html += (
                        f'<div style="margin-bottom:8px;">'
                        f'<span style="font-size:11px; color:#f59e0b; font-weight:700; text-transform:uppercase;">Held (no change): </span>'
                        f'{held_pills}'
                        f'</div>'
                    )

                # No changes
                if not new_syms and not closed_syms:
                    delta_html += '<div style="font-size:13px; color:#6b7280;">No portfolio changes this cycle — AI is holding current positions.</div>'

                # Equity change
                equity_data = get_agent_equity()
                if len(equity_data) >= 2:
                    prev_val = equity_data[-2]["total_value"]
                    curr_val = equity_data[-1]["total_value"]
                    eq_change = curr_val - prev_val
                    eq_pct = (eq_change / prev_val * 100) if prev_val > 0 else 0
                    eq_c = "#22c55e" if eq_change > 0 else "#ef4444"
                    delta_html += (
                        f'<div style="margin-top:10px; padding-top:10px; border-top:1px solid #1a1a1a; display:flex; justify-content:space-between;">'
                        f'<span style="font-size:12px; color:#6b7280;">Portfolio change since last run</span>'
                        f'<span style="font-size:14px; font-weight:700; color:{eq_c};">{eq_pct:+.2f}% (${eq_change:+,.0f})</span>'
                        f'</div>'
                    )

                delta_html += '</div>'
                st.markdown(delta_html, unsafe_allow_html=True)

            else:
                st.caption("Run the agent at least twice to see the delta between decisions.")

    # ── Portfolio Summary ──────────────────────────────────
    config = get_agent_config()  # Refresh after potential run
    cash = config.get("current_cash", capital)
    starting = config.get("starting_capital", capital)

    open_positions = get_agent_positions(status="open")
    closed_positions = get_agent_positions(status="closed")

    # Calculate invested value
    invested = 0
    for p in open_positions:
        try:
            from src.data.gateway import DataGateway
            gw = DataGateway()
            q = gw.get_quote(p["symbol"])
            cur_price = float(q.price) if q and q.price else p["entry_price"]
        except Exception:
            cur_price = p["entry_price"]
        invested += cur_price * p["shares"]

    total_value = cash + invested
    total_return = ((total_value - starting) / starting) * 100

    pnl_color = "#22c55e" if total_return > 0 else "#ef4444" if total_return < 0 else "#6b7280"
    win_count = sum(1 for p in closed_positions if p.get("pnl", 0) and p["pnl"] > 0)
    total_closed = len(closed_positions)
    win_rate = (win_count / total_closed * 100) if total_closed > 0 else 0
    wr_color = "#22c55e" if win_rate >= 60 else "#ef4444" if win_rate < 40 else "#f59e0b"

    st.markdown(
        f'<div style="display:grid; grid-template-columns:repeat(5, 1fr); gap:12px; margin:20px 0;">'
        f'<div style="background:#111; border:1px solid #1a1a1a; border-radius:12px; padding:16px; text-align:center;">'
        f'<div style="font-size:10px; color:#6b7280; text-transform:uppercase;">Portfolio</div>'
        f'<div style="font-size:22px; font-weight:800; color:#e5e5e5;">${total_value:,.0f}</div></div>'
        f'<div style="background:#111; border:1px solid #1a1a1a; border-radius:12px; padding:16px; text-align:center;">'
        f'<div style="font-size:10px; color:#6b7280; text-transform:uppercase;">Return</div>'
        f'<div style="font-size:22px; font-weight:800; color:{pnl_color};">{total_return:+.1f}%</div></div>'
        f'<div style="background:#111; border:1px solid #1a1a1a; border-radius:12px; padding:16px; text-align:center;">'
        f'<div style="font-size:10px; color:#6b7280; text-transform:uppercase;">Cash</div>'
        f'<div style="font-size:22px; font-weight:800; color:#e5e5e5;">${cash:,.0f}</div></div>'
        f'<div style="background:#111; border:1px solid #1a1a1a; border-radius:12px; padding:16px; text-align:center;">'
        f'<div style="font-size:10px; color:#6b7280; text-transform:uppercase;">Open</div>'
        f'<div style="font-size:22px; font-weight:800; color:#e5e5e5;">{len(open_positions)}</div></div>'
        f'<div style="background:#111; border:1px solid #1a1a1a; border-radius:12px; padding:16px; text-align:center;">'
        f'<div style="font-size:10px; color:#6b7280; text-transform:uppercase;">Win Rate</div>'
        f'<div style="font-size:22px; font-weight:800; color:{wr_color};">{win_rate:.0f}%</div>'
        f'<div style="font-size:10px; color:#6b7280;">{win_count}W / {total_closed - win_count}L</div></div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── Recent Activity Summary ─────────────────────────
    recent_decisions = get_agent_decisions(limit=50)
    if recent_decisions:
        # Group by run_date
        runs_grouped: dict[str, list[dict]] = {}
        for d in recent_decisions:
            runs_grouped.setdefault(d.get("run_date", ""), []).append(d)

        run_dates_sorted = sorted(runs_grouped.keys(), reverse=True)
        num_runs = len(run_dates_sorted)

        if num_runs > 0:
            st.markdown(
                '<div style="display:flex; align-items:center; gap:8px; margin:20px 0 12px;">'
                '<div style="height:2px; flex:1; background:linear-gradient(to right, #333, transparent);"></div>'
                '<span style="font-size:13px; font-weight:700; color:#6b7280; text-transform:uppercase; letter-spacing:1px;">Recent Activity</span>'
                '<div style="height:2px; flex:1; background:linear-gradient(to left, #333, transparent);"></div>'
                '</div>',
                unsafe_allow_html=True,
            )

            # Show last 5 cycles as a timeline
            for run_date in run_dates_sorted[:5]:
                cycle_decisions = runs_grouped[run_date]
                trades = [d for d in cycle_decisions if d["step"] in ("ai_trade", "human_trade")]
                closes = [d for d in cycle_decisions if d["step"] == "close_position"]
                discovery = next((d for d in cycle_decisions if d["step"] == "ai_discovery"), None)

                # Summarize
                actions = []
                for t in trades:
                    src_icon = "🤖" if t.get("source", "ai") == "ai" else "👤"
                    actions.append(f'{src_icon} {t.get("decision", "")[:40]}')
                for c in closes:
                    actions.append(f'📤 Closed {c.get("symbol", "")} — {c.get("reasoning", "")[:30]}')

                if not actions:
                    actions.append("No trades — AI held positions")

                actions_html = "".join(f'<div style="font-size:12px; color:#d1d5db; margin:2px 0;">{a}</div>' for a in actions[:3])

                st.markdown(
                    f'<div style="background:#111; border:1px solid #1a1a1a; border-radius:8px; padding:12px; margin-bottom:6px;">'
                    f'<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">'
                    f'<span style="font-size:12px; font-weight:700; color:#e5e5e5;">{run_date[:16]}</span>'
                    f'<span style="font-size:11px; color:#6b7280;">{len(trades)} trades, {len(closes)} closed</span>'
                    f'</div>'
                    f'{actions_html}'
                    + (f'<div style="font-size:11px; color:#6b7280; margin-top:4px; font-style:italic;">Focus: {discovery["decision"][:60]}</div>' if discovery else "")
                    + f'</div>',
                    unsafe_allow_html=True,
                )

    # ── Equity Curve ───────────────────────────────────────
    equity_data = get_agent_equity()
    if equity_data and len(equity_data) >= 2:
        fig = go.Figure()
        dates = [e["date"] for e in equity_data]
        values = [e["cumulative_return"] for e in equity_data]
        fig.add_trace(go.Scatter(x=dates, y=values, name="AI Agent",
                                  line=dict(color="#22c55e", width=2),
                                  fill="tozeroy", fillcolor="rgba(34,197,94,0.06)"))
        fig.update_layout(template="plotly_dark", height=300, plot_bgcolor="#0a0a0a", paper_bgcolor="#0a0a0a",
                          yaxis_title="Return %", hovermode="x unified", margin=dict(l=0, r=0, t=10, b=0))
        st.plotly_chart(fig, use_container_width=True)

    # ── Tabs ───────────────────────────────────────────────
    tab_positions, tab_human, tab_history, tab_decisions = st.tabs(["Open Positions", "Add Manual Trade", "Trade History", "AI Decisions"])

    with tab_positions:
        if open_positions:
            for p in open_positions:
                try:
                    gw = _get_gateway()
                    q = gw.get_quote(p["symbol"])
                    cur_price = float(q.price) if q and q.price else p["entry_price"]
                except Exception:
                    cur_price = p["entry_price"]

                pnl_pct = ((cur_price - p["entry_price"]) / p["entry_price"]) * 100
                pc = "#22c55e" if pnl_pct > 0 else "#ef4444"

                source = p.get("source", "ai")
                source_color = "#a855f7" if source == "ai" else "#3b82f6"
                source_label = "AI" if source == "ai" else "MANUAL"
                source_icon = "🤖" if source == "ai" else "👤"

                st.markdown(
                    f'<div style="background:#111; border:1px solid #1a1a1a; border-left:3px solid {pc}; border-radius:10px; padding:14px; margin-bottom:8px;">'
                    f'<div style="display:flex; justify-content:space-between; align-items:center;">'
                    f'<div>'
                    f'<span style="font-size:18px; font-weight:800; color:#e5e5e5;">{p["symbol"]}</span>'
                    f'<span style="font-size:10px; font-weight:700; color:{source_color}; background:rgba({",".join(str(int(source_color[i:i+2], 16)) for i in (1,3,5))},0.15); padding:2px 8px; border-radius:10px; margin-left:8px;">{source_icon} {source_label}</span>'
                    f'<span style="font-size:12px; color:#6b7280; margin-left:10px;">{p["shares"]} shares @ ${p["entry_price"]:.2f}</span>'
                    f'</div>'
                    f'<div style="text-align:right;">'
                    f'<div style="font-size:16px; font-weight:700; color:#e5e5e5;">${cur_price:.2f}</div>'
                    f'<div style="font-size:14px; font-weight:700; color:{pc};">{pnl_pct:+.1f}%</div>'
                    f'</div>'
                    f'</div>'
                    f'<div style="font-size:11px; color:#6b7280; margin-top:6px;">Stop: ${p.get("stop_loss", 0):.2f} | Target: ${p.get("target", 0):.2f} | Entered: {p["entry_date"][:10]}</div>'
                    f'<div style="font-size:12px; color:#9ca3af; margin-top:4px; font-style:italic;">{p.get("ai_reasoning", "")[:100]}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
        else:
            st.markdown(
                '<div style="background:#111; border-radius:12px; padding:40px; text-align:center;">'
                '<div style="font-size:24px; margin-bottom:8px;">📭</div>'
                '<div style="font-size:14px; color:#6b7280;">No open positions. Click "Run AI Agent Cycle" to start trading.</div>'
                '</div>',
                unsafe_allow_html=True,
            )

    with tab_human:
        st.markdown(
            '<div style="font-size:14px; color:#e5e5e5; margin-bottom:12px;">Add a stock manually — tracked alongside AI trades with a <span style="color:#3b82f6;">👤 MANUAL</span> badge.</div>',
            unsafe_allow_html=True,
        )
        with st.form("human_trade_form"):
            h1, h2 = st.columns(2)
            with h1:
                h_sym = st.text_input("Symbol", placeholder="AAPL", max_chars=10, key="h_sym")
                h_shares = st.number_input("Shares", min_value=1, step=1, value=50, key="h_shares")
                h_entry = st.number_input("Entry Price ($)", min_value=0.01, step=0.01, value=0.01, key="h_entry")
            with h2:
                h_stop = st.number_input("Stop Loss ($)", min_value=0.0, step=0.01, value=0.0, key="h_stop")
                h_target = st.number_input("Target ($)", min_value=0.0, step=0.01, value=0.0, key="h_target")
                h_reason = st.text_area("Your Thesis", placeholder="Why are you taking this trade?", key="h_reason")

            if st.form_submit_button("Add Manual Trade", type="primary", use_container_width=True):
                if h_sym and h_entry > 0 and h_shares > 0:
                    if h_entry <= 0.01:
                        try:
                            gw = _get_gateway()
                            q = gw.get_quote(h_sym.upper())
                            h_entry = float(q.price) if q and q.price else 0
                        except Exception:
                            pass
                    if h_entry > 0:
                        trade_id = add_human_trade(
                            h_sym.upper(), "long", h_shares, h_entry,
                            h_stop if h_stop > 0 else None,
                            h_target if h_target > 0 else None,
                            h_reason,
                        )
                        st.success(f"Manual trade #{trade_id} added for {h_sym.upper()}")
                        st.rerun()
                    else:
                        st.error("Could not determine price. Enter entry price manually.")

    with tab_history:
        if closed_positions:
            rows = ""
            for p in closed_positions[:20]:
                pc = "#22c55e" if p.get("pnl", 0) and p["pnl"] > 0 else "#ef4444"
                src = p.get("source", "ai")
                src_badge = "🤖" if src == "ai" else "👤"
                rows += (
                    f'<tr style="border-bottom:1px solid #1a1a1a;">'
                    f'<td style="padding:10px; font-weight:700; color:#e5e5e5;">{src_badge} {p["symbol"]}</td>'
                    f'<td style="padding:10px; color:#e5e5e5;">{p["shares"]}</td>'
                    f'<td style="padding:10px; color:#e5e5e5;">${p["entry_price"]:.2f}</td>'
                    f'<td style="padding:10px; color:#e5e5e5;">${p.get("exit_price", 0):.2f}</td>'
                    f'<td style="padding:10px; color:{pc}; font-weight:700;">{p.get("pnl_percent", 0):+.1f}%</td>'
                    f'<td style="padding:10px; color:#6b7280;">{(p.get("entry_date") or "")[:10]}</td>'
                    f'<td style="padding:10px; color:#9ca3af; font-size:11px;">{(p.get("ai_reasoning") or "")[:50]}</td>'
                    f'</tr>'
                )
            st.markdown(
                f'<div style="background:#111; border-radius:12px; padding:16px; overflow-x:auto;">'
                f'<table style="width:100%; border-collapse:collapse; font-size:13px;">'
                f'<thead><tr style="border-bottom:1px solid #333;">'
                f'<th style="text-align:left; padding:10px; color:#6b7280;">Stock</th>'
                f'<th style="text-align:left; padding:10px; color:#6b7280;">Shares</th>'
                f'<th style="text-align:left; padding:10px; color:#6b7280;">Entry</th>'
                f'<th style="text-align:left; padding:10px; color:#6b7280;">Exit</th>'
                f'<th style="text-align:left; padding:10px; color:#6b7280;">P/L %</th>'
                f'<th style="text-align:left; padding:10px; color:#6b7280;">Date</th>'
                f'<th style="text-align:left; padding:10px; color:#6b7280;">AI Reason</th>'
                f'</tr></thead><tbody>{rows}</tbody></table></div>',
                unsafe_allow_html=True,
            )
        else:
            st.info("No closed trades yet.")

    with tab_decisions:
        decisions = get_agent_decisions(limit=30)
        if decisions:
            for d in decisions:
                step_colors = {
                    "market_analysis": "#3b82f6", "discovery": "#f59e0b", "ai_discovery": "#f59e0b",
                    "ai_trade": "#22c55e", "human_trade": "#3b82f6",
                    "close_position": "#ef4444", "ai_error": "#ef4444",
                    "pre_trade_check": "#06b6d4", "trade_blocked": "#ef4444",
                }
                sc = step_colors.get(d["step"], "#6b7280")
                sym_html = f' — <b style="color:#e5e5e5;">{d["symbol"]}</b>' if d.get("symbol") else ""
                st.markdown(
                    f'<div style="background:#111; border-left:3px solid {sc}; border-radius:8px; padding:12px; margin-bottom:6px;">'
                    f'<div style="display:flex; justify-content:space-between; align-items:center;">'
                    f'<div>'
                    f'<span style="font-size:12px; color:{sc}; font-weight:700; text-transform:uppercase;">{d["step"].replace("_", " ")}</span>'
                    f'{sym_html}'
                    f'</div>'
                    f'<span style="font-size:11px; color:#6b7280;">{(d.get("created_at") or "")[:16]}</span>'
                    f'</div>'
                    f'<div style="font-size:12px; color:#9ca3af; margin-top:4px;">{d["decision"]} — {d["reasoning"][:100]}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
        else:
            st.info("No AI decisions yet. Run a cycle to see the agent's reasoning.")


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
elif step == 6:
    page_ai_agent()

st.markdown('<div class="disclaimer">This is AI-generated analysis for informational purposes only. Not financial advice.</div>', unsafe_allow_html=True)
