"""Per-agent candidate discovery for daily picks (service layer).

Each agent independently SELECTS its candidates from the real-data opportunity
cards (discover_service) by its lens; `value` and `options` add a bounded
gateway screen. Deterministic, no LLM. Returns up to _PICKS_PER_AGENT picks per
agent with the real evidence that justifies them. Per-agent errors degrade to
[] (never crash the run). No brief import.
"""
from __future__ import annotations

from src.analysis.daily_picks_scoring import conviction_from_score, rank_candidates

_PICKS_PER_AGENT = 5
_SHORTLIST = 15  # bound gateway calls for value/options lenses

_STRATEGY_LENSES = {
    "momentum": {"Momentum", "Breakout", "Golden Cross", "Volume Spike", "Gap Fill"},
    "contrarian": {"Oversold Bounce", "Mean Reversion", "Support Bounce"},
    "macro": {"Sector Leader", "Dividend Play"},
    "disruption": {"Breakout", "Momentum", "Earnings Catalyst"},
    "insider": {"Insider Accumulation"},
    "flow": {"Congress Buying"},
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


def _strategy_select(agent_key: str, opportunities: list[dict]) -> list[dict]:
    wanted = _STRATEGY_LENSES[agent_key]
    matched = [c for c in opportunities
               if c.get("strategy") in wanted
               or any(s in wanted for s in (c.get("secondary_strategies") or []))]
    top = rank_candidates(matched, key="score", top_n=_PICKS_PER_AGENT)
    return [_pick(c) for c in top]


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
    shortlist = rank_candidates(opportunities, key="score", top_n=_SHORTLIST)
    out = []
    for c in shortlist:
        summ = gateway.get_options_summary(c["symbol"])
        pcr = getattr(summ, "put_call_ratio", None) if summ else None
        if pcr is not None and float(pcr) < 0.7:
            out.append(_pick(c, {"put_call_ratio": float(pcr)}))
    return out[:_PICKS_PER_AGENT]


def discover_for_agent(agent_key: str, *, opportunities: list[dict], gateway) -> list[dict]:
    """Return up to 5 picks for one agent. Degrades to [] on any error."""
    try:
        if agent_key in _STRATEGY_LENSES:
            return _strategy_select(agent_key, opportunities)
        if agent_key == "value":
            return _value_select(opportunities, gateway)
        if agent_key == "options":
            return _options_select(opportunities, gateway)
        return []
    except Exception:
        return []
