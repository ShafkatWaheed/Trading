"""Tests for the SEC 13F loader (Phase 7A).

Network (SEC EDGAR) is mocked. CUSIP resolution is mocked too because the
default resolver matches against stocks_universe.name with prefix patterns
that are realistic but unsuitable for tests.
"""

from __future__ import annotations

import pytest

from src.data.institutions_seed_loader import load_institutions
from src.data.sec_13f_loader import (
    parse_13f_holdings_xml,
    process_institution,
)
from src.data.universe_loader import load_tier_a
from src.utils.db import get_connection, init_db


# ── XML parsing ──────────────────────────────────────────────────


SAMPLE_13F_XML = """<?xml version="1.0"?>
<informationTable>
  <infoTable>
    <nameOfIssuer>NVIDIA CORP</nameOfIssuer>
    <titleOfClass>COM</titleOfClass>
    <cusip>67066G104</cusip>
    <value>5000000</value>
    <sshPrnamt>1500000</sshPrnamt>
  </infoTable>
  <infoTable>
    <nameOfIssuer>MICROSOFT CORP</nameOfIssuer>
    <titleOfClass>COM</titleOfClass>
    <cusip>594918104</cusip>
    <value>4500000</value>
    <sshPrnamt>900000</sshPrnamt>
  </infoTable>
  <infoTable>
    <nameOfIssuer>BROKEN ROW NO CUSIP</nameOfIssuer>
    <value>100</value>
  </infoTable>
</informationTable>"""


def test_parse_13f_extracts_holdings():
    out = parse_13f_holdings_xml(SAMPLE_13F_XML)
    assert len(out) == 2
    nvda = next(h for h in out if "NVIDIA" in h["name"])
    # 13F values are in $ thousands → 5_000_000 thousand = $5B
    assert nvda["value_usd"] == 5_000_000_000
    assert nvda["cusip"] == "67066G104"
    assert nvda["shares"] == 1_500_000


def test_parse_13f_skips_malformed_rows():
    out = parse_13f_holdings_xml(SAMPLE_13F_XML)
    # The "BROKEN ROW NO CUSIP" entry should be skipped silently
    assert all("BROKEN" not in h["name"] for h in out)


def test_parse_13f_returns_empty_on_no_matches():
    out = parse_13f_holdings_xml("not xml at all")
    assert out == []


def test_parse_13f_handles_lowercase_tags():
    """Some filings use lowercase tag names — the regex is case-insensitive."""
    xml = """<infoTable>
      <nameofissuer>APPLE INC</nameofissuer>
      <cusip>037833100</cusip>
      <value>1000</value>
    </infoTable>"""
    out = parse_13f_holdings_xml(xml)
    assert len(out) == 1
    assert "APPLE" in out[0]["name"]


# ── process_institution end-to-end (mocked) ──────────────────────


def test_process_institution_writes_holdings(monkeypatch):
    init_db()
    load_tier_a()
    load_institutions()

    # Mocked fetch: returns the sample XML and a period
    def fake_fetch(cik):
        return SAMPLE_13F_XML, "2026-03-31"

    # Mocked CUSIP resolver: matches NVIDIA→NVDA, MICROSOFT→MSFT
    def fake_resolve(cusip, name):
        if "NVIDIA" in name.upper():
            return "NVDA"
        if "MICROSOFT" in name.upper():
            return "MSFT"
        return None

    out = process_institution(
        "1364742",
        fetch_fn=fake_fetch,
        resolve_fn=fake_resolve,
    )
    assert out["error"] is None
    assert out["rows_written"] == 2

    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT symbol, value_usd, source, as_of FROM institution_holdings "
            "WHERE cik='1364742' AND source='13F' ORDER BY value_usd DESC"
        ).fetchall()
        assert len(rows) == 2
        assert rows[0]["symbol"] == "NVDA"
        assert rows[0]["value_usd"] == 5_000_000_000
        assert rows[0]["as_of"] == "2026-03-31"
    finally:
        conn.execute("DELETE FROM institution_holdings WHERE source='13F'")
        conn.commit()
        conn.close()


def test_process_institution_returns_error_on_no_filing(monkeypatch):
    def fake_fetch(cik):
        return None, None

    out = process_institution("1364742", fetch_fn=fake_fetch)
    assert out["error"] == "no_filing"
    assert out["rows_written"] == 0


def test_process_institution_skips_unresolved_cusips(monkeypatch):
    init_db()
    load_tier_a()
    load_institutions()

    def fake_fetch(cik):
        return SAMPLE_13F_XML, "2026-03-31"

    def fake_resolve(cusip, name):
        # Always returns None — no CUSIPs resolve
        return None

    out = process_institution("102909", fetch_fn=fake_fetch, resolve_fn=fake_resolve)
    assert out["rows_written"] == 0


def test_process_institution_skips_off_universe_symbols(monkeypatch):
    """A CUSIP that resolves to a symbol not in stocks_universe is skipped."""
    init_db()
    load_tier_a()
    load_institutions()

    def fake_fetch(cik):
        return SAMPLE_13F_XML, "2026-03-31"

    def fake_resolve(cusip, name):
        return "ZZZ_NOT_REAL"   # not in stocks_universe

    out = process_institution("93751", fetch_fn=fake_fetch, resolve_fn=fake_resolve)
    assert out["rows_written"] == 0


def test_process_institution_computes_pct_portfolio(monkeypatch):
    """pct_portfolio = value / total_value of all holdings × 100."""
    init_db()
    load_tier_a()
    load_institutions()

    def fake_fetch(cik):
        return SAMPLE_13F_XML, "2026-03-31"

    def fake_resolve(cusip, name):
        return {"NVIDIA": "NVDA", "MICROSOFT": "MSFT"}.get(name.split()[0])

    process_institution("1364742", fetch_fn=fake_fetch, resolve_fn=fake_resolve)

    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT symbol, pct_portfolio FROM institution_holdings "
            "WHERE cik='1364742' AND source='13F'"
        ).fetchall()
        # 5B + 4.5B = 9.5B total. NVDA's pct = 5/9.5 ≈ 52.6%
        nvda = next(r for r in rows if r["symbol"] == "NVDA")
        assert 50 < nvda["pct_portfolio"] < 55
    finally:
        conn.execute("DELETE FROM institution_holdings WHERE source='13F'")
        conn.commit()
        conn.close()
