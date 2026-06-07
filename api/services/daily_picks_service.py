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

from src.personalities import AGENT_PERSONALITIES
from src.utils.claude_cli import ask_claude_json
from src.utils.db import cache_get, cache_set


_CACHE_TTL_HOURS = 8
# Mirror the ai_analyst_service pattern: parallelize all personalities at
# once so wall-clock equals the slowest agent, not a sum-of-batches.
_MAX_PARALLEL = 8
_PICKS_PER_AGENT = 5


def _build_agent_prompt(agent_key: str, market_ctx: dict) -> str:
    """Build a personality-specific prompt asking the agent to pick 5 stocks."""
    p = AGENT_PERSONALITIES[agent_key]
    philosophy = (p.get("philosophy") or p.get("tagline") or "")[:400]
    return f"""You are {p['name']}. {philosophy}

Today's market context:
- VIX: {market_ctx.get('vix', '?')}
- S&P 500 3M: {market_ctx.get('spy_3m_pct', '?')}%
- 10Y yield: {market_ctx.get('tnx', '?')}%
- Top sector: {market_ctx.get('top_sector', '?')}

Pick exactly 5 stocks to BUY today based on YOUR investment style.
Bias hard toward your style — don't drift toward consensus.
Each pick: ticker, 1-sentence rationale, conviction (high/med/low).

Output JSON only:
{{"picks":[
  {{"symbol":"...","rationale":"...","conviction":"high"}},
  ...
]}}
"""


def _market_ctx() -> dict:
    """Lightweight market snapshot — VIX, SPY, yields. Reuse what brief_service uses."""
    try:
        from api.services.brief_service import _market_context
        return _market_context() or {}
    except Exception:
        return {}


def _run_one_agent(agent_key: str, market_ctx: dict) -> dict:
    """Run one agent. Returns {agent_key, agent_name, picks, error}."""
    p = AGENT_PERSONALITIES[agent_key]
    prompt = _build_agent_prompt(agent_key, market_ctx)
    try:
        result = ask_claude_json(prompt, model="haiku", timeout=120, retries=1)
        picks = result.get("picks", []) if isinstance(result, dict) else []
        # Cap to 5, normalize
        picks = picks[:_PICKS_PER_AGENT]
        for pk in picks:
            if isinstance(pk, dict):
                pk["symbol"] = (pk.get("symbol") or "").upper().strip()
        return {
            "agent_key": agent_key,
            "agent_name": p["name"],
            "risk_tolerance": p.get("risk_tolerance", ""),
            "picks": picks,
            "error": None,
        }
    except Exception as e:
        return {
            "agent_key": agent_key,
            "agent_name": p["name"],
            "risk_tolerance": p.get("risk_tolerance", ""),
            "picks": [],
            "error": str(e)[:200],
        }


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
    agents = list(AGENT_PERSONALITIES.keys())

    agent_results: list[dict] = []
    # Mirrors ai_analyst_service.py:1234 — ThreadPoolExecutor with
    # max_workers = number of personalities so all calls fire concurrently
    # and total wall-clock equals the slowest single agent.
    with ThreadPoolExecutor(max_workers=_MAX_PARALLEL) as pool:
        futures = {pool.submit(_run_one_agent, k, ctx): k for k in agents}
        for f in as_completed(futures):
            agent_results.append(f.result())

    # Stable order by personality key (insertion order of AGENT_PERSONALITIES)
    order = {k: i for i, k in enumerate(agents)}
    agent_results.sort(key=lambda r: order.get(r["agent_key"], 999))

    # Compute consensus + contrarian via the pure function in
    # src/analysis/daily_picks_consensus.py (built in Phase 1C).
    # If that module isn't deployed yet, gracefully degrade with empty lists.
    consensus_payload: dict[str, list] = {"consensus": [], "contrarians": []}
    try:
        from src.analysis.daily_picks_consensus import compute_consensus_and_contrarian
        consensus_payload = compute_consensus_and_contrarian(agent_results)
    except ImportError:
        pass
    except Exception:
        pass

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
        payload["option_plans"] = option_picks_service.enrich_symbols(symbols)
    except Exception:
        payload["option_plans"] = {}

    try:
        cache_set(cache_key, payload, ttl_minutes=_CACHE_TTL_HOURS * 60)
    except Exception:
        pass
    return payload
