"""Portfolio AI Agent: screen the 69-symbol universe + 7 personality agents pick stocks.

Live mode only for now. Reuses rich-context helpers from `ai_analyst_service`.
The historical walk-forward simulation is a separate follow-up.

Pipeline:
  1. Screen — for every symbol, load history, compute snap + opportunity score
     at *today*, rank, take top N=15.
  2. Per-agent pick — for each of 7 personalities, one Claude call:
     "given this ranked candidate ladder, pick up to 3 to BUY".
  3. Tally — count distinct agents per symbol. ≥3 agents = consensus.
  4. Return — full result for UI to render (no execution yet).
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from src.data.gateway import DataGateway
from src.data.stock_db import STOCK_DB
from src.utils.db import init_db
from src.analysis.backtester import _compute_indicators
from src.personalities import AGENT_PERSONALITIES

from api.services.ai_analyst_service import (
    _ask_claude,
    _series_at,
    _stock_meta,
    _historical_opportunity,
    _signal_summary,
    _MULTI_AGENTS,
)


_SCREEN_TOP_N = 15
_MIN_AGENTS_FOR_CONSENSUS = 3
_MAX_PICKS_PER_AGENT = 3
# yfinance shares HTTP-session state across threads — parallel calls can return
# multi-symbol DataFrames that corrupt the per-symbol cache. Keep screen serial
# unless/until we replace yfinance with a thread-safe client.
_MAX_PARALLEL_SCREEN = 1
_MAX_PARALLEL_AGENT = 4


# ── Step 1 — screen the universe ─────────────────────────────────────


def _screen_one(symbol: str) -> dict | None:
    """Fetch history + compute snap/opportunity at *today* for one symbol.

    Returns None on missing/insufficient data — caller filters Nones.
    """
    try:
        gw = DataGateway()
        hist = gw.get_historical(symbol, period_days=365)
        if hist is None or hist.empty or len(hist) < 60:
            return None
        df = hist.reset_index(drop=True)
        idx = len(df) - 1

        close = df["close"].astype(float)
        high = df["high"].astype(float)
        low = df["low"].astype(float)
        volume = df["volume"].astype(float)
        indicators = _compute_indicators(close, high, low, volume)

        date_str = str(df["date"].iloc[idx])[:10]
        price_now = float(close.iloc[idx])
        rsi = _series_at(indicators, "rsi", idx)
        macd_hist = _series_at(indicators, "macd_hist", idx)
        sma_50 = _series_at(indicators, "sma_50", idx)
        sma_200 = _series_at(indicators, "sma_200", idx)
        bb_lower = _series_at(indicators, "bb_lower", idx)
        bb_upper = _series_at(indicators, "bb_upper", idx)

        vol_ratio = None
        if idx >= 20:
            avg_vol = float(volume.iloc[idx - 20:idx].mean())
            if avg_vol > 0:
                vol_ratio = float(volume.iloc[idx]) / avg_vol

        change_5d = None
        change_20d = None
        if idx >= 5:
            p5 = float(close.iloc[idx - 5])
            change_5d = ((price_now - p5) / p5) * 100 if p5 else None
        if idx >= 20:
            p20 = float(close.iloc[idx - 20])
            change_20d = ((price_now - p20) / p20) * 100 if p20 else None

        snap = {
            "date": date_str, "price": price_now,
            "rsi": rsi, "macd_hist": macd_hist,
            "sma_50": sma_50, "sma_200": sma_200,
            "bb_upper": bb_upper, "bb_lower": bb_lower,
            "vol_ratio": vol_ratio,
            "change_5d": change_5d, "change_20d": change_20d,
        }

        opp = _historical_opportunity(symbol, df.iloc[: idx + 1], change_20d, None)
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


def screen_universe(symbols: list[str] | None = None,
                    top_n: int = _SCREEN_TOP_N) -> list[dict]:
    """Screen the universe and return top-N candidates ranked by opportunity score."""
    init_db()
    universe = list(symbols or STOCK_DB.keys())

    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=_MAX_PARALLEL_SCREEN) as pool:
        for r in pool.map(_screen_one, universe):
            if r is not None:
                results.append(r)

    results.sort(
        key=lambda r: (r.get("opportunity") or {}).get("total", 0) or 0,
        reverse=True,
    )
    return results[:top_n]


# ── Step 2 — per-agent stock-pick prompt + parsing ───────────────────


def _candidate_line(c: dict, rank: int) -> str:
    snap = c["snap"]
    opp = c.get("opportunity") or {}
    sig = c["signal_sum"]

    rsi = snap.get("rsi")
    rsi_s = f"RSI {rsi:.0f}" if rsi is not None else "RSI —"

    chg20 = snap.get("change_20d")
    chg_s = f"{chg20:+5.1f}%/20d" if chg20 is not None else "  —/20d "

    vr = snap.get("vol_ratio")
    vol_s = f"{vr:.1f}x" if vr is not None else "  —"

    return (
        f"  #{rank:<2} {c['symbol']:<6} {c['sector'][:14]:<14} "
        f"opp:{opp.get('total', 0):>3} {opp.get('strategy', 'Neutral')[:13]:<13} "
        f"${snap['price']:>7.2f}  {chg_s}  {rsi_s:>8}  vol:{vol_s:>5}  "
        f"sig:{sig['bull']}↑/{sig['bear']}↓"
    )


def _build_pick_prompt(agent_key: str, candidates: list[dict]) -> str:
    p = AGENT_PERSONALITIES.get(agent_key, {})
    name = p.get("name", agent_key)
    icon = p.get("icon", "🤖")
    philosophy = p.get("philosophy", "")
    prio = p.get("prioritizes", []) or []
    avoid = p.get("avoids", []) or []
    risk = p.get("risk_tolerance", "")

    lines = "\n".join(_candidate_line(c, i + 1) for i, c in enumerate(candidates))
    prio_block = ("\n  - " + "\n  - ".join(prio)) if prio else ""
    avoid_block = ("\n  - " + "\n  - ".join(avoid)) if avoid else ""

    return (
        f"You are the {icon} {name} agent.\n"
        f"Philosophy: {philosophy}\n"
        f"You prioritize:{prio_block}\n"
        f"You avoid:{avoid_block}\n"
        f"Risk tolerance: {risk}\n"
        f"\n"
        f"=== TODAY'S TOP {len(candidates)} CANDIDATES (ranked by opportunity score) ===\n"
        f"{lines}\n"
        f"\n"
        f"Select up to {_MAX_PICKS_PER_AGENT} stocks to BUY now through YOUR personality lens.\n"
        f"If none fit your style, reply NONE. Be selective — quality over quantity.\n"
        f"\n"
        f"Reply on a SINGLE LINE in this exact pipe-delimited format:\n"
        f"  SYMBOL1 | one-sentence reason | SYMBOL2 | reason | SYMBOL3 | reason\n"
        f"or:\n"
        f"  NONE | one-sentence reason\n"
        f"\n"
        f"Example: AAPL | strong RSI + sector momentum | NVDA | breakout above SMA50\n"
        f"Example: NONE | all candidates overbought; waiting for pullback"
    )


def _parse_picks(text: str | None, valid_symbols: set[str]) -> list[dict]:
    if not text:
        return []
    line = text.strip().split("\n")[0].strip()
    if not line or line.upper().startswith("NONE"):
        return []

    parts = [p.strip() for p in line.split("|")]
    picks: list[dict] = []
    i = 0
    while i + 1 < len(parts) and len(picks) < _MAX_PICKS_PER_AGENT:
        head = parts[i].split()[0].upper() if parts[i] else ""
        reason = parts[i + 1] if i + 1 < len(parts) else ""
        if head in valid_symbols and head not in {p["symbol"] for p in picks}:
            picks.append({"symbol": head, "reason": reason[:240]})
        i += 2
    return picks


def _ask_one_agent(agent_key: str, candidates: list[dict],
                   valid_set: set[str]) -> dict:
    prompt = _build_pick_prompt(agent_key, candidates)
    text = _ask_claude(prompt)
    picks = _parse_picks(text, valid_set)
    return {
        "agent": agent_key,
        "picks": picks,
        "raw": (text or "")[:400],
        "prompt": prompt,
    }


# ── Step 3 — orchestrate the live pick ───────────────────────────────


def _candidate_view(c: dict) -> dict:
    """Flatten a candidate for the API response."""
    snap = c["snap"]
    opp = c.get("opportunity") or {}
    sig = c["signal_sum"]
    return {
        "symbol": c["symbol"],
        "name": c["name"],
        "sector": c["sector"],
        "price": snap.get("price"),
        "rsi": snap.get("rsi"),
        "change_5d": snap.get("change_5d"),
        "change_20d": snap.get("change_20d"),
        "vol_ratio": snap.get("vol_ratio"),
        "opportunity_score": opp.get("total", 0),
        "opportunity_label": opp.get("label", "—"),
        "strategy": opp.get("strategy", "Neutral"),
        "bull_signals": sig["bull"],
        "bear_signals": sig["bear"],
        "alignment_pct": sig["alignment_pct"],
        "dominant": sig["dominant"],
    }


def run_portfolio_pick(top_n: int = _SCREEN_TOP_N,
                       min_agents: int = _MIN_AGENTS_FOR_CONSENSUS) -> dict:
    """Run the full live pipeline. Returns the result; does not execute trades."""
    candidates = screen_universe(top_n=top_n)
    if not candidates:
        return {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "universe_size": len(STOCK_DB),
            "error": "No candidates passed screening",
            "candidates_screened": [],
            "agent_votes": [],
            "consensus_picks": [],
            "final_portfolio": [],
        }

    valid_set = {c["symbol"] for c in candidates}

    with ThreadPoolExecutor(max_workers=_MAX_PARALLEL_AGENT) as pool:
        agent_results = list(pool.map(
            lambda k: _ask_one_agent(k, candidates, valid_set),
            _MULTI_AGENTS,
        ))

    # Tally: count distinct agents per symbol
    tally: dict[str, list[dict]] = {}
    for r in agent_results:
        for p in r["picks"]:
            tally.setdefault(p["symbol"], []).append({
                "agent": r["agent"],
                "reason": p["reason"],
            })

    consensus = sorted(
        [
            {"symbol": s, "agent_count": len(voters), "votes": voters}
            for s, voters in tally.items()
            if len(voters) >= min_agents
        ],
        key=lambda x: x["agent_count"],
        reverse=True,
    )

    # Final portfolio = top consensus picks (Risk Manager polish deferred)
    final = [c for c in consensus[:5]]

    # Strip prompts from the public response by default — UI can request
    # via separate endpoint if needed. Keep agent picks + raw text snippet.
    agent_votes_view = [
        {
            "agent": r["agent"],
            "picks": r["picks"],
            "raw": r["raw"],
        }
        for r in agent_results
    ]

    return {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "universe_size": len(STOCK_DB),
        "candidates_screened": [_candidate_view(c) for c in candidates],
        "agent_votes": agent_votes_view,
        "consensus_picks": consensus,
        "final_portfolio": final,
        "config": {
            "top_n": top_n,
            "min_agents_for_consensus": min_agents,
            "max_picks_per_agent": _MAX_PICKS_PER_AGENT,
            "agents": list(_MULTI_AGENTS),
        },
    }


# ── Execute the suggested portfolio (paper trades) ───────────────────


def execute_picks(
    symbols: list[str],
    reasons_by_symbol: dict[str, str] | None = None,
) -> dict:
    """Open paper-trade long positions for the given symbols.

    Reuses the existing `TradingAgent._execute_buy` machinery — same risk
    budget, sector concentration, earnings, max-position, cash-reserve, and
    tactical-entry checks the live agent uses. Symbols that fail any check
    are returned in `skipped` with the reason from the checklist log.
    """
    from src.agent import TradingAgent

    init_db()
    agent = TradingAgent()
    run_date = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
    reasons_by_symbol = reasons_by_symbol or {}

    executed: list[dict] = []
    skipped: list[dict] = []

    for sym in symbols:
        sym = sym.upper()
        if sym not in STOCK_DB:
            skipped.append({"symbol": sym, "reason": "Not in stock universe"})
            continue
        # Already holding? Skip.
        already_open = any(
            p.symbol == sym and p.status == "open" for p in agent.positions
        )
        if already_open:
            skipped.append({"symbol": sym, "reason": "Position already open"})
            continue

        trade = {
            "symbol": sym,
            "action": "BUY",
            "reason": reasons_by_symbol.get(sym, "Portfolio AI consensus pick"),
        }
        result = agent._execute_buy(sym, trade, run_date)
        if result:
            executed.append(result)
        else:
            # _execute_buy returns None for: tactical wait, pre-trade fail,
            # zero shares, no current price. The detailed reasons are in
            # agent_decisions log — fetch the most recent one for this symbol.
            reason = "Pre-trade check or tactical wait"
            try:
                from src.utils.db import get_connection
                conn = get_connection()
                row = conn.execute(
                    "SELECT step, decision, reasoning FROM agent_decisions "
                    "WHERE run_date = ? AND symbol = ? "
                    "ORDER BY created_at DESC LIMIT 1",
                    (run_date, sym),
                ).fetchone()
                conn.close()
                if row:
                    reason = f"{row['step']}: {row['decision']} — {row['reasoning'][:160]}"
            except Exception:
                pass
            skipped.append({"symbol": sym, "reason": reason})

    return {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "run_date": run_date,
        "executed": executed,
        "skipped": skipped,
        "cash_remaining": float(agent.config.current_cash),
        "open_positions": sum(1 for p in agent.positions if p.status == "open"),
        "max_positions": int(agent.config.max_positions),
    }
