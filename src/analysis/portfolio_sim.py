"""Portfolio simulation engine: multi-stock strategy backtesting.

Pure computation — receives historical DataFrames, returns PortfolioResult.
No I/O, no API calls, no database access.
"""

import math

import numpy as np
import pandas as pd

from src.analysis.backtester import SIGNALS, _compute_indicators, _detect_signal
from src.models.backtest_types import (
    BacktestTrade,
    PortfolioPosition,
    PortfolioResult,
    PortfolioSnapshot,
)


def simulate_portfolio(
    symbols: list[str],
    historical_data: dict[str, pd.DataFrame],  # symbol -> OHLCV DataFrame
    benchmark_data: pd.DataFrame,               # SPY OHLCV
    strategy: str = "rsi_oversold",             # signal name from backtester.SIGNALS
    initial_capital: float = 100000.0,
    position_size_pct: float = 0.2,             # 20% per position
) -> PortfolioResult:
    """Simulate a multi-stock portfolio driven by a single signal strategy.

    Walks through each trading day, opens positions when signals trigger,
    closes after 30 days or on an opposite signal, and tracks equity vs benchmark.
    """
    if strategy not in SIGNALS:
        raise ValueError(f"Unknown strategy: {strategy}. Choose from: {list(SIGNALS.keys())}")

    if not symbols or not historical_data:
        return _empty_result(strategy, initial_capital)

    # --- 1. Align all DataFrames to the same date range ---
    aligned, bench, dates = _align_data(symbols, historical_data, benchmark_data)
    if len(dates) < 2:
        return _empty_result(strategy, initial_capital)

    # --- 2. Pre-compute indicators and signal triggers per symbol ---
    signal_sets: dict[str, set[int]] = {}
    opposite_sets: dict[str, set[int]] = {}
    opposite_name = _get_opposite_signal(strategy)

    for sym in aligned:
        df = aligned[sym]
        close = df["close"].astype(float)
        high = df["high"].astype(float)
        low = df["low"].astype(float)
        volume = df["volume"].astype(float)
        ind = _compute_indicators(close, high, low, volume)

        signal_sets[sym] = set(_detect_signal(strategy, df, ind))
        if opposite_name:
            opposite_sets[sym] = set(_detect_signal(opposite_name, df, ind))
        else:
            opposite_sets[sym] = set()

    # --- 3. Walk through each trading day ---
    cash = initial_capital
    positions: dict[str, _OpenPosition] = {}  # symbol -> open position info
    closed_trades: list[BacktestTrade] = []
    equity_curve: list[PortfolioSnapshot] = []
    direction = SIGNALS[strategy]["direction"]

    bench_start = float(bench["close"].iloc[0])
    prev_total = initial_capital

    for day_idx in range(len(dates)):
        date_str = str(dates[day_idx])

        # Check for exits first (30-day hold or opposite signal)
        symbols_to_close = []
        for sym, pos in positions.items():
            hold_days = day_idx - pos.entry_idx
            opposite_fired = day_idx in opposite_sets.get(sym, set())
            if hold_days >= 30 or opposite_fired:
                symbols_to_close.append(sym)

        for sym in symbols_to_close:
            pos = positions.pop(sym)
            exit_price = float(aligned[sym]["close"].iloc[day_idx])
            trade = _close_position(pos, exit_price, date_str, day_idx, direction, strategy)
            closed_trades.append(trade)
            cash += exit_price * pos.shares

        # Check for entries (signal fires, we have cash, no existing position)
        for sym in aligned:
            if sym in positions:
                continue
            if day_idx not in signal_sets.get(sym, set()):
                continue

            alloc = initial_capital * position_size_pct
            if cash < alloc * 0.1:  # not enough cash (less than 10% of target alloc)
                continue

            entry_price = float(aligned[sym]["close"].iloc[day_idx])
            if entry_price <= 0:
                continue

            spend = min(alloc, cash)
            shares = int(spend / entry_price)
            if shares <= 0:
                continue

            cost = shares * entry_price
            cash -= cost
            positions[sym] = _OpenPosition(
                symbol=sym,
                shares=shares,
                entry_price=entry_price,
                entry_date=date_str,
                entry_idx=day_idx,
            )

        # Compute portfolio value
        invested = 0.0
        for sym, pos in positions.items():
            current_price = float(aligned[sym]["close"].iloc[day_idx])
            invested += current_price * pos.shares

        total_value = cash + invested
        daily_return = (total_value - prev_total) / prev_total if prev_total > 0 else 0.0
        cumulative_return = (total_value - initial_capital) / initial_capital
        bench_price = float(bench["close"].iloc[day_idx])
        benchmark_return = (bench_price - bench_start) / bench_start

        equity_curve.append(PortfolioSnapshot(
            date=date_str,
            total_value=round(total_value, 2),
            cash=round(cash, 2),
            invested=round(invested, 2),
            daily_return=round(daily_return, 6),
            cumulative_return=round(cumulative_return, 6),
            benchmark_return=round(benchmark_return, 6),
        ))
        prev_total = total_value

    # --- 4. Force-close any remaining positions on the last day ---
    last_idx = len(dates) - 1
    last_date = str(dates[last_idx])
    for sym, pos in positions.items():
        exit_price = float(aligned[sym]["close"].iloc[last_idx])
        trade = _close_position(pos, exit_price, last_date, last_idx, direction, strategy)
        closed_trades.append(trade)

    # --- 5. Compute summary statistics ---
    return _build_portfolio_result(
        strategy=strategy,
        initial_capital=initial_capital,
        equity_curve=equity_curve,
        closed_trades=closed_trades,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

class _OpenPosition:
    """Lightweight tracker for an open position during simulation."""

    __slots__ = ("symbol", "shares", "entry_price", "entry_date", "entry_idx")

    def __init__(self, symbol: str, shares: int, entry_price: float,
                 entry_date: str, entry_idx: int) -> None:
        self.symbol = symbol
        self.shares = shares
        self.entry_price = entry_price
        self.entry_date = entry_date
        self.entry_idx = entry_idx


def _get_opposite_signal(strategy: str) -> str | None:
    """Return the opposite signal name, or None if no natural opposite exists."""
    opposites = {
        "rsi_oversold": "rsi_overbought",
        "rsi_overbought": "rsi_oversold",
        "macd_bullish": "macd_bearish",
        "macd_bearish": "macd_bullish",
        "sma50_cross_up": "sma50_cross_down",
        "sma50_cross_down": "sma50_cross_up",
        "golden_cross": "death_cross",
        "death_cross": "golden_cross",
        "bb_lower_touch": "bb_upper_touch",
        "bb_upper_touch": "bb_lower_touch",
        "support_bounce": "resistance_rejection",
        "resistance_rejection": "support_bounce",
    }
    return opposites.get(strategy)


def _align_data(
    symbols: list[str],
    historical_data: dict[str, pd.DataFrame],
    benchmark_data: pd.DataFrame,
) -> tuple[dict[str, pd.DataFrame], pd.DataFrame, list]:
    """Align all DataFrames to the intersection of available dates."""
    # Collect date sets
    date_sets: list[set] = []
    valid_symbols: list[str] = []

    for sym in symbols:
        if sym not in historical_data or historical_data[sym].empty:
            continue
        df = historical_data[sym].copy()
        df["date"] = pd.to_datetime(df["date"])
        historical_data[sym] = df
        date_sets.append(set(df["date"].values))
        valid_symbols.append(sym)

    if not valid_symbols:
        return {}, pd.DataFrame(), []

    bench = benchmark_data.copy()
    bench["date"] = pd.to_datetime(bench["date"])
    date_sets.append(set(bench["date"].values))

    # Intersect all date sets
    common_dates = sorted(set.intersection(*date_sets))
    if len(common_dates) < 2:
        return {}, pd.DataFrame(), []

    common_set = set(common_dates)

    aligned: dict[str, pd.DataFrame] = {}
    for sym in valid_symbols:
        df = historical_data[sym]
        df = df[df["date"].isin(common_set)].sort_values("date").reset_index(drop=True)
        aligned[sym] = df

    bench = bench[bench["date"].isin(common_set)].sort_values("date").reset_index(drop=True)

    dates = [d for d in common_dates]
    return aligned, bench, dates


def _close_position(
    pos: _OpenPosition,
    exit_price: float,
    exit_date: str,
    exit_idx: int,
    direction: str,
    signal_name: str,
) -> BacktestTrade:
    """Create a BacktestTrade from a closed position."""
    if direction == "buy":
        pnl = (exit_price - pos.entry_price) * pos.shares
        pnl_pct = ((exit_price - pos.entry_price) / pos.entry_price) * 100 if pos.entry_price else 0.0
    else:
        pnl = (pos.entry_price - exit_price) * pos.shares
        pnl_pct = ((pos.entry_price - exit_price) / pos.entry_price) * 100 if pos.entry_price else 0.0

    hold_days = exit_idx - pos.entry_idx

    return BacktestTrade(
        symbol=pos.symbol,
        signal_name=signal_name,
        direction=direction,
        entry_date=pos.entry_date,
        entry_price=round(pos.entry_price, 2),
        exit_date=exit_date,
        exit_price=round(exit_price, 2),
        pnl=round(pnl, 2),
        pnl_percent=round(pnl_pct, 2),
        hold_days=hold_days,
        outcome="win" if pnl > 0 else "loss",
    )


def _build_portfolio_result(
    strategy: str,
    initial_capital: float,
    equity_curve: list[PortfolioSnapshot],
    closed_trades: list[BacktestTrade],
) -> PortfolioResult:
    """Compute final summary stats from the equity curve and trade list."""
    if not equity_curve:
        return _empty_result(strategy, initial_capital)

    final_value = equity_curve[-1].total_value
    total_return = (final_value - initial_capital) / initial_capital
    benchmark_final = equity_curve[-1].benchmark_return

    # Annualized return
    trading_days = len(equity_curve)
    years = trading_days / 252.0
    if years > 0 and final_value > 0:
        annualized_return = (final_value / initial_capital) ** (1.0 / years) - 1.0
    else:
        annualized_return = 0.0

    # Sharpe ratio from daily returns
    daily_returns = [s.daily_return for s in equity_curve]
    if len(daily_returns) > 1 and np.std(daily_returns) > 0:
        sharpe = (np.mean(daily_returns) / np.std(daily_returns)) * math.sqrt(252)
    else:
        sharpe = 0.0

    # Max drawdown from equity curve
    values = np.array([s.total_value for s in equity_curve])
    peak = np.maximum.accumulate(values)
    drawdowns = (values - peak) / peak
    max_drawdown = float(np.min(drawdowns)) if len(drawdowns) > 0 else 0.0

    # Win rate
    wins = sum(1 for t in closed_trades if t.outcome == "win")
    win_rate = wins / len(closed_trades) if closed_trades else 0.0

    # Alpha vs benchmark
    alpha = total_return - benchmark_final

    # Best / worst trades
    best_trade = max(closed_trades, key=lambda t: t.pnl_percent) if closed_trades else None
    worst_trade = min(closed_trades, key=lambda t: t.pnl_percent) if closed_trades else None

    return PortfolioResult(
        strategy=strategy,
        initial_capital=round(initial_capital, 2),
        final_value=round(final_value, 2),
        total_return=round(total_return, 6),
        annualized_return=round(annualized_return, 6),
        sharpe_ratio=round(float(sharpe), 4),
        max_drawdown=round(max_drawdown, 6),
        win_rate=round(win_rate, 4),
        total_trades=len(closed_trades),
        alpha=round(alpha, 6),
        best_trade=best_trade,
        worst_trade=worst_trade,
        equity_curve=equity_curve,
        closed_trades=closed_trades,
    )


def _empty_result(strategy: str, initial_capital: float) -> PortfolioResult:
    """Return a zeroed-out result when simulation cannot run."""
    return PortfolioResult(
        strategy=strategy,
        initial_capital=round(initial_capital, 2),
        final_value=round(initial_capital, 2),
        total_return=0.0,
        annualized_return=0.0,
        sharpe_ratio=0.0,
        max_drawdown=0.0,
        win_rate=0.0,
        total_trades=0,
        alpha=0.0,
    )
