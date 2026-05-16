"""Tests for the knowledge-graph schema migration + Tier A seed loader.

Verifies:
  * All seven new tables exist after init_db()
  * Constraint enforcement on tier values + check constraints
  * Tier A seed has ~150 stocks and loads cleanly (idempotent)
  * stock_industry primary mappings are created
  * Universe queries return tier-filtered results
"""

from __future__ import annotations

import sqlite3
from datetime import datetime

import pytest

from src.data.tier_a_seed import TIER_A, tier_a_count, tier_a_symbols
from src.data.universe_loader import (
    get_universe,
    load_tier_a,
    universe_counts,
)
from src.utils.db import get_connection, init_db


# --- schema -----------------------------------------------------------------


NEW_TABLES = [
    "industries",
    "stocks_universe",
    "stock_industry",
    "stock_peers",
    "stock_relations",
    "keyword_impact",
    "keyword_groups",
]


def test_init_db_creates_all_new_tables():
    init_db()
    conn = get_connection()
    try:
        for name in NEW_TABLES:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
            ).fetchone()
            assert row is not None, f"missing table: {name}"
    finally:
        conn.close()


def test_init_db_is_idempotent():
    init_db()
    init_db()
    conn = get_connection()
    try:
        for name in NEW_TABLES:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
            ).fetchone()
            assert row is not None
    finally:
        conn.close()


def test_stocks_universe_tier_check_constraint_rejects_bad_value():
    init_db()
    conn = get_connection()
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO stocks_universe (symbol, tier, source) VALUES (?, 'X', 'test')",
                ("BAD_TIER_TEST",),
            )
            conn.commit()
        conn.rollback()
    finally:
        conn.close()


def test_keyword_impact_requires_industry_or_target_stock():
    init_db()
    conn = get_connection()
    try:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO keyword_impact (keyword, polarity, weight) VALUES (?, ?, ?)",
                ("test_orphan", 0.5, 0.5),
            )
            conn.commit()
        conn.rollback()
    finally:
        conn.close()


# --- tier A seed data integrity --------------------------------------------


def test_tier_a_seed_has_target_count():
    assert 100 < tier_a_count() < 200, f"Tier A should be ~150 stocks, got {tier_a_count()}"


def test_tier_a_seed_has_no_duplicate_symbols():
    symbols = tier_a_symbols()
    assert len(symbols) == len(set(symbols)), "duplicate symbol in Tier A seed"


def test_tier_a_seed_has_unique_required_fields():
    for symbol, name, sector, industry, exchange, country in TIER_A:
        assert symbol, f"empty symbol in tier_a_seed"
        assert name, f"empty name for {symbol}"
        assert sector, f"empty sector for {symbol}"
        assert industry, f"empty industry for {symbol}"
        assert exchange in ("NASDAQ", "NYSE", "TSX"), f"unexpected exchange '{exchange}' for {symbol}"
        assert country in ("US", "CA"), f"unexpected country '{country}' for {symbol}"


def test_tier_a_covers_at_least_eight_sectors():
    sectors = {sector for _, _, sector, _, _, _ in TIER_A}
    assert len(sectors) >= 8, f"Tier A should span ≥8 sectors, got {len(sectors)}: {sectors}"


def test_tier_a_includes_mag7():
    symbols = set(tier_a_symbols())
    mag7 = {"AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA"}
    missing = mag7 - symbols
    assert not missing, f"Tier A missing Mag-7: {missing}"


def test_tier_a_includes_critical_themes():
    """Spot-check that key thematic anchors are present."""
    symbols = set(tier_a_symbols())
    must_have = {
        "TSM",     # foundry — critical AI supply chain
        "ASML",    # litho monopoly
        "MU",      # memory
        "LMT",     # defense
        "XOM",     # oil
        "JPM",     # mega bank
        "LLY",     # GLP-1 leader
        "CCJ",     # uranium / AI power
        "CEG",     # nuclear utility
        "GEV",     # grid power for AI
    }
    missing = must_have - symbols
    assert not missing, f"Tier A missing thematic anchors: {missing}"


# --- loader behavior --------------------------------------------------------
# Tests that assert exact insert counts use `fresh_db` (conftest.py) for a
# guaranteed-empty DB. No DELETE-by-source needed.


def test_load_tier_a_inserts_all_seed_rows(fresh_db):
    counts = load_tier_a()
    assert counts["stocks_inserted"] == tier_a_count(), counts

    rows = get_universe(tier=["A"])
    assert len(rows) == tier_a_count()
    syms = {r["symbol"] for r in rows}
    assert syms == set(tier_a_symbols())


def test_load_tier_a_creates_primary_industry_mapping_per_stock(fresh_db):
    load_tier_a()
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT symbol, industry_code, weight, is_primary FROM stock_industry "
            "WHERE source='tier_a_seed'"
        ).fetchall()
        assert len(rows) == tier_a_count()
        for r in rows:
            assert r["weight"] == 1.0
            assert r["is_primary"] == 1
    finally:
        conn.close()


def test_load_tier_a_creates_industry_rows(fresh_db):
    load_tier_a()
    conn = get_connection()
    try:
        # Every distinct industry in the seed must appear in industries.
        seed_industries = {industry for _, _, _, industry, _, _ in TIER_A}
        for industry in seed_industries:
            row = conn.execute(
                "SELECT code, sector FROM industries WHERE code=?", (industry,)
            ).fetchone()
            assert row is not None, f"industry not loaded: {industry}"
            assert row["sector"], f"sector empty for {industry}"
    finally:
        conn.close()


def test_load_tier_a_is_idempotent(fresh_db):
    first = load_tier_a()
    second = load_tier_a()
    # Second run finds the already-inserted rows; no duplicates.
    assert second["stocks_inserted"] == 0
    assert second["stocks_updated"] == tier_a_count()
    counts = universe_counts()
    assert counts["A"] == tier_a_count()


def test_universe_counts_reports_tier_a():
    load_tier_a()
    counts = universe_counts()
    assert counts.get("A") == tier_a_count()
    assert counts["total"] >= tier_a_count()


def test_get_universe_filters_by_tier():
    load_tier_a()
    a_rows = get_universe(tier=["A"])
    assert all(r["tier"] == "A" for r in a_rows)
    # B/C/D rows may be present from other tests' index_loader inserts; just
    # verify the filter is correctly applied — the returned rows must all be B.
    b_rows = get_universe(tier=["B"])
    assert all(r["tier"] == "B" for r in b_rows)
    # Bogus tier returns empty, doesn't error
    assert get_universe(tier=["Z"]) == []


def test_get_universe_returns_dicts_with_expected_keys():
    load_tier_a()
    rows = get_universe(tier=["A"])
    sample = rows[0]
    for key in ("symbol", "name", "tier", "exchange", "country", "source", "as_of"):
        assert key in sample, f"missing key '{key}' in universe row"
    assert sample["tier"] == "A"
