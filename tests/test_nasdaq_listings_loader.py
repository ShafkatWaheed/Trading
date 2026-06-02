"""Tests for the NASDAQ listings loader (Tier D source)."""
from __future__ import annotations

import pytest

from src.data.nasdaq_listings_loader import (
    apply_nasdaq_listings,
    parse_nasdaqlisted,
)
from src.utils.db import get_connection, init_db


_SAMPLE = """Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares
AAPL|Apple Inc. - Common Stock|Q|N|N|100|N|N
MSFT|Microsoft Corp - Common Stock|Q|N|N|100|N|N
BIGCO|Big Mid-Cap Inc - Common Stock|G|N|N|100|N|N
TINY|Tiny Micro Cap Inc - Common Stock|S|N|N|100|N|N
SCAM|Scam Penny Stock - Common Stock|S|N|D|100|N|N
ETF1|Index Tracker ETF|S|N|N|100|Y|N
TEST|Test Issue|Q|Y|N|100|N|N
File Creation Time: 0526202612:00|||||||"""


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    """Per-test temp DB so we can assert exact row counts on stocks_universe."""
    from src.utils import db
    test_db = tmp_path / "t.db"
    monkeypatch.setattr(db, "DB_PATH", test_db)
    init_db()
    yield test_db


def test_parse_skips_etf_and_test_issues():
    rows = parse_nasdaqlisted(_SAMPLE)
    syms = {r["symbol"] for r in rows}
    assert syms == {"AAPL", "MSFT", "BIGCO", "TINY", "SCAM"}
    # ETF1 and TEST must be filtered out
    assert "ETF1" not in syms
    assert "TEST" not in syms


def test_parse_pulls_market_category():
    rows = parse_nasdaqlisted(_SAMPLE)
    by_sym = {r["symbol"]: r for r in rows}
    assert by_sym["AAPL"]["market_category"] == "Q"
    assert by_sym["BIGCO"]["market_category"] == "G"
    assert by_sym["TINY"]["market_category"] == "S"


def test_parse_handles_empty_text():
    assert parse_nasdaqlisted("") == []


def test_parse_ignores_footer_line():
    rows = parse_nasdaqlisted(_SAMPLE)
    syms = {r["symbol"] for r in rows}
    assert "File Creation Time" not in syms


def test_apply_inserts_capital_market_only_by_default(fresh_db):
    rows = parse_nasdaqlisted(_SAMPLE)
    res = apply_nasdaq_listings(rows)
    assert res["inserted"] == 2  # TINY + SCAM (Capital Market 'S')
    # AAPL, MSFT (Q), BIGCO (G) all skipped — only_capital_market=True
    conn = get_connection()
    rows_in_db = conn.execute("SELECT symbol, tier FROM stocks_universe").fetchall()
    conn.close()
    assert {r["symbol"] for r in rows_in_db} == {"TINY", "SCAM"}
    assert {r["tier"] for r in rows_in_db} == {"D"}


def test_apply_does_not_downgrade_existing_higher_tier(fresh_db):
    # Seed a TINY row as Tier B (e.g., it appeared in Russell)
    conn = get_connection()
    conn.execute(
        "INSERT INTO stocks_universe (symbol, name, tier, source) VALUES (?, ?, 'B', 'index_loader')",
        ("TINY", "Tiny Micro Cap Inc"),
    )
    conn.commit()
    conn.close()

    rows = parse_nasdaqlisted(_SAMPLE)
    res = apply_nasdaq_listings(rows)
    # TINY should be skipped (existing B); SCAM is the only true new insert
    assert res["inserted"] == 1
    assert res["skipped_existing_higher"] == 1

    conn = get_connection()
    row = conn.execute("SELECT tier FROM stocks_universe WHERE symbol='TINY'").fetchone()
    conn.close()
    assert row["tier"] == "B"  # unchanged


def test_apply_all_market_categories_when_requested(fresh_db):
    rows = parse_nasdaqlisted(_SAMPLE)
    res = apply_nasdaq_listings(rows, only_capital_market=False)
    # Q and G should slot in as Tier C via classify_tier(nasdaq_market_tier=...)
    assert res["inserted"] == 5

    conn = get_connection()
    by_tier = {}
    for r in conn.execute("SELECT symbol, tier FROM stocks_universe").fetchall():
        by_tier.setdefault(r["tier"], []).append(r["symbol"])
    conn.close()
    assert set(by_tier.get("C", [])) == {"AAPL", "MSFT", "BIGCO"}
    assert set(by_tier.get("D", [])) == {"TINY", "SCAM"}
