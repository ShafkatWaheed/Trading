"""Tests for fuzzy entity-alias matching (Wave 1)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.data.entity_aliases import insert_alias, resolve_ticker
from src.utils.db import get_connection, init_db


@pytest.fixture(autouse=True)
def _clean():
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


def _seed(ticker: str, alias: str):
    insert_alias(
        ticker=ticker, cik=None, uei=None,
        alias_type="legal", alias_name=alias,
        alias_source="test_fixture", confidence=1.0, created_at=_now(),
    )


def test_fuzzy_off_does_not_match_typo():
    _seed("AAPL", "apple")
    assert resolve_ticker("Aple Inc.", use_fuzzy=False) is None


def test_fuzzy_on_matches_close_typo_at_high_threshold():
    _seed("MSFT", "microsoft")
    r = resolve_ticker("Microsft Corporation", use_fuzzy=True, min_confidence=0.9)
    assert r is not None and r.ticker == "MSFT"
    assert 0.9 <= r.confidence <= 1.0


def test_fuzzy_rejects_low_confidence_match_at_scored_threshold():
    """Scored signals require ≥0.9 — junk strings should not pass."""
    _seed("AAPL", "apple")
    r = resolve_ticker("zebra giraffe ostrich", use_fuzzy=True, min_confidence=0.9)
    assert r is None


def test_fuzzy_information_threshold_is_looser():
    """Information sources accept ≥0.8 — slightly noisier matches OK."""
    _seed("LMT", "lockheed martin")
    r = resolve_ticker("Lockheed-Martin Co", use_fuzzy=True, min_confidence=0.8)
    assert r is not None and r.ticker == "LMT"


def test_fuzzy_match_returns_actual_confidence_score():
    _seed("AAPL", "apple")
    r = resolve_ticker("aple", use_fuzzy=True, min_confidence=0.8)
    assert r is not None, "fuzzy match for 'aple' → 'apple' should succeed at 0.8 threshold"
    # Confidence is the rapidfuzz score / 100, in (0, 1) exclusive.
    assert 0.0 < r.confidence < 1.0


def test_ambiguous_match_picks_highest_score():
    """If two aliases tie or near-tie, we must return one deterministically.
    Highest token_set_ratio wins; ties broken by ticker alpha order."""
    _seed("AAPL", "apple")
    _seed("APLE", "apple hospitality reit")
    r = resolve_ticker("Apple", use_fuzzy=True, min_confidence=0.8)
    # Exact match on 'apple' must win over partial on 'apple hospitality reit'
    assert r is not None and r.ticker == "AAPL"
