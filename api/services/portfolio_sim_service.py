"""Portfolio simulation: multi-stock signal-driven backtest.

Wraps `src/analysis/portfolio_sim.simulate_portfolio` with HTTP-friendly inputs.
"""
from __future__ import annotations

from datetime import datetime
from src.analysis.portfolio_sim import simulate_portfolio
from src.data.gateway import DataGateway


def run_portfolio_simulation(
    symbols: list[str],
    strategy: str,
    initial_capital: float = 100000.0,
    position_size_pct: float = 0.20,
    period_days: int = 730,
) -> dict:
    syms = [s.upper().strip() for s in symbols if s.strip()]
    syms = list(dict.fromkeys(syms))[:12]
    if not syms:
        return {"error": "Need at least one symbol", "rows": [], "equity_curve": []}

    gw = DataGateway()
    historical: dict = {}
    for s in syms:
        try:
            h = gw.get_historical(s, period_days=period_days)
            if h is not None and not h.empty:
                historical[s] = h
        except Exception:
            continue
    try:
        bench = gw.get_historical("SPY", period_days=period_days)
    except Exception:
        bench = None

    if not historical or bench is None or bench.empty:
        return {"error": "Not enough historical data", "rows": [], "equity_curve": []}

    try:
        result = simulate_portfolio(
            symbols=list(historical.keys()),
            historical_data=historical,
            benchmark_data=bench,
            strategy=strategy,
            initial_capital=initial_capital,
            position_size_pct=position_size_pct,
        )
    except Exception as e:
        return {"error": f"Simulation failed: {e}", "rows": [], "equity_curve": []}

    equity_curve = []
    for s in (result.equity_curve or []):
        equity_curve.append({
            "date": s.date,
            "total_value": float(s.total_value),
            "cash": float(s.cash),
            "invested": float(s.invested),
            "daily_return": float(s.daily_return),
            "cumulative_return": float(s.cumulative_return),
            "benchmark_return": float(s.benchmark_return),
        })

    trades = []
    for t in (result.closed_trades or [])[:200]:
        trades.append({
            "symbol": t.symbol,
            "entry_date": str(t.entry_date),
            "entry_price": float(t.entry_price),
            "exit_date": str(t.exit_date),
            "exit_price": float(t.exit_price),
            "pnl_percent": float(t.pnl_percent),
            "hold_days": int(t.hold_days),
            "outcome": str(t.outcome),
        })

    best = result.best_trade
    worst = result.worst_trade

    return {
        "strategy": result.strategy,
        "symbols": list(historical.keys()),
        "initial_capital": float(result.initial_capital),
        "final_value": float(result.final_value),
        "total_return": float(result.total_return),
        "annualized_return": float(result.annualized_return),
        "sharpe_ratio": float(result.sharpe_ratio),
        "max_drawdown": float(result.max_drawdown),
        "win_rate": float(result.win_rate),
        "total_trades": int(result.total_trades),
        "alpha": float(result.alpha),
        "best_trade": {
            "symbol": best.symbol, "pnl_percent": float(best.pnl_percent),
            "entry_date": str(best.entry_date), "exit_date": str(best.exit_date),
        } if best else None,
        "worst_trade": {
            "symbol": worst.symbol, "pnl_percent": float(worst.pnl_percent),
            "entry_date": str(worst.entry_date), "exit_date": str(worst.exit_date),
        } if worst else None,
        "equity_curve": equity_curve,
        "trades": trades,
        "last_updated": datetime.utcnow().isoformat() + "Z",
    }
