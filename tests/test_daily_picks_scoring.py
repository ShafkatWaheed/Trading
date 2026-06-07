"""Pure tests for daily_picks_scoring (no I/O)."""
from __future__ import annotations

from src.analysis.daily_picks_scoring import conviction_from_score, rank_candidates


def test_conviction_thresholds():
    assert conviction_from_score(85) == "high"
    assert conviction_from_score(70) == "high"
    assert conviction_from_score(69.9) == "med"
    assert conviction_from_score(45) == "med"
    assert conviction_from_score(44.9) == "low"
    assert conviction_from_score(0) == "low"
    assert conviction_from_score(None) == "low"


def test_rank_candidates_sorts_desc_and_truncates():
    cands = [{"symbol": "A", "score": 10}, {"symbol": "B", "score": 90},
             {"symbol": "C", "score": 50}]
    out = rank_candidates(cands, key="score", top_n=2)
    assert [c["symbol"] for c in out] == ["B", "C"]


def test_rank_candidates_stable_for_ties():
    cands = [{"symbol": "A", "score": 50}, {"symbol": "B", "score": 50}]
    out = rank_candidates(cands, key="score", top_n=5)
    assert [c["symbol"] for c in out] == ["A", "B"]  # input order preserved on ties
