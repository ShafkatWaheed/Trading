"""Tests for the 10-K Item 1A extractor.

Network (SEC EDGAR) and LLM (Claude CLI) are both mocked via injection. No
live calls happen during tests.
"""

from __future__ import annotations

from unittest.mock import patch  # audit: allow fake-data

import pytest

from src.data.sec_10k_extractor import (
    _build_extraction_prompt,
    _parse_concentration_pct,
    _strength_from_concentration,
    _strip_html,
    _write_relations_from_extraction,
    extract_item_1a,
    process_symbol,
)
from src.data.universe_loader import load_tier_a
from src.utils.db import get_connection, init_db


# ── HTML / text utilities ────────────────────────────────────────


def test_strip_html_removes_tags():
    out = _strip_html("<p>Hello <b>world</b></p>")
    assert out == "Hello world"


def test_strip_html_collapses_whitespace():
    out = _strip_html("<p>Hello\n\n   <b>world</b>  </p>")
    assert "  " not in out


def test_strip_html_handles_entities():
    out = _strip_html("AT&amp;T &nbsp; report")
    assert "AT&T" in out


def test_extract_item_1a_finds_section():
    text = (
        "Item 1. Business. Some content here. "
        "Item 1A. Risk Factors. We rely on TSM for our chips and Microsoft is a major customer. "
        "Item 1B. Other. Boring legal stuff."
    )
    out = extract_item_1a(text)
    assert out is not None
    assert "TSM" in out
    assert "Microsoft" in out
    assert "Item 1B" not in out
    assert "Boring" not in out


def test_extract_item_1a_returns_none_if_section_missing():
    text = "Just some boilerplate without the section header"
    assert extract_item_1a(text) is None


def test_extract_item_1a_supports_item_2_as_terminator():
    text = (
        "Item 1A: Risk Factors. We depend on suppliers. "
        "Item 2 - Properties. We own properties."
    )
    out = extract_item_1a(text)
    assert out is not None
    assert "depend on suppliers" in out
    assert "Properties" not in out


# ── prompt construction ──────────────────────────────────────────


def test_prompt_includes_symbol():
    prompt = _build_extraction_prompt("NVDA", "We depend on TSM for our chips.")
    assert "NVDA" in prompt


def test_prompt_truncates_long_text():
    long_text = "X" * 20_000
    prompt = _build_extraction_prompt("NVDA", long_text, max_chars=1000)
    assert "truncated" in prompt
    # Body should not contain the full 20k chars
    assert prompt.count("X") < 5_000


def test_prompt_requests_json():
    prompt = _build_extraction_prompt("NVDA", "irrelevant content")
    assert "JSON" in prompt or "json" in prompt


# ── _write_relations_from_extraction ─────────────────────────────


def test_writes_supplier_edges():
    """The function writes one stock_relations row per valid (in-universe) edge.

    Uses synthetic source stocks (no spine entries) so the test isolates the
    extractor's behavior from the hand-loaded spine.
    """
    init_db()
    load_tier_a()
    conn = get_connection()
    try:
        # Insert a synthetic source stock so we don't conflict with the spine
        conn.execute("DELETE FROM stocks_universe WHERE symbol='SYN_X'")
        conn.execute("DELETE FROM stock_relations WHERE from_symbol='SYN_X'")
        conn.execute(
            "INSERT INTO stocks_universe (symbol, tier, source) VALUES ('SYN_X', 'B', 'test')"
        )
        conn.commit()

        parsed = {
            "suppliers": [
                {"symbol": "TSM", "name": "Taiwan Semi", "evidence": "sole foundry"},
                {"symbol": "ASML", "name": "ASML Holding", "evidence": "EUV equipment"},
            ],
            "customers": [],
            "joint_ventures": [],
        }
        n = _write_relations_from_extraction(
            conn,
            symbol="SYN_X",
            parsed=parsed,
            valid_universe={"TSM", "ASML", "SYN_X"},
        )
        conn.commit()
        assert n == 2

        rows = conn.execute(
            "SELECT to_symbol, evidence FROM stock_relations WHERE from_symbol='SYN_X'"
        ).fetchall()
        targets = {r["to_symbol"] for r in rows}
        assert targets == {"TSM", "ASML"}
        # Synthetic source has no spine entries, so all evidence should be 10k_mined
        for r in rows:
            assert r["evidence"].startswith("10k_mined:")
    finally:
        conn.execute("DELETE FROM stock_relations WHERE from_symbol='SYN_X'")
        conn.execute("DELETE FROM stocks_universe WHERE symbol='SYN_X'")
        conn.commit()
        conn.close()


