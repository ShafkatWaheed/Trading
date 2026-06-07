"""Tests for daily_picks_service orchestrator (grounded discovery + synthesis)."""
from __future__ import annotations

import api.services.daily_picks_service as dps
from src.utils.db import get_connection, init_db


def _opps():
    # Cards spanning several strategies so multiple lenses find a candidate.
    return {"opportunities": [
        {"symbol": "AAA", "strategy": "Momentum", "score": 88,
         "secondary_strategies": [], "sub_scores": {}, "sector": "Tech", "price": 100},
        {"symbol": "BBB", "strategy": "Insider Accumulation", "score": 80,
         "secondary_strategies": [], "sub_scores": {}, "sector": "Tech", "price": 50},
        {"symbol": "CCC", "strategy": "Oversold Bounce", "score": 60,
         "secondary_strategies": [], "sub_scores": {}, "sector": "Health", "price": 30},
        {"symbol": "DDD", "strategy": "Sector Leader", "score": 70,
         "secondary_strategies": [], "sub_scores": {}, "sector": "Energy", "price": 20},
        {"symbol": "EEE", "strategy": "Congress Buying", "score": 65,
         "secondary_strategies": [], "sub_scores": {}, "sector": "Defense", "price": 40},
    ]}


def _clear_cache():
    init_db()
    c = get_connection()
    c.execute("DELETE FROM cache WHERE key LIKE 'daily_picks:%'")
    c.commit(); c.close()


def _patch_common(monkeypatch):
    import api.services.discover_service as disc
    import api.services.daily_picks_synthesis as syn
    import api.services.option_picks_service as ops
    monkeypatch.setattr(disc, "get_opportunities", lambda **kw: _opps())
    monkeypatch.setattr(dps, "_market_ctx", lambda: {"vix": 15})
    monkeypatch.setattr(syn, "synthesize",
                        lambda agents, ctx: {"consensus": [{"symbol": "AAA", "agent_count": 1,
                                                            "agents": ["momentum"], "rationale": "r"}],
                                             "contrarians": []})
    monkeypatch.setattr(ops, "enrich_symbols", lambda syms, **kw: {})

    class _FakeGateway:
        def get_fundamentals(self, s): return None
        def get_options_summary(self, s): return None

    monkeypatch.setattr(dps, "_make_gateway", lambda: _FakeGateway())


def test_get_daily_picks_runs_all_agents(monkeypatch):
    """Service runs all 8 agents over real candidates and returns consensus."""
    _clear_cache()
    _patch_common(monkeypatch)
    out = dps.get_daily_picks(force=True)
    assert len(out["agents"]) == 8
    assert any(a["picks"] for a in out["agents"])      # at least some lenses matched
    assert out["consensus"][0]["symbol"] == "AAA"
    assert out["as_of_date"] and "generated_at" in out


def test_get_daily_picks_isolates_agent_failure(monkeypatch):
    """If one agent's discovery raises, others still produce; that agent records an error."""
    _clear_cache()
    _patch_common(monkeypatch)
    import api.services.daily_picks_agents as dpa
    real = dpa.discover_for_agent

    def flaky(agent_key, **kw):
        if agent_key == "momentum":
            raise RuntimeError("boom")
        return real(agent_key, **kw)

    monkeypatch.setattr(dpa, "discover_for_agent", flaky)
    out = dps.get_daily_picks(force=True)
    assert len(out["agents"]) == 8
    momentum = next(a for a in out["agents"] if a["agent_key"] == "momentum")
    assert momentum["error"]                            # failure isolated to this agent
    assert momentum["picks"] == []


def test_get_daily_picks_uses_cache_within_day(monkeypatch):
    """Second same-day call returns the cached payload (no re-discovery)."""
    _clear_cache()
    _patch_common(monkeypatch)
    import api.services.discover_service as disc
    calls = {"n": 0}

    def counting(**kw):
        calls["n"] += 1
        return _opps()

    monkeypatch.setattr(disc, "get_opportunities", counting)
    dps.get_daily_picks(force=True)
    first = calls["n"]
    dps.get_daily_picks(force=False)                    # should hit cache
    assert calls["n"] == first, "second call should not re-run discovery"
