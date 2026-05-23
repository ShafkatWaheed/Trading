"""Tests for the geopolitical fallback chain in events_service."""
from __future__ import annotations

import pytest

from src.data.quota_tracker import clear_exhausted, mark_exhausted
from src.utils.db import cache_delete, init_db


@pytest.fixture(autouse=True)
def _fresh_state():
    init_db()
    cache_delete("geo_events_v1")
    clear_exhausted("tavily")
    clear_exhausted("exa")
    yield
    cache_delete("geo_events_v1")
    clear_exhausted("tavily")
    clear_exhausted("exa")


def _stub_all(monkeypatch, *, tavily=([], False), exa=([], False),
              gdelt=None, google=None):
    """Patch all four upstreams. gdelt/google are raw row lists (or None)."""
    from api.services import events_service as svc

    monkeypatch.setattr(svc, "_search_tavily", lambda q: tavily)
    monkeypatch.setattr(svc, "_search_exa", lambda q: exa)
    monkeypatch.setattr(svc, "get_gdelt_articles", lambda q, limit=5: gdelt)
    monkeypatch.setattr(svc, "get_google_news", lambda q, limit=5: google)


def test_uses_tavily_when_available(monkeypatch):
    from api.services import events_service as svc

    tavily_rows = [{"title": "Tariff news", "content": "details about tariff", "url": "https://x"}]
    _stub_all(monkeypatch, tavily=(tavily_rows, True))

    out = svc.get_geopolitical_events()
    assert out["data_available"] is True
    assert len(out["events"]) >= 1
    assert out["events"][0]["title"] == "Tariff news"


def test_falls_back_to_exa_when_tavily_fails(monkeypatch):
    from api.services import events_service as svc

    exa_rows = [{"title": "Exa news", "content": "details", "url": "https://y"}]
    _stub_all(monkeypatch, tavily=([], False), exa=(exa_rows, True))

    out = svc.get_geopolitical_events()
    assert out["data_available"] is True
    assert out["events"][0]["title"] == "Exa news"


def test_falls_back_to_gdelt_when_tavily_exa_fail(monkeypatch):
    from api.services import events_service as svc

    gdelt_rows = [{"title": "GDELT headline", "url": "https://g/1",
                   "seendate": "20260523T120000Z", "domain": "reuters.com"}]
    _stub_all(monkeypatch, tavily=([], False), exa=([], False),
              gdelt=gdelt_rows)

    out = svc.get_geopolitical_events()
    assert out["data_available"] is True
    assert out["events"][0]["title"] == "GDELT headline"
    assert out["events"][0]["url"] == "https://g/1"


def test_falls_back_to_google_when_gdelt_fails(monkeypatch):
    from api.services import events_service as svc

    google_rows = [{"title": "Google headline", "url": "https://goog/1",
                    "pub_date": "Sat, 23 May 2026 12:00:00 GMT",
                    "source": "Bloomberg", "description": "Google snippet"}]
    _stub_all(monkeypatch, tavily=([], False), exa=([], False),
              gdelt=None, google=google_rows)

    out = svc.get_geopolitical_events()
    assert out["data_available"] is True
    assert out["events"][0]["title"] == "Google headline"
    assert out["events"][0]["snippet"] == "Google snippet"


def test_all_fail_sets_data_unavailable_short_ttl(monkeypatch):
    from api.services import events_service as svc
    from src.utils.db import get_connection
    from datetime import datetime

    _stub_all(monkeypatch, gdelt=None, google=None)

    out = svc.get_geopolitical_events()
    assert out["events"] == []
    assert out["data_available"] is False

    # Confirm short TTL — cache entry must expire in <= 6 min.
    # Uses get_connection() so the test honors the temp-DB fixture in conftest.py.
    conn = get_connection()
    row = conn.execute(
        "SELECT expires_at FROM cache WHERE key=?", ("geo_events_v1",)
    ).fetchone()
    conn.close()
    assert row is not None
    expires = datetime.fromisoformat(row["expires_at"])
    delta_min = (expires - datetime.utcnow()).total_seconds() / 60
    assert delta_min <= 6, f"expected short TTL on failure, got {delta_min} min"


def test_tavily_skipped_when_on_cooldown(monkeypatch):
    """If Tavily is marked exhausted, _search_tavily must NOT be invoked."""
    from api.services import events_service as svc

    call_log = []
    def spy_tavily(q):
        call_log.append(q)
        return [{"title": "should not appear", "content": "", "url": ""}], True

    gdelt_rows = [{"title": "GDELT win", "url": "https://g",
                   "seendate": "20260523T120000Z", "domain": "x"}]
    monkeypatch.setattr(svc, "_search_tavily", spy_tavily)
    monkeypatch.setattr(svc, "_search_exa", lambda q: ([], False))
    monkeypatch.setattr(svc, "get_gdelt_articles", lambda q, limit=5: gdelt_rows)
    monkeypatch.setattr(svc, "get_google_news", lambda q, limit=5: None)

    mark_exhausted("tavily")
    out = svc.get_geopolitical_events()

    assert call_log == [], "Tavily should be skipped while on cooldown"
    assert out["data_available"] is True
    assert out["events"][0]["title"] == "GDELT win"


def test_tavily_429_marks_exhausted(monkeypatch):
    """A 429 response from Tavily inside events_service must trigger cooldown."""
    from api.services import events_service as svc
    from src.data.quota_tracker import is_exhausted

    class FakeResp:
        status_code = 429
        text = "rate limited"
        def json(self): return {}

    monkeypatch.setenv("TAVILY_API_KEY", "fake-key")
    monkeypatch.setattr(svc.httpx, "post", lambda *a, **kw: FakeResp())
    clear_exhausted("tavily")

    rows, ok = svc._search_tavily("anything")
    assert rows == [] and ok is False
    assert is_exhausted("tavily") is True


def test_tavily_432_marks_exhausted(monkeypatch):
    """Tavily's custom HTTP 432 (plan usage exceeded) must trigger cooldown."""
    from api.services import events_service as svc
    from src.data.quota_tracker import is_exhausted

    class FakeResp:
        status_code = 432
        text = '{"detail":{"error":"plan usage exceeded"}}'
        def json(self): return {}

    monkeypatch.setenv("TAVILY_API_KEY", "fake-key")
    monkeypatch.setattr(svc.httpx, "post", lambda *a, **kw: FakeResp())
    clear_exhausted("tavily")

    rows, ok = svc._search_tavily("anything")
    assert rows == [] and ok is False
    assert is_exhausted("tavily") is True
