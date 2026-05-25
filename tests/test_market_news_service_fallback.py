"""Verify the Tavily → Exa → GDELT → Google News fallback chain in
api/services/market_news_service.

These tests monkeypatch every external dep — no network, no real
NewsProvider construction, no real quota state.
"""
from __future__ import annotations

import pytest

from api.services import market_news_service as svc


@pytest.fixture(autouse=True)
def _invalidate_cache(monkeypatch):
    """Make every test start with a clean slate so cached payloads from
    earlier tests don't leak in."""
    monkeypatch.setattr(svc, "cache_get", lambda *a, **k: None)
    # Swallow cache_set so tests don't pollute the (temp) cache table.
    monkeypatch.setattr(svc, "cache_set", lambda *a, **k: None)


def _stub_news_provider_empty():
    """A fake NewsProvider whose search_news and search_research always return []."""

    class _Stub:
        def search_news(self, q, max_results=4):  # noqa: ARG002
            return []

        def search_research(self, q):  # noqa: ARG002
            return []

    return _Stub()


# ── Tavily+Exa empty → GDELT supplies rows ────────────────────────────

def test_falls_back_to_gdelt_when_tavily_and_exa_empty(monkeypatch):
    monkeypatch.setattr(svc, "NewsProvider", _stub_news_provider_empty)
    monkeypatch.setattr(svc, "is_exhausted", lambda p: False)
    monkeypatch.setattr(
        svc,
        "get_gdelt_articles",
        lambda q, **k: [
            {
                "title": f"GDELT story for {q}",
                "url": f"http://example.com/{abs(hash(q))}",
                "domain": "example.com",
                "seendate": "20260525T120000Z",
            }
        ],
    )
    # Google News must not be called — but stub it anyway so a regression doesn't fail noisily.
    monkeypatch.setattr(svc, "get_google_news", lambda q, **k: None)

    payload = svc.get_market_news(force=True)

    assert payload["provider"] == "gdelt"
    assert payload["source_warning"] == "Tavily + Exa exhausted — using GDELT (free)."
    assert len(payload["items"]) >= 1
    assert all(i["url"].startswith("http://example.com/") for i in payload["items"])


# ── Tavily exhausted by quota, GDELT supplies rows ────────────────────

def test_skips_tavily_exa_when_exhausted(monkeypatch):
    """Even with a working NewsProvider, is_exhausted=True must skip both
    paid sources and fall through to GDELT."""
    called = {"tavily": 0, "exa": 0}

    class _Spy:
        def search_news(self, q, max_results=4):  # noqa: ARG002
            called["tavily"] += 1
            return [{"title": "should not be called", "url": "x", "content_snippet": "x"}]

        def search_research(self, q):  # noqa: ARG002
            called["exa"] += 1
            return [{"title": "should not be called", "url": "y", "content_snippet": "y"}]

    monkeypatch.setattr(svc, "NewsProvider", _Spy)
    monkeypatch.setattr(svc, "is_exhausted", lambda p: True)
    monkeypatch.setattr(
        svc,
        "get_gdelt_articles",
        lambda q, **k: [{"title": "GDELT", "url": f"http://g/{q}", "domain": "g.com", "seendate": ""}],
    )
    monkeypatch.setattr(svc, "get_google_news", lambda q, **k: None)

    payload = svc.get_market_news(force=True)

    assert called["tavily"] == 0, "Tavily must be skipped when is_exhausted"
    assert called["exa"] == 0, "Exa must be skipped when is_exhausted"
    assert payload["provider"] == "gdelt"


# ── GDELT also empty → Google News RSS is last resort ─────────────────

def test_falls_through_to_google_news_when_gdelt_empty(monkeypatch):
    monkeypatch.setattr(svc, "NewsProvider", _stub_news_provider_empty)
    monkeypatch.setattr(svc, "is_exhausted", lambda p: False)
    monkeypatch.setattr(svc, "get_gdelt_articles", lambda q, **k: [])  # no hits
    monkeypatch.setattr(
        svc,
        "get_google_news",
        lambda q, **k: [
            {
                "title": f"Google story {q[:10]}",
                "url": f"http://news.example/{abs(hash(q))}",
                "pub_date": "Mon, 25 May 2026 12:00:00 GMT",
                "source": "Example News",
                "description": "Snippet body text.",
            }
        ],
    )

    payload = svc.get_market_news(force=True)

    assert payload["provider"] == "google_news"
    assert payload["source_warning"] == "Upstream news providers exhausted — using Google News RSS (free)."
    assert len(payload["items"]) >= 1
    assert payload["items"][0]["source"] == "Example News"
    assert payload["items"][0]["snippet"] == "Snippet body text."


# ── Everything dark → provider=None, warning explains why ────────────

def test_all_providers_empty_sets_provider_none(monkeypatch):
    monkeypatch.setattr(svc, "NewsProvider", _stub_news_provider_empty)
    monkeypatch.setattr(svc, "is_exhausted", lambda p: False)
    monkeypatch.setattr(svc, "get_gdelt_articles", lambda q, **k: None)
    monkeypatch.setattr(svc, "get_google_news", lambda q, **k: None)

    payload = svc.get_market_news(force=True)

    assert payload["provider"] is None
    assert payload["source_warning"] == "All news providers returned no results."
    assert payload["items"] == []
    assert payload["net_sentiment"] == "no coverage"


# ── Cache key bump from v1 → v2 invalidates stale "no coverage" payload ──

def test_cache_key_is_v2(monkeypatch):
    """Schema bump must use a new cache key so old empty payloads from the
    Tavily-only code path aren't returned forever."""
    seen_keys: list[str] = []

    def fake_cache_get(key):
        seen_keys.append(key)
        return None

    monkeypatch.setattr(svc, "cache_get", fake_cache_get)
    monkeypatch.setattr(svc, "cache_set", lambda *a, **k: None)
    monkeypatch.setattr(svc, "NewsProvider", _stub_news_provider_empty)
    monkeypatch.setattr(svc, "is_exhausted", lambda p: False)
    monkeypatch.setattr(svc, "get_gdelt_articles", lambda q, **k: None)
    monkeypatch.setattr(svc, "get_google_news", lambda q, **k: None)

    svc.get_market_news(force=False)

    assert "market_news:v2" in seen_keys
    assert "market_news:v1" not in seen_keys
