"""Tests for entity-matches service (Wave 2 debug card)."""
from __future__ import annotations

import pytest


def test_entity_matches_for_ticker_with_no_history_returns_empty():
    from api.services.entity_matches_service import get_matches_for_ticker
    out = get_matches_for_ticker("ZZZ_NEVER_QUERIED")
    assert out["ticker"] == "ZZZ_NEVER_QUERIED"
    assert out["matches"] == []


def test_entity_matches_returns_recent_decisions():
    from datetime import datetime, timezone
    from src.utils.db import get_connection, init_db
    init_db()
    now = datetime.now(tz=timezone.utc).isoformat()
    conn = get_connection()
    conn.execute(
        "INSERT INTO entity_match_decisions (ticker, source, input_name, matched_alias, "
        "method, confidence, rejected_candidates_json, decided_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("MATCH_TEST", "test_source", "Match Test Corp", "match test",
         "exact_alias", 1.0, None, now),
    )
    conn.commit()
    conn.close()

    from api.services.entity_matches_service import get_matches_for_ticker
    out = get_matches_for_ticker("MATCH_TEST")
    assert out["ticker"] == "MATCH_TEST"
    assert len(out["matches"]) >= 1
    m = out["matches"][0]
    assert m["source"] == "test_source"
    assert m["method"] == "exact_alias"
    assert m["confidence"] == 1.0

    # cleanup
    conn = get_connection()
    conn.execute("DELETE FROM entity_match_decisions WHERE source='test_source'")
    conn.commit()
    conn.close()
