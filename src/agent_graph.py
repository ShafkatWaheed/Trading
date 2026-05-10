"""Graph-relevance helper for the AI agent (Phase 8).

Provides a clean, testable bridge between the agent's discovery loop and
the knowledge-graph relevance scorer. The agent picks candidates by
technical+fundamental score; this module adds a graph-relevance multiplier
that boosts candidates the graph thinks are aligned with currently-active
themes (e.g. "AI capex" + "uranium" + "rate cuts").

Usage from the agent:

    from src.agent_graph import (
        get_active_themes_from_agent_config,
        graph_boost_for_candidates,
    )

    themes = get_active_themes_from_agent_config()
    boosts = graph_boost_for_candidates(candidate_symbols, themes)
    final_score = base_score * boosts.get(symbol, 1.0)

When `themes` is empty (default), every multiplier is 1.0 — no behavior change.
"""

from __future__ import annotations

import json
from typing import Iterable

from src.graph.relevance import ActiveTheme, relevance_for_universe
from src.utils.db import get_connection, init_db


# Maximum boost from graph relevance. A score of 1.0 (perfectly aligned) maps
# to a multiplier of 1 + GRAPH_BOOST_CAP. We keep it modest so technical
# signals still dominate; graph relevance is a tiebreaker, not a takeover.
GRAPH_BOOST_CAP: float = 0.30


def graph_boost_for_candidates(
    symbols: Iterable[str],
    active_themes: list[ActiveTheme],
    *,
    cap: float = GRAPH_BOOST_CAP,
) -> dict[str, float]:
    """Return {symbol: multiplier} for each input symbol.

    Multiplier ∈ [1 - cap, 1 + cap]:
      * 1.0 when the stock has no graph relevance to active themes
      * > 1.0 when bullish-aligned (boost score)
      * < 1.0 when bearish-aligned (suppress score)

    `active_themes=[]` → all multipliers are 1.0 (no-op).
    """
    syms = [s.upper() for s in symbols]
    if not active_themes:
        return {sym: 1.0 for sym in syms}

    scores = relevance_for_universe(active_themes)
    out: dict[str, float] = {}
    for sym in syms:
        relevance = scores.get(sym)
        if relevance is None:
            out[sym] = 1.0
            continue
        # Clamp the signed score into [-1, 1], scale by cap, add to 1.0
        clamped = max(-1.0, min(1.0, relevance.score))
        out[sym] = 1.0 + cap * clamped
    return out


def get_active_themes_from_agent_config() -> list[ActiveTheme]:
    """Read currently-active themes from agent_config (JSON column).

    The agent_config table is the existing scheduler config; we add an
    optional `active_themes_json` column populated by the user (or by an
    upstream news-watching job in the future). Returns an empty list when
    the column is missing or empty.

    Schema-flexible: if the column doesn't exist, returns []. This keeps
    the agent backward-compatible with older DBs.
    """
    init_db()
    conn = get_connection()
    try:
        # Detect whether the column exists. SQLite allows ALTER TABLE ADD COLUMN
        # but the existing init_db doesn't define this column, so older DBs
        # may lack it. Probe via PRAGMA table_info.
        cols = {
            r["name"]
            for r in conn.execute("PRAGMA table_info(agent_config)").fetchall()
        }
        if "active_themes_json" not in cols:
            return []
        row = conn.execute(
            "SELECT active_themes_json FROM agent_config WHERE id = 1"
        ).fetchone()
        if not row or not row["active_themes_json"]:
            return []
        try:
            raw_themes = json.loads(row["active_themes_json"])
        except (ValueError, TypeError):
            return []
        if not isinstance(raw_themes, list):
            return []
        out: list[ActiveTheme] = []
        for r in raw_themes:
            if not isinstance(r, dict):
                continue
            out.append(ActiveTheme(
                commodity_code=r.get("commodity_code"),
                direction=r.get("direction") or "up",
                target_stock=r.get("target_stock"),
                intensity=float(r.get("intensity", 1.0)),
            ))
        return out
    finally:
        conn.close()


def set_active_themes_in_agent_config(themes: list[ActiveTheme]) -> None:
    """Persist active themes in agent_config so the next discovery cycle
    picks them up. Adds the column on first call if it doesn't exist."""
    init_db()
    conn = get_connection()
    try:
        cols = {
            r["name"]
            for r in conn.execute("PRAGMA table_info(agent_config)").fetchall()
        }
        if "active_themes_json" not in cols:
            conn.execute("ALTER TABLE agent_config ADD COLUMN active_themes_json TEXT")
            conn.commit()
        payload = json.dumps([
            {
                "commodity_code": t.commodity_code,
                "direction": t.direction,
                "target_stock": t.target_stock,
                "intensity": t.intensity,
            }
            for t in themes
        ])
        # Upsert into agent_config row id=1
        existing = conn.execute("SELECT 1 FROM agent_config WHERE id = 1").fetchone()
        if existing:
            conn.execute(
                "UPDATE agent_config SET active_themes_json = ? WHERE id = 1",
                (payload,),
            )
        else:
            conn.execute(
                "INSERT INTO agent_config (id, active_themes_json) VALUES (1, ?)",
                (payload,),
            )
        conn.commit()
    finally:
        conn.close()
