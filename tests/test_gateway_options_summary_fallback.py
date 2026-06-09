"""gateway.get_options_summary falls back to yfinance when Polygon is
unconfigured/empty (so the daily-picks Options agent works without a paid key)."""
from __future__ import annotations

from src.data.gateway import DataGateway


class _FakePolygon:
    def __init__(self, *, result=None, boom=False):
        self._result, self._boom = result, boom
    def get_options_summary(self, symbol):
        if self._boom:
            raise RuntimeError("403 Forbidden (options is paid)")
        return self._result


_SENTINEL = object()


def test_falls_back_to_yfinance_when_polygon_none(monkeypatch):
    gw = DataGateway()
    monkeypatch.setattr(gw, "_get_polygon", lambda: _FakePolygon(result=None))
    import src.data.yf_options as yfo
    monkeypatch.setattr(yfo, "get_options_summary", lambda s: _SENTINEL)
    assert gw.get_options_summary("AVGO") is _SENTINEL


def test_falls_back_to_yfinance_when_polygon_raises(monkeypatch):
    gw = DataGateway()
    monkeypatch.setattr(gw, "_get_polygon", lambda: _FakePolygon(boom=True))
    import src.data.yf_options as yfo
    monkeypatch.setattr(yfo, "get_options_summary", lambda s: _SENTINEL)
    assert gw.get_options_summary("AVGO") is _SENTINEL


def test_polygon_preferred_when_available(monkeypatch):
    gw = DataGateway()
    poly = object()
    monkeypatch.setattr(gw, "_get_polygon", lambda: _FakePolygon(result=poly))
    import src.data.yf_options as yfo
    monkeypatch.setattr(yfo, "get_options_summary", lambda s: _SENTINEL)
    assert gw.get_options_summary("AVGO") is poly


def test_none_when_both_fail(monkeypatch):
    gw = DataGateway()
    monkeypatch.setattr(gw, "_get_polygon", lambda: _FakePolygon(boom=True))
    import src.data.yf_options as yfo
    def boom(s): raise RuntimeError("no options")
    monkeypatch.setattr(yfo, "get_options_summary", boom)
    assert gw.get_options_summary("AVGO") is None