def test_skips_unknown_symbols():
    init_db()
    conn = get_connection()
    try:
        parsed = {
            "suppliers": [
                {"symbol": "GHOST_CORP", "name": "Ghost", "evidence": "x"},
            ],
            "customers": [],
            "joint_ventures": [],
        }
        n = _write_relations_from_extraction(
            conn,
            symbol="NVDA",
            parsed=parsed,
            valid_universe={"NVDA"},   # GHOST_CORP not in universe → skipped
        )
        assert n == 0
    finally:
        conn.close()


def test_skips_self_loop():
    init_db()
    conn = get_connection()
    try:
        parsed = {
            "suppliers": [{"symbol": "NVDA", "name": "self", "evidence": "x"}],
            "customers": [], "joint_ventures": [],
        }
        n = _write_relations_from_extraction(
            conn,
            symbol="NVDA",
            parsed=parsed,
            valid_universe={"NVDA"},
        )
        assert n == 0
    finally:
        conn.close()


def test_does_not_overwrite_hand_loaded_spine():
    """Hand seed has NVDA→TSM with evidence='seed:hand | …'. A 10k extraction
    that names TSM should NOT overwrite that evidence string."""
    from src.data.relations_seed_loader import load_spine
    init_db()
    load_tier_a()
    load_spine()
    conn = get_connection()
    try:
        # Pre-condition: NVDA→TSM exists with seed:hand evidence
        before = conn.execute(
            "SELECT evidence FROM stock_relations "
            "WHERE from_symbol='NVDA' AND to_symbol='TSM' AND relation_type='supplier'"
        ).fetchone()
        assert before["evidence"].startswith("seed:hand")

        # Now write a 10k_mined supplier edge for the same pair
        parsed = {
            "suppliers": [{"symbol": "TSM", "name": "TSMC", "evidence": "10k says foundry"}],
            "customers": [],
            "joint_ventures": [],
        }
        _write_relations_from_extraction(
            conn,
            symbol="NVDA",
            parsed=parsed,
            valid_universe={"NVDA", "TSM"},
        )
        conn.commit()

        # Evidence should STILL be the seed:hand one — UPSERT clause preserves it
        after = conn.execute(
            "SELECT evidence FROM stock_relations "
            "WHERE from_symbol='NVDA' AND to_symbol='TSM' AND relation_type='supplier'"
        ).fetchone()
        assert after["evidence"].startswith("seed:hand")
    finally:
        conn.close()


# ── process_symbol end-to-end (both fetch + extract mocked) ─────


def test_process_symbol_marks_done_on_success():
    init_db()
    load_tier_a()

    def fake_fetch(sym):
        return ("Item 1A: We depend on TSM for our foundry needs.", "https://example/10k")

    def fake_extract(prompt, **kw):
        return {
            "suppliers": [{"symbol": "TSM", "name": "Taiwan Semi", "evidence": "sole foundry"}],
            "customers": [],
            "joint_ventures": [],
        }

    out = process_symbol("NVDA", fetch_fn=fake_fetch, extract_fn=fake_extract)
    assert out["error"] is None

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT status, edges_written, filing_url FROM tenk_jobs WHERE symbol='NVDA'"
        ).fetchone()
        assert row["status"] == "done"
        assert row["filing_url"] == "https://example/10k"
        assert row["edges_written"] >= 1
    finally:
        conn.execute("DELETE FROM tenk_jobs WHERE symbol='NVDA'")
        conn.execute(
            "DELETE FROM stock_relations WHERE from_symbol='NVDA' AND evidence LIKE '10k_mined:%'"
        )
        conn.commit()
        conn.close()


def test_process_symbol_marks_failed_when_no_item_1a():
    init_db()
    load_tier_a()

    def fake_fetch(sym):
        return (None, "https://example/badfiling")

    out = process_symbol("MSFT", fetch_fn=fake_fetch)
    assert out["error"] == "no_item_1a"

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT status, error FROM tenk_jobs WHERE symbol='MSFT'"
        ).fetchone()
        assert row["status"] == "failed"
        assert row["error"]
    finally:
        conn.execute("DELETE FROM tenk_jobs WHERE symbol='MSFT'")
        conn.commit()
        conn.close()


