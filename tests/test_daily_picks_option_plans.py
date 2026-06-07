"""get_daily_picks attaches option_plans for the unique picked symbols.

We stub the agent run + enrichment so no claude CLI / network is touched."""
from __future__ import annotations

import api.services.daily_picks_service as dps


def test_payload_includes_option_plans(monkeypatch):
    # Stub the 8-agent run with two agents picking overlapping symbols.
    fake_agents = [
        {"agent_key": "a1", "agent_name": "A1", "risk_tolerance": "",
         "picks": [{"symbol": "AAA", "rationale": "x", "conviction": "high"},
                   {"symbol": "BBB", "rationale": "y", "conviction": "med"}],
         "error": None},
        {"agent_key": "a2", "agent_name": "A2", "risk_tolerance": "",
         "picks": [{"symbol": "AAA", "rationale": "z", "conviction": "high"}],
         "error": None},
    ]
    monkeypatch.setattr(dps, "_run_one_agent",
                        lambda k, ctx: fake_agents[0] if k == "a1" else fake_agents[1])
    monkeypatch.setattr(dps, "AGENT_PERSONALITIES", {"a1": {"name": "A1"},
                                                     "a2": {"name": "A2"}})
    monkeypatch.setattr(dps, "_market_ctx", lambda: {})

    captured = {}

    def fake_enrich(symbols, **kw):
        captured["symbols"] = sorted(set(s.upper() for s in symbols))
        return {s.upper(): {"direction": "bullish", "entry": "100"}
                for s in symbols}

    import api.services.option_picks_service as ops
    monkeypatch.setattr(ops, "enrich_symbols", fake_enrich)

    payload = dps.get_daily_picks(force=True)
    assert "option_plans" in payload
    assert set(captured["symbols"]) == {"AAA", "BBB"}
    assert payload["option_plans"]["AAA"]["direction"] == "bullish"
