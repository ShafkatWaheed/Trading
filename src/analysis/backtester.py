"""Signal backtester: validate how well each indicator predicts profits.

Pure computation — receives historical DataFrame, returns BacktestResult.
No I/O, no API calls, no database access.
"""

import math
from datetime import datetime

import numpy as np
import pandas as pd
import ta

from src.models.backtest_types import BacktestResult, BacktestTrade


# All supported signals with their detection logic
SIGNALS = {
    # Technical (original 14)
    "rsi_oversold": {"direction": "buy", "description": "RSI < 30 (oversold bounce)", "category": "technical"},
    "rsi_overbought": {"direction": "sell", "description": "RSI > 70 (overbought)", "category": "technical"},
    "macd_bullish": {"direction": "buy", "description": "MACD crosses above signal", "category": "technical"},
    "macd_bearish": {"direction": "sell", "description": "MACD crosses below signal", "category": "technical"},
    "sma50_cross_up": {"direction": "buy", "description": "Price crosses above SMA(50)", "category": "technical"},
    "sma50_cross_down": {"direction": "sell", "description": "Price crosses below SMA(50)", "category": "technical"},
    "sma200_cross_up": {"direction": "buy", "description": "Price crosses above SMA(200)", "category": "technical"},
    "golden_cross": {"direction": "buy", "description": "SMA(50) crosses above SMA(200)", "category": "technical"},
    "death_cross": {"direction": "sell", "description": "SMA(50) crosses below SMA(200)", "category": "technical"},
    "bb_lower_touch": {"direction": "buy", "description": "Price touches lower Bollinger Band", "category": "technical"},
    "bb_upper_touch": {"direction": "sell", "description": "Price touches upper Bollinger Band", "category": "technical"},
    "volume_spike": {"direction": "buy", "description": "Volume > 2x 20-day average", "category": "technical"},
    "support_bounce": {"direction": "buy", "description": "Price near 20-day low", "category": "technical"},
    "resistance_rejection": {"direction": "sell", "description": "Price near 20-day high", "category": "technical"},
    # Earnings (Phase 7)
    "earnings_beat": {"direction": "buy", "description": "Buy after earnings beat (EPS > estimate)", "category": "fundamental"},
    "earnings_miss": {"direction": "sell", "description": "Sell after earnings miss (EPS < estimate)", "category": "fundamental"},
    # Macro / VIX (Phase 1)
    "vix_low": {"direction": "buy", "description": "VIX below 20 (low fear, risk-on)", "category": "macro"},
    "vix_high": {"direction": "sell", "description": "VIX above 30 (high fear, risk-off)", "category": "macro"},
    "vix_spike": {"direction": "sell", "description": "VIX jumps 20%+ in a day (panic)", "category": "macro"},
    # Insider (Phase 2)
    "insider_buy": {"direction": "buy", "description": "Corporate insider purchased shares", "category": "smart_money"},
    "insider_sell": {"direction": "sell", "description": "Corporate insider sold shares", "category": "smart_money"},
    # Congress (Phase 3)
    "congress_buy": {"direction": "buy", "description": "Congress member purchased stock", "category": "congress"},
    "congress_sell": {"direction": "sell", "description": "Congress member sold stock", "category": "congress"},
    # Analyst (Phase 4)
    "analyst_upgrade_momentum": {"direction": "buy", "description": "Analyst buy ratings increasing month-over-month", "category": "analyst"},
    "analyst_downgrade_momentum": {"direction": "sell", "description": "Analyst sell ratings increasing month-over-month", "category": "analyst"},
    # News Sentiment (Phase 5)
    "news_bullish_spike": {"direction": "buy", "description": "News sentiment >70% bullish in a week", "category": "sentiment"},
    "news_bearish_spike": {"direction": "sell", "description": "News sentiment >70% bearish in a week", "category": "sentiment"},
    # Options Flow (Phase 8)
    "options_bullish": {"direction": "buy", "description": "Put/Call ratio < 0.7 (bullish options flow)", "category": "options"},
    "options_bearish": {"direction": "sell", "description": "Put/Call ratio > 1.3 (bearish options flow)", "category": "options"},
    # Community Buzz (Phase 11)
    "community_bullish": {"direction": "buy", "description": "Reddit/social >70% bullish discussion", "category": "community"},
    "community_bearish": {"direction": "sell", "description": "Reddit/social >70% bearish discussion", "category": "community"},
    # Institutional (Phase 12)
    "institutions_accumulating": {"direction": "buy", "description": "Top institutions increasing positions QoQ", "category": "institutional"},
    "institutions_distributing": {"direction": "sell", "description": "Top institutions decreasing positions QoQ", "category": "institutional"},
    # Geopolitical (Phase 9)
    "geopolitical_risk_spike": {"direction": "sell", "description": "Major geopolitical event affecting stock's sector", "category": "geopolitical"},
    # Disruption (Phase 10)
    "disruption_tailwind": {"direction": "buy", "description": "Stock's sector benefiting from tech disruption theme", "category": "disruption"},
}