def test_process_symbol_marks_failed_when_extraction_returns_none():
    init_db()
    load_tier_a()

    def fake_fetch(sym):
        return ("Item 1A. Some text.", "url")

    def fake_extract(prompt, **kw):
        return None    # parse failure

    out = process_symbol("AMZN", fetch_fn=fake_fetch, extract_fn=fake_extract)
    assert out["error"] == "extraction_failed"

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT status FROM tenk_jobs WHERE symbol='AMZN'"
        ).fetchone()
        assert row["status"] == "failed"
    finally:
        conn.execute("DELETE FROM tenk_jobs WHERE symbol='AMZN'")
        conn.commit()
        conn.close()


def test_process_symbol_skips_non_universe_extracted_targets():
    """Out-of-universe extracted symbols (BLAHCORP) get filtered; in-universe
    ones (TSM) get an edge attempt. Uses synthetic source stock to avoid
    spine collision."""
    init_db()
    load_tier_a()

    conn = get_connection()
    try:
        conn.execute("DELETE FROM stocks_universe WHERE symbol='SYN_Y'")
        conn.execute("DELETE FROM stock_relations WHERE from_symbol='SYN_Y'")
        conn.execute(
            "INSERT INTO stocks_universe (symbol, tier, source) VALUES ('SYN_Y', 'B', 'test')"
        )
        conn.commit()
    finally:
        conn.close()

    def fake_fetch(sym):
        return ("Item 1A. Suppliers.", "url")

    def fake_extract(prompt, **kw):
        return {
            "suppliers": [
                {"symbol": "TSM", "name": "TSMC", "evidence": "real"},
                {"symbol": "BLAHCORP", "name": "Fake", "evidence": "fake"},
            ],
            "customers": [],
            "joint_ventures": [],
        }

    out = process_symbol("SYN_Y", fetch_fn=fake_fetch, extract_fn=fake_extract)
    # TSM in universe → 1 edge written; BLAHCORP not → skipped
    assert out["edges_written"] == 1

    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT to_symbol FROM stock_relations WHERE from_symbol='SYN_Y'"
        ).fetchall()
        assert {r["to_symbol"] for r in rows} == {"TSM"}
    finally:
        conn.execute("DELETE FROM tenk_jobs WHERE symbol='SYN_Y'")
        conn.execute("DELETE FROM stock_relations WHERE from_symbol='SYN_Y'")
        conn.execute("DELETE FROM stocks_universe WHERE symbol='SYN_Y'")
        conn.commit()
        conn.close()


# ── Wave 1: concentration-pct → strength derivation ─────────────


def test_strength_from_concentration_thresholds():
    """Confirm the disclosed-% → strength mapping. Reg S-K Item 101 mandates
    disclosure for any customer ≥10% of revenue; we tier strength accordingly."""
    assert _strength_from_concentration(35) == 0.95   # >= 30
    assert _strength_from_concentration(30) == 0.95   # boundary
    assert _strength_from_concentration(25) == 0.80   # 20..30
    assert _strength_from_concentration(20) == 0.80   # boundary
    assert _strength_from_concentration(15) == 0.65   # 10..20
    assert _strength_from_concentration(10) == 0.65   # boundary
    assert _strength_from_concentration(5)  == 0.55   # below mandatory floor
    assert _strength_from_concentration(None) == 0.55  # named but not quantified


def test_parse_concentration_pct_normalizes_input():
    """Extractor JSON may pass int, float, str, or null. Out-of-range and
    non-numeric values normalize to None (default-strength path)."""
    assert _parse_concentration_pct(22) == 22.0
    assert _parse_concentration_pct(22.5) == 22.5
    assert _parse_concentration_pct("18") == 18.0
    assert _parse_concentration_pct(None) is None
    assert _parse_concentration_pct("not a number") is None
    assert _parse_concentration_pct(-5) is None      # negative — invalid
    assert _parse_concentration_pct(150) is None     # impossible — invalid


