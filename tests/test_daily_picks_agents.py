"""daily_picks_agents.discover_for_agent — deterministic, injected gateway."""
from __future__ import annotations

import pytest

from api.services import daily_picks_agents as dpa
from src.utils.db import get_connection, init_db


def _card(symbol, strategy, score, sub_flow=0, secondary=None, sector="Tech"):
    secs = [{"name": s, "icon": "", "description": ""} for s in (secondary or [])]
    return {"symbol": symbol, "strategy": strategy, "score": score,
            "secondary_strategies": secs,
            "sub_scores": {"volume": 0, "price": 0, "flow": sub_flow, "risk_reward": 0},
            "sector": sector, "price": 100}


_OPPS = [
    _card("SYN_MOM", "Momentum", 88),
    _card("SYN_BRK", "Breakout", 75),
    _card("SYN_OVS", "Oversold Bounce", 62),
    _card("SYN_MR", "Mean Reversion", 55),
    _card("SYN_INS", "Insider Accumulation", 80),
    _card("SYN_CON", "Congress Buying", 71, sub_flow=90),
    _card("SYN_SEC", "Sector Leader", 66),
    _card("SYN_NEU", "Neutral", 40),
]


class _FakeGateway:
    """Returns canned fundamentals/options for value/options lenses."""
    def __init__(self, *, cheap={"SYN_MOM"}, bullish={"SYN_BRK"}):
        self._cheap, self._bullish = cheap, bullish

    def get_fundamentals(self, symbol):
        class F: pass
        f = F()
        f.pe_ratio = 12.0 if symbol in self._cheap else 90.0
        f.profit_margin = 0.2 if symbol in self._cheap else 0.2
        return f

    def get_options_summary(self, symbol):
        if symbol not in self._bullish:
            return None
        class O: pass
        o = O()
        o.put_call_ratio = 0.5
        return o


def test_momentum_selects_momentum_family():
    picks = dpa.discover_for_agent("momentum", opportunities=_OPPS, gateway=_FakeGateway())
    syms = {p["symbol"] for p in picks}
    assert "SYN_MOM" in syms and "SYN_BRK" in syms
    assert "SYN_OVS" not in syms
    assert all("evidence" in p and "conviction" in p for p in picks)
    assert picks[0]["symbol"] == "SYN_MOM"


def test_contrarian_selects_mean_reversion_family():
    picks = dpa.discover_for_agent("contrarian", opportunities=_OPPS, gateway=_FakeGateway())
    syms = {p["symbol"] for p in picks}
    assert syms == {"SYN_OVS", "SYN_MR"}


def test_insider_selects_insider_accumulation():
    picks = dpa.discover_for_agent("insider", opportunities=_OPPS, gateway=_FakeGateway())
    assert [p["symbol"] for p in picks] == ["SYN_INS"]


def test_value_uses_gateway_fundamentals():
    picks = dpa.discover_for_agent("value", opportunities=_OPPS,
                                   gateway=_FakeGateway(cheap={"SYN_MOM", "SYN_SEC"}))
    syms = {p["symbol"] for p in picks}
    assert syms <= {"SYN_MOM", "SYN_SEC"}
    assert "SYN_BRK" not in syms


def test_options_uses_gateway_bullish_flow():
    # bullish symbol must be within the top _OPTIONS_SHORTLIST(5) by score;
    # SYN_MOM (88) is rank 1, so it's in the options shortlist.
    picks = dpa.discover_for_agent("options", opportunities=_OPPS,
                                   gateway=_FakeGateway(bullish={"SYN_MOM"}))
    assert [p["symbol"] for p in picks] == ["SYN_MOM"]


def test_unknown_agent_returns_empty():
    assert dpa.discover_for_agent("nope", opportunities=_OPPS, gateway=_FakeGateway()) == []


def test_gateway_error_in_value_yields_empty_not_crash():
    class Boom(_FakeGateway):
        def get_fundamentals(self, symbol):
            raise RuntimeError("rate limited")
    picks = dpa.discover_for_agent("value", opportunities=_OPPS, gateway=Boom())
    assert picks == []


def test_momentum_matches_via_secondary_strategy():
    # primary strategy is Neutral, but a SECONDARY strategy (dict-shaped) is Momentum
    opps = [_card("SYN_SEC2", "Neutral", 77, secondary=["Momentum"])]
    picks = dpa.discover_for_agent("momentum", opportunities=opps, gateway=_FakeGateway())
    assert [p["symbol"] for p in picks] == ["SYN_SEC2"]


def test_macro_selects_inflow_sector(monkeypatch):
    # macro now keys off the sector tape (inflow), not a "Sector Leader" tag.
    import api.services.smart_money_service as sm
    monkeypatch.setattr(sm, "get_sector_tape",
                        lambda **kw: {"sectors": [{"sector": "Tech", "direction": "inflow"}]})
    # _OPPS cards are all sector="Tech"; the highest-score one should surface.
    picks = dpa.discover_for_agent("macro", opportunities=_OPPS, gateway=_FakeGateway())
    assert picks and picks[0]["symbol"] == "SYN_MOM"   # Tech inflow, top score 88


def test_flow_selects_congress_buying():
    # Flow agent now queries the DB for real congressional buys; seed SYN_CON with 2 buys.
    init_db()
    c = get_connection()
    c.execute("DELETE FROM congress_trades WHERE source='test_agents'")
    c.execute("DELETE FROM institution_holdings WHERE source='test_agents'")
    for i in range(2):
        c.execute(
            "INSERT INTO congress_trades (filing_uuid, txn_index, chamber, politician_name, "
            "party, ticker, transaction_type, transaction_date, fetched_at, source) "
            "VALUES (?,?,?,?,?,?,?,date('now','-10 day'),datetime('now'),'test_agents')",
            (f"ta{i}", i, "House", "Rep X", "R", "SYN_CON", "buy"),
        )
    c.commit()
    c.close()
    picks = dpa.discover_for_agent("flow", opportunities=_OPPS, gateway=_FakeGateway())
    assert [p["symbol"] for p in picks] == ["SYN_CON"]


def test_value_gateway_calls_bounded_to_shortlist():
    # 20 candidates, but value must only query fundamentals for the top 15 by score.
    opps = [_card(f"SYN_{i:02d}", "Momentum", float(i)) for i in range(20)]
    queried = []

    class CountingGateway(_FakeGateway):
        def get_fundamentals(self, symbol):
            queried.append(symbol)
            return super().get_fundamentals(symbol)

    dpa.discover_for_agent("value", opportunities=opps, gateway=CountingGateway())
    assert len(queried) == 15  # _SHORTLIST bound, not all 20
    # the lowest-score names (00..04) must not be queried
    assert "SYN_00" not in queried and "SYN_04" not in queried
