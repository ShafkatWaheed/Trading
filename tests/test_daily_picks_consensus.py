"""Tests for daily_picks_consensus."""
from __future__ import annotations

from src.analysis.daily_picks_consensus import compute_consensus_and_contrarian


def _agent(key: str, name: str, picks: list[tuple[str, str, str]]) -> dict:
    """Helper: build agent_result dict from (symbol, rationale, conviction) tuples."""
    return {
        "agent_key": key, "agent_name": name, "risk_tolerance": "moderate",
        "picks": [{"symbol": s, "rationale": r, "conviction": c} for s, r, c in picks],
        "error": None,
    }


def test_consensus_requires_three_agents():
    """Symbol picked by 3+ agents is consensus. Below threshold = not."""
    results = [
        _agent("value", "Value", [("NVDA", "growth", "high"), ("XOM", "fcf", "high")]),
        _agent("growth", "Growth", [("NVDA", "AI", "high"), ("MSFT", "azure", "med")]),
        _agent("momentum", "Momentum", [("NVDA", "breakout", "high"), ("SPY", "trend", "low")]),
        _agent("contrarian", "Contrarian", [("XOM", "oversold", "med")]),  # XOM=2 only
    ]
    out = compute_consensus_and_contrarian(results)
    syms = {c["symbol"] for c in out["consensus"]}
    assert "NVDA" in syms              # 3 agents
    assert "XOM" not in syms           # only 2 agents
    # NVDA row has 3 agents
    nvda = next(c for c in out["consensus"] if c["symbol"] == "NVDA")
    assert nvda["agent_count"] == 3
    assert len(nvda["agents"]) == 3


def test_consensus_sorted_by_count_then_alpha():
    results = [
        _agent("a", "A", [("AAA", "x", "high"), ("BBB", "x", "high"), ("CCC", "x", "high")]),
        _agent("b", "B", [("AAA", "x", "high"), ("BBB", "x", "high"), ("CCC", "x", "high")]),
        _agent("c", "C", [("AAA", "x", "high"), ("BBB", "x", "high")]),
        _agent("d", "D", [("AAA", "x", "high")]),
    ]
    out = compute_consensus_and_contrarian(results)
    # AAA=4, BBB=3, CCC=2 (below threshold so skipped)
    assert [c["symbol"] for c in out["consensus"]] == ["AAA", "BBB"]
    assert out["consensus"][0]["agent_count"] == 4
    assert out["consensus"][1]["agent_count"] == 3


def test_contrarian_is_top_conviction_unique_pick_per_agent():
    """Each agent's contrarian = highest-conviction pick no other agent has."""
    results = [
        _agent("value", "Value", [
            ("AAPL", "shared", "high"),    # shared with growth
            ("BG",   "ag bottom", "high"), # unique
            ("LMT",  "defense", "low"),    # also unique but low
        ]),
        _agent("growth", "Growth", [
            ("AAPL", "still growing", "high"),  # shared with value
            ("ASML", "monopoly", "high"),       # unique
        ]),
    ]
    out = compute_consensus_and_contrarian(results)
    # Value's contrarian = BG (high conviction unique pick), not LMT
    value_c = next(c for c in out["contrarians"] if c["agent_key"] == "value")
    assert value_c["symbol"] == "BG"
    assert value_c["conviction"] == "high"
    # Growth's contrarian = ASML
    growth_c = next(c for c in out["contrarians"] if c["agent_key"] == "growth")
    assert growth_c["symbol"] == "ASML"


def test_contrarian_skips_agent_with_no_unique_picks():
    """If all an agent's picks were also picked by others, no contrarian for them."""
    results = [
        _agent("a", "A", [("AAA", "x", "high"), ("BBB", "x", "high")]),
        _agent("b", "B", [("AAA", "x", "high"), ("BBB", "x", "high")]),  # nothing unique
    ]
    out = compute_consensus_and_contrarian(results)
    # Both share AAA and BBB → no unique picks for either → both skipped
    assert out["contrarians"] == []


def test_handles_empty_inputs():
    assert compute_consensus_and_contrarian([]) == {"consensus": [], "contrarians": []}
    # Agents with no picks contribute nothing but don't crash
    results = [_agent("a", "A", [])]
    out = compute_consensus_and_contrarian(results)
    assert out == {"consensus": [], "contrarians": []}


def test_handles_missing_or_blank_symbols():
    """Symbols that are empty/whitespace are skipped, don't break the computation."""
    results = [
        {"agent_key": "x", "agent_name": "X", "risk_tolerance": "moderate",
         "picks": [{"symbol": "", "rationale": "blank", "conviction": "high"},
                   {"symbol": "  ", "rationale": "ws", "conviction": "high"},
                   {"symbol": "GOOD", "rationale": "ok", "conviction": "high"}],
         "error": None},
    ]
    out = compute_consensus_and_contrarian(results)
    # Only GOOD is a contrarian (unique to single agent)
    assert len(out["contrarians"]) == 1
    assert out["contrarians"][0]["symbol"] == "GOOD"
    assert out["consensus"] == []  # only 1 agent picked GOOD
