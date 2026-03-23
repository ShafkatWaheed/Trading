"""Trade journal module for logging, closing, and analyzing trades."""

from datetime import datetime, timezone

from src.models.backtest_types import JournalStats, JournalTrade
from src.utils.db import (
    close_journal_trade,
    get_journal_trades,
    save_journal_trade,
)


def _row_to_journal_trade(row: dict) -> JournalTrade:
    """Convert a DB row dict to a JournalTrade dataclass."""
    return JournalTrade(
        id=row["id"],
        symbol=row["symbol"],
        direction=row["direction"],
        entry_date=row["entry_date"],
        entry_price=row["entry_price"],
        exit_date=row.get("exit_date"),
        exit_price=row.get("exit_price"),
        shares=row["shares"],
        pnl=row.get("pnl"),
        pnl_percent=row.get("pnl_percent"),
        report_verdict=row.get("report_verdict", ""),
        thesis=row.get("thesis", ""),
        notes=row.get("notes", ""),
        status=row["status"],
        created_at=row["created_at"],
    )


def log_trade(
    symbol: str,
    direction: str,
    entry_price: float,
    shares: int,
    thesis: str = "",
    report_verdict: str = "",
) -> int:
    """Log a new trade to the journal. Returns the trade ID."""
    if not symbol or not symbol.strip():
        raise ValueError("symbol must be a non-empty string")
    if direction not in ("long", "short"):
        raise ValueError("direction must be 'long' or 'short'")
    if entry_price <= 0:
        raise ValueError("entry_price must be positive")
    if shares <= 0:
        raise ValueError("shares must be positive")

    entry_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return save_journal_trade(
        symbol=symbol,
        direction=direction,
        entry_date=entry_date,
        entry_price=entry_price,
        shares=shares,
        report_verdict=report_verdict,
        thesis=thesis,
    )


def close_trade(trade_id: int, exit_price: float, notes: str = "") -> None:
    """Close an open trade with the given exit price."""
    if exit_price <= 0:
        raise ValueError("exit_price must be positive")
    close_journal_trade(trade_id=trade_id, exit_price=exit_price, notes=notes)


def get_open_trades() -> list[JournalTrade]:
    """Return all trades with status='open'."""
    rows = get_journal_trades(status="open")
    return [_row_to_journal_trade(r) for r in rows]


def get_trade_history(symbol: str | None = None) -> list[JournalTrade]:
    """Return all closed trades, optionally filtered by symbol."""
    rows = get_journal_trades(status="closed", symbol=symbol)
    return [_row_to_journal_trade(r) for r in rows]


def get_performance_stats() -> JournalStats:
    """Compute performance statistics from all closed trades."""
    all_rows = get_journal_trades()
    all_trades = [_row_to_journal_trade(r) for r in all_rows]

    open_trades = [t for t in all_trades if t.status == "open"]
    closed = [t for t in all_trades if t.status == "closed"]

    wins = [t for t in closed if t.pnl is not None and t.pnl > 0]
    losses = [t for t in closed if t.pnl is not None and t.pnl <= 0]

    total_closed = len(closed)
    win_count = len(wins)
    loss_count = len(losses)
    win_rate = win_count / total_closed if total_closed > 0 else 0.0

    total_pnl = sum(t.pnl for t in closed if t.pnl is not None)
    avg_win = sum(t.pnl for t in wins) / win_count if win_count > 0 else 0.0
    avg_loss = sum(t.pnl for t in losses) / loss_count if loss_count > 0 else 0.0

    pnl_values = [t.pnl for t in closed if t.pnl is not None]
    best_trade = max(pnl_values) if pnl_values else 0.0
    worst_trade = min(pnl_values) if pnl_values else 0.0

    # Expectancy = (win_rate * avg_win) + ((1 - win_rate) * avg_loss)
    # avg_loss is negative for losing trades, so addition works correctly
    expectancy = (win_rate * avg_win) + ((1 - win_rate) * avg_loss) if total_closed > 0 else 0.0

    return JournalStats(
        total_trades=len(all_trades),
        open_trades=len(open_trades),
        closed_trades=total_closed,
        wins=win_count,
        losses=loss_count,
        win_rate=win_rate,
        total_pnl=total_pnl,
        avg_win=avg_win,
        avg_loss=avg_loss,
        expectancy=expectancy,
        best_trade=best_trade,
        worst_trade=worst_trade,
        report_accuracy=get_report_accuracy(),
    )


def get_report_accuracy() -> dict[str, dict]:
    """Group closed trades by report_verdict and compute win rates.

    Returns a dict like:
        {"Strong Buy": {"trades": 5, "wins": 4, "win_rate": 0.8}, ...}
    """
    closed = get_trade_history()
    verdicts: dict[str, dict] = {}

    for trade in closed:
        verdict = trade.report_verdict or "Unknown"
        if verdict not in verdicts:
            verdicts[verdict] = {"trades": 0, "wins": 0, "win_rate": 0.0}
        verdicts[verdict]["trades"] += 1
        if trade.pnl is not None and trade.pnl > 0:
            verdicts[verdict]["wins"] += 1

    for stats in verdicts.values():
        stats["win_rate"] = stats["wins"] / stats["trades"] if stats["trades"] > 0 else 0.0

    return verdicts