# Signal categories for filtering in Prove It
SIGNAL_CATEGORIES = {
    "All Signals": list(SIGNALS.keys()),
    "Technical Only": [k for k, v in SIGNALS.items() if v.get("category") == "technical"],
    "Earnings": [k for k, v in SIGNALS.items() if v.get("category") == "fundamental"],
    "Macro / VIX": [k for k, v in SIGNALS.items() if v.get("category") == "macro"],
    "Smart Money (Insider)": [k for k, v in SIGNALS.items() if v.get("category") == "smart_money"],
    "Congressional": [k for k, v in SIGNALS.items() if v.get("category") == "congress"],
    "Analyst Ratings": [k for k, v in SIGNALS.items() if v.get("category") == "analyst"],
    "News Sentiment": [k for k, v in SIGNALS.items() if v.get("category") == "sentiment"],
    "Options Flow": [k for k, v in SIGNALS.items() if v.get("category") == "options"],
    "Community Buzz": [k for k, v in SIGNALS.items() if v.get("category") == "community"],
    "Institutional": [k for k, v in SIGNALS.items() if v.get("category") == "institutional"],
    "Geopolitical": [k for k, v in SIGNALS.items() if v.get("category") == "geopolitical"],
    "Disruption": [k for k, v in SIGNALS.items() if v.get("category") == "disruption"],
}


def backtest_signal(
    symbol: str,
    df: pd.DataFrame,
    signal_name: str,
    hold_days: int = 30,
) -> BacktestResult:
    """Backtest a single signal on historical data.

    Args:
        symbol: Stock ticker.
        df: DataFrame with columns: date, open, high, low, close, volume.
        signal_name: One of SIGNALS keys.
        hold_days: Days to hold after signal triggers.
    """
    if signal_name not in SIGNALS:
        raise ValueError(f"Unknown signal: {signal_name}. Choose from: {list(SIGNALS.keys())}")

    category = SIGNALS[signal_name].get("category", "technical")

    # Event-based signals use a different detection path
    if category in ("fundamental", "macro", "smart_money", "congress", "analyst",
                     "sentiment", "options", "community", "institutional", "geopolitical", "disruption"):
        return _backtest_event_signal(symbol, df, signal_name, hold_days)

    df = df.copy().reset_index(drop=True)
    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    volume = df["volume"].astype(float)

    # Compute indicators
    indicators = _compute_indicators(close, high, low, volume)
    triggers = _detect_signal(signal_name, df, indicators)

    # Simulate trades
    trades: list[BacktestTrade] = []
    direction = SIGNALS[signal_name]["direction"]

    i = 0
    while i < len(triggers):
        entry_idx = triggers[i]
        exit_idx = min(entry_idx + hold_days, len(df) - 1)

        if exit_idx <= entry_idx:
            i += 1
            continue

        entry_price = float(close.iloc[entry_idx])
        exit_price = float(close.iloc[exit_idx])

        if direction == "buy":
            pnl = exit_price - entry_price
            pnl_pct = (pnl / entry_price) * 100
        else:
            pnl = entry_price - exit_price
            pnl_pct = (pnl / entry_price) * 100

        trades.append(BacktestTrade(
            symbol=symbol,
            signal_name=signal_name,
            direction=direction,
            entry_date=str(df["date"].iloc[entry_idx]),
            entry_price=round(entry_price, 2),
            exit_date=str(df["date"].iloc[exit_idx]),
            exit_price=round(exit_price, 2),
            pnl=round(pnl, 2),
            pnl_percent=round(pnl_pct, 2),
            hold_days=exit_idx - entry_idx,
            outcome="win" if pnl > 0 else "loss",
        ))

        # Skip ahead past the hold period to avoid overlapping trades
        i += 1
        while i < len(triggers) and triggers[i] < exit_idx:
            i += 1

    return _build_result(symbol, signal_name, hold_days, len(df), trades)


def backtest_all_signals(
    symbol: str,
    df: pd.DataFrame,
    hold_days: int = 30,
) -> list[BacktestResult]:
    """Run all 14 signals and return results sorted by expected value."""
    results = []
    for sig_name in SIGNALS:
        try:
            result = backtest_signal(symbol, df, sig_name, hold_days)
            if result.total_trades > 0:
                results.append(result)
        except Exception:
            continue

    results.sort(key=lambda r: r.win_rate * r.avg_return, reverse=True)
    return results


# --- Deep Dive section → backtest signal mapping ---

