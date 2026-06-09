"""Insider agent selects opportunities with insider buying (cached SEC summary)."""
from __future__ import annotations

import api.services.daily_picks_agents as dpa


def _card(sym, score=70):
    return {"symbol": sym, "strategy": "Neutral", "score": score,
            "secondary_strategies": [], "sub_scores": {}, "sector": "Tech", "price": 100}


class _Sum:
    def __init__(self, *, cluster=False, signal="neutral", buys=0, net=0):
        self.cluster_buy = cluster; self.signal = signal
        self.total_buys = buys; self.net_shares = net


class _FakeGateway:
    def __init__(self, m, boom=()):
        self._m = m; self._boom = set(boom)
    def get_insider_summary(self, sym, days=90):
        if sym in self._boom:
            raise RuntimeError("SEC 500")
        return self._m.get(sym)


def test_insider_selects_buying_signals():
    opps = [_card("SYN_C", 90), _card("SYN_S", 85), _card("SYN_N", 80)]
    gw = _FakeGateway({
        "SYN_C": _Sum(cluster=True),
        "SYN_S": _Sum(signal="strong buy"),
        "SYN_N": _Sum(signal="neutral", buys=0),
    })
    picks = dpa.discover_for_agent("insider", opportunities=opps, gateway=gw)
    syms = {p["symbol"] for p in picks}
    assert syms == {"SYN_C", "SYN_S"}
    assert all("evidence" in p for p in picks)


def test_insider_skips_symbol_on_error():
    opps = [_card("SYN_X", 90), _card("SYN_Y", 80)]
    gw = _FakeGateway({"SYN_Y": _Sum(cluster=True)}, boom=["SYN_X"])
    picks = dpa.discover_for_agent("insider", opportunities=opps, gateway=gw)
    assert [p["symbol"] for p in picks] == ["SYN_Y"]
