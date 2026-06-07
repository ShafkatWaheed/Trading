"""daily_picks_synthesis.synthesize — Claude ranking with deterministic fallback."""
from __future__ import annotations

import api.services.daily_picks_synthesis as syn


def _agents():
    return [
        {"agent_key": "momentum", "agent_name": "Momentum Trader", "risk_tolerance": "aggressive",
         "picks": [{"symbol": "AAA", "rationale": "", "conviction": "high"},
                   {"symbol": "BBB", "rationale": "", "conviction": "med"}], "error": None},
        {"agent_key": "insider", "agent_name": "Insider Shadow", "risk_tolerance": "moderate",
         "picks": [{"symbol": "AAA", "rationale": "", "conviction": "high"}], "error": None},
        {"agent_key": "value", "agent_name": "Value Investor", "risk_tolerance": "conservative",
         "picks": [{"symbol": "AAA", "rationale": "", "conviction": "high"}], "error": None},
    ]


def test_synthesize_uses_claude_json_when_available(monkeypatch):
    def fake_json(prompt, **kw):
        return {"consensus": [{"symbol": "AAA", "agent_count": 2, "agents": ["momentum", "insider"],
                               "rationale": "Two lenses converge on AAA."}],
                "contrarians": [{"agent_key": "momentum", "agent_name": "Momentum Trader",
                                 "symbol": "BBB", "rationale": "Momentum's unique call.",
                                 "conviction": "med"}]}
    monkeypatch.setattr(syn, "ask_claude_json", fake_json)
    out = syn.synthesize(_agents(), {"vix": 15})
    assert out["consensus"][0]["symbol"] == "AAA"
    assert out["consensus"][0]["rationale"]
    assert out["contrarians"][0]["symbol"] == "BBB"


def test_synthesize_falls_back_when_claude_returns_none(monkeypatch):
    monkeypatch.setattr(syn, "ask_claude_json", lambda prompt, **kw: None)
    out = syn.synthesize(_agents(), {})
    assert any(c["symbol"] == "AAA" for c in out["consensus"])
    assert "contrarians" in out


def test_synthesize_empty_agents_returns_empty(monkeypatch):
    monkeypatch.setattr(syn, "ask_claude_json", lambda prompt, **kw: None)
    out = syn.synthesize([], {})
    assert out == {"consensus": [], "contrarians": []}


def test_synthesize_falls_back_when_claude_raises(monkeypatch):
    def boom(prompt, **kw):
        raise RuntimeError("claude timeout")
    monkeypatch.setattr(syn, "ask_claude_json", boom)
    out = syn.synthesize(_agents(), {})
    assert any(c["symbol"] == "AAA" for c in out["consensus"])  # deterministic fallback used


def test_synthesize_falls_back_on_parse_miss(monkeypatch):
    # dict returned but no usable "consensus" list -> fallback
    monkeypatch.setattr(syn, "ask_claude_json", lambda prompt, **kw: {"rankings": [{"symbol": "AAA"}]})
    out = syn.synthesize(_agents(), {})
    assert any(c["symbol"] == "AAA" for c in out["consensus"])
