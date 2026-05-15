"""Tests for the SEC EDGAR alias seeder (Wave 1)."""
from __future__ import annotations

import pytest

from src.data.entity_aliases import seed_from_sec_mapping
from src.utils.db import get_connection, init_db


@pytest.fixture(autouse=True)
def _clean():
    init_db()
    conn = get_connection()
    conn.execute("DELETE FROM entity_aliases WHERE alias_source = 'sec_test'")
    conn.commit()
    conn.close()
    yield


def test_seed_from_sec_mapping_inserts_cik_aliases():
    """Given a dict of {ticker: (cik, legal_name)}, the seeder inserts rows
    with alias_type='legal', confidence=1.0, and cik populated."""
    mapping = {
        "AAPL": ("0000320193", "Apple Inc."),
        "MSFT": ("0000789019", "Microsoft Corporation"),
    }
    n = seed_from_sec_mapping(mapping, alias_source="sec_test")
    assert n == 2

    conn = get_connection()
    rows = conn.execute(
        "SELECT ticker, cik, alias_name, alias_type, confidence FROM entity_aliases "
        "WHERE alias_source = 'sec_test' ORDER BY ticker"
    ).fetchall()
    conn.close()
    assert len(rows) == 2
    assert rows[0]["ticker"] == "AAPL"
    assert rows[0]["cik"] == "0000320193"
    assert rows[0]["alias_name"] == "apple"   # normalized
    assert rows[0]["alias_type"] == "legal"
    assert rows[0]["confidence"] == 1.0


def test_seed_from_sec_mapping_handles_empty():
    assert seed_from_sec_mapping({}, alias_source="sec_test") == 0


def test_seed_from_sec_mapping_skips_blank_entries():
    mapping = {
        "AAPL": ("0000320193", "Apple Inc."),
        "": ("0000000000", "ignored"),       # blank ticker → skip
        "BAD": ("", "no cik"),               # blank cik → skip
    }
    n = seed_from_sec_mapping(mapping, alias_source="sec_test")
    assert n == 1
