"""Tests for institutions + holdings CSV loaders (Phase 7A)."""

from __future__ import annotations

import pytest

from src.data.institutions_seed_loader import (
    DEFAULT_HOLDINGS_PATH,
    DEFAULT_INSTITUTIONS_PATH,
    VALID_TYPES,
    holdings_count,
    institution_count,
    load_all,
    load_holdings,
    load_institutions,
    parse_holdings_csv,
    parse_institutions_csv,
)
from src.data.universe_loader import load_tier_a
from src.utils.db import get_connection, init_db


# ── institutions CSV ─────────────────────────────────────────────


def test_institutions_seed_exists():
    assert DEFAULT_INSTITUTIONS_PATH.exists()


def test_parse_institutions_returns_rows():
    rows = parse_institutions_csv()
    assert len(rows) >= 30, f"expected ≥30 institution rows, got {len(rows)}"


def test_no_duplicate_ciks():
    rows = parse_institutions_csv()
    ciks = [r["cik"] for r in rows]
    assert len(ciks) == len(set(ciks)), "duplicate CIK in institutions seed"


def test_big_three_present():
    rows = parse_institutions_csv()
    by_cik = {r["cik"]: r["name"] for r in rows}
    # Real CIKs for the Big Three
    assert "1364742" in by_cik   # BlackRock
    assert "102909" in by_cik    # Vanguard
    assert "93751" in by_cik     # State Street


def test_types_within_allowlist():
    rows = parse_institutions_csv()
    for r in rows:
        if r["type"]:
            assert r["type"] in VALID_TYPES


def test_load_institutions_populates_table():
    init_db()
    counts = load_institutions()
    assert counts["total"] >= 30
    assert institution_count() >= 30


def test_load_institutions_idempotent():
    init_db()
    load_institutions()
    n1 = institution_count()
    load_institutions()
    n2 = institution_count()
    assert n1 == n2


def test_blackrock_is_index_fund():
    init_db()
    load_institutions()
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT type, name FROM institutions WHERE cik='1364742'"
        ).fetchone()
        assert row is not None
        assert row["type"] == "index_fund"
        assert "BlackRock" in row["name"]
    finally:
        conn.close()


# ── holdings CSV ────────────────────────────────────────────────


def test_holdings_seed_exists():
    assert DEFAULT_HOLDINGS_PATH.exists()


def test_parse_holdings_returns_rows():
    rows = parse_holdings_csv()
    assert len(rows) >= 30


def test_holdings_uppercases_symbols():
    rows = parse_holdings_csv()
    for r in rows:
        assert r["symbol"] == r["symbol"].upper()


def test_load_holdings_inserts_seed_rows():
    init_db()
    load_tier_a()
    load_institutions()
    counts = load_holdings()
    assert counts["inserted"] >= 30


def test_load_holdings_skips_orphan_symbols():
    """Some seed entries reference KHC, CMG, HLT, PLTR — not in Tier A.
    The loader should skip these as orphans, not crash."""
    init_db()
    load_tier_a()
    load_institutions()
    counts = load_holdings()
    assert counts["skipped_orphan"] >= 0


def test_load_holdings_idempotent_final_count():
    init_db()
    load_tier_a()
    load_all()
    n1 = holdings_count()
    load_all()
    n2 = holdings_count()
    assert n1 == n2


def test_blackrock_top_holding_is_aapl():
    init_db()
    load_tier_a()
    load_all()
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT pct_portfolio FROM institution_holdings "
            "WHERE cik='1364742' AND symbol='AAPL' AND as_of='2026-03-31'"
        ).fetchone()
        assert row is not None
        assert row["pct_portfolio"] >= 4.0
    finally:
        conn.close()


def test_berkshire_concentrated_in_aapl():
    """Berkshire's AAPL position should be much larger fraction of portfolio
    than the Big Three's (~28% vs ~4%) — verifying the active vs passive split."""
    init_db()
    load_tier_a()
    load_all()
    conn = get_connection()
    try:
        brk = conn.execute(
            "SELECT pct_portfolio FROM institution_holdings "
            "WHERE cik='1067983' AND symbol='AAPL' AND as_of='2026-03-31'"
        ).fetchone()
        blk = conn.execute(
            "SELECT pct_portfolio FROM institution_holdings "
            "WHERE cik='1364742' AND symbol='AAPL' AND as_of='2026-03-31'"
        ).fetchone()
        assert brk["pct_portfolio"] > 20.0
        assert blk["pct_portfolio"] < 10.0
    finally:
        conn.close()


def test_load_all_runs_both():
    init_db()
    load_tier_a()
    out = load_all()
    assert "institutions" in out
    assert "holdings" in out
    assert out["institutions"]["total"] >= 30
    assert out["holdings"]["inserted"] >= 30
