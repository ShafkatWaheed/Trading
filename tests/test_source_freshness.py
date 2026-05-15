"""Tests for per-source freshness registration (Wave 1)."""
from __future__ import annotations

import pytest

from src.data.source_freshness import (
    SourceFreshness,
    get_all_sources,
    get_source,
    record_fetch,
    register_source,
)
from src.utils.db import get_connection, init_db


@pytest.fixture(autouse=True)
def _clean():
    init_db()
    conn = get_connection()
    conn.execute("DELETE FROM source_freshness WHERE source LIKE 'test_%'")
    conn.commit()
    conn.close()
    yield
    conn = get_connection()
    conn.execute("DELETE FROM source_freshness WHERE source LIKE 'test_%'")
    conn.commit()
    conn.close()


def test_register_source_inserts_row():
    register_source(
        source="test_uspto", cadence="weekly", ttl_seconds=7 * 86400,
        rate_limit_budget=None,
    )
    s = get_source("test_uspto")
    assert s is not None
    assert s.cadence == "weekly"
    assert s.ttl_seconds == 7 * 86400


def test_register_source_is_idempotent():
    register_source(source="test_a", cadence="daily", ttl_seconds=86400, rate_limit_budget=240)
    register_source(source="test_a", cadence="daily", ttl_seconds=86400, rate_limit_budget=240)
    # Single row, no duplicate-key error
    assert get_source("test_a") is not None


def test_record_fetch_updates_freshness():
    register_source(source="test_b", cadence="daily", ttl_seconds=86400, rate_limit_budget=240)
    record_fetch(
        source="test_b", status="ok", payload_count=12,
        rate_limit_remaining=239, error=None,
    )
    s = get_source("test_b")
    assert s.last_status == "ok"
    assert s.last_payload_count == 12
    assert s.rate_limit_remaining == 239
    assert s.last_fetched_at is not None
    assert s.next_due_at is not None
    assert s.next_due_at > s.last_fetched_at


def test_record_fetch_empty_payload_shortens_ttl(monkeypatch):
    """Per spec §6.2 empty-payload pitfall: 0 records → next_due_at within 1h."""
    register_source(source="test_c", cadence="weekly", ttl_seconds=7 * 86400, rate_limit_budget=None)
    record_fetch(source="test_c", status="empty", payload_count=0, rate_limit_remaining=None, error=None)
    s = get_source("test_c")
    # last_fetched_at + 3600s ≤ next_due_at ≤ last_fetched_at + 3700s (1h window with small slack)
    from datetime import datetime
    last = datetime.fromisoformat(s.last_fetched_at.replace("Z", "+00:00"))
    nxt = datetime.fromisoformat(s.next_due_at.replace("Z", "+00:00"))
    delta_s = (nxt - last).total_seconds()
    assert 3500 <= delta_s <= 3700


def test_get_all_sources_returns_registered_sources():
    register_source(source="test_x", cadence="daily", ttl_seconds=86400, rate_limit_budget=None)
    register_source(source="test_y", cadence="weekly", ttl_seconds=7 * 86400, rate_limit_budget=None)
    sources = {s.source for s in get_all_sources()}
    assert "test_x" in sources
    assert "test_y" in sources
