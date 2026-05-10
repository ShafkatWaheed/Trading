"""Graph-relevance scorer (Phase 8).

Given a set of currently-active themes (commodities-up/down, keyword-events,
or directly-named stocks), compute a `graph_relevance` score for any stock
in the universe. The score reflects how strongly the stock would benefit (or
suffer) given those themes — combining direct keyword/commodity hits AND
1-hop graph expansion via supplier/customer/peer/complement edges.

Used by the AI agent's discovery loop to BIAS candidate selection toward
stocks the graph thinks are relevant to the current news regime.

The implementation reuses `news_impact_service.analyze_news` indirectly by
calling the same primitives (causal_chain.trace_from_commodities + traverse.expand)
without re-tokenizing arbitrary text.

Public API:
    relevance_for_stock(symbol, active_themes) → RelevanceScore
    relevance_for_universe(active_themes, tier=...) → list[RelevanceScore]
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from src.graph import causal_chain, traverse
from src.utils.db import get_connection, init_db


@dataclass
class ActiveTheme:
    """One currently-active theme passed into the relevance scorer.

    Either `commodity_code` (with a direction) or `target_stock` is set —
    these are the two trigger types the scorer understands.
    """
    commodity_code: str | None = None
    direction: str = "up"             # 'up' | 'down' (only meaningful for commodities)
    target_stock: str | None = None
    intensity: float = 1.0            # 0..1 weighting of this theme


@dataclass
class RelevanceScore:
    """One stock's relevance to the active-theme set."""
    symbol: str
    score: float                      # signed: + bullish, - bearish (range bounded)
    magnitude: float                  # |score|, bounded 0..1
    reasons: list[str] = field(default_factory=list)


# ── core scoring ───────────────────────────────────────────────


def relevance_for_universe(
    active_themes: list[ActiveTheme],
    *,
    tier: list[str] | None = None,
    expand_hops: int = 1,
    conn: sqlite3.Connection | None = None,
) -> dict[str, RelevanceScore]:
    """Compute relevance scores for every stock in the universe (or tier slice).

    Returns a dict keyed by symbol. Stocks with zero relevance are omitted
    so the caller only sees actually-affected names.
    """
    if not active_themes:
        return {}

    init_db()
    own_conn = conn is None
    if own_conn:
        conn = get_connection()

    try:
        # 1) Run commodity causal chains for any commodity-themed entries
        commodity_moves: list[tuple[str, str]] = []
        for theme in active_themes:
            if theme.commodity_code:
                commodity_moves.append((theme.commodity_code, theme.direction))

        causal_hits = (
            causal_chain.trace_from_commodities(commodity_moves, expand_hops=expand_hops)
            if commodity_moves else {}
        )

        # 2) Run direct-stock graph expansion for target_stock themes
        stock_seeds: dict[str, float] = {}
        for theme in active_themes:
            if theme.target_stock:
                stock_seeds[theme.target_stock.upper()] = theme.intensity
        graph_hits: dict[str, traverse.GraphResult] = {}
        if stock_seeds:
            graph_hits = traverse.expand(
                stock_seeds.keys(),
                hops=expand_hops,
                edge_types=["peer", "supplier", "customer", "complement"],
                starting_polarity=stock_seeds,
                conn=conn,
            )

        # 3) Merge into RelevanceScore per symbol
        out: dict[str, RelevanceScore] = {}

        # 3a) From commodity causal hits
        intensity_by_commodity = {
            t.commodity_code: t.intensity for t in active_themes if t.commodity_code
        }
        for sym, hit in causal_hits.items():
            intensity = intensity_by_commodity.get(hit.commodity_code, 1.0)
            score = hit.polarity * hit.magnitude * intensity
            magnitude = abs(score)
            reasons = list(hit.chain[:3])    # cap chain length for UI
            existing = out.get(sym)
            if existing is None:
                out[sym] = RelevanceScore(
                    symbol=sym, score=score, magnitude=magnitude, reasons=reasons,
                )
            else:
                # Same-sign → diminishing-sum boost; opposite-sign → keep stronger
                if (existing.score >= 0) == (score >= 0):
                    new_mag = 1.0 - (1.0 - existing.magnitude) * (1.0 - magnitude)
                    existing.magnitude = new_mag
                    existing.score = (1.0 if existing.score >= 0 else -1.0) * new_mag
                    existing.reasons.extend(reasons)
                elif magnitude > existing.magnitude:
                    out[sym] = RelevanceScore(
                        symbol=sym, score=score, magnitude=magnitude, reasons=reasons,
                    )

        # 3b) From direct stock graph expansion (only NON-seeds, since seeds are
        #     directly named in active_themes — they're already known relevant)
        for sym, gr in graph_hits.items():
            if gr.hop == 0 and sym in stock_seeds:
                # Seed itself — its score is the starting intensity directly
                seed_intensity = stock_seeds[sym]
                if sym not in out:
                    out[sym] = RelevanceScore(
                        symbol=sym, score=seed_intensity, magnitude=abs(seed_intensity),
                        reasons=["direct seed"],
                    )
                continue
            # 1-hop or further — apply hop decay
            hop_decay = 0.6 ** gr.hop
            score = gr.cumulative_polarity * gr.cumulative_strength * hop_decay
            magnitude = abs(score)
            if magnitude < 0.05:
                continue
            edge_reasons = [
                f"  via {e.from_symbol} →{e.edge_type}→ {e.to_symbol}"
                for e in gr.incoming_edges[:2]
            ]
            existing = out.get(sym)
            if existing is None:
                out[sym] = RelevanceScore(
                    symbol=sym, score=score, magnitude=magnitude, reasons=edge_reasons,
                )
            elif magnitude > existing.magnitude:
                existing.score = score
                existing.magnitude = magnitude
                existing.reasons = edge_reasons + existing.reasons

        # 4) Tier filter (if specified)
        if tier:
            tlist = [t.upper() for t in tier]
            placeholders = ",".join("?" * len(tlist))
            allowed = {
                r["symbol"]
                for r in conn.execute(
                    f"SELECT symbol FROM stocks_universe WHERE tier IN ({placeholders})",
                    tlist,
                ).fetchall()
            }
            out = {k: v for k, v in out.items() if k in allowed}

        return out
    finally:
        if own_conn:
            conn.close()


def relevance_for_stock(
    symbol: str,
    active_themes: list[ActiveTheme],
    *,
    expand_hops: int = 1,
    conn: sqlite3.Connection | None = None,
) -> RelevanceScore:
    """Convenience wrapper: relevance for a single stock."""
    sym = symbol.upper()
    universe_scores = relevance_for_universe(
        active_themes, expand_hops=expand_hops, conn=conn,
    )
    if sym in universe_scores:
        return universe_scores[sym]
    return RelevanceScore(symbol=sym, score=0.0, magnitude=0.0, reasons=[])


# ── ranking helper ────────────────────────────────────────────


def top_n(
    scores: dict[str, RelevanceScore],
    *,
    n: int = 20,
    bullish_only: bool = False,
) -> list[RelevanceScore]:
    """Sort by magnitude descending. `bullish_only` returns only +ve scores."""
    rows = list(scores.values())
    if bullish_only:
        rows = [r for r in rows if r.score > 0]
    rows.sort(key=lambda r: -r.magnitude)
    return rows[:n]
