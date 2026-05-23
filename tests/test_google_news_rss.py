"""Tests for the Google News RSS fetcher.

Note: the NewsItem adapter (google_to_news_item) tests live in
test_news_adapters.py once Task 2 lands. This file covers the fetcher
only, which is what events_service.py depends on for the geopolitical
fallback chain.
"""
from __future__ import annotations

import pytest

from src.utils.db import init_db


@pytest.fixture(autouse=True)
def _ensure_schema():
    init_db()
    yield


_SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/">
<channel>
<item>
  <title>Apple beats Q4 estimates - Reuters</title>
  <link>https://news.google.com/articles/redirect-url-apple-q4</link>
  <pubDate>Tue, 14 Jan 2026 10:15:00 GMT</pubDate>
  <source url="https://reuters.com">Reuters</source>
  <description>Apple reported strong iPhone sales</description>
</item>
<item>
  <title>iPhone supply chain ramps - Bloomberg</title>
  <link>https://news.google.com/articles/redirect-supply</link>
  <pubDate>Tue, 14 Jan 2026 09:00:00 GMT</pubDate>
  <source url="https://bloomberg.com">Bloomberg</source>
  <description>Suppliers note demand</description>
</item>
</channel>
</rss>"""


def test_google_fetcher_parses_items(monkeypatch):
    from src.data import google_news_rss as mod

    class FakeResp:
        text = _SAMPLE_RSS
        status_code = 200
        def raise_for_status(self): pass

    monkeypatch.setattr(mod.httpx, "get", lambda *a, **kw: FakeResp())
    rows = mod.get_google_news("AAPL stock")
    assert rows is not None and len(rows) == 2
    assert rows[0]["title"].startswith("Apple beats")
    assert rows[0]["source"] == "Reuters"
    assert "GMT" in rows[0]["pub_date"]


def test_google_fetcher_returns_none_on_failure(monkeypatch):
    from src.data import google_news_rss as mod
    import httpx as real_httpx

    def boom(*a, **kw):
        raise real_httpx.ConnectError("nope")

    monkeypatch.setattr(mod.httpx, "get", boom)
    assert mod.get_google_news("AAPL") is None
