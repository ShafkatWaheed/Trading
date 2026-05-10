"""Tests for src/graph/rank.py — composite scoring + hop decay."""

from __future__ import annotations

import math

import pytest

from src.graph.rank import (
    HOP_DECAY,
    TIER_WEIGHT,
    edge_confidence_weight,
    hop_decay,
    rank,
    tier_weight,
)
from src.graph.traverse import Edge, GraphResult


# ── primitive helpers ────────────────────────────────────────────


def test_tier_weight_known_tiers():
    assert tier_weight("A") == 1.0
    assert tier_weight("B") == 0.7
    assert tier_weight("C") == 0.4
    assert tier_weight("D") == 0.1


def test_tier_weight_lowercase_input():
    assert tier_weight("a") == 1.0


def test_tier_weight_unknown_is_zero():
    assert tier_weight(None) == 0.0
    assert tier_weight("X") == 0.0


def test_hop_decay_values():
    assert hop_decay(0) == 1.0
    assert hop_decay(1) == 0.6
    assert hop_decay(2) == 0.3
    assert hop_decay(3) == 0.15


def test_hop_decay_beyond_known_is_zero():
    assert hop_decay(10) == 0.0


def test_edge_confidence_weight_picks_max():
    edges = [
        Edge("A", "B", "peer", 0.5, 1.0, "low", "claude_batch"),
        Edge("A", "C", "peer", 0.5, 1.0, "high", "hand"),
    ]
    gr = GraphResult(symbol="A", hop=1, incoming_edges=edges)
    assert edge_confidence_weight(gr) == 1.0   # 'high' wins


def test_edge_confidence_weight_seed_no_edges_is_one():
    gr = GraphResult(symbol="X", hop=0, incoming_edges=[])
    assert edge_confidence_weight(gr) == 1.0


# ── ranking ──────────────────────────────────────────────────────


def _make_result(symbol: str, hop: int, polarity: float = 1.0,
                 strength: float = 1.0, confidence: str = "high") -> GraphResult:
    edges = []
    if hop > 0:
        edges = [Edge("seed", symbol, "peer", strength, polarity, confidence, "hand")]
    return GraphResult(
        symbol=symbol,
        hop=hop,
        incoming_edges=edges,
        cumulative_polarity=polarity,
        cumulative_strength=strength,
    )


def test_rank_seeds_score_one_when_tier_a():
    seeds = {"NVDA": _make_result("NVDA", 0)}
    out = rank(seeds, tiers={"NVDA": "A"})
    assert len(out) == 1
    assert math.isclose(out[0].composite_score, 1.0)


def test_rank_tier_d_seed_scores_low():
    seeds = {"X": _make_result("X", 0)}
    out = rank(seeds, tiers={"X": "D"})
    assert math.isclose(out[0].composite_score, 0.1)


def test_rank_unknown_tier_drops_to_zero():
    seeds = {"X": _make_result("X", 0)}
    out = rank(seeds, tiers={})    # no tier provided
    assert out[0].composite_score == 0.0


def test_rank_one_hop_decay_applied():
    seeds = {
        "NVDA": _make_result("NVDA", 0),
        "AVGO": _make_result("AVGO", 1),
    }
    out = rank(seeds, tiers={"NVDA": "A", "AVGO": "A"})
    nvda = next(r for r in out if r.symbol == "NVDA")
    avgo = next(r for r in out if r.symbol == "AVGO")
    # NVDA gets full score; AVGO at hop=1 gets ×0.6
    assert math.isclose(avgo.composite_score, 0.6)
    assert nvda.composite_score > avgo.composite_score


def test_rank_polarity_magnitude_used():
    """A negative polarity should still produce positive composite_score
    (we sort by magnitude; the sign is shown separately)."""
    seeds = {"X": _make_result("X", 1, polarity=-1.0, strength=0.5)}
    out = rank(seeds, tiers={"X": "A"})
    assert out[0].composite_score > 0
    assert out[0].polarity == -1.0


def test_rank_industry_boost_amplifies_score():
    seeds = {"X": _make_result("X", 1)}
    no_boost = rank(seeds, tiers={"X": "A"})
    boosted = rank(seeds, tiers={"X": "A"}, industry_boost={"X": 0.8})
    assert boosted[0].composite_score < no_boost[0].composite_score   # boost < 1.0 reduces


def test_rank_opp_score_amplifies_score():
    seeds = {"X": _make_result("X", 1)}
    no_score = rank(seeds, tiers={"X": "A"})
    scored = rank(seeds, tiers={"X": "A"}, opp_scores={"X": 0.5})
    assert scored[0].composite_score < no_score[0].composite_score


def test_rank_min_score_filters_low_results():
    seeds = {
        "STRONG": _make_result("STRONG", 0),                          # score 1.0
        "WEAK":   _make_result("WEAK", 3, polarity=1.0, strength=0.5), # score 0.5 * 0.15 = 0.075
    }
    out = rank(seeds, tiers={"STRONG": "A", "WEAK": "A"}, min_score=0.5)
    syms = {r.symbol for r in out}
    assert "STRONG" in syms
    assert "WEAK" not in syms


def test_rank_sorted_descending_by_score():
    seeds = {
        "TOP":  _make_result("TOP", 0),                                         # 1.0
        "MID":  _make_result("MID", 1, strength=0.8),                           # 0.8 * 0.6 = 0.48
        "LOW":  _make_result("LOW", 2, strength=0.4),                           # 0.4 * 0.3 = 0.12
    }
    out = rank(seeds, tiers={"TOP": "A", "MID": "A", "LOW": "A"})
    syms = [r.symbol for r in out]
    assert syms == ["TOP", "MID", "LOW"]


def test_rank_hop_zero_preferred_at_score_tie():
    """When two stocks tie on score, the one with lower hop ranks first."""
    seeds = {
        "DIRECT": _make_result("DIRECT", 0, strength=0.6),       # 0.6 * 1.0 = 0.6
        "HOPPED": _make_result("HOPPED", 1, strength=1.0),       # 1.0 * 0.6 = 0.6
    }
    out = rank(seeds, tiers={"DIRECT": "A", "HOPPED": "A"})
    syms = [r.symbol for r in out]
    assert syms == ["DIRECT", "HOPPED"]


def test_rank_why_trace_populated_for_non_seed():
    seeds = {
        "NVDA": _make_result("NVDA", 0),
        "TSM":  _make_result("TSM", 1),
    }
    out = rank(seeds, tiers={"NVDA": "A", "TSM": "A"})
    nvda = next(r for r in out if r.symbol == "NVDA")
    tsm = next(r for r in out if r.symbol == "TSM")
    assert nvda.why == ["seed"]
    assert "→peer" in tsm.why[0] or "→supplier" in tsm.why[0] or "→customer" in tsm.why[0]


def test_rank_low_confidence_reduces_score():
    """A 'low' confidence edge weights the score down by 0.4 vs 1.0 for 'high'."""
    high_seeds = {"X": _make_result("X", 1, confidence="high")}
    low_seeds  = {"X": _make_result("X", 1, confidence="low")}
    high_out = rank(high_seeds, tiers={"X": "A"})
    low_out  = rank(low_seeds,  tiers={"X": "A"})
    assert low_out[0].composite_score < high_out[0].composite_score
