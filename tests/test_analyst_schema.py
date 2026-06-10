"""Schema additions for the AI analyst: signal_archive + daily_predictions.mode."""
from src.utils.db import get_connection, init_db


def _cols(conn, table):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def test_signal_archive_table_exists():
    init_db()
    conn = get_connection()
    try:
        cols = _cols(conn, "signal_archive")
    finally:
        conn.close()
    assert {"as_of_date", "symbol", "signals_json", "captured_at"} <= cols


def test_daily_predictions_has_mode_column():
    init_db()
    conn = get_connection()
    try:
        assert "mode" in _cols(conn, "daily_predictions")
    finally:
        conn.close()


def test_init_db_is_idempotent_for_mode():
    # Running init_db twice must not error on the ALTER (column already added).
    init_db()
    init_db()
    conn = get_connection()
    try:
        assert "mode" in _cols(conn, "daily_predictions")
    finally:
        conn.close()
