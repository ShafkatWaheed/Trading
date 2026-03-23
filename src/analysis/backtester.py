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
    "rsi_oversold": {"direction": "buy", "description": "RSI < 30 (oversold bounce)"},
    "rsi_overbought": {"direction": "sell", "description": "RSI > 70 (overbought)"},
    "macd_bullish": {"direction": "buy", "description": "MACD crosses above signal"},
    "macd_bearish": {"direction": "sell", "description": "MACD crosses below signal"},
    "sma50_cross_up": {"direction": "buy", "description": "Price crosses above SMA(50)"},
    "sma50_cross_down": {"direction": "sell", "description": "Price crosses below SMA(50)"},
    "sma200_cross_up": {"direction": "buy", "description": "Price crosses above SMA(200)"},
    "golden_cross": {"direction": "buy", "description": "SMA(50) crosses above SMA(200)"},
    "death_cross": {"direction": "sell", "description": "SMA(50) crosses below SMA(200)"},
    "bb_lower_touch": {"direction": "buy", "description": "Price touches lower Bollinger Band"},
    "bb_upper_touch": {"direction": "sell", "description": "Price touches upper Bollinger Band"},
    "volume_spike": {"direction": "buy", "description": "Volume > 2x 20-day average"},
    "support_bounce": {"direction": "buy", "description": "Price near 20-day low"},
    "resistance_rejection": {"direction": "sell", "description": "Price near 20-day high"},
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