SECTION_SIGNAL_MAP = {
    "Technical Analysis": {
        "bullish": ["rsi_oversold", "macd_bullish", "sma50_cross_up", "golden_cross"],
        "bearish": ["rsi_overbought", "macd_bearish", "sma50_cross_down", "death_cross"],
        "neutral": ["macd_bullish", "macd_bearish"],
    },
    "Fundamental Analysis": {
        "bullish": ["earnings_beat"],
        "bearish": ["earnings_miss"],
        "neutral": ["earnings_beat", "earnings_miss"],
    },
    "Macro Environment": {
        "bullish": ["vix_low"],
        "bearish": ["vix_high", "vix_spike"],
        "neutral": ["vix_low", "vix_high"],
    },
    "Options Flow": {
        "bullish": ["volume_spike"],
        "bearish": ["volume_spike"],
        "neutral": ["volume_spike"],
    },
    "Smart Money": {
        "bullish": ["insider_buy"],
        "bearish": ["insider_sell"],
        "neutral": ["insider_buy", "insider_sell"],
    },
    "Congressional Trades": {
        "bullish": ["congress_buy"],
        "bearish": ["congress_sell"],
        "neutral": ["congress_buy", "congress_sell"],
    },
    "Analyst Ratings": {
        "bullish": ["analyst_upgrade_momentum"],
        "bearish": ["analyst_downgrade_momentum"],
        "neutral": ["analyst_upgrade_momentum", "analyst_downgrade_momentum"],
    },
    "News Sentiment": {
        "bullish": ["news_bullish_spike"],
        "bearish": ["news_bearish_spike"],
        "neutral": ["news_bullish_spike", "news_bearish_spike"],
    },
    "Options Flow": {
        "bullish": ["options_bullish"],
        "bearish": ["options_bearish"],
        "neutral": ["options_bullish", "options_bearish"],
    },
    "Community Buzz": {
        "bullish": ["community_bullish"],
        "bearish": ["community_bearish"],
        "neutral": ["community_bullish", "community_bearish"],
    },
    "Institutional Holders": {
        "bullish": ["institutions_accumulating"],
        "bearish": ["institutions_distributing"],
        "neutral": ["institutions_accumulating", "institutions_distributing"],
    },
    "Geopolitical & Event Risk": {
        "bullish": [],
        "bearish": ["geopolitical_risk_spike"],
        "neutral": ["geopolitical_risk_spike"],
    },
    "Disruptive Technology": {
        "bullish": ["disruption_tailwind"],
        "bearish": [],
        "neutral": ["disruption_tailwind"],
    },
}

# Nothing is non-backtestable anymore — all indicators have event date fetchers
NON_BACKTESTABLE = set()


def backtest_section_signals(
    symbol: str,
    df: pd.DataFrame,
    section_type: str,
    direction: str,
    hold_days: int = 30,
) -> dict | None:
    """Backtest signals relevant to a Deep Dive section.

    Returns aggregated track record across all relevant signals, or None
    if the section type is not backtestable.
    """
    if section_type in NON_BACKTESTABLE:
        return None

    sig_map = SECTION_SIGNAL_MAP.get(section_type, {})
    signal_names = sig_map.get(direction, sig_map.get("neutral", []))

    if not signal_names:
        return None

    all_trades: list[BacktestTrade] = []
    for sig_name in signal_names:
        try:
            result = backtest_signal(symbol, df, sig_name, hold_days)
            all_trades.extend(result.trades)
        except Exception:
            continue

    if not all_trades:
        return None

    # Deduplicate trades on same date (different signals may trigger same day)
    seen_dates = set()
    unique_trades = []
    for t in sorted(all_trades, key=lambda t: t.entry_date):
        if t.entry_date not in seen_dates:
            seen_dates.add(t.entry_date)
            unique_trades.append(t)

    wins = [t for t in unique_trades if t.outcome == "win"]
    losses = [t for t in unique_trades if t.outcome == "loss"]
    returns = [t.pnl_percent for t in unique_trades]

    return {
        "total": len(unique_trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / len(unique_trades) * 100, 1) if unique_trades else 0,
        "avg_return": round(sum(returns) / len(returns), 2) if returns else 0,
        "best": round(max(returns), 2) if returns else 0,
        "worst": round(min(returns), 2) if returns else 0,
        "hold_days": hold_days,
        "trades": unique_trades,
        "signals_used": signal_names,
    }


# --- Indicator computation ---

def _compute_indicators(close: pd.Series, high: pd.Series, low: pd.Series, volume: pd.Series) -> dict:
    return {
        "rsi": ta.momentum.RSIIndicator(close, window=14).rsi(),
        "macd": ta.trend.MACD(close).macd(),
        "macd_signal": ta.trend.MACD(close).macd_signal(),
        "macd_hist": ta.trend.MACD(close).macd_diff(),
        "sma20": ta.trend.SMAIndicator(close, window=20).sma_indicator(),
        "sma50": ta.trend.SMAIndicator(close, window=50).sma_indicator(),
        "sma200": ta.trend.SMAIndicator(close, window=200).sma_indicator(),
        "bb_upper": ta.volatility.BollingerBands(close).bollinger_hband(),
        "bb_lower": ta.volatility.BollingerBands(close).bollinger_lband(),
        "vol_avg20": volume.rolling(20).mean(),
        "low_20": low.rolling(20).min(),
        "high_20": high.rolling(20).max(),
    }


