from __future__ import annotations

from src.utils.db import get_connection, init_db


def test_known_future_events_table_exists():
    init_db()
    conn = get_connection()
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='known_future_events'"
    ).fetchone()
    conn.close()
    assert row is not None


def test_known_future_events_columns():
    init_db()
    conn = get_connection()
    cols = {r["name"] for r in conn.execute(
        "PRAGMA table_info(known_future_events)"
    ).fetchall()}
    conn.close()
    expected = {
        "event_id", "ticker", "event_type", "event_date",
        "source", "source_url", "details_json", "added_at",
    }
    assert expected.issubset(cols)


def test_known_future_events_indices():
    init_db()
    conn = get_connection()
    idxs = {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='known_future_events'"
    ).fetchall()}
    conn.close()
    assert "idx_known_future_events_date" in idxs
    assert "idx_known_future_events_ticker" in idxs