def test_writer_stores_concentration_pct_and_derives_strength():
    """A 10-K disclosure of '22% of revenue' should produce strength=0.80
    and persist the % in the new column."""
    init_db()
    conn = get_connection()
    try:
        conn.execute("DELETE FROM stocks_universe WHERE symbol IN ('SYN_CONC1','SYN_CONC2')")
        conn.execute("DELETE FROM stock_relations WHERE from_symbol='SYN_CONC1'")
        conn.execute(
            "INSERT INTO stocks_universe (symbol, tier, source) VALUES ('SYN_CONC1','B','test')"
        )
        conn.execute(
            "INSERT INTO stocks_universe (symbol, tier, source) VALUES ('SYN_CONC2','B','test')"
        )
        conn.commit()

        parsed = {
            "suppliers": [],
            "customers": [
                {"symbol": "SYN_CONC2", "name": "Bigco", "revenue_pct": 22,
                 "evidence": "22% of consolidated revenue"},
            ],
            "joint_ventures": [],
        }
        _write_relations_from_extraction(
            conn, symbol="SYN_CONC1", parsed=parsed,
            valid_universe={"SYN_CONC1", "SYN_CONC2"},
            filing_date="2024-04-15",
        )
        conn.commit()

        row = conn.execute(
            "SELECT strength, concentration_pct, source_filing_date, last_verified_at "
            "FROM stock_relations WHERE from_symbol='SYN_CONC1' AND to_symbol='SYN_CONC2'"
        ).fetchone()
        assert row is not None
        assert row["strength"] == 0.80
        assert row["concentration_pct"] == 22.0
        assert row["source_filing_date"] == "2024-04-15"
        assert row["last_verified_at"] is not None
    finally:
        conn.execute("DELETE FROM stock_relations WHERE from_symbol='SYN_CONC1'")
        conn.execute("DELETE FROM stocks_universe WHERE symbol IN ('SYN_CONC1','SYN_CONC2')")
        conn.commit()
        conn.close()


def test_writer_falls_back_to_default_strength_when_pct_missing():
    """No revenue_pct disclosed → strength stays at the default 0.55 (named
    but not quantified) and concentration_pct is NULL."""
    init_db()
    conn = get_connection()
    try:
        conn.execute("DELETE FROM stocks_universe WHERE symbol IN ('SYN_NOQ1','SYN_NOQ2')")
        conn.execute("DELETE FROM stock_relations WHERE from_symbol='SYN_NOQ1'")
        conn.execute("INSERT INTO stocks_universe (symbol, tier, source) VALUES ('SYN_NOQ1','B','test')")
        conn.execute("INSERT INTO stocks_universe (symbol, tier, source) VALUES ('SYN_NOQ2','B','test')")
        conn.commit()

        parsed = {
            "suppliers": [
                {"symbol": "SYN_NOQ2", "name": "Supp", "evidence": "named only"},
            ],
            "customers": [],
            "joint_ventures": [],
        }
        _write_relations_from_extraction(
            conn, symbol="SYN_NOQ1", parsed=parsed,
            valid_universe={"SYN_NOQ1", "SYN_NOQ2"},
        )
        conn.commit()
        row = conn.execute(
            "SELECT strength, concentration_pct FROM stock_relations "
            "WHERE from_symbol='SYN_NOQ1' AND to_symbol='SYN_NOQ2'"
        ).fetchone()
        assert row["strength"] == 0.55
        assert row["concentration_pct"] is None
    finally:
        conn.execute("DELETE FROM stock_relations WHERE from_symbol='SYN_NOQ1'")
        conn.execute("DELETE FROM stocks_universe WHERE symbol IN ('SYN_NOQ1','SYN_NOQ2')")
        conn.commit()
        conn.close()


def test_hand_seed_strength_and_pct_are_preserved():
    """A hand-seeded edge (evidence LIKE 'seed:hand%') must not have its strength,
    evidence, or concentration_pct overwritten by a subsequent 10-K mining."""
    from src.data.relations_seed_loader import load_spine
    init_db()
    load_tier_a()
    load_spine()
    conn = get_connection()
    try:
        before = conn.execute(
            "SELECT strength, evidence, concentration_pct FROM stock_relations "
            "WHERE from_symbol='NVDA' AND to_symbol='TSM' AND relation_type='supplier'"
        ).fetchone()
        # Hand seed for NVDA→TSM is strength=0.95, evidence='seed:hand | …', no pct
        assert before["evidence"].startswith("seed:hand")
        hand_strength = before["strength"]

        # 10-K mining now reports TSM with a (hypothetical) 22% disclosure.
        # The writer should still leave the hand row alone.
        parsed = {
            "suppliers": [
                {"symbol": "TSM", "name": "TSMC", "revenue_pct": 22,
                 "evidence": "10-K text"},
            ],
            "customers": [],
            "joint_ventures": [],
        }
        _write_relations_from_extraction(
            conn, symbol="NVDA", parsed=parsed,
            valid_universe={"NVDA", "TSM"},
        )
        conn.commit()

        after = conn.execute(
            "SELECT strength, evidence, concentration_pct FROM stock_relations "
            "WHERE from_symbol='NVDA' AND to_symbol='TSM' AND relation_type='supplier'"
        ).fetchone()
        assert after["strength"] == hand_strength
        assert after["evidence"].startswith("seed:hand")
        assert after["concentration_pct"] is None
    finally:
        conn.close()
