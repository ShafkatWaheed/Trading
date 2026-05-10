"""Tests for the 10-K Item 1A extractor.

Network (SEC EDGAR) and LLM (Claude CLI) are both mocked via injection. No
live calls happen during tests.
"""

from __future__ import annotations

from unittest.mock import patch  # audit: allow fake-data

import pytest

from src.data.sec_10k_extractor import (
    _build_extraction_prompt,
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
