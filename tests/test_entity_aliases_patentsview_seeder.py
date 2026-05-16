"""Tests for USPTO PatentsView assignee canonicalization seeder (Wave 2)."""
from __future__ import annotations

import pytest

from src.data.entity_aliases import seed_from_patentsview_assignees
from src.utils.db import get_connection, init_db


@pytest.fixture(autouse=True)
def _clean():
    init_db()
    conn = get_connection()
    conn.execute("DELETE FROM entity_aliases WHERE alias_source = 'patentsview_test'")
    conn.commit()
    conn.close()
    yield


def test_seed_from_patentsview_inserts_uspto_canonical():
    """Given {ticker: [canonical_assignee_names]}, inserts uspto_canonical aliases."""
    mapping = {
        "AAPL": ["Apple Inc.", "Apple Computer, Inc.", "Apple Computer Inc"],
        "MSFT": ["Microsoft Corporation", "Microsoft Technology Licensing LLC"],
    }
    n = seed_from_patentsview_assignees(mapping, alias_source="patentsview_test")
    assert n == 5

    conn = get_connection()
    rows = conn.execute(
        "SELECT ticker, alias_name, alias_type FROM entity_aliases "
        "WHERE alias_source = 'patentsview_test' ORDER BY ticker, alias_name"
    ).fetchall()
    conn.close()
    assert all(r["alias_type"] == "uspto_canonical" for r in rows)
    aapl_aliases = {r["alias_name"] for r in rows if r["ticker"] == "AAPL"}
    assert "apple" in aapl_aliases               # normalized
    assert "apple computer" in aapl_aliases      # subsidiary form preserved


def test_seed_from_patentsview_handles_empty_list():
    mapping = {"AAPL": []}
    assert seed_from_patentsview_assignees(mapping, alias_source="patentsview_test") == 0


def test_seed_from_patentsview_deduplicates_within_ticker():
    """Same normalized alias for one ticker should only insert once (PK constraint)."""
    mapping = {"AAPL": ["Apple Inc.", "Apple Inc.", "APPLE INC"]}
    n = seed_from_patentsview_assignees(mapping, alias_source="patentsview_test")
    assert n == 3  # function counts attempts, not DB inserts
    conn = get_connection()
    rows = conn.execute(
        "SELECT COUNT(*) AS c FROM entity_aliases WHERE alias_source='patentsview_test' AND ticker='AAPL'"
    ).fetchone()
    conn.close()
    assert rows["c"] == 1
