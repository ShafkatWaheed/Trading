from __future__ import annotations

from src.utils.db import get_connection, init_db


def test_source_freshness_table_exists():
    init_db()
    conn = get_connection()
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='source_freshness'"
    ).fetchone()
    conn.close()
    assert row is not None


def test_source_freshness_columns():
    init_db()
    conn = get_connection()
    cols = {r["name"] for r in conn.execute(
        "PRAGMA table_info(source_freshness)"
    ).fetchall()}
    conn.close()
    expected = {
        "source", "cadence", "ttl_seconds", "last_fetched_at",
        "next_due_at", "last_status", "last_error", "last_payload_count",
        "rate_limit_budget", "rate_limit_remaining",
    }
    assert expected.issubset(cols), f"missing columns: {expected - cols}"


def test_source_freshness_next_due_index():
    init_db()
    conn = get_connection()
    idxs = {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='source_freshness'"
    ).fetchall()}
    conn.close()
    assert "idx_source_freshness_next_due" in idxs