def _backtest_event_signal(symbol: str, df: pd.DataFrame, signal_name: str, hold_days: int) -> BacktestResult:
    """Backtest event-based signals (earnings, VIX, insider, congress, analyst)."""
    df = df.copy().reset_index(drop=True)
    close = df["close"].astype(float)
    dates = df["date"].astype(str).tolist()
    date_to_idx = {d: i for i, d in enumerate(dates)}

    direction = SIGNALS[signal_name]["direction"]
    event_dates = _get_event_dates(symbol, signal_name, dates)

    trades: list[BacktestTrade] = []
    used_dates = set()

    for event_date in event_dates:
        # Find the closest trading day on or after the event date
        entry_idx = None
        for offset in range(0, 5):  # Look up to 5 days forward for a match
            check_date = event_date  # Simple string comparison works for YYYY-MM-DD
            if event_date in date_to_idx:
                entry_idx = date_to_idx[event_date]
                break
            # Try next day — increment date
            try:
                from datetime import datetime as dt, timedelta
                d = dt.strptime(event_date, "%Y-%m-%d") + timedelta(days=offset)
                check = d.strftime("%Y-%m-%d")
                if check in date_to_idx:
                    entry_idx = date_to_idx[check]
                    break
            except Exception:
                break

        if entry_idx is None or entry_idx in used_dates:
            continue

        exit_idx = min(entry_idx + hold_days, len(df) - 1)
        if exit_idx <= entry_idx:
            continue

        entry_price = float(close.iloc[entry_idx])
        exit_price = float(close.iloc[exit_idx])

        if direction == "buy":
            pnl = exit_price - entry_price
        else:
            pnl = entry_price - exit_price
        pnl_pct = (pnl / entry_price) * 100 if entry_price > 0 else 0

        trades.append(BacktestTrade(
            symbol=symbol, signal_name=signal_name, direction=direction,
            entry_date=dates[entry_idx], entry_price=round(entry_price, 2),
            exit_date=dates[exit_idx], exit_price=round(exit_price, 2),
            pnl=round(pnl, 2), pnl_percent=round(pnl_pct, 2),
            hold_days=exit_idx - entry_idx,
            outcome="win" if pnl > 0 else "loss",
        ))
        used_dates.add(entry_idx)

    return _build_result(symbol, signal_name, hold_days, len(df), trades)


def _get_event_dates(symbol: str, signal_name: str, available_dates: list[str]) -> list[str]:
    """Fetch event dates for non-technical signals. Returns list of YYYY-MM-DD strings."""

    if signal_name in ("earnings_beat", "earnings_miss"):
        return _get_earnings_event_dates(symbol, signal_name)

    if signal_name in ("vix_low", "vix_high", "vix_spike"):
        return _get_vix_event_dates(signal_name, available_dates)

    if signal_name in ("insider_buy", "insider_sell"):
        return _get_insider_event_dates(symbol, signal_name)

    if signal_name in ("congress_buy", "congress_sell"):
        return _get_congress_event_dates(symbol, signal_name)

    if signal_name in ("analyst_upgrade_momentum", "analyst_downgrade_momentum"):
        return _get_analyst_event_dates(symbol, signal_name)

    if signal_name in ("news_bullish_spike", "news_bearish_spike"):
        return _get_news_event_dates(symbol, signal_name, available_dates)

    if signal_name in ("options_bullish", "options_bearish"):
        return _get_options_event_dates(symbol, signal_name, available_dates)

    if signal_name in ("community_bullish", "community_bearish"):
        return _get_community_event_dates(symbol, signal_name)

    if signal_name in ("institutions_accumulating", "institutions_distributing"):
        return _get_institutional_event_dates(symbol, signal_name)

    if signal_name == "geopolitical_risk_spike":
        return _get_geopolitical_event_dates(symbol, available_dates)

    if signal_name == "disruption_tailwind":
        return _get_disruption_event_dates(symbol)

    return []


def _get_earnings_event_dates(symbol: str, signal_name: str) -> list[str]:
    """Get dates when earnings beat or missed estimates."""
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        ed = ticker.earnings_dates
        if ed is None or ed.empty:
            return []

        dates = []
        for date_idx, row in ed.iterrows():
            eps_est = row.get("EPS Estimate")
            eps_act = row.get("Reported EPS")
            if eps_est is None or eps_act is None:
                continue
            if str(eps_est) == "nan" or str(eps_act) == "nan":
                continue

            beat = float(eps_act) > float(eps_est)
            miss = float(eps_act) < float(eps_est)
            date_str = date_idx.strftime("%Y-%m-%d") if hasattr(date_idx, "strftime") else str(date_idx)[:10]

            if signal_name == "earnings_beat" and beat:
                dates.append(date_str)
            elif signal_name == "earnings_miss" and miss:
                dates.append(date_str)

        return dates
    except Exception:
        return []


def _get_vix_event_dates(signal_name: str, available_dates: list[str]) -> list[str]:
    """Get dates when VIX crossed thresholds."""
    try:
        import yfinance as yf
        # Fetch VIX history covering the same period as the stock
        vix = yf.download("^VIX", period="2y", progress=False, auto_adjust=True)
        if vix is None or vix.empty:
            return []
        if hasattr(vix.columns, "levels") and vix.columns.nlevels > 1:
            vix.columns = vix.columns.get_level_values(0)

        vix = vix.reset_index()
        vix["date_str"] = vix["Date"].dt.strftime("%Y-%m-%d")
        avail_set = set(available_dates)

        dates = []
        vix_close = vix["Close"].astype(float)

        for i in range(1, len(vix)):
            d = vix["date_str"].iloc[i]
            if d not in avail_set:
                continue
            val = float(vix_close.iloc[i])
            prev = float(vix_close.iloc[i - 1])

            if signal_name == "vix_low" and val < 20 and prev >= 20:
                dates.append(d)
            elif signal_name == "vix_high" and val > 30 and prev <= 30:
                dates.append(d)
            elif signal_name == "vix_spike" and prev > 0:
                change = (val - prev) / prev
                if change > 0.20:
                    dates.append(d)

        return dates
    except Exception:
        return []


