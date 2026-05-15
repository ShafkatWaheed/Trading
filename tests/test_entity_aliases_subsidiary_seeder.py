"""Tests for parent→subsidiary alias seeding (Wave 1)."""
from __future__ import annotations

import pytest

from src.data.entity_aliases import resolve_ticker, seed_subsidiaries_from_text
from src.utils.db import get_connection, init_db


@pytest.fixture(autouse=True)
def _clean():
    init_db()
    conn = get_connection()
    conn.execute("DELETE FROM entity_aliases WHERE alias_source = 'exhibit21_test'")
    conn.commit()
    conn.close()
    yield


EXHIBIT_21 = """
Exhibit 21
List of Subsidiaries of the Registrant

Name                                     Jurisdiction
Beats Electronics, LLC                   Delaware
Apple Operations International           Ireland
"""


def test_seed_subsidiaries_inserts_rows_pointing_to_parent():
    n = seed_subsidiaries_from_text(
        parent_ticker="AAPL",
        exhibit_21_text=EXHIBIT_21,
        alias_source="exhibit21_test",
    )
    assert n == 2

    r = resolve_ticker("Beats Electronics LLC")
    assert r is not None and r.ticker == "AAPL"
    assert r.alias_type == "subsidiary"

    r2 = resolve_ticker("Apple Operations International")
    assert r2 is not None and r2.ticker == "AAPL"


def test_seed_subsidiaries_empty_text_returns_zero():
    n = seed_subsidiaries_from_text(
        parent_ticker="AAPL",
        exhibit_21_text="",
        alias_source="exhibit21_test",
    )
    assert n == 0


def test_seed_subsidiaries_requires_uppercase_ticker():
    # Lowercase ticker should be uppercased before insert.
    n = seed_subsidiaries_from_text(
        parent_ticker="aapl",
        exhibit_21_text=EXHIBIT_21,
        alias_source="exhibit21_test",
    )
    assert n == 2
    r = resolve_ticker("Beats Electronics LLC")
    assert r is not None and r.ticker == "AAPL"  # stored uppercase
