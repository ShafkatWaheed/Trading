"""Synthesis pass for daily picks: rank + consensus/contrarian + rationale.

Hands Claude the agents' REAL picks + evidence and asks it to rank/dedupe/explain
(never to invent), so it does not hit the 'refuse to fabricate' path. If the LLM
fails/parses empty, falls back to the deterministic compute_consensus_and_contrarian
so the page is never empty when candidates exist. No brief import.
"""
from __future__ import annotations

import json

from src.analysis.daily_picks_consensus import compute_consensus_and_contrarian
from src.utils.claude_cli import ask_claude_json
from src.utils.db import init_db, log_api_call


def _build_prompt(agent_results: list[dict], market_ctx: dict) -> str:
    lines = []
    for a in agent_results:
        picks = a.get("picks") or []
        if not picks:
            continue
        lines.append(f"{a.get('agent_name')} ({a.get('agent_key')}):")
        for p in picks:
            lines.append(f"  - {p['symbol']} [{p.get('conviction','')}] evidence={json.dumps(p.get('evidence') or {})}")
    body = "\n".join(lines)
    return f"""You are ranking REAL stock candidates already screened by 8 strategy agents.
Do NOT invent tickers — only use the symbols below. Use the evidence to rank.

Market context: {json.dumps(market_ctx or {})}

Agent picks:
{body}

Produce JSON only:
{{"consensus":[{{"symbol":"...","agent_count":N,"agents":["key",...],"rationale":"1-2 sentences citing the evidence"}}],
  "contrarians":[{{"agent_key":"...","agent_name":"...","symbol":"...","rationale":"...","conviction":"high|med|low"}}]}}
Consensus = symbols multiple agents independently picked, ranked by conviction+agent_count.
Contrarians = each agent's strongest pick no other agent chose.
"""


def synthesize(agent_results: list[dict], market_ctx: dict) -> dict:
    """Return {"consensus": [...], "contrarians": [...]}. Never raises."""
    init_db()
    has_picks = any((a.get("picks") for a in agent_results))
    if not has_picks:
        return {"consensus": [], "contrarians": []}

    try:
        result = ask_claude_json(_build_prompt(agent_results, market_ctx),
                                 model="haiku", timeout=120, retries=1)
        if isinstance(result, dict) and isinstance(result.get("consensus"), list):
            result.setdefault("contrarians", [])
            log_api_call("daily_picks_synth", "synthesize", "success")
            return {"consensus": result["consensus"], "contrarians": result["contrarians"]}
    except Exception as exc:
        log_api_call("daily_picks_synth", "synthesize", "error", error=str(exc)[:200])

    log_api_call("daily_picks_synth", "synthesize", "fallback")
    return compute_consensus_and_contrarian(agent_results)
