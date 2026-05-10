"""Graph-relevance service (Phase 8).

Exposes the graph relevance scorer over an HTTP API. Callers (the agent,
the React UI, downstream tools) can ask:

    "Given these active themes, which stocks does the graph think are relevant?"
"""

from __future__ import annotations

from src.graph.relevance import ActiveTheme, relevance_for_universe, top_n


def compute_relevance(
    active_themes: list[dict],
    *,
    tier: list[str] | None = None,
    bullish_only: bool = False,
    limit: int = 50,
) -> dict:
    """Compute and rank graph relevance for a set of active themes.

    Args:
        active_themes: list of {commodity_code | target_stock, direction, intensity}.
        tier: optional tier filter (e.g. ['A','B']).
        bullish_only: skip stocks with negative scores.
        limit: cap results.
    """
    themes = []
    for raw in active_themes:
        themes.append(ActiveTheme(
            commodity_code=raw.get("commodity_code"),
            direction=raw.get("direction") or "up",
            target_stock=raw.get("target_stock"),
            intensity=float(raw.get("intensity", 1.0)),
        ))
    scores = relevance_for_universe(themes, tier=tier)
    ranked = top_n(scores, n=limit, bullish_only=bullish_only)

    return {
        "active_themes": [
            {
                "commodity_code": t.commodity_code,
                "direction": t.direction,
                "target_stock": t.target_stock,
                "intensity": t.intensity,
            }
            for t in themes
        ],
        "relevance": [
            {
                "symbol": r.symbol,
                "score": r.score,
                "magnitude": r.magnitude,
                "reasons": r.reasons,
            }
            for r in ranked
        ],
        "total": len(scores),
    }
