"""Tests for the ETF holdings parser + universe membership upsert.

Network fetch (`fetch_holdings`, `fetch_all_indices`) is NOT exercised in
tests — those touch live iShares/Invesco endpoints. We test the CSV parser
against a real-format fixture and the upsert path with synthetic memberships.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.data.index_loader import (
    apply_universe_memberships,
    load_holdings_csv,
    _parse_holdings_text,
)
from src.data.universe_loader import load_tier_a, universe_counts
from src.utils.db import get_connection, init_db


FIXTURE = Path(__file__).parent / "fixtures" / "sample_holdings.csv"


# ── CSV parsing ───────────────────────────────────────────────────────


def test_parser_skips_metadata_header_and_extracts_tickers():
    out = load_holdings_csv(FIXTURE)
    assert {"NVDA", "MSFT", "AAPL"} <= out


def test_parser_filters_cash_and_futures_rows():
    out = load_holdings_csv(FIXTURE)
    assert "CASH" not in out
    assert "USD" not in out
    assert not any("FUTURE" in s for s in out)


def test_parser_returns_uppercase_symbols():
    out = load_holdings_csv(FIXTURE)
    assert all(s.upper() == s for s in out)


def test_parser_returns_empty_for_unstructured_text():
    out = _parse_holdings_text("not a csv\nsome random text\nno ticker header here")
    assert out == set()


def test_parser_raises_on_missing_file():
    with pytest.raises(FileNotFoundError):
        load_holdings_csv("/nonexistent/path/holdings.csv")


# ── Universe upsert ────────────────────────────────────────────────────
# Each test below uses the `fresh_db` fixture (defined in conftest.py) for a
# guaranteed-empty DB. No production-source DELETEs needed.


def test_apply_memberships_inserts_correct_tier(fresh_db):
    test_syms = ("NVDA", "MSFT", "AAPL", "MIDCAP", "RUSSELL_ONLY", "SMALLCAP", "RY")
    counts = apply_universe_memberships(
        memberships={
            "sp500":     {"NVDA", "MSFT", "AAPL", "MIDCAP"},
            "russell1k": {"NVDA", "MSFT", "AAPL", "MIDCAP", "RUSSELL_ONLY"},
            "russell2k": {"SMALLCAP"},
            "qqq":       {"NVDA", "MSFT"},
            "tsx60":     {"RY"},
        },
        market_cap_map={
            "NVDA": 3.5e12,
            "MSFT": 3.2e12,
            "AAPL": 3.0e12,
            "MIDCAP": 8e9,
            "RUSSELL_ONLY": 5e9,
            "SMALLCAP": 800e6,
        },
        adv_map={
            "NVDA": 20e9, "MSFT": 12e9, "AAPL": 10e9,
            "MIDCAP": 50e6, "RUSSELL_ONLY": 20e6, "SMALLCAP": 5e6,
        },
    )
    assert counts["total_seen"] == 7

    conn = get_connection()
    try:
        # Query by symbol set — symbols that the loader didn't insert (e.g. NVDA
        # was already in via tier_a_seed) still count: the upsert updates them.
        placeholders = ",".join("?" * len(test_syms))
        rows = {r["symbol"]: r["tier"] for r in conn.execute(
            f"SELECT symbol, tier FROM stocks_universe WHERE symbol IN ({placeholders})",
            test_syms,
        ).fetchall()}
        # SP500 + cap + adv → A
        assert rows["NVDA"] == "A"
        assert rows["MSFT"] == "A"
        assert rows["AAPL"] == "A"
        # SP500 below cap → B
        assert rows["MIDCAP"] == "B"
        # Russell1000 only → B
        assert rows["RUSSELL_ONLY"] == "B"
        # Russell2000 only → C
        assert rows["SMALLCAP"] == "C"
        # TSX60 only → B
        assert rows["RY"] == "B"
    finally:
        conn.close()


def test_apply_memberships_promotes_hand_seeded_tier_a_above_classifier(fresh_db):
    """ARM is in the tier_a_seed but might not show up in S&P 500 indices.
    Even if memberships have it only in Russell 1000, it must stay tier A."""
    counts = apply_universe_memberships(
        memberships={"russell1k": {"ARM"}},
    )
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT tier FROM stocks_universe WHERE symbol='ARM'"
        ).fetchone()
        assert row is not None
        assert row["tier"] == "A", "hand_seeded_tier_a override must dominate"
    finally:
        conn.close()


def test_apply_memberships_idempotent(fresh_db):
    apply_universe_memberships(
        memberships={"sp500": {"NEW_NAME"}},
        market_cap_map={"NEW_NAME": 60e9},
        adv_map={"NEW_NAME": 300e6},
    )
    second = apply_universe_memberships(
        memberships={"sp500": {"NEW_NAME"}},
        market_cap_map={"NEW_NAME": 60e9},
        adv_map={"NEW_NAME": 300e6},
    )
    # Second run finds the row and updates rather than re-inserts.
    assert second["updated"] >= 1
    assert second["inserted"] == 0


def test_apply_memberships_does_not_demote_tier_a(fresh_db):
    """Once a stock is tier A (hand-seeded or classifier), index_loader
    must never demote it on a later run that lacks index data."""
    load_tier_a()                       # establishes NVDA = A from hand seed
    apply_universe_memberships(
        memberships={"russell1k": {"NVDA"}},   # no S&P, no cap data
    )
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT tier FROM stocks_universe WHERE symbol='NVDA'"
        ).fetchone()
        assert row["tier"] == "A"
    finally:
        conn.close()
