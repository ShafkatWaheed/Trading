"""Macro agent selects opportunities in inflow sectors + dividend plays."""
from __future__ import annotations

import api.services.daily_picks_agents as dpa


def _card(sym, sector, score=70):
    return {"symbol": sym, "strategy": "Neutral", "score": score,
            "secondary_strategies": [], "sub_scores": {}, "sector": sector, "price": 100}


class _FakeFund:
    def __init__(self, dy): self.dividend_yield = dy


class _FakeGateway:
    def __init__(self, divs): self._divs = divs
    def get_fundamentals(self, sym):
        from decimal import Decimal
        dy = self._divs.get(sym)
        return _FakeFund(Decimal(str(dy)) if dy is not None else None)


def test_macro_selects_inflow_sector_and_dividend(monkeypatch):
    import api.services.smart_money_service as sm
    monkeypatch.setattr(sm, "get_sector_tape",
                        lambda **kw: {"sectors": [{"sector": "Technology", "direction": "inflow"},
                                                  {"sector": "Energy", "direction": "outflow"}]})
    opps = [_card("SYN_T", "Technology", 88),
            _card("SYN_E", "Energy", 80),
            _card("SYN_D", "Energy", 60)]
    gw = _FakeGateway({"SYN_D": 4.0, "SYN_T": 0.0, "SYN_E": 0.0})
    picks = dpa.discover_for_agent("macro", opportunities=opps, gateway=gw)
    syms = {p["symbol"] for p in picks}
    assert "SYN_T" in syms
    assert "SYN_D" in syms
    assert "SYN_E" not in syms


def test_macro_empty_when_no_inflow_no_dividend(monkeypatch):
    import api.services.smart_money_service as sm
    monkeypatch.setattr(sm, "get_sector_tape", lambda **kw: {"sectors": []})
    opps = [_card("SYN_E", "Energy", 70)]
    picks = dpa.discover_for_agent("macro", opportunities=opps, gateway=_FakeGateway({}))
    assert picks == []
