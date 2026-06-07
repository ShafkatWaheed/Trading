"""Daily Picks — what to buy today, from 8 different agent perspectives.

Runs all 8 personalities in parallel via ThreadPoolExecutor (mirrors
ai_analyst_service pattern). Each agent picks its top 5 stocks using
the brief pipeline narrowed to that agent's lens. The service then
computes consensus (stocks 3+ agents picked) and each agent's
contrarian pick (their top stock no one else picked).

Cached for 8 hours by day (so the picks are stable within a session
but refresh overnight).
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from typing import Any

from api.services import daily_picks_agents, daily_picks_synthesis
from src.personalities import AGENT_PERSONALITIES
from src.utils.db import cache_get, cache_set


_CACHE_TTL_HOURS = 8
# Mirror the ai_analyst_service pattern: parallelize all personalities at
# once so wall-clock equals the slowest agent, not a sum-of-batches.
_MAX_PARALLEL = 8
_PICKS_PER_AGENT = 5


def _make_gateway():
    """Module-level factory — monkeypatch this in tests to avoid network calls."""
    from src.data.gateway import DataGateway
    return DataGateway()


def _market_ctx() -> dict:
    """Lightweight market snapshot — VIX, SPY, yields. Reuse what brief_service uses."""
    try:
        from api.services.brief_service import _market_context
        return _market_context() or {}
    except Exception:
        return {}


def _run_one_agent(agent_key: str, ctx: dict, opportunities: list[dict], gateway) -> dict:
    """Discover this agent's picks from real data. Returns the agent_results shape."""
    p = AGENT_PERSONALITIES[agent_key]
    try:
        raw = daily_picks_agents.discover_for_agent(
            agent_key, opportunities=opportunities, gateway=gateway)
        picks = [{"symbol": r["symbol"], "rationale": "",
                  "conviction": r.get("conviction", ""), "evidence": r.get("evidence", {})}
                 for r in raw]
        return {"agent_key": agent_key, "agent_name": p["name"],
                "risk_tolerance": p.get("risk_tolerance", ""), "picks": picks, "error": None}
    except Exception as e:
        return {"agent_key": agent_key, "agent_name": p["name"],
                "risk_tolerance": p.get("risk_tolerance", ""), "picks": [], "error": str(e)[:200]}


def get_daily_picks(*, force: bool = False) -> dict:
    """Run all 8 agents in parallel, return consolidated payload.

    Cache key includes today's date — picks reset overnight.
    """
    today = date.today().isoformat()
    cache_key = f"daily_picks:v1:{today}"

    if not force:
        cached = cache_get(cache_key)
        if cached:
            cached["from_cache"] = True
            return cached

    ctx = _market_ctx()
    from api.services import discover_service
    opportunities = (discover_service.get_opportunities(limit=60, period="1M") or {}).get("opportunities", [])
    gateway = _make_gateway()
    agents = list(AGENT_PERSONALITIES.keys())
    agent_results: list[dict] = []
    with ThreadPoolExecutor(max_workers=_MAX_PARALLEL) as pool:
        futures = {pool.submit(_run_one_agent, k, ctx, opportunities, gateway): k for k in agents}
        for f in as_completed(futures):
            agent_results.append(f.result())
    order = {k: i for i, k in enumerate(agents)}
    agent_results.sort(key=lambda r: order.get(r["agent_key"], 999))

    consensus_payload = daily_picks_synthesis.synthesize(agent_results, ctx)

    payload: dict[str, Any] = {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "as_of_date": today,
        "market_context": ctx,
        "agents": agent_results,
        "consensus": consensus_payload.get("consensus", []),
        "contrarians": consensus_payload.get("contrarians", []),
        "from_cache": False,
    }

    # Enrich the unique picked symbols with a bullish option trade plan.
    # Best-effort: never break the picks payload if enrichment fails.
    try:
        from api.services import option_picks_service
        symbols: list[str] = []
        for a in agent_results:
            for pk in a.get("picks", []) or []:
                if isinstance(pk, dict) and pk.get("symbol"):
                    symbols.append(pk["symbol"])
        for row in consensus_payload.get("consensus", []):
            if row.get("symbol"):
                symbols.append(row["symbol"])
        for row in consensus_payload.get("contrarians", []):
            if row.get("symbol"):
                symbols.append(row["symbol"])
        symbols = list(dict.fromkeys(symbols))
        payload["option_plans"] = option_picks_service.enrich_symbols(symbols)
    except Exception:
        payload["option_plans"] = {}

    has_picks = bool(payload.get("consensus")) or any(a.get("picks") for a in agent_results)
    if has_picks:
        try:
            cache_set(cache_key, payload, ttl_minutes=_CACHE_TTL_HOURS * 60)
        except Exception:
            pass
    return payload
