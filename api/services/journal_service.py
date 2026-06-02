"""Trade Journal API service — wraps src.journal for HTTP routes.

The personal journal lets the user log their own buys/sells so the Gap
Finder agent can reason against a real portfolio. Storage is the existing
`journal_trades` table (one row per round-trip position):

  • open_position(symbol, entry_price, shares, thesis)  →  log a buy
  • close_position(position_id, exit_price, notes)       →  log a sell
  • list_positions(status?, symbol?)                     →  history + holdings
  • current_holdings()                                   →  derived per-symbol
                                                            aggregation
  • stats()                                              →  P&L summary

Holdings are derived by aggregating OPEN positions per symbol with a
weighted-average entry price (handles multiple lots per symbol).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from src import journal as journal_core


def _trade_to_dict(t) -> dict:
    return {
        "id": t.id,
        "symbol": t.symbol,
        "direction": t.direction,
        "entry_date": t.entry_date,
        "entry_price": t.entry_price,
        "exit_date": t.exit_date,
        "exit_price": t.exit_price,
        "shares": t.shares,
        "pnl": t.pnl,
        "pnl_percent": t.pnl_percent,
        "report_verdict": t.report_verdict or "",
        "thesis": t.thesis or "",
        "notes": t.notes or "",
        "status": t.status,
        "created_at": t.created_at,
    }


def open_position(
    symbol: str,
    entry_price: float,
    shares: int,
    *,
    direction: str = "long",
    thesis: str = "",
    report_verdict: str = "",
) -> dict:
    """Log a buy (or short) into the journal. Returns the persisted row.

    `direction` defaults to 'long' — short-selling is supported but rare for
    the personal journal use case.
    """
    trade_id = journal_core.log_trade(
        symbol=symbol.upper(),
        direction=direction,
        entry_price=float(entry_price),
        shares=int(shares),
        thesis=thesis,
        report_verdict=report_verdict,
    )
    # Round-trip read so the caller gets the full persisted shape including
    # auto-generated entry_date and created_at.
    rows = journal_core.get_open_trades()
    match = next((r for r in rows if r.id == trade_id), None)
    if match is None:
        # Shouldn't happen — log_trade just persisted this id.
        return {"id": trade_id, "symbol": symbol.upper(), "error": "persisted but not found"}
    return _trade_to_dict(match)


def close_position(position_id: int, exit_price: float, notes: str = "") -> dict:
    """Close a previously opened position at `exit_price`. Returns updated row.

    Raises ValueError if position_id is unknown or already closed.
    """
    journal_core.close_trade(trade_id=int(position_id), exit_price=float(exit_price), notes=notes)
    # Re-read the closed trade
    history = journal_core.get_trade_history()
    match = next((t for t in history if t.id == position_id), None)
    if match is None:
        raise ValueError(f"position {position_id} not found after close")
    return _trade_to_dict(match)


def list_positions(*, status: Optional[str] = None, symbol: Optional[str] = None,
                    limit: int = 200) -> dict:
    """List positions. status='open'|'closed'|None (both)."""
    if status == "open":
        trades = journal_core.get_open_trades()
        if symbol:
            sym_u = symbol.upper()
            trades = [t for t in trades if t.symbol == sym_u]
    elif status == "closed":
        trades = journal_core.get_trade_history(symbol=symbol.upper() if symbol else None)
    else:
        opens = journal_core.get_open_trades()
        closed = journal_core.get_trade_history(symbol=symbol.upper() if symbol else None)
        if symbol:
            sym_u = symbol.upper()
            opens = [t for t in opens if t.symbol == sym_u]
        trades = opens + closed

    # Sort: open first, then by entry_date desc
    trades.sort(key=lambda t: (
        0 if t.status == "open" else 1,
        -datetime.fromisoformat((t.entry_date or "1970-01-01")).timestamp(),
    ))
    return {
        "positions": [_trade_to_dict(t) for t in trades[:limit]],
        "total": len(trades),
    }


def current_holdings() -> dict:
    """Aggregate open positions per symbol with weighted-average entry price.

    Returns:
        {
          "holdings": [
            {"symbol": "AAPL", "shares": 100, "avg_entry_price": 178.50,
             "lots": 2, "total_cost": 17850.0, "first_entry_date": "...",
             "latest_thesis": "..."},
            ...
          ],
          "total_symbols": int,
        }
    """
    opens = journal_core.get_open_trades()
    by_symbol: dict[str, dict] = {}
    for t in opens:
        sym = t.symbol
        b = by_symbol.setdefault(sym, {
            "symbol": sym,
            "shares": 0,
            "total_cost": 0.0,
            "lots": 0,
            "first_entry_date": t.entry_date,
            "latest_thesis": t.thesis or "",
            "latest_entry_date": t.entry_date,
        })
        shares = int(t.shares or 0)
        cost = shares * float(t.entry_price or 0)
        b["shares"] += shares
        b["total_cost"] += cost
        b["lots"] += 1
        # Track the most recent entry date / thesis for "latest read"
        if (t.entry_date or "") > (b["latest_entry_date"] or ""):
            b["latest_entry_date"] = t.entry_date
            if t.thesis:
                b["latest_thesis"] = t.thesis
        if (t.entry_date or "") < (b["first_entry_date"] or ""):
            b["first_entry_date"] = t.entry_date

    out_holdings: list[dict] = []
    for b in by_symbol.values():
        avg = b["total_cost"] / b["shares"] if b["shares"] > 0 else None
        out_holdings.append({
            "symbol": b["symbol"],
            "shares": b["shares"],
            "avg_entry_price": round(avg, 2) if avg is not None else None,
            "total_cost": round(b["total_cost"], 2),
            "lots": b["lots"],
            "first_entry_date": b["first_entry_date"],
            "latest_entry_date": b["latest_entry_date"],
            "latest_thesis": b["latest_thesis"],
        })

    out_holdings.sort(key=lambda h: -(h["total_cost"] or 0))
    return {
        "holdings": out_holdings,
        "total_symbols": len(out_holdings),
    }


def get_stats() -> dict:
    """Performance summary from src.journal — wraps for HTTP."""
    s = journal_core.get_performance_stats()
    return {
        "total_trades":   s.total_trades,
        "open_trades":    s.open_trades,
        "closed_trades":  s.closed_trades,
        "wins":           s.wins,
        "losses":         s.losses,
        "win_rate":       s.win_rate,
        "total_pnl":      s.total_pnl,
        "avg_win":        s.avg_win,
        "avg_loss":       s.avg_loss,
        "expectancy":     s.expectancy,
        "best_trade":     s.best_trade,
        "worst_trade":    s.worst_trade,
        "report_accuracy": s.report_accuracy,
    }
