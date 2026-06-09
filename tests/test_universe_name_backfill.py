"""Backfill stocks_universe.name for nameless rows from the Nasdaq directory.

Temp DB + synthetic SYN_* rows + injected name_map (no network).
CLAUDE.md test isolation: synthetic symbols, source='test', never prod DB.
"""
from __future__ import annotations

from src.data.nasdaq_listings_loader import (
    _clean_security_name,
    backfill_universe_names,
    parse_otherlisted,
)
from src.utils.db import get_connection, init_db

_OTHER_SAMPLE = """ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol
A|Agilent Technologies, Inc. Common Stock|N|A|N|100|N|A
AA|Alcoa Corporation Common Stock|N|AA|N|100|N|AA
SPY|SPDR S&P 500 ETF Trust|P|SPY|Y|100|N|SPY
TST|Test Co Common Stock|N|TST|N|100|Y|TST
File Creation Time: 0526202612:00|||||||"""


def test_clean_strips_security_type_descriptors():
    assert _clean_security_name("Apple Inc. - Common Stock") == "Apple Inc."
    assert (
        _clean_security_name("Agilent Technologies, Inc. Common Stock")
        == "Agilent Technologies, Inc."
    )
    assert (
        _clean_security_name(
            "ATA Creativity Global - American Depositary Shares, each representing two"
        )
        == "ATA Creativity Global"
    )
    # class designation is informative — kept; only the trailing 'Common Stock' drops
    assert (
        _clean_security_name("Berkshire Hathaway Inc. Class B Common Stock")
        == "Berkshire Hathaway Inc. Class B"
    )


def test_parse_otherlisted_skips_etf_test_and_footer():
    rows = parse_otherlisted(_OTHER_SAMPLE)
    syms = {r["symbol"] for r in rows}
    assert syms == {"A", "AA"}  # SPY (ETF), TST (test), footer all excluded
    by_sym = {r["symbol"]: r for r in rows}
    assert by_sym["AA"]["security_name"] == "Alcoa Corporation Common Stock"


def test_parse_otherlisted_handles_empty():
    assert parse_otherlisted("") == []


def _seed_nameless():
    init_db()
    conn = get_connection()
    try:
        conn.execute("DELETE FROM stocks_universe WHERE source='test'")
        conn.execute(
            "INSERT INTO stocks_universe (symbol, name, tier, source) VALUES ('SYN_BB', NULL, 'B', 'test')"
        )
        conn.execute(
            "INSERT INTO stocks_universe (symbol, name, tier, source) VALUES ('SYN_CC', '', 'C', 'test')"
        )
        conn.execute(
            "INSERT INTO stocks_universe (symbol, name, tier, source) VALUES ('SYN_AA', 'Existing Name Inc', 'A', 'test')"
        )
        conn.commit()
    finally:
        conn.close()


def _cleanup():
    conn = get_connection()
    try:
        conn.execute("DELETE FROM stocks_universe WHERE source='test'")
        conn.commit()
    finally:
        conn.close()


def test_backfill_fills_only_empty_names_never_overwrites():
    _seed_nameless()
    name_map = {
        "SYN_BB": "Synthetic BB Corp",
        "SYN_CC": "Synthetic CC Inc",
        "SYN_AA": "WRONG Should Not Overwrite",
    }
    res = backfill_universe_names(name_map)
    conn = get_connection()
    try:
        names = {
            r["symbol"]: r["name"]
            for r in conn.execute(
                "SELECT symbol, name FROM stocks_universe WHERE source='test'"
            )
        }
    finally:
        conn.close()
    _cleanup()
    assert names["SYN_BB"] == "Synthetic BB Corp"
    assert names["SYN_CC"] == "Synthetic CC Inc"
    assert names["SYN_AA"] == "Existing Name Inc"  # untouched — not overwritten
    assert res["filled"] == 2  # only the two nameless mapped rows


def test_backfill_reports_remaining_when_map_incomplete():
    _seed_nameless()
    res = backfill_universe_names({"SYN_BB": "Only BB Corp"})
    _cleanup()
    assert res["filled"] == 1  # only SYN_BB mapped
    assert res["remaining"] >= 1  # SYN_CC unmapped
