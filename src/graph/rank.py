"""Composite ranking for graph expansion results.

Inputs:
  * `GraphResult` per stock (hop, cumulative polarity, cumulative strength, edges)
  * Tier from stocks_universe (A=1.0 / B=0.7 / C=0.4 / D=0.1)
  * Optional per-stock industry boost (the news-impact aggregator's per-industry strength)
  * Optional per-stock opportunity score (existing technical/fundamental signal)

Composite formula:

    score = abs(cumulative_polarity)
          × cumulative_strength
          × tier_weight
          × hop_decay(hop)
          × industry_boost           # 1.0 when no boost provided
          × opp_score                # 1.0 when no score provided
          × edge_confidence_weight

Hop decay: direct hit = 1.0, 1-hop = 0.6, 2-hop = 0.3, 3-hop = 0.15.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from src.graph.traverse import GraphResult


TIER_WEIGHT: dict[str, float] = {"A": 1.0, "B": 0.7, "C": 0.4, "D": 0.1}
HOP_DECAY: dict[int, float] = {0: 1.0, 1: 0.6, 2: 0.3, 3: 0.15, 4: 0.075}
CONFIDENCE_WEIGHT: dict[str, float] = {"high": 1.0, "medium": 0.7, "low": 0.4}


def hop_decay(hop: int) -> float:
    """Multiplier for distance from a seed node. Saturates at 0 beyond 4 hops."""
    if hop in HOP_DECAY:
        return HOP_DECAY[hop]
    return 0.0 if hop > 4 else 1.0


def tier_weight(tier: str | None) -> float:
    if tier is None:
        return 0.0
    return TIER_WEIGHT.get(tier.upper(), 0.0)


def edge_confidence_weight(result: GraphResult) -> float:
    """Best (max) confidence across the result's incoming edges."""
    if not result.incoming_edges:
        return 1.0       # seed node — no edge to weight
    weights = [CONFIDENCE_WEIGHT.get(e.confidence, 0.4) for e in result.incoming_edges]
    return max(weights)


@dataclass
class RankedResult:
    """A traversal result with its final composite score."""
    symbol: str
    hop: int
    tier: str | None
    polarity: float
    strength: float
    composite_score: float
    why: list[str]               # short trace strings, one per hop


def _build_why_trace(result: GraphResult) -> list[str]:
    """One-line summary of how this stock got here."""
    if not result.incoming_edges:
        return ["seed"]
    out = []
    for e in result.incoming_edges:
        sign = "+" if e.polarity > 0 else "-"
        out.append(
            f"{e.from_symbol} →{e.edge_type}({sign}{e.strength:.2f}) {e.to_symbol}"
        )
    return out


def rank(
    results: Mapping[str, GraphResult],
    *,
    tiers: Mapping[str, str] | None = None,
    industry_boost: Mapping[str, float] | None = None,
    opp_scores: Mapping[str, float] | None = None,
    min_score: float = 0.0,
) -> list[RankedResult]:
    """Compute composite scores and return a ranked list, descending.

    Args:
        results: output of `traverse.expand`.
        tiers: optional {symbol: tier} map. If absent, tier_weight=0 ⇒ score=0.
        industry_boost: optional {symbol: 0..1} multiplier from news-impact engine.
        opp_scores: optional {symbol: 0..1} multiplier from existing signal score.
        min_score: drop results below this composite.
    """
    tiers = tiers or {}
    industry_boost = industry_boost or {}
    opp_scores = opp_scores or {}

    out: list[RankedResult] = []
    for sym, gr in results.items():
        tier = tiers.get(sym)
        tw = tier_weight(tier)
        hd = hop_decay(gr.hop)
        ib = industry_boost.get(sym, 1.0)
        ops = opp_scores.get(sym, 1.0)
        cw = edge_confidence_weight(gr)

        composite = (
            abs(gr.cumulative_polarity)
            * gr.cumulative_strength
            * tw
            * hd
            * ib
            * ops
            * cw
        )
        if composite < min_score:
            continue
        out.append(RankedResult(
            symbol=sym,
            hop=gr.hop,
            tier=tier,
            polarity=gr.cumulative_polarity,
            strength=gr.cumulative_strength,
            composite_score=composite,
            why=_build_why_trace(gr),
        ))

    # Hop=0 (seed) rises to the top within its score bucket; sort by score desc
    # then prefer lower hop in ties.
    out.sort(key=lambda r: (-r.composite_score, r.hop, r.symbol))
    return out
