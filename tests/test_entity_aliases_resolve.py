"""Tests for entity-alias ticker resolution (Wave 1)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.data.entity_aliases import (
    ResolvedEntity,
    insert_alias,
    resolve_by_cik,
    resolve_by_uei,
    resolve_ticker,
)
from src.utils.db import get_connection, init_db


@pytest.fixture(autouse=True)
def _clean_aliases():
    init_db()
    conn = get_connection()
    conn.execute("DELETE FROM entity_aliases WHERE alias_source IN ('test_fixture')")
    conn.commit()
    conn.close()
    yield
    conn = get_connection()
    conn.execute("DELETE FROM entity_aliases WHERE alias_source IN ('test_fixture')")
    conn.commit()
    conn.close()


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def test_resolve_by_cik_returns_authoritative_match():
    insert_alias(
        ticker="AAPL", cik="0000320193", uei=None,
        alias_type="legal", alias_name="apple",
        alias_source="test_fixture", confidence=1.0, created_at=_now(),
    )
    r = resolve_by_cik("0000320193")
    assert r == ResolvedEntity(ticker="AAPL", matched_alias="apple", confidence=1.0, alias_type="legal")


def test_resolve_by_cik_returns_none_for_unknown():
    assert resolve_by_cik("9999999999") is None


def test_resolve_by_uei_returns_authoritative_match():
    insert_alias(
        ticker="LMT", cik=None, uei="ABC123DEF456",
        alias_type="sam_business_name", alias_name="lockheed martin",
        alias_source="test_fixture", confidence=1.0, created_at=_now(),
    )
    r = resolve_by_uei("ABC123DEF456")
    assert r is not None and r.ticker == "LMT"
    assert r.confidence == 1.0


def test_resolve_ticker_exact_match_after_normalize():
    insert_alias(
        ticker="MSFT", cik=None, uei=None,
        alias_type="legal", alias_name="microsoft",
        alias_source="test_fixture", confidence=1.0, created_at=_now(),
    )
    r = resolve_ticker("Microsoft Corporation")
    assert r is not None and r.ticker == "MSFT"
    assert r.confidence == 1.0
    assert r.matched_alias == "microsoft"


def test_resolve_ticker_returns_none_for_empty_input():
    assert resolve_ticker("") is None
    assert resolve_ticker("   ") is None


def test_resolve_ticker_returns_none_when_no_match():
    r = resolve_ticker("Nonexistent Hypothetical Co")
    assert r is None


def test_valid_alias_types_constant_matches_db_check_constraint():
    """The Python constant VALID_ALIAS_TYPES must match the SQL CHECK constraint
    on entity_aliases.alias_type. Otherwise insertions silently fail at runtime
    instead of validating at the Python boundary.
    """
    from src.data.entity_aliases import VALID_ALIAS_TYPES
    expected = frozenset({
        "legal", "common", "subsidiary",
        "uspto_canonical", "sam_business_name",
        "brand", "override",
    })
    assert VALID_ALIAS_TYPES == expected


def test_insert_alias_rejects_invalid_alias_type_python_side():
    """A bad alias_type should be rejected with ValueError BEFORE hitting SQL."""
    with pytest.raises(ValueError) as exc_info:
        insert_alias(
            ticker="AAPL", cik=None, uei=None,
            alias_type="not_a_real_type",
            alias_name="apple",
            alias_source="test_fixture", confidence=1.0, created_at=_now(),
        )
    assert "not_a_real_type" in str(exc_info.value)
