"""universe_service.search — universe-wide ticker/name autocomplete.

Verifies the /stocks/search backend now suggests from the full stocks_universe
(not the 69-symbol STOCK_DB), with prefix/exact ranking and a sector hint.
Temp DB + synthetic SYN_* symbols (CLAUDE.md test isolation).
"""
from __future__ import annotations

import pytest

from api.services import universe_service
from src.utils.db import get_connection, init_db


@pytest.fixture(autouse=True)
def _seed():
    """Seed synthetic universe rows, then remove them so tier counts elsewhere
    (test_universe_schema asserts counts['A'] == tier_a_count()) stay clean."""
    init_db()
    conn = get_connection()
    try:
        conn.execute("DELETE FROM stocks_universe WHERE source='test'")
        conn.execute("DELETE FROM stock_industry WHERE source='test'")
        rows = [
            ("SYN_MA", "Synthetic Mastercard", "B"),
            ("SYN_MAR", "Synthetic Marriott", "B"),
            ("SYN_NAME", "Mastery Holdings", "C"),   # name-only match for "Mastery"
            ("SYN_TA", "Synthetic Tier A", "A"),
            ("SYN_TB", "Synthetic Tier B", "B"),
            ("SYN_ZZZ", "Unrelated Inc", "A"),
        ]
        for sym, name, tier in rows:
            conn.execute(
                "INSERT INTO stocks_universe (symbol, name, tier, source) VALUES (?,?,?,'test')",
                (sym, name, tier),
            )
        conn.execute(
            "INSERT INTO stock_industry (symbol, industry_code, weight, is_primary, source) "
            "VALUES ('SYN_MA','Credit Services',1.0,1,'test')"
        )
        conn.execute(
            "INSERT OR IGNORE INTO industries (code, sector) VALUES ('Credit Services','Financial Services')"
        )
        conn.commit()
    finally:
        conn.close()
    yield
    conn = get_connection()
    try:
        conn.execute("DELETE FROM stocks_universe WHERE source='test'")
        conn.execute("DELETE FROM stock_industry WHERE source='test'")
        conn.commit()
    finally:
        conn.close()


def test_exact_symbol_ranks_before_prefix():
    res = universe_service.search("SYN_MA")
    syms = [r["symbol"] for r in res]
    assert "SYN_MA" in syms and "SYN_MAR" in syms
    assert syms.index("SYN_MA") < syms.index("SYN_MAR")  # exact before prefix


def test_name_fragment_matches():
    res = universe_service.search("Mastery")
    syms = [r["symbol"] for r in res]
    assert syms == ["SYN_NAME"]


def test_tier_a_ranks_before_tier_b_at_same_match_rank():
    res = universe_service.search("SYN_T")
    syms = [r["symbol"] for r in res]
    assert syms == ["SYN_TA", "SYN_TB"]  # both prefix matches; A outranks B


def test_sector_hint_from_industries_join():
    res = universe_service.search("SYN_MA")
    by_sym = {r["symbol"]: r for r in res}
    assert by_sym["SYN_MA"]["sector"] == "Financial Services"
    assert by_sym["SYN_MAR"]["sector"] is None  # no industry row → null


def test_empty_query_returns_empty():
    assert universe_service.search("   ") == []


def test_limit_is_respected():
    res = universe_service.search("SYN_", limit=2)
    assert len(res) == 2