def _get_insider_event_dates(symbol: str, signal_name: str) -> list[str]:
    """Get dates when insiders bought or sold."""
    try:
        from src.utils.db import cache_get
        cached = cache_get(f"sec:insider:{symbol}:365")
        if not cached or not isinstance(cached, list):
            # Try fetching fresh
            try:
                import yfinance as yf
                ticker = yf.Ticker(symbol)
                insider = ticker.insider_transactions
                if insider is not None and not insider.empty:
                    dates = []
                    for _, row in insider.iterrows():
                        txn = str(row.get("Transaction", "")).lower()
                        date_val = row.get("Start Date")
                        if date_val is None:
                            continue
                        date_str = date_val.strftime("%Y-%m-%d") if hasattr(date_val, "strftime") else str(date_val)[:10]
                        if signal_name == "insider_buy" and ("purchase" in txn or "buy" in txn or "acquisition" in txn):
                            dates.append(date_str)
                        elif signal_name == "insider_sell" and ("sale" in txn or "sell" in txn or "disposition" in txn):
                            dates.append(date_str)
                    return dates
            except Exception:
                pass
            return []

        dates = []
        for trade in cached:
            txn_type = trade.get("transaction_type", "").lower()
            date_str = trade.get("date", "")[:10]
            if not date_str:
                continue
            if signal_name == "insider_buy" and txn_type == "buy":
                dates.append(date_str)
            elif signal_name == "insider_sell" and txn_type == "sell":
                dates.append(date_str)
        return dates
    except Exception:
        return []


def _get_congress_event_dates(symbol: str, signal_name: str) -> list[str]:
    """Get dates when congress members bought or sold."""
    try:
        from src.utils.db import cache_get
        cached = cache_get(f"congress:{symbol}")
        if not cached or not isinstance(cached, dict):
            return []

        trades = cached.get("trades", [])
        dates = []
        for trade in trades:
            txn_type = trade.get("type", "").lower()
            date_str = trade.get("trade_date", "")[:10]
            if not date_str:
                date_str = trade.get("date", "")[:10]
            if not date_str:
                continue
            if signal_name == "congress_buy" and ("purchase" in txn_type or "buy" in txn_type):
                dates.append(date_str)
            elif signal_name == "congress_sell" and ("sale" in txn_type or "sell" in txn_type):
                dates.append(date_str)
        return dates
    except Exception:
        return []


def _get_analyst_event_dates(symbol: str, signal_name: str) -> list[str]:
    """Get approximate dates when analyst consensus shifted."""
    try:
        import yfinance as yf
        from datetime import datetime as dt, timedelta

        ticker = yf.Ticker(symbol)
        recs = ticker.recommendations
        if recs is None or recs.empty or len(recs) < 2:
            return []

        dates = []
        now = dt.now()

        for i in range(len(recs) - 1):
            current = recs.iloc[i]
            prev = recs.iloc[i + 1]

            curr_bull = int(current.get("strongBuy", 0)) + int(current.get("buy", 0))
            prev_bull = int(prev.get("strongBuy", 0)) + int(prev.get("buy", 0))
            curr_bear = int(current.get("sell", 0)) + int(current.get("strongSell", 0))
            prev_bear = int(prev.get("sell", 0)) + int(prev.get("strongSell", 0))

            # Approximate date: period column is "0m", "-1m", "-2m" etc.
            period = current.get("period", "0m")
            try:
                months_ago = abs(int(str(period).replace("m", "")))
            except (ValueError, TypeError):
                months_ago = i
            approx_date = (now - timedelta(days=months_ago * 30)).strftime("%Y-%m-%d")

            if signal_name == "analyst_upgrade_momentum" and curr_bull > prev_bull and curr_bear <= prev_bear:
                dates.append(approx_date)
            elif signal_name == "analyst_downgrade_momentum" and curr_bear > prev_bear:
                dates.append(approx_date)

        return dates
    except Exception:
        return []


