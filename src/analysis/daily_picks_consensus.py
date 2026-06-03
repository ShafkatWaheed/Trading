"""Compute consensus + contrarian picks from multi-agent results.

Per CLAUDE.md: pure analysis, no I/O. Inputs are already-fetched data
(in this case, the list of agent results from daily_picks_service).
"""
from __future__ import annotations

from collections import defaultdict


_CONSENSUS_THRESHOLD = 3  # need at least 3 agents to agree

# Conviction priority (higher = better). Accepts "high"/"med"/"medium"/"low".
_CONVICTION_PRIORITY = {"high": 3, "med": 2, "medium": 2, "low": 1}


def compute_consensus_and_contrarian(agent_results: list[dict]) -> dict:
    """Process N agent results into consensus + contrarian rows.

    Args:
        agent_results: list of {agent_key, agent_name, risk_tolerance,
                                picks: list[{symbol, rationale, conviction}],
                                error: str | None}

    Returns:
        {
            "consensus": [
                {
                    "symbol": str,
                    "agent_count": int,
                    "agents": [{agent_key, agent_name, rationale, conviction}, ...],
                },
                ...sorted by agent_count desc, then symbol asc
            ],
            "contrarians": [
                {
                    "agent_key": str,
                    "agent_name": str,
                    "symbol": str,
                    "rationale": str,
                    "conviction": str,
                },
                ...one per agent that has a unique pick (no contrarian if all
                their picks were also picked by others; skipped silently)
            ],
        }

    Rules:
    - Consensus = stocks picked by >= _CONSENSUS_THRESHOLD agents
    - Contrarian per agent = their TOP-conviction pick whose symbol
      no other agent picked. Conviction priority: high > med > low.
      Within same conviction, picks earlier in the agent's list win.
    - Errors are tolerated: agents with empty picks contribute nothing
      to consensus and have no contrarian.
    """
    # 1. Build per-symbol roll-up: symbol -> list of agent-pick dicts.
    by_symbol: dict[str, list[dict]] = defaultdict(list)

    for a in agent_results:
        for pk in a.get("picks", []) or []:
            sym = (pk.get("symbol") or "").upper().strip()
            if not sym:
                continue
            by_symbol[sym].append({
                "agent_key": a["agent_key"],
                "agent_name": a["agent_name"],
                "rationale": pk.get("rationale", ""),
                "conviction": pk.get("conviction", "med"),
            })

    # 2. Consensus = symbols with >= threshold agents.
    consensus_rows: list[dict] = []
    for sym, picks_list in by_symbol.items():
        if len(picks_list) >= _CONSENSUS_THRESHOLD:
            consensus_rows.append({
                "symbol": sym,
                "agent_count": len(picks_list),
                "agents": picks_list,
            })
    # Sort: most-agreed first, then alpha.
    consensus_rows.sort(key=lambda r: (-r["agent_count"], r["symbol"]))

    # 3. Contrarian per agent = highest-conviction pick unique to that agent.
    contrarians: list[dict] = []
    for a in agent_results:
        my_picks = a.get("picks", []) or []
        if not my_picks:
            continue
        unique_picks: list[tuple[int, int, dict, str]] = []
        for idx, pk in enumerate(my_picks):
            sym = (pk.get("symbol") or "").upper().strip()
            if not sym:
                continue
            others = [p for p in by_symbol[sym] if p["agent_key"] != a["agent_key"]]
            if not others:
                priority = _CONVICTION_PRIORITY.get(
                    (pk.get("conviction") or "med").lower(), 2
                )
                # earlier idx wins ties → use -idx so larger sorts first.
                unique_picks.append((priority, -idx, pk, sym))
        if not unique_picks:
            continue
        unique_picks.sort(reverse=True)
        _, _, top, sym = unique_picks[0]
        contrarians.append({
            "agent_key": a["agent_key"],
            "agent_name": a["agent_name"],
            "symbol": sym,
            "rationale": top.get("rationale", ""),
            "conviction": top.get("conviction", "med"),
        })

    return {"consensus": consensus_rows, "contrarians": contrarians}
