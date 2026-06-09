"""Guarded purge of non-equity junk rows from stocks_universe.

Temp DB + synthetic SYN_* symbols, source='test'. Verifies the purge deletes
nameless non-equity artifacts (incl. the over-long 'blob' symbol) but REFUSES
to delete any row that carries a graph edge — the core safety guard.
"""
from __future__ import annotations

from scripts.purge_universe_junk import purge_junk_universe_rows
from src.utils.db import get_connection, init_db


def _seed():
    init_db()
    conn = get_connection()
    try:
        conn.execute("DELETE FROM stocks_universe WHERE source='test'")
        conn.execute("DELETE FROM stock_industry WHERE source='test'")
        for sym in ("SYN_JUNK1", "SYN_JUNK2", "SYN_EDGED"):
            conn.execute(
                "INSERT INTO stocks_universe (symbol, tier, source) VALUES (?, 'B', 'test')",
                (sym,),
            )
        blob = "X" * 150  # stands in for the disclaimer blob (LENGTH > threshold)
        conn.execute(
            "INSERT INTO stocks_universe (symbol, tier, source) VALUES (?, 'B', 'test')",
            (blob,),
        )
        # SYN_EDGED is in the junk list but carries a graph edge → must be kept.
        conn.execute(
            "INSERT INTO stock_industry (symbol, industry_code, weight, is_primary, source) "
            "VALUES ('SYN_EDGED', 'Software', 1.0, 1, 'test')"
        )
        conn.commit()
    finally:
        conn.close()
    return blob


def _cleanup():
    conn = get_connection()
    try:
        conn.execute("DELETE FROM stocks_universe WHERE source='test'")
        conn.execute("DELETE FROM stock_industry WHERE source='test'")
        conn.commit()
    finally:
        conn.close()


def test_purge_deletes_junk_and_blob_keeps_edged():
    blob = _seed()
    res = purge_junk_universe_rows(
        source="test",
        symbols=["SYN_JUNK1", "SYN_JUNK2", "SYN_EDGED"],
        blob_min_len=100,
    )
    conn = get_connection()
    try:
        remaining = {
            r["symbol"]
            for r in conn.execute("SELECT symbol FROM stocks_universe WHERE source='test'")
        }
    finally:
        conn.close()
    _cleanup()

    # junk + blob gone; the edge-bearing row survived
    assert "SYN_JUNK1" not in remaining
    assert "SYN_JUNK2" not in remaining
    assert blob not in remaining
    assert "SYN_EDGED" in remaining

    assert set(res["deleted"]) >= {"SYN_JUNK1", "SYN_JUNK2"}
    skipped_syms = {s for s, _ in res["skipped_with_edges"]}
    assert "SYN_EDGED" in skipped_syms


def test_purge_is_scoped_to_source():
    # symbol is the PK, so a row exists under exactly one source. A row whose
    # source differs from the purge scope must not be considered a candidate.
    init_db()
    conn = get_connection()
    try:
        conn.execute("DELETE FROM stocks_universe WHERE symbol='SYN_OTHER'")
        conn.execute(
            "INSERT INTO stocks_universe (symbol, tier, source) VALUES ('SYN_OTHER', 'B', 'other')"
        )
        conn.commit()
    finally:
        conn.close()
    # Ask to purge SYN_OTHER but scoped to source='test' — different source → no-op.
    res = purge_junk_universe_rows(source="test", symbols=["SYN_OTHER"], blob_min_len=100)
    conn = get_connection()
    try:
        kept = conn.execute(
            "SELECT COUNT(*) FROM stocks_universe WHERE symbol='SYN_OTHER' AND source='other'"
        ).fetchone()[0]
        conn.execute("DELETE FROM stocks_universe WHERE symbol='SYN_OTHER'")
        conn.commit()
    finally:
        conn.close()
    assert kept == 1  # untouched — wrong source
    assert "SYN_OTHER" not in res["deleted"]