def _get_news_event_dates(symbol: str, signal_name: str, available_dates: list[str]) -> list[str]:
    """Get dates when news sentiment spiked bullish or bearish via Tavily."""
    try:
        import httpx
        from src.utils.config import TAVILY_API_KEY
        from datetime import datetime as dt, timedelta

        if not TAVILY_API_KEY:
            return []

        bullish_words = {"surge", "beat", "upgrade", "rally", "buy", "bull", "record", "growth", "positive"}
        bearish_words = {"crash", "miss", "downgrade", "sell", "bear", "decline", "loss", "negative", "warning"}

        dates = []
        now = dt.now()

        # Search by quarter (4 calls) to stay within rate limits
        for months_back in [0, 3, 6, 9]:
            end = now - timedelta(days=months_back * 30)
            start = end - timedelta(days=90)

            try:
                resp = httpx.post(
                    "https://api.tavily.com/search",
                    json={
                        "query": f"{symbol} stock news sentiment",
                        "api_key": TAVILY_API_KEY,
                        "max_results": 5,
                        "search_depth": "basic",
                        "start_date": start.strftime("%Y-%m-%d"),
                        "end_date": end.strftime("%Y-%m-%d"),
                    },
                    timeout=15,
                )
                results = resp.json().get("results", [])

                bull = sum(1 for r in results if any(w in (r.get("title", "") + r.get("content", "")).lower() for w in bullish_words))
                bear = sum(1 for r in results if any(w in (r.get("title", "") + r.get("content", "")).lower() for w in bearish_words))
                total = len(results)

                if total >= 3:
                    mid_date = (start + timedelta(days=45)).strftime("%Y-%m-%d")
                    if signal_name == "news_bullish_spike" and bull / total >= 0.7:
                        dates.append(mid_date)
                    elif signal_name == "news_bearish_spike" and bear / total >= 0.7:
                        dates.append(mid_date)
            except Exception:
                continue

        return dates
    except Exception:
        return []


def _get_options_event_dates(symbol: str, signal_name: str, available_dates: list[str]) -> list[str]:
    """Get dates when options P/C ratio crossed thresholds via Polygon."""
    try:
        import httpx
        from src.utils.config import POLYGON_API_KEY
        from datetime import datetime as dt, timedelta

        if not POLYGON_API_KEY:
            return []

        dates = []
        avail_set = set(available_dates)

        # Sample monthly — Polygon free tier is limited
        now = dt.now()
        for months_back in range(0, 12):
            check_date = (now - timedelta(days=months_back * 30)).strftime("%Y-%m-%d")

            try:
                resp = httpx.get(
                    f"https://api.polygon.io/v3/snapshot/options/{symbol}",
                    params={"apiKey": POLYGON_API_KEY, "limit": 50},
                    timeout=15,
                )
                data = resp.json().get("results", [])
                if not data:
                    continue

                calls = sum(1 for d in data if d.get("details", {}).get("contract_type") == "call")
                puts = sum(1 for d in data if d.get("details", {}).get("contract_type") == "put")

                if calls > 0:
                    pcr = puts / calls
                    # Find nearest available date
                    for d in available_dates:
                        if d <= check_date:
                            if signal_name == "options_bullish" and pcr < 0.7:
                                dates.append(d)
                            elif signal_name == "options_bearish" and pcr > 1.3:
                                dates.append(d)
                            break
            except Exception:
                continue

            import time
            time.sleep(0.5)  # Rate limit: Polygon free tier

        return dates
    except Exception:
        return []


def _get_community_event_dates(symbol: str, signal_name: str) -> list[str]:
    """Get dates when community sentiment spiked via Exa historical search."""
    try:
        import httpx
        from src.utils.config import EXA_API_KEY
        from datetime import datetime as dt, timedelta

        if not EXA_API_KEY:
            return []

        bullish_words = {"buy", "bull", "moon", "calls", "long", "undervalued", "beat", "squeeze"}
        bearish_words = {"sell", "bear", "puts", "short", "crash", "overvalued", "dump", "miss"}

        dates = []
        now = dt.now()

        # Search by quarter
        for months_back in [0, 3, 6, 9]:
            end = now - timedelta(days=months_back * 30)
            start = end - timedelta(days=90)

            try:
                resp = httpx.post(
                    "https://api.exa.ai/search",
                    headers={"x-api-key": EXA_API_KEY},
                    json={
                        "query": f"{symbol} stock reddit discussion sentiment buy sell",
                        "type": "auto",
                        "num_results": 8,
                        "contents": {"highlights": {"max_characters": 200}},
                        "publishedAfter": start.strftime("%Y-%m-%dT00:00:00Z"),
                        "publishedBefore": end.strftime("%Y-%m-%dT00:00:00Z"),
                    },
                    timeout=15,
                )
                results = resp.json().get("results", [])

                bull = 0
                bear = 0
                for r in results:
                    text = (r.get("title", "") + " " + " ".join(r.get("highlights", []))).lower()
                    if any(w in text for w in bullish_words):
                        bull += 1
                    if any(w in text for w in bearish_words):
                        bear += 1

                total = len(results)
                if total >= 3:
                    mid_date = (start + timedelta(days=45)).strftime("%Y-%m-%d")
                    if signal_name == "community_bullish" and bull / total >= 0.6:
                        dates.append(mid_date)
                    elif signal_name == "community_bearish" and bear / total >= 0.6:
                        dates.append(mid_date)
            except Exception:
                continue

        return dates
    except Exception:
        return []


