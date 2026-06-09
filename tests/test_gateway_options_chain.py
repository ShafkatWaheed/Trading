"""DataGateway.get_options_chain: Polygon first, yfinance fallback, [] if both fail."""
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
    """Polygon result is returned directly when non-empty."""
    gw = DataGateway()
    chain = OptionsChain(underlying="SYN", underlying_price=Decimal("100"),
                         expiration="2026-06-20")
    monkeypatch.setattr(gw, "_get_polygon", lambda: _FakePolygon([chain]))
    out = gw.get_options_chain("SYN")
    assert out == [chain]


def test_get_options_chain_returns_empty_on_error(monkeypatch):
    """When Polygon raises AND yfinance also fails, gateway returns []."""
    gw = DataGateway()
    monkeypatch.setattr(gw, "_get_polygon", lambda: _FakePolygon(boom=True))
    import src.data.yf_options as yfo
    monkeypatch.setattr(yfo, "get_options_chain",
                        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("yf down")))
    assert gw.get_options_chain("SYN") == []


# ── yfinance fallback tests ──────────────────────────────────────────

_SENTINEL = [OptionsChain(underlying="SYN_YF", underlying_price=Decimal("50"),
                           expiration="2026-07-18")]


def test_yfinance_fallback_when_polygon_empty(monkeypatch):
    """When Polygon returns [] the gateway falls back to yfinance."""
    gw = DataGateway()
    monkeypatch.setattr(gw, "_get_polygon", lambda: _FakePolygon(result=[]))
    import src.data.yf_options as yfo
    monkeypatch.setattr(yfo, "get_options_chain", lambda *a, **kw: _SENTINEL)
    out = gw.get_options_chain("SYN_YF")
    assert out == _SENTINEL


def test_yfinance_fallback_when_polygon_raises(monkeypatch):
    """When Polygon raises (403 / rate-limit) the gateway falls back to yfinance."""
    gw = DataGateway()
    monkeypatch.setattr(gw, "_get_polygon", lambda: _FakePolygon(boom=True))
    import src.data.yf_options as yfo
    monkeypatch.setattr(yfo, "get_options_chain", lambda *a, **kw: _SENTINEL)
    out = gw.get_options_chain("SYN_YF")
    assert out == _SENTINEL


def test_polygon_result_preferred_over_yfinance(monkeypatch):
    """When Polygon returns data, yfinance is never called."""
    gw = DataGateway()
    poly_chain = OptionsChain(underlying="SYN_POLY", underlying_price=Decimal("200"),
                               expiration="2026-06-20")
    monkeypatch.setattr(gw, "_get_polygon", lambda: _FakePolygon([poly_chain]))
    import src.data.yf_options as yfo

    def _should_not_be_called(*a, **kw):
        raise AssertionError("yfinance should not be called when Polygon succeeds")

    monkeypatch.setattr(yfo, "get_options_chain", _should_not_be_called)
    out = gw.get_options_chain("SYN_POLY")
    assert out == [poly_chain]
