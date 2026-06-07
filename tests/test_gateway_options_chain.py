"""DataGateway.get_options_chain delegates to the polygon provider and
returns [] on any error (no fabrication)."""
from __future__ import annotations

from decimal import Decimal

from src.data.gateway import DataGateway
from src.models.data_types import OptionsChain


class _FakePolygon:
    def __init__(self, result=None, boom=False):
        self._result = result or []
        self._boom = boom

    def get_options_chain(self, symbol):
        if self._boom:
            raise RuntimeError("polygon 429 rate limit")
        return self._result


def test_get_options_chain_delegates(monkeypatch):
    gw = DataGateway()
    chain = OptionsChain(underlying="SYN", underlying_price=Decimal("100"),
                         expiration="2026-06-20")
    monkeypatch.setattr(gw, "_get_polygon", lambda: _FakePolygon([chain]))
    out = gw.get_options_chain("SYN")
    assert out == [chain]


def test_get_options_chain_returns_empty_on_error(monkeypatch):
    gw = DataGateway()
    monkeypatch.setattr(gw, "_get_polygon", lambda: _FakePolygon(boom=True))
    assert gw.get_options_chain("SYN") == []
