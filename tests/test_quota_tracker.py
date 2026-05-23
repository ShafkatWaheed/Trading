"""Tests for the source-quota cooldown tracker."""
from __future__ import annotations

import pytest

from src.data.quota_tracker import (
    clear_exhausted,
    is_exhausted,
    mark_exhausted,
)
from src.utils.db import init_db


@pytest.fixture(autouse=True)
def _fresh_quota_state():
    init_db()
    for src in ("tavily", "exa", "test_src"):
        clear_exhausted(src)
    yield
    for src in ("tavily", "exa", "test_src"):
        clear_exhausted(src)


def test_source_starts_not_exhausted():
    assert is_exhausted("test_src") is False


def test_mark_then_is_exhausted_true():
    mark_exhausted("test_src", cooldown_minutes=240)
    assert is_exhausted("test_src") is True


def test_clear_resets_state():
    mark_exhausted("test_src", cooldown_minutes=240)
    clear_exhausted("test_src")
    assert is_exhausted("test_src") is False


def test_cooldown_expires_after_ttl(monkeypatch):
    from datetime import datetime, timedelta
    import src.data.quota_tracker as qt

    real_now = datetime.utcnow()
    mark_exhausted("test_src", cooldown_minutes=1)

    # Fast-forward 2 minutes: cooldown should have expired.
    future = real_now + timedelta(minutes=2)
    monkeypatch.setattr(qt, "_utcnow", lambda: future)
    assert is_exhausted("test_src") is False


def test_different_sources_isolated():
    mark_exhausted("tavily", cooldown_minutes=240)
    assert is_exhausted("tavily") is True
    assert is_exhausted("exa") is False


def test_tavily_429_marks_exhausted(monkeypatch):
    """When httpx returns 429, NewsProvider must mark Tavily exhausted."""
    from src.data import news as news_mod

    class FakeResp:
        status_code = 429
        text = "rate limited"
        def json(self): return {}
        def raise_for_status(self): pass

    monkeypatch.setattr(news_mod, "TAVILY_API_KEY", "fake-key")
    monkeypatch.setattr(news_mod.httpx, "post", lambda *a, **kw: FakeResp())

    out = news_mod.NewsProvider()._tavily_search("AAPL", max_results=3)
    assert out == []
    assert is_exhausted("tavily") is True


def test_exa_402_marks_exhausted(monkeypatch):
    from src.data import news as news_mod

    class FakeResp:
        status_code = 402
        text = "quota exceeded"
        def json(self): return {}
        def raise_for_status(self): pass

    monkeypatch.setattr(news_mod, "EXA_API_KEY", "fake-key")
    monkeypatch.setattr(news_mod.httpx, "post", lambda *a, **kw: FakeResp())

    out = news_mod.NewsProvider()._exa_search("AAPL", num_results=3)
    assert out == []
    assert is_exhausted("exa") is True


def test_tavily_500_does_not_mark_exhausted(monkeypatch):
    """A non-quota error (500 / connection error) must NOT trigger cooldown."""
    from src.data import news as news_mod

    class FakeResp:
        status_code = 500
        text = "server error"
        def json(self): return {}
        def raise_for_status(self): pass

    monkeypatch.setattr(news_mod, "TAVILY_API_KEY", "fake-key")
    monkeypatch.setattr(news_mod.httpx, "post", lambda *a, **kw: FakeResp())
    clear_exhausted("tavily")

    news_mod.NewsProvider()._tavily_search("AAPL", max_results=3)
    assert is_exhausted("tavily") is False
