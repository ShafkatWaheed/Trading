"""Walk-forward AI portfolio simulation.

For each cycle date in [start_date, end_date]:
  1. Screen the universe at THAT date (history sliced to t, no future bars)
  2. Run 7 personality agents on the candidate ladder (Claude calls in parallel)
  3. Close any positions held >= cycle_days
  4. Open consensus picks (>= min_agents) with the cycle date's open price
  5. Mark-to-market and log equity

All fetch helpers are date-aware. No closing prices, fundamentals, news, or
filings AFTER the cycle date enter the prompt.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from dataclasses import dataclass, field

import pandas as pd

from src.data.gateway import DataGateway
from src.data.stock_db import STOCK_DB
from src.utils.db import init_db
from src.analysis.backtester import _compute_indicators

from api.services.ai_analyst_service import (
    _ask_claude,
    _series_at,
    _stock_meta,
    _historical_opportunity,
    _signal_summary,
    _MULTI_AGENTS,
)
from api.services.portfolio_agent_service import (
    _build_pick_prompt,
    _parse_picks,
    _candidate_view,
    _MAX_PICKS_PER_AGENT,
)


_MAX_PARALLEL_AGENT = 4
_MAX_PARALLEL_CYCLE_PREP = 1   # yfinance not thread-safe — keep serial
_DEFAULT_HOLD_DAYS = 14
_POSITION_SIZE_PCT = 0.10      # 10% of starting capital per position
_MIN_HISTORY_NEEDED = 60       # Bars before t needed for indicators


# ── Per-symbol history fetch (one-shot up to today) ────────────────


def _fetch_universe_history(period_days: int = 365) -> dict[str, pd.DataFrame]:
    """Pre-fetch ~1 year of OHLC for the entire universe — used by all cycles."""
    gw = DataGateway()
    out: dict[str, pd.DataFrame] = {}
    # Serial — yfinance corrupts cache under parallel use
    for sym in STOCK_DB:
        try:
            h = gw.get_historical(sym, period_days=period_days)
            if h is not None and not h.empty and len(h) >= _MIN_HISTORY_NEEDED:
                out[sym] = h.reset_index(drop=True)
        except Exception:
            pass
    return out


def _idx_at_or_before(df: pd.DataFrame, date_str: str) -> int | None:
    """Return the row index whose date <= date_str. None if none qualifies."""
    dates = df["date"].astype(str).str[:10]
    mask = dates <= date_str
    if not mask.any():
        return None
    return int(mask[::-1].idxmax())  # last True index


def _open_price_at_or_after(df: pd.DataFrame, date_str: str) -> tuple[str, float] | None:
    """Find the first bar with date >= date_str; return (date, open)."""
    dates = df["date"].astype(str).str[:10]
    mask = dates >= date_str
    if not mask.any():
        return None
    idx = int(mask.idxmax())
    return str(df["date"].iloc[idx])[:10], float(df["open"].iloc[idx])


# ── Screen at a past date ──────────────────────────────────────────


def _screen_one_at_date(symbol: str, hist: pd.DataFrame, date_str: str) -> dict | None:
    """Same shape as `portfolio_agent_service._screen_one`, sliced to `date_str`."""
    try:
        idx = _idx_at_or_before(hist, date_str)
        if idx is None or idx < _MIN_HISTORY_NEEDED:
            return None
        df = hist.iloc[: idx + 1].reset_index(drop=True)
        sub_idx = len(df) - 1

        close = df["close"].astype(float)
        high = df["high"].astype(float)
        low = df["low"].astype(float)
        volume = df["volume"].astype(float)
        indicators = _compute_indicators(close, high, low, volume)

        cycle_date = str(df["date"].iloc[sub_idx])[:10]
        price_now = float(close.iloc[sub_idx])
        rsi = _series_at(indicators, "rsi", sub_idx)
        macd_hist = _series_at(indicators, "macd_hist", sub_idx)
        sma_50 = _series_at(indicators, "sma_50", sub_idx)
        sma_200 = _series_at(indicators, "sma_200", sub_idx)
        bb_lower = _series_at(indicators, "bb_lower", sub_idx)
        bb_upper = _series_at(indicators, "bb_upper", sub_idx)

        vol_ratio = None
        if sub_idx >= 20:
            avg = float(volume.iloc[sub_idx - 20:sub_idx].mean())
            if avg > 0:
                vol_ratio = float(volume.iloc[sub_idx]) / avg

        change_5d = None
        change_20d = None
        if sub_idx >= 5:
            p5 = float(close.iloc[sub_idx - 5])
            change_5d = ((price_now - p5) / p5) * 100 if p5 else None
        if sub_idx >= 20:
            p20 = float(close.iloc[sub_idx - 20])
            change_20d = ((price_now - p20) / p20) * 100 if p20 else None

        snap = {
            "date": cycle_date, "price": price_now,
            "rsi": rsi, "macd_hist": macd_hist,
            "sma_50": sma_50, "sma_200": sma_200,
            "bb_upper": bb_upper, "bb_lower": bb_lower,
            "vol_ratio": vol_ratio,
            "change_5d": change_5d, "change_20d": change_20d,
        }

        opp = _historical_opportunity(symbol, df, change_20d, None)
        sig = _signal_summary(snap)
        meta = _stock_meta(symbol)

        return {
            "symbol": symbol,
            "name": meta.get("name") or symbol,
            "sector": meta.get("sector") or "—",
            "snap": snap,
            "opportunity": opp,
            "signal_sum": sig,
        }
    except Exception:
        return None


def _screen_universe_at_date(histories: dict[str, pd.DataFrame],
                             date_str: str, top_n: int) -> list[dict]:
    rows: list[dict] = []
    for sym, hist in histories.items():
        r = _screen_one_at_date(sym, hist, date_str)
        if r is not None:
            rows.append(r)
    rows.sort(
        key=lambda r: (r.get("opportunity") or {}).get("total", 0) or 0,
        reverse=True,
    )
    return rows[:top_n]


# ── Per-cycle agent vote ───────────────────────────────────────────


def _ask_one_agent(agent_key: str, candidates: list[dict],
                   valid_set: set[str]) -> dict:
    prompt = _build_pick_prompt(agent_key, candidates)
    text = _ask_claude(prompt)
    picks = _parse_picks(text, valid_set)
    return {
        "agent": agent_key,
        "picks": picks,
        "raw": (text or "")[:300],
    }


def _vote_cycle(candidates: list[dict]) -> list[dict]:
    valid_set = {c["symbol"] for c in candidates}
    with ThreadPoolExecutor(max_workers=_MAX_PARALLEL_AGENT) as pool:
        return list(pool.map(
            lambda k: _ask_one_agent(k, candidates, valid_set),
            _MULTI_AGENTS,
        ))


def _tally_consensus(agent_votes: list[dict], min_agents: int) -> list[dict]:
    tally: dict[str, list[dict]] = {}
    for r in agent_votes:
        for p in r["picks"]:
            tally.setdefault(p["symbol"], []).append({
                "agent": r["agent"],
                "reason": p["reason"],
            })
    return sorted(
        [
            {"symbol": s, "agent_count": len(voters), "votes": voters}
            for s, voters in tally.items()
            if len(voters) >= min_agents
        ],
        key=lambda x: x["agent_count"],
        reverse=True,
    )


# ── In-memory trade book ───────────────────────────────────────────


@dataclass
class _SimPosition:
    symbol: str
    shares: int
    entry_price: float
    entry_date: str
    cycle_index: int
    consensus_count: int
    voters: list[dict] = field(default_factory=list)


@dataclass
class _ClosedTrade:
    symbol: str
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    shares: int
    pnl: float
    pnl_pct: float
    consensus_count: int
    voters: list[dict] = field(default_factory=list)


def _close_position(pos: _SimPosition, exit_price: float, exit_date: str) -> _ClosedTrade:
    pnl = (exit_price - pos.entry_price) * pos.shares
    pnl_pct = ((exit_price - pos.entry_price) / pos.entry_price) * 100 if pos.entry_price else 0.0
    return _ClosedTrade(
        symbol=pos.symbol, entry_date=pos.entry_date, exit_date=exit_date,
        entry_price=pos.entry_price, exit_price=exit_price, shares=pos.shares,
        pnl=pnl, pnl_pct=pnl_pct,
        consensus_count=pos.consensus_count, voters=pos.voters,
    )


# ── Cycle date list ────────────────────────────────────────────────


def _build_cycle_dates(start_date: str, end_date: str, cycle_days: int) -> list[str]:
    s = datetime.strptime(start_date, "%Y-%m-%d")
    e = datetime.strptime(end_date, "%Y-%m-%d")
    dates: list[str] = []
    cur = s
    while cur <= e:
        dates.append(cur.strftime("%Y-%m-%d"))
        cur += timedelta(days=cycle_days)
    return dates


# ── Public entry ───────────────────────────────────────────────────


def run_walk_forward(
    start_date: str,
    end_date: str,
    cycle_days: int = _DEFAULT_HOLD_DAYS,
    initial_capital: float = 100_000.0,
    max_positions: int = 5,
    min_agents: int = 3,
    top_n: int = 12,
    position_size_pct: float = _POSITION_SIZE_PCT,
) -> dict:
    """Run a walk-forward AI portfolio simulation.

    Returns equity curve, closed trades, per-cycle decision log, and metrics.
    Walk-forward: every fetch is sliced to the cycle date.
    """
    init_db()
    histories = _fetch_universe_history(period_days=365)
    if not histories:
        return {"error": "Universe history empty", "cycles": [], "trades": []}

    cycle_dates = _build_cycle_dates(start_date, end_date, cycle_days)
    if len(cycle_dates) < 2:
        return {"error": "Cycle range too short", "cycles": [], "trades": []}

    cash = float(initial_capital)
    open_positions: list[_SimPosition] = []
    closed_trades: list[_ClosedTrade] = []
    cycles_log: list[dict] = []
    equity_curve: list[dict] = []

    per_position_budget = initial_capital * position_size_pct

    for ci, cycle_date in enumerate(cycle_dates):
        # 1) Close positions held >= cycle_days
        still_open: list[_SimPosition] = []
        for pos in open_positions:
            held_cycles = ci - pos.cycle_index
            if held_cycles >= 1:
                # Exit at cycle_date open
                hist = histories.get(pos.symbol)
                exit_pair = _open_price_at_or_after(hist, cycle_date) if hist is not None else None
                if exit_pair is None:
                    still_open.append(pos)
                    continue
                exit_date, exit_price = exit_pair
                cash += pos.shares * exit_price
                closed_trades.append(_close_position(pos, exit_price, exit_date))
            else:
                still_open.append(pos)
        open_positions = still_open

        # 2) Screen the universe AT this cycle date
        candidates = _screen_universe_at_date(histories, cycle_date, top_n=top_n)
        if not candidates:
            cycles_log.append({
                "cycle_index": ci, "date": cycle_date,
                "skipped": "no candidates",
                "agent_votes": [], "consensus_picks": [], "opened": [],
            })
            equity_curve.append({"date": cycle_date, "equity": cash})
            continue

        # 3) 7 personality agents vote
        agent_votes = _vote_cycle(candidates)

        # 4) Tally
        consensus = _tally_consensus(agent_votes, min_agents=min_agents)

        # 5) Open positions for consensus picks (limited by max_positions + cash)
        opened_this_cycle: list[dict] = []
        already_open_syms = {p.symbol for p in open_positions}
        for pick in consensus:
            if len(open_positions) >= max_positions:
                break
            if pick["symbol"] in already_open_syms:
                continue
            hist = histories.get(pick["symbol"])
            if hist is None:
                continue
            entry_pair = _open_price_at_or_after(hist, cycle_date)
            if entry_pair is None:
                continue
            entry_date, entry_price = entry_pair
            shares = int(per_position_budget // entry_price)
            cost = shares * entry_price
            if shares <= 0 or cost > cash:
                continue
            cash -= cost
            pos = _SimPosition(
                symbol=pick["symbol"], shares=shares,
                entry_price=entry_price, entry_date=entry_date,
                cycle_index=ci,
                consensus_count=pick["agent_count"],
                voters=pick["votes"],
            )
            open_positions.append(pos)
            opened_this_cycle.append({
                "symbol": pos.symbol, "shares": shares,
                "entry_price": entry_price, "entry_date": entry_date,
                "consensus_count": pick["agent_count"],
            })

        # 6) Mark-to-market equity
        mtm = cash
        for pos in open_positions:
            hist = histories.get(pos.symbol)
            if hist is None:
                continue
            idx = _idx_at_or_before(hist, cycle_date)
            if idx is None:
                continue
            mtm += pos.shares * float(hist["close"].iloc[idx])
        equity_curve.append({"date": cycle_date, "equity": round(mtm, 2)})

        cycles_log.append({
            "cycle_index": ci,
            "date": cycle_date,
            "candidates_screened": [_candidate_view(c) for c in candidates],
            "agent_votes": [
                {"agent": v["agent"], "picks": v["picks"], "raw": v["raw"]}
                for v in agent_votes
            ],
            "consensus_picks": consensus,
            "opened": opened_this_cycle,
        })

    # Final liquidation: use the last cycle date but never EARLIER than the
    # position's entry_date (positions opened in the final cycle would otherwise
    # close at a stale prior bar — exit before entry).
    final_date = cycle_dates[-1]
    for pos in open_positions:
        hist = histories.get(pos.symbol)
        if hist is None:
            continue
        target_date = max(final_date, pos.entry_date)
        idx = _idx_at_or_before(hist, target_date)
        if idx is None:
            continue
        # If we'd be exiting at the same bar we entered, hold through the next
        # available bar so the trade reflects at least one period of P&L.
        entry_idx = _idx_at_or_before(hist, pos.entry_date)
        if entry_idx is not None and idx == entry_idx and idx + 1 < len(hist):
            idx = idx + 1
        exit_price = float(hist["close"].iloc[idx])
        exit_date = str(hist["date"].iloc[idx])[:10]
        cash += pos.shares * exit_price
        closed_trades.append(_close_position(pos, exit_price, exit_date))
    open_positions = []

    final_equity = cash
    total_return_pct = ((final_equity - initial_capital) / initial_capital) * 100 if initial_capital else 0.0
    winners = [t for t in closed_trades if t.pnl > 0]
    win_rate = (len(winners) / len(closed_trades)) if closed_trades else 0.0
    avg_pnl_pct = (sum(t.pnl_pct for t in closed_trades) / len(closed_trades)) if closed_trades else 0.0

    return {
        "config": {
            "start_date": start_date,
            "end_date": end_date,
            "cycle_days": cycle_days,
            "initial_capital": initial_capital,
            "max_positions": max_positions,
            "min_agents": min_agents,
            "top_n": top_n,
            "position_size_pct": position_size_pct,
            "agents": list(_MULTI_AGENTS),
        },
        "summary": {
            "initial_capital": initial_capital,
            "final_equity": round(final_equity, 2),
            "total_return_pct": round(total_return_pct, 2),
            "total_trades": len(closed_trades),
            "winners": len(winners),
            "win_rate": round(win_rate, 3),
            "avg_pnl_pct": round(avg_pnl_pct, 2),
            "cycles_run": len(cycle_dates),
        },
        "equity_curve": equity_curve,
        "trades": [
            {
                "symbol": t.symbol,
                "entry_date": t.entry_date,
                "exit_date": t.exit_date,
                "entry_price": round(t.entry_price, 2),
                "exit_price": round(t.exit_price, 2),
                "shares": t.shares,
                "pnl": round(t.pnl, 2),
                "pnl_pct": round(t.pnl_pct, 2),
                "consensus_count": t.consensus_count,
                "voters": t.voters,
            }
            for t in closed_trades
        ],
        "cycles": cycles_log,
    }
