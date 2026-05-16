from __future__ import annotations

from src.utils.db import get_connection, init_db


def test_entity_match_decisions_table_exists():
    init_db()
    conn = get_connection()
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='entity_match_decisions'"
    ).fetchone()
    conn.close()
    assert row is not None


def test_entity_match_decisions_columns():
    init_db()
    conn = get_connection()
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(entity_match_decisions)").fetchall()}
    conn.close()
    expected = {
        "id", "ticker", "source", "input_name",
        "matched_alias", "method", "confidence",
        "rejected_candidates_json", "decided_at",
    }
    assert expected.issubset(cols)


def test_entity_match_decisions_indices():
    init_db()
    conn = get_connection()
    idxs = {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='entity_match_decisions'"
    ).fetchall()}
    conn.close()
    assert "idx_entity_match_decisions_ticker" in idxs
    assert "idx_entity_match_decisions_source" in idxs
