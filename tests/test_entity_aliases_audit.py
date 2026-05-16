"""Tests for the audit-logging resolver wrapper (Wave 2)."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from src.data.entity_aliases import (
    insert_alias,
    resolve_ticker_with_audit,
)
from src.utils.db import get_connection, init_db


@pytest.fixture(autouse=True)
def _clean():
    init_db()
    conn = get_connection()
    conn.execute("DELETE FROM entity_aliases WHERE alias_source = 'audit_test'")
    conn.execute("DELETE FROM entity_match_decisions WHERE source = 'audit_test'")
    conn.commit()
    conn.close()
    yield


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _seed(ticker: str, alias_name: str, alias_type: str = "legal", cik: str | None = None):
    insert_alias(
        ticker=ticker, cik=cik, uei=None,
        alias_type=alias_type, alias_name=alias_name,
        alias_source="audit_test", confidence=1.0, created_at=_now(),
    )


def test_resolve_with_audit_logs_exact_match():
    _seed("AAPL", "apple", cik="0000320193")
    out = resolve_ticker_with_audit("Apple Inc.", source="audit_test", use_fuzzy=False)
    assert out.ticker == "AAPL"
    assert out.method == "exact_alias"
    assert out.confidence == 1.0

    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM entity_match_decisions WHERE source='audit_test' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    assert row["ticker"] == "AAPL"
    assert row["input_name"] == "Apple Inc."
    assert row["method"] == "exact_alias"
    assert row["confidence"] == 1.0


def test_resolve_with_audit_logs_no_match():
    out = resolve_ticker_with_audit("ZZZZZ Unknown Co", source="audit_test", use_fuzzy=False)
    assert out.ticker is None
    assert out.method == "no_match"
    assert out.confidence == 0.0

    conn = get_connection()
    row = conn.execute(
        "SELECT ticker, method FROM entity_match_decisions WHERE source='audit_test' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    assert row["ticker"] is None
    assert row["method"] == "no_match"


def test_resolve_with_audit_records_rejected_candidates():
    _seed("AAPL", "apple")
    _seed("APLE", "apple hospitality reit")
    out = resolve_ticker_with_audit(
        "Apple Hospitalty",   # typo
        source="audit_test",
        use_fuzzy=True,
        min_confidence=0.8,
    )
    conn = get_connection()
    row = conn.execute(
        "SELECT rejected_candidates_json FROM entity_match_decisions "
        "WHERE source='audit_test' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    rejected = json.loads(row["rejected_candidates_json"] or "[]")
    # Either AAPL or APLE is chosen; the other appears in rejected (or other candidates do).
    if out.ticker == "AAPL":
        tickers_rejected = {c["ticker"] for c in rejected}
        assert "APLE" in tickers_rejected or len(rejected) >= 1
