"""Tests for the GDELT DOC 2.0 fetcher.

Adapter (gdelt_to_news_item) deferred until the NewsItem model lands.
"""
from __future__ import annotations

import pytest

from src.utils.db import init_db


@pytest.fixture(autouse=True)
def _ensure_schema():
    init_db()
    yield


_SAMPLE_JSON = {
    "articles": [
        {
            "url": "https://reuters.example.com/apple-q4-2026",
            "url_mobile": "",
            "title": "Apple beats Q4 estimates",
            "seendate": "20260114T101500Z",
            "socialimage": "",
            "domain": "reuters.example.com",
            "language": "English",
            "sourcecountry": "United States",
        },
        {
            "url": "https://bloomberg.example.com/iphone-supply",
            "title": "iPhone supply chain ramps",
            "seendate": "20260114T090000Z",
            "domain": "bloomberg.example.com",
            "language": "English",
            "sourcecountry": "United States",
        },
    ]
}


def test_gdelt_fetcher_parses_articles(monkeypatch):
    from src.data import gdelt_doc as mod

    class FakeResp:
        status_code = 200
        def json(self): return _SAMPLE_JSON
        def raise_for_status(self): pass
        @property
        def text(self): return "ok"

    monkeypatch.setattr(mod.httpx, "get", lambda *a, **kw: FakeResp())
    rows = mod.get_gdelt_articles("AAPL")
    assert rows is not None and len(rows) == 2
    assert rows[0]["url"].startswith("https://reuters")
    assert rows[0]["title"] == "Apple beats Q4 estimates"
    assert rows[0]["seendate"] == "20260114T101500Z"


def test_gdelt_fetcher_returns_none_on_failure(monkeypatch):
    from src.data import gdelt_doc as mod
    import httpx as real_httpx

    def boom(*a, **kw):
        raise real_httpx.ConnectError("nope")

    monkeypatch.setattr(mod.httpx, "get", boom)
    # Distinct query string from other tests so we don't hit the cache.
    assert mod.get_gdelt_articles("AAPL_BOOM_TEST") is None


def test_gdelt_fetcher_handles_empty_articles(monkeypatch):
    from src.data import gdelt_doc as mod

    class FakeResp:
        status_code = 200
        def json(self): return {"articles": []}
        def raise_for_status(self): pass
        text = ""

    monkeypatch.setattr(mod.httpx, "get", lambda *a, **kw: FakeResp())
    rows = mod.get_gdelt_articles("XYZNOMATCH")
    assert rows == []
