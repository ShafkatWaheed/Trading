"""Tests for the peer seed CSV loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.data.peer_seed_loader import (
    DEFAULT_SEED_PATH,
    SEED_CONFIDENCE_HIGH,
    SEED_SOURCE_HAND,
    load_tier_a_peers,
    parse_peer_csv,
    peer_counts,
)
from src.data.universe_loader import load_tier_a
from src.utils.db import get_connection, init_db


# ── CSV parsing ──────────────────────────────────────────────────


def test_seed_file_exists():
    assert DEFAULT_SEED_PATH.exists(), f"missing seed file: {DEFAULT_SEED_PATH}"


def test_parse_returns_rows():
    rows = parse_peer_csv(DEFAULT_SEED_PATH)
    assert len(rows) >= 100, f"expected ≥100 peer edges, got {len(rows)}"


def test_parse_uppercases_symbols():
    rows = parse_peer_csv(DEFAULT_SEED_PATH)
    for r in rows:
        assert r["from_symbol"] == r["from_symbol"].upper()
        assert r["to_symbol"] == r["to_symbol"].upper()


def test_parse_skips_self_edges():
    rows = parse_peer_csv(DEFAULT_SEED_PATH)
    for r in rows:
        assert r["from_symbol"] != r["to_symbol"]


def test_similarity_within_range():
    rows = parse_peer_csv(DEFAULT_SEED_PATH)
    for r in rows:
        assert 0.0 <= r["similarity"] <= 1.0


def test_critical_peer_pairs_present():
    """Spot-check that key competitive pairs are in the seed."""
    rows = parse_peer_csv(DEFAULT_SEED_PATH)
    pairs = {(r["from_symbol"], r["to_symbol"]) for r in rows}
    must_have = {
        ("NVDA", "AVGO"), ("NVDA", "AMD"),
        ("MSFT", "GOOGL"), ("MSFT", "AMZN"),
        ("V", "MA"), ("MA", "V"),
        ("LMT", "RTX"), ("LMT", "NOC"),
        ("XOM", "CVX"),
        ("HD", "LOW"),
        ("LLY", "NVO"),
        ("UPS", "FDX"),
        ("CAT", "DE"),
    }
    missing = must_have - pairs
    assert not missing, f"seed missing critical peer pairs: {missing}"


# ── Loader behaviour ─────────────────────────────────────────────


def test_load_inserts_bidirectional_edges():
    init_db()
    load_tier_a()
    counts = load_tier_a_peers(bidirectional=True)
    # bidirectional means inserted is 2x rows-loaded (minus skipped orphans)
    assert counts["inserted"] >= 200
    assert counts["skipped_orphan"] >= 0  # ok if some 'to_symbol's are off-universe
    assert counts["total_input"] == counts["inserted"] // 2 + counts["skipped_orphan"]


def test_load_writes_with_correct_source_and_confidence():
    init_db()
    load_tier_a()
    load_tier_a_peers()
    conn = get_connection()
    try:
        rows = conn.execute(
            f"SELECT source, confidence FROM stock_peers WHERE source='{SEED_SOURCE_HAND}' LIMIT 1"
        ).fetchall()
        assert rows, "no seed-tagged peer rows found"
        assert rows[0]["confidence"] == SEED_CONFIDENCE_HIGH
    finally:
        conn.close()


def test_load_is_idempotent():
    """Two consecutive loads must leave the same number of rows in the table.

    We don't rely on `deleted == inserted` because the CSV legitimately has
    some pairs declared in both directions (e.g. MSFT-GOOGL and GOOGL-MSFT),
    so the bidirectional pass triggers UPSERT-update instead of a fresh
    insert on the duplicates. The right invariant is final-row-count equality.
    """
    init_db()
    load_tier_a()
    load_tier_a_peers()
    conn = get_connection()
    try:
        n1 = conn.execute(
            f"SELECT COUNT(*) FROM stock_peers WHERE source='{SEED_SOURCE_HAND}'"
        ).fetchone()[0]
    finally:
        conn.close()

    load_tier_a_peers()
    conn = get_connection()
    try:
        n2 = conn.execute(
            f"SELECT COUNT(*) FROM stock_peers WHERE source='{SEED_SOURCE_HAND}'"
        ).fetchone()[0]
    finally:
        conn.close()

    assert n1 == n2, f"seed loader not idempotent: {n1} → {n2} rows"


def test_load_skips_orphan_to_symbols():
    """Edges referencing a symbol not in stocks_universe should be skipped, not crash."""
    # The seed includes references to some symbols that may not be in Tier A
    # (e.g. UMC, GFS, BJ, BURL — these are Tier B/C). Until network refresh
    # populates them, they should be reported as orphans, not raise.
    init_db()
    load_tier_a()
    counts = load_tier_a_peers()
    # Some rows ARE expected to be orphans given current Tier-A-only universe.
    # Just verify the loader runs without error.
    assert counts["inserted"] > 0


def test_specific_pair_loaded_correctly():
    init_db()
    load_tier_a()
    load_tier_a_peers()
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM stock_peers WHERE from_symbol='NVDA' AND to_symbol='AMD'"
        ).fetchone()
        assert row is not None, "NVDA-AMD edge missing"
        assert row["similarity"] >= 0.7
        assert row["overlap_dimensions"] is not None
        assert "gpu" in row["overlap_dimensions"].lower()
    finally:
        conn.close()


def test_bidirectional_reverse_edge_present():
    init_db()
    load_tier_a()
    load_tier_a_peers(bidirectional=True)
    conn = get_connection()
    try:
        # Check both NVDA→AMD AND AMD→NVDA exist
        forward = conn.execute(
            "SELECT 1 FROM stock_peers WHERE from_symbol='NVDA' AND to_symbol='AMD'"
        ).fetchone()
        reverse = conn.execute(
            "SELECT 1 FROM stock_peers WHERE from_symbol='AMD' AND to_symbol='NVDA'"
        ).fetchone()
        assert forward is not None
        assert reverse is not None
    finally:
        conn.close()


def test_peer_counts_diagnostic():
    init_db()
    load_tier_a()
    load_tier_a_peers()
    counts = peer_counts()
    assert counts.get(SEED_SOURCE_HAND, 0) >= 200
    assert counts["total"] >= 200
