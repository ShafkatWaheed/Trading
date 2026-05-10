"""Tests for the industries reference seed."""

from __future__ import annotations

from src.data.industries_seed import (
    INDUSTRIES,
    industries_by_sector,
    industries_count,
    load_industries,
)
from src.utils.db import get_connection, init_db


def test_industry_count_in_target_range():
    n = industries_count()
    assert 100 <= n <= 200, f"expected ~150 industries, got {n}"


def test_no_duplicate_industry_codes():
    codes = [code for code, _ in INDUSTRIES]
    assert len(codes) == len(set(codes)), "duplicate industry code in seed"


def test_every_row_has_non_empty_sector():
    for code, sector in INDUSTRIES:
        assert code, "empty industry code"
        assert sector, f"empty sector for {code}"


def test_covers_all_eleven_gics_sectors():
    sectors = {sector for _, sector in INDUSTRIES}
    expected = {
        "Technology",
        "Communication Services",
        "Consumer Cyclical",
        "Consumer Defensive",
        "Healthcare",
        "Financial Services",
        "Energy",
        "Industrials",
        "Basic Materials",
        "Real Estate",
        "Utilities",
    }
    missing = expected - sectors
    assert not missing, f"missing sectors: {missing}"


def test_critical_industries_present():
    """Spot-check that key industries the prototype depends on exist."""
    codes = {code for code, _ in INDUSTRIES}
    must_have = {
        "Semiconductors",
        "Semiconductor Equipment & Materials",
        "Aerospace & Defense",
        "Oil & Gas E&P",
        "Oil & Gas Refining & Marketing",
        "Drug Manufacturers—General",
        "Healthcare Plans",
        "Banks—Diversified",
        "Software—Infrastructure",
        "Software—Application",
        "Uranium",                      # nuclear/AI-power thesis
        "Electrical Equipment & Parts", # GEV / ETN / VRT
        "Utilities—Regulated Electric",
        "REIT—Specialty",               # data-center REITs
    }
    missing = must_have - codes
    assert not missing, f"missing critical industries: {missing}"


def test_industries_by_sector_groups_correctly():
    grouped = industries_by_sector()
    # Each sector should have at least 5 industries.
    for sector, industries in grouped.items():
        assert len(industries) >= 5, f"sector {sector} has only {len(industries)} industries"


# ── loader behavior ────────────────────────────────────────────────


def test_load_industries_inserts_all_seed_rows():
    init_db()
    conn = get_connection()
    try:
        conn.execute(
            "DELETE FROM industries WHERE code IN (" +
            ",".join("?" * len(INDUSTRIES)) + ")",
            [code for code, _ in INDUSTRIES],
        )
        conn.commit()
    finally:
        conn.close()

    counts = load_industries()
    assert counts["inserted"] == industries_count()

    conn = get_connection()
    try:
        for code, expected_sector in INDUSTRIES:
            row = conn.execute(
                "SELECT sector FROM industries WHERE code=?", (code,)
            ).fetchone()
            assert row is not None, f"industry not loaded: {code}"
            assert row["sector"] == expected_sector
    finally:
        conn.close()


def test_load_industries_idempotent():
    load_industries()
    second = load_industries()
    assert second["inserted"] == 0
    assert second["updated"] == industries_count()