def _get_institutional_event_dates(symbol: str, signal_name: str) -> list[str]:
    """Get approximate quarterly dates when institutional ownership changed."""
    try:
        import yfinance as yf
        from datetime import datetime as dt, timedelta

        ticker = yf.Ticker(symbol)
        ih = ticker.institutional_holders
        if ih is None or ih.empty:
            return []

        dates = []
        for _, row in ih.iterrows():
            pct_change = float(row.get("pctChange", 0))
            date_val = row.get("Date Reported")
            if date_val is None:
                continue
            date_str = date_val.strftime("%Y-%m-%d") if hasattr(date_val, "strftime") else str(date_val)[:10]

            if signal_name == "institutions_accumulating" and pct_change > 0.01:
                dates.append(date_str)
            elif signal_name == "institutions_distributing" and pct_change < -0.01:
                dates.append(date_str)

        # Deduplicate to one date per quarter
        seen_quarters = set()
        unique = []
        for d in dates:
            q = d[:7]  # YYYY-MM
            if q not in seen_quarters:
                seen_quarters.add(q)
                unique.append(d)

        return unique
    except Exception:
        return []


def _get_geopolitical_event_dates(symbol: str, available_dates: list[str]) -> list[str]:
    """Get dates when major geopolitical events affected markets via Tavily."""
    try:
        import httpx
        from src.utils.config import TAVILY_API_KEY
        from datetime import datetime as dt, timedelta

        if not TAVILY_API_KEY:
            return []

        # Get stock's sector for relevance
        sector = ""
        try:
            import yfinance as yf
            info = yf.Ticker(symbol).info
            sector = info.get("sector", "")
        except Exception:
            pass

        dates = []
        now = dt.now()
        event_queries = [
            f"tariff trade war impact {sector or 'stocks'} market",
            f"war sanctions military impact {sector or 'stocks'} market",
        ]

        for months_back in [0, 6]:
            end = now - timedelta(days=months_back * 30)
            start = end - timedelta(days=180)

            for query in event_queries:
                try:
                    resp = httpx.post(
                        "https://api.tavily.com/search",
                        json={
                            "query": query,
                            "api_key": TAVILY_API_KEY,
                            "max_results": 3,
                            "search_depth": "basic",
                            "start_date": start.strftime("%Y-%m-%d"),
                            "end_date": end.strftime("%Y-%m-%d"),
                        },
                        timeout=15,
                    )
                    results = resp.json().get("results", [])
                    severity_words = ["escalat", "retaliat", "sanction", "tariff", "invasion", "strike"]
                    for r in results:
                        text = (r.get("title", "") + " " + r.get("content", "")[:100]).lower()
                        if any(w in text for w in severity_words):
                            # Approximate date from published or mid-period
                            mid_date = (start + timedelta(days=90)).strftime("%Y-%m-%d")
                            dates.append(mid_date)
                            break
                except Exception:
                    continue

        return list(set(dates))
    except Exception:
        return []


def _get_disruption_event_dates(symbol: str) -> list[str]:
    """Get dates when disruption themes accelerated for this stock's sector."""
    try:
        import httpx
        from src.utils.config import EXA_API_KEY
        from datetime import datetime as dt, timedelta

        if not EXA_API_KEY:
            return []

        # Get sector
        sector = ""
        try:
            import yfinance as yf
            info = yf.Ticker(symbol).info
            sector = info.get("sector", "") or info.get("industry", "")
        except Exception:
            pass

        if not sector:
            return []

        dates = []
        now = dt.now()

        # Search quarterly for disruption acceleration
        for months_back in [0, 3, 6, 9]:
            end = now - timedelta(days=months_back * 30)
            start = end - timedelta(days=90)

            try:
                resp = httpx.post(
                    "https://api.exa.ai/search",
                    headers={"x-api-key": EXA_API_KEY},
                    json={
                        "query": f"{sector} disruption technology transformation impact stocks",
                        "type": "auto",
                        "num_results": 5,
                        "publishedAfter": start.strftime("%Y-%m-%dT00:00:00Z"),
                        "publishedBefore": end.strftime("%Y-%m-%dT00:00:00Z"),
                    },
                    timeout=15,
                )
                results = resp.json().get("results", [])
                accel_words = {"revolution", "transform", "disrupt", "surge", "dominat", "trillion", "breakout", "paradigm"}
                hits = sum(1 for r in results if any(w in (r.get("title", "")).lower() for w in accel_words))

                if hits >= 2:
                    mid_date = (start + timedelta(days=45)).strftime("%Y-%m-%d")
                    dates.append(mid_date)
            except Exception:
                continue

        return dates
    except Exception:
        return []


