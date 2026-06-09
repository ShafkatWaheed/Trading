"""Tests for the cache_admin service.

Verifies audit shape, namespace-scoped clears, expired-row pruning,
single-key clears, and the nuclear `clear_all`. All operations target
the temp DB via tests/conftest.py — production trading.db is untouched.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from api.services import cache_admin
from src.utils.db import cache_set, get_connection, init_db


def _seed(key: str, value: object = {"x": 1}, ttl_minutes: int = 60) -> None:
    cache_set(key, value, ttl_minutes=ttl_minutes)


def _force_expired(key: str) -> None:
    """Manually backdate a row's expires_at so audit/clear_expired see it."""
    init_db()
    conn = get_connection()
    past = (datetime.utcnow() - timedelta(hours=2)).isoformat()
    conn.execute("UPDATE cache SET expires_at = ? WHERE key = ?", (past, key))
    conn.commit()
    conn.close()


@pytest.fixture(autouse=True)
def _clean_cache():
    init_db()
    conn = get_connection()
    conn.execute("DELETE FROM cache")
    conn.commit()
    conn.close()


# ── audit ────────────────────────────────────────────────────────


def test_audit_returns_zero_when_empty():
    out = cache_admin.audit()
    assert out["total"] == 0
    assert out["by_namespace"] == []
    assert out["expiry_buckets"]["expired"] == 0


def test_audit_groups_by_namespace_prefix():
    _seed("options_flow:v1:AAPL")
    _seed("options_flow:v1:MSFT")
    _seed("news_feed:v1:AAPL")

    out = cache_admin.audit()
    assert out["total"] == 3
    ns = {row["namespace"]: row["rows"] for row in out["by_namespace"]}
    assert ns["options_flow"] == 2
    assert ns["news_feed"] == 1


def test_audit_bucket_counts_expired_separately():
    _seed("foo:bar", ttl_minutes=60)
    _force_expired("foo:bar")

    out = cache_admin.audit()
    assert out["expiry_buckets"]["expired"] == 1


# ── clear_namespace ──────────────────────────────────────────────


def test_clear_namespace_scopes_to_prefix():
    _seed("options_flow:v1:AAPL")
    _seed("options_flow:v1:MSFT")
    _seed("news_feed:v1:AAPL")

    out = cache_admin.clear_namespace("options_flow")
    assert out["deleted"] == 2

    after = cache_admin.audit()
    assert after["total"] == 1


def test_clear_namespace_refuses_too_short_prefix():
    """A single-char prefix would wipe the whole cache — refuse."""
    _seed("a:foo")
    _seed("ab:bar")

    out = cache_admin.clear_namespace("a")
    assert out["deleted"] == 0
    assert out.get("error") == "prefix_too_short"


# ── clear_expired ────────────────────────────────────────────────


def test_clear_expired_deletes_only_stale_rows():
    _seed("fresh:row")
    _seed("stale:row")
    _force_expired("stale:row")

    out = cache_admin.clear_expired()
    assert out["deleted"] == 1

    after = cache_admin.audit()
    assert after["total"] == 1
    assert {r["namespace"] for r in after["by_namespace"]} == {"fresh"}


def test_clear_expired_returns_zero_when_all_fresh():
    _seed("a:b")
    _seed("c:d")
    out = cache_admin.clear_expired()
    assert out["deleted"] == 0


# ── clear_key ────────────────────────────────────────────────────


def test_clear_key_exact_match():
    _seed("foo:bar:baz")
    _seed("foo:bar:other")

    out = cache_admin.clear_key("foo:bar:baz")
    assert out["deleted"] == 1
    assert cache_admin.audit()["total"] == 1


def test_clear_key_unknown_returns_zero():
    out = cache_admin.clear_key("never:seen")
    assert out["deleted"] == 0


# ── clear_all ────────────────────────────────────────────────────


def test_clear_all_nukes_every_row():
    for i in range(5):
        _seed(f"x:y:{i}")

    out = cache_admin.clear_all()
    assert out["deleted"] == 5
    assert cache_admin.audit()["total"] == 0
