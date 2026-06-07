"""get_daily_picks produces non-empty grounded picks and doesn't cache empties."""
from __future__ import annotations

import api.services.daily_picks_service as dps
from src.utils.db import get_connection, init_db


def _fake_opps():
    return {"opportunities": [
        {"symbol": "AAA", "strategy": "Momentum", "score": 88,
         "secondary_strategies": [], "sub_scores": {}, "sector": "Tech", "price": 100},
        {"symbol": "BBB", "strategy": "Insider Accumulation", "score": 80,
         "secondary_strategies": [], "sub_scores": {}, "sector": "Tech", "price": 50},
    ]}


def _clear_cache():
    init_db()
    c = get_connection(); c.execute("DELETE FROM cache WHERE key LIKE 'daily_picks:%'")
    c.commit(); c.close()


def test_grounded_picks_non_empty(monkeypatch):
    _clear_cache()
    import api.services.discover_service as disc
    monkeypatch.setattr(disc, "get_opportunities", lambda **kw: _fake_opps())
    monkeypatch.setattr(dps, "_market_ctx", lambda: {})
    import api.services.daily_picks_synthesis as syn
    monkeypatch.setattr(syn, "synthesize",
                        lambda agents, ctx: {"consensus": [{"symbol": "AAA", "agent_count": 1,
                                                            "agents": ["momentum"], "rationale": "r"}],
                                             "contrarians": []})
    import api.services.option_picks_service as ops
    monkeypatch.setattr(ops, "enrich_symbols", lambda syms, **kw: {})

    payload = dps.get_daily_picks(force=True)
    assert payload["consensus"][0]["symbol"] == "AAA"
    assert any(a["picks"] for a in payload["agents"])


def test_empty_run_not_cached(monkeypatch):
    _clear_cache()
    import api.services.discover_service as disc
    monkeypatch.setattr(disc, "get_opportunities", lambda **kw: {"opportunities": []})
    monkeypatch.setattr(dps, "_market_ctx", lambda: {})
    import api.services.daily_picks_synthesis as syn
    monkeypatch.setattr(syn, "synthesize", lambda agents, ctx: {"consensus": [], "contrarians": []})
    import api.services.option_picks_service as ops
    monkeypatch.setattr(ops, "enrich_symbols", lambda syms, **kw: {})

    payload = dps.get_daily_picks(force=True)
    assert payload["consensus"] == []
    c = get_connection()
    row = c.execute("SELECT COUNT(*) FROM cache WHERE key LIKE 'daily_picks:%'").fetchone()[0]
    c.close()
    assert row == 0  # empty payload must NOT be cached
