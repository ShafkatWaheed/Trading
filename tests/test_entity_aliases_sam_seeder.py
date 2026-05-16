"""Tests for SAM.gov UEI alias seeder (Wave 2)."""
from __future__ import annotations

import pytest

from src.data.entity_aliases import seed_from_sam_mapping
from src.utils.db import get_connection, init_db


@pytest.fixture(autouse=True)
def _clean():
    init_db()
    conn = get_connection()
    conn.execute("DELETE FROM entity_aliases WHERE alias_source = 'sam_test'")
    conn.commit()
    conn.close()
    yield


def test_seed_from_sam_mapping_inserts_uei_aliases():
    """Given {ticker: (uei, business_name)}, inserts uei + sam_business_name aliases."""
    mapping = {
        "LMT": ("PR7YEP4DZW43", "LOCKHEED MARTIN CORPORATION"),
        "BA":  ("HQRPNEPAGM84", "THE BOEING COMPANY"),
    }
    n = seed_from_sam_mapping(mapping, alias_source="sam_test")
    assert n == 2

    conn = get_connection()
    rows = conn.execute(
        "SELECT ticker, uei, alias_name, alias_type, confidence FROM entity_aliases "
        "WHERE alias_source = 'sam_test' ORDER BY ticker"
    ).fetchall()
    conn.close()
    assert len(rows) == 2
    assert rows[1]["ticker"] == "LMT"
    assert rows[1]["uei"] == "PR7YEP4DZW43"
    assert rows[1]["alias_name"] == "lockheed martin"   # normalized
    assert rows[1]["alias_type"] == "sam_business_name"
    assert rows[1]["confidence"] == 1.0


def test_seed_from_sam_mapping_skips_blanks():
    mapping = {"LMT": ("PR7YEP4DZW43", "LOCKHEED MARTIN CORPORATION"),
               "":    ("AAAA", "ignored"),
               "BAD": ("", "no uei")}
    assert seed_from_sam_mapping(mapping, alias_source="sam_test") == 1
