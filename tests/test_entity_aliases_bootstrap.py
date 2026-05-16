"""Tests for lazy alias bootstrap (Wave 2 fix)."""
from __future__ import annotations

import pytest

from src.data import entity_aliases
from src.data.entity_aliases import ensure_alias_for_ticker, resolve_ticker
from src.utils.db import get_connection, init_db


@pytest.fixture(autouse=True)
def _clean():
    init_db()
    conn = get_connection()
    # Scope cleanup to bootstrap rows so we don't wipe manual overrides
    conn.execute("DELETE FROM entity_aliases WHERE alias_source = 'sec_lazy_bootstrap'")
    conn.commit()
    conn.close()
    # Also reset the in-memory cache between tests
    entity_aliases._SEC_MAPPING_CACHE = None
    yield
    entity_aliases._SEC_MAPPING_CACHE = None
    conn = get_connection()
    conn.execute("DELETE FROM entity_aliases WHERE alias_source = 'sec_lazy_bootstrap'")
    conn.commit()
    conn.close()


def test_ensure_alias_no_op_when_alias_already_exists():
    """If ticker already has any alias, bootstrap is a no-op."""
    from datetime import datetime, timezone
    from src.data.entity_aliases import insert_alias

    insert_alias(
        ticker="EXIST", cik=None, uei=None,
        alias_type="legal", alias_name="Existing Co",
        alias_source="manual", confidence=1.0,
        created_at=datetime.now(tz=timezone.utc).isoformat(),
    )
    # Should not touch network or insert anything
    inserted = ensure_alias_for_ticker("EXIST", fetcher=lambda: {})
    assert inserted is False

    conn = get_connection()
    rows = conn.execute(
        "SELECT alias_source FROM entity_aliases WHERE ticker = 'EXIST'"
    ).fetchall()
    conn.close()
    # Only the manual row, no new bootstrap row
    assert all(r["alias_source"] == "manual" for r in rows)


def test_ensure_alias_inserts_from_sec_mapping_on_first_call():
    """When ticker has no alias, fetch SEC mapping and insert a legal alias."""
    # Inject a fake SEC mapping (avoid network)
    fake_mapping = {
        "FOOBAR": ("0001234567", "Foobar Industries Inc."),
        "OTHER":  ("0009999999", "Other Co"),
    }
    inserted = ensure_alias_for_ticker("FOOBAR", fetcher=lambda: fake_mapping)
    assert inserted is True

    r = resolve_ticker("Foobar Industries Inc.")
    assert r is not None and r.ticker == "FOOBAR"

    conn = get_connection()
    row = conn.execute(
        "SELECT cik, alias_source, alias_type FROM entity_aliases "
        "WHERE ticker = 'FOOBAR' ORDER BY id"
    ).fetchone() if False else conn.execute(
        "SELECT cik, alias_source, alias_type FROM entity_aliases WHERE ticker = 'FOOBAR' LIMIT 1"
    ).fetchone()
    conn.close()
    assert row["cik"] == "0001234567"
    assert row["alias_source"] == "sec_lazy_bootstrap"
    assert row["alias_type"] == "legal"


def test_ensure_alias_returns_false_when_ticker_not_in_sec_mapping():
    """Unknown ticker → can't bootstrap → returns False, no row inserted."""
    fake_mapping = {"DIFFERENT": ("0000000001", "Different Co")}
    inserted = ensure_alias_for_ticker("UNKNOWN", fetcher=lambda: fake_mapping)
    assert inserted is False

    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM entity_aliases WHERE ticker = 'UNKNOWN'"
    ).fetchall()
    conn.close()
    assert rows == []


def test_ensure_alias_caches_sec_mapping_across_calls():
    """The fetcher should only be called once across multiple bootstrap requests."""
    call_count = {"n": 0}

    def counting_fetcher():
        call_count["n"] += 1
        return {
            "CACHED_A": ("0000000001", "Cached A Inc"),
            "CACHED_B": ("0000000002", "Cached B Corp"),
        }

    ensure_alias_for_ticker("CACHED_A", fetcher=counting_fetcher)
    ensure_alias_for_ticker("CACHED_B", fetcher=counting_fetcher)
    assert call_count["n"] == 1  # Only one network call


def test_get_sec_display_name_returns_raw_name_after_bootstrap():
    """After lazy bootstrap, the raw SEC display name should be retrievable
    (unnormalized — for downstream API queries like USPTO that need
    'Apple Inc.' not 'apple')."""
    from src.data.entity_aliases import get_sec_display_name

    fake_mapping = {"DISP_TEST": ("0001111111", "Display Test Industries Inc.")}
    ensure_alias_for_ticker("DISP_TEST", fetcher=lambda: fake_mapping)

    name = get_sec_display_name("DISP_TEST")
    assert name == "Display Test Industries Inc."


def test_get_sec_display_name_returns_none_when_ticker_unknown():
    """If the ticker has never been bootstrapped (cache miss), return None."""
    from src.data.entity_aliases import get_sec_display_name

    # Force cache to a known-mapped state without the target ticker
    fake_mapping = {"SOMETHING_ELSE": ("0000000001", "Something Else Co")}
    ensure_alias_for_ticker("SOMETHING_ELSE", fetcher=lambda: fake_mapping)

    assert get_sec_display_name("ZZZZZ_NOT_IN_CACHE") is None


def test_get_sec_display_name_returns_none_before_cache_populated():
    """If the SEC mapping hasn't been fetched yet, return None (no fetch)."""
    import src.data.entity_aliases as ea
    ea._SEC_MAPPING_CACHE = None  # reset

    from src.data.entity_aliases import get_sec_display_name
    assert get_sec_display_name("AAPL") is None