def _detect_signal(signal_name: str, df: pd.DataFrame, ind: dict) -> list[int]:
    """Return list of row indices where the signal triggers."""
    close = df["close"].astype(float)
    volume = df["volume"].astype(float)
    triggers = []

    for i in range(1, len(df)):
        triggered = False

        if signal_name == "rsi_oversold":
            triggered = _valid(ind["rsi"], i) and ind["rsi"].iloc[i] < 30

        elif signal_name == "rsi_overbought":
            triggered = _valid(ind["rsi"], i) and ind["rsi"].iloc[i] > 70

        elif signal_name == "macd_bullish":
            triggered = (_valid(ind["macd_hist"], i) and _valid(ind["macd_hist"], i-1)
                         and ind["macd_hist"].iloc[i] > 0 and ind["macd_hist"].iloc[i-1] <= 0)

        elif signal_name == "macd_bearish":
            triggered = (_valid(ind["macd_hist"], i) and _valid(ind["macd_hist"], i-1)
                         and ind["macd_hist"].iloc[i] < 0 and ind["macd_hist"].iloc[i-1] >= 0)

        elif signal_name == "sma50_cross_up":
            triggered = (_valid(ind["sma50"], i) and _valid(ind["sma50"], i-1)
                         and close.iloc[i] > ind["sma50"].iloc[i]
                         and close.iloc[i-1] <= ind["sma50"].iloc[i-1])

        elif signal_name == "sma50_cross_down":
            triggered = (_valid(ind["sma50"], i) and _valid(ind["sma50"], i-1)
                         and close.iloc[i] < ind["sma50"].iloc[i]
                         and close.iloc[i-1] >= ind["sma50"].iloc[i-1])

        elif signal_name == "sma200_cross_up":
            triggered = (_valid(ind["sma200"], i) and _valid(ind["sma200"], i-1)
                         and close.iloc[i] > ind["sma200"].iloc[i]
                         and close.iloc[i-1] <= ind["sma200"].iloc[i-1])

        elif signal_name == "golden_cross":
            triggered = (_valid(ind["sma50"], i) and _valid(ind["sma200"], i)
                         and _valid(ind["sma50"], i-1) and _valid(ind["sma200"], i-1)
                         and ind["sma50"].iloc[i] > ind["sma200"].iloc[i]
                         and ind["sma50"].iloc[i-1] <= ind["sma200"].iloc[i-1])

        elif signal_name == "death_cross":
            triggered = (_valid(ind["sma50"], i) and _valid(ind["sma200"], i)
                         and _valid(ind["sma50"], i-1) and _valid(ind["sma200"], i-1)
                         and ind["sma50"].iloc[i] < ind["sma200"].iloc[i]
                         and ind["sma50"].iloc[i-1] >= ind["sma200"].iloc[i-1])

        elif signal_name == "bb_lower_touch":
            triggered = (_valid(ind["bb_lower"], i) and close.iloc[i] <= ind["bb_lower"].iloc[i])

        elif signal_name == "bb_upper_touch":
            triggered = (_valid(ind["bb_upper"], i) and close.iloc[i] >= ind["bb_upper"].iloc[i])

        elif signal_name == "volume_spike":
            triggered = (_valid(ind["vol_avg20"], i) and ind["vol_avg20"].iloc[i] > 0
                         and volume.iloc[i] > ind["vol_avg20"].iloc[i] * 2)

        elif signal_name == "support_bounce":
            triggered = (_valid(ind["low_20"], i) and ind["low_20"].iloc[i] > 0
                         and close.iloc[i] <= ind["low_20"].iloc[i] * 1.02)

        elif signal_name == "resistance_rejection":
            triggered = (_valid(ind["high_20"], i) and ind["high_20"].iloc[i] > 0
                         and close.iloc[i] >= ind["high_20"].iloc[i] * 0.98)

        if triggered:
            triggers.append(i)

    return triggers


def _valid(series: pd.Series, idx: int) -> bool:
    return not pd.isna(series.iloc[idx])


def _build_result(symbol: str, signal_name: str, hold_days: int,
                   lookback_days: int, trades: list[BacktestTrade]) -> BacktestResult:
    if not trades:
        return BacktestResult(
            symbol=symbol, signal_name=signal_name, hold_days=hold_days,
            lookback_days=lookback_days, total_trades=0, wins=0, losses=0,
            win_rate=0.0, avg_return=0.0, total_return=0.0,
            max_gain=0.0, max_loss=0.0, max_drawdown=0.0, sharpe_ratio=0.0,
            trades=[],
        )

    wins = sum(1 for t in trades if t.outcome == "win")
    losses = len(trades) - wins
    returns = [t.pnl_percent for t in trades]

    avg_ret = sum(returns) / len(returns)
    total_ret = sum(returns)
    max_gain = max(returns)
    max_loss = min(returns)

    # Max drawdown from cumulative returns
    cumulative = np.cumsum(returns)
    peak = np.maximum.accumulate(cumulative)
    drawdowns = cumulative - peak
    max_dd = float(min(drawdowns)) if len(drawdowns) > 0 else 0.0

    # Sharpe ratio (annualized, assuming ~12 trades/year)
    if len(returns) > 1 and np.std(returns) > 0:
        sharpe = (avg_ret / np.std(returns)) * math.sqrt(min(len(returns), 12))
    else:
        sharpe = 0.0

    return BacktestResult(
        symbol=symbol, signal_name=signal_name, hold_days=hold_days,
        lookback_days=lookback_days, total_trades=len(trades),
        wins=wins, losses=losses,
        win_rate=round(wins / len(trades), 4),
        avg_return=round(avg_ret, 4),
        total_return=round(total_ret, 4),
        max_gain=round(max_gain, 4),
        max_loss=round(max_loss, 4),
        max_drawdown=round(max_dd, 4),
        sharpe_ratio=round(sharpe, 4),
        trades=trades,
    )
