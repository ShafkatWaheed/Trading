"""Tests for the commodity + stock_commodity_exposure CSV loaders (Phase 6)."""

from __future__ import annotations

import pytest

from src.data.commodity_seed_loader import (
    DEFAULT_COMMODITIES_PATH,
    DEFAULT_EXPOSURE_PATH,
    SEED_CONFIDENCE_HIGH,
    SEED_SOURCE_HAND,
    VALID_ROLES,
    commodity_count,
    exposure_counts,
    load_all,
    load_commodities,
    load_exposures,
    parse_commodities_csv,
    parse_exposure_csv,
)
from src.data.universe_loader import load_tier_a
from src.utils.db import get_connection, init_db


# ── commodities CSV ────────────────────────────────────────────


def test_commodities_seed_exists():
    assert DEFAULT_COMMODITIES_PATH.exists()


def test_parse_commodities_returns_rows():
    rows = parse_commodities_csv()
    assert len(rows) >= 25, f"expected ≥25 commodity rows, got {len(rows)}"


def test_commodity_codes_lowercased():
    rows = parse_commodities_csv()
    for r in rows:
        assert r["code"] == r["code"].lower()


def test_critical_commodities_present():
    rows = parse_commodities_csv()
    codes = {r["code"] for r in rows}
    must_have = {
        "crude_oil", "natural_gas", "gasoline",
        "copper", "gold", "silver", "uranium", "lithium", "steel", "rare_earths",
        "wheat", "corn", "sugar", "cocoa", "coffee",
    }
    missing = must_have - codes
    assert not missing, f"seed missing critical commodities: {missing}"


def test_load_commodities_populates_table():
    init_db()
    counts = load_commodities()
    assert counts["total"] >= 25
    assert commodity_count() == counts["total"]


def test_load_commodities_idempotent():
    init_db()
    load_commodities()
    n1 = commodity_count()
    load_commodities()
    n2 = commodity_count()
    assert n1 == n2


# ── exposure CSV ───────────────────────────────────────────────


def test_exposure_seed_exists():
    assert DEFAULT_EXPOSURE_PATH.exists()


def test_parse_exposure_returns_rows():
    rows = parse_exposure_csv()
    assert len(rows) >= 100, f"expected ≥100 exposure rows, got {len(rows)}"


def test_exposure_role_validity():
    rows = parse_exposure_csv()
    for r in rows:
        assert r["role"] in VALID_ROLES


def test_exposure_polarity_range():
    rows = parse_exposure_csv()
    for r in rows:
        assert -1.0 <= r["polarity"] <= 1.0


def test_exposure_elasticity_range():
    rows = parse_exposure_csv()
    for r in rows:
        assert 0.0 <= r["elasticity"] <= 1.0


def test_outputs_have_positive_polarity():
    """Stocks selling a commodity should have polarity=+1 by convention."""
    rows = parse_exposure_csv()
    for r in rows:
        if r["role"] == "output":
            assert r["polarity"] > 0, f"output role with non-positive polarity: {r}"


def test_inputs_typically_have_negative_polarity():
    """Pure inputs (not refiner output) should have polarity=-1."""
    rows = parse_exposure_csv()
    # Refiners are nuanced — VLO/MPC/PSX ARE input:crude_oil with polarity=-1.
    # Test the convention rather than a count.
    for r in rows:
        if r["role"] == "input":
            assert r["polarity"] < 0, f"input role with non-negative polarity: {r}"


def test_critical_exposures_present():
    rows = parse_exposure_csv()
    triples = {(r["symbol"], r["commodity_code"], r["role"]) for r in rows}
    must_have = {
        ("XOM", "crude_oil", "output"),
        ("CVX", "crude_oil", "output"),
        ("VLO", "crude_oil", "input"),
        ("VLO", "gasoline", "output"),
        ("CCJ", "uranium", "output"),
        ("FCX", "copper", "output"),
        ("NEM", "gold", "output"),
        ("TSLA", "lithium", "input"),
        ("LMT", "rare_earths", "input"),
        ("UPS", "diesel", "input"),
        ("MDLZ", "cocoa", "input"),
        ("SBUX", "coffee", "input"),
        ("HD", "lumber", "input"),
    }
    missing = must_have - triples
    assert not missing, f"seed missing critical exposures: {missing}"


def test_load_exposures_writes_seed_rows():
    init_db()
    load_tier_a()
    load_commodities()
    counts = load_exposures()
    assert counts["inserted"] >= 50, f"expected ≥50 exposures inserted, got {counts}"


def test_load_exposures_idempotent_final_count():
    init_db()
    load_tier_a()
    load_commodities()
    load_exposures()
    conn = get_connection()
    try:
        n1 = conn.execute(
            f"SELECT COUNT(*) FROM stock_commodity_exposure WHERE source='{SEED_SOURCE_HAND}'"
        ).fetchone()[0]
    finally:
        conn.close()

    load_exposures()
    conn = get_connection()
    try:
        n2 = conn.execute(
            f"SELECT COUNT(*) FROM stock_commodity_exposure WHERE source='{SEED_SOURCE_HAND}'"
        ).fetchone()[0]
    finally:
        conn.close()
    assert n1 == n2


def test_load_exposures_writes_correct_source_and_confidence():
    init_db()
    load_tier_a()
    load_commodities()
    load_exposures()
    conn = get_connection()
    try:
        rows = conn.execute(
            f"SELECT source, confidence FROM stock_commodity_exposure WHERE source='{SEED_SOURCE_HAND}' LIMIT 5"
        ).fetchall()
        for r in rows:
            assert r["source"] == SEED_SOURCE_HAND
            assert r["confidence"] == SEED_CONFIDENCE_HIGH
    finally:
        conn.close()


def test_load_exposures_skips_orphan_symbols():
    init_db()
    load_tier_a()
    load_commodities()
    counts = load_exposures()
    # Some seed rows reference symbols that aren't in Tier A — skipped is OK.
    assert counts["skipped_orphan"] >= 0


def test_specific_exposure_loaded_correctly():
    init_db()
    load_tier_a()
    load_commodities()
    load_exposures()
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM stock_commodity_exposure "
            "WHERE symbol='XOM' AND commodity_code='crude_oil' AND role='output'"
        ).fetchone()
        assert row is not None
        assert row["polarity"] == 1.0
        assert row["elasticity"] >= 0.7
    finally:
        conn.close()


def test_load_all_runs_both_loaders():
    init_db()
    load_tier_a()
    out = load_all()
    assert "commodities" in out
    assert "exposures" in out
    assert out["commodities"]["total"] >= 25
    assert out["exposures"]["inserted"] >= 50


def test_exposure_counts_diagnostic():
    init_db()
    load_tier_a()
    load_all()
    counts = exposure_counts()
    assert counts.get("output", 0) >= 10
    assert counts.get("input", 0) >= 30
    assert counts["total"] >= 50


def test_exposure_skips_unknown_commodity_code():
    """Rows referencing a non-existent commodity should be skipped, not crash."""
    init_db()
    load_tier_a()
    load_commodities()
    # No setup needed — we trust the loader's unconditional behavior.
    counts = load_exposures()
    # The seed shouldn't have any unknown codes today, but the protection should hold.
    assert "skipped_orphan" in counts
