"""Daily Picks — what to buy today, grounded in real market data.

Each of the 8 agents runs a deterministic per-lens screen over the real
opportunity cards from discover_service (+ DataGateway for the value/options
lenses) — see api/services/daily_picks_agents.py. A single Claude synthesis
pass (api/services/daily_picks_synthesis.py) then ranks the agents' real
candidates into consensus + contrarian picks with rationale, falling back to
the deterministic compute_consensus_and_contrarian if the LLM is unavailable.
Picks are enriched with option trade plans and cached per day (empty payloads
are never cached). The brief pipeline is intentionally NOT used here.
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


def get_daily_picks(*, force: bool = False, job_key: str | None = None) -> dict:
    """Run all 8 agents in parallel, return consolidated payload.

    Cache key includes today's date — picks reset overnight.

    `job_key` — when set, emits heartbeat(job_key, phase, progress_pct)
    between phases so the background-jobs tracker can surface progress
    and the 5-min watchdog can reap stuck Claude subprocesses. No-op
    when called synchronously (force=True from a user click).
    """
    def _hb(phase: str, pct: int) -> None:
        if not job_key:
            return
        try:
            from api.services._background_jobs import heartbeat
            heartbeat(job_key, phase=phase, progress_pct=pct)
        except Exception:
            pass
    today = date.today().isoformat()
    cache_key = f"daily_picks:v1:{today}"

    if not force:
        cached = cache_get(cache_key)
        if cached:
            cached["from_cache"] = True
            return cached

    _hb("context", 5)
    ctx = _market_ctx()
    from api.services import discover_service
    opportunities = (discover_service.get_opportunities(limit=60, period="1M") or {}).get("opportunities", [])
    gateway = _make_gateway()
    agents = list(AGENT_PERSONALITIES.keys())
    agent_results: list[dict] = []

    _hb("agents", 20)
    with ThreadPoolExecutor(max_workers=_MAX_PARALLEL) as pool:
        futures = {pool.submit(_run_one_agent, k, ctx, opportunities, gateway): k for k in agents}
        completed = 0
        for f in as_completed(futures):
            agent_results.append(f.result())
            completed += 1
            # Each agent completion ticks progress 20→70 across the 8 agents.
            _hb("agents", 20 + int((completed / max(len(agents), 1)) * 50))
    order = {k: i for i, k in enumerate(agents)}
    agent_results.sort(key=lambda r: order.get(r["agent_key"], 999))

    _hb("synthesis", 75)
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

    _hb("enrich", 85)

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
    _hb("done", 95)
    return payload
