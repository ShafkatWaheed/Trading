"""Per-agent candidate discovery for daily picks (service layer).

Each agent independently SELECTS its candidates from the real-data opportunity
cards (discover_service) by its lens; `value` and `options` add a bounded
gateway screen. Deterministic, no LLM. Returns up to _PICKS_PER_AGENT picks per
agent with the real evidence that justifies them. Per-agent errors degrade to
[] (never crash the run). No brief import.
"""
from __future__ import annotations

from src.analysis.daily_picks_scoring import conviction_from_score, rank_candidates
from src.utils.db import get_connection, init_db

_PICKS_PER_AGENT = 5
_SHORTLIST = 15  # bound gateway calls for the value lens (fundamentals, cached 24h)
# Polygon options is rate-limited (free tier ~5/min), so keep the options lens
# shortlist tiny — otherwise it dominates the synchronous daily-picks request.
_OPTIONS_SHORTLIST = 5
_INSIDER_SHORTLIST = 15
_CONGRESS_BUY_MIN = 2     # >= this many recent congressional buys
_INST_HOLDER_MIN = 5      # >= this many distinct 13F holders
_DIV_YIELD_MIN = 3.0      # % minimum dividend yield for macro dividend-play branch

_STRATEGY_LENSES = {
    "momentum": {"Momentum", "Breakout", "Golden Cross", "Volume Spike", "Gap Fill"},
    "contrarian": {"Oversold Bounce", "Mean Reversion", "Support Bounce"},
    "disruption": {"Breakout", "Momentum", "Earnings Catalyst"},
}


def _evidence(card: dict) -> dict:
    return {
        "strategy": card.get("strategy"),
        "score": card.get("score"),
        "sub_scores": card.get("sub_scores"),
        "sector": card.get("sector"),
    }


def _pick(card: dict, extra: dict | None = None) -> dict:
    ev = _evidence(card)
    if extra:
        ev.update(extra)
    return {
        "symbol": card["symbol"],
        "evidence": ev,
        "conviction": conviction_from_score(card.get("score")),
    }


def _secondary_names(card: dict) -> list[str]:
    """Return strategy names from secondary_strategies, handling both dict and string forms."""
    out = []
    for s in (card.get("secondary_strategies") or []):
        out.append(s.get("name") if isinstance(s, dict) else s)
    return out


def _strategy_select(agent_key: str, opportunities: list[dict]) -> list[dict]:
    wanted = _STRATEGY_LENSES[agent_key]
    matched = [c for c in opportunities
               if c.get("strategy") in wanted
               or any(name in wanted for name in _secondary_names(c))]
    top = rank_candidates(matched, key="score", top_n=_PICKS_PER_AGENT)
    return [_pick(c) for c in top]


def _flow_signals() -> tuple[set[str], dict[str, int], dict[str, int]]:
    """Bulk read: tickers with recent congressional buys + 13F breadth.

    Returns (symbols, congress_counts, institution_counts). Empty on any error.
    """
    init_db()
    congress: dict[str, int] = {}
    inst: dict[str, int] = {}
    try:
        conn = get_connection()
        try:
            for r in conn.execute(
                "SELECT ticker, COUNT(*) AS n FROM congress_trades "
                "WHERE transaction_type='buy' AND transaction_date >= date('now','-180 day') "
                "GROUP BY ticker HAVING n >= ?", (_CONGRESS_BUY_MIN,)
            ):
                if r["ticker"]:
                    congress[r["ticker"].upper()] = r["n"]
            for r in conn.execute(
                "SELECT symbol, COUNT(DISTINCT cik) AS h FROM institution_holdings "
                "GROUP BY symbol HAVING h >= ?", (_INST_HOLDER_MIN,)
            ):
                if r["symbol"]:
                    inst[r["symbol"].upper()] = r["h"]
        finally:
            conn.close()
    except Exception:
        return set(), {}, {}
    return set(congress) | set(inst), congress, inst


def _flow_select(opportunities: list[dict]) -> list[dict]:
    symbols, congress, inst = _flow_signals()
    if not symbols:
        return []
    matched_cards = [c for c in opportunities if (c.get("symbol") or "").upper() in symbols]
    top = rank_candidates(matched_cards, key="score", top_n=_PICKS_PER_AGENT)
    return [_pick(c, {"congress_buys": congress.get((c.get("symbol") or "").upper()),
                      "institutions": inst.get((c.get("symbol") or "").upper())})
            for c in top]


