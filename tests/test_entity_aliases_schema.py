"""Schema test for entity_aliases table (Wave 1 foundation)."""
from __future__ import annotations

from src.utils.db import get_connection, init_db


def test_entity_aliases_table_exists():
    init_db()
    conn = get_connection()
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='entity_aliases'"
    ).fetchone()
    conn.close()
    assert row is not None, "entity_aliases table missing"


def test_entity_aliases_required_columns():
    init_db()
    conn = get_connection()
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(entity_aliases)").fetchall()}
    conn.close()
    expected = {
        "ticker", "cik", "uei", "alias_type", "alias_name",
        "alias_source", "confidence", "created_at",
    }
    assert expected.issubset(cols), f"missing columns: {expected - cols}"


def test_entity_aliases_indices():
    init_db()
    conn = get_connection()
    idxs = {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='entity_aliases'"
    ).fetchall()}
    conn.close()
    assert "idx_entity_aliases_name" in idxs
    assert "idx_entity_aliases_cik" in idxs
    assert "idx_entity_aliases_uei" in idxs


def test_entity_aliases_check_constraint_on_alias_type():
    init_db()
    conn = get_connection()
    import sqlite3
    with conn:
        try:
            conn.execute(
                "INSERT INTO entity_aliases (ticker, alias_type, alias_name, alias_source, confidence, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("AAPL", "bogus_type", "apple inc", "manual", 1.0, "2026-05-15T00:00:00Z"),
            )
            assert False, "expected CHECK constraint to reject 'bogus_type'"
        except sqlite3.IntegrityError:
            pass
    conn.close()
