"""Tests for SAM.gov contractor UEI seeder."""
from __future__ import annotations

import pytest

from src.data.sam_contractor_seed import (
    TOP_CONTRACTOR_UEIS,
    ensure_uei_for_ticker,
    seed_top_contractors,
)
from src.utils.db import get_connection, init_db


@pytest.fixture(autouse=True)
def _clean():
    init_db()
    conn = get_connection()
    conn.execute("DELETE FROM entity_aliases WHERE alias_source = 'sam_curated'")
    conn.commit()
    conn.close()
    yield
    conn = get_connection()
    conn.execute("DELETE FROM entity_aliases WHERE alias_source = 'sam_curated'")
    conn.commit()
    conn.close()


def test_top_contractor_ueis_has_expected_size():
    """Sanity: covers at least the major defense primes + IT govtech."""
    assert len(TOP_CONTRACTOR_UEIS) >= 25
    for t in ("LMT", "RTX", "GD", "NOC", "BA", "MSFT", "AMZN", "ACN"):
        assert t in TOP_CONTRACTOR_UEIS


def test_uei_format_is_12_chars():
    """SAM.gov UEIs are exactly 12 alphanumeric chars."""
    for ticker, (uei, _name) in TOP_CONTRACTOR_UEIS.items():
        assert len(uei) == 12, f"{ticker} UEI {uei!r} is not 12 chars"
        assert uei.isalnum(), f"{ticker} UEI {uei!r} is not alphanumeric"


def test_seed_top_contractors_inserts_all_rows():
    n = seed_top_contractors()
    assert n == len(TOP_CONTRACTOR_UEIS)

    conn = get_connection()
    row = conn.execute(
        "SELECT COUNT(*) FROM entity_aliases WHERE alias_source = 'sam_curated' AND alias_type = 'sam_business_name'"
    ).fetchone()
    conn.close()
    assert row[0] == len(TOP_CONTRACTOR_UEIS)


def test_seed_top_contractors_is_idempotent():
    seed_top_contractors()
    seed_top_contractors()
    # Still only the curated count (INSERT OR REPLACE)
    conn = get_connection()
    row = conn.execute(
        "SELECT COUNT(*) FROM entity_aliases WHERE alias_source = 'sam_curated'"
    ).fetchone()
    conn.close()
    assert row[0] == len(TOP_CONTRACTOR_UEIS)


def test_ensure_uei_for_known_ticker_inserts():
    inserted = ensure_uei_for_ticker("LMT")
    assert inserted is True
    conn = get_connection()
    row = conn.execute(
        "SELECT uei FROM entity_aliases WHERE ticker = 'LMT' AND alias_type = 'sam_business_name'"
    ).fetchone()
    conn.close()
    assert row["uei"] == TOP_CONTRACTOR_UEIS["LMT"][0]


def test_ensure_uei_for_unknown_ticker_returns_false():
    inserted = ensure_uei_for_ticker("ZZZ_UNKNOWN")
    assert inserted is False


def test_ensure_uei_is_idempotent():
    ensure_uei_for_ticker("LMT")
    inserted = ensure_uei_for_ticker("LMT")
    assert inserted is False  # Already seeded, no-op
