"""A smart_money summary with a failed section is cached only briefly, so a
transient upstream failure (e.g. SEC 500) self-heals on the next view instead
of sticking for the full 6h TTL. No network — sections + cache are stubbed."""
from __future__ import annotations

import api.services.smart_money_service as sm


def _patch(monkeypatch, *, insider_error: bool) -> dict:
    captured: dict = {}
    monkeypatch.setattr(sm, "cache_get", lambda k: None)            # force miss
    monkeypatch.setattr(sm, "cache_set",
                        lambda k, v, ttl_minutes=None: captured.__setitem__("ttl", ttl_minutes))
    monkeypatch.setattr(sm, "_institutional_section", lambda s: {"error": None})
    monkeypatch.setattr(sm, "_insider_section",
                        lambda s: {"error": "Insider fetch failed: 500" if insider_error else None})
    monkeypatch.setattr(sm, "_congress_section", lambda s: {"error": None})
    monkeypatch.setattr(sm, "_summary_signal", lambda a, b, c: "neutral")
    return captured


def test_errored_section_uses_short_ttl(monkeypatch):
    cap = _patch(monkeypatch, insider_error=True)
    sm.get_smart_money("PEP", force=True)
    assert cap["ttl"] == sm._ERROR_CACHE_TTL_MINUTES
    assert sm._ERROR_CACHE_TTL_MINUTES < sm._CACHE_TTL_MINUTES


def test_clean_section_uses_full_ttl(monkeypatch):
    cap = _patch(monkeypatch, insider_error=False)
    sm.get_smart_money("PEP", force=True)
    assert cap["ttl"] == sm._CACHE_TTL_MINUTES