def _value_select(opportunities: list[dict], gateway) -> list[dict]:
    shortlist = rank_candidates(opportunities, key="score", top_n=_SHORTLIST)
    out = []
    for c in shortlist:
        f = gateway.get_fundamentals(c["symbol"])
        pe = getattr(f, "pe_ratio", None)
        margin = getattr(f, "profit_margin", None)
        if pe is not None and 0 < float(pe) <= 25 and (margin is None or float(margin) > 0):
            out.append(_pick(c, {"pe_ratio": float(pe)}))
    return out[:_PICKS_PER_AGENT]


def _options_select(opportunities: list[dict], gateway) -> list[dict]:
    shortlist = rank_candidates(opportunities, key="score", top_n=_OPTIONS_SHORTLIST)
    out = []
    for c in shortlist:
        if len(out) >= _PICKS_PER_AGENT:
            break
        summ = gateway.get_options_summary(c["symbol"])
        pcr = getattr(summ, "put_call_ratio", None) if summ else None
        if pcr is not None and float(pcr) < 0.7:
            out.append(_pick(c, {"put_call_ratio": float(pcr)}))
    return out[:_PICKS_PER_AGENT]


def _macro_select(opportunities: list[dict], gateway) -> list[dict]:
    # Inflow sectors from the cached sector tape (case-insensitive match).
    inflow: set[str] = set()
    try:
        from api.services import smart_money_service
        tape = smart_money_service.get_sector_tape() or {}
        inflow = {(s.get("sector") or "").lower()
                  for s in tape.get("sectors", []) if s.get("direction") == "inflow"}
    except Exception:
        inflow = set()

    chosen: dict[str, dict] = {}   # symbol -> _pick dict (dedup)
    if inflow:
        for c in opportunities:
            if (c.get("sector") or "").lower() in inflow:
                sym = (c.get("symbol") or "").upper()
                chosen[sym] = _pick(c, {"sector": c.get("sector"), "sector_inflow": True})
    for c in rank_candidates(opportunities, key="score", top_n=_SHORTLIST):
        sym = (c.get("symbol") or "").upper()
        if sym in chosen:
            continue
        try:
            f = gateway.get_fundamentals(c["symbol"])
            dy = getattr(f, "dividend_yield", None)
            if dy is not None and float(dy) >= _DIV_YIELD_MIN:
                chosen[sym] = _pick(c, {"sector": c.get("sector"), "dividend_yield": float(dy)})
        except Exception:
            continue
    picks = sorted(chosen.values(),
                   key=lambda p: float(p["evidence"].get("score") or 0), reverse=True)
    return picks[:_PICKS_PER_AGENT]


def _insider_select(opportunities: list[dict], gateway) -> list[dict]:
    out = []
    for c in rank_candidates(opportunities, key="score", top_n=_INSIDER_SHORTLIST):
        if len(out) >= _PICKS_PER_AGENT:
            break
        try:
            s = gateway.get_insider_summary(c["symbol"], days=90)
        except Exception:
            continue
        if s is None:
            continue
        buying = (getattr(s, "cluster_buy", False)
                  or getattr(s, "signal", "") in ("buy", "strong buy")
                  or (getattr(s, "total_buys", 0) or 0) >= 3)
        if buying:
            out.append(_pick(c, {"signal": getattr(s, "signal", ""),
                                 "cluster_buy": getattr(s, "cluster_buy", False),
                                 "total_buys": getattr(s, "total_buys", 0),
                                 "net_shares": getattr(s, "net_shares", 0)}))
    return out


def discover_for_agent(agent_key: str, *, opportunities: list[dict], gateway) -> list[dict]:
    """Return up to 5 picks for one agent. Degrades to [] on any error."""
    try:
        if agent_key in _STRATEGY_LENSES:
            return _strategy_select(agent_key, opportunities)
        if agent_key == "value":
            return _value_select(opportunities, gateway)
        if agent_key == "options":
            return _options_select(opportunities, gateway)
        if agent_key == "flow":
            return _flow_select(opportunities)
        if agent_key == "macro":
            return _macro_select(opportunities, gateway)
        if agent_key == "insider":
            return _insider_select(opportunities, gateway)
        return []
    except Exception:
        return []
